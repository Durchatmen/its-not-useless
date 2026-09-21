"""检查助手 Agent：把检查前的准备事项讲清楚（API-24 检查注意事项）。

对应功能设计 §4.2 的「检查助手 Agent」——触发场景是开具检查单后，
职责是推送检查目的、流程与准备事项。

产出**分条**的注意事项（而不是一整段）：`ExamPrecautionsData.precautions` 按行分条展示，
`voiceText` 也复用同一批句子逐句播报，两份文案因此天然一致；返回整段再让调用方
去拆行，拆错了语音播报就会连读成一坨。
`purpose` / `process` 不由模型产出 —— 检查知识库里本来就有原文，`exam_service`
直接取用，免得模型改写后与院内实际流程不符。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.llm import chat
from app.services.rag.agents.tools import build_document_messages
from app.services.rag.prompts import EXAM_PRECAUTIONS_SYSTEM, format_context

# 一条检查在检查知识库里就是一个 chunk，实际命中通常只有 1 条，多给几条是防着
# 索引切分不一致；再多就是拿别的检查的注意事项来凑数了。
MAX_CONTEXT_CHUNKS = 4

# 注意事项条数上限，与提示词里「3~6 条」一致，兜住模型不听话的情况
MAX_LINES = 6

# 准备要求写错会让患者白跑一趟，温度压到最低
TEMPERATURE = 0.2

# 行首的编号与列表符号（提示词已要求不写，模型偶尔还是会加）
_LINE_PREFIX_RE = re.compile(r"^\s*(?:[-–—•·*>]+|\d+\s*[.、)）]|[（(]\s*\d+\s*[)）])\s*")
# 行内残留的 Markdown 标记，语音播报念出来很难听
_MARKUP_RE = re.compile(r"[*`#|]+")


def _to_lines(text: str) -> list[str]:
    """模型输出 → 分条文案：去编号/标记、去小标题、去空行、去重、限条数。"""
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = _MARKUP_RE.sub(" ", _LINE_PREFIX_RE.sub("", raw))
        line = re.sub(r"\s+", " ", line)
        # 中文标点前的空格是 Markdown 清洗留下的，语音播报念出来会顿一下
        line = re.sub(r"\s+([：:；;，,。、])", r"\1", line).strip(" ;；,，。")
        # 「注意事项：」这类小标题后面跟的才是条目，它自己不是一条提醒
        if line.endswith(("：", ":")):
            continue
        # 一句话总得有内容，太短的（残留的序号、分隔符）直接丢
        if len(line) < 4 or line in lines:
            continue
        lines.append(line)
        if len(lines) >= MAX_LINES:
            break
    return lines


def precautions(*, exam_name: str, hits: Sequence[Mapping[str, Any]]) -> list[str]:
    """生成检查注意事项。

    hits 是检查知识库（kb_exam）的命中条目，条目里带 **检查目的** / **检查流程** /
    **注意事项** 三段；调用方只在命中非空时才调本函数 —— 一条资料都没有时模型只能
    自己编准备要求，而模板那边还有库内缓存（t_exam.precautions）可用。
    """
    messages = build_document_messages(
        system=EXAM_PRECAUTIONS_SYSTEM,
        context=format_context(list(hits)[:MAX_CONTEXT_CHUNKS]),
        document=f"检查名称：{exam_name}",
        header="本次检查",
    )
    return _to_lines(chat(messages, temperature=TEMPERATURE))


__all__ = ["precautions"]
