"""BGE-M3 向量化（dense）。

模型加载很重（本地权重约 4.3 GB，实测加载 45 s），因此做成懒加载单例：
只有真正要算向量时才会载入内存，`--dry-run` 之类的路径完全不碰它。

模型来源由 .env 的 EMBEDDING_MODEL 决定：
  - 指向本地目录（含 config.json）：直接用，零下载；
  - 指向 ModelScope 模型 id（如 BAAI/bge-m3）：下载到 EMBEDDING_CACHE_DIR 再用。
本机 huggingface.co 不通，所以绝不让 transformers 自己去联网。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

_model = None
_resolved_path: Path | None = None


def _looks_like_local_model(value: str) -> bool:
    p = Path(value)
    return p.is_dir() and (p / "config.json").is_file()


def resolve_model_path() -> Path:
    """把 EMBEDDING_MODEL 解析成一个本地目录，必要时从 ModelScope 下载。"""
    global _resolved_path
    if _resolved_path is not None:
        return _resolved_path

    value = settings.embedding_model
    if _looks_like_local_model(value):
        _resolved_path = Path(value).resolve()
        logger.info("使用本地 BGE-M3 权重: %s", _resolved_path)
    else:
        # 当成 ModelScope 模型 id 下载（绕开不通的 huggingface.co）
        from modelscope import snapshot_download

        cache_dir = settings.embedding_cache_path
        cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("从 ModelScope 下载 %s 到 %s（首次较慢）", value, cache_dir)
        local_dir = snapshot_download(value, cache_dir=str(cache_dir))
        _resolved_path = Path(local_dir).resolve()
        logger.info("下载完成: %s", _resolved_path)

    return _resolved_path


def get_embedder():
    """懒加载 BGE-M3 单例。"""
    global _model
    if _model is None:
        model_path = resolve_model_path()
        # 本地权重已备齐，禁止 transformers 中途回连 huggingface.co —— 本机不通，会卡到超时
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        from FlagEmbedding import BGEM3FlagModel

        logger.info("加载 BGE-M3（首次约 45 s）…")
        _model = BGEM3FlagModel(
            str(model_path),
            # ⚠ 库里 use_fp16 默认为 True，纯 CPU 环境必须显式关掉
            use_fp16=settings.embedding_use_fp16,
            devices=settings.embedding_devices or None,
            # 默认只有 512，而 chunk 最长 CHUNK_SIZE，不抬高会静默截断
            passage_max_length=settings.embedding_max_length,
            cache_dir=str(settings.embedding_cache_path),
        )
        logger.info("BGE-M3 加载完成")
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量编码为 dense 向量，返回纯 Python list（Milvus 不接受 numpy）。"""
    if not texts:
        return []

    model = get_embedder()
    vectors: list[list[float]] = []
    batch_size = settings.embedding_batch_size

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        output = model.encode(
            batch,
            batch_size=batch_size,
            max_length=settings.embedding_max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        dense = output["dense_vecs"]
        vectors.extend(np.asarray(dense, dtype=np.float32).tolist())
        logger.debug("已编码 %d/%d", min(start + batch_size, len(texts)), len(texts))

    dim = len(vectors[0]) if vectors else 0
    if dim != settings.embedding_dim:
        # 维度对不上会导致 Milvus 写入直接失败，早点报清楚
        raise ValueError(
            f"向量维度 {dim} 与配置 EMBEDDING_DIM={settings.embedding_dim} 不一致，"
            f"请检查 .env 与所用模型是否匹配"
        )
    return vectors


def embedding_dim() -> int:
    return settings.embedding_dim


__all__ = ["embed_texts", "embedding_dim", "get_embedder", "resolve_model_path"]
