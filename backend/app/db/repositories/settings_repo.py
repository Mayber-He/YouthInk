"""Repository for global.db settings, LLM profiles, prompts, and styles."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.builtin.prompt_templates import BUILTIN_PROMPT_TEMPLATES
from app.core.exceptions import AppError
from app.core.security import decrypt_api_key, encrypt_api_key, safe_mask_encrypted_key
from app.schemas.settings import (
    LlmProfileCreate,
    LlmProfileResponse,
    LlmProfileUpdate,
    PromptTemplateItem,
    StyleTemplateCreate,
    StyleTemplateResponse,
    TaskAssignmentResponse,
    TaskAssignmentUpdate,
    TrustModeSettings,
)


class SettingsRepository:
    """Data access methods for global.db tables."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # --- LLM Profiles ---

    def list_llm_profiles(self) -> list[LlmProfileResponse]:
        rows = self._conn.execute(
            "SELECT * FROM llm_profiles ORDER BY is_default DESC, id ASC"
        ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    def get_llm_profile(self, profile_id: int) -> LlmProfileResponse:
        row = self._conn.execute(
            "SELECT * FROM llm_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if not row:
            raise AppError("PROFILE_NOT_FOUND", f"未找到模型档案 (id={profile_id})", status_code=404)
        return self._row_to_profile(row)

    def get_llm_credentials(self, profile_id: int | None = None) -> tuple[int, str, str, str]:
        """Return (id, base_url, model, decrypted_api_key) for given or default profile."""
        if profile_id is not None:
            row = self._conn.execute(
                "SELECT * FROM llm_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM llm_profiles ORDER BY is_default DESC, id ASC LIMIT 1"
            ).fetchone()
        if not row:
            raise AppError(
                "NO_LLM_PROFILE",
                "尚未配置可用的大模型档案，请先在「全局设置」中添加模型档案",
                status_code=400,
            )
        plain_key = decrypt_api_key(row["api_key_encrypted"])
        return int(row["id"]), str(row["base_url"]), str(row["model"]), plain_key

    def get_credentials_for_task(self, task_category: str) -> tuple[int, str, str, str]:
        """Resolve LLM credentials assigned to task_category (writing/planning/extract)."""
        row = self._conn.execute(
            "SELECT profile_id FROM task_model_assignments WHERE task_category = ?",
            (task_category,),
        ).fetchone()
        profile_id = int(row["profile_id"]) if row else None
        return self.get_llm_credentials(profile_id)

    def create_llm_profile(self, payload: LlmProfileCreate) -> LlmProfileResponse:
        encrypted = encrypt_api_key(payload.api_key)
        existing_count = self._conn.execute("SELECT COUNT(*) AS cnt FROM llm_profiles").fetchone()["cnt"]
        is_def = 1 if (payload.is_default or existing_count == 0) else 0
        if is_def:
            self._conn.execute("UPDATE llm_profiles SET is_default = 0")
        try:
            cur = self._conn.execute(
                """
                INSERT INTO llm_profiles (name, base_url, model, api_key_encrypted, is_default)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payload.name.strip(), payload.base_url.strip(), payload.model.strip(), encrypted, is_def),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError("DUPLICATE_PROFILE_NAME", f"模型档案名称已存在: {payload.name}", status_code=409) from exc
        return self.get_llm_profile(int(cur.lastrowid))

    def update_llm_profile(self, profile_id: int, payload: LlmProfileUpdate) -> LlmProfileResponse:
        row = self._conn.execute("SELECT * FROM llm_profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            raise AppError("PROFILE_NOT_FOUND", f"未找到模型档案 (id={profile_id})", status_code=404)
        name = payload.name.strip() if payload.name is not None else row["name"]
        base_url = payload.base_url.strip() if payload.base_url is not None else row["base_url"]
        model = payload.model.strip() if payload.model is not None else row["model"]
        encrypted = (
            encrypt_api_key(payload.api_key)
            if payload.api_key and payload.api_key.strip()
            else row["api_key_encrypted"]
        )
        is_def = int(payload.is_default) if payload.is_default is not None else int(row["is_default"])
        if is_def:
            self._conn.execute("UPDATE llm_profiles SET is_default = 0")
        self._conn.execute(
            """
            UPDATE llm_profiles
            SET name = ?, base_url = ?, model = ?, api_key_encrypted = ?, is_default = ?
            WHERE id = ?
            """,
            (name, base_url, model, encrypted, is_def, profile_id),
        )
        return self.get_llm_profile(profile_id)

    def delete_llm_profile(self, profile_id: int) -> None:
        cur = self._conn.execute("DELETE FROM llm_profiles WHERE id = ?", (profile_id,))
        if cur.rowcount == 0:
            raise AppError("PROFILE_NOT_FOUND", f"未找到模型档案 (id={profile_id})", status_code=404)

    # --- Task Model Assignments ---

    def get_task_assignments(self) -> TaskAssignmentResponse:
        rows = self._conn.execute("SELECT task_category, profile_id FROM task_model_assignments").fetchall()
        mapping = {r["task_category"]: int(r["profile_id"]) for r in rows}
        return TaskAssignmentResponse(
            writing=mapping.get("writing"),
            planning=mapping.get("planning"),
            extract=mapping.get("extract"),
        )

    def update_task_assignments(self, payload: TaskAssignmentUpdate) -> TaskAssignmentResponse:
        for category in ("writing", "planning", "extract"):
            if category not in payload.model_fields_set:
                continue
            prof_id = getattr(payload, category)
            if prof_id is None:
                self._conn.execute(
                    "DELETE FROM task_model_assignments WHERE task_category = ?",
                    (category,),
                )
                continue
            self.get_llm_profile(prof_id)
            self._conn.execute(
                """
                INSERT INTO task_model_assignments (task_category, profile_id)
                VALUES (?, ?)
                ON CONFLICT(task_category) DO UPDATE SET profile_id = excluded.profile_id
                """,
                (category, prof_id),
            )
        return self.get_task_assignments()

    # --- Prompt Templates ---

    def list_prompt_templates(self) -> list[PromptTemplateItem]:
        rows = self._conn.execute("SELECT * FROM prompt_templates").fetchall()
        overrides = {r["task_type"]: r for r in rows}
        items: list[PromptTemplateItem] = []
        for task_type, builtin in BUILTIN_PROMPT_TEMPLATES.items():
            ov = overrides.get(task_type)
            items.append(
                PromptTemplateItem(
                    task_type=task_type,
                    description=str(builtin["description"]),
                    content=str(ov["content"]) if ov else str(builtin["content"]),
                    version=str(ov["version"]) if ov else str(builtin["version"]),
                    is_overridden=ov is not None,
                    updated_at=str(ov["updated_at"]) if ov else None,
                )
            )
        return items

    def upsert_prompt_template(self, task_type: str, content: str, version: str = "custom-1.0") -> PromptTemplateItem:
        if task_type not in BUILTIN_PROMPT_TEMPLATES:
            raise AppError("UNKNOWN_TASK_TYPE", f"未知的 Prompt 任务类型: {task_type}", status_code=400)
        self._conn.execute(
            """
            INSERT INTO prompt_templates (task_type, content, version, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(task_type) DO UPDATE SET
                content = excluded.content,
                version = excluded.version,
                updated_at = datetime('now')
            """,
            (task_type, content, version),
        )
        return next(item for item in self.list_prompt_templates() if item.task_type == task_type)

    def reset_prompt_template(self, task_type: str) -> PromptTemplateItem:
        if task_type not in BUILTIN_PROMPT_TEMPLATES:
            raise AppError("UNKNOWN_TASK_TYPE", f"未知的 Prompt 任务类型: {task_type}", status_code=400)
        self._conn.execute("DELETE FROM prompt_templates WHERE task_type = ?", (task_type,))
        return next(item for item in self.list_prompt_templates() if item.task_type == task_type)

    # --- Style Templates ---

    def list_style_templates(self) -> list[StyleTemplateResponse]:
        rows = self._conn.execute("SELECT * FROM style_templates ORDER BY is_builtin DESC, id ASC").fetchall()
        return [self._row_to_style(r) for r in rows]

    def create_style_template(self, payload: StyleTemplateCreate) -> StyleTemplateResponse:
        try:
            cur = self._conn.execute(
                """
                INSERT INTO style_templates (
                    name, is_builtin, pov, tense_feel, tone, sentence_pref,
                    dialogue_ratio, desc_focus, pacing, example_paras, forbidden_exprs
                ) VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.name.strip(),
                    payload.pov,
                    payload.tense_feel,
                    payload.tone,
                    payload.sentence_pref,
                    payload.dialogue_ratio,
                    payload.desc_focus,
                    payload.pacing,
                    json.dumps(payload.example_paras, ensure_ascii=False),
                    json.dumps(payload.forbidden_exprs, ensure_ascii=False),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError("DUPLICATE_STYLE_NAME", f"风格模板已存在: {payload.name}", status_code=409) from exc
        row = self._conn.execute("SELECT * FROM style_templates WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self._row_to_style(row)

    # --- App Settings (Trust Mode, etc.) ---

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        self._conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
            """,
            (key, json.dumps(value, ensure_ascii=False)),
        )

    def get_trust_mode(self) -> TrustModeSettings:
        data = self.get_setting("trust_mode", {})
        return TrustModeSettings(**data) if isinstance(data, dict) else TrustModeSettings()

    def set_trust_mode(self, payload: TrustModeSettings) -> TrustModeSettings:
        self.set_setting("trust_mode", payload.model_dump())
        return payload

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> LlmProfileResponse:
        return LlmProfileResponse(
            id=int(row["id"]),
            name=str(row["name"]),
            base_url=str(row["base_url"]),
            model=str(row["model"]),
            api_key_masked=safe_mask_encrypted_key(str(row["api_key_encrypted"])),
            is_default=bool(row["is_default"]),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _row_to_style(row: sqlite3.Row) -> StyleTemplateResponse:
        return StyleTemplateResponse(
            id=int(row["id"]),
            name=str(row["name"]),
            is_builtin=bool(row["is_builtin"]),
            pov=str(row["pov"] or ""),
            tense_feel=str(row["tense_feel"] or ""),
            tone=str(row["tone"] or ""),
            sentence_pref=str(row["sentence_pref"] or ""),
            dialogue_ratio=str(row["dialogue_ratio"] or ""),
            desc_focus=str(row["desc_focus"] or ""),
            pacing=str(row["pacing"] or ""),
            example_paras=json.loads(row["example_paras"] or "[]"),
            forbidden_exprs=json.loads(row["forbidden_exprs"] or "[]"),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
