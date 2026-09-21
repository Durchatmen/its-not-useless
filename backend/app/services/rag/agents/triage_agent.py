"""分诊 Agent：把预诊给出的科室结论，落实成科室位置与推荐医生。

对应功能设计 §4.2 的「分诊 Agent」——触发场景是挂号环节，职责是结合
医生擅长与号源推荐具体医生。这里只补全 triageCard，不重写预诊的正文：
一次 API-08 调用只回一段 reply，语气由预诊节点统一把握，分诊正文若也拼进去
会前后重复、口径不一。
"""

from __future__ import annotations

from app.services.llm import chat
from app.services.rag.agents.state import PreConsultState
from app.services.rag.agents.tools import build_messages, search_knowledge
from app.services.rag.prompts import TRIAGE_SYSTEM, split_reply_and_result

NODE_NAME = "triage"
"""图里的节点名，graph.py 组装时引用。"""

COLLECTION = "kb_triage"
"""科室及医生知识库；对应的 docs/ 目录名与 collections.py 记录不一致，见项目备忘。"""


def _build_query(question: str, department: str) -> str:
    """把「症状 + 推荐科室」拼成检索词。

    只拿症状去分诊库检索，召回的多是泛泛的科室介绍；带上科室名才能命中
    该科室的诊区位置与医生擅长条目。
    """
    return f"{question} {department}".strip() if department else question


def triage_node(state: PreConsultState) -> dict:
    """LangGraph 节点：检索科室医生库 -> 调用大模型 -> 补全分诊卡片。

    sources 与上一节点的结果合并去重：一次调用的响应要同时体现两个库都被用到了。
    reply 有意不返回，LangGraph 会沿用预诊节点写入的正文。
    """
    question = state.get("question") or ""
    card = state.get("triage_card") or {}
    department = card.get("department") or ""

    context, sources = search_knowledge(_build_query(question, department), COLLECTION)
    messages = build_messages(
        system=TRIAGE_SYSTEM,
        question=_build_query(question, department),
        context=context,
        history=state.get("history") or [],
    )

    _, data = split_reply_and_result(chat(messages))

    merged = list(state.get("sources") or [])
    merged.extend(name for name in sources if name not in merged)
    return {
        "triage_context": context,
        # 分诊库查不到科室就退回预诊的卡片，宁可少填位置也不要退回 None
        "triage_card": data.get("triageCard") or state.get("triage_card"),
        "sources": merged,
    }


__all__ = ["COLLECTION", "NODE_NAME", "triage_node"]
