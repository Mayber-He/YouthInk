"""Queue actions preserve extraction provenance and reject obsolete evidence."""
import sqlite3

import pytest

from app.core.exceptions import AppError
from app.db.init_schema import init_novel_db
from app.db.repositories.memory_repo import MemoryRepository
from app.db.repositories.novel_repo import NovelRepository
from app.schemas.memory import BatchQueueActionRequest, ForeshadowUpdate, PendingItemUpdateRequest


SPECS = {
    "fact": ("facts", "status", "content"),
    "char_state": ("character_state_changes", "confirm_status", "value"),
    "cognitive": ("cognitive_records", "confirm_status", "secret"),
    "relationship": ("relationship_changes", "confirm_status", "rel_type"),
    "foreshadowing": ("foreshadowing", "confirm_status", "description"),
    "constraint_check": ("constraint_checks", "confirm_status", "description"),
}


@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_novel_db(conn)
    conn.execute("INSERT INTO novels(id,title) VALUES(1,'测试')")
    conn.execute("INSERT INTO volumes(id,novel_id,title,sort_order) VALUES(1,1,'卷',1)")
    conn.execute("INSERT INTO arcs(id,volume_id,title,sort_order) VALUES(1,1,'弧',1)")
    conn.execute("INSERT INTO chapters(id,arc_id,title,sort_order) VALUES(1,1,'章',1)")
    conn.execute("INSERT INTO characters(id,name,role) VALUES(1,'甲','major'),(2,'乙','minor')")
    conn.execute("INSERT INTO constraints(id,target_type,content) VALUES(1,'novel','禁令')")
    conn.execute("INSERT INTO facts(id,chapter_id,content,fact_type) VALUES(1,1,'原文','event')")
    conn.execute("INSERT INTO character_state_changes(id,character_id,chapter_id,field,value) VALUES(1,1,1,'emotion','原文')")
    conn.execute("INSERT INTO cognitive_records(id,chapter_id,secret,knower_ids) VALUES(1,1,'原文','[1]')")
    conn.execute("INSERT INTO relationship_changes(id,char_a_id,char_b_id,chapter_id,rel_type) VALUES(1,1,2,1,'原文')")
    conn.execute("INSERT INTO foreshadowing(id,planted_chapter_id,description) VALUES(1,1,'原文')")
    conn.execute("INSERT INTO constraint_checks(id,constraint_id,chapter_id,verdict,description) VALUES(1,1,1,'resolved','原文')")
    for table, _, _ in SPECS.values():
        conn.execute(f"UPDATE {table} SET origin='extracted', source_hash='hash-v1'")
    conn.commit()
    yield MemoryRepository(conn)
    conn.close()


def row(repo, kind):
    return repo.conn.execute(f"SELECT * FROM {SPECS[kind][0]} WHERE id=1").fetchone()


@pytest.mark.parametrize("kind", SPECS)
@pytest.mark.parametrize("status,is_stale,expected", [
    ("pending", 0, 1),
    ("pending", 1, 0),
    ("confirmed", 0, 0),
    ("discarded", 0, 0),
])
def test_novel_pending_count_matches_visible_queue(repo, kind, status, is_stale, expected):
    for table, _, _ in SPECS.values():
        repo.conn.execute(f"UPDATE {table} SET is_stale=1")
    table, status_col, _ = SPECS[kind]
    repo.conn.execute(f"UPDATE {table} SET {status_col}=?, is_stale=?", (status, is_stale))

    detail = NovelRepository(repo.conn, "test").get_novel_detail()
    assert detail.pending_confirm_count == expected
    assert detail.pending_confirm_count == len(repo.list_pending_queue())


@pytest.mark.parametrize("kind", SPECS)
@pytest.mark.parametrize("action,text,origin,source_hash", [
    ("confirm", None, "extracted", "hash-v1"),
    ("edit", "原文", "extracted", "hash-v1"),
    ("edit", "改文", "manual", None),
])
def test_only_changed_content_becomes_manual(repo, kind, action, text, origin, source_hash):
    repo.update_pending_item(kind, 1, PendingItemUpdateRequest(action=action, updated_text=text))
    result = row(repo, kind)
    assert result[SPECS[kind][1]] == "confirmed"
    assert (result["origin"], result["source_hash"], result["is_stale"]) == (origin, source_hash, 0)
    assert result[SPECS[kind][2]] == (text or "原文")
    if kind == "constraint_check":
        assert repo.conn.execute("SELECT status FROM constraints").fetchone()[0] == "resolved"


@pytest.mark.parametrize("kind", SPECS)
def test_confirmation_ignores_updated_text(repo, kind):
    repo.update_pending_item(kind, 1, PendingItemUpdateRequest(action="confirm", updated_text="夹带改文"))
    result = row(repo, kind)
    assert result[SPECS[kind][2]] == "原文"
    assert (result["origin"], result["source_hash"]) == ("extracted", "hash-v1")


@pytest.mark.parametrize("status", ["pending", "confirmed", "discarded"])
def test_stale_records_hidden_in_every_queue_filter(repo, status):
    for table, status_col, _ in SPECS.values():
        repo.conn.execute(f"UPDATE {table} SET {status_col}=?", (status,))
    assert {item.item_type for item in repo.list_pending_queue(status_filter=status)} == set(SPECS)
    assert len(repo.list_foreshadowing()) == (0 if status == "discarded" else 1)
    for table, _, _ in SPECS.values():
        repo.conn.execute(f"UPDATE {table} SET is_stale=1")
    assert repo.list_pending_queue(status_filter=status) == []
    assert repo.list_foreshadowing() == []
    assert repo.list_foreshadowing(status="planted") == []


@pytest.mark.parametrize("kind", SPECS)
@pytest.mark.parametrize("action", ["confirm", "edit"])
def test_stale_records_cannot_be_confirmed_or_edited(repo, kind, action):
    repo.conn.execute(f"UPDATE {SPECS[kind][0]} SET is_stale=1")
    before = dict(row(repo, kind))
    with pytest.raises(AppError) as error:
        repo.update_pending_item(kind, 1, PendingItemUpdateRequest(action=action, updated_text="改文"))
    assert (error.value.status_code, error.value.code) == (409, "MEMORY_ITEM_STALE")
    assert dict(row(repo, kind)) == before
    assert repo.conn.execute("SELECT status FROM constraints").fetchone()[0] == "active"


@pytest.mark.parametrize("kind", SPECS)
def test_missing_item_returns_404(repo, kind):
    with pytest.raises(AppError) as error:
        repo.update_pending_item(kind, 999, PendingItemUpdateRequest(action="confirm"))
    assert error.value.status_code == 404


@pytest.mark.parametrize("update", [ForeshadowUpdate(confirm_status="confirmed"), ForeshadowUpdate(description="改文")])
def test_direct_foreshadow_update_rejects_stale(repo, update):
    repo.conn.execute("UPDATE foreshadowing SET is_stale=1")
    with pytest.raises(AppError) as error:
        repo.update_foreshadowing(1, update)
    assert (error.value.status_code, error.value.code) == (409, "MEMORY_ITEM_STALE")
    assert row(repo, "foreshadowing")["is_stale"] == 1


@pytest.mark.parametrize("text,origin,source_hash", [("原文", "extracted", "hash-v1"), ("改文", "manual", None)])
def test_direct_foreshadow_edit_tracks_actual_content_change(repo, text, origin, source_hash):
    repo.update_foreshadowing(1, ForeshadowUpdate(description=text, confirm_status="confirmed"))
    result = row(repo, "foreshadowing")
    assert (result["origin"], result["source_hash"]) == (origin, source_hash)


@pytest.mark.parametrize("update", [
    ForeshadowUpdate(status="recovered"),
    ForeshadowUpdate(plan_recover_start=2),
    ForeshadowUpdate(plan_recover_end=4),
])
def test_direct_foreshadow_content_fields_become_manual(repo, update):
    repo.update_foreshadowing(1, update)
    result = row(repo, "foreshadowing")
    assert (result["origin"], result["source_hash"], result["is_stale"]) == ("manual", None, 0)
    for field, value in update.model_dump(exclude_none=True).items():
        assert result[field] == value


@pytest.mark.parametrize("update", [
    ForeshadowUpdate(confirm_status="confirmed"),
    ForeshadowUpdate(status="planted", description="原文"),
    ForeshadowUpdate(plan_recover_start=2, plan_recover_end=4),
])
def test_direct_foreshadow_confirmation_and_noop_preserve_provenance(repo, update):
    repo.conn.execute("UPDATE foreshadowing SET plan_recover_start=2, plan_recover_end=4")
    repo.update_foreshadowing(1, update)
    result = row(repo, "foreshadowing")
    assert (result["origin"], result["source_hash"], result["is_stale"]) == ("extracted", "hash-v1", 0)


def test_batch_error_rolls_back_earlier_confirmation(repo):
    repo.conn.execute("UPDATE foreshadowing SET is_stale=1")
    repo.conn.commit()
    with pytest.raises(AppError):
        with repo.conn:
            repo.batch_update_pending(BatchQueueActionRequest(items=[
                {"item_type": "fact", "id": 1},
                {"item_type": "constraint_check", "id": 1},
                {"item_type": "foreshadowing", "id": 1},
            ]))
    assert row(repo, "fact")["status"] == "pending"
    assert repo.conn.execute("SELECT COUNT(*) FROM facts_fts").fetchone()[0] == 0
    assert repo.conn.execute("SELECT status FROM constraints").fetchone()[0] == "active"


@pytest.mark.parametrize("kind", SPECS)
def test_existing_manual_confirmation_preserves_provenance(repo, kind):
    repo.conn.execute(f"UPDATE {SPECS[kind][0]} SET origin='manual', source_hash=NULL")
    repo.update_pending_item(kind, 1, PendingItemUpdateRequest(action="confirm"))
    result = row(repo, kind)
    assert (result["origin"], result["source_hash"]) == ("manual", None)


@pytest.mark.parametrize("kind", SPECS)
def test_discard_cannot_edit_or_revive_stale_item(repo, kind):
    repo.conn.execute(f"UPDATE {SPECS[kind][0]} SET is_stale=1")
    repo.update_pending_item(kind, 1, PendingItemUpdateRequest(action="discard", updated_text="夹带改文"))
    result = row(repo, kind)
    assert result[SPECS[kind][1]] == "discarded"
    assert result[SPECS[kind][2]] == "原文"
    assert (result["origin"], result["source_hash"], result["is_stale"]) == ("extracted", "hash-v1", 1)


def invalidate_after_read(repo, monkeypatch):
    original = repo._require_current_memory_item

    def read_then_invalidate(table, item_id, **kwargs):
        current = original(table, item_id, **kwargs)
        repo.conn.execute(f"UPDATE {table} SET is_stale=1 WHERE id=?", (item_id,))
        return current

    monkeypatch.setattr(repo, "_require_current_memory_item", read_then_invalidate)


@pytest.mark.parametrize("kind", SPECS)
@pytest.mark.parametrize("action", ["confirm", "edit"])
def test_queue_action_rechecks_freshness_when_writing(repo, monkeypatch, kind, action):
    invalidate_after_read(repo, monkeypatch)
    with pytest.raises(AppError) as error:
        repo.update_pending_item(kind, 1, PendingItemUpdateRequest(action=action, updated_text="改文"))
    assert (error.value.status_code, error.value.code) == (409, "MEMORY_ITEM_STALE")
    result = row(repo, kind)
    assert result[SPECS[kind][1]] == "pending"
    assert result[SPECS[kind][2]] == "原文"
    assert (result["origin"], result["source_hash"], result["is_stale"]) == ("extracted", "hash-v1", 1)
    assert repo.conn.execute("SELECT status FROM constraints").fetchone()[0] == "active"


def test_direct_foreshadow_rechecks_freshness_when_writing(repo, monkeypatch):
    invalidate_after_read(repo, monkeypatch)
    with pytest.raises(AppError) as error:
        repo.update_foreshadowing(1, ForeshadowUpdate(description="改文", confirm_status="confirmed"))
    assert (error.value.status_code, error.value.code) == (409, "MEMORY_ITEM_STALE")
    result = row(repo, "foreshadowing")
    assert (result["description"], result["confirm_status"], result["is_stale"]) == ("原文", "pending", 1)
