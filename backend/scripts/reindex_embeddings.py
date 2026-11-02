"""Rebuild per-novel vector chunks with the bge-m3 ONNX encoder.

Default is a read-only dry-run: it lists finalized chapters and chunk counts
without writing anything. ``--apply`` backs up ``vectors/chunks.json`` first,
rebuilds with 1024-dim bge-m3 vectors, then validates count and dimensions.

Only finalized chapters are processed. Chapter text, memory tables, and chapter
status are never modified.

Usage (from backend/):
  python scripts/reindex_embeddings.py                     # dry-run, all novels
  python scripts/reindex_embeddings.py --novel-uid novel_xxx
  python scripts/reindex_embeddings.py --apply             # writes after backup
  python scripts/reindex_embeddings.py --compare-query 江边黄昏照 --compare-query 开学
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_config  # noqa: E402
from app.core.text_hash import text_sha256  # noqa: E402
from app.db.vector_store import NovelVectorStore, VectorChunkRecord  # noqa: E402
from app.services.embedding.encoder import (  # noqa: E402
    EMBEDDING_DIM,
    EMBEDDING_MODEL_ID,
    EMBEDDING_VERSION,
    LEGACY_EMBEDDING_DIM,
    LEGACY_EMBEDDING_VERSION,
    EmbeddingModelUnavailable,
    encode_text_legacy_hash_sync,
    encode_texts_sync,
    get_embedding_runtime_status,
)
from app.services.memory.finalizer import split_text_chunks  # noqa: E402


def _open_ro(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _discover_novels(novel_uid: str | None) -> list[Path]:
    cfg = get_config()
    if novel_uid:
        target = cfg.novel_dir(novel_uid)
        if not (target / "novel.db").exists():
            raise SystemExit(f"找不到作品数据库：{target / 'novel.db'}")
        return [target]
    paths = [
        sub
        for sub in sorted(cfg.data_dir.iterdir())
        if sub.is_dir() and sub.name != "models" and (sub / "novel.db").exists()
    ]
    if not paths:
        raise SystemExit("没有找到任何作品数据库。")
    return paths


def _finalized_chapters(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, sort_order, story_time, content_hash
        FROM chapters
        WHERE status = 'final' AND continuity_review_required = 0
        ORDER BY sort_order ASC, id ASC
        """
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        cid = int(row["id"])
        version = conn.execute(
            "SELECT id, content FROM chapter_versions WHERE chapter_id = ? "
            "ORDER BY version DESC, id DESC LIMIT 1",
            (cid,),
        ).fetchone()
        content = str(version["content"]) if version else ""
        if not content.strip():
            continue
        scenes = conn.execute(
            "SELECT id, pov_character, character_ids, location_id FROM scenes "
            "WHERE chapter_id = ? ORDER BY id ASC",
            (cid,),
        ).fetchall()
        char_ids: set[int] = set()
        for scene in scenes:
            if scene["pov_character"]:
                char_ids.add(int(scene["pov_character"]))
            try:
                char_ids.update(int(x) for x in json.loads(scene["character_ids"] or "[]"))
            except Exception:
                pass
        loc_id = next((int(s["location_id"]) for s in scenes if s["location_id"]), None)
        result.append(
            {
                "chapter_id": cid,
                "sort_order": float(row["sort_order"]),
                "story_time": str(row["story_time"] or ""),
                "content_hash": str(row["content_hash"] or ""),
                "content": content,
                "scene_id": int(scenes[0]["id"]) if scenes else None,
                "character_ids": sorted(char_ids),
                "location_id": loc_id,
                "pieces": split_text_chunks(content),
            }
        )
    return result


def _build_records(chapters: list[dict]) -> list[VectorChunkRecord]:
    pieces: list[str] = []
    for chapter in chapters:
        pieces.extend(chapter["pieces"])
    vectors = encode_texts_sync(pieces)
    if len(vectors) != len(pieces):
        raise RuntimeError(f"编码数量不匹配：切片 {len(pieces)}，向量 {len(vectors)}")
    records: list[VectorChunkRecord] = []
    cursor = 0
    for chapter in chapters:
        for index, piece in enumerate(chapter["pieces"], start=1):
            vector = vectors[cursor]
            cursor += 1
            if len(vector) != EMBEDDING_DIM:
                raise RuntimeError(
                    f"向量维度错误：chapter {chapter['chapter_id']} 第 {index} 片为 {len(vector)}"
                )
            records.append(
                VectorChunkRecord(
                    chunk_id=f"ch_{chapter['chapter_id']}_ck_{index}",
                    chapter_id=chapter["chapter_id"],
                    chapter_sort_order=chapter["sort_order"],
                    scene_id=chapter["scene_id"],
                    character_ids=chapter["character_ids"],
                    location_id=chapter["location_id"],
                    story_time=chapter["story_time"],
                    embedding_model_id=EMBEDDING_MODEL_ID,
                    text=piece,
                    vector=vector,
                    source_hash=chapter["content_hash"] or text_sha256(chapter["content"]),
                    embedding_dim=EMBEDDING_DIM,
                    embedding_version=EMBEDDING_VERSION,
                )
            )
    return records


def _validate_store(store: NovelVectorStore, expected_count: int) -> tuple[int, list[int]]:
    records = store._load_all()  # read-only validation of the file just written
    dims = sorted({len(record.vector) for record in records})
    bad_meta = [
        record.chunk_id
        for record in records
        if record.embedding_model_id != EMBEDDING_MODEL_ID
        or record.embedding_version != EMBEDDING_VERSION
        or record.embedding_dim != EMBEDDING_DIM
    ]
    if len(records) != expected_count:
        raise RuntimeError(f"校验失败：期望 {expected_count} 条，实际 {len(records)} 条")
    if dims != [EMBEDDING_DIM]:
        raise RuntimeError(f"校验失败：向量维度为 {dims}，期望 [{EMBEDDING_DIM}]")
    if bad_meta:
        raise RuntimeError(f"校验失败：{len(bad_meta)} 条元数据不是当前模型")
    return len(records), dims


def _backup_store(store: NovelVectorStore, timestamp: str) -> Path | None:
    if not store.store_file.exists():
        return None
    cfg = get_config()
    target_dir = cfg.data_dir / "_loop_backups" / f"embedding_{timestamp}" / store.novel_uid
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "chunks.json"
    target.write_bytes(store.store_file.read_bytes())
    return target


def _print_dry_run(store: NovelVectorStore, chapters: list[dict]) -> int:
    total = sum(len(chapter["pieces"]) for chapter in chapters)
    existing = store._load_all() if store.store_file.exists() else []
    dims = sorted({len(record.vector) for record in existing})
    print(f"  现有向量：{len(existing)} 条，维度 {dims or '无'}")
    print(f"  已定稿章节：{len(chapters)} 章，切片 {total} 条")
    for chapter in chapters:
        print(
            f"    - 第 #{chapter['chapter_id']} 章 "
            f"(sort={chapter['sort_order']:g})：{len(chapter['pieces'])} 片"
        )
    return total


def _print_comparison(chapters: list[dict], queries: list[str]) -> None:
    """Old hash-space top3 vs new ONNX-space top3. Read-only; model required."""
    runtime = get_embedding_runtime_status()
    # Keep old and new sides in the same scope: the first novel that has
    # finalized chapters. Mixing novels would compare unrelated chunks.
    novel_uid = chapters[0]["_novel_uid"]
    scoped = [c for c in chapters if c["_novel_uid"] == novel_uid]
    store = NovelVectorStore(novel_uid)
    existing = store._load_all() if store.store_file.exists() else []
    legacy = [r for r in existing if r.embedding_dim == LEGACY_EMBEDDING_DIM]
    print(
        f"\n[对比] 作品 {novel_uid} 查询 top3"
        "（旧 256 维哈希 / 新 1024 维 bge-m3）"
    )
    if not runtime.ready:
        print(f"  新编码不可用，只展示旧编码：{runtime.error}")
    all_pieces = [
        (chapter["chapter_id"], piece)
        for chapter in scoped
        for piece in chapter["pieces"]
    ]
    new_vectors: list[list[float]] | None = None
    if runtime.ready:
        new_vectors = encode_texts_sync([piece for _, piece in all_pieces])
    for query in queries:
        print(f"  查询「{query}」")
        old_q = encode_text_legacy_hash_sync(query)
        old_scored = sorted(
            (
                (sum(a * b for a, b in zip(old_q, record.vector)), record)
                for record in legacy
            ),
            key=lambda item: item[0],
            reverse=True,
        )[:3]
        for score, record in old_scored:
            print(f"    旧 #{record.chapter_id} {score:.4f} {record.text[:60]}")
        if new_vectors is None:
            print("    新：不可用（模型缺失）")
            continue
        new_q = encode_texts_sync([query])[0]
        new_scored = sorted(
            (
                (
                    sum(a * b for a, b in zip(new_q, vector)),
                    chapter_id,
                    piece,
                )
                for (chapter_id, piece), vector in zip(all_pieces, new_vectors)
            ),
            key=lambda item: item[0],
            reverse=True,
        )[:3]
        for score, chapter_id, piece in new_scored:
            print(f"    新 #{chapter_id} {score:.4f} {piece[:60]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--novel-uid", help="只处理指定作品；默认处理 data/ 下所有作品")
    parser.add_argument("--apply", action="store_true", help="写入重建结果（默认只读演练）")
    parser.add_argument(
        "--compare-query",
        action="append",
        default=[],
        help="对比旧/新编码的 top3（可重复；只读，需要真实模型）",
    )
    args = parser.parse_args()

    runtime = get_embedding_runtime_status()
    print(
        f"Embedding 模型：{runtime.model_id} {runtime.dimension} 维 "
        f"version={runtime.version} ready={runtime.ready}"
    )
    if runtime.error:
        print(f"模型状态错误：{runtime.error}")
    if args.apply and not runtime.ready:
        raise SystemExit("模型不可用，已拒绝 --apply，未写入任何文件。")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_chapters: list[dict] = []
    for novel_dir in _discover_novels(args.novel_uid):
        print(f"\n作品：{novel_dir.name}")
        conn = _open_ro(novel_dir / "novel.db")
        try:
            chapters = _finalized_chapters(conn)
        finally:
            conn.close()
        for chapter in chapters:
            chapter["_novel_uid"] = novel_dir.name
        all_chapters.extend(chapters)
        store = NovelVectorStore(novel_dir.name)
        expected = _print_dry_run(store, chapters)
        if not args.apply or expected == 0:
            continue

        backup = _backup_store(store, timestamp)
        print(f"  备份：{backup if backup else '（无旧索引，跳过备份）'}")
        try:
            records = _build_records(chapters)
            store.replace_all_chunks(records)
            count, dims = _validate_store(store, expected)
            print(f"  写入并校验通过：{count} 条，维度 {dims}")
        except Exception as exc:
            if backup and backup.exists():
                store.store_file.parent.mkdir(parents=True, exist_ok=True)
                store.store_file.write_bytes(backup.read_bytes())
                print(f"  失败，已从备份恢复：{exc}")
            else:
                print(f"  失败，且没有可恢复的备份：{exc}")
            raise

    if args.compare_query:
        if not all_chapters:
            print("没有可对比的已定稿章节。")
            return
        _print_comparison(all_chapters, args.compare_query)


if __name__ == "__main__":
    main()
