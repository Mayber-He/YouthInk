"""T12 fixed #81 replay and deterministic injection limits; no live model."""
import hashlib
import json
from pathlib import Path

from app.services.memory.extraction_parse import parse_extraction_items

FIXTURES = Path(__file__).parent / "fixtures"


def test_log81_fixture_identity_and_replay():
    provenance = json.loads((FIXTURES / "memory_extract_log81_provenance.json").read_text(encoding="utf-8"))
    assert provenance["generation_log_id"] == 81
    assert provenance["chapter_version"] == 10
    output = (FIXTURES / "memory_extract_log81_output.json").read_text(encoding="utf-8")
    chapter = (FIXTURES / "memory_extract_log81_chapter_v10.txt").read_text(encoding="utf-8")
    assert len(output) == provenance["output_chars"] == 8519
    assert len(chapter) == provenance["chapter_chars"] == 2779
    assert hashlib.sha256(output.encode()).hexdigest() == provenance["output_sha256"] == "720ad7943c41b2c5fde6c439f84449a47cf59b5d78ffb66790c208e4fac7a1d5"
    assert hashlib.sha256(chapter.encode()).hexdigest() == provenance["chapter_sha256"] == "448a1ee39ea3d32f14e86329ff18ee7782bc75e062aa2ecbf386135ebd1f61ca"
    assert provenance["source"] == "docs/loop/eval_export.md"
    assert provenance["output_section"] == 4 and provenance["chapter_section"] == 1
    parsed = parse_extraction_items(output, chapter)
    assert parsed.raw_items == 43
    assert len(parsed.output.facts) == 15  # Unedited verbose output, not a fabricated compact response.
    assert len(parsed.output.foreshadowing) == 4
    from app.services.context.memory_selection import select_memory_rows
    selected = select_memory_rows([{"content": f.content} for f in parsed.output.facts], [], "content", 6)
    assert len(selected) == 6
    assert all(row["content"] in {f.content for f in parsed.output.facts} for row in selected)


def test_extraction_prompt_requires_durable_compact_memories():
    from app.services.memory.finalizer import MEMORY_EXTRACTION_SCHEMA_GUIDE
    for text in ["最多 8 条", "关系变化", "承诺", "秘密", "关键物品", "地点状态", "看相册", "收藏照片", "同义内容只保留一条", "明确回收可能"]:
        assert text in MEMORY_EXTRACTION_SCHEMA_GUIDE


def test_selection_caps_deduplicates_and_removes_complete_summary_clauses():
    from app.services.context.memory_selection import select_memory_rows
    rows = [{"content": "已  承诺，保密。"}, {"content": "已承诺,保密."}, {"content": "摘要已有事实"}]
    rows += [{"content": f"新事实{i}"} for i in range(10)]
    selected = select_memory_rows(rows, ["摘要已有事实。以及其他事件。"], "content", 6)
    assert [r["content"] for r in selected] == ["已  承诺，保密。"] + [f"新事实{i}" for i in range(5)]
    assert select_memory_rows([], [], "content", 6) == []
    assert select_memory_rows([{"description": "摘要已有事实"}], ["摘要已有事实"], "description", 4) == []


def test_summary_partial_matches_preserve_negation_and_different_subjects():
    from app.services.context.memory_selection import select_memory_rows
    rows = [{"content": "承诺保密"}, {"content": "江澈承诺保密"}]
    summaries = ["他拒绝承诺保密。", "裴南栀说江澈承诺保密。", "裴南栀否认这个说法：江澈承诺保密。"]
    assert select_memory_rows(rows, summaries, "content", 6) == rows


from test_repetition_guard import client, two_chapters


def test_injection_prioritizes_recent_then_locked_and_caps(client, two_chapters):
    from app.db.manager import get_novel_db
    uid, previous, current, scene = two_chapters
    with get_novel_db(uid) as conn:
        conn.execute("UPDATE chapters SET status='final', continuity_review_required=0 WHERE id=?", (previous,))
        conn.execute("INSERT INTO summaries(level,ref_id,content,source_hash) SELECT 'chapter',id,'摘要重复事实',content_hash FROM chapters WHERE id=?", (previous,))
        for i in range(8):
            conn.execute("INSERT INTO facts(content,fact_type,chapter_id,origin,status) VALUES(?,'event',?,'manual','confirmed')", (f"近章事实{i}", previous))
        conn.execute("INSERT INTO facts(content,fact_type,chapter_id,origin,status) VALUES('近章重要承诺','event',?,'manual','locked')", (previous,))
        conn.execute("INSERT INTO facts(content,fact_type,chapter_id,origin,status) VALUES('后插入的普通事实','event',?,'manual','confirmed')", (previous,))
        conn.execute("INSERT INTO facts(content,fact_type,chapter_id,origin,status) VALUES('摘要重复事实','event',?,'manual','locked')", (previous,))
        conn.execute("INSERT INTO facts(content,fact_type,chapter_id,origin,status) VALUES('无章节旧事实','event',NULL,'manual','locked')")
        for i in range(6):
            conn.execute("INSERT INTO foreshadowing(description,origin,confirm_status) VALUES(?,'manual','confirmed')", (f"待回收线索{i}",))
        conn.execute("INSERT INTO foreshadowing(description,origin,confirm_status) VALUES('摘要重复事实','manual','confirmed')")
        conn.commit()
    result = client.get(f"/api/v1/novels/{uid}/chapters/{current}/context-preview").json()
    block = next(b for b in result["blocks"] if b["key"] == "foreshadowing_and_facts")["content"]
    facts = [line for line in block.splitlines() if "[已确认事实]" in line]
    assert len(facts) == 6
    assert "近章重要承诺" in facts[0]
    assert "无章节旧事实" not in block
    assert "摘要重复事实" not in block
    assert len([line for line in block.splitlines() if "[伏笔-" in line]) == 4


def test_empty_memory_context_is_explicit(client, two_chapters):
    uid, previous, current, scene = two_chapters
    result = client.get(f"/api/v1/novels/{uid}/chapters/{current}/context-preview").json()
    block = next(b for b in result["blocks"] if b["key"] == "foreshadowing_and_facts")
    assert block["content"] == "暂无待回收伏笔或历史事实"


def test_disabling_summaries_preserves_matching_memories(client, two_chapters):
    from app.db.manager import get_novel_db
    uid, previous, current, scene = two_chapters
    with get_novel_db(uid) as conn:
        conn.execute("UPDATE chapters SET status='final', continuity_review_required=0 WHERE id=?", (previous,))
        conn.execute("INSERT INTO summaries(level,ref_id,content,source_hash) SELECT 'chapter',id,'共同承诺与待回收线索',content_hash FROM chapters WHERE id=?", (previous,))
        conn.execute("INSERT INTO facts(content,fact_type,chapter_id,origin,status) VALUES('共同承诺','event',?,'manual','confirmed')", (previous,))
        conn.execute("INSERT INTO foreshadowing(description,origin,confirm_status) VALUES('待回收线索','manual','confirmed')")
        conn.commit()
    result = client.get(
        f"/api/v1/novels/{uid}/chapters/{current}/context-preview",
        params={"disabled_keys": "summaries_and_prev"},
    ).json()
    assert not next(b for b in result["blocks"] if b["key"] == "summaries_and_prev")["enabled"]
    block = next(b for b in result["blocks"] if b["key"] == "foreshadowing_and_facts")["content"]
    assert "共同承诺" in block and "待回收线索" in block
