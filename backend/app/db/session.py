"""数据库引擎与会话工厂（MySQL 8.0 + PyMySQL）。

连接串优先取环境变量 DATABASE_URL，未配置时回落到演示环境的远程库。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = (
    "mysql+pymysql://root:123456@192.168.21.41:3306/hospital_ai?charset=utf8mb4"
)

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)

SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖注入用的会话生成器。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
