"""Scene roster selection through the real context-preview API and temporary DBs."""

import pytest

from test_constraints import client, novel_uid


@pytest.fixture()
def roster(client, novel_uid):
    base = f"/api/v1/novels/{novel_uid}"
    ids = {}
    for name, role, aliases in [
        ("林夏", "female_lead", []),
        ("周远", "male_lead", ["小周"]),
        ("陈叔", "minor", []),
    ]:
        response = client.post(f"{base}/characters", json={"name": name, "role": role, "aliases": aliases})
        assert response.status_code == 201, response.text
        ids[name] = response.json()["id"]
        response = client.post(f"{base}/constraints", json={
            "target_type": "character", "target_id": ids[name], "content": f"{name}专属禁令",
        })
        assert response.status_code == 201, response.text
    volume = client.post(f"{base}/outline/volumes", json={"title": "卷"}).json()
    arc = client.post(f"{base}/outline/arcs", json={"volume_id": volume["id"], "title": "篇"}).json()
    chapter = client.post(f"{base}/outline/chapters", json={"arc_id": arc["id"], "title": "章"}).json()
    return base, chapter["id"], ids


def scene(client, roster, **payload):
    base, chapter_id, _ = roster
    response = client.post(f"{base}/chapters/{chapter_id}/scenes", json={"beat": "整理材料", **payload})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def preview(client, roster, scene_id=None, synopsis=""):
    base, chapter_id, _ = roster
    if synopsis:
        response = client.put(f"{base}/outline/chapters/{chapter_id}", json={"synopsis": synopsis})
        assert response.status_code == 200, response.text
    response = client.get(f"{base}/chapters/{chapter_id}/context-preview", params={"scene_id": scene_id} if scene_id else {})
    assert response.status_code == 200, response.text
    return {block["key"]: block["content"] for block in response.json()["blocks"]}


def assert_active(blocks, active, inactive):
    for name in active:
        assert f"【{name}】" in blocks["character_states"]
        assert f"【{name}】" in blocks["cognitive_constraints"]
        assert f"{name}专属禁令" in blocks["hard_constraints"]
    for name in inactive:
        assert f"【{name}】" not in blocks["character_states"]
        assert f"【{name}】" not in blocks["cognitive_constraints"]
        assert f"{name}专属禁令" not in blocks["hard_constraints"]


@pytest.mark.parametrize("colon", ["：", ":"])
def test_forbidden_line_does_not_activate_character(client, roster, colon):
    scene(client, roster, beat=f"林夏整理材料\n 本场禁止出现{colon}@小周提前赶来；陈叔插话")
    assert_active(preview(client, roster), ["林夏"], ["周远", "陈叔"])


def test_explicit_ids_override_synopsis_beats_and_contradictory_pov(client, roster):
    _, _, ids = roster
    selected = scene(client, roster, character_ids=[ids["林夏"]], pov_character=ids["周远"], beat="想起陈叔")
    scene(client, roster, character_ids=[ids["周远"]], beat="周远与陈叔交谈")
    blocks = preview(client, roster, selected, synopsis="林夏、周远、陈叔的安排")
    assert_active(blocks, ["林夏"], ["周远", "陈叔"])


def test_explicit_names_and_aliases_override_other_mentions(client, roster):
    selected = scene(client, roster, beat="在场人物：林夏、@小周\n林夏回忆陈叔\n本场禁止出现：陈叔插话")
    assert_active(preview(client, roster, selected, synopsis="陈叔来访"), ["林夏", "周远"], ["陈叔"])


def test_selected_scene_inference_excludes_other_scene_mentions(client, roster):
    selected = scene(client, roster, beat="林夏整理材料")
    scene(client, roster, beat="周远与陈叔交谈")
    assert_active(preview(client, roster, selected), ["林夏"], ["周远", "陈叔"])


def test_no_roster_preserves_synopsis_alias_and_pov_inference(client, roster):
    _, _, ids = roster
    selected = scene(client, roster, pov_character=ids["林夏"], beat="@小周整理材料")
    assert_active(preview(client, roster, selected, synopsis="陈叔来访"), ["林夏", "周远", "陈叔"], [])


def test_lead_fallback_does_not_resurrect_forbidden_names(client, roster):
    scene(client, roster, beat="整理材料\n本场禁止出现：小周到访")
    assert_active(preview(client, roster), ["林夏"], ["周远", "陈叔"])


def test_no_roster_no_mentions_preserves_lead_fallback(client, roster):
    scene(client, roster)
    assert_active(preview(client, roster), ["林夏", "周远"], ["陈叔"])


@pytest.mark.parametrize("names", ["无", "", "陌生路人"])
def test_explicit_unmatched_roster_does_not_fall_back_to_leads(client, roster, names):
    selected = scene(client, roster, beat=f"在场人物：{names}\n林夏\n周远")
    assert_active(preview(client, roster, selected), [], ["林夏", "周远", "陈叔"])


def test_character_ids_take_precedence_over_text_roster(client, roster):
    _, _, ids = roster
    selected = scene(client, roster, character_ids=[ids["林夏"]], beat="在场人物：周远\n陈叔来访")
    assert_active(preview(client, roster, selected), ["林夏"], ["周远", "陈叔"])


def test_chapter_preview_unions_explicit_scene_rosters(client, roster):
    _, _, ids = roster
    scene(client, roster, character_ids=[ids["林夏"]])
    scene(client, roster, beat="在场人物：小周\n本场禁止出现：陈叔来访")
    assert_active(preview(client, roster, synopsis="陈叔来访"), ["林夏", "周远"], ["陈叔"])
