"""t_medication 药品表（设计文档 3.7）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Medication(Base, TimestampMixin):
    """药品知识库的结构化落地，支撑药单展示与用药提醒。"""

    __tablename__ = "t_medication"

    drug_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="药品编号")
    drug_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="药品名称")
    drug_type: Mapped[Optional[str]] = mapped_column(
        String(32), comment="类型：处方药/非处方药/中成药等"
    )
    specification: Mapped[Optional[str]] = mapped_column(String(64), comment="规格，如“0.25g×24粒”")
    supplier: Mapped[Optional[str]] = mapped_column(String(128), comment="供应商")
    stock: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="库存"
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0.00", comment="单价（元）"
    )
    insurance_type: Mapped[Optional[str]] = mapped_column(
        String(8), comment="医保属性：A甲类 B乙类 SELF自费"
    )
    usage_instruction: Mapped[Optional[str]] = mapped_column(String(255), comment="默认用法用量说明")
    contraindication: Mapped[Optional[str]] = mapped_column(String(255), comment="禁忌与副作用要点")
