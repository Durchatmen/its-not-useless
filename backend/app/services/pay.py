"""第三方支付渠道接入层（支付宝 / 微信统一下单、查单）。

⚠ 当前是**桩实现**：`backend/.env` 里没有支付宝/微信的商户号、应用私钥、
   证书等凭据，config.py 也没有对应字段，所以无法真正调起下单接口。
   本文件把「下单」与「查单」两种情况收敛在那两个函数里：接入真实网关时
   只改 `unified_order` 与 `query_gateway`，上层（payment_service / bill_service）
   一行都不用动。

桩的行为（已与需求方确认）：
    下单返回合成的渠道唤起参数，支付单落库为 PAYING；
    查单直接返回 SUCCESS，模拟「用户已付款、支付网关已回调」。
于是 创建支付单 → 查询支付结果 这条链路在无商户号的情况下也能完整跑通。

真实环境下 query_gateway 应当调用：
    微信   GET  https://api.mch.weixin.qq.com/v3/pay/transactions/out-trade-no/{out_trade_no}
    支付宝 POST alipay.trade.query
并把返回的 trade_state / trade_status 映射成下面的 SUCCESS / FAIL / PAYING。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 接口文档 3.5.3：支付单过期时间默认 15 分钟
PAY_EXPIRE_MINUTES = 15

# 网关侧交易状态，与 t_payment.pay_status 的取值保持一致
GATEWAY_SUCCESS = "SUCCESS"
GATEWAY_FAIL = "FAIL"
GATEWAY_PAYING = "PAYING"


def mock_enabled() -> bool:
    """是否使用桩实现。

    目前恒为 True —— 没有配置商户凭据。接入真实网关后改成
    「读 config 里的商户号与私钥，任一缺失则仍走桩」。
    """
    return True


def unified_order(
    channel: str,
    payment_id: str,
    amount: Decimal,
    return_url: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """向渠道下单，返回前端唤起支付所需的参数。

    返回 None 表示下单失败，调用方转接口文档 2.5 的 3002（支付渠道下单失败）。
    """
    if not mock_enabled():
        logger.error("未实现的真实网关下单路径：channel=%s payment_id=%s", channel, payment_id)
        return None

    if amount <= 0:
        logger.warning("支付金额非正数，拒绝下单：payment_id=%s amount=%s", payment_id, amount)
        return None

    if channel == "WECHAT":
        # 真实环境返回 code_url（NATIVE 扫码）或 JSAPI 的 prepay_id + 签名参数
        return {
            "trade_type": "NATIVE",
            "code_url": f"weixin://wxpay/bizpayurl?pr={payment_id}",
            "prepay_id": f"wx{payment_id}",
        }
    if channel == "ALIPAY":
        # 真实环境返回一个自动提交的跳转表单参数
        params = {
            "out_trade_no": payment_id,
            "total_amount": f"{amount:.2f}",
            "product_code": "FAST_INSTANT_TRADE_PAY",
        }
        if return_url:
            params["return_url"] = return_url
        return params

    logger.error("未知支付渠道：%s", channel)
    return None


def query_gateway(payment_id: str, channel: str) -> Optional[str]:
    """查单：问支付网关这笔交易最终成了没有。

    返回 SUCCESS / FAIL / PAYING；返回 None 表示网关不可用（调用方保持原状态，
    不要把「问不到」当成「支付失败」）。

    桩实现直接返回 SUCCESS，即「用户已付款且网关已回调」。
    """
    if not mock_enabled():
        logger.error("未实现的真实网关查单路径：channel=%s payment_id=%s", channel, payment_id)
        return None

    logger.info("桩网关查单：payment_id=%s channel=%s → SUCCESS", payment_id, channel)
    return GATEWAY_SUCCESS


def expire_time_from(now: datetime) -> datetime:
    """支付单过期时间 = 下单时间 + 15 分钟。"""
    return now + timedelta(minutes=PAY_EXPIRE_MINUTES)


def is_expired(expire_time: Optional[datetime], now: datetime) -> bool:
    """支付单是否已过期。未落过期时间的按未过期处理（历史数据容错）。"""
    return expire_time is not None and expire_time <= now


def new_payment_id(now: datetime, seq: int) -> str:
    """生成支付单号。

    形如 PAY20260921143012001：时间前缀便于排查，末三位是同秒序号避开主键冲突。
    真实环境应当用渠道侧的 out_trade_no 规则，这里保持与 seed 的 PAY#### 风格一致但更唯一。
    """
    return f"PAY{now:%Y%m%d%H%M%S}{seq:03d}"


__all__ = [
    "GATEWAY_FAIL",
    "GATEWAY_PAYING",
    "GATEWAY_SUCCESS",
    "PAY_EXPIRE_MINUTES",
    "expire_time_from",
    "is_expired",
    "mock_enabled",
    "new_payment_id",
    "query_gateway",
    "unified_order",
]
