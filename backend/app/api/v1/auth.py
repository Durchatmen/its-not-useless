"""用户认证接口（接口文档 3.1：API-01 登录 / API-02 注册 / API-03 发送短信验证码）。

本文件只做 HTTP 适配：解析入参、取客户端 IP、套统一信封。业务规则全在
`services/auth_service.py`（密码校验、实名核验、验证码限发、JWT 签发都在那边）。

前端契约：frontend/src/api/auth.js
    POST /auth/login
    POST /auth/register
    POST /auth/sms-code

与其它模块的两点不同：

1. 本模块的 service 直接抛 `BizError`（core 原生异常），而不是自己定义一套领域错误。
   auth 是最早落地的模块，错误码（1001/1002/1003/1004/4003）与接口文档 2.5 一一对应，
   再包一层 XxxError 只会多一次无意义的转换。
2. 因此这里不需要 `_call()`：BizError 直接冒泡给 `core/middleware.py` 的异常处理器，
   由它转成 HTTP 200 + 信封。这是比 `_call()` 更省事的路径，新模块也可以这么写。
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.response import Envelope
from app.db.session import get_session
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    SmsCodeRequest,
    SmsLoginRequest,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["用户认证"])

SessionDep = Annotated[Session, Depends(get_session)]


def _client_ip(request: Request) -> Optional[str]:
    """取客户端 IP 写进操作日志（t_operation_log.ip）。

    反代之后 `request.client.host` 是 nginx 的地址，所以优先读 X-Forwarded-For
    的第一段（最靠近客户端的那一跳）。这一列只用于合规审计排查，不参与鉴权，
    因此不校验可信代理链 —— 伪造 XFF 最多是让日志里的 IP 不准。
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


@router.post("/login", summary="API-01 用户登录")
def login(payload: LoginRequest, session: SessionDep, request: Request) -> Any:
    """账号（手机号或身份证号）+ 密码登录，返回 accessToken 与用户信息。

    账号不存在与密码错误返回同一个 1001，避免账号探测；角色不匹配、账号被禁用返回 4003。
    成功后签发 JWT 并写一条 LOGIN 操作日志（合规审计留存不少于 6 个月）。
    """
    user, token, expires_in = auth_service.login(session, payload, ip=_client_ip(request))
    return Envelope.ok(auth_service.build_login_data(user, token, expires_in))


@router.post("/login/sms", summary="手机号 + 验证码登录（《功能设计文档》3.1 多方式登录）")
def login_by_sms(payload: SmsLoginRequest, session: SessionDep, request: Request) -> Any:
    """手机号 + 短信验证码登录。

    接口文档当前只收录了账号密码登录（API-01），本条是功能设计文档要求的第二种登录方式，
    服务层早已实现（auth_service.login_by_sms），此处按需挂出，路径 /auth/login/sms
    未占用接口编号 —— 若后续接口文档补了编号，改这一行的 summary 即可。
    """
    user, token, expires_in = auth_service.login_by_sms(
        session, payload, ip=_client_ip(request)
    )
    return Envelope.ok(auth_service.build_login_data(user, token, expires_in))


@router.post("/register", summary="API-02 用户注册")
def register(payload: RegisterRequest, session: SessionDep) -> Any:
    """注册账号（角色固定 PATIENT）。

    两步校验：短信验证码（1003）+ 实名认证（1004）。手机号已注册返回 1002。
    身份证号以 AES-SIV 确定性加密落库，既满足密文存储，又支持按证件号等值登录。
    """
    user = auth_service.register(session, payload)
    return Envelope.ok(
        {"userId": user.user_id, "realNameVerified": bool(user.real_name_verified)}
    )


@router.post("/sms-code", summary="API-03 发送短信验证码")
def send_sms_code(payload: SmsCodeRequest, session: SessionDep) -> Any:
    """发送 6 位短信验证码。

    scene=REGISTER 时会先确认账号未被占用（已注册返回 1002）；
    同号同场景 60 秒内不允许重复发送。接口文档 3.1.3 规定本接口无业务数据。
    """
    auth_service.send_register_code(session, payload)
    return Envelope.ok(None)


__all__ = ["router"]
