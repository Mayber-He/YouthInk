"""Deterministic + model-based prose style review for AI-like writing patterns."""

from __future__ import annotations

from app.builtin.style_presets import DEFAULT_FORBIDDEN_EXPRESSIONS
from app.core.exceptions import AppError
from app.db.repositories.settings_repo import SettingsRepository
from app.schemas.writing import AiSmellHit, AiSmellScanResponse, LlmAiSmellOutput
from app.services.llm.client import complete_chat
from app.services.llm.json_parser import parse_and_validate_json

_LOCAL_SMELL_RULES: list[tuple[str, str, str, str]] = [
    ("不由得", "AI套话惯用词", "高频无意识副词，削弱动作主动性", "直接写出具体动作或停顿，删去“不由得”"),
    ("嘴角勾起一抹弧度", "网文陈旧套话", "脸谱化表情描写，AI感极强", "改为自然的“笑了笑”或具体神态细节"),
    ("仿佛整个世界都安静了下来", "过度煽情修辞", "悬浮夸张的氛围套话", "改为具体的周围环境声响变化"),
    ("心中五味杂陈", "直接总结情绪", "用抽象成语代替真实心理反应", "通过一个停顿或动作留白展现复杂心情"),
    ("眼中闪过一丝", "网文陈旧套话", "机械化的眼神特写", "直接写人物看向何处或说了什么"),
    ("命运的齿轮开始转动", "总结式旁白套话", "跳出视角的说教式预告", "删去上帝视角旁白，留在当下场景"),
    ("嘴角微微上扬", "高频模板神态", "重复率极高的AI微表情套话", "用对话语气或顺手动作体现心情"),
    ("深邃的眼眸", "悬浮外貌修饰", "脱离日常语感的译制片腔调", "改为平实的视线描写"),
    ("不知为何", "伪悬念套话", "无意义的模糊归因", "直接描写人物当下的反应"),
    ("莫名地", "AI高频副词", "空洞的情绪修饰词", "删去“莫名地”，直接写动作"),
    ("拇指悬在屏幕", "高频AI微动作癖", "在多章反复出现的机械玩手机动作", "删去悬停动作，直接写发出或删掉消息"),
    ("屏幕朝下扣在桌面", "高频AI微动作癖", "套路化的收尾道具动作", "换用贴合情境的自然动作或直接切入对话"),
]


def _scan_local_patterns(text: str) -> list[AiSmellHit]:
    hits: list[AiSmellHit] = []
    seen_spans: set[tuple[int, int]] = set()
    rules = list(_LOCAL_SMELL_RULES)
    existing_phrases = {r[0] for r in rules}
    for expr in DEFAULT_FORBIDDEN_EXPRESSIONS:
        if expr not in existing_phrases:
            rules.append((expr, "禁用套话表达", "命中风格模板禁用词表", "删去或换用平实直白的日常表达"))

    for phrase, category, reason, suggestion in rules:
        start = text.find(phrase)
        while start != -1:
            end = start + len(phrase)
            if (start, end) not in seen_spans:
                seen_spans.add((start, end))
                start_offset = len(text[:start].encode("utf-16-le")) // 2
                end_offset = len(text[:end].encode("utf-16-le")) // 2
                hits.append(
                    AiSmellHit(
                        matched_text=phrase,
                        category=category,
                        reason=reason,
                        suggestion=suggestion,
                        suggested_rewrite="",
                        start_index=start_offset,
                        end_index=end_offset,
                    )
                )
            start = text.find(phrase, start + 1)
    hits.sort(key=lambda h: h.start_index)
    return hits


async def scan_ai_smell(
    text: str,
    novel_uid: str,
    settings_repo: SettingsRepository,
    chapter_id: int | None = None,
) -> AiSmellScanResponse:
    """Combine deterministic cliché scanning with model-based prose style review."""
    if not text.strip():
        return AiSmellScanResponse(total_hits=0, hits=[])

    local_hits = _scan_local_patterns(text)

    try:
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
    except Exception:
        if local_hits:
            return AiSmellScanResponse(total_hits=len(local_hits), hits=local_hits)
        raise

    hits: list[AiSmellHit] = list(local_hits)
    seen_spans: set[tuple[int, int]] = {
        (
            len(text.encode("utf-16-le")[: h.start_index * 2].decode("utf-16-le", errors="ignore")),
            len(text.encode("utf-16-le")[: h.end_index * 2].decode("utf-16-le", errors="ignore")),
        )
        for h in local_hits
    }
    llm_located = 0
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
        llm_located += 1
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

    if parsed.hits and llm_located == 0 and not local_hits:
        raise AppError(
            "AI_SMELL_QUOTES_UNLOCATABLE",
            "模型返回的问题片段无法在正文中精确定位，请重试。",
            status_code=502,
        )

    hits.sort(key=lambda hit: hit.start_index)
    return AiSmellScanResponse(total_hits=len(hits), hits=hits)
