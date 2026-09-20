"""t_bill 账单表（设计文档 3.10）。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Bill(Base, TimestampMixin):
    """覆盖挂号缴费与就诊缴费两类账单。"""

    __tablename__ = "t_bill"
    __table_args__ = (Index("idx_bill_patient_status", "patient_id", "pay_status"),)

    bill_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="账单编号")
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("t_patient.patient_id"), nullable=False, comment="就诊人编号"
    )
    appointment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("t_appointment.appointment_id"), comment="预约编号（挂号缴费类必填）"
    )
    bill_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="REGISTRATION",
        server_default="REGISTRATION",
        comment="账单类型：REGISTRATION挂号缴费 TREATMENT就诊缴费",
    )
    bill_title: Mapped[Optional[str]] = mapped_column(String(64), comment="账单名称，如“门诊挂号费”")
    related_type: Mapped[Optional[str]] = mapped_column(
        String(16), comment="关联业务类型：EXAM检查单 PRESCRIPTION处方"
    )
    related_id: Mapped[Optional[str]] = mapped_column(String(32), comment="关联业务编号")
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0.00", comment="总金额"
    )
    insurance_cover: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0.00", comment="医保预估报销金额（元）"
    )
    self_pay: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0.00", comment="预估自付金额（元）"
    )
    pay_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="UNPAID",
        server_default="UNPAID",
        comment="支付状态：UNPAID待缴费 PAID已缴费 REFUNDED已退费",
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="缴费完成时间")
    invoice_no: Mapped[Optional[str]] = mapped_column(String(64), comment="电子票据号")
    external_no: Mapped[Optional[str]] = mapped_column(String(64), comment="HIS账单同步编号")
