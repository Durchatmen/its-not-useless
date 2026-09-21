"""预诊分诊 Agent 共用的检索与提示词装配工具。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.services.rag import retriever
from app.services.rag.prompts import collect_sources, format_context

if TYPE_CHECKING:
    from app.services.llm import Message


def search_knowledge(query: str, collection: str, *, top_k: int | None = None) -> tuple[str, list[str]]:
    """检索指定知识库，返回 (格式化好的上下文, 引用来源)。

    来源取实际命中的知识库名，而不是模型自述的出处 —— 这样响应里的 sources
    一定可追溯到真实检索结果，不会出现幻觉来源。
    """
    chunks = retriever.retrieve(query, collection, top_k=top_k)
    return format_context(chunks), collect_sources(chunks)


def build_messages(
    *,
    system: str,
    question: str,
    context: str,
    history: Sequence["Message"] = (),
) -> list["Message"]:
    """按「系统提示 + 历史对话 + 本轮问题（附知识库资料）」组装 messages。

    知识库资料放进本轮 user 消息而非 system：它是「这一问」的检索结果，
    多轮时逐轮替换，放在 user 侧既贴合 OpenAI 兼容端点的长上下文用法，
    也不会让系统提示随每轮检索结果膨胀。
    """
    messages: list["Message"] = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append(
        {
            "role": "user",
            "content": f"【知识库资料】\n{context}\n\n【患者本轮描述】\n{question}",
        }
    )
    return messages


__all__ = ["build_messages", "search_knowledge"]
