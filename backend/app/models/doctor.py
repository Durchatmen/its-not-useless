"""t_doctor 医生表（设计文档 3.2）。"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import CHAR, Date, ForeignKey, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Doctor(Base, TimestampMixin):
    """医生档案与擅长方向，供排班与分诊推荐（按病种擅长排序）使用。"""

    __tablename__ = "t_doctor"
    __table_args__ = (Index("idx_doctor_dept", "dept_id"),)

    doctor_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="医生编号")
    dept_id: Mapped[str] = mapped_column(
        ForeignKey("t_department.dept_id"), nullable=False, comment="所属科室编号"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="姓名")
    gender: Mapped[Optional[str]] = mapped_column(CHAR(1), comment="性别：M男 F女")
    birth_date: Mapped[Optional[date]] = mapped_column(Date, comment="出生日期")
    title: Mapped[Optional[str]] = mapped_column(String(32), comment="职称/职务")
    specialty: Mapped[Optional[str]] = mapped_column(
        String(255), comment="擅长方向（分诊Agent按病种推荐排序依据）"
    )
    avatar: Mapped[Optional[str]] = mapped_column(String(255), comment="医生头像URL")
    intro: Mapped[Optional[str]] = mapped_column(String(512), comment="医生简介")
    visit_status: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1", comment="出诊状态：1正常 2停诊 3替诊"
    )
