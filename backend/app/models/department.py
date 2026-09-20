"""t_department 科室表（设计文档 3.1）。"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Department(Base, TimestampMixin):
    """全院科室职能、位置与联系方式，供分诊推荐与院内导航使用。"""

    __tablename__ = "t_department"

    dept_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="科室编号")
    dept_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="科室名称")
    dept_addr: Mapped[Optional[str]] = mapped_column(
        String(128), comment="科室地址/门诊位置描述，如“门诊楼3楼305诊区”"
    )
    phone: Mapped[Optional[str]] = mapped_column(String(16), comment="联系电话")
    floor_position: Mapped[Optional[str]] = mapped_column(
        String(32), comment="楼层位置编码（院内导航用），如“3F-E-305”"
    )
    introduction: Mapped[Optional[str]] = mapped_column(String(512), comment="科室职能简介")
    status: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1", comment="状态：1正常 0停诊维护"
    )
