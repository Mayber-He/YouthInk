"""Embedded vector store manager for per-novel <novel_uid>/vectors/."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path

from app.core.config import get_config
from app.db.manager import validate_novel_uid
from app.services.embedding.encoder import (
    EMBEDDING_MODEL_ID,
    LEGACY_EMBEDDING_DIM,
    LEGACY_EMBEDDING_MODEL_ID,
    LEGACY_EMBEDDING_VERSION,
    cosine_similarity,
)


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
    # bge-m3 migration metadata. Older files only stored model id and vector;
    # missing values are inferred from the vector length as the legacy hash space.
    embedding_dim: int = 0
    embedding_version: str = ""


class NovelVectorStore:
    """Manages scene-level vector chunks in <novel_uid>/vectors/chunks.json."""

    def __init__(self, novel_uid: str) -> None:
        validate_novel_uid(novel_uid)
        self.novel_uid = novel_uid
        cfg = get_config()
        self.vectors_dir: Path = cfg.novel_vectors_dir(novel_uid)
        self.vectors_dir.mkdir(parents=True, exist_ok=True)
        self.store_file: Path = self.vectors_dir / "chunks.json"
        # Written when embedding/indexing fails so finalization can still
        # succeed while the UI reports "待重建" and the reason.
        self.index_status_file: Path = self.vectors_dir / "index_status.json"

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
                    vector = [float(v) for v in item.get("vector", [])]
                    dim = int(item.get("embedding_dim") or len(vector))
                    version = str(item.get("embedding_version") or "")
                    if not version and dim == LEGACY_EMBEDDING_DIM:
                        version = LEGACY_EMBEDDING_VERSION
                    model_id = str(item.get("embedding_model_id") or "")
                    if not model_id:
                        model_id = (
                            LEGACY_EMBEDDING_MODEL_ID
                            if dim == LEGACY_EMBEDDING_DIM
                            else EMBEDDING_MODEL_ID
                        )
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
                                item.get("embedding_model_id", EMBEDDING_MODEL_ID)
                            ),
                            text=str(item.get("text", "")),
                            vector=vector,
                            source_hash=str(item.get("source_hash", "")),
                            embedding_dim=dim,
                            embedding_version=version,
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

    def replace_all_chunks(self, records: list[VectorChunkRecord]) -> int:
        """Atomically replace the whole store (used by re-index after all encoding succeeded)."""
        if records:
            self._save_all(records)
        elif self.store_file.exists():
            self.store_file.unlink()
        return len(records)

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

    def read_index_status(self) -> dict[str, object]:
        """Return the pending-rebuild marker written after an indexing failure."""
        empty: dict[str, object] = {
            "pending_rebuild": False,
            "reason": "",
            "chapters": [],
            "updated_at": "",
        }
        if not self.index_status_file.exists():
            return empty
        try:
            raw = json.loads(self.index_status_file.read_text(encoding="utf-8"))
        except Exception:
            return {**empty, "pending_rebuild": True, "reason": "索引状态文件损坏"}
        if not isinstance(raw, dict):
            return {**empty, "pending_rebuild": True, "reason": "索引状态文件格式错误"}
        chapters = raw.get("chapters") or []
        try:
            chapter_ids = sorted({int(c) for c in chapters})
        except Exception:
            return {**empty, "pending_rebuild": True, "reason": "索引状态文件章节字段损坏"}
        return {
            "pending_rebuild": bool(raw.get("pending_rebuild")),
            "reason": str(raw.get("reason") or ""),
            "chapters": chapter_ids,
            "updated_at": str(raw.get("updated_at") or ""),
        }

    def mark_rebuild_pending(
        self, reason: str, chapter_ids: list[int] | None = None
    ) -> None:
        """Persist a pending marker; never raises into the finalization path."""
        status = self.read_index_status()
        chapters = set(status["chapters"])  # type: ignore[arg-type]
        chapters.update(int(c) for c in (chapter_ids or []))
        payload = {
            "pending_rebuild": True,
            "reason": reason,
            "chapters": sorted(chapters),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        tmp = self.index_status_file.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.index_status_file)
        except Exception:
            # The marker is diagnostic; failure to write it must not fail finalize.
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def clear_chapter_pending(self, chapter_id: int) -> None:
        status = self.read_index_status()
        if not status["pending_rebuild"]:
            return
        chapters = [c for c in status["chapters"] if int(c) != int(chapter_id)]  # type: ignore[union-attr]
        try:
            if chapters:
                payload = {
                    **status,
                    "chapters": chapters,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
                tmp = self.index_status_file.with_suffix(".tmp")
                tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                tmp.replace(self.index_status_file)
            else:
                self.index_status_file.unlink(missing_ok=True)
        except Exception:
            pass

    def clear_rebuild_pending(self) -> None:
        self.index_status_file.unlink(missing_ok=True)

    @staticmethod
    def is_compatible(
        record: VectorChunkRecord,
        expected_dim: int,
        expected_version: str,
        expected_model_id: str | None = None,
    ) -> bool:
        """A record may only be compared inside its own embedding space."""
        if record.embedding_dim != expected_dim:
            return False
        if record.embedding_version != expected_version:
            return False
        if expected_model_id is not None and record.embedding_model_id != expected_model_id:
            return False
        return True

    def incompatible_chapter_ids(
        self, expected_dim: int, expected_version: str, expected_model_id: str | None = None
    ) -> list[int]:
        return sorted(
            {
                r.chapter_id
                for r in self._load_all()
                if not self.is_compatible(r, expected_dim, expected_version, expected_model_id)
            }
        )

    def has_model_mismatch(self, current_model_id: str) -> bool:
        """Legacy check by model id; prefer ``has_incompatible`` for bge-m3 migration."""
        records = self._load_all()
        if not records:
            return False
        return any(r.embedding_model_id != current_model_id for r in records)

    def has_incompatible(
        self, expected_dim: int, expected_version: str, expected_model_id: str | None = None
    ) -> bool:
        return any(
            not self.is_compatible(r, expected_dim, expected_version, expected_model_id)
            for r in self._load_all()
        )

    def search_vectors(
        self,
        query_vec: list[float],
        max_chapter_sort: float | None = None,
        character_ids: list[int] | None = None,
        location_id: int | None = None,
        allowed_chapter_hashes: dict[int, str] | None = None,
        top_k: int = 8,
        expected_dim: int | None = None,
        expected_version: str | None = None,
        expected_model_id: str | None = None,
    ) -> list[tuple[VectorChunkRecord, float]]:
        """
        Metadata pre-filtering + cosine similarity ranking.
        Returns list of (record, similarity_score) sorted descending.
        """
        records = self._load_all()
        scored: list[tuple[VectorChunkRecord, float]] = []
        char_filter = set(character_ids) if character_ids else None

        for rec in records:
            if expected_dim is not None and expected_version is not None:
                if not self.is_compatible(rec, expected_dim, expected_version, expected_model_id):
                    continue
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
