"""t_medication_reminder 用药提醒计划表（设计文档 3.17）。"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class MedicationReminder(Base, TimestampMixin):
    """用药Agent根据处方生成的服药计划，驱动浏览器通知/页面提醒/日历导出。"""

    __tablename__ = "t_medication_reminder"
    __table_args__ = (Index("idx_reminder_patient_date", "patient_id", "plan_date"),)

    reminder_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="主键")
    prescription_id: Mapped[str] = mapped_column(
        ForeignKey("t_prescription.prescription_id"), nullable=False, comment="处方编号"
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("t_patient.patient_id"), nullable=False, comment="就诊人编号"
    )
    drug_id: Mapped[str] = mapped_column(
        ForeignKey("t_medication.drug_id"), nullable=False, comment="药品编号"
    )
    dose: Mapped[Optional[str]] = mapped_column(String(32), comment="剂量，如“0.5g”")
    take_time: Mapped[str] = mapped_column(String(16), nullable=False, comment="服药时间点，如“12:30”")
    meal_relation: Mapped[Optional[str]] = mapped_column(String(16), comment="餐前/餐中/饭后")
    plan_date: Mapped[date] = mapped_column(Date, nullable=False, comment="计划日期")
    taken_status: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0", comment="完成：1已服 0未服"
    )
    conflict_warning: Mapped[Optional[str]] = mapped_column(
        String(255), comment="药物相互作用或禁忌风险提示"
    )
