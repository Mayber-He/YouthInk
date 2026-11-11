"""Temporal query helper for character state, relationship, and character memory timeline (Dev Doc 4.3)."""

from __future__ import annotations

import json
import re
import sqlite3

from app.schemas.entities import CharacterResponse, CharacterTimelineSnapshot

_STOP_BIGRAMS = {"今天", "明天", "已经", "完成", "取消", "过期", "安排", "日程", "待办", "结束"}


def _bigrams(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "", text or "")
    if len(cleaned) < 2:
        return {cleaned} if cleaned else set()
    return {
        cleaned[i : i + 2]
        for i in range(len(cleaned) - 1)
        if cleaned[i : i + 2] not in _STOP_BIGRAMS
    }


def match_pending_schedule_id(
    candidates: list[dict[str, object]],
    knower_ids: list[int],
    secret: str,
    time_scope: str = "",
) -> int | None:
    """Match a follow-up schedule completion/cancellation/expiration to an earlier pending schedule."""
    knower_set = set(knower_ids)
    shared = [
        c
        for c in candidates
        if c.get("memory_type") == "schedule"
        and (c.get("effective_schedule_status") or c.get("schedule_status")) == "pending"
        and set(c.get("knower_ids") or []) & knower_set  # type: ignore[arg-type]
    ]
    if not shared:
        return None
    target_grams = _bigrams(f"{secret} {time_scope}")
    best_id: int | None = None
    best_score = 0
    for cand in shared:
        cand_grams = _bigrams(f"{cand.get('secret', '')} {cand.get('time_scope', '')}")
        score = len(target_grams & cand_grams)
        if score >= best_score and score > 0:
            best_score = score
            best_id = int(cand["id"])  # type: ignore[arg-type]
    if best_id is not None:
        return best_id
    if len(shared) == 1:
        return int(shared[0]["id"])  # type: ignore[arg-type]
    return None


def query_character_memories(
    conn: sqlite3.Connection,
    *,
    character_id: int | None = None,
    up_to_chapter_sort: float | None = None,
    memory_type: str | None = None,
    include_disabled: bool = True,
    include_pending: bool = False,
) -> list[dict[str, object]]:
    """Query character memories with temporal filtering and schedule status resolution."""
    chapter_rows = conn.execute(
        """
        SELECT c.id, c.title, c.sort_order, c.story_time
        FROM chapters c
        JOIN arcs a ON a.id = c.arc_id
        JOIN volumes v ON v.id = a.volume_id
        ORDER BY v.sort_order ASC, a.sort_order ASC, c.sort_order ASC, c.id ASC
        """
    ).fetchall()
    chapter_meta: dict[int, dict[str, object]] = {
        int(r["id"]): {
            "title": str(r["title"] or f"第{idx}章"),
            "display_index": idx,
            "sort_order": float(r["sort_order"]),
            "story_time": str(r["story_time"] or ""),
        }
        for idx, r in enumerate(chapter_rows, start=1)
    }
    char_names = {
        int(r["id"]): str(r["name"])
        for r in conn.execute("SELECT id, name FROM characters").fetchall()
    }

    status_clause = (
        "cg.confirm_status IN ('pending', 'confirmed')"
        if include_pending
        else "cg.confirm_status = 'confirmed'"
    )
    sort_clause = (
        "AND (cg.chapter_id IS NULL OR c.sort_order <= ?)"
        if up_to_chapter_sort is not None
        else ""
    )
    params: tuple[object, ...] = (
        (up_to_chapter_sort,) if up_to_chapter_sort is not None else ()
    )

    rows = conn.execute(
        f"""
        SELECT cg.*, c.title AS chapter_title, c.sort_order, c.story_time
        FROM cognitive_records cg
        LEFT JOIN chapters c ON c.id = cg.chapter_id
        WHERE {status_clause}
          AND cg.is_stale = 0
          AND (cg.chapter_id IS NULL OR cg.origin = 'manual' OR
               (cg.origin = 'extracted' AND cg.source_hash = c.content_hash
                AND c.status = 'final' AND c.continuity_review_required = 0))
          {sort_clause}
        ORDER BY COALESCE(c.sort_order, -1.0) ASC, cg.id ASC
        """,
        params,
    ).fetchall()

    base_records: list[dict[str, object]] = []
    base_by_id: dict[int, dict[str, object]] = {}
    followup_rows: list[sqlite3.Row] = []

    for r in rows:
        mtype = str(r["memory_type"] or "secret")
        sched_status = str(r["schedule_status"] or "pending")
        rel_id = r["related_record_id"]
        if mtype == "schedule" and (
            rel_id is not None or sched_status in ("completed", "cancelled", "expired")
        ):
            followup_rows.append(r)
            continue

        knowers: list[int] = [
            int(k)
            for k in json.loads(r["knower_ids"] or "[]")
            if isinstance(k, (int, str)) and str(k).isdigit()
        ]
        cid = int(r["chapter_id"]) if r["chapter_id"] is not None else None
        ch_info = chapter_meta.get(cid or 0, {})
        disabled = bool(r["is_disabled"])
        c_status = str(r["confirm_status"] or "pending")
        rec: dict[str, object] = {
            "id": int(r["id"]),
            "secret": str(r["secret"]),
            "content": str(r["secret"]),
            "memory_type": mtype,
            "time_scope": str(r["time_scope"] or ""),
            "schedule_status": sched_status if mtype == "schedule" else "pending",
            "effective_schedule_status": sched_status if mtype == "schedule" else "pending",
            "related_record_id": int(rel_id) if rel_id is not None else None,
            "knower_ids": knowers,
            "knower_names": [char_names.get(k, str(k)) for k in knowers],
            "learned_by": str(r["learned_by"] or ""),
            "chapter_id": cid,
            "chapter_title": str(ch_info.get("title") or r["chapter_title"] or ""),
            "chapter_display_index": ch_info.get("display_index"),
            "chapter_sort_order": r["sort_order"],
            "story_time": str(r["story_time"] or ""),
            "source_quote": str(r["source_quote"] or ""),
            "origin": str(r["origin"] or "legacy"),
            "confirm_status": c_status,
            "is_disabled": disabled,
            "is_stale": bool(r["is_stale"]),
            "is_effective": c_status == "confirmed" and not disabled,
            "resolved_chapter_id": None,
            "resolved_chapter_title": "",
            "resolved_chapter_display_index": None,
            "resolved_story_time": "",
            "resolved_quote": "",
            "resolution_record_id": None,
            "created_at": str(r["created_at"] or ""),
        }
        base_records.append(rec)
        base_by_id[int(r["id"])] = rec

    for r in followup_rows:
        knowers = [
            int(k)
            for k in json.loads(r["knower_ids"] or "[]")
            if isinstance(k, (int, str)) and str(k).isdigit()
        ]
        rel_id = int(r["related_record_id"]) if r["related_record_id"] is not None else None
        target = base_by_id.get(rel_id) if rel_id is not None else None
        if target is None:
            matched_id = match_pending_schedule_id(
                base_records,
                knowers,
                str(r["secret"] or ""),
                str(r["time_scope"] or ""),
            )
            if matched_id is not None:
                target = base_by_id.get(matched_id)

        disabled = bool(r["is_disabled"])
        c_status = str(r["confirm_status"] or "pending")
        cid = int(r["chapter_id"]) if r["chapter_id"] is not None else None
        ch_info = chapter_meta.get(cid or 0, {})

        if target is not None:
            # 只有已确认且未停用的后续记录才会更新原临时安排在当前观测节点的状态
            if c_status == "confirmed" and not disabled:
                new_st = str(r["schedule_status"] or "completed")
                target["effective_schedule_status"] = new_st
                target["resolved_chapter_id"] = cid
                target["resolved_chapter_title"] = str(
                    ch_info.get("title") or r["chapter_title"] or ""
                )
                target["resolved_chapter_display_index"] = ch_info.get("display_index")
                target["resolved_story_time"] = str(r["story_time"] or "")
                target["resolved_quote"] = str(r["source_quote"] or "")
                target["resolution_record_id"] = int(r["id"])
        else:
            # 独立无前置待办的已完成/取消/过期安排记录
            sched_st = str(r["schedule_status"] or "completed")
            rec = {
                "id": int(r["id"]),
                "secret": str(r["secret"]),
                "content": str(r["secret"]),
                "memory_type": "schedule",
                "time_scope": str(r["time_scope"] or ""),
                "schedule_status": sched_st,
                "effective_schedule_status": sched_st,
                "related_record_id": rel_id,
                "knower_ids": knowers,
                "knower_names": [char_names.get(k, str(k)) for k in knowers],
                "learned_by": str(r["learned_by"] or ""),
                "chapter_id": cid,
                "chapter_title": str(ch_info.get("title") or r["chapter_title"] or ""),
                "chapter_display_index": ch_info.get("display_index"),
                "chapter_sort_order": r["sort_order"],
                "story_time": str(r["story_time"] or ""),
                "source_quote": str(r["source_quote"] or ""),
                "origin": str(r["origin"] or "legacy"),
                "confirm_status": c_status,
                "is_disabled": disabled,
                "is_stale": bool(r["is_stale"]),
                "is_effective": c_status == "confirmed" and not disabled,
                "resolved_chapter_id": cid,
                "resolved_chapter_title": str(
                    ch_info.get("title") or r["chapter_title"] or ""
                ),
                "resolved_chapter_display_index": ch_info.get("display_index"),
                "resolved_story_time": str(r["story_time"] or ""),
                "resolved_quote": str(r["source_quote"] or ""),
                "resolution_record_id": int(r["id"]),
                "created_at": str(r["created_at"] or ""),
            }
            base_records.append(rec)

    results: list[dict[str, object]] = []
    for rec in base_records:
        if character_id is not None and character_id not in (rec["knower_ids"] or []):  # type: ignore[operator]
            continue
        if memory_type and rec["memory_type"] != memory_type:
            continue
        if not include_disabled and rec["is_disabled"]:
            continue
        results.append(rec)
    return results


def build_character_timeline_snapshot(
    conn: sqlite3.Connection,
    char: CharacterResponse,
    up_to_chapter_sort: float | None = None,
) -> CharacterTimelineSnapshot:
    """
    Compute temporal state, relationships, and character memories for a character
    at chapter.sort_order <= up_to_chapter_sort (Dev Doc 4.2 & 4.3).
    Only 'confirmed' records are included in known_secrets; character_memories
    also retains disabled records so the timeline UI can restore them.
    """
    char_id = char.id
    sort_filter = "AND c.sort_order <= ?" if up_to_chapter_sort is not None else ""
    params: tuple[object, ...] = (
        (char_id, up_to_chapter_sort) if up_to_chapter_sort is not None else (char_id,)
    )

    state_rows = conn.execute(
        f"""
        SELECT s.field, s.value, s.chapter_id, c.sort_order, c.story_time,
               s.id, s.is_disabled
        FROM character_state_changes s
        JOIN chapters c ON c.id = s.chapter_id
        WHERE s.character_id = ? AND s.confirm_status = 'confirmed' AND s.is_stale = 0
          AND (s.origin = 'manual' OR (s.origin = 'extracted' AND s.source_hash = c.content_hash
               AND c.status = 'final' AND c.continuity_review_required = 0)) {sort_filter}
        ORDER BY c.sort_order DESC, s.id DESC
        """,
        params,
    ).fetchall()

    current_states: dict[str, str] = {}
    state_sources: dict[str, dict[str, object]] = {}
    seen_fields: set[str] = set()
    for r in state_rows:
        fld = str(r["field"])
        if fld in seen_fields:
            continue
        seen_fields.add(fld)
        # 最新一条被作者停用时不回退到更早的旧状态。
        if r["is_disabled"]:
            continue
        current_states[fld] = str(r["value"])
        state_sources[fld] = {
            "chapter_id": int(r["chapter_id"]),
            "chapter_sort_order": r["sort_order"],
            "story_time": str(r["story_time"] or ""),
        }

    effective_appearance = char.appearance
    if "appearance" in current_states:
        effective_appearance = (
            f"{char.appearance}（近期变化：{current_states['appearance']}）".strip()
        )

    rel_params: tuple[object, ...] = (
        (char_id, char_id, up_to_chapter_sort)
        if up_to_chapter_sort is not None
        else (char_id, char_id)
    )
    rel_rows = conn.execute(
        f"""
        SELECT r.*, c.sort_order, c.story_time,
               ca.name AS char_a_name, cb.name AS char_b_name
        FROM relationship_changes r
        JOIN chapters c ON c.id = r.chapter_id
        JOIN characters ca ON ca.id = r.char_a_id
        JOIN characters cb ON cb.id = r.char_b_id
        WHERE (r.char_a_id = ? OR r.char_b_id = ?) AND r.confirm_status = 'confirmed' {sort_filter}
          AND r.is_stale = 0
          AND (r.origin = 'manual' OR (r.origin = 'extracted' AND r.source_hash = c.content_hash
               AND c.status = 'final' AND c.continuity_review_required = 0))
        ORDER BY c.sort_order DESC, r.id DESC
        """,
        rel_params,
    ).fetchall()

    seen_pairs: set[tuple[int, int]] = set()
    relationships: list[dict[str, object]] = []
    for r in rel_rows:
        a_id, b_id = int(r["char_a_id"]), int(r["char_b_id"])
        pair = (min(a_id, b_id), max(a_id, b_id))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        # 同一对人物只看最新一条；最新一条被停用时不再回退到旧关系。
        if r["is_disabled"]:
            continue
        relationships.append(
            {
                "char_a_id": a_id,
                "char_a_name": str(r["char_a_name"]),
                "char_b_id": b_id,
                "char_b_name": str(r["char_b_name"]),
                "rel_type": str(r["rel_type"]),
                "intimacy": r["intimacy"],
                "publicity": r["publicity"],
                "change_reason": r["change_reason"],
                "chapter_id": int(r["chapter_id"]),
                "chapter_sort_order": r["sort_order"],
                "story_time": str(r["story_time"] or ""),
            }
        )

    all_char_memories = query_character_memories(
        conn,
        character_id=char_id,
        up_to_chapter_sort=up_to_chapter_sort,
        include_disabled=True,
        include_pending=False,
    )
    known_secrets = [m for m in all_char_memories if not m.get("is_disabled")]

    return CharacterTimelineSnapshot(
        character_id=char_id,
        up_to_chapter_sort=up_to_chapter_sort,
        effective_appearance=effective_appearance,
        current_states=current_states,
        state_sources=state_sources,
        relationships=relationships,
        known_secrets=known_secrets,
        character_memories=all_char_memories,
    )
