"""Repository for Worldview, Characters, Locations, and Main Plot."""

from __future__ import annotations

import json
import sqlite3

from app.core.exceptions import AppError
from app.db.repositories.timeline_repo import build_character_timeline_snapshot
from app.schemas.entities import (
    CharacterCreate,
    CharacterResponse,
    CharacterTimelineSnapshot,
    CharacterUpdate,
    LlmCharacterItem,
    LlmLocationItem,
    LlmMainPlotOutput,
    LlmWorldviewItem,
    LocationCreate,
    LocationResponse,
    LocationUpdate,
    MainPlotResponse,
    MainPlotUpdate,
    TurningPointItem,
    WorldviewCreate,
    WorldviewResponse,
    WorldviewUpdate,
)


class EntityRepository:
    """Data access layer for novel setting entities in novel.db."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # --- Worldview ---

    def list_worldview(self) -> list[WorldviewResponse]:
        rows = self._conn.execute("SELECT * FROM worldview_entries ORDER BY id ASC").fetchall()
        return [self._row_to_worldview(r) for r in rows]

    def get_worldview(self, entry_id: int) -> WorldviewResponse:
        row = self._conn.execute("SELECT * FROM worldview_entries WHERE id = ?", (entry_id,)).fetchone()
        if not row:
            raise AppError("WORLDVIEW_NOT_FOUND", f"未找到世界观条目 (id={entry_id})", status_code=404)
        return self._row_to_worldview(row)

    def create_worldview(self, payload: WorldviewCreate) -> WorldviewResponse:
        cur = self._conn.execute(
            "INSERT INTO worldview_entries (category, content, locked) VALUES (?, ?, ?)",
            (payload.category, payload.content.strip(), int(payload.locked)),
        )
        return self.get_worldview(int(cur.lastrowid))

    def update_worldview(self, entry_id: int, payload: WorldviewUpdate) -> WorldviewResponse:
        current = self.get_worldview(entry_id)
        cat = payload.category if payload.category is not None else current.category
        content = payload.content.strip() if payload.content is not None else current.content
        locked = int(payload.locked) if payload.locked is not None else int(current.locked)
        self._conn.execute(
            "UPDATE worldview_entries SET category = ?, content = ?, locked = ?, updated_at = datetime('now') WHERE id = ?",
            (cat, content, locked, entry_id),
        )
        return self.get_worldview(entry_id)

    def delete_worldview(self, entry_id: int) -> None:
        self._conn.execute("DELETE FROM worldview_entries WHERE id = ?", (entry_id,))

    def replace_unlocked_worldview(self, items: list[LlmWorldviewItem]) -> list[WorldviewResponse]:
        self._conn.execute("DELETE FROM worldview_entries WHERE locked = 0")
        for item in items:
            self._conn.execute(
                "INSERT INTO worldview_entries (category, content, locked) VALUES (?, ?, 0)",
                (item.category, item.content.strip()),
            )
        return self.list_worldview()

    # --- Characters ---

    def list_characters(self) -> list[CharacterResponse]:
        rows = self._conn.execute("SELECT * FROM characters ORDER BY id ASC").fetchall()
        return [self._row_to_character(r) for r in rows]

    def get_character(self, char_id: int) -> CharacterResponse:
        row = self._conn.execute("SELECT * FROM characters WHERE id = ?", (char_id,)).fetchone()
        if not row:
            raise AppError("CHARACTER_NOT_FOUND", f"未找到人物卡 (id={char_id})", status_code=404)
        return self._row_to_character(row)

    def create_character(self, payload: CharacterCreate) -> CharacterResponse:
        cur = self._conn.execute(
            """
            INSERT INTO characters (
                name, aliases, role, gender, initial_age, appearance,
                personality, speech_style, background, arc_design, locked
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name.strip(),
                json.dumps(payload.aliases, ensure_ascii=False),
                payload.role,
                payload.gender,
                payload.initial_age,
                payload.appearance,
                payload.personality,
                payload.speech_style,
                payload.background,
                payload.arc_design,
                int(payload.locked),
            ),
        )
        return self.get_character(int(cur.lastrowid))

    def update_character(self, char_id: int, payload: CharacterUpdate) -> CharacterResponse:
        current = self.get_character(char_id)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return current
        if "aliases" in updates:
            updates["aliases"] = json.dumps(updates["aliases"], ensure_ascii=False)
        if "locked" in updates:
            updates["locked"] = int(bool(updates["locked"]))
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [char_id]
        self._conn.execute(
            f"UPDATE characters SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        return self.get_character(char_id)

    def delete_character(self, char_id: int) -> None:
        self._conn.execute("DELETE FROM characters WHERE id = ?", (char_id,))

    def replace_unlocked_characters(self, items: list[LlmCharacterItem]) -> list[CharacterResponse]:
        self._conn.execute("DELETE FROM characters WHERE locked = 0")
        for item in items:
            self.create_character(CharacterCreate(**item.model_dump(), locked=False))
        return self.list_characters()

    def get_character_timeline_snapshot(
        self, char_id: int, up_to_chapter_sort: float | None = None
    ) -> CharacterTimelineSnapshot:
        char = self.get_character(char_id)
        return build_character_timeline_snapshot(self._conn, char, up_to_chapter_sort)

    # --- Locations ---

    def list_locations(self) -> list[LocationResponse]:
        rows = self._conn.execute("SELECT * FROM locations ORDER BY id ASC").fetchall()
        return [self._row_to_location(r) for r in rows]

    def get_location(self, loc_id: int) -> LocationResponse:
        row = self._conn.execute("SELECT * FROM locations WHERE id = ?", (loc_id,)).fetchone()
        if not row:
            raise AppError("LOCATION_NOT_FOUND", f"未找到地点 (id={loc_id})", status_code=404)
        return self._row_to_location(row)

    def create_location(self, payload: LocationCreate) -> LocationResponse:
        cur = self._conn.execute(
            """
            INSERT INTO locations (name, aliases, type, description, sensory_details, related_chars, locked)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name.strip(),
                json.dumps(payload.aliases, ensure_ascii=False),
                payload.type,
                payload.description,
                payload.sensory_details,
                json.dumps(payload.related_chars),
                int(payload.locked),
            ),
        )
        return self.get_location(int(cur.lastrowid))

    def update_location(self, loc_id: int, payload: LocationUpdate) -> LocationResponse:
        current = self.get_location(loc_id)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return current
        if "aliases" in updates:
            updates["aliases"] = json.dumps(updates["aliases"], ensure_ascii=False)
        if "related_chars" in updates:
            updates["related_chars"] = json.dumps(updates["related_chars"])
        if "locked" in updates:
            updates["locked"] = int(bool(updates["locked"]))
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [loc_id]
        self._conn.execute(
            f"UPDATE locations SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        return self.get_location(loc_id)

    def delete_location(self, loc_id: int) -> None:
        self._conn.execute("DELETE FROM locations WHERE id = ?", (loc_id,))

    def replace_unlocked_locations(self, items: list[LlmLocationItem]) -> list[LocationResponse]:
        self._conn.execute("DELETE FROM locations WHERE locked = 0")
        for item in items:
            self.create_location(LocationCreate(**item.model_dump(), locked=False))
        return self.list_locations()

    # --- Main Plot ---

    def get_main_plot(self) -> MainPlotResponse:
        novel_row = self._conn.execute("SELECT id FROM novels ORDER BY id ASC LIMIT 1").fetchone()
        novel_id = int(novel_row["id"]) if novel_row else 1
        row = self._conn.execute("SELECT * FROM main_plots WHERE novel_id = ?", (novel_id,)).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT OR IGNORE INTO main_plots (novel_id, key_turning_pts) VALUES (?, '[]')",
                (novel_id,),
            )
            self._conn.commit()
            row = self._conn.execute("SELECT * FROM main_plots WHERE novel_id = ?", (novel_id,)).fetchone()
        pts_raw = json.loads(row["key_turning_pts"] or "[]")
        return MainPlotResponse(
            id=int(row["id"]),
            novel_id=int(row["novel_id"]),
            core_conflict=str(row["core_conflict"] or ""),
            romance_arc=str(row["romance_arc"] or ""),
            growth_arc=str(row["growth_arc"] or ""),
            key_turning_pts=[TurningPointItem(**pt) for pt in pts_raw],
            locked=bool(row["locked"]),
            updated_at=str(row["updated_at"]),
        )

    def update_main_plot(self, payload: MainPlotUpdate) -> MainPlotResponse:
        current = self.get_main_plot()
        core_conflict = payload.core_conflict if payload.core_conflict is not None else current.core_conflict
        romance_arc = payload.romance_arc if payload.romance_arc is not None else current.romance_arc
        growth_arc = payload.growth_arc if payload.growth_arc is not None else current.growth_arc
        pts = (
            [pt.model_dump() for pt in payload.key_turning_pts]
            if payload.key_turning_pts is not None
            else [pt.model_dump() for pt in current.key_turning_pts]
        )
        locked = int(payload.locked) if payload.locked is not None else int(current.locked)
        self._conn.execute(
            """
            UPDATE main_plots
            SET core_conflict = ?, romance_arc = ?, growth_arc = ?, key_turning_pts = ?,
                locked = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (core_conflict, romance_arc, growth_arc, json.dumps(pts, ensure_ascii=False), locked, current.id),
        )
        return self.get_main_plot()

    def apply_generated_main_plot(self, output: LlmMainPlotOutput) -> MainPlotResponse:
        current = self.get_main_plot()
        if current.locked:
            raise AppError("MAIN_PLOT_LOCKED", "主线剧情已锁定，如需 AI 重新生成请先解锁", status_code=400)
        return self.update_main_plot(
            MainPlotUpdate(
                core_conflict=output.core_conflict,
                romance_arc=output.romance_arc,
                growth_arc=output.growth_arc,
                key_turning_pts=output.key_turning_pts,
            )
        )

    @staticmethod
    def _row_to_worldview(row: sqlite3.Row) -> WorldviewResponse:
        return WorldviewResponse(
            id=int(row["id"]),
            category=row["category"],
            content=str(row["content"]),
            locked=bool(row["locked"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_character(row: sqlite3.Row) -> CharacterResponse:
        return CharacterResponse(
            id=int(row["id"]),
            name=str(row["name"]),
            aliases=json.loads(row["aliases"] or "[]"),
            role=row["role"],
            gender=str(row["gender"] or ""),
            initial_age=str(row["initial_age"] or ""),
            appearance=str(row["appearance"] or ""),
            personality=str(row["personality"] or ""),
            speech_style=str(row["speech_style"] or ""),
            background=str(row["background"] or ""),
            arc_design=str(row["arc_design"] or ""),
            locked=bool(row["locked"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_location(row: sqlite3.Row) -> LocationResponse:
        return LocationResponse(
            id=int(row["id"]),
            name=str(row["name"]),
            aliases=json.loads(row["aliases"] or "[]"),
            type=str(row["type"] or ""),
            description=str(row["description"] or ""),
            sensory_details=str(row["sensory_details"] or ""),
            related_chars=json.loads(row["related_chars"] or "[]"),
            locked=bool(row["locked"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
