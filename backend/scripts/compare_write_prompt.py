"""对比“同一场景”的写作提示词字符数（改动前 vs 改动后），并输出示例。

只读：在一份数据副本上构建提示词，不调用任何 LLM，不改动数据库内容。
改动前的基线通过 --legacy 开关复现（WritingService 里保留的旧拼装路径），
改动后为默认路径。两者用同一场景，便于量化“瘦身”效果。

用法：
  cd backend
  python scripts/compare_write_prompt.py --data-dir <含 global.db 与 novel_xxx/ 的数据副本目录> \
      --novel novel_cf825d92d2d9 --chapter-id 2 --scene-index 1 \
      --out ../docs/loop/prompt_after.md

不要对线上 backend/data 直接运行写入类脚本；本脚本虽只读，仍建议指向备份副本。
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))


def _open_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def main() -> None:
    parser = argparse.ArgumentParser(description="对比写作提示词改动前后字符数")
    parser.add_argument("--data-dir", required=True, help="数据副本目录（含 global.db 与 novel 目录）")
    parser.add_argument("--novel", required=True, help="作品目录名，如 novel_cf825d92d2d9")
    parser.add_argument("--chapter-id", type=int, required=True)
    parser.add_argument("--scene-index", type=int, default=1, help="本章第几个场景（从 1 起）")
    parser.add_argument("--out", default=str(REPO_ROOT / "docs" / "loop" / "prompt_after.md"))
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    os.environ["YOUTHINK_DATA_DIR"] = str(data_dir)

    from app.core.config import reset_config_for_testing
    from app.db.repositories.settings_repo import SettingsRepository
    from app.schemas.writing import StreamWriteRequest
    from app.services.writing_service import WritingService

    reset_config_for_testing(data_dir)

    novel_db = data_dir / args.novel / "novel.db"
    global_db = data_dir / "global.db"
    if not novel_db.exists() or not global_db.exists():
        raise SystemExit(f"数据副本不完整：{novel_db} / {global_db}")

    nconn = _open_ro(novel_db)
    gconn = _open_ro(global_db)
    try:
        svc = WritingService(args.novel, nconn, SettingsRepository(gconn))
        scenes = svc._writing_repo.list_scenes(args.chapter_id)
        if not scenes:
            raise SystemExit(f"章节 {args.chapter_id} 没有场景，请先拆场景或换章节")
        idx = max(1, min(args.scene_index, len(scenes)))
        scene = scenes[idx - 1]
        req = StreamWriteRequest(
            chapter_id=args.chapter_id, scene_id=scene.id, mode="scene", existing_content=""
        )

        legacy_sys, legacy_user = svc.prepare_stream_write_prompts(req, "", legacy=True)
        new_sys, new_user = svc.prepare_stream_write_prompts(req, "")
    finally:
        nconn.close()
        gconn.close()

    def total(s: str, u: str) -> int:
        return len(s) + len(u)

    lt, nt = total(legacy_sys, legacy_user), total(new_sys, new_user)
    ls, ns = len(legacy_sys), len(new_sys)
    lu, nu = len(legacy_user), len(new_user)

    def pct(old: int, new: int) -> str:
        return f"{(1 - new / old) * 100:.1f}%" if old else "n/a"

    lines = [
        "# 写作提示词改动前后对比（同一场景）",
        "",
        f"- 作品：`{args.novel}`　章节 id：{args.chapter_id}　场景序号：{idx}（scene_id={scene.id}）",
        "- 方法：在数据副本上分别用旧拼装路径（legacy）与新路径构建提示词，字符数 = Python `len()`。",
        "",
        "| 部分 | 改动前 | 改动后 | 减少 |",
        "|---|---:|---:|---:|",
        f"| system | {ls} | {ns} | {pct(ls, ns)} |",
        f"| user | {lu} | {nu} | {pct(lu, nu)} |",
        f"| **合计** | **{lt}** | **{nt}** | **{pct(lt, nt)}** |",
        "",
        "## 改动后 · system",
        "",
        "```text",
        new_sys,
        "```",
        "",
        "## 改动后 · user",
        "",
        "```text",
        new_user,
        "```",
        "",
    ]
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"legacy total={lt} (system={ls}, user={lu})")
    print(f"new    total={nt} (system={ns}, user={nu})")
    print(f"reduction={pct(lt, nt)}")
    print(f"report -> {out_path}")


if __name__ == "__main__":
    main()
