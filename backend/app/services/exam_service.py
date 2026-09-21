"""检查模块业务逻辑（接口文档 3.8：API-24 ~ API-29，另有检查列表）。

分层约定：本模块只依赖 SQLAlchemy 会话，不感知 HTTP；错误统一以 `ExamError`
抛出，由 `api/v1/exams.py` 转成接口文档 2.4 的统一信封。

AI 部分的两点取舍：
1. 检查注意事项、报告解读都先走知识库检索（kb_exam / kb_report）再套模板拼装，
   检索失败就退回数据库里的缓存字段（t_exam.precautions、t_exam_report.ai_analysis），
   不把「知识库抖一下」放大成接口 5003 —— 缓存字段本身就是设计文档里给这两件事留的落点。
2. 大模型调用收敛在 `_llm_*` 两个函数里（分别对接报告 Agent 与检查助手 Agent），
   它们只产出「一段解读」/「几条注意事项」，abnormalItems、riskLevel、advice、
   sources 这些字段仍由本模块按知识库与规则表产出，响应结构对前端不变。
   .env 没配 LLM_API_KEY、模型调用失败、模型输出为空，一律返回空值走规则模板 ——
   大模型是增强项，不该让检查报告的接口跟着一起挂。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.department import Department
from app.models.exam import Exam
from app.models.exam_report import ExamReport
from app.models.patient import Patient
from app.schemas.exam import (
    DISCLAIMER,
    WAIT_ESTIMATE_NOTE,
    AbnormalItemMeaning,
    ExamAnalysisData,
    ExamAnalysisRequest,
    ExamListItem,
    ExamListData,
    ExamLocationData,
    ExamPrecautionsData,
    ExamQueueData,
    ExamReportData,
    ExamReportItem,
    ExamStatusData,
    ExamStatusStep,
    KnowledgeSource,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

EXAM_STATUS_DESC: dict[str, str] = {
    "WAIT_PAY": "待缴费",
    "WAIT_EXAM": "待检查",
    "WAIT_REPORT": "待报告",
    "REPORTED": "已报告",
}

# 状态机是单向的（数据库设计文档 4.x），进度条据此展开
EXAM_STATUS_ORDER: tuple[str, ...] = ("WAIT_PAY", "WAIT_EXAM", "WAIT_REPORT", "REPORTED")

# 只有待检查 / 待报告的检查单才在叫号队列里有意义（seed 与设计文档 4.4 一致）
IN_QUEUE_STATUS: tuple[str, ...] = ("WAIT_EXAM", "WAIT_REPORT")

# 知识库 collection（services/rag/collections.py 的注册表名）
KB_EXAM = "kb_exam"
KB_REPORT = "kb_report"

# 检索命中低于该分数视为没命中，避免拿不相关知识硬凑解读
SEARCH_MIN_SCORE = 0.45

# 引用来源上限：每条异常指标贡献一条来源，给足条数以保证逐项可溯源，同时兜住上限
MAX_SOURCES = 10

# 未匹配到具体医技科室时的兜底名（t_department 里没有这一行，deptId 返回 null）
DEFAULT_EXEC_DEPT = "医技科室"

# 检查项目 → 执行医技科室。按顺序匹配，命中即止，所以影像类必须排在检验类之前
# （否则「心血管CT」会被检验类的「血」关键字抢走）。
_DEPT_BY_KEYWORD: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("超声医学科", ("超声", "B超", "彩超", "多普勒")),
    (
        "医学影像科",
        ("CT", "MRI", "核磁", "X线", "X光", "DR", "平扫", "增强", "CTA", "造影", "摄片", "骨密度"),
    ),
    ("内镜中心", ("胃镜", "肠镜", "支气管镜", "膀胱镜", "喉镜", "内镜")),
    ("心电图室", ("心电图", "动态血压", "血压监测")),
    ("肺功能室", ("肺功能",)),
    (
        "医学检验科",
        (
            "血", "尿", "粪便", "肝功", "肾功", "血脂", "血糖", "糖化", "凝血", "心肌",
            "肌钙", "脑钠肽", "BNP", "D-二聚体", "C反应蛋白", "CRP", "红细胞沉降", "血沉",
            "降钙素", "甲状腺", "肿瘤标志物", "乙肝", "感染四项", "血型", "血气", "电解质",
            "淀粉酶", "脂肪酶", "流感", "核酸", "冠状病毒", "白蛋白", "胆红素", "尿酸", "肌酐",
        ),
    ),
)

# t_exam 没存科室，检查项目名也认不出来时退一步看房间名（seed 的房间名带执行科室特征）
_DEPT_BY_ROOM: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("医学影像科", ("影像",)),
    ("超声医学科", ("超声",)),
    ("心电图室", ("心电图",)),
    ("医学检验科", ("检验", "采血")),
)

# 影像类检查一旦异常，风险等级直接判高（与 seed 的 _risk_level_for 口径一致）
_IMAGING_HINT: tuple[str, ...] = ("CT", "MRI", "X线", "DR", "造影", "摄片", "超声", "B超", "彩超")

# 定性结果（阳性/阴性）不能套用「偏高/偏低」的说法
_QUALITATIVE_HINT: tuple[str, ...] = ("阳性", "阴性", "未见", "检出", "不除")

_KB_FIELD_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(.*?)\s*\|\s*$", re.MULTILINE)
_KB_SECTION_RE = re.compile(r"\*\*(检查目的|检查流程|注意事项)\*\*")
_MARKUP_RE = re.compile(r"[*`#>|]")


class ExamError(Exception):
    """检查模块业务错误。

    code 取接口文档 2.5 通用错误码表；core/errors.py 落地后应改为继承统一的
    业务异常基类，这里的定位是「领域错误 → HTTP 适配」的中间层。
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- #
# 执行科室解析
# --------------------------------------------------------------------------- #


def resolve_exec_dept(exam: Exam) -> str:
    """按检查项目名推断执行科室，认不出来就看房间名，最后兜底「医技科室」。"""
    name = exam.exam_name or ""
    for dept_name, keywords in _DEPT_BY_KEYWORD:
        if any(k in name for k in keywords):
            return dept_name

    room = exam.room or ""
    for dept_name, keywords in _DEPT_BY_ROOM:
        if any(k in room for k in keywords):
            return dept_name

    return DEFAULT_EXEC_DEPT


def _load_departments(session: Session, dept_names: Iterable[str]) -> dict[str, Department]:
    """一次性把用到的科室查出来，避免列表里逐行查库。"""
    names = {n for n in dept_names if n}
    if not names:
        return {}
    rows = session.scalars(select(Department).where(Department.dept_name.in_(names))).all()
    return {d.dept_name: d for d in rows}


def _join_location(*parts: Optional[str]) -> Optional[str]:
    text = "".join(p for p in parts if p)
    return text or None


# --------------------------------------------------------------------------- #
# 知识库检索
# --------------------------------------------------------------------------- #


def _search_many(specs: Sequence[tuple[str, str, int]]) -> list[list[dict[str, Any]]]:
    """批量向量检索，specs 为 (collection, query, top_k)。

    一次编码全部 query 再逐条检索：BGE-M3 在 CPU 上很贵，逐条调用会把同一批
    query 反复过一遍模型。检索是本模块的增强项而非必需项，任何环节失败都
    返回空结果由调用方降级，不往上抛。

    AI 依赖（torch / FlagEmbedding / pymilvus）单独装在 requirements-ai.txt，
    因此这里延迟导入 —— 没装 AI 依赖时检查模块的其余接口照常可用。
    """
    if not specs:
        return []

    try:
        from app.services.rag.embedding import embed_texts
        from app.services.rag.milvus_client import get_client
    except ImportError:
        logger.warning("未安装 AI 依赖，跳过知识库检索")
        return [[] for _ in specs]

    try:
        client = get_client()
        vectors = embed_texts([query for _, query, _ in specs])
    except Exception:
        logger.warning("知识库向量化/连接失败，改用数据库缓存字段", exc_info=True)
        return [[] for _ in specs]

    output_fields = ["text", "source_file", "title_path", "category"]
    results: list[list[dict[str, Any]]] = []
    for (collection, query, top_k), vector in zip(specs, vectors):
        try:
            hits = client.search(
                collection_name=collection,
                data=[vector],
                limit=top_k,
                output_fields=output_fields,
            )
        except Exception:
            logger.warning("知识库检索失败：collection=%s query=%s", collection, query, exc_info=True)
            results.append([])
            continue

        rows: list[dict[str, Any]] = []
        for group in hits:
            for hit in group:
                entity = dict(hit.get("entity") or {})
                score = float(hit.get("distance") or 0.0)
                if score < SEARCH_MIN_SCORE:
                    continue
                entity["score"] = score
                rows.append(entity)
        results.append(rows)

    return results


def _plain(text: Optional[str]) -> str:
    """去掉 Markdown 标记，得到可直接念出来/展示的纯文本。

    知识库条目之间用 `---` 分隔，这类「只有符号」的行要去掉，
    否则会原样跑进注意事项和语音播报里。
    """
    if not text:
        return ""
    cleaned = _MARKUP_RE.sub(" ", text)
    cleaned = re.sub(r"(?m)^[\s\-–—•·*=~_]+$", "", cleaned)
    cleaned = re.sub(r"^\s*[-•]\s*", "", cleaned, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", cleaned).strip(" ;；。-")


def _join_sentences(parts: Iterable[str]) -> str:
    """拼成适合语音播报的整段：逐句收尾补句号，避免句子连读粘连。"""
    sentences: list[str] = []
    for part in parts:
        text = (part or "").strip()
        if not text:
            continue
        if text[-1] not in "。！？；：":
            text += "。"
        sentences.append(text)
    return "".join(sentences)


def _to_sources(hits: Sequence[dict[str, Any]], limit: int = MAX_SOURCES) -> list[KnowledgeSource]:
    """检索结果 → 引用来源，按「来源文件 + 标题」去重后保序输出。"""
    sources: list[KnowledgeSource] = []
    seen: set[tuple[str, str]] = set()
    for hit in hits:
        title = hit.get("title_path") or hit.get("category") or "知识库"
        source_file = hit.get("source_file") or ""
        key = (source_file, title)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            KnowledgeSource(
                title=title,
                sourceFile=source_file,
                snippet=_plain(hit.get("text"))[:160],
            )
        )
        if len(sources) >= limit:
            break
    return sources


def _split_exam_kb(text: str) -> dict[str, str]:
    """把检查知识库的一条条目拆成 检查目的 / 检查流程 / 注意事项 三段。"""
    matches = list(_KB_SECTION_RE.finditer(text or ""))
    sections: dict[str, str] = {}
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections[match.group(1)] = text[start:end].strip()
    return sections


def _parse_kb_fields(text: str) -> dict[str, str]:
    """解析报告知识库的字段表（`ref` / `↑ causes` / `↓ causes` / `suggest` …）。"""
    return {name.strip(): value for name, value in _KB_FIELD_RE.findall(text or "")}


def _kb_entry_matches(item_name: str, title: str) -> bool:
    """判断检索到的知识库条目是否真的就是这条指标。

    报告知识库只收录检验指标，而报告里还有「影像所见」这类自由文本项。
    向量检索总归会返回一个「最接近」的条目，若不加这道校验，就会把
    「细胞角蛋白 19 片段」的病因安到「右肺下叶斑片状磨玻璃影」头上 ——
    宁可不说，也不能说错。标题形如「一、血常规 > 1.1 白细胞计数 WBC」。
    """
    kb_name = re.sub(r"^\s*\d+(\.\d+)*\s*", "", _plain((title or "").split(">")[-1])).strip()
    item = _plain(item_name)
    if not kb_name or not item:
        return False

    kb_compact, item_compact = kb_name.replace(" ", ""), item.replace(" ", "")
    if item_compact in kb_compact or kb_compact in item_compact:
        return True

    # 标题带缩写时（如「中性粒细胞 NEUT / NEUT%」）逐段比对，取标题里的中文词
    return any(
        len(token) >= 2 and (token in item_compact or item_compact in token)
        for token in kb_name.replace("/", " ").split()
    )


# --------------------------------------------------------------------------- #
# 内部查询
# --------------------------------------------------------------------------- #


def _get_exam(session: Session, exam_id: str, user_id: str) -> Exam:
    """取检查单并校验归属。

    检查单不存在与不属于当前账号返回同一个 4003：既避免用错误码差异暴露
    「这个编号存在」，也省掉一次多余的枚举风险。
    """
    exam = session.scalars(
        select(Exam)
        .join(Patient, Exam.patient_id == Patient.patient_id)
        .where(Exam.exam_id == exam_id, Patient.user_id == user_id)
    ).first()
    if exam is None:
        raise ExamError(4003, "检查单不存在或无权访问")
    return exam


def _get_report(session: Session, exam_id: str) -> Optional[ExamReport]:
    return session.scalars(
        select(ExamReport).where(ExamReport.exam_id == exam_id).order_by(ExamReport.report_id.desc())
    ).first()


def _parse_items(report: Optional[ExamReport]) -> list[ExamReportItem]:
    """t_exam_report.items_json → 结构化指标项，坏数据不拖垮整个接口。"""
    if report is None or not report.items_json:
        return []
    try:
        raw = json.loads(report.items_json)
    except (TypeError, ValueError):
        logger.warning("报告 %s 的 items_json 不是合法 JSON，按无指标处理", report.report_id)
        return []
    if not isinstance(raw, list):
        return []

    items: list[ExamReportItem] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        flag = str(entry.get("abnormalFlag") or "NORMAL").upper()
        items.append(
            ExamReportItem(
                itemName=str(entry.get("itemName") or ""),
                value=None if entry.get("value") is None else str(entry.get("value")),
                unit=None if entry.get("unit") is None else str(entry.get("unit")),
                referenceRange=(
                    None if entry.get("referenceRange") is None else str(entry.get("referenceRange"))
                ),
                abnormalFlag=flag if flag in ("NORMAL", "HIGH", "LOW") else "NORMAL",
            )
        )
    return items


def _derive_exam_date(exam: Exam, appt_date: Optional[date]) -> Optional[date]:
    """检查日期：优先预约日期，无预约时回落开单日期。"""
    if appt_date is not None:
        return appt_date
    return exam.created_at.date() if exam.created_at else None


# --------------------------------------------------------------------------- #
# 检查列表
# --------------------------------------------------------------------------- #


def list_exams(
    session: Session,
    *,
    user_id: str,
    patient_id: Optional[str] = None,
    exam_status: Optional[str] = None,
    page_num: int = 1,
    page_size: int = 10,
) -> ExamListData:
    """查询当前账号（可指定就诊人）的全部检查，按日期倒序 —— 最近的排最前。

    排序键用「预约日期，缺省回落开单日期」：t_exam 本身没有检查日期字段
    （数据库设计文档 3.12 如此），而用户理解的「检查日期」就是那次就诊的日期。
    """
    if exam_status and exam_status not in EXAM_STATUS_DESC:
        raise ExamError(4001, f"检查状态取值不合法：{exam_status}")

    conditions = [Patient.user_id == user_id]
    if patient_id:
        conditions.append(Exam.patient_id == patient_id)
    if exam_status:
        conditions.append(Exam.exam_status == exam_status)

    total = session.scalar(
        select(func.count())
        .select_from(Exam)
        .join(Patient, Exam.patient_id == Patient.patient_id)
        .where(*conditions)
    ) or 0

    exam_date = func.coalesce(Appointment.appt_date, func.date(Exam.created_at))
    rows = session.execute(
        select(Exam, Patient.name, Appointment.appt_date, ExamReport)
        .join(Patient, Exam.patient_id == Patient.patient_id)
        .outerjoin(Appointment, Exam.appointment_id == Appointment.appointment_id)
        .outerjoin(ExamReport, ExamReport.exam_id == Exam.exam_id)
        .where(*conditions)
        .order_by(exam_date.desc(), Exam.exam_id.desc())
        .offset((page_num - 1) * page_size)
        .limit(page_size)
    ).all()

    dept_names = {resolve_exec_dept(exam) for exam, _, _, _ in rows}
    dept_by_name = _load_departments(session, dept_names)

    items: list[ExamListItem] = []
    for exam, patient_name, appt_date, report in rows:
        dept_name = resolve_exec_dept(exam)
        dept = dept_by_name.get(dept_name)
        items.append(
            ExamListItem(
                examId=exam.exam_id,
                examName=exam.exam_name,
                examStatus=exam.exam_status,
                statusDesc=EXAM_STATUS_DESC.get(exam.exam_status, exam.exam_status),
                patientId=exam.patient_id,
                patientName=patient_name or "",
                deptId=dept.dept_id if dept else None,
                deptName=dept_name,
                building=exam.building,
                floor=exam.floor,
                room=exam.room,
                locationText=_join_location(exam.building, exam.floor, exam.room),
                examDate=_derive_exam_date(exam, appt_date),
                queueNo=exam.queue_no,
                reportId=report.report_id if report else None,
                reportStatus=report.report_status if report else None,
            )
        )

    return ExamListData(total=total, pageNum=page_num, pageSize=page_size, list=items)


# --------------------------------------------------------------------------- #
# API-27 检查报告查询
# --------------------------------------------------------------------------- #


def get_report(session: Session, exam_id: str, user_id: str) -> ExamReportData:
    """报告未出具不算错误：返回 reportStatus=WAIT_REPORT 的空壳给前端轮询/等推送。"""
    exam = _get_exam(session, exam_id, user_id)
    report = _get_report(session, exam_id)

    return ExamReportData(
        examId=exam.exam_id,
        examName=exam.exam_name,
        reportId=report.report_id if report else None,
        reportStatus=report.report_status if report else "WAIT_REPORT",
        reportTime=report.report_time if report else None,
        reportContent=report.report_content if report else None,
        items=_parse_items(report),
        reportImageUrl=report.report_image_url if report else None,
    )


# --------------------------------------------------------------------------- #
# API-29 检查报告 AI 分析
# --------------------------------------------------------------------------- #


def _is_qualitative(value: Optional[str]) -> bool:
    return any(k in (value or "") for k in _QUALITATIVE_HINT)


def _build_meaning(item: ExamReportItem, fields: dict[str, str]) -> str:
    """用报告知识库的字段表拼出该项的通俗解释。

    fields 为空表示知识库没有这条指标（如「影像所见」这类自由文本项），
    此时只做客观复述并交回医生，不做任何病因推断。
    """
    if not fields:
        value = f"：{item.value}" if item.value else ""
        return (
            f"{item.itemName}{value}。该项需由医生结合原始报告与临床表现判读，"
            "本系统不单独解释其含义，请以接诊医生意见为准。"
        )

    direction = "↑ causes" if item.abnormalFlag == "HIGH" else "↓ causes"
    causes = fields.get(direction)

    if _is_qualitative(item.value):
        head = f"{item.itemName}结果为「{item.value}」"
    else:
        head = f"{item.itemName}{'偏高' if item.abnormalFlag == 'HIGH' else '偏低'}"

    if not causes:
        mechanism = fields.get("mechanism")
        if mechanism:
            return f"{head}。{_plain(mechanism)}。建议结合参考区间与临床症状由医生判断。"
        return f"{head}。建议携带报告复诊，由医生结合临床症状综合判断。"

    meaning = f"{head}。常见原因：{_plain(causes)}。"
    if fields.get("suggest"):
        meaning += f"建议：{_plain(fields['suggest'])}。"
    if fields.get("warn"):
        meaning += f"需留意：{_plain(fields['warn'])}。"
    return meaning


def _derive_risk_level(exam_name: str, abnormal_items: Sequence[ExamReportItem]) -> str:
    """风险等级：无异常为低；影像类异常提示器质性病变，判高；其余判中。"""
    if not abnormal_items:
        return "LOW"
    if any(k in (exam_name or "") for k in _IMAGING_HINT):
        return "HIGH"
    return "MEDIUM"


def _max_risk(cached: Optional[str], derived: str) -> str:
    """缓存等级与按指标推算的等级取更严重的一个。

    缓存值来自建库/上一次分析，可能与结构化指标对不上（seed 数据里就有
    「3 项指标偏高却标 LOW」的情况）。指标是机器可读的事实，等级若比它低
    就是错的；缓存更高则保留（可能来自更权威的大模型解读）。
    """
    order = ("LOW", "MEDIUM", "HIGH")
    if cached not in order:
        return derived
    return cached if order.index(cached) >= order.index(derived) else derived


def _build_advice(risk_level: str, abnormal_items: Sequence[ExamReportItem], suggests: Sequence[str]) -> str:
    if not abnormal_items:
        return "本次检查各项指标未见明显异常，建议保持现有作息与用药，按医嘱定期随访复查。"

    lines: list[str] = []
    if risk_level == "HIGH":
        lines.append("本次检查存在需要重点关注的异常，建议尽快携带报告复诊，由医生结合症状、体征与其他检查综合判断。")
    else:
        lines.append("本次检查部分指标异常，建议携带报告复诊，由医生结合症状、体征与其他检查综合判断。")

    for text in dict.fromkeys(s for s in suggests if s):
        lines.append(f"· {text}")

    lines.append("如出现发热、胸痛、呼吸困难、意识改变等急症表现，请直接前往急诊，不要等待复诊。")
    return "\n".join(lines)


def _llm_analyze(
    exam: Exam,
    report: ExamReport,
    meanings: Sequence[AbnormalItemMeaning],
    hits: Sequence[dict[str, Any]],
) -> Optional[str]:
    """报告 Agent 入口：让大模型把逐项含义写成一段通读的解读，失败返回 None。

    abnormalItems / riskLevel / advice / sources 仍由本模块产出，响应结构对前端不变。

    交给模型的是 `meanings`（规则表算出的逐项通俗含义）而不是全部指标项：
    这些含义已经过知识库核对（见 _kb_entry_matches），模型据此组织语言即可，
    既不用自己判断数值高低（说反了就成事故），也没有臆测的余地。

    未配 LLM_API_KEY、网络不通、模型输出为空、AI 依赖没装 —— 一律返回 None 走规则模板：
    检查报告解读不该因为大模型抖一下而整个接口失败。
    """
    if not meanings and not (report.report_content or "").strip():
        return None  # 没有可解读的素材，模型只能编，直接走模板
    try:
        from app.services.rag.agents import report_agent

        return (
            report_agent.analyze(
                exam_name=exam.exam_name,
                report_content=report.report_content or "",
                items=[item.model_dump() for item in meanings],
                hits=list(hits),
            )
            or None
        )
    except Exception as exc:  # noqa: BLE001 - 大模型是增强项，失败即回规则模板
        logger.warning("报告解读大模型调用失败，改用规则模板: %s", exc)
        return None


def _template_analysis(
    report: ExamReport,
    items: Sequence[ExamReportItem],
    meanings: Sequence[AbnormalItemMeaning],
) -> str:
    lines: list[str] = []
    if report.report_content:
        lines.append(f"检查结论：{_plain(report.report_content)}")

    if items:
        lines.append(f"本次共 {len(items)} 项指标，其中 {len(meanings)} 项异常。")
    elif report.report_content:
        lines.append("本次报告未提供结构化指标项，以上结论供参考。")

    for idx, item in enumerate(meanings, start=1):
        lines.append(f"{idx}. {item.meaning}")

    if not meanings:
        lines.append("各项指标均在参考区间内，未见提示性异常。")

    return "\n".join(lines)


def analyze_report(
    session: Session,
    exam_id: str,
    user_id: str,
    payload: Optional[ExamAnalysisRequest] = None,
) -> ExamAnalysisData:
    """报告解读：结构化指标 → 异常项逐条检索报告知识库 → 大模型组织语言，失败走模板。"""
    exam = _get_exam(session, exam_id, user_id)
    payload = payload or ExamAnalysisRequest()

    report = _get_report(session, exam_id)
    if report is None or report.report_status != "REPORTED":
        raise ExamError(4001, "报告尚未出具，暂无法解读，请稍后再试")
    if payload.reportId and payload.reportId != report.report_id:
        # 报告ID 与检查单不匹配：宁可报错也不解读错的报告
        raise ExamError(4001, "报告ID与检查单不匹配")

    items = _parse_items(report)
    abnormal = [i for i in items if i.abnormalFlag != "NORMAL"]

    # 逐条异常项检索：query 带上指标名与异常方向，便于命中对应条目
    specs = [
        (KB_REPORT, f"{i.itemName} {i.value or ''} {'偏高' if i.abnormalFlag == 'HIGH' else '偏低'} 临床意义", 1)
        for i in abnormal
    ]
    hit_groups = _search_many(specs)

    meanings: list[AbnormalItemMeaning] = []
    suggests: list[str] = []
    used_hits: list[dict[str, Any]] = []
    for item, hits in zip(abnormal, hit_groups):
        # 命中的条目要和指标对得上才拿来用，否则当作知识库未收录（见 _kb_entry_matches）
        fields: dict[str, str] = {}
        if hits and _kb_entry_matches(item.itemName, hits[0].get("title_path", "")):
            fields = _parse_kb_fields(hits[0]["text"])
            used_hits.extend(hits)
        else:
            logger.debug("报告知识库未收录指标「%s」，仅做客观复述", item.itemName)

        meanings.append(
            AbnormalItemMeaning(
                itemName=item.itemName,
                value=item.value,
                abnormalFlag=item.abnormalFlag,
                meaning=_build_meaning(item, fields),
            )
        )
        if fields.get("suggest"):
            suggests.append(_plain(fields["suggest"]))

    risk_level = _max_risk(report.risk_level, _derive_risk_level(exam.exam_name, abnormal))
    advice = _build_advice(risk_level, abnormal, suggests)

    analysis = _llm_analyze(exam, report, meanings, used_hits) or _template_analysis(report, items, meanings)

    # 解读结果回写缓存（t_exam_report.ai_analysis 的设计用途），下次直接复用；
    # 缓存的风险等级偏低时一并纠正，否则错误的低等级会一直留在库里
    if not report.ai_analysis:
        report.ai_analysis = analysis
    if report.risk_level != risk_level:
        report.risk_level = risk_level
    session.commit()

    follow_up = f"/ai?scene=REPORT&examId={exam.exam_id}&reportId={report.report_id}"
    if payload.sessionId:
        follow_up += f"&sessionId={payload.sessionId}"

    return ExamAnalysisData(
        examId=exam.exam_id,
        examName=exam.exam_name,
        reportId=report.report_id,
        analysis=analysis,
        abnormalItems=meanings,
        riskLevel=risk_level,
        advice=advice,
        followUpUrl=follow_up,
        sources=_to_sources(used_hits),
    )


# --------------------------------------------------------------------------- #
# API-24 检查注意事项
# --------------------------------------------------------------------------- #


def _llm_precautions(exam: Exam, hits: Sequence[dict[str, Any]]) -> list[str]:
    """检查助手 Agent 入口：返回分条的注意事项，失败返回空列表走模板。

    返回列表而不是整段文本：`precautions` 与语音播报 `voiceText` 共用同一批句子，
    两边文案因此天然一致（见 get_precautions）。

    一条检查知识库资料都没命中时不调模型 —— 它只能自己编准备要求（「空腹 8 小时」
    这类，编错了患者就白跑一趟），而模板那边还有库内缓存 t_exam.precautions 可用。
    """
    if not hits:
        return []
    try:
        from app.services.rag.agents import exam_agent

        return exam_agent.precautions(exam_name=exam.exam_name, hits=list(hits))
    except Exception as exc:  # noqa: BLE001 - 大模型是增强项，失败即回规则模板
        logger.warning("检查注意事项大模型调用失败，改用规则模板: %s", exc)
        return []


def _template_precautions(exam: Exam, sections: dict[str, str], cached: Optional[str]) -> list[str]:
    """注意事项文本：库内缓存（检查知识库生成的）+ 知识库条目的分条要点。"""
    lines: list[str] = []
    if cached:
        lines.append(_plain(cached))

    raw_notes = sections.get("注意事项") or ""
    for line in raw_notes.splitlines():
        text = _plain(line)
        if text and text not in lines:
            lines.append(text)

    if not lines:
        lines.append("请按检查申请单与医务人员指引做好准备，如有疑问请咨询开单医生或检查科室。")
    return lines


def get_precautions(session: Session, exam_id: str, user_id: str) -> ExamPrecautionsData:
    """注意事项：检索检查知识库拿 目的/流程/注意事项，检索不到就用库内缓存字段。"""
    exam = _get_exam(session, exam_id, user_id)

    # 只取最高分的 1 条：检查知识库里一项检查就是一个 chunk，目的/流程/注意事项
    # 都在同一段里，多召回的条目不会被读到，列进 sources 反而误导用户。
    hits = _search_many([(KB_EXAM, f"{exam.exam_name} 检查目的 检查流程 注意事项", 1)])[0]
    sections = _split_exam_kb(hits[0]["text"]) if hits else {}

    # 大模型与模板产出的都是「分条文案」，二者共用下面这批 lines：
    # 展示用的 precautions 与语音播报的 voiceText 由同一份内容拼出，不会各说各话
    lines = _llm_precautions(exam, hits) or _template_precautions(exam, sections, exam.precautions)
    precautions = "\n".join(lines)

    purpose = _plain(sections.get("检查目的")) or None
    process = _plain(sections.get("检查流程")) or None

    # 语音播报：一口气念完，位置信息一并带上（检查指引页有无障碍播报需求）
    voice_parts = [f"{exam.exam_name}的检查注意事项。", *lines]
    if exam.building or exam.floor or exam.room:
        voice_parts.append(f"检查地点：{_join_location(exam.building, exam.floor, exam.room)}")
    voice_parts.append(DISCLAIMER)

    return ExamPrecautionsData(
        examId=exam.exam_id,
        examName=exam.exam_name,
        precautions=precautions,
        purpose=purpose,
        process=process,
        voiceText=_join_sentences(voice_parts),
        sources=_to_sources(hits),
    )


# --------------------------------------------------------------------------- #
# API-25 检查叫号查询
# --------------------------------------------------------------------------- #


def get_queue(session: Session, exam_id: str, user_id: str) -> ExamQueueData:
    """叫号信息。设计文档 4.4 建议轮询 HIS 而不落库，本期直接读本地同步值。"""
    exam = _get_exam(session, exam_id, user_id)
    in_queue = exam.exam_status in IN_QUEUE_STATUS

    return ExamQueueData(
        examId=exam.exam_id,
        examName=exam.exam_name,
        queueNo=exam.queue_no if in_queue else None,
        currentNo=exam.current_no if in_queue else None,
        peopleAhead=exam.people_ahead if in_queue else None,
        estimatedWaitMinutes=exam.estimated_wait_minutes if in_queue else None,
        estimateNote=WAIT_ESTIMATE_NOTE,
        inQueue=in_queue,
    )


# --------------------------------------------------------------------------- #
# API-26 检查位置指引
# --------------------------------------------------------------------------- #


def get_location(session: Session, exam_id: str, user_id: str) -> ExamLocationData:
    """位置指引。位置以检查单自身为准，缺失时回落执行科室的登记位置。"""
    exam = _get_exam(session, exam_id, user_id)
    dept_name = resolve_exec_dept(exam)
    dept = _load_departments(session, [dept_name]).get(dept_name)

    # 位置以检查单自身字段为准（它描述的就是这次检查的实际去处），
    # t_exam 三个字段全空时才退回科室登记的地址；Department 没有独立楼栋列，
    # 所以不从 dept_addr 里拆楼栋，直接把整条地址当兜底。
    building, floor, room = exam.building, exam.floor, exam.room
    if any((building, floor, room)):
        full_address = _join_location(building, floor, room) or "位置信息待补充"
    else:
        full_address = (dept.dept_addr if dept else None) or "位置信息待补充"

    # 院内导航按 targetCode 定位（接口文档 API-21），优先用科室的楼层位置编码
    target_code = (dept.floor_position if dept and dept.floor_position else None) or full_address
    nav_url = f"/navigation/indoor?targetCode={target_code}"
    if floor:
        nav_url += f"&floor={floor}"

    return ExamLocationData(
        examId=exam.exam_id,
        examName=exam.exam_name,
        deptName=dept_name,
        building=building,
        floor=floor,
        room=room,
        fullAddress=full_address,
        indoorNavUrl=nav_url,
    )


# --------------------------------------------------------------------------- #
# API-28 检查状态查询
# --------------------------------------------------------------------------- #


def get_status(session: Session, exam_id: str, user_id: str) -> ExamStatusData:
    """状态 + 进度条节点。"""
    exam = _get_exam(session, exam_id, user_id)

    current_idx = (
        EXAM_STATUS_ORDER.index(exam.exam_status) if exam.exam_status in EXAM_STATUS_ORDER else -1
    )
    steps = [
        ExamStatusStep(
            status=status,  # type: ignore[arg-type]
            statusDesc=EXAM_STATUS_DESC[status],
            reached=idx <= current_idx,
            current=idx == current_idx,
        )
        for idx, status in enumerate(EXAM_STATUS_ORDER)
    ]

    updated: Optional[datetime] = exam.updated_at
    return ExamStatusData(
        examId=exam.exam_id,
        examName=exam.exam_name,
        examStatus=exam.exam_status,  # type: ignore[arg-type]
        statusDesc=EXAM_STATUS_DESC.get(exam.exam_status, exam.exam_status),
        updateTime=updated.strftime("%Y-%m-%d %H:%M:%S") if updated else None,
        steps=steps,
    )


__all__ = [
    "DEFAULT_EXEC_DEPT",
    "EXAM_STATUS_DESC",
    "EXAM_STATUS_ORDER",
    "ExamError",
    "analyze_report",
    "get_location",
    "get_precautions",
    "get_queue",
    "get_report",
    "get_status",
    "list_exams",
    "resolve_exec_dept",
]
