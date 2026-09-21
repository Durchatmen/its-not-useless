"""数据库引擎与会话工厂（MySQL 8.0 + PyMySQL）。

连接串只认 backend/.env 里的 DATABASE_URL（由 app.core.config 读取），
本模块不存第二份默认值 —— 否则换库时容易漏改一处，静默连到旧机器。
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

DATABASE_URL = settings.database_url

if not DATABASE_URL:
    raise RuntimeError("未配置 DATABASE_URL，请在 backend/.env 中填写数据库连接串")

engine = create_engine(
    DATABASE_URL, pool_pre_ping=True, pool_recycle=3600, echo=settings.db_echo
)

SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖注入用的会话生成器。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
