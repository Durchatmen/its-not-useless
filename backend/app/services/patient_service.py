"""就诊人业务逻辑（《接口文档》3.2：API-04 ~ API-07）。

分层约定与 exams / bills 一致：本模块只依赖 SQLAlchemy 会话，不感知 HTTP；
错误统一以 `PatientError` 抛出，由 `api/v1/patients.py` 转成统一信封。

三处需要留意的实现取舍：

1. **身份证号进出都过加解密**。库里存的是确定性密文（app/core/crypto，`enc:v1:` 前缀），
   而接口文档 API-04 要求返回「脱敏后的身份证号」。直接对密文调 mask_idcard 会得到
   一串无意义的「enc:****1kQg」，所以出口必须 `try_decrypt_text` 还原明文后再脱敏。
   入库方向同理：`encrypt_text` 幂等，重复加密不会出问题。

2. **删除是软删**。t_patient 加了 is_deleted 列（见 app/models/patient.py 的说明），
   列表与详情一律过滤 is_deleted=0。已软删的行仍占着 uk_user_idcard 唯一键，所以
   「删掉同一个就诊人再加回来」不能走新增分支，必须复活原行（见 create_patient）。

3. **isDefault 唯一**。接口文档没明说，但「默认就诊人」语义上必须唯一 —— 否则下单时
   取默认就诊人会拿到不确定的结果。因此任何一次把某行置为默认，都会先把同账号其它
   就诊人置 0（`_clear_other_defaults`）。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import crypto
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.schemas.patient import (
    RELATION_DESC,
    PatientCreateData,
    PatientCreateRequest,
    PatientListItem,
    PatientListData,
    PatientUpdateRequest,
)
from app.utils.id_gen import next_id
from app.utils.mask import mask_idcard, mask_name, mask_phone
from app.utils.validators import is_valid_idcard

# 未完成的挂号单状态：存在这些状态的挂号单时不允许删除就诊人（接口文档 API-07）
UNFINISHED_APPOINTMENT_STATUS: tuple[str, ...] = ("BOOKED", "CHECKED_IN")

# 单账号就诊人上限。接口文档没规定，这里只是防御性兜底，避免被脚本灌爆一张表
MAX_PATIENTS_PER_USER = 50


class PatientError(Exception):
    """就诊人模块业务错误。

    code 取接口文档 2.5 通用错误码表：1002 账号/记录已存在、2002 挂号单状态不允许、
    2003 就诊人信息校验失败、4003 无权访问该资源。
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #


def _to_item(patient: Patient) -> PatientListItem:
    """ORM → 列表项，出口统一脱敏。

    idcard 先解密再脱敏：库里是 `enc:v1:` 密文，直接脱敏会丢掉「这是谁的身份证」这一
    语义（前端要靠它比对用户手输的号码）。解密失败（如 secret_key 换过）时
    try_decrypt_text 返回 None，此时宁可让该字段为空，也不把密文片段当证件号返回。
    """
    plain_idcard = crypto.try_decrypt_text(patient.idcard)
    return PatientListItem(
        patientId=patient.patient_id,
        name=mask_name(patient.name),
        idcard=mask_idcard(plain_idcard),
        phone=mask_phone(patient.phone),
        gender=patient.gender,
        birthDate=patient.birth_date,
        relation=patient.relation,
        relationDesc=RELATION_DESC.get(patient.relation, patient.relation),
        bloodType=patient.blood_type,
        allergyHistory=patient.allergy_history,
        medicalHistory=patient.medical_history,
        isDefault=bool(patient.is_default),
    )


def _get_patient(session: Session, patient_id: str, user_id: str) -> Patient:
    """取就诊人并校验归属（同时排除已软删的行）。

    就诊人不存在、不属于当前账号、已被删除三种情况返回同一个 4003：既避免用错误码
    差异暴露「这个编号存在」，也省掉一次多余的枚举风险（与 exam_service._get_exam 同理由）。
    """
    patient = session.scalars(
        select(Patient).where(
            Patient.patient_id == patient_id,
            Patient.user_id == user_id,
            Patient.is_deleted == 0,
        )
    ).first()
    if patient is None:
        raise PatientError(4003, "就诊人不存在或无权访问")
    return patient


def _find_by_idcard(session: Session, user_id: str, idcard: str) -> Optional[Patient]:
    """按身份证号在**当前账号下**查重（含已软删的行）。

    身份证号是确定性密文，所以要拿 `equality_candidates` 的两种形态一起匹配：
    密文形态是本模块写进去的，明文形态用于兼容 seed 等历史数据。
    唯一键 uk_user_idcard 是 (user_id, idcard)，故不同账号之间互不干扰。
    """
    candidates = crypto.equality_candidates(idcard)
    if not candidates:
        return None
    return session.scalars(
        select(Patient).where(Patient.user_id == user_id, Patient.idcard.in_(candidates))
    ).first()


def _clear_other_defaults(session: Session, user_id: str, keep_id: Optional[str] = None) -> None:
    """把同账号下其它就诊人的 is_default 置 0，保证默认就诊人唯一。

    keep_id 为 None 时即「全部清空」—— 用户把当前默认就诊人的 isDefault 改成 false 时，
    账号会短暂处于「没有默认就诊人」的状态。这是允许的：前端取默认值时本来就要处理空值。
    """
    conditions = [Patient.user_id == user_id, Patient.is_default == 1]
    if keep_id is not None:
        conditions.append(Patient.patient_id != keep_id)
    session.execute(update(Patient).where(*conditions).values(is_default=0))


def _validate_idcard(idcard: str) -> str:
    """身份证号校验：18 位 + 校验位合法。

    校验位不合法返回 2003（就诊人信息校验失败）而不是 4001：4001 留给「字段缺失/类型不对」
    这类请求体层面的问题，身份证号本身格式对但号码不真，属于业务校验。
    """
    normalized = (idcard or "").strip().upper()
    if not is_valid_idcard(normalized, checksum=True):
        raise PatientError(2003, "身份证号校验未通过，请核对后重试")
    return normalized


# --------------------------------------------------------------------------- #
# API-04 查询就诊人列表
# --------------------------------------------------------------------------- #


def list_patients(
    session: Session,
    *,
    user_id: str,
    keyword: Optional[str] = None,
    page_num: int = 1,
    page_size: int = 50,
) -> PatientListData:
    """查询当前账号绑定的全部就诊人（接口文档 API-04）。

    keyword 按姓名模糊匹配。姓名在库里是明文（只有身份证号加密），所以直接 like。
    默认就诊人排最前，其余按创建时间正序 —— 与前端「默认就诊人置顶」的展示预期一致。
    """
    conditions = [Patient.user_id == user_id, Patient.is_deleted == 0]
    if keyword and keyword.strip():
        conditions.append(Patient.name.like(f"%{keyword.strip()}%"))

    total = session.scalar(select(func.count()).select_from(Patient).where(*conditions)) or 0

    rows = session.scalars(
        select(Patient)
        .where(*conditions)
        .order_by(Patient.is_default.desc(), Patient.created_at.asc(), Patient.patient_id.asc())
        .offset((page_num - 1) * page_size)
        .limit(page_size)
    ).all()

    return PatientListData(
        total=total,
        pageNum=page_num,
        pageSize=page_size,
        list=[_to_item(p) for p in rows],
    )


# --------------------------------------------------------------------------- #
# API-05 新增就诊人
# --------------------------------------------------------------------------- #


def create_patient(session: Session, *, user_id: str, payload: PatientCreateRequest) -> PatientCreateData:
    """添加家庭成员为就诊人（接口文档 API-05）。

    同一账号下身份证号重复时返回 1002 —— 这是**接口文档原文**的要求。注意 1002 在通用
    错误码表里的文案是「账号已存在」，语义上略有出入，按「文档是权威契约」照用，不另造码；
    真正属于本模块的 2003 留给「身份证号本身不合法」。

    重复的情形分两种：
      * 命中未删除的记录 —— 报 1002；
      * 命中**已软删**的记录 —— 不是重复，是「删了又加回来」：复活原行并覆盖全部字段。
        不能走新增分支，因为 uk_user_idcard 唯一键只管 (user_id, idcard)，软删的行仍占位，
        直接 INSERT 会撞唯一键报 500。
    """
    idcard = _validate_idcard(payload.idcard)
    is_default = 1 if payload.isDefault else 0

    existing = _find_by_idcard(session, user_id, idcard)
    if existing is not None and existing.is_deleted == 0:
        raise PatientError(1002, "该身份证号已在本账号下添加过就诊人")

    if existing is None:
        active_count = session.scalar(
            select(func.count())
            .select_from(Patient)
            .where(Patient.user_id == user_id, Patient.is_deleted == 0)
        ) or 0
        if active_count >= MAX_PATIENTS_PER_USER:
            raise PatientError(2003, f"就诊人数量已达上限（{MAX_PATIENTS_PER_USER} 人）")
        patient = Patient(patient_id=next_id(session, Patient.patient_id, "PAT"), user_id=user_id)
        session.add(patient)
    else:
        patient = existing
        patient.is_deleted = 0

    # 复用同一段赋值逻辑：新增与复活之后要写的字段完全一样
    _apply_fields(patient, payload, idcard=idcard)
    patient.is_default = is_default

    if is_default:
        _clear_other_defaults(session, user_id, keep_id=patient.patient_id)

    session.commit()
    return PatientCreateData(patientId=patient.patient_id)


def _apply_fields(patient: Patient, payload: PatientCreateRequest, *, idcard: str) -> None:
    """把请求体写进 ORM 行（新增与复活共用）。

    身份证号在这里加密落库：encrypt_text 幂等，传进来的若已是密文不会被二次加密。
    姓名与手机号保持明文（接口文档只要求身份证号加密存储，见数据库设计文档 3.3）。
    """
    patient.name = payload.name.strip()
    patient.idcard = crypto.encrypt_text(idcard)
    patient.phone = (payload.phone or "").strip() or None
    patient.gender = payload.gender
    patient.birth_date = payload.birthDate
    patient.relation = payload.relation
    patient.blood_type = payload.bloodType
    patient.allergy_history = payload.allergyHistory
    patient.medical_history = payload.medicalHistory


# --------------------------------------------------------------------------- #
# API-06 修改就诊人
# --------------------------------------------------------------------------- #


def update_patient(
    session: Session,
    patient_id: str,
    *,
    user_id: str,
    payload: PatientUpdateRequest,
) -> None:
    """修改就诊人资料（接口文档 API-06：请求体字段全部可选）。

    未传的字段保持原值（`exclude_unset` 语义由调用方给到的模型天然满足：Pydantic 未传的
    可选字段就是 None，这里逐字段判 None 即可）。idcard 改动时要重新走校验与判重。
    """
    patient = _get_patient(session, patient_id, user_id)

    if payload.name is not None:
        patient.name = payload.name.strip()
    if payload.gender is not None:
        patient.gender = payload.gender
    if payload.birthDate is not None:
        patient.birth_date = payload.birthDate
    if payload.relation is not None:
        patient.relation = payload.relation
    if payload.bloodType is not None:
        patient.blood_type = payload.bloodType
    if payload.allergyHistory is not None:
        patient.allergy_history = payload.allergyHistory
    if payload.medicalHistory is not None:
        patient.medical_history = payload.medicalHistory
    if payload.phone is not None:
        patient.phone = payload.phone.strip() or None

    if payload.idcard is not None:
        idcard = _validate_idcard(payload.idcard)
        duplicated = _find_by_idcard(session, user_id, idcard)
        if duplicated is not None and duplicated.patient_id != patient.patient_id:
            # 撞上同账号下另一个人（含已软删的其它行）：仍是「已存在」语义，返回 1002
            raise PatientError(1002, "该身份证号已在本账号下添加过就诊人")
        patient.idcard = crypto.encrypt_text(idcard)

    if payload.isDefault is not None:
        if payload.isDefault:
            _clear_other_defaults(session, user_id, keep_id=patient.patient_id)
            patient.is_default = 1
        else:
            patient.is_default = 0

    session.commit()


# --------------------------------------------------------------------------- #
# API-07 删除就诊人
# --------------------------------------------------------------------------- #


def delete_patient(session: Session, patient_id: str, *, user_id: str) -> None:
    """解绑并删除就诊人（接口文档 API-07）。

    存在未完成挂号单（BOOKED / CHECKED_IN）时返回 2002，提示先取消挂号 —— 这是文档原文
    的要求，也避免号源被「人已删除但号还占着」的状态锁死。

    删除是软删（is_deleted=1）：就诊人身上挂着挂号单、病历、账单等历史数据，
    物理删除会让这些记录失去归属。软删后该行的身份证号仍占用 uk_user_idcard 唯一键，
    下次添加同一个人会复活它（见 create_patient）。
    """
    patient = _get_patient(session, patient_id, user_id)

    unfinished = session.scalar(
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.patient_id == patient_id,
            Appointment.appointment_status.in_(UNFINISHED_APPOINTMENT_STATUS),
        )
    ) or 0
    if unfinished:
        raise PatientError(2002, f"该就诊人还有 {unfinished} 条未完成的挂号单，请先取消挂号")

    patient.is_deleted = 1
    # 删除默认就诊人后账号不再有默认值，前端取默认值时需处理空值
    patient.is_default = 0
    session.commit()


__all__ = [
    "MAX_PATIENTS_PER_USER",
    "UNFINISHED_APPOINTMENT_STATUS",
    "PatientError",
    "create_patient",
    "delete_patient",
    "list_patients",
    "update_patient",
]
