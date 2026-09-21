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

    # ---------- Reranker（BGE-reranker-large）----------
    # 本地模型目录绝对路径，或 ModelScope 模型 id（如 BAAI/bge-reranker-large）
    reranker_model: str = "BAAI/bge-reranker-large"
    # ⚠ 与 BGEM3FlagModel 同理，FlagReranker 的 use_fp16 也默认 True，纯 CPU 必须关掉
    reranker_use_fp16: bool = False
    # 计算设备，"cpu" 或 "cuda:0"；留空则交给 FlagEmbedding 自动探测
    reranker_devices: str = "cpu"
    # query 与 passage 会拼在一起过模型，按 passage 满配给足长度
    reranker_max_length: int = 512
    reranker_batch_size: int = 8

    # ---------- 检索（retriever）----------
    # 向量召回候选数，随后交给 reranker 精排
    retrieval_top_k: int = 20
    # 最终返回条数（关闭精排时即向量召回的截断条数）
    retrieval_rerank_top_k: int = 5
    # 关掉则跳过精排，直接按向量相似度返回，省一次模型加载
    retrieval_enable_rerank: bool = True
    # 混合检索：向量召回之外再叠一层 BM25 关键词召回，两路 RRF 融合后送精排
    retrieval_enable_hybrid: bool = True

    # ---------- 切分 ----------
    chunk_size: int = 800
    chunk_overlap: int = 120

    # ---------- 大模型（Qwen / OpenAI 兼容端点）----------
    # 阿里云百炼的 OpenAI 兼容端点；换自建 vLLM 时改成对应地址即可，调用方代码不动
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # 百炼控制台申请；留空时调用会立刻报错提示，不会发出无鉴权的请求
    llm_api_key: str = ""
    # 百炼模型 id，如 qwen-plus / qwen-max / qwen-turbo
    llm_model: str = "qwen-plus"
    # 单次请求超时（秒）；流式下是相邻两段数据之间的最长等待，不是总时长
    llm_timeout: float = 60.0
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.7

    # ---------- 多模态（图片 / 语音走同一个兼容端点，只是换模型）----------
    # 图片理解 / OCR 用的视觉模型；2026 年起可换成 qwen3-vl-plus 或 qwen-vl-max
    llm_vl_model: str = "qwen-vl-plus"
    # 语音转写用的全模态模型；不支持 audioFormat=amr（需先转码成 wav/mp3）
    llm_omni_model: str = "qwen-omni-turbo"

    # ---------- 挂号（接口文档 API-15 叫号提醒）----------
    # 单个患者的平均问诊分钟数，用于按「前方人数 × 该值」估算预计叫号时间。
    # 库里不存 HIS 的实时叫号队列（数据库设计文档 4.4 建议轮询不落库），
    # 因此这个值是本地估算的参数，接 HIS 后应改为直接读队列。
    appointment_avg_minutes: int = 8

    # ---------- 其他（本模块暂未使用，保留以对齐 .env）----------
    llm_provider: str = ""
    his_base_url: str = ""
    his_enabled: bool = False

    # ---------- 跨域（前端直连后端时需要；走 Vite 代理时用不到）----------
    # 逗号分隔的 Origin 列表；开发环境默认放行 Vite 的 5173 端口。
    # 生产环境务必在 .env 里显式覆盖，不要留这个默认值。
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

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
