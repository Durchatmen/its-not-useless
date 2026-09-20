"""ORM 模型汇总。

与《智慧医疗AI辅助系统数据库表设计文档 V1.0》第 2 节的 19 张表一一对应。
导入顺序即依赖顺序（被引用的父表在前），Base.metadata 由此收集全部表结构。
"""

from app.models.ai_message import AiMessage
from app.models.ai_session import AiSession
from app.models.appointment import Appointment
from app.models.bill import Bill
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.exam import Exam
from app.models.exam_report import ExamReport
from app.models.medical_record import MedicalRecord
from app.models.medication import Medication
from app.models.medication_reminder import MedicationReminder
from app.models.operation_log import OperationLog
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.prescription import Prescription
from app.models.prescription_item import PrescriptionItem
from app.models.schedule import Schedule
from app.models.sms_code import SmsCode
from app.models.user import User

__all__ = [
    "AiMessage",
    "AiSession",
    "Appointment",
    "Bill",
    "Department",
    "Doctor",
    "Exam",
    "ExamReport",
    "MedicalRecord",
    "Medication",
    "MedicationReminder",
    "OperationLog",
    "Patient",
    "Payment",
    "Prescription",
    "PrescriptionItem",
    "Schedule",
    "SmsCode",
    "User",
]
