"""Novel project management, initiation form, and backup routes."""

from __future__ import annotations

import asyncio
from fastapi import APIRouter, Depends, status

from app.api.deps import get_novel_repo
from app.db.repositories.novel_repo import (
    NovelRepository,
    create_novel_project,
    delete_novel_project,
    list_all_novels,
)
from app.schemas.novel import BackupInfo, NovelCreate, NovelDetail, NovelUpdate
from app.services.backup_service import (
    create_novel_backup,
    list_novel_backups,
    restore_novel_backup,
)

router = APIRouter(prefix="/novels", tags=["novels"])


@router.get("", response_model=list[NovelDetail])
def list_novels() -> list[NovelDetail]:
    return list_all_novels()


@router.post("", response_model=NovelDetail, status_code=status.HTTP_201_CREATED)
def create_novel(payload: NovelCreate) -> NovelDetail:
    return create_novel_project(payload)


@router.get("/{novel_uid}", response_model=NovelDetail)
def get_novel(repo: NovelRepository = Depends(get_novel_repo)) -> NovelDetail:
    return repo.get_novel_detail()


@router.put("/{novel_uid}", response_model=NovelDetail)
def update_novel(
    payload: NovelUpdate,
    repo: NovelRepository = Depends(get_novel_repo),
) -> NovelDetail:
    return repo.update_novel(payload)


@router.delete("/{novel_uid}", status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,  # 显式禁用：避免新版 FastAPI 从 `-> None` 注解推断 response_model 导致 204 断言失败
)
def delete_novel(novel_uid: str) -> None:
    delete_novel_project(novel_uid)


@router.get("/{novel_uid}/backups", response_model=list[BackupInfo])
def get_backups(novel_uid: str) -> list[BackupInfo]:
    return list_novel_backups(novel_uid)


@router.post(
    "/{novel_uid}/backups",
    response_model=BackupInfo,
    status_code=status.HTTP_201_CREATED,
)
async def create_backup(novel_uid: str, reason: str = "manual") -> BackupInfo:
    return await asyncio.to_thread(create_novel_backup, novel_uid, reason)


@router.post("/{novel_uid}/backups/{filename}/restore", response_model=BackupInfo)
async def restore_backup(novel_uid: str, filename: str) -> BackupInfo:
    return await asyncio.to_thread(restore_novel_backup, novel_uid, filename)
