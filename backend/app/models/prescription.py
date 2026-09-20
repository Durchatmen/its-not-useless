"""t_prescription 处方主表（设计文档 3.8）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class Prescription(Base, CreatedAtMixin):
    """一条处方对应一次就诊的整张药单，明细见 t_prescription_item。"""

    __tablename__ = "t_prescription"

    prescription_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="处方编号")
    appointment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("t_appointment.appointment_id"), comment="关联预约编号"
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("t_patient.patient_id"), nullable=False, comment="就诊人编号"
    )
    doctor_id: Mapped[str] = mapped_column(
        ForeignKey("t_doctor.doctor_id"), nullable=False, comment="开方医生编号"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0.00", comment="处方总金额（元）"
    )
    insurance_cover: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0.00", comment="医保预估报销金额（元）"
    )
    self_pay: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0.00", comment="预估自付金额（元）"
    )
    external_no: Mapped[Optional[str]] = mapped_column(String(64), comment="HIS处方同步编号")
