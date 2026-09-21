"""多模态预诊分诊的 HTTP 接口（接口文档 3.3：API-08 提交、API-09 查询历史）。

本文件只做 HTTP 层的事：解析入参、拿 user_id、装配统一信封。业务一行都不在这里，
全在 `app.services.ai_service`；SSE 帧的字面格式在 `app.services.sse`。

`stream=true` 按文档 API-08 的说明不再套 JSON 信封，直接回 `text/event-stream`；
其余情况一律 `{code, message, data, timestamp}`（文档 2.4）。

`router` 由 `app/api/v1/router.py` 挂载 —— 那个文件属队友，此处不碰。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

import jwt
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal, get_session
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

# 文档 2.5 通用错误码表
_CODE_SUCCESS = 0
_CODE_PARAM_INVALID = 4001
_CODE_UNAUTHORIZED = 4002
_CODE_FORBIDDEN = 4003
_CODE_LLM_FAILED = 5002
_CODE_INTERNAL = 9999

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    # nginx 反代默认攒缓冲，会把 delta 憋成一坨再发，必须显式关掉
    "X-Accel-Buffering": "no",
}


# ---------------------------------------------------------------------------
# 临时：core 层还没提供的两块基础件
#   app/core/deps.py      登录依赖（解 JWT 取 user_id）—— 文档 2.2
#   app/core/response.py  统一响应信封              —— 文档 2.4
# 这两块由队友负责，主干上仍是空文件。下面按文档写了最小实现顶上，
# 等 core 就绪后整段删掉换成 import 即可，两个路由函数一行都不用改。
# ---------------------------------------------------------------------------


class _AuthFailed(Exception):
    """令牌缺失 / 无效 / 过期，对应错误码 4002。"""


def _current_user_id(authorization: str | None) -> str:
    """从 `Authorization: Bearer {accessToken}` 里解出 user_id。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _AuthFailed("缺少 Authorization: Bearer 令牌")

    token = authorization[7:].strip()
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise _AuthFailed(f"令牌无效或已过期：{exc}") from exc

    # auth 模块尚未落定 claim 名：sub 是 JWT 惯例，另两个是常见变体，都认
    user_id = claims.get("sub") or claims.get("userId") or claims.get("user_id")
    if not user_id:
        raise _AuthFailed("令牌里没有用户标识（sub / userId）")
    return str(user_id)


def _envelope(code: int, message: str, data) -> dict:
    """文档 2.4 的统一信封；timestamp 按 2.1 用东八区 `yyyy-MM-dd HH:mm:ss`。"""
    return {
        "code": code,
        "message": message,
        "data": data,
        "timestamp": datetime.now(ZoneInfo(settings.tz)).strftime("%Y-%m-%d %H:%M:%S"),
    }


def _error_code(status: int) -> int:
    return {
        400: _CODE_PARAM_INVALID,
        401: _CODE_UNAUTHORIZED,
        403: _CODE_FORBIDDEN,
        # 2.5 没有「资源不存在」这一档，归进参数校验，是谁不存在由 message 说明
        404: _CODE_PARAM_INVALID,
        # 语音/图片能力未接入，按服务不可用上报，比 9999 更贴近用户看到的话术
        501: _CODE_LLM_FAILED,
        502: _CODE_LLM_FAILED,
    }.get(status, _CODE_INTERNAL)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@router.post("/multimodal/messages", response_model=None, summary="API-08 提交多模态预诊输入")
def submit_message(
    payload: MultiModalMessageRequest,
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_session),
):
    """预诊分诊核心接口：文本/语音/图片进，AI 回复与分诊卡片出。

    同一个 sessionId 多次调用即多轮会话 —— 历史由 `ai_service` 从库里捞。
    """
    if payload.stream:
        return _stream_response(payload, authorization)

    try:
        user_id = _current_user_id(authorization)
    except _AuthFailed as exc:
        return _envelope(_CODE_UNAUTHORIZED, str(exc), None)

    try:
        result = ai_service.handle_message(db, user_id=user_id, **_call_args(payload))
    except AIServiceError as exc:
        logger.warning("API-08 失败: %s", exc)
        return _envelope(_error_code(exc.status_code), str(exc), None)

    return _envelope(_CODE_SUCCESS, "success", _to_data(result).model_dump(by_alias=True))


@router.get("/multimodal/sessions/{session_id}", summary="API-09 查询会话历史")
def get_session_history(
    session_id: str,
    authorization: Annotated[str | None, Header()] = None,
    page_num: Annotated[int, Query(alias="pageNum", ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 10,
    db: Session = Depends(get_session),
):
    """按时间正序分页返回某会话的多轮问答记录（文档 2.1 的 total/pageNum/pageSize/list）。"""
    try:
        user_id = _current_user_id(authorization)
    except _AuthFailed as exc:
        return _envelope(_CODE_UNAUTHORIZED, str(exc), None)

    try:
        messages, total = ai_service.list_messages(
            db,
            user_id=user_id,
            session_id=session_id,
            page_num=page_num,
            page_size=page_size,
        )
    except AIServiceError as exc:
        return _envelope(_error_code(exc.status_code), str(exc), None)

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
    return _envelope(_CODE_SUCCESS, "success", data.model_dump(by_alias=True))


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


def _stream_response(payload: MultiModalMessageRequest, authorization: str | None):
    try:
        user_id = _current_user_id(authorization)
    except _AuthFailed as exc:
        # 前端流式分支只看 response.ok（`api/sse.js`），鉴权失败必须用非 2xx 表达
        return JSONResponse(
            status_code=401, content=_envelope(_CODE_UNAUTHORIZED, str(exc), None)
        )

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
