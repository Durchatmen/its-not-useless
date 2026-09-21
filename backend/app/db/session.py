"""数据库引擎与会话工厂（MySQL 8.0 + PyMySQL）。

连接串的**唯一来源是 backend/.env 的 DATABASE_URL**（由 core/config.py 读取）。

历史遗留问题：这里原先还支持进程环境变量 DATABASE_URL，并保留了一份硬编码的
演示库地址兜底。两个来源会各说各话 —— 改了 .env 却不生效（因为实际走的是硬编码那份），
排查时极具误导性。已删除，改数据库地址请只改 .env（参考 .env.example）。
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

DATABASE_URL = settings.database_url

if not DATABASE_URL:
    raise RuntimeError(
        "未配置 DATABASE_URL：请在 backend/.env 中设置数据库连接串（参考 backend/.env.example）"
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)

SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖注入用的会话生成器。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
