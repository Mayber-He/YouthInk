"""Repository for Scenes, Chapter Versions, Word Count calculation, and Export (M3)."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Literal

from app.core.exceptions import AppError
from app.core.text_hash import text_sha256
from app.db.repositories.outline_repo import OutlineRepository
from app.schemas.writing import (
    ChapterVersionResponse,
    ChapterWorkspaceResponse,
    SceneCreate,
    SceneResponse,
    SceneUpdate,
)

_WHITESPACE_RE = re.compile(r"\s+")


def count_novel_words(text: str) -> int:
    """Count non-whitespace characters in Chinese novel prose."""
    if not text:
        return 0
    return len(_WHITESPACE_RE.sub("", text))


def sanitize_filename(name: str) -> str:
    """Strip illegal filename characters for cross-platform compatibility."""
    cleaned = re.sub(r'[\\/*?:"<>|]+', "_", name).strip()
    return cleaned or "未命名"


class WritingRepository:
    """Data access layer for scenes, chapter_versions, and manuscript export."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._outline_repo = OutlineRepository(conn)

    # --- Scenes ---

    def list_scenes(self, chapter_id: int) -> list[SceneResponse]:
        rows = self._conn.execute(
            "SELECT * FROM scenes WHERE chapter_id = ? ORDER BY sort_order ASC, id ASC",
            (chapter_id,),
        ).fetchall()
        return [self._row_to_scene(r) for r in rows]

    def get_scene(self, scene_id: int) -> SceneResponse:
        row = self._conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,)).fetchone()
        if not row:
            raise AppError("SCENE_NOT_FOUND", f"未找到场景节拍 (id={scene_id})", status_code=404)
        return self._row_to_scene(row)

    def create_scene(self, chapter_id: int, payload: SceneCreate) -> SceneResponse:
        ch = self._outline_repo.get_chapter(chapter_id)
        max_sort = float(
            self._conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0.0) FROM scenes WHERE chapter_id = ?",
                (chapter_id,),
            ).fetchone()[0]
        )
        sort_order = payload.sort_order if payload.sort_order is not None else max_sort + 1.0
        cur = self._conn.execute(
            """
            INSERT INTO scenes (
                chapter_id, sort_order, beat, pov_character, location_id,
                character_ids, story_time, target_words
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chapter_id,
                sort_order,
                payload.beat.strip(),
                payload.pov_character,
                payload.location_id,
                json.dumps(payload.character_ids),
                payload.story_time,
                payload.target_words,
            ),
        )
        if ch.status == "pending":
            self._conn.execute(
                "UPDATE chapters SET status = 'outline' WHERE id = ?", (chapter_id,)
            )
        return self.get_scene(int(cur.lastrowid))

    def update_scene(self, scene_id: int, payload: SceneUpdate) -> SceneResponse:
        current = self.get_scene(scene_id)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return current
        if "character_ids" in updates:
            updates["character_ids"] = json.dumps(updates["character_ids"])
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [scene_id]
        self._conn.execute(f"UPDATE scenes SET {set_clause} WHERE id = ?", values)
        return self.get_scene(scene_id)

    def delete_scene(self, scene_id: int) -> None:
        self._conn.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))

    def replace_chapter_scenes(
        self, chapter_id: int, scenes_to_insert: list[SceneCreate]
    ) -> list[SceneResponse]:
        self._outline_repo.get_chapter(chapter_id)
        self._conn.execute("DELETE FROM scenes WHERE chapter_id = ?", (chapter_id,))
        for item in scenes_to_insert:
            self.create_scene(chapter_id, item)
        return self.list_scenes(chapter_id)

    # --- Chapter Versions & Workspace ---

    def list_versions(self, chapter_id: int) -> list[ChapterVersionResponse]:
        rows = self._conn.execute(
            "SELECT * FROM chapter_versions WHERE chapter_id = ? ORDER BY version DESC, id DESC",
            (chapter_id,),
        ).fetchall()
        return [self._row_to_version(r) for r in rows]

    def get_chapter_workspace(self, chapter_id: int) -> ChapterWorkspaceResponse:
        ch = self._outline_repo.get_chapter(chapter_id)
        scenes = self.list_scenes(chapter_id)
        versions = self.list_versions(chapter_id)
        latest_content = versions[0].content if versions else ""
        latest_ver = versions[0].version if versions else 0
        return ChapterWorkspaceResponse(
            chapter=ch,
            latest_content=latest_content,
            latest_version=latest_ver,
            scenes=scenes,
            versions=versions,
        )

    def save_chapter_content(
        self,
        chapter_id: int,
        content: str,
        source: Literal["ai", "manual"] = "manual",
        create_new_version: bool = False,
    ) -> ChapterWorkspaceResponse:
        """
        Save chapter content and update word_count.
        If create_new_version is True or no version exists or source changed, insert a new version row;
        otherwise update the latest version row in-place for smooth auto-save.
        Note: If chapter was 'final', editing marks its summary as stale and moves status back to 'draft'.
        """
        ch = self._outline_repo.get_chapter(chapter_id)
        latest_row = self._conn.execute(
            "SELECT * FROM chapter_versions WHERE chapter_id = ? ORDER BY version DESC LIMIT 1",
            (chapter_id,),
        ).fetchone()
        content_changed = latest_row is None or str(latest_row["content"]) != content
        content_hash = text_sha256(content)

        if latest_row is None or create_new_version or latest_row["source"] != source:
            next_ver = (int(latest_row["version"]) + 1) if latest_row else 1
            self._conn.execute(
                """
                INSERT INTO chapter_versions (chapter_id, version, content, source)
                VALUES (?, ?, ?, ?)
                """,
                (chapter_id, next_ver, content, source),
            )
        else:
            self._conn.execute(
                """
                UPDATE chapter_versions
                SET content = ?, created_at = datetime('now')
                WHERE id = ?
                """,
                (content, int(latest_row["id"])),
            )

        words = count_novel_words(content)
        next_status = ch.status
        if words > 0 and ch.status in ("pending", "outline"):
            next_status = "draft"
        elif ch.status == "final" and content_changed:
            next_status = "draft"

        if content_changed:
            self._invalidate_chapter_memory(chapter_id, ch.sort_order, ch.arc_id)

        self._conn.execute(
            "UPDATE chapters SET word_count = ?, status = ?, content_hash = ? WHERE id = ?",
            (words, next_status, content_hash, chapter_id),
        )
        return self.get_chapter_workspace(chapter_id)

    def _invalidate_chapter_memory(
        self, chapter_id: int, sort_order: float, arc_id: int
    ) -> None:
        prior_dirty = self._conn.execute(
            "SELECT continuity_dirty_from_chapter_id FROM chapters "
            "WHERE sort_order <= ? AND continuity_review_required = 1 "
            "ORDER BY sort_order, id LIMIT 1",
            (sort_order,),
        ).fetchone()
        dirty_from_id = int(prior_dirty[0]) if prior_dirty and prior_dirty[0] else chapter_id
        self._conn.execute(
            """UPDATE chapters SET continuity_review_required = 1,
                   continuity_dirty_from_chapter_id = ?
               WHERE sort_order >= ? AND (word_count > 0 OR status = 'final')""",
            (dirty_from_id, sort_order),
        )
        volume = self._conn.execute(
            "SELECT volume_id FROM arcs WHERE id = ?", (arc_id,)
        ).fetchone()
        self._conn.execute(
            """UPDATE summaries SET is_stale = 1
               WHERE (level = 'chapter' AND ref_id = ?)
                  OR (level = 'arc' AND ref_id = ?)
                  OR (level = 'volume' AND ref_id = ?)
                  OR level = 'novel'""",
            (chapter_id, arc_id, int(volume[0]) if volume else -1),
        )
        for table, chapter_column in (
            ("facts", "chapter_id"),
            ("character_state_changes", "chapter_id"),
            ("cognitive_records", "chapter_id"),
            ("relationship_changes", "chapter_id"),
            ("foreshadowing", "planted_chapter_id"),
            ("constraint_checks", "chapter_id"),
        ):
            self._conn.execute(
                f"UPDATE {table} SET is_stale = 1 WHERE {chapter_column} = ? AND origin != 'manual'",
                (chapter_id,),
            )

    def restore_chapter_version(
        self, chapter_id: int, version_num: int
    ) -> ChapterWorkspaceResponse:
        row = self._conn.execute(
            "SELECT * FROM chapter_versions WHERE chapter_id = ? AND version = ?",
            (chapter_id, version_num),
        ).fetchone()
        if not row:
            raise AppError(
                "VERSION_NOT_FOUND",
                f"未找到历史版本 v{version_num}",
                status_code=404,
            )
        return self.save_chapter_content(
            chapter_id,
            content=str(row["content"]),
            source="manual",
            create_new_version=True,
        )

    def get_previous_chapter_text(
        self, current_sort_order: float, tail_chars: int | None = 1500
    ) -> str:
        """Fetch the latest content of the immediately preceding chapter, optionally as a tail."""
        prev_ch = self._conn.execute(
            "SELECT id, title FROM chapters WHERE sort_order < ? ORDER BY sort_order DESC LIMIT 1",
            (current_sort_order,),
        ).fetchone()
        if not prev_ch:
            return ""
        ver = self._conn.execute(
            "SELECT content FROM chapter_versions WHERE chapter_id = ? ORDER BY version DESC LIMIT 1",
            (int(prev_ch["id"]),),
        ).fetchone()
        if not ver or not ver["content"]:
            return ""
        text = str(ver["content"]).strip()
        if tail_chars is not None and len(text) > tail_chars:
            text = "……\n" + text[-tail_chars:]
        label = "完整正文" if tail_chars is None else "结尾片段"
        return f"【上一章《{prev_ch['title']}》{label}】\n{text}"

    # --- Export (TXT / Markdown) ---

    def export_novel_manuscript(
        self, fmt: Literal["txt", "md"] = "md", chapter_id: int | None = None
    ) -> tuple[str, str]:
        """Export a single chapter or all chapters in sort_order as TXT or Markdown. Returns (filename, content)."""
        ext = "md" if fmt == "md" else "txt"

        if chapter_id is not None:
            ch = self._outline_repo.get_chapter(chapter_id)
            ver = self._conn.execute(
                "SELECT content FROM chapter_versions WHERE chapter_id = ? ORDER BY version DESC LIMIT 1",
                (ch.id,),
            ).fetchone()
            body = str(ver["content"]).strip() if ver and ver["content"] else "（本章尚未撰写正文）"
            header = f"第{ch.display_index}章 {ch.title}".strip()
            safe_name = sanitize_filename(header)
            filename = f"{safe_name}.{ext}"

            if fmt == "md":
                content = f"# {header}\n\n{body}\n"
            else:
                content = f"{header}\n\n{body}\n"
            return filename, content

        novel_row = self._conn.execute("SELECT title, synopsis FROM novels ORDER BY id ASC LIMIT 1").fetchone()
        title = str(novel_row["title"]) if novel_row else "未命名作品"
        safe_title = sanitize_filename(title)
        synopsis = str(novel_row["synopsis"] or "") if novel_row else ""

        tree = self._outline_repo.get_outline_tree()
        lines: list[str] = []
        if fmt == "md":
            lines.append(f"# 《{title}》\n")
            if synopsis:
                lines.append(f"> {synopsis}\n")
        else:
            lines.append(f"《{title}》\n")
            if synopsis:
                lines.append(f"简介：{synopsis}\n")
            lines.append("=" * 40 + "\n")

        for vol in tree.volumes:
            lines.append(f"\n## {vol.title}\n" if fmt == "md" else f"\n【{vol.title}】\n")
            for arc in vol.arcs:
                for ch in arc.chapters:
                    ver = self._conn.execute(
                        "SELECT content FROM chapter_versions WHERE chapter_id = ? ORDER BY version DESC LIMIT 1",
                        (ch.id,),
                    ).fetchone()
                    body = str(ver["content"]).strip() if ver and ver["content"] else "（本章尚未撰写正文）"
                    header = f"第{ch.display_index}章 {ch.title}"
                    if fmt == "md":
                        lines.append(f"\n### {header}\n\n{body}\n")
                    else:
                        lines.append(f"\n{header}\n\n{body}\n")

        return f"{safe_title}.{ext}", "\n".join(lines)

    @staticmethod
    def _row_to_scene(row: sqlite3.Row) -> SceneResponse:
        return SceneResponse(
            id=int(row["id"]),
            chapter_id=int(row["chapter_id"]),
            sort_order=float(row["sort_order"]),
            beat=str(row["beat"] or ""),
            pov_character=row["pov_character"],
            location_id=row["location_id"],
            character_ids=json.loads(row["character_ids"] or "[]"),
            story_time=str(row["story_time"] or ""),
            target_words=int(row["target_words"] or 800),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_version(row: sqlite3.Row) -> ChapterVersionResponse:
        content = str(row["content"] or "")
        return ChapterVersionResponse(
            id=int(row["id"]),
            chapter_id=int(row["chapter_id"]),
            version=int(row["version"]),
            content=content,
            source=row["source"],
            word_count=count_novel_words(content),
            created_at=str(row["created_at"]),
        )
