"""Repository for Volumes, Arcs, and Chapters with floating-point sort_order (Dev Doc 4.3)."""

from __future__ import annotations

import re
import sqlite3

from app.core.exceptions import AppError
from app.schemas.outline import (
    ArcCreate,
    ArcResponse,
    ArcTreeNode,
    ArcUpdate,
    ChapterCreate,
    ChapterResponse,
    ChapterUpdate,
    LlmChapterPlanItem,
    LlmVolumePlanItem,
    OutlineTreeResponse,
    VolumeCreate,
    VolumeResponse,
    VolumeTreeNode,
    VolumeUpdate,
)


def compute_float_sort_order(
    prev_sort: float | None, next_sort: float | None, default_max: float = 0.0
) -> float:
    """Calculate midpoint float sort_order for insertion or reordering (Dev Doc 4.3)."""
    if prev_sort is not None and next_sort is not None:
        return (prev_sort + next_sort) / 2.0
    if prev_sort is not None:
        return prev_sort + 1.0
    if next_sort is not None:
        return next_sort / 2.0 if next_sort > 0 else next_sort - 1.0
    return default_max + 1.0


_DATE_PATTERN = re.compile(
    r"(?:(?P<year>\d{4})年)?(?P<month>\d{1,2}|[一二三四五六七八九十]{1,3})月"
    r"(?P<day>\d{1,2}|[一二三四五六七八九十]{1,3})[日号]"
)


def _chinese_number(value: str) -> int:
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if value == "十":
        return 10
    if "十" in value:
        tens, _, ones = value.partition("十")
        return (digits[tens] if tens else 1) * 10 + (digits[ones] if ones else 0)
    if len(value) == 1:
        return digits[value]
    return int("".join(str(digits[char]) for char in value))


def _explicit_chapter_date(
    value: str, *, leading_only: bool = False
) -> tuple[int | None, int, int] | None:
    value = value.lstrip()
    match = _DATE_PATTERN.match(value) if leading_only else _DATE_PATTERN.search(value)
    if not match:
        return None
    month_text, day_text = match.group("month"), match.group("day")
    month = int(month_text) if month_text.isdigit() else _chinese_number(month_text)
    day = int(day_text) if day_text.isdigit() else _chinese_number(day_text)
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    year = int(match.group("year")) if match.group("year") else None
    return year, month, day


def _date_is_before(
    current: tuple[tuple[int | None, int, int], int | None],
    previous: tuple[tuple[int | None, int, int], int | None],
) -> bool:
    current_date, current_hour = current
    previous_date, previous_hour = previous
    current_year, current_month, current_day = current_date
    previous_year, previous_month, previous_day = previous_date
    if current_year is not None and previous_year is not None:
        date_is_before = (current_year, current_month, current_day) < (
            previous_year, previous_month, previous_day
        )
    else:
        current_day_of_year = current_month * 32 + current_day
        previous_day_of_year = previous_month * 32 + previous_day
        delta = current_day_of_year - previous_day_of_year
        # A large backwards jump is likely a year boundary (for example Dec 31 to Jan 1).
        date_is_before = delta < 0 and delta > -186
    if date_is_before:
        return True
    return (
        current_date == previous_date
        and current_hour is not None
        and previous_hour is not None
        and current_hour < previous_hour
    )


def _explicit_chapter_hour(value: str) -> int | None:
    match = re.search(
        r"(凌晨|清晨|早晨|上午|中午|下午|傍晚|晚上|夜里|深夜)?\s*"
        r"([0-9]{1,2}|[一二三四五六七八九十]{1,3})点(?:半)?",
        value,
    )
    if match:
        period, hour_text = match.groups()
        hour = int(hour_text) if hour_text.isdigit() else _chinese_number(hour_text)
        if period in ("下午", "傍晚", "晚上", "夜里", "深夜") and hour < 12:
            hour += 12
        elif period in ("凌晨", "清晨", "早晨") and hour == 12:
            hour = 0
        return hour if 0 <= hour <= 23 else None

    period_match = re.search(r"凌晨|清晨|早晨|上午|中午|下午|傍晚|晚上|夜里|深夜", value)
    if not period_match:
        return None
    return {
        "凌晨": 2,
        "清晨": 6,
        "早晨": 7,
        "上午": 9,
        "中午": 12,
        "下午": 14,
        "傍晚": 18,
        "晚上": 20,
        "夜里": 20,
        "深夜": 23,
    }[period_match.group()]


def _chapter_date_from_fields(
    story_time: str, synopsis: str
) -> tuple[tuple[int | None, int, int], int | None] | None:
    time_date = _explicit_chapter_date(story_time)
    synopsis_date = _explicit_chapter_date(synopsis, leading_only=True)
    if time_date and synopsis_date and time_date != synopsis_date:
        raise AppError(
            "CHAPTER_TIME_CONFLICT",
            "章节故事时间与梗概开头的日期不一致，请同步调整其中一处。",
            status_code=422,
        )
    chapter_date = time_date or synopsis_date
    if chapter_date is None:
        return None
    hour = _explicit_chapter_hour(story_time)
    if hour is None:
        hour = _explicit_chapter_hour(synopsis)
    return chapter_date, hour


def _validate_chapter_timeline(entries: list[tuple[str, str, str]]) -> None:
    previous: tuple[
        str, tuple[tuple[int | None, int, int], int | None], str
    ] | None = None
    report_day_anchor: tuple[tuple[int | None, int, int], str] | None = None
    for title, story_time, synopsis in entries:
        if re.search(r"回忆|倒叙|插叙", story_time):
            continue
        current_date = _chapter_date_from_fields(story_time, synopsis)
        report_date = _explicit_report_date(synopsis)
        if report_date is None and re.search(r"报到日|报到当天|报到那天", title):
            report_date = current_date[0] if current_date else None
        if report_date:
            if report_day_anchor and report_date != report_day_anchor[0]:
                anchor_year, anchor_month, anchor_day = report_day_anchor[0]
                year, month, day = report_date
                anchor_label = f"{anchor_year or ''}年{anchor_month}月{anchor_day}日"
                current_label = f"{year or ''}年{month}月{day}日"
                raise AppError(
                    "CHAPTER_EVENT_DATE_CONFLICT",
                    f"固定事件“报到”的日期冲突：前文已明确为{anchor_label}，但《{title}》安排在{current_label}。",
                    status_code=422,
                )
            report_day_anchor = (report_date, title)
        if current_date is None:
            continue
        if previous and _date_is_before(current_date, previous[1]):
            raise AppError(
                "CHAPTER_TIME_REVERSED",
                f"章节故事时间倒序：{previous[0]}（{previous[2]}）之后，"
                f"不能安排为 {title}（{story_time or '梗概中标注的日期'}）。"
                "请调整章节日期，或在故事时间中明确标注回忆/倒叙/插叙。",
                status_code=422,
            )
        previous = (title, current_date, story_time or synopsis[:32])


def _explicit_report_date(synopsis: str) -> tuple[int | None, int, int] | None:
    for match in _DATE_PATTERN.finditer(synopsis):
        remainder = synopsis[match.end():].split("，", 1)[0].split("。", 1)[0]
        if "报到" in remainder[:12]:
            return _explicit_chapter_date(match.group())
    return None


class OutlineRepository:
    """Data access layer for volumes, arcs, and chapters in novel.db."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _get_novel_id(self) -> int:
        row = self._conn.execute("SELECT id FROM novels ORDER BY id ASC LIMIT 1").fetchone()
        if not row:
            raise AppError("NOVEL_EMPTY", "作品未初始化", status_code=404)
        return int(row["id"])

    # --- Full Outline Tree ---

    def get_outline_tree(self) -> OutlineTreeResponse:
        vol_rows = self._conn.execute(
            "SELECT * FROM volumes ORDER BY sort_order ASC, id ASC"
        ).fetchall()
        arc_rows = self._conn.execute(
            "SELECT * FROM arcs ORDER BY sort_order ASC, id ASC"
        ).fetchall()
        ch_rows = self._conn.execute(
            "SELECT * FROM chapters ORDER BY sort_order ASC, id ASC"
        ).fetchall()

        # Assign sequential display_index across the entire novel (decoupled from sort_order/id)
        chapters_by_arc: dict[int, list[ChapterResponse]] = {}
        for idx, r in enumerate(ch_rows, start=1):
            ch = self._row_to_chapter(r, display_index=idx)
            chapters_by_arc.setdefault(ch.arc_id, []).append(ch)

        arcs_by_vol: dict[int, list[ArcTreeNode]] = {}
        for r in arc_rows:
            arc = self._row_to_arc(r)
            node = ArcTreeNode(**arc.model_dump(), chapters=chapters_by_arc.get(arc.id, []))
            arcs_by_vol.setdefault(arc.volume_id, []).append(node)

        volumes: list[VolumeTreeNode] = []
        for r in vol_rows:
            vol = self._row_to_volume(r)
            volumes.append(VolumeTreeNode(**vol.model_dump(), arcs=arcs_by_vol.get(vol.id, [])))

        return OutlineTreeResponse(volumes=volumes, total_chapters=len(ch_rows))

    # --- Volumes ---

    def create_volume(self, payload: VolumeCreate) -> VolumeResponse:
        novel_id = self._get_novel_id()
        max_sort = float(
            self._conn.execute("SELECT COALESCE(MAX(sort_order), 0.0) FROM volumes").fetchone()[0]
        )
        sort_order = payload.sort_order if payload.sort_order is not None else max_sort + 1.0
        cur = self._conn.execute(
            "INSERT INTO volumes (novel_id, sort_order, title, synopsis, goal) VALUES (?, ?, ?, ?, ?)",
            (novel_id, sort_order, payload.title.strip(), payload.synopsis, payload.goal),
        )
        return self.get_volume(int(cur.lastrowid))

    def get_volume(self, vol_id: int) -> VolumeResponse:
        row = self._conn.execute("SELECT * FROM volumes WHERE id = ?", (vol_id,)).fetchone()
        if not row:
            raise AppError("VOLUME_NOT_FOUND", f"未找到分卷 (id={vol_id})", status_code=404)
        return self._row_to_volume(row)

    def update_volume(self, vol_id: int, payload: VolumeUpdate) -> VolumeResponse:
        current = self.get_volume(vol_id)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return current
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [vol_id]
        self._conn.execute(
            f"UPDATE volumes SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        return self.get_volume(vol_id)

    def delete_volume(self, vol_id: int) -> None:
        self._conn.execute("DELETE FROM volumes WHERE id = ?", (vol_id,))

    # --- Arcs ---

    def create_arc(self, payload: ArcCreate) -> ArcResponse:
        self.get_volume(payload.volume_id)
        max_sort = float(
            self._conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0.0) FROM arcs WHERE volume_id = ?",
                (payload.volume_id,),
            ).fetchone()[0]
        )
        sort_order = payload.sort_order if payload.sort_order is not None else max_sort + 1.0
        cur = self._conn.execute(
            """
            INSERT INTO arcs (volume_id, sort_order, title, goal, core_conflict, start_chapter, end_chapter)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.volume_id,
                sort_order,
                payload.title.strip(),
                payload.goal,
                payload.core_conflict,
                payload.start_chapter,
                payload.end_chapter,
            ),
        )
        return self.get_arc(int(cur.lastrowid))

    def get_arc(self, arc_id: int) -> ArcResponse:
        row = self._conn.execute("SELECT * FROM arcs WHERE id = ?", (arc_id,)).fetchone()
        if not row:
            raise AppError("ARC_NOT_FOUND", f"未找到情节弧 (id={arc_id})", status_code=404)
        return self._row_to_arc(row)

    def update_arc(self, arc_id: int, payload: ArcUpdate) -> ArcResponse:
        current = self.get_arc(arc_id)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return current
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [arc_id]
        self._conn.execute(
            f"UPDATE arcs SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        return self.get_arc(arc_id)

    def delete_arc(self, arc_id: int) -> None:
        self._conn.execute("DELETE FROM arcs WHERE id = ?", (arc_id,))

    # --- Chapters ---

    def create_chapter(self, payload: ChapterCreate) -> ChapterResponse:
        self.get_arc(payload.arc_id)
        if payload.sort_order is not None:
            sort_order = payload.sort_order
        elif payload.after_chapter_id is not None or payload.before_chapter_id is not None:
            prev_s = (
                self.get_chapter(payload.after_chapter_id).sort_order
                if payload.after_chapter_id
                else None
            )
            next_s = (
                self.get_chapter(payload.before_chapter_id).sort_order
                if payload.before_chapter_id
                else None
            )
            sort_order = compute_float_sort_order(prev_s, next_s)
        else:
            max_sort = float(
                self._conn.execute("SELECT COALESCE(MAX(sort_order), 0.0) FROM chapters").fetchone()[0]
            )
            sort_order = max_sort + 1.0

        cur = self._conn.execute(
            """
            INSERT INTO chapters (arc_id, sort_order, title, synopsis, story_time, locked)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.arc_id,
                sort_order,
                payload.title.strip(),
                payload.synopsis,
                payload.story_time,
                int(payload.locked),
            ),
        )
        return self.get_chapter(int(cur.lastrowid))

    def get_chapter(self, chapter_id: int) -> ChapterResponse:
        row = self._conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
        if not row:
            raise AppError("CHAPTER_NOT_FOUND", f"未找到章节 (id={chapter_id})", status_code=404)
        rank = int(
            self._conn.execute(
                "SELECT COUNT(*) FROM chapters WHERE sort_order < ? OR (sort_order = ? AND id <= ?)",
                (row["sort_order"], row["sort_order"], row["id"]),
            ).fetchone()[0]
        )
        return self._row_to_chapter(row, display_index=max(1, rank))

    def _validate_chapter_time_order(
        self, chapter_id: int, sort_order: float, story_time: str, synopsis: str
    ) -> None:
        rows = self._conn.execute(
            "SELECT id, sort_order, title, story_time, synopsis FROM chapters "
            "WHERE id != ? ORDER BY sort_order, id",
            (chapter_id,),
        ).fetchall()
        timeline = [
            (
                float(row["sort_order"]),
                int(row["id"]),
                str(row["title"]),
                str(row["story_time"] or ""),
                str(row["synopsis"] or ""),
            )
            for row in rows
        ]
        timeline.append(
            (
                sort_order,
                chapter_id,
                self.get_chapter(chapter_id).title,
                story_time,
                synopsis,
            )
        )
        timeline.sort(key=lambda item: (item[0], item[1]))
        _validate_chapter_timeline(
            [
                (title, item_time, item_synopsis)
                for _, _, title, item_time, item_synopsis in timeline
            ]
        )

    def _validate_generated_chapter_timeline(
        self, arc_id: int, chapters_plan: list[LlmChapterPlanItem]
    ) -> None:
        retained = self._conn.execute(
            "SELECT title, story_time, synopsis FROM chapters "
            "WHERE arc_id = ? AND (locked = 1 OR status NOT IN ('pending', 'outline')) "
            "ORDER BY sort_order, id",
            (arc_id,),
        ).fetchall()
        entries = [
            (str(row["title"]), str(row["story_time"] or ""), str(row["synopsis"] or ""))
            for row in retained
        ]
        entries.extend(
            (chapter.title, chapter.story_time, chapter.synopsis) for chapter in chapters_plan
        )
        _validate_chapter_timeline(entries)

    def update_chapter(self, chapter_id: int, payload: ChapterUpdate) -> ChapterResponse:
        current = self.get_chapter(chapter_id)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return current
        if "story_time" in updates or "sort_order" in updates or "synopsis" in updates:
            self._validate_chapter_time_order(
                chapter_id,
                float(updates.get("sort_order", current.sort_order)),
                str(updates.get("story_time", current.story_time) or ""),
                str(updates.get("synopsis", current.synopsis) or ""),
            )
        if "locked" in updates:
            updates["locked"] = int(bool(updates["locked"]))
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [chapter_id]
        self._conn.execute(f"UPDATE chapters SET {set_clause} WHERE id = ?", values)
        return self.get_chapter(chapter_id)

    def reorder_chapter(
        self, chapter_id: int, prev_sort: float | None, next_sort: float | None
    ) -> ChapterResponse:
        new_sort = compute_float_sort_order(prev_sort, next_sort)
        return self.update_chapter(chapter_id, ChapterUpdate(sort_order=new_sort))

    def delete_chapter(self, chapter_id: int) -> None:
        self._conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))

    # --- AI Batch Structure & Rolling Arc Chapters ---

    def apply_generated_structure(self, volumes_plan: list[LlmVolumePlanItem]) -> OutlineTreeResponse:
        """Create volumes and arcs from AI plan (preserving any volumes that contain locked chapters)."""
        for v_item in volumes_plan:
            vol = self.create_volume(
                VolumeCreate(title=v_item.title, synopsis=v_item.synopsis, goal=v_item.goal)
            )
            for a_item in v_item.arcs:
                self.create_arc(
                    ArcCreate(
                        volume_id=vol.id,
                        title=a_item.title,
                        goal=a_item.goal,
                        core_conflict=a_item.core_conflict,
                        start_chapter=a_item.start_chapter,
                        end_chapter=a_item.end_chapter,
                    )
                )
        return self.get_outline_tree()

    def replace_unlocked_arc_chapters(
        self, arc_id: int, chapters_plan: list[LlmChapterPlanItem]
    ) -> OutlineTreeResponse:
        """Delete unlocked pending/outline chapters in arc_id and insert newly generated chapters."""
        self.get_arc(arc_id)
        self._validate_generated_chapter_timeline(arc_id, chapters_plan)
        self._conn.execute(
            "DELETE FROM chapters WHERE arc_id = ? AND locked = 0 AND status IN ('pending', 'outline')",
            (arc_id,),
        )
        for ch_item in chapters_plan:
            self.create_chapter(
                ChapterCreate(
                    arc_id=arc_id,
                    title=ch_item.title,
                    synopsis=ch_item.synopsis,
                    story_time=ch_item.story_time,
                    locked=False,
                )
            )
        return self.get_outline_tree()

    @staticmethod
    def _row_to_volume(row: sqlite3.Row) -> VolumeResponse:
        return VolumeResponse(
            id=int(row["id"]),
            novel_id=int(row["novel_id"]),
            sort_order=float(row["sort_order"]),
            title=str(row["title"]),
            synopsis=str(row["synopsis"] or ""),
            goal=str(row["goal"] or ""),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_arc(row: sqlite3.Row) -> ArcResponse:
        return ArcResponse(
            id=int(row["id"]),
            volume_id=int(row["volume_id"]),
            sort_order=float(row["sort_order"]),
            title=str(row["title"]),
            goal=str(row["goal"] or ""),
            core_conflict=str(row["core_conflict"] or ""),
            start_chapter=row["start_chapter"],
            end_chapter=row["end_chapter"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_chapter(row: sqlite3.Row, display_index: int = 1) -> ChapterResponse:
        return ChapterResponse(
            id=int(row["id"]),
            arc_id=int(row["arc_id"]),
            sort_order=float(row["sort_order"]),
            display_index=display_index,
            title=str(row["title"] or ""),
            synopsis=str(row["synopsis"] or ""),
            status=row["status"],
            word_count=int(row["word_count"] or 0),
            story_time=str(row["story_time"] or ""),
            locked=bool(row["locked"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
