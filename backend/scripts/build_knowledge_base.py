#!/usr/bin/env python
"""六大知识库构建入口。

    python scripts/build_knowledge_base.py --dry-run          # 只看要做什么
    python scripts/build_knowledge_base.py --skip-embed       # 只转换+切分
    python scripts/build_knowledge_base.py                    # 全量入库

流程：扫描 docs/ -> PDF / Word 经 MinerU 转成同目录同名 md -> 按类型切分
-> BGE-M3 向量化 -> 按文件所在子目录写入对应的 Milvus collection
-> 入库成功的源 PDF / Word 归档到 docs0/<原父目录>/。

切分方式：xlsx 按行；md 按标题层级；pdf / word 先转 md 再按标题层级。

切分素材**只从 docs/ 下找**；docs0/ 是归档目录，不会被当作素材来源。

配置全部来自 backend/.env，见 app/core/config.py。
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

# 允许从任意目录直接运行本脚本
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.services.rag import ingest, milvus_client  # noqa: E402
from app.services.rag.collections import KB_COLLECTIONS, resolve_by_collection_name, resolve_by_directory  # noqa: E402

logger = logging.getLogger("build_knowledge_base")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把 docs/ 下的六大知识库素材转成 Milvus 向量库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--docs-root", type=Path, default=None, help="覆盖 .env 的 KB_DOCS_ROOT")
    parser.add_argument("--docs0-root", type=Path, default=None, help="覆盖 .env 的 KB_ARCHIVE_ROOT（归档目录）")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="NAME",
        help="只处理指定知识库，可用 collection 名（kb_insurance）或目录名（医保知识库）；可重复",
    )
    parser.add_argument("--tier", default=None, help="覆盖 .env 的 MINERU_TIER（flash/basic/standard/advanced）")
    parser.add_argument("--skip-convert", action="store_true", help="跳过 MinerU，只用现成的 md")
    parser.add_argument("--skip-xlsx", action="store_true", help="跳过 xlsx")
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="入库成功后不把源 PDF / Word 移到 docs0/（默认会移，见 .env 的 KB_ARCHIVE_ROOT）",
    )
    parser.add_argument("--skip-embed", action="store_true", help="只转换和切分，不加载模型、不连 Milvus")
    parser.add_argument("--force", action="store_true", help="强制重新解析 PDF，忽略已有 md")
    parser.add_argument("--reset", action="store_true", help="入库前 drop 并重建目标 collection")
    parser.add_argument("--dry-run", action="store_true", help="只扫描和统计，不做任何转换与写入")
    parser.add_argument(
        "--verbose-chunks", type=int, default=0, metavar="N", help="打印每个文件前 N 个 chunk 的标题与摘要"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="打印调试日志")
    return parser.parse_args(argv)


def _resolve_dir(arg: Path | None, fallback: Path) -> Path:
    if arg is None:
        return fallback
    return arg if arg.is_absolute() else (BACKEND_DIR / arg).resolve()


def _resolve_docs_root(arg: Path | None) -> Path:
    return _resolve_dir(arg, settings.docs_root)


def _resolve_archive_root(arg: Path | None) -> Path:
    return _resolve_dir(arg, settings.archive_root)


def _selected_kb_names(only: list[str]) -> set[str] | None:
    """把 --only 的输入统一成 collection 名；返回 None 表示全选。"""
    if not only:
        return None
    names: set[str] = set()
    for item in only:
        kb = resolve_by_collection_name(item) or resolve_by_directory(item)
        if kb is None:
            valid = "、".join(f"{c.collection_name}({c.directory})" for c in KB_COLLECTIONS)
            raise SystemExit(f"未知的知识库: {item}\n可用: {valid}")
        names.add(kb.collection_name)
    return names


def _report_plan(
    docs_root: Path,
    archive_root: Path,
    scan: ingest.ScanResult,
    selected: set[str] | None,
    *,
    no_archive: bool,
) -> None:
    print(f"docs 根目录:   {docs_root}")
    print(f"归档 目录:     {archive_root}{'（--no-archive，不归档）' if no_archive else ''}")
    if scan.unknown_dirs:
        print(f"⚠ 未映射到知识库的目录（会被忽略）: {'、'.join(scan.unknown_dirs)}")
    print()

    by_kb: dict[str, list[ingest.SourceDoc]] = defaultdict(list)
    for doc in scan.documents:
        by_kb[doc.kb.collection_name].append(doc)

    print(f"{'collection':<16}{'目录':<12}{'文件':<6}{'待转换':<8}{'待归档':<8}源文件")
    print("-" * 100)
    for kb in KB_COLLECTIONS:
        if selected is not None and kb.collection_name not in selected:
            continue
        docs = by_kb.get(kb.collection_name, [])
        pending = sum(1 for d in docs if d.needs_conversion)
        archive = sum(1 for d in docs if _will_archive(d, no_archive))
        print(f"{kb.collection_name:<16}{kb.directory:<12}{len(docs):<6}{pending:<8}{archive:<8}", end="")
        if docs:
            print("、".join(d.rel_path.name for d in docs))
        else:
            print("(无素材)")
    print()


def _will_archive(doc: ingest.SourceDoc, no_archive: bool) -> bool:
    return (
        not no_archive
        and doc.origin_path is not None
        and doc.origin_path.suffix.lower() in ingest.ARCHIVE_SUFFIXES
    )


def _convert_sources(scan: ingest.ScanResult, tier: str) -> dict[Path, Path]:
    """把待转换的 PDF / Word 都转掉，返回 {源文件绝对路径: md 绝对路径}。"""
    converted: dict[Path, Path] = {}
    if not scan.pending_sources:
        return converted

    mineru_cmd = ingest.resolve_mineru_command()
    logger.info("MinerU 命令: %s", " ".join(mineru_cmd))
    ingest.ensure_mineru_server(mineru_cmd)

    for doc in scan.pending_sources:
        try:
            converted[doc.path] = ingest.convert_to_markdown(
                doc.path,
                tier=tier,
                wait_seconds=settings.mineru_wait_seconds,
                mineru_cmd=mineru_cmd,
            )
        except Exception as exc:  # noqa: BLE001 - 单个文件失败不该中断整批
            logger.error("转换失败 %s: %s", doc.rel_path, exc)
    return converted


def _build_worklist(
    scan: ingest.ScanResult,
    converted: dict[Path, Path],
    *,
    skip_xlsx: bool,
) -> list[ingest.SourceDoc]:
    """转换完成后，确定真正要切分入库的文件清单。

    PDF / Word 条目改指向其 md 产物；转换失败的跳过（它没有可入库的内容）。
    """
    worklist: list[ingest.SourceDoc] = []
    for doc in scan.documents:
        if doc.doc_type == "excel":
            if not skip_xlsx:
                worklist.append(doc)
            continue
        # 按 path 的真实类型判断是否已就绪，不能按 doc_type —— 由 PDF / Word 转出来的
        # md 其 doc_type 已被还原成 pdf / word，但它本身已是 md，不需要再转换。
        # origin_path 也已由 scan_documents 填好（原生 md 为 None，无从归档）。
        if not doc.needs_conversion:
            worklist.append(doc)
            continue

        # 还带着 pdf / word 原件的条目：转换成功才有 md 可用
        md_path = converted.get(doc.path)
        if md_path is None:
            logger.warning("跳过未转换成功的 %s: %s", doc.doc_type, doc.rel_path)
            continue
        # rel_path / doc_type 保留源文件信息：便于在 Milvus 里溯源，
        # origin_path 则用于入库成功后把源文件归档到 docs0/
        worklist.append(
            ingest.SourceDoc(
                path=md_path,
                rel_path=doc.rel_path,
                kb=doc.kb,
                doc_type=doc.doc_type,
                origin_path=doc.path,
            )
        )
    return worklist


def _preview_chunks(docs: list[ingest.SourceDoc], limit: int) -> None:
    for doc in docs:
        chunks = ingest.load_chunks(doc)
        print(f"\n=== {doc.rel_path}  [{doc.kb.collection_name}]  {len(chunks)} chunks")
        for chunk in chunks[:limit]:
            summary = chunk.text.replace("\n", " ")[:80]
            print(f"  #{chunk.chunk_index:<4} [{chunk.title_path or '-'}] {summary}")
    print()


def _summarize(results: list[ingest.IngestResult]) -> int:
    if not results:
        return 0

    per_kb: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))  # collection -> (文件数, chunk 数)
    for r in results:
        files, chunks = per_kb[r.collection_name]
        per_kb[r.collection_name] = (files + 1, chunks + r.chunk_count)

    print()
    print(f"{'collection':<16}{'文件数':<8}{'chunk 数':<10}")
    print("-" * 36)
    for name in sorted(per_kb):
        files, chunks = per_kb[name]
        print(f"{name:<16}{files:<8}{chunks:<10}")

    errors = [r for r in results if r.error]
    if errors:
        print(f"\n⚠ {len(errors)} 个文件失败：")
        for r in errors:
            print(f"  - {r.source_file}: {r.error}")
    print(f"\n合计: {len(results)} 个文件, {sum(r.chunk_count for r in results)} 个 chunk, 失败 {len(errors)} 个")
    return len(errors)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    # langchain / FlagEmbedding 的 INFO 日志很吵
    for noisy in ("httpx", "urllib3", "modelscope", "filelock", "FlagEmbedding"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    docs_root = _resolve_docs_root(args.docs_root)
    archive_root = _resolve_archive_root(args.docs0_root)
    selected = _selected_kb_names(args.only)
    tier = args.tier or settings.mineru_tier

    print(f"Milvus: {settings.milvus_uri}")
    print(f"Embedding: {settings.embedding_model} (dim={settings.embedding_dim})")
    print(f"MinerU tier: {tier}")
    print()

    # archive_root 传进去是为了识别「已归档 PDF 留下的 md」，让 source_file 在
    # 归档前后保持一致，重跑不会产生重复
    scan = ingest.scan_documents(docs_root, archive_root=archive_root, force=args.force)
    if selected is not None:
        scan.documents = [d for d in scan.documents if d.kb.collection_name in selected]
        scan.pending_sources = [d for d in scan.pending_sources if d.kb.collection_name in selected]

    _report_plan(docs_root, archive_root, scan, selected, no_archive=args.no_archive)

    if not scan.documents:
        print("没有找到任何待入库的文件。")
        return 0

    if args.dry_run:
        print("--dry-run：到此为止，未做任何转换与写入。")
        return 0

    # --- PDF / Word 转换 ---
    converted: dict[Path, Path] = {}
    if args.skip_convert:
        if scan.pending_sources:
            print(f"--skip-convert：跳过 {len(scan.pending_sources)} 个 PDF / Word 的转换")
            for doc in scan.pending_sources:
                md_path = doc.path.with_suffix(".md")
                if md_path.is_file():
                    converted[doc.path] = md_path
    else:
        converted = _convert_sources(scan, tier)

    worklist = _build_worklist(scan, converted, skip_xlsx=args.skip_xlsx)
    if not worklist:
        print("没有可入库的文件。")
        return 1

    # --- 只切分，不入库 ---
    if args.skip_embed:
        print(f"--skip-embed：只切分 {len(worklist)} 个文件\n")
        total = 0
        for doc in worklist:
            chunks = ingest.load_chunks(doc)
            total += len(chunks)
            print(f"  {doc.rel_path}  ->  {len(chunks)} chunks  [{doc.kb.collection_name}]")
        print(f"\n合计 {total} 个 chunk（未向量化、未入库）")
        if args.verbose_chunks:
            _preview_chunks(worklist, args.verbose_chunks)
        return 0

    if args.verbose_chunks:
        _preview_chunks(worklist, args.verbose_chunks)

    # --- 向量化 + 入库 ---
    if args.reset:
        client = milvus_client.get_client()
        for name in sorted({d.kb.collection_name for d in worklist}):
            milvus_client.drop_collection(client, name)

    results: list[ingest.IngestResult] = []
    archived: list[Path] = []
    for index, doc in enumerate(worklist, 1):
        print(f"[{index}/{len(worklist)}] {doc.rel_path} … ", end="", flush=True)
        result = ingest.ingest_document(doc, reset=False)
        results.append(result)
        if result.error:
            print(f"失败: {result.error}")
            continue

        line = f"{result.chunk_count} chunks  {result.seconds:.1f}s  -> {result.collection_name}"
        if not args.no_archive:
            # 入库成功才归档。失败的原件留在 docs/ 里，方便直接重跑这一份
            try:
                moved = ingest.archive_processed(doc, archive_root)
            except OSError as exc:
                print(f"{line}\n  ⚠ 归档失败（原件仍在 docs/）: {exc}")
                continue
            if moved is not None:
                archived.append(moved)
                line += f"  ⇢ 已归档 {moved.parent.name}/"
        print(line)

    failed = _summarize(results)
    if archived:
        print(f"已归档 {len(archived)} 个源文件到 {archive_root}")

    # 收尾打印各库实际行数，便于和上面的 chunk 数对账
    client = milvus_client.get_client()
    print("\nMilvus 实际行数：")
    for name in sorted({d.kb.collection_name for d in worklist}):
        print(f"  {name:<16}{milvus_client.count(client, name)}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
