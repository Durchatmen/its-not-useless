"""t_schedule 医生排班号源表（设计文档 3.5）。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Schedule(Base, TimestampMixin):
    """支撑“展示医生排班表、分时段预约”与号源余量实时查询。"""

    __tablename__ = "t_schedule"
    __table_args__ = (
        Index("idx_sched_query", "doctor_id", "appt_date"),
        UniqueConstraint("doctor_id", "appt_date", "time_slot", name="uk_sched_slot"),
    )

    schedule_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="排班编号")
    doctor_id: Mapped[str] = mapped_column(
        ForeignKey("t_doctor.doctor_id"), nullable=False, comment="医生编号"
    )
    dept_id: Mapped[str] = mapped_column(
        ForeignKey("t_department.dept_id"), nullable=False, comment="科室编号"
    )
    appt_date: Mapped[date] = mapped_column(Date, nullable=False, comment="出诊日期")
    time_slot: Mapped[str] = mapped_column(String(32), nullable=False, comment="时段，如 08:30-09:00")
    total_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="时段号源总数"
    )
    remaining: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="剩余号源数（挂号扣减、取消回补）"
    )
    fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0.00", comment="挂号费（元）"
    )
    external_no: Mapped[Optional[str]] = mapped_column(String(64), comment="HIS排班同步编号")
