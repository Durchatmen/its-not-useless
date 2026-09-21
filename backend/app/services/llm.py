"""Qwen 客户端：阿里云百炼的 OpenAI 兼容端点。

用 httpx 直连 `/chat/completions` 而不是引入 DashScope SDK —— 与项目「用 httpx 调大模型」
（技术选型 §二）的约定一致，且换服务商（自建 vLLM、其它兼容网关）只改 LLM_BASE_URL，
调用方代码一行都不用动。

两种调用形态：
  - `chat()`        非流式，一次性拿完整回复，适合内部判定、结构化抽取；
  - `chat_stream()` 流式，逐段产出增量文本，供 SSE 端点按 delta 事件推给前端。

本模块同步实现，与 rag/ 检索链（BGE 编码、Milvus 查询均为同步）保持一致；
FastAPI 侧用 `def` 端点即可让调用跑在线程池里，SSE 端点见 `app/services/sse.py`。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Sequence
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

ContentPart = dict[str, Any]
"""OpenAI 兼容端点的多模态 content 片段，如
{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}} 或
{"type": "input_audio", "input_audio": {"data": "...", "format": "wav"}}。"""

Message = dict[str, str | list[ContentPart]]
"""一条对话消息：{"role": ..., "content": "纯文本" 或 [多模态片段]}。

文本对话照旧传 str；图片/语音由调用方把 content 组装成 list 后原样透传，
本模块不做内容改写，因此 chat / chat_stream 两套文本路径不用改就能吃多模态。"""

_DATA_PREFIX = "data: "
_STREAM_DONE = "[DONE]"

_client: httpx.Client | None = None


class LLMError(RuntimeError):
    """调用大模型失败：未配置 Key、网络异常、HTTP 非 2xx、响应体不符合预期。"""


def get_client() -> httpx.Client:
    """进程内复用一个 httpx.Client，拿到连接池的便宜。"""
    global _client
    if _client is None:
        # 流式场景下 timeout 是「相邻两段数据之间的最长等待」，不是整个回复的总时长
        _client = httpx.Client(timeout=settings.llm_timeout)
    return _client


def reset_client() -> None:
    """丢弃缓存的连接（测试或改动 base_url / 超时后调用）。"""
    global _client
    _client = None


def _endpoint() -> str:
    # base_url 末尾有无斜杠都拼得出正确地址，避免 httpx base_url 合并时丢段
    return f"{settings.llm_base_url.rstrip('/')}/chat/completions"


def _headers() -> dict[str, str]:
    if not settings.llm_api_key:
        # 早点报清楚，别发一个注定 401 的请求
        raise LLMError("未配置 LLM_API_KEY，请在 backend/.env 里填入百炼的 API Key")
    return {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }


def _payload(
    messages: Sequence[Message],
    *,
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
    stream: bool,
) -> dict:
    return {
        "model": model or settings.llm_model,
        "messages": list(messages),
        "temperature": settings.llm_temperature if temperature is None else temperature,
        "max_tokens": settings.llm_max_tokens if max_tokens is None else max_tokens,
        "stream": stream,
    }


def chat(
    messages: Sequence[Message],
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """非流式调用，返回助手回复的完整文本。"""
    payload = _payload(messages, model=model, temperature=temperature, max_tokens=max_tokens, stream=False)

    try:
        response = get_client().post(_endpoint(), headers=_headers(), json=payload)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LLMError(f"大模型返回 HTTP {exc.response.status_code}: {exc.response.text[:200]}") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"调用大模型失败: {exc}") from exc

    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"响应体缺少 choices[0].message.content: {str(data)[:200]}") from exc
    return _extract_text(content)


def _extract_text(content: Any) -> str:
    """从回复里抽纯文本。

    文本模型返回 str；qwen-vl / qwen-omni 偶尔把 content 组织成片段数组
    （每个片段是 {"type": "text", "text": "..."}），这里统一抽成 str 再交出去。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "".join(parts)
    return str(content) if content else ""


def chat_stream(
    messages: Sequence[Message],
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Iterator[str]:
    """流式调用，逐段产出增量文本。

    只负责产出文本增量；sources / triageCard 等业务事件的封装由 `sse.py` 负责。
    异常在迭代过程中抛出，调用方需自行捕获（SSE 端点要把它转成 error 事件）。
    """
    payload = _payload(messages, model=model, temperature=temperature, max_tokens=max_tokens, stream=True)

    try:
        with get_client().stream("POST", _endpoint(), headers=_headers(), json=payload) as response:
            if response.status_code >= 400:
                # 此时 body 还没读，报状态码即可，别去读它（会破坏流式读取）
                raise LLMError(f"大模型返回 HTTP {response.status_code}")
            for line in response.iter_lines():
                text = _parse_sse_line(line)
                if text is _STREAM_DONE:
                    break
                if text:
                    yield text
    except httpx.HTTPError as exc:
        raise LLMError(f"调用大模型失败: {exc}") from exc


def _parse_sse_line(line: str) -> str | None:
    """解析一条 SSE 行：返回增量文本，`[DONE]` 原样返回，无内容的行返回 None。"""
    if not line.startswith(_DATA_PREFIX):
        # 空行分隔符、心跳/注释行等
        return None

    data = line[len(_DATA_PREFIX) :].strip()
    if data == _STREAM_DONE:
        return _STREAM_DONE

    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        logger.debug("跳过无法解析的 SSE 数据: %s", data[:120])
        return None

    choices = payload.get("choices") or []
    if not choices:
        return None
    # 流式响应里增量在 delta，不是 message
    return (choices[0].get("delta") or {}).get("content") or None


__all__ = ["LLMError", "Message", "chat", "chat_stream", "get_client", "reset_client"]
