"""用药提醒接口（接口文档 3.9.2：API-31 生成服药计划与提醒）。

本文件只做 HTTP 适配：把 service 的 dataclass 结果翻成接口文档的 camelCase 字段
（service 层不感知对外契约，字段名是 snake_case），套统一信封。

前端契约：接口文档 3.9.2。**frontend/src/api/ 下目前没有对应的 js 文件**
（用药提醒页面尚未落地），因此这里严格按文档字段输出，不做前端兼容性妥协。

⚠ 服务层还实现了列表/打卡/依从性统计/日历导出等能力（medication_service 的
   list_reminders / check_in / adherence / calendar 等），但接口文档只定义了 API-31
   这一个接口，其余暂不挂出 —— 避免超出契约造出没人认领的接口。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import BizError
from app.core.response import Envelope
from app.db.session import get_session
from app.models import User
from app.services import medication_service

router = APIRouter(prefix="/medication-reminders", tags=["用药与提醒"])

SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]


class MedicationReminderRequest(BaseModel):
    """API-31 请求体（接口文档 3.9.2）。"""

    prescriptionId: str = Field(min_length=1, description="处方ID（来自 API-30）")
    patientId: Optional[str] = Field(default=None, description="就诊人ID，默认本人")
    # 文档没列 startDate，但用药计划总得有个起点；不传按当天（service 的默认行为）
    startDate: Optional[date] = Field(default=None, description="计划起始日期，默认当天")


@router.post("", summary="API-31 生成用药提醒")
def create_medication_reminders(
    payload: MedicationReminderRequest,
    session: SessionDep,
    user: UserDep,
) -> Any:
    """按处方明细生成服药计划与提醒（幂等：重复调用会先清掉旧提醒再写新的）。

    响应含 planItems（药品、剂量、服药时间点、餐前/餐中/饭后）、conflictWarning
    （相互作用风险提示，无则为空）、calendarExportUrl 与强制携带的 disclaimer。

    处方不存在返回 4001；patientId 给出的处方不属于该就诊人时返回 4003。
    本接口只写提醒计划，不做用药建议 —— 免责声明由服务端下发，前端必须原样展示。
    """
    try:
        plan = medication_service.generate_reminders(
            session,
            prescription_id=payload.prescriptionId,
            patient_id=payload.patientId,
            start_date=payload.startDate,
        )
    except LookupError as exc:
        # 处方不存在：归进参数校验（接口文档 2.5 没有「资源不存在」这一档）
        raise BizError(4001, str(exc)) from exc
    except PermissionError as exc:
        raise BizError(4003, "该处方不属于当前就诊人") from exc
    except ValueError as exc:
        raise BizError(2003, f"处方信息无法解析：{exc}") from exc

    return Envelope.ok(
        {
            "reminderId": plan.reminder_id,
            # 文档字段是 reminderId（单个代表编号），整张计划的行编号额外给一份，
            # 前端要逐条打卡时用得着（不拿它当一行用，见 ReminderPlan 的说明）
            "reminderIds": plan.reminder_ids,
            "planItems": [
                {
                    "drugName": item.drug_name,
                    "dose": item.dose,
                    "time": item.time,
                    "mealRelation": item.meal_relation,
                    "remark": item.remark,
                }
                for item in plan.plan_items
            ],
            "conflictWarning": plan.conflict_warning,
            "calendarExportUrl": plan.calendar_export_url,
            "disclaimer": plan.disclaimer,
            # 频次没能识别的药品名（用了兜底时间点），提示前端可让用户手工调
            "unresolved": plan.unresolved,
            "rowCount": plan.row_count,
        }
    )


__all__ = ["router"]
