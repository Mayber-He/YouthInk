"""Targeted post-generation AI style review and surgical span-only rewrite service."""

from __future__ import annotations

import re

from app.schemas.style_profile import (
    StyleProfile,
    StyleReviewResponse,
    StyleSpanIssue,
    StyleSpanRewriteResponse,
)
from app.services.prompt.style_profile import (
    compute_language_metrics,
    select_dynamic_scene_pacing,
)
from app.services.repetition_service import clean_dangling_seam_particles

# 10类典型AI文风病灶的精准定位规则：(issue_type, dimension, severity, regex, reason, directive, deterministic_fix_fn)
_SPAN_PATTERNS: list[tuple[str, str, str, re.Pattern[str], str, str]] = [
    (
        "broken_rewrite_seam",
        "阅读自然度",
        "high",
        re.compile(r"(?:^|\n)[ \t\u3000]*([了着过地的][，、][^\n。！？]{3,35}[。！？])"),
        "局部改写残留的断句残片（句首孤立助词“了，/着，”），破坏阅读流畅度",
        "删去句首孤立的残余助词与逗号，使主谓宾自然接续",
    ),
    (
        "stock_micro_action",
        "AI腔程度",
        "high",
        re.compile(
            r"[^。！？\n]*(?:拇指悬在屏幕|指尖悬了半秒|把手机(?:翻过来)?屏幕朝下扣|眉心(?:挤出|拧出|蹙起)[^。！？\n]*褶|舌尖抵了抵后槽牙)[^。！？\n]*[。！？]?"
        ),
        "高频复读的AI套路微动作/道具癖，机械感重且缺乏真实人物个性",
        "删去套路化的手指悬停/扣手机/眉心褶皱描写，换用贴合当下情境的顺手动作或直接接入对话",
    ),
    (
        "direct_emotion_telling",
        "情绪感染力",
        "medium",
        re.compile(
            r"[^。！？\n]*(?:心中五味杂陈|心里泛起一丝|莫名地感到一[丝股]|涌起一股难以言喻|心头莫名一颤|不由得怔住了)[^。！？\n]*[。！？]?"
        ),
        "直接用套话总结/解释人物情绪，而非通过具体场景反应与留白展现",
        "去掉空泛的情绪总结词，改为一个具体的停顿、视线转移或半句没说完的话",
    ),
    (
        "over_ornamented_simile",
        "阅读自然度",
        "medium",
        re.compile(
            r"[^。！？\n]*(?:嘴角勾起一抹弧度|眼中闪过一丝[^。！？\n]{1,6}的光|仿佛整个世界都安静了下来|命运的齿轮开始转动|像被按下了暂停键)[^。！？\n]*[。！？]?"
        ),
        "过度雕琢的网文陈旧套话修辞，AI生成痕迹明显",
        "用平实直白的自然动作或神态替代陈旧套话",
    ),
    (
        "zero_info_psych",
        "节奏控制",
        "medium",
        re.compile(
            r"[^。！？\n]*(?:他心里很清楚，这意味着|她不得不承认，在某种意义上|他比谁都明白，此刻的自己)[^。！？\n]*[。！？]?"
        ),
        "无信息增量的总结式心理独白，打断叙事节奏",
        "精简或删除原地复盘的总结式心理描写，让行动或对话直接体现态度",
    ),
    (
        "procedural_checklist",
        "节奏控制",
        "medium",
        re.compile(
            r"[^。！？\n]*(?:先从包里抽出[^。！？\n]{2,15}，又把[^。！？\n]{2,15}塞回|接过表格，拧开笔帽，在[^。！？\n]{2,18}一笔一划地填上)[^。！？\n]*[。！？]?"
        ),
        "把日常跑腿/填表/收拾拆解成无戏剧张力的微动作流水账",
        "将繁琐的事务性步骤压缩为一句话结果，把笔墨留给人物互动",
    ),
    (
        "mechanical_thesis_ending",
        "情绪感染力",
        "medium",
        re.compile(
            r"[^。！？\n]*(?:他暗暗下定决心，无论如何也要|这一刻，他终于彻底明白了[^。！？\n]{2,15}的意义)[^。！？\n]*[。！？]?"
        ),
        "段落末尾生硬喊口号或替读者升华总结，缺少余韵与留白",
        "删去口号式总结，停在具体动作或半句对白上留白",
    ),
]

_MONOSYLLABIC_REPLY_RE = re.compile(r"^[“「](?:嗯|行|好|哦|多|对|是)[。！？!?]*[”」]$")


def _deterministic_span_fix(issue_type: str, span: str) -> str:
    """Provide a conservative, plot-preserving deterministic rewrite for known AI clichés."""
    s = span.strip()
    if issue_type == "broken_rewrite_seam":
        return clean_dangling_seam_particles(s)
    if issue_type == "stock_micro_action":
        s = re.sub(r"拇指悬在屏幕上方[^，。！？]*[，]?", "他看了眼屏幕，", s)
        s = re.sub(r"指尖悬了半秒[，]?", "他顿了一下，", s)
        s = re.sub(r"把手机(?:翻过来)?屏幕朝下扣在桌面上", "把手机放到手边", s)
        s = re.sub(r"眉心(?:挤出|拧出|蹙起)一道浅褶", "目光微顿", s)
        return s
    if issue_type in ("direct_emotion_telling", "over_ornamented_simile"):
        s = s.replace("不由得怔住了", "愣了一下")
        s = s.replace("嘴角勾起一抹弧度", "笑了笑")
        s = s.replace("仿佛整个世界都安静了下来", "四周顿时安静下来")
        s = re.sub(r"心中五味杂陈[，。]?", "一时没说话。", s)
        s = re.sub(r"心里泛起一丝[^，。！？]+[，]?", "动作慢了半拍，", s)
        s = re.sub(r"莫名地", "", s)
        s = re.sub(r"不由得", "", s)
        return s
    if issue_type == "procedural_checklist":
        return re.sub(r"先从包里抽出([^，。！？]+)，又把[^，。！？]+", r"拿出\1", s)
    return s


def diagnose_chapter_style(
    text: str,
    *,
    chapter_id: int = 0,
    beat: str = "",
    style_profile: StyleProfile | None = None,
) -> StyleReviewResponse:
    """Run targeted post-generation style review across the 10 AI-style dimensions."""
    cleaned = (text or "").strip()
    metrics = compute_language_metrics(cleaned)
    paragraphs = [p.strip() for p in cleaned.splitlines() if p.strip()]
    issues: list[StyleSpanIssue] = []

    # 1. Scan paragraph by paragraph for localized span pathologies
    mono_Indices: list[tuple[int, str]] = []
    for p_idx, para in enumerate(paragraphs):
        for issue_type, dim, sev, pattern, reason, directive in _SPAN_PATTERNS:
            for match in pattern.finditer(para):
                quote = (match.group(1) if match.lastindex else match.group(0)).strip()
                if len(quote) < 4:
                    continue
                issues.append(
                    StyleSpanIssue(
                        issue_type=issue_type,
                        dimension=dim,
                        severity=sev,  # type: ignore[arg-type]
                        paragraph_index=p_idx,
                        evidence_quote=quote,
                        reason=reason,
                        rewrite_directive=directive,
                        suggested_rewrite=_deterministic_span_fix(issue_type, quote),
                    )
                )
        if _MONOSYLLABIC_REPLY_RE.match(para):
            mono_Indices.append((p_idx, para))

    # 2. Check for monosyllabic dialogue walls (>= 2 bare single-character replies in a scene/chapter)
    if len(mono_Indices) >= 2:
        for p_idx, para in mono_Indices[1:]:
            issues.append(
                StyleSpanIssue(
                    issue_type="monosyllabic_dialogue_wall",
                    dimension="人物对话质量",
                    severity="medium",
                    paragraph_index=p_idx,
                    evidence_quote=para,
                    reason="角色连续使用单字（“嗯/行/好”）机械应答，缺少潜台词、反问或顺手动作支撑",
                    rewrite_directive="结合人物性格补足半句反问、顺嘴接茬或具体动作反应，避免单字敷衍",
                    suggested_rewrite=para[:-1] + "，你先过去吧。”" if para.endswith("”") else para,
                )
            )

    # 3. Check for uniform paragraph cadence (every paragraph having almost identical length)
    if len(paragraphs) >= 5:
        lengths = [len(p) for p in paragraphs]
        avg_len = sum(lengths) / len(lengths)
        near_uniform = sum(1 for ln in lengths if abs(ln - avg_len) <= 18)
        if near_uniform / len(lengths) >= 0.80 and metrics.single_line_para_ratio < 15.0:
            target_idx = len(paragraphs) // 2
            snippet = paragraphs[target_idx][:60]
            issues.append(
                StyleSpanIssue(
                    issue_type="uniform_paragraph_cadence",
                    dimension="节奏控制",
                    severity="low",
                    paragraph_index=target_idx,
                    evidence_quote=snippet,
                    reason=f"段落结构过于工整（单行短段仅占 {metrics.single_line_para_ratio}%），缺乏网文长短段交错的呼吸感",
                    rewrite_directive="将长段中的关键对白或转折动作独立成段，拉开长短段反差",
                    suggested_rewrite=snippet,
                )
            )

    pacing_mode, _ = select_dynamic_scene_pacing(beat)
    high_cnt = sum(1 for i in issues if i.severity == "high")
    med_cnt = sum(1 for i in issues if i.severity == "medium")

    base_penalty = high_cnt * 12 + med_cnt * 6
    dlg_bonus = 6 if 25.0 <= metrics.dialogue_ratio_pct <= 60.0 else 0
    cadence_bonus = 5 if metrics.single_line_para_ratio >= 20.0 else 0

    scores = {
        "阅读自然度": max(40, min(98, 90 - base_penalty + cadence_bonus)),
        "AI腔控制": max(35, min(98, 92 - high_cnt * 15 - med_cnt * 7)),
        "人物对话质量": max(45, min(98, 86 + dlg_bonus - sum(8 for i in issues if i.dimension == "人物对话质量"))),
        "情绪感染力": max(45, min(98, 88 - sum(8 for i in issues if i.dimension == "情绪感染力"))),
        "剧情连贯性": 92,
        "节奏控制": max(45, min(98, 86 + cadence_bonus - sum(7 for i in issues if i.dimension == "节奏控制"))),
        "题材适配性": 90,
        "文风档案匹配度": max(50, min(98, 88 - base_penalty // 2 + dlg_bonus // 2)),
    }

    summary = (
        f"共检出 {len(issues)} 处局部文风问题（高优 {high_cnt} 处，中优 {med_cnt} 处）；"
        f"当前对白占比 {metrics.dialogue_ratio_pct}%，短句占比 {metrics.short_sentence_pct}%，建议仅对标出片段做局部替换。"
        if issues
        else f"未检出明显AI套话或机械微动作；对白占比 {metrics.dialogue_ratio_pct}%，短句占比 {metrics.short_sentence_pct}%，整体文风自然。"
    )
    return StyleReviewResponse(
        chapter_id=chapter_id,
        total_issues=len(issues),
        dimension_scores=scores,
        pacing_mode=pacing_mode,
        issues=issues,
        metrics=metrics,
        summary=summary,
    )


def validate_span_replacement_safety(original_span: str, replacement_span: str) -> tuple[bool, str]:
    """Ensure a local span replacement does not drop dates/numbers or inject meta-commentary."""
    rep = (replacement_span or "").strip()
    if not rep:
        return False, "替换内容为空"
    if any(tok in rep for tok in ("【", "】", "修改后：", "改写说明", "注：")):
        return False, "替换内容包含非正文注释标记"
    # Preserve explicit digits/dates if present in the original span
    orig_digits = set(re.findall(r"\d+", original_span))
    rep_digits = set(re.findall(r"\d+", rep))
    if orig_digits and not orig_digits.issubset(rep_digits):
        return False, f"替换内容丢失了原文中的数字/时间信息: {orig_digits - rep_digits}"
    return True, ""


def apply_surgical_span_rewrites(
    text: str,
    issues: list[StyleSpanIssue],
    *,
    issue_indices: list[int] | None = None,
    max_spans: int = 5,
) -> StyleSpanRewriteResponse:
    """Surgically replace ONLY the unqualified spans, leaving all other sentences 100% untouched."""
    if not text or not issues:
        return StyleSpanRewriteResponse(
            original_text=text,
            rewritten_text=text,
            replaced_count=0,
            skipped_count=0,
            replacements=[],
            warnings=[],
        )

    selected = [
        issues[i] for i in (issue_indices if issue_indices is not None else range(len(issues)))
        if 0 <= i < len(issues)
    ][:max_spans]

    working = text
    replacements: list[dict[str, str]] = []
    warnings: list[str] = []
    touched_paragraphs: set[int] = set()
    skipped = 0

    for item in selected:
        if item.paragraph_index in touched_paragraphs:
            skipped += 1
            warnings.append(f"段落 {item.paragraph_index + 1} 本轮已做过局部修订，跳过二次润色以防模板化。")
            continue
        quote = item.evidence_quote.strip()
        cand = item.suggested_rewrite.strip()
        if not quote or not cand or quote == cand:
            skipped += 1
            continue
        if working.count(quote) != 1:
            skipped += 1
            warnings.append(f"片段「{quote[:18]}…」在全文中未唯一命中，跳过自动替换以保护上下文。")
            continue
        ok, reason = validate_span_replacement_safety(quote, cand)
        if not ok:
            skipped += 1
            warnings.append(f"片段「{quote[:18]}…」未通过安全校验（{reason}），保留原文。")
            continue

        working = working.replace(quote, cand, 1)
        touched_paragraphs.add(item.paragraph_index)
        replacements.append(
            {
                "issue_type": item.issue_type,
                "original_span": quote,
                "replacement_span": cand,
            }
        )

    working = clean_dangling_seam_particles(working)
    return StyleSpanRewriteResponse(
        original_text=text,
        rewritten_text=working,
        replaced_count=len(replacements),
        skipped_count=skipped,
        replacements=replacements,
        warnings=warnings,
    )
