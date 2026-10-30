"""OpenAI-compatible LLM client with non-streaming, SSE streaming, and token accounting."""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import AsyncIterator
import httpx

from app.core.exceptions import AppError
from app.db.manager import get_novel_db
from app.db.repositories.novel_repo import NovelRepository


@dataclass
class LlmCompletionResult:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    elapsed_ms: int


def build_chat_completions_url(base_url: str) -> str:
    """Normalize an OpenAI-compatible base_url into full /chat/completions endpoint."""
    cleaned = base_url.strip().rstrip("/")
    if cleaned.endswith("/chat/completions"):
        return cleaned
    if cleaned.endswith("/v1") or cleaned.endswith("/v3") or cleaned.endswith("/v4"):
        return f"{cleaned}/chat/completions"
    return f"{cleaned}/v1/chat/completions"


def estimate_tokens(text: str) -> int:
    """Lightweight token estimator (~1.5 tokens per CJK char or 0.75 per ASCII word)."""
    if not text:
        return 0
    cjk_count = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other_count = len(text) - cjk_count
    return max(1, int(cjk_count * 0.7 + other_count * 0.3))


async def complete_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    timeout_sec: float = 60.0,
    novel_uid: str | None = None,
    task_type: str = "general",
    template_id: str | None = None,
    template_ver: str | None = None,
    chapter_id: int | None = None,
    scene_id: int | None = None,
) -> LlmCompletionResult:
    """Execute a non-streaming OpenAI-compatible chat completion and record generation_logs."""
    url = build_chat_completions_url(base_url)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }

    start_ns = time.perf_counter_ns()
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise AppError(
            code="UPSTREAM_API_ERROR",
            message=f"大模型接口连接失败: {exc}",
            detail=str(exc),
            status_code=502,
        ) from exc

    elapsed_ms = int((time.perf_counter_ns() - start_ns) / 1_000_000)

    if resp.status_code >= 400:
        raise AppError(
            code="UPSTREAM_API_ERROR",
            message=f"大模型接口返回错误 (HTTP {resp.status_code})",
            detail=resp.text[:500],
            status_code=502,
        )

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise AppError(
            code="INVALID_UPSTREAM_RESPONSE",
            message="大模型返回数据结构不符合 OpenAI 规范",
            detail=str(data)[:500],
            status_code=502,
        ) from exc

    usage = data.get("usage") or {}
    in_tok = int(usage.get("prompt_tokens") or estimate_tokens(system_prompt + user_prompt))
    out_tok = int(usage.get("completion_tokens") or estimate_tokens(content))

    if novel_uid:
        _safe_log_generation(
            novel_uid=novel_uid,
            task_type=task_type,
            model=model,
            prompt=f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}",
            output=content,
            input_tokens=in_tok,
            output_tokens=out_tok,
            elapsed_ms=elapsed_ms,
            template_id=template_id,
            template_ver=template_ver,
            chapter_id=chapter_id,
            scene_id=scene_id,
        )

    return LlmCompletionResult(
        content=content,
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        elapsed_ms=elapsed_ms,
    )


async def stream_chat_sse(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.8,
    timeout_sec: float = 120.0,
    novel_uid: str | None = None,
    task_type: str = "writing",
    template_id: str | None = None,
    template_ver: str | None = None,
    chapter_id: int | None = None,
    scene_id: int | None = None,
) -> AsyncIterator[str]:
    """
    Yield standard YouthInk SSE events (meta, delta, done, error) per Dev Doc 5.2.
    Always records generation_logs even if stopped midway.
    """
    url = build_chat_completions_url(base_url)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    context_tokens = estimate_tokens(system_prompt + user_prompt)
    gen_id = int(time.time() * 1000) % 1_000_000
    yield _sse_event(
        "meta",
        {"generation_id": gen_id, "model": model, "context_tokens": context_tokens},
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }

    start_ns = time.perf_counter_ns()
    collected: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    err_body = (await resp.aread()).decode("utf-8", errors="replace")[:300]
                    yield _sse_event(
                        "error",
                        {
                            "code": "UPSTREAM_API_ERROR",
                            "message": f"API 返回错误 (HTTP {resp.status_code}): {err_body}",
                        },
                    )
                    return

                async for raw_line in resp.aiter_lines():
                    line = raw_line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {}).get("content")
                        if delta:
                            collected.append(delta)
                            yield _sse_event("delta", {"content": delta})
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

        elapsed_ms = int((time.perf_counter_ns() - start_ns) / 1_000_000)
        full_output = "".join(collected)
        out_tokens = estimate_tokens(full_output)
        yield _sse_event(
            "done",
            {
                "input_tokens": context_tokens,
                "output_tokens": out_tokens,
                "elapsed_ms": elapsed_ms,
            },
        )
    except httpx.HTTPError as exc:
        yield _sse_event(
            "error",
            {
                "code": "UPSTREAM_API_ERROR",
                "message": f"API 连接中断，已保留当前已生成片段 ({exc})",
            },
        )
    finally:
        elapsed_ms = int((time.perf_counter_ns() - start_ns) / 1_000_000)
        full_output = "".join(collected)
        if novel_uid:
            _safe_log_generation(
                novel_uid=novel_uid,
                task_type=task_type,
                model=model,
                prompt=f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}",
                output=full_output,
                input_tokens=context_tokens,
                output_tokens=estimate_tokens(full_output),
                elapsed_ms=elapsed_ms,
                template_id=template_id,
                template_ver=template_ver,
                chapter_id=chapter_id,
                scene_id=scene_id,
            )


def _sse_event(event_name: str, data: dict[str, object]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _safe_log_generation(
    *,
    novel_uid: str,
    task_type: str,
    model: str,
    prompt: str,
    output: str,
    input_tokens: int,
    output_tokens: int,
    elapsed_ms: int,
    template_id: str | None,
    template_ver: str | None,
    chapter_id: int | None,
    scene_id: int | None,
) -> None:
    try:
        with get_novel_db(novel_uid) as conn:
            repo = NovelRepository(conn, novel_uid)
            repo.record_generation_log(
                task_type=task_type,
                model=model,
                prompt=prompt,
                output=output,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                elapsed_ms=elapsed_ms,
                template_id=template_id,
                template_ver=template_ver,
                chapter_id=chapter_id,
                scene_id=scene_id,
            )
    except Exception:
        pass
