"""多模态预诊分诊的请求 / 响应模型（接口文档 3.3：API-08、API-09）。

字段一律 Python 侧 snake_case、JSON 侧 camelCase，靠 `alias_generator=to_camel`
整体转换，不逐个手写 alias —— 少一个驼峰就是前端拿不到值。

统一信封 `{code, message, data, timestamp}` 由 `app/core/response.py` 组装
（文档 2.4 已声明：各接口的「响应参数」都指 data 里的内容，所以这里只描述 data）。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator
from pydantic.alias_generators import to_camel

from app.services.rag.prompts import DISCLAIMER

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
"""接口文档 2.1：时间格式 yyyy-MM-dd HH:mm:ss。"""


class _CamelModel(BaseModel):
    """进出一律用驼峰：出参 `model_dump(by_alias=True)`，入参按驼峰解析。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AIInputType(str, Enum):
    """文档 2.6 通用枚举：TEXT 文本、VOICE 语音、IMAGE 图片。"""

    TEXT = "TEXT"
    VOICE = "VOICE"
    IMAGE = "IMAGE"


class AudioFormat(str, Enum):
    WAV = "wav"
    MP3 = "mp3"
    AMR = "amr"


class MultiModalMessageRequest(_CamelModel):
    """API-08 请求体。语音与图片以 Base64 文本放在 audioData / imageData 里。"""

    session_id: str | None = None
    patient_id: str | None = None
    input_type: AIInputType
    text_content: str | None = None
    audio_data: str | None = None
    audio_format: AudioFormat | None = None
    image_data: str | None = None
    stream: bool = False

    @model_validator(mode="after")
    def _payload_required(self) -> "MultiModalMessageRequest":
        """按 inputType 校验对应的内容字段 —— 这是接口文档里的「条件必填」。"""
        field, wire = {
            AIInputType.TEXT: ("text_content", "textContent"),
            AIInputType.VOICE: ("audio_data", "audioData"),
            AIInputType.IMAGE: ("image_data", "imageData"),
        }[self.input_type]

        if not (getattr(self, field) or "").strip():
            raise ValueError(f"inputType={self.input_type.value} 时 {wire} 不能为空")
        return self


class TriageCard(_CamelModel):
    """分诊卡片。检索不到的字段为 null，前端 `TriageCard.vue` 会显示成占位符。"""

    department: str | None = None
    location: str | None = None
    doctor: str | None = None
    button_action: str | None = None


class MultiModalMessageData(_CamelModel):
    """API-08 响应 data（非流式）。流式的对应事件见 `app/services/sse.py`。"""

    session_id: str
    recognized_text: str = ""
    reply: str = ""
    triage_card: TriageCard | None = None
    risk_warning: str = ""
    sources: list[str] = Field(default_factory=list)
    # 文档 2.8 要求所有 AI 回复都带免责声明，给个默认值兜底，免得哪条路径漏传
    disclaimer: str = DISCLAIMER
    next_question: str = ""


class SessionHistoryQuery(_CamelModel):
    """API-09 分页查询参数（文档 2.1：pageNum 默认 1、pageSize 默认 10）。"""

    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)


class SessionMessageItem(_CamelModel):
    """API-09 的一条会话记录。`role` 取 user / bot。"""

    message_id: str
    role: str
    input_type: str | None = None
    text_content: str | None = None
    reply: str | None = None
    create_time: datetime

    @field_serializer("create_time")
    def _format_time(self, value: datetime) -> str:
        return value.strftime(_TIME_FORMAT)


class SessionHistoryData(_CamelModel):
    """API-09 响应 data；分页字段名沿用文档 2.1 的 total / pageNum / pageSize / list。"""

    total: int
    page_num: int
    page_size: int
    # list 是内置类型名，属性另起个名，序列化时仍按文档输出 "list"
    items: list[SessionMessageItem] = Field(default_factory=list, alias="list")


__all__ = [
    "AIInputType",
    "AudioFormat",
    "MultiModalMessageData",
    "MultiModalMessageRequest",
    "SessionHistoryData",
    "SessionHistoryQuery",
    "SessionMessageItem",
    "TriageCard",
]
