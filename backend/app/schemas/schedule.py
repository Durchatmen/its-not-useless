"""排班模块数据契约（《接口文档》3.4.1：API-10 查询排班与号源）。

字段名与接口文档一致（camelCase、主键 string），前端 frontend/src/api/appointments.js
的 listSchedules() 直接对接（注意：排班接口挂在 appointments.js 里，没有独立的
frontend/src/api/schedules.js）。

金额一律声明为 `float`：库里是 Numeric(10,2)（Decimal），而 Pydantic 会把 Decimal
序列化成字符串，前端也没有 Number() 兜底 —— 接口文档写的是 number，必须是 number。
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class ScheduleListItem(BaseModel):
    """排班列表项（接口文档 API-10 响应 data.list 内元素）。"""

    scheduleId: str
    deptCode: str = Field(description="科室编码（即 t_department.dept_id）")
    deptName: str = Field(description="科室名称")
    doctorId: str
    doctorName: str
    doctorTitle: Optional[str] = Field(default=None, description="职称")
    specialty: Optional[str] = Field(default=None, description="擅长方向（用于按病种排序推荐）")
    apptDate: Optional[date] = Field(default=None, description="就诊日期 yyyy-MM-dd")
    timeSlot: str = Field(description="时段，如 08:30-09:00")
    fee: float = Field(description="挂号费（元）")
    remaining: int = Field(description="剩余号源数")


class ScheduleListData(BaseModel):
    """分页信封（接口文档 2.1 分页约定）。

    接口文档 API-10 的请求参数表里没有分页项，但响应写的是「data.list 内元素」，
    且前端 listSchedules() 会传 pageNum/pageSize。这里返回全局分页信封，
    是文档与前端的超集：不传分页参数时按 pageSize=20 返回第一页。
    """

    total: int
    pageNum: int
    pageSize: int
    list: list[ScheduleListItem]


__all__ = [
    "ScheduleListData",
    "ScheduleListItem",
]
