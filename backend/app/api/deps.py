"""FastAPI dependencies for database sessions, repositories, and services."""

from __future__ import annotations

from typing import Iterator
from fastapi import Path

from app.db.manager import get_global_db, get_novel_db
from app.db.repositories.constraint_repo import ConstraintRepository
from app.db.repositories.entity_repo import EntityRepository
from app.db.repositories.memory_repo import MemoryRepository
from app.db.repositories.novel_repo import NovelRepository
from app.db.repositories.outline_repo import OutlineRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.db.repositories.writing_repo import WritingRepository
from app.services.context.assembler import ContextAssembler
from app.services.memory.consistency import ConsistencyReviewService
from app.services.memory.finalizer import ChapterFinalizerService
from app.services.rag.retriever import HybridRagRetriever
from app.services.setting_generator import SettingGeneratorService
from app.services.writing_service import WritingService


def get_settings_repo() -> Iterator[SettingsRepository]:
    """Yield a SettingsRepository backed by global.db."""
    with get_global_db() as conn:
        yield SettingsRepository(conn)


def get_novel_repo(
    novel_uid: str = Path(..., description="Unique novel directory identifier"),
) -> Iterator[NovelRepository]:
    """Yield a NovelRepository backed by <novel_uid>/novel.db."""
    with get_novel_db(novel_uid) as conn:
        yield NovelRepository(conn, novel_uid)


def get_entity_repo(
    novel_uid: str = Path(..., description="Unique novel directory identifier"),
) -> Iterator[EntityRepository]:
    """Yield an EntityRepository backed by <novel_uid>/novel.db."""
    with get_novel_db(novel_uid) as conn:
        yield EntityRepository(conn)


def get_outline_repo(
    novel_uid: str = Path(..., description="Unique novel directory identifier"),
) -> Iterator[OutlineRepository]:
    """Yield an OutlineRepository backed by <novel_uid>/novel.db."""
    with get_novel_db(novel_uid) as conn:
        yield OutlineRepository(conn)


def get_writing_repo(
    novel_uid: str = Path(..., description="Unique novel directory identifier"),
) -> Iterator[WritingRepository]:
    """Yield a WritingRepository backed by <novel_uid>/novel.db."""
    with get_novel_db(novel_uid) as conn:
        yield WritingRepository(conn)


def get_memory_repo(
    novel_uid: str = Path(..., description="Unique novel directory identifier"),
) -> Iterator[MemoryRepository]:
    """Yield a MemoryRepository backed by <novel_uid>/novel.db."""
    with get_novel_db(novel_uid) as conn:
        yield MemoryRepository(conn)


def get_constraint_repo(
    novel_uid: str = Path(..., description="Unique novel directory identifier"),
) -> Iterator[ConstraintRepository]:
    """Yield a ConstraintRepository backed by <novel_uid>/novel.db."""
    with get_novel_db(novel_uid) as conn:
        yield ConstraintRepository(conn)


def get_setting_generator(
    novel_uid: str = Path(..., description="Unique novel directory identifier"),
) -> Iterator[SettingGeneratorService]:
    """Yield a SettingGeneratorService connected to both novel.db and global.db."""
    with get_novel_db(novel_uid) as novel_conn, get_global_db() as global_conn:
        yield SettingGeneratorService(
            novel_uid=novel_uid,
            novel_repo=NovelRepository(novel_conn, novel_uid),
            entity_repo=EntityRepository(novel_conn),
            outline_repo=OutlineRepository(novel_conn),
            settings_repo=SettingsRepository(global_conn),
            constraint_repo=ConstraintRepository(novel_conn),
        )


def get_context_assembler(
    novel_uid: str = Path(..., description="Unique novel directory identifier"),
) -> Iterator[ContextAssembler]:
    """Yield a ContextAssembler connected to both novel.db and global.db."""
    with get_novel_db(novel_uid) as novel_conn, get_global_db() as global_conn:
        yield ContextAssembler(
            novel_conn=novel_conn,
            novel_uid=novel_uid,
            settings_repo=SettingsRepository(global_conn),
        )


def get_writing_service(
    novel_uid: str = Path(..., description="Unique novel directory identifier"),
) -> Iterator[WritingService]:
    """Yield a WritingService connected to both novel.db and global.db."""
    with get_novel_db(novel_uid) as novel_conn, get_global_db() as global_conn:
        yield WritingService(
            novel_uid=novel_uid,
            novel_conn=novel_conn,
            settings_repo=SettingsRepository(global_conn),
        )


def get_chapter_finalizer(
    novel_uid: str = Path(..., description="Unique novel directory identifier"),
) -> Iterator[ChapterFinalizerService]:
    """Yield a ChapterFinalizerService connected to both novel.db and global.db."""
    with get_novel_db(novel_uid) as novel_conn, get_global_db() as global_conn:
        yield ChapterFinalizerService(
            novel_uid=novel_uid,
            novel_conn=novel_conn,
            global_conn=global_conn,
        )


def get_consistency_service(
    novel_uid: str = Path(..., description="Unique novel directory identifier"),
) -> Iterator[ConsistencyReviewService]:
    """Yield a ConsistencyReviewService connected to both novel.db and global.db."""
    with get_novel_db(novel_uid) as novel_conn, get_global_db() as global_conn:
        yield ConsistencyReviewService(
            novel_uid=novel_uid,
            novel_conn=novel_conn,
            settings_repo=SettingsRepository(global_conn),
        )


def get_rag_retriever(
    novel_uid: str = Path(..., description="Unique novel directory identifier"),
) -> Iterator[HybridRagRetriever]:
    """Yield a HybridRagRetriever connected to both novel.db and global.db."""
    with get_novel_db(novel_uid) as novel_conn, get_global_db() as global_conn:
        yield HybridRagRetriever(
            novel_uid=novel_uid,
            novel_conn=novel_conn,
            global_conn=global_conn,
        )
