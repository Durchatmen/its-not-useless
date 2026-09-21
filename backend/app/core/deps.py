"""FastAPI 依赖：数据库会话、JWT 鉴权、角色校验。

接口层（app/api/v1/*.py）用 Depends 复用这里的依赖；
services 层只接收 Session 与 User，不感知 HTTP。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import BizError, ErrorCode
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import User

bearer_scheme = HTTPBearer(
    auto_error=False, description="Authorization: Bearer {accessToken}"
)


def get_db() -> Iterator[Session]:
    """请求级数据库会话（FastAPI 依赖注入用）。"""
    yield from get_session()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """解析 Bearer 令牌并载入账号；缺失/失效返回 4002，被禁用返回 4003。"""
    if credentials is None or not credentials.credentials:
        raise BizError(ErrorCode.UNAUTHORIZED)
    payload = decode_access_token(credentials.credentials)
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise BizError(ErrorCode.UNAUTHORIZED)
    if user.status != 1:
        raise BizError(ErrorCode.FORBIDDEN, "账号已被禁用，请联系管理员")
    return user


def require_roles(*roles: str) -> Callable[[User], User]:
    """角色校验依赖工厂。

    用法：user: User = Depends(require_roles("DOCTOR", "ADMIN"))
    """

    allowed = {getattr(role, "value", role) for role in roles}

    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise BizError(ErrorCode.FORBIDDEN)
        return user

    return _checker
