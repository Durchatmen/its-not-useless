"""账单接口（接口文档 3.5.1 API-16、3.5.2 API-17）。

与 exams 模块同样的分层：本文件只做 HTTP 适配（解析入参、取当前账号、
把领域错误翻成接口文档 2.5 的错误码、套统一信封），业务规则全在
`services/bill_service.py`。

⚠ 对接说明（core/ 目前是空文件，本模块按《环境搭建方案》§4.7 的约定引用）：
    app.core.deps.get_current_user  —— Bearer 鉴权依赖，返回 t_user 对象（取 .user_id）
    app.core.response.ok            —— 统一信封 code/message/data/timestamp
    app.core.errors.BizError        —— 业务异常，由全局异常处理器输出信封
  这三处是唯一的耦合点，core 落地时若命名不同，改上面的 import 即可。

另：请求体的字段校验失败（如 payChannel 缺失）由 FastAPI 抛 422，按项目约定
    由 core 的全局异常处理器统一翻成 4001，本模块不重复拦截。
"""

from __future__ import annotations

from typing import Annotated, Any, Callable, Optional

from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user  # type: ignore[attr-defined]
from app.core.errors import BizError  # type: ignore[attr-defined]
from app.core.response import ok  # type: ignore[attr-defined]
from app.db.session import get_session
from app.schemas.bill import BillSettleRequest
from app.services import bill_service
from app.services.bill_service import BillError

router = APIRouter(prefix="/bills", tags=["支付模块"])

SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[Any, Depends(get_current_user)]

BillId = Annotated[str, Path(description="账单ID")]


def _call(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """执行业务函数并套统一信封。

    BillError → BizError 的转换收在这一处：service 不依赖 core，core 不感知
    支付模块的错误码（3001/3002/3003），两边各自独立。
    """
    try:
        data = action(*args, **kwargs)
    except BillError as exc:
        raise BizError(exc.code, exc.message) from exc
    return ok(data)


@router.get("", summary="API-16 查询医院账单")
def list_bills(
    session: SessionDep,
    user: UserDep,
    patientId: Annotated[
        Optional[str], Query(description="就诊人编号，不传返回该账号下全部就诊人的账单")
    ] = None,
    billType: Annotated[
        Optional[str], Query(description="账单类型：REGISTRATION 挂号缴费 / TREATMENT 就诊缴费")
    ] = None,
    billStatus: Annotated[
        Optional[str],
        Query(description="账单状态：UNPAID 待缴费 / PAID 已缴费 / REFUNDED 已退费，缺省 UNPAID"),
    ] = None,
    pageNum: Annotated[int, Query(ge=1, description="页码，从 1 开始")] = 1,
    pageSize: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 10,
) -> Any:
    """查询当前账号（可指定就诊人）的账单，最近的排在最前面。

    每项返回账单名称、总金额、医保预估报销与自付金额、状态，供「缴费」列表页展示；
    billStatus 不传时只看待缴费（接口文档 3.5.1 的默认值），查历史账单需显式传 PAID。
    """
    return _call(
        bill_service.list_bills,
        session,
        user_id=user.user_id,
        patient_id=patientId,
        bill_type=billType,
        bill_status=billStatus,
        page_num=pageNum,
        page_size=pageSize,
    )


@router.post("/{billId}/settle", summary="API-17 账单缴费")
def settle_bill(
    billId: BillId,
    session: SessionDep,
    user: UserDep,
    payload: Annotated[Optional[BillSettleRequest], Body()] = None,
) -> Any:
    """对账单执行缴费确认，成功后返回实付金额、医保统筹金额与电子票据号。

    医保（INSURANCE）直接结算；微信/支付宝（WECHAT/ALIPAY）必须先经 API-18
    创建支付单，再把 paymentId 传进来。
    缴费成功后同步推进关联业务状态：账单关联检查单时，检查单由「待缴费」转为「待检查」。
    """
    return _call(bill_service.settle_bill, session, billId, user.user_id, payload)


__all__ = ["router"]
