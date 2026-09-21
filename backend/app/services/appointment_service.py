"""挂号业务逻辑（《接口文档》3.4.2 ~ 3.4.6：API-11 ~ API-15）。

分层约定与其他模块一致：本模块只依赖 SQLAlchemy 会话，不感知 HTTP；
错误统一以 `AppointmentError` 抛出，由 `api/v1/appointments.py` 转成统一信封。

接口文档把 HIS 写成这几个接口的对接系统，但本期 HIS 未接入（settings.his_enabled=False），
所有读写都落在本系统库（t_schedule / t_appointment / t_bill）。接入后只需把
`_sync_his` 换成真实调用，本模块其余部分不用动。

四个需要留意的实现取舍：

1. **扣号源用原子条件更新**。`UPDATE ... SET remaining = remaining - 1 WHERE remaining > 0`
   由数据库保证不会超卖；先读后写会在并发下把号发出去两次。
2. **挂号必带账单**。接口文档 API-11 的响应里有 billId，所以创建挂号单时同步生成
   billType=REGISTRATION 的待缴费账单并回填，前端拿到的挂号单可以直接去缴费。
3. **取消挂号与账单联动**。账单未支付 → 置 REFUNDED 并释放号源；已支付 → 拒绝取消（2002）。
   否则会出现「钱收了、号没了」的状态。
4. **叫号进度是本地估算**。库里不存叫号队列（数据库设计文档 4.4），API-15 的数字由
   「同医生同日、队列号在我前面、且仍在队列中的人数 × 平均问诊时长」推算，
   响应固定带 estimateNote 要求页面标注「以现场为准」。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Department, Doctor, OperationLog, Patient, Schedule, User
from app.models.appointment import Appointment
from app.models.bill import Bill
from app.schemas.appointment import (
    APPOINTMENT_STATUS_DESC,
    QUEUE_PREFIX_FEVER,
    QUEUE_PREFIX_NORMAL,
    REMINDER_ESTIMATE_NOTE,
    AppointmentCancelData,
    AppointmentCreateRequest,
    AppointmentData,
    AppointmentHistoryData,
    AppointmentHistoryItem,
    AppointmentReminderData,
    AppointmentUpdateRequest,
)
from app.utils.id_gen import next_id
from app.utils.time_utils import now

logger = logging.getLogger(__name__)

# 发热门诊科室编号（app/db/seed.py 的 FEVER_DEPT_ID）：队列号前缀与医保报销比例都看它
FEVER_DEPT_ID = "DEPT0001"

# 挂号费账单：医保预估报销比例（沿用 seed 对 REGISTRATION 账单的 0.6 口径）
REGISTRATION_INSURANCE_RATIO = Decimal("0.6")

# 挂号单状态
STATUS_BOOKED = "BOOKED"
STATUS_CHECKED_IN = "CHECKED_IN"
STATUS_FINISHED = "FINISHED"
STATUS_CANCELED = "CANCELED"

# 仍在候诊队列里的状态（API-15 的 inQueue 判定，与 exam_service.IN_QUEUE_STATUS 同思路）
IN_QUEUE_STATUS: tuple[str, ...] = (STATUS_BOOKED, STATUS_CHECKED_IN)

# 允许改期的状态：已取号（人已到院）、已完成、已取消都不允许改期（接口文档 API-12 语义）
RESCHEDULABLE_STATUS: tuple[str, ...] = (STATUS_BOOKED,)

# 允许取消的状态：接口文档 API-13 明确「已取号（CHECKED_IN）的挂号单不允许取消」
CANCELABLE_STATUS: tuple[str, ...] = (STATUS_BOOKED,)

# 挂号费账单的名称
REGISTRATION_BILL_TITLE = "门诊挂号费"


class AppointmentError(Exception):
    """挂号模块业务错误。

    code 取接口文档 2.5 通用错误码表：2001 号源不足或已被占用、2002 挂号单不存在或
    当前状态不允许该操作、2003 就诊人信息校验失败、4003 无权访问该资源、5001 HIS 调用失败。
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- #
# 内部查询
# --------------------------------------------------------------------------- #


def _get_appointment(session: Session, appointment_id: str, user_id: str) -> Appointment:
    """取挂号单并校验归属。

    挂号单不存在与不属于当前账号返回同一个 4003：不靠错误码差异暴露「这个编号存在」
    （与 exam_service._get_exam 同一理由）。
    """
    appointment = session.scalars(
        select(Appointment).where(
            Appointment.appointment_id == appointment_id,
            Appointment.user_id == user_id,
        )
    ).first()
    if appointment is None:
        raise AppointmentError(4003, "挂号单不存在或无权访问")
    return appointment


def _get_patient(session: Session, patient_id: str, user_id: str) -> Patient:
    """取就诊人并校验归属（排除已软删的就诊人）。"""
    patient = session.scalars(
        select(Patient).where(
            Patient.patient_id == patient_id,
            Patient.user_id == user_id,
            Patient.is_deleted == 0,
        )
    ).first()
    if patient is None:
        # 就诊人不存在/不属于该账号/已删除：统称信息校验失败，不区分（避免枚举他人编号）
        raise AppointmentError(2003, "就诊人不存在或不属于当前账号")
    return patient


def _get_schedule(session: Session, schedule_id: str) -> Schedule:
    schedule = session.get(Schedule, schedule_id)
    if schedule is None:
        raise AppointmentError(2001, "排班不存在或已下架，请重新选择时段")
    return schedule


def _consume_slot(session: Session, schedule_id: str) -> None:
    """原子扣减一个号源；号源已满时抛 2001。

    用 `UPDATE ... WHERE remaining > 0` 而不是「先查再减」：并发下两个请求会同时
    读到 remaining=1 并各自减一次，超卖一个号。条件更新把判断权交给数据库，
    rowcount=0 就说明这一枪打空了。
    """
    result = session.execute(
        update(Schedule)
        .where(Schedule.schedule_id == schedule_id, Schedule.remaining > 0)
        .values(remaining=Schedule.remaining - 1)
    )
    if result.rowcount == 0:
        raise AppointmentError(2001, "该时段号源不足或已被占用，请更换时段")


def _release_slot(session: Session, schedule_id: str) -> None:
    """回补一个号源（改期释放原时段、取消挂号时调）。

    上限卡在 total_count：号源表被人工改过（或历史数据不一致）时，
    回补不应该让 remaining 超过总数，否则这个时段会被多卖出号。
    """
    session.execute(
        update(Schedule)
        .where(Schedule.schedule_id == schedule_id, Schedule.remaining < Schedule.total_count)
        .values(remaining=Schedule.remaining + 1)
    )


def _next_queue_no(session: Session, schedule: Schedule) -> str:
    """生成就诊队列号：前缀 + 3 位序号，序号按「同医生同日」递增。

    seed 的约定是发热门诊用 F、其余科室用 A（app/db/seed.py 的
    `f"{'F' if is_fever else 'A'}{idx:03d}"`）。序号取同医生同日已有挂号单数的最大值 +1，
    已取消的单不占号，所以它们不参与计数。
    """
    prefix = QUEUE_PREFIX_FEVER if schedule.dept_id == FEVER_DEPT_ID else QUEUE_PREFIX_NORMAL
    used = session.scalar(
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.doctor_id == schedule.doctor_id,
            Appointment.appt_date == schedule.appt_date,
            Appointment.appointment_status != STATUS_CANCELED,
        )
    ) or 0
    return f"{prefix}{used + 1:03d}"


def _dept_location(session: Session, dept_id: str) -> Optional[str]:
    """科室位置：优先 dept_addr，缺省回落 floor_position。

    t_appointment 没有冗余的位置列（数据库设计文档 3.6），接口文档 API-11 却要求响应
    带 location，因此这里现查 t_department。两个字段都为空时返回 None，
    前端按「位置待补充」展示即可，不为此报错。
    """
    dept = session.get(Department, dept_id)
    if dept is None:
        return None
    return dept.dept_addr or dept.floor_position


def _create_registration_bill(
    session: Session,
    *,
    appointment: Appointment,
    amount: Decimal,
) -> Bill:
    """为挂号单建一张待缴费的挂号费账单并回填 appointment.bill_id。

    金额与医保拆分沿用 seed 对 REGISTRATION 账单的口径（报销 60%，自付 = 总额 - 报销额）：
    自付额用减法得出，避免两处各自四舍五入后加起来与总额差一分钱。
    """
    cover = (amount * REGISTRATION_INSURANCE_RATIO).quantize(Decimal("0.01"))
    bill = Bill(
        bill_id=next_id(session, Bill.bill_id, "BILL"),
        patient_id=appointment.patient_id,
        appointment_id=appointment.appointment_id,
        bill_type="REGISTRATION",
        bill_title=REGISTRATION_BILL_TITLE,
        related_type=None,
        related_id=None,
        amount=amount,
        insurance_cover=cover,
        self_pay=(amount - cover).quantize(Decimal("0.01")),
        pay_status="UNPAID",
    )
    session.add(bill)
    # ⚠ 这里必须先把账单落库，再回填 appointment.bill_id。
    # t_appointment.bill_id 与 t_bill.appointment_id 互指（建表环路，fk_appt_bill / t_bill_ibfk_2），
    # SQLAlchemy 对环状外键排不出先后顺序：回填若与账单的 INSERT 挤在同一次 flush，它会先发
    # appointment 的写语句，MySQL 上直接报 fk_appt_bill（sqlite 默认不校验外键，本机测不出来，
    # 共享库上挂号会返回 9999）。seed.py 处理同一环路也是这么两段式做的。
    session.flush()
    appointment.bill_id = bill.bill_id
    return bill


def _write_log(
    session: Session,
    *,
    user_id: str,
    action: str,
    appointment_id: str,
    detail: Optional[str] = None,
) -> None:
    """写 t_operation_log（合规审计留存，见 auth_service._write_log 的同一约定）。"""
    session.add(
        OperationLog(
            log_id=next_id(session, OperationLog.log_id, "LOG"),
            user_id=user_id,
            action=action,
            target_type="APPOINTMENT",
            target_id=appointment_id,
            detail=detail,
        )
    )


def _sync_his(action: str, appointment_id: str) -> None:
    """HIS 挂号同步钩子（预留）。

    当前 settings.his_enabled=False，本函数是空操作：挂号主流程完全走本地库，
    不能因为 HIS 没接上就让用户挂不了号。接入后在此调用
    app/services/his.py 的 sync_appointment 并把回执写进 Appointment.external_no，
    调不通时抛 AppointmentError(5001) —— 那时「挂号成功但 HIS 没有」才是更坏的结果。
    """
    return None


# --------------------------------------------------------------------------- #
# API-11 预约挂号
# --------------------------------------------------------------------------- #


def create_appointment(
    session: Session,
    *,
    user_id: str,
    payload: AppointmentCreateRequest,
) -> AppointmentData:
    """创建挂号单（接口文档 API-11，手动挂号与 AI 自动挂号共用）。

    步骤：校验就诊人归属 → 原子扣号源 → 生成队列号 → 建挂号费账单 → 写操作日志，
    全部副作用做完**最后一次性 commit**（与 bill_service.settle_bill 同一取舍）：
    中途任何一步抛错，整笔挂号都不会留下半截数据。

    号源不足抛 2001；就诊人不存在/不属于当前账号抛 2003。
    """
    patient = _get_patient(session, payload.patientId, user_id)
    schedule = _get_schedule(session, payload.scheduleId)

    # 医生停诊/替诊的时段不该被挂号：schedule 还在、号也还有，但当天没人出诊
    doctor = session.get(Doctor, schedule.doctor_id)
    if doctor is None or doctor.visit_status != 1:
        raise AppointmentError(2001, "该医生当前停诊，请选择其它时段")

    # 日期已过的排班不允许挂号（seed 里有历史排班，不拦的话能挂到昨天去）
    if schedule.appt_date < date.today():
        raise AppointmentError(2001, "该时段已过期，请重新选择")

    _consume_slot(session, schedule.schedule_id)

    appointment = Appointment(
        appointment_id=next_id(session, Appointment.appointment_id, "APT"),
        user_id=user_id,
        patient_id=patient.patient_id,
        doctor_id=schedule.doctor_id,
        schedule_id=schedule.schedule_id,
        dept_id=schedule.dept_id,
        appt_date=schedule.appt_date,
        time_slot=schedule.time_slot,
        # 接口文档的入参叫 remark，库列叫 chief_complaint（数据库设计文档 3.6），
        # 同一份语义的两个名字：对外收 remark，对内落 chief_complaint
        chief_complaint=payload.remark,
        queue_no=_next_queue_no(session, schedule),
        appointment_status=STATUS_BOOKED,
        source=payload.source,
    )
    session.add(appointment)
    # flush 一下拿到 appointment_id 对应的行，账单要引用它（也是主键冲突的暴露点）
    session.flush()

    _create_registration_bill(
        session, appointment=appointment, amount=Decimal(schedule.fee or 0)
    )
    _write_log(
        session,
        user_id=user_id,
        action="APPT_CREATE",
        appointment_id=appointment.appointment_id,
        detail=(
            f"挂号 {schedule.appt_date} {schedule.time_slot} "
            f"{doctor.name}（队列号 {appointment.queue_no}）"
        ),
    )
    _sync_his("CREATE", appointment.appointment_id)

    session.commit()
    return _to_data(session, appointment)


def _to_data(session: Session, appointment: Appointment) -> AppointmentData:
    """挂号单 → API-11 / API-12 响应（9 个字段，两处结构相同）。"""
    doctor = session.get(Doctor, appointment.doctor_id)
    return AppointmentData(
        appointmentId=appointment.appointment_id,
        queueNo=appointment.queue_no,
        apptDate=appointment.appt_date,
        timeSlot=appointment.time_slot,
        deptName=_dept_name(session, appointment.dept_id),
        doctorName=doctor.name if doctor else None,
        location=_dept_location(session, appointment.dept_id),
        billId=appointment.bill_id,
        appointmentStatus=appointment.appointment_status,  # type: ignore[arg-type]
    )


def _dept_name(session: Session, dept_id: str) -> Optional[str]:
    dept = session.get(Department, dept_id)
    return dept.dept_name if dept else None


# --------------------------------------------------------------------------- #
# API-12 修改挂号（改期 / 换时段）
# --------------------------------------------------------------------------- #


def update_appointment(
    session: Session,
    appointment_id: str,
    *,
    user_id: str,
    payload: AppointmentUpdateRequest,
) -> AppointmentData:
    """修改挂号信息（接口文档 API-12：原时段释放并重新锁定新号源）。

    顺序很关键：**先扣新号源、再释放原号源**。反过来写的话，新时段已经满号时
    原号源已经放出去了，用户会既没改到期也丢了原来的号。
    新号源扣减失败会抛 2001，事务未提交，原号码还在。

    已取号 / 已完成 / 已取消的挂号单不允许改期（抛 2002）。
    """
    appointment = _get_appointment(session, appointment_id, user_id)

    if appointment.appointment_status not in RESCHEDULABLE_STATUS:
        raise AppointmentError(
            2002,
            f"当前状态（{APPOINTMENT_STATUS_DESC.get(appointment.appointment_status, appointment.appointment_status)}）"
            "不允许改期",
        )

    new_schedule = _get_schedule(session, payload.scheduleId)
    if new_schedule.schedule_id == appointment.schedule_id:
        # 改到同一个时段：不算错，直接更新备注即可，不必折腾号源
        if payload.remark is not None:
            appointment.chief_complaint = payload.remark
            session.commit()
        return _to_data(session, appointment)

    doctor = session.get(Doctor, new_schedule.doctor_id)
    if doctor is None or doctor.visit_status != 1:
        raise AppointmentError(2001, "该医生当前停诊，请选择其它时段")
    if new_schedule.appt_date < date.today():
        raise AppointmentError(2001, "该时段已过期，请重新选择")

    old_schedule_id = appointment.schedule_id
    old_doctor_id = appointment.doctor_id
    old_appt_date = appointment.appt_date

    _consume_slot(session, new_schedule.schedule_id)
    _release_slot(session, old_schedule_id)

    appointment.schedule_id = new_schedule.schedule_id
    appointment.doctor_id = new_schedule.doctor_id
    appointment.dept_id = new_schedule.dept_id
    appointment.appt_date = new_schedule.appt_date
    appointment.time_slot = new_schedule.time_slot
    if payload.remark is not None:
        appointment.chief_complaint = payload.remark

    # 换医生或换日期后队列号要重排（队列号是按「同医生同日」编的）
    if new_schedule.doctor_id != old_doctor_id or new_schedule.appt_date != old_appt_date:
        appointment.queue_no = _next_queue_no(session, new_schedule)

    _write_log(
        session,
        user_id=user_id,
        action="APPT_UPDATE",
        appointment_id=appointment.appointment_id,
        detail=f"改期至 {new_schedule.appt_date} {new_schedule.time_slot}",
    )
    _sync_his("UPDATE", appointment.appointment_id)

    session.commit()
    return _to_data(session, appointment)


# --------------------------------------------------------------------------- #
# API-13 取消挂号
# --------------------------------------------------------------------------- #


def cancel_appointment(session: Session, appointment_id: str, *, user_id: str) -> AppointmentCancelData:
    """取消挂号（接口文档 API-13：状态置 CANCELED 并释放号源）。

    两种状态不允许取消，都返回 2002：
      * CHECKED_IN 已取号 —— 接口文档明说；人已到院，取消与否该走退号流程。
      * 关联账单已支付 —— 见下。

    关于账单：挂号时自动建了一张 REGISTRATION 账单，取消时**未支付**的置 REFUNDED
    （与 seed 对已取消挂号单的账单口径一致，前端账单列表据此显示「已退费」）；
    已支付的则拒绝取消 —— 线上没有接退款通道（app/services/pay.py 是桩），
    直接置 REFUNDED 会造成「钱已收、账记退费」的假账，宁可让用户走线下退费。
    """
    appointment = _get_appointment(session, appointment_id, user_id)

    if appointment.appointment_status not in CANCELABLE_STATUS:
        raise AppointmentError(
            2002,
            f"当前状态（{APPOINTMENT_STATUS_DESC.get(appointment.appointment_status, appointment.appointment_status)}）"
            "不允许取消",
        )

    bill = (
        session.get(Bill, appointment.bill_id) if appointment.bill_id else None
    )
    if bill is not None and bill.pay_status == "PAID":
        raise AppointmentError(2002, "该挂号已缴费，请在就诊前到窗口办理退号退费")

    appointment.appointment_status = STATUS_CANCELED
    _release_slot(session, appointment.schedule_id)

    if bill is not None and bill.pay_status == "UNPAID":
        bill.pay_status = "REFUNDED"

    _write_log(
        session,
        user_id=user_id,
        action="APPT_CANCEL",
        appointment_id=appointment.appointment_id,
        detail=f"取消 {appointment.appt_date} {appointment.time_slot} 的挂号",
    )
    _sync_his("CANCEL", appointment.appointment_id)

    session.commit()
    return AppointmentCancelData(
        appointmentId=appointment.appointment_id, appointmentStatus=STATUS_CANCELED
    )


# --------------------------------------------------------------------------- #
# API-14 查询历史挂号
# --------------------------------------------------------------------------- #


def list_history(
    session: Session,
    *,
    user_id: str,
    patient_id: Optional[str] = None,
    appointment_status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page_num: int = 1,
    page_size: int = 10,
) -> AppointmentHistoryData:
    """查询当前账号的全部历史挂号，按时间倒序分页（接口文档 API-14）。

    医生名与科室名用一次批量查询取回，避免列表里逐行查库（N+1）——
    与 medical_record_service 的批量取名法同一取舍。
    """
    if appointment_status and appointment_status not in APPOINTMENT_STATUS_DESC:
        raise AppointmentError(4001, f"挂号状态取值不合法：{appointment_status}")

    conditions = [Appointment.user_id == user_id]
    if patient_id:
        conditions.append(Appointment.patient_id == patient_id)
    if appointment_status:
        conditions.append(Appointment.appointment_status == appointment_status)
    if start_date:
        conditions.append(Appointment.appt_date >= start_date)
    if end_date:
        conditions.append(Appointment.appt_date <= end_date)

    total = session.scalar(
        select(func.count()).select_from(Appointment).where(*conditions)
    ) or 0

    rows = session.execute(
        select(Appointment, Patient.name)
        .join(Patient, Appointment.patient_id == Patient.patient_id)
        .where(*conditions)
        .order_by(Appointment.appt_date.desc(), Appointment.appointment_id.desc())
        .offset((page_num - 1) * page_size)
        .limit(page_size)
    ).all()

    doctors = _name_map(session, Doctor, Doctor.doctor_id, Doctor.name, {a.doctor_id for a, _ in rows})
    depts = _name_map(
        session, Department, Department.dept_id, Department.dept_name, {a.dept_id for a, _ in rows}
    )

    items = [
        AppointmentHistoryItem(
            appointmentId=appointment.appointment_id,
            patientId=appointment.patient_id,
            patientName=patient_name or "",
            deptName=depts.get(appointment.dept_id),
            doctorName=doctors.get(appointment.doctor_id),
            apptDate=appointment.appt_date,
            timeSlot=appointment.time_slot,
            queueNo=appointment.queue_no,
            appointmentStatus=appointment.appointment_status,  # type: ignore[arg-type]
            statusDesc=APPOINTMENT_STATUS_DESC.get(appointment.appointment_status),
            createTime=appointment.created_at,
        )
        for appointment, patient_name in rows
    ]

    return AppointmentHistoryData(
        total=total, pageNum=page_num, pageSize=page_size, list=items
    )


def _name_map(session: Session, model, id_column, name_column, ids) -> dict:  # type: ignore[no-untyped-def]
    """批量取 {id: name}，避免列表逐行查库。"""
    keys = {i for i in ids if i}
    if not keys:
        return {}
    rows = session.execute(
        select(id_column, name_column).where(id_column.in_(keys))
    ).all()
    return {row[0]: row[1] for row in rows}


# --------------------------------------------------------------------------- #
# API-15 挂号提醒（候诊进度）
# --------------------------------------------------------------------------- #


def get_reminder(
    session: Session,
    appointment_id: str,
    *,
    user_id: str,
    remind_before_minutes: Optional[int] = None,
) -> AppointmentReminderData:
    """查候诊进度与预计叫号时间（接口文档 API-15）。

    ⚠ 接口文档说本接口「对接医院HIS系统查询挂号表获取当前排队进度」，而 HIS 未接入、
    库里也不存叫号队列（数据库设计文档 4.4 明确建议轮询 HIS 而不落库）。因此这里的
    currentNo / peopleAhead / estimatedTime 是**本地估算**：
      peopleAhead = 同医生同日、队列号排在我前面、且仍在队列中（BOOKED/CHECKED_IN）的人数
      estimatedTime = 当前时间 + peopleAhead × settings.appointment_avg_minutes

    响应固定带 estimateNote（接口文档要求「页面须标注以现场为准」）。接 HIS 后
    换掉本函数的估算段即可，出参结构不变。

    已取消 / 已完成的挂号单不在队列中：inQueue=false，叫号字段一律为 null。
    """
    appointment = _get_appointment(session, appointment_id, user_id)
    in_queue = appointment.appointment_status in IN_QUEUE_STATUS

    if not in_queue:
        return AppointmentReminderData(
            appointmentId=appointment.appointment_id,
            queueNo=appointment.queue_no,
            inQueue=False,
            estimateNote=REMINDER_ESTIMATE_NOTE,
            remindBeforeMinutes=remind_before_minutes,
            statusDesc=APPOINTMENT_STATUS_DESC.get(appointment.appointment_status),
        )

    # 队列号形如 A003，比较大小要按数字比而不是字符串比（A010 > A009 但 "A010" < "A009"）
    my_no = _queue_seq(appointment.queue_no)
    people_ahead = 0
    current_no: Optional[str] = None
    if my_no is not None:
        prefix = _queue_prefix(appointment.queue_no)
        rows = session.scalars(
            select(Appointment.queue_no).where(
                Appointment.doctor_id == appointment.doctor_id,
                Appointment.appt_date == appointment.appt_date,
                Appointment.appointment_status.in_(IN_QUEUE_STATUS),
                Appointment.appointment_id != appointment.appointment_id,
            )
        ).all()
        ahead_seqs = sorted(
            seq for seq in (_queue_seq(no) for no in rows) if seq is not None and seq < my_no
        )
        people_ahead = len(ahead_seqs)
        # 当前叫号 = 我前面那个人的号；前面没人则视为已轮到我
        current_no = f"{prefix}{ahead_seqs[-1]:03d}" if ahead_seqs else appointment.queue_no

    avg_minutes = max(1, int(settings.appointment_avg_minutes))
    wait_minutes = people_ahead * avg_minutes
    estimated = _fmt_dt(now() + timedelta(minutes=wait_minutes))

    return AppointmentReminderData(
        appointmentId=appointment.appointment_id,
        queueNo=appointment.queue_no,
        currentNo=current_no,
        peopleAhead=people_ahead,
        estimatedTime=estimated,
        remindBeforeMinutes=remind_before_minutes,
        estimatedWaitMinutes=wait_minutes,
        estimateNote=REMINDER_ESTIMATE_NOTE,
        inQueue=True,
        statusDesc=APPOINTMENT_STATUS_DESC.get(appointment.appointment_status),
    )


def _queue_seq(queue_no: Optional[str]) -> Optional[int]:
    """从队列号里取出数字部分（A003 → 3）；取不出来返回 None。"""
    if not queue_no:
        return None
    digits = "".join(ch for ch in queue_no if ch.isdigit())
    return int(digits) if digits else None


def _queue_prefix(queue_no: Optional[str]) -> str:
    """取队列号的字母前缀（A003 → "A"）。"""
    return "".join(ch for ch in (queue_no or "") if not ch.isdigit())


def _fmt_dt(value: datetime) -> str:
    """接口文档 2.1：时间统一 yyyy-MM-dd HH:mm:ss。"""
    return value.strftime("%Y-%m-%d %H:%M:%S")


__all__ = [
    "CANCELABLE_STATUS",
    "FEVER_DEPT_ID",
    "IN_QUEUE_STATUS",
    "REGISTRATION_BILL_TITLE",
    "REGISTRATION_INSURANCE_RATIO",
    "RESCHEDULABLE_STATUS",
    "AppointmentError",
    "cancel_appointment",
    "create_appointment",
    "get_reminder",
    "list_history",
    "update_appointment",
]
