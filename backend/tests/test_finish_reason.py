"""T7: generation_logs.temperature / finish_reason + stream end-state detection.

All upstream traffic is mocked (no live LLM).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from app.core.config import reset_config_for_testing
from app.db.init_schema import init_novel_db
from app.db.manager import ensure_global_db_initialized, get_novel_db
from app.db.repositories.novel_repo import create_novel_project
from app.schemas.novel import NovelCreate
from app.services.llm.client import (
    complete_chat,
    is_truncated,
    normalize_finish_reason,
    stream_chat_sse,
)


def _chunk(content: str | None = None, finish: str | None = None) -> str:
    delta = {"content": content} if content is not None else {}
    return "data: " + json.dumps(
        {"choices": [{"delta": delta, "finish_reason": finish}]}, ensure_ascii=False
    )


class FakeStreamResponse:
    status_code = 200

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    async def aiter_lines(self):
        for ln in self._lines:
            yield ln

    async def aread(self) -> bytes:
        return b""


def _patch_stream(monkeypatch: pytest.MonkeyPatch, lines: list[str]) -> list[dict]:
    seen: list[dict] = []

    @asynccontextmanager
    async def fake_stream(self, method, url, **kwargs):
        seen.append(kwargs["json"])
        yield FakeStreamResponse(lines)

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    return seen


@pytest.fixture()
def novel(tmp_path: Path):
    reset_config_for_testing(tmp_path / "test_data_t7")
    ensure_global_db_initialized()
    detail = create_novel_project(NovelCreate(title="T7"))
    return str(detail.novel_uid)


def _run_stream(uid: str | None, **kw) -> list[tuple[str, dict]]:
    async def go():
        frames: list[tuple[str, dict]] = []
        async for raw in stream_chat_sse(
            base_url="https://api.example.com/v1", api_key="sk-x", model="m",
            system_prompt="s", user_prompt="u", novel_uid=uid, task_type="write_scene", **kw,
        ):
            name = raw.split("\n", 1)[0].removeprefix("event: ")
            data = json.loads(raw.split("data: ", 1)[1])
            frames.append((name, data))
        return frames

    return asyncio.run(go())


def _last_log(uid: str):
    with get_novel_db(uid) as conn:
        return conn.execute(
            "SELECT task_type, temperature, finish_reason, output FROM generation_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()


# ------------------------------------------------------------------ normalization

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("stop", "stop"), ("STOP", "stop"), (" length ", "length"),
        ("max_tokens", "length"), ("max_output_tokens", "length"),
        ("content_filter", "content_filter"), ("tool_calls", "tool_calls"),
        (None, None), ("", None), ("   ", None), (123, None), ({"a": 1}, None),
    ],
)
def test_normalize_finish_reason(raw, expected) -> None:
    assert normalize_finish_reason(raw) == expected


def test_is_truncated_only_for_length_and_content_filter() -> None:
    assert is_truncated("length") and is_truncated("content_filter")
    # unknown (None) must NOT count as truncated — many providers never send finish_reason
    assert not is_truncated(None) and not is_truncated("stop") and not is_truncated("tool_calls")


# ------------------------------------------------------------------ the two required end states

def test_stream_normal_stop_is_success(novel, monkeypatch) -> None:
    _patch_stream(monkeypatch, [_chunk("夕阳把走廊拉得很长，"), _chunk("广播里传来钢琴曲。"), _chunk(None, "stop"), "data: [DONE]"])
    frames = _run_stream(novel, temperature=0.7)
    done = next(d for n, d in frames if n == "done")
    assert done["finish_reason"] == "stop" and done["truncated"] is False
    assert [d["content"] for n, d in frames if n == "delta"] == ["夕阳把走廊拉得很长，", "广播里传来钢琴曲。"]
    row = _last_log(novel)
    assert row["finish_reason"] == "stop" and row["temperature"] == pytest.approx(0.7)


def test_stream_length_is_flagged_truncated(novel, monkeypatch) -> None:
    _patch_stream(monkeypatch, [_chunk("写到一半"), _chunk("被截断的"), _chunk(None, "length"), "data: [DONE]"])
    frames = _run_stream(novel, temperature=0.8)
    names = [n for n, _ in frames]
    assert names[0] == "meta" and names[-1] == "done"  # the stream still ends normally
    done = frames[-1][1]
    assert done["finish_reason"] == "length" and done["truncated"] is True
    assert "error" not in names  # not an upstream error: the UI must decide from `truncated`
    row = _last_log(novel)
    assert row["finish_reason"] == "length" and row["output"] == "写到一半被截断的"


# ------------------------------------------------------------------ edge cases that occur in practice

def test_finish_reason_in_same_chunk_as_content(novel, monkeypatch) -> None:
    """Some OpenAI-compatible servers put the last text and finish_reason in ONE chunk."""
    _patch_stream(monkeypatch, [_chunk("前半"), _chunk("最后一截", "length"), "data: [DONE]"])
    frames = _run_stream(novel)
    assert "".join(d["content"] for n, d in frames if n == "delta") == "前半最后一截"  # content not lost
    assert frames[-1][1]["truncated"] is True


def test_usage_only_trailing_chunk_does_not_hide_finish_reason(novel, monkeypatch) -> None:
    usage = "data: " + json.dumps({"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 9}})
    _patch_stream(monkeypatch, [_chunk("正文"), _chunk(None, "length"), usage, "data: [DONE]"])
    done = _run_stream(novel)[-1][1]
    assert done["finish_reason"] == "length" and done["truncated"] is True


def test_missing_finish_reason_is_unknown_not_stop_and_not_truncated(novel, monkeypatch) -> None:
    """Providers that never send finish_reason must keep working: unknown -> success, logged as NULL."""
    _patch_stream(monkeypatch, [_chunk("只有正文"), "data: [DONE]"])
    done = _run_stream(novel)[-1][1]
    assert done["finish_reason"] is None and done["truncated"] is False
    assert _last_log(novel)["finish_reason"] is None  # NOT fabricated as 'stop'


def test_content_filter_is_also_truncation(novel, monkeypatch) -> None:
    _patch_stream(monkeypatch, [_chunk("部分"), _chunk(None, "content_filter"), "data: [DONE]"])
    done = _run_stream(novel)[-1][1]
    assert done["finish_reason"] == "content_filter" and done["truncated"] is True


def test_length_alias_max_tokens_is_normalized(novel, monkeypatch) -> None:
    _patch_stream(monkeypatch, [_chunk("x"), _chunk(None, "max_tokens"), "data: [DONE]"])
    done = _run_stream(novel)[-1][1]
    assert done["finish_reason"] == "length" and done["truncated"] is True


def test_last_non_null_finish_reason_wins_and_null_frames_ignored(novel, monkeypatch) -> None:
    _patch_stream(monkeypatch, [_chunk("a", None), _chunk("b", None), _chunk(None, "stop"), _chunk(None, None), "data: [DONE]"])
    assert _run_stream(novel)[-1][1]["finish_reason"] == "stop"


def test_malformed_frames_are_skipped_without_losing_the_end_state(novel, monkeypatch) -> None:
    _patch_stream(monkeypatch, ["data: {not json", "data: " + json.dumps({"choices": [None]}), _chunk("好"),
                                _chunk(None, "length"), "data: [DONE]"])
    frames = _run_stream(novel)
    assert frames[-1][1]["truncated"] is True and "".join(d["content"] for n, d in frames if n == "delta") == "好"


def test_upstream_connection_error_is_logged_as_error(novel, monkeypatch) -> None:
    @asynccontextmanager
    async def boom(self, method, url, **kwargs):
        raise httpx.ConnectError("down")
        yield  # pragma: no cover

    monkeypatch.setattr(httpx.AsyncClient, "stream", boom)
    frames = _run_stream(novel, temperature=0.5)
    assert frames[-1][0] == "error"
    row = _last_log(novel)
    assert row["finish_reason"] == "error" and row["temperature"] == pytest.approx(0.5)


def test_no_novel_uid_means_no_log_and_no_crash(monkeypatch) -> None:
    _patch_stream(monkeypatch, [_chunk("x"), _chunk(None, "stop"), "data: [DONE]"])
    assert _run_stream(None)[-1][1]["finish_reason"] == "stop"


def test_request_payload_still_carries_temperature(novel, monkeypatch) -> None:
    seen = _patch_stream(monkeypatch, [_chunk("x"), "data: [DONE]"])
    _run_stream(novel, temperature=0.65)
    assert seen[0]["temperature"] == 0.65 and seen[0]["stream"] is True


# ------------------------------------------------------------------ non-streaming

def _post_returning(monkeypatch, finish, content="ok"):
    async def fake_post(self, url, **kw):
        choice = {"message": {"content": content}}
        if finish is not ...:
            choice["finish_reason"] = finish
        return httpx.Response(200, json={"choices": [choice], "usage": {"prompt_tokens": 3, "completion_tokens": 4}},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


def _complete(uid, **kw):
    return asyncio.run(complete_chat(base_url="https://api.example.com/v1", api_key="sk-x", model="m",
                                     system_prompt="s", user_prompt="u", novel_uid=uid, task_type="memory_extract", **kw))


def test_complete_chat_records_length_and_temperature(novel, monkeypatch) -> None:
    _post_returning(monkeypatch, "length", '{"facts": [')
    res = _complete(novel, temperature=0.2)
    assert res.finish_reason == "length" and res.content == '{"facts": ['  # behaviour unchanged: no raise
    row = _last_log(novel)
    assert row["finish_reason"] == "length" and row["temperature"] == pytest.approx(0.2)


def test_complete_chat_without_finish_reason_stays_none(novel, monkeypatch) -> None:
    _post_returning(monkeypatch, ...)
    res = _complete(novel)
    assert res.finish_reason is None and _last_log(novel)["finish_reason"] is None


def test_complete_chat_default_temperature_is_logged(novel, monkeypatch) -> None:
    _post_returning(monkeypatch, "stop")
    _complete(novel)  # no temperature passed -> the function's default (0.7)
    assert _last_log(novel)["temperature"] == pytest.approx(0.7)


# ------------------------------------------------------------------ schema / migration

def test_new_database_has_the_columns(novel) -> None:
    with get_novel_db(novel) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(generation_logs)")]
    assert "temperature" in cols and "finish_reason" in cols


def test_old_database_is_migrated_without_touching_existing_rows(tmp_path: Path) -> None:
    """Simulate a pre-T7 novel.db (no new columns, populated rows) and run the real migration."""
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    init_novel_db(conn)
    # rebuild generation_logs WITHOUT the new columns to mimic an old database
    conn.executescript(
        """
        DROP TABLE generation_logs;
        CREATE TABLE generation_logs (
            id INTEGER PRIMARY KEY, task_type TEXT NOT NULL, model TEXT NOT NULL,
            template_id TEXT, template_ver TEXT, prompt TEXT NOT NULL, output TEXT,
            input_tokens INTEGER, output_tokens INTEGER, elapsed_ms INTEGER,
            chapter_id INTEGER, scene_id INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO generation_logs (task_type, model, prompt, output, input_tokens, output_tokens, elapsed_ms)
        VALUES ('memory_extract', 'deepseek-flash', 'P1', 'O1', 10, 20, 30),
               ('write_scene', 'deepseek-flash', 'P2', 'O2', 11, 21, 31);
        """
    )
    before = [tuple(r) for r in conn.execute("SELECT id, task_type, model, prompt, output, input_tokens, output_tokens, elapsed_ms FROM generation_logs ORDER BY id")]
    init_novel_db(conn)   # real migration path
    init_novel_db(conn)   # idempotent
    cols = [r[1] for r in conn.execute("PRAGMA table_info(generation_logs)")]
    after = [tuple(r) for r in conn.execute("SELECT id, task_type, model, prompt, output, input_tokens, output_tokens, elapsed_ms FROM generation_logs ORDER BY id")]
    old_new_vals = conn.execute("SELECT temperature, finish_reason FROM generation_logs").fetchall()
    conn.close()
    assert "temperature" in cols and "finish_reason" in cols
    assert before == after  # existing rows untouched
    assert all(r["temperature"] is None and r["finish_reason"] is None for r in old_new_vals)  # nothing fabricated
