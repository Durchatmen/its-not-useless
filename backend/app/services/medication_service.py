"""用药提醒业务逻辑（接口文档 API-30 本次药单查询、API-31 用药提醒生成）。

这是「用药 Agent」的确定性内核，链路是：

    药单读取 -> 频次/餐次解析 -> 服药计划展开 -> 冲突筛查 -> 落库 -> 日历导出

大模型与知识库检索只做**复述与提示**，不参与剂量与频次的决策。需求分析 §10.1 写得很死：

    用药建议：仅复述处方，不新增、不调整剂量

所以剂量、频次、疗程一律只从 t_prescription_item 读；任何 AI 产出都只能进 remark 文案，
且产出里出现「加量/减量/停药」这类措辞时会被 _looks_like_dosage_change() 拦下、回落模板。

AI 钩子（检索链与大模型都还没实现，缺失时降级而不是报错）：

    set_retriever() / set_llm()    注入真实实现
    _get_retriever() / _get_llm()  先看注入值，再懒加载 app.services.rag.retriever
                                   与 app.services.llm。这两个模块目前是 0 字节空桩，
                                   导入必然抛 ImportError，捕获后返回 None，
                                   主流程照常走本地规则表与模板文案。

落库形态与表设计对齐：t_medication_reminder 按「每个药品 × 每一天 × 每个服药时间点」
一行存储（索引 idx_reminder_patient_date 即 (patient_id, plan_date)），所以 API-31 里那个
单个 reminderId 只是**代表编号**，全量编号见 ReminderPlan.reminder_ids。
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    Department,
    Doctor,
    Medication,
    MedicationReminder,
    Patient,
    Prescription,
    PrescriptionItem,
)
from app.services.insurance_service import classify_drug

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

DISCLAIMER = "用药提醒仅复述处方信息，不构成用药建议，请严格遵医嘱"

TAKEN_NO = 0
TAKEN_YES = 1
"""t_medication_reminder.taken_status 的取值，见该模型 comment。"""

TZID = "Asia/Shanghai"
CALENDAR_EVENT_MINUTES = 15
"""日历事件默认时长（分钟）。"""

CALENDAR_ALARM_MINUTES = 10
"""日历提醒默认提前量（分钟）。"""

DEFAULT_TAKE_TIME = "08:00"
"""频次识别不出来时的兜底时间点。"""

DEFAULT_COURSE_DAYS = 1
"""days 为空时的疗程兜底。"""

DAY_TIME_START = "08:00"
DAY_TIME_END = "20:00"
"""未知每日次数时，服药时间点均匀分布在这个区间的两端之间。"""

MAX_REMINDER_ROWS = 500
"""单张处方的落库上限。药单大时按此截断并告警，避免一次写出上千行。"""

MAX_REMARK_LENGTH = 120

FREQUENCY_SCHEDULE: dict[str, tuple[str, ...]] = {
    "每日1次": ("08:00",),
    "每日2次": ("08:00", "18:30"),
    "每日3次": ("08:00", "12:30", "18:30"),
    "每日4次": ("08:00", "12:00", "16:00", "20:00"),
    "每6小时1次": ("00:00", "06:00", "12:00", "18:00"),
    "每8小时1次": ("06:00", "14:00", "22:00"),
    "每12小时1次": ("08:00", "20:00"),
    "每晚1次": ("20:00",),
    "睡前": ("21:30",),
    "晨起空腹": ("07:00",),
}
"""频次 -> 每日服药时间点。

时间点贴合三餐作息（08:00 / 12:30 / 18:30），便于与 MEAL_OFFSET_MINUTES 叠加成
「饭后 08:30」这种带餐次含义的提醒。表里没收录的每日次数由 _evenly_spaced_times()
在 08:00–20:00 之间均匀铺开，而不是把剂量丢掉只提醒一次。
"""

MEAL_OFFSET_MINUTES: dict[str, int] = {
    "餐前": -30,
    "饭前": -30,
    "空腹": -60,
    "餐中": 0,
    "随餐": 0,
    "餐后": 30,
    "饭后": 30,
    "不限": 0,
}
"""与餐关系 -> 相对基准时间点的偏移（分钟）。

基准点当作三餐开饭时间，饭后要晚半小时、餐前要早半小时，于是提醒才会落在
「饭后 08:30」这种真实服药点上。
"""

_CN_DIGITS: dict[str, str] = {
    "一": "1",
    "两": "2",
    "二": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
    "十": "10",
}

_DAILY_COUNT_RE = re.compile(r"每日(\d+)次")
_HOURLY_RE = re.compile(r"每(\d+)小时1次")
_HHMM_RE = re.compile(r"(\d{1,2}):(\d{2})")

# --------------------------------------------------------------------------- #
# 药物相互作用规则
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class InteractionRule:
    """一条用药风险规则，命中方式有两种。

    配对式（group_b 非空）：group_a 与 group_b 各命中一个**不同**药品。
    单药式（group_b 为空）：group_a 命中任一药品，且处方里还有其他药（存在同服冲突）。

    group_a 与 group_b 给同一组关键词时即为「同类药叠加」，配对式天然只认不同药品。
    """

    group_a: tuple[str, ...]
    group_b: tuple[str, ...]
    warning: str
    """命中的提示文案，写进 t_medication_reminder.conflict_warning。"""


INTERACTION_RULES: tuple[InteractionRule, ...] = (
    InteractionRule(
        group_a=("阿司匹林", "氯吡格雷", "华法林", "利伐沙班", "达比加群", "替格瑞洛"),
        group_b=(
            "阿司匹林", "氯吡格雷", "华法林", "利伐沙班", "达比加群", "替格瑞洛",
            "复方丹参", "血府逐瘀", "麝香保心丸", "丹参", "银杏", "三七",
        ),
        warning="抗凝/抗血小板作用叠加，出血风险升高，请告知医生正在服用的全部药物",
    ),
    InteractionRule(
        group_a=("头孢", "阿莫西林", "青霉素", "左氧氟沙星", "阿奇霉素", "甲硝唑", "克拉霉素"),
        group_b=("双歧杆菌", "活菌", "益生菌", "乳酸菌", "整肠生"),
        warning="抗菌药物会抑制或灭活活菌制剂，两药需间隔 2 小时以上服用",
    ),
    InteractionRule(
        group_a=("对乙酰氨基酚", "扑热息痛", "氨酚"),
        group_b=("复方感冒", "感冒灵", "复方氨酚", "氨酚黄那敏", "感冒清热"),
        warning="复方感冒药常含对乙酰氨基酚，叠加服用易致肝损伤，请核对成分后避免同服",
    ),
    InteractionRule(
        group_a=("布洛芬", "萘普生", "双氯芬酸", "洛索洛芬", "塞来昔布", "尼美舒利", "吲哚美辛"),
        group_b=("布洛芬", "萘普生", "双氯芬酸", "洛索洛芬", "塞来昔布", "尼美舒利", "吲哚美辛"),
        warning="两种及以上解热镇痛药联用会明显增加胃肠道出血与肾损伤风险，请遵医嘱",
    ),
    InteractionRule(
        group_a=("蒙脱石",),
        group_b=(),
        warning="蒙脱石散会吸附同服药物，需与其他口服药间隔 1 小时以上",
    ),
    InteractionRule(
        group_a=("铝碳酸镁",),
        group_b=(),
        warning="铝碳酸镁会与多种药物结合影响吸收，需与其他药物间隔 1–2 小时",
    ),
)
"""规则内容取自 docs/药品知识库 的「药物相互作用」条目，先覆盖种子数据会命中的几组。"""

_ALLERGY_SPLIT_RE = re.compile(r"[、,，;；/\\|\s]+")
_ALLERGY_STOPWORDS = frozenset({"无", "否", "没有", "不详", "未发现", "否认", "无明显", "-", "／"})
"""过敏史里的「无 / 否认」这类否定词，不参与匹配。"""

_DOSAGE_CHANGE_RE = re.compile(
    # 剂量加减：「加/减/增」后面跟量、至、为、到、半、倍，或直接「加一片」的加服
    r"加量|减量|加倍|减半|加至|增至|加为|加到|减至|减为|减到|加服|减服"
    # 停药换药
    r"|停药|停服|停用|改用|改服|改吃|替换|替代"
    # 改动措辞：只说「改用/改用」不够，「改为 / 换成 / 调为」同样是在改处方
    r"|改为|改成|换为|换成|换服|换吃|调为|调至|调到|调整为"
    # 把决定权交回患者的说法，等于默许自行改药
    r"|自行调整|自行增减|自行减量|酌情增减"
)
"""大模型复述里一旦出现这些词，说明它越界给了用药建议，文案直接作废。

覆盖三类越界：改剂量（加量/减半/加至）、停药换药（停用/换成）、改服药安排
（改为饭后服用）。第三类实测漏过 —— 它不改剂量但改了医嘱，同样不能由 AI 说出口。
"""

# --------------------------------------------------------------------------- #
# AI 钩子
# --------------------------------------------------------------------------- #

RetrieverFn = Callable[[str, int], Sequence[Mapping[str, Any]]]
"""知识库检索： (query, top_k) -> 命中片段，每项至少含 text。"""

LlmFn = Callable[[str, str], str]
"""大模型调用： (system_prompt, user_prompt) -> 回复文本。"""

_retriever: RetrieverFn | None = None
_llm: LlmFn | None = None

_REMARK_SYSTEM_PROMPT = (
    "你是医院智能就医系统的用药提醒助手。只允许把医生已经开好的用法用量复述成一句通俗中文提醒，"
    "不超过 60 字。严禁给出任何调整建议：不得建议加量、减量、停药、换药或改变服药时间。"
    "只输出这一句话，不要解释、不要前后缀。"
)


def set_retriever(fn: RetrieverFn | None) -> None:
    """注入药品知识库检索实现；传 None 则恢复成「懒加载 retriever 模块」。"""
    global _retriever
    _retriever = fn


def set_llm(fn: LlmFn | None) -> None:
    """注入大模型实现；传 None 则恢复成「懒加载 llm 模块」。"""
    global _llm
    _llm = fn


def _get_retriever() -> RetrieverFn | None:
    """取检索实现：先看注入值，再试 app.services.rag.retriever（当前是空桩）。"""
    global _retriever
    if _retriever is not None:
        return _retriever
    try:
        from app.services.rag.retriever import search
    except ImportError:
        logger.debug("app.services.rag.retriever 尚未实现，用药冲突提示仅用本地规则")
        return None
    _retriever = search
    return _retriever


def _get_llm() -> LlmFn | None:
    """取大模型实现：先看注入值，再试 app.services.llm（当前是空桩）。"""
    global _llm
    if _llm is not None:
        return _llm
    try:
        from app.services.llm import chat
    except ImportError:
        logger.debug("app.services.llm 尚未实现，用药提醒文案改用模板复述")
        return None
    _llm = chat
    return _llm


def _ask_llm(system: str, user: str) -> str | None:
    """调大模型；未配置或调用失败都返回 None，由调用方决定怎么降级。"""
    provider = _get_llm()
    if provider is None:
        return None
    try:
        reply = provider(system, user)
    except Exception as exc:  # noqa: BLE001 - 大模型失败不该让用药提醒整体不可用
        logger.warning("用药提醒文案生成失败，回落到模板复述: %s", exc)
        return None
    text = (reply or "").strip()
    return text or None


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #


@dataclass
class DrugLine:
    """药单里的一行药品。"""

    drug_id: str
    drug_name: str
    specification: str | None
    dosage: str | None
    frequency: str | None
    usage: str | None
    meal_relation: str | None
    """餐前 / 餐中 / 饭后。与 usage 是两个维度：usage 说的是给药途径（口服/外用），
    这里说的是与进餐的先后。接口文档把 API-30 的 usage 举例成「饭后服用」，
    所以路由层拼响应时要把这两个字段一起放进去，否则医嘱里的餐次要求就丢了。
    """
    days: int | None
    quantity: int
    subtotal: Decimal
    insurance_type: str
    insurance_label: str
    """中文口径：甲类 / 乙类 / 自费，来自 insurance_service.classify_drug。"""

    instructions: str | None
    contraindication: str | None


@dataclass
class CurrentPrescription:
    """API-30 的响应体（不含信封，信封由路由层拼）。"""

    prescription_id: str
    patient_id: str
    visit_date: date | None
    dept_name: str | None
    doctor_name: str | None
    total_amount: Decimal
    insurance_cover: Decimal
    self_pay: Decimal
    drugs: list[DrugLine] = field(default_factory=list)


@dataclass
class DrugPlan:
    """一个药品的每日服药安排，是「每日模板」，尚未按天展开。"""

    drug_id: str
    drug_name: str
    dose: str | None
    """单次剂量，原样取自 t_prescription_item.dosage。
    周知 §10.1「不新增、不调整剂量」，所以这里只是搬运，任何环节都不许改写它。
    """
    times: tuple[str, ...]
    meal_relation: str | None
    days: int
    recognized: bool
    """频次是否被识别。False 表示 times 只含兜底时间点。"""

    remark: str


@dataclass
class PlanItem:
    """API-31 的 planItems 元素，与接口文档字段一一对应（注意没有日期字段）。"""

    drug_id: str
    drug_name: str
    dose: str | None
    time: str
    meal_relation: str | None
    remark: str


@dataclass
class ReminderPlan:
    """API-31 的响应体。"""

    prescription_id: str
    reminder_id: str | None
    """代表编号：整张计划写入的第一条提醒行。

    t_medication_reminder 按「每药每天每时间点一行」设计，没有计划级主键，
    所以这里只是个代表，全量编号在 reminder_ids 里。调用方别拿它当一行用。
    """

    reminder_ids: list[str] = field(default_factory=list)
    plan_items: list[PlanItem] = field(default_factory=list)
    """每日服药计划；按天展开的完整明细在 reminder_ids 与日历导出里。"""

    conflict_warning: str | None = None
    calendar_export_url: str = ""
    disclaimer: str = DISCLAIMER
    unresolved: list[str] = field(default_factory=list)
    """频次未能识别、只能用兜底时间点的药品名。"""

    row_count: int = 0
    """实际写入 t_medication_reminder 的行数。"""


@dataclass
class ReminderItem:
    """一条提醒记录，已 join 上药品信息。"""

    reminder_id: str
    prescription_id: str
    patient_id: str
    plan_date: date
    take_time: str
    meal_relation: str | None
    dose: str | None
    taken_status: int
    taken: bool
    conflict_warning: str | None
    drug_id: str
    drug_name: str
    specification: str | None
    usage_instruction: str | None
    contraindication: str | None
    insurance_type: str
    insurance_label: str


@dataclass
class AdherenceSummary:
    """一段区间内的服药依从性。"""

    patient_id: str
    start_date: date
    end_date: date
    total: int
    taken: int
    pending: int
    rate: float
    """已服比例，0.0–1.0；无提醒记录时为 0.0。"""


# --------------------------------------------------------------------------- #
# 药单查询
# --------------------------------------------------------------------------- #


def get_current_prescription(
    session: Session,
    *,
    patient_id: str | None = None,
    user_id: str | None = None,
) -> CurrentPrescription | None:
    """API-30 本次药单查询。

    patient_id 省略时按「默认本人」取该账号的默认就诊人。该就诊人没有任何处方时
    返回 None —— 这是正常业务状态，不是异常。
    """
    if patient_id is None:
        if user_id is None:
            raise ValueError("patient_id 与 user_id 至少需要一个")
        patient_id = _default_patient_id(session, user_id)
        if patient_id is None:
            logger.info("账号 %s 下没有就诊人，无药单可查", user_id)
            return None

    prescription = _latest_prescription(session, patient_id)
    if prescription is None:
        logger.info("就诊人 %s 没有处方记录", patient_id)
        return None

    drugs: list[DrugLine] = []
    for item, medication in _prescription_rows(session, prescription.prescription_id):
        entry = classify_drug(medication)
        drugs.append(
            DrugLine(
                drug_id=medication.drug_id,
                drug_name=medication.drug_name,
                specification=medication.specification,
                dosage=item.dosage,
                frequency=item.frequency,
                usage=item.usage_method,
                meal_relation=item.meal_relation,
                days=item.days,
                quantity=item.quantity,
                subtotal=item.subtotal,
                insurance_type=entry.insurance_type,
                insurance_label=entry.category_label,
                instructions=medication.usage_instruction,
                contraindication=medication.contraindication,
            )
        )

    visit_date, dept_name, doctor_name = _visit_context(session, prescription)
    return CurrentPrescription(
        prescription_id=prescription.prescription_id,
        patient_id=prescription.patient_id,
        visit_date=visit_date,
        dept_name=dept_name,
        doctor_name=doctor_name,
        total_amount=prescription.total_amount,
        insurance_cover=prescription.insurance_cover,
        self_pay=prescription.self_pay,
        drugs=drugs,
    )


# --------------------------------------------------------------------------- #
# 提醒生成与查询
# --------------------------------------------------------------------------- #


def generate_reminders(
    session: Session,
    *,
    prescription_id: str,
    patient_id: str | None = None,
    start_date: date | None = None,
) -> ReminderPlan:
    """API-31 用药提醒生成。

    按处方明细的「频次 × 疗程天数」展开成逐条的服药提醒并落库。重复调用是幂等的：
    先删该处方的旧提醒行再写新的，所以重跑不会叠加。

    patient_id 给出时会校验处方归属，防止越权查看他人处方。
    """
    prescription = session.get(Prescription, prescription_id)
    if prescription is None:
        raise LookupError(f"处方不存在: {prescription_id}")
    if patient_id and prescription.patient_id != patient_id:
        raise PermissionError(f"处方 {prescription_id} 不属于就诊人 {patient_id}")

    patient = session.get(Patient, prescription.patient_id)
    first_day = start_date or date.today()
    export_url = _calendar_export_url(prescription.patient_id)

    items = (
        session.execute(
            select(PrescriptionItem)
            .where(PrescriptionItem.prescription_id == prescription_id)
            .order_by(PrescriptionItem.item_id)
        )
        .scalars()
        .all()
    )
    if not items:
        logger.warning("处方 %s 没有明细，清空旧提醒后返回空计划", prescription_id)
        _clear_reminders(session, prescription_id)
        session.commit()
        return ReminderPlan(prescription_id=prescription_id, reminder_id=None, calendar_export_url=export_url)

    drugs = _load_drugs(session, [item.drug_id for item in items])
    plans, unresolved = _build_drug_plans(items, drugs)

    # 提示是处方级的：冲突发生在药品之间，而 conflict_warning 是行级列，故整段写入每行。
    warnings = _screen_conflicts(
        list(drugs.values()),
        allergy_history=patient.allergy_history if patient else None,
    )
    conflict_warning = _join_warnings(warnings)

    rows = _materialize_rows(
        plans,
        prescription_id=prescription_id,
        patient_id=prescription.patient_id,
        first_day=first_day,
        conflict_warning=conflict_warning,
    )

    _clear_reminders(session, prescription_id)
    session.add_all(rows)
    session.commit()

    logger.info(
        "处方 %s 生成用药提醒 %d 行（药品 %d 种，起始 %s）",
        prescription_id,
        len(rows),
        len(plans),
        first_day,
    )
    return ReminderPlan(
        prescription_id=prescription_id,
        reminder_id=rows[0].reminder_id if rows else None,
        reminder_ids=[row.reminder_id for row in rows],
        plan_items=_to_plan_items(plans),
        conflict_warning=conflict_warning,
        calendar_export_url=export_url,
        unresolved=unresolved,
        row_count=len(rows),
    )


def list_reminders(
    session: Session,
    *,
    patient_id: str,
    plan_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    only_pending: bool = False,
) -> list[ReminderItem]:
    """查某个就诊人的服药提醒。

    plan_date 给定时只查当天（走 idx_reminder_patient_date 索引）；否则用
    start_date / end_date 圈一个区间，两者都可省略表示不设边界。
    """
    stmt = (
        select(MedicationReminder, Medication)
        .join(Medication, Medication.drug_id == MedicationReminder.drug_id)
        .where(MedicationReminder.patient_id == patient_id)
    )
    if plan_date is not None:
        stmt = stmt.where(MedicationReminder.plan_date == plan_date)
    else:
        if start_date is not None:
            stmt = stmt.where(MedicationReminder.plan_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(MedicationReminder.plan_date <= end_date)
    if only_pending:
        stmt = stmt.where(MedicationReminder.taken_status == TAKEN_NO)

    stmt = stmt.order_by(
        MedicationReminder.plan_date,
        MedicationReminder.take_time,
        MedicationReminder.drug_id,
    )

    items: list[ReminderItem] = []
    for reminder, medication in session.execute(stmt).all():
        entry = classify_drug(medication)
        items.append(
            ReminderItem(
                reminder_id=reminder.reminder_id,
                prescription_id=reminder.prescription_id,
                patient_id=reminder.patient_id,
                plan_date=reminder.plan_date,
                take_time=reminder.take_time,
                meal_relation=reminder.meal_relation,
                dose=reminder.dose,
                taken_status=reminder.taken_status,
                taken=reminder.taken_status == TAKEN_YES,
                conflict_warning=reminder.conflict_warning,
                drug_id=medication.drug_id,
                drug_name=medication.drug_name,
                specification=medication.specification,
                usage_instruction=medication.usage_instruction,
                contraindication=medication.contraindication,
                insurance_type=entry.insurance_type,
                insurance_label=entry.category_label,
            )
        )
    return items


def mark_taken(session: Session, *, reminder_id: str, taken: bool = True) -> bool:
    """标记某条提醒已服 / 未服，返回是否命中记录。"""
    reminder = session.get(MedicationReminder, reminder_id)
    if reminder is None:
        logger.info("提醒不存在，无法标记: %s", reminder_id)
        return False
    reminder.taken_status = TAKEN_YES if taken else TAKEN_NO
    session.commit()
    return True


def summarize_adherence(
    session: Session,
    *,
    patient_id: str,
    start_date: date,
    end_date: date,
) -> AdherenceSummary:
    """统计一段区间内的服药依从性，纯聚合。"""
    rows = session.execute(
        select(MedicationReminder.taken_status, func.count())
        .where(
            MedicationReminder.patient_id == patient_id,
            MedicationReminder.plan_date >= start_date,
            MedicationReminder.plan_date <= end_date,
        )
        .group_by(MedicationReminder.taken_status)
    ).all()

    counts = {int(status): int(count) for status, count in rows}
    taken = counts.get(TAKEN_YES, 0)
    total = sum(counts.values())
    return AdherenceSummary(
        patient_id=patient_id,
        start_date=start_date,
        end_date=end_date,
        total=total,
        taken=taken,
        pending=total - taken,
        rate=round(taken / total, 4) if total else 0.0,
    )


# --------------------------------------------------------------------------- #
# 日历导出
# --------------------------------------------------------------------------- #


def build_calendar(
    session: Session,
    *,
    patient_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> str:
    """生成 RFC 5545 的 ics 文本，支撑 API-31 的 calendarExportUrl。

    只产出内容，不拼主机名与鉴权 —— 完整 URL 由路由层给。
    """
    reminders = list_reminders(session, patient_id=patient_id, start_date=start_date, end_date=end_date)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//hospital-ai//medication-reminder//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape('用药提醒')}",
        f"X-WR-TIMEZONE:{TZID}",
    ]
    for reminder in reminders:
        lines.extend(_calendar_event(reminder, stamp=stamp))
    lines.append("END:VCALENDAR")

    folded: list[str] = []
    for line in lines:
        folded.extend(_fold_line(line))
    logger.debug("导出日历：%d 条提醒，%d 行 ics", len(reminders), len(folded))
    return "\r\n".join(folded) + "\r\n"


# --------------------------------------------------------------------------- #
# 计划展开
# --------------------------------------------------------------------------- #


def _build_drug_plans(
    items: Sequence[PrescriptionItem],
    drugs: Mapping[str, Medication],
) -> tuple[list[DrugPlan], list[str]]:
    """把处方明细摊成「每药每日服药安排」，同时收集频次未能识别的药品名。"""
    plans: list[DrugPlan] = []
    unresolved: list[str] = []

    for item in items:
        drug = drugs.get(item.drug_id)
        if drug is None:
            logger.warning("处方明细 %s 引用的药品不存在: %s", item.item_id, item.drug_id)
            continue

        times, recognized = _resolve_take_times(item.frequency)
        offset = MEAL_OFFSET_MINUTES.get((item.meal_relation or "").strip(), 0)
        shifted = tuple(_shift_time(t, offset) for t in times)
        days = max(item.days or DEFAULT_COURSE_DAYS, 1)

        if not recognized:
            unresolved.append(drug.drug_name)
            logger.info(
                "药品 %s 的频次无法识别（%r），改用兜底时间点 %s",
                drug.drug_name,
                item.frequency,
                DEFAULT_TAKE_TIME,
            )

        plans.append(
            DrugPlan(
                drug_id=drug.drug_id,
                drug_name=drug.drug_name,
                dose=item.dosage,
                times=shifted,
                meal_relation=item.meal_relation,
                days=days,
                recognized=recognized,
                remark=_compose_remark(item, drug, frequency_recognized=recognized),
            )
        )
    return plans, unresolved


def _resolve_take_times(frequency: str | None) -> tuple[tuple[str, ...], bool]:
    """频次 -> 每日服药时间点；第二个返回值表示频次是否被识别。"""
    key = _normalize_frequency(frequency)
    if key is None:
        return (DEFAULT_TAKE_TIME,), False
    if key in FREQUENCY_SCHEDULE:
        return FREQUENCY_SCHEDULE[key], True

    match = _DAILY_COUNT_RE.fullmatch(key)
    if match:
        return _evenly_spaced_times(int(match.group(1))), True

    match = _HOURLY_RE.fullmatch(key)
    if match:
        hours = int(match.group(1))
        if 1 <= hours <= 24:
            return _hourly_times(hours), True

    return (DEFAULT_TAKE_TIME,), False


def _normalize_frequency(frequency: str | None) -> str | None:
    """把五花八门的频次写法归一成 FREQUENCY_SCHEDULE 的键口径。

    种子里出现过「每日三次」「每日两次」「每日一次」「每6小时一次」，实际医嘱还可能写成
    「每天3次」「一日三次」「每晚一次」。统一折成阿拉伯数字 + 「次」之后再查表，
    查不到再由 _resolve_take_times 兜底。
    """
    if not frequency:
        return None
    text = frequency.strip().replace(" ", "")
    if not text:
        return None

    for alias, canonical in (("每天", "每日"), ("一日", "每日"), ("每曰", "每日")):
        text = text.replace(alias, canonical)
    for cn, digit in _CN_DIGITS.items():
        text = text.replace(cn, digit)
    text = text.replace("一次", "1次").replace("一回", "1次")

    if text in FREQUENCY_SCHEDULE:
        return text
    if _DAILY_COUNT_RE.fullmatch(text) or _HOURLY_RE.fullmatch(text):
        return text
    if "睡前" in text:
        return "睡前"
    if "每晚" in text:
        return "每晚1次"
    if "空腹" in text or "晨起" in text:
        return "晨起空腹"
    return None


def _evenly_spaced_times(count: int) -> tuple[str, ...]:
    """把 count 次服药均匀排在 08:00–20:00 之间。"""
    if count <= 0:
        return ()
    if count == 1:
        return (DAY_TIME_START,)

    start = _parse_hhmm(DAY_TIME_START)
    end = _parse_hhmm(DAY_TIME_END)
    step = (end - start) / (count - 1)
    return tuple(_format_hhmm(round(start + step * index)) for index in range(count))


def _hourly_times(hours: int) -> tuple[str, ...]:
    """每 N 小时一次 -> 一天内均分的时间点（从 00:00 起算）。"""
    count = max(1, 24 // hours)
    return tuple(_format_hhmm(index * hours * 60) for index in range(count))


def _materialize_rows(
    plans: Sequence[DrugPlan],
    *,
    prescription_id: str,
    patient_id: str,
    first_day: date,
    conflict_warning: str | None,
) -> list[MedicationReminder]:
    """把每日安排按疗程天数展开成逐条提醒行，超上限即截断。"""
    planned_total = sum(plan.days * len(plan.times) for plan in plans)
    if planned_total > MAX_REMINDER_ROWS:
        logger.warning(
            "处方 %s 需写 %d 行提醒，超过上限 %d，已截断",
            prescription_id,
            planned_total,
            MAX_REMINDER_ROWS,
        )

    rows: list[MedicationReminder] = []
    for plan in plans:
        for day_offset in range(plan.days):
            plan_date = first_day + timedelta(days=day_offset)
            for take_time in plan.times:
                if len(rows) >= MAX_REMINDER_ROWS:
                    return rows
                rows.append(
                    MedicationReminder(
                        reminder_id=_new_id("REM"),
                        prescription_id=prescription_id,
                        patient_id=patient_id,
                        drug_id=plan.drug_id,
                        dose=plan.dose,
                        take_time=take_time,
                        meal_relation=plan.meal_relation,
                        plan_date=plan_date,
                        taken_status=TAKEN_NO,
                        conflict_warning=conflict_warning,
                    )
                )
    return rows


def _to_plan_items(plans: Sequence[DrugPlan]) -> list[PlanItem]:
    """每日安排展开成 API-31 的 planItems（每药每时间点一条，不含日期）。"""
    items: list[PlanItem] = []
    for plan in plans:
        for take_time in plan.times:
            items.append(
                PlanItem(
                    drug_id=plan.drug_id,
                    drug_name=plan.drug_name,
                    dose=plan.dose,
                    time=take_time,
                    meal_relation=plan.meal_relation,
                    remark=plan.remark,
                )
            )
    return items


# --------------------------------------------------------------------------- #
# 冲突筛查
# --------------------------------------------------------------------------- #


def _screen_conflicts(drugs: Sequence[Medication], *, allergy_history: str | None = None) -> list[str]:
    """按「过敏史 -> 相互作用规则 -> 知识库」三段筛查，顺序即严重程度。

    第三段的知识库增强依赖 app.services.rag.retriever，未就绪时静默跳过，
    前两段的结论不受影响。
    """
    warnings: list[str] = []
    warnings.extend(_allergy_conflicts(drugs, allergy_history))
    warnings.extend(_interaction_conflicts(drugs))

    kb_hint = _kb_conflicts([drug.drug_name for drug in drugs])
    if kb_hint:
        warnings.append(kb_hint)
    return warnings


def _allergy_conflicts(drugs: Sequence[Medication], allergy_history: str | None) -> list[str]:
    """把患者过敏史拆词后比对药名与禁忌，命中即报（这一档最严重）。"""
    tokens = [
        token
        for token in _ALLERGY_SPLIT_RE.split(allergy_history or "")
        if len(token) >= 2 and token not in _ALLERGY_STOPWORDS
    ]
    if not tokens:
        return []

    warnings: list[str] = []
    for drug in drugs:
        haystack = f"{drug.drug_name}{drug.contraindication or ''}"
        for token in tokens:
            if token in haystack:
                warnings.append(
                    f"患者过敏史含「{token}」，处方中的 {drug.drug_name} 存在过敏风险，请务必先向医生确认"
                )
                break
    return warnings


def _interaction_conflicts(drugs: Sequence[Medication]) -> list[str]:
    """两条规则逐条过：配对式找两个不同药品，单药式要求处方里还有其他药。"""
    names = [drug.drug_name or "" for drug in drugs]
    warnings: list[str] = []

    for rule in INTERACTION_RULES:
        target = _first_pair_hit(names, rule)
        if target is None:
            continue
        warnings.append(f"{target}：{rule.warning}")
    return warnings


def _first_pair_hit(names: Sequence[str], rule: InteractionRule) -> str | None:
    """返回首个命中的描述串（配对式形如「A + B」），没命中返回 None。

    配对式只认**不同药品**：判据是药名不同，不是下标不同。同一张处方里同一个药开了两行
    （重复开方、不同规格各一行）是「重复用药」，不是「配伍叠加」，靠下标比就会误报。
    规则里 group_a 与 group_b 给同一组关键词（同类药叠加）也靠这一条兜住。
    """
    if not rule.group_b:
        if len(names) < 2:
            return None
        return next((name for name in names if _match_any(name, rule.group_a)), None)

    for index_a, name_a in enumerate(names):
        if not _match_any(name_a, rule.group_a):
            continue
        for index_b, name_b in enumerate(names):
            if index_a != index_b and name_b != name_a and _match_any(name_b, rule.group_b):
                return f"{name_a} + {name_b}"
    return None


def _match_any(name: str, keywords: Sequence[str]) -> bool:
    return bool(name) and any(keyword in name for keyword in keywords)


def _kb_conflicts(drug_names: Sequence[str]) -> str | None:
    """可选增强：从药品知识库捞一条相互作用/禁忌提示。

    检索链未就绪时直接返回 None，规则表的结论不受影响。
    """
    if not drug_names:
        return None
    provider = _get_retriever()
    if provider is None:
        return None

    query = "、".join(drug_names) + " 药物相互作用 禁忌"
    try:
        hits = provider(query, 1)
    except Exception as exc:  # noqa: BLE001 - 知识库增强失败不影响本地规则结论
        logger.warning("药品知识库检索失败，冲突提示仅用本地规则: %s", exc)
        return None

    for item in hits or []:
        text = item.get("text") if isinstance(item, Mapping) else getattr(item, "text", None)
        if not text:
            continue
        text = str(text).replace("\n", " ").strip()
        if any(word in text for word in ("相互作用", "禁忌", "不宜", "避免同服")):
            return "知识库提示：" + _trim(text, 150)
    return None


def _join_warnings(warnings: Sequence[str], *, limit: int = 255) -> str | None:
    """拼成一段写进 conflict_warning（该列 varchar(255)）。"""
    if not warnings:
        return None
    return _trim("；".join(dict.fromkeys(warnings)), limit)


# --------------------------------------------------------------------------- #
# 提醒文案
# --------------------------------------------------------------------------- #


def _compose_remark(item: PrescriptionItem, drug: Medication, *, frequency_recognized: bool) -> str:
    """给一个药品生成提醒文案。

    先试大模型做通俗化复述；产出里一旦出现调整剂量的措辞就丢弃回落到模板 ——
    需求分析 §10.1「用药建议仅复述处方，不新增、不调整剂量」在这里落地。
    """
    template = _remark_template(item, drug)
    if not frequency_recognized:
        return _trim(f"{template}（频次未能识别，请以处方或药盒说明为准）", MAX_REMARK_LENGTH)

    reply = _ask_llm(_REMARK_SYSTEM_PROMPT, _remark_user_prompt(item, drug))
    if reply is None:
        return template
    if _looks_like_dosage_change(reply):
        logger.warning("大模型复述中出现剂量调整措辞，已丢弃回落模板: %s", _trim(reply, 60))
        return template
    return _trim(reply, MAX_REMARK_LENGTH)


def _remark_user_prompt(item: PrescriptionItem, drug: Medication) -> str:
    fields = [
        f"药品：{drug.drug_name}",
        f"单次剂量：{item.dosage}" if item.dosage else "",
        f"用药频次：{item.frequency}" if item.frequency else "",
        f"用法：{item.usage_method}" if item.usage_method else "",
        f"与餐关系：{item.meal_relation}" if item.meal_relation else "",
        f"说明书要点：{drug.usage_instruction}" if drug.usage_instruction else "",
    ]
    return "\n".join(field for field in fields if field)


def _remark_template(item: PrescriptionItem, drug: Medication) -> str:
    """无大模型时的复述模板：只把处方原样串起来说。"""
    parts: list[str] = []
    meal = (item.meal_relation or "").strip()
    if meal and meal != "不限":
        parts.append(f"{meal}服用")
    if item.dosage:
        parts.append(f"每次{item.dosage}")
    if item.frequency:
        parts.append(item.frequency)
    if drug.usage_instruction:
        parts.append(drug.usage_instruction)
    return _trim("，".join(parts) or "按处方服用", MAX_REMARK_LENGTH)


def _looks_like_dosage_change(text: str) -> bool:
    """判断文案里有没有越界的用药调整建议（剂量、停换药、服药安排都算）。"""
    return bool(_DOSAGE_CHANGE_RE.search(text or ""))


# --------------------------------------------------------------------------- #
# 日历内部
# --------------------------------------------------------------------------- #


def _calendar_export_url(patient_id: str) -> str:
    """日历导出的相对路径；主机名与鉴权由路由层负责。"""
    return f"/api/v1/medication-reminders/calendar?patientId={patient_id}"


def _calendar_event(reminder: ReminderItem, *, stamp: str) -> list[str]:
    """拼一个 VEVENT，含提前提醒的 VALARM 与带免责声明的 DESCRIPTION。"""
    minutes = _parse_hhmm(reminder.take_time)
    start = datetime.combine(reminder.plan_date, time(hour=minutes // 60, minute=minutes % 60))
    end = start + timedelta(minutes=CALENDAR_EVENT_MINUTES)

    summary = f"服药提醒：{reminder.drug_name} {reminder.dose or ''}".strip()
    description = "；".join(
        part
        for part in (reminder.meal_relation, reminder.usage_instruction, reminder.conflict_warning, DISCLAIMER)
        if part
    )

    return [
        "BEGIN:VEVENT",
        f"UID:{reminder.reminder_id}@hospital-ai",
        f"DTSTAMP:{stamp}",
        f"DTSTART;TZID={TZID}:{start.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND;TZID={TZID}:{end.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_ics_escape(summary)}",
        f"DESCRIPTION:{_ics_escape(description)}",
        "BEGIN:VALARM",
        f"TRIGGER:-PT{CALENDAR_ALARM_MINUTES}M",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_ics_escape('服药提醒')}",
        "END:VALARM",
        "END:VEVENT",
    ]


def _ics_escape(text: str) -> str:
    """按 RFC 5545 转义反斜杠、分号、逗号与换行。"""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold_line(line: str, *, limit: int = 75) -> list[str]:
    """按 75 字节折行。

    RFC 5545 规定按**字节**而非字符算，中文一个字占 3 字节，按字符折会超限。
    续行以单个空格开头，那 1 字节也要算进预算里。
    """
    pieces: list[str] = []
    current = ""
    for char in line:
        budget = limit if not pieces else limit - 1
        if current and len(current.encode("utf-8")) + len(char.encode("utf-8")) > budget:
            pieces.append(current)
            current = char
        else:
            current += char

    if current or not pieces:
        pieces.append(current)
    return [pieces[0]] + [" " + piece for piece in pieces[1:]]


# --------------------------------------------------------------------------- #
# 查询与工具
# --------------------------------------------------------------------------- #


def _default_patient_id(session: Session, user_id: str) -> str | None:
    """取账号的默认就诊人；没有 is_default=1 的则退到第一条，保证「默认本人」可用。"""
    return session.execute(
        select(Patient.patient_id)
        .where(Patient.user_id == user_id)
        .order_by(Patient.is_default.desc(), Patient.patient_id)
        .limit(1)
    ).scalar_one_or_none()


def _latest_prescription(session: Session, patient_id: str) -> Prescription | None:
    """该就诊人最近一张处方；created_at 相同时用处方号兜底排序。"""
    return session.execute(
        select(Prescription)
        .where(Prescription.patient_id == patient_id)
        .order_by(Prescription.created_at.desc(), Prescription.prescription_id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _prescription_rows(session: Session, prescription_id: str) -> list[tuple[PrescriptionItem, Medication]]:
    """处方明细 join 药品表。模型层没有 relationship()，关系一律手写 join。"""
    return list(
        session.execute(
            select(PrescriptionItem, Medication)
            .join(Medication, Medication.drug_id == PrescriptionItem.drug_id)
            .where(PrescriptionItem.prescription_id == prescription_id)
            .order_by(PrescriptionItem.item_id)
        ).all()
    )


def _load_drugs(session: Session, drug_ids: Sequence[str]) -> dict[str, Medication]:
    unique_ids = sorted(set(drug_ids))
    if not unique_ids:
        return {}
    medications = session.execute(select(Medication).where(Medication.drug_id.in_(unique_ids))).scalars().all()
    return {medication.drug_id: medication for medication in medications}


def _visit_context(session: Session, prescription: Prescription) -> tuple[date | None, str | None, str | None]:
    """经 t_appointment 反查就诊日期、科室、医生；预约链路断了就一律给 None。"""
    if not prescription.appointment_id:
        return None, None, None

    appointment = session.get(Appointment, prescription.appointment_id)
    if appointment is None:
        return None, None, None

    department = session.get(Department, appointment.dept_id)
    doctor = session.get(Doctor, appointment.doctor_id)
    return (
        appointment.appt_date,
        department.dept_name if department else None,
        doctor.name if doctor else None,
    )


def _clear_reminders(session: Session, prescription_id: str) -> int:
    """删掉该处方已有的提醒行，保证重复生成不会叠加。"""
    result = session.execute(
        delete(MedicationReminder).where(MedicationReminder.prescription_id == prescription_id)
    )
    count = result.rowcount or 0
    if count:
        logger.info("清除处方 %s 的旧提醒 %d 行", prescription_id, count)
    return count


def _new_id(prefix: str) -> str:
    """生成 32 位以内的业务主键，避开种子的序号风格（REM0001）。"""
    return f"{prefix}{uuid.uuid4().hex[:20].upper()}"


def _parse_hhmm(value: str) -> int:
    """'08:30' -> 510（分钟）；解析不了返回 0（当天 00:00）。"""
    match = _HHMM_RE.fullmatch((value or "").strip())
    if not match:
        return 0
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return 0
    return hour * 60 + minute


def _format_hhmm(minutes: int) -> str:
    """分钟 -> 'HH:MM'，自动绕回一天之内。"""
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _shift_time(value: str, offset_minutes: int) -> str:
    if not offset_minutes:
        return value
    return _format_hhmm(_parse_hhmm(value) + offset_minutes)


def _trim(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


__all__ = [
    "DISCLAIMER",
    "DEFAULT_TAKE_TIME",
    "FREQUENCY_SCHEDULE",
    "INTERACTION_RULES",
    "MEAL_OFFSET_MINUTES",
    "AdherenceSummary",
    "CurrentPrescription",
    "DrugLine",
    "DrugPlan",
    "InteractionRule",
    "PlanItem",
    "ReminderItem",
    "ReminderPlan",
    "build_calendar",
    "generate_reminders",
    "get_current_prescription",
    "list_reminders",
    "mark_taken",
    "set_llm",
    "set_retriever",
    "summarize_adherence",
]
