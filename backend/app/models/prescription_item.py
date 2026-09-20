"""t_prescription_item 处方明细表（设计文档 3.9）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PrescriptionItem(Base):
    """处方中的药品明细行，一张处方含多条明细。"""

    __tablename__ = "t_prescription_item"

    item_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="主键")
    prescription_id: Mapped[str] = mapped_column(
        ForeignKey("t_prescription.prescription_id"), nullable=False, comment="处方编号"
    )
    drug_id: Mapped[str] = mapped_column(
        ForeignKey("t_medication.drug_id"), nullable=False, comment="药品编号"
    )
    dosage: Mapped[Optional[str]] = mapped_column(String(32), comment="单次剂量，如“0.5g”")
    frequency: Mapped[Optional[str]] = mapped_column(
        String(32), comment="用药频次，如“每日三次”（用药Agent生成提醒依据）"
    )
    usage_method: Mapped[Optional[str]] = mapped_column(String(32), comment="用法：口服、静脉注射等")
    meal_relation: Mapped[Optional[str]] = mapped_column(
        String(16), comment="餐前/餐中/饭后（如阿莫西林饭后服用）"
    )
    days: Mapped[Optional[int]] = mapped_column(Integer, comment="疗程天数")
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1", comment="数量"
    )
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0.00", comment="小计金额（元）"
    )
