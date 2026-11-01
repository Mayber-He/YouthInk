"""Regression cases from the four-chapter continuity and style diagnosis."""
import json

import httpx
import pytest

from test_m3_writing_stream import client, setup_chapter
from app.db.manager import get_global_db, get_novel_db
from app.db.repositories.settings_repo import SettingsRepository
from app.schemas.writing import StreamWriteRequest
from app.services.writing_service import WritingService
from app.services.memory.consistency import ConsistencyReviewService


def test_author_style_and_unknown_memory(client, setup_chapter):
    uid, chapter, _ = setup_chapter
    client.put(f'/api/v1/novels/{uid}', json={
        'tone': '轻松搞笑', 'pov': '第三人称全知',
        'style_note': '对白推动关系，快节奏，不用环境描写填充篇幅。',
    })
    with get_novel_db(uid) as conn, get_global_db() as glob:
        settings = SettingsRepository(glob)
        svc = WritingService(uid, conn, settings)
        system, user = svc.prepare_stream_write_prompts(StreamWriteRequest(chapter_id=chapter))
        assert '对白推动关系，快节奏' in system
        assert '基调：轻松搞笑' in system
        assert '叙事视角：第三人称全知' in system
        assert '慢热细腻' not in system
        assert '尚不知晓任何隐藏秘密' not in user
        assert '未记录' in user
        review = ConsistencyReviewService(uid, conn, settings)
        checklist = review._build_checklist(chapter, 1.0)
        assert '尚未熟稔/初见' not in checklist
        assert '第三人称全知' in checklist
        assert '对白推动关系，快节奏' in checklist


def test_review_reads_complete_chapter(client, setup_chapter):
    uid, chapter, _ = setup_chapter
    with get_novel_db(uid) as conn, get_global_db() as glob:
        svc = ConsistencyReviewService(uid, conn, SettingsRepository(glob))
        ch = svc._outline_repo.get_chapter(chapter)
        prompt = svc._build_prompt(ch, '正文' * 4000 + '末尾楼层矛盾', '')
        assert '末尾楼层矛盾' in prompt


def mock_completion(monkeypatch, result):
    async def post(self, url, **kwargs):
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': json.dumps(result, ensure_ascii=False)}}]
        })
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)


# 衔接检查不再因证据对不上前文而中止（原先编造的 '宿舍在五楼。' 会让整次生成 502）。
# 两种引用都必须 200 且正文照常流式生成；next_step 不带 evidence_quote，所以两种情况都注入。
@pytest.mark.parametrize('quote', ['宿舍在四楼。', '宿舍在五楼。'])
def test_prewrite_boundary_evidence_never_aborts(client, setup_chapter, monkeypatch, quote):
    from contextlib import asynccontextmanager
    uid, chapter, _ = setup_chapter
    mock_completion(monkeypatch, {
        'established': [{'statement': '宿舍楼层为四楼', 'evidence_quote': quote}],
        'repeated_events': [], 'next_step': '接续搬家后的交流，不重演搬家。',
    })
    captured = []
    @asynccontextmanager
    async def stream(self, method, url, **kwargs):
        captured.append(kwargs['json']['messages'])
        yield httpx.Response(200, text='data: [DONE]\n\n', request=httpx.Request(method, url))
    monkeypatch.setattr(httpx.AsyncClient, 'stream', stream)
    r = client.post(f'/api/stream/novels/{uid}/write', json={
        'chapter_id': chapter, 'existing_content': '宿舍在四楼。', 'mode': 'scene',
    })
    assert r.status_code == 200  # writing is never blocked by the continuity check
    assert captured, '正文必须照常流式生成'
    # next_step 永远不带 evidence_quote，两种输入都应注入
    assert '接续搬家后的交流' in str(captured)
    prompt = captured[0][-1]['content']
    assert prompt.index('生成前章节衔接检查') < prompt.index('【⑥ 输出格式要求】')


def test_apply_review_preserves_original_and_rejects_stale(client, setup_chapter, monkeypatch):
    uid, chapter, _ = setup_chapter
    base = f'/api/v1/novels/{uid}'
    original = '宿舍在三楼。她停在门口。'
    client.put(f'{base}/chapters/{chapter}/content', json={'content': original, 'create_new_version': True})
    mock_completion(monkeypatch, {'issues': [{
        'check_type': 'continuity', 'verdict': 'violation', 'evidence_quote': '宿舍在三楼。',
        'suggested_rewrite': '宿舍在四楼。', 'description': '楼层矛盾',
    }]})
    review = client.post(f'{base}/chapters/{chapter}/consistency-review').json()
    endpoint = f"{base}/consistency-reviews/{review['id']}/apply"
    payload = {'issue_index': 0, 'expected_content': original}
    r = client.post(endpoint, json=payload)
    assert r.status_code == 200
    assert r.json()['latest_content'] == '宿舍在四楼。她停在门口。'
    assert any(v['content'] == original for v in r.json()['versions'])
    assert client.post(endpoint, json=payload).status_code == 409


@pytest.mark.parametrize('text,expected_content', [('同一句。同一句。', '同一句。同一句。'), ('同一句。', '未保存的编辑')])
def test_apply_refuses_ambiguous_or_unsaved_text(client, setup_chapter, monkeypatch, text, expected_content):
    uid, chapter, _ = setup_chapter
    base = f'/api/v1/novels/{uid}'
    client.put(f'{base}/chapters/{chapter}/content', json={'content': text})
    mock_completion(monkeypatch, {'issues': [{
        'check_type': 'common_sense', 'verdict': 'violation', 'evidence_quote': '同一句。',
        'suggested_rewrite': '修改后的句子。',
    }]})
    review = client.post(f'{base}/chapters/{chapter}/consistency-review').json()
    r = client.post(f"{base}/consistency-reviews/{review['id']}/apply", json={
        'issue_index': 0, 'expected_content': expected_content,
    })
    assert r.status_code == 409
    assert client.get(f'{base}/chapters/{chapter}/workspace').json()['latest_content'] == text


def test_review_is_stale_when_previous_chapter_changes_during_call(client, setup_chapter, monkeypatch):
    from app.db.repositories.writing_repo import WritingRepository
    uid, first, _ = setup_chapter
    base = f'/api/v1/novels/{uid}'
    ch = client.get(f'{base}/chapters/{first}/workspace').json()['chapter']
    second = client.post(f'{base}/outline/chapters', json={
        'arc_id': ch['arc_id'], 'title': '后章', 'sort_order': 2,
    }).json()['id']
    client.put(f'{base}/chapters/{first}/content', json={'content': '宿舍在三楼。'})
    client.put(f'{base}/chapters/{second}/content', json={'content': '她走上三楼。'})
    async def post(self, url, **kwargs):
        with get_novel_db(uid) as conn:
            WritingRepository(conn).save_chapter_content(first, '宿舍在四楼。', create_new_version=True)
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': '{"issues": []}'}}]
        })
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    report = client.post(f'{base}/chapters/{second}/consistency-review').json()
    assert report['is_stale'] is True
    r = client.post(f"{base}/consistency-reviews/{report['id']}/apply", json={
        'issue_index': 0, 'expected_content': '她走上三楼。',
    })
    assert r.status_code == 409


def test_prose_advice_is_never_a_hard_violation(client, setup_chapter, monkeypatch):
    uid, chapter, _ = setup_chapter
    base = f'/api/v1/novels/{uid}'
    client.put(f'{base}/chapters/{chapter}/content', json={'content': '他拿起手机，又放下手机。'})
    mock_completion(monkeypatch, {'issues': [{
        'check_type': 'prose', 'verdict': 'violation', 'evidence_quote': '他拿起手机，又放下手机。',
        'suggested_rewrite': '他放下手机。',
    }]})
    report = client.post(f'{base}/chapters/{chapter}/consistency-review').json()
    assert report['violation_count'] == 0
    assert report['issues'][0]['verdict'] == 'suspicious'


def test_boundary_uses_previous_prose_and_author_style(client, setup_chapter, monkeypatch):
    import asyncio
    uid, first, _ = setup_chapter
    base = f'/api/v1/novels/{uid}'
    ch = client.get(f'{base}/chapters/{first}/workspace').json()['chapter']
    second = client.post(f'{base}/outline/chapters', json={
        'arc_id': ch['arc_id'], 'title': '晚间交流', 'synopsis': '再次讲述搬箱子', 'sort_order': 2,
    }).json()['id']
    client.put(f'{base}/chapters/{first}/content', json={'content': '她说学弟帮忙搬了箱子。'})
    client.put(f'{base}', json={'style_note': '用幽默对白推动剧情'})
    async def post(self, url, **kwargs):
        prompt = kwargs['json']['messages'][-1]['content']
        assert '她说学弟帮忙搬了箱子。' in prompt
        assert '用幽默对白推动剧情' in prompt
        assert '再次讲述搬箱子' in prompt
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': json.dumps({
                'established': [], 'repeated_events': [{
                    'statement': '不要再次介绍搬箱子', 'evidence_quote': '她说学弟帮忙搬了箱子。',
                }], 'next_step': '从帮助产生的关系变化继续。',
            }, ensure_ascii=False)}}]
        })
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    with get_novel_db(uid) as conn, get_global_db() as glob:
        service = WritingService(uid, conn, SettingsRepository(glob))
        assert '不要再次介绍搬箱子' in asyncio.run(service.check_write_boundary(StreamWriteRequest(chapter_id=second)))
        # An opening chapter with no preceding prose does not call the model.
        assert asyncio.run(service.check_write_boundary(StreamWriteRequest(chapter_id=first))) == ''
