"""Repository for Volumes, Arcs, and Chapters with floating-point sort_order (Dev Doc 4.3)."""

from __future__ import annotations

import sqlite3

from app.core.exceptions import AppError
from app.schemas.outline import (
    ArcCreate,
    ArcResponse,
    ArcTreeNode,
    ArcUpdate,
    ChapterCreate,
    ChapterResponse,
    ChapterUpdate,
    LlmChapterPlanItem,
    LlmVolumePlanItem,
    OutlineTreeResponse,
    VolumeCreate,
    VolumeResponse,
    VolumeTreeNode,
    VolumeUpdate,
)


def compute_float_sort_order(
    prev_sort: float | None, next_sort: float | None, default_max: float = 0.0
) -> float:
    """Calculate midpoint float sort_order for insertion or reordering (Dev Doc 4.3)."""
    if prev_sort is not None and next_sort is not None:
        return (prev_sort + next_sort) / 2.0
    if prev_sort is not None:
        return prev_sort + 1.0
    if next_sort is not None:
        return next_sort / 2.0 if next_sort > 0 else next_sort - 1.0
    return default_max + 1.0


class OutlineRepository:
    """Data access layer for volumes, arcs, and chapters in novel.db."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _get_novel_id(self) -> int:
        row = self._conn.execute("SELECT id FROM novels ORDER BY id ASC LIMIT 1").fetchone()
        if not row:
            raise AppError("NOVEL_EMPTY", "作品未初始化", status_code=404)
        return int(row["id"])

    # --- Full Outline Tree ---

    def get_outline_tree(self) -> OutlineTreeResponse:
        vol_rows = self._conn.execute(
            "SELECT * FROM volumes ORDER BY sort_order ASC, id ASC"
        ).fetchall()
        arc_rows = self._conn.execute(
            "SELECT * FROM arcs ORDER BY sort_order ASC, id ASC"
        ).fetchall()
        ch_rows = self._conn.execute(
            "SELECT * FROM chapters ORDER BY sort_order ASC, id ASC"
        ).fetchall()

        # Assign sequential display_index across the entire novel (decoupled from sort_order/id)
        chapters_by_arc: dict[int, list[ChapterResponse]] = {}
        for idx, r in enumerate(ch_rows, start=1):
            ch = self._row_to_chapter(r, display_index=idx)
            chapters_by_arc.setdefault(ch.arc_id, []).append(ch)

        arcs_by_vol: dict[int, list[ArcTreeNode]] = {}
        for r in arc_rows:
            arc = self._row_to_arc(r)
            node = ArcTreeNode(**arc.model_dump(), chapters=chapters_by_arc.get(arc.id, []))
            arcs_by_vol.setdefault(arc.volume_id, []).append(node)

        volumes: list[VolumeTreeNode] = []
        for r in vol_rows:
            vol = self._row_to_volume(r)
            volumes.append(VolumeTreeNode(**vol.model_dump(), arcs=arcs_by_vol.get(vol.id, [])))

        return OutlineTreeResponse(volumes=volumes, total_chapters=len(ch_rows))

    # --- Volumes ---

    def create_volume(self, payload: VolumeCreate) -> VolumeResponse:
        novel_id = self._get_novel_id()
        max_sort = float(
            self._conn.execute("SELECT COALESCE(MAX(sort_order), 0.0) FROM volumes").fetchone()[0]
        )
        sort_order = payload.sort_order if payload.sort_order is not None else max_sort + 1.0
        cur = self._conn.execute(
            "INSERT INTO volumes (novel_id, sort_order, title, synopsis, goal) VALUES (?, ?, ?, ?, ?)",
            (novel_id, sort_order, payload.title.strip(), payload.synopsis, payload.goal),
        )
        return self.get_volume(int(cur.lastrowid))

    def get_volume(self, vol_id: int) -> VolumeResponse:
        row = self._conn.execute("SELECT * FROM volumes WHERE id = ?", (vol_id,)).fetchone()
        if not row:
            raise AppError("VOLUME_NOT_FOUND", f"未找到分卷 (id={vol_id})", status_code=404)
        return self._row_to_volume(row)

    def update_volume(self, vol_id: int, payload: VolumeUpdate) -> VolumeResponse:
        current = self.get_volume(vol_id)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return current
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [vol_id]
        self._conn.execute(
            f"UPDATE volumes SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        return self.get_volume(vol_id)

    def delete_volume(self, vol_id: int) -> None:
        self._conn.execute("DELETE FROM volumes WHERE id = ?", (vol_id,))

    # --- Arcs ---

    def create_arc(self, payload: ArcCreate) -> ArcResponse:
        self.get_volume(payload.volume_id)
        max_sort = float(
            self._conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0.0) FROM arcs WHERE volume_id = ?",
                (payload.volume_id,),
            ).fetchone()[0]
        )
        sort_order = payload.sort_order if payload.sort_order is not None else max_sort + 1.0
        cur = self._conn.execute(
            """
            INSERT INTO arcs (volume_id, sort_order, title, goal, core_conflict, start_chapter, end_chapter)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.volume_id,
                sort_order,
                payload.title.strip(),
                payload.goal,
                payload.core_conflict,
                payload.start_chapter,
                payload.end_chapter,
            ),
        )
        return self.get_arc(int(cur.lastrowid))

    def get_arc(self, arc_id: int) -> ArcResponse:
        row = self._conn.execute("SELECT * FROM arcs WHERE id = ?", (arc_id,)).fetchone()
        if not row:
            raise AppError("ARC_NOT_FOUND", f"未找到情节弧 (id={arc_id})", status_code=404)
        return self._row_to_arc(row)

    def update_arc(self, arc_id: int, payload: ArcUpdate) -> ArcResponse:
        current = self.get_arc(arc_id)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return current
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [arc_id]
        self._conn.execute(
            f"UPDATE arcs SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        return self.get_arc(arc_id)

    def delete_arc(self, arc_id: int) -> None:
        self._conn.execute("DELETE FROM arcs WHERE id = ?", (arc_id,))

    # --- Chapters ---

    def create_chapter(self, payload: ChapterCreate) -> ChapterResponse:
        self.get_arc(payload.arc_id)
        if payload.sort_order is not None:
            sort_order = payload.sort_order
        elif payload.after_chapter_id is not None or payload.before_chapter_id is not None:
            prev_s = (
                self.get_chapter(payload.after_chapter_id).sort_order
                if payload.after_chapter_id
                else None
            )
            next_s = (
                self.get_chapter(payload.before_chapter_id).sort_order
                if payload.before_chapter_id
                else None
            )
            sort_order = compute_float_sort_order(prev_s, next_s)
        else:
            max_sort = float(
                self._conn.execute("SELECT COALESCE(MAX(sort_order), 0.0) FROM chapters").fetchone()[0]
            )
            sort_order = max_sort + 1.0

        cur = self._conn.execute(
            """
            INSERT INTO chapters (arc_id, sort_order, title, synopsis, story_time, locked)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.arc_id,
                sort_order,
                payload.title.strip(),
                payload.synopsis,
                payload.story_time,
                int(payload.locked),
            ),
        )
        return self.get_chapter(int(cur.lastrowid))

    def get_chapter(self, chapter_id: int) -> ChapterResponse:
        row = self._conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
        if not row:
            raise AppError("CHAPTER_NOT_FOUND", f"未找到章节 (id={chapter_id})", status_code=404)
        rank = int(
            self._conn.execute(
                "SELECT COUNT(*) FROM chapters WHERE sort_order < ? OR (sort_order = ? AND id <= ?)",
                (row["sort_order"], row["sort_order"], row["id"]),
            ).fetchone()[0]
        )
        return self._row_to_chapter(row, display_index=max(1, rank))

    def update_chapter(self, chapter_id: int, payload: ChapterUpdate) -> ChapterResponse:
        current = self.get_chapter(chapter_id)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return current
        if "locked" in updates:
            updates["locked"] = int(bool(updates["locked"]))
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [chapter_id]
        self._conn.execute(f"UPDATE chapters SET {set_clause} WHERE id = ?", values)
        return self.get_chapter(chapter_id)

    def reorder_chapter(
        self, chapter_id: int, prev_sort: float | None, next_sort: float | None
    ) -> ChapterResponse:
        new_sort = compute_float_sort_order(prev_sort, next_sort)
        return self.update_chapter(chapter_id, ChapterUpdate(sort_order=new_sort))

    def delete_chapter(self, chapter_id: int) -> None:
        self._conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))

    # --- AI Batch Structure & Rolling Arc Chapters ---

    def apply_generated_structure(self, volumes_plan: list[LlmVolumePlanItem]) -> OutlineTreeResponse:
        """Create volumes and arcs from AI plan (preserving any volumes that contain locked chapters)."""
        for v_item in volumes_plan:
            vol = self.create_volume(
                VolumeCreate(title=v_item.title, synopsis=v_item.synopsis, goal=v_item.goal)
            )
            for a_item in v_item.arcs:
                self.create_arc(
                    ArcCreate(
                        volume_id=vol.id,
                        title=a_item.title,
                        goal=a_item.goal,
                        core_conflict=a_item.core_conflict,
                        start_chapter=a_item.start_chapter,
                        end_chapter=a_item.end_chapter,
                    )
                )
        return self.get_outline_tree()

    def replace_unlocked_arc_chapters(
        self, arc_id: int, chapters_plan: list[LlmChapterPlanItem]
    ) -> OutlineTreeResponse:
        """Delete unlocked pending/outline chapters in arc_id and insert newly generated chapters."""
        self.get_arc(arc_id)
        self._conn.execute(
            "DELETE FROM chapters WHERE arc_id = ? AND locked = 0 AND status IN ('pending', 'outline')",
            (arc_id,),
        )
        for ch_item in chapters_plan:
            self.create_chapter(
                ChapterCreate(
                    arc_id=arc_id,
                    title=ch_item.title,
                    synopsis=ch_item.synopsis,
                    story_time=ch_item.story_time,
                    locked=False,
                )
            )
        return self.get_outline_tree()

    @staticmethod
    def _row_to_volume(row: sqlite3.Row) -> VolumeResponse:
        return VolumeResponse(
            id=int(row["id"]),
            novel_id=int(row["novel_id"]),
            sort_order=float(row["sort_order"]),
            title=str(row["title"]),
            synopsis=str(row["synopsis"] or ""),
            goal=str(row["goal"] or ""),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_arc(row: sqlite3.Row) -> ArcResponse:
        return ArcResponse(
            id=int(row["id"]),
            volume_id=int(row["volume_id"]),
            sort_order=float(row["sort_order"]),
            title=str(row["title"]),
            goal=str(row["goal"] or ""),
            core_conflict=str(row["core_conflict"] or ""),
            start_chapter=row["start_chapter"],
            end_chapter=row["end_chapter"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_chapter(row: sqlite3.Row, display_index: int = 1) -> ChapterResponse:
        return ChapterResponse(
            id=int(row["id"]),
            arc_id=int(row["arc_id"]),
            sort_order=float(row["sort_order"]),
            display_index=display_index,
            title=str(row["title"] or ""),
            synopsis=str(row["synopsis"] or ""),
            status=row["status"],
            word_count=int(row["word_count"] or 0),
            story_time=str(row["story_time"] or ""),
            locked=bool(row["locked"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
