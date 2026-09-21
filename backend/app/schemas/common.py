"""通用枚举字典（《接口文档》2.6）。

取值与前端 frontend/src/constants/enums.js 一致，前后端不得各写一套。
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """字符串枚举基类：比较时可直接与字符串字面量等价。"""

    def __str__(self) -> str:  # pragma: no cover - 便于日志/拼接
        return self.value


class UserRole(StrEnum):
    """用户角色（t_user.role）。"""

    PATIENT = "PATIENT"
    DOCTOR = "DOCTOR"
    ADMIN = "ADMIN"


class Relation(StrEnum):
    """就诊人与账号本人的关系（t_patient.relation）。"""

    SELF = "SELF"
    SPOUSE = "SPOUSE"
    CHILD = "CHILD"
    PARENT = "PARENT"
    OTHER = "OTHER"


class AppointmentStatus(StrEnum):
    BOOKED = "BOOKED"
    CHECKED_IN = "CHECKED_IN"
    FINISHED = "FINISHED"
    CANCELED = "CANCELED"


class ExamStatus(StrEnum):
    WAIT_PAY = "WAIT_PAY"
    WAIT_EXAM = "WAIT_EXAM"
    WAIT_REPORT = "WAIT_REPORT"
    REPORTED = "REPORTED"


class BillType(StrEnum):
    REGISTRATION = "REGISTRATION"
    TREATMENT = "TREATMENT"


class BillStatus(StrEnum):
    UNPAID = "UNPAID"
    PAID = "PAID"
    REFUNDED = "REFUNDED"


class PayChannel(StrEnum):
    WECHAT = "WECHAT"
    ALIPAY = "ALIPAY"


class AiInputType(StrEnum):
    TEXT = "TEXT"
    VOICE = "VOICE"
    IMAGE = "IMAGE"


class SmsScene(StrEnum):
    """短信验证码用途（接口文档 3.1.3 scene 参数，演示数据含 RESET_PWD）。"""

    REGISTER = "REGISTER"
    LOGIN = "LOGIN"
    RESET_PWD = "RESET_PWD"
