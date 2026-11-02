"""T20-b: scene planning must keep prop names used in the previous chapter."""

from __future__ import annotations

import httpx
import pytest

from test_scene_event_checklist import _scene_body, _setup, client

PROP_RULE = (
    "行李、手机等道具的称谓必须沿用上一章已出现的说法，不得换名"
    "（例如上一章是“行李箱”，不要写成“行李袋”）。"
)


def test_planning_prompt_requires_prop_names_from_previous_chapter(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, ch = _setup(client)
    prompts: list[str] = []
    scenes = [{
        "goal": "江澈拖着行李箱报到",
        "entry_state": "校门口",
        "must_happen": ["江澈找到报到处"],
        "exit_state": "开始排队",
        "must_not_include": [],
        "pov_character_name": "江澈",
        "character_names": ["江澈"],
        "story_time": "报到日上午",
        "target_words": 700,
    }]

    async def fake_post(self, url, **kwargs):
        prompts.append(kwargs["json"]["messages"][-1]["content"])
        return httpx.Response(200, json=_scene_body(scenes), request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    resp = client.post(f"/api/v1/novels/{uid}/chapters/{ch}/scenes/generate",
                       json={"scene_count": 1})
    assert resp.status_code == 200, resp.text
    assert len(prompts) == 1
    assert PROP_RULE in prompts[0]
    assert "上一章是“行李箱”" in prompts[0]
    assert "不要写成“行李袋”" in prompts[0]
