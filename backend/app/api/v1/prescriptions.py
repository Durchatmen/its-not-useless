"""处方（药单）模块接口（接口文档 3.9.1）。

  API-30  GET /prescriptions/current  本次药单查询

敏感数据，走接口文档 2.2 的登录鉴权；越权访问他人就诊人由 service 层按 4003 拒绝。

依赖的公共模块（非本模块职责，由公共基建提供）：
  app.core.deps.get_current_user  —— Bearer JWT 解析出的当前用户（ORM User，取 .user_id）
  app.core.response.Envelope.ok   —— 统一响应信封包装
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.response import Envelope
from app.models import User
from app.services import prescription_service

router = APIRouter(prefix="/prescriptions", tags=["用药"])

SessionDep = Annotated[Session, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/current", summary="API-30 本次药单查询")
def get_current_prescription(
    session: SessionDep,
    user: UserDep,
    patient_id: Optional[str] = Query(
        default=None, alias="patientId", description="就诊人ID，默认本人"
    ),
) -> Any:
    """返回本次就诊的整张药单（处方金额 + 所开药品明细）。

    该就诊人尚无处方时 data 为 null，前端据此展示空状态；就诊人不存在或不属于
    当前账号时分别返回 2003 / 4003，按业务失败处理。
    """
    detail = prescription_service.get_current_prescription(
        session,
        user_id=user.user_id,
        patient_id=patient_id,
    )
    return Envelope.ok(detail.model_dump() if detail is not None else None)
