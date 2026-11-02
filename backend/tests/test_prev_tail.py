"""T16: configurable previous-chapter ending excerpt.

No live LLM. Context is assembled from a throw-away DB.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized
from app.main import create_app
from app.services.context.prev_tail import (
    DEFAULT_MAX_CHARS,
    select_previous_tail,
    prev_tail_max_chars,
    prev_tail_strategy,
)

SCENERY = "窗外的天空被夕阳染成橘红色，远处的云层一层层压下来，街道上的灯光在雨后的空气里散开。"
LONG_TEXT = "他推开门，把伞靠在墙边。" + SCENERY + "“明天再说吧。”" + "他转身下楼。"


# --- pure helpers ---

def test_default_tail_matches_legacy_1500_behaviour() -> None:
    text = "开" + "甲" * 2000 + "结尾"
    out = select_previous_tail(text)
    assert out == "……\n" + text[-DEFAULT_MAX_CHARS:]
    assert select_previous_tail("短正文") == "短正文"
    assert select_previous_tail("   ") == ""


def test_dialogue_action_drops_large_scenery_but_keeps_speech_actions_and_hook() -> None:
    out = select_previous_tail(LONG_TEXT, max_chars=500, strategy="dialogue_action")
    assert SCENERY not in out
    assert "他推开门，把伞靠在墙边。" in out
    assert "“明天再说吧。”" in out
    assert "他转身下楼。" in out  # the final sentence is the hook; never dropped
    assert out.startswith("……\n")  # marks that content was omitted


def test_dialogue_action_keeps_scenery_when_it_is_the_hook() -> None:
    text = "她走进站台，把票握在手里。" + SCENERY
    out = select_previous_tail(text, max_chars=500, strategy="dialogue_action")
    assert "她走进站台，把票握在手里。" in out
    assert SCENERY in out  # last sentence retained even though it is scenery
    assert out == text  # nothing was omitted, so no ellipsis marker


def test_dialogue_action_still_respects_the_length_limit() -> None:
    padding = "他走了几步。" * 100
    out = select_previous_tail(padding, max_chars=300, strategy="dialogue_action")
    body = out.removeprefix("……\n")
    assert len(body) <= 300
    assert body  # never empty


def test_tail_length_env_default_clamp_and_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUTHINK_PREV_TAIL_CHARS", raising=False)
    assert prev_tail_max_chars() == 1500
    monkeypatch.setenv("YOUTHINK_PREV_TAIL_CHARS", "800")
    assert prev_tail_max_chars() == 800
    monkeypatch.setenv("YOUTHINK_PREV_TAIL_CHARS", "10")
    assert prev_tail_max_chars() == 200
    monkeypatch.setenv("YOUTHINK_PREV_TAIL_CHARS", "99999")
    assert prev_tail_max_chars() == 4000
    monkeypatch.setenv("YOUTHINK_PREV_TAIL_CHARS", "abc")
    assert prev_tail_max_chars() == 1500


def test_tail_strategy_env_default_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUTHINK_PREV_TAIL_STRATEGY", raising=False)
    assert prev_tail_strategy() == "tail"
    monkeypatch.setenv("YOUTHINK_PREV_TAIL_STRATEGY", "dialogue_action")
    assert prev_tail_strategy() == "dialogue_action"
    monkeypatch.setenv("YOUTHINK_PREV_TAIL_STRATEGY", "unknown")
    assert prev_tail_strategy() == "tail"


# --- integration: assembler injection ---

@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data_t16")
    ensure_global_db_initialized()
    app = create_app()
    with TestClient(app) as tc:
        yield tc


def _mk_book(client: TestClient, prev_text: str) -> tuple[str, int]:
    uid = client.post("/api/v1/novels", json={"title": "T16书"}).json()["novel_uid"]
    v = client.post(f"/api/v1/novels/{uid}/outline/volumes", json={"title": "卷一"}).json()["id"]
    a = client.post(f"/api/v1/novels/{uid}/outline/arcs",
                    json={"volume_id": v, "title": "弧一"}).json()["id"]
    prev = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={"arc_id": a, "title": "上一章", "synopsis": "雨中送伞"},
    ).json()["id"]
    client.put(
        f"/api/v1/novels/{uid}/chapters/{prev}/content",
        json={"content": prev_text, "source": "manual", "create_new_version": True},
    )
    current = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={"arc_id": a, "title": "下一章", "synopsis": "第二天"},
    ).json()["id"]
    return uid, current


def _prev_block(client: TestClient, uid: str, chapter_id: int) -> str:
    data = client.get(f"/api/v1/novels/{uid}/chapters/{chapter_id}/context-preview").json()
    return next(b["content"] for b in data["blocks"] if b["key"] == "summaries_and_prev")


def test_context_tail_length_is_configurable(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    text = "开" + "MIDDLE_UNIQUE" + "填" * 1000 + "TAIL_UNIQUE"
    uid, current = _mk_book(client, text)

    default_block = _prev_block(client, uid, current)
    assert "MIDDLE_UNIQUE" in default_block and "TAIL_UNIQUE" in default_block

    monkeypatch.setenv("YOUTHINK_PREV_TAIL_CHARS", "600")
    short_block = _prev_block(client, uid, current)
    assert "TAIL_UNIQUE" in short_block
    assert "MIDDLE_UNIQUE" not in short_block
    assert "……\n" in short_block


def test_context_tail_strategy_drops_scenery_only_when_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, current = _mk_book(client, LONG_TEXT)

    default_block = _prev_block(client, uid, current)
    assert SCENERY in default_block  # default behaviour unchanged

    monkeypatch.setenv("YOUTHINK_PREV_TAIL_STRATEGY", "dialogue_action")
    trimmed = _prev_block(client, uid, current)
    assert SCENERY not in trimmed
    assert "“明天再说吧。”" in trimmed
    assert "他转身下楼。" in trimmed
