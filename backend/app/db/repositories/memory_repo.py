"""Repository for M4 Memory Loop: FTS5 indexing, Pending Queue, Character Memories, Foreshadowing, and Summaries."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter

import jieba

from app.core.exceptions import AppError
from app.db.repositories.timeline_repo import query_character_memories
from app.schemas.memory import (
    BatchQueueActionRequest,
    ChapterMemoryItem,
    CharacterMemoryCreate,
    CharacterMemoryResponse,
    CharacterMemoryUpdate,
    DisableableMemoryCategory,
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

_DISABLE_TABLE_MAP: dict[str, str] = {
    "fact": "facts",
    "char_state": "character_state_changes",
    "cognitive": "cognitive_records",
    "relationship": "relationship_changes",
    "foreshadowing": "foreshadowing",
}


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
        self.conn.execute("DELETE FROM chapters_fts WHERE rowid = ?", (version_id,))
        segmented = tokenize_for_fts(content)
        if segmented:
            self.conn.execute(
                "INSERT INTO chapters_fts(rowid, content) VALUES (?, ?)",
                (version_id, segmented),
            )

    def index_fact_fts(self, fact_id: int, content: str) -> None:
        self.conn.execute("DELETE FROM facts_fts WHERE rowid = ?", (fact_id,))
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
              AND c.continuity_review_required = 0
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
        self,
        level: SummaryLevel,
        ref_id: int,
        content: str,
        is_stale: bool = False,
        source_hash: str | None = None,
    ) -> SummaryResponse:
        self.conn.execute(
            """
            INSERT INTO summaries (level, ref_id, content, source_hash, is_stale, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(level, ref_id) DO UPDATE SET
                content = excluded.content, source_hash = excluded.source_hash,
                is_stale = excluded.is_stale, updated_at = datetime('now')
            """,
            (level, ref_id, content, source_hash, 1 if is_stale else 0),
        )
        row = self.conn.execute(
            "SELECT * FROM summaries WHERE level = ? AND ref_id = ?", (level, ref_id)
        ).fetchone()
        return self._row_to_summary(row)

    def list_summaries(self, level: str | None = None) -> list[SummaryResponse]:
        sql = "SELECT * FROM summaries" + (" WHERE level = ?" if level else "") + " ORDER BY level, ref_id"
        rows = self.conn.execute(sql, (level,) if level else ()).fetchall()
        return [self._row_to_summary(r) for r in rows]

    # --- Character Memories (expanded from cognitive_records) ---

    def list_character_memories(
        self,
        *,
        character_id: int | None = None,
        up_to_chapter_sort: float | None = None,
        memory_type: str | None = None,
        include_disabled: bool = True,
        include_pending: bool = False,
    ) -> list[CharacterMemoryResponse]:
        records = query_character_memories(
            self.conn,
            character_id=character_id,
            up_to_chapter_sort=up_to_chapter_sort,
            memory_type=memory_type,
            include_disabled=include_disabled,
            include_pending=include_pending,
        )
        return [CharacterMemoryResponse(**rec) for rec in records]  # type: ignore[arg-type]

    def get_character_memory(
        self, record_id: int, up_to_chapter_sort: float | None = None
    ) -> CharacterMemoryResponse:
        records = query_character_memories(
            self.conn,
            up_to_chapter_sort=up_to_chapter_sort,
            include_disabled=True,
            include_pending=True,
        )
        for rec in records:
            if int(rec["id"]) == record_id:  # type: ignore[arg-type]
                return CharacterMemoryResponse(**rec)  # type: ignore[arg-type]
        row = self.conn.execute(
            "SELECT * FROM cognitive_records WHERE id = ? AND is_stale = 0",
            (record_id,),
        ).fetchone()
        if row is None:
            raise AppError("MEMORY_ITEM_NOT_FOUND", f"未找到人物记忆 #{record_id}", status_code=404)
        return self._row_to_character_memory(row)

    def _validate_knower_ids(self, knower_ids: list[int]) -> list[int]:
        cleaned = list(dict.fromkeys(int(k) for k in knower_ids if int(k) > 0))
        if not cleaned:
            raise AppError("INVALID_KNOWER_IDS", "请至少选择一位有效的知情人物", status_code=400)
        existing = {
            int(r["id"])
            for r in self.conn.execute("SELECT id FROM characters").fetchall()
        }
        unknown = [k for k in cleaned if k not in existing]
        if unknown:
            raise AppError(
                "UNKNOWN_CHARACTER",
                f"知情人物包含不存在的角色编号: {unknown}",
                status_code=400,
            )
        return cleaned

    def _validate_chapter_id(self, chapter_id: int | None) -> int | None:
        if chapter_id is None:
            return None
        row = self.conn.execute(
            "SELECT id FROM chapters WHERE id = ?", (int(chapter_id),)
        ).fetchone()
        if row is None:
            raise AppError("CHAPTER_NOT_FOUND", f"未找到章节 #{chapter_id}", status_code=404)
        return int(chapter_id)

    def create_character_memory(self, data: CharacterMemoryCreate) -> CharacterMemoryResponse:
        text = (data.content or data.secret or "").strip()
        if not text:
            raise AppError("INVALID_MEMORY_CONTENT", "人物记忆内容不能为空", status_code=400)
        knower_ids = self._validate_knower_ids(data.knower_ids)
        chapter_id = self._validate_chapter_id(data.chapter_id)
        resolved_cid = self._validate_chapter_id(data.resolved_chapter_id)
        time_scope = (data.time_scope or "").strip()
        if data.memory_type == "schedule" and data.related_record_id is None and not time_scope:
            raise AppError("TIME_SCOPE_REQUIRED", "临时安排必须填写适用时间说明", status_code=400)

        learned_by = (data.learned_by or "").strip()
        if not learned_by and chapter_id is None:
            learned_by = "故事开始前已知"

        separate_resolution = (
            data.memory_type == "schedule"
            and data.schedule_status in ("completed", "cancelled", "expired")
            and resolved_cid is not None
            and resolved_cid != chapter_id
        )
        base_status = (
            "pending"
            if separate_resolution
            else (data.schedule_status if data.memory_type == "schedule" else "pending")
        )

        cur = self.conn.execute(
            """
            INSERT INTO cognitive_records (
                secret, knower_ids, chapter_id, learned_by,
                memory_type, time_scope, schedule_status, related_record_id,
                source_quote, confirm_status, origin, is_stale, is_disabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', 'manual', 0, 0)
            """,
            (
                text,
                json.dumps(knower_ids),
                chapter_id,
                learned_by,
                data.memory_type,
                time_scope,
                base_status,
                data.related_record_id,
                (data.source_quote or "").strip(),
            ),
        )
        base_id = int(cur.lastrowid or 0)
        if separate_resolution:
            self.conn.execute(
                """
                INSERT INTO cognitive_records (
                    secret, knower_ids, chapter_id, learned_by,
                    memory_type, time_scope, schedule_status, related_record_id,
                    source_quote, confirm_status, origin, is_stale, is_disabled
                ) VALUES (?, ?, ?, ?, 'schedule', ?, ?, ?, ?, 'confirmed', 'manual', 0, 0)
                """,
                (
                    text,
                    json.dumps(knower_ids),
                    resolved_cid,
                    learned_by,
                    time_scope,
                    data.schedule_status,
                    base_id,
                    (data.source_quote or "").strip(),
                ),
            )
        return self.get_character_memory(base_id)

    def update_character_memory(
        self, record_id: int, data: CharacterMemoryUpdate
    ) -> CharacterMemoryResponse:
        row = self._require_current_memory_item("cognitive_records", record_id)
        new_text_raw = data.content if data.content is not None else data.secret
        text = new_text_raw.strip() if new_text_raw is not None else str(row["secret"])
        if not text:
            raise AppError("INVALID_MEMORY_CONTENT", "人物记忆内容不能为空", status_code=400)

        mtype = (
            data.memory_type
            if data.memory_type is not None
            else str(row["memory_type"] or "secret")
        )
        knower_ids = (
            self._validate_knower_ids(data.knower_ids)
            if data.knower_ids is not None
            else self._parse_int_list(row["knower_ids"])
        )
        if data.prior_to_story is True:
            chapter_id = None
        elif "chapter_id" in data.model_fields_set:
            chapter_id = self._validate_chapter_id(data.chapter_id)
        else:
            chapter_id = int(row["chapter_id"]) if row["chapter_id"] is not None else None

        learned_by = (
            data.learned_by.strip()
            if data.learned_by is not None
            else str(row["learned_by"] or "")
        )
        if not learned_by and chapter_id is None:
            learned_by = "故事开始前已知"

        time_scope = (
            data.time_scope.strip()
            if data.time_scope is not None
            else str(row["time_scope"] or "")
        )
        if mtype == "schedule" and row["related_record_id"] is None and not time_scope:
            raise AppError("TIME_SCOPE_REQUIRED", "临时安排必须填写适用时间说明", status_code=400)

        source_quote = (
            data.source_quote.strip()
            if data.source_quote is not None
            else str(row["source_quote"] or "")
        )
        is_disabled = (
            int(bool(data.is_disabled))
            if data.is_disabled is not None
            else int(row["is_disabled"])
        )
        base_sched_status = str(row["schedule_status"] or "pending")
        resolved_cid = (
            self._validate_chapter_id(data.resolved_chapter_id)
            if data.resolved_chapter_id is not None
            else None
        )

        if mtype == "schedule" and data.schedule_status is not None:
            if data.schedule_status == "pending":
                base_sched_status = "pending"
                self.conn.execute(
                    "UPDATE cognitive_records SET confirm_status = 'discarded', is_stale = 1 "
                    "WHERE related_record_id = ? AND is_stale = 0",
                    (record_id,),
                )
            else:
                existing_followup = self.conn.execute(
                    "SELECT id, chapter_id FROM cognitive_records "
                    "WHERE related_record_id = ? AND is_stale = 0 AND confirm_status != 'discarded' "
                    "ORDER BY id DESC LIMIT 1",
                    (record_id,),
                ).fetchone()
                if resolved_cid is not None and resolved_cid != chapter_id:
                    base_sched_status = "pending"
                    if existing_followup:
                        self.conn.execute(
                            """
                            UPDATE cognitive_records
                            SET schedule_status = ?, chapter_id = ?, secret = ?,
                                knower_ids = ?, time_scope = ?, confirm_status = 'confirmed',
                                origin = 'manual', source_hash = NULL, is_disabled = 0
                            WHERE id = ?
                            """,
                            (
                                data.schedule_status,
                                resolved_cid,
                                text,
                                json.dumps(knower_ids),
                                time_scope,
                                int(existing_followup["id"]),
                            ),
                        )
                    else:
                        self.conn.execute(
                            """
                            INSERT INTO cognitive_records (
                                secret, knower_ids, chapter_id, learned_by,
                                memory_type, time_scope, schedule_status, related_record_id,
                                source_quote, confirm_status, origin, is_stale, is_disabled
                            ) VALUES (?, ?, ?, ?, 'schedule', ?, ?, ?, ?, 'confirmed', 'manual', 0, 0)
                            """,
                            (
                                text,
                                json.dumps(knower_ids),
                                resolved_cid,
                                learned_by,
                                time_scope,
                                data.schedule_status,
                                record_id,
                                source_quote,
                            ),
                        )
                elif existing_followup:
                    self.conn.execute(
                        """
                        UPDATE cognitive_records
                        SET schedule_status = ?, secret = ?, knower_ids = ?, time_scope = ?,
                            confirm_status = 'confirmed', origin = 'manual', source_hash = NULL,
                            is_disabled = 0
                        WHERE id = ?
                        """,
                        (
                            data.schedule_status,
                            text,
                            json.dumps(knower_ids),
                            time_scope,
                            int(existing_followup["id"]),
                        ),
                    )
                else:
                    base_sched_status = data.schedule_status

        content_changed = (
            text != str(row["secret"])
            or mtype != str(row["memory_type"] or "secret")
            or knower_ids != self._parse_int_list(row["knower_ids"])
            or chapter_id != (int(row["chapter_id"]) if row["chapter_id"] is not None else None)
            or learned_by != str(row["learned_by"] or "")
            or time_scope != str(row["time_scope"] or "")
            or base_sched_status != str(row["schedule_status"] or "pending")
            or source_quote != str(row["source_quote"] or "")
            or data.schedule_status is not None
        )
        confirm_status = (
            data.confirm_status
            if data.confirm_status is not None
            else ("confirmed" if content_changed else str(row["confirm_status"]))
        )
        result = self.conn.execute(
            """
            UPDATE cognitive_records
            SET secret = ?, knower_ids = ?, chapter_id = ?, learned_by = ?,
                memory_type = ?, time_scope = ?, schedule_status = ?,
                source_quote = ?, is_disabled = ?, confirm_status = ?,
                origin = CASE WHEN ? THEN 'manual' ELSE origin END,
                source_hash = CASE WHEN ? THEN NULL ELSE source_hash END
            WHERE id = ? AND is_stale = 0
            """,
            (
                text,
                json.dumps(knower_ids),
                chapter_id,
                learned_by,
                mtype,
                time_scope,
                base_sched_status if mtype == "schedule" else "pending",
                source_quote,
                is_disabled,
                confirm_status,
                content_changed,
                content_changed,
                record_id,
            ),
        )
        if result.rowcount == 0:
            raise AppError(
                "MEMORY_ITEM_STALE", "该记忆条目已失效，请刷新后处理最新抽取结果", status_code=409
            )
        return self.get_character_memory(record_id)

    def _row_to_character_memory(self, row: sqlite3.Row) -> CharacterMemoryResponse:
        chapter_meta = self._chapter_meta()
        char_names = {
            int(r["id"]): str(r["name"])
            for r in self.conn.execute("SELECT id, name FROM characters").fetchall()
        }
        knower_ids = self._parse_int_list(row["knower_ids"])
        cid = int(row["chapter_id"]) if row["chapter_id"] is not None else None
        title, idx, story_time = chapter_meta.get(cid or 0, ("", None, ""))
        mtype = str(row["memory_type"] or "secret")
        sched_st = str(row["schedule_status"] or "pending") if mtype == "schedule" else "pending"
        disabled = bool(row["is_disabled"])
        c_status = str(row["confirm_status"] or "pending")
        return CharacterMemoryResponse(
            id=int(row["id"]),
            content=str(row["secret"]),
            secret=str(row["secret"]),
            memory_type=mtype,  # type: ignore[arg-type]
            time_scope=str(row["time_scope"] or ""),
            schedule_status=sched_st,  # type: ignore[arg-type]
            effective_schedule_status=sched_st,  # type: ignore[arg-type]
            related_record_id=(
                int(row["related_record_id"]) if row["related_record_id"] is not None else None
            ),
            knower_ids=knower_ids,
            knower_names=[char_names.get(k, str(k)) for k in knower_ids],
            learned_by=str(row["learned_by"] or ""),
            chapter_id=cid,
            chapter_title=title,
            chapter_display_index=idx,
            story_time=story_time,
            source_quote=str(row["source_quote"] or ""),
            origin=str(row["origin"] or "legacy"),
            confirm_status=c_status,
            is_disabled=disabled,
            is_stale=bool(row["is_stale"]),
            is_effective=c_status == "confirmed" and not disabled,
            created_at=str(row["created_at"] or ""),
        )

    def list_foreshadowing(self, status: str | None = None) -> list[ForeshadowResponse]:
        sql = """
            SELECT f.*, COALESCE(c.title, '') AS planted_chapter_title
            FROM foreshadowing f LEFT JOIN chapters c ON c.id = f.planted_chapter_id
            WHERE f.confirm_status != 'discarded' AND f.is_stale = 0
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
                status, related_chapter_ids, source_quote, confirm_status, origin, is_stale
            ) VALUES (?, ?, ?, ?, ?, '[]', ?, ?, 'manual', 0)
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
            raise AppError("FORESHADOW_NOT_FOUND", f"未找到伏笔 #{fid}", status_code=404)
        return self._row_to_foreshadow(row)

    def update_foreshadowing(self, fid: int, data: ForeshadowUpdate) -> ForeshadowResponse:
        cur = self.get_foreshadowing(fid)
        self._require_current_memory_item("foreshadowing", fid)
        content_changed = any(
            value is not None and value != getattr(cur, field)
            for field, value in (
                ("description", data.description),
                ("plan_recover_start", data.plan_recover_start),
                ("plan_recover_end", data.plan_recover_end),
                ("status", data.status),
            )
        )
        result = self.conn.execute(
            """
            UPDATE foreshadowing
            SET description = ?, plan_recover_start = ?, plan_recover_end = ?,
                status = ?, confirm_status = ?,
                origin = CASE WHEN ? THEN 'manual' ELSE origin END,
                source_hash = CASE WHEN ? THEN NULL ELSE source_hash END,
                is_stale = CASE WHEN ? THEN 0 ELSE is_stale END,
                updated_at = datetime('now')
            WHERE id = ? AND is_stale = 0
            """,
            (
                data.description if data.description is not None else cur.description,
                data.plan_recover_start if data.plan_recover_start is not None else cur.plan_recover_start,
                data.plan_recover_end if data.plan_recover_end is not None else cur.plan_recover_end,
                data.status if data.status is not None else cur.status,
                data.confirm_status if data.confirm_status is not None else cur.confirm_status,
                content_changed,
                content_changed,
                content_changed,
                fid,
            ),
        )
        if result.rowcount == 0:
            raise AppError("MEMORY_ITEM_STALE", "该记忆条目已失效，请刷新后处理最新抽取结果", status_code=409)
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
        char_names = {
            int(r["id"]): str(r["name"])
            for r in self.conn.execute("SELECT id, name FROM characters").fetchall()
        }
        items: list[PendingQueueItem] = []
        specs: list[tuple[MemoryItemCategory, str, str]] = [
            ("fact", "SELECT * FROM facts WHERE status = ? AND is_stale = 0 ORDER BY id DESC", "chapter_id"),
            (
                "char_state",
                "SELECT cs.*, ch.name AS char_name FROM character_state_changes cs JOIN characters ch ON ch.id = cs.character_id WHERE cs.confirm_status = ? AND cs.is_stale = 0 ORDER BY cs.id DESC",
                "chapter_id",
            ),
            ("cognitive", "SELECT * FROM cognitive_records WHERE confirm_status = ? AND is_stale = 0 ORDER BY id DESC", "chapter_id"),
            (
                "relationship",
                "SELECT rc.*, ca.name AS char_a_name, cb.name AS char_b_name FROM relationship_changes rc JOIN characters ca ON ca.id = rc.char_a_id JOIN characters cb ON cb.id = rc.char_b_id WHERE rc.confirm_status = ? AND rc.is_stale = 0 ORDER BY rc.id DESC",
                "chapter_id",
            ),
            ("foreshadowing", "SELECT * FROM foreshadowing WHERE confirm_status = ? AND is_stale = 0 ORDER BY id DESC", "planted_chapter_id"),
            (
                "constraint_check",
                "SELECT cc.*, cc.evidence_quote AS source_quote, c.content AS constraint_content "
                "FROM constraint_checks cc "
                "JOIN constraints c ON c.id = cc.constraint_id "
                "WHERE cc.confirm_status = ? AND cc.is_stale = 0 ORDER BY cc.id DESC",
                "chapter_id",
            ),
        ]
        for cat, sql, ch_col in specs:
            if item_type and item_type != cat:
                continue
            for r in self.conn.execute(sql, (status_filter,)).fetchall():
                cid = r[ch_col]
                if chapter_id is not None and cid != chapter_id:
                    continue
                ch_title, ch_idx = chapters_map.get(cid, ("", None))
                payload = dict(r)
                if cat == "cognitive":
                    knower_ids = self._parse_int_list(r["knower_ids"])
                    payload["knower_ids_list"] = knower_ids
                    payload["knower_names"] = [char_names.get(k, str(k)) for k in knower_ids]
                    payload["memory_type"] = str(r["memory_type"] or "secret")
                    payload["time_scope"] = str(r["time_scope"] or "")
                    payload["schedule_status"] = str(r["schedule_status"] or "pending")
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
                        is_disabled=(
                            bool(r["is_disabled"]) if "is_disabled" in r.keys() else False
                        ),
                        raw_payload=payload,
                        created_at=str(r["created_at"]),
                    )
                )
        return items

    def list_chapter_memory_items(self, chapter_id: int) -> list[ChapterMemoryItem]:
        """List every current (non-stale) memory created by one chapter.

        Disabled rows stay in the list so the author can restore them. Conflict
        flags apply to multiple effective relationship rows for one character pair;
        independent character memories for the same character coexist without
        false conflict warnings.
        """
        chapter_meta = self._chapter_meta()
        char_names = {
            int(r["id"]): str(r["name"])
            for r in self.conn.execute("SELECT id, name FROM characters").fetchall()
        }
        pair_conflicts, _ = self._conflict_keys()
        items: list[ChapterMemoryItem] = []

        def add(
            cat: DisableableMemoryCategory,
            row: sqlite3.Row,
            *,
            content: str,
            status: str,
            cid: int | None,
            meta: dict[str, object] | None = None,
            conflict: bool = False,
            conflict_reason: str = "",
        ) -> None:
            title, idx, story_time = chapter_meta.get(cid or 0, ("", None, ""))
            disabled = bool(row["is_disabled"])
            items.append(
                ChapterMemoryItem(
                    item_type=cat,
                    id=int(row["id"]),
                    chapter_id=cid,
                    chapter_title=title,
                    chapter_display_index=idx,
                    story_time=story_time,
                    content=content,
                    source_quote=str(row["source_quote"] or ""),
                    status=status,
                    is_disabled=disabled,
                    is_effective=status in ("confirmed", "locked") and not disabled,
                    conflict=conflict and not disabled,
                    conflict_reason=conflict_reason if conflict and not disabled else "",
                    meta=meta or {},
                    created_at=str(row["created_at"] or ""),
                )
            )

        for r in self.conn.execute(
            "SELECT * FROM facts WHERE chapter_id = ? AND is_stale = 0 "
            "AND status != 'discarded' ORDER BY id DESC",
            (chapter_id,),
        ).fetchall():
            add(
                "fact", r,
                content=str(r["content"]),
                status=str(r["status"]),
                cid=r["chapter_id"],
                meta={"fact_type": r["fact_type"]},
            )

        for r in self.conn.execute(
            """
            SELECT cs.*, ch.name AS char_name
            FROM character_state_changes cs
            JOIN characters ch ON ch.id = cs.character_id
            WHERE cs.chapter_id = ? AND cs.is_stale = 0
              AND cs.confirm_status != 'discarded'
            ORDER BY cs.id DESC
            """,
            (chapter_id,),
        ).fetchall():
            add(
                "char_state", r,
                content=f"{r['char_name']}：{r['field']} → {r['value']}",
                status=str(r["confirm_status"]),
                cid=r["chapter_id"],
                meta={
                    "character_id": r["character_id"],
                    "character_name": str(r["char_name"]),
                    "field": str(r["field"]),
                },
            )

        for r in self.conn.execute(
            "SELECT * FROM cognitive_records WHERE chapter_id = ? AND is_stale = 0 "
            "AND confirm_status != 'discarded' ORDER BY id DESC",
            (chapter_id,),
        ).fetchall():
            knower_ids = self._parse_int_list(r["knower_ids"])
            mtype = str(r["memory_type"] or "secret")
            sched_st = str(r["schedule_status"] or "pending") if mtype == "schedule" else "pending"
            add(
                "cognitive", r,
                content=str(r["secret"]),
                status=str(r["confirm_status"]),
                cid=r["chapter_id"],
                meta={
                    "knower_ids": knower_ids,
                    "knower_names": [char_names.get(k, str(k)) for k in knower_ids],
                    "learned_by": str(r["learned_by"] or ""),
                    "memory_type": mtype,
                    "time_scope": str(r["time_scope"] or ""),
                    "schedule_status": sched_st,
                    "related_record_id": r["related_record_id"],
                    "origin": str(r["origin"] or "legacy"),
                },
                conflict=False,
                conflict_reason="",
            )

        for r in self.conn.execute(
            """
            SELECT rc.*, ca.name AS char_a_name, cb.name AS char_b_name
            FROM relationship_changes rc
            JOIN characters ca ON ca.id = rc.char_a_id
            JOIN characters cb ON cb.id = rc.char_b_id
            WHERE rc.chapter_id = ? AND rc.is_stale = 0
              AND rc.confirm_status != 'discarded'
            ORDER BY rc.id DESC
            """,
            (chapter_id,),
        ).fetchall():
            a_id, b_id = int(r["char_a_id"]), int(r["char_b_id"])
            pair = (min(a_id, b_id), max(a_id, b_id))
            conflict = pair in pair_conflicts
            add(
                "relationship", r,
                content=(
                    f"{r['char_a_name']} ↔ {r['char_b_name']}：{r['rel_type']}"
                    f"（亲密度 {r['intimacy']}）"
                ),
                status=str(r["confirm_status"]),
                cid=r["chapter_id"],
                meta={
                    "char_a_id": a_id,
                    "char_a_name": str(r["char_a_name"]),
                    "char_b_id": b_id,
                    "char_b_name": str(r["char_b_name"]),
                    "rel_type": str(r["rel_type"]),
                    "intimacy": r["intimacy"],
                    "publicity": str(r["publicity"] or ""),
                },
                conflict=conflict,
                conflict_reason="同一对人物存在多条生效关系" if conflict else "",
            )

        for r in self.conn.execute(
            "SELECT * FROM foreshadowing WHERE planted_chapter_id = ? AND is_stale = 0 "
            "AND confirm_status != 'discarded' ORDER BY id DESC",
            (chapter_id,),
        ).fetchall():
            add(
                "foreshadowing", r,
                content=str(r["description"]),
                status=str(r["confirm_status"]),
                cid=r["planted_chapter_id"],
                meta={"foreshadow_status": str(r["status"])},
            )

        return items

    def set_memory_item_disabled(
        self, item_type: DisableableMemoryCategory, item_id: int, is_disabled: bool
    ) -> None:
        """Toggle author-facing injection without touching confirm_status or rows."""
        table = _DISABLE_TABLE_MAP.get(item_type)
        if table is None:
            raise AppError("MEMORY_ITEM_NOT_DISABLEABLE", "该记忆类型不支持停用", status_code=400)
        self._require_current_memory_item(table, item_id)
        result = self.conn.execute(
            f"UPDATE {table} SET is_disabled = ? WHERE id = ? AND is_stale = 0",
            (1 if is_disabled else 0, item_id),
        )
        if result.rowcount == 0:
            raise AppError(
                "MEMORY_ITEM_STALE", "该记忆条目已失效，请刷新后处理最新抽取结果", status_code=409
            )

    def _conflict_keys(self) -> tuple[set[tuple[int, int]], set[int]]:
        pair_counts: Counter[tuple[int, int]] = Counter()
        for r in self.conn.execute(
            "SELECT char_a_id, char_b_id FROM relationship_changes "
            "WHERE confirm_status = 'confirmed' AND is_stale = 0 AND is_disabled = 0"
        ).fetchall():
            a_id, b_id = int(r["char_a_id"]), int(r["char_b_id"])
            pair_counts[(min(a_id, b_id), max(a_id, b_id))] += 1
        pair_conflicts = {pair for pair, count in pair_counts.items() if count > 1}
        # 取消“同一人物有多条认知即冲突”的判断；不同内容的记忆可以正常共存。
        return pair_conflicts, set()

    @staticmethod
    def _parse_int_list(raw: object) -> list[int]:
        try:
            values = json.loads(str(raw or "[]"))
        except (TypeError, ValueError):
            return []
        if not isinstance(values, list):
            return []
        return [int(v) for v in values if isinstance(v, (int, str)) and str(v).isdigit()]

    def _chapter_meta(self) -> dict[int, tuple[str, int, str]]:
        rows = self.conn.execute(
            """
            SELECT c.id, c.title, c.story_time FROM chapters c
            JOIN arcs a ON a.id = c.arc_id JOIN volumes v ON v.id = a.volume_id
            ORDER BY v.sort_order ASC, a.sort_order ASC, c.sort_order ASC, c.id ASC
            """
        ).fetchall()
        return {
            int(r["id"]): (str(r["title"] or f"第{idx}章"), idx, str(r["story_time"] or ""))
            for idx, r in enumerate(rows, start=1)
        }

    @staticmethod
    def _format_queue_summary(cat: MemoryItemCategory, r: sqlite3.Row) -> str:
        if cat == "fact":
            return f"[{r['fact_type']}] {r['content']}"
        if cat == "char_state":
            return f"{r['char_name']} · {r['field']} → {r['value']}"
        if cat == "cognitive":
            mtype = str(r["memory_type"] or "secret") if "memory_type" in r.keys() else "secret"
            if mtype == "daily":
                return f"日常认知：{r['secret']}"
            if mtype == "schedule":
                sched_st = (
                    str(r["schedule_status"] or "pending")
                    if "schedule_status" in r.keys()
                    else "pending"
                )
                st_label = {
                    "pending": "待办",
                    "completed": "已完成",
                    "cancelled": "已取消",
                    "expired": "已过期",
                }.get(sched_st, "待办")
                scope = (
                    str(r["time_scope"] or "").strip()
                    if "time_scope" in r.keys()
                    else ""
                )
                scope_part = f"｜{scope}" if scope else ""
                return f"临时安排（{st_label}{scope_part}）：{r['secret']}"
            return f"秘密认知：{r['secret']}"
        if cat == "relationship":
            return f"{r['char_a_name']} ↔ {r['char_b_name']}：{r['rel_type']} (亲密度 {r['intimacy']})"
        if cat == "constraint_check":
            tag = "违反硬约束" if r["verdict"] == "violated" else "约束疑似解除"
            return f"[{tag}] {r['description']}"
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
            "constraint_check": ("constraint_checks", "confirm_status", "description"),
        }
        tbl, st_col, txt_col = table_map[item_type]
        row = self._require_current_memory_item(tbl, item_id, allow_stale=req.action == "discard")
        if req.action == "edit" and item_type == "cognitive":
            new_txt = req.updated_text if req.updated_text is not None else str(row[txt_col])
            new_mtype = (
                req.memory_type
                if req.memory_type is not None
                else str(row["memory_type"] or "secret")
            )
            new_scope = (
                req.time_scope.strip()
                if req.time_scope is not None
                else str(row["time_scope"] or "")
            )
            new_sched = (
                req.schedule_status
                if req.schedule_status is not None
                else str(row["schedule_status"] or "pending")
            )
            new_knowers = (
                self._validate_knower_ids(req.knower_ids)
                if req.knower_ids is not None
                else self._parse_int_list(row["knower_ids"])
            )
            new_learned = (
                req.learned_by.strip()
                if req.learned_by is not None
                else str(row["learned_by"] or "")
            )
            if new_mtype == "schedule" and row["related_record_id"] is None and not new_scope:
                raise AppError("TIME_SCOPE_REQUIRED", "临时安排必须填写适用时间说明", status_code=400)
            changed = (
                new_txt != row[txt_col]
                or new_mtype != str(row["memory_type"] or "secret")
                or new_scope != str(row["time_scope"] or "")
                or new_sched != str(row["schedule_status"] or "pending")
                or new_knowers != self._parse_int_list(row["knower_ids"])
                or new_learned != str(row["learned_by"] or "")
            )
            if changed:
                result = self.conn.execute(
                    """
                    UPDATE cognitive_records
                    SET secret = ?, memory_type = ?, time_scope = ?, schedule_status = ?,
                        knower_ids = ?, learned_by = ?, confirm_status = ?,
                        origin = 'manual', source_hash = NULL, is_stale = 0
                    WHERE id = ? AND is_stale = 0
                    """,
                    (
                        new_txt,
                        new_mtype,
                        new_scope,
                        new_sched if new_mtype == "schedule" else "pending",
                        json.dumps(new_knowers),
                        new_learned,
                        target,
                        item_id,
                    ),
                )
            else:
                result = self.conn.execute(
                    f"UPDATE {tbl} SET {st_col} = ? WHERE id = ? AND is_stale = 0",
                    (target, item_id),
                )
        elif req.action == "edit" and req.updated_text is not None and req.updated_text != row[txt_col]:
            result = self.conn.execute(
                f"UPDATE {tbl} SET {txt_col} = ?, {st_col} = ?, origin = 'manual', "
                f"source_hash = NULL, is_stale = 0 WHERE id = ? AND is_stale = 0",
                (req.updated_text, target, item_id),
            )
        else:
            freshness_filter = "" if req.action == "discard" else " AND is_stale = 0"
            result = self.conn.execute(
                f"UPDATE {tbl} SET {st_col} = ? WHERE id = ?{freshness_filter}", (target, item_id)
            )
        if result.rowcount == 0:
            raise AppError("MEMORY_ITEM_STALE", "该记忆条目已失效，请刷新后处理最新抽取结果", status_code=409)
        if item_type == "fact" and target == "confirmed":
            row = self.conn.execute("SELECT content FROM facts WHERE id = ?", (item_id,)).fetchone()
            if row:
                self.index_fact_fts(item_id, str(row["content"]))
        if item_type == "constraint_check" and target == "confirmed":
            self._apply_constraint_check_verdict(item_id)

    def _require_current_memory_item(
        self, table: str, item_id: int, *, allow_stale: bool = False
    ) -> sqlite3.Row:
        row = self.conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise AppError("MEMORY_ITEM_NOT_FOUND", f"未找到记忆条目 #{item_id}", status_code=404)
        if row["is_stale"] and not allow_stale:
            raise AppError(
                "MEMORY_ITEM_STALE", "该记忆条目已失效，请刷新后处理最新抽取结果", status_code=409
            )
        return row

    def _apply_constraint_check_verdict(self, check_id: int) -> None:
        """Apply a confirmed violation/resolution verdict to the constraint itself."""
        row = self.conn.execute(
            "SELECT constraint_id, chapter_id, verdict FROM constraint_checks WHERE id = ?",
            (check_id,),
        ).fetchone()
        if row is None:
            return
        if row["verdict"] == "violated":
            # The rule still holds for future chapters; flag it for the author's attention.
            self.conn.execute(
                "UPDATE constraints SET status = 'violated' WHERE id = ?",
                (row["constraint_id"],),
            )
        else:
            self.conn.execute(
                """
                UPDATE constraints
                SET status = 'resolved', valid_until_chapter_id = ?
                WHERE id = ?
                """,
                (row["chapter_id"], row["constraint_id"]),
            )

    def batch_update_pending(self, req: BatchQueueActionRequest) -> int:
        count = 0
        single_req = PendingItemUpdateRequest(action=req.action)
        for entry in req.items:
            itype = str(entry.get("item_type", ""))
            iid = int(entry.get("id", 0))
            if itype in ("fact", "char_state", "cognitive", "relationship", "foreshadowing", "constraint_check") and iid > 0:
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
