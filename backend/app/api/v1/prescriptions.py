"""处方（药单）模块接口（接口文档 3.9.1）。

  API-30  GET /prescriptions/current  本次药单查询

敏感数据，走接口文档 2.2 的登录鉴权；越权访问他人就诊人由 service 层按 4003 拒绝。

依赖的公共模块（非本模块职责，由公共基建提供）：
  app.core.deps.get_db            —— 数据库会话依赖
  app.core.deps.get_current_user  —— Bearer JWT 解析出的当前用户
  app.core.response.ok            —— 统一响应信封包装，签名 ok(data)
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.response import ok
from app.services import prescription_service

router = APIRouter(prefix="/prescriptions", tags=["用药"])


def _user_id(current_user: Any) -> str:
    """从当前用户取账号编号。

    get_current_user 返回 ORM User 时读 user_id；若公共基建改成返回令牌载荷 dict，
    这里兼容 sub / userId / user_id 三种键，避免因形态差异导致接口不可用。
    """
    if isinstance(current_user, dict):
        return str(
            current_user.get("sub")
            or current_user.get("userId")
            or current_user.get("user_id")
            or ""
        )
    return str(getattr(current_user, "user_id", "") or "")


@router.get("/current", summary="API-30 本次药单查询")
def get_current_prescription(
    patient_id: Optional[str] = Query(
        default=None, alias="patientId", description="就诊人ID，默认本人"
    ),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> dict:
    """返回本次就诊的整张药单（处方金额 + 所开药品明细）。

    该就诊人尚无处方时 data 为 null，前端据此展示空状态；就诊人不存在或不属于
    当前账号时分别返回 2003 / 4003，按业务失败处理。
    """
    detail = prescription_service.get_current_prescription(
        db,
        user_id=_user_id(current_user),
        patient_id=patient_id,
    )
    return ok(detail.model_dump() if detail is not None else None)
