"""t_medical_record 病历表（设计文档 3.14）。"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class MedicalRecord(Base, TimestampMixin):
    """通过 HIS 获取历史病情并结构化存储，供病历查询与 AI 解读。"""

    __tablename__ = "t_medical_record"
    __table_args__ = (Index("idx_record_patient", "patient_id", "visit_date"),)

    record_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="病历编号")
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("t_patient.patient_id"), nullable=False, comment="就诊人编号"
    )
    appointment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("t_appointment.appointment_id"), comment="关联预约编号"
    )
    doctor_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("t_doctor.doctor_id"), comment="接诊医生编号"
    )
    dept_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("t_department.dept_id"), comment="接诊科室编号"
    )
    visit_date: Mapped[date] = mapped_column(Date, nullable=False, comment="就诊日期")
    chief_complaint: Mapped[Optional[str]] = mapped_column(String(255), comment="主诉")
    diagnosis: Mapped[Optional[str]] = mapped_column(String(255), comment="诊断结果")
    treatment_advice: Mapped[Optional[str]] = mapped_column(String(512), comment="处理意见")
    raw_text: Mapped[Optional[str]] = mapped_column(Text, comment="病历原文（拍照识别文本，供AI解读）")
    external_no: Mapped[Optional[str]] = mapped_column(String(64), comment="HIS病历同步编号")
