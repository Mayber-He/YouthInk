"""Embedded vector store manager for per-novel <novel_uid>/vectors/."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from app.core.config import get_config
from app.db.manager import validate_novel_uid
from app.services.embedding.encoder import cosine_similarity


@dataclass
class VectorChunkRecord:
    chunk_id: str
    chapter_id: int
    chapter_sort_order: float
    scene_id: int | None
    character_ids: list[int]
    location_id: int | None
    story_time: str
    embedding_model_id: str
    text: str
    vector: list[float]
    source_hash: str = ""


class NovelVectorStore:
    """Manages scene-level vector chunks in <novel_uid>/vectors/chunks.json."""

    def __init__(self, novel_uid: str) -> None:
        validate_novel_uid(novel_uid)
        self.novel_uid = novel_uid
        cfg = get_config()
        self.vectors_dir: Path = cfg.novel_vectors_dir(novel_uid)
        self.vectors_dir.mkdir(parents=True, exist_ok=True)
        self.store_file: Path = self.vectors_dir / "chunks.json"

    def _load_all(self) -> list[VectorChunkRecord]:
        if not self.store_file.exists():
            return []
        try:
            raw_list = json.loads(self.store_file.read_text(encoding="utf-8"))
            if not isinstance(raw_list, list):
                return []
            records: list[VectorChunkRecord] = []
            for item in raw_list:
                if isinstance(item, dict):
                    records.append(
                        VectorChunkRecord(
                            chunk_id=str(item.get("chunk_id", "")),
                            chapter_id=int(item.get("chapter_id", 0)),
                            chapter_sort_order=float(item.get("chapter_sort_order", 0.0)),
                            scene_id=int(item["scene_id"])
                            if item.get("scene_id") is not None
                            else None,
                            character_ids=[int(x) for x in item.get("character_ids", [])],
                            location_id=int(item["location_id"])
                            if item.get("location_id") is not None
                            else None,
                            story_time=str(item.get("story_time", "")),
                            embedding_model_id=str(
                                item.get("embedding_model_id", "bge-m3-onnx-int8")
                            ),
                            text=str(item.get("text", "")),
                            vector=[float(v) for v in item.get("vector", [])],
                            source_hash=str(item.get("source_hash", "")),
                        )
                    )
            return records
        except Exception:
            return []

    def _save_all(self, records: list[VectorChunkRecord]) -> None:
        payload = [asdict(r) for r in records]
        tmp_path = self.store_file.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        tmp_path.replace(self.store_file)

    def upsert_chapter_chunks(
        self, chapter_id: int, new_chunks: list[VectorChunkRecord]
    ) -> int:
        """Replace all chunks belonging to `chapter_id` with `new_chunks`."""
        existing = [r for r in self._load_all() if r.chapter_id != chapter_id]
        existing.extend(new_chunks)
        self._save_all(existing)
        return len(new_chunks)

    def remove_chapter_chunks(self, chapter_ids: list[int]) -> int:
        """Remove stale chunks for deleted chapters while preserving other chapters."""
        ids = set(chapter_ids)
        if not ids:
            return 0
        records = self._load_all()
        retained = [record for record in records if record.chapter_id not in ids]
        removed_count = len(records) - len(retained)
        if removed_count:
            self._save_all(retained)
        return removed_count

    def clear_all_vectors(self) -> None:
        """Remove all stored vector chunks (used before full re-indexing)."""
        if self.store_file.exists():
            self.store_file.unlink()

    def has_model_mismatch(self, current_model_id: str) -> bool:
        """Check if any stored chunk uses a different embedding_model_id."""
        records = self._load_all()
        if not records:
            return False
        return any(r.embedding_model_id != current_model_id for r in records)

    def search_vectors(
        self,
        query_vec: list[float],
        max_chapter_sort: float | None = None,
        character_ids: list[int] | None = None,
        location_id: int | None = None,
        allowed_chapter_hashes: dict[int, str] | None = None,
        top_k: int = 8,
    ) -> list[tuple[VectorChunkRecord, float]]:
        """
        Metadata pre-filtering + cosine similarity ranking.
        Returns list of (record, similarity_score) sorted descending.
        """
        records = self._load_all()
        scored: list[tuple[VectorChunkRecord, float]] = []
        char_filter = set(character_ids) if character_ids else None

        for rec in records:
            if allowed_chapter_hashes is not None and (
                rec.chapter_id not in allowed_chapter_hashes
                or rec.source_hash != allowed_chapter_hashes[rec.chapter_id]
            ):
                continue
            if (
                max_chapter_sort is not None
                and rec.chapter_sort_order > max_chapter_sort
            ):
                continue
            if location_id is not None and rec.location_id != location_id:
                continue
            if char_filter:
                if not rec.character_ids or not char_filter.intersection(
                    rec.character_ids
                ):
                    continue
            sim = cosine_similarity(query_vec, rec.vector)
            scored.append((rec, sim))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]
