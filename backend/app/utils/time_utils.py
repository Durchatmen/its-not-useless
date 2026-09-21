"""时间工具：全站统一东八区（《接口文档》2.1 全局约定）。

数据库 DATETIME 列不带时区，统一写入东八区本地时间（naive），
与 app/db/base.py 的 server_default=func.now() 语义保持一致。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings

TZ = ZoneInfo(settings.tz)
FMT = "%Y-%m-%d %H:%M:%S"


def now() -> datetime:
    """当前东八区时间（naive，可直接写入 DATETIME 列）。"""
    return datetime.now(TZ).replace(tzinfo=None)


def fmt(value: datetime | None) -> str | None:
    """按接口约定的 yyyy-MM-dd HH:mm:ss 格式化。"""
    return value.strftime(FMT) if value else None
