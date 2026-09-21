"""BGE-reranker-large 精排。

与 `embedding.py` 刻意对称：reranker 权重同样很大（约 2.2 GB）且加载慢，
因此也做成懒加载单例 —— 只有真正要精排时才把它读进内存，
`--skip-embed`、`--dry-run` 这类路径完全不碰它。

模型来源由 .env 的 RERANKER_MODEL 决定：
  - 指向本地目录（含 config.json）：直接用，零下载；
  - 指向 ModelScope 模型 id（如 BAAI/bge-reranker-large）：下载后再用。
本机 huggingface.co 不通，所以绝不让 transformers 自己去联网。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

_model = None
_resolved_path: Path | None = None


def _looks_like_local_model(value: str) -> bool:
    p = Path(value)
    return p.is_dir() and (p / "config.json").is_file()


def resolve_model_path() -> Path:
    """把 RERANKER_MODEL 解析成一个本地目录，必要时从 ModelScope 下载。"""
    global _resolved_path
    if _resolved_path is not None:
        return _resolved_path

    value = settings.reranker_model
    if _looks_like_local_model(value):
        _resolved_path = Path(value).resolve()
        logger.info("使用本地 BGE-reranker 权重: %s", _resolved_path)
    else:
        # 当成 ModelScope 模型 id 下载（绕开不通的 huggingface.co）
        from modelscope import snapshot_download

        # 与 embedding 共用缓存目录，两个模型都落在同一个 .models 下
        cache_dir = settings.embedding_cache_path
        cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("从 ModelScope 下载 %s 到 %s（首次较慢）", value, cache_dir)
        local_dir = snapshot_download(value, cache_dir=str(cache_dir))
        _resolved_path = Path(local_dir).resolve()
        logger.info("下载完成: %s", _resolved_path)

    return _resolved_path


def get_reranker():
    """懒加载 FlagReranker 单例。"""
    global _model
    if _model is None:
        model_path = resolve_model_path()
        # 本地权重已备齐，禁止 transformers 中途回连 huggingface.co —— 本机不通，会卡到超时
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        from FlagEmbedding import FlagReranker

        logger.info("加载 BGE-reranker（首次约 1 分钟）…")
        _model = FlagReranker(
            str(model_path),
            # ⚠ 与 BGEM3FlagModel 同理，库里 use_fp16 默认为 True，纯 CPU 环境必须显式关掉
            use_fp16=settings.reranker_use_fp16,
            devices=settings.reranker_devices or None,
            cache_dir=str(settings.embedding_cache_path),
        )
        logger.info("BGE-reranker 加载完成")
    return _model


def score(query: str, passages: list[str]) -> list[float]:
    """给每个 passage 打相关性分，返回与 passages 等长的列表（越大越相关）。

    分数未归一化（模型按交叉熵训练，没有上下界），只用于同一批内排序，
    不要跨查询比较绝对值。
    """
    if not passages:
        return []

    ranker = get_reranker()
    pairs = [[query, passage] for passage in passages]
    scores = ranker.compute_score(
        pairs,
        batch_size=settings.reranker_batch_size,
        max_length=settings.reranker_max_length,
    )
    # 只传一对时 compute_score 会退化成标量，统一成 list 让调用方少一个分支
    if isinstance(scores, (int, float)):
        return [float(scores)]
    return [float(s) for s in scores]


__all__ = ["get_reranker", "resolve_model_path", "score"]
