"""排班接口（接口文档 3.4.1：API-10 查询排班与号源）。

本文件只做 HTTP 适配，业务规则全在 `services/schedule_service.py`。

前端契约：frontend/src/api/appointments.js 的 listSchedules()
    GET /schedules?deptId=&doctorId=&date=&pageNum=&pageSize=

⚠ 科室入参的两个名字（deptCode 与 deptId）都收，原因见 schedule_service.list_schedules。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Callable, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import BizError
from app.core.response import Envelope
from app.db.session import get_session
from app.models import User
from app.services import schedule_service
from app.services.schedule_service import ScheduleError

router = APIRouter(prefix="/schedules", tags=["挂号模块"])

SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]


def _call(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """执行业务函数并套统一信封。"""
    try:
        data = action(*args, **kwargs)
    except ScheduleError as exc:
        raise BizError(exc.code, exc.message) from exc
    return Envelope.ok(data)


@router.get("", summary="API-10 查询排班与号源")
def list_schedules(
    session: SessionDep,
    user: UserDep,
    deptCode: Annotated[
        Optional[str], Query(description="科室编码，不传返回全部科室")
    ] = None,
    deptId: Annotated[
        Optional[str],
        Query(
            description=(
                "科室编码（接口文档名为 deptCode；前端 appointments.js 传的是 deptId，"
                "两者等价，都指向 t_department.dept_id）。同时传时以 deptId 为准"
            )
        ),
    ] = None,
    doctorId: Annotated[
        Optional[str], Query(description="医生ID，不传返回全部医生")
    ] = None,
    date: Annotated[
        Optional[date],
        Query(description="就诊日期 yyyy-MM-dd，不传按当天起 7 天窗口返回"),
    ] = None,
    onlyAvailable: Annotated[
        bool, Query(description="是否仅返回有号时段，默认 true")
    ] = True,
    pageNum: Annotated[int, Query(ge=1, description="页码，从 1 开始")] = 1,
    pageSize: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
) -> Any:
    """查询科室/医生的排班表与分时段号源余量，供手动挂号与 AI 自动挂号选择时段。

    每项返回排班ID、科室、医生（姓名/职称/擅长方向）、就诊日期、时段、挂号费与剩余号源。
    默认只返回有号且医生正常出诊的时段；传 onlyAvailable=false 可拿到满号/停诊的时段。
    """
    return _call(
        schedule_service.list_schedules,
        session,
        # deptId 优先：前端只传 deptId，文档读者只传 deptCode，两者同时出现时以前端字段为准
        dept_code=deptId or deptCode,
        doctor_id=doctorId,
        date_value=date,
        only_available=onlyAvailable,
        page_num=pageNum,
        page_size=pageSize,
    )


__all__ = ["router"]
