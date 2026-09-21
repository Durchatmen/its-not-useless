"""病历解释 Agent：把病历写成人话（API-23 病历 AI 解读）。

对应功能设计 §4.2 的「病历解释 Agent」——触发场景是查看病历时，职责是把专业术语与
诊断换成患者能听懂的说法，让患者看懂这次是什么问题、医生嘱咐了什么。

被 `medical_record_service._load_default_agent` 惰性探测，约定见该模块顶部的
Agent 契约注释：接收 record / text / session_id 三个关键字参数，返回
(通俗化解读文本, 引用来源列表)。术语对照有意不返回 —— 本地 TERM_DICT /
DIAGNOSIS_PLAIN 是人工校对的词表，比模型现编的对照可靠；`_run_agent` 在只收到
二元组时正是沿用词典的识别结果。

只做复述不做诊断：模型拿不到患者身份信息（姓名 / 证件号 / 手机号在上游就不传），
送出去的只有病历正文本身。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from app.services.llm import chat
from app.services.rag.agents.tools import build_document_messages
from app.services.rag.prompts import RECORD_INTERPRET_SYSTEM

if TYPE_CHECKING:
    from app.models.medical_record import MedicalRecord

logger = logging.getLogger(__name__)

COLLECTION = "kb_diagnosis"
"""诊疗知识库。与本地术语词典、medical_record_service.RULE_BASED_SOURCES 同源。"""

# 通俗化改写本就允许一点措辞上的灵活；涉及医学判断的部分由提示词约束
TEMPERATURE = 0.5

# 检索不到资料时给模型的替代上下文。不能沿用 format_context 的空结果话术
# （那句是「无法判断」），病历解释此时仍要把病历原话讲成人话，只是不许再补医学解释。
_NO_KB_NOTICE = "（本次没有检索到资料：只把病历原话讲成白话，不要补充资料以外的医学解释。）"


def _build_query(diagnosis: str, chief_complaint: str) -> str:
    """检索词以诊断为主、主诉为辅：病历里最需要解释的就是诊断。"""
    return " ".join(part for part in (diagnosis, chief_complaint) if part).strip()


def _search(query: str) -> tuple[str, list[str]]:
    """检索诊疗知识库；AI 依赖没装或检索链没起来都只当作「没有资料」。"""
    if not query:
        return _NO_KB_NOTICE, []
    try:
        from app.services.rag.agents.tools import search_knowledge

        context, sources = search_knowledge(f"{query} 是什么病 注意事项", COLLECTION)
    except Exception as exc:  # noqa: BLE001 - 检索是增强项，失败也要能出解读
        logger.warning("诊疗知识库检索失败，本次解读不做知识库引用: %s", exc)
        return _NO_KB_NOTICE, []
    return (context or _NO_KB_NOTICE), sources


def _interpret_sync(document: str, query: str) -> tuple[str, list[str]]:
    """阻塞部分：检索 + 调大模型。放进线程执行，理由见 interpret。"""
    context, sources = _search(query)
    messages = build_document_messages(
        system=RECORD_INTERPRET_SYSTEM,
        context=context,
        document=document,
        header="病历原文",
    )
    return chat(messages, temperature=TEMPERATURE).strip(), sources


async def interpret(
    *,
    record: Optional["MedicalRecord"],
    text: Optional[str],
    session_id: Optional[str] = None,
) -> tuple[str, list[str]]:
    """Agent 入口：返回 (解读文本, 引用来源)。

    本函数是 async（`api/v1/medical_records.py` 的端点是 `async def`），但它要做的事
    全是同步阻塞的：BGE 编码吃满 CPU、httpx 等网络。直接在事件循环里跑会把整个服务
    卡住，所以整段挪进线程。ORM 对象不能跨线程碰（Session 非线程安全），
    字段在这里先取成纯文本再传进去。

    正文为空或模型返回空文本时返回空字符串，由调用方回落到术语词典 ——
    「宁可退回词典，也不要回一段空解读」。
    """
    document = (text or "").strip()
    if not document:
        return "", []
    if session_id:
        logger.debug("病历解释 Agent 会话 %s", session_id)

    diagnosis = getattr(record, "diagnosis", None) or ""
    chief_complaint = getattr(record, "chief_complaint", None) or ""
    query = _build_query(diagnosis, chief_complaint)

    return await asyncio.to_thread(_interpret_sync, document, query)


__all__ = ["COLLECTION", "interpret"]
