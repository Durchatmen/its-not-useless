"""挂号模块数据契约（《接口文档》3.4.2 ~ 3.4.6：API-11 ~ API-15）。

字段名与接口文档一致（camelCase、主键 string），前端 frontend/src/api/appointments.js
直接对接，中间没有 snake→camel 转换层。

中文状态文案与 frontend/src/constants/enums.js 的 APPOINTMENT_STATUS_LABEL 逐字一致，
前端若不自己映射可直接用 statusDesc（超集字段，文档没要求但前端已有该常量表）。

时间字段一律加 `@field_serializer` 输出 `yyyy-MM-dd HH:mm:ss`（接口文档 2.1），
否则 Pydantic 默认吐 ISO 8601（带 T）。金额一律声明为 float，避免 Decimal 被序列化成字符串。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_serializer

# 挂号状态，取值以接口文档 2.6 枚举表为准
AppointmentStatus = Literal["BOOKED", "CHECKED_IN", "FINISHED", "CANCELED"]

# 挂号来源：MANUAL 手动挂号、AI_AUTO AI 自动挂号（t_appointment.source）
AppointmentSource = Literal["MANUAL", "AI_AUTO"]

# 与 frontend/src/constants/enums.js 的 APPOINTMENT_STATUS_LABEL 保持一致
APPOINTMENT_STATUS_DESC: dict[str, str] = {
    "BOOKED": "已预约待就诊",
    "CHECKED_IN": "已取号",
    "FINISHED": "已完成",
    "CANCELED": "已取消",
}

APPOINTMENT_SOURCE_DESC: dict[str, str] = {
    "MANUAL": "手动挂号",
    "AI_AUTO": "AI自动挂号",
}

# 队列号前缀：沿用 seed 的约定，发热门诊用 F，其余科室用 A（见 app/db/seed.py）
QUEUE_PREFIX_FEVER = "F"
QUEUE_PREFIX_NORMAL = "A"

# 接口文档 API-15 要求页面标注「以现场为准」，这句话由服务端下发，前端原样展示
REMINDER_ESTIMATE_NOTE = "预计叫号时间由前方人数与平均问诊时长估算，实际以现场叫号为准"


class AppointmentCreateRequest(BaseModel):
    """预约挂号请求体（接口文档 API-11）。

    `remark` 是对外参数名，落库进 t_appointment.chief_complaint
    （库列名来自数据库设计文档 3.6「就诊原因/主诉」，接口文档则叫备注）——
    同一份语义的两个名字，以文档契约收参、以库设计落库，见 appointment_service。
    """

    patientId: str = Field(min_length=1, description="就诊人ID")
    scheduleId: str = Field(min_length=1, description="排班ID（由 API-10 获得）")
    source: AppointmentSource = Field(default="MANUAL", description="来源：MANUAL手动 AI_AUTO自动")
    remark: Optional[str] = Field(
        default=None, max_length=255, description="备注（如预诊摘要同步给医生）"
    )


class AppointmentUpdateRequest(BaseModel):
    """修改挂号请求体（接口文档 API-12，改期/换时段）。"""

    scheduleId: str = Field(min_length=1, description="新排班ID")
    remark: Optional[str] = Field(default=None, max_length=255, description="备注")


class AppointmentData(BaseModel):
    """API-11 / API-12 响应 data（两处响应结构相同，接口文档 3.4.3 明说「同 3.4.2」）。"""

    appointmentId: str
    queueNo: Optional[str] = Field(default=None, description="就诊队列号")
    apptDate: Optional[date] = Field(default=None, description="就诊日期")
    timeSlot: Optional[str] = Field(default=None, description="时段")
    deptName: Optional[str] = Field(default=None, description="科室名称")
    doctorName: Optional[str] = Field(default=None, description="医生姓名")
    location: Optional[str] = Field(default=None, description="科室位置（楼层/诊区）")
    billId: Optional[str] = Field(default=None, description="关联挂号缴费账单ID")
    appointmentStatus: AppointmentStatus = Field(description="状态，初始为 BOOKED")


class AppointmentCancelData(BaseModel):
    """API-13 响应 data：appointmentStatus（返回 CANCELED）。"""

    appointmentId: str
    appointmentStatus: AppointmentStatus = Field(description="取消后状态，CANCELED")


class AppointmentHistoryItem(BaseModel):
    """挂号历史列表项（接口文档 API-14 响应 data.list 内元素，10 个字段）。"""

    appointmentId: str
    patientId: str
    patientName: str = Field(description="就诊人姓名")
    deptName: Optional[str] = Field(default=None, description="科室名称")
    doctorName: Optional[str] = Field(default=None, description="医生姓名")
    apptDate: Optional[date] = None
    timeSlot: Optional[str] = None
    queueNo: Optional[str] = None
    appointmentStatus: AppointmentStatus
    statusDesc: Optional[str] = Field(default=None, description="状态中文名，供前端直接展示")
    createTime: Optional[datetime] = Field(default=None, description="挂号时间")

    @field_serializer("createTime")
    def _serialize_create_time(self, value: Optional[datetime]) -> Optional[str]:
        """接口文档 2.1：时间统一 yyyy-MM-dd HH:mm:ss。"""
        return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


class AppointmentHistoryData(BaseModel):
    """分页信封（接口文档 2.1 分页约定）。"""

    total: int
    pageNum: int
    pageSize: int
    list: list[AppointmentHistoryItem]


class AppointmentReminderData(BaseModel):
    """API-15 响应 data。

    前 6 个字段是接口文档 3.4.6 列出的；后 3 个（estimatedWaitMinutes / estimateNote /
    inQueue）是前端 frontend/src/api/exams.js 的「候诊提醒」组件已经在用的
    ExamQueueData 同形字段（见 schemas/exam.py），补上后前端无论读哪一套都能用，
    不必为一个接口分叉出两套渲染逻辑。
    """

    appointmentId: str
    queueNo: Optional[str] = Field(default=None, description="我的队列号")
    currentNo: Optional[str] = Field(default=None, description="当前叫号（估算值）")
    peopleAhead: Optional[int] = Field(default=None, description="前方等待人数")
    estimatedTime: Optional[str] = Field(
        default=None, description="预计叫号时间（估算值，页面须标注「以现场为准」）"
    )
    remindBeforeMinutes: Optional[int] = Field(default=None, description="用户设置的提前提醒分钟数")
    estimatedWaitMinutes: Optional[int] = Field(default=None, description="预计等待分钟数（估算值）")
    estimateNote: str = Field(default=REMINDER_ESTIMATE_NOTE, description="估算说明，前端原样展示")
    inQueue: bool = Field(default=False, description="是否在候诊队列中；已取消/已完成的挂号单为 false")
    statusDesc: Optional[str] = Field(default=None, description="挂号状态中文名")


__all__ = [
    "APPOINTMENT_SOURCE_DESC",
    "APPOINTMENT_STATUS_DESC",
    "QUEUE_PREFIX_FEVER",
    "QUEUE_PREFIX_NORMAL",
    "REMINDER_ESTIMATE_NOTE",
    "AppointmentCancelData",
    "AppointmentCreateRequest",
    "AppointmentData",
    "AppointmentHistoryData",
    "AppointmentHistoryItem",
    "AppointmentReminderData",
    "AppointmentSource",
    "AppointmentStatus",
    "AppointmentUpdateRequest",
]
