"""全局异常处理与链路追踪中间件（《接口文档》2.3 / 2.4 / 2.5）。

这里承接三件事，缺一件前端就拿不到正确的提示：

1. **BizError → HTTP 200 + 信封**。业务失败一律用「HTTP 200 + code != 0」表达，
   这是接口文档 2.4 的信封语义，也是前端 `api/request.js` 的硬约束 ——
   它把 HTTP 4xx 当网络异常处理，会丢掉服务端给的 message，用户只能看到「网络错误」。
   所以「账号或密码错误」「号源不足」这类失败必须是 200 + code=1001/2001。

2. **参数校验失败 → 4001**。FastAPI 默认对校验失败返回 422，body 是
   `{"detail": [...]}` 这种不是信封的结构，前端读不出 message。这里统一翻成 4001。

3. **未捕获异常 → 9999**。日志里带 X-Request-Id 与完整堆栈，响应体里只有一句
   「系统内部错误」—— 不把堆栈、SQL、表名泄漏给客户端。

另有一个 ASGI 层的请求 ID 中间件：把 X-Request-Id（没有就生成）回写到响应头，
并放进 ContextVar，让同一次请求的所有日志行都能对上号（接口文档 2.3）。

⚠ 为什么请求 ID 用**裸 ASGI 中间件**而不是 `@app.middleware("http")`：
   后者基于 Starlette 的 BaseHTTPMiddleware，它会缓冲响应体，会把
   `/ai/multimodal/messages?stream=true` 的 SSE 流憋成一坨再发（前端逐字显示的效果没了）。
   裸 ASGI 只在 `send` 时挂一个响应头，不碰 body，流式接口不受影响。
"""

from __future__ import annotations

import contextvars
import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import BizError, ErrorCode
from app.core.response import Envelope

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = b"x-request-id"

# 当前请求的链路追踪ID；日志过滤器从这里取，缺省为 "-"
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


def current_request_id() -> str:
    """取当前请求的链路追踪ID（后台任务/线程里取到的是默认值）。"""
    return request_id_var.get()


class RequestIdMiddleware:
    """裸 ASGI 中间件：出入都带 X-Request-Id，不触碰响应体。

    放在最外层（最后 add_middleware 的反而最先执行），这样异常处理器里
    `current_request_id()` 已经有值，错误日志能带上请求 ID。
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            # websocket / lifespan 不参与，直接透传
            await self.app(scope, receive, send)
            return

        request_id = self._extract(scope)
        token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, self._with_header(send, request_id))
        finally:
            request_id_var.reset(token)

    @staticmethod
    def _extract(scope: dict) -> str:
        """优先用客户端带来的 X-Request-Id（便于跨系统串联），否则自己生成。"""
        for key, value in scope.get("headers") or []:
            if key.lower() == REQUEST_ID_HEADER:
                incoming = value.decode("latin-1").strip()
                if incoming:
                    return incoming
        return uuid.uuid4().hex

    @staticmethod
    def _with_header(send: Any, request_id: str) -> Any:
        async def _send(message: dict) -> None:
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((REQUEST_ID_HEADER, request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        return _send


# --------------------------------------------------------------------------- #
# 异常处理器
# --------------------------------------------------------------------------- #


def _json(payload: Envelope, status_code: int = 200) -> JSONResponse:
    """信封 → JSON 响应。

    用 `model_dump(mode="json")` 而不是 `model_dump()`：Envelope.data 在成功路径上
    可能是带 date/datetime 的 pydantic 模型，json 模式能把这些转成字符串。
    """
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _wants_stream(request: Request) -> bool:
    """这次请求是不是「要 SSE 流」。

    两个信号任一成立即算：Accept 里带 text/event-stream（前端 sse.js 会带），
    或 query 里有 stream=true（接口文档 API-08 的开关）。
    """
    if "text/event-stream" in (request.headers.get("accept") or "").lower():
        return True
    return (request.query_params.get("stream") or "").lower() in ("1", "true", "yes")


# 流式请求下「业务码 → HTTP 状态码」的映射：只列鉴权两档，其余仍走 200。
# 为什么流式要特殊对待：前端 api/sse.js 只看 `response.ok`，不解析 JSON 信封 ——
# 若鉴权失败也返回 200，它会当成正常流去读，读出 0 个 SSE 事件后静默结束，
# 用户看到的是一个转完就没反应的加载动画，任何提示都没有。
_STREAM_STATUS: dict[int, int] = {
    int(ErrorCode.UNAUTHORIZED): 401,
    int(ErrorCode.FORBIDDEN): 403,
}


async def biz_error_handler(request: Request, exc: BizError) -> JSONResponse:
    """业务异常：HTTP 200 + {code, message, data:null}（接口文档 2.4）。

    唯一的例外是流式请求的鉴权失败，见 _STREAM_STATUS。
    """
    # 4001 这类「用户传错了」用 info 就够了，真正的服务端问题才值得 warning
    level = logging.INFO if exc.code < 5000 else logging.WARNING
    logger.log(
        level,
        "[%s] 业务失败 %s %s -> code=%s message=%s",
        current_request_id(),
        request.method,
        request.url.path,
        exc.code,
        exc.message,
    )
    status_code = 200
    if _wants_stream(request):
        status_code = _STREAM_STATUS.get(exc.code, 200)
    return _json(Envelope.fail(exc.code, exc.message), status_code=status_code)


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """请求体/query 校验失败 → 4001（而不是 FastAPI 默认的 422 + detail 数组）。"""
    message = _format_validation_error(exc)
    logger.info(
        "[%s] 参数校验失败 %s %s -> %s",
        current_request_id(),
        request.method,
        request.url.path,
        message,
    )
    return _json(Envelope.fail(ErrorCode.PARAM_INVALID, message))


def _format_validation_error(exc: RequestValidationError) -> str:
    """把 Pydantic 的错误列表拼成一句人话。

    只取第一条并带上字段路径：前端的表单校验提示只显示一行，
    列全 10 条反而看不清先改哪个。
    """
    errors = exc.errors()
    if not errors:
        return "参数校验失败"

    first = errors[0]
    # loc 形如 ("body", "patientId") / ("query", "pageSize")，去掉第一段（来源）留下字段路径
    location = ".".join(str(p) for p in first.get("loc", ())[1:]) or "请求参数"
    detail = first.get("msg", "取值不合法")
    # Pydantic v2 的 msg 是英文（"Field required"），补一层常见说法的中文
    detail = _ZH_MESSAGES.get(detail, detail)
    return f"参数 {location} {detail}"


_ZH_MESSAGES: dict[str, str] = {
    "Field required": "缺失（必填）",
    "Input should be a valid integer": "必须是整数",
    "Input should be a valid number": "必须是数字",
    "Input should be a valid string": "必须是字符串",
    "Input should be a valid boolean": "必须是布尔值",
    "Input should be a valid date or datetime": "必须是合法日期",
    "String should have at least 1 character": "不能为空",
}


async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Starlette/FastAPI 抛出的 HTTPException（如 404 路由不存在、405 方法不对）。

    这一档**保留原始 HTTP 状态码**：它是「客户端调错了接口」而不是业务失败，
    用 200 表达反而会让调用方以为路由是通的。body 仍是统一信封，至少能读出 message。
    """
    message = "接口不存在" if exc.status_code == 404 else str(exc.detail)
    logger.info(
        "[%s] HTTP %s %s %s -> %s",
        current_request_id(),
        exc.status_code,
        request.method,
        request.url.path,
        message,
    )
    return _json(
        Envelope.fail(ErrorCode.PARAM_INVALID, message), status_code=exc.status_code
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底：未预期的异常 → 9999，堆栈只进日志不进响应体。"""
    logger.exception(
        "[%s] 未捕获异常 %s %s", current_request_id(), request.method, request.url.path
    )
    return _json(Envelope.fail(ErrorCode.INTERNAL))


def register_exception_handlers(app: FastAPI) -> None:
    """挂上全部异常处理器（由 app/main.py 调用）。"""
    app.add_exception_handler(BizError, biz_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)


__all__ = [
    "REQUEST_ID_HEADER",
    "RequestIdMiddleware",
    "current_request_id",
    "register_exception_handlers",
]
