"""FastAPI 应用装配（《接口文档》2.1 接口基础地址 /api/v1）。

跑起来：
    cd backend
    ./venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
    接口文档：http://127.0.0.1:8000/docs

本文件只做装配，不含任何业务逻辑：
    * 建表（lifespan 里 Base.metadata.create_all）
    * 挂 /api/v1 下的全部业务路由
    * 注册全局异常处理器与请求 ID 中间件（core/middleware.py）
    * CORS（前端直连时需要；走 Vite 代理时用不到）

关于建表：本项目**不用 Alembic**，表结构由 `Base.metadata.create_all` 从 ORM 模型直接建。
它只建不存在的表、**不会给已存在的表加列**。因此本次给 t_patient 新增的 is_deleted 列
对已有的开发库不会自动生效，需要手工执行一次（见交付说明）：

    ALTER TABLE t_patient ADD COLUMN is_deleted tinyint NOT NULL DEFAULT 0
        COMMENT '软删标记 1已删除 0正常' AFTER is_default;

新库（drop 后重建）不受影响，create_all 会带上这一列。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.middleware import RequestIdMiddleware, register_exception_handlers

logger = logging.getLogger(__name__)

API_VERSION = "1.0.0"


def _setup_logging() -> None:
    """最简日志配置：让 core/middleware.py 里的错误日志真的打出来。

    只配一次（basicConfig 对已配置的 root logger 无副作用）。生产环境若用
    gunicorn/uvicorn 的 --log-config，这一段会被覆盖，不影响。
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动时建表；建表失败只告警不阻断启动。

    数据库连不上时让进程起不来的话，连 `/docs` 都打不开 —— 而那恰恰是排查
    「DATABASE_URL 是不是配错了」时最想看到的东西。所以这里降级为一条明确的
    错误日志，让服务先起来，具体失败留给真实请求去暴露。
    """
    try:
        from app.db.base import Base
        from app.db.session import engine
        import app.models  # noqa: F401  导入即向 Base.metadata 注册全部 19 张表

        Base.metadata.create_all(bind=engine)
        logger.info("数据库表结构已就绪（create_all）")
    except Exception:
        logger.exception(
            "建表失败：服务仍会启动，但数据库相关接口会报错。"
            "请检查 backend/.env 的 DATABASE_URL 与数据库连通性"
        )

    yield


def create_app() -> FastAPI:
    """应用工厂（测试里也用这个，避免各处重复装配顺序）。"""
    _setup_logging()

    app = FastAPI(
        title=f"{settings.app_name} 智慧医疗AI辅助系统 API",
        version=API_VERSION,
        description=(
            "智慧医疗AI辅助系统后端接口。\n\n"
            "响应统一为 `{code, message, data, timestamp}` 信封（接口文档 2.4）：\n"
            "`code=0` 表示成功；业务失败返回 **HTTP 200 + 非 0 code**（如 1001 账号或密码错误、"
            "2001 号源不足），前端据 code 提示用户。\n\n"
            "鉴权：除登录/注册/发验证码外，均需请求头 `Authorization: Bearer {accessToken}`。"
        ),
        lifespan=lifespan,
    )

    # 中间件注册顺序 = 执行顺序的**逆序**：最后 add 的最先进入请求。
    # 因此 RequestIdMiddleware 放最后 —— 它要最先执行，后续日志才有 request id。
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-Id"],
        )
    app.add_middleware(RequestIdMiddleware)  # type: ignore[arg-type]

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/health", tags=["运维"], summary="健康检查")
    def health() -> dict[str, Any]:
        """存活探针：不查数据库，只证明进程活着、路由挂上了。

        `code=0` 是统一信封的约定（接口文档 2.4），因此这里也套一层信封，
        方便前端/运维用同一套解析逻辑。
        """
        return {"code": 0, "message": "success", "data": {"status": "ok", "env": settings.app_env}}

    return app


app = create_app()

__all__ = ["API_VERSION", "app", "create_app"]
