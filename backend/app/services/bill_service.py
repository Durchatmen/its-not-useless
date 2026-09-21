"""账单业务逻辑（接口文档 3.5.1 API-16、3.5.2 API-17）。

分层约定与 exams 模块一致：本模块只依赖 SQLAlchemy 会话，不感知 HTTP；
错误统一以 `BillError` 抛出，由 `api/v1/bills.py` 转成统一信封。

`BillError` 是整个支付模块（账单 + 支付单）的领域错误，`payment_service` 也从这里导入 ——
一个模块一个错误类型，避免两边各定义一套错误码。core/errors.py 落地后应改为
继承统一的业务异常基类。

金额一律用 Decimal 参与运算，只在出口由 schema 转成 float（见 schemas/bill.py 的说明）。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.bill import Bill
from app.models.exam import Exam
from app.models.patient import Patient
from app.models.payment import Payment
from app.schemas.bill import (
    BILL_TYPE_DESC,
    DEFAULT_BILL_STATUS,
    BillListData,
    BillListItem,
    BillSettleData,
    BillSettleRequest,
)
from app.services import his, pay

logger = logging.getLogger(__name__)

# 取值以接口文档 2.6 枚举表为准，这里同时用于参数校验
BILL_TYPES: tuple[str, ...] = ("REGISTRATION", "TREATMENT")
BILL_STATUSES: tuple[str, ...] = ("UNPAID", "PAID", "REFUNDED")
PAY_CHANNELS: tuple[str, ...] = ("INSURANCE", "WECHAT", "ALIPAY")

# 走第三方渠道（需先建支付单）的渠道
THIRD_PARTY_CHANNELS: tuple[str, ...] = ("WECHAT", "ALIPAY")

# 缴费后检查单要推进到的状态：待缴费 → 待检查（接口文档 API-17 明确举了这个例子）
EXAM_STATUS_AFTER_PAY = "WAIT_EXAM"
EXAM_STATUS_BEFORE_PAY = "WAIT_PAY"


class BillError(Exception):
    """支付模块业务错误。

    code 取接口文档 2.5 通用错误码表：3001 账单不存在或已缴费、3002 支付渠道下单失败、
    3003 支付超时或用户取消支付、4001 参数校验失败、4003 无权访问、5001 HIS 调用失败。
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- #
# 取数与权限
# --------------------------------------------------------------------------- #


def get_bill(session: Session, bill_id: str, user_id: str) -> Bill:
    """取账单并校验归属。

    t_bill 本身没有 user_id 列，归属要经 t_patient 绕一下（一人账号全家就医）。
    账单不存在与不属于当前账号返回同一个 4003：不靠错误码差异暴露「这个编号存在」。

    公开给 payment_service 用 —— 支付单必须先确认账单归属才允许下单。
    """
    bill = session.scalars(
        select(Bill)
        .join(Patient, Bill.patient_id == Patient.patient_id)
        .where(Bill.bill_id == bill_id, Patient.user_id == user_id)
    ).first()
    if bill is None:
        raise BillError(4003, "账单不存在或无权访问")
    return bill


def _get_payment_for_bill(session: Session, payment_id: str, bill: Bill, user_id: str) -> Payment:
    """取支付单，并校验它确实属于这张账单、这个账号。

    三者任一不符都返回同一个 4001：调用方拿到的是一个自洽的请求，参数对不上就是参数错。
    """
    payment = session.scalars(
        select(Payment).where(
            Payment.payment_id == payment_id,
            Payment.bill_id == bill.bill_id,
            Payment.user_id == user_id,
        )
    ).first()
    if payment is None:
        raise BillError(4001, "支付单不存在或与账单不匹配")
    return payment


# --------------------------------------------------------------------------- #
# 金额与票据
# --------------------------------------------------------------------------- #


def _to_float(value: Optional[Decimal]) -> float:
    """Decimal → float。金额出口统一走这里，避免 Pydantic 把 Decimal 序列化成字符串。"""
    return float(value or 0)


def _generate_invoice_no(bill: Bill, now: datetime) -> str:
    """本地生成电子票据号：INV + 日期 + 账单序号，与 seed 的格式一致。"""
    digits = re.sub(r"\D", "", bill.bill_id) or "0"
    return f"INV{now:%Y%m%d}{int(digits):05d}"


# --------------------------------------------------------------------------- #
# 结算落库（API-17 与 API-19 共用）
# --------------------------------------------------------------------------- #


def _advance_exam_status(session: Session, bill: Bill) -> None:
    """缴费成功后推进关联检查单的状态：WAIT_PAY → WAIT_EXAM。

    接口文档 API-17：「缴费成功后 HIS 侧状态同步更新（如挂号单进入已缴费、
    检查状态由待缴费转为待检查）」。

    只在当前确实为 WAIT_PAY 时推进 —— 已经做过检查的单子不能被缴费动作倒推回去。
    """
    if bill.related_type != "EXAM" or not bill.related_id:
        return

    exam = session.get(Exam, bill.related_id)
    if exam is None:
        logger.warning("账单 %s 关联的检查单 %s 不存在，跳过状态推进", bill.bill_id, bill.related_id)
        return
    if exam.exam_status != EXAM_STATUS_BEFORE_PAY:
        logger.info(
            "检查单 %s 当前为 %s，非待缴费，不做状态推进", exam.exam_id, exam.exam_status
        )
        return

    exam.exam_status = EXAM_STATUS_AFTER_PAY
    logger.info("检查单 %s 状态推进：%s → %s", exam.exam_id, EXAM_STATUS_BEFORE_PAY, EXAM_STATUS_AFTER_PAY)

    # HIS 已接入时把这次状态变更回写过去；未接入返回 False，本地库照样更新
    his.sync_exam_status(exam.exam_id, EXAM_STATUS_AFTER_PAY)


def mark_bill_paid(session: Session, bill: Bill, *, invoice_no: str, now: datetime) -> None:
    """把账单标记为已缴费并执行缴费成功的副作用。

    API-17（显式结算）与 API-19（查单时兜底结算）两条路径都调这里，
    状态机只写一遍，避免两条路径产生不一致。

    只落库不 commit，事务边界留给调用方。

    注意 t_bill 没有「实付金额」列 —— insurance_cover / self_pay 在设计上是**预估**值，
    实际支付金额记在 t_payment.amount 上，所以这里不接收金额参数。
    """
    bill.pay_status = "PAID"
    bill.paid_at = now
    bill.invoice_no = invoice_no
    _advance_exam_status(session, bill)


def apply_payment_success(
    session: Session,
    bill: Bill,
    *,
    pay_channel: str,
    paid_amount: Decimal,
    insurance_paid: Decimal,
    payment_id: Optional[str],
    now: datetime,
) -> str:
    """缴费成功后的统一落库动作，返回电子票据号。

    API-17（用户点「确认缴费」）与 API-19（查单发现网关已回调，兜底结算）
    共用这一处：同步 HIS → 取/生成票据号 → 标记账单 → 推进检查状态。
    两条路径的副作用必须一致，否则同样一笔钱会因为走的入口不同留下不同状态。

    只落库不 commit；HIS 调用失败抛 5001，调用方不要 commit（本次全部改动作废）。
    """
    try:
        receipt = his.settle_bill(
            bill.bill_id, pay_channel, paid_amount, insurance_paid, payment_id
        )
    except his.HisUnavailable as exc:
        raise BillError(5001, "医院HIS系统调用失败，请稍后重试") from exc

    # HIS 已接入时以其回执的票据号为准，未接入（None）则本地生成
    invoice_no = (receipt or {}).get("invoiceNo") or _generate_invoice_no(bill, now)

    mark_bill_paid(session, bill, invoice_no=invoice_no, now=now)
    return invoice_no


# --------------------------------------------------------------------------- #
# API-16 查询医院账单
# --------------------------------------------------------------------------- #


def list_bills(
    session: Session,
    *,
    user_id: str,
    patient_id: Optional[str] = None,
    bill_type: Optional[str] = None,
    bill_status: Optional[str] = None,
    page_num: int = 1,
    page_size: int = 10,
) -> BillListData:
    """查询当前账号（可指定就诊人）的账单，最近的排最前面。

    billStatus 缺省为 UNPAID（接口文档 3.5.1 明确写了默认值）：进页面先看待缴费，
    要看历史账单得显式传 PAID。
    """
    if bill_type and bill_type not in BILL_TYPES:
        raise BillError(4001, f"账单类型取值不合法：{bill_type}")
    status_filter = bill_status or DEFAULT_BILL_STATUS
    if status_filter not in BILL_STATUSES:
        raise BillError(4001, f"账单状态取值不合法：{bill_status}")

    conditions = [Patient.user_id == user_id, Bill.pay_status == status_filter]
    if patient_id:
        conditions.append(Bill.patient_id == patient_id)
    if bill_type:
        conditions.append(Bill.bill_type == bill_type)

    total = session.scalar(
        select(func.count())
        .select_from(Bill)
        .join(Patient, Bill.patient_id == Patient.patient_id)
        .where(*conditions)
    ) or 0

    rows = session.scalars(
        select(Bill)
        .join(Patient, Bill.patient_id == Patient.patient_id)
        .where(*conditions)
        # t_bill 没有独立的「开单时间」列，created_at 就是开单时间。
        # 种子数据的 created_at 是同一次灌库时间，退到 bill_id 保证顺序稳定。
        .order_by(Bill.created_at.desc(), Bill.bill_id.desc())
        .offset((page_num - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        BillListItem(
            billId=bill.bill_id,
            billType=bill.bill_type,
            billTitle=bill.bill_title or BILL_TYPE_DESC.get(bill.bill_type, "费用"),
            amount=_to_float(bill.amount),
            insuranceCover=_to_float(bill.insurance_cover),
            selfPay=_to_float(bill.self_pay),
            billStatus=bill.pay_status,
            relatedId=bill.related_id,
            createTime=bill.created_at,
        )
        for bill in rows
    ]
    return BillListData(total=total, pageNum=page_num, pageSize=page_size, list=items)


# --------------------------------------------------------------------------- #
# API-17 账单缴费（HIS 端）
# --------------------------------------------------------------------------- #


def _resolve_payment(
    session: Session,
    bill: Bill,
    user_id: str,
    payment_id: Optional[str],
    now: datetime,
) -> Payment:
    """校验并「确认」第三方支付单，返回可据以结算的支付单。

    微信/支付宝渠道必须先经 API-18 建单；真正付没付以网关为准，
    所以 PAYING 的支付单要问一次网关（`pay.query_gateway`），而不是直接认账。
    """
    if not payment_id:
        raise BillError(4001, "走微信/支付宝支付时必须提供 paymentId（请先调用创建支付单接口）")

    payment = _get_payment_for_bill(session, payment_id, bill, user_id)

    if payment.pay_status == "SUCCESS":
        return payment
    if payment.pay_status == "FAIL":
        raise BillError(3002, "支付渠道下单失败，请重新发起支付")
    if payment.pay_status == "CLOSED":
        raise BillError(3003, "支付超时或用户取消支付，请重新发起支付")

    # 仍是 PAYING：先看过期没
    if pay.is_expired(payment.expire_time, now):
        payment.pay_status = "CLOSED"
        session.commit()
        raise BillError(3003, "支付超时或用户取消支付，请重新发起支付")

    # 问网关。桩实现直接回 SUCCESS，等价于「用户已付款、回调已到达」
    gateway_status = pay.query_gateway(payment.payment_id, payment.channel)
    if gateway_status == pay.GATEWAY_SUCCESS:
        payment.pay_status = "SUCCESS"
        payment.paid_at = now
        payment.callback_at = now
        return payment
    if gateway_status == pay.GATEWAY_FAIL:
        payment.pay_status = "FAIL"
        session.commit()
        raise BillError(3002, "支付渠道下单失败，请重新发起支付")

    # 网关说还没成（真的 PAYING），或问不到网关 —— 都不能当成已支付
    raise BillError(3003, "支付尚未完成，请在支付渠道完成付款后重试")


def settle_bill(
    session: Session,
    bill_id: str,
    user_id: str,
    payload: Optional[BillSettleRequest] = None,
) -> BillSettleData:
    """对账单执行缴费确认。

    医保（INSURANCE）与第三方渠道（WECHAT/ALIPAY）的金额拆分不同：
      医保：统筹出 insurance_cover，个人出 self_pay
      第三方：整笔由用户先付（insurance_paid = 0），后续走线下报销
    """
    now = datetime.now()
    bill = get_bill(session, bill_id, user_id)

    if payload is None:
        raise BillError(4001, "缺少请求体：payChannel 必填")
    pay_channel = payload.payChannel
    if pay_channel not in PAY_CHANNELS:
        raise BillError(4001, f"支付渠道取值不合法：{pay_channel}")

    if bill.pay_status != "UNPAID":
        raise BillError(3001, "账单不存在或已缴费")

    if pay_channel == "INSURANCE":
        paid_amount = bill.self_pay
        insurance_paid = bill.insurance_cover
        payment_id: Optional[str] = None
    else:
        payment = _resolve_payment(session, bill, user_id, payload.paymentId, now)
        paid_amount = payment.amount
        insurance_paid = Decimal("0.00")
        payment_id = payment.payment_id

    invoice_no = apply_payment_success(
        session,
        bill,
        pay_channel=pay_channel,
        paid_amount=paid_amount,
        insurance_paid=insurance_paid,
        payment_id=payment_id,
        now=now,
    )
    session.commit()

    return BillSettleData(
        billId=bill.bill_id,
        billStatus="PAID",
        paidAmount=_to_float(paid_amount),
        insurancePaid=_to_float(insurance_paid),
        invoiceNo=invoice_no,
    )


__all__ = [
    "BILL_STATUSES",
    "BILL_TYPES",
    "PAY_CHANNELS",
    "THIRD_PARTY_CHANNELS",
    "BillError",
    "apply_payment_success",
    "get_bill",
    "list_bills",
    "mark_bill_paid",
    "settle_bill",
]
