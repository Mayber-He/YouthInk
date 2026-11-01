"""T2: constraints take effect per chapter phase; snapshot wording; audit script.

No live LLM. Uses in-memory / temp SQLite built from the real schema.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.db.init_schema import init_novel_db
from app.db.repositories.constraint_repo import ConstraintRepository
from app.schemas.constraints import ConstraintCreate

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _novel_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_novel_db(conn)
    return conn


def _seed_structure(conn: sqlite3.Connection) -> dict[str, int]:
    conn.execute("INSERT INTO novels (id, title) VALUES (1, '测试')")
    conn.execute("INSERT INTO volumes (id, novel_id, sort_order, title) VALUES (1, 1, 1, '卷一')")
    conn.execute("INSERT INTO arcs (id, volume_id, sort_order, title) VALUES (1, 1, 1, '弧一')")
    ch_ids = {}
    for i in (1, 2, 3):
        conn.execute(
            "INSERT INTO chapters (id, arc_id, sort_order, title) VALUES (?, 1, ?, ?)",
            (i, float(i), f"第{i}章"),
        )
        ch_ids[f"ch{i}"] = i
    conn.execute(
        "INSERT INTO characters (id, name, role, background) VALUES (1, '林夏', 'female_lead', '大一新生')"
    )
    conn.commit()
    return {**ch_ids, "char": 1}


def test_constraint_filtered_by_chapter_window() -> None:
    conn = _novel_conn()
    ids = _seed_structure(conn)
    repo = ConstraintRepository(conn)

    # A constraint only valid for chapters 2..3 (from ch2, until ch3).
    repo.create_constraint(
        ConstraintCreate(
            target_type="character",
            target_id=ids["char"],
            content="仅第2-3章生效的约束",
            severity="hard",
            valid_from_chapter_id=ids["ch2"],
            valid_until_chapter_id=ids["ch3"],
        )
    )
    # A constraint with no window -> always active.
    repo.create_constraint(
        ConstraintCreate(
            target_type="character",
            target_id=ids["char"],
            content="全程生效的约束",
            severity="hard",
        )
    )
    conn.commit()

    def active_contents(ch_id: int, sort_order: float) -> list[str]:
        rows = repo.list_active_for_chapter(ch_id, sort_order, [ids["char"]], [])
        return [c.content for c in rows]

    # Chapter 1 (sort 1.0): before window -> only the unscoped one.
    c1 = active_contents(ids["ch1"], 1.0)
    assert "全程生效的约束" in c1
    assert "仅第2-3章生效的约束" not in c1

    # Chapter 2 (sort 2.0): inside window -> both.
    c2 = active_contents(ids["ch2"], 2.0)
    assert "全程生效的约束" in c2
    assert "仅第2-3章生效的约束" in c2

    # Chapter 3 (sort 3.0): still inside window (until inclusive) -> both.
    c3 = active_contents(ids["ch3"], 3.0)
    assert "仅第2-3章生效的约束" in c3


def test_constraint_window_excludes_after_until() -> None:
    conn = _novel_conn()
    ids = _seed_structure(conn)
    repo = ConstraintRepository(conn)
    # valid only up to chapter 1.
    repo.create_constraint(
        ConstraintCreate(
            target_type="character",
            target_id=ids["char"],
            content="只在第1章生效",
            severity="hard",
            valid_from_chapter_id=ids["ch1"],
            valid_until_chapter_id=ids["ch1"],
        )
    )
    conn.commit()
    rows = repo.list_active_for_chapter(ids["ch2"], 2.0, [ids["char"]], [])
    assert all("只在第1章生效" not in c.content for c in rows)
    rows1 = repo.list_active_for_chapter(ids["ch1"], 1.0, [ids["char"]], [])
    assert any("只在第1章生效" in c.content for c in rows1)


def test_character_state_snapshot_wording(tmp_path: Path) -> None:
    """When no structured state changes exist, the context uses the new
    chapter-start snapshot wording, not the old '保持初始基准状态'."""
    from app.core.config import reset_config_for_testing
    from app.db.manager import ensure_global_db_initialized
    from app.main import create_app
    from fastapi.testclient import TestClient

    reset_config_for_testing(tmp_path / "test_data_t2")
    ensure_global_db_initialized()
    app = create_app()
    with TestClient(app) as client:
        uid = client.post("/api/v1/novels", json={"title": "T2文案"}).json()["novel_uid"]
        client.post(
            f"/api/v1/novels/{uid}/characters",
            json={"name": "林夏", "role": "female_lead", "background": "大一新生"},
        )
        v = client.post(f"/api/v1/novels/{uid}/outline/volumes", json={"title": "卷一"}).json()["id"]
        a = client.post(
            f"/api/v1/novels/{uid}/outline/arcs", json={"volume_id": v, "title": "弧一"}
        ).json()["id"]
        ch = client.post(
            f"/api/v1/novels/{uid}/outline/chapters",
            json={"arc_id": a, "title": "第一章", "synopsis": "林夏报到"},
        ).json()["id"]

        ctx = client.get(f"/api/v1/novels/{uid}/chapters/{ch}/context-preview").json()
        block = next(b for b in ctx["blocks"] if b["key"] == "character_states")
        assert "保持初始基准状态" not in block["content"]
        assert "本章起点" in block["content"]


def test_audit_script_runs_and_produces_report(tmp_path: Path) -> None:
    """The read-only audit script runs on a DB and writes a markdown report,
    flagging the居住地/陌生 contradiction case."""
    db_path = tmp_path / "novel.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_novel_db(conn)
    ids = _seed_structure(conn)
    # A location that 林夏 is related to (lives there).
    conn.execute(
        "INSERT INTO locations (id, name, related_chars) VALUES (1, '桂花巷', '[\"林夏\"]')"
    )
    # A constraint claiming 林夏 is unfamiliar with 桂花巷 -> should be flagged.
    repo = ConstraintRepository(conn)
    repo.create_constraint(
        ConstraintCreate(
            target_type="character",
            target_id=ids["char"],
            content="林夏对桂花巷完全陌生，不认识路",
            severity="hard",
        )
    )
    conn.commit()
    conn.close()

    out_path = tmp_path / "audit.md"
    result = subprocess.run(
        [sys.executable, "scripts/audit_constraints.py",
         "--db", str(db_path), "--out", str(out_path)],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out_path.exists()
    report = out_path.read_text(encoding="utf-8")
    assert "约束只读审计报告" in report
    assert "桂花巷" in report
    # The related_chars contradiction heuristic must fire.
    assert "可能冲突" in report
    assert "related_chars" in report


def test_audit_script_does_not_modify_db(tmp_path: Path) -> None:
    """Audit opens the DB read-only; row counts are unchanged after running."""
    db_path = tmp_path / "novel.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_novel_db(conn)
    ids = _seed_structure(conn)
    repo = ConstraintRepository(conn)
    repo.create_constraint(
        ConstraintCreate(target_type="novel", content="全书约束", severity="soft")
    )
    conn.commit()
    before = conn.execute("SELECT COUNT(*) AS n FROM constraints").fetchone()["n"]
    conn.close()

    subprocess.run(
        [sys.executable, "scripts/audit_constraints.py",
         "--db", str(db_path), "--out", str(tmp_path / "a.md")],
        cwd=str(BACKEND_ROOT), capture_output=True, text=True, check=True,
    )

    conn2 = sqlite3.connect(str(db_path))
    after = conn2.execute("SELECT COUNT(*) FROM constraints").fetchone()[0]
    conn2.close()
    assert before == after == 1
