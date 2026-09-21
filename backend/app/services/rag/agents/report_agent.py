"""报告 Agent：把检查/检验报告讲成患者能看懂的一段话。

对应功能设计 §4.2 的「报告 Agent」——触发场景是查看检查报告（API-29），
职责是异常项解读与整体分析。

只产出解读正文。`abnormalItems` / `riskLevel` / `advice` / `sources` 仍由
`exam_service.analyze_report` 按报告知识库与规则表产出：这几项是机器可读的事实，
不能让模型改写，响应结构对前端也保持原样。调用方负责兜底 ——
`exam_service._llm_analyze` 捕到异常就返回 None，改用规则模板。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.llm import chat
from app.services.rag.agents.tools import build_document_messages
from app.services.rag.prompts import REPORT_ANALYSIS_SYSTEM, format_context

# 注入提示词的知识库条数上限。异常项是逐条检索的，一次可能有十几条命中，
# 全塞进去只会把最相关的那几条稀释掉，token 也白花。
MAX_CONTEXT_CHUNKS = 8

# 解读要稳不要发挥；模型这里只是把已核对过的逐项含义串成通读的段落
TEMPERATURE = 0.3

# 与 schemas/exam.py 的 AbnormalFlag 对应，仅用于拼给模型看的文字
_FLAG_WORD = {"HIGH": "偏高", "LOW": "偏低"}


def _format_items(items: Sequence[Mapping[str, Any]]) -> str:
    """把异常项拼成「序号. 指标 值（方向）：通俗含义」的清单。

    meaning 来自报告知识库（未收录的指标则是客观复述），模型据此组织语言，
    不必自己判断数值高低，也就不会把「偏高」说反。
    """
    lines: list[str] = []
    for index, item in enumerate(items, 1):
        name = str(item.get("itemName") or "").strip()
        value = str(item.get("value") or "").strip()
        word = _FLAG_WORD.get(str(item.get("abnormalFlag") or ""), "")
        head = f"{name}{f' {value}' if value else ''}{f'（{word}）' if word else ''}"
        meaning = str(item.get("meaning") or "").strip()
        lines.append(f"{index}. {head}：{meaning}" if meaning else f"{index}. {head}")
    return "\n".join(lines)


def analyze(
    *,
    exam_name: str,
    report_content: str,
    items: Sequence[Mapping[str, Any]],
    hits: Sequence[Mapping[str, Any]],
) -> str:
    """生成报告解读正文。

    items 是本次的**异常项**（每项含 itemName / value / abnormalFlag / meaning），
    hits 是报告知识库的命中条目。两者都收 dict 而不是 schema 对象，本模块因此
    不依赖业务 schema —— `exam_service` 直连 milvus，它的命中本来就是 dict。
    """
    document = [f"检查名称：{exam_name}"]
    document.append(f"报告结论：{report_content.strip() or '（报告未给出结论文本）'}")
    if items:
        document.append(f"异常项（共 {len(items)} 项）：\n{_format_items(items)}")
    else:
        document.append("异常项：无，各项指标均在参考区间内。")

    messages = build_document_messages(
        system=REPORT_ANALYSIS_SYSTEM,
        context=format_context(list(hits)[:MAX_CONTEXT_CHUNKS]),
        document="\n".join(document),
        header="检查报告",
    )
    return chat(messages, temperature=TEMPERATURE).strip()


__all__ = ["analyze"]
