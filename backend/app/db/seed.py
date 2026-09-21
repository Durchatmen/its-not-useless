"""演示数据填充脚本（SQLAlchemy 2.0 ORM）。

依据《智慧医疗AI辅助系统数据库表设计文档 V1.0》建 19 张表并写入约 50 条/表的模拟数据。

**发热门诊优先级最高**：科室、医生、排班、挂号、病历、检查、报告、处方、药品、
AI 预诊会话与消息、账单等表中，发热门诊的数据都排在最前面（主键序号最小、写入最早）。
由于 InnoDB 聚簇索引按主键排序，`SELECT * FROM t_xxx` 不带 ORDER BY 时
发热门诊的数据自然显示在各表最上方。

脚本是**幂等**的：已存在的表不会重建，已有数据的表不会重灌，默认全程不删任何既有数据。
重复执行只会补齐缺失的表和空表，已灌好的表原样保留。

用法（在 backend/ 目录下）：
    .venv/Scripts/python.exe -m app.db.seed             # 补建缺失的表、只给空表灌数据
    .venv/Scripts/python.exe -m app.db.seed --dry-run   # 只打印将要执行的动作，不连库
    .venv/Scripts/python.exe -m app.db.seed --reset     # 先清空 19 张业务表再重灌（会丢数据）
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from itertools import count
from typing import Optional

import bcrypt
from sqlalchemy import Engine, URL, create_engine, inspect, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import DATABASE_URL
from app.models import (
    AiMessage,
    AiSession,
    Appointment,
    Bill,
    Department,
    Doctor,
    Exam,
    ExamReport,
    MedicalRecord,
    Medication,
    MedicationReminder,
    OperationLog,
    Patient,
    Payment,
    Prescription,
    PrescriptionItem,
    Schedule,
    SmsCode,
    User,
)

# --------------------------------------------------------------------------- #
# 基础常量
# --------------------------------------------------------------------------- #

RNG = random.Random(20260920)  # 固定种子：ID 与取值可复现
TODAY = date.today()

FEVER_DEPT_ID = "DEPT0001"
FEVER_DEPT_NAME = "发热门诊"
FEVER_DOCTOR_COUNT = 8  # 发热门诊配属医生数，全院最多

DEPT_COUNT = 50
DOCTOR_COUNT = 50
USER_COUNT = 50
PATIENT_COUNT = 50
SCHEDULE_DAYS = 7  # 排班生成未来 7 天

DEMO_PASSWORD = "123456"  # 全部演示账号统一口令，登录即可用

_phone_seq = count(1)


def _phone() -> str:
    """生成唯一的演示手机号。"""
    return f"13{next(_phone_seq):09d}"


def _idcard(birth: date, seq: int) -> str:
    """生成 18 位演示身份证号（前 6 位为演示地区码）。"""
    return f"330106{birth:%Y%m%d}{seq:04d}"


def _money(value: float) -> Decimal:
    return Decimal(f"{value:.2f}")


def _split_amount(amount: Decimal, cover_ratio: float) -> tuple[Decimal, Decimal]:
    """按比例拆分医保报销与自付。

    自付额用总额减去报销额得出，避免对半拆分时的浮点舍入导致两者之和与总额差一分钱。
    """
    cover = _money(float(amount) * cover_ratio)
    return cover, (amount - cover).quantize(Decimal("0.01"))


def _ids(prefix: str, n: int) -> list[str]:
    return [f"{prefix}{i:04d}" for i in range(1, n + 1)]


def _hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt(rounds=10)).decode()


# --------------------------------------------------------------------------- #
# 科室：发热门诊排在首位
# --------------------------------------------------------------------------- #

# 前 7 个科室构成发热门诊的完整诊疗链路（分诊 → 检验 → 影像），排在科室表最上方。
DEPT_NAMES = [
    "发热门诊", "呼吸内科", "感染科", "急诊医学科", "儿科", "医学检验科", "医学影像科",
    "结核病科", "肠道门诊", "重症医学科", "消化内科", "心血管内科", "神经内科", "内分泌科",
    "肾内科", "血液内科", "风湿免疫科", "肝病科", "普外科", "骨科",
    "神经外科", "泌尿外科", "心胸外科", "血管外科", "妇产科", "皮肤科",
    "眼科", "耳鼻咽喉科", "口腔科", "中医科", "康复医学科", "精神心理科",
    "疼痛科", "肿瘤内科", "全科医学科", "老年医学科", "超声医学科", "病理科",
    "输血科", "麻醉科", "营养科", "药剂科", "护理门诊", "艾滋病专科门诊",
    "预防保健科", "职业病科", "变态反应科", "儿外科", "新生儿科", "高压氧治疗科",
]

# 发热门诊及其链路科室使用真实位置与职能描述，便于院内导航与分诊知识库演示。
DEPT_DETAILS: dict[str, tuple[str, str, str, str]] = {
    # 科室名: (楼栋, 楼层位置编码, 房间号, 职能简介)
    "发热门诊": (
        "感染楼",
        "1F-E-101",
        "感染楼1楼东侧发热门诊专区（独立出入口，24小时开放）",
        "承担发热患者的预检分诊、筛查与诊治，设独立挂号、诊室、检验、留观与药房窗口，"
        "实行“三区两通道”管理；对体温≥37.3℃或有呼吸道症状的患者优先接诊，"
        "开展流感、新冠等呼吸道病原学检测与隔离转运。",
    ),
    "呼吸内科": (
        "门诊楼",
        "3F-E-305",
        "门诊楼3楼305诊区",
        "诊治咳嗽、咳痰、气促、咯血、肺部感染、慢阻肺、哮喘、肺结节等呼吸系统疾病，"
        "常规开展肺功能、支气管镜与睡眠呼吸监测。",
    ),
    "感染科": (
        "感染楼",
        "2F-E-201",
        "感染楼2楼201诊区",
        "诊治各类病毒性、细菌性、寄生虫感染与发热待查，负责传染病报告、隔离指导与"
        "抗菌药物合理使用会诊。",
    ),
    "急诊医学科": (
        "急诊楼",
        "1F-A-102",
        "急诊楼1楼抢救区/急诊诊室（24小时）",
        "承担急危重症的院前衔接与院内抢救，设预检分诊台、抢救室、留观区，"
        "对高热惊厥、呼吸困难、意识障碍等开通绿色通道。",
    ),
    "儿科": (
        "门诊楼",
        "2F-W-208",
        "门诊楼2楼208诊区",
        "诊治儿童发热、呼吸道感染、腹泻、皮疹等常见病，设儿童输液区与雾化室，"
        "对3个月以下婴儿发热优先接诊。",
    ),
    "医学检验科": (
        "医技楼",
        "2F-T-210",
        "医技楼2楼检验采样大厅",
        "承担门急诊标本采集与检测，发热门诊标本走专用通道与独立检测批次，"
        "提供血常规、CRP、甲乙流抗原、新冠核酸等快速检测。",
    ),
    "医学影像科": (
        "医技楼",
        "1F-T-108",
        "医技楼1楼影像中心CT-2室",
        "提供 DR、CT、MRI 检查，发热门诊患者胸部CT 使用专用机房并即时消毒，"
        "报告完成后同步至 HIS 与患者端。",
    ),
}


def _build_departments() -> list[Department]:
    rows: list[Department] = []
    for idx, name in enumerate(DEPT_NAMES, start=1):
        dept_id = f"DEPT{idx:04d}"
        detail = DEPT_DETAILS.get(name)
        if detail:
            building, floor_position, addr, intro = detail
        else:
            building = "门诊楼" if idx % 3 else "住院楼"
            floor = 2 + (idx % 4)
            wing = "E" if idx % 2 == 0 else "W"
            room = f"{floor}F-{wing}-{300 + idx}"
            floor_position = room
            addr = f"{building}{floor}楼{300 + idx}诊区"
            intro = (
                f"{name}负责本科室常见病、多发病的门诊诊治与慢病随访，"
                f"提供检查检验开单、用药指导与复诊预约服务。"
            )
        rows.append(
            Department(
                dept_id=dept_id,
                dept_name=name,
                dept_addr=addr,
                phone=f"0571-8700-{1000 + idx}",
                floor_position=floor_position,
                introduction=intro,
                status=1,
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# 医生：发热门诊 8 名排最前
# --------------------------------------------------------------------------- #

SURNAMES = [
    "张", "王", "李", "赵", "陈", "刘", "杨", "黄", "周", "吴",
    "徐", "孙", "马", "朱", "胡", "郭", "何", "高", "林", "罗",
    "郑", "梁", "谢", "宋", "唐", "许", "韩", "冯", "邓", "曹",
]
GIVEN_NAMES = [
    "建国", "志强", "慧敏", "秀兰", "伟", "静", "俊", "丽娟", "明", "晓东",
    "海燕", "磊", "文博", "雅琴", "鹏", "雪梅", "浩", "丹", "立新", "倩",
    "岩", "宁", "峰", "琳", "涛", "波", "霞", "刚", "平", "敏",
]

FEVER_DOCTOR_SPECS = [
    ("主任医师", "发热待查与不明原因发热的鉴别诊断、重症肺炎救治"),
    ("主任医师", "流行性感冒与新型冠状病毒感染的诊治"),
    ("副主任医师", "呼吸道感染性疾病与抗菌药物合理使用"),
    ("副主任医师", "儿童发热与出疹性疾病的诊治"),
    ("副主任医师", "感染性腹泻与肠道传染病的防治"),
    ("主治医师", "病毒性肝炎等传染病的抗病毒治疗"),
    ("主治医师", "发热伴血小板减少综合征、虫媒传染病的诊治"),
    ("医师", "发热患者预检分诊与隔离转运、流行病学调查"),
]

# 非发热门诊的科室配属（科室名 → 医生数），其余医生轮转覆盖后续科室。
DEPT_DOCTOR_MIX = [
    ("呼吸内科", 2), ("感染科", 2), ("急诊医学科", 2), ("儿科", 2),
    ("医学检验科", 1), ("医学影像科", 1),
]

FEVER_AVATAR = "https://cdn.demo-hospital.local/avatar/fever/{n}.png"


def _build_doctors(departments: list[Department]) -> list[Doctor]:
    dept_by_name = {d.dept_name: d for d in departments}
    rows: list[Doctor] = []
    used_names: set[str] = set()

    def next_name() -> str:
        while True:
            name = RNG.choice(SURNAMES) + RNG.choice(GIVEN_NAMES)
            if name not in used_names:
                used_names.add(name)
                return name

    def make(idx: int, dept: Department, title: str, specialty: str) -> Doctor:
        gender = "M" if RNG.random() < 0.55 else "F"
        birth_year = RNG.randint(1968, 1992)
        return Doctor(
            doctor_id=f"DOC{idx:04d}",
            dept_id=dept.dept_id,
            name=next_name(),
            gender=gender,
            birth_date=date(birth_year, RNG.randint(1, 12), RNG.randint(1, 28)),
            title=title,
            specialty=specialty,
            avatar=(
                FEVER_AVATAR.format(n=idx)
                if dept.dept_name == FEVER_DEPT_NAME
                else f"https://cdn.demo-hospital.local/avatar/{idx}.png"
            ),
            intro=f"长期从事{dept.dept_name}临床工作，擅长{specialty}。",
            visit_status=1 if idx % 11 else 2,  # 少量停诊，便于演示出诊状态
        )

    # 1) 发热门诊：优先写入，ID 最小
    fever_dept = dept_by_name[FEVER_DEPT_NAME]
    for i, (title, specialty) in enumerate(FEVER_DOCTOR_SPECS, start=1):
        rows.append(make(i, fever_dept, title, specialty))

    # 2) 发热门诊链路上的科室
    idx = len(rows) + 1
    for dept_name, n in DEPT_DOCTOR_MIX:
        dept = dept_by_name[dept_name]
        for _ in range(n):
            rows.append(make(idx, dept, RNG.choice(["主任医师", "副主任医师", "主治医师"]),
                             f"{dept_name}常见病与疑难病的诊治"))
            idx += 1

    # 3) 其余医生轮转覆盖后面尚未配属医生的科室
    taken = {d.dept_id for d in rows}
    for dept in departments:
        if len(rows) >= DOCTOR_COUNT:
            break
        if dept.dept_id in taken:
            continue
        rows.append(make(idx, dept, RNG.choice(["副主任医师", "主治医师", "医师"]),
                         f"{dept.dept_name}常见病的门诊诊治"))
        idx += 1

    return rows[:DOCTOR_COUNT]


# --------------------------------------------------------------------------- #
# 账号与就诊人
# --------------------------------------------------------------------------- #


def _build_users(doctors: list[Doctor]) -> list[User]:
    """发热门诊医生的登录账号排在最前，其次其他医生、患者、管理员。"""
    password_hash = _hash_password(DEMO_PASSWORD)
    rows: list[User] = []
    idx = 0

    fever_docs = [d for d in doctors if d.dept_id == FEVER_DEPT_ID]
    other_docs = [d for d in doctors if d.dept_id != FEVER_DEPT_ID]
    # 8 个发热门诊账号 + 12 个其他医生账号
    account_docs = fever_docs + other_docs[: max(0, 20 - len(fever_docs))]

    for doctor in account_docs:
        idx += 1
        phone = _phone()
        rows.append(
            User(
                user_id=f"USR{idx:04d}",
                account=phone,
                password=password_hash,
                name=doctor.name,
                idcard=_idcard(doctor.birth_date, idx),
                phone=phone,
                role="DOCTOR",
                real_name_verified=1,
                status=1,
                last_login_at=datetime.combine(TODAY, time(7, 30)) - timedelta(days=idx % 5),
            )
        )

    patient_account_count = USER_COUNT - idx - 4  # 预留 4 个管理员
    for _ in range(patient_account_count):
        idx += 1
        phone = _phone()
        rows.append(
            User(
                user_id=f"USR{idx:04d}",
                account=phone,
                password=password_hash,
                name=_patient_name(),
                idcard=None,
                phone=phone,
                role="PATIENT",
                real_name_verified=1,
                status=1,
                last_login_at=datetime.combine(TODAY, time(9, 0)) - timedelta(hours=idx),
            )
        )

    for _ in range(USER_COUNT - idx):
        idx += 1
        phone = _phone()
        rows.append(
            User(
                user_id=f"USR{idx:04d}",
                account=phone,
                password=password_hash,
                name=f"系统管理员{idx}",
                idcard=None,
                phone=phone,
                role="ADMIN",
                real_name_verified=1,
                status=1,
                last_login_at=datetime.combine(TODAY, time(8, 30)),
            )
        )

    return rows


def _patient_name() -> str:
    return RNG.choice(SURNAMES) + RNG.choice(GIVEN_NAMES)


BLOOD_TYPES = ["A", "B", "O", "AB"]
ALLERGY_POOL = [
    "青霉素过敏",
    "头孢类过敏",
    "磺胺类药物过敏",
    "海鲜过敏",
    "花粉、尘螨过敏",
    "无已知过敏史",
]
HISTORY_POOL = [
    "高血压病2级，规律服用硝苯地平控释片",
    "2型糖尿病，口服二甲双胍",
    "慢性乙型病毒性肝炎",
    "支气管哮喘，季节性发作",
    "慢性胃炎",
    "无重大既往病史",
]


def _build_patients(users: list[User]) -> list[Patient]:
    """就诊人按主键顺序写入；前 30 位服务于后面的发热门诊挂号，排在各表最前。"""
    patient_accounts = [u for u in users if u.role == "PATIENT"]
    rows: list[Patient] = []
    idx = 0

    # 每个患者账号 2 名就诊人（本人 + 家属），最后 2 个账号仅 1 名，凑满 50 条。
    for account in patient_accounts:
        for relation in ("SELF", "SPOUSE"):
            if len(rows) >= PATIENT_COUNT:
                break
            idx += 1
            birth = date(RNG.randint(1948, 2019), RNG.randint(1, 12), RNG.randint(1, 28))
            rows.append(
                Patient(
                    patient_id=f"PAT{idx:04d}",
                    user_id=account.user_id,
                    name=account.name if relation == "SELF" else _patient_name(),
                    idcard=_idcard(birth, 100 + idx),
                    phone=account.phone,
                    gender="M" if relation == "SELF" and idx % 2 else RNG.choice("MF"),
                    birth_date=birth,
                    relation=relation,
                    blood_type=RNG.choice(BLOOD_TYPES),
                    allergy_history=RNG.choice(ALLERGY_POOL),
                    medical_history=RNG.choice(HISTORY_POOL),
                    is_default=1 if relation == "SELF" else 0,
                )
            )
        if len(rows) >= PATIENT_COUNT:
            break

    return rows


# --------------------------------------------------------------------------- #
# 排班与挂号
# --------------------------------------------------------------------------- #

TIME_SLOTS = [
    "08:00-08:30", "08:30-09:00", "09:00-09:30", "09:30-10:00", "10:00-10:30",
    "10:30-11:00", "13:30-14:00", "14:00-14:30", "14:30-15:00", "15:00-15:30",
]

FEVER_CHIEF_COMPLAINTS = [
    "发热3天，最高体温39.2℃，伴咽痛、乏力",
    "发热伴咳嗽、咳黄痰5天",
    "高热2天，伴畏寒、肌肉酸痛",
    "发热1天，咽痛明显，自测甲流抗原阳性",
    "反复发热1周，抗感染治疗效果不佳",
    "发热伴腹泻3天，每日5-6次水样便",
    "发热伴皮疹2天，躯干为主",
    "发热伴胸闷、气促1天",
    "发热4天，伴头痛、眼眶后疼痛",
    "低热2周，伴盗汗、消瘦",
    "发热伴关节疼痛、乏力2周",
    "发热伴呕吐、腹痛1天",
]

OTHER_CHIEF_COMPLAINTS = [
    "咳嗽咳痰1周",
    "上腹隐痛2周",
    "血压控制不佳复诊",
    "腰部疼痛伴活动受限",
    "反复头晕1月",
    "皮疹瘙痒加重3天",
    "血糖控制不佳复诊",
    "视物模糊1周",
    "关节疼痛晨僵",
    "心慌胸闷1周",
]


def _build_schedules(doctors: list[Doctor], departments: list[Department]) -> list[Schedule]:
    """发热门诊医生的号源排在最前。

    排班窗口取“近 3 天 + 今天 + 未来 3 天”：未来段供预约挂号演示，
    过去段供已完成就诊（病历/检查/报告/处方/账单）关联，保证业务闭环时间自洽。
    """
    fever_docs = [d for d in doctors if d.dept_id == FEVER_DEPT_ID][:5]
    other_docs = [d for d in doctors if d.dept_id != FEVER_DEPT_ID][:5]
    ordered = fever_docs + other_docs

    rows: list[Schedule] = []
    idx = 0
    for doctor in ordered:
        for day_offset in range(SCHEDULE_DAYS):
            idx += 1
            appt_date = TODAY - timedelta(days=3) + timedelta(days=day_offset)
            slot = TIME_SLOTS[(idx + day_offset) % len(TIME_SLOTS)]
            total = 20 if doctor.dept_id == FEVER_DEPT_ID else 12
            booked = RNG.randint(0, total // 2)
            fee = _money(50 if doctor.title in ("主任医师", "副主任医师") else 20)
            rows.append(
                Schedule(
                    schedule_id=f"SCH{idx:04d}",
                    doctor_id=doctor.doctor_id,
                    dept_id=doctor.dept_id,
                    appt_date=appt_date,
                    time_slot=slot,
                    total_count=total,
                    remaining=total - booked,
                    fee=fee,
                    external_no=f"HIS-SCH-{idx:06d}",
                )
            )
    return rows


def _build_appointments(
    users: list[User],
    patients: list[Patient],
    schedules: list[Schedule],
) -> list[Appointment]:
    """前 30 条为发热门诊挂号，排在各表最上方。"""
    patient_owner = {p.patient_id: p.user_id for p in patients}
    # 挂号一律取自“今天及以前”的号源：这样每次挂号都对应一次已完成的就诊，
    # 后面的病历、检查、报告、处方、账单才有真实的时间落点。
    past = [s for s in schedules if s.appt_date <= TODAY]
    fever_schedules = [s for s in past if s.dept_id == FEVER_DEPT_ID]
    other_schedules = [s for s in past if s.dept_id != FEVER_DEPT_ID]

    rows: list[Appointment] = []
    for idx in range(1, 51):
        is_fever = idx <= 30
        schedule = RNG.choice(fever_schedules if is_fever else other_schedules)
        patient = patients[(idx - 1) % len(patients)]
        appt_date = schedule.appt_date
        status = "FINISHED" if appt_date < TODAY else "CHECKED_IN"
        if idx % 13 == 0:
            status = "CANCELED"
        rows.append(
            Appointment(
                appointment_id=f"APT{idx:04d}",
                user_id=patient_owner[patient.patient_id],
                patient_id=patient.patient_id,
                doctor_id=schedule.doctor_id,
                schedule_id=schedule.schedule_id,
                dept_id=schedule.dept_id,
                appt_date=appt_date,
                time_slot=schedule.time_slot,
                chief_complaint=RNG.choice(
                    FEVER_CHIEF_COMPLAINTS if is_fever else OTHER_CHIEF_COMPLAINTS
                ),
                queue_no=f"{'F' if is_fever else 'A'}{idx:03d}",
                appointment_status=status,
                # 发热门诊以 AI 预诊分诊后自动挂号为主，体现分诊闭环
                source="AI_AUTO" if is_fever and idx % 3 else "MANUAL",
                external_no=f"HIS-APT-{idx:06d}",
            )
        )
    return rows




# --------------------------------------------------------------------------- #
# 药品
# --------------------------------------------------------------------------- #

# (药品名称, 类型, 规格, 医保属性, 用法用量, 禁忌与副作用要点)
# 前 15 种为发热门诊常用药，排在药品表最上方。
DRUG_SPECS: list[tuple[str, str, str, str, str, str]] = [
    ("磷酸奥司他韦胶囊", "处方药", "75mg×10粒", "A", "口服，每次75mg，每日2次，连用5天",
     "对本品过敏者禁用；可见恶心、呕吐，肾功能不全者需调整剂量"),
    ("磷酸奥司他韦颗粒", "处方药", "15mg×12袋", "B", "口服，按体重每次1.5-3mg/kg，每日2次，连用5天",
     "对本品过敏者禁用；儿童按体重精确给药"),
    ("布洛芬缓释胶囊", "非处方药", "0.3g×20粒", "A", "口服，每次1粒，每日2次，餐后服用",
     "活动性消化道溃疡、对阿司匹林过敏者禁用；不超过3天"),
    ("对乙酰氨基酚片", "非处方药", "0.5g×20片", "A", "口服，每次0.5g，每4-6小时1次，24小时不超过4次",
     "严重肝肾功能不全者禁用；用药期间禁止饮酒"),
    ("连花清瘟胶囊", "中成药", "0.35g×24粒", "B", "口服，每次4粒，每日3次",
     "风寒感冒者不适用；运动员慎用"),
    ("金花清感颗粒", "中成药", "5g×10袋", "B", "开水冲服，每次1袋，每日3次",
     "脾胃虚寒者慎用；孕妇慎用"),
    ("阿莫西林胶囊", "处方药", "0.25g×24粒", "A", "口服，每次0.5g，每6-8小时1次",
     "青霉素过敏者及传染性单核细胞增多症患者禁用"),
    ("头孢克肟分散片", "处方药", "0.1g×12片", "B", "口服，每次0.1g，每日2次",
     "对头孢类过敏者禁用；用药期间避免饮酒"),
    ("盐酸莫西沙星片", "处方药", "0.4g×6片", "B", "口服，每次0.4g，每日1次",
     "18岁以下、孕妇及哺乳期妇女禁用；可致QT间期延长"),
    ("蒲地蓝消炎口服液", "中成药", "10ml×12支", "B", "口服，每次10ml，每日3次",
     "脾胃虚寒者慎用；糖尿病患者注意含糖量"),
    ("阿奇霉素干混悬剂", "处方药", "0.1g×6袋", "B", "口服，首日0.2g，第2-5日每次0.1g，每日1次",
     "对大环内酯类过敏者禁用；肝功能不全者慎用"),
    ("盐酸氨溴索口服溶液", "非处方药", "100ml:0.3g", "A", "口服，每次10ml，每日3次，餐后服用",
     "对本品过敏者禁用；妊娠早期慎用"),
    ("复方甲氧那明胶囊", "处方药", "12粒×2板", "B", "口服，每次2粒，每日3次，餐后服用",
     "8岁以下儿童禁用；勿与其他镇咳祛痰药同服"),
    ("孟鲁司特钠片", "处方药", "10mg×5片", "B", "口服，每次10mg，每晚1次",
     "对本品过敏者禁用；注意神经精神系统不良反应"),
    ("布地奈德福莫特罗粉吸入剂", "处方药", "160μg:4.5μg×60吸", "B", "吸入，每次1吸，每日2次",
     "对本品成分过敏者禁用；吸入后需漱口"),
    ("硝苯地平控释片", "处方药", "30mg×7片", "A", "口服，每次30mg，每日1次",
     "心源性休克者禁用；整片吞服不可掰开"),
    ("阿托伐他汀钙片", "处方药", "20mg×7片", "B", "口服，每次20mg，每晚1次",
     "活动性肝病者禁用；监测肝功能与肌酸激酶"),
    ("缬沙坦胶囊", "处方药", "80mg×7粒", "B", "口服，每次80mg，每日1次",
     "孕妇禁用；双侧肾动脉狭窄者禁用"),
    ("二甲双胍缓释片", "处方药", "0.5g×30片", "A", "口服，每次0.5g，每日1次，随晚餐服用",
     "肾功能不全、严重感染者禁用；造影检查前后需停药"),
    ("阿卡波糖片", "处方药", "50mg×30片", "B", "口服，每次50mg，每日3次，随第一口主食嚼服",
     "肠道疾病、肠梗阻者禁用；常见腹胀排气增多"),
    ("奥美拉唑肠溶胶囊", "处方药", "20mg×14粒", "A", "口服，每次20mg，每日1次，晨起空腹",
     "对本品过敏者禁用；长期使用需评估骨质疏松风险"),
    ("铝碳酸镁咀嚼片", "非处方药", "0.5g×20片", "B", "口服，每次1片，每日3次，餐后1小时嚼服",
     "严重肾功能不全者禁用；与其他药物间隔1-2小时"),
    ("双歧杆菌四联活菌片", "非处方药", "0.5g×36片", "B", "口服，每次3片，每日3次，餐后温水送服",
     "勿与抗菌药物同服，需间隔2小时以上"),
    ("蒙脱石散", "非处方药", "3g×10袋", "A", "口服，每次1袋，每日3次，温水50ml冲服",
     "与其他药物间隔1小时以上；便秘者慎用"),
    ("美托洛尔缓释片", "处方药", "47.5mg×7片", "B", "口服，每次47.5mg，每日1次",
     "严重心动过缓、二度以上房室传导阻滞者禁用；不可骤然停药"),
    ("阿司匹林肠溶片", "处方药", "100mg×30片", "A", "口服，每次100mg，每日1次，餐前服用",
     "活动性消化道溃疡、出血体质者禁用"),
    ("呋塞米片", "处方药", "20mg×100片", "A", "口服，每次20mg，每日1次，晨服",
     "低钾血症、肝性脑病者禁用；注意电解质监测"),
    ("螺内酯片", "处方药", "20mg×100片", "A", "口服，每次20mg，每日1次",
     "高钾血症、急性肾功能不全者禁用"),
    ("碳酸钙D3片", "非处方药", "0.6g×60片", "B", "口服，每次1片，每日1次，餐后服用",
     "高钙血症、高钙尿症者禁用"),
    ("塞来昔布胶囊", "处方药", "0.2g×6粒", "B", "口服，每次0.2g，每日1次",
     "磺胺过敏、冠脉搭桥围术期患者禁用"),
    ("氨基葡萄糖胶囊", "非处方药", "0.24g×60粒", "B", "口服，每次1粒，每日3次，餐时服用",
     "对贝类过敏者慎用；哮喘患者注意过敏反应"),
    ("甲钴胺片", "处方药", "0.5mg×20片", "B", "口服，每次0.5mg，每日3次",
     "对本品过敏者禁用；从事汞作业人员不宜长期服用"),
    ("卤米松乳膏", "处方药", "10g:5mg", "B", "外用，每日1-2次薄涂患处",
     "面部、腋下等皮肤薄嫩部位慎用；连续使用不超过2周"),
    ("复方醋酸地塞米松乳膏", "非处方药", "20g", "B", "外用，每日2次涂敷患处",
     "皮肤破溃及感染部位禁用；面部禁用"),
    ("氯雷他定片", "非处方药", "10mg×6片", "A", "口服，每次10mg，每日1次",
     "对本品过敏者禁用；肝功能不全者减量"),
    ("盐酸西替利嗪滴剂", "非处方药", "10ml:0.1g", "B", "口服，每次5-10滴，每日1次",
     "对本品过敏者禁用；用药期间避免驾驶"),
    ("左氧氟沙星滴眼液", "处方药", "5ml:24.4mg", "A", "滴眼，每次1-2滴，每日3-5次",
     "对喹诺酮类过敏者禁用；佩戴隐形眼镜者需先摘除"),
    ("玻璃酸钠滴眼液", "非处方药", "5ml:5mg", "B", "滴眼，每次1滴，每日5-6次",
     "对本品过敏者禁用；开瓶后4周内用完"),
    ("丙酸氟替卡松鼻喷雾剂", "处方药", "50μg×120喷", "B", "喷鼻，每次各鼻孔2喷，每日1次",
     "对本品过敏者禁用；长期使用需监测鼻黏膜"),
    ("糠酸莫米松鼻喷雾剂", "处方药", "50μg×60喷", "B", "喷鼻，每次各鼻孔2喷，每日1次",
     "未经治疗的活动性鼻部感染患者禁用"),
    ("布洛芬混悬液", "非处方药", "100ml:2g", "A", "口服，按体重每次5-10mg/kg，每6小时1次",
     "6个月以下婴儿禁用；24小时不超过4次"),
    ("头孢克洛干混悬剂", "处方药", "0.125g×6袋", "B", "口服，按体重每次10mg/kg，每日3次",
     "对头孢类过敏者禁用；青霉素过敏者慎用"),
    ("小儿豉翘清热颗粒", "中成药", "2g×9袋", "B", "开水冲服，每次1-2袋，每日3次",
     "风寒感冒者不适用；糖尿病患儿禁用含糖剂型"),
    ("健胃消食片", "非处方药", "0.8g×32片", "B", "口服，每次3片，每日3次，餐后服用",
     "对本品过敏者禁用；孕妇慎用"),
    ("复方丹参滴丸", "中成药", "27mg×150丸", "A", "口服或舌下含服，每次10丸，每日3次",
     "孕妇禁用；有出血倾向者慎用"),
    ("麝香保心丸", "中成药", "22.5mg×42丸", "A", "口服，每次2丸，每日3次",
     "孕妇禁用；本品含蟾酥，不可过量久服"),
    ("归脾丸", "中成药", "9g×10丸", "B", "口服，每次1丸，每日3次，温开水送服",
     "感冒发热患者不宜服用；忌生冷油腻"),
    ("血府逐瘀胶囊", "中成药", "0.4g×24粒", "B", "口服，每次6粒，每日2次",
     "孕妇禁用；月经期妇女慎用"),
    ("甲巯咪唑片", "处方药", "10mg×50片", "A", "口服，初始每次10mg，每日3次，维持期减量",
     "哺乳期禁用；定期监测血常规与肝功能"),
    ("左甲状腺素钠片", "处方药", "50μg×100片", "A", "口服，每次50μg，每日1次，晨起空腹",
     "未经治疗的甲亢、急性心肌梗死患者禁用"),
]

SUPPLIERS = [
    "国药控股浙江有限公司", "华东医药股份有限公司", "浙江英特药业有限责任公司",
    "上海医药集团股份有限公司", "石药集团欧意药业有限公司",
]


def _build_medications() -> list[Medication]:
    rows: list[Medication] = []
    for idx, (name, dtype, spec, insurance, usage, contra) in enumerate(DRUG_SPECS, start=1):
        rows.append(
            Medication(
                drug_id=f"DRUG{idx:04d}",
                drug_name=name,
                drug_type=dtype,
                specification=spec,
                supplier=RNG.choice(SUPPLIERS),
                stock=RNG.randint(0, 2000),
                price=_money(RNG.uniform(8.0, 168.0)),
                insurance_type=insurance,
                usage_instruction=usage,
                contraindication=contra,
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# 病历、处方、账单
# --------------------------------------------------------------------------- #

FEVER_DIAGNOSES = [
    ("流行性感冒（甲型）", "奥司他韦抗病毒治疗，布洛芬退热，多饮水，居家隔离5天，3天后复诊"),
    ("急性上呼吸道感染", "对症退热，连花清瘟清热解毒，注意休息，如持续高热48小时以上复诊"),
    ("急性化脓性扁桃体炎", "阿莫西林抗感染，布洛芬退热，生理盐水漱口，5天后复查"),
    ("社区获得性肺炎", "莫西沙星抗感染，氨溴索化痰，胸部CT复查，建议住院观察"),
    ("感染性腹泻", "蒙脱石散止泻，双歧杆菌调节肠道菌群，口服补液盐，避免油腻饮食"),
    ("新型冠状病毒感染", "对症退热，连花清瘟，居家隔离，监测血氧饱和度，低于93%立即就医"),
    ("发热待查", "完善血培养、胸部CT与自身免疫抗体检查，暂予对症处理，门诊随访"),
    ("支气管哮喘急性发作", "布地奈德福莫特罗吸入，孟鲁司特口服，避免接触过敏原"),
    ("急性胃肠炎", "补液、蒙脱石散，必要时抗感染，清淡饮食"),
    ("水痘", "阿昔洛韦抗病毒，炉甘石洗剂外用，隔离至全部疱疹结痂"),
    ("流行性腮腺炎", "对症退热，局部冷敷，隔离治疗，注意并发症"),
    ("细菌性痢疾", "左氧氟沙星抗感染，补液，报传染病卡，注意手卫生"),
]

OTHER_DIAGNOSES = [
    ("急性支气管炎", "止咳化痰对症治疗，必要时抗感染，1周后复诊"),
    ("慢性胃炎", "奥美拉唑抑酸，铝碳酸镁保护胃黏膜，规律饮食"),
    ("原发性高血压2级", "缬沙坦降压，低盐饮食，监测血压，2周后复诊"),
    ("腰椎间盘突出症", "塞来昔布止痛，康复理疗，避免负重"),
    ("2型糖尿病", "二甲双胍控糖，饮食运动干预，监测血糖"),
    ("过敏性皮炎", "氯雷他定抗过敏，卤米松乳膏外用，避免搔抓"),
    ("冠心病稳定型心绞痛", "阿司匹林抗血小板，美托洛尔控制心率，复方丹参滴丸"),
    ("甲状腺功能亢进症", "甲巯咪唑抗甲状腺，定期复查血常规与肝功能"),
]

EXAM_CATALOG = [
    # (检查名称, 注意事项, 楼栋, 楼层, 房间)
    ("胸部CT平扫", "检查前请去除颈部及胸部金属饰品；孕妇禁用；检查时配合屏气", "医技楼", "1F", "影像中心CT-2室"),
    ("血常规+CRP", "无需空腹；采血后按压穿刺点5分钟", "医技楼", "2F", "检验采样大厅3号窗口"),
    ("甲型/乙型流感病毒抗原检测", "鼻咽拭子采样前2小时避免进食；采样时可能有轻微不适", "医技楼", "2F", "检验采样大厅1号窗口"),
    ("新型冠状病毒核酸检测", "采样前30分钟避免进食、吸烟；咽拭子采样", "医技楼", "2F", "检验采样大厅2号窗口"),
    ("C反应蛋白测定", "无需空腹，可与血常规同时采血", "医技楼", "2F", "检验采样大厅3号窗口"),
    ("降钙素原检测", "无需空腹；结果用于鉴别细菌感染", "医技楼", "2F", "检验采样大厅3号窗口"),
    ("肝功能+肾功能", "需空腹8小时以上；检查前一日避免饮酒", "医技楼", "2F", "检验采样大厅4号窗口"),
    ("腹部B超", "需空腹8小时以上；检查前1小时饮水憋尿", "医技楼", "3F", "超声科B超-3室"),
    ("心电图", "检查前静坐休息5分钟；避免剧烈运动", "门诊楼", "2F", "心电图室2室"),
    ("关节X线片", "检查前去除检查部位金属物品；孕妇禁用", "医技楼", "1F", "影像中心DR-1室"),
]

FEVER_EXAM_NAMES = {
    "胸部CT平扫", "血常规+CRP", "甲型/乙型流感病毒抗原检测",
    "新型冠状病毒核酸检测", "C反应蛋白测定", "降钙素原检测",
}

REPORT_CONTENT_BY_EXAM = {
    "胸部CT平扫": ("双肺纹理增粗，右肺下叶见斑片状磨玻璃密度影，边界模糊，考虑炎性病变；"
                "纵隔未见肿大淋巴结，双侧胸腔未见积液。"),
    "血常规+CRP": "白细胞计数 11.2×10^9/L，中性粒细胞百分比 82.4%，C反应蛋白 38.6 mg/L，提示细菌感染可能。",
    "甲型/乙型流感病毒抗原检测": "甲型流感病毒抗原：阳性（+）；乙型流感病毒抗原：阴性（-）。",
    "新型冠状病毒核酸检测": "新型冠状病毒 ORF1ab 基因：阴性；N 基因：阴性。",
    "C反应蛋白测定": "C反应蛋白 26.8 mg/L（参考范围 0-8 mg/L），明显升高。",
    "降钙素原检测": "降钙素原 0.32 ng/mL（参考范围 <0.05 ng/mL），轻度升高，提示细菌感染可能。",
    "肝功能+肾功能": "丙氨酸氨基转移酶 68 U/L（参考 9-50），余项未见明显异常。",
    "腹部B超": "肝、胆、胰、脾、双肾未见明显异常回声。",
    "心电图": "窦性心动过速，心率 112 次/分，ST-T 未见明显异常。",
    "关节X线片": "腰椎生理曲度变直，L4-L5 椎间隙轻度变窄，未见骨折征象。",
}


def _items_json(exam_name: str) -> str:
    """按检查项目生成结构化指标（参考范围与异常标记）。"""
    presets: dict[str, list[tuple[str, str, str, str, str]]] = {
        "血常规+CRP": [
            ("白细胞计数", "11.2", "10^9/L", "3.5-9.5", "HIGH"),
            ("中性粒细胞百分比", "82.4", "%", "40-75", "HIGH"),
            ("淋巴细胞百分比", "13.1", "%", "20-50", "LOW"),
            ("血红蛋白", "138", "g/L", "130-175", "NORMAL"),
            ("血小板计数", "186", "10^9/L", "125-350", "NORMAL"),
            ("C反应蛋白", "38.6", "mg/L", "0-8", "HIGH"),
        ],
        "C反应蛋白测定": [("C反应蛋白", "26.8", "mg/L", "0-8", "HIGH")],
        "降钙素原检测": [("降钙素原", "0.32", "ng/mL", "<0.05", "HIGH")],
        "甲型/乙型流感病毒抗原检测": [
            ("甲型流感病毒抗原", "阳性", "-", "阴性", "HIGH"),
            ("乙型流感病毒抗原", "阴性", "-", "阴性", "NORMAL"),
        ],
        "新型冠状病毒核酸检测": [
            ("ORF1ab 基因", "阴性", "-", "阴性", "NORMAL"),
            ("N 基因", "阴性", "-", "阴性", "NORMAL"),
        ],
        "肝功能+肾功能": [
            ("丙氨酸氨基转移酶", "68", "U/L", "9-50", "HIGH"),
            ("天门冬氨酸氨基转移酶", "42", "U/L", "15-40", "HIGH"),
            ("肌酐", "76", "μmol/L", "57-97", "NORMAL"),
        ],
    }
    if exam_name == "胸部CT平扫":
        return json.dumps(
            [{"itemName": "影像所见", "value": "右肺下叶斑片状磨玻璃影", "unit": "",
              "referenceRange": "未见异常密度影", "abnormalFlag": "HIGH"}],
            ensure_ascii=False,
        )
    if exam_name in presets:
        return json.dumps(
            [
                {"itemName": n, "value": v, "unit": u, "referenceRange": r, "abnormalFlag": f}
                for n, v, u, r, f in presets[exam_name]
            ],
            ensure_ascii=False,
        )
    return json.dumps(
        [{"itemName": "检查结论", "value": "未见明显异常", "unit": "",
          "referenceRange": "未见明显异常", "abnormalFlag": "NORMAL"}],
        ensure_ascii=False,
    )


def _risk_level_for(exam_name: str, abnormal: bool) -> str:
    if exam_name in ("胸部CT平扫",) and abnormal:
        return "HIGH"
    if abnormal:
        return "MEDIUM"
    return "LOW"


def _build_prescriptions(
    appointments: list[Appointment],
    medications: list[Medication],
) -> tuple[list[Prescription], list[PrescriptionItem]]:
    """前 30 张处方属发热门诊；处方明细按发热门诊常用药组合生成。"""
    fever_drugs = medications[:15]
    other_drugs = medications[15:]

    prescriptions: list[Prescription] = []
    items: list[PrescriptionItem] = []
    item_idx = 0

    for idx, appt in enumerate(appointments, start=1):
        is_fever = appt.dept_id == FEVER_DEPT_ID
        pool = fever_drugs if is_fever else other_drugs
        # 发热门诊按“抗病毒 + 退热 + 中成药”组合开方，共 2-3 条明细；其他科室 1-2 条。
        picked = RNG.sample(pool, RNG.randint(2, 3) if is_fever else RNG.randint(1, 2))

        total = Decimal("0.00")
        line_items: list[PrescriptionItem] = []
        for drug in picked:
            item_idx += 1
            quantity = RNG.randint(1, 3)
            quantity = quantity * (5 if is_fever else 2)
            subtotal = _money(float(drug.price) * quantity)
            total += subtotal
            line_items.append(
                PrescriptionItem(
                    item_id=f"ITEM{item_idx:04d}",
                    prescription_id=f"PRE{idx:04d}",
                    drug_id=drug.drug_id,
                    dosage=RNG.choice(["0.5g", "1粒", "2粒", "10ml", "1袋"]),
                    frequency=RNG.choice(["每日三次", "每日两次", "每日一次", "每6小时一次"]),
                    usage_method=RNG.choice(["口服", "口服", "口服", "外用", "吸入"]),
                    meal_relation=RNG.choice(["饭后", "餐前", "餐中", "不限"]),
                    days=RNG.choice([3, 5, 7]),
                    quantity=quantity,
                    subtotal=subtotal,
                )
            )

        insurance_cover = _money(float(total) * (0.6 if is_fever else 0.5))
        prescriptions.append(
            Prescription(
                prescription_id=f"PRE{idx:04d}",
                appointment_id=appt.appointment_id,
                patient_id=appt.patient_id,
                doctor_id=appt.doctor_id,
                total_amount=total,
                insurance_cover=insurance_cover,
                self_pay=_money(float(total) - float(insurance_cover)),
                external_no=f"HIS-PRE-{idx:06d}",
            )
        )
        items.extend(line_items)

    return prescriptions, items


def _build_records(appointments: list[Appointment]) -> list[MedicalRecord]:
    rows: list[MedicalRecord] = []
    for idx, appt in enumerate(appointments, start=1):
        is_fever = appt.dept_id == FEVER_DEPT_ID
        diagnosis, advice = RNG.choice(FEVER_DIAGNOSES if is_fever else OTHER_DIAGNOSES)
        rows.append(
            MedicalRecord(
                record_id=f"MR{idx:04d}",
                patient_id=appt.patient_id,
                appointment_id=appt.appointment_id,
                doctor_id=appt.doctor_id,
                dept_id=appt.dept_id,
                visit_date=appt.appt_date,
                chief_complaint=appt.chief_complaint,
                diagnosis=diagnosis,
                treatment_advice=advice,
                raw_text=(
                    f"主诉：{appt.chief_complaint}。\n"
                    f"现病史：患者{appt.appt_date:%Y-%m-%d}来诊，"
                    f"{'有明确发热患者接触史，' if is_fever else ''}"
                    f"查体见{'咽部充血，双侧扁桃体I度肿大' if is_fever else '腹软，无压痛'}。\n"
                    f"辅助检查：{'甲流抗原阳性' if is_fever and idx % 3 == 0 else '待回报'}。\n"
                    f"诊断：{diagnosis}。\n处理意见：{advice}"
                ),
                external_no=f"HIS-MR-{idx:06d}",
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# 检查与报告
# --------------------------------------------------------------------------- #


def _build_exams(appointments: list[Appointment]) -> list[Exam]:
    """发热门诊的检查单排在最前，覆盖胸部CT、血常规、流感/新冠病原学检测。"""
    fever_catalog = [e for e in EXAM_CATALOG if e[0] in FEVER_EXAM_NAMES]
    other_catalog = [e for e in EXAM_CATALOG if e[0] not in FEVER_EXAM_NAMES]

    rows: list[Exam] = []
    status_cycle = ["REPORTED", "REPORTED", "REPORTED", "WAIT_REPORT", "WAIT_EXAM", "WAIT_PAY"]
    for idx, appt in enumerate(appointments, start=1):
        is_fever = appt.dept_id == FEVER_DEPT_ID
        name, precautions, building, floor, room = RNG.choice(
            fever_catalog if is_fever else other_catalog
        )
        status = RNG.choice(status_cycle)
        queue_no = f"{'F' if is_fever else 'A'}{200 + idx}"
        # 叫号信息仅对在检查队列中的检查单有意义（设计文档 4.4：实时性强的字段建议轮询 HIS）
        in_queue = status in ("WAIT_EXAM", "WAIT_REPORT")
        people_ahead = RNG.randint(0, 8) if in_queue else None
        rows.append(
            Exam(
                exam_id=f"EXAM{idx:04d}",
                patient_id=appt.patient_id,
                appointment_id=appt.appointment_id,
                exam_name=name,
                exam_status=status,
                precautions=precautions,
                building=building,
                floor=floor,
                room=room,
                queue_no=queue_no,
                current_no=f"{'F' if is_fever else 'A'}{180 + (idx % 20)}" if in_queue else None,
                people_ahead=people_ahead,
                estimated_wait_minutes=people_ahead * 6 if people_ahead is not None else None,
                external_no=f"HIS-EXAM-{idx:06d}",
            )
        )
    return rows


def _build_exam_reports(
    exams: list[Exam], appointments: list[Appointment]
) -> list[ExamReport]:
    visit_date_by_appointment = {a.appointment_id: a.appt_date for a in appointments}
    rows: list[ExamReport] = []
    for idx, exam in enumerate(exams, start=1):
        reported = exam.exam_status == "REPORTED"
        visit_date = visit_date_by_appointment.get(exam.appointment_id, TODAY)
        content = REPORT_CONTENT_BY_EXAM.get(exam.exam_name, "检查未见明显异常。")
        abnormal = any(
            flag in content for flag in ("阳性", "升高", "增粗", "模糊", "变窄", "增快")
        )
        rows.append(
            ExamReport(
                report_id=f"RPT{idx:04d}",
                exam_id=exam.exam_id,
                report_status="REPORTED" if reported else "WAIT_REPORT",
                report_content=content if reported else None,
                items_json=_items_json(exam.exam_name) if reported else None,
                report_image_url=(
                    f"https://cdn.demo-hospital.local/report/{exam.exam_id}.jpg" if reported else None
                ),
                report_time=(
                    datetime.combine(visit_date, time(15, 20)) + timedelta(minutes=idx % 60)
                    if reported
                    else None
                ),
                risk_level=_risk_level_for(exam.exam_name, abnormal) if reported else None,
                ai_analysis=(
                    f"AI解读：{content}"
                    f"建议结合临床症状与医生面诊综合判断，"
                    f"{'指标存在异常，建议尽快复诊' if abnormal else '指标基本正常，按医嘱随访即可'}。"
                    if reported
                    else None
                ),
                external_no=f"HIS-RPT-{idx:06d}",
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# 账单与支付
# --------------------------------------------------------------------------- #

PAY_CHANNELS = ["WECHAT", "ALIPAY"]


def _treatment_bill(
    idx: int,
    *,
    patient_id: str,
    appointment_id: Optional[str],
    title: str,
    related_type: str,
    related_id: str,
    amount: Decimal,
    visit_date: date,
    unpaid: bool,
) -> Bill:
    """构造一条就诊缴费账单。

    待缴费的检查单要配一张未缴费账单（`unpaid=True`）：没有它，「待缴费 → 待检查」
    这条流程（接口文档 API-17 举的例子）就没有数据可演示。
    """
    cover, self_pay = _split_amount(amount, 0.5)
    return Bill(
        bill_id=f"BILL{idx:04d}",
        patient_id=patient_id,
        appointment_id=appointment_id,
        bill_type="TREATMENT",
        bill_title=title,
        related_type=related_type,
        related_id=related_id,
        amount=amount,
        insurance_cover=cover,
        self_pay=self_pay,
        pay_status="UNPAID" if unpaid else "PAID",
        paid_at=None if unpaid else datetime.combine(visit_date, time(16, idx % 60)),
        invoice_no=None if unpaid else f"INV{visit_date:%Y%m%d}{idx:05d}",
        external_no=f"HIS-BILL-{idx:06d}",
    )


def _build_bills(
    appointments: list[Appointment],
    exams: list[Exam],
    prescriptions: list[Prescription],
) -> list[Bill]:
    """前 40 条为挂号缴费账单，后若干条为检查/处方引起的就诊缴费账单。"""
    route_by_appointment = {a.appointment_id: a.appt_date for a in appointments}
    rows: list[Bill] = []
    idx = 0

    for appt in appointments[:40]:
        idx += 1
        amount = _money(50 if appt.dept_id == FEVER_DEPT_ID else 20)
        if appt.appointment_status == "CANCELED":
            pay_status, paid_at, invoice_no = "REFUNDED", None, None
        elif appt.appointment_status == "BOOKED":
            pay_status, paid_at, invoice_no = "UNPAID", None, None
        else:
            paid_at = datetime.combine(appt.appt_date, time(7 + idx % 4, (idx * 7) % 60))
            pay_status, invoice_no = "PAID", f"INV{appt.appt_date:%Y%m%d}{idx:05d}"
        cover, self_pay = _split_amount(amount, 0.6)
        rows.append(
            Bill(
                bill_id=f"BILL{idx:04d}",
                patient_id=appt.patient_id,
                appointment_id=appt.appointment_id,
                bill_type="REGISTRATION",
                bill_title="门诊挂号费",
                related_type=None,
                related_id=None,
                amount=amount,
                insurance_cover=cover,
                self_pay=self_pay,
                pay_status=pay_status,
                paid_at=paid_at,
                invoice_no=invoice_no,
                external_no=f"HIS-BILL-{idx:06d}",
            )
        )

    # 后 10 条为就诊缴费账单：检查费与处方药费交替，凑满 50 条。
    # 已取消的挂号没有实际就诊，不能产生就诊缴费账单。
    canceled = {
        a.appointment_id for a in appointments if a.appointment_status == "CANCELED"
    }
    visited_exams = [e for e in exams if e.appointment_id not in canceled]
    visited_prescriptions = [
        p for p in prescriptions if p.appointment_id not in canceled
    ]
    billed_exam_ids: set[str] = set()
    for exam, prescription in zip(visited_exams[:5], visited_prescriptions[:5]):
        for source, is_exam in ((exam, True), (prescription, False)):
            idx += 1
            if is_exam:
                amount = _money(280.00)
                title, related_type, related_id = f"{exam.exam_name}检查费", "EXAM", exam.exam_id
                patient_id, appointment_id = exam.patient_id, exam.appointment_id
                billed_exam_ids.add(exam.exam_id)
            else:
                amount = prescription.total_amount
                title, related_type, related_id = "门诊处方药费", "PRESCRIPTION", prescription.prescription_id
                patient_id, appointment_id = prescription.patient_id, prescription.appointment_id
            rows.append(
                _treatment_bill(
                    idx,
                    patient_id=patient_id,
                    appointment_id=appointment_id,
                    title=title,
                    related_type=related_type,
                    related_id=related_id,
                    amount=amount,
                    visit_date=route_by_appointment.get(appointment_id, TODAY),
                    # 待缴费的检查单，账单也得是待缴费的，否则状态自相矛盾
                    unpaid=is_exam and exam.exam_status == "WAIT_PAY",
                )
            )

    # 其余待缴费的检查单补一张未缴费账单：原先只有 6 条待缴费检查单，
    # 其中 5 条完全没有账单，导致「待缴费列表」是空的。
    for exam in visited_exams:
        if exam.exam_status != "WAIT_PAY" or exam.exam_id in billed_exam_ids:
            continue
        idx += 1
        rows.append(
            _treatment_bill(
                idx,
                patient_id=exam.patient_id,
                appointment_id=exam.appointment_id,
                title=f"{exam.exam_name}检查费",
                related_type="EXAM",
                related_id=exam.exam_id,
                amount=_money(280.00),
                visit_date=route_by_appointment.get(exam.appointment_id, TODAY),
                unpaid=True,
            )
        )

    return rows


def _build_payments(bills: list[Bill], users: list[User]) -> list[Payment]:
    """已缴费账单各生成一条成功支付单，另有少量失败/支付中记录（重试场景）。"""
    patient_users = [u for u in users if u.role == "PATIENT"]
    rows: list[Payment] = []
    idx = 0

    for bill in bills:
        if bill.pay_status not in ("PAID", "REFUNDED"):
            continue
        idx += 1
        paid_at = bill.paid_at or datetime.combine(TODAY, time(10, 0))
        rows.append(
            Payment(
                payment_id=f"PAY{idx:04d}",
                bill_id=bill.bill_id,
                user_id=patient_users[idx % len(patient_users)].user_id,
                channel=RNG.choice(PAY_CHANNELS),
                channel_trade_no=f"42000{paid_at:%Y%m%d%H%M%S}{idx:03d}",
                pay_status="SUCCESS" if bill.pay_status == "PAID" else "CLOSED",
                amount=bill.amount,
                pay_params=json.dumps(
                    {"prepay_id": f"wx{idx:020d}", "trade_type": "JSAPI"},
                    ensure_ascii=False,
                ),
                expire_time=paid_at + timedelta(minutes=15),
                paid_at=paid_at if bill.pay_status == "PAID" else None,
                callback_at=paid_at + timedelta(seconds=3) if bill.pay_status == "PAID" else None,
            )
        )

    # 补充未成功/支付中的支付单（失败重试与超时关闭场景），把支付单凑满 50 条
    extra_status = ["FAIL", "PAYING", "FAIL", "CLOSED", "PAYING"]
    retry = 0
    while len(rows) < 50 and retry < 40:
        status = extra_status[retry % len(extra_status)]
        idx += 1
        retry += 1
        bill = bills[(idx + 2) % len(bills)]
        rows.append(
            Payment(
                payment_id=f"PAY{idx:04d}",
                bill_id=bill.bill_id,
                user_id=patient_users[(idx + 3) % len(patient_users)].user_id,
                channel=RNG.choice(PAY_CHANNELS),
                channel_trade_no=None if status in ("FAIL", "PAYING") else f"42000{idx:017d}",
                pay_status=status,
                amount=bill.amount,
                pay_params=json.dumps(
                    {"code_url": f"weixin://wxpay/bizpayurl?pr=DEMO{idx:03d}"}
                ),
                expire_time=datetime.combine(TODAY, time(23, 59)),
                paid_at=None,
                callback_at=datetime.combine(TODAY, time(11, idx % 60, 30)) if status == "FAIL" else None,
            )
        )

    return rows


# --------------------------------------------------------------------------- #
# AI 会话与消息
# --------------------------------------------------------------------------- #

FEVER_FOLLOW_UPS = [
    "体温38.5℃算高热吗？需要马上吃退烧药吗？",
    "家里有老人和小孩，我需要单独隔离吗？",
    "奥司他韦要吃几天？停药后还会传染吗？",
    "核酸检测阴性是不是就不是流感了？",
    "发热期间可以洗澡吗？饮食上要注意什么？",
    "什么情况下必须回医院复诊？",
]

TRIAGE_SOURCES = [
    ["《发热门诊建设与管理规范（2024年版）》"],
    ["《流行性感冒诊疗方案（2025年版）》"],
    ["《新型冠状病毒感染诊疗方案（试行第十版）》"],
    ["《社区获得性肺炎诊断和治疗指南》"],
    ["《成人流行性感冒抗病毒治疗专家共识》"],
]

DISCLAIMER = "本建议由AI辅助生成，仅供参考，不能替代医生面诊，如有不适请及时就医。"


def _build_ai_sessions(users: list[User], patients: list[Patient]) -> list[AiSession]:
    """前 25 个会话为发热门诊预诊分诊，排在各表最上方。"""
    patient_accounts = [u for u in users if u.role == "PATIENT"]
    rows: list[AiSession] = []

    for idx in range(1, 51):
        account = patient_accounts[(idx - 1) % len(patient_accounts)]
        if idx <= 25:
            scene, department = "PRE_CONSULT", FEVER_DEPT_NAME
        elif idx <= 35:
            scene, department = "PRE_CONSULT", RNG.choice(DEPT_NAMES[1:20])
        elif idx <= 43:
            scene, department = "INSURANCE", None
        elif idx <= 47:
            scene, department = "REPORT", None
        else:
            scene, department = "RECORD", None
        rows.append(
            AiSession(
                session_id=f"SES{idx:04d}",
                user_id=account.user_id,
                patient_id=patients[(idx - 1) % len(patients)].patient_id,
                scene=scene,
                department=department,
                message_count=1,
                status=1,
            )
        )
    return rows


def _triage_card(department: str) -> str:
    detail = DEPT_DETAILS.get(department)
    if detail:
        building, floor_position, addr, _ = detail
        location = f"{addr}"
    else:
        building, floor_position, location = "门诊楼", "", department
    return json.dumps(
        {
            "department": department,
            "building": building,
            "location": location,
            "floorPosition": floor_position,
            "buttonAction": "REGISTER",
        },
        ensure_ascii=False,
    )


def _build_ai_messages(sessions: list[AiSession]) -> list[AiMessage]:
    """每条消息承载一轮完整问答（content 记用户输入，reply 记 AI 回复）。"""
    rows: list[AiMessage] = []
    for idx, session in enumerate(sessions, start=1):
        is_fever = idx <= 25
        if is_fever:
            complaint = RNG.choice(FEVER_CHIEF_COMPLAINTS)
            rows.append(
                AiMessage(
                    message_id=f"MSG{idx:04d}",
                    session_id=session.session_id,
                    role="bot",
                    input_type=RNG.choice(["TEXT", "VOICE", "IMAGE"]),
                    content=complaint,
                    reply=(
                        f"根据您描述的“{complaint}”，结合发热门诊分诊标准，"
                        f"建议前往**发热门诊**就诊，已完成预检分诊并为您推荐号源。\n"
                        f"就诊提示：请全程佩戴医用外科口罩，避免乘坐公共交通工具；"
                        f"到院后先至分诊台测量体温并如实告知流行病学史。"
                        f"预计需完成血常规、甲流/乙流抗原或胸部CT检查，请预留2小时。"
                    ),
                    triage_card=_triage_card(FEVER_DEPT_NAME),
                    risk_warning=(
                        "若出现体温≥39℃持续不退、呼吸困难、胸痛、意识模糊或抽搐，"
                        "请立即前往急诊医学科抢救区，不要在发热门诊排队等候。"
                        if idx % 3 == 0
                        else None
                    ),
                    next_question=RNG.choice(FEVER_FOLLOW_UPS),
                    sources=json.dumps(RNG.choice(TRIAGE_SOURCES), ensure_ascii=False),
                    disclaimer=DISCLAIMER,
                )
            )
        else:
            rows.append(
                AiMessage(
                    message_id=f"MSG{idx:04d}",
                    session_id=session.session_id,
                    role="user",
                    input_type=RNG.choice(["TEXT", "VOICE"]),
                    content={
                        "PRE_CONSULT": RNG.choice(OTHER_CHIEF_COMPLAINTS),
                        "INSURANCE": "职工医保门诊报销比例是多少？异地就医需要备案吗？",
                        "REPORT": "我的胸部CT报告上写“磨玻璃密度影”，严重吗？",
                        "RECORD": "请帮我解读一下这份既往病历里的诊断和用药。",
                    }[session.scene],
                    reply=None,
                    triage_card=None,
                    risk_warning=None,
                    next_question=None,
                    sources=None,
                    disclaimer=None,
                )
            )
    return rows


def _build_reminders(
    prescriptions: list[Prescription],
    items: list[PrescriptionItem],
    medications: list[Medication],
) -> list[MedicationReminder]:
    """按处方明细生成服药计划，发热门诊处方的提醒排在最前。"""
    drug_by_id = {m.drug_id: m for m in medications}
    items_by_prescription: dict[str, list[PrescriptionItem]] = {}
    for item in items:
        items_by_prescription.setdefault(item.prescription_id, []).append(item)

    take_times = ["08:00", "12:30", "18:30", "22:00"]
    rows: list[MedicationReminder] = []
    idx = 0

    for prescription in prescriptions:
        if len(rows) >= 50:
            break
        for item in items_by_prescription.get(prescription.prescription_id, []):
            idx += 1
            drug = drug_by_id[item.drug_id]
            conflict = None
            if drug.drug_name in ("阿司匹林肠溶片", "复方丹参滴丸", "血府逐瘀胶囊"):
                conflict = "与抗凝/抗血小板药物合用可能增加出血风险，请告知医生正在服用的全部药物"
            elif drug.drug_name in ("阿莫西林胶囊", "头孢克肟分散片", "头孢克洛干混悬剂"):
                conflict = "与双歧杆菌四联活菌片同服会降低活菌疗效，两药需间隔2小时以上"
            rows.append(
                MedicationReminder(
                    reminder_id=f"REM{idx:04d}",
                    prescription_id=prescription.prescription_id,
                    patient_id=prescription.patient_id,
                    drug_id=item.drug_id,
                    dose=item.dosage,
                    take_time=take_times[(idx - 1) % len(take_times)],
                    meal_relation=item.meal_relation,
                    plan_date=TODAY + timedelta(days=(idx - 1) % 5),
                    taken_status=RNG.choice([0, 0, 1]),
                    conflict_warning=conflict,
                )
            )
    return rows[:50]


# --------------------------------------------------------------------------- #
# 短信验证码与操作日志
# --------------------------------------------------------------------------- #

SMS_SCENES = ["REGISTER", "LOGIN", "RESET_PWD"]

LOG_ACTIONS = [
    ("LOGIN", "账号登录成功"),
    ("AI_CHAT", "发起AI预诊会话并完成分诊"),
    ("APPT_CREATE", "创建挂号预约"),
    ("PAY", "完成账单支付"),
    ("REPORT_QUERY", "查询检查报告"),
    ("RECORD_QUERY", "查询既往病历"),
    ("MED_REMINDER", "生成用药提醒计划"),
    ("LOGOUT", "退出登录"),
]


def _build_sms_codes(users: list[User]) -> list[SmsCode]:
    rows: list[SmsCode] = []
    for idx, account in enumerate(users, start=1):
        sent_at = datetime.combine(TODAY, time(8, 0)) + timedelta(minutes=idx * 7)
        rows.append(
            SmsCode(
                sms_id=f"SMS{idx:04d}",
                phone=account.account,
                code=f"{RNG.randint(0, 999999):06d}",
                scene=SMS_SCENES[idx % len(SMS_SCENES)],
                expired_at=sent_at + timedelta(minutes=5),
                used_status=RNG.choice([1, 1, 0]),
            )
        )
    return rows


def _build_operation_logs(
    users: list[User],
    patients: list[Patient],
    appointments: list[Appointment],
    sessions: list[AiSession],
) -> list[OperationLog]:
    """先写发热门诊账号与发热门诊业务对象的日志，使其排在日志表最上方。"""
    fever_accounts = users[:FEVER_DOCTOR_COUNT]
    fever_appointments = [a for a in appointments if a.dept_id == FEVER_DEPT_ID]
    fever_sessions = sessions[:25]
    patient_accounts = [u for u in users if u.role == "PATIENT"]

    rows: list[OperationLog] = []
    idx = 0

    def add(user_id: str | None, action: str, target_type: str | None,
            target_id: str | None, detail: str, ip: str) -> None:
        nonlocal idx
        idx += 1
        rows.append(
            OperationLog(
                log_id=f"LOG{idx:04d}",
                user_id=user_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                detail=detail,
                ip=ip,
            )
        )

    # 发热门诊医生的登录/接诊日志
    for i, account in enumerate(fever_accounts, start=1):
        add(account.user_id, "LOGIN", "USER", account.user_id,
            f"发热门诊医生 {account.name} 登录工作站，终端：诊室{i}号机",
            f"192.168.21.{100 + i}")

    # 发热门诊患者的预诊与挂号日志
    for i, session in enumerate(fever_sessions, start=1):
        account_id = session.user_id
        detail = "AI预诊分诊会话，推荐科室：发热门诊"
        add(account_id, "AI_CHAT", "AI_SESSION", session.session_id, detail,
            f"10.20.33.{i + 10}")

    for i, appt in enumerate(fever_appointments, start=1):
        if len(rows) >= 50:
            break
        add(appt.user_id, "APPT_CREATE", "APPOINTMENT", appt.appointment_id,
            f"发热门诊挂号成功，医生 {appt.doctor_id}，时段 {appt.time_slot}，"
            f"来源 {'AI自动挂号' if appt.source == 'AI_AUTO' else '手动挂号'}",
            f"10.20.33.{i + 40}")

    # 其余账号的常规操作，补满 50 条
    for i, account in enumerate(patient_accounts):
        if len(rows) >= 50:
            break
        action, memo = LOG_ACTIONS[i % len(LOG_ACTIONS)]
        add(account.user_id, action, "USER", account.user_id, memo,
            f"10.20.44.{i + 10}")

    for i, account in enumerate(users):
        if len(rows) >= 50:
            break
        add(account.user_id, "LOGOUT", "USER", account.user_id, "会话超时自动退出",
            f"192.168.21.{150 + i}")

    return rows[:50]


# --------------------------------------------------------------------------- #
# 建库 / 建表 / 灌数据
# --------------------------------------------------------------------------- #


def ensure_database(url_str: str) -> str:
    """按连接串自动创建目标库（不存在时），返回库名。"""
    url = make_url(url_str)
    db_name = url.database
    if not db_name:
        raise SystemExit("连接串中未指定数据库名，无法自动建库")

    # 注意：URL.set(database=None) 在 SQLAlchemy 2.0 中是空操作（None 表示“保持不变”），
    # 建库阶段必须用 URL.create 重新构造一个不带库名的连接串。
    server_url = URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        query=dict(url.query),
    )
    server_engine = create_engine(
        server_url, pool_pre_ping=True, connect_args={"connect_timeout": 8}
    )
    with server_engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
        )
    server_engine.dispose()
    return db_name


def truncate_all(engine: Engine) -> None:
    """按依赖逆序清空全部业务表，使脚本可重复执行。"""
    table_names = [t.name for t in reversed(Base.metadata.sorted_tables)]
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for name in table_names:
            conn.execute(text(f"TRUNCATE TABLE `{name}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


def seed(session: Session, skip_tables: set[str] | None = None) -> dict[str, int]:
    """按依赖顺序写入演示数据，返回本次实际写入的各表行数。

    skip_tables 中的表已有数据，直接跳过、不做任何写入。
    """
    skip = skip_tables or set()
    departments = _build_departments()
    doctors = _build_doctors(departments)
    users = _build_users(doctors)
    patients = _build_patients(users)
    schedules = _build_schedules(doctors, departments)
    appointments = _build_appointments(users, patients, schedules)
    medications = _build_medications()
    # 已取消的挂号未实际就诊，不产生病历、检查与处方
    visited = [a for a in appointments if a.appointment_status != "CANCELED"]
    prescriptions, prescription_items = _build_prescriptions(visited, medications)
    records = _build_records(visited)
    exams = _build_exams(visited)
    reports = _build_exam_reports(exams, visited)
    bills = _build_bills(appointments, exams, prescriptions)
    payments = _build_payments(bills, users)
    sessions = _build_ai_sessions(users, patients)
    messages = _build_ai_messages(sessions)
    reminders = _build_reminders(prescriptions, prescription_items, medications)
    sms_codes = _build_sms_codes(users)
    logs = _build_operation_logs(users, patients, appointments, sessions)

    ordered: list[tuple[type, list]] = [
        (Department, departments),
        (Doctor, doctors),
        (User, users),
        (Patient, patients),
        (Schedule, schedules),
        (Appointment, appointments),
        (Medication, medications),
        (Prescription, prescriptions),
        (PrescriptionItem, prescription_items),
        (Bill, bills),
        (Payment, payments),
        (Exam, exams),
        (ExamReport, reports),
        (MedicalRecord, records),
        (AiSession, sessions),
        (AiMessage, messages),
        (MedicationReminder, reminders),
        (SmsCode, sms_codes),
        (OperationLog, logs),
    ]

    # 逐表提交：SQLAlchemy 的 flush 只按 relationship() 排序，模型里只有裸外键时
    # 不会自动保证父表先插入，因此这里按上面的依赖顺序显式逐表落库。
    counts: dict[str, int] = {}
    for model, rows in ordered:
        if model.__tablename__ in skip:
            continue
        session.add_all(rows)
        session.commit()
        counts[model.__tablename__] = len(rows)

    # t_appointment.bill_id 与 t_bill.appointment_id 互指（建表环路），
    # 预约侧的账单号必须等账单落库后再回填，否则外键校验不通过。
    # 两侧任一被跳过时都不能回填：回填值来自本次内存里生成的账单编号，
    # 账单没落库的话会把已有预约指向不存在的账单行。
    if "t_appointment" not in skip and "t_bill" not in skip:
        registrations = {
            b.appointment_id: b.bill_id for b in bills if b.bill_type == "REGISTRATION"
        }
        for appt_id, bill_id in registrations.items():
            session.execute(
                update(Appointment)
                .where(Appointment.appointment_id == appt_id)
                .values(bill_id=bill_id)
            )
        session.commit()

    return counts


def report(engine: Engine, written: dict[str, int]) -> None:
    """打印各表当前行数与本次写入情况，并核对发热门诊数据是否排在各表最上方。"""
    with engine.connect() as conn:
        print("\n各表当前行数（本次写入 / 库中合计）：")
        total = 0
        for table in [t.name for t in Base.metadata.sorted_tables]:
            live = conn.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar() or 0
            total += live
            n = written.get(table)
            print(f"  {table:<24}{live:>5} 行   {'本次 +' + str(n) if n else '本次跳过'}")
        print(f"  {'合计':<24}{total:>5} 行")

        print("\n发热门诊数据位置核对（不带 ORDER BY 取首行）：")
        checks = [
            ("t_department", "dept_name", "dept_id"),
            ("t_doctor", "name", "doctor_id"),
            ("t_appointment", "chief_complaint", "appointment_id"),
            ("t_medical_record", "diagnosis", "record_id"),
            ("t_exam", "exam_name", "exam_id"),
            ("t_prescription", "prescription_id", "prescription_id"),
            ("t_bill", "bill_title", "bill_id"),
            ("t_medication", "drug_name", "drug_id"),
            ("t_ai_session", "department", "session_id"),
            ("t_operation_log", "detail", "log_id"),
        ]
        for table, shown, key in checks:
            row = conn.execute(text(f"SELECT `{key}`, `{shown}` FROM `{table}` LIMIT 1")).first()
            if row:
                print(f"  {table:<20} 首行 {row[0]} → {row[1]}")


def table_row_counts(engine: Engine, table_names: list[str]) -> dict[str, int]:
    """读取各表当前行数。"""
    with engine.connect() as conn:
        return {
            name: conn.execute(text(f"SELECT COUNT(*) FROM `{name}`")).scalar() or 0
            for name in table_names
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="建表并写入智慧医疗演示数据（已存在的表不重建，已有数据的表不重灌）"
    )
    parser.add_argument("--url", default=DATABASE_URL, help="数据库连接串")
    parser.add_argument(
        "--reset", action="store_true", help="先清空 19 张业务表再重灌（会丢失既有数据）"
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不连接数据库")
    args = parser.parse_args()

    url = make_url(args.url)
    print(f"目标数据库：{url.host}:{url.port}/{url.database}")
    needed = [t.name for t in Base.metadata.sorted_tables]
    print(f"设计文档共 {len(needed)} 张表")
    if args.dry_run:
        print(f"  {', '.join(needed)}")
        print("dry-run：未连接数据库，未做任何变更。")
        return

    db_name = ensure_database(args.url)
    engine = create_engine(args.url, pool_pre_ping=True, pool_recycle=3600)
    print(f"已确认数据库存在：{db_name}")

    before = set(inspect(engine).get_table_names())
    Base.metadata.create_all(engine)  # 只建缺失的表，已存在的一律不动
    created = sorted(set(inspect(engine).get_table_names()) - before)
    present = sorted(set(needed) & before)
    if created:
        print(f"新建 {len(created)} 张表：{', '.join(created)}")
    else:
        print("没有需要新建的表。")
    print(f"已存在 {len(present)} 张表，跳过重建。")

    if args.reset:
        truncate_all(engine)
        print("--reset：已清空 19 张业务表。")

    live = table_row_counts(engine, needed)
    non_empty = [t for t in needed if live[t] > 0]
    empty = [t for t in needed if live[t] == 0]

    if non_empty:
        print(f"\n以下 {len(non_empty)} 张表已有数据，跳过写入（原数据保留）：")
        for t in non_empty:
            print(f"  {t:<24}{live[t]:>5} 行")

    if not empty:
        print("\n所有表都已有数据，无需插入。")
        report(engine, {})
        engine.dispose()
        return

    print(f"\n以下 {len(empty)} 张表为空，将写入演示数据：")
    print(f"  {', '.join(empty)}")

    # 空表若引用已有数据的父表，而父表行号又不是本脚本生成的，插入会撞外键，这里先提醒
    risky = [
        (t.name, fk.column.table.name)
        for t in Base.metadata.sorted_tables
        if t.name in empty
        for fk in t.foreign_keys
        if fk.column.table.name in non_empty
    ]
    if risky:
        print("\n⚠ 以下空表的外键指向已存在数据的表，")
        print("  若库中父行编号不是本脚本的生成规则（DEPT0001/DOC0001/…），插入会报外键错误：")
        for child, parent in risky:
            print(f"    {child} → {parent}")

    with Session(engine) as session:
        written = seed(session, skip_tables=set(non_empty))

    report(engine, written)
    engine.dispose()


if __name__ == "__main__":
    main()
