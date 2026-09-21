"""排班业务逻辑（《接口文档》3.4.1：API-10 查询排班与号源）。

分层约定与其他模块一致：本模块只依赖 SQLAlchemy 会话，不感知 HTTP。

接口文档把本接口的对接系统写成「医院HIS系统」，而排班表 t_schedule 在本系统里有
完整副本（seed 已灌入），所以本期直接读本地库：HIS 未接入时不影响挂号主流程，
接入后由 app/services/his.py 的同步任务往 t_schedule 灌数据，本接口一行都不用改。

学院科入参有一处文档与前端不一致，见 list_schedules 的说明。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.doctor import Doctor
from app.models.schedule import Schedule
from app.schemas.schedule import ScheduleListData, ScheduleListItem

# date 不传时的默认查询窗口：当天起 7 天（接口文档 API-10「默认当天起7天」）
DEFAULT_DAYS_WINDOW = 7

# 只有出诊状态正常的医生的排班才会被展示（t_doctor.visit_status：1正常 2停诊 3替诊）
DOCTOR_VISIT_NORMAL = 1


class ScheduleError(Exception):
    """排班模块业务错误。

    code 取接口文档 2.5 通用错误码表；本模块目前只在日期格式不合法时用 4001
    （大部分格式问题会被 FastAPI 的 query 校验拦下，这里兜住手工传参的情况）。
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def list_schedules(
    session: Session,
    *,
    dept_code: Optional[str] = None,
    doctor_id: Optional[str] = None,
    date_value: Optional[date] = None,
    only_available: bool = True,
    page_num: int = 1,
    page_size: int = 20,
) -> ScheduleListData:
    """查询科室/医生的排班表与分时段号源余量（接口文档 API-10）。

    ⚠ 科室入参的不一致：接口文档的 query 参数名是 `deptCode`，而前端
    frontend/src/api/appointments.js 的 listSchedules() 传的是 `deptId`。
    两个名字指向的是同一列 —— t_department 只有 dept_id 这一个编码列
    （设计文档里「科室编码」就是 dept_id），所以接口层两个参数名都收，
    映射到这里的同一个 dept_code。按「文档是权威契约，前端硬约束也不能破」处理。

    only_available=True（默认）时只返回 remaining > 0 且医生出诊状态正常的排班。
    停诊/替诊（visit_status != 1）的医生整体排除 —— 号还在但医生不出诊，
    让用户选中只会变成一次失败的挂号。

    date 不传时按文档取「当天起 7 天」窗口。排班是公共资源，不做账号归属校验。
    """
    today = date.today()
    start = date_value or today
    end = start + timedelta(days=DEFAULT_DAYS_WINDOW - 1) if date_value is None else start

    conditions = [Schedule.appt_date >= start, Schedule.appt_date <= end]
    if dept_code:
        conditions.append(Schedule.dept_id == dept_code)
    if doctor_id:
        conditions.append(Schedule.doctor_id == doctor_id)
    if only_available:
        conditions.append(Schedule.remaining > 0)
        conditions.append(Doctor.visit_status == DOCTOR_VISIT_NORMAL)

    # 计数与取数都要 join Doctor（only_available 时会用到 visit_status），
    # 用同一个 join 条件，避免两处写法漂移
    def _base(stmt):  # type: ignore[no-untyped-def]
        return stmt.join(Doctor, Schedule.doctor_id == Doctor.doctor_id).join(
            Department, Schedule.dept_id == Department.dept_id
        )

    total = session.scalar(
        _base(select(func.count()).select_from(Schedule).where(*conditions))
    ) or 0

    rows = session.execute(
        _base(select(Schedule, Doctor, Department).where(*conditions))
        .order_by(
            Schedule.appt_date.asc(),
            Schedule.time_slot.asc(),
            # 第三键保稳定：同一时段多个医生时，分页翻页不会出现重复/漏行
            Schedule.schedule_id.asc(),
        )
        .offset((page_num - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        ScheduleListItem(
            scheduleId=schedule.schedule_id,
            deptCode=dept.dept_id,
            deptName=dept.dept_name,
            doctorId=doctor.doctor_id,
            doctorName=doctor.name,
            doctorTitle=doctor.title,
            specialty=doctor.specialty,
            apptDate=schedule.appt_date,
            timeSlot=schedule.time_slot,
            # Decimal → float：出口不做这一步，Pydantic 会序列化成字符串 "50.00"
            fee=float(schedule.fee or 0),
            remaining=schedule.remaining,
        )
        for schedule, doctor, dept in rows
    ]

    return ScheduleListData(total=total, pageNum=page_num, pageSize=page_size, list=items)


__all__ = [
    "DEFAULT_DAYS_WINDOW",
    "DOCTOR_VISIT_NORMAL",
    "ScheduleError",
    "list_schedules",
]
