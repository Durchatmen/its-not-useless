"""就诊人模块数据契约（《接口文档》3.2：API-04 ~ API-07）。

字段名与接口文档一致（camelCase、主键 string），前端 frontend/src/api/patients.js
直接对接，中间没有 snake→camel 转换层。

脱敏约定（接口文档 2.2、API-04 响应说明）
    列表响应里的 name / idcard / phone 都是**已脱敏**的字符串（如「张*生」），
    service 层在出口统一处理，本文件不做二次加工。
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.common import Relation
from app.utils.validators import IDCARD_PATTERN

# 与本人关系，取值以接口文档 2.6 枚举表为准（schemas/common.Relation 是同一套值，
# 这里用 Literal 是因为 request 模型要直接参与 FastAPI 的入参校验与 OpenAPI 生成）
RelationValue = Literal["SELF", "SPOUSE", "CHILD", "PARENT", "OTHER"]

RELATION_DESC: dict[str, str] = {
    Relation.SELF.value: "本人",
    Relation.SPOUSE.value: "配偶",
    Relation.CHILD.value: "子女",
    Relation.PARENT.value: "父母",
    Relation.OTHER.value: "其他",
}

GenderValue = Literal["M", "F"]

GENDER_DESC: dict[str, str] = {"M": "男", "F": "女"}


class PatientListItem(BaseModel):
    """就诊人列表项（接口文档 API-04 响应 data.list 内元素）。"""

    patientId: str
    name: Optional[str] = Field(default=None, description="姓名（脱敏，如「张*生」）")
    idcard: Optional[str] = Field(default=None, description="身份证号（脱敏）")
    phone: Optional[str] = Field(default=None, description="手机号（脱敏）")
    gender: Optional[str] = Field(default=None, description="性别：M男 F女")
    birthDate: Optional[date] = Field(default=None, description="出生日期")
    relation: Optional[str] = Field(default=None, description="与账号本人关系，见枚举字典")
    relationDesc: Optional[str] = Field(default=None, description="关系中文名，供前端直接展示")
    bloodType: Optional[str] = Field(default=None, description="血型")
    allergyHistory: Optional[str] = Field(default=None, description="过敏史")
    medicalHistory: Optional[str] = Field(default=None, description="既往病史")
    isDefault: bool = Field(default=False, description="是否默认就诊人")


class PatientListData(BaseModel):
    """分页信封（接口文档 2.1 分页约定）。

    接口文档 API-04 只写了「data.list 内元素」，没写分页参数；但全局约定 2.1
    要求分页响应在 data 中返回 total/pageNum/pageSize/list，且前端 patients.js
    调本接口时不传分页参数。这里按全局约定返回完整信封，是文档的超集。
    """

    total: int
    pageNum: int
    pageSize: int
    list: list[PatientListItem]


class PatientCreateRequest(BaseModel):
    """新增就诊人请求体（接口文档 API-05）。

    必填项与文档一致：name / idcard / gender / birthDate / relation。
    身份证号只校验 18 位格式（与注册接口 app/schemas/auth.py 同口径），
    校验位是否合法交给 service，以使失败时返回业务码 2003 而不是 4001。
    """

    name: str = Field(min_length=1, max_length=32, description="姓名")
    idcard: str = Field(pattern=IDCARD_PATTERN.pattern, description="18位身份证号")
    phone: Optional[str] = Field(default=None, description="手机号")
    gender: GenderValue = Field(description="性别：M男 F女")
    birthDate: date = Field(description="出生日期 yyyy-MM-dd")
    relation: RelationValue = Field(description="与本人关系，见枚举字典")
    bloodType: Optional[str] = Field(default=None, max_length=8, description="血型")
    allergyHistory: Optional[str] = Field(default=None, description="过敏史")
    medicalHistory: Optional[str] = Field(default=None, description="既往病史")
    isDefault: bool = Field(default=False, description="是否设为默认就诊人")


class PatientUpdateRequest(BaseModel):
    """修改就诊人请求体（接口文档 API-06：字段同 3.2.2，全部可选）。

    区分「未传」与「显式传 null」需要 fields_set，本接口不做这个区分：
    传了 null 就当作清空该字段，未传则保持原值。
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=32)
    idcard: Optional[str] = Field(default=None, pattern=IDCARD_PATTERN.pattern)
    phone: Optional[str] = None
    gender: Optional[GenderValue] = None
    birthDate: Optional[date] = None
    relation: Optional[RelationValue] = None
    bloodType: Optional[str] = Field(default=None, max_length=8)
    allergyHistory: Optional[str] = None
    medicalHistory: Optional[str] = None
    isDefault: Optional[bool] = None


class PatientCreateData(BaseModel):
    """API-05 响应 data：patientId（新建就诊人ID）。"""

    patientId: str


__all__ = [
    "GENDER_DESC",
    "RELATION_DESC",
    "GenderValue",
    "PatientCreateData",
    "PatientCreateRequest",
    "PatientListItem",
    "PatientListData",
    "PatientUpdateRequest",
    "RelationValue",
]
