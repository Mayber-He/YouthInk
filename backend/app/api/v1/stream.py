"""SSE Streaming Routes for Scene/Chapter Writing and Selection Rewriting (/api/stream/*)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.db.manager import get_global_db, get_novel_db
from app.db.repositories.settings_repo import SettingsRepository
from app.schemas.writing import StreamRewriteRequest, StreamWriteRequest
from app.services.llm.client import stream_chat_sse
from app.services.writing_service import WritingService

router = APIRouter(prefix="/stream/novels/{novel_uid}", tags=["stream"])


@router.post("/write")
async def stream_write_prose(
    novel_uid: str,
    payload: StreamWriteRequest,
) -> StreamingResponse:
    with get_novel_db(novel_uid) as novel_conn, get_global_db() as global_conn:
        settings_repo = SettingsRepository(global_conn)
        _, base_url, model, api_key = settings_repo.get_credentials_for_task("writing")
        svc = WritingService(novel_uid, novel_conn, settings_repo)
        sys_prompt, user_prompt = svc.prepare_stream_write_prompts(payload)

    event_gen = stream_chat_sse(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=sys_prompt,
        user_prompt=user_prompt,
        temperature=0.8,
        novel_uid=novel_uid,
        task_type="write_scene" if payload.mode == "scene" else "write_chapter",
        chapter_id=payload.chapter_id,
        scene_id=payload.scene_id,
    )
    return StreamingResponse(
        event_gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/rewrite")
async def stream_rewrite_selection(
    novel_uid: str,
    payload: StreamRewriteRequest,
) -> StreamingResponse:
    with get_novel_db(novel_uid) as novel_conn, get_global_db() as global_conn:
        settings_repo = SettingsRepository(global_conn)
        _, base_url, model, api_key = settings_repo.get_credentials_for_task("writing")
        svc = WritingService(novel_uid, novel_conn, settings_repo)
        sys_prompt, user_prompt = svc.prepare_stream_rewrite_prompts(payload)

    event_gen = stream_chat_sse(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=sys_prompt,
        user_prompt=user_prompt,
        temperature=0.75,
        novel_uid=novel_uid,
        task_type=f"rewrite_{payload.action_type}",
        chapter_id=payload.chapter_id,
    )
    return StreamingResponse(
        event_gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
