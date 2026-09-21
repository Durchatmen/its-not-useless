"""就诊人接口（接口文档 3.2：API-04 列表 / API-05 新增 / API-06 修改 / API-07 删除）。

本文件只做 HTTP 适配：解析入参、取当前账号、把领域错误翻成接口文档 2.5 的错误码、
套统一信封（Envelope）。业务规则全在 `services/patient_service.py`。

前端契约：frontend/src/api/patients.js
    GET    /patients
    POST   /patients
    PUT    /patients/{patientId}
    DELETE /patients/{patientId}
"""

from __future__ import annotations

from typing import Annotated, Any, Callable, Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import BizError
from app.core.response import Envelope
from app.db.session import get_session
from app.models import User
from app.schemas.patient import PatientCreateRequest, PatientUpdateRequest
from app.services import patient_service
from app.services.patient_service import PatientError

router = APIRouter(prefix="/patients", tags=["就诊人管理"])

SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]

PatientId = Annotated[str, Path(description="就诊人ID")]


def _call(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """执行业务函数并套统一信封。

    PatientError → BizError 的转换收在这一处：service 不依赖 core，core 不感知
    就诊人模块的错误码（2002/2003），两边各自独立。
    """
    try:
        data = action(*args, **kwargs)
    except PatientError as exc:
        raise BizError(exc.code, exc.message) from exc
    return Envelope.ok(data)


@router.get("", summary="API-04 查询就诊人列表")
def list_patients(
    session: SessionDep,
    user: UserDep,
    keyword: Annotated[
        Optional[str], Query(description="按姓名模糊搜索，不传返回全部就诊人")
    ] = None,
    pageNum: Annotated[int, Query(ge=1, description="页码，从 1 开始")] = 1,
    pageSize: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 50,
) -> Any:
    """查询当前登录账号绑定的全部就诊人及健康档案概览（过敏史、既往病史、血型等）。

    姓名、身份证号、手机号均已脱敏（接口文档 2.2），默认就诊人排在最前。
    已删除的就诊人不出现在结果里（软删，见 patient_service 的说明）。
    """
    return _call(
        patient_service.list_patients,
        session,
        user_id=user.user_id,
        keyword=keyword,
        page_num=pageNum,
        page_size=pageSize,
    )


@router.post("", summary="API-05 新增就诊人")
def create_patient(
    payload: PatientCreateRequest,
    session: SessionDep,
    user: UserDep,
) -> Any:
    """添加家庭成员为就诊人，返回新建就诊人ID。

    同一账号下身份证号重复返回 1002（接口文档原文口径）；身份证号校验位不合法返回 2003。
    isDefault=true 时会把同账号其它就诊人的默认标记清掉，保证默认就诊人唯一。
    """
    return _call(patient_service.create_patient, session, user_id=user.user_id, payload=payload)


@router.put("/{patientId}", summary="API-06 修改就诊人")
def update_patient(
    patientId: PatientId,
    payload: PatientUpdateRequest,
    session: SessionDep,
    user: UserDep,
) -> Any:
    """修改就诊人资料，请求体字段全部可选（接口文档 3.2.3）。

    只更新请求体里出现过的字段；就诊人不存在或不属于当前账号返回 4003。
    改身份证号时会重新判重，撞上同账号下另一人返回 1002。
    """
    return _call(
        patient_service.update_patient,
        session,
        patientId,
        user_id=user.user_id,
        payload=payload,
    )


@router.delete("/{patientId}", summary="API-07 删除就诊人")
def delete_patient(patientId: PatientId, session: SessionDep, user: UserDep) -> Any:
    """解绑并删除就诊人（软删，保留其历史挂号/病历的归属）。

    存在未完成挂号单时返回 2002，需先取消挂号。
    """
    return _call(patient_service.delete_patient, session, patientId, user_id=user.user_id)


__all__ = ["router"]
