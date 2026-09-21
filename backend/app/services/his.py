"""医院 HIS 系统调用接缝。

HIS 是院内真实业务系统的边界：账单结算、检查状态回写这些动作，按接口文档
3.5.2 的说法「缴费成功后 HIS 侧状态同步更新」，权威数据在 HIS 那边，本地库
只是影子副本。本文件是这条边界的唯一出口，业务代码不直接发 HTTP。

当前状态：`backend/.env` 里 HIS_ENABLED 未开（默认 false）、HIS_BASE_URL 也是空的，
所以 `is_enabled()` 返回 False，所有调用直接返回 None，**调用方转而更新本地库**。
这样在没有院内联调环境时，支付模块依然能完整跑通；等 HIS 开通了，
只要把 HIS_ENABLED/HIS_BASE_URL 配上、按院内接口核对 `_PATHS` 与字段名即可。

设计取舍：HIS 未启用 = 静默走本地库（None）；HIS 已启用但调不通 = 抛
`HisUnavailable`，由 service 转接口文档 2.5 的 5001。两种情况必须分开 ——
「没接 HIS」不该报错，「接了但坏了」不能假装成功。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# 单次调用超时（秒）。HIS 是同步调用，不能让一次转账卡住整个请求
TIMEOUT_SECONDS = 5.0

# 院内接口路径，联调时按 HIS 实际路径核对
_PATHS: dict[str, str] = {
    "settle_bill": "/api/his/bill/settle",
    "sync_exam_status": "/api/his/exam/status",
}


class HisUnavailable(Exception):
    """HIS 已启用但调用失败（网络、超时、非 2xx、返回体不符合预期）。

    service 层把它转成接口文档 2.5 的 5001（医院HIS系统调用失败）。
    """


def is_enabled() -> bool:
    """HIS 是否已接入。两个开关都要有：只填 URL 不开开关视为没接。"""
    return bool(settings.his_enabled and settings.his_base_url)


def _post(path_key: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """POST 到 HIS。

    未启用 → None（调用方走本地库）；启用但失败 → 抛 HisUnavailable。
    """
    if not is_enabled():
        logger.debug("HIS 未启用，跳过调用：%s", path_key)
        return None

    url = settings.his_base_url.rstrip("/") + _PATHS[path_key]
    try:
        response = httpx.post(url, json=payload, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("HIS 调用失败：%s %s", url, exc, exc_info=True)
        raise HisUnavailable(f"HIS 调用失败：{path_key}") from exc

    if not isinstance(body, dict):
        raise HisUnavailable(f"HIS 返回体不是对象：{path_key}")
    return body


def settle_bill(
    bill_id: str,
    pay_channel: str,
    paid_amount: Decimal,
    insurance_paid: Decimal,
    payment_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """把缴费结果同步给 HIS，返回 HIS 侧回执（含电子票据号）。

    返回 None 表示 HIS 未接入，调用方自行生成票据号并更新本地库。
    """
    return _post(
        "settle_bill",
        {
            "billId": bill_id,
            "payChannel": pay_channel,
            "paymentId": payment_id,
            "paidAmount": f"{paid_amount:.2f}",
            "insurancePaid": f"{insurance_paid:.2f}",
        },
    )


def sync_exam_status(exam_id: str, exam_status: str) -> bool:
    """把检查单状态回写 HIS（如缴费后 WAIT_PAY → WAIT_EXAM）。

    返回 True 表示 HIS 已接收；False 表示 HIS 未接入（调用方只更新本地库）。
    """
    receipt = _post("sync_exam_status", {"examId": exam_id, "examStatus": exam_status})
    return receipt is not None


__all__ = ["HisUnavailable", "is_enabled", "settle_bill", "sync_exam_status"]
