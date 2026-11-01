"""T8 resolution evidence must be literal; extraction never disables constraints."""
import json
import sqlite3

import pytest

from app.core.exceptions import AppError
from app.db.init_schema import init_novel_db
from app.db.repositories.constraint_repo import ConstraintRepository
from app.services.memory.extraction_parse import parse_extraction_items
from app.services.memory.finalizer import ChapterFinalizerService, MEMORY_EXTRACTION_SCHEMA_GUIDE


@pytest.mark.parametrize("quote", ["她已经熟悉校园。", "她 已经熟悉校园。", "她已经熟悉校园", "她已经熟悉校园！"])
def test_resolution_requires_literal_evidence(quote):
    chapter = "一个月后，她已经熟悉校园。"
    result = parse_extraction_items(json.dumps({"constraint_checks": [{
        "constraint_id": 1, "verdict": "resolved", "evidence_quote": quote,
        "description": "正式解除陌生校园约束",
    }]}, ensure_ascii=False), chapter)
    assert bool(result.output.constraint_checks) == (quote in chapter)


@pytest.mark.parametrize("description", ["本章未涉及，未违反。", "本章没有违反该约束。"])
def test_non_involvement_is_not_resolution(description):
    result = parse_extraction_items(json.dumps({"constraint_checks": [{
        "constraint_id": 1, "verdict": "resolved", "evidence_quote": "他在家里。",
        "description": description,
    }]}, ensure_ascii=False), "他在家里。")
    assert result.output.constraint_checks == []


def test_resolution_prompt_excludes_uninvolved_constraints():
    assert "剧情已正式解除" in MEMORY_EXTRACTION_SCHEMA_GUIDE
    assert "本章未涉及/未违反" in MEMORY_EXTRACTION_SCHEMA_GUIDE


def test_repository_rejects_invented_resolution():
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    init_novel_db(conn)
    conn.execute("INSERT INTO novels(id,title) VALUES(1,'测试')")
    conn.execute("INSERT INTO volumes(id,novel_id,title,sort_order) VALUES(1,1,'卷',1)")
    conn.execute("INSERT INTO arcs(id,volume_id,title,sort_order) VALUES(1,1,'弧',1)")
    conn.execute("INSERT INTO chapters(id,arc_id,title,sort_order) VALUES(1,1,'一',1)")
    conn.execute("INSERT INTO chapter_versions(chapter_id,version,content,source) VALUES(1,1,'她熟悉校园。','manual')")
    conn.execute("INSERT INTO constraints(id,target_type,content) VALUES(1,'novel','陌生校园')")
    repo = ConstraintRepository(conn)
    with pytest.raises(AppError):
        repo.create_constraint_check(1,1,'resolved','她已熟悉校园。','解除')
    repo.create_constraint_check(1,1,'resolved','她熟悉校园。','正式解除')
    row=conn.execute('SELECT * FROM constraint_checks').fetchone()
    assert row['confirm_status']=='pending'
    assert repo.get_constraint(1).status=='active'
    conn.close()



def test_actual_extraction_prompt_does_not_require_checks_for_every_constraint():
    prompt = ChapterFinalizerService._build_extraction_prompt(None, "一", "正文", [], "[#1]陌生校园")
    assert "必须逐条判定" not in prompt
    assert "未涉及/未违反" in prompt



def test_resolution_accepts_source_quote_and_prior_non_violation():
    result = parse_extraction_items(json.dumps({"constraint_checks": [{
        "constraint_id": 1, "verdict": "resolved", "source_quote": "禁令正式解除。",
        "description": "此前未违反，但本章禁令已正式解除",
    }]}, ensure_ascii=False), "禁令正式解除。")
    assert len(result.output.constraint_checks) == 1
