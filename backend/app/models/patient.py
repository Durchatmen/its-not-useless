"""t_patient 就诊人表（设计文档 3.4）。"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import CHAR, Date, ForeignKey, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Patient(Base, TimestampMixin):
    """家庭成员绑定、一人账号全家就医，承载健康档案概览。"""

    __tablename__ = "t_patient"
    __table_args__ = (UniqueConstraint("user_id", "idcard", name="uk_user_idcard"),)

    patient_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="就诊人编号")
    user_id: Mapped[str] = mapped_column(
        ForeignKey("t_user.user_id"), nullable=False, comment="所属账号编号"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="就诊人姓名")
    idcard: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="身份证号，加密存储，同账号下唯一"
    )
    phone: Mapped[Optional[str]] = mapped_column(String(16), comment="手机号")
    gender: Mapped[str] = mapped_column(CHAR(1), nullable=False, comment="性别：M男 F女")
    birth_date: Mapped[Optional[date]] = mapped_column(Date, comment="出生日期")
    relation: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="SELF",
        server_default="SELF",
        comment="与账号本人关系：SELF本人 SPOUSE配偶 CHILD子女 PARENT父母 OTHER其他",
    )
    blood_type: Mapped[Optional[str]] = mapped_column(String(8), comment="血型（健康档案概览）")
    allergy_history: Mapped[Optional[str]] = mapped_column(Text, comment="过敏史（预诊Agent采集依据）")
    medical_history: Mapped[Optional[str]] = mapped_column(Text, comment="既往病史（健康档案概览）")
    is_default: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0", comment="是否默认就诊人：1是 0否"
    )
