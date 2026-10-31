"""Dual-database connection manager for global.db and per-novel <novel_uid>/novel.db."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3
from typing import Iterator

from app.core.config import get_config
from app.core.exceptions import AppError
from app.db.init_schema import init_global_db, init_novel_db

_SAFE_UID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_ENSURED_NOVEL_DB_PATHS: set[str] = set()


def validate_novel_uid(novel_uid: str) -> str:
    """Ensure novel_uid is a safe directory identifier without path traversal."""
    if not _SAFE_UID_PATTERN.match(novel_uid):
        raise AppError(
            code="INVALID_NOVEL_ID",
            message=f"无效的作品目录标识: {novel_uid}",
            status_code=400,
        )
    return novel_uid


def _open_sqlite(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode, foreign keys, and Row factory."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def ensure_global_db_initialized() -> None:
    """Ensure global.db exists and has schema + default seeds applied."""
    cfg = get_config()
    conn = _open_sqlite(cfg.global_db_path)
    try:
        init_global_db(conn)
    finally:
        conn.close()


@contextmanager
def get_global_db() -> Iterator[sqlite3.Connection]:
    """Context manager yielding a connection to global.db with transaction commit/rollback."""
    cfg = get_config()
    conn = _open_sqlite(cfg.global_db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_novel_db(novel_uid: str, create_if_missing: bool = False) -> Iterator[sqlite3.Connection]:
    """Context manager yielding a connection to <novel_uid>/novel.db."""
    validate_novel_uid(novel_uid)
    cfg = get_config()
    db_path = cfg.novel_db_path(novel_uid)
    if not create_if_missing and not db_path.exists():
        raise AppError(
            code="NOVEL_NOT_FOUND",
            message=f"未找到作品数据库: {novel_uid}",
            status_code=404,
        )
    is_new = not db_path.exists()
    db_key = str(db_path.resolve())
    conn = _open_sqlite(db_path)
    try:
        if is_new or db_key not in _ENSURED_NOVEL_DB_PATHS:
            init_novel_db(conn)
            cfg.novel_vectors_dir(novel_uid).mkdir(parents=True, exist_ok=True)
            cfg.novel_backups_dir(novel_uid).mkdir(parents=True, exist_ok=True)
            _ENSURED_NOVEL_DB_PATHS.add(db_key)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
