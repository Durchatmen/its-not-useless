"""预诊分诊链路：把两个 Agent 组装成 LangGraph 状态图。

流程是 START -> 预诊 -> （科室明确？）-> 分诊 -> END。
科室没定下来时直接结束：预诊节点已经通过 nextQuestion 追问了，此时拿模糊症状
去分诊库检索只会召回一堆无关科室，不如等患者补齐信息再走一次。

注意 nextQuestion 非空并不代表要跳过分诊 —— 接口文档的响应示例里，
追问和完整分诊卡片是同一次返回的。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.services.rag.agents.pre_diagnosis_agent import (
    NODE_NAME as PRE_DIAGNOSIS,
    pre_diagnosis_node,
)
from app.services.rag.agents.state import PreConsultState
from app.services.rag.agents.triage_agent import NODE_NAME as TRIAGE, triage_node


def _has_department(state: PreConsultState) -> bool:
    card = state.get("triage_card") or {}
    return bool(card.get("department"))


def build_graph():
    """建图并编译，返回可 invoke 的对象。"""
    builder = StateGraph(PreConsultState)
    builder.add_node(PRE_DIAGNOSIS, pre_diagnosis_node)
    builder.add_node(TRIAGE, triage_node)
    builder.add_edge(START, PRE_DIAGNOSIS)
    builder.add_conditional_edges(PRE_DIAGNOSIS, _has_department, {True: TRIAGE, False: END})
    builder.add_edge(TRIAGE, END)
    return builder.compile()


graph = build_graph()
"""模块级编译结果，供 /ai/multimodal 接口直接 invoke / astream。"""


__all__ = ["build_graph", "graph"]
