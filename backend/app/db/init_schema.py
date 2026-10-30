"""SQLite schema initialization for global.db and per-novel novel.db."""

from __future__ import annotations

import json
import sqlite3

from app.builtin.style_presets import BUILTIN_STYLE_TEMPLATES

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
    status          TEXT    NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','confirmed','locked','discarded')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    content,
    content='facts',
    content_rowid='id',
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS summaries (
    id          INTEGER PRIMARY KEY,
    level       TEXT    NOT NULL CHECK(level IN ('chapter','arc','volume','novel')),
    ref_id      INTEGER NOT NULL,
    content     TEXT    NOT NULL,
    is_stale    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(level, ref_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chapters_fts USING fts5(
    content,
    content='chapter_versions',
    content_rowid='id',
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
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

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
        "model_id": "bge-m3-onnx-int8",
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
