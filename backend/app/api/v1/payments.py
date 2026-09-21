"""支付单接口（接口文档 3.5.3 API-18、3.5.4 API-19）。

与 bills.py 同样的薄适配层，业务规则在 `services/payment_service.py`，
账单侧的领域错误与落库动作复用 `services/bill_service.py`。

⚠ 与 bills.py 共用同一组 core 约定（get_current_user / ok / BizError），
   详情见 `api/v1/bills.py` 的模块说明。
"""

from __future__ import annotations

from typing import Annotated, Any, Callable, Optional

from fastapi import APIRouter, Body, Depends, Path
from sqlalchemy.orm import Session

from app.core.deps import get_current_user  # type: ignore[attr-defined]
from app.core.errors import BizError  # type: ignore[attr-defined]
from app.core.response import ok  # type: ignore[attr-defined]
from app.db.session import get_session
from app.schemas.payment import PaymentCreateRequest
from app.services import payment_service
from app.services.bill_service import BillError

router = APIRouter(prefix="/payments", tags=["支付模块"])

SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[Any, Depends(get_current_user)]

PaymentId = Annotated[str, Path(description="支付单ID")]


def _call(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """执行业务函数并套统一信封（与 bills.py 同一套错误码转换）。"""
    try:
        data = action(*args, **kwargs)
    except BillError as exc:
        raise BizError(exc.code, exc.message) from exc
    return ok(data)


@router.post("", summary="API-18 创建支付单")
def create_payment(
    session: SessionDep,
    user: UserDep,
    payload: Annotated[Optional[PaymentCreateRequest], Body()] = None,
) -> Any:
    """调用支付宝/微信统一下单，返回前端唤起支付所需的参数。

    金额以服务端账单为准，请求体里传 amount 会被忽略；支付单默认 15 分钟过期。
    医保支付不走本接口（请用 API-17 账单缴费）。
    """
    return _call(payment_service.create_payment, session, user.user_id, payload)


@router.get("/{paymentId}", summary="API-19 支付结果查询")
def get_payment(paymentId: PaymentId, session: SessionDep, user: UserDep) -> Any:
    """查询支付结果：支付状态、支付时间，以及账单当前状态。

    ⚠ 不是纯读接口：支付中的支付单会向支付网关查一次单，网关确认收款后
    本次调用就会把支付单与账单一起落库（接口文档把它定位为「结果确认与兜底」）。
    """
    return _call(payment_service.get_payment, session, paymentId, user.user_id)


__all__ = ["router"]
