"""统一响应信封（《接口文档》2.4）：{code, message, data, timestamp}。

code 为 0 表示成功、message 固定 "success"；失败时 data 为 null。
接口层直接用 Envelope.ok(data) / Envelope.fail(code)。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.errors import ErrorCode, message_of
from app.utils.time_utils import fmt, now

SUCCESS_MESSAGE = "success"


class Envelope(BaseModel):
    code: int = 0
    message: str = SUCCESS_MESSAGE
    data: Any = None
    timestamp: str = Field(default_factory=lambda: fmt(now()))

    @classmethod
    def ok(cls, data: Any = None) -> "Envelope":
        return cls(code=int(ErrorCode.SUCCESS), message=SUCCESS_MESSAGE, data=data)

    @classmethod
    def fail(cls, code: ErrorCode | int, message: str | None = None) -> "Envelope":
        return cls(code=int(code), message=message_of(int(code), message), data=None)
