"""支付单业务逻辑（接口文档 3.5.3 API-18、3.5.4 API-19）。

账单相关的领域错误、取数、落库动作都复用 `bill_service`：
支付单是账单的从属实体，两者共享同一套状态机，分成两个 service 只是按接口边界切分。

关于 API-19 的一处反直觉设计：这是一个 **GET，但会推进状态**。
接口文档把它定位为「前端支付完成后主动查询支付结果；支付网关回调为准，
本接口用于结果确认与兜底」—— 项目里没有供支付网关回调的入口（文档 3.5 只有 4 个接口），
所以由这个接口承担「发现网关已收款 → 把账单同步为已缴费」的回调职责。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.bill import Bill
from app.models.payment import Payment
from app.schemas.payment import PaymentCreateData, PaymentCreateRequest, PaymentQueryData
from app.services import bill_service, pay

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# API-18 创建支付单
# --------------------------------------------------------------------------- #


def _next_payment_id(session: Session, now: datetime) -> str:
    """生成支付单号：同一秒内并发下单时靠序号避开主键冲突。"""
    prefix = f"PAY{now:%Y%m%d%H%M%S}"
    used = session.scalar(
        select(func.count()).select_from(Payment).where(Payment.payment_id.like(f"{prefix}%"))
    ) or 0
    return pay.new_payment_id(now, used + 1)


def create_payment(
    session: Session, user_id: str, payload: Optional[PaymentCreateRequest] = None
) -> PaymentCreateData:
    """向支付宝/微信下单，返回前端唤起支付所需的参数。

    金额以服务端账单为准，不接受客户端传入 —— 前端多传的 amount 会被 schema 丢掉。
    """
    if payload is None:
        raise bill_service.BillError(4001, "缺少请求体：billId 与 channel 必填")

    now = datetime.now()
    bill = bill_service.get_bill(session, payload.billId, user_id)

    if payload.channel == "INSURANCE":
        # 医保不走第三方渠道，它有独立的结算接口（API-17），不该在这里建支付单
        raise bill_service.BillError(4001, "医保支付请使用账单结算接口，无需创建支付单")

    if bill.pay_status != "UNPAID":
        raise bill_service.BillError(3001, "账单不存在或已缴费")

    # 先定号再下单：渠道侧的 out_trade_no 用的就是这个号，不能事后对不上
    payment_id = _next_payment_id(session, now)
    pay_params = pay.unified_order(payload.channel, payment_id, bill.amount, payload.returnUrl)
    if pay_params is None:
        raise bill_service.BillError(3002, "支付渠道下单失败，请稍后重试")

    payment = Payment(
        payment_id=payment_id,
        bill_id=bill.bill_id,
        user_id=user_id,
        channel=payload.channel,
        pay_status="PAYING",
        amount=bill.amount,
        pay_params=json.dumps(pay_params, ensure_ascii=False),
        expire_time=pay.expire_time_from(now),
    )
    session.add(payment)
    session.commit()

    logger.info(
        "支付单已创建：%s bill=%s channel=%s", payment.payment_id, bill.bill_id, payload.channel
    )

    return PaymentCreateData(
        paymentId=payment.payment_id,
        channel=payment.channel,
        payParams=pay_params,
        expireTime=payment.expire_time,
    )


# --------------------------------------------------------------------------- #
# API-19 支付结果查询
# --------------------------------------------------------------------------- #


def _get_payment(session: Session, payment_id: str, user_id: str) -> Payment:
    """取支付单并校验归属。不存在与不属于当前账号返回同一个 4003。"""
    payment = session.scalars(
        select(Payment).where(Payment.payment_id == payment_id, Payment.user_id == user_id)
    ).first()
    if payment is None:
        raise bill_service.BillError(4003, "支付单不存在或无权访问")
    return payment


def _settle_linked_bill(session: Session, payment: Payment, now: datetime) -> None:
    """支付网关确认收款后，把关联账单同步为已缴费（承担回调职责）。

    账单可能已被 API-17 提前结算过（用户先点了确认缴费），此时不再重复处理 ——
    `pay_status != UNPAID` 就跳过，避免把票据号覆盖成新的。
    """
    bill = session.get(Bill, payment.bill_id)
    if bill is None:
        logger.warning("支付单 %s 关联的账单 %s 不存在", payment.payment_id, payment.bill_id)
        return
    if bill.pay_status != "UNPAID":
        logger.info("账单 %s 已是 %s，回调不重复结算", bill.bill_id, bill.pay_status)
        return

    # HIS 没同步上时这里抛 5001，本次改动随请求一起丢弃，下次查询再重试
    bill_service.apply_payment_success(
        session,
        bill,
        pay_channel=payment.channel,
        paid_amount=payment.amount,
        insurance_paid=Decimal("0.00"),
        payment_id=payment.payment_id,
        now=now,
    )


def _sync_from_gateway(session: Session, payment: Payment, now: datetime) -> None:
    """问一次网关，必要时推进支付单与账单状态。

    网关是权威：先问它，再决定是否按过期关闭 —— 用户可能在过期那一瞬间付成功，
    先按过期关掉就把这笔钱弄丢了。
    """
    gateway_status = pay.query_gateway(payment.payment_id, payment.channel)

    if gateway_status == pay.GATEWAY_SUCCESS:
        payment.pay_status = "SUCCESS"
        payment.paid_at = payment.paid_at or now
        payment.callback_at = payment.callback_at or now
        _settle_linked_bill(session, payment, now)
        return

    if gateway_status == pay.GATEWAY_FAIL:
        payment.pay_status = "FAIL"
        return

    # 网关说还没成，或问不到网关：只有确实过期了才关闭
    if pay.is_expired(payment.expire_time, now):
        payment.pay_status = "CLOSED"


def get_payment(session: Session, payment_id: str, user_id: str) -> PaymentQueryData:
    """查询支付结果。

    ⚠ 不是纯读：PAYING 的支付单会问一次网关，网关确认收款后本次调用就会
    把支付单与账单一起落库（见模块 docstring）。
    """
    now = datetime.now()
    payment = _get_payment(session, payment_id, user_id)

    if payment.pay_status == "PAYING":
        _sync_from_gateway(session, payment, now)
        session.commit()

    bill = session.get(Bill, payment.bill_id)

    return PaymentQueryData(
        paymentId=payment.payment_id,
        channel=payment.channel,
        payStatus=payment.pay_status,
        paidTime=payment.paid_at,
        billId=payment.bill_id,
        billStatus=bill.pay_status if bill else None,
    )


__all__ = ["create_payment", "get_payment"]
