"""SQLite schema initialization for global.db and per-novel novel.db."""

from __future__ import annotations

import json
import sqlite3

from app.builtin.style_presets import BUILTIN_STYLE_TEMPLATES
from app.core.text_hash import text_sha256
from app.services.embedding.encoder import EMBEDDING_MODEL_ID

GLOBAL_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_profiles (
    id                INTEGER PRIMARY KEY,
    name              TEXT    NOT NULL UNIQUE,
    base_url          TEXT    NOT NULL,
    model             TEXT    NOT NULL,
    api_key_encrypted TEXT    NOT NULL,
    is_default        INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS task_model_assignments (
    task_category   TEXT    PRIMARY KEY,
    profile_id      INTEGER NOT NULL REFERENCES llm_profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT    PRIMARY KEY,
    value       TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prompt_templates (
    id          INTEGER PRIMARY KEY,
    task_type   TEXT    NOT NULL UNIQUE,
    content     TEXT    NOT NULL,
    version     TEXT    NOT NULL DEFAULT '1.0',
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS style_templates (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    is_builtin      INTEGER NOT NULL DEFAULT 0,
    pov             TEXT,
    tense_feel      TEXT,
    tone            TEXT,
    sentence_pref   TEXT,
    dialogue_ratio  TEXT,
    desc_focus      TEXT,
    pacing          TEXT,
    example_paras   TEXT,
    forbidden_exprs TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

NOVEL_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS novels (
    id                  INTEGER PRIMARY KEY,
    title               TEXT    NOT NULL,
    genre               TEXT,
    tone                TEXT,
    pov                 TEXT,
    protagonist_concept TEXT,
    synopsis            TEXT,
    target_words        INTEGER DEFAULT 1000000,
    estimated_chapters  INTEGER,
    words_per_chapter   INTEGER DEFAULT 2500,
    romance_ending      TEXT,
    growth_ending       TEXT,
    ending_note         TEXT,
    style_note          TEXT,
    style_template_id   INTEGER,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS volumes (
    id          INTEGER PRIMARY KEY,
    novel_id    INTEGER NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
    sort_order  REAL    NOT NULL,
    title       TEXT    NOT NULL,
    synopsis    TEXT,
    goal        TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS arcs (
    id              INTEGER PRIMARY KEY,
    volume_id       INTEGER NOT NULL REFERENCES volumes(id) ON DELETE CASCADE,
    sort_order      REAL    NOT NULL,
    title           TEXT    NOT NULL,
    goal            TEXT,
    core_conflict   TEXT,
    start_chapter   INTEGER,
    end_chapter     INTEGER,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chapters (
    id              INTEGER PRIMARY KEY,
    arc_id          INTEGER NOT NULL REFERENCES arcs(id) ON DELETE CASCADE,
    sort_order      REAL    NOT NULL,
    title           TEXT,
    synopsis        TEXT,
    status          TEXT    NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','outline','draft','final')),
    word_count      INTEGER DEFAULT 0,
    content_hash    TEXT,
    continuity_review_required INTEGER NOT NULL DEFAULT 0,
    continuity_dirty_from_chapter_id INTEGER,
    story_time      TEXT,
    locked          INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chapters_arc ON chapters(arc_id, sort_order);

CREATE TABLE IF NOT EXISTS worldview_entries (
    id          INTEGER PRIMARY KEY,
    category    TEXT    NOT NULL
                    CHECK(category IN ('era','city','school','rules','culture','term')),
    content     TEXT    NOT NULL,
    locked      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS characters (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL,
    aliases         TEXT,
    role            TEXT    NOT NULL
                        CHECK(role IN ('female_lead','male_lead','major','minor','extra')),
    gender          TEXT,
    initial_age     TEXT,
    appearance      TEXT,
    personality     TEXT,
    speech_style    TEXT,
    background      TEXT,
    arc_design      TEXT,
    locked          INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS locations (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL,
    aliases         TEXT,
    type            TEXT,
    description     TEXT,
    sensory_details TEXT,
    related_chars   TEXT,
    locked          INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS main_plots (
    id              INTEGER PRIMARY KEY,
    novel_id        INTEGER NOT NULL UNIQUE REFERENCES novels(id) ON DELETE CASCADE,
    core_conflict   TEXT,
    romance_arc     TEXT,
    growth_arc      TEXT,
    key_turning_pts TEXT,
    locked          INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scenes (
    id              INTEGER PRIMARY KEY,
    chapter_id      INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    sort_order      REAL    NOT NULL,
    beat            TEXT,
    pov_character   INTEGER REFERENCES characters(id) ON DELETE SET NULL,
    location_id     INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    character_ids   TEXT,
    story_time      TEXT,
    target_words    INTEGER,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_scenes_chapter ON scenes(chapter_id, sort_order);

CREATE TABLE IF NOT EXISTS chapter_versions (
    id          INTEGER PRIMARY KEY,
    chapter_id  INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    version     INTEGER NOT NULL,
    content     TEXT    NOT NULL,
    source      TEXT    NOT NULL CHECK(source IN ('ai','manual')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chapter_versions ON chapter_versions(chapter_id, version DESC);

CREATE TABLE IF NOT EXISTS character_state_changes (
    id              INTEGER PRIMARY KEY,
    character_id    INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    chapter_id      INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    scene_id        INTEGER REFERENCES scenes(id) ON DELETE SET NULL,
    field           TEXT    NOT NULL
                        CHECK(field IN ('location','body','emotion','goal',
                                        'identity','item','appearance')),
    value           TEXT    NOT NULL,
    source_hash     TEXT,
    origin          TEXT    NOT NULL DEFAULT 'legacy',
    is_stale        INTEGER NOT NULL DEFAULT 0,
    source_quote    TEXT,
    confirm_status  TEXT    NOT NULL DEFAULT 'pending'
                        CHECK(confirm_status IN ('pending','confirmed','discarded')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_char_state ON character_state_changes(character_id, field, chapter_id);

CREATE TABLE IF NOT EXISTS cognitive_records (
    id              INTEGER PRIMARY KEY,
    secret          TEXT    NOT NULL,
    knower_ids      TEXT    NOT NULL,
    chapter_id      INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    learned_by      TEXT,
    source_hash     TEXT,
    origin          TEXT    NOT NULL DEFAULT 'legacy',
    is_stale        INTEGER NOT NULL DEFAULT 0,
    source_quote    TEXT,
    confirm_status  TEXT    NOT NULL DEFAULT 'pending'
                        CHECK(confirm_status IN ('pending','confirmed','discarded')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS relationship_changes (
    id              INTEGER PRIMARY KEY,
    char_a_id       INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    char_b_id       INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    chapter_id      INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    scene_id        INTEGER REFERENCES scenes(id) ON DELETE SET NULL,
    rel_type        TEXT    NOT NULL,
    intimacy        INTEGER,
    publicity       TEXT    CHECK(publicity IN ('public','mutual','one_sided')),
    change_reason   TEXT,
    source_hash     TEXT,
    origin          TEXT    NOT NULL DEFAULT 'legacy',
    is_stale        INTEGER NOT NULL DEFAULT 0,
    source_quote    TEXT,
    confirm_status  TEXT    NOT NULL DEFAULT 'pending'
                        CHECK(confirm_status IN ('pending','confirmed','discarded')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rel_chars ON relationship_changes(char_a_id, char_b_id, chapter_id);

CREATE TABLE IF NOT EXISTS timeline_events (
    id          INTEGER PRIMARY KEY,
    story_time  TEXT    NOT NULL,
    description TEXT    NOT NULL,
    chapter_id  INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS foreshadowing (
    id                  INTEGER PRIMARY KEY,
    description         TEXT    NOT NULL,
    planted_chapter_id  INTEGER REFERENCES chapters(id) ON DELETE SET NULL,
    plan_recover_start  INTEGER,
    plan_recover_end    INTEGER,
    status              TEXT    NOT NULL DEFAULT 'planted'
                            CHECK(status IN ('planted','hinted','recovered','abandoned')),
    related_chapter_ids TEXT,
    source_quote        TEXT,
    source_hash         TEXT,
    origin              TEXT    NOT NULL DEFAULT 'legacy',
    is_stale            INTEGER NOT NULL DEFAULT 0,
    confirm_status      TEXT    NOT NULL DEFAULT 'pending'
                            CHECK(confirm_status IN ('pending','confirmed','discarded')),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS facts (
    id              INTEGER PRIMARY KEY,
    content         TEXT    NOT NULL,
    fact_type       TEXT    NOT NULL,
    entity_ids      TEXT,
    chapter_id      INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    scene_id        INTEGER REFERENCES scenes(id) ON DELETE SET NULL,
    source_quote    TEXT,
    source_hash     TEXT,
    origin          TEXT    NOT NULL DEFAULT 'legacy',
    is_stale        INTEGER NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','confirmed','locked','discarded')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    content,
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS constraints (
    id                      INTEGER PRIMARY KEY,
    target_type             TEXT    NOT NULL
                                CHECK(target_type IN ('character','location','worldview','chapter','novel')),
    target_id               INTEGER,
    content                 TEXT    NOT NULL,
    severity                TEXT    NOT NULL DEFAULT 'hard'
                                CHECK(severity IN ('hard','soft')),
    status                  TEXT    NOT NULL DEFAULT 'active'
                                CHECK(status IN ('active','resolved','violated')),
    valid_from_chapter_id   INTEGER REFERENCES chapters(id) ON DELETE SET NULL,
    valid_until_chapter_id  INTEGER REFERENCES chapters(id) ON DELETE SET NULL,
    source_quote            TEXT,
    locked                  INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS summaries (
    id          INTEGER PRIMARY KEY,
    level       TEXT    NOT NULL CHECK(level IN ('chapter','arc','volume','novel')),
    ref_id      INTEGER NOT NULL,
    content     TEXT    NOT NULL,
    source_hash TEXT,
    is_stale    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(level, ref_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chapters_fts USING fts5(
    content,
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS generation_logs (
    id              INTEGER PRIMARY KEY,
    task_type       TEXT    NOT NULL,
    model           TEXT    NOT NULL,
    template_id     TEXT,
    template_ver    TEXT,
    prompt          TEXT    NOT NULL,
    output          TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    elapsed_ms      INTEGER,
    chapter_id      INTEGER REFERENCES chapters(id) ON DELETE SET NULL,
    scene_id        INTEGER REFERENCES scenes(id) ON DELETE SET NULL,
    temperature     REAL,
    finish_reason   TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_constraints_target ON constraints(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_constraints_status ON constraints(status);

CREATE TABLE IF NOT EXISTS constraint_checks (
    id              INTEGER PRIMARY KEY,
    constraint_id   INTEGER NOT NULL REFERENCES constraints(id) ON DELETE CASCADE,
    chapter_id      INTEGER REFERENCES chapters(id) ON DELETE SET NULL,
    verdict         TEXT    NOT NULL CHECK(verdict IN ('violated','resolved')),
    evidence_quote  TEXT,
    description     TEXT    NOT NULL,
    source_hash     TEXT,
    origin          TEXT    NOT NULL DEFAULT 'legacy',
    is_stale        INTEGER NOT NULL DEFAULT 0,
    confirm_status  TEXT    NOT NULL DEFAULT 'pending'
                        CHECK(confirm_status IN ('pending','confirmed','discarded')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_constraint_checks_status ON constraint_checks(confirm_status);

CREATE TABLE IF NOT EXISTS consistency_reviews (
    id              INTEGER PRIMARY KEY,
    chapter_id      INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    version_id      INTEGER REFERENCES chapter_versions(id) ON DELETE SET NULL,
    content_hash    TEXT,
    upstream_hash   TEXT,
    summary         TEXT    NOT NULL DEFAULT '',
    issue_count     INTEGER NOT NULL DEFAULT 0,
    violation_count INTEGER NOT NULL DEFAULT 0,
    issues_json     TEXT    NOT NULL DEFAULT '[]',
    model           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
-- T5: 场景正文生成后的确定性重复检测记录（只加表，向后兼容；旧库启动时自动建表）
CREATE TABLE IF NOT EXISTS repetition_checks (
    id              INTEGER PRIMARY KEY,
    chapter_id      INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    scene_id        INTEGER REFERENCES scenes(id) ON DELETE SET NULL,
    stage           TEXT    NOT NULL DEFAULT 'initial'
                        CHECK(stage IN ('initial','after_rewrite')),
    triggered       INTEGER NOT NULL DEFAULT 0,
    action_taken    TEXT    NOT NULL DEFAULT 'none'
                        CHECK(action_taken IN ('none','rewritten','kept_with_warning','rewrite_failed')),
    coverage        REAL    NOT NULL DEFAULT 0,
    reasons_json    TEXT    NOT NULL DEFAULT '[]',
    report_json     TEXT    NOT NULL DEFAULT '{}',
    thresholds_json TEXT    NOT NULL DEFAULT '{}',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_repetition_checks_chapter ON repetition_checks(chapter_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_consistency_reviews_chapter ON consistency_reviews(chapter_id);
CREATE INDEX IF NOT EXISTS idx_facts_status   ON facts(status);
CREATE INDEX IF NOT EXISTS idx_facts_entities ON facts(entity_ids);
CREATE INDEX IF NOT EXISTS idx_summaries_ref  ON summaries(level, ref_id);
CREATE INDEX IF NOT EXISTS idx_gen_logs_task  ON generation_logs(task_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_foreshadow_st  ON foreshadowing(status);

CREATE TRIGGER IF NOT EXISTS trg_novels_upd AFTER UPDATE ON novels
    BEGIN UPDATE novels SET updated_at = datetime('now') WHERE id = NEW.id; END;
CREATE TRIGGER IF NOT EXISTS trg_chapters_upd AFTER UPDATE ON chapters
    BEGIN UPDATE chapters SET updated_at = datetime('now') WHERE id = NEW.id; END;
CREATE TRIGGER IF NOT EXISTS trg_scenes_upd AFTER UPDATE ON scenes
    BEGIN UPDATE scenes SET updated_at = datetime('now') WHERE id = NEW.id; END;
CREATE TRIGGER IF NOT EXISTS trg_constraints_upd AFTER UPDATE ON constraints
    BEGIN UPDATE constraints SET updated_at = datetime('now') WHERE id = NEW.id; END;
"""


DEFAULT_APP_SETTINGS: dict[str, object] = {
    "trust_mode": {
        "enabled": True,
        "auto_confirm_facts": True,
        "auto_confirm_foreshadow_hint": True,
        "auto_confirm_char_state": False,
        "auto_confirm_relationship": False,
        "auto_confirm_cognitive": False,
        "auto_confirm_foreshadow_plant_recover": False,
    },
    "embedding": {
        "model_id": EMBEDDING_MODEL_ID,
        "download_source": "modelscope",
    },
}


def init_global_db(conn: sqlite3.Connection) -> None:
    """Create tables and seed built-in style templates & default settings in global.db."""
    conn.executescript(GLOBAL_DB_SCHEMA)
    with conn:
        for tpl in BUILTIN_STYLE_TEMPLATES:
            conn.execute(
                """
                INSERT OR IGNORE INTO style_templates (
                    name, is_builtin, pov, tense_feel, tone, sentence_pref,
                    dialogue_ratio, desc_focus, pacing, example_paras, forbidden_exprs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tpl["name"],
                    tpl["is_builtin"],
                    tpl["pov"],
                    tpl["tense_feel"],
                    tpl["tone"],
                    tpl["sentence_pref"],
                    tpl["dialogue_ratio"],
                    tpl["desc_focus"],
                    tpl["pacing"],
                    json.dumps(tpl["example_paras"], ensure_ascii=False),
                    json.dumps(tpl["forbidden_exprs"], ensure_ascii=False),
                ),
            )
        for key, val in DEFAULT_APP_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                (key, json.dumps(val, ensure_ascii=False)),
            )


def init_novel_db(conn: sqlite3.Connection) -> None:
    """Create all tables, FTS5 virtual tables, indexes, and triggers in a novel.db."""
    conn.executescript(NOVEL_DB_SCHEMA)
    _migrate_external_content_fts(conn)
    _migrate_novel_memory_revision_columns(conn)


def _migrate_external_content_fts(conn: sqlite3.Connection) -> None:
    """Replace incompatible external-content indexes with tokenized internal FTS tables."""
    fts_tables = (
        ("chapters_fts", "chapter_versions"),
        ("facts_fts", "facts"),
    )
    legacy_tables = []
    for fts_table, content_table in fts_tables:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (fts_table,),
        ).fetchone()
        sql = "".join(str(row[0] or "").split()).lower() if row else ""
        if f"content='{content_table}'" in sql or f'content="{content_table}"' in sql:
            legacy_tables.append((fts_table, content_table))

    if not legacy_tables:
        return

    from app.db.repositories.memory_repo import tokenize_for_fts

    conn.execute("BEGIN IMMEDIATE")
    try:
        for fts_table, content_table in legacy_tables:
            rows = conn.execute(
                f'SELECT id, content FROM "{content_table}" ORDER BY id'
            ).fetchall()
            conn.execute(f'DROP TABLE "{fts_table}"')
            conn.execute(
                f"CREATE VIRTUAL TABLE \"{fts_table}\" USING fts5(content, tokenize='unicode61')"
            )
            for row in rows:
                segmented = tokenize_for_fts(str(row[1] or ""))
                if segmented:
                    conn.execute(
                        f'INSERT INTO "{fts_table}"(rowid, content) VALUES (?, ?)',
                        (int(row[0]), segmented),
                    )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _migrate_novel_memory_revision_columns(conn: sqlite3.Connection) -> None:
    columns: dict[str, dict[str, str]] = {
        "chapters": {
            "content_hash": "TEXT",
            "continuity_review_required": "INTEGER NOT NULL DEFAULT 0",
            "continuity_dirty_from_chapter_id": "INTEGER",
        },
        "summaries": {"source_hash": "TEXT"},
        # is_disabled：作者手动停用某条记忆。与 is_stale（被新抽取结果替代、单向）
        # 分开记录，停用可随时恢复，且不会删除原始记录。
        "facts": {
            "source_hash": "TEXT",
            "origin": "TEXT NOT NULL DEFAULT 'legacy'",
            "is_stale": "INTEGER NOT NULL DEFAULT 0",
            "is_disabled": "INTEGER NOT NULL DEFAULT 0",
        },
        "character_state_changes": {
            "source_hash": "TEXT",
            "origin": "TEXT NOT NULL DEFAULT 'legacy'",
            "is_stale": "INTEGER NOT NULL DEFAULT 0",
            "is_disabled": "INTEGER NOT NULL DEFAULT 0",
        },
        "cognitive_records": {
            "source_hash": "TEXT",
            "origin": "TEXT NOT NULL DEFAULT 'legacy'",
            "is_stale": "INTEGER NOT NULL DEFAULT 0",
            "is_disabled": "INTEGER NOT NULL DEFAULT 0",
        },
        "relationship_changes": {
            "source_hash": "TEXT",
            "origin": "TEXT NOT NULL DEFAULT 'legacy'",
            "is_stale": "INTEGER NOT NULL DEFAULT 0",
            "is_disabled": "INTEGER NOT NULL DEFAULT 0",
        },
        "foreshadowing": {
            "source_hash": "TEXT",
            "origin": "TEXT NOT NULL DEFAULT 'legacy'",
            "is_stale": "INTEGER NOT NULL DEFAULT 0",
            "is_disabled": "INTEGER NOT NULL DEFAULT 0",
        },
        "constraint_checks": {
            "source_hash": "TEXT",
            "origin": "TEXT NOT NULL DEFAULT 'legacy'",
            "is_stale": "INTEGER NOT NULL DEFAULT 0",
        },
        "consistency_reviews": {"content_hash": "TEXT", "upstream_hash": "TEXT"},
        # T7：只加可空列、不回填。旧行为 NULL = "当时没有记录"，比编造默认值（如 'stop'）诚实。
        "generation_logs": {"temperature": "REAL", "finish_reason": "TEXT"},
    }
    for table, table_columns in columns.items():
        existing = {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}
        for column, declaration in table_columns.items():
            if column not in existing:
                conn.execute(
                    f'ALTER TABLE "{table}" ADD COLUMN "{column}" {declaration}'
                )

    with conn:
        chapters = conn.execute(
            "SELECT id, status FROM chapters WHERE content_hash IS NULL"
        ).fetchall()
        for chapter in chapters:
            latest = conn.execute(
                "SELECT content FROM chapter_versions WHERE chapter_id = ? "
                "ORDER BY version DESC LIMIT 1",
                (int(chapter["id"]),),
            ).fetchone()
            content = str(latest["content"] or "") if latest else ""
            if content:
                conn.execute(
                    "UPDATE chapters SET content_hash = ? WHERE id = ?",
                    (text_sha256(content), int(chapter["id"])),
                )

        conn.execute(
            "UPDATE summaries SET is_stale = 1 WHERE level = 'chapter' AND source_hash IS NULL"
        )

        artifact_specs = (
            ("facts", "chapter_id", "source_quote"),
            ("character_state_changes", "chapter_id", "source_quote"),
            ("cognitive_records", "chapter_id", "source_quote"),
            ("relationship_changes", "chapter_id", "source_quote"),
            ("foreshadowing", "planted_chapter_id", "source_quote"),
            ("constraint_checks", "chapter_id", "evidence_quote"),
        )
        for table, chapter_column, quote_column in artifact_specs:
            rows = conn.execute(
                f"SELECT id, \"{chapter_column}\" AS chapter_id, \"{quote_column}\" AS source_quote "
                f"FROM \"{table}\" WHERE source_hash IS NULL AND is_stale = 0"
            ).fetchall()
            for row in rows:
                chapter_id = row["chapter_id"]
                if chapter_id is None:
                    conn.execute(
                        f"UPDATE \"{table}\" SET origin = 'manual' WHERE id = ?",
                        (int(row["id"]),),
                    )
                    continue
                chapter = conn.execute(
                    "SELECT c.status, c.content_hash, cv.content FROM chapters c "
                    "LEFT JOIN chapter_versions cv ON cv.id = ("
                    "SELECT v.id FROM chapter_versions v WHERE v.chapter_id = c.id "
                    "ORDER BY v.version DESC, v.id DESC LIMIT 1) "
                    "WHERE c.id = ?",
                    (int(chapter_id),),
                ).fetchone()
                quote = str(row["source_quote"] or "").strip()
                if (
                    chapter
                    and chapter["status"] == "final"
                    and quote
                    and quote in str(chapter["content"] or "")
                ):
                    conn.execute(
                        f"UPDATE \"{table}\" SET source_hash = ?, origin = 'extracted' WHERE id = ?",
                        (str(chapter["content_hash"]), int(row["id"])),
                    )
                else:
                    conn.execute(
                        f"UPDATE \"{table}\" SET origin = 'legacy', is_stale = 1 WHERE id = ?",
                        (int(row["id"]),),
                    )
