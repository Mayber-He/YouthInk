"""Repository for the Explicit Constraint System: hard/soft anti-hallucination constraints."""

from __future__ import annotations

import sqlite3

from app.core.exceptions import AppError
from app.schemas.constraints import (
    ConstraintCreate,
    ConstraintResponse,
    ConstraintStatus,
    ConstraintTargetType,
    ConstraintUpdate,
)


class ConstraintRepository:
    """Data access layer for novel.db constraints table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # --- CRUD ---

    def create_constraint(self, payload: ConstraintCreate) -> ConstraintResponse:
        cur = self.conn.execute(
            """
            INSERT INTO constraints (
                target_type, target_id, content, severity, status,
                valid_from_chapter_id, valid_until_chapter_id,
                source_quote, locked
            ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                payload.target_type,
                payload.target_id,
                payload.content.strip(),
                payload.severity,
                payload.valid_from_chapter_id,
                payload.valid_until_chapter_id,
                payload.source_quote,
                1 if payload.locked else 0,
            ),
        )
        return self.get_constraint(int(cur.lastrowid or 0))

    def get_constraint(self, cid: int) -> ConstraintResponse:
        row = self.conn.execute(
            "SELECT * FROM constraints WHERE id = ?", (cid,)
        ).fetchone()
        if row is None:
            raise AppError("CONSTRAINT_NOT_FOUND", f"未找到约束 #{cid}", status_code=404)
        return self._row_to_response(row)

    def list_constraints(
        self,
        target_type: ConstraintTargetType | None = None,
        target_id: int | None = None,
        status: ConstraintStatus | None = None,
    ) -> list[ConstraintResponse]:
        sql = "SELECT * FROM constraints WHERE 1=1"
        params: list[object] = []
        if target_type:
            sql += " AND target_type = ?"
            params.append(target_type)
        if target_id is not None:
            sql += " AND target_id = ?"
            params.append(target_id)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id ASC"
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return [self._row_to_response(r) for r in rows]

    def update_constraint(self, cid: int, payload: ConstraintUpdate) -> ConstraintResponse:
        cur = self.get_constraint(cid)
        data = payload.model_dump(exclude_unset=True)
        if "locked" in data:
            data["locked"] = 1 if data["locked"] else 0
        if not data:
            return cur
        sets = ", ".join(f"{k} = ?" for k in data)
        self.conn.execute(
            f"UPDATE constraints SET {sets} WHERE id = ?",
            (*data.values(), cid),
        )
        return self.get_constraint(cid)

    def delete_constraint(self, cid: int) -> None:
        self.get_constraint(cid)
        self.conn.execute("DELETE FROM constraints WHERE id = ?", (cid,))

    def delete_for_target(
        self, target_type: ConstraintTargetType, target_id: int
    ) -> int:
        """Delete all constraints bound to a target (e.g. a replaced character)."""
        cur = self.conn.execute(
            "DELETE FROM constraints WHERE target_type = ? AND target_id = ?",
            (target_type, target_id),
        )
        return cur.rowcount or 0

    # --- Violation / resolution detection records ---

    def create_constraint_check(
        self,
        constraint_id: int,
        chapter_id: int,
        verdict: str,
        evidence_quote: str,
        description: str,
    ) -> int:
        """Record an LLM verdict on a constraint; always enters pending queue."""
        self.get_constraint(constraint_id)  # validate target exists
        cur = self.conn.execute(
            """
            INSERT INTO constraint_checks (
                constraint_id, chapter_id, verdict, evidence_quote, description, confirm_status
            ) VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (constraint_id, chapter_id, verdict, evidence_quote, description),
        )
        return int(cur.lastrowid or 0)

    # --- Active constraints for writing ---

    def list_active_for_chapter(
        self,
        chapter_id: int,
        chapter_sort_order: float,
        character_ids: list[int] | None = None,
        location_ids: list[int] | None = None,
    ) -> list[ConstraintResponse]:
        """Return constraints in effect for the given chapter.

        Scope: novel-wide + this chapter + active characters + active locations,
        filtered by status in ('active', 'violated') and the chapter validity window.
        A 'violated' constraint still holds for future writing (the rule stands),
        it is just flagged. Hard constraints come first.
        """
        char_ids = character_ids or []
        loc_ids = location_ids or []
        sql = """
            SELECT c.* FROM constraints c
            LEFT JOIN chapters cf ON cf.id = c.valid_from_chapter_id
            LEFT JOIN chapters cu ON cu.id = c.valid_until_chapter_id
            WHERE c.status IN ('active', 'violated')
              AND (cf.id IS NULL OR cf.sort_order <= ?)
              AND (cu.id IS NULL OR cu.sort_order >= ?)
              AND (
                    (c.target_type = 'novel')
                 OR (c.target_type = 'chapter' AND c.target_id = ?)
        """
        params: list[object] = [chapter_sort_order, chapter_sort_order, chapter_id]
        if char_ids:
            sql += f" OR (c.target_type = 'character' AND c.target_id IN ({','.join('?' * len(char_ids))}))"
            params.extend(char_ids)
        if loc_ids:
            sql += f" OR (c.target_type = 'location' AND c.target_id IN ({','.join('?' * len(loc_ids))}))"
            params.extend(loc_ids)
        sql += ") ORDER BY CASE WHEN c.severity = 'hard' THEN 0 ELSE 1 END, c.id ASC"
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return [self._row_to_response(r) for r in rows]

    # --- helpers ---

    def _resolve_target_name(self, target_type: str, target_id: int | None) -> str:
        if target_id is None:
            return "全书通用" if target_type == "novel" else ""
        table_col = {
            "character": ("characters", "name"),
            "location": ("locations", "name"),
            "worldview": ("worldview_entries", "content"),
            "chapter": ("chapters", "title"),
        }.get(target_type)
        if not table_col:
            return ""
        tbl, col = table_col
        row = self.conn.execute(
            f"SELECT {col} FROM {tbl} WHERE id = ?", (target_id,)
        ).fetchone()
        if row is None:
            return f"#{target_id}"
        val = str(row[col] or "")
        return val[:24] if target_type == "worldview" else val

    def _row_to_response(self, row: sqlite3.Row) -> ConstraintResponse:
        return ConstraintResponse(
            id=int(row["id"]),
            target_type=row["target_type"],  # type: ignore[arg-type]
            target_id=row["target_id"],
            content=str(row["content"]),
            severity=row["severity"],  # type: ignore[arg-type]
            status=row["status"],  # type: ignore[arg-type]
            valid_from_chapter_id=row["valid_from_chapter_id"],
            valid_until_chapter_id=row["valid_until_chapter_id"],
            source_quote=str(row["source_quote"] or ""),
            locked=bool(row["locked"]),
            target_name=self._resolve_target_name(
                str(row["target_type"]), row["target_id"]
            ),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
