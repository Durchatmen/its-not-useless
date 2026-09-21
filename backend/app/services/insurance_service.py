"""医保业务逻辑（接口文档 API-32 医保智能咨询）。

医保目录分类 + 自付预估卡片 + 多轮咨询会话。

一条硬规矩贯穿全模块：**代码里不做医保政策数值计算**。起付线、报销比例、乙类
先行自付比例这些数字一律不硬编码，只有两个合法来源：

    kb_insurance 知识库片段   _extract_reimburse_ratio() 只在片段里显式写出比例时才取用
    t_prescription / t_bill   insurance_cover / self_pay 是种子与 HIS 落好的存量值

所以 estimateCard 经常是 None —— 拿不到知识库依据时就不编数字，只回「以当地医保局
最新规定为准」。这既是既定决策（报销数值完全交给知识库），也是医保咨询的合规底线。

AI 钩子（检索链或大模型不可用时降级而不是报错）：

    set_retriever() / set_llm()    注入实现，传 None 恢复默认
    _get_retriever() / _get_llm()  先看注入值，再懒加载 app.services.rag.retriever
                                   与 app.services.llm

    这两个模块的签名与本模块约定的钩子形态不一样（retrieve 收 collection 关键字参数
    并返回 RetrievedChunk，chat 收 messages 列表），由 _retriever_from_kb /
    _llm_from_chat 在各层对齐 —— 别再把裸函数直接当钩子交出去，调用时会因为参数
    对不上抛 TypeError，又被 _ask_llm 的兜底 except 吞掉，表现成「配了也用不上」。

    检索链缺 AI 依赖（requirements-ai.txt）、未配 LLM_API_KEY、网络不通，
    都会在这里或 _ask_llm / _retrieve 处兜住，主流程照常走「检索原文作答」
    或「能力受限提示」。
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AiMessage, AiSession, Medication, Prescription, PrescriptionItem

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

DISCLAIMER = "医保政策以当地医保局最新规定为准"

KB_COLLECTION = "kb_insurance"
"""医保知识库的 collection 名，见 rag/collections.py 的注册表。"""

SCENE = "INSURANCE"
"""t_ai_session.scene 的取值，见该模型 comment。"""

ROLE_USER = "user"
ROLE_BOT = "bot"
"""t_ai_message.role 的取值，见该模型 comment。"""

INPUT_TYPE_TEXT = "TEXT"

DEFAULT_TOP_K = 5
MAX_SOURCES = 5
"""引用来源最多列几条，避免 sources 列（varchar(512)）写爆。"""

SOURCES_MAX_LENGTH = 512
"""t_ai_message.sources 的列宽，超长按此截断。"""

INSURANCE_TYPE_LABELS: dict[str, str] = {
    "A": "甲类",
    "B": "乙类",
    "SELF": "自费",
}

INSURANCE_TYPE_NOTES: dict[str, str] = {
    "A": "甲类：全额纳入医保报销范围",
    "B": "乙类：部分医保报销，需先自付一定比例",
    "SELF": "自费：无医保报销",
}
"""口径取自 docs/药品知识库 的「医保属性说明」，不额外发明政策细节。"""

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "起付线": ("起付线", "起付标准", "门槛", "最低支付"),
    "报销比例": ("报销比例", "报销多少", "能报", "报多少", "报销率", "报销多少"),
    "封顶线": ("封顶", "最高支付", "限额", "上限"),
    "异地就医": ("异地", "外地", "跨省", "转诊", "备案"),
    "目录": ("目录", "甲类", "乙类", "自费", "纳入", "医保药"),
    "个人账户": ("个人账户", "医保卡", "余额", "共济"),
}
"""用于组织追问建议，不参与任何数值判断。"""

# 只认「显式写出来的比例」，不做任何推断
_DRUG_FORM_RE = re.compile(r"(分散片|缓释片|肠溶片|咀嚼片|胶囊|片|颗粒|口服液|注射液|滴剂|喷雾剂|软膏|栓|丸|散|糖浆)$")
"""药名末尾的剂型，比对时剥掉。长剂型在前，避免「分散片」被「片」先吃掉一个「片」字。"""

_REIMBURSE_RATIO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"报销比例[^0-9%]{0,8}(\d{1,3}(?:\.\d+)?)\s*%"),
    re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%[^0-9%]{0,8}(?:予以)?报销"),
    re.compile(r"按[^0-9%]{0,6}(\d{1,3}(?:\.\d+)?)\s*%[^0-9%]{0,6}报销"),
)

_ANSWER_SYSTEM_PROMPT = (
    "你是医院智能就医系统的医保咨询助手。只能依据用户消息中提供的【知识库片段】作答。"
    "不得自行推断或编造报销比例、起付线、封顶线等任何政策数字；片段中没有的内容，"
    "直接回答「知识库暂未收录，请以当地医保局最新规定为准」。回答用中文，分点、简洁。"
)

_ANSWER_USER_TEMPLATE = "【知识库片段】\n{context}\n\n【患者问题】\n{question}"

_KB_NOT_READY_ANSWER = (
    "医保知识库检索链路尚未就绪，暂时无法给出有依据的回答。"
    "请先完成医保知识库入库（docs/医保知识库/），并配置大模型服务后重试。"
)

_LLM_NOT_READY_ANSWER = (
    "已从医保知识库检索到相关内容，但大模型服务尚未配置，无法组织成回答。"
    "以下为知识库原文摘录，供参考。"
)

# --------------------------------------------------------------------------- #
# AI 钩子
# --------------------------------------------------------------------------- #

RetrieverFn = Callable[[str, int], Sequence[Mapping[str, Any]]]
"""知识库检索： (query, top_k) -> 命中片段，每项至少含 text / source_file / category。"""

LlmFn = Callable[[str, str], str]
"""大模型调用： (system_prompt, user_prompt) -> 回复文本。"""

_retriever: RetrieverFn | None = None
_llm: LlmFn | None = None


def set_retriever(fn: RetrieverFn | None) -> None:
    """注入医保知识库检索实现；传 None 则恢复成「懒加载 retriever 模块」。"""
    global _retriever
    _retriever = fn


def set_llm(fn: LlmFn | None) -> None:
    """注入大模型实现；传 None 则恢复成「懒加载 llm 模块」。"""
    global _llm
    _llm = fn


def _retriever_from_kb(retrieve: Callable[..., Sequence[Any]]) -> RetrieverFn:
    """把 `retriever.retrieve` 适配成本模块的 (query, top_k) 形态。

    retrieve 的签名是 `retrieve(query, collection, *, top_k)`，返回 RetrievedChunk
    数据类；而本模块约定 RetrieverFn 是 `(query, top_k)`，且 `_retrieve` 只认
    KbChunk 与 Mapping（不认 RetrievedChunk）—— 差的一层在这里对齐，
    免得调用方和注入接口被迫跟着改。
    """

    def search(query: str, top_k: int) -> list[dict[str, Any]]:
        chunks = retrieve(query, KB_COLLECTION, top_k=top_k)
        return [
            {
                "text": chunk.text,
                "source_file": chunk.source_file,
                "category": chunk.category,
                "score": chunk.score,
            }
            for chunk in chunks
        ]

    return search


def _llm_from_chat(chat: Callable[..., str]) -> LlmFn:
    """把 `llm.chat` 适配成本模块的 (system, user) 形态。

    本模块的提示词是「系统段 + 用户段」两段；llm.chat 收的是 messages 列表。
    曾经直接把 chat 当 LlmFn 交出去，调用时 `provider(system, user)` 抛 TypeError，
    又被 _ask_llm 的兜底 except 吞掉 —— 表现是「大模型配好了但一直不出声」。
    """

    def ask(system: str, user: str) -> str:
        return chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )

    return ask


def _get_retriever() -> RetrieverFn | None:
    """取检索实现：先看注入值，再看 app.services.rag.retriever 的默认实现。

    宽捕 Exception 而不是 ImportError：检索链还拖着可选依赖（milvus / torch 等，
    见 requirements-ai.txt），缺依赖时抛的未必是 ImportError，但结论一样 ——
    没有检索就明说能力受限，不能让医保咨询整个接口挂掉。
    """
    global _retriever
    if _retriever is not None:
        return _retriever
    try:
        from app.services.rag.retriever import retrieve
    except Exception:  # noqa: BLE001 - 见 docstring
        logger.debug("知识库检索链不可用，医保咨询降级为无引用作答", exc_info=True)
        return None
    _retriever = _retriever_from_kb(retrieve)
    return _retriever


def _get_llm() -> LlmFn | None:
    """取大模型实现：先看注入值，再看 app.services.llm。

    未配 LLM_API_KEY 时 `chat` 会抛 LLMError，由 _ask_llm 兜住并回落成「摘录知识库原文」，
    所以这里不必自己判断 Key 是否填了。
    """
    global _llm
    if _llm is not None:
        return _llm
    try:
        from app.services.llm import chat
    except Exception:  # noqa: BLE001 - 大模型客户端不可用时回落成摘录原文
        logger.debug("大模型客户端不可用，医保咨询改用检索原文作答", exc_info=True)
        return None
    _llm = _llm_from_chat(chat)
    return _llm


def _ask_llm(system: str, user: str) -> str | None:
    """调大模型；未配置或调用失败都返回 None，由调用方决定怎么降级。"""
    provider = _get_llm()
    if provider is None:
        return None
    try:
        reply = provider(system, user)
    except Exception as exc:  # noqa: BLE001 - 大模型失败不该让整条咨询链路不可用
        logger.warning("医保咨询大模型调用失败，改用检索原文作答: %s", exc)
        return None
    text = (reply or "").strip()
    return text or None


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #


@dataclass
class CatalogEntry:
    """药品在医保目录里的归类。"""

    drug_id: str
    drug_name: str
    insurance_type: str
    """原始取值：A / B / SELF。"""

    category_label: str
    """中文口径：甲类 / 乙类 / 自费。"""

    note: str
    """该类别的一句话说明。"""

    specification: str | None = None
    price: Decimal | None = None


@dataclass
class CatalogSummary:
    """一张处方的医保构成。"""

    prescription_id: str
    total_items: int
    counts: dict[str, int] = field(default_factory=dict)
    """各医保类别的条目数，键是中文口径（甲类/乙类/自费）。"""

    subtotals: dict[str, Decimal] = field(default_factory=dict)
    """各医保类别的存量小计金额（元），直接取 t_prescription_item.subtotal。

    这里只是把库里已有的钱加总，不乘任何报销比例 —— 比例属于政策，归知识库。
    """

    entries: list[CatalogEntry] = field(default_factory=list)


@dataclass
class KbChunk:
    """一条知识库命中片段。"""

    text: str
    source_file: str = ""
    category: str = ""
    score: float = 0.0


@dataclass
class EstimateCard:
    """自付预估卡片。

    只在「知识库片段里有显式比例」且「库里取得到金额」两件事同时成立时才存在。
    """

    item_name: str
    reimburse_ratio: Decimal
    reimburse_ratio_label: str
    """如「70%」，直接给前端展示。"""

    estimated_self_pay: Decimal
    basis: str
    """依据说明，交代比例与金额各从哪来。"""


@dataclass
class ConsultResult:
    """API-32 的响应体（不含信封，信封由路由层拼）。"""

    session_id: str
    answer: str
    estimate_card: EstimateCard | None
    sources: list[str]
    disclaimer: str = DISCLAIMER
    next_question: str | None = None
    kb_ready: bool = False
    """知识库检索是否真的召回了内容。False 时 answer 是能力受限提示，不是答案。"""


@dataclass
class ConsultTurn:
    """一条历史会话记录。"""

    message_id: str
    role: str
    content: str | None
    reply: str | None
    sources: list[str] = field(default_factory=list)
    disclaimer: str | None = None
    next_question: str | None = None
    """下一轮追问建议，只有 bot 侧有值；写库与回读走同一列。"""
    created_at: datetime | None = None


# --------------------------------------------------------------------------- #
# 医保目录
# --------------------------------------------------------------------------- #


def classify_drug(medication: Medication) -> CatalogEntry:
    """把 t_medication.insurance_type 翻成医保目录口径。

    这是甲乙类语义的唯一出口，用药模块也复用它，避免两处各写一份映射。

    A/B/SELF 之外的历史脏值一律按自费处理 —— 宁可让患者自己去核对，也不要误报能报销。
    """
    raw = (medication.insurance_type or "").strip().upper()
    if raw not in INSURANCE_TYPE_LABELS:
        if raw:
            logger.warning("药品 %s 的医保属性无法识别，按自费处理: %r", medication.drug_id, raw)
        raw = "SELF"

    return CatalogEntry(
        drug_id=medication.drug_id,
        drug_name=medication.drug_name,
        insurance_type=raw,
        category_label=INSURANCE_TYPE_LABELS[raw],
        note=INSURANCE_TYPE_NOTES[raw],
        specification=medication.specification,
        price=medication.price,
    )


def lookup_catalog(
    session: Session,
    *,
    drug_ids: Sequence[str] | None = None,
    prescription_id: str | None = None,
    keyword: str | None = None,
    insurance_type: str | None = None,
    limit: int = 100,
) -> list[CatalogEntry]:
    """按处方 / 药品编号 / 药名关键字 / 甲乙类过滤查医保目录。

    prescription_id 与 drug_ids 同时给出时以 prescription_id 为准（处方是更窄的范围）。
    """
    if prescription_id:
        stmt = (
            select(Medication)
            .join(PrescriptionItem, PrescriptionItem.drug_id == Medication.drug_id)
            .where(PrescriptionItem.prescription_id == prescription_id)
        )
    else:
        stmt = select(Medication)
        if drug_ids:
            stmt = stmt.where(Medication.drug_id.in_(list(drug_ids)))

    if keyword:
        stmt = stmt.where(Medication.drug_name.like(f"%{keyword}%"))

    wanted = (insurance_type or "").strip().upper()
    if wanted:
        stmt = stmt.where(Medication.insurance_type == wanted)

    stmt = stmt.order_by(Medication.drug_id).limit(limit)
    medications = session.execute(stmt).scalars().all()
    return [classify_drug(m) for m in medications]


def summarize_prescription_catalog(session: Session, *, prescription_id: str) -> CatalogSummary:
    """统计一张处方里的甲/乙/自费构成，供前端展示医保标识。

    纯数据聚合：条目数 + 存量小计金额，不做任何报销比例运算。
    """
    rows = session.execute(
        select(PrescriptionItem, Medication)
        .join(Medication, Medication.drug_id == PrescriptionItem.drug_id)
        .where(PrescriptionItem.prescription_id == prescription_id)
        .order_by(PrescriptionItem.item_id)
    ).all()

    summary = CatalogSummary(prescription_id=prescription_id, total_items=len(rows))
    for item, medication in rows:
        entry = classify_drug(medication)
        summary.entries.append(entry)
        label = entry.category_label
        summary.counts[label] = summary.counts.get(label, 0) + 1
        summary.subtotals[label] = summary.subtotals.get(label, Decimal("0.00")) + (
            item.subtotal or Decimal("0.00")
        )

    if not rows:
        logger.debug("处方 %s 无明细，医保构成统计为空", prescription_id)
    return summary


# --------------------------------------------------------------------------- #
# 咨询
# --------------------------------------------------------------------------- #


def consult(
    session: Session,
    *,
    question: str,
    user_id: str,
    patient_id: str | None = None,
    session_id: str | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> ConsultResult:
    """API-32 医保智能咨询。

    流程：会话 → 检索 kb_insurance → 意图识别 → 组织回答 → 自付预估卡片 → 落库。
    任何一环的 AI 依赖缺失都只降级、不抛异常，唯一会抛的是入参问题（空问题、会话不存在）。
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("医保咨询问题不能为空")

    ai_session = _get_or_create_session(
        session, user_id=user_id, patient_id=patient_id, session_id=session_id
    )

    chunks = _retrieve(question, top_k=top_k)
    kb_ready = bool(chunks)
    topics = _detect_topics(question)

    answer = _compose_answer(question, chunks=chunks)
    estimate_card = _build_estimate_card(session, question=question, chunks=chunks, patient_id=patient_id)
    sources = _collect_sources(chunks)
    next_question = _suggest_next_question(topics)

    _persist_turn(
        session,
        ai_session=ai_session,
        question=question,
        answer=answer,
        estimate_card=estimate_card,
        sources=sources,
        next_question=next_question,
    )

    logger.info(
        "医保咨询完成: session=%s 召回=%d 有卡片=%s",
        ai_session.session_id,
        len(chunks),
        estimate_card is not None,
    )
    return ConsultResult(
        session_id=ai_session.session_id,
        answer=answer,
        estimate_card=estimate_card,
        sources=sources,
        next_question=next_question,
        kb_ready=kb_ready,
    )


def list_consult_history(
    session: Session,
    *,
    session_id: str,
    limit: int = 20,
) -> list[ConsultTurn]:
    """回读一轮会话里的消息，按时间正序。

    created_at 只到秒，同轮两条必然相同，真正决定同秒内先后的是 message_id ——
    见 _new_message_id：主键里编了生成时刻的微秒时间戳。顺序依赖主键的单调性，
    别把 message_id 换成纯随机值。
    """
    messages = (
        session.execute(
            select(AiMessage)
            .where(AiMessage.session_id == session_id)
            .order_by(AiMessage.created_at, AiMessage.message_id)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        ConsultTurn(
            message_id=m.message_id,
            role=m.role,
            content=m.content,
            reply=m.reply,
            sources=_parse_sources(m.sources),
            disclaimer=m.disclaimer,
            next_question=m.next_question,
            created_at=m.created_at,
        )
        for m in messages
    ]


# --------------------------------------------------------------------------- #
# 咨询内部步骤
# --------------------------------------------------------------------------- #


def _get_or_create_session(
    session: Session,
    *,
    user_id: str,
    patient_id: str | None,
    session_id: str | None,
) -> AiSession:
    """复用已有医保会话，或新建一个。"""
    if session_id:
        ai_session = session.get(AiSession, session_id)
        if ai_session is None:
            raise LookupError(f"会话不存在: {session_id}")
        if ai_session.scene != SCENE:
            raise ValueError(f"会话 {session_id} 的场景是 {ai_session.scene}，不是医保咨询")
        return ai_session

    ai_session = AiSession(
        session_id=_new_id("AIS"),
        user_id=user_id,
        patient_id=patient_id,
        scene=SCENE,
        message_count=0,
        status=1,
    )
    session.add(ai_session)
    # 先落父表，确保 t_ai_message 的外键有得指
    session.flush()
    return ai_session


def _retrieve(question: str, *, top_k: int = DEFAULT_TOP_K) -> list[KbChunk]:
    """从医保知识库召回片段；检索链未就绪、collection 为空、调用失败都返回空列表。"""
    provider = _get_retriever()
    if provider is None:
        return []

    try:
        raw = provider(question, top_k)
    except Exception as exc:  # noqa: BLE001 - 检索失败降级为无引用作答
        logger.warning("医保知识库检索失败，降级为无引用作答: %s", exc)
        return []

    chunks: list[KbChunk] = []
    for item in raw or []:
        if isinstance(item, KbChunk):
            chunks.append(item)
        elif isinstance(item, Mapping):
            score = item.get("score")
            chunks.append(
                KbChunk(
                    text=str(item.get("text") or ""),
                    source_file=str(item.get("source_file") or ""),
                    category=str(item.get("category") or ""),
                    score=float(score) if isinstance(score, (int, float)) else 0.0,
                )
            )

    if not chunks:
        logger.debug("医保知识库未召回内容: %s", question)
    return chunks


def _detect_topics(question: str) -> list[str]:
    """识别问题涉及的医保话题，只用于组织追问建议。"""
    return [topic for topic, words in TOPIC_KEYWORDS.items() if any(w in question for w in words)]


def _compose_answer(question: str, *, chunks: Sequence[KbChunk]) -> str:
    """组织回答：有检索 + 有大模型 → 生成；只有检索 → 摘录原文；都没有 → 明说能力受限。

    没有检索结果时**绝不生成** —— 医保数字编错了比答不上来更糟。
    """
    if not chunks:
        return _KB_NOT_READY_ANSWER

    context = "\n\n".join(_trim(chunk.text, 800) for chunk in chunks if chunk.text.strip())
    reply = _ask_llm(_ANSWER_SYSTEM_PROMPT, _ANSWER_USER_TEMPLATE.format(context=context, question=question))
    if reply:
        return reply

    return f"{_LLM_NOT_READY_ANSWER}\n\n" + _answer_from_chunks(chunks)


def _answer_from_chunks(chunks: Sequence[KbChunk]) -> str:
    """无大模型时的兜底：直接摘录检索到的原文，不做任何改写。"""
    lines: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        text = _trim(chunk.text.replace("\n", " ").strip(), 300)
        if text:
            lines.append(f"{idx}. {text}")
    return "\n".join(lines)


def _extract_reimburse_ratio(chunks: Sequence[KbChunk]) -> Decimal | None:
    """从知识库片段里抠出**显式写出**的报销比例。

    抠不到就返回 None —— 绝不按类别猜一个默认比例。这正是「报销数值完全交给知识库」
    这条决策落地的地方。
    """
    for chunk in chunks:
        if not chunk.text:
            continue
        for pattern in _REIMBURSE_RATIO_PATTERNS:
            match = pattern.search(chunk.text)
            if not match:
                continue
            ratio = Decimal(match.group(1))
            if Decimal("0") < ratio <= Decimal("100"):
                logger.debug("知识库片段中出现显式报销比例: %s%%", ratio)
                return ratio
    return None


def _build_estimate_card(
    session: Session,
    *,
    question: str,
    chunks: Sequence[KbChunk],
    patient_id: str | None,
) -> EstimateCard | None:
    """拼自付预估卡片；比例或金额缺一样就不给卡片。"""
    ratio = _extract_reimburse_ratio(chunks)
    if ratio is None:
        logger.debug("知识库片段中无显式报销比例，跳过自付预估卡片")
        return None

    target = _resolve_estimate_target(session, patient_id=patient_id, question=question)
    if target is None:
        logger.debug("就诊人 %s 无处方可挂靠，跳过自付预估卡片", patient_id)
        return None

    item_name, amount = target
    reimburse = (amount * ratio / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return EstimateCard(
        item_name=item_name,
        reimburse_ratio=ratio,
        reimburse_ratio_label=f"{_format_ratio(ratio)}%",
        estimated_self_pay=(amount - reimburse).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        basis=(
            "报销比例取自医保知识库检索片段，金额取自处方存量数据；"
            "两者相乘仅为粗略参考，实际以医院结算为准"
        ),
    )


def _format_ratio(ratio: Decimal) -> str:
    """比例 -> 「70」。

    不能直接 str(Decimal('70').normalize())：normalize() 会把整数比例变成科学计数法的
    Decimal('7E+1')，卡片上就成了「7E+1%」。'f' 格式固定用普通小数写法，绕开这一层。
    """
    return format(ratio.normalize(), "f")


def _resolve_estimate_target(
    session: Session,
    *,
    patient_id: str | None,
    question: str,
) -> tuple[str, Decimal] | None:
    """定位预估挂靠的标的：问题里点到的药优先，否则退到本次处方合计。

    只读库里已有的金额，不做任何比例运算。
    """
    if not patient_id:
        return None

    prescription = (
        session.execute(
            select(Prescription)
            .where(Prescription.patient_id == patient_id)
            .order_by(Prescription.created_at.desc(), Prescription.prescription_id.desc())
            .limit(1)
        )
        .scalar_one_or_none()
    )
    if prescription is None:
        return None

    rows = session.execute(
        select(PrescriptionItem, Medication)
        .join(Medication, Medication.drug_id == PrescriptionItem.drug_id)
        .where(PrescriptionItem.prescription_id == prescription.prescription_id)
    ).all()
    for item, medication in rows:
        if _mentioned_in(medication.drug_name, question):
            return medication.drug_name, item.subtotal or Decimal("0.00")

    return "本次处方合计", prescription.total_amount or Decimal("0.00")


def _mentioned_in(drug_name: str | None, question: str) -> bool:
    """药名主干是否被问题提到。

    患者不会照着处方的全名念 —— 问的是「阿莫西林能报多少」，而处方上写的是
    「阿莫西林胶囊」。所以整名匹配不中时，再剥掉剂型后缀拿主干比一次，
    否则「问题里点到的药优先」这条分支永远走不到。
    """
    name = (drug_name or "").strip()
    if not name:
        return False
    if name in question:
        return True
    stem = _DRUG_FORM_RE.sub("", name)
    return len(stem) >= 2 and stem in question


def _collect_sources(chunks: Sequence[KbChunk]) -> list[str]:
    """把命中片段收敛成去重后的来源名，格式化成《文件名》。"""
    sources: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        label = chunk.source_file or chunk.category
        if not label:
            continue
        name = Path(label).stem
        if not name:
            continue
        text = f"《{name}》"
        if text in seen:
            continue
        seen.add(text)
        sources.append(text)
        if len(sources) >= MAX_SOURCES:
            break
    return sources


def _suggest_next_question(topics: Sequence[str]) -> str | None:
    """挑几个本次没聊到的话题作为追问建议。"""
    candidates = [topic for topic in TOPIC_KEYWORDS if topic not in topics]
    if not candidates:
        return None
    return f"还可以问我：{'、'.join(candidates[:3])}"


def _persist_turn(
    session: Session,
    *,
    ai_session: AiSession,
    question: str,
    answer: str,
    estimate_card: EstimateCard | None,
    sources: Sequence[str],
    next_question: str | None,
) -> None:
    """把这一轮问答写进 t_ai_message，并推进会话轮数。"""
    # 一轮取一次时间戳，提问与回复共用，保证主键大小关系就是「提问在前」。
    base_micros = time.time_ns() // 1_000
    session.add(
        AiMessage(
            message_id=_new_message_id(base_micros, 0),
            session_id=ai_session.session_id,
            role=ROLE_USER,
            input_type=INPUT_TYPE_TEXT,
            content=question,
        )
    )
    session.add(
        AiMessage(
            message_id=_new_message_id(base_micros, 1),
            session_id=ai_session.session_id,
            role=ROLE_BOT,
            # t_ai_message 没有通用的「卡片」列，只有为分诊设计的 triage_card。
            # 医保的 estimateCard 复用该列存放，读取时按 JSON 解析。
            triage_card=_dump_card(estimate_card),
            reply=answer,
            next_question=next_question,
            sources=_dump_sources(sources),
            disclaimer=DISCLAIMER,
        )
    )
    ai_session.message_count = (ai_session.message_count or 0) + 1
    session.commit()


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #


def _new_id(prefix: str) -> str:
    """生成 32 位以内的业务主键，避开种子的序号风格（AIS0001 / MSG0001）。"""
    return f"{prefix}{uuid.uuid4().hex[:20].upper()}"


def _new_message_id(base_micros: int, ordinal: int) -> str:
    """生成一轮问答内按先后递增的消息主键（仅 t_ai_message 用）。

    t_ai_message.created_at 是 datetime（秒精度，实测线上表就是 datetime 无小数秒），
    同一轮的用户提问与助手回复必然落在同一秒里，于是
    ORDER BY created_at, message_id 会退化成按随机主键比大小 —— 助手的回复可能被排到
    提问前面，前端渲染多轮对话就错位了。

    把生成时刻的微秒时间戳编进主键，同秒内的先后便有据可依；调用方一轮只取一次
    时间戳，靠 ordinal 区分提问/回复，即便两次取到同一微秒也仍是提问在前。
    随机尾巴从原来的 20 位缩到 6 位：主键要去排序，长度预算得留给时间戳。
    """
    return f"MSG{base_micros + ordinal:016d}{uuid.uuid4().hex[:6].upper()}"


def _trim(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _dump_sources(sources: Sequence[str]) -> str | None:
    if not sources:
        return None
    text = json.dumps(list(sources), ensure_ascii=False)
    if len(text) > SOURCES_MAX_LENGTH:
        logger.warning("引用来源超出 sources 列宽，已截断: %d 字", len(text))
        text = text[: SOURCES_MAX_LENGTH - 1] + "]"
    return text


def _parse_sources(raw: str | None) -> list[str]:
    """把 sources 列的 JSON 解析回来；脏数据不抛异常，返回空列表。"""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("sources 列不是合法 JSON，按无来源处理: %s", _trim(raw, 40))
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _dump_card(card: EstimateCard | None) -> str | None:
    if card is None:
        return None
    return json.dumps(
        {
            "itemName": card.item_name,
            "reimburseRatio": card.reimburse_ratio_label,
            "estimatedSelfPay": str(card.estimated_self_pay),
            "basis": card.basis,
        },
        ensure_ascii=False,
    )


__all__ = [
    "DISCLAIMER",
    "INSURANCE_TYPE_LABELS",
    "KB_COLLECTION",
    "SCENE",
    "CatalogEntry",
    "CatalogSummary",
    "ConsultResult",
    "ConsultTurn",
    "EstimateCard",
    "KbChunk",
    "classify_drug",
    "consult",
    "list_consult_history",
    "lookup_catalog",
    "set_llm",
    "set_retriever",
    "summarize_prescription_catalog",
]
