"""预诊 Agent：分析症状，生成初步病情描述与就诊科室建议。

对应功能设计 §4.2 的「预诊 Agent」——触发场景是用户描述症状时，
职责是分析症状、生成初步病情描述、推荐就诊科室。

正文有两条出口：一边逐段写进 LangGraph 的 custom stream（流式接口据此推 delta 事件），
一边拼完整存进 state.reply（非流式接口与落库都用它）。两条出口共用同一个切分器，
拼出来的字完全一致。
"""

from __future__ import annotations

from langgraph.config import get_stream_writer

from app.services.llm import chat_stream
from app.services.rag.agents.state import PreConsultState
from app.services.rag.agents.tools import build_messages, search_knowledge
from app.services.rag.prompts import PRE_DIAGNOSIS_SYSTEM, ResultStreamSplitter

NODE_NAME = "pre_diagnosis"
"""图里的节点名，graph.py 组装时引用，避免两处字符串写歪。"""


def pre_diagnosis_node(state: PreConsultState) -> dict:
    """LangGraph 节点：检索诊疗知识库 -> 流式调用大模型 -> 解析结构化字段。

    只返回自己要更新的键，其余字段由 LangGraph 沿用旧值。
    """
    question = state.get("question") or ""

    context, sources = search_knowledge(question, "kb_diagnosis")
    messages = build_messages(
        system=PRE_DIAGNOSIS_SYSTEM,
        question=question,
        context=context,
        # 历史里的角色须已是 user / assistant；库里存的 "bot" 由上层读记录时转换
        history=state.get("history") or [],
    )

    # 非流式调用下 writer 是空操作，这段逻辑照样跑得通，所以流式与非流式共用一份实现
    writer = get_stream_writer()
    splitter = ResultStreamSplitter()
    parts: list[str] = []

    for chunk in chat_stream(messages):
        text = splitter.feed(chunk)
        if text:
            parts.append(text)
            writer(text)

    tail, data = splitter.finish()
    if tail:
        parts.append(tail)
        writer(tail)

    return {
        "reply": "".join(parts),
        "diagnosis_context": context,
        # 用检索到的库名，而不是模型自述的 sources —— 见 tools.search_knowledge 的说明
        "sources": sources,
        "triage_card": data.get("triageCard"),
        "risk_warning": data.get("riskWarning") or "",
        "next_question": data.get("nextQuestion") or "",
    }


__all__ = ["NODE_NAME", "pre_diagnosis_node"]
