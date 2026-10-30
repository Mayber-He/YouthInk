"""Temporal query helper for character state, relationship, and cognitive timeline (Dev Doc 4.3)."""

from __future__ import annotations

import json
import sqlite3

from app.schemas.entities import CharacterResponse, CharacterTimelineSnapshot


def build_character_timeline_snapshot(
    conn: sqlite3.Connection,
    char: CharacterResponse,
    up_to_chapter_sort: float | None = None,
) -> CharacterTimelineSnapshot:
    """
    Compute temporal state, relationships, and known secrets for a character
    at chapter.sort_order <= up_to_chapter_sort (Dev Doc 4.2 & 4.3).
    Only 'confirmed' records are included.
    """
    char_id = char.id
    sort_filter = "AND c.sort_order <= ?" if up_to_chapter_sort is not None else ""
    params: tuple[object, ...] = (
        (char_id, up_to_chapter_sort) if up_to_chapter_sort is not None else (char_id,)
    )

    state_rows = conn.execute(
        f"""
        SELECT s.field, s.value, c.sort_order, s.id
        FROM character_state_changes s
        JOIN chapters c ON c.id = s.chapter_id
        WHERE s.character_id = ? AND s.confirm_status = 'confirmed' {sort_filter}
        ORDER BY c.sort_order DESC, s.id DESC
        """,
        params,
    ).fetchall()

    current_states: dict[str, str] = {}
    for r in state_rows:
        fld = str(r["field"])
        if fld not in current_states:
            current_states[fld] = str(r["value"])

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
        SELECT r.*, c.sort_order, ca.name AS char_a_name, cb.name AS char_b_name
        FROM relationship_changes r
        JOIN chapters c ON c.id = r.chapter_id
        JOIN characters ca ON ca.id = r.char_a_id
        JOIN characters cb ON cb.id = r.char_b_id
        WHERE (r.char_a_id = ? OR r.char_b_id = ?) AND r.confirm_status = 'confirmed' {sort_filter}
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
            }
        )

    cog_params: tuple[object, ...] = (
        (up_to_chapter_sort,) if up_to_chapter_sort is not None else ()
    )
    cog_rows = conn.execute(
        f"""
        SELECT cg.secret, cg.knower_ids, cg.learned_by, c.title AS chapter_title
        FROM cognitive_records cg
        LEFT JOIN chapters c ON c.id = cg.chapter_id
        WHERE cg.confirm_status = 'confirmed' {sort_filter if up_to_chapter_sort is not None else ''}
        ORDER BY cg.id ASC
        """,
        cog_params,
    ).fetchall()

    known_secrets: list[dict[str, object]] = []
    for cg in cog_rows:
        knowers: list[int] = json.loads(cg["knower_ids"] or "[]")
        if char_id in knowers:
            known_secrets.append(
                {
                    "secret": str(cg["secret"]),
                    "learned_by": cg["learned_by"],
                    "chapter_title": cg["chapter_title"],
                }
            )

    return CharacterTimelineSnapshot(
        character_id=char_id,
        up_to_chapter_sort=up_to_chapter_sort,
        effective_appearance=effective_appearance,
        current_states=current_states,
        relationships=relationships,
        known_secrets=known_secrets,
    )
