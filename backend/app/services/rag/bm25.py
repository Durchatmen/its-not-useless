"""BM25 稀疏检索：混合检索里的「关键词」一路，与稠密向量召回互补。

Milvus 只建了向量索引、没有倒排索引，BM25 没法在库里直接查，所以这里把目标
collection 的正文全量拉到内存、建 BM25 索引再打分。算法等价于 rank-bm25 的
BM25Okapi（k1=1.5, b=0.75），自实现以省掉一个纯 Python 依赖。

中文没有天然空格分词，这里用「字级 bigram」切词：不用引入 jieba，对医学短文本
（如「高血压」「白细胞升高」）的关键词匹配足够；连续的字母数字串保持整词，
英文缩写（WBC）和数值不会被拆碎。

索引按 collection 懒加载并缓存 —— 知识库「构建一次、长期只读」，重复查询不必
反复拉全量；重建知识库后调用 reset() 让缓存失效。
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, replace

from app.services.rag import milvus_client

logger = logging.getLogger(__name__)

_K1 = 1.5
_B = 0.75

# 与 retriever._OUTPUT_FIELDS 对齐；不含 vector，省去整库 1024 维浮点的传输
_FIELDS = (
    "text",
    "source_file",
    "category",
    "doc_type",
    "title_path",
    "chunk_index",
    "sheet_name",
)

_CJK_OR_ALNUM = re.compile(r"[一-鿿]+|[a-zA-Z0-9]+")

_QUERY_BATCH = 1024


@dataclass
class Bm25Hit:
    """一条 BM25 召回结果，字段与 retriever.RetrievedChunk 一一对应。"""

    text: str
    score: float
    source_file: str = ""
    category: str = ""
    doc_type: str = ""
    title_path: str = ""
    chunk_index: int = 0
    sheet_name: str = ""


def _tokenize(text: str) -> list[str]:
    """中文按字级 bigram、字母数字按整词（小写）切。"""
    tokens: list[str] = []
    for part in _CJK_OR_ALNUM.findall(text or ""):
        if "一" <= part[0] <= "鿿":
            if len(part) == 1:
                tokens.append(part)
            else:
                tokens.extend(part[i : i + 2] for i in range(len(part) - 1))
        else:
            tokens.append(part.lower())
    return tokens


class _BM25:
    """BM25Okapi。corpus 是已经 tokenize 好的文档列表。"""

    def __init__(self, corpus: list[list[str]]) -> None:
        self._corpus = corpus
        self._n = len(corpus)
        # 空 corpus 下 avgdl 无意义；max 到 1 兜底，避免后面除以 0
        self._avgdl = max(1.0, sum(len(d) for d in corpus) / self._n) if self._n else 1.0

        df: dict[str, int] = {}
        for doc in corpus:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1
        self._idf = {
            term: math.log(1 + (self._n - n + 0.5) / (n + 0.5)) for term, n in df.items()
        }
        # 预存每条文档的词频，打分时只查 dict，不再逐字符 count
        self._tf = [Counter(doc) for doc in corpus]

    def score(self, query: list[str]) -> list[float]:
        """给每条文档打分，返回与 corpus 等长的列表（越大越相关）。"""
        scores = [0.0] * self._n
        for term in query:
            idf = self._idf.get(term)
            if not idf:
                continue
            for i, tf_map in enumerate(self._tf):
                tf = tf_map.get(term, 0)
                if tf:
                    dl = len(self._corpus[i])
                    scores[i] += (
                        idf * tf * (_K1 + 1) / (tf + _K1 * (1 - _B + _B * dl / self._avgdl))
                    )
        return scores


_cache: dict[str, tuple[_BM25, list[Bm25Hit]]] = {}


def _fetch_all(client, collection_name: str) -> list[dict]:
    """把 collection 的正文与元数据全量拉出（按 pk>=0 过滤 = 全部行）。"""
    total = milvus_client.count(client, collection_name)
    rows: list[dict] = []
    for offset in range(0, total, _QUERY_BATCH):
        batch = client.query(
            collection_name=collection_name,
            filter=f"{milvus_client.PRIMARY_FIELD} >= 0",
            output_fields=list(_FIELDS),
            limit=_QUERY_BATCH,
            offset=offset,
        )
        if not batch:
            break
        rows.extend(batch)
    return rows


def _build(client, collection_name: str) -> tuple[_BM25, list[Bm25Hit]]:
    rows = _fetch_all(client, collection_name)
    hits = [
        Bm25Hit(
            text=row.get("text") or "",
            score=0.0,
            source_file=row.get("source_file") or "",
            category=row.get("category") or "",
            doc_type=row.get("doc_type") or "",
            title_path=row.get("title_path") or "",
            chunk_index=int(row.get("chunk_index") or 0),
            sheet_name=row.get("sheet_name") or "",
        )
        for row in rows
    ]
    corpus = [_tokenize(h.text) for h in hits]
    return _BM25(corpus), hits


def search(query: str, collection: str, top_k: int) -> list[Bm25Hit]:
    """对单个 collection 做 BM25 关键词召回，返回 top_k 条（分数降序，非正分不返回）。"""
    query = (query or "").strip()
    if not query or top_k <= 0:
        return []

    client = milvus_client.get_client()
    if not client.has_collection(collection):
        logger.warning("collection 不存在，跳过 BM25: %s", collection)
        return []

    if collection not in _cache:
        logger.info("首次为 %s 建 BM25 索引…", collection)
        _cache[collection] = _build(client, collection)

    model, hits = _cache[collection]
    if not hits:
        return []

    ranked = sorted(zip(model.score(_tokenize(query)), hits), key=lambda pair: pair[0], reverse=True)
    result: list[Bm25Hit] = []
    for score, hit in ranked[:top_k]:
        if score <= 0:
            break
        # 返回副本而非改缓存里的 hit，避免把本次打分写进共享缓存
        result.append(replace(hit, score=score))
    return result


def reset(collection: str | None = None) -> None:
    """清掉 BM25 缓存（知识库重建后调用）。不传参数则全部清空。"""
    if collection is None:
        _cache.clear()
    else:
        _cache.pop(collection, None)


__all__ = ["Bm25Hit", "reset", "search"]
