"""应用配置：pydantic-settings 读取 backend/.env。

字段名与 .env 中的变量名大小写不敏感地一一对应（MILVUS_HOST -> milvus_host）。
.env 中未声明的额外变量一律忽略，避免历史遗留项导致启动失败。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- 应用 ----------
    app_env: str = "dev"
    app_name: str = "hospital-ai"
    tz: str = "Asia/Shanghai"

    # ---------- 认证 ----------
    secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120

    # ---------- 数据库 ----------
    database_url: str = ""
    db_echo: bool = False

    # ---------- Redis ----------
    redis_url: str = ""
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # ---------- Milvus（六大知识库）----------
    milvus_host: str = "127.0.0.1"
    milvus_port: int = 19530
    milvus_token: str = ""
    milvus_timeout: float = 10.0

    # ---------- 对象存储 ----------
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "hospital-files"
    minio_secure: bool = False

    # ---------- 知识库构建 ----------
    # docs 根目录，相对路径按 backend/ 解析
    kb_docs_root: str = "../docs"
    # 已处理完的原始文件（PDF / Word）归档根目录，与 docs 同级；
    # 归档时按源文件在 docs/ 下的相对路径落位，于是 docs0/医保知识库/x.pdf 对应 docs/医保知识库/x.pdf
    # 注意：这只是归档目录，切分素材始终只从 kb_docs_root 下找
    kb_archive_root: str = "../docs0"
    # MinerU 解析档位：flash / basic / standard / advanced；remote 需配 MINERU_API_KEY
    mineru_tier: str = "flash"
    # 单个文档解析等待上限（秒）
    mineru_wait_seconds: int = 600
    # MinerU 可执行文件；留空则用当前解释器同目录下的 mineru
    mineru_bin: str = ""

    # ---------- Embedding（BGE-M3）----------
    # 本地模型目录绝对路径，或 ModelScope 模型 id（如 BAAI/bge-m3）
    embedding_model: str = "BAAI/bge-m3"
    # 仅当 embedding_model 填模型 id 时使用；相对路径按 backend/ 解析
    embedding_cache_dir: str = ".models"
    embedding_dim: int = 1024
    embedding_batch_size: int = 16
    # ⚠ FlagEmbedding 的 use_fp16 默认为 True，纯 CPU 环境必须显式关掉
    embedding_use_fp16: bool = False
    # 计算设备，"cpu" 或 "cuda:0"；留空则交给 FlagEmbedding 自动探测
    embedding_devices: str = "cpu"
    # 与 CHUNK_SIZE 匹配，避免长 chunk 被静默截断
    embedding_max_length: int = 1024

    # ---------- 切分 ----------
    chunk_size: int = 800
    chunk_overlap: int = 120

    # ---------- 其他（本模块暂未使用，保留以对齐 .env）----------
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model: str = "qwen"
    his_base_url: str = ""
    his_enabled: bool = False

    # ---------- 短信网关（注册验证码，接口文档 3.1.3）----------
    sms_gateway_url: str = ""
    sms_api_key: str = ""
    sms_sign_name: str = "智慧医疗"
    sms_timeout: float = 8.0
    # 验证码有效期（分钟）与同号同场景重发间隔（秒）
    sms_code_ttl_minutes: int = 5
    sms_resend_seconds: int = 60

    # ---------- 医院与院外导航（接口文档 API-20）----------
    hospital_code: str = "H0001"
    hospital_name: str = "示范医院"
    hospital_latitude: float = 30.274084
    hospital_longitude: float = 120.155070
    # 医院主入口坐标（院外导航默认终点）；留 0 时回落到医院坐标
    hospital_gate_latitude: float = 0.0
    hospital_gate_longitude: float = 0.0

    # ---------- 高德开放平台 ----------
    # Web 服务 Key（路径规划/POI/静态图）；留空时院外导航直接返回 5004
    amap_web_key: str = ""
    amap_base_url: str = "https://restapi.amap.com"
    amap_city: str = "杭州"
    amap_timeout: float = 8.0

    # ----- 派生属性 -----

    @property
    def milvus_uri(self) -> str:
        return f"http://{self.milvus_host}:{self.milvus_port}"

    @property
    def docs_root(self) -> Path:
        """docs 根目录的绝对路径。"""
        return self._resolve(self.kb_docs_root)

    @property
    def archive_root(self) -> Path:
        """已处理源文件的归档根目录（docs0）的绝对路径。"""
        return self._resolve(self.kb_archive_root)

    @property
    def embedding_cache_path(self) -> Path:
        return self._resolve(self.embedding_cache_dir)

    @staticmethod
    def _resolve(value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
