"""t_ai_session AI会话表（设计文档 3.15）。"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AiSession(Base, TimestampMixin):
    """承载多模态预诊、医保咨询、报告追问等多轮会话容器。"""

    __tablename__ = "t_ai_session"

    session_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="会话编号")
    user_id: Mapped[str] = mapped_column(
        ForeignKey("t_user.user_id"), nullable=False, comment="所属账号编号"
    )
    patient_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("t_patient.patient_id"), comment="预诊针对的就诊人编号"
    )
    scene: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PRE_CONSULT",
        server_default="PRE_CONSULT",
        comment="场景：PRE_CONSULT预诊分诊 INSURANCE医保咨询 REPORT报告追问 RECORD病历解读",
    )
    department: Mapped[Optional[str]] = mapped_column(String(64), comment="会话最终推荐科室（预诊结论）")
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="消息轮数"
    )
    status: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1", comment="状态：1进行中 0已结束"
    )
