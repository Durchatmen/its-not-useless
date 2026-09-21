"""导航接口（接口文档 3.6.1：API-20 院外导航）。

本文件只做 HTTP 适配：把 query 参数组装成 `OutdoorNavQuery`，调用
`services/navigation_service.outdoor_navigation`，套统一信封。高德的调用细节、
多方案拼装、静态图与 POI 都在 service 层。

前端契约：frontend/src/api/navigation.js 的 getOutdoorNavigation()
    GET /navigation/outdoor?originLng=&originLat=&mode=driving

⚠ 参数名有两处不一致，本接口按「文档是权威契约、前端硬约束也不能破」两个都收：
  1. 坐标：文档是 latitude / longitude，前端传的是 originLat / originLng。
  2. 出行方式：文档是 DRIVE / BUS / WALK / RIDE，前端传的是小写 driving。
     大写优先，小写与 driving 都映射到 DRIVE。

⚠ 院内导航（API-21）**不在本期范围**：前端 navigation.js 里还留着 getIndoorNavigation，
   但它调用的 /navigation/indoor 在本后端不存在，会返回 404。这是已知的遗留入口，
   处理方式见交付说明（前端应下线该调用，或后端后续补实现）。
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user
from app.core.errors import BizError
from app.core.response import Envelope
from app.models import User
from app.schemas.navigation import DestType, OutdoorNavQuery, TravelMode
from app.services import navigation_service

router = APIRouter(prefix="/navigation", tags=["院外导航"])

UserDep = Annotated[User, Depends(get_current_user)]

# 前端传的是小写出行方式（'driving'），文档是大写枚举；这张表把两者对齐。
# 'transit'/'bus' 都归 BUS：高德的公交接口就一个，前端两种叫法都可能出现。
_MODE_ALIASES: dict[str, TravelMode] = {
    "drive": TravelMode.DRIVE,
    "driving": TravelMode.DRIVE,
    "car": TravelMode.DRIVE,
    "bus": TravelMode.BUS,
    "transit": TravelMode.BUS,
    "walk": TravelMode.WALK,
    "walking": TravelMode.WALK,
    "ride": TravelMode.RIDE,
    "riding": TravelMode.RIDE,
    "bicycling": TravelMode.RIDE,
}


def _resolve_mode(raw: Optional[str]) -> Optional[TravelMode]:
    """出行方式归一化：不传 → None（返回全部方案对比）；认不出来 → 4001。"""
    if not raw or not raw.strip():
        return None
    key = raw.strip().lower()
    mode = _MODE_ALIASES.get(key)
    if mode is None:
        raise BizError(4001, f"出行方式取值不合法：{raw}（可选 DRIVE/BUS/WALK/RIDE）")
    return mode


def _resolve_dest_type(raw: Optional[str]) -> DestType:
    """目的地类型归一化：不传默认 GATE（文档默认值）。"""
    if not raw or not raw.strip():
        return DestType.GATE
    try:
        return DestType(raw.strip().upper())
    except ValueError as exc:
        raise BizError(4001, f"目的地类型取值不合法：{raw}（可选 GATE/PARKING）") from exc


@router.get("/outdoor", summary="API-20 院外导航")
def get_outdoor_navigation(
    user: UserDep,
    latitude: Annotated[
        Optional[float], Query(ge=-90, le=90, description="用户纬度（文档参数名）")
    ] = None,
    longitude: Annotated[
        Optional[float], Query(ge=-180, le=180, description="用户经度（文档参数名）")
    ] = None,
    originLat: Annotated[
        Optional[float],
        Query(ge=-90, le=90, description="用户纬度（前端 navigation.js 的参数名，等价于 latitude）"),
    ] = None,
    originLng: Annotated[
        Optional[float],
        Query(ge=-180, le=180, description="用户经度（前端 navigation.js 的参数名，等价于 longitude）"),
    ] = None,
    mode: Annotated[
        Optional[str],
        Query(description="出行方式：DRIVE 驾车 / BUS 公交 / WALK 步行 / RIDE 骑行；不传返回全部方案对比"),
    ] = None,
    destType: Annotated[
        Optional[str], Query(description="目的地类型：GATE 医院主入口（默认）/ PARKING 停车场")
    ] = None,
    hospitalCode: Annotated[
        Optional[str], Query(description="目标医院编码，不传为当前院区")
    ] = None,
) -> Any:
    """规划从用户当前位置到医院的院外路线，返回多出行方式方案对比与一键导航链接。

    响应含各方案耗时/里程/拥堵/换乘摘要、高德地图缩略图、唤起高德 APP 的链接，
    destType=PARKING 时还带医院周边停车场余位提示。
    高德服务不可用（未配 Key 或调用失败）返回 5004。
    """
    # 前端字段优先：两个都传时以 originLat/originLng 为准（那是实际会被发出的字段）
    lat = originLat if originLat is not None else latitude
    lng = originLng if originLng is not None else longitude
    if lat is None or lng is None:
        raise BizError(4001, "缺少定位坐标：latitude/longitude（或前端别名 originLat/originLng）")

    query = OutdoorNavQuery(
        latitude=lat,
        longitude=lng,
        hospitalCode=hospitalCode,
        mode=_resolve_mode(mode),
        destType=_resolve_dest_type(destType),
    )
    # navigation_service 直接抛 BizError(4001/5004)，不需要转换，冒泡给全局处理器
    return Envelope.ok(navigation_service.outdoor_navigation(query))


__all__ = ["router"]
