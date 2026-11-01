"""T11 deterministic RAG exclusion with no embedding/model calls."""
from types import SimpleNamespace
import pytest


@pytest.mark.parametrize("length,kept", [(19, True), (20, False)])
def test_overlap_threshold(length, kept):
    from app.services.rag.dedup import filter_history_hits
    overlap = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉"[:length]
    record = SimpleNamespace(chapter_id=1, text="起"+overlap+"终")
    hits = filter_history_hits([(record, .9)], excluded_chapter_ids={2,3},
                               history_texts=["前"+overlap+"后"])
    assert bool(hits) == kept


def test_current_previous_and_written_overlap_are_removed():
    from app.services.rag.dedup import filter_history_hits
    repeated = "旧章关键内容与本章已写信息在这里有连续二十字重叠"
    records = [SimpleNamespace(chapter_id=i, text=t) for i,t in
               [(2,"上一章"),(3,"本章"),(1,repeated),(1,"有用的旧章秘密")]]
    hits = filter_history_hits([(r,.9) for r in records], excluded_chapter_ids={2,3},
                               history_texts=[repeated])
    assert [r.text for r,_ in hits] == ["有用的旧章秘密"]


def test_no_hits_stays_empty():
    from app.services.rag.dedup import filter_history_hits
    assert filter_history_hits([], excluded_chapter_ids={2}, history_texts=[]) == []


from test_repetition_guard import client, two_chapters


@pytest.mark.parametrize("store_exists,keep_old", [(False,False),(True,False),(True,True)])
def test_rag_context_omits_empty_section_and_filters_chapters(client,two_chapters,monkeypatch,store_exists,keep_old):
    import app.services.context.assembler as assembler
    from app.db.manager import get_novel_db
    uid, previous, current, scene = two_chapters
    class Store:
        store_file=SimpleNamespace(exists=lambda:store_exists)
        def search_vectors(self,**kwargs):
            assert previous not in kwargs['allowed_chapter_hashes']
            assert current not in kwargs['allowed_chapter_hashes']
            hits=[(SimpleNamespace(chapter_id=previous,text="上一章正文"),.9),
                  (SimpleNamespace(chapter_id=current,text="本章已写正文"),.9)]
            if keep_old:
                hits.append((SimpleNamespace(chapter_id=999,text="远章关键秘密"),.8))
            return hits
    monkeypatch.setattr(assembler,'NovelVectorStore',lambda _:Store())
    monkeypatch.setattr(assembler,'encode_text_sync',lambda _:[])
    result=client.get(f'/api/v1/novels/{uid}/chapters/{current}/context-preview').json()
    rag=[b for b in result['blocks'] if b['key']=='rag_history']
    assert bool(rag)==keep_old
    if keep_old:
        assert '远章关键秘密' in rag[0]['content']
        assert '上一章正文' not in rag[0]['content'] and '本章已写正文' not in rag[0]['content']


def test_unsaved_chapter_content_filters_overlapping_rag(client,two_chapters,monkeypatch):
    import app.services.context.assembler as assembler
    from app.db.manager import get_global_db,get_novel_db
    from app.db.repositories.settings_repo import SettingsRepository
    uid, previous,current,scene=two_chapters
    overlap="甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉"
    class Store:
        store_file=SimpleNamespace(exists=lambda:True)
        def search_vectors(self,**kwargs):
            return [(SimpleNamespace(chapter_id=999,text=overlap),.9)]
    monkeypatch.setattr(assembler,'NovelVectorStore',lambda _:Store())
    monkeypatch.setattr(assembler,'encode_text_sync',lambda _:[])
    with get_novel_db(uid) as n,get_global_db() as g:
        instance=assembler.ContextAssembler(n,uid,SettingsRepository(g))
        preview=instance.build_context_preview(current,scene,existing_content=overlap)
    assert not any(b.key=='rag_history' for b in preview.blocks)



def test_generation_and_supplement_forward_unsaved_content(client,two_chapters,monkeypatch):
    import app.services.context.assembler as assembler
    from app.db.manager import get_global_db,get_novel_db
    from app.db.repositories.settings_repo import SettingsRepository
    from app.services.writing_service import WritingService
    from app.schemas.writing import StreamWriteRequest,StreamSupplementRequest
    uid,previous,current,scene=two_chapters
    overlap="甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉"
    class Store:
        store_file=SimpleNamespace(exists=lambda:True)
        def search_vectors(self,**kwargs):
            return [(SimpleNamespace(chapter_id=999,text=overlap),.9)]
    monkeypatch.setattr(assembler,'NovelVectorStore',lambda _:Store())
    monkeypatch.setattr(assembler,'encode_text_sync',lambda _:[])
    with get_novel_db(uid) as n,get_global_db() as g:
        service=WritingService(uid,n,SettingsRepository(g))
        _,control=service.prepare_stream_write_prompts(StreamWriteRequest(chapter_id=current,scene_id=scene))
        assert "RAG 检索相关历史场景片段" in control
        _,writing=service.prepare_stream_write_prompts(StreamWriteRequest(
            chapter_id=current,scene_id=scene,existing_content=overlap))
        _,supplement=service.prepare_stream_supplement_prompts(StreamSupplementRequest(
            chapter_id=current,content=overlap,insertion_index=0,instruction="补充对话"))
    assert "RAG 检索相关历史场景片段" not in writing
    assert "RAG 检索相关历史场景片段" not in supplement
