"""病历模块业务逻辑（接口文档 3.7：API-22 历史病历查询 / API-23 病历AI解读）。

数据来源：开发期 HIS_ENABLED=false，直接读本地库 t_medical_record 及其关联表
（t_appointment / t_department / t_doctor / t_prescription / t_prescription_item / t_medication）；
HIS 就绪后只需把 _query_records 换成服务层调用，返回结构不变。

病历解读走「可插拔 Agent + 术语词典兜底」两条路：
  1. AI 模块就绪后调用 register_interpret_agent() 注册真实实现，或实现
     app.services.rag.agents.record_agent.interpret，本模块会自动探测到；
  2. 二者都没有时用本地术语词典生成通俗化解读，保证接口随时可联调。

依赖的公共模块（非本模块职责，由公共基建提供）：
  app.core.errors.BizError  —— 业务异常，签名 BizError(code, message)
  app.utils.mask.mask_name  —— 姓名脱敏，保留首末字符，如“张*生”“张*”
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BizError
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.medical_record import MedicalRecord
from app.models.medication import Medication
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.models.prescription_item import PrescriptionItem
from app.schemas.medical_record import (
    InterpretationResponse,
    MedicalRecordBrief,
    MedicalRecordPage,
    TermMapping,
)
from app.utils.mask import mask_name

logger = logging.getLogger(__name__)

# 接口文档 2.5 通用错误码
PARAM_INVALID = 4001
ACCESS_DENIED = 4003

DISCLAIMER = "以上解读仅为辅助参考，不构成医疗诊断，最终以医疗机构和执业医师意见为准"
FOLLOW_UP_URL = "/ai"  # 前端 AI 助手路由（frontend/src/router/routes.js）
NO_PRESCRIPTION = "暂无处方"
RULE_BASED_SOURCES = ["诊疗知识库"]

# 单条医嘱最多列出几种药名，超出则以“等N种”收尾
BRIEF_NAME_LIMIT = 3
# 解读文本中最多罗列的术语条数，避免长篇堆砌
TERM_LIST_LIMIT = 12


# --------------------------------------------------------------------------- #
# 术语词典：专业表述 -> 通俗解释
# 覆盖 seed 数据中病历原文、检验指标与常见诊断的用词，供规则化解读使用。
# --------------------------------------------------------------------------- #

TERM_DICT: dict[str, str] = {
    # —— 病历文书用语 ——
    "主诉": "你这次来看病，最主要的不舒服是什么",
    "现病史": "这次不舒服从什么时候开始、怎么变化的",
    "查体": "医生用手或简单器械做的身体检查",
    "辅助检查": "抽血、拍片、B超这类检查",
    "待回报": "检查结果还没出来",
    "处理意见": "医生给出的治疗安排和注意事项",
    "复诊": "按医生约的时间再来一次",
    "随访": "医生定期了解你的病情变化",
    "对症治疗": "有什么症状就缓解什么症状，不是直接针对病因",
    "抗感染": "用药物对付细菌等病原体",
    "抗病毒": "用药物抑制病毒",
    "居家隔离": "在家休息，尽量不外出、不接触他人",
    # —— 症状与体征 ——
    "咽部充血": "咽喉发红、充血，说明有炎症",
    "双侧扁桃体I度肿大": "两边的扁桃体轻度肿大（I度是最轻的一级）",
    "扁桃体肿大": "喉咙两侧的扁桃体肿起来了",
    "高热": "体温比较高，一般指 39℃ 以上",
    "发热": "发烧，体温高于正常",
    "咳嗽": "嗓子受刺激后不自主地用力呼气",
    "气促": "呼吸比平时急、觉得气不够用",
    "血氧饱和度": "血液里氧气的含量，低于 93% 要尽快就医",
    "空腹": "检查前不要吃东西",
    "憋尿": "检查前喝水把膀胱撑起来，方便 B 超看清",
    # —— 检验指标 ——
    "白细胞计数": "血液里负责抵抗感染的白细胞数量",
    "中性粒细胞百分比": "白细胞里专门对付细菌的那一类占的比例",
    "淋巴细胞百分比": "白细胞里主要负责抗病毒的那一类占的比例",
    "血红蛋白": "血液里负责运输氧气的蛋白，偏低就是贫血",
    "血小板计数": "负责止血的血细胞数量",
    "C反应蛋白": "身体有炎症或感染时会升高的一项指标",
    "降钙素原": "细菌感染时会升高的一项指标，越高越提示细菌感染",
    "丙氨酸氨基转移酶": "反映肝细胞有没有受损的指标，常说的“转氨酶”之一",
    "天门冬氨酸氨基转移酶": "同样反映肝脏情况的一项转氨酶",
    "肌酐": "反映肾脏过滤功能的指标",
    "转氨酶": "肝脏里的酶，肝细胞受损时会漏到血里，指标就升高",
    "甲型流感病毒抗原": "用于查甲型流感的化验项目",
    "甲流抗原阳性": "检出了甲型流感病毒，也就是常说的“甲流”",
    "阳性": "检查发现了要找的东西",
    "阴性": "检查没有发现要找的东西",
    # —— 影像与心电 ——
    "双肺纹理增粗": "肺部的血管和支气管影像比平时清晰，常见于炎症或长期吸烟",
    "斑片状磨玻璃密度影": "肺里有一小片淡淡的雾状模糊影，多提示炎症",
    "磨玻璃密度影": "影像上像磨砂玻璃一样的淡淡影子，常提示炎症等改变",
    "炎性病变": "由炎症引起的改变",
    "纵隔未见肿大淋巴结": "两肺之间的区域没有发现淋巴结肿大，属于正常表现",
    "双侧胸腔未见积液": "胸腔里没有积水，属于正常表现",
    "未见明显异常": "没有发现明显的问题",
    "未见骨折征象": "片子上没有看到骨折",
    "窦性心动过速": "心跳偏快，但心脏的起搏点是正常的",
    "腰椎生理曲度变直": "腰椎正常的弧度变平了，常和久坐、腰部劳损有关",
    "椎间隙轻度变窄": "腰椎骨之间的“垫子”（椎间盘）薄了一点",
    "CT平扫": "不打显影剂的 CT 检查",
    "B超": "用超声波看内脏的检查，没有辐射",
}


# --------------------------------------------------------------------------- #
# 常见诊断的通俗解释（seed 数据的 FEVER_DIAGNOSES / OTHER_DIAGNOSES 全覆盖）
# --------------------------------------------------------------------------- #

DIAGNOSIS_PLAIN: dict[str, str] = {
    "流行性感冒（甲型）": "得了甲型流感，是流感病毒引起的呼吸道传染病，比普通感冒症状重、发热更明显",
    "急性上呼吸道感染": "俗称“感冒”，鼻子、咽喉这些上呼吸道被病原体感染了",
    "急性化脓性扁桃体炎": "扁桃体被细菌感染并化脓发炎了，常伴咽痛和高热",
    "社区获得性肺炎": "在医院外得的肺部感染，肺组织发炎了",
    "感染性腹泻": "肠道被病原体感染引起的拉肚子",
    "新型冠状病毒感染": "感染了新冠病毒，可能表现为发热、咽痛、咳嗽等",
    "发热待查": "目前有发烧，但还没查明原因，需要继续做检查",
    "支气管哮喘急性发作": "哮喘突然加重，气道变窄导致喘不上气",
    "急性胃肠炎": "胃肠黏膜急性发炎，常表现为上吐下泻、肚子痛",
    "水痘": "水痘病毒引起的传染病，身上起水疱，需要隔离",
    "流行性腮腺炎": "腮腺炎病毒引起的传染病，脸颊两侧肿痛，需要隔离",
    "细菌性痢疾": "痢疾杆菌引起的肠道传染病，表现为发热、腹痛、里急后重",
    "急性支气管炎": "支气管黏膜急性发炎，主要表现为咳嗽",
    "慢性胃炎": "胃黏膜长期反复发炎，常表现为上腹不适、饱胀",
    "原发性高血压2级": "血压持续偏高，属于中等程度，需要长期控制",
    "腰椎间盘突出症": "腰椎之间的“垫子”突出来压到神经，可引起腰痛腿麻",
    "2型糖尿病": "身体对胰岛素的利用变差，血糖长期偏高",
    "过敏性皮炎": "皮肤接触过敏原后出现的炎症，常伴瘙痒",
    "冠心病稳定型心绞痛": "给心脏供血的血管变窄，累的时候胸口会闷痛",
    "甲状腺功能亢进症": "甲状腺激素分泌过多，代谢变快，可心慌、多汗、消瘦",
}

# 长名称优先命中，避免诊断里含多个词条时被短的先匹配走
_DIAGNOSIS_KEYS = sorted(DIAGNOSIS_PLAIN, key=len, reverse=True)

# 单次正则扫描完成术语识别：长词在前保证“斑片状磨玻璃密度影”优先于“磨玻璃密度影”
_TERM_PATTERN = re.compile(
    "|".join(re.escape(t) for t in sorted(TERM_DICT, key=len, reverse=True))
)


# --------------------------------------------------------------------------- #
# 可插拔的病历解释 Agent
# --------------------------------------------------------------------------- #

# Agent 约定：接收 (record, text, session_id) 三个关键字参数，返回
#   (通俗化解读文本, 引用来源列表)                       —— 术语对照沿用本地词典
#   (通俗化解读文本, 引用来源列表, 术语对照列表)          —— 术语对照以 Agent 为准
# 术语对照列表元素为 (术语, 通俗解释) 二元组或 TermMapping。真实实现由 AI 模块提供。
InterpretAgent = Callable[..., Awaitable[tuple]]

_interpret_agent: Optional[InterpretAgent] = None


def register_interpret_agent(agent: InterpretAgent) -> None:
    """注册真实的病历解释 Agent（AI 模块就绪后在启动阶段调用一次即可）。"""
    global _interpret_agent
    _interpret_agent = agent


async def _run_agent(
    agent: InterpretAgent,
    *,
    record: Optional[MedicalRecord],
    text: Optional[str],
    session_id: Optional[str],
) -> tuple[str, list[str], Optional[list[tuple[str, str]]]]:
    """调用 Agent 并归一化其返回值，兼容二/三元组两种实现。"""
    produced = await agent(record=record, text=text, session_id=session_id)
    interpretation = produced[0]
    sources = list(produced[1] or [])
    if len(produced) < 3 or not produced[2]:
        return interpretation, sources, None

    mappings: list[tuple[str, str]] = []
    for entry in produced[2]:
        if isinstance(entry, TermMapping):
            mappings.append((entry.term, entry.plain))
        else:
            term, plain = entry
            mappings.append((term, plain))
    return interpretation, sources, mappings


def _load_default_agent() -> Optional[InterpretAgent]:
    """惰性探测 app.services.rag.agents.record_agent.interpret。

    惰性而不是模块级导入：Agent 那条链拖着可选依赖（见 requirements-ai.txt），
    缺依赖时本模块其余接口仍要能用。探测不到就返回 None 走词典兜底。

    这里刻意宽捕 Exception：Agent 导入期可能因缺模型依赖等原因失败，
    而兜底路径存在的意义正是“AI 没就绪也能出解读”，不应被它带崩。
    """
    try:
        from app.services.rag.agents import record_agent
    except Exception:
        logger.warning("病历解释Agent 加载失败，本次改用术语词典兜底", exc_info=True)
        return None
    agent = getattr(record_agent, "interpret", None)
    return agent if callable(agent) else None


# --------------------------------------------------------------------------- #
# API-22 历史病历查询
# --------------------------------------------------------------------------- #


def list_records(
    db: Session,
    *,
    user_id: str,
    patient_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page_num: int = 1,
    page_size: int = 10,
) -> MedicalRecordPage:
    """查询当前账号（含被授权家属）的历史病历，按就诊日期倒序分页返回。"""
    if patient_id:
        _assert_patient_owned(db, user_id, patient_id)

    conds: list[Any] = [Patient.user_id == user_id]
    if patient_id:
        conds.append(MedicalRecord.patient_id == patient_id)
    if start_date:
        conds.append(MedicalRecord.visit_date >= start_date)
    if end_date:
        conds.append(MedicalRecord.visit_date <= end_date)

    total = db.scalar(
        select(func.count())
        .select_from(MedicalRecord)
        .join(Patient, Patient.patient_id == MedicalRecord.patient_id)
        .where(*conds)
    ) or 0

    rows = db.execute(
        select(MedicalRecord, Patient)
        .join(Patient, Patient.patient_id == MedicalRecord.patient_id)
        .where(*conds)
        .order_by(MedicalRecord.visit_date.desc(), MedicalRecord.record_id.desc())
        .offset((page_num - 1) * page_size)
        .limit(page_size)
    ).all()

    doctors = _name_map(db, Doctor.doctor_id, Doctor.name, {r.doctor_id for r, _ in rows})
    depts = _name_map(
        db, Department.dept_id, Department.dept_name, {r.dept_id for r, _ in rows}
    )
    briefs = _prescription_briefs(db, rows)

    return MedicalRecordPage(
        total=total,
        pageNum=page_num,
        pageSize=page_size,
        list=[
            MedicalRecordBrief(
                recordId=record.record_id,
                patientId=record.patient_id,
                patientName=mask_name(patient.name),
                visitDate=record.visit_date.isoformat(),
                deptName=depts.get(record.dept_id or "", ""),
                doctorName=doctors.get(record.doctor_id or "", ""),
                diagnosis=record.diagnosis or "",
                prescriptionBrief=briefs.get(record.record_id, NO_PRESCRIPTION),
                detailUrl=f"/record/{record.record_id}",
            )
            for record, patient in rows
        ],
    )


def _assert_patient_owned(db: Session, user_id: str, patient_id: str) -> Patient:
    """校验就诊人属于当前账号，否则按接口文档 4003 拒绝。"""
    patient = db.get(Patient, patient_id)
    if patient is None or patient.user_id != user_id:
        raise BizError(ACCESS_DENIED, "无权访问该资源")
    return patient


def _name_map(
    db: Session, id_col: Any, name_col: Any, ids: set[Optional[str]]
) -> dict[str, str]:
    """按主键批量取名称，避免逐条查询。"""
    keys = {i for i in ids if i}
    if not keys:
        return {}
    return dict(db.execute(select(id_col, name_col).where(id_col.in_(keys))).all())


def _prescription_briefs(db: Session, rows: list[Any]) -> dict[str, str]:
    """按病历批量拼处方摘要：先经 appointment_id 关联处方，缺失时回落到就诊人最新处方。"""
    if not rows:
        return {}

    appt_ids = {r.appointment_id for r, _ in rows if r.appointment_id}
    pres_by_appt: dict[str, str] = {}
    pres_ids: list[str] = []

    if appt_ids:
        for pres in db.execute(
            select(Prescription).where(Prescription.appointment_id.in_(appt_ids))
        ).scalars():
            pres_by_appt[pres.appointment_id] = pres.prescription_id
            pres_ids.append(pres.prescription_id)

    # 病历未挂预约号时的回落路径：取该就诊人名下无预约的处方
    orphan_patients = {r.patient_id for r, _ in rows if not r.appointment_id}
    pres_by_patient: dict[str, str] = {}
    if orphan_patients:
        for pres in db.execute(
            select(Prescription)
            .where(
                Prescription.patient_id.in_(orphan_patients),
                Prescription.appointment_id.is_(None),
            )
            .order_by(Prescription.prescription_id.desc())
        ).scalars():
            pres_by_patient.setdefault(pres.patient_id, pres.prescription_id)
            pres_ids.append(pres.prescription_id)

    names = _drug_names_by_prescription(db, set(pres_ids))

    briefs: dict[str, str] = {}
    for record, _patient in rows:
        pres_id = pres_by_appt.get(record.appointment_id) if record.appointment_id else None
        if pres_id is None:
            pres_id = pres_by_patient.get(record.patient_id)
        briefs[record.record_id] = _format_brief(names.get(pres_id or "", []))
    return briefs


def _drug_names_by_prescription(db: Session, pres_ids: set[str]) -> dict[str, list[str]]:
    """按处方批量取药品名称列表（明细表关联药品表）。"""
    if not pres_ids:
        return {}
    result: dict[str, list[str]] = {}
    for pres_id, drug_name in db.execute(
        select(PrescriptionItem.prescription_id, Medication.drug_name)
        .join(Medication, Medication.drug_id == PrescriptionItem.drug_id)
        .where(PrescriptionItem.prescription_id.in_(pres_ids))
        .order_by(PrescriptionItem.item_id)
    ).all():
        result.setdefault(pres_id, []).append(drug_name)
    return result


def _format_brief(drug_names: list[str]) -> str:
    """药单摘要：3 种以内全列，超出则“前3种 等N种”。"""
    if not drug_names:
        return NO_PRESCRIPTION
    if len(drug_names) <= BRIEF_NAME_LIMIT:
        return "、".join(drug_names)
    return "、".join(drug_names[:BRIEF_NAME_LIMIT]) + f" 等{len(drug_names)}种"


# --------------------------------------------------------------------------- #
# API-23 病历AI解读
# --------------------------------------------------------------------------- #


async def interpret(
    db: Session,
    *,
    user_id: str,
    record_id: Optional[str] = None,
    raw_text: Optional[str] = None,
    session_id: Optional[str] = None,
) -> InterpretationResponse:
    """把病历内容解读成大白话。recordId 与 rawText 二选一。"""
    if not record_id and not raw_text:
        raise BizError(PARAM_INVALID, "recordId 与 rawText 必须提供其一")

    record: Optional[MedicalRecord] = None
    if record_id:
        record = db.get(MedicalRecord, record_id)
        if record is None:
            raise BizError(PARAM_INVALID, "病历不存在或已被删除")
        # 敏感数据：仅本人及同账号下被授权的家属可访问
        _assert_patient_owned(db, user_id, record.patient_id)

    text = raw_text or (record.raw_text if record else None) or _structured_text(record)
    mappings = _match_terms(text)

    agent = _interpret_agent or _load_default_agent()
    interpretation: Optional[str] = None
    sources: list[str] = []
    if agent is not None:
        try:
            interpretation, sources, agent_mappings = await _run_agent(
                agent, record=record, text=text, session_id=session_id
            )
        except Exception:  # noqa: BLE001 - 大模型/检索链出问题也要出解读，回落到词典
            logger.warning("病历解释 Agent 调用失败，本次改用术语词典兜底", exc_info=True)
            interpretation = None
        else:
            # Agent 未给出术语对照时（如只返回二元组），沿用本地词典的识别结果
            mappings = agent_mappings or mappings

    if not (interpretation or "").strip():
        # Agent 不可用（未配 LLM_API_KEY、检索链未就绪、AI 依赖没装）或返回了空文本。
        # 契约上「解读」不能为空，退回本地词典：宁可话糙，也不能回一屏空白。
        dept_name, doctor_name = _visit_context(db, record)
        interpretation = _rule_based(record, text, mappings, dept_name, doctor_name)
        sources = list(RULE_BASED_SOURCES)

    follow_up = f"{FOLLOW_UP_URL}?sessionId={session_id}" if session_id else FOLLOW_UP_URL
    return InterpretationResponse(
        interpretation=interpretation,
        termMapping=[TermMapping(term=term, plain=plain) for term, plain in mappings],
        followUpUrl=follow_up,
        sources=sources,
        disclaimer=DISCLAIMER,
    )


def _structured_text(record: Optional[MedicalRecord]) -> str:
    """病历无原文时，用结构化字段拼出可解读文本。"""
    if record is None:
        return ""
    lines = []
    if record.chief_complaint:
        lines.append(f"主诉：{record.chief_complaint}")
    if record.diagnosis:
        lines.append(f"诊断：{record.diagnosis}")
    if record.treatment_advice:
        lines.append(f"处理意见：{record.treatment_advice}")
    return "\n".join(lines)


def _visit_context(
    db: Session, record: Optional[MedicalRecord]
) -> tuple[Optional[str], Optional[str]]:
    """取本次就诊的科室名与医生名，用于解读开头的就诊概况。"""
    if record is None:
        return None, None
    dept_name = (
        db.scalar(select(Department.dept_name).where(Department.dept_id == record.dept_id))
        if record.dept_id
        else None
    )
    doctor_name = (
        db.scalar(select(Doctor.name).where(Doctor.doctor_id == record.doctor_id))
        if record.doctor_id
        else None
    )
    return dept_name, doctor_name


def _match_terms(text: Optional[str]) -> list[tuple[str, str]]:
    """识别文本中命中的术语，按在原文中出现的先后去重返回。"""
    if not text:
        return []
    hits: dict[str, int] = {}
    for match in _TERM_PATTERN.finditer(text):
        hits.setdefault(match.group(0), match.start())
    return [(term, TERM_DICT[term]) for term, _ in sorted(hits.items(), key=lambda kv: kv[1])]


def _plain_text(text: Optional[str]) -> str:
    """把文本里的术语就地替换为“术语（通俗解释）”，单次扫描避免嵌套替换。"""
    if not text:
        return text or ""
    return _TERM_PATTERN.sub(lambda m: f"{m.group(0)}（{TERM_DICT[m.group(0)]}）", text)


def _diagnosis_plain(diagnosis: Optional[str]) -> str:
    """按最长匹配找诊断的通俗解释，未收录则返回空串。"""
    if not diagnosis:
        return ""
    for key in _DIAGNOSIS_KEYS:
        if key in diagnosis:
            return DIAGNOSIS_PLAIN[key]
    return ""


def _rule_based(
    record: Optional[MedicalRecord],
    text: Optional[str],
    mappings: list[tuple[str, str]],
    dept_name: Optional[str],
    doctor_name: Optional[str],
) -> str:
    """无大模型时，用术语词典 + 结构化字段生成通俗化解读。"""
    sections: list[str] = []

    if record is not None:
        who = f"{dept_name or '本院门诊'}就诊"
        if doctor_name:
            who += f"，接诊医生是{doctor_name}医生"
        overview = [f"{record.visit_date.isoformat()} 你到{who}。"]
        if record.chief_complaint:
            overview.append(f"你当时的主要不适是：{record.chief_complaint}。")
        sections.append("【这次就诊的情况】\n" + "".join(overview))

    if record is not None and record.diagnosis:
        diag = [f"医生的诊断是「{record.diagnosis}」。"]
        plain = _diagnosis_plain(record.diagnosis)
        if plain:
            diag.append(f"通俗说就是：{plain}。")
        else:
            diag.append("这个诊断名称是医学专科表述，可参考下方「术语对照」里的相关词条。")
        sections.append("【医生是怎么判断的】\n" + "".join(diag))

    if record is not None and record.treatment_advice:
        advice = [f"医生给出的处理意见是：{record.treatment_advice}。"]
        plain_advice = _plain_text(record.treatment_advice)
        if plain_advice != record.treatment_advice:
            advice.append(f"换成大白话：{plain_advice}。")
        sections.append("【接下来该怎么做】\n" + "".join(advice))

    if mappings:
        listed = mappings[:TERM_LIST_LIMIT]
        bullets = "\n".join(f"· {term}：{plain}" for term, plain in listed)
        more = f"\n（另有 {len(mappings) - len(listed)} 条术语未列出）" if len(mappings) > len(listed) else ""
        sections.append(f"【记录里出现的医学说法】\n{bullets}{more}")
    elif text:
        sections.append("【记录里出现的医学说法】\n本次记录中没有识别到需要特别解释的医学名词。")

    sections.append(
        "【温馨提示】\n"
        "· 这份解读只是把病历里的专业说法翻译成大白话，帮你读懂医生的记录，不是诊断结论。\n"
        "· 用药、停药和复诊安排，请以医生当面交代的为准；出现新的不适请及时回医院。\n"
        "· 对诊断或治疗有疑问，最直接的办法是复诊时问主诊医生，也可以通过下方入口继续追问。"
    )
    return "\n\n".join(sections)
