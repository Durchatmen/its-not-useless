"""检查模块接口（接口文档 3.8：API-24 ~ API-29，另有检查列表）。

本文件只做 HTTP 适配：解析入参、取当前账号、把领域错误翻成接口文档 2.5 的
错误码、套统一信封。业务规则全在 `services/exam_service.py`。

⚠ 对接说明（core/ 目前是空文件，本模块按《环境搭建方案》§4.7 的约定引用）：
    app.core.deps.get_current_user  —— Bearer 鉴权依赖，返回 t_user 对象（取 .user_id）
    app.core.response.ok            —— 统一信封 code/message/data/timestamp
    app.core.errors.BizError        —— 业务异常，由全局异常处理器输出信封
  这三处是唯一的耦合点，core 落地时若命名不同，改上面的 import 即可。
"""

from __future__ import annotations

from typing import Annotated, Any, Callable, Optional

from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user  # type: ignore[attr-defined]
from app.core.errors import BizError  # type: ignore[attr-defined]
from app.core.response import ok  # type: ignore[attr-defined]
from app.db.session import get_session
from app.schemas.exam import ExamAnalysisRequest
from app.services import exam_service
from app.services.exam_service import ExamError

router = APIRouter(prefix="/exams", tags=["检查模块"])

SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[Any, Depends(get_current_user)]

ExamId = Annotated[str, Path(description="检查单ID")]


def _call(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """执行业务函数并套统一信封。

    ExamError → BizError 的转换收在这一处：service 不依赖 core，core 不感知
    检查模块的错误码，两边各自独立。
    """
    try:
        data = action(*args, **kwargs)
    except ExamError as exc:
        raise BizError(exc.code, exc.message) from exc
    return ok(data)


@router.get("", summary="检查列表（按日期倒序）")
def list_exams(
    session: SessionDep,
    user: UserDep,
    patientId: Annotated[
        Optional[str], Query(description="就诊人编号，不传返回该账号下全部就诊人的检查")
    ] = None,
    examStatus: Annotated[
        Optional[str],
        Query(description="状态过滤：WAIT_PAY / WAIT_EXAM / WAIT_REPORT / REPORTED"),
    ] = None,
    pageNum: Annotated[int, Query(ge=1, description="页码，从 1 开始")] = 1,
    pageSize: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 10,
) -> Any:
    """查询当前账号（可指定就诊人）的全部检查，最近的排在最前面。

    每项返回检查名称、检查状态、执行科室、所在楼栋/楼层/房间，以及报告状态，
    供「检查与报告」列表页一屏展示；按「预约日期，缺省回落开单日期」倒序。
    """
    return _call(
        exam_service.list_exams,
        session,
        user_id=user.user_id,
        patient_id=patientId,
        exam_status=examStatus,
        page_num=pageNum,
        page_size=pageSize,
    )


@router.get("/{examId}/precautions", summary="API-24 检查注意事项")
def get_exam_precautions(examId: ExamId, session: SessionDep, user: UserDep) -> Any:
    """按检查项目返回注意事项（如空腹、憋尿），来自检查知识库；附检查目的与流程。

    同时返回 voiceText（语音播报文本）与 sources（知识库引用），
    供检查指引页做大字/语音等无障碍播报。
    """
    return _call(exam_service.get_precautions, session, examId, user.user_id)


@router.get("/{examId}/queue", summary="API-25 检查叫号查询")
def get_exam_queue(examId: ExamId, session: SessionDep, user: UserDep) -> Any:
    """查询检查排队信息：我的排队号、当前叫号、前方人数与预计等待时间。

    预计等待分钟数为估算值（响应中的 estimateNote 已注明）；
    已报告/待缴费的检查单不在队列中，此时 inQueue=false 且各排队字段为 null。
    """
    return _call(exam_service.get_queue, session, examId, user.user_id)


@router.get("/{examId}/location", summary="API-26 检查位置指引")
def get_exam_location(examId: ExamId, session: SessionDep, user: UserDep) -> Any:
    """返回检查所在科室与楼栋/楼层/房间，并给出跳转院内导航的链接。"""
    return _call(exam_service.get_location, session, examId, user.user_id)


@router.get("/{examId}/report", summary="API-27 检查报告查询")
def get_exam_report(examId: ExamId, session: SessionDep, user: UserDep) -> Any:
    """查询检查报告：报告状态、报告时间、结构化指标项与报告原图地址。

    报告尚未出具不算错误（reportStatus=WAIT_REPORT，reportId 与指标为空），
    前端可据此展示「待报告」并等待推送，不必靠错误码判断。
    """
    return _call(exam_service.get_report, session, examId, user.user_id)


@router.get("/{examId}/status", summary="API-28 检查状态查询")
def get_exam_status(examId: ExamId, session: SessionDep, user: UserDep) -> Any:
    """返回检查状态与中文描述，并给出 steps 进度条节点供前端直接渲染。"""
    return _call(exam_service.get_status, session, examId, user.user_id)


@router.post("/{examId}/report/analysis", summary="API-29 检查报告 AI 分析")
def analyze_exam_report(
    examId: ExamId,
    session: SessionDep,
    user: UserDep,
    payload: Annotated[Optional[ExamAnalysisRequest], Body()] = None,
) -> Any:
    """把检查报告转成通俗语言：逐项解释异常指标、给出风险等级与初步建议。

    响应固定携带 disclaimer；报告未出具时返回 4001。
    请求体可带 sessionId 以支持多轮追问（followUpUrl 会带上会话）。
    """
    return _call(exam_service.analyze_report, session, examId, user.user_id, payload)


__all__ = ["router"]
