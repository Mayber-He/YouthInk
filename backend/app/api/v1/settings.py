"""Global settings, LLM profiles, prompt templates, style presets, and embedding routes."""

from __future__ import annotations

from typing import Literal
from fastapi import APIRouter, Depends, status

from app.api.deps import get_settings_repo
from app.core.exceptions import AppError
from app.db.repositories.settings_repo import SettingsRepository
from app.schemas.settings import (
    EmbeddingModelStatus,
    LlmConnectionTestRequest,
    LlmConnectionTestResponse,
    LlmProfileCreate,
    LlmProfileResponse,
    LlmProfileUpdate,
    PromptTemplateItem,
    PromptTemplateUpdate,
    StyleTemplateCreate,
    StyleTemplateResponse,
    StyleTemplateUpdate,
    TaskAssignmentResponse,
    TaskAssignmentUpdate,
    TrustModeSettings,
)
from app.schemas.style_profile import (
    StyleProfileAnalyzeRequest,
    StyleProfileAnalyzeResponse,
)
from app.services.embedding.encoder import EMBEDDING_MODEL_ID
from app.services.embedding.manager import (
    check_embedding_model_status,
    trigger_embedding_download,
)
from app.services.llm.client import complete_chat
from app.services.prompt.style_profile import (
    analyze_reference_excerpt,
    analyze_reference_excerpt_with_llm,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/llm-profiles", response_model=list[LlmProfileResponse])
def list_profiles(
    repo: SettingsRepository = Depends(get_settings_repo),
) -> list[LlmProfileResponse]:
    return repo.list_llm_profiles()


@router.post(
    "/llm-profiles",
    response_model=LlmProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    payload: LlmProfileCreate,
    repo: SettingsRepository = Depends(get_settings_repo),
) -> LlmProfileResponse:
    return repo.create_llm_profile(payload)


@router.put("/llm-profiles/{profile_id}", response_model=LlmProfileResponse)
def update_profile(
    profile_id: int,
    payload: LlmProfileUpdate,
    repo: SettingsRepository = Depends(get_settings_repo),
) -> LlmProfileResponse:
    return repo.update_llm_profile(profile_id, payload)


@router.delete(
    "/llm-profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,  # 显式禁用：避免新版 FastAPI 从 `-> None` 注解推断 response_model 导致 204 断言失败
)
def delete_profile(
    profile_id: int,
    repo: SettingsRepository = Depends(get_settings_repo),
) -> None:
    repo.delete_llm_profile(profile_id)


@router.post("/llm-profiles/test", response_model=LlmConnectionTestResponse)
async def test_llm_connection(
    payload: LlmConnectionTestRequest,
    repo: SettingsRepository = Depends(get_settings_repo),
) -> LlmConnectionTestResponse:
    if payload.profile_id is not None:
        _, base_url, model, api_key = repo.get_llm_credentials(payload.profile_id)
    elif payload.base_url and payload.model and payload.api_key:
        base_url = payload.base_url
        model = payload.model
        api_key = payload.api_key
    else:
        raise AppError(
            "MISSING_TEST_PARAMS",
            "请提供已保存的 profile_id 或完整的 base_url、model、api_key",
            status_code=400,
        )

    res = await complete_chat(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt="你是 YouthInk 青春小说工作台连接测试助手，请简短回复。",
        user_prompt=payload.prompt,
        temperature=0.5,
        timeout_sec=30.0,
    )
    return LlmConnectionTestResponse(
        ok=True,
        model=res.model,
        reply=res.content,
        elapsed_ms=res.elapsed_ms,
        input_tokens=res.input_tokens,
        output_tokens=res.output_tokens,
    )


@router.get("/task-assignments", response_model=TaskAssignmentResponse)
def get_task_assignments(
    repo: SettingsRepository = Depends(get_settings_repo),
) -> TaskAssignmentResponse:
    return repo.get_task_assignments()


@router.put("/task-assignments", response_model=TaskAssignmentResponse)
def update_task_assignments(
    payload: TaskAssignmentUpdate,
    repo: SettingsRepository = Depends(get_settings_repo),
) -> TaskAssignmentResponse:
    return repo.update_task_assignments(payload)


@router.get("/prompt-templates", response_model=list[PromptTemplateItem])
def list_prompts(
    repo: SettingsRepository = Depends(get_settings_repo),
) -> list[PromptTemplateItem]:
    return repo.list_prompt_templates()


@router.put("/prompt-templates/{task_type}", response_model=PromptTemplateItem)
def update_prompt(
    task_type: str,
    payload: PromptTemplateUpdate,
    repo: SettingsRepository = Depends(get_settings_repo),
) -> PromptTemplateItem:
    return repo.upsert_prompt_template(task_type, payload.content, payload.version)


@router.delete("/prompt-templates/{task_type}", response_model=PromptTemplateItem)
def reset_prompt(
    task_type: str,
    repo: SettingsRepository = Depends(get_settings_repo),
) -> PromptTemplateItem:
    return repo.reset_prompt_template(task_type)


@router.get("/style-templates", response_model=list[StyleTemplateResponse])
def list_styles(
    repo: SettingsRepository = Depends(get_settings_repo),
) -> list[StyleTemplateResponse]:
    return repo.list_style_templates()


@router.post(
    "/style-templates",
    response_model=StyleTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_style(
    payload: StyleTemplateCreate,
    repo: SettingsRepository = Depends(get_settings_repo),
) -> StyleTemplateResponse:
    return repo.create_style_template(payload)


@router.post("/style-templates/analyze", response_model=StyleProfileAnalyzeResponse)
async def analyze_style_excerpt(
    payload: StyleProfileAnalyzeRequest,
    repo: SettingsRepository = Depends(get_settings_repo),
) -> StyleProfileAnalyzeResponse:
    if payload.use_llm:
        base_url = api_key = model = None
        try:
            _, base_url, model, api_key = repo.get_credentials_for_task("extract")
        except AppError:
            pass
        profile, derived, notes = await analyze_reference_excerpt_with_llm(
            reference_text=payload.reference_text,
            genre=payload.genre,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
    else:
        profile, derived, notes = analyze_reference_excerpt(
            reference_text=payload.reference_text,
            genre=payload.genre,
        )
        notes.append("本次采用纯本地量化统计 + 规则映射（未调用大模型）。")
    saved_id: int | None = None
    if payload.target_template_id is not None:
        updated = repo.update_style_template(
            payload.target_template_id,
            StyleTemplateUpdate(
                pov=str(derived["pov"]),
                tense_feel=str(derived["tense_feel"]),
                tone=str(derived["tone"]),
                sentence_pref=str(derived["sentence_pref"]),
                dialogue_ratio=str(derived["dialogue_ratio"]),
                desc_focus=str(derived["desc_focus"]),
                pacing=str(derived["pacing"]),
                style_profile=profile,
            ),
        )
        saved_id = updated.id
    elif payload.save_as_template:
        tpl_name = (payload.template_name or f"{payload.genre}参考文风档案").strip()
        created = repo.create_style_template(
            StyleTemplateCreate(
                name=tpl_name,
                pov=str(derived["pov"]),
                tense_feel=str(derived["tense_feel"]),
                tone=str(derived["tone"]),
                sentence_pref=str(derived["sentence_pref"]),
                dialogue_ratio=str(derived["dialogue_ratio"]),
                desc_focus=str(derived["desc_focus"]),
                pacing=str(derived["pacing"]),
                style_profile=profile,
            )
        )
        saved_id = created.id
    return StyleProfileAnalyzeResponse(
        style_profile=profile,
        derived_template_fields=derived,
        saved_template_id=saved_id,
        analysis_notes=notes,
    )


@router.put("/style-templates/{template_id:int}", response_model=StyleTemplateResponse)
def update_style(
    template_id: int,
    payload: StyleTemplateUpdate,
    repo: SettingsRepository = Depends(get_settings_repo),
) -> StyleTemplateResponse:
    return repo.update_style_template(template_id, payload)


@router.get("/trust-mode", response_model=TrustModeSettings)
def get_trust_mode(
    repo: SettingsRepository = Depends(get_settings_repo),
) -> TrustModeSettings:
    return repo.get_trust_mode()


@router.put("/trust-mode", response_model=TrustModeSettings)
def update_trust_mode(
    payload: TrustModeSettings,
    repo: SettingsRepository = Depends(get_settings_repo),
) -> TrustModeSettings:
    return repo.set_trust_mode(payload)


@router.get("/embedding", response_model=EmbeddingModelStatus)
def get_embedding_status(
    repo: SettingsRepository = Depends(get_settings_repo),
) -> EmbeddingModelStatus:
    emb_cfg = repo.get_setting("embedding", {}) or {}
    src = emb_cfg.get("download_source", "modelscope")
    return check_embedding_model_status(src)


@router.post("/embedding/download", response_model=EmbeddingModelStatus)
async def download_embedding_model(
    source: Literal["modelscope", "hf_mirror", "huggingface"] = "modelscope",
    repo: SettingsRepository = Depends(get_settings_repo),
) -> EmbeddingModelStatus:
    repo.set_setting("embedding", {"model_id": EMBEDDING_MODEL_ID, "download_source": source})
    return await trigger_embedding_download(source)
