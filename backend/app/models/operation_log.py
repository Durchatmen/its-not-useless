"""t_operation_log 操作日志表（设计文档 3.19）。"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class OperationLog(Base, CreatedAtMixin):
    """合规审计要求：会话与关键操作日志留存不少于6个月。"""

    __tablename__ = "t_operation_log"
    __table_args__ = (Index("idx_log_user_time", "user_id", "created_at"),)

    log_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="主键")
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("t_user.user_id"), comment="操作账号编号"
    )
    action: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="动作：LOGIN登录 REGISTER注册 APPT_CREATE挂号 PAY缴费 AI_CHAT会话等"
    )
    target_type: Mapped[Optional[str]] = mapped_column(String(32), comment="操作对象类型")
    target_id: Mapped[Optional[str]] = mapped_column(String(32), comment="操作对象编号")
    detail: Mapped[Optional[str]] = mapped_column(Text, comment="详情（敏感信息脱敏后记录）")
    ip: Mapped[Optional[str]] = mapped_column(String(64), comment="来源IP")
