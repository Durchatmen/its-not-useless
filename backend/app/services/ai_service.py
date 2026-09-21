"""多模态预诊分诊的服务层编排（API-08 提交、API-09 查询）。

一次请求 = 一次图执行：本模块负责把请求翻译成 `PreConsultState`，跑图，再把
`reply` / `triageCard` / `sources` 等结果落库或推成 SSE 事件。路由层只管鉴权、
参数校验和响应信封，不碰业务。

两种返回形态共用同一条主干（`_prepare` -> 跑图 -> `_to_result` -> `_save_turn`）：
  - `handle_message`  非流式，等图跑完把结果整体返回；
  - `stream_message`  流式，节点的正文增量实时推 delta，收尾再补卡片与来源。
"""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_message import AiMessage
from app.models.ai_session import AiSession
from app.models.patient import Patient
from app.services.llm import LLMError
from app.services.rag.agents.graph import graph
from app.services.rag.ocr import audio_to_text, image_to_text
from app.services.rag.prompts import DISCLAIMER
from app.services.sse import (
    delta_event,
    done_event,
    error_event,
    sources_event,
    triage_card_event,
)

logger = logging.getLogger(__name__)

SCENE = "PRE_CONSULT"
"""本模块只跑预诊分诊场景；t_ai_session.scene 的取值范围见模型定义。"""

MAX_HISTORY_TURNS = 6
"""回喂大模型的历史轮数上限。预诊靠的是本轮症状，历史给多了既挤上下文又拖慢首字。"""

_MAX_VARCHAR = 255
"""t_ai_message 里 risk_warning / next_question / disclaimer 都是 String(255)。

模型偶尔话多，落库前按字符截断（utf8mb4 下 255 就是 255 个字），
否则 MySQL 严格模式会直接报错、整轮对话作废。
"""


class AIServiceError(RuntimeError):
    """业务层错误。带 `status_code`，路由层据此决定 HTTP 码，不必再猜异常类型。"""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class PreConsultResult:
    """一次预诊分诊的完整产出，字段与接口文档 API-08 的 data 一一对应。"""

    session_id: str
    recognized_text: str
    reply: str
    triage_card: dict | None
    risk_warning: str
    next_question: str
    sources: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


@dataclass
class SessionMessage:
    """API-09 的一条会话记录。"""

    message_id: str
    role: str
    input_type: str | None
    text_content: str | None
    reply: str | None
    create_time: datetime


@dataclass
class _Prepared:
    """跑图前的准备结果：会话行、图的初始状态、识别出的文本。"""

    session: AiSession
    state: dict
    recognized_text: str
    input_type: str


def _now() -> datetime:
    """当前时间，按 .env 的 TZ（东八区）取，且不带 tzinfo。

    文档 2.1 要求所有时间都是东八区，但 t_ai_message.created_at 是无时区的 DateTime，
    所以不能靠数据库的 `CURRENT_TIMESTAMP`（服务器时区未必是东八区，UTC 会差 8 小时），
    也不能带 tzinfo 写进去（MySQL 会把偏移丢掉）。
    """
    return datetime.now(ZoneInfo(settings.tz)).replace(tzinfo=None)


def _new_id(prefix: str) -> str:
    """生成 32 位以内的主键。

    时间戳精确到微秒且放在前面，让主键按字典序就等于按时间序 ——
    库里 created_at 只到秒，同一秒内的两轮对话（历史加载、API-09 分页）
    得靠主键来定先后，随机后缀放在末尾不影响排序。
    """
    return f"{prefix}{_now():%Y%m%d%H%M%S%f}{secrets.token_hex(4).upper()}"


def _recognize_text(
    input_type: str,
    text_content: str,
    audio_data: str,
    image_data: str,
    audio_format: str | None = None,
) -> str:
    """把本轮输入转成文字。

    TEXT 直接用原文；VOICE / IMAGE 走 Qwen 多模态（见 `rag/ocr.py`），
    识别得到的文字再进预诊链路，两种输入共用同一条纯文本主干。
    """
    if input_type == "TEXT":
        text = (text_content or "").strip()
        if not text:
            raise AIServiceError("inputType=TEXT 时 textContent 不能为空")
        return text

    if input_type == "VOICE":
        if not audio_data:
            raise AIServiceError("inputType=VOICE 时 audioData 不能为空")
        try:
            return audio_to_text(audio_data, audio_format)
        except LLMError as exc:
            raise AIServiceError(f"语音转写失败：{exc}", status_code=502) from exc

    if input_type == "IMAGE":
        if not image_data:
            raise AIServiceError("inputType=IMAGE 时 imageData 不能为空")
        try:
            return image_to_text(image_data)
        except LLMError as exc:
            raise AIServiceError(f"图片识别失败：{exc}", status_code=502) from exc

    raise AIServiceError(f"不支持的 inputType: {input_type}")


def _check_patient(db: Session, user_id: str, patient_id: str | None) -> None:
    """就诊人必须属于当前账号 —— 预诊会带上既往病史等隐私内容。"""
    if not patient_id:
        return
    owner = db.scalar(select(Patient.user_id).where(Patient.patient_id == patient_id))
    if owner is None:
        raise AIServiceError(f"就诊人不存在: {patient_id}", status_code=404)
    if owner != user_id:
        raise AIServiceError("无权使用该就诊人", status_code=403)


def _load_history(db: Session, session_id: str) -> list[dict]:
    """取最近若干轮对话，翻成正序后喂给大模型。

    先按时间倒序取「最近 N 轮」再翻正 —— 正序取会拿到最早的 N 轮，
    而多轮问诊里越近的信息越关键。

    每行的 `content` 是用户输入、`reply` 是 AI 回复（见 t_ai_message 模型注释），
    因此这里按字段有无还原角色，不依赖 `role` 列：库里 bot 行同样带 content。
    """
    rows = db.scalars(
        select(AiMessage)
        .where(AiMessage.session_id == session_id)
        .order_by(AiMessage.created_at.desc(), AiMessage.message_id.desc())
        .limit(MAX_HISTORY_TURNS)
    ).all()

    history: list[dict] = []
    for row in reversed(rows):
        if row.content:
            history.append({"role": "user", "content": row.content})
        if row.reply:
            history.append({"role": "assistant", "content": row.reply})
    return history


def _prepare(
    db: Session,
    *,
    user_id: str,
    input_type: str,
    text_content: str = "",
    audio_data: str = "",
    image_data: str = "",
    audio_format: str | None = None,
    session_id: str | None = None,
    patient_id: str | None = None,
) -> _Prepared:
    """校验入参、拿到或新建会话、装载历史，产出图的初始状态。"""
    _check_patient(db, user_id, patient_id)
    recognized = _recognize_text(input_type, text_content, audio_data, image_data, audio_format)

    if session_id:
        session = db.get(AiSession, session_id)
        if session is None:
            raise AIServiceError(f"会话不存在: {session_id}", status_code=404)
        if session.user_id != user_id:
            raise AIServiceError("无权访问该会话", status_code=403)
        history = _load_history(db, session.session_id)
    else:
        # 首轮：会话号由服务端生成后回填给前端，后续轮次带着它回来
        session = AiSession(
            session_id=_new_id("SES"),
            user_id=user_id,
            patient_id=patient_id,
            scene=SCENE,
            message_count=0,
            status=1,
        )
        db.add(session)
        db.commit()
        history = []

    return _Prepared(
        session=session,
        state={"session_id": session.session_id, "question": recognized, "history": history},
        recognized_text=recognized,
        input_type=input_type,
    )


def _save_turn(db: Session, prepared: _Prepared, result: PreConsultResult) -> None:
    """把这一轮问答落库，并回填会话上的预诊结论。"""
    card = result.triage_card or {}
    db.add(
        AiMessage(
            message_id=_new_id("MSG"),
            session_id=prepared.session.session_id,
            created_at=_now(),
            role="bot",
            input_type=prepared.input_type,
            content=prepared.recognized_text,
            reply=result.reply,
            triage_card=json.dumps(card, ensure_ascii=False) if card else None,
            risk_warning=result.risk_warning[:_MAX_VARCHAR] or None,
            next_question=result.next_question[:_MAX_VARCHAR] or None,
            sources=json.dumps(result.sources, ensure_ascii=False) if result.sources else None,
            disclaimer=result.disclaimer[:_MAX_VARCHAR],
        )
    )
    prepared.session.message_count = (prepared.session.message_count or 0) + 1
    if card.get("department"):
        prepared.session.department = card["department"][:64]
    db.commit()


def _to_result(prepared: _Prepared, state: dict) -> PreConsultResult:
    return PreConsultResult(
        session_id=prepared.session.session_id,
        recognized_text=prepared.recognized_text,
        reply=state.get("reply") or "",
        triage_card=state.get("triage_card"),
        risk_warning=state.get("risk_warning") or "",
        next_question=state.get("next_question") or "",
        sources=state.get("sources") or [],
    )


def handle_message(
    db: Session,
    *,
    user_id: str,
    input_type: str,
    text_content: str = "",
    audio_data: str = "",
    image_data: str = "",
    audio_format: str | None = None,
    session_id: str | None = None,
    patient_id: str | None = None,
) -> PreConsultResult:
    """非流式预诊分诊：跑完整张图再落库返回。"""
    prepared = _prepare(
        db,
        user_id=user_id,
        input_type=input_type,
        text_content=text_content,
        audio_data=audio_data,
        image_data=image_data,
        audio_format=audio_format,
        session_id=session_id,
        patient_id=patient_id,
    )

    try:
        state = graph.invoke(prepared.state)
    except LLMError as exc:
        raise AIServiceError(f"大模型调用失败：{exc}", status_code=502) from exc

    result = _to_result(prepared, state)
    _save_turn(db, prepared, result)
    return result


def stream_message(
    db: Session,
    *,
    user_id: str,
    input_type: str,
    text_content: str = "",
    audio_data: str = "",
    image_data: str = "",
    audio_format: str | None = None,
    session_id: str | None = None,
    patient_id: str | None = None,
) -> Iterator[str]:
    """流式预诊分诊：产出 SSE 事件帧。

    HTTP 状态码在首个事件发出时就定死了，准备阶段的错误因此不能再靠状态码表达，
    统一转成 error 事件（前端 `useSse` 收到后走 fail 分支）。

    客户端中途断开时生成器会被 close，收尾的落库自然跳过 —— 半截的回复不值得存。
    """
    try:
        prepared = _prepare(
            db,
            user_id=user_id,
            input_type=input_type,
            text_content=text_content,
            audio_data=audio_data,
            image_data=image_data,
            audio_format=audio_format,
            session_id=session_id,
            patient_id=patient_id,
        )
    except AIServiceError as exc:
        yield error_event(str(exc))
        return

    final_state: dict = {}
    try:
        # custom 通道拿节点写的正文增量，values 通道拿最终状态（分诊卡片只在这里）
        for mode, chunk in graph.stream(prepared.state, stream_mode=["custom", "values"]):
            if mode == "custom":
                yield delta_event(chunk)
            else:
                final_state = chunk
    except LLMError as exc:
        logger.warning("预诊流式中断: %s", exc)
        yield error_event(f"大模型调用失败：{exc}")
        return

    result = _to_result(prepared, final_state)
    _save_turn(db, prepared, result)

    yield triage_card_event(result.triage_card)
    yield sources_event(result.sources)
    yield done_event(
        session_id=result.session_id,
        recognized_text=result.recognized_text,
        risk_warning=result.risk_warning,
        next_question=result.next_question,
        disclaimer=result.disclaimer,
    )


def list_messages(
    db: Session, *, user_id: str, session_id: str, page_num: int = 1, page_size: int = 20
) -> tuple[list[SessionMessage], int]:
    """API-09 会话历史：按时间正序分页，返回 (本轮消息, 总条数)。

    一行 t_ai_message 承载一轮完整问答，所以这里一行对应一条记录，
    `role` 沿用库里的值（首次入库的 bot 行同时带 content 与 reply）。
    """
    session = db.get(AiSession, session_id)
    if session is None:
        raise AIServiceError(f"会话不存在: {session_id}", status_code=404)
    if session.user_id != user_id:
        raise AIServiceError("无权访问该会话", status_code=403)

    total = db.scalar(
        select(func.count()).select_from(AiMessage).where(AiMessage.session_id == session_id)
    )
    rows = db.scalars(
        select(AiMessage)
        .where(AiMessage.session_id == session_id)
        .order_by(AiMessage.created_at.asc(), AiMessage.message_id.asc())
        .offset((page_num - 1) * page_size)
        .limit(page_size)
    ).all()

    messages = [
        SessionMessage(
            message_id=row.message_id,
            role=row.role,
            input_type=row.input_type,
            text_content=row.content,
            reply=row.reply,
            create_time=row.created_at,
        )
        for row in rows
    ]
    return messages, total or 0


__all__ = [
    "AIServiceError",
    "MAX_HISTORY_TURNS",
    "PreConsultResult",
    "SessionMessage",
    "handle_message",
    "list_messages",
    "stream_message",
]
