"""多模态预诊分诊的 HTTP 接口（接口文档 3.3：API-08 提交、API-09 查询历史）。

本文件只做 HTTP 层的事：解析入参、取当前用户、装配统一信封。业务一行都不在这里，
全在 `app.services.ai_service`；SSE 帧的字面格式在 `app.services.sse`。

`stream=true` 按文档 API-08 的说明不再套 JSON 信封，直接回 `text/event-stream`；
其余情况一律 `{code, message, data, timestamp}`（文档 2.4）。

鉴权走 core 的 `get_current_user`（core/deps.py）：解 JWT **并查库**取 t_user，
因此账号被停用（status != 1）时会和其他模块一样被 403 拦下。

⚠ 流式分支的鉴权失败为什么仍要非 2xx：前端 `api/sse.js` 只看 `response.ok`，
   不解析 JSON 信封。所以 core/middleware.py 对「Accept: text/event-stream 的请求 +
   4002/4003」返回 401/403 而不是 200 + 信封（见那边的 _STREAM_STATUS）。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import BizError, ErrorCode
from app.core.response import Envelope
from app.db.session import SessionLocal, get_session
from app.models import User
from app.schemas.ai import (
    MultiModalMessageData,
    MultiModalMessageRequest,
    SessionHistoryData,
    SessionMessageItem,
    TriageCard,
)
from app.services import ai_service
from app.services.ai_service import AIServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI 预诊分诊"])

SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]

# HTTP 状态码 → 接口文档 2.5 业务码。
# 2.5 没有「资源不存在」这一档，404 归进参数校验，是谁不存在由 message 说明。
_STATUS_TO_CODE: dict[int, int] = {
    400: int(ErrorCode.PARAM_INVALID),
    401: int(ErrorCode.UNAUTHORIZED),
    403: int(ErrorCode.FORBIDDEN),
    404: int(ErrorCode.PARAM_INVALID),
    # 语音/图片能力未接入，按服务不可用上报，比 9999 更贴近用户看到的话术
    501: int(ErrorCode.LLM_FAILED),
    502: int(ErrorCode.LLM_FAILED),
    503: int(ErrorCode.RAG_FAILED),
}

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    # nginx 反代默认攒缓冲，会把 delta 憋成一坨再发，必须显式关掉
    "X-Accel-Buffering": "no",
}


def _raise_for_service_error(exc: AIServiceError) -> None:
    """AIServiceError → BizError（service 不依赖 core，两边各自独立）。"""
    code = _STATUS_TO_CODE.get(exc.status_code, int(ErrorCode.INTERNAL))
    logger.warning("AI 服务失败（HTTP %s）：%s", exc.status_code, exc)
    raise BizError(code, str(exc)) from exc


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@router.post("/multimodal/messages", response_model=None, summary="API-08 提交多模态预诊输入")
def submit_message(payload: MultiModalMessageRequest, session: SessionDep, user: UserDep):
    """预诊分诊核心接口：文本/语音/图片进，AI 回复与分诊卡片出。

    同一个 sessionId 多次调用即多轮会话 —— 历史由 `ai_service` 从库里捞。
    stream=true 时改回 SSE 流（delta / triageCard / sources / done / error）。
    """
    if payload.stream:
        return _stream_response(payload, user.user_id)

    try:
        result = ai_service.handle_message(session, user_id=user.user_id, **_call_args(payload))
    except AIServiceError as exc:
        _raise_for_service_error(exc)

    return Envelope.ok(_to_data(result).model_dump())


@router.get("/multimodal/sessions/{session_id}", summary="API-09 查询会话历史")
def get_session_history(
    session_id: str,
    session: SessionDep,
    user: UserDep,
    page_num: Annotated[int, Query(alias="pageNum", ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 10,
) -> Any:
    """按时间正序分页返回某会话的多轮问答记录（文档 2.1 的 total/pageNum/pageSize/list）。"""
    try:
        messages, total = ai_service.list_messages(
            session,
            user_id=user.user_id,
            session_id=session_id,
            page_num=page_num,
            page_size=page_size,
        )
    except AIServiceError as exc:
        _raise_for_service_error(exc)

    data = SessionHistoryData(
        total=total,
        page_num=page_num,
        page_size=page_size,
        items=[
            SessionMessageItem(
                message_id=item.message_id,
                role=item.role,
                input_type=item.input_type,
                text_content=item.text_content,
                reply=item.reply,
                create_time=item.create_time,
            )
            for item in messages
        ],
    )
    return Envelope.ok(data.model_dump())


# ---------------------------------------------------------------------------
# 内部装配
# ---------------------------------------------------------------------------


def _call_args(payload: MultiModalMessageRequest) -> dict:
    """请求模型 -> `ai_service` 的关键字参数（服务层不收 Enum，统一给字符串）。"""
    return {
        "input_type": payload.input_type.value,
        "text_content": payload.text_content or "",
        "audio_data": payload.audio_data or "",
        "image_data": payload.image_data or "",
        "audio_format": payload.audio_format.value if payload.audio_format else None,
        "session_id": payload.session_id,
        "patient_id": payload.patient_id,
    }


def _to_data(result: ai_service.PreConsultResult) -> MultiModalMessageData:
    return MultiModalMessageData(
        session_id=result.session_id,
        recognized_text=result.recognized_text,
        reply=result.reply,
        # model_validate 而非 TriageCard(**card)：模型偶尔多吐字段，直接解包会 TypeError
        triage_card=TriageCard.model_validate(result.triage_card) if result.triage_card else None,
        risk_warning=result.risk_warning,
        sources=result.sources,
        disclaimer=result.disclaimer,
        next_question=result.next_question,
    )


def _stream_response(payload: MultiModalMessageRequest, user_id: str) -> StreamingResponse:
    """流式分支：鉴权已由 UserDep 完成，这里只管把生成器包成 SSE 响应。"""
    return StreamingResponse(
        _stream_frames(payload, user_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


def _stream_frames(payload: MultiModalMessageRequest, user_id: str) -> Iterator[str]:
    """流式分支自己开会话，不用 FastAPI 注入的那个。

    带 yield 的依赖在响应发出前就收尾，会话会被提前 close，而生成器要一直跑到流结束，
    所以注入的 db 在流式分支里只当占位、不碰它。
    """
    db = SessionLocal()
    try:
        yield from ai_service.stream_message(db, user_id=user_id, **_call_args(payload))
    finally:
        db.close()


__all__ = ["router"]
