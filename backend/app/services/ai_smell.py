"""Model-based prose style review for AI-like writing patterns."""

from __future__ import annotations

from app.core.exceptions import AppError
from app.db.repositories.settings_repo import SettingsRepository
from app.schemas.writing import AiSmellHit, AiSmellScanResponse, LlmAiSmellOutput
from app.services.llm.client import complete_chat
from app.services.llm.json_parser import parse_and_validate_json


async def scan_ai_smell(
    text: str,
    novel_uid: str,
    settings_repo: SettingsRepository,
    chapter_id: int | None = None,
) -> AiSmellScanResponse:
    """Ask the configured analysis model to flag prose issues with locatable quotes."""
    if not text.strip():
        return AiSmellScanResponse(total_hits=0, hits=[])

    _profile_id, base_url, model, api_key = settings_repo.get_credentials_for_task("extract")
    result = await complete_chat(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=(
            "你是中文小说编辑，评估文本是否存在明显的模板化、机械化或生硬表达。"
            "你不能鉴定文本是否由AI生成，只能指出可观察到的写作问题。"
            "正常的环境描写、短句、重复和修辞不应仅因形式本身被判为问题。"
            "只输出符合要求的JSON。"
        ),
        user_prompt=(
            "请通读下面的小说正文，从整体和局部检查：套用模板、重复相似句式或动作、流水账式罗列、"
            "抽象情绪标签、过度解释、机械开头/收尾、对话或转场不自然等明显问题。"
            "只返回值得作者修改的明确片段，最多12条；不要为了凑数挑普通描写。"
            "每条quote必须是正文中连续、逐字一致的原文，建议选择能准确定位的短句或短语；"
            "reason说明具体问题，suggestion给出简短修改方向，suggested_rewrite给出修改后的完整片段，"
            "必须能直接替换quote且保留上下文语气；如果只是局部句子有问题，只改必要部分。"
            "若没有明显问题，hits返回空数组。\n"
            "输出格式：{\"hits\":[{\"quote\":\"正文原文\",\"category\":\"问题类型\","
            "\"reason\":\"具体原因\",\"suggestion\":\"修改方向\","
            "\"suggested_rewrite\":\"可直接替换原文的修改片段\"}]}\n\n"
            f"正文：\n{text}"
        ),
        temperature=0.2,
        timeout_sec=90.0,
        novel_uid=novel_uid,
        task_type="ai_smell_scan",
        chapter_id=chapter_id,
    )
    parsed = await parse_and_validate_json(result.content, LlmAiSmellOutput)

    hits: list[AiSmellHit] = []
    seen_spans: set[tuple[int, int]] = set()
    for finding in parsed.hits[:12]:
        quote = finding.quote
        if not quote:
            continue
        start = text.find(quote)
        while start != -1 and (start, start + len(quote)) in seen_spans:
            start = text.find(quote, start + 1)
        if start == -1:
            continue
        end = start + len(quote)
        seen_spans.add((start, end))
        start_offset = len(text[:start].encode("utf-16-le")) // 2
        end_offset = len(text[:end].encode("utf-16-le")) // 2
        hits.append(
            AiSmellHit(
                matched_text=quote,
                category=finding.category,
                reason=finding.reason,
                suggestion=finding.suggestion,
                suggested_rewrite=finding.suggested_rewrite,
                start_index=start_offset,
                end_index=end_offset,
            )
        )

    if parsed.hits and not hits:
        raise AppError(
            "AI_SMELL_QUOTES_UNLOCATABLE",
            "模型返回的问题片段无法在正文中精确定位，请重试。",
            status_code=502,
        )

    hits.sort(key=lambda hit: hit.start_index)
    return AiSmellScanResponse(total_hits=len(hits), hits=hits)
