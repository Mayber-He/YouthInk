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
            system_prompt="你是小说一致性审查员，只输出严格 JSON，不做任何解释。",
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
            summary = "未发现问题：正文与检查表一致"
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
        scenes = self._writing_repo.list_scenes(chapter_id)
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
                for c in self._entity_repo.list_characters()
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
            char_lines.append(
                f"[人物#{c.id}「{c.name}」] {c.role}；{c.background or ''}"
                f"{'；当前状态：' + states if states else ''}"
            )
        if char_lines:
            sections.append("【检查表C：出场人物核心属性】\n" + "\n".join(char_lines))

        return "\n\n".join(sections)

    @staticmethod
    def _build_prompt(ch, content: str, checklist: str) -> str:
        return (
            "你是小说一致性审查员。请逐项检查【待审正文】是否违反以下检查表，"
            "只输出存在问题的项（遵守的项不要输出）。\n\n"
            f"{checklist}\n\n"
            f"待审正文（第 {ch.display_index} 章《{ch.title}》）：\n{content[:6000]}\n\n"
            "输出严格 JSON：{\"issues\": [{\"check_type\": \"constraint|fact|character\", "
            "\"ref_id\": 检查表编号, \"ref_label\": \"如 硬约束#1\", "
            "\"verdict\": \"violation|suspicious\", "
            "\"evidence_quote\": \"正文原句证据\", "
            "\"description\": \"违反说明\", \"suggestion\": \"一句话修改建议\"}]}。\n"
            "判定标准：violation=明确违反检查表；suspicious=疑似但证据不足。"
            "不要输出任何解释文字。"
        )
