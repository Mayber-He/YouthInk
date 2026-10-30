"""Repository for M4 Memory Loop: FTS5 indexing, Pending Queue, Foreshadowing, and Summaries."""

from __future__ import annotations

import json
import re
import sqlite3
import jieba

from app.core.exceptions import AppError
from app.schemas.memory import (
    BatchQueueActionRequest,
    ForeshadowCreate,
    ForeshadowResponse,
    ForeshadowUpdate,
    MemoryItemCategory,
    PendingItemUpdateRequest,
    PendingQueueItem,
    SummaryLevel,
    SummaryResponse,
)

_SAFE_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+")


def tokenize_for_fts(text: str) -> str:
    """Segment Chinese text with jieba.cut_for_search for FTS5 unicode61 indexing/querying."""
    if not text or not text.strip():
        return ""
    tokens = [
        t.strip()
        for t in jieba.cut_for_search(text)
        if t.strip() and _SAFE_TOKEN_RE.fullmatch(t.strip())
    ]
    return " ".join(tokens)


class MemoryRepository:
    """Data access layer for novel.db memory tables, pending queue, and FTS5."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def index_chapter_version_fts(self, version_id: int, content: str) -> None:
        segmented = tokenize_for_fts(content)
        if segmented:
            self.conn.execute(
                "INSERT INTO chapters_fts(rowid, content) VALUES (?, ?)",
                (version_id, segmented),
            )

    def index_fact_fts(self, fact_id: int, content: str) -> None:
        segmented = tokenize_for_fts(content)
        if segmented:
            self.conn.execute(
                "INSERT INTO facts_fts(rowid, content) VALUES (?, ?)",
                (fact_id, segmented),
            )

    def search_chapters_fts(
        self, query: str, max_chapter_sort: float | None = None, top_k: int = 8
    ) -> list[dict[str, object]]:
        tokens = tokenize_for_fts(query).split()
        if not tokens:
            return []
        match_expr = " OR ".join(f'"{t}"' for t in tokens[:12])
        sql = """
            SELECT cv.id AS version_id, cv.chapter_id, cv.content, c.sort_order
            FROM (
                SELECT rowid, rank FROM chapters_fts WHERE chapters_fts MATCH ? LIMIT 40
            ) fts
            JOIN chapter_versions cv ON cv.id = fts.rowid
            JOIN chapters c ON c.id = cv.chapter_id
            WHERE c.status = 'final'
              AND cv.version = (
                  SELECT MAX(v2.version) FROM chapter_versions v2 WHERE v2.chapter_id = c.id
              )
        """
        params: list[object] = [match_expr]
        if max_chapter_sort is not None:
            sql += " AND c.sort_order <= ?"
            params.append(max_chapter_sort)
        sql += " ORDER BY fts.rank LIMIT ?"
        params.append(top_k)
        return [dict(r) for r in self.conn.execute(sql, tuple(params)).fetchall()]

    def upsert_summary(
        self, level: SummaryLevel, ref_id: int, content: str, is_stale: bool = False
    ) -> SummaryResponse:
        self.conn.execute(
            """
            INSERT INTO summaries (level, ref_id, content, is_stale, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(level, ref_id) DO UPDATE SET
                content = excluded.content, is_stale = excluded.is_stale, updated_at = datetime('now')
            """,
            (level, ref_id, content, 1 if is_stale else 0),
        )
        row = self.conn.execute(
            "SELECT * FROM summaries WHERE level = ? AND ref_id = ?", (level, ref_id)
        ).fetchone()
        return self._row_to_summary(row)

    def list_summaries(self, level: str | None = None) -> list[SummaryResponse]:
        sql = "SELECT * FROM summaries" + (" WHERE level = ?" if level else "") + " ORDER BY level, ref_id"
        rows = self.conn.execute(sql, (level,) if level else ()).fetchall()
        return [self._row_to_summary(r) for r in rows]

    def list_foreshadowing(self, status: str | None = None) -> list[ForeshadowResponse]:
        sql = """
            SELECT f.*, COALESCE(c.title, '') AS planted_chapter_title
            FROM foreshadowing f LEFT JOIN chapters c ON c.id = f.planted_chapter_id
            WHERE f.confirm_status != 'discarded'
        """
        params: list[object] = []
        if status:
            sql += " AND f.status = ?"
            params.append(status)
        rows = self.conn.execute(sql + " ORDER BY f.id DESC", tuple(params)).fetchall()
        return [self._row_to_foreshadow(r) for r in rows]

    def create_foreshadowing(self, data: ForeshadowCreate) -> ForeshadowResponse:
        cur = self.conn.execute(
            """
            INSERT INTO foreshadowing (
                description, planted_chapter_id, plan_recover_start, plan_recover_end,
                status, related_chapter_ids, source_quote, confirm_status
            ) VALUES (?, ?, ?, ?, ?, '[]', ?, ?)
            """,
            (
                data.description,
                data.planted_chapter_id,
                data.plan_recover_start,
                data.plan_recover_end,
                data.status,
                data.source_quote,
                data.confirm_status,
            ),
        )
        return self.get_foreshadowing(int(cur.lastrowid or 0))

    def get_foreshadowing(self, fid: int) -> ForeshadowResponse:
        row = self.conn.execute(
            """
            SELECT f.*, COALESCE(c.title, '') AS planted_chapter_title
            FROM foreshadowing f LEFT JOIN chapters c ON c.id = f.planted_chapter_id
            WHERE f.id = ?
            """,
            (fid,),
        ).fetchone()
        if row is None:
            raise AppError("FORESHADOW_NOT_FOUND", f"未找到伏笔 #{fid}", 404)
        return self._row_to_foreshadow(row)

    def update_foreshadowing(self, fid: int, data: ForeshadowUpdate) -> ForeshadowResponse:
        cur = self.get_foreshadowing(fid)
        self.conn.execute(
            """
            UPDATE foreshadowing
            SET description = ?, plan_recover_start = ?, plan_recover_end = ?,
                status = ?, confirm_status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                data.description if data.description is not None else cur.description,
                data.plan_recover_start if data.plan_recover_start is not None else cur.plan_recover_start,
                data.plan_recover_end if data.plan_recover_end is not None else cur.plan_recover_end,
                data.status if data.status is not None else cur.status,
                data.confirm_status if data.confirm_status is not None else cur.confirm_status,
                fid,
            ),
        )
        return self.get_foreshadowing(fid)

    def delete_foreshadowing(self, fid: int) -> None:
        self.conn.execute("DELETE FROM foreshadowing WHERE id = ?", (fid,))

    def list_pending_queue(
        self,
        item_type: str | None = None,
        chapter_id: int | None = None,
        status_filter: str = "pending",
    ) -> list[PendingQueueItem]:
        chapters_map = self._chapter_lookup()
        items: list[PendingQueueItem] = []
        specs: list[tuple[MemoryItemCategory, str, str]] = [
            ("fact", "SELECT * FROM facts WHERE status = ? ORDER BY id DESC", "chapter_id"),
            (
                "char_state",
                "SELECT cs.*, ch.name AS char_name FROM character_state_changes cs JOIN characters ch ON ch.id = cs.character_id WHERE cs.confirm_status = ? ORDER BY cs.id DESC",
                "chapter_id",
            ),
            ("cognitive", "SELECT * FROM cognitive_records WHERE confirm_status = ? ORDER BY id DESC", "chapter_id"),
            (
                "relationship",
                "SELECT rc.*, ca.name AS char_a_name, cb.name AS char_b_name FROM relationship_changes rc JOIN characters ca ON ca.id = rc.char_a_id JOIN characters cb ON cb.id = rc.char_b_id WHERE rc.confirm_status = ? ORDER BY rc.id DESC",
                "chapter_id",
            ),
            ("foreshadowing", "SELECT * FROM foreshadowing WHERE confirm_status = ? ORDER BY id DESC", "planted_chapter_id"),
        ]
        for cat, sql, ch_col in specs:
            if item_type and item_type != cat:
                continue
            for r in self.conn.execute(sql, (status_filter,)).fetchall():
                cid = r[ch_col]
                if chapter_id is not None and cid != chapter_id:
                    continue
                ch_title, ch_idx = chapters_map.get(cid, ("", None))
                items.append(
                    PendingQueueItem(
                        item_type=cat,
                        id=int(r["id"]),
                        chapter_id=cid,
                        chapter_title=ch_title,
                        chapter_display_index=ch_idx,
                        summary_text=self._format_queue_summary(cat, r),
                        source_quote=str(r["source_quote"] or ""),
                        status=str(r["status"] if cat == "fact" else r["confirm_status"]),
                        raw_payload=dict(r),
                        created_at=str(r["created_at"]),
                    )
                )
        return items

    @staticmethod
    def _format_queue_summary(cat: MemoryItemCategory, r: sqlite3.Row) -> str:
        if cat == "fact":
            return f"[{r['fact_type']}] {r['content']}"
        if cat == "char_state":
            return f"{r['char_name']} · {r['field']} → {r['value']}"
        if cat == "cognitive":
            return f"秘密认知：{r['secret']}"
        if cat == "relationship":
            return f"{r['char_a_name']} ↔ {r['char_b_name']}：{r['rel_type']} (亲密度 {r['intimacy']})"
        return f"[{r['status']}] {r['description']}"

    def update_pending_item(
        self, item_type: MemoryItemCategory, item_id: int, req: PendingItemUpdateRequest
    ) -> None:
        target = "confirmed" if req.action in ("confirm", "edit") else "discarded"
        table_map = {
            "fact": ("facts", "status", "content"),
            "char_state": ("character_state_changes", "confirm_status", "value"),
            "cognitive": ("cognitive_records", "confirm_status", "secret"),
            "relationship": ("relationship_changes", "confirm_status", "rel_type"),
            "foreshadowing": ("foreshadowing", "confirm_status", "description"),
        }
        tbl, st_col, txt_col = table_map[item_type]
        if req.updated_text:
            self.conn.execute(
                f"UPDATE {tbl} SET {txt_col} = ?, {st_col} = ? WHERE id = ?",
                (req.updated_text, target, item_id),
            )
        else:
            self.conn.execute(
                f"UPDATE {tbl} SET {st_col} = ? WHERE id = ?", (target, item_id)
            )
        if item_type == "fact" and target == "confirmed":
            row = self.conn.execute("SELECT content FROM facts WHERE id = ?", (item_id,)).fetchone()
            if row:
                self.index_fact_fts(item_id, str(row["content"]))

    def batch_update_pending(self, req: BatchQueueActionRequest) -> int:
        count = 0
        single_req = PendingItemUpdateRequest(action=req.action)
        for entry in req.items:
            itype = str(entry.get("item_type", ""))
            iid = int(entry.get("id", 0))
            if itype in ("fact", "char_state", "cognitive", "relationship", "foreshadowing") and iid > 0:
                self.update_pending_item(itype, iid, single_req)  # type: ignore[arg-type]
                count += 1
        return count

    def _chapter_lookup(self) -> dict[int, tuple[str, int]]:
        rows = self.conn.execute(
            """
            SELECT c.id, c.title FROM chapters c
            JOIN arcs a ON a.id = c.arc_id JOIN volumes v ON v.id = a.volume_id
            ORDER BY v.sort_order ASC, a.sort_order ASC, c.sort_order ASC, c.id ASC
            """
        ).fetchall()
        return {int(r["id"]): (str(r["title"] or f"第{idx}章"), idx) for idx, r in enumerate(rows, start=1)}

    @staticmethod
    def _row_to_summary(row: sqlite3.Row) -> SummaryResponse:
        return SummaryResponse(
            id=int(row["id"]),
            level=row["level"],
            ref_id=int(row["ref_id"]),
            content=str(row["content"]),
            is_stale=bool(row["is_stale"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_foreshadow(row: sqlite3.Row) -> ForeshadowResponse:
        rel_ids = json.loads(row["related_chapter_ids"] or "[]")
        return ForeshadowResponse(
            id=int(row["id"]),
            description=str(row["description"]),
            planted_chapter_id=row["planted_chapter_id"],
            planted_chapter_title=str(row["planted_chapter_title"] or ""),
            plan_recover_start=row["plan_recover_start"],
            plan_recover_end=row["plan_recover_end"],
            status=row["status"],
            related_chapter_ids=[int(x) for x in rel_ids],
            source_quote=str(row["source_quote"] or ""),
            confirm_status=str(row["confirm_status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
