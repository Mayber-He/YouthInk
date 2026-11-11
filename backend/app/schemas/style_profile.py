"""Structured 6-dimension Style Profile schemas & targeted style review/rewrite models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LanguageMetrics(BaseModel):
    """Quantitative metrics extracted from a reference novel excerpt (no raw sentences copied)."""

    char_count: int = 0
    paragraph_count: int = 0
    sentence_count: int = 0
    avg_paragraph_chars: float = 0.0
    single_line_para_ratio: float = 0.0
    avg_sentence_chars: float = 0.0
    short_sentence_pct: float = 0.0
    medium_sentence_pct: float = 0.0
    long_sentence_pct: float = 0.0
    dialogue_ratio_pct: float = 0.0
    colloquial_per_kchars: float = 0.0
    rhetoric_per_kchars: float = 0.0


class LanguageExpressionProfile(BaseModel):
    """1. 语言表达：口语化程度、长短句比例、修辞密度。"""

    colloquial_level: str = Field(
        default="自然口语化（三分书面七分白话，贴近当代青年日常语感）",
        max_length=600,
    )
    sentence_length_ratio: str = Field(
        default="短句（≤12字）约45%、中句（13-28字）约40%、长句（>28字）约15%，对话与动作交锋处多用短促断句",
        max_length=600,
    )
    rhetoric_density: str = Field(
        default="低密度克制修辞（每千字不超1处比喻，禁用刻意雕琢的伪文艺通感）",
        max_length=600,
    )
    paragraph_rhythm: str = Field(
        default="单句成段与2-4句短段交替，避免连续超过5行的大段说明块",
        max_length=600,
    )
    metrics: LanguageMetrics = Field(default_factory=LanguageMetrics)


class NarrativeModeProfile(BaseModel):
    """2. 叙事方式：视角、信息释放、场景与概述的比例。"""

    pov_mode: str = Field(
        default="第三人称贴身限知（紧贴当前POV人物即时感知，绝不越界偷看他人内心）",
        max_length=600,
    )
    info_release: str = Field(
        default="渐进式错位释放（先给反常细节与半截话，延迟解释背景原因，不搞设定说明书）",
        max_length=600,
    )
    scene_to_summary_ratio: str = Field(
        default="实时场景80% : 简明过渡概述20%（日常跑腿/排队/填表一笔带过，笔墨集中在人物交锋瞬间）",
        max_length=600,
    )
    transition_style: str = Field(
        default="以动作结果或时间切口直接跳切，不写步步移动的机械过场",
        max_length=600,
    )


class DialogueCraftProfile(BaseModel):
    """3. 人物对话：对白节奏、潜台词、角色之间的互动。"""

    dialogue_rhythm: str = Field(
        default="快慢错落、有来有回（禁止一方长篇提问而另一方只回“嗯/行/好”单字敷衍）",
        max_length=600,
    )
    subtext_technique: str = Field(
        default="话只说七分，靠答非所问、故意岔开话题、停顿改口或反问传递潜台词",
        max_length=600,
    )
    interaction_texture: str = Field(
        default="对话夹杂生活化顺手动作（递东西、看路、顺口接梗），避免站桩问答与审讯感",
        max_length=600,
    )


class EmotionExpressionProfile(BaseModel):
    """4. 情绪表达：动作、细节、心理活动与留白。"""

    action_and_detail: str = Field(
        default="选取1个反常的具体反应代替情绪标签，严禁高频复读“拇指悬在屏幕/手机扣在桌面/眉心浅褶”等套路微动作",
        max_length=600,
    )
    inner_monologue_ratio: str = Field(
        default="心理活动精炼且必须产生新判断或新误会，禁止原地复盘已知事实",
        max_length=600,
    )
    whitespace_and_restraint: str = Field(
        default="关键情绪节点留白（点到动作或半句对白即止，把潜台词留给读者体会，不写总结陈词）",
        max_length=600,
    )


class ChapterPacingProfile(BaseModel):
    """5. 章节节奏：铺垫、冲突、转折、收尾。"""

    opening_setup: str = Field(
        default="开门见山切入具体情境或对话现场，3句内出现人物当下处境或小阻碍",
        max_length=600,
    )
    conflict_progression: str = Field(
        default="通过信息差、身份错位或小意外层层推进拉扯，不靠生硬误会凑字数",
        max_length=600,
    )
    turning_point: str = Field(
        default="中后段设置一个细节破绽、意外照面或态度松动，改变双方心理距离",
        max_length=600,
    )
    closing_hook: str = Field(
        default="落在未完的互动余韵、新悬念或干脆的干脆行动上，不写抒情升华或口号式决心",
        max_length=600,
    )


class GenreTraitsProfile(BaseModel):
    """6. 题材特征：校园、都市、恋爱、玄幻等不同写法。"""

    genre_name: str = Field(default="校园青春恋爱", max_length=120)
    core_appeal: str = Field(
        default="少年感、线上线下掉马张力、拉扯推拉感与鲜活的生活烟火气",
        max_length=600,
    )
    characteristic_techniques: str = Field(
        default="注重同龄人自然的聊天损人/接梗节奏，真实还原校园空间动线但不过度堆砌地名",
        max_length=600,
    )
    genre_taboos: list[str] = Field(
        default_factory=lambda: [
            "把青春日常写成办事流程说明书（排队、填表、领物资逐项报账）",
            "男主全程单字冷漠复读机（只会回“嗯”“行”“好”）",
            "角色用公文体或心理咨询师口吻分析自己的感情",
        ]
    )


class StyleProfile(BaseModel):
    """Complete structured, editable 6-dimension Style Profile."""

    version: str = Field(default="1.0", max_length=16)
    source_type: Literal["builtin_preset", "reference_excerpt", "user_custom"] = "builtin_preset"
    language: LanguageExpressionProfile = Field(default_factory=LanguageExpressionProfile)
    narrative: NarrativeModeProfile = Field(default_factory=NarrativeModeProfile)
    dialogue: DialogueCraftProfile = Field(default_factory=DialogueCraftProfile)
    emotion: EmotionExpressionProfile = Field(default_factory=EmotionExpressionProfile)
    pacing: ChapterPacingProfile = Field(default_factory=ChapterPacingProfile)
    genre_traits: GenreTraitsProfile = Field(default_factory=GenreTraitsProfile)
    anti_ai_rules: list[str] = Field(
        default_factory=lambda: [
            "禁止连续使用“拇指悬在屏幕上/指尖悬了半秒/把手机屏幕朝下扣在桌面/眉心挤出浅褶”等高频AI习惯动作",
            "禁止把普通转场、排队、收拾拆解成无信息增量的微动作流水账",
            "禁止在段落结尾用总结式心理独白把潜台词直接点破",
        ]
    )


class StyleProfileAnalyzeRequest(BaseModel):
    """Request to analyze a user-provided reference novel excerpt into a StyleProfile."""

    reference_text: str = Field(..., min_length=60, max_length=30000)
    genre: str = Field(default="校园", max_length=64)
    template_name: str = Field(default="", max_length=64)
    save_as_template: bool = False
    target_template_id: int | None = None
    use_llm: bool = True


class StyleProfileAnalyzeResponse(BaseModel):
    """Structured Style Profile extracted from reference excerpt + optional saved template ID."""

    style_profile: StyleProfile
    derived_template_fields: dict[str, object]
    saved_template_id: int | None = None
    analysis_notes: list[str] = Field(default_factory=list)


class StyleSpanIssue(BaseModel):
    """A localized span-level AI style issue identified during post-generation style review."""

    issue_type: str
    dimension: str
    severity: Literal["high", "medium", "low"] = "medium"
    paragraph_index: int
    evidence_quote: str
    reason: str
    rewrite_directive: str
    suggested_rewrite: str = ""


class StyleReviewRequest(BaseModel):
    """Request to run targeted post-generation style review on chapter or scene prose."""

    text: str | None = None
    scene_id: int | None = None
    use_llm: bool = False


class StyleReviewResponse(BaseModel):
    """Report from post-generation targeted style review."""

    chapter_id: int
    total_issues: int
    dimension_scores: dict[str, int]
    pacing_mode: str = ""
    issues: list[StyleSpanIssue]
    metrics: LanguageMetrics
    summary: str


class StyleSpanRewriteRequest(BaseModel):
    """Request to surgically rewrite only unqualified spans in a chapter/scene."""

    text: str | None = None
    issue_indices: list[int] | None = None
    max_spans: int = Field(default=5, ge=1, le=12)
    use_llm: bool = False
    save_to_chapter: bool = False


class StyleSpanRewriteResponse(BaseModel):
    """Result of surgical span-only rewrite (preserving plot, relationships, foreshadowing)."""

    original_text: str
    rewritten_text: str
    replaced_count: int
    skipped_count: int
    replacements: list[dict[str, str]]
    warnings: list[str] = Field(default_factory=list)
