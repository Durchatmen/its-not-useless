"""t_sms_code 短信验证码表（设计文档 3.18）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class SmsCode(Base, CreatedAtMixin):
    """注册环节短信验证码的发送与校验（5分钟有效、60秒限发）。"""

    __tablename__ = "t_sms_code"
    __table_args__ = (Index("idx_sms_phone_scene", "phone", "scene", "created_at"),)

    sms_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="主键")
    phone: Mapped[str] = mapped_column(String(16), nullable=False, comment="手机号")
    code: Mapped[str] = mapped_column(String(8), nullable=False, comment="验证码")
    scene: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="REGISTER",
        server_default="REGISTER",
        comment="用途：REGISTER注册等",
    )
    expired_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="过期时间（发送后5分钟）"
    )
    used_status: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0", comment="使用：1已使用 0未使用"
    )
