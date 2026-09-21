"""病历模块接口（接口文档 3.7）。

  API-22  GET  /medical-records                  历史病历查询
  API-23  POST /medical-records/interpretation   病历AI解读

两个接口都是敏感数据，走接口文档 2.2 的登录鉴权；越权访问他人就诊人由
service 层按 4003 拒绝。响应统一由 app.core.response.ok 包成信封。

依赖的公共模块（非本模块职责，由公共基建提供）：
  app.core.deps.get_db            —— 数据库会话依赖
  app.core.deps.get_current_user  —— Bearer JWT 解析出的当前用户
  app.core.response.ok            —— 统一响应信封包装，签名 ok(data)
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.response import ok
from app.schemas.medical_record import InterpretationRequest
from app.services import medical_record_service

router = APIRouter(prefix="/medical-records", tags=["病历"])


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


@router.get("", summary="API-22 历史病历查询")
def list_medical_records(
    patient_id: Optional[str] = Query(default=None, alias="patientId", description="按就诊人过滤"),
    start_date: Optional[date] = Query(default=None, alias="startDate", description="起始就诊日期"),
    end_date: Optional[date] = Query(default=None, alias="endDate", description="截止就诊日期"),
    page_num: int = Query(default=1, alias="pageNum", ge=1, description="页码"),
    page_size: int = Query(default=10, alias="pageSize", ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> dict:
    """返回当前账号（含被授权家属）的历史病历分页列表。"""
    page = medical_record_service.list_records(
        db,
        user_id=_user_id(current_user),
        patient_id=patient_id,
        start_date=start_date,
        end_date=end_date,
        page_num=page_num,
        page_size=page_size,
    )
    return ok(page.model_dump())


@router.post("/interpretation", summary="API-23 病历AI解读")
async def interpret_medical_record(
    payload: InterpretationRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> dict:
    """把病历内容解读成通俗语言。

    recordId 与 rawText（或前端别名 textContent）二选一，都缺失时返回 4001。
    响应强制携带 sources 与 disclaimer，前端须原样展示。
    """
    result = await medical_record_service.interpret(
        db,
        user_id=_user_id(current_user),
        record_id=payload.recordId,
        raw_text=payload.source_text,
        session_id=payload.sessionId,
    )
    return ok(result.model_dump())
