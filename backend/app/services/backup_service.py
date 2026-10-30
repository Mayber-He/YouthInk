"""Snapshot backup and restoration service for per-novel novel.db."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from app.core.config import get_config
from app.core.exceptions import AppError
from app.db.manager import validate_novel_uid
from app.schemas.novel import BackupInfo


def create_novel_backup(novel_uid: str, reason: str = "manual") -> BackupInfo:
    """Create a safe SQLite snapshot backup in <novel_uid>/backups/."""
    validate_novel_uid(novel_uid)
    cfg = get_config()
    src_db = cfg.novel_db_path(novel_uid)
    if not src_db.exists():
        raise AppError("NOVEL_NOT_FOUND", f"作品数据库不存在: {novel_uid}", status_code=404)

    backups_dir = cfg.novel_backups_dir(novel_uid)
    backups_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    safe_reason = "".join(c for c in reason if c.isalnum() or c in ("-", "_")) or "snap"
    filename = f"novel_{timestamp}_{safe_reason}.db"
    dst_db = backups_dir / filename

    src_conn = sqlite3.connect(str(src_db))
    dst_conn = sqlite3.connect(str(dst_db))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    stat = dst_db.stat()
    return BackupInfo(
        filename=filename,
        size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    )


def list_novel_backups(novel_uid: str) -> list[BackupInfo]:
    """List all snapshot backups for a novel ordered newest first."""
    validate_novel_uid(novel_uid)
    cfg = get_config()
    backups_dir = cfg.novel_backups_dir(novel_uid)
    if not backups_dir.exists():
        return []

    items: list[BackupInfo] = []
    for f in backups_dir.glob("*.db"):
        stat = f.stat()
        items.append(
            BackupInfo(
                filename=f.name,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            )
        )
    items.sort(key=lambda b: b.created_at, reverse=True)
    return items


def restore_novel_backup(novel_uid: str, filename: str) -> BackupInfo:
    """Restore a specific backup file over <novel_uid>/novel.db (after creating a pre-restore snapshot)."""
    validate_novel_uid(novel_uid)
    if "/" in filename or "\\" in filename or ".." in filename:
        raise AppError("INVALID_BACKUP_NAME", "非法的备份文件名", status_code=400)

    cfg = get_config()
    backup_file: Path = cfg.novel_backups_dir(novel_uid) / filename
    if not backup_file.exists():
        raise AppError("BACKUP_NOT_FOUND", f"未找到备份文件: {filename}", status_code=404)

    # First snapshot current state before overwriting
    create_novel_backup(novel_uid, reason="pre_restore")

    target_db = cfg.novel_db_path(novel_uid)
    src_conn = sqlite3.connect(str(backup_file))
    dst_conn = sqlite3.connect(str(target_db))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    stat = backup_file.stat()
    return BackupInfo(
        filename=filename,
        size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    )
