"""t_exam 检查单表（设计文档 3.12）。"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Exam(Base, TimestampMixin):
    """支撑检查模块六个接口：注意事项、叫号、指引、报告查询、状态、分析。"""

    __tablename__ = "t_exam"
    __table_args__ = (Index("idx_exam_patient_status", "patient_id", "exam_status"),)

    exam_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="检查单编号")
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("t_patient.patient_id"), nullable=False, comment="就诊人编号"
    )
    appointment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("t_appointment.appointment_id"), comment="关联预约编号"
    )
    exam_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="检查名称，如“胸部CT”")
    exam_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="WAIT_PAY",
        server_default="WAIT_PAY",
        comment="状态机：WAIT_PAY待缴费 WAIT_EXAM待检查 WAIT_REPORT待报告 REPORTED已报告",
    )
    precautions: Mapped[Optional[str]] = mapped_column(
        String(512), comment="检查注意事项（检查知识库生成，如空腹、憋尿）"
    )
    building: Mapped[Optional[str]] = mapped_column(String(32), comment="楼栋（位置指引）")
    floor: Mapped[Optional[str]] = mapped_column(String(8), comment="楼层，如“2F”")
    room: Mapped[Optional[str]] = mapped_column(String(32), comment="房间号，如“影像中心CT-2室”")
    queue_no: Mapped[Optional[str]] = mapped_column(String(16), comment="检查排队号")
    current_no: Mapped[Optional[str]] = mapped_column(String(16), comment="当前叫号（HIS同步）")
    people_ahead: Mapped[Optional[int]] = mapped_column(Integer, comment="前方等待人数（推算预计等待用）")
    estimated_wait_minutes: Mapped[Optional[int]] = mapped_column(Integer, comment="预计等待分钟数（估算值）")
    external_no: Mapped[Optional[str]] = mapped_column(String(64), comment="HIS检查单同步编号")
