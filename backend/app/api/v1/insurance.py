"""医保接口（接口文档 3.10.1：API-32 医保智能咨询）。

本文件只做 HTTP 适配：把 service 的 dataclass 结果翻成接口文档的 camelCase 字段
（service 层不感知对外契约，字段名是 snake_case），套统一信封。

前端契约：frontend/src/api/insurance.js 的 consultInsurance({question, sessionId, patientId})
    POST /insurance/consult

⚠ 本模块的 AI 能力（医保知识库检索 + 大模型组织回答）在依赖缺失时**只降级不报错**：
   未装 AI 依赖或知识库没就绪时，service 返回 kb_ready=false 与一段能力受限提示，
   HTTP 仍是 200 + code=0。前端据 kb_ready 决定是否展示「知识库未就绪」的提示条。
   这样做的理由是医保咨询属于咨询类功能，让整页报 5003 比给一段降级话术更糟。
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import BizError
from app.core.response import Envelope
from app.db.session import get_session
from app.models import User
from app.services import insurance_service

router = APIRouter(prefix="/insurance", tags=["医保"])

SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]


class InsuranceConsultRequest(BaseModel):
    """API-32 请求体（接口文档 3.10.1）。"""

    question: str = Field(min_length=1, description="用户医保问题，如「阿莫西林医保能报销多少」")
    sessionId: Optional[str] = Field(default=None, description="会话ID，多轮追问")
    patientId: Optional[str] = Field(
        default=None, description="就诊人ID（用于结合处方做自付金额预估）"
    )


@router.post("/consult", summary="API-32 医保智能咨询")
def consult_insurance(
    payload: InsuranceConsultRequest,
    session: SessionDep,
    user: UserDep,
) -> Any:
    """检索医保知识库并组织回答，返回回复文本、引用来源、自付预估卡片与免责声明。

    estimateCard 只在「知识库片段里有显式报销比例」且「库里取得到金额」两件事同时成立
    时才存在，其余情况为 null；sources 与 disclaimer 前端须原样展示（接口文档 2.8）。
    问题为空返回 4001；sessionId 指向的会话不属于当前账号返回 4003。
    """
    try:
        result = insurance_service.consult(
            session,
            question=payload.question,
            user_id=user.user_id,
            patient_id=payload.patientId,
            session_id=payload.sessionId,
        )
    except ValueError as exc:
        # 空问题、会话不存在等入参问题（service 只用 ValueError 表达这一类）
        raise BizError(4001, str(exc)) from exc

    card = result.estimate_card
    return Envelope.ok(
        {
            "sessionId": result.session_id,
            "answer": result.answer,
            "estimateCard": (
                {
                    "itemName": card.item_name,
                    "reimburseRatio": float(card.reimburse_ratio),
                    "reimburseRatioLabel": card.reimburse_ratio_label,
                    "estimatedSelfPay": float(card.estimated_self_pay),
                    "basis": card.basis,
                }
                if card
                else None
            ),
            "sources": result.sources,
            "disclaimer": result.disclaimer,
            "nextQuestion": result.next_question,
            # 知识库未就绪时为 false，此时 answer 是能力受限提示而非答案
            "kbReady": result.kb_ready,
        }
    )


__all__ = ["router"]
