"""预诊分诊链路的共享状态（LangGraph `StateGraph` 的 State）。

一次 API-08 调用就是一次图执行：每个节点只返回「自己要更新的字段」，
没返回的键沿用旧值，所以这里用 `total=False` 声明所有键都可以缺省。

字段刻意只用内置类型（str / list / dict）：LangGraph 建图时要用 `get_type_hints`
解析这个 TypedDict，注解里一旦出现运行时导入不到的类型（比如放在 TYPE_CHECKING 下的
`RetrievedChunk`），建图会直接报错。检索结果因此以「格式化后的文本」入状态，
而不是原始对象。
"""

from __future__ import annotations

from typing import TypedDict


class PreConsultState(TypedDict, total=False):
    """预诊 + 分诊一次调用的全部中间数据。"""

    # ----- 输入 -----
    session_id: str
    """会话编号（t_ai_session.session_id）；首轮由服务端生成后回填。"""

    patient_id: str
    """本次预诊针对的就诊人（t_patient.patient_id）；缺省表示就诊人本人。"""

    question: str
    """本轮用户问题。语音转写、图片识别的结果都会先收敛成文本再进这里。"""

    history: list[dict]
    """历史对话，元素形如 {"role": "user"|"assistant", "content": "..."}。"""

    # ----- 检索结果 -----
    diagnosis_context: str
    """诊疗知识库召回并格式化后的上下文，预诊节点用。"""

    triage_context: str
    """科室及医生知识库召回并格式化后的上下文，分诊节点用。"""

    sources: list[str]
    """本次实际引用到的知识库名，对应响应里的 sources。"""

    # ----- 生成结果 -----
    reply: str
    """AI 回复正文；流式返回时它就是逐段推给前端的 delta。"""

    triage_card: dict | None
    """分诊卡片 {department, location, doctor, buttonAction}；信息不足时为 None。"""

    risk_warning: str
    """高危症状预警文本，无则为空串。"""

    next_question: str
    """下一轮追问建议，无则为空串。"""


__all__ = ["PreConsultState"]
