"""t_appointment 挂号/预约表（设计文档 3.6）。"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Appointment(Base, TimestampMixin):
    """挂号/预约业务表，覆盖挂号增改删查、历史挂号与提醒。"""

    __tablename__ = "t_appointment"
    __table_args__ = (
        Index("idx_appt_user", "user_id"),
        Index("idx_appt_patient", "patient_id"),
        Index("idx_appt_date_status", "appt_date", "appointment_status"),
    )

    appointment_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="预约编号")
    user_id: Mapped[str] = mapped_column(
        ForeignKey("t_user.user_id"), nullable=False, comment="操作账号编号"
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("t_patient.patient_id"), nullable=False, comment="患者编号"
    )
    doctor_id: Mapped[str] = mapped_column(
        ForeignKey("t_doctor.doctor_id"), nullable=False, comment="医生编号"
    )
    schedule_id: Mapped[str] = mapped_column(
        ForeignKey("t_schedule.schedule_id"), nullable=False, comment="排班编号"
    )
    dept_id: Mapped[str] = mapped_column(
        ForeignKey("t_department.dept_id"), nullable=False, comment="科室编号（冗余，便于查询）"
    )
    appt_date: Mapped[date] = mapped_column(Date, nullable=False, comment="预约日期")
    time_slot: Mapped[str] = mapped_column(String(32), nullable=False, comment="预约时段")
    chief_complaint: Mapped[Optional[str]] = mapped_column(
        String(255), comment="就诊原因/主诉，可由预诊摘要自动填入"
    )
    queue_no: Mapped[Optional[str]] = mapped_column(String(16), comment="就诊队列号")
    appointment_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="BOOKED",
        server_default="BOOKED",
        comment="状态：BOOKED已预约待就诊 CHECKED_IN已取号 FINISHED已完成 CANCELED已取消",
    )
    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="MANUAL",
        server_default="MANUAL",
        comment="来源：MANUAL手动挂号 AI_AUTO AI自动挂号",
    )
    # t_appointment 与 t_bill 互有外键（账单侧记预约、预约侧记账单），
    # 形成建表环路，故该边用 use_alter 交由 create_all 在两张表建好后补加。
    bill_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("t_bill.bill_id", use_alter=True, name="fk_appt_bill"),
        comment="关联挂号缴费账单",
    )
    external_no: Mapped[Optional[str]] = mapped_column(String(64), comment="HIS挂号同步编号")
