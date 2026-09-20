"""t_user 用户账号表（设计文档 3.3）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """系统登录账号，患者、医生、系统管理员三类角色共用。"""

    __tablename__ = "t_user"
    __table_args__ = (
        UniqueConstraint("account", name="uk_account"),
        Index("idx_user_phone", "phone"),
    )

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="账号编号")
    account: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="登录账号：手机号或身份证号，唯一索引"
    )
    password: Mapped[str] = mapped_column(String(128), nullable=False, comment="密码，加盐哈希存储")
    name: Mapped[Optional[str]] = mapped_column(String(64), comment="姓名")
    idcard: Mapped[Optional[str]] = mapped_column(String(128), comment="身份证号，加密存储")
    phone: Mapped[Optional[str]] = mapped_column(String(16), comment="手机号")
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PATIENT",
        server_default="PATIENT",
        comment="角色：PATIENT患者 DOCTOR医生 ADMIN系统管理员",
    )
    real_name_verified: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0", comment="实名认证状态：1已认证 0未认证"
    )
    status: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1", comment="状态：1正常 0禁用"
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最近登录时间")
