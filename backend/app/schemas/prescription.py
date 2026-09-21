"""处方（药单）模块 Pydantic 模型（接口文档 3.9.1：API-30 本次药单查询）。

“所开药品”即响应中的 drugs 数组，字段与接口文档 3.9.1 逐一对应。
金额按接口文档 2.1 约定：单位为元、保留两位小数、JSON 中为数字类型。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DrugItem(BaseModel):
    """API-30 响应 data.drugs 内元素，来自 t_prescription_item 关联 t_medication。"""

    drugId: str = Field(description="药品编号")
    drugName: str = Field(description="药品名称")
    specification: Optional[str] = Field(default=None, description="规格，如“0.25g×24粒”")
    dosage: Optional[str] = Field(default=None, description="单次剂量，如“0.5g”")
    frequency: Optional[str] = Field(default=None, description="用药频次，如“每日三次”")
    usage: Optional[str] = Field(default=None, description="用法，如“饭后服用”")
    days: Optional[int] = Field(default=None, description="疗程天数")
    insuranceType: Optional[str] = Field(
        default=None, description="医保属性：甲类 / 乙类 / 自费（由库中 A/B/SELF 转写）"
    )
    instructions: Optional[str] = Field(default=None, description="说明书要点（默认用法用量）")
    contraindication: Optional[str] = Field(default=None, description="禁忌与副作用要点")


class PrescriptionDetail(BaseModel):
    """API-30 响应 data：本次就诊的整张药单。"""

    prescriptionId: str = Field(description="处方编号")
    visitDate: Optional[str] = Field(default=None, description="就诊日期 yyyy-MM-dd")
    deptName: Optional[str] = Field(default=None, description="开方科室名称")
    doctorName: Optional[str] = Field(default=None, description="开方医生姓名")
    totalAmount: float = Field(description="处方总金额（元）")
    insuranceCover: float = Field(description="医保预估报销金额（元）")
    selfPay: float = Field(description="预估自付金额（元）")
    drugs: list[DrugItem] = Field(default_factory=list, description="所开药品明细")
