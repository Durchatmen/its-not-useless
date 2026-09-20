"""t_ai_message AI消息表（设计文档 3.16）。"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class AiMessage(Base, CreatedAtMixin):
    """逐条保存多轮对话消息，AI回复强制携带免责声明与引用来源。"""

    __tablename__ = "t_ai_message"
    __table_args__ = (Index("idx_msg_session", "session_id"),)

    message_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="主键")
    session_id: Mapped[str] = mapped_column(
        ForeignKey("t_ai_session.session_id"), nullable=False, comment="会话编号"
    )
    role: Mapped[str] = mapped_column(String(8), nullable=False, comment="角色：user用户 bot助手")
    input_type: Mapped[Optional[str]] = mapped_column(
        String(8), comment="输入类型：TEXT文本 VOICE语音 IMAGE图片（bot侧为空）"
    )
    content: Mapped[Optional[str]] = mapped_column(Text, comment="用户原文或语音/图片识别文本")
    reply: Mapped[Optional[str]] = mapped_column(Text, comment="AI回复文本（bot侧）")
    triage_card: Mapped[Optional[str]] = mapped_column(
        Text, comment="分诊卡片JSON：department、location、doctor、buttonAction"
    )
    risk_warning: Mapped[Optional[str]] = mapped_column(
        String(255), comment="高危症状预警提示（急危重症安全话术）"
    )
    next_question: Mapped[Optional[str]] = mapped_column(String(255), comment="下一轮追问建议")
    sources: Mapped[Optional[str]] = mapped_column(
        String(512), comment="引用来源数组JSON，如《临床诊疗指南》"
    )
    disclaimer: Mapped[Optional[str]] = mapped_column(String(255), comment="免责声明文本")
