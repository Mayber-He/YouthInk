"""Checklist-based Consistency Review (Phase 3): an independent reviewer pass over chapter text."""

from __future__ import annotations

import json
import sqlite3

from app.core.exceptions import AppError
from app.db.repositories.constraint_repo import ConstraintRepository
from app.db.repositories.entity_repo import EntityRepository
from app.db.repositories.outline_repo import OutlineRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.db.repositories.writing_repo import WritingRepository
from app.schemas.consistency import (
    ConsistencyIssue,
    ConsistencyReviewResponse,
    ConsistencyReviewSummary,
    LlmConsistencyOutput,
)
from app.services.llm.client import complete_chat
from app.services.llm.json_parser import parse_and_validate_json


class ConsistencyReviewService:
    """Runs an LLM reviewer against an explicit checklist; flags only, never auto-edits."""

    def __init__(
        self,
        novel_uid: str,
        novel_conn: sqlite3.Connection,
        settings_repo: SettingsRepository,
    ) -> None:
        self._novel_uid = novel_uid
        self._conn = novel_conn
        self._outline_repo = OutlineRepository(novel_conn)
        self._writing_repo = WritingRepository(novel_conn)
        self._entity_repo = EntityRepository(novel_conn)
        self._constraint_repo = ConstraintRepository(novel_conn)
        self._settings_repo = settings_repo

    async def run_review(self, chapter_id: int) -> ConsistencyReviewResponse:
        ch = self._outline_repo.get_chapter(chapter_id)
        versions = self._writing_repo.list_versions(chapter_id)
        latest = versions[0] if versions else None
        content = latest.content.strip() if latest else ""
        if not content:
            raise AppError("EMPTY_CHAPTER_CONTENT", "章节正文为空，无法执行一致性审查。", 400)

        checklist = self._build_checklist(chapter_id, ch.sort_order)
        prompt = self._build_prompt(ch, content, checklist)

        _pid, base_url, model, api_key = self._settings_repo.get_credentials_for_task("extract")
        res = await complete_chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt="你是小说一致性与常理逻辑审查员，只输出严格 JSON，不做任何解释。",
            user_prompt=prompt,
            novel_uid=self._novel_uid,
            task_type="consistency_review",
            chapter_id=chapter_id,
        )
        parsed = await parse_and_validate_json(res.content, LlmConsistencyOutput)
        issues = [i for i in parsed.issues if i.verdict in ("violation", "suspicious")]
        violation_count = sum(1 for i in issues if i.verdict == "violation")
        suspicious_count = len(issues) - violation_count
        if not issues:
            summary = "未发现问题：正文与检查表及常理逻辑一致"
        else:
            parts = []
            if violation_count:
                parts.append(f"{violation_count} 项违反")
            if suspicious_count:
                parts.append(f"{suspicious_count} 项可疑")
            summary = "发现" + "、".join(parts)

        cur = self._conn.execute(
            """
            INSERT INTO consistency_reviews (
                chapter_id, version_id, summary, issue_count, violation_count, issues_json, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chapter_id,
                latest.id if latest else None,
                summary,
                len(issues),
                violation_count,
                json.dumps([i.model_dump() for i in issues], ensure_ascii=False),
                model,
            ),
        )
        self._conn.commit()
        return self.get_review(int(cur.lastrowid or 0))

    def get_review(self, review_id: int) -> ConsistencyReviewResponse:
        row = self._conn.execute(
            "SELECT * FROM consistency_reviews WHERE id = ?", (review_id,)
        ).fetchone()
        if row is None:
            raise AppError("REVIEW_NOT_FOUND", f"未找到审查记录 #{review_id}", status_code=404)
        return ConsistencyReviewResponse(
            id=int(row["id"]),
            chapter_id=int(row["chapter_id"]),
            version_id=row["version_id"],
            summary=str(row["summary"]),
            issue_count=int(row["issue_count"]),
            violation_count=int(row["violation_count"]),
            issues=[ConsistencyIssue(**d) for d in json.loads(row["issues_json"] or "[]")],
            model=str(row["model"] or ""),
            created_at=str(row["created_at"]),
        )

    def list_reviews(self, chapter_id: int) -> list[ConsistencyReviewSummary]:
        rows = self._conn.execute(
            "SELECT * FROM consistency_reviews WHERE chapter_id = ? ORDER BY id DESC",
            (chapter_id,),
        ).fetchall()
        return [
            ConsistencyReviewSummary(
                id=int(r["id"]),
                chapter_id=int(r["chapter_id"]),
                summary=str(r["summary"]),
                issue_count=int(r["issue_count"]),
                violation_count=int(r["violation_count"]),
                created_at=str(r["created_at"]),
            )
            for r in rows
        ]

    def _build_checklist(self, chapter_id: int, sort_order: float) -> str:
        ch = self._outline_repo.get_chapter(chapter_id)
        scenes = self._writing_repo.list_scenes(chapter_id)
        all_chars = self._entity_repo.list_characters()
        char_name_by_id = {c.id: c.name for c in all_chars}

        char_ids = sorted(
            {
                cid
                for s in scenes
                for cid in ([s.pov_character] if s.pov_character else []) + s.character_ids
            }
        )
        loc_ids = sorted({s.location_id for s in scenes if s.location_id})
        if not char_ids:
            char_ids = [
                c.id
                for c in all_chars
                if c.role in ("female_lead", "male_lead", "major")
            ]

        sections: list[str] = []

        constraints = self._constraint_repo.list_active_for_chapter(
            chapter_id, sort_order, char_ids, loc_ids
        )
        if constraints:
            lines = [
                f"[#{c.id}]【{'硬约束' if c.severity == 'hard' else '软约束'}"
                f"·{c.target_type}{'「' + c.target_name + '」' if c.target_name else ''}】{c.content}"
                for c in constraints
            ]
            sections.append("【检查表A：硬约束/软约束】（违反=事故）\n" + "\n".join(lines))

        fact_rows = self._conn.execute(
            """
            SELECT f.id, f.content FROM facts f
            LEFT JOIN chapters c ON c.id = f.chapter_id
            WHERE f.status IN ('confirmed', 'locked')
              AND (c.sort_order IS NULL OR c.sort_order <= ?)
            ORDER BY f.id DESC LIMIT 15
            """,
            (sort_order,),
        ).fetchall()
        if fact_rows:
            lines = [f"[#{r['id']}] {r['content']}" for r in fact_rows]
            sections.append("【检查表B：已确认事实】\n" + "\n".join(lines))

        char_lines: list[str] = []
        for cid in char_ids:
            try:
                c = self._entity_repo.get_character(cid)
            except AppError:
                continue
            snap = self._entity_repo.get_character_timeline_snapshot(cid, sort_order)
            states = "；".join(f"{k}:{v}" for k, v in snap.current_states.items())
            rels = (
                "；".join(
                    f"{r['char_a_name']}↔{r['char_b_name']}({r['rel_type']})"
                    for r in snap.relationships
                )
                or "尚未熟稔/初见"
            )
            char_lines.append(
                f"[人物#{c.id}「{c.name}」] {c.role}；身份背景：{c.background or '未填'}"
                f"{'；当前状态：' + states if states else ''}；当前关系：{rels}"
            )
        if char_lines:
            sections.append("【检查表C：出场人物核心属性与时序状态】\n" + "\n".join(char_lines))

        scene_summary_lines = [
            f"本章梗概：{ch.synopsis or '无'}（故事时间：{ch.story_time or '未指定'}）"
        ]
        for idx, s in enumerate(scenes, start=1):
            pov_name = char_name_by_id.get(s.pov_character, "未指定") if s.pov_character else "未指定"
            present = [char_name_by_id[cid] for cid in s.character_ids if cid in char_name_by_id]
            scene_summary_lines.append(
                f"场景{idx}（POV：{pov_name}；在场：{'、'.join(present) or '未指定'}）：{s.beat}"
            )

        common_sense_lines = [
            *scene_summary_lines,
            "[#901]【环境与空间熟悉度常理】若角色属于初次到访（如新生刚报到、刚转学、首次踏足某场所），绝不能表现得对校园/建筑/路线熟门熟路、轻车熟路；空间移动需有合理过渡，不能瞬移。",
            "[#902]【人际关系与初见边界】初次见面或尚未熟稔的角色之间，绝不能无铺垫自来熟、绝不能未经自我介绍或他人提及便直呼对方姓名/绰号/知晓对方过往隐私。",
            "[#903]【限知视角与超知边界】POV 视角人物绝不能开启上帝视角直接读取他人内心独白，也绝不能知晓其不在场时发生的事件或尚未揭晓的秘密。",
            "[#904]【时间、季节与物理状态连续性】正文中的昼夜时间流速、季节气候与人物穿着、身体伤病限制、随身携带物品必须前后自洽，不能出现物理与季节常识矛盾。",
            "[#905]【在场状态与身份常识】未到场或已离场的角色绝不能凭空插话或参与互动；人物言行、消费与技能不得违背其年龄、学生身份或时代背景常识。",
        ]
        sections.append("【检查表D：本章情境与六大常理逻辑自洽】\n" + "\n".join(common_sense_lines))

        prev_tail = self._writing_repo.get_previous_chapter_text(sort_order, tail_chars=1200)
        if prev_tail:
            sections.append(
                "【检查表E：跨章连贯】\n"
                f"{prev_tail}\n"
                "[#951]【重复揭示】上一章已交代的信息，本章不得当作新信息重新揭示，角色不得再次询问已知答案。\n"
                "[#952]【悬念承接】上一章结尾留下的悬念、承诺或人物情绪，本章须有承接或交代，不能凭空断档。\n"
                "[#953]【时间日期衔接】本章故事时间、日期与上一章及已交代的计划（如报到日、“下周”“明天”）须一致。"
            )

        return "\n\n".join(sections)

    @staticmethod
    def _build_prompt(ch, content: str, checklist: str) -> str:
        return (
            "你是小说一致性与常理逻辑审查员。请逐项检查【待审正文】是否违反以下检查表（含A硬软约束、B已确认事实、C人物属性、D情境常理逻辑与E跨章连贯），"
            "只输出存在问题的项（遵守的项不要输出）。\n\n"
            f"{checklist}\n\n"
            f"待审正文（第 {ch.display_index} 章《{ch.title}》）：\n{content[:6000]}\n\n"
            "输出严格 JSON：{\"issues\": [{\"check_type\": \"constraint|fact|character|common_sense|continuity\", "
            "\"ref_id\": 检查表编号, \"ref_label\": \"如 硬约束#1、常理#901 或 连贯#951\", "
            "\"verdict\": \"violation|suspicious\", "
            "\"evidence_quote\": \"正文原句证据\", "
            "\"description\": \"违反说明（指出为何违背设定或常理）\", \"suggestion\": \"一句话修改建议\"}]}。\n"
            "判定标准：violation=明确违反检查表或违反情境常理（例如新生刚报到却对学校熟门熟路、初见未介绍却直呼姓名、上帝视角读心等）；suspicious=疑似但证据不足。"
            "不要输出任何解释文字。"
        )
