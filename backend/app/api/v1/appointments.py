"""挂号接口（接口文档 3.4.2 ~ 3.4.6：API-11 ~ API-15）。

本文件只做 HTTP 适配，业务规则全在 `services/appointment_service.py`。

前端契约：frontend/src/api/appointments.js
    POST   /appointments                             创建挂号
    PUT    /appointments/{appointmentId}             修改挂号（改期）
    DELETE /appointments/{appointmentId}             取消挂号
    GET    /appointments/history                     挂号历史
    GET    /appointments/{appointmentId}/reminder    候诊提醒

⚠ 路由顺序：`/history` 必须声明在 `/{appointmentId}` 之前，否则 "history" 会被当作
   appointmentId 匹配进路径参数里。本模块不实现 GET /{appointmentId}（前端没有这个调用），
   但 `/history` 与 `/{appointmentId}/reminder` 的先后仍按「静态路径优先」排布。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Callable, Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import BizError
from app.core.response import Envelope
from app.db.session import get_session
from app.models import User
from app.schemas.appointment import AppointmentCreateRequest, AppointmentUpdateRequest
from app.services import appointment_service
from app.services.appointment_service import AppointmentError

router = APIRouter(prefix="/appointments", tags=["挂号模块"])

SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]

AppointmentId = Annotated[str, Path(description="挂号单ID")]


def _call(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """执行业务函数并套统一信封。

    AppointmentError → BizError 的转换收在这一处：service 不依赖 core，core 不感知
    挂号模块的错误码（2001/2002/2003），两边各自独立。
    """
    try:
        data = action(*args, **kwargs)
    except AppointmentError as exc:
        raise BizError(exc.code, exc.message) from exc
    return Envelope.ok(data)


@router.post("", summary="API-11 预约挂号")
def create_appointment(
    payload: AppointmentCreateRequest,
    session: SessionDep,
    user: UserDep,
) -> Any:
    """手动挂号（AI 自动挂号复用本接口，由 source 区分来源）。

    号源被占用或时段已满返回 2001；就诊人不存在或不属于当前账号返回 2003。
    挂号成功会同步生成一张 billType=REGISTRATION 的待缴费账单，其编号在 billId 中返回。
    """
    return _call(
        appointment_service.create_appointment, session, user_id=user.user_id, payload=payload
    )


@router.get("/history", summary="API-14 查询历史挂号")
def list_appointment_history(
    session: SessionDep,
    user: UserDep,
    patientId: Annotated[
        Optional[str], Query(description="按就诊人过滤，不传返回全部就诊人")
    ] = None,
    appointmentStatus: Annotated[
        Optional[str],
        Query(description="按状态过滤：BOOKED / CHECKED_IN / FINISHED / CANCELED"),
    ] = None,
    status: Annotated[
        Optional[str],
        Query(
            description=(
                "appointmentStatus 的别名（前端 appointments.js 传的是 status）。"
                "同时传时以 appointmentStatus 为准"
            )
        ),
    ] = None,
    startDate: Annotated[Optional[date], Query(description="起始日期 yyyy-MM-dd")] = None,
    endDate: Annotated[Optional[date], Query(description="结束日期 yyyy-MM-dd")] = None,
    pageNum: Annotated[int, Query(ge=1, description="页码，从 1 开始")] = 1,
    pageSize: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 10,
) -> Any:
    """查询当前账号的全部历史挂号，按时间倒序分页。

    每项含就诊人、科室、医生、就诊日期、时段、队列号、状态与挂号时间。

    ⚠ 状态入参的两处名字（appointmentStatus 与 status）都收：接口文档的 query 参数名是
    appointmentStatus，而前端 `listAppointmentHistory()` 传的是 status。按「文档是权威契约、
    前端硬约束也不能破」处理，两个都认。
    """
    return _call(
        appointment_service.list_history,
        session,
        user_id=user.user_id,
        patient_id=patientId,
        appointment_status=appointmentStatus or status,
        start_date=startDate,
        end_date=endDate,
        page_num=pageNum,
        page_size=pageSize,
    )


@router.get("/{appointmentId}/reminder", summary="API-15 挂号提醒查询")
def get_appointment_reminder(
    appointmentId: AppointmentId,
    session: SessionDep,
    user: UserDep,
    remindBeforeMinutes: Annotated[
        Optional[int],
        Query(ge=0, le=240, description="提前提醒分钟数（服务端仅记录用户偏好）"),
    ] = None,
) -> Any:
    """查询候诊进度：我的队列号、当前叫号、前方人数与预计叫号时间。

    ⚠ 库中不存 HIS 的叫号队列，currentNo / peopleAhead / estimatedTime 均为**本地估算**
    （前方人数 × 平均问诊时长），响应固定带 estimateNote，页面须标注「以现场为准」。
    已取消 / 已完成的挂号单不在队列中：inQueue=false 且叫号字段为 null。
    """
    return _call(
        appointment_service.get_reminder,
        session,
        appointmentId,
        user_id=user.user_id,
        remind_before_minutes=remindBeforeMinutes,
    )


@router.put("/{appointmentId}", summary="API-12 修改挂号")
def update_appointment(
    appointmentId: AppointmentId,
    payload: AppointmentUpdateRequest,
    session: SessionDep,
    user: UserDep,
) -> Any:
    """修改挂号信息（改期/更换时段）：释放原时段号源并锁定新号源。

    新时段满号返回 2001（此时原号源不会释放，用户不会两头落空）；
    已取号/已完成/已取消的挂号单不允许改期，返回 2002。
    """
    return _call(
        appointment_service.update_appointment,
        session,
        appointmentId,
        user_id=user.user_id,
        payload=payload,
    )


@router.delete("/{appointmentId}", summary="API-13 取消挂号")
def cancel_appointment(appointmentId: AppointmentId, session: SessionDep, user: UserDep) -> Any:
    """取消挂号，释放号源并返回 appointmentStatus=CANCELED。

    已取号（CHECKED_IN）或关联账单已缴费的挂号单不允许取消，返回 2002。
    未缴费的挂号费账单会一并置为 REFUNDED。
    """
    return _call(
        appointment_service.cancel_appointment, session, appointmentId, user_id=user.user_id
    )


__all__ = ["router"]
