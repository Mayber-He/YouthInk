"""Repository for per-novel novel.db operations and novel directory management."""

from __future__ import annotations

import shutil
import sqlite3
import uuid

from app.core.config import get_config
from app.core.exceptions import AppError
from app.db.manager import get_novel_db, validate_novel_uid
from app.schemas.novel import NovelCreate, NovelDetail, NovelUpdate


def create_novel_project(payload: NovelCreate) -> NovelDetail:
    """Create a new <novel_uid>/novel.db directory and insert the novel initiation row."""
    novel_uid = f"novel_{uuid.uuid4().hex[:12]}"
    with get_novel_db(novel_uid, create_if_missing=True) as conn:
        repo = NovelRepository(conn, novel_uid)
        return repo.insert_novel(payload)


def list_all_novels() -> list[NovelDetail]:
    """Scan YOUTHINK_DATA_DIR for all valid <novel_uid>/novel.db projects."""
    cfg = get_config()
    results: list[NovelDetail] = []
    if not cfg.data_dir.exists():
        return results
    for sub in sorted(cfg.data_dir.iterdir()):
        if not sub.is_dir() or sub.name == "models":
            continue
        db_file = sub / "novel.db"
        if not db_file.exists():
            continue
        try:
            with get_novel_db(sub.name) as conn:
                repo = NovelRepository(conn, sub.name)
                results.append(repo.get_novel_detail())
        except Exception:
            continue
    results.sort(key=lambda item: item.updated_at, reverse=True)
    return results


def delete_novel_project(novel_uid: str) -> None:
    """Delete the entire <novel_uid> directory."""
    validate_novel_uid(novel_uid)
    cfg = get_config()
    target = cfg.novel_dir(novel_uid)
    if not target.exists():
        raise AppError("NOVEL_NOT_FOUND", f"作品不存在: {novel_uid}", status_code=404)
    shutil.rmtree(target)


class NovelRepository:
    """Data access methods operating on a single <novel_uid>/novel.db connection."""

    def __init__(self, conn: sqlite3.Connection, novel_uid: str) -> None:
        self._conn = conn
        self._novel_uid = novel_uid

    def insert_novel(self, payload: NovelCreate) -> NovelDetail:
        cur = self._conn.execute(
            """
            INSERT INTO novels (
                title, genre, tone, pov, protagonist_concept, synopsis,
                target_words, estimated_chapters, words_per_chapter,
                romance_ending, growth_ending, ending_note, style_note, style_template_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.title.strip(),
                payload.genre,
                payload.tone,
                payload.pov,
                payload.protagonist_concept,
                payload.synopsis,
                payload.target_words,
                payload.estimated_chapters,
                payload.words_per_chapter,
                payload.romance_ending,
                payload.growth_ending,
                payload.ending_note,
                payload.style_note,
                payload.style_template_id,
            ),
        )
        novel_id = int(cur.lastrowid)
        # Initialize empty main_plots row for this novel
        self._conn.execute(
            "INSERT OR IGNORE INTO main_plots (novel_id, key_turning_pts) VALUES (?, '[]')",
            (novel_id,),
        )
        return self.get_novel_detail()

    def get_novel_detail(self) -> NovelDetail:
        row = self._conn.execute("SELECT * FROM novels ORDER BY id ASC LIMIT 1").fetchone()
        if not row:
            raise AppError("NOVEL_EMPTY", f"作品库为空: {self._novel_uid}", status_code=404)

        ch_stats = self._conn.execute(
            """
            SELECT
                COUNT(*) AS total_chapters,
                COALESCE(SUM(CASE WHEN status = 'final' THEN 1 ELSE 0 END), 0) AS finalized_chapters,
                COALESCE(SUM(word_count), 0) AS current_words
            FROM chapters
            """
        ).fetchone()

        pending_cnt = self._count_pending_confirmations()

        return NovelDetail(
            novel_uid=self._novel_uid,
            id=int(row["id"]),
            title=str(row["title"]),
            genre=row["genre"],
            tone=row["tone"],
            pov=row["pov"],
            protagonist_concept=row["protagonist_concept"],
            synopsis=row["synopsis"],
            target_words=int(row["target_words"] or 1000000),
            estimated_chapters=row["estimated_chapters"],
            words_per_chapter=int(row["words_per_chapter"] or 2500),
            romance_ending=row["romance_ending"],
            growth_ending=row["growth_ending"],
            ending_note=row["ending_note"],
            style_note=row["style_note"],
            style_template_id=row["style_template_id"],
            total_chapters=int(ch_stats["total_chapters"] or 0),
            finalized_chapters=int(ch_stats["finalized_chapters"] or 0),
            current_words=int(ch_stats["current_words"] or 0),
            pending_confirm_count=pending_cnt,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def update_novel(self, payload: NovelUpdate) -> NovelDetail:
        current = self.get_novel_detail()
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return current
        set_clause = ", ".join(f"{col} = ?" for col in updates.keys())
        values = list(updates.values()) + [current.id]
        self._conn.execute(f"UPDATE novels SET {set_clause} WHERE id = ?", values)
        return self.get_novel_detail()

    def record_generation_log(
        self,
        *,
        task_type: str,
        model: str,
        prompt: str,
        output: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        elapsed_ms: int = 0,
        template_id: str | None = None,
        template_ver: str | None = None,
        chapter_id: int | None = None,
        scene_id: int | None = None,
        temperature: float | None = None,
        finish_reason: str | None = None,
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO generation_logs (
                task_type, model, template_id, template_ver, prompt, output,
                input_tokens, output_tokens, elapsed_ms, chapter_id, scene_id,
                temperature, finish_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_type,
                model,
                template_id,
                template_ver,
                prompt,
                output,
                input_tokens,
                output_tokens,
                elapsed_ms,
                chapter_id,
                scene_id,
                temperature,
                finish_reason,
            ),
        )
        return int(cur.lastrowid)

    def _count_pending_confirmations(self) -> int:
        queries = [
            "SELECT COUNT(*) FROM facts WHERE status = 'pending' AND is_stale = 0",
            "SELECT COUNT(*) FROM character_state_changes WHERE confirm_status = 'pending' AND is_stale = 0",
            "SELECT COUNT(*) FROM cognitive_records WHERE confirm_status = 'pending' AND is_stale = 0",
            "SELECT COUNT(*) FROM relationship_changes WHERE confirm_status = 'pending' AND is_stale = 0",
            "SELECT COUNT(*) FROM foreshadowing WHERE confirm_status = 'pending' AND is_stale = 0",
            "SELECT COUNT(*) FROM constraint_checks WHERE confirm_status = 'pending' AND is_stale = 0",
        ]
        total = 0
        for q in queries:
            total += int(self._conn.execute(q).fetchone()[0])
        return total
