"""检查模块的请求/响应模型（接口文档 3.8，API-24 ~ API-29，另有检查列表）。

字段名一律与接口文档保持一致（camelCase、主键按 string 序列化），
这样 schema 本身就是对接说明，Swagger 上看到的即前端拿到的。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_serializer

# 检查状态与报告状态的取值，供 schema 与 service 共用
ExamStatus = Literal["WAIT_PAY", "WAIT_EXAM", "WAIT_REPORT", "REPORTED"]
ReportStatus = Literal["WAIT_REPORT", "REPORTED"]
AbnormalFlag = Literal["NORMAL", "HIGH", "LOW"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]

# 强制免责声明（接口文档 3.7.6 / 3.8.6 统一口径）
DISCLAIMER = "以上解读仅为辅助参考，不构成医疗诊断，最终以医疗机构和执业医师意见为准"

# 报告解读的预计等待说明（估算值，接口文档 3.8.2）
WAIT_ESTIMATE_NOTE = "预计等待时间由前方人数估算，实际以现场叫号为准"


class KnowledgeSource(BaseModel):
    """知识库引用来源，前端在答案下方展示可溯源片段。"""

    title: str = Field(description="标题面包屑，如「一、血常规 > 1.1 白细胞计数 WBC」")
    sourceFile: str = Field(description="来源文件，如「报告知识库/医学检验常见异常指标解读知识库.md」")
    snippet: str = Field(description="命中片段节选，便于用户核对原文")


# --------------------------------------------------------------------------- #
# 检查列表
# --------------------------------------------------------------------------- #


class ExamListItem(BaseModel):
    """列表项。除接口文档 3.8.3 的位置字段外，额外带上报告与就诊人信息，
    家庭账号（一人账号全家就医）下需要靠 patientName 区分是谁的检查。
    """

    examId: str
    examName: str
    examStatus: ExamStatus
    statusDesc: str = Field(description="状态中文描述，前端进度条直接展示")
    patientId: str
    patientName: str
    deptId: Optional[str] = Field(default=None, description="执行科室编号，未匹配到科室时为 null")
    deptName: str = Field(description="执行科室名称，如「医学影像科」")
    building: Optional[str] = None
    floor: Optional[str] = None
    room: Optional[str] = None
    locationText: Optional[str] = Field(default=None, description="拼接好的位置，如「医技楼1F影像中心CT-2室」")
    examDate: Optional[date] = Field(default=None, description="检查日期，取预约日期，缺省回落开单日期")
    queueNo: Optional[str] = None
    reportId: Optional[str] = None
    reportStatus: Optional[ReportStatus] = None


class ExamListData(BaseModel):
    """分页信封（接口文档 2.1 分页约定）。"""

    total: int
    pageNum: int
    pageSize: int
    list: list[ExamListItem]


# --------------------------------------------------------------------------- #
# API-27 检查报告查询
# --------------------------------------------------------------------------- #


class ExamReportItem(BaseModel):
    """报告指标项，对应 t_exam_report.items_json 的单条结构。"""

    itemName: str
    value: Optional[str] = None
    unit: Optional[str] = None
    referenceRange: Optional[str] = None
    abnormalFlag: AbnormalFlag = "NORMAL"


class ExamReportData(BaseModel):
    examId: str
    examName: str
    reportId: Optional[str] = Field(default=None, description="报告ID，报告尚未生成时为 null")
    reportStatus: ReportStatus
    reportTime: Optional[datetime] = Field(default=None, description="报告时间，未出报告为 null")
    reportContent: Optional[str] = Field(default=None, description="报告结论文本，如「双肺纹理增粗」")
    items: list[ExamReportItem] = Field(default_factory=list)
    reportImageUrl: Optional[str] = None

    @field_serializer("reportTime")
    def _serialize_report_time(self, value: Optional[datetime]) -> Optional[str]:
        """接口文档 2.1：时间统一 yyyy-MM-dd HH:mm:ss，避免默认的 ISO 8601（带 T）。"""
        return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


# --------------------------------------------------------------------------- #
# API-29 检查报告 AI 分析
# --------------------------------------------------------------------------- #


class ExamAnalysisRequest(BaseModel):
    """三个字段全部可选：不带 body 时按 examId 直接解读库内报告。"""

    reportId: Optional[str] = Field(default=None, description="报告ID，缺省取该检查单关联报告")
    sessionId: Optional[str] = Field(default=None, description="追问会话ID，支持多轮追问")
    imageData: Optional[str] = Field(default=None, description="纸质报告拍照图片 Base64，本期透传不解析")


class AbnormalItemMeaning(BaseModel):
    """异常项 + 通俗解释，前端用 AbnormalItemList 组件渲染。"""

    itemName: str
    value: Optional[str] = None
    abnormalFlag: AbnormalFlag = "NORMAL"
    meaning: str = Field(description="临床意义的通俗解释，来自报告知识库")


class ExamAnalysisData(BaseModel):
    examId: str
    examName: str
    reportId: Optional[str] = Field(default=None, description="报告ID")
    analysis: str = Field(description="报告分析文本")
    abnormalItems: list[AbnormalItemMeaning] = Field(default_factory=list)
    riskLevel: RiskLevel
    advice: str = Field(description="初步健康建议（非诊断）")
    followUpUrl: Optional[str] = Field(default=None, description="追问入口链接，跳转 AI 会话继续问")
    sources: list[KnowledgeSource] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


# --------------------------------------------------------------------------- #
# API-24 检查注意事项
# --------------------------------------------------------------------------- #


class ExamPrecautionsData(BaseModel):
    examId: str
    examName: str
    precautions: str = Field(description="注意事项文本，按行分条")
    purpose: Optional[str] = Field(default=None, description="检查目的（检查知识库）")
    process: Optional[str] = Field(default=None, description="检查流程（检查知识库）")
    voiceText: str = Field(description="语音播报文本，已去掉 Markdown 与符号")
    sources: list[KnowledgeSource] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


# --------------------------------------------------------------------------- #
# API-25 检查叫号查询
# --------------------------------------------------------------------------- #


class ExamQueueData(BaseModel):
    examId: str
    examName: str
    queueNo: Optional[str] = Field(default=None, description="我的排队号")
    currentNo: Optional[str] = Field(default=None, description="当前叫号")
    peopleAhead: Optional[int] = Field(default=None, description="前方人数")
    estimatedWaitMinutes: Optional[int] = Field(default=None, description="预计等待分钟数（估算值）")
    estimateNote: str = WAIT_ESTIMATE_NOTE
    inQueue: bool = Field(description="是否在叫号队列中；已报告/未缴费的检查单为 false")


# --------------------------------------------------------------------------- #
# API-26 检查位置指引
# --------------------------------------------------------------------------- #


class ExamLocationData(BaseModel):
    examId: str
    examName: str
    deptName: str = Field(description="执行科室名称")
    building: Optional[str] = None
    floor: Optional[str] = None
    room: Optional[str] = None
    fullAddress: str = Field(description="完整位置，如「医技楼1F影像中心CT-2室」")
    indoorNavUrl: str = Field(description="跳转院内导航的链接（前端路由）")


# --------------------------------------------------------------------------- #
# API-28 检查状态查询
# --------------------------------------------------------------------------- #


class ExamStatusStep(BaseModel):
    """进度条节点，前端按 reached 上色、按 current 打点。"""

    status: ExamStatus
    statusDesc: str
    reached: bool
    current: bool


class ExamStatusData(BaseModel):
    examId: str
    examName: str
    examStatus: ExamStatus
    statusDesc: str
    updateTime: Optional[str] = Field(default=None, description="状态更新时间 yyyy-MM-dd HH:mm:ss")
    steps: list[ExamStatusStep] = Field(default_factory=list)


__all__ = [
    "DISCLAIMER",
    "WAIT_ESTIMATE_NOTE",
    "AbnormalItemMeaning",
    "AbnormalFlag",
    "ExamAnalysisData",
    "ExamAnalysisRequest",
    "ExamListItem",
    "ExamListData",
    "ExamLocationData",
    "ExamPrecautionsData",
    "ExamQueueData",
    "ExamReportData",
    "ExamReportItem",
    "ExamStatus",
    "ExamStatusData",
    "ExamStatusStep",
    "KnowledgeSource",
    "ReportStatus",
    "RiskLevel",
]
