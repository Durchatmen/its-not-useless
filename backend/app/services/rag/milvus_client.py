"""Milvus 连接与 collection 管理。

六个知识库各一个 collection，表结构统一（见 `build_schema`）。
对外只暴露「确保建好、写入、清空、统计」四件事，检索逻辑不在这里。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from pymilvus import DataType, MilvusClient

from app.core.config import settings

logger = logging.getLogger(__name__)

# Milvus 对 VARCHAR 的硬上限
MAX_VARCHAR_LENGTH = 65535

VECTOR_FIELD = "vector"
PRIMARY_FIELD = "pk"

_client: MilvusClient | None = None


def get_client() -> MilvusClient:
    """按 .env 里的 MILVUS_HOST / MILVUS_PORT 建连接，进程内复用。"""
    global _client
    if _client is None:
        logger.info("连接 Milvus: %s", settings.milvus_uri)
        _client = MilvusClient(
            uri=settings.milvus_uri,
            token=settings.milvus_token,
            timeout=settings.milvus_timeout,
        )
    return _client


def reset_client() -> None:
    """丢弃缓存的连接（测试或切换地址后调用）。"""
    global _client
    _client = None


def build_schema(dim: int):
    """六个 collection 共用的表结构。"""
    schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field(PRIMARY_FIELD, DataType.INT64, is_primary=True, auto_id=True)
    schema.add_field(VECTOR_FIELD, DataType.FLOAT_VECTOR, dim=dim)
    # chunk 正文，最长按 Milvus 上限给
    schema.add_field("text", DataType.VARCHAR, max_length=MAX_VARCHAR_LENGTH)
    # 来源文件，相对 docs/ 的路径，如「医保知识库/国家基本医疗保险….pdf」
    schema.add_field("source_file", DataType.VARCHAR, max_length=512)
    # 知识库中文名，如「医保知识库」
    schema.add_field("category", DataType.VARCHAR, max_length=64)
    # 源文件类型：pdf / word / excel / markdown
    schema.add_field("doc_type", DataType.VARCHAR, max_length=16)
    # markdown 标题面包屑，如「一、血常规 > 1.1 白细胞计数 WBC」
    schema.add_field("title_path", DataType.VARCHAR, max_length=512)
    # 文档内序号
    schema.add_field("chunk_index", DataType.INT64)
    # 仅 xlsx 用，其余为空串
    schema.add_field("sheet_name", DataType.VARCHAR, max_length=64)
    return schema


def build_index_params():
    """向量索引：AUTOINDEX + COSINE。

    BGE-M3 的输出已做 L2 归一化（实测范数为 1.0），COSINE 与内积等价且更直观。
    AUTOINDEX 让 Milvus 自选索引类型，省去调参。
    """
    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(
        field_name=VECTOR_FIELD,
        index_type="AUTOINDEX",
        metric_type="COSINE",
    )
    return index_params


def ensure_collection(
    client: MilvusClient,
    collection_name: str,
    dim: int,
    description: str = "",
) -> None:
    """collection 不存在才创建；已存在则原样返回（不校验表结构差异）。"""
    if client.has_collection(collection_name):
        logger.debug("collection 已存在，跳过创建: %s", collection_name)
        return
    logger.info("创建 collection: %s (dim=%d)", collection_name, dim)
    client.create_collection(
        collection_name=collection_name,
        schema=build_schema(dim),
        index_params=build_index_params(),
    )


def drop_collection(client: MilvusClient, collection_name: str) -> None:
    """删库重来前调用。不存在的库静默跳过。"""
    if client.has_collection(collection_name):
        logger.warning("删除 collection: %s", collection_name)
        client.drop_collection(collection_name)


def delete_by_source(client: MilvusClient, collection_name: str, source_file: str) -> int:
    """清掉某个来源文件的全部旧 chunk，保证重跑不产生重复。

    注意 pymilvus 3.x 的过滤参数叫 `filter`（不是 `expr`）。
    """
    if not client.has_collection(collection_name):
        return 0
    # 文件名里可能有单引号或反斜杠，统一转义后再拼表达式
    escaped = source_file.replace("\\", "\\\\").replace('"', '\\"')
    result = client.delete(collection_name=collection_name, filter=f'source_file == "{escaped}"')
    return int(result.get("delete_count", 0)) if isinstance(result, dict) else 0


def insert_chunks(
    client: MilvusClient,
    collection_name: str,
    rows: Sequence[dict[str, Any]],
) -> int:
    """写入一批 chunk，并 flush 使其立即可见。

    rows 每项须含 vector 与全部标量字段（pk 由 auto_id 生成，不要传）。
    `insert` 自身不 flush，不显式刷盘的话紧随其后的 get_collection_stats
    读到的行数会偏少。
    """
    if not rows:
        return 0
    result = client.insert(collection_name=collection_name, data=list(rows))
    # 空插入时 insert_count 会被 OmitZeroDict 抹掉，回退到 len(rows)
    inserted = result.get("insert_count", 0) if isinstance(result, dict) else 0
    client.flush(collection_name)
    logger.debug("写入 %s: %d 条", collection_name, inserted or len(rows))
    return int(inserted or len(rows))


def count(client: MilvusClient, collection_name: str) -> int:
    """collection 行数；不存在返回 0。"""
    if not client.has_collection(collection_name):
        return 0
    stats = client.get_collection_stats(collection_name)
    return int(stats.get("row_count", 0))


@dataclass
class IngestedChunk:
    """切分产物：正文 + 全部标量元数据（不含向量）。"""

    text: str
    source_file: str
    category: str
    doc_type: str
    title_path: str = ""
    chunk_index: int = 0
    sheet_name: str = ""

    def to_row(self, vector: Iterable[float]) -> dict[str, Any]:
        """转成 Milvus insert 要的 dict（pk 由 auto_id 生成，不传）。"""
        return {
            VECTOR_FIELD: list(vector),
            "text": self.text,
            "source_file": self.source_file,
            "category": self.category,
            "doc_type": self.doc_type,
            "title_path": self.title_path,
            "chunk_index": self.chunk_index,
            "sheet_name": self.sheet_name,
        }


__all__ = [
    "IngestedChunk",
    "MAX_VARCHAR_LENGTH",
    "PRIMARY_FIELD",
    "VECTOR_FIELD",
    "build_index_params",
    "build_schema",
    "count",
    "delete_by_source",
    "drop_collection",
    "ensure_collection",
    "get_client",
    "insert_chunks",
    "reset_client",
]
