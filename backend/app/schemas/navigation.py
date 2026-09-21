"""导航模块数据契约（《接口文档》3.6：API-20 院外导航）。

院外导航基于高德地图路径规划，返回多出行方式的方案对比、静态地图与
一键唤起高德 APP 的链接；院外导航由前端 frontend/src/api/navigation.js 调用。
院内导航不在本期范围，因此不再定义院内查询与响应模型。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TravelMode(str, Enum):
    """出行方式（接口文档 API-20 mode 参数）。"""

    DRIVE = "DRIVE"
    BUS = "BUS"
    WALK = "WALK"
    RIDE = "RIDE"


class DestType(str, Enum):
    """院外导航目的地类型（接口文档 API-20 destType 参数）。"""

    GATE = "GATE"
    PARKING = "PARKING"


class GeoCoord(BaseModel):
    """经纬度坐标。"""

    longitude: float
    latitude: float


class OutdoorNavQuery(BaseModel):
    """API-20 院外导航查询参数。"""

    latitude: float = Field(ge=-90, le=90, description="用户纬度")
    longitude: float = Field(ge=-180, le=180, description="用户经度")
    hospitalCode: str | None = Field(default=None, description="目标医院编码，默认当前院区")
    mode: TravelMode | None = Field(default=None, description="不传则返回全部出行方案对比")
    destType: DestType = Field(default=DestType.GATE, description="目的地类型")


class RouteOption(BaseModel):
    """一种出行方式的方案摘要。"""

    mode: TravelMode
    modeText: str = Field(description="出行方式中文名，供前端直接展示")
    durationText: str | None = Field(default=None, description="耗时描述，如“驾车约18分钟”")
    distanceText: str | None = Field(default=None, description="里程描述，如“12.4公里”")
    trafficText: str | None = Field(default=None, description="红绿灯数量与拥堵情况")
    transferText: str | None = Field(default=None, description="公交换乘方案摘要")
    walkDistance: float | None = Field(default=None, description="步行距离（米）")


class ParkingOption(BaseModel):
    """停车场引导（《功能设计文档》导航补充建议：停车引导）。"""

    name: str
    distanceText: str | None = None
    availableText: str | None = Field(default=None, description="余位提示；对接停车系统前为提示文案")
    coord: GeoCoord | None = None


class OutdoorNavData(BaseModel):
    """API-20 响应 data。"""

    distanceText: str = Field(description="距离描述，如“距离您 5.2公里”")
    hospitalName: str
    hospitalCoord: GeoCoord
    destType: DestType
    destCoord: GeoCoord
    routes: list[RouteOption] = Field(default_factory=list, description="各交通方案对比")
    staticMapUrl: str | None = Field(default=None, description="高德地图缩略图URL（标注起终点）")
    amapNavigationUrl: str | None = Field(default=None, description="一键唤起高德地图APP导航的链接")
    parkingOptions: list[ParkingOption] = Field(default_factory=list)
