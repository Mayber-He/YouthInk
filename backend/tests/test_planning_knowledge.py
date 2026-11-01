"""Planning must not inherit unsupported recognition clues as established facts."""
import json
import httpx
from test_m3_writing_stream import client, setup_chapter


def test_outline_and_review_receive_relationship_sources(client, setup_chapter, monkeypatch):
    uid, _, _ = setup_chapter
    base = f'/api/v1/novels/{uid}'
    client.post(f'{base}/characters', json={
        'name': '江澈', 'role': 'male_lead', 'background': '只通过文字聊天，从未见面或视频。',
    })
    client.put(f'{base}/main-plot', json={'core_conflict': '通过打字前抿嘴的习惯认出网友'})
    prompts = []
    async def post(self, url, **kwargs):
        prompt = kwargs['json']['messages'][-1]['content']
        prompts.append(prompt)
        payload = {'volumes': [{'title': '开学', 'synopsis': '认出网友', 'goal': '身份确认',
            'arcs': [{'title': '初遇', 'goal': '观察锁屏', 'core_conflict': '通过已分享的照片认出网友'}]}]}
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': json.dumps(payload, ensure_ascii=False)}}]})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    response = client.post(f'{base}/outline/generate-structure', json={})
    assert response.status_code == 200
    assert len(prompts) == 2
    for prompt in prompts:
        assert '只通过文字聊天，从未见面或视频。' in prompt
        assert '信息来源与获取顺序' in prompt
        assert '上游规划不等于已发生事实' in prompt
        assert '不得补造视频' in prompt


def test_main_plot_is_reviewed_for_knowledge_errors(client, setup_chapter, monkeypatch):
    uid, _, _ = setup_chapter
    prompts = []
    async def post(self, url, **kwargs):
        prompt = kwargs['json']['messages'][-1]['content']
        prompts.append(prompt)
        conflict = '靠未见过的抿嘴习惯认出网友' if len(prompts) == 1 else '靠曾分享的照片与同步消息认出网友'
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': json.dumps({'core_conflict': conflict,
                'romance_arc': '相识', 'growth_arc': '成长', 'key_turning_pts': []}, ensure_ascii=False)}}]})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    result = client.post(f'/api/v1/novels/{uid}/main-plot/generate', json={})
    assert result.status_code == 200
    assert len(prompts) == 2
    assert result.json()['core_conflict'] == '靠曾分享的照片与同步消息认出网友'
    assert '靠未见过的抿嘴习惯认出网友' in prompts[1]
    assert '信息来源与获取顺序' in prompts[1]


def test_failed_main_plot_review_keeps_saved_plot(client, setup_chapter, monkeypatch):
    uid, _, _ = setup_chapter
    base = f'/api/v1/novels/{uid}'
    client.put(f'{base}/main-plot', json={'core_conflict': '原有主线'})
    calls = 0
    async def post(self, url, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            return httpx.Response(500, request=httpx.Request('POST', url), text='review failed')
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': json.dumps({'core_conflict': '待核对的新主线',
                'romance_arc': '', 'growth_arc': '', 'key_turning_pts': []})}}]})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    assert client.post(f'{base}/main-plot/generate', json={}).status_code == 502
    assert client.get(f'{base}/main-plot').json()['core_conflict'] == '原有主线'
