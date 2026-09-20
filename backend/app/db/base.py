"""SQLAlchemy 2.0 声明式基类与公共时间戳列。

对应《智慧医疗AI辅助系统数据库表设计文档 V1.0》1.1 设计原则：
主键统一 varchar(32)，所有业务表带 created_at / updated_at 时间戳。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """全部 ORM 模型的声明式基类，其 metadata 用于 create_all 建表。"""


class CreatedAtMixin:
    """仅带创建时间的表（处方主表、支付单表、AI消息表、短信验证码表、操作日志表）。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )


class TimestampMixin(CreatedAtMixin):
    """创建时间 + 更新时间，供绝大多数业务表复用。"""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )
