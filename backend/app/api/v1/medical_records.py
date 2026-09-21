"""病历模块接口（接口文档 3.7）。

  API-22  GET  /medical-records                  历史病历查询
  API-23  POST /medical-records/interpretation   病历AI解读

两个接口都是敏感数据，走接口文档 2.2 的登录鉴权；越权访问他人就诊人由
service 层按 4003 拒绝。响应统一由 app.core.response.Envelope 包成信封。

依赖的公共模块（非本模块职责，由公共基建提供）：
  app.core.deps.get_current_user  —— Bearer JWT 解析出的当前用户（ORM User，取 .user_id）
  app.core.response.Envelope.ok   —— 统一响应信封包装
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.response import Envelope
from app.models import User
from app.schemas.medical_record import InterpretationRequest
from app.services import medical_record_service

router = APIRouter(prefix="/medical-records", tags=["病历"])

SessionDep = Annotated[Session, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("", summary="API-22 历史病历查询")
def list_medical_records(
    session: SessionDep,
    user: UserDep,
    patient_id: Optional[str] = Query(default=None, alias="patientId", description="按就诊人过滤"),
    start_date: Optional[date] = Query(default=None, alias="startDate", description="起始就诊日期"),
    end_date: Optional[date] = Query(default=None, alias="endDate", description="截止就诊日期"),
    page_num: int = Query(default=1, alias="pageNum", ge=1, description="页码"),
    page_size: int = Query(default=10, alias="pageSize", ge=1, le=100, description="每页条数"),
) -> Any:
    """返回当前账号（含被授权家属）的历史病历分页列表。"""
    page = medical_record_service.list_records(
        session,
        user_id=user.user_id,
        patient_id=patient_id,
        start_date=start_date,
        end_date=end_date,
        page_num=page_num,
        page_size=page_size,
    )
    return Envelope.ok(page.model_dump())


@router.post("/interpretation", summary="API-23 病历AI解读")
async def interpret_medical_record(
    payload: InterpretationRequest,
    session: SessionDep,
    user: UserDep,
) -> Any:
    """把病历内容解读成通俗语言。

    recordId 与 rawText（或前端别名 textContent）二选一，都缺失时返回 4001。
    响应强制携带 sources 与 disclaimer，前端须原样展示。
    """
    result = await medical_record_service.interpret(
        session,
        user_id=user.user_id,
        record_id=payload.recordId,
        raw_text=payload.source_text,
        session_id=payload.sessionId,
    )
    return Envelope.ok(result.model_dump())
