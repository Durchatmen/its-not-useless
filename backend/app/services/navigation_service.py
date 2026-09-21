"""院外智能导航（《功能设计文档》3.3 院外导航、《接口文档》3.6 API-20）。

按用户经纬度调用高德路径规划，返回驾车/公交/步行/骑行方案对比、里程与耗时、
红绿灯与拥堵情况、静态地图缩略图、一键唤起高德 APP 的实时导航链接，
并在目的地为停车场时附带周边停车场引导。

院内导航不在本期范围，因此不做围栏切换与楼层路径计算。
"""

from __future__ import annotations

import logging
import math

from app.core.config import settings
from app.core.errors import BizError, ErrorCode
from app.schemas.navigation import (
    DestType,
    GeoCoord,
    OutdoorNavData,
    OutdoorNavQuery,
    ParkingOption,
    RouteOption,
    TravelMode,
)
from app.services import amap

logger = logging.getLogger(__name__)

MODE_TEXT: dict[TravelMode, str] = {
    TravelMode.DRIVE: "驾车",
    TravelMode.BUS: "公交/地铁",
    TravelMode.WALK: "步行",
    TravelMode.RIDE: "骑行",
}
# 未指定 mode 时按此顺序返回全部方案对比
_MODE_ORDER = (TravelMode.DRIVE, TravelMode.BUS, TravelMode.WALK, TravelMode.RIDE)

_EARTH_RADIUS_M = 6371008.8


# --------------------------------------------------------------------------- #
# 位置计算
# --------------------------------------------------------------------------- #


def hospital_coord() -> tuple[float, float]:
    """医院坐标：(经度, 纬度)。"""
    return settings.hospital_longitude, settings.hospital_latitude


def gate_coord() -> tuple[float, float]:
    """医院主入口坐标；未单独配置时回落到医院坐标。"""
    if settings.hospital_gate_longitude and settings.hospital_gate_latitude:
        return settings.hospital_gate_longitude, settings.hospital_gate_latitude
    return hospital_coord()


def haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    """两个 (经度, 纬度) 之间的球面直线距离（米），用于“距离您 X 公里”。"""
    lon1, lat1 = a
    lon2, lat2 = b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


# --------------------------------------------------------------------------- #
# API-20 院外导航
# --------------------------------------------------------------------------- #


def outdoor_navigation(query: OutdoorNavQuery) -> OutdoorNavData:
    """院外导航：路径规划 + 方案对比 + 静态地图 + 唤起高德链接。"""
    hospital_code = query.hospitalCode or settings.hospital_code
    if hospital_code != settings.hospital_code:
        raise BizError(ErrorCode.PARAM_INVALID, f"未知医院编码：{hospital_code}")

    origin = (query.longitude, query.latitude)
    destination = gate_coord() if query.destType is DestType.GATE else hospital_coord()
    destination_name = "停车场" if query.destType is DestType.PARKING else "主入口"

    origin_text = _amap_location(origin)
    destination_text = _amap_location(destination)

    modes = (query.mode,) if query.mode else _MODE_ORDER
    routes: list[RouteOption] = []
    for mode in modes:
        estimate = _estimate(mode, origin_text, destination_text)
        if estimate is not None:
            routes.append(_to_route_option(mode, estimate))
    if not routes:
        raise BizError(ErrorCode.AMAP_FAILED, "未规划出可用路线，请稍后重试")

    return OutdoorNavData(
        distanceText=f"距离您 {_format_meters(haversine_meters(origin, destination))}",
        hospitalName=settings.hospital_name,
        hospitalCoord=_geo(hospital_coord()),
        destType=query.destType,
        destCoord=_geo(destination),
        routes=routes,
        staticMapUrl=(
            amap.static_map(origin=origin_text, destination=destination_text)
            if settings.amap_web_key
            else None
        ),
        amapNavigationUrl=amap.navigation_uri(
            origin=origin_text,
            destination=destination_text,
            origin_name="我的位置",
            destination_name=f"{settings.hospital_name}{destination_name}",
            mode=_uri_mode(query.mode),
        ),
        parkingOptions=_parking_options(destination) if query.destType is DestType.PARKING else [],
    )


def _estimate(mode: TravelMode, origin: str, destination: str) -> amap.RouteEstimate | None:
    """按出行方式调用高德路径规划。"""
    if mode is TravelMode.DRIVE:
        return amap.driving(origin, destination)
    if mode is TravelMode.BUS:
        return amap.transit(origin, destination)
    if mode is TravelMode.WALK:
        return amap.walking(origin, destination)
    if mode is TravelMode.RIDE:
        return amap.bicycling(origin, destination)
    return None


def _to_route_option(mode: TravelMode, estimate: amap.RouteEstimate) -> RouteOption:
    return RouteOption(
        mode=mode,
        modeText=MODE_TEXT[mode],
        durationText=f"{MODE_TEXT[mode]}约{_format_duration(estimate.duration)}",
        distanceText=_format_meters(estimate.distance),
        trafficText=_traffic_text(estimate) if mode is TravelMode.DRIVE else None,
        transferText=estimate.transfer_text if mode is TravelMode.BUS else None,
        walkDistance=estimate.walk_distance,
    )


def _traffic_text(estimate: amap.RouteEstimate) -> str | None:
    """红绿灯数量与拥堵情况（接口文档 API-20 routes.trafficText）。"""
    parts: list[str] = []
    if estimate.traffic_lights is not None:
        parts.append(f"红绿灯{estimate.traffic_lights}个")
    if estimate.congestion:
        parts.append(f"路况以{estimate.congestion}为主")
    return "，".join(parts) or None


def _parking_options(center: tuple[float, float]) -> list[ParkingOption]:
    """停车场引导（《功能设计文档》导航补充建议）。

    停车余位需对接医院停车管理系统，当前只返回周边停车场与提示文案；
    检索失败不影响主流程，直接省略停车引导。
    """
    try:
        pois = amap.place_around("停车场", center=_amap_location(center), radius=2000, page_size=5)
    except BizError as exc:
        logger.warning("停车场检索失败，跳过停车引导：%s", exc)
        return []

    options: list[ParkingOption] = []
    for poi in pois:
        if not isinstance(poi, dict):
            continue
        distance = _as_float(poi.get("distance"))
        coord = _parse_coord(poi.get("location"))
        options.append(
            ParkingOption(
                name=str(poi.get("name") or "停车场"),
                distanceText=(
                    f"距医院约{int(round(distance))}米" if distance is not None else poi.get("address")
                ),
                availableText="余位信息以现场为准（未对接停车管理系统）",
                coord=_geo(coord) if coord else None,
            )
        )
    return options


def _uri_mode(mode: TravelMode | None) -> str:
    """唤起高德 APP 的出行方式取值。"""
    return {
        TravelMode.BUS: "bus",
        TravelMode.WALK: "walk",
        TravelMode.RIDE: "ride",
    }.get(mode, "car")


# --------------------------------------------------------------------------- #
# 通用格式化
# --------------------------------------------------------------------------- #


def _amap_location(coord: tuple[float, float]) -> str:
    """(经度, 纬度) -> 高德坐标串。"""
    return amap.format_location(coord[0], coord[1])


def _geo(coord: tuple[float, float]) -> GeoCoord:
    return GeoCoord(longitude=coord[0], latitude=coord[1])


def _parse_coord(value: str | None) -> tuple[float, float] | None:
    """"经度,纬度" -> (经度, 纬度)。"""
    if not value or "," not in value:
        return None
    longitude, _, latitude = value.partition(",")
    parsed = _as_float(longitude), _as_float(latitude)
    if parsed[0] is None or parsed[1] is None:
        return None
    return parsed  # type: ignore[return-value]


def _format_meters(meters: float) -> str:
    if meters >= 1000:
        return f"{meters / 1000:.1f}公里"
    return f"{int(round(meters))}米"


def _format_duration(seconds: float) -> str:
    minutes = max(1, int(round(seconds / 60)))
    if minutes < 60:
        return f"{minutes}分钟"
    hours, remainder = divmod(minutes, 60)
    return f"{hours}小时{remainder}分钟" if remainder else f"{hours}小时"


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
