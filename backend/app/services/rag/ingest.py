"""知识库构建管线：docs/ 扫描 -> 转 md -> 切分 -> (向量化) -> Milvus。

按阶段拆成互不依赖的纯函数，便于单独调用与调试：

    scan_documents()       扫描 docs/，按子目录归到六大知识库
    convert_to_markdown()  调 MinerU 把 PDF / Word 转成同目录同名 md
    archive_processed()    把已入库的原始 PDF / Word 移到 docs0/<原父目录>/
    chunk_markdown()       md 按标题层级切分
    chunk_xlsx()           xlsx 按行结构化切分
    load_chunks()          上面两个的调度入口
    ingest_document()      切分 -> 向量化 -> 写 Milvus

切分方式按源文件类型分派：

    .xlsx / .xls   按行切，一行 = 一个 chunk（列名与值拼成自然语句）
    .md            按 markdown 标题层级切
    .pdf           先 MinerU 转 md，再按标题层级切
    .doc / .docx   先 MinerU 转 md，再按标题层级切

Word 之所以不单独写一套解析：MinerU 原生支持 doc/docx（OFFICE_EXTENSIONS），
转换后得到带 `#` 标题的 md，与 PDF 共用同一条切分链路，且旧版 .doc 也能吃。

向量化与 Milvus 写入只发生在 `ingest_document`，因此 `--skip-embed` 与
`--dry-run` 路径都不会加载 4.3 GB 的 BGE-M3，也不会去连 Milvus。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services.rag import milvus_client
from app.services.rag.collections import KbCollection, resolve_by_directory, resolve_by_relative_path
from app.services.rag.milvus_client import IngestedChunk

logger = logging.getLogger(__name__)

# 记录的是「源文件」的类型，不是切分时读取的文件的类型：
# 一份 PDF 转成 md 后入库，doc_type 仍是 pdf，方便检索时按来源过滤与溯源。
DocType = Literal["pdf", "word", "excel", "markdown"]

# md 标题层级 -> 元数据键；用于切分与 title_path 面包屑
HEADERS_TO_SPLIT_ON: list[tuple[str, str]] = [("#", "h1"), ("##", "h2"), ("###", "h3")]

# 中文没有空格分词，按段落 -> 行 -> 句读逐级降级，末尾空串兜底。
# 末尾的空串不能省：没有字符级兜底时，一段超长无标点文本会整块超限输出。
CHINESE_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", "、", ""]

# MinerU 写在 md 里的两类注释：页码标记与「下一页」续读提示
_PAGE_MARKER_RE = re.compile(r"^\s*<!--\s*page\s+\d+\s+of\s+\d+\s*-->\s*$", re.MULTILINE)
_NEXT_HINT_RE = re.compile(r"^\s*<!--\s*Next:.*?-->\s*$", re.MULTILINE | re.DOTALL)

# 扫描件（图片型 PDF）会被 MinerU 包成图片块，正文塞在 <details> 里。
# 这些 HTML 脚手架不该进向量：标记行整行删掉，<details> 壳去掉但保留里面的正文。
_IMAGE_BLOCK_RE = re.compile(r"^\s*!\[Image block[^\]]*\]\([^)]*\)\s*$", re.MULTILINE)
_SUMMARY_RE = re.compile(r"^\s*<summary[^>]*>.*?</summary>\s*$", re.MULTILINE | re.DOTALL)
_DETAILS_TAG_RE = re.compile(r"^\s*</?details[^>]*>\s*$", re.MULTILINE)

_PDF_SUFFIXES = {".pdf"}
_WORD_SUFFIXES = {".doc", ".docx"}
_EXCEL_SUFFIXES = {".xlsx", ".xls"}

# 需要先经 MinerU 转成 md 的类型。Excel 不在此列 —— 它按行结构化入库，
# 转成 md 反而把行与列的结构拍平了。
_MINERU_SUFFIXES: frozenset[str] = frozenset(_PDF_SUFFIXES | _WORD_SUFFIXES)

_DOC_TYPE_BY_SUFFIX: dict[str, DocType] = {
    ".pdf": "pdf",
    ".doc": "word",
    ".docx": "word",
    ".xlsx": "excel",
    ".xls": "excel",
}

# 入库成功后从 docs/ 移到 docs0/ 的源文件类型：
# PDF 与 Word 都会被转成 md 留在 docs/，原件不再参与后续处理，因此一并归档。
# Excel 不在其中 —— 它按行结构化切分，docs/ 下的 xlsx 始终是唯一副本。
ARCHIVE_SUFFIXES: frozenset[str] = frozenset(_PDF_SUFFIXES | _WORD_SUFFIXES)


# ---------------------------------------------------------------- 扫描


@dataclass
class SourceDoc:
    """一个待入库的源文件。

    `path` 与 `rel_path` 在转换过的文档上并不指向同一个文件：PDF 转成 md 后，
    切分读的是 md（path），而溯源与归档用的仍是原始 PDF（rel_path / origin_path）。
    """

    path: Path
    """实际读取并切分的文件：md 本身，或 md 产物，或 xlsx。"""

    rel_path: Path
    """源文件相对 docs/ 的路径，写入 Milvus 的 source_file（如 医保知识库/x.pdf）。"""

    kb: KbCollection

    doc_type: DocType
    """源文件类型。"""

    origin_path: Path | None = None
    """需要归档的原始文件（已转成 md 的 pdf / word）；原生 md 与 xlsx 为 None。"""

    @property
    def category(self) -> str:
        return self.kb.directory

    @property
    def needs_conversion(self) -> bool:
        """是否还需要调 MinerU（path 仍是 pdf / word 本身）。"""
        return self.path.suffix.lower() in _MINERU_SUFFIXES


@dataclass
class ScanResult:
    documents: list[SourceDoc]
    """需要入库的文件（待转换的 pdf / word 也在内）。"""

    pending_sources: list[SourceDoc]
    """其中还需要调 MinerU 转换的 PDF / Word。"""

    unknown_dirs: list[str]
    """docs/ 下无法映射到任何知识库的子目录。"""


def _iter_kb_dirs(docs_root: Path) -> tuple[list[Path], list[str]]:
    """列出 docs/ 下的一级子目录，并分出能映射到知识库的那些。"""
    known: list[Path] = []
    unknown: list[str] = []
    for child in sorted(p for p in docs_root.iterdir() if p.is_dir()):
        if resolve_by_directory(child.name) is not None:
            known.append(child)
        else:
            unknown.append(child.name)
    return known, unknown


def _stem_of(rel_path: Path) -> Path:
    """去掉 .md 扩展名，保留文件名里其余的点和空格。

    `Path("a.b.md").with_suffix("")` 会得到 `a.b`，再 `.with_suffix(".pdf")` 却
    变成 `a.pdf` —— 把 `.b` 当成扩展名吃掉了。所以按字符串截，不按 Path 语义。
    """
    text = str(rel_path)
    return Path(text[: -len(".md")] if text.lower().endswith(".md") else text)


def _detect_origin_suffix(md_rel_path: Path, docs_root: Path, archive_root: Path | None) -> str | None:
    """md 若是 PDF / Word 经 MinerU 转出来的，返回那个源文件的扩展名。

    注意这里查 docs0/ 只是**认名字**，不是找素材 —— 切分素材永远只来自 docs/。
    之所以要连归档目录一起查：源文件可能还在 docs/ 下，也可能已经移到 docs0/，
    「归档前」和「归档后」两次扫描必须得出同一个 source_file，
    否则重跑时 `delete_by_source` 匹配不上旧记录，同一个文件会被入库两遍。
    """
    stem = _stem_of(md_rel_path)
    roots = [docs_root] if archive_root is None else [docs_root, archive_root]
    for suffix in sorted(_MINERU_SUFFIXES):
        for root in roots:
            if Path(f"{root / stem}{suffix}").is_file():
                return suffix
    return None


def scan_documents(
    docs_root: Path,
    *,
    archive_root: Path | None = None,
    force: bool = False,
) -> ScanResult:
    """扫描 docs/，按子目录归到六大知识库。

    **素材只从 docs/ 下找**，docs0/ 里的归档件一律不作为切分来源 ——
    archive_root 参数只参与「这个 md 的源文件叫什么名字」的判定。

    只处理一级子目录下的文件（递归到子目录，但不做更深的层级推断）。
    PDF / Word 若已存在同名 md，则只保留 md，不再重复转换；force=True 时无视已有 md。
    """
    if not docs_root.is_dir():
        raise FileNotFoundError(f"docs 根目录不存在: {docs_root}")

    kb_dirs, unknown_dirs = _iter_kb_dirs(docs_root)

    # 先按类型收齐，再分类 —— 避免依赖遍历顺序（.md 排在 .pdf 前面，边遍历边判断会出错）
    convertibles: dict[Path, SourceDoc] = {}  # pdf / word，需经 MinerU
    markdowns: dict[Path, SourceDoc] = {}
    spreadsheets: list[SourceDoc] = []

    for kb_dir in kb_dirs:
        for path in sorted(kb_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.name.startswith("~$"):
                # Excel / Word 打开文件时产生的锁文件，不是真实素材
                logger.debug("跳过临时文件: %s", path.name)
                continue
            rel_path = path.relative_to(docs_root)
            kb = resolve_by_relative_path(rel_path)
            if kb is None:  # 理论上不会发生，_iter_kb_dirs 已过滤
                continue

            suffix = path.suffix.lower()
            if suffix in _MINERU_SUFFIXES:
                convertibles[path] = SourceDoc(path, rel_path, kb, _DOC_TYPE_BY_SUFFIX[suffix])
            elif suffix == ".md":
                # 若是 PDF / Word 的转换产物，source_file 与 doc_type 都还原成源文件。
                # 两个都要还原，否则原件归档之后再跑一遍，同一个文件会以
                # source_file=x.md / doc_type=markdown 的面目重新入库一遍：
                # delete_by_source 匹配不上旧记录，按 doc_type 过滤也查不到它。
                origin_suffix = _detect_origin_suffix(rel_path, docs_root, archive_root)
                if origin_suffix:
                    source_rel = Path(f"{_stem_of(rel_path)}{origin_suffix}")
                    doc_type: DocType = _DOC_TYPE_BY_SUFFIX[origin_suffix]
                else:
                    source_rel = rel_path
                    doc_type = "markdown"
                markdowns[path] = SourceDoc(path, source_rel, kb, doc_type)
            elif suffix in _EXCEL_SUFFIXES:
                spreadsheets.append(SourceDoc(path, rel_path, kb, "excel"))
            else:
                logger.debug("跳过不支持的文件类型: %s", rel_path)

    # 源文件的 md 产物已存在时，用 md 条目（顺带记上 origin_path 以便入库后归档），
    # 源文件本身不进待转换队列
    documents = list(spreadsheets) + list(markdowns.values())
    pending_sources: list[SourceDoc] = []
    for path, doc in convertibles.items():
        md_path = path.with_suffix(".md")
        existing = markdowns.get(md_path)
        if existing is not None and not force:
            existing.origin_path = path
            continue
        if existing is not None:
            # 强制重转：旧的 md 条目让位给源文件条目
            documents = [d for d in documents if d.path is not existing]
            del markdowns[md_path]
        documents.append(doc)
        pending_sources.append(doc)

    documents.sort(key=lambda d: str(d.rel_path))
    return ScanResult(documents, pending_sources, unknown_dirs)


# ------------------------------------------------- 源文件（PDF / Word）-> md


def resolve_mineru_command() -> list[str]:
    """定位 mineru 可执行文件。

    优先 .env 的 MINERU_BIN，其次当前解释器同目录下的 mineru（venv），
    再退到 PATH，最后用 `python -m mineru.cli.main`。
    """
    if settings.mineru_bin:
        return [settings.mineru_bin]

    exe_name = "mineru.exe" if os.name == "nt" else "mineru"
    candidate = Path(sys.executable).parent / exe_name
    if candidate.is_file():
        return [str(candidate)]

    found = shutil.which("mineru")
    if found:
        return [found]

    return [sys.executable, "-m", "mineru.cli.main"]


def ensure_mineru_server(mineru_cmd: list[str]) -> None:
    """MinerU 4.x 的 parse 依赖本地后台服务，这里确保它起来了。

    服务已在运行 / 刚启动 / 启动失败都当作「继续尝试解析」，
    真正的失败留给 parse 步骤报错，避免这里掩盖原始错误。
    """
    try:
        proc = subprocess.run(
            [*mineru_cmd, "server", "start"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        message = (proc.stdout or proc.stderr or "").strip().splitlines()
        logger.debug("mineru server start: %s", message[-1] if message else "(无输出)")
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("启动 mineru 服务失败（继续尝试解析）: %s", exc)


def clean_mineru_markdown(text: str) -> str:
    """清掉 MinerU 的脚手架，留下干净的正文 md。

    处理三类：页码注释、「下一页」续读提示、扫描件的图片块包装
    （`![Image block](doc:…)` + `<details>` 壳，正文保留、壳去掉）。
    """
    text = _PAGE_MARKER_RE.sub("", text)
    text = _NEXT_HINT_RE.sub("", text)
    text = _IMAGE_BLOCK_RE.sub("", text)
    text = _SUMMARY_RE.sub("", text)
    text = _DETAILS_TAG_RE.sub("", text)
    # 删行后会留下多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def convert_to_markdown(
    source_path: Path,
    *,
    tier: str,
    wait_seconds: int,
    mineru_cmd: list[str],
) -> Path:
    """把 PDF / Word 转成**同目录同名** md，返回 md 路径。

    `--pages all` 是必须的：MinerU 默认只输出前 10 页。
    用 `-o` 写文件而不是读 stdout，可绕开 CLI 的 `--limit` 字符截断。
    MinerU 按扩展名自动选解析器，PDF 与 doc/docx 走的是同一个命令。
    """
    md_path = source_path.with_suffix(".md")
    tmp_path = md_path.with_suffix(".md.tmp")

    cmd = [
        *mineru_cmd,
        "parse",
        str(source_path),
        "--pages",
        "all",
        "--tier",
        tier,
        "--wait",
        str(wait_seconds),
        "-o",
        str(tmp_path),
    ]
    logger.info("MinerU 解析: %s (tier=%s)", source_path.name, tier)
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tmp_path.unlink(missing_ok=True)
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"MinerU 解析失败（exit={proc.returncode}）: {detail}")

    if not tmp_path.is_file():
        raise RuntimeError(f"MinerU 未产出文件: {tmp_path}（stdout: {(proc.stdout or '').strip()[:200]}）")

    tmp_path.write_text(clean_mineru_markdown(tmp_path.read_text(encoding="utf-8")), encoding="utf-8")
    tmp_path.replace(md_path)
    logger.info("转换完成 %.1fs -> %s", time.time() - started, md_path.name)
    return md_path


def archive_processed(doc: SourceDoc, archive_root: Path) -> Path | None:
    """把已处理完的源文件移到 docs0/ 下与原父目录同名的目录里。

        docs/医保知识库/国家医保目录.pdf  ->  docs0/医保知识库/国家医保目录.pdf

    目标路径直接由 `doc.rel_path` 拼出，因此 docs0 与 docs/ 的目录结构一一镜像。
    返回归档后的路径；无需归档（原生 md / xlsx，或源文件已不在 docs/）时返回 None。
    """
    origin = doc.origin_path
    if origin is None or not origin.is_file():
        return None
    if origin.suffix.lower() not in ARCHIVE_SUFFIXES:
        return None

    target = archive_root / doc.rel_path
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        if target.stat().st_size == origin.stat().st_size:
            # 上一次已经归档过了（比如归档成功但入库统计时报了错），
            # docs/ 里这份是重复件，直接删掉即可，不覆盖归档件
            logger.info("归档件已存在且大小一致，删除 docs/ 中的副本: %s", doc.rel_path)
            origin.unlink()
            return target
        # 同名但内容不同：以本次处理的原件为准。shutil.move 在 Windows 上
        # 遇到已存在的目标会直接抛错，所以先删。
        logger.warning("归档目标已存在且大小不同，覆盖: %s", target)
        target.unlink()

    shutil.move(str(origin), str(target))
    logger.info("已归档 %s -> %s", doc.rel_path, target)
    return target


# ---------------------------------------------------------------- 切分


def _make_size_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=CHINESE_SEPARATORS,
        # 分隔符跟在它所结束的那句话后面，切出来的 chunk 不会以标点开头
        keep_separator="end",
    )


def _title_path_of(metadata: dict) -> str:
    return " > ".join(metadata[key] for _, key in HEADERS_TO_SPLIT_ON if metadata.get(key))


def chunk_markdown(text: str, doc: SourceDoc) -> list[IngestedChunk]:
    """按 markdown 标题层级切分，超长小节再按句读二次切分。"""
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=False,  # 标题留在正文里，给向量更多上下文
    )
    size_splitter = _make_size_splitter()

    sections = [(s.page_content, s.metadata or {}) for s in header_splitter.split_text(text)]
    if not sections:
        # 整篇没有 markdown 标题（MinerU 对纯段落文档可能产出这种）
        sections = [(text, {})]

    chunks: list[IngestedChunk] = []
    for content, metadata in sections:
        title_path = _title_path_of(metadata)
        for piece in size_splitter.split_text(content):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                IngestedChunk(
                    text=piece,
                    source_file=str(doc.rel_path),
                    category=doc.category,
                    doc_type=doc.doc_type,
                    title_path=title_path,
                    chunk_index=len(chunks),
                )
            )
    return chunks


def _format_cell(value: object) -> str:
    """把单元格值转成干净的字符串，空值返回空串。"""
    if value is None:
        return ""
    try:
        import pandas as pd

        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def chunk_xlsx(path: Path, doc: SourceDoc) -> list[IngestedChunk]:
    """xlsx 结构化入库：一行 = 一个 chunk，列名与值拼成自然语句。

    表头识别：真实表上方通常有一行整表标题（已实测两个 sheet 都是这个版式），
    因此取前若干行里第一行「每个单元格都有值」的行作为表头。
    """
    import pandas as pd

    chunks: list[IngestedChunk] = []
    sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=str)

    for sheet_name, frame in sheets.items():
        if frame.empty:
            logger.warning("%s 的 sheet「%s」为空，跳过", path.name, sheet_name)
            continue

        header_row = _detect_header_row(frame)
        columns = [_format_cell(v) for v in frame.iloc[header_row].tolist()]

        for _, row in frame.iloc[header_row + 1 :].iterrows():
            pairs = []
            for column, value in zip(columns, row.tolist()):
                value_text = _format_cell(value)
                if column and value_text:
                    pairs.append(f"{column}：{value_text}")
            if not pairs:
                continue  # 整行空白

            chunks.append(
                IngestedChunk(
                    text="；".join(pairs),
                    source_file=str(doc.rel_path),
                    category=doc.category,
                    doc_type=doc.doc_type,
                    title_path=sheet_name,
                    chunk_index=len(chunks),
                    sheet_name=sheet_name,
                )
            )

    return chunks


def _detect_header_row(frame, max_scan: int = 5) -> int:
    """找表头行：前 max_scan 行里第一行「所有单元格都有值」的。"""
    width = frame.shape[1]
    for i in range(min(max_scan, len(frame))):
        row = frame.iloc[i].tolist()
        if sum(1 for v in row if _format_cell(v)) == width:
            return i
    return 0


def load_chunks(doc: SourceDoc) -> list[IngestedChunk]:
    """按文件类型分派到对应的切分函数。

    excel 按行结构化切分；markdown / pdf / word 统一按 markdown 标题层级切
    —— 后两者的 doc.path 已经是 MinerU 产出的 md，三者共用同一条链路。
    """
    if doc.doc_type == "excel":
        return chunk_xlsx(doc.path, doc)
    return chunk_markdown(doc.path.read_text(encoding="utf-8"), doc)


# ---------------------------------------------------------------- 入库


@dataclass
class IngestResult:
    source_file: str
    collection_name: str
    chunk_count: int
    seconds: float
    error: str | None = None


def ingest_document(doc: SourceDoc, *, reset: bool = False) -> IngestResult:
    """切分 -> 向量化 -> 写 Milvus。单个文件失败不抛出，以 error 字段返回。"""
    from app.services.rag.embedding import embed_texts

    collection_name = doc.kb.collection_name
    started = time.time()
    try:
        chunks = load_chunks(doc)
        if not chunks:
            return IngestResult(str(doc.rel_path), collection_name, 0, time.time() - started)

        vectors = embed_texts([c.text for c in chunks])

        client = milvus_client.get_client()
        if reset:
            milvus_client.drop_collection(client, collection_name)
        milvus_client.ensure_collection(client, collection_name, settings.embedding_dim)
        # 先清掉该文件的旧 chunk，保证重跑幂等
        milvus_client.delete_by_source(client, collection_name, str(doc.rel_path))
        inserted = milvus_client.insert_chunks(
            client, collection_name, [c.to_row(v) for c, v in zip(chunks, vectors)]
        )

        return IngestResult(str(doc.rel_path), collection_name, inserted, time.time() - started)
    except Exception as exc:  # noqa: BLE001 - 单文件失败不应中断整批
        logger.exception("入库失败: %s", doc.rel_path)
        return IngestResult(
            str(doc.rel_path), collection_name, 0, time.time() - started, error=f"{type(exc).__name__}: {exc}"
        )


__all__ = [
    "ARCHIVE_SUFFIXES",
    "CHINESE_SEPARATORS",
    "DocType",
    "HEADERS_TO_SPLIT_ON",
    "IngestResult",
    "ScanResult",
    "SourceDoc",
    "archive_processed",
    "chunk_markdown",
    "chunk_xlsx",
    "clean_mineru_markdown",
    "convert_to_markdown",
    "ensure_mineru_server",
    "ingest_document",
    "load_chunks",
    "resolve_mineru_command",
    "scan_documents",
]
