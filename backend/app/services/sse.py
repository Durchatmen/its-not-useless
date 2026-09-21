"""API-08 流式响应的事件帧（`text/event-stream`）。

前端 `frontend/src/api/sse.js` 按空行切事件块，读 `event:` 作事件名、`data:` 作 JSON；
`frontend/src/composables/useSse.js` 逐个消费载荷。事件名和载荷形状是前后端约定，
改这里必须同步改前端：

    delta       {"text": "..."}   逐段追加到气泡正文
    triageCard  {...}             分诊卡片对象，未确定科室时推 null
    sources     [...]             引用来源数组
    done        {...}             收尾字段（会话号、识别文本、预警、免责声明、追问）
    error       {"message": "..."} 异常提示

本模块只做帧组装、不碰网络与数据库：AI 服务层拿到大模型文本块后调用这里拼帧。
"""

from __future__ import annotations

import json
from typing import Any

EVENT_DELTA = "delta"
EVENT_TRIAGE_CARD = "triageCard"
EVENT_SOURCES = "sources"
EVENT_DONE = "done"
EVENT_ERROR = "error"


def format_event(event: str, data: Any) -> str:
    """拼一个 SSE 事件帧。

    载荷统一走 json.dumps：正文里的换行会被转义成 \\n，不会提前撞上 SSE 的
    空行分隔符把事件截断。ensure_ascii=False 保住中文原文。
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def delta_event(text: str) -> str:
    return format_event(EVENT_DELTA, {"text": text})


def triage_card_event(card: dict | None) -> str:
    return format_event(EVENT_TRIAGE_CARD, card)


def sources_event(sources: list[str]) -> str:
    return format_event(EVENT_SOURCES, sources)


def done_event(
    *,
    session_id: str,
    recognized_text: str = "",
    risk_warning: str = "",
    next_question: str = "",
    disclaimer: str = "",
) -> str:
    """收尾帧。

    这些字段没有独立的流式时机（要么是整轮结束才知道的，要么前端只在一处渲染），
    所以一并挂在 done 上，前端 `finish(payload)` 直接铺进消息对象。
    """
    return format_event(
        EVENT_DONE,
        {
            "sessionId": session_id,
            "recognizedText": recognized_text,
            "riskWarning": risk_warning,
            "nextQuestion": next_question,
            "disclaimer": disclaimer,
        },
    )


def error_event(message: str) -> str:
    """异常帧。流已经开始后再出错不能再改 HTTP 状态码，只能靠它告诉前端。"""
    return format_event(EVENT_ERROR, {"message": message})


__all__ = [
    "EVENT_DELTA",
    "EVENT_DONE",
    "EVENT_ERROR",
    "EVENT_SOURCES",
    "EVENT_TRIAGE_CARD",
    "delta_event",
    "done_event",
    "error_event",
    "format_event",
    "sources_event",
    "triage_card_event",
]
