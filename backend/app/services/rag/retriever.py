"""知识库检索：稠密向量召回 + BM25 关键词召回 + BGE-reranker 精排。

`milvus_client.py` 只负责连接、建库与写入，检索逻辑全在这里。

三段式：
  1. BGE-M3 把 query 编成向量，从目标 collection 召回 RETRIEVAL_TOP_K 条候选；
  2. 可选混合：BM25（`bm25.py`）再召回同样条数的关键词候选，两路 RRF 融合后
     仍只保留 RETRIEVAL_TOP_K 条，候选更全但精排负担不变；
  3. BGE-reranker 逐条精排，取前 RETRIEVAL_RERANK_TOP_K 条返回。

想省下一次模型加载时，可用 RETRIEVAL_ENABLE_RERANK=false 关掉精排，
此时按召回分数返回（开了混合就是 RRF 融合分，否则是向量相似度）；
RETRIEVAL_ENABLE_HYBRID=false 可单独关掉 BM25 这一路。

六个知识库各对应一个 collection，目录名到 collection 名的映射见 `collections.py`，
所以 `retrieve()` 的 collection 参数既认 collection 名（kb_diagnosis）也认目录名（诊疗知识库）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import settings
from app.services.rag import bm25, milvus_client, reranker
from app.services.rag.collections import (
    KB_COLLECTIONS,
    resolve_by_collection_name,
    resolve_by_directory,
)
from app.services.rag.embedding import embed_texts

if TYPE_CHECKING:
    from pymilvus import MilvusClient

logger = logging.getLogger(__name__)

# 带回来的标量字段；不含 vector —— 省掉一次 1024 维浮点的白白传输
_OUTPUT_FIELDS = (
    "text",
    "source_file",
    "category",
    "doc_type",
    "title_path",
    "chunk_index",
    "sheet_name",
)


@dataclass
class RetrievedChunk:
    """一条召回结果。`score` 是最终排序依据：开了精排就是精排分，否则是向量相似度。"""

    text: str
    score: float
    source_file: str = ""
    category: str = ""
    doc_type: str = ""
    title_path: str = ""
    chunk_index: int = 0
    sheet_name: str = ""
    # 精排前的向量相似度，留一份便于对照「精排把顺序改成了什么样」
    vector_score: float = 0.0


def resolve_collection_name(collection: str) -> str:
    """把 collection 名或目录名统一成 collection 名，未知则抛 ValueError。"""
    kb = resolve_by_collection_name(collection) or resolve_by_directory(collection)
    if kb is None:
        valid = "、".join(f"{c.collection_name}({c.directory})" for c in KB_COLLECTIONS)
        raise ValueError(f"未知的知识库: {collection}\n可用: {valid}")
    return kb.collection_name


def _search(
    client: "MilvusClient",
    collection_name: str,
    vector: list[float],
    limit: int,
) -> list[RetrievedChunk]:
    """向 Milvus 要 limit 条向量近邻，按相似度降序返回。"""
    results = client.search(
        collection_name=collection_name,
        data=[vector],
        limit=limit,
        # 与 build_index_params 的 COSINE 保持一致；COSINE 下 distance 越大越相似
        search_params={"metric_type": "COSINE"},
        output_fields=list(_OUTPUT_FIELDS),
    )

    # search 返回「每个查询向量一组」，这里只传了一个 query，所以取第 0 组
    hits = results[0] if results else []
    chunks: list[RetrievedChunk] = []
    for hit in hits:
        entity = hit.get("entity") or {}
        similarity = float(hit.get("distance", 0.0))
        chunks.append(
            RetrievedChunk(
                text=entity.get("text") or "",
                score=similarity,
                source_file=entity.get("source_file") or "",
                category=entity.get("category") or "",
                doc_type=entity.get("doc_type") or "",
                title_path=entity.get("title_path") or "",
                chunk_index=int(entity.get("chunk_index") or 0),
                sheet_name=entity.get("sheet_name") or "",
                vector_score=similarity,
            )
        )
    return chunks


def _fuse(
    dense: list[RetrievedChunk], bm25_hits: list[bm25.Bm25Hit], k: int = 60
) -> list[RetrievedChunk]:
    """RRF 融合两路召回：只看排名、不看原始分。

    向量相似度（COSINE 0~1）与 BM25 分（无上界）量纲不同，不能直接相加；
    RRF 把两路的排名都折算成 1/(k+rank)，同量纲后相加，用 text 做去重键。
    """
    rrf: dict[str, float] = {}
    merged: dict[str, RetrievedChunk] = {}
    for rank, chunk in enumerate(dense):
        rrf[chunk.text] = rrf.get(chunk.text, 0.0) + 1.0 / (k + rank + 1)
        merged.setdefault(chunk.text, chunk)
    for rank, hit in enumerate(bm25_hits):
        rrf[hit.text] = rrf.get(hit.text, 0.0) + 1.0 / (k + rank + 1)
        if hit.text not in merged:
            merged[hit.text] = RetrievedChunk(
                text=hit.text,
                score=0.0,
                source_file=hit.source_file,
                category=hit.category,
                doc_type=hit.doc_type,
                title_path=hit.title_path,
                chunk_index=hit.chunk_index,
                sheet_name=hit.sheet_name,
            )
    for text, chunk in merged.items():
        chunk.score = rrf[text]
    return sorted(merged.values(), key=lambda c: c.score, reverse=True)


def retrieve(
    query: str,
    collection: str,
    *,
    top_k: int | None = None,
    enable_rerank: bool | None = None,
    enable_hybrid: bool | None = None,
) -> list[RetrievedChunk]:
    """检索单个知识库，返回按相关性降序的结果。

    top_k 是最终返回条数，默认取 RETRIEVAL_RERANK_TOP_K；
    enable_rerank / enable_hybrid 默认分别跟随 RETRIEVAL_ENABLE_RERANK /
    RETRIEVAL_ENABLE_HYBRID。
    """
    query = (query or "").strip()
    if not query:
        return []

    collection_name = resolve_collection_name(collection)
    client = milvus_client.get_client()
    if not client.has_collection(collection_name):
        logger.warning("collection 不存在，跳过检索: %s（是否还没跑 build_knowledge_base.py？）", collection_name)
        return []

    final_k = top_k or settings.retrieval_rerank_top_k
    # 召回数要盖过最终条数，否则精排没有富余的候选可挑
    recall_k = max(settings.retrieval_top_k, final_k)

    dense = _search(client, collection_name, embed_texts([query])[0], recall_k)

    do_hybrid = settings.retrieval_enable_hybrid if enable_hybrid is None else enable_hybrid
    if do_hybrid:
        # 融合后仍只保留 recall_k 条，rerank 候选数与纯向量召回一致，不额外拖慢精排
        candidates = _fuse(dense, bm25.search(query, collection_name, recall_k))[:recall_k]
    else:
        candidates = dense

    if not candidates:
        return []

    do_rerank = settings.retrieval_enable_rerank if enable_rerank is None else enable_rerank
    if do_rerank:
        scores = reranker.score(query, [c.text for c in candidates])
        for chunk, value in zip(candidates, scores):
            chunk.score = value
        candidates.sort(key=lambda c: c.score, reverse=True)

    return candidates[:final_k]


__all__ = ["RetrievedChunk", "resolve_collection_name", "retrieve"]
