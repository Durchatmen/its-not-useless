"""高德地图服务封装（《接口文档》2.7：通过 MCP 方式接入高德地图服务）。

本模块是院外导航唯一的高德出入口：路径规划（驾车/公交/步行/骑行）、静态地图、
POI 检索、唤起高德 APP 的链接拼接。

* 使用同步 httpx，与项目内其它外部调用（短信网关等）保持一致；
* 若后续改为 MCP 方式接入，只需替换本模块内部实现，对外函数签名不变；
* 高德返回异常统一转 5004（高德地图服务调用失败），由导航服务决定是否降级。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.errors import BizError, ErrorCode

logger = logging.getLogger(__name__)

# 高德 Web 服务成功标识
_AMAP_STATUS_OK = "1"
# 驾车路径规划策略：32 = 默认（高德未给默认值的版本按 32 处理）
_DEFAULT_DRIVE_STRATEGY = 32

DriveStrategy = int


@dataclass(frozen=True)
class RouteEstimate:
    """一条方案的量化结果，文案格式化交给 navigation_service。"""

    distance: float  # 米
    duration: float  # 秒
    traffic_lights: int | None = None  # 红绿灯数量（驾车）
    congestion: str | None = None  # 路况概括：畅通/缓行/拥堵/严重拥堵（驾车）
    walk_distance: float | None = None  # 步行距离（公交/地铁方案）
    transfer_text: str | None = None  # 换乘摘要，如“地铁1号线 → 公交7路”


def format_location(longitude: float, latitude: float) -> str:
    """高德要求的坐标串：经度在前、纬度在后，小数点后 6 位。"""
    return f"{longitude:.6f},{latitude:.6f}"


# --------------------------------------------------------------------------- #
# 路径规划
# --------------------------------------------------------------------------- #


def driving(origin: str, destination: str, *, strategy: DriveStrategy = _DEFAULT_DRIVE_STRATEGY) -> RouteEstimate | None:
    """驾车路径规划，返回首条推荐路线；无可行路线返回 None。"""
    payload = _request(
        "/v5/direction/driving",
        {
            "origin": origin,
            "destination": destination,
            "strategy": strategy,
            "show_fields": "cost,tmcs",
        },
    )
    path = _first_item(payload, "route", "paths")
    if path is None:
        return None
    return RouteEstimate(
        distance=_as_float(path.get("distance")) or 0.0,
        duration=_duration(path) or 0.0,
        traffic_lights=_as_int(path.get("traffic_lights")),
        congestion=_summarize_congestion(path),
    )


def transit(origin: str, destination: str, *, city: str | None = None) -> RouteEstimate | None:
    """公交/地铁综合换乘方案。city 为所在城市（高德 city1/city2）。"""
    city_name = city or settings.amap_city
    payload = _request(
        "/v5/direction/transit/integrated",
        {
            "origin": origin,
            "destination": destination,
            "city1": city_name,
            "city2": city_name,
            "show_fields": "cost",
        },
    )
    plan = _first_item(payload, "route", "transits")
    if plan is None:
        return None
    return RouteEstimate(
        distance=_as_float(plan.get("distance")) or 0.0,
        duration=_duration(plan) or 0.0,
        walk_distance=_walk_distance(plan),
        transfer_text=_transfer_text(plan),
    )


def _duration(item: dict[str, Any]) -> float | None:
    """取方案耗时（秒）。

    v5 文档把 duration 归在 cost 分组下（“show_fields=cost 后可返回方案所需时间
    及费用成本”），因此真实返回可能是 cost.duration 而非同级 duration；两种层级
    都读，避免把耗时读成 0 导致前端显示“约1分钟”。真实响应待配 Key 后复核。
    """
    cost = item.get("cost")
    return _as_float(item.get("duration")) or (
        _as_float(cost.get("duration")) if isinstance(cost, dict) else None
    )


def _walk_distance(plan: dict[str, Any]) -> float | None:
    """公交方案的总步行距离。

    优先取 walking_distance（v3 的字段名，v5 文档已无此项）；取不到则累加各分段
    walking.steps[].distance（官方把分段结构指向 v3 老接口）。都拿不到返回 None
    而不是 0，让前端不显示这一行，避免误导。
    """
    flat = _as_float(plan.get("walking_distance"))
    if flat is not None:
        return flat

    total = 0.0
    found = False
    for segment in plan.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        walking = segment.get("walking")
        if not isinstance(walking, dict):
            continue
        for step in walking.get("steps") or []:
            value = _as_float(step.get("distance")) if isinstance(step, dict) else None
            if value is not None:
                total += value
                found = True
    return total if found else None


def walking(origin: str, destination: str) -> RouteEstimate | None:
    return _simple_route("/v5/direction/walking", origin, destination)


def bicycling(origin: str, destination: str) -> RouteEstimate | None:
    return _simple_route("/v5/direction/bicycling", origin, destination)


def _simple_route(path: str, origin: str, destination: str) -> RouteEstimate | None:
    # 步行/骑行同样只有 show_fields=cost 才返回 duration（官方文档“返回结果”一节），
    # 不传的话耗时字段缺失，前端会看到“约1分钟”这种兜底值
    payload = _request(path, {"origin": origin, "destination": destination, "show_fields": "cost"})
    item = _first_item(payload, "route", "paths")
    if item is None:
        return None
    return RouteEstimate(
        distance=_as_float(item.get("distance")) or 0.0,
        duration=_duration(item) or 0.0,
    )


def place_around(
    keywords: str | None = None,
    *,
    center: str,
    types: str | None = None,
    radius: int = 3000,
    page_size: int = 10,
) -> list[dict[str, Any]]:
    """周边检索（v5 /v5/place/around）：以 center 为中心、radius 米内检索。

    center 是该接口的必填项，也只有它返回的 pois[].distance 才是“离中心点距离”，
    因此需要按远近展示（如停车场引导）时用这个接口，而不是关键字搜索 /v5/place/text。
    radius 上限 50000 米、page_size 上限 25，超出会被官方按默认值处理，这里先夹住。
    """
    payload = _request(
        "/v5/place/around",
        {
            "keywords": keywords,
            "types": types,
            "location": center,
            "radius": min(radius, 50_000),
            "page_size": min(page_size, 25),
            "sortrule": "distance",
            "show_fields": "business",
        },
    )
    return payload.get("pois") or []


# --------------------------------------------------------------------------- #
# URL 拼接（不发起请求）
# --------------------------------------------------------------------------- #


def static_map(
    *,
    origin: str,
    destination: str,
    width: int = 512,
    height: int = 256,
) -> str:
    """静态地图缩略图 URL，标注起点（蓝，A）与终点（红，B）。

    刻意**不传 location 与 zoom**：官方文档说明“有标注时中心点与地图级别可选填，
    不传时地图区域以包含所有标注的几何中心为中心、由系统计算 zoom”。手动指定
    location=医院&zoom=13 会在用户距离较远时把起点裁出画面，图上只剩一个终点标记。

    marker 标签按官方限制取单个大写字母（可用 [0-9]、[A-Z] 或单个中文字，多字
    中文会整条 markers 失效，故用 A/B 最稳）。
    size 上限 1024*1024，scale=2 会把宽高翻倍，故默认 512*256（实际出图 1024*512）。
    """
    markers = f"mid,0x1E90FF,A:{origin}|mid,0xFF4D4F,B:{destination}"
    return (
        f"{settings.amap_base_url}/v3/staticmap"
        f"?size={width}*{height}&markers={markers}"
        f"&scale=2&key={settings.amap_web_key}"
    )


def navigation_uri(
    *,
    origin: str,
    destination: str,
    origin_name: str = "我的位置",
    destination_name: str = "目的地",
    mode: str = "car",
) -> str:
    """一键唤起高德 APP 实时导航的 URI（院外导航“导航去医院（高德）”按钮）。"""
    return (
        "https://uri.amap.com/navigation"
        f"?from={origin},{quote(origin_name)}"
        f"&to={destination},{quote(destination_name)}"
        f"&mode={mode}&coordinate=gaode&callnative=1&src={quote(settings.app_name)}"
    )


# --------------------------------------------------------------------------- #
# 内部实现
# --------------------------------------------------------------------------- #


def _request(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """调用高德 Web 服务并解统一信封；任何失败统一转 5004。"""
    if not settings.amap_web_key:
        raise BizError(ErrorCode.AMAP_FAILED, "未配置高德地图 Key（AMAP_WEB_KEY）")

    query = {k: v for k, v in params.items() if v is not None and v != ""}
    query.update({"key": settings.amap_web_key, "output": "json"})

    try:
        with httpx.Client(timeout=settings.amap_timeout) as client:
            response = client.get(f"{settings.amap_base_url}{path}", params=query)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        logger.error("高德地图请求失败：path=%s err=%s", path, exc)
        raise BizError(ErrorCode.AMAP_FAILED) from exc
    except ValueError as exc:  # 响应不是 JSON
        logger.error("高德地图响应无法解析：path=%s", path)
        raise BizError(ErrorCode.AMAP_FAILED, "高德地图返回内容无法解析") from exc

    if str(payload.get("status")) != _AMAP_STATUS_OK:
        info = payload.get("info") or "未知原因"
        logger.error("高德地图返回失败：path=%s info=%s", path, info)
        raise BizError(ErrorCode.AMAP_FAILED, f"高德地图服务调用失败（{info}）")
    return payload


def _first_item(payload: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    """按 keys 逐层取到列表并返回首项，任一层缺失都返回 None。"""
    node: Any = payload
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if isinstance(node, list) and node and isinstance(node[0], dict):
        return node[0]
    return None


def _transfer_text(plan: dict[str, Any]) -> str | None:
    """从换乘方案的分段里提取交通工具名称，拼成“地铁1号线 → 公交7路”。

    公交线路名在 bus.buslines[].name（v5 文档把 bus 子树标注为“参考 v3 老接口”）；
    兼容 bus.steps[].buslines 的写法。火车在 railway.name。
    打车段（taxi）官方只有费用/距离/起终点，没有线路名，故不参与拼接。
    """
    names: list[str] = []
    for segment in plan.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        for line in _buslines(segment.get("bus")):
            name = line.get("name")
            if name and str(name) not in names:
                names.append(str(name))
        railway = segment.get("railway")
        name = railway.get("name") if isinstance(railway, dict) else None
        if name and str(name) not in names:
            names.append(str(name))
    return " → ".join(names) if names else None


def _buslines(bus: Any) -> list[dict[str, Any]]:
    """取公交分段里的线路列表，兼容 buslines 与 steps[].buslines 两种层级。"""
    if not isinstance(bus, dict):
        return []
    lines = [line for line in bus.get("buslines") or [] if isinstance(line, dict)]
    if lines:
        return lines
    for step in bus.get("steps") or []:
        if isinstance(step, dict):
            lines += [line for line in step.get("buslines") or [] if isinstance(line, dict)]
    return lines


def _summarize_congestion(path: dict[str, Any]) -> str | None:
    """把分段路况（steps[].tmcs[]）汇总成一个主导状态，供前端展示“拥堵情况”。

    字段名按官方 v5 文档为 tmc_status（取值：未知/畅通/缓行/拥堵/严重拥堵），
    需请求时带 show_fields=tmcs 才会返回。
    """
    counts: dict[str, int] = {}
    for step in path.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for tmc in step.get("tmcs") or []:
            status = tmc.get("tmc_status") if isinstance(tmc, dict) else None
            if status:
                counts[str(status)] = counts.get(str(status), 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    return int(number) if number is not None else None
