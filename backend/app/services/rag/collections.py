"""六大知识库的 Milvus collection 注册表。

docs/ 下的第一层子目录名与功能设计文档 §4.1 的六大知识库一一对应，
知识库文件按「它所在的子目录」路由到对应的 collection。

对应关系（环境搭建方案 §6.1）：

    docs/分诊知识库    -> kb_triage      科室及医生知识库（分诊）
    docs/药品知识库    -> kb_medication  药品知识库（用药提醒）
    docs/检查知识库    -> kb_exam        检查知识库（检查指引）
    docs/报告知识库    -> kb_report      报告知识库（报告解读）
    docs/医保知识库    -> kb_insurance   医保知识库（医保咨询）
    docs/诊疗知识库    -> kb_diagnosis   诊疗知识库（预诊）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

IngestMode = Literal["markdown", "xlsx"]


@dataclass(frozen=True)
class KbCollection:
    """一个知识库：源文件所在目录 + 目标 collection + 入库方式。"""

    directory: str
    """docs/ 下的第一层子目录名（中文）。"""

    collection_name: str
    """Milvus collection 名（须匹配 [A-Za-z_][A-Za-z0-9_]*）。"""

    description: str
    """服务场景，写入 collection 描述便于运维辨认。"""

    ingest_mode: IngestMode = "markdown"
    """markdown: 走 md 切分；xlsx: 按行结构化入库。"""


KB_COLLECTIONS: tuple[KbCollection, ...] = (
    KbCollection("分诊知识库", "kb_triage", "科室及医生知识库（分诊）", "xlsx"),
    KbCollection("药品知识库", "kb_medication", "药品知识库（用药提醒）"),
    KbCollection("检查知识库", "kb_exam", "检查知识库（检查指引）"),
    KbCollection("报告知识库", "kb_report", "报告知识库（报告解读）"),
    KbCollection("医保知识库", "kb_insurance", "医保知识库（医保咨询）"),
    KbCollection("诊疗知识库", "kb_diagnosis", "诊疗知识库（预诊）"),
)

BY_DIRECTORY: dict[str, KbCollection] = {c.directory: c for c in KB_COLLECTIONS}
BY_NAME: dict[str, KbCollection] = {c.collection_name: c for c in KB_COLLECTIONS}


def resolve_by_directory(directory: str) -> KbCollection | None:
    """按 docs/ 下的第一层子目录名查知识库。"""
    return BY_DIRECTORY.get(directory)


def resolve_by_collection_name(name: str) -> KbCollection | None:
    return BY_NAME.get(name)


def resolve_by_relative_path(rel_path: str | Path) -> KbCollection | None:
    """按「相对 docs/ 的路径」的第一层目录名查知识库。

    >>> resolve_by_relative_path("医保知识库/国家基本医疗保险….pdf")
    KbCollection(directory='医保知识库', collection_name='kb_insurance', ...)
    """
    parts = Path(rel_path).parts
    if len(parts) < 2:
        # 直接躺在 docs/ 根下的文件没有归属，不做猜测
        return None
    return BY_DIRECTORY.get(parts[0])
