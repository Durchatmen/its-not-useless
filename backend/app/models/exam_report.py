"""t_exam_report 检查报告表（设计文档 3.13）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ExamReport(Base, TimestampMixin):
    """接收 LIS/PACS 同步的报告数据，供报告查询与 AI 分析。"""

    __tablename__ = "t_exam_report"

    report_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="报告编号")
    exam_id: Mapped[str] = mapped_column(
        ForeignKey("t_exam.exam_id"), nullable=False, comment="检查单编号"
    )
    report_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="WAIT_REPORT",
        server_default="WAIT_REPORT",
        comment="状态：WAIT_REPORT待报告 REPORTED已报告",
    )
    report_content: Mapped[Optional[str]] = mapped_column(Text, comment="报告结论文本，如“双肺纹理增粗”")
    items_json: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="指标项JSON数组：itemName、value、unit、referenceRange、abnormalFlag（NORMAL/HIGH/LOW）",
    )
    report_image_url: Mapped[Optional[str]] = mapped_column(String(255), comment="报告原图/影像图片地址")
    report_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="报告时间")
    risk_level: Mapped[Optional[str]] = mapped_column(
        String(8), comment="AI分析风险等级：LOW、MEDIUM、HIGH"
    )
    ai_analysis: Mapped[Optional[str]] = mapped_column(Text, comment="AI分析结果缓存（报告Agent输出）")
    external_no: Mapped[Optional[str]] = mapped_column(String(64), comment="LIS/PACS同步编号")
