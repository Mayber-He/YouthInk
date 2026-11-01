"""只读审计：列出某部作品的现有约束，启发式标出可能的冲突条目。

绝不修改数据库——以只读模式打开 novel.db。输出 Markdown 到
docs/loop/constraint_audit.md（或 --out 指定路径）。

用法：
  cd backend
  python scripts/audit_constraints.py --novel novel_cf825d92d2d9
  python scripts/audit_constraints.py --db data/novel_xxx/novel.db --out ../docs/loop/constraint_audit.md

启发式只提示“可能冲突”，供人工复核，不自动改任何数据。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent

# 表示“陌生/不熟悉”的约束常见措辞；若约束 target 是人物、内容含这些词，
# 而该约束绑定的地点正是人物的居住地/相关地点，则很可能自相矛盾。
_UNFAMILIAR_HINTS = ("不熟", "陌生", "不认识", "不知道", "初次", "第一次", "没来过", "没去过", "不清楚")
_FAMILIAR_HINTS = ("熟悉", "了如指掌", "熟门熟路", "常来", "住在", "居住", "家在", "长大")


def _open_ro(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_db(args: argparse.Namespace) -> Path:
    if args.db:
        return Path(args.db).resolve()
    if args.novel:
        return (BACKEND_ROOT / "data" / args.novel / "novel.db").resolve()
    raise SystemExit("必须提供 --db 或 --novel")


def _chapter_index(conn: sqlite3.Connection) -> dict[int, tuple[int, str, float]]:
    """chapter_id -> (display_index, title, sort_order)。"""
    rows = conn.execute(
        """
        SELECT c.id, c.title, c.sort_order FROM chapters c
        JOIN arcs a ON a.id = c.arc_id JOIN volumes v ON v.id = a.volume_id
        ORDER BY v.sort_order, a.sort_order, c.sort_order, c.id
        """
    ).fetchall()
    return {int(r["id"]): (i, str(r["title"] or ""), float(r["sort_order"]))
            for i, r in enumerate(rows, start=1)}


def _character_lookup(conn: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    return {int(r["id"]): r for r in conn.execute("SELECT * FROM characters").fetchall()}


def _location_lookup(conn: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    return {int(r["id"]): r for r in conn.execute("SELECT * FROM locations").fetchall()}


def _loc_related_names(loc: sqlite3.Row) -> list[str]:
    try:
        return [str(x) for x in json.loads(loc["related_chars"] or "[]")]
    except Exception:
        return []


def audit(conn: sqlite3.Connection) -> list[str]:
    chapters = _character_lookup  # placeholder to satisfy linters (unused)
    del chapters
    ch_idx = _chapter_index(conn)
    chars = _character_lookup(conn)
    locs = _location_lookup(conn)
    max_sort = max((v[2] for v in ch_idx.values()), default=0.0)

    constraints = conn.execute(
        "SELECT * FROM constraints ORDER BY id"
    ).fetchall()

    lines: list[str] = []
    lines.append("# 约束只读审计报告")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- 约束总数：{len(constraints)}")
    lines.append(f"- 章节总数：{len(ch_idx)}（最大 sort_order = {max_sort}）")
    lines.append("")
    lines.append("> 本报告仅为启发式提示，不修改任何数据。请人工复核标注的条目。")
    lines.append("")

    flagged = 0
    lines.append("## 全部约束清单")
    lines.append("")
    for c in constraints:
        cid = int(c["id"])
        content = str(c["content"] or "")
        target_type = str(c["target_type"])
        target_id = c["target_id"]
        sev = str(c["severity"])
        status = str(c["status"])
        vf, vu = c["valid_from_chapter_id"], c["valid_until_chapter_id"]

        target_name = ""
        if target_type == "character" and target_id in chars:
            target_name = str(chars[int(target_id)]["name"])
        elif target_type == "location" and target_id in locs:
            target_name = str(locs[int(target_id)]["name"])

        def ch_label(chapter_id: object) -> str:
            if chapter_id is None:
                return "—"
            info = ch_idx.get(int(chapter_id))
            return f"第{info[0]}章《{info[1]}》" if info else f"#{chapter_id}"

        window = f"[{ch_label(vf)} → {ch_label(vu)}]"
        head = f"### #{cid} [{sev}/{status}] {target_type}" + (
            f"「{target_name}」" if target_name else ""
        )
        lines.append(head)
        lines.append(f"- 生效范围：{window}")
        lines.append(f"- 内容：{content}")

        warnings = _flag_constraint(c, content, target_type, target_id, chars, locs, ch_idx, max_sort)
        if warnings:
            flagged += 1
            for w in warnings:
                lines.append(f"- ⚠️ 可能冲突：{w}")
        lines.append("")

    summary = f"## 小结\n\n- 标注为“可能冲突”的约束数：{flagged} / {len(constraints)}"
    lines.insert(8, summary + "\n")
    return lines


def _flag_constraint(
    c: sqlite3.Row,
    content: str,
    target_type: str,
    target_id: object,
    chars: dict[int, sqlite3.Row],
    locs: dict[int, sqlite3.Row],
    ch_idx: dict[int, tuple[int, str, float]],
    max_sort: float,
) -> list[str]:
    warnings: list[str] = []

    # 1) 人物“不熟悉某地”，但该地点的 related_chars 含该人物 / 人物背景提到住在该地。
    if target_type == "character" and target_id in chars and any(h in content for h in _UNFAMILIAR_HINTS):
        char = chars[int(target_id)]
        char_name = str(char["name"])
        background = str(char["background"] or "")
        for loc in locs.values():
            loc_name = str(loc["name"] or "")
            if not loc_name or loc_name not in content:
                continue
            related = _loc_related_names(loc)
            if char_name in related:
                warnings.append(
                    f"约束称“{char_name}”对「{loc_name}」陌生，但该地点 related_chars 含“{char_name}”，"
                    f"疑为其常驻/相关地点。"
                )
            if any(h in background for h in _FAMILIAR_HINTS) and loc_name in background:
                warnings.append(
                    f"约束称“{char_name}”对「{loc_name}」陌生，但人物背景提到与该地点的熟悉/居住关系。"
                )

    # 2) 生效范围窗口异常：from > until，或 until 已早于全书最大章（约束可能早已失效却仍 active）。
    vf, vu = c["valid_from_chapter_id"], c["valid_until_chapter_id"]
    if vf is not None and vu is not None:
        sf = ch_idx.get(int(vf), (0, "", 1e18))[2]
        su = ch_idx.get(int(vu), (0, "", -1e18))[2]
        if sf > su:
            warnings.append("生效起点章晚于终点章（valid_from 的 sort_order > valid_until），窗口为空。")
    if str(c["status"]) == "active" and vu is not None:
        su = ch_idx.get(int(vu), (0, "", 1e18))[2]
        if su < max_sort:
            warnings.append(
                "状态仍为 active，但 valid_until 已早于全书最新章节，可能应标记为 resolved。"
            )

    # 3) 约束文本自相矛盾：同时含“陌生”类与“熟悉”类措辞。
    if any(h in content for h in _UNFAMILIAR_HINTS) and any(h in content for h in _FAMILIAR_HINTS):
        warnings.append("约束文本同时出现“陌生/不熟”与“熟悉/居住”类措辞，表述可能自相矛盾。")

    return warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="只读审计现有约束，输出 Markdown 报告")
    parser.add_argument("--novel", help="作品目录名，如 novel_cf825d92d2d9（相对 backend/data）")
    parser.add_argument("--db", help="直接指定 novel.db 路径（优先于 --novel）")
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "docs" / "loop" / "constraint_audit.md"),
        help="输出 Markdown 路径",
    )
    args = parser.parse_args()

    db_path = _resolve_db(args)
    if not db_path.exists():
        raise SystemExit(f"数据库不存在：{db_path}")

    conn = _open_ro(db_path)
    try:
        lines = audit(conn)
    finally:
        conn.close()

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"审计完成：{db_path}")
    print(f"报告已写入：{out_path}")


if __name__ == "__main__":
    main()
