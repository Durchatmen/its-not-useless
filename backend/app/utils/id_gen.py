"""业务主键生成。

《数据库表设计文档》1.1：主键统一 varchar(32)；沿用演示数据
（USR0001 / SMS0001 / DEPT0001）的“前缀 + 4 位序号”约定。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def next_id(db: Session, column: Any, prefix: str, *, width: int = 4) -> str:
    """返回该表下一个可用主键，如 next_id(db, User.user_id, "USR") -> "USR0051"。

    并发插入时两个会话可能算出同一个序号，最终由主键唯一约束拦下；
    调用方捕捉 IntegrityError 后重试即可（见 app/services/auth_service.register）。
    """
    last = db.execute(select(func.max(column)).where(column.like(f"{prefix}%"))).scalar()
    seq = 1
    if isinstance(last, str) and last[len(prefix):].isdigit():
        seq = int(last[len(prefix):]) + 1
    return f"{prefix}{seq:0{width}d}"
