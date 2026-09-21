"""处方（药单）模块业务逻辑（接口文档 3.9.1：API-30 本次药单查询）。

“本次药单”取该就诊人名下最近一次就诊所开的处方：优先按预约就诊日期倒序，
处方未挂预约号时回落到处方编号倒序（seed 中 PRE 序号即开方顺序）。

数据来源：开发期 HIS_ENABLED=false，直接读本地库
t_prescription / t_prescription_item / t_medication，并经 t_appointment
关联 t_department / t_doctor 取科室与医生名。

依赖的公共模块（非本模块职责，由公共基建提供）：
  app.core.errors.BizError  —— 业务异常，签名 BizError(code, message)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BizError
from app.models.appointment import Appointment
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.medication import Medication
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.models.prescription_item import PrescriptionItem
from app.schemas.prescription import DrugItem, PrescriptionDetail

# 接口文档 2.5 通用错误码
PATIENT_INVALID = 2003
ACCESS_DENIED = 4003

# 库中 insurance_type 为 A/B/SELF，接口文档要求输出中文属性
INSURANCE_TYPE_TEXT = {"A": "甲类", "B": "乙类", "SELF": "自费"}

# meal_relation 为“不限”时不拼进用法文案
MEAL_UNLIMITED = "不限"


def get_current_prescription(
    db: Session,
    *,
    user_id: str,
    patient_id: Optional[str] = None,
) -> Optional[PrescriptionDetail]:
    """查询本次就诊药单。该就诊人没有任何处方时返回 None，由接口层输出 data: null。"""
    patient = _resolve_patient(db, user_id, patient_id)

    prescription, appointment = _latest_prescription(db, patient.patient_id)
    if prescription is None:
        return None

    dept_name = (
        db.scalar(select(Department.dept_name).where(Department.dept_id == appointment.dept_id))
        if appointment is not None and appointment.dept_id
        else None
    )
    doctor_name = db.scalar(select(Doctor.name).where(Doctor.doctor_id == prescription.doctor_id))

    return PrescriptionDetail(
        prescriptionId=prescription.prescription_id,
        visitDate=appointment.appt_date.isoformat() if appointment is not None else None,
        deptName=dept_name,
        doctorName=doctor_name,
        totalAmount=_yuan(prescription.total_amount),
        insuranceCover=_yuan(prescription.insurance_cover),
        selfPay=_yuan(prescription.self_pay),
        drugs=_drug_items(db, prescription.prescription_id),
    )


def _resolve_patient(db: Session, user_id: str, patient_id: Optional[str]) -> Patient:
    """确定要查询的就诊人：显式传入则校验归属，否则取默认就诊人、再退到最早绑定的一位。"""
    if patient_id:
        patient = db.get(Patient, patient_id)
        if patient is None or patient.user_id != user_id:
            raise BizError(ACCESS_DENIED, "无权访问该资源")
        return patient

    patient = db.scalar(
        select(Patient)
        .where(Patient.user_id == user_id)
        .order_by(Patient.is_default.desc(), Patient.created_at.asc())
        .limit(1)
    )
    if patient is None:
        raise BizError(PATIENT_INVALID, "就诊人信息校验失败")
    return patient


def _latest_prescription(
    db: Session, patient_id: str
) -> tuple[Optional[Prescription], Optional[Appointment]]:
    """取最近一次就诊的处方及其预约单。

    处方表没有就诊日期，故经 appointment_id 关联排班日期排序；
    未挂预约号的处方取不到日期，用处方编号倒序作为回落顺序。
    """
    row = db.execute(
        select(Prescription, Appointment)
        .join(Appointment, Appointment.appointment_id == Prescription.appointment_id)
        .where(Prescription.patient_id == patient_id)
        .order_by(Appointment.appt_date.desc(), Prescription.prescription_id.desc())
        .limit(1)
    ).first()
    if row is not None:
        return row[0], row[1]

    orphan = db.scalar(
        select(Prescription)
        .where(Prescription.patient_id == patient_id, Prescription.appointment_id.is_(None))
        .order_by(Prescription.prescription_id.desc())
        .limit(1)
    )
    return orphan, None


def _drug_items(db: Session, prescription_id: str) -> list[DrugItem]:
    """处方明细关联药品表，输出“所开药品”列表。"""
    rows = db.execute(
        select(PrescriptionItem, Medication)
        .join(Medication, Medication.drug_id == PrescriptionItem.drug_id)
        .where(PrescriptionItem.prescription_id == prescription_id)
        .order_by(PrescriptionItem.item_id)
    ).all()

    return [
        DrugItem(
            drugId=medication.drug_id,
            drugName=medication.drug_name,
            specification=medication.specification,
            dosage=item.dosage,
            frequency=item.frequency,
            usage=_usage_text(item.usage_method, item.meal_relation),
            days=item.days,
            insuranceType=INSURANCE_TYPE_TEXT.get(
                (medication.insurance_type or "").upper(), medication.insurance_type
            ),
            instructions=medication.usage_instruction,
            contraindication=medication.contraindication,
        )
        for item, medication in rows
    ]


def _usage_text(usage_method: Optional[str], meal_relation: Optional[str]) -> Optional[str]:
    """拼用法文案，如“口服，饭后服用”；餐次不限时不拼。"""
    parts: list[str] = []
    if usage_method:
        parts.append(usage_method)
    if meal_relation and meal_relation != MEAL_UNLIMITED:
        parts.append(f"{meal_relation}服用")
    return "，".join(parts) or None


def _yuan(amount: Optional[Decimal]) -> float:
    """金额按接口文档 2.1：单位元、保留两位小数、JSON 中为数字。"""
    return round(float(amount or 0), 2)
