"""密码哈希与 JWT 会话令牌（技术选型：PyJWT + Passlib[bcrypt]）。

《接口文档》2.2：登录成功后签发 accessToken，此后需要登录的接口在
Authorization 头携带 Bearer {accessToken}；令牌超时或无效统一返回 4002。
"""

from __future__ import annotations

from datetime import datetime, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.errors import BizError, ErrorCode

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = settings.jwt_algorithm
JWT_ISSUER = settings.app_name


def hash_password(raw: str) -> str:
    """bcrypt 加盐哈希（《数据库表设计文档》3.3：密码加盐哈希存储）。"""
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    """校验明文口令；库里存了非 bcrypt 格式的历史数据时按“密码错误”处理。"""
    try:
        return pwd_context.verify(raw, hashed)
    except (ValueError, TypeError):
        return False


def create_access_token(
    *,
    user_id: str,
    role: str,
    account: str | None = None,
    expires_minutes: int | None = None,
) -> tuple[str, int]:
    """签发 JWT，返回 (accessToken, expiresIn 秒)。"""
    minutes = expires_minutes or settings.access_token_expire_minutes
    # 用 Unix 时间戳而非 datetime，避免 naive/aware 混用导致的时区偏移
    issued_at = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "sub": user_id,
        "account": account,
        "role": role,
        "iss": JWT_ISSUER,
        "iat": issued_at,
        "exp": issued_at + minutes * 60,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
    return token, minutes * 60


def decode_access_token(token: str) -> dict:
    """校验签名、有效期与签发方；任何异常一律转 4002。"""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM], issuer=JWT_ISSUER)
    except jwt.PyJWTError as exc:
        raise BizError(ErrorCode.UNAUTHORIZED) from exc
