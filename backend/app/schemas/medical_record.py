"""病历模块 Pydantic 模型（接口文档 3.7：API-22 历史病历查询 / API-23 病历AI解读）。

统一响应信封 code/message/data/timestamp 由 app.core.response 负责，
本文件只描述信封内 data 字段的形状，故不定义外层包装。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class MedicalRecordBrief(BaseModel):
    """API-22 响应 data.list 内元素。"""

    recordId: str = Field(description="病历ID")
    patientId: str = Field(description="就诊人ID，便于前端跳转详情时携带")
    patientName: str = Field(description="就诊人姓名（脱敏展示）")
    visitDate: str = Field(description="就诊日期 yyyy-MM-dd")
    deptName: str = Field(description="科室名称")
    doctorName: str = Field(description="接诊医生姓名")
    diagnosis: str = Field(description="诊断结果")
    prescriptionBrief: str = Field(description="处方摘要，如“奥司他韦胶囊、布洛芬缓释胶囊 等3种”")
    detailUrl: str = Field(description="病历详情页地址，对应前端路由 /record/:recordId")


class MedicalRecordPage(BaseModel):
    """API-22 分页结构（接口文档 2.1：total / pageNum / pageSize / list）。

    未复用 app.schemas.common，避免与公共模块产生跨文件耦合。
    """

    total: int = Field(description="符合条件的总条数")
    pageNum: int = Field(description="当前页码")
    pageSize: int = Field(description="每页条数")
    # 字段名 list 是接口文档 2.1 的分页约定，它会遮蔽内置 list，
    # 故此处的注解必须写 typing.List，否则 pydantic 求值注解时报 FieldInfo 不可下标。
    list: List[MedicalRecordBrief] = Field(default_factory=list, description="病历列表")


class InterpretationRequest(BaseModel):
    """API-23 请求体。

    接口文档定义为 rawText；前端 frontend/src/api/medicalRecords.js 传的是 textContent，
    两者都接收，取值优先级 rawText > textContent。
    """

    recordId: Optional[str] = Field(default=None, description="病历ID（已结构化病历）")
    rawText: Optional[str] = Field(default=None, description="病历原文（拍照识别文本）")
    textContent: Optional[str] = Field(
        default=None, description="病历原文的别名字段，兼容前端既有调用"
    )
    sessionId: Optional[str] = Field(default=None, description="追问会话ID，支持多轮追问")

    @property
    def source_text(self) -> Optional[str]:
        """请求中携带的病历原文，未提供则为 None。"""
        return self.rawText or self.textContent


class TermMapping(BaseModel):
    """API-23 响应 termMapping 元素：专业术语与通俗解释的对照。"""

    term: str = Field(description="专业术语")
    plain: str = Field(description="通俗解释")


class InterpretationResponse(BaseModel):
    """API-23 响应 data。"""

    interpretation: str = Field(description="通俗化解读文本")
    termMapping: list[TermMapping] = Field(default_factory=list, description="术语对照表")
    followUpUrl: str = Field(description="继续追问入口，跳转 AI 助手")
    sources: list[str] = Field(default_factory=list, description="引用来源")
    disclaimer: str = Field(description="免责声明，前端须原样展示")
