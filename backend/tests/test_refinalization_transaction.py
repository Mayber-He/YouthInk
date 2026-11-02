"""Re-finalization swaps SQLite memory batches atomically; upstream is always mocked."""
import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from app.core.exceptions import AppError
from app.core.text_hash import text_sha256
from app.db.init_schema import init_novel_db
from app.db.repositories.constraint_repo import ConstraintRepository
from app.db.repositories.entity_repo import EntityRepository
from app.db.repositories.memory_repo import MemoryRepository
from app.db.repositories.outline_repo import OutlineRepository
from app.db.repositories.writing_repo import WritingRepository
from app.schemas.memory import LlmMemoryExtractionOutput, PendingItemUpdateRequest
from app.schemas.settings import TrustModeSettings
from app.services.embedding.encoder import EmbeddingModelUnavailable
from app.services.memory.finalizer import ChapterFinalizerService

TABLES = ('facts', 'character_state_changes', 'cognitive_records', 'relationship_changes', 'foreshadowing', 'constraint_checks')
KINDS = ('fact', 'char_state', 'cognitive', 'relationship', 'foreshadowing', 'constraint_check')
BODY = '江澈承诺保密。裴南栀知道秘密。禁令正式解除。'


def extraction(label):
    return LlmMemoryExtractionOutput.model_validate({
        'facts': [{'content': label, 'source_quote': '江澈承诺保密。', 'character_names': ['江澈']}],
        'state_changes': [{'character_name': '江澈', 'field': 'emotion', 'value': label, 'source_quote': '江澈承诺保密。'}],
        'cognitive_records': [{'secret': label, 'knower_names': ['裴南栀'], 'source_quote': '裴南栀知道秘密。'}],
        'relationship_changes': [{'char_a_name': '江澈', 'char_b_name': '裴南栀', 'rel_type': label, 'intimacy': 3, 'publicity': 'mutual', 'source_quote': '江澈承诺保密。'}],
        'foreshadowing': [{'description': label, 'status': 'planted', 'source_quote': '江澈承诺保密。'}],
        'constraint_checks': [{'constraint_id': 1, 'verdict': 'resolved', 'evidence_quote': '禁令正式解除。', 'description': label}],
    })


@pytest.fixture()
def service(monkeypatch):
    conn = sqlite3.connect(':memory:'); conn.row_factory = sqlite3.Row
    init_novel_db(conn)
    for sql in [
        "INSERT INTO novels(id,title) VALUES(1,'事务测试')",
        "INSERT INTO volumes(id,novel_id,title,sort_order) VALUES(1,1,'卷',1)",
        "INSERT INTO arcs(id,volume_id,title,sort_order) VALUES(1,1,'弧',1)",
        "INSERT INTO chapters(id,arc_id,title,sort_order,status) VALUES(1,1,'章',1,'final')",
        "INSERT INTO characters(id,name,role) VALUES(1,'江澈','male_lead'),(2,'裴南栀','female_lead')",
        "INSERT INTO constraints(id,target_type,content) VALUES(1,'novel','禁令')",
    ]:
        conn.execute(sql)
    conn.execute("INSERT INTO chapter_versions(chapter_id,version,content,source) VALUES(1,1,?,'manual')", (BODY,))
    conn.execute('UPDATE chapters SET content_hash=? WHERE id=1', (text_sha256(BODY),))
    conn.commit()
    svc = object.__new__(ChapterFinalizerService)
    svc.conn = conn; svc.novel_uid = 'test'
    trust = TrustModeSettings(auto_confirm_char_state=True, auto_confirm_cognitive=True,
        auto_confirm_relationship=True, auto_confirm_foreshadow_plant_recover=True)
    svc.settings_repo = SimpleNamespace(get_trust_mode=lambda: trust, get_setting=lambda key, default: default)
    svc.entity_repo = EntityRepository(conn); svc.outline_repo = OutlineRepository(conn)
    svc.writing_repo = WritingRepository(conn); svc.constraint_repo = ConstraintRepository(conn)
    svc.memory_repo = MemoryRepository(conn)
    svc.events = []; svc.round = 0
    vector_status = {'pending_rebuild': False, 'reason': '', 'chapters': []}
    def index(*args):
        assert conn.in_transaction, 'Publish prepared vectors only after source validation under the write lock'
        svc.events.append('index')
    def read_index_status():
        return dict(vector_status, chapters=sorted(vector_status['chapters']))
    def mark_rebuild_pending(reason, chapter_ids=None):
        vector_status.update(pending_rebuild=True, reason=reason)
        vector_status['chapters'] = sorted(set(vector_status['chapters']) | set(chapter_ids or []))
    def clear_chapter_pending(chapter_id):
        vector_status['chapters'] = [c for c in vector_status['chapters'] if c != chapter_id]
        if not vector_status['chapters']:
            vector_status.update(pending_rebuild=False, reason='')
    def clear_rebuild_pending():
        vector_status.update(pending_rebuild=False, reason='', chapters=[])
    svc.vector_store = SimpleNamespace(
        upsert_chapter_chunks=index,
        read_index_status=read_index_status,
        mark_rebuild_pending=mark_rebuild_pending,
        clear_chapter_pending=clear_chapter_pending,
        clear_rebuild_pending=clear_rebuild_pending,
    )
    def encode(texts):
        assert not conn.in_transaction, 'Embedding must not hold a SQLite transaction'
        return [[1.0] + [0.0] * 1023 for _ in texts]
    monkeypatch.setattr('app.services.memory.finalizer.encode_texts_sync', encode)
    monkeypatch.setattr('app.services.memory.finalizer.create_novel_backup', lambda *args, **kw: SimpleNamespace(filename='mock.db'))
    async def summary(*args):
        assert not conn.in_transaction, 'Summary model call inside transaction'
        svc.round += 1; svc.events.append('summary')
        return f'摘要{svc.round}'
    async def extract(*args):
        assert not conn.in_transaction, 'Extraction model call inside transaction'
        svc.events.append('extract')
        return extraction(f'记忆{svc.round}'), 'ok'
    svc._generate_chapter_summary = summary; svc._extract_chapter_memories = extract
    yield svc
    conn.close()


def run(svc):
    return asyncio.run(svc.finalize_chapter(1))


def snapshot(conn):
    return {t: [tuple(r) for r in conn.execute(f'SELECT * FROM {t} ORDER BY id')]
            for t in (*TABLES, 'summaries', 'chapters')}


def test_two_finalizations_have_one_effective_batch_and_one_summary(service):
    run(service)
    # Confirming an extracted item must not opt it out of next batch replacement.
    service.memory_repo.update_pending_item('fact', 1, PendingItemUpdateRequest(action='confirm'))
    service.conn.commit()
    run(service)
    for table in TABLES:
        assert tuple(service.conn.execute(f'SELECT COUNT(*),SUM(is_stale=0),SUM(is_stale=1) FROM {table}').fetchone()) == (2,1,1)
    assert service.conn.execute('SELECT COUNT(*) FROM summaries').fetchone()[0] == 1
    assert service.conn.execute('SELECT content FROM summaries').fetchone()[0] == '摘要2'


def test_model_and_embedding_work_precedes_short_transaction(service):
    run(service)
    assert service.events == ['summary', 'extract', 'index']
    assert not service.conn.in_transaction


@pytest.mark.parametrize('table,kind', zip(TABLES,KINDS))
def test_genuinely_edited_manual_memory_survives(service,table,kind):
    run(service)
    service.memory_repo.update_pending_item(kind,1,PendingItemUpdateRequest(action='edit',updated_text='人工内容'))
    service.conn.commit()
    run(service)
    old=service.conn.execute(f'SELECT * FROM {table} WHERE id=1').fetchone()
    assert old['origin']=='manual' and old['is_stale']==0


@pytest.mark.parametrize('failure_point', ['summary_write','middle_of_batch'])
def test_failed_publication_rolls_back_batch_summary_and_chapter(service,monkeypatch,failure_point):
    run(service); before=snapshot(service.conn)
    if failure_point=='summary_write':
        original=service.memory_repo.upsert_summary
        def fail(*args,**kw):
            original(*args,**kw)
            raise sqlite3.IntegrityError('injected summary failure')
        monkeypatch.setattr(service.memory_repo,'upsert_summary',fail)
    else:
        service.conn.execute("CREATE TRIGGER fail_rel BEFORE INSERT ON relationship_changes BEGIN SELECT RAISE(ABORT,'injected batch failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        run(service)
    assert snapshot(service.conn)==before
    assert not service.conn.in_transaction


def test_failed_extraction_preserves_effective_memories_and_existing_summary(service):
    run(service)
    old_ids={t:service.conn.execute(f'SELECT id FROM {t}').fetchone()[0] for t in TABLES}
    async def fallback(*args):
        assert not service.conn.in_transaction
        return service._fallback_extraction('章',BODY,['江澈']), 'failed'
    service._extract_chapter_memories=fallback
    result=run(service)
    assert result.extraction_status=='failed'
    for table,iid in old_ids.items():
        assert service.conn.execute(f'SELECT is_stale FROM {table} WHERE id=?',(iid,)).fetchone()[0]==0
    assert service.conn.execute('SELECT content FROM summaries').fetchone()[0]=='摘要1'
    assert service.conn.execute("SELECT COUNT(*) FROM facts WHERE status='pending'").fetchone()[0]==1


def test_first_finalization_fallback_still_creates_pending_fact_and_summary(service):
    async def fallback(*args):
        return service._fallback_extraction('章',BODY,['江澈']), 'failed'
    service._extract_chapter_memories=fallback
    result=run(service)
    assert result.extraction_status=='failed'
    assert service.conn.execute('SELECT status FROM facts').fetchone()[0]=='pending'
    assert service.conn.execute('SELECT COUNT(*) FROM summaries').fetchone()[0]==1


@pytest.mark.parametrize('status',['active','violated','resolved'])
def test_reextraction_never_applies_or_rolls_back_constraint_status(service,status):
    service.conn.execute('UPDATE constraints SET status=? WHERE id=1',(status,)); service.conn.commit()
    run(service); run(service)
    assert service.conn.execute('SELECT status FROM constraints WHERE id=1').fetchone()[0]==status
    assert service.conn.execute('SELECT confirm_status FROM constraint_checks WHERE is_stale=0').fetchone()[0]=='pending'


def test_model_failure_does_not_publish_summary(service):
    run(service);before=snapshot(service.conn)
    async def fail(*args):
        assert not service.conn.in_transaction
        raise ValueError('injected extraction validation failure')
    service._extract_chapter_memories=fail
    with pytest.raises(ValueError):run(service)
    assert snapshot(service.conn)==before


@pytest.mark.parametrize('in_place', [False, True])
def test_content_changed_during_model_call_cannot_be_finalized_with_old_results(service,in_place):
    original=service._extract_chapter_memories
    async def changed(*args):
        result=await original(*args)
        if in_place:
            service.conn.execute("UPDATE chapter_versions SET content='修改后的正文' WHERE chapter_id=1")
        else:
            service.conn.execute("INSERT INTO chapter_versions(chapter_id,version,content,source) VALUES(1,2,'修改后的正文','manual')")
        service.conn.execute("UPDATE chapters SET status='draft' WHERE id=1")
        service.conn.commit()
        return result
    service._extract_chapter_memories=changed
    with pytest.raises(AppError) as err:run(service)
    assert err.value.code=='CHAPTER_CONTENT_CHANGED'
    assert service.conn.execute('SELECT COUNT(*) FROM facts').fetchone()[0]==0
    assert service.conn.execute("SELECT status FROM chapters WHERE id=1").fetchone()[0]=='draft'
    assert 'index' not in service.events


@pytest.mark.parametrize('failure_point', ['embedding', 'vector_publish'])
def test_index_failure_still_finalizes_text_and_marks_pending(service,monkeypatch,failure_point):
    run(service)
    def fail(*args):
        raise OSError('injected index failure')
    if failure_point=='embedding':
        monkeypatch.setattr('app.services.memory.finalizer.encode_texts_sync',fail)
    else:
        service.vector_store.upsert_chapter_chunks=fail
    result=run(service)
    assert result.status=='final'
    assert result.extraction_status=='ok'
    assert result.chapter_summary=='摘要2'
    assert result.chunks_indexed==0
    assert result.vector_index_status=='pending_rebuild'
    assert 'injected index failure' in (result.vector_index_error or '')
    assert service.conn.execute("SELECT status FROM chapters WHERE id=1").fetchone()[0]=='final'
    assert service.conn.execute("SELECT content FROM summaries WHERE is_stale=0").fetchone()[0]=='摘要2'
    for table in TABLES:
        assert tuple(service.conn.execute(
            f'SELECT COUNT(*),SUM(is_stale=0),SUM(is_stale=1) FROM {table}'
        ).fetchone())==(2,1,1)
    assert not service.conn.in_transaction


def test_missing_embedding_model_degrades_to_pending_not_failure(service,monkeypatch):
    # Simulate a missing/failed model on the very first finalization.
    def unavailable(*args):
        raise EmbeddingModelUnavailable('模型文件缺失')
    monkeypatch.setattr('app.services.memory.finalizer.encode_texts_sync',unavailable)
    result=run(service)
    assert result.status=='final'
    assert result.extraction_status=='ok'
    assert result.vector_index_status=='pending_rebuild'
    assert '模型文件缺失' in (result.vector_index_error or '')
    assert result.chunks_indexed==0
    assert service.conn.execute("SELECT content FROM summaries").fetchone()[0]=='摘要1'
    assert service.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]==1


def test_failure_after_fts_rolls_back_all_sqlite_indexes(service,monkeypatch):
    run(service);before=snapshot(service.conn)
    def indexes():
        return {t:[tuple(r) for r in service.conn.execute(f'SELECT rowid,content FROM {t} ORDER BY rowid')]
                for t in ('chapters_fts','facts_fts')}
    old_indexes=indexes()
    original=service.memory_repo.index_chapter_version_fts
    def fail(*args):
        original(*args)
        raise sqlite3.IntegrityError('injected after FTS failure')
    monkeypatch.setattr(service.memory_repo,'index_chapter_version_fts',fail)
    with pytest.raises(sqlite3.IntegrityError):run(service)
    assert snapshot(service.conn)==before
    assert indexes()==old_indexes
    assert not service.conn.in_transaction
