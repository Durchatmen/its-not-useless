"""各 Agent 共用的检索与提示词装配工具。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.services.rag.prompts import collect_sources, format_context

if TYPE_CHECKING:
    from app.services.llm import Message


def search_knowledge(query: str, collection: str, *, top_k: int | None = None) -> tuple[str, list[str]]:
    """检索指定知识库，返回 (格式化好的上下文, 引用来源)。

    来源取实际命中的知识库名，而不是模型自述的出处 —— 这样响应里的 sources
    一定可追溯到真实检索结果，不会出现幻觉来源。

    retriever 延迟导入：它拖着一整条 AI 依赖链（torch / FlagEmbedding / pymilvus，
    装在 requirements-ai.txt），而报告解读、检查注意事项、病历解释只用得上大模型、
    用不上检索。这几条链路的 Agent 因此要能在没装 AI 依赖的机器上 import 成功，
    检索调用失败时各自降级 —— 与 exam_service._search_many 同样的理由。
    """
    from app.services.rag import retriever

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


def build_document_messages(
    *,
    system: str,
    context: str,
    document: str,
    header: str,
) -> list["Message"]:
    """按「系统提示 + 知识库资料 + 待处理文书」组装 messages。

    与 build_messages 只差最后一段的标签：那里是预诊分诊的「患者本轮描述」，
    而报告解读、检查注意事项、病历解释处理的是检查单 / 报告 / 病历，标签各不相同，
    由调用方用 header 指定（如「检查报告」「病历原文」），所以单独开一个而不去改
    已经在跑的预诊分诊。知识库资料同样放在 user 侧：它是本次的检索结果、逐次替换。
    """
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"【知识库资料】\n{context}\n\n【{header}】\n{document}"},
    ]


__all__ = ["build_document_messages", "build_messages", "search_knowledge"]
