import asyncio

import pytest

from app.services.repetition_guard import RepetitionConfig, analyze_scene_repetition
from app.services.repetition_service import run_repetition_pipeline
from test_repetition_guard import client, two_chapters


@pytest.mark.parametrize(('previous', 'current', 'gap'), [
    ('八月二十五日', '九月一日', 7),
    ('二〇二五年八月二十五日', '二〇二六年九月一日', 372),
    ('元年八月二十五日', '次年九月一日', None),
    ('8月31日晚', '9月1日早', 1),
    ('2026-08-25', '2026/09/01', 7),
    ('2024年2月28日', '2024年3月1日', 2),
    ('2026-12-31', '2027-01-01', 1),
    ('冬日', '翌晨', None), ('', '9月1日', None),
    ('12月31日', '1月1日', None),
    ('2月28日', '3月1日', None),
    ('2026年8月25日', '9月1日', None),
])
def test_story_time_gap(previous, current, gap):
    from app.services.story_time import story_time_gap
    assert story_time_gap(previous, current) == gap


@pytest.mark.parametrize('word', ['昨晚', '昨天', '昨夜'])
@pytest.mark.parametrize('gap', [None, 1, 7])
def test_relative_time_rule(word, gap):
    report = analyze_scene_repetition(f'{word}他独自经过河边。', story_time_gap_days=gap)
    assert report.triggered is (gap == 7)
    if gap == 7:
        assert word in report.describe_for_model()
        assert '7 天' in report.describe_for_model()


@pytest.mark.parametrize('auto_rewrite', [False, True])
def test_relative_time_rewrite_once_or_warn(auto_rewrite):
    calls = []
    async def rewrite(text, report):
        calls.append(report)
        return text
    result = asyncio.run(run_repetition_pipeline(
        '昨天他独自经过河边。', previous_chapter='', chapter_so_far='', must_not_include=[],
        config=RepetitionConfig(auto_rewrite=auto_rewrite), rewrite_fn=rewrite,
        story_time_gap_days=7,
    ))
    assert len(calls) == int(auto_rewrite)
    assert result['action'] == 'kept_with_warning'
    assert result['warnings']


def test_relative_time_rule_respects_disabled_guard():
    assert not analyze_scene_repetition('昨天他经过河边。', story_time_gap_days=7,
                                        config=RepetitionConfig(enabled=False)).triggered


@pytest.mark.parametrize('current,gap', [('九月一日', 7), ('翌晨', None)])
def test_context_time_anchor_and_reminder(client, two_chapters, current, gap):
    from app.db.manager import get_novel_db
    uid, previous_id, current_id, scene = two_chapters
    with get_novel_db(uid) as conn:
        conn.execute('UPDATE chapters SET story_time = ? WHERE id = ?', ('八月二十五日', previous_id))
        conn.execute('UPDATE chapters SET story_time = ? WHERE id = ?', (current, current_id))
        conn.commit()
    preview = client.get(f'/api/v1/novels/{uid}/chapters/{current_id}/context-preview').json()
    block = next(b['content'] for b in preview['blocks'] if b['key'] == 'summaries_and_prev')
    assert '上一章发生时间：八月二十五日' in block
    assert f'本章发生时间：{current}' in block
    assert '禁止用“昨晚/昨天/今早”指称上一章' in block
    if gap is None:
        assert '无法确定' in block
        assert any('story_time' in warning for warning in preview['warnings'])
    else:
        assert '相隔天数：7 天' in block
        assert preview['warnings'] == []
    response = client.post(
        f'/api/v1/novels/{uid}/chapters/{current_id}/scenes/{scene}/repetition-check',
        json={'scene_text': '昨天他独自经过河边。', 'auto_rewrite': False},
    )
    assert response.status_code == 200
    assert response.json()['triggered'] is (gap == 7)



def test_memory_extraction_prompt_anchors_relative_times():
    from app.services.memory.finalizer import ChapterFinalizerService
    prompt = ChapterFinalizerService._build_extraction_prompt(
        None, "一", "正文", [], "", story_time="八月二十五日")
    assert "本章发生时间：八月二十五日" in prompt
    assert "state_changes、facts、foreshadowing" in prompt
    assert "相对本章时间" in prompt and "明天/下周/过几天" in prompt
