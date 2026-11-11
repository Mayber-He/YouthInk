"""Style Profile analyzer, anti-copy sanitizer, prompt renderer, and dynamic scene pacing selector."""

from __future__ import annotations

import json
import re

from app.schemas.style_profile import (
    ChapterPacingProfile,
    DialogueCraftProfile,
    EmotionExpressionProfile,
    GenreTraitsProfile,
    LanguageExpressionProfile,
    LanguageMetrics,
    NarrativeModeProfile,
    StyleProfile,
)

_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?…]+")
_DIALOGUE_SPAN_RE = re.compile(r"“[^”\n]{1,300}”|「[^」\n]{1,300}」")
_COLLOQUIAL_RE = re.compile(r"[吧呢啊呀呗嘛喽哈哦哎哟嘿]|是不是|没法|干嘛|咋|挺|算了|行吧|得了吧")
_RHETORIC_RE = re.compile(r"仿佛|宛如|好似|像是一|如同|恰似|恍若|某种|一抹|一丝")
_FIRST_PERSON_RE = re.compile(r"(?<![“「])(?:我|我们)(?![”」])")
_SUMMARY_TIME_RE = re.compile(r"接下来的几天|那段时间|不知不觉|一转眼|几天后|整个暑假|这几天里")
_INNER_PSYCH_RE = re.compile(r"心想|意识到|暗自|心里清楚|不得不承认|某种意义上|他明白|她明白")
_ACTION_CUE_RE = re.compile(r"递|接过|抬眼|转身|停住|推开|拎起|放进|合上|笑了一下|顿了顿")

_GENRE_TRAITS_MAP: dict[str, dict[str, object]] = {
    "校园": {
        "genre_name": "青春校园",
        "core_appeal": "少年感、熟人/半熟人拉扯、同龄人鲜活对话与微酸微甜的暗涌",
        "characteristic_techniques": "用顺手的小动作和接梗拆台体现亲疏变化，少写说教感独白，多用日常场景反差",
        "genre_taboos": [
            "禁止把报到、排队、领教材写成事无巨细的办事流程说明书",
            "禁止男主沦为只会回“嗯/行/好”的单字复读机",
            "禁止用成年人公文腔或心理学术语剖析青春期好感",
        ],
    },
    "都市": {
        "genre_name": "现代都市",
        "core_appeal": "成年人克制下的推拉感、生活烟火气与职场/日常身份反差",
        "characteristic_techniques": "对白讲究分寸与留白，细节落在生活器物与都市空间冷暖对比，点到即止",
        "genre_taboos": [
            "禁止悬浮的霸总套话或脱离生活常识的煽情",
            "禁止无意义的通勤/点餐动作流水账",
        ],
    },
    "恋爱": {
        "genre_name": "言情甜宠/暗恋拉扯",
        "core_appeal": "眼神与话语的试探交锋、掉马前后的信息差张力、细腻的心理距离变化",
        "characteristic_techniques": "通过“嘴硬心软”“故意岔开话题”“记住对方随口提过的小事”展现心动，而非直接写“他心动了”",
        "genre_taboos": [
            "禁止直接给情绪贴标签（如“心中泛起涟漪”“莫名感到一丝温柔”）",
            "禁止双方像面试官一样机械一问一答",
        ],
    },
    "玄幻": {
        "genre_name": "东方玄幻/仙侠",
        "core_appeal": "境界压迫感、杀伐果断的爽感节奏、奇观场景的视觉冲击",
        "characteristic_techniques": "战斗与对峙多用短促有力的动词短句，世界观信息随冲突自然带出，不写大段设定百科",
        "genre_taboos": [
            "禁止在交手关键处插入冗长的背景说明",
            "禁止现代网络烂梗破坏古风/玄幻语境",
        ],
    },
}


def compute_language_metrics(text: str) -> LanguageMetrics:
    """Compute quantitative stylistic features from Chinese prose without storing raw text."""
    cleaned = text.strip()
    if not cleaned:
        return LanguageMetrics()
    paragraphs = [p.strip() for p in cleaned.splitlines() if p.strip()]
    char_count = sum(len(p) for p in paragraphs)
    if char_count == 0:
        return LanguageMetrics()

    single_line_cnt = sum(1 for p in paragraphs if len(p) <= 28 or p.count("。") <= 1)
    dlg_chars = sum(len(m.group(0)) for m in _DIALOGUE_SPAN_RE.finditer(cleaned))

    raw_sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(cleaned) if len(s.strip()) >= 2]
    sent_count = max(1, len(raw_sentences))
    short_cnt = sum(1 for s in raw_sentences if len(s) <= 12)
    med_cnt = sum(1 for s in raw_sentences if 13 <= len(s) <= 28)
    long_cnt = sum(1 for s in raw_sentences if len(s) > 28)

    kchars = max(0.1, char_count / 1000.0)
    colloquial_hits = len(_COLLOQUIAL_RE.findall(cleaned))
    rhetoric_hits = len(_RHETORIC_RE.findall(cleaned))

    return LanguageMetrics(
        char_count=char_count,
        paragraph_count=len(paragraphs),
        sentence_count=len(raw_sentences),
        avg_paragraph_chars=round(char_count / max(1, len(paragraphs)), 1),
        single_line_para_ratio=round(single_line_cnt / max(1, len(paragraphs)) * 100.0, 1),
        avg_sentence_chars=round(sum(len(s) for s in raw_sentences) / sent_count, 1),
        short_sentence_pct=round(short_cnt / sent_count * 100.0, 1),
        medium_sentence_pct=round(med_cnt / sent_count * 100.0, 1),
        long_sentence_pct=round(long_cnt / sent_count * 100.0, 1),
        dialogue_ratio_pct=round(min(100.0, dlg_chars / char_count * 100.0), 1),
        colloquial_per_kchars=round(colloquial_hits / kchars, 1),
        rhetoric_per_kchars=round(rhetoric_hits / kchars, 1),
    )


def sanitize_profile_against_source(profile: StyleProfile, source_text: str, min_ngram: int = 7) -> StyleProfile:
    """Guarantee zero verbatim copying of 7+ char phrases from reference text into StyleProfile."""
    compact_src = re.sub(r"\s+", "", source_text)
    if len(compact_src) < min_ngram:
        return profile
    src_ngrams = {compact_src[i : i + min_ngram] for i in range(len(compact_src) - min_ngram + 1)}

    def _clean_str(val: str) -> str:
        out = val
        for ng in src_ngrams:
            if ng in out:
                out = out.replace(ng, "")
        return out.strip() or val[:12]

    raw = profile.model_dump()
    for section_key in ("language", "narrative", "dialogue", "emotion", "pacing", "genre_traits"):
        sec = raw.get(section_key, {})
        if isinstance(sec, dict):
            for k, v in list(sec.items()):
                if isinstance(v, str):
                    sec[k] = _clean_str(v)
                elif isinstance(v, list):
                    sec[k] = [_clean_str(x) if isinstance(x, str) else x for x in v]
    return StyleProfile.model_validate(raw)


def analyze_reference_excerpt(
    reference_text: str,
    genre: str = "校园",
) -> tuple[StyleProfile, dict[str, object], list[str]]:
    """Extract a structured 6-dimension StyleProfile from a user-provided reference novel excerpt."""
    m = compute_language_metrics(reference_text)
    notes: list[str] = []

    if m.colloquial_per_kchars >= 10:
        colloquial_desc = f"高口语化（千字语气/口语词约 {m.colloquial_per_kchars} 处），叙事贴近人物日常说话腔调，鲜活轻快"
    elif m.colloquial_per_kchars >= 4:
        colloquial_desc = f"自然半白话（千字口语词约 {m.colloquial_per_kchars} 处），叙述干净利落，对白鲜活接地气"
    else:
        colloquial_desc = f"克制平实（千字口语词约 {m.colloquial_per_kchars} 处），用词准确凝练，少用语气助词"

    sent_ratio_desc = (
        f"平均句长 {m.avg_sentence_chars} 字；短句(≤12字)占 {m.short_sentence_pct}%、"
        f"中句(13-28字)占 {m.medium_sentence_pct}%、长句(>28字)占 {m.long_sentence_pct}%"
    )
    if m.short_sentence_pct >= 45:
        sent_pref_short = "短句为主，干脆利落，交锋处多用单句断行"
    elif m.long_sentence_pct >= 25:
        sent_pref_short = "长短句交错，铺陈处舒展，转折处收短"
    else:
        sent_pref_short = "中等句长为主，长短错落，呼吸感自然"

    if m.rhetoric_per_kchars <= 1.5:
        rhetoric_desc = f"极简白描（千字修辞仅 {m.rhetoric_per_kchars} 处），靠准确动词与具象细节支撑画面，拒绝堆砌比喻"
    elif m.rhetoric_per_kchars <= 4.0:
        rhetoric_desc = f"适度点染（千字修辞约 {m.rhetoric_per_kchars} 处），仅在关键情绪节点使用贴切比喻"
    else:
        rhetoric_desc = f"意象丰富（千字修辞约 {m.rhetoric_per_kchars} 处），注重感官色彩与氛围烘托，但需防套路化"

    para_rhythm_desc = (
        f"平均段长 {m.avg_paragraph_chars} 字，短段/单行段占比 {m.single_line_para_ratio}%；"
        + ("偏网文高频换行节奏，阅读呼吸感快" if m.single_line_para_ratio >= 45 else "段落饱满度适中，短段与3-4句段交替")
    )

    first_p_hits = len(_FIRST_PERSON_RE.findall(reference_text))
    pov_label = "第一人称" if first_p_hits >= 5 else "第三人称限知"
    pov_desc = (
        f"{pov_label}贴身叙事，严格锚定主视角当下所见所闻，不跳出视角做上帝总结"
    )
    summary_hits = len(_SUMMARY_TIME_RE.findall(reference_text))
    scene_ratio_desc = (
        "实时现场场景约 85% : 简明过渡概述 15%，重现场交锋、轻过场交代"
        if summary_hits <= 1
        else "实时场景约 70% : 叙事概述 30%，场景与时间跳跃衔接紧凑"
    )

    if m.dialogue_ratio_pct >= 42:
        dlg_rhythm = f"高对白驱动（对白占比 {m.dialogue_ratio_pct}%），以密集有来有回的对话推进关系与剧情"
        dlg_ratio_label = f"{int(round(m.dialogue_ratio_pct / 5.0) * 5)}%"
    elif m.dialogue_ratio_pct >= 22:
        dlg_rhythm = f"叙事与对白均衡（对白占比 {m.dialogue_ratio_pct}%），动作反应与台词交替咬合"
        dlg_ratio_label = f"{int(round(m.dialogue_ratio_pct / 5.0) * 5)}%"
    else:
        dlg_rhythm = f"精炼点睛对白（对白占比 {m.dialogue_ratio_pct}%），台词少而重，字字带潜台词"
        dlg_ratio_label = "20%"

    psych_hits = len(_INNER_PSYCH_RE.findall(reference_text))
    action_hits = len(_ACTION_CUE_RE.findall(reference_text))
    if action_hits >= psych_hits * 2:
        emotion_mode = "重外在动作与微反应、轻直白心理剖析（以停顿、视线回避、顺手动作承载情绪）"
    else:
        emotion_mode = "动作反应与简短内心吐槽结合，不在同一情绪上反复原地打转"

    genre_cfg = _GENRE_TRAITS_MAP.get(genre, _GENRE_TRAITS_MAP["校园"])
    for key, cfg in _GENRE_TRAITS_MAP.items():
        if key in genre:
            genre_cfg = cfg
            break

    profile = StyleProfile(
        source_type="reference_excerpt",
        language=LanguageExpressionProfile(
            colloquial_level=colloquial_desc,
            sentence_length_ratio=sent_ratio_desc,
            rhetoric_density=rhetoric_desc,
            paragraph_rhythm=para_rhythm_desc,
            metrics=m,
        ),
        narrative=NarrativeModeProfile(
            pov_mode=pov_desc,
            info_release="先呈现反常举动或对话半截话，再顺带点出原委，不在段首摆设定说明书",
            scene_to_summary_ratio=scene_ratio_desc,
            transition_style="场景转换直接切入下一处动作或对话结果，省略上下楼、走路、排队的机械流水账",
        ),
        dialogue=DialogueCraftProfile(
            dialogue_rhythm=dlg_rhythm,
            subtext_technique="话留三分，多用反问、顺嘴接茬、故意避重就轻体现人物真实态度，避免直白表态",
            interaction_texture="对白间穿插顺手的生活化动作，杜绝一方连珠炮提问、另一方只回“嗯/行/好”",
        ),
        emotion=EmotionExpressionProfile(
            action_and_detail=emotion_mode,
            inner_monologue_ratio="心理活动控制在1-2句内，只写当下的意外判断或嘴硬念头，不写总结陈词",
            whitespace_and_restraint="情绪高点用半句被打断的话或干脆的动作收住，留白给读者品味",
        ),
        pacing=ChapterPacingProfile(
            opening_setup="开场直接进入正在发生的互动或小状况，不写冗长天气与环境铺垫",
            conflict_progression="靠人物性格反差、信息错位或小插曲推高张力，每段都有实质推进",
            turning_point="通过一个不经意漏出的细节或态度变化打破原有平衡",
            closing_hook="收在有余味的台词、干脆的行动或悬而未决的微妙气氛上，严禁升华主题",
        ),
        genre_traits=GenreTraitsProfile(
            genre_name=str(genre_cfg["genre_name"]),
            core_appeal=str(genre_cfg["core_appeal"]),
            characteristic_techniques=str(genre_cfg["characteristic_techniques"]),
            genre_taboos=list(genre_cfg["genre_taboos"]),  # type: ignore[arg-type]
        ),
    )
    profile = sanitize_profile_against_source(profile, reference_text)

    derived_fields = {
        "pov": pov_label,
        "tense_feel": "贴身当下感",
        "tone": str(genre_cfg["genre_name"]),
        "sentence_pref": sent_pref_short,
        "dialogue_ratio": dlg_ratio_label,
        "desc_focus": emotion_mode,
        "pacing": para_rhythm_desc,
    }
    notes.append(f"已从 {m.char_count} 字样本完成本地量化统计（对白占比 {m.dialogue_ratio_pct}%、短句占比 {m.short_sentence_pct}%、单行短段 {m.single_line_para_ratio}%）。")
    return profile, derived_fields, notes


_LLM_STYLE_EXTRACT_SYSTEM = """你是一名资深中文网络小说主编与文学文本分析专家。
你的任务是阅读用户提供的参考小说片段，结合给定的量化统计指标，提取高层次的【六维文风档案（Style Profile）】JSON。

【绝对红线】
1. 只提取高层次的写作技法、句式呼吸感、叙事调度、对白潜台词手法与情绪留白方式。
2. 严禁在任何字段中出现参考样本中的具体人名、地名、专有名词、具体剧情事件或连续 6 个字以上的原句！
3. 必须严格输出合法的 JSON 对象（不要使用 Markdown 代码块包裹之外的解释文字），结构如下：
{
  "language": {
    "colloquial_level": "具体描述口语化程度、用词质地与语气特征",
    "sentence_length_ratio": "结合统计数据描述长短句交错方式与节奏感",
    "rhetoric_density": "描述修辞密度、意象选择偏好或白描程度",
    "paragraph_rhythm": "结合统计数据描述段落长短与网文换行呼吸感"
  },
  "narrative": {
    "pov_mode": "叙事视角与镜头距离（如第三人称限知贴身视角如何锚定感官）",
    "info_release": "背景与设定信息的释放方式（如顺着动作/对话自然带出而非段首说明）",
    "scene_to_summary_ratio": "实时场景展现与过场概述的比例及处理手法",
    "transition_style": "场景切换与时间跳跃的剪辑方式"
  },
  "dialogue": {
    "dialogue_rhythm": "对白密度、句幅长短与接话节奏",
    "subtext_technique": "人物如何表达潜台词（如反问、嘴硬、避重就轻、半截话）",
    "interaction_texture": "对话间如何穿插微动作、眼神或器物互动"
  },
  "emotion": {
    "action_and_detail": "如何通过具体动作、停顿或生理微反应承载情绪",
    "inner_monologue_ratio": "心理活动的篇幅控制与切入方式（如短促吐槽、当下判断）",
    "whitespace_and_restraint": "情绪高点如何收束与留白"
  },
  "pacing": {
    "opening_setup": "开场切入情境的方式",
    "conflict_progression": "日常互动或冲突张力的递进手法",
    "turning_point": "小高潮或破绽转折的镜头处理",
    "closing_hook": "收尾余味或钩子的落点方式"
  },
  "genre_traits": {
    "genre_name": "细分题材与风格定位",
    "core_appeal": "该文风最抓人的阅读体验与爽点/张力来源",
    "characteristic_techniques": "最具辨识度的 2-3 项招牌写作手法",
    "genre_taboos": ["针对该文风的写作禁忌1", "写作禁忌2", "写作禁忌3"]
  },
  "anti_ai_rules": [
    "针对该文风定制的反AI腔铁律1",
    "反AI腔铁律2",
    "反AI腔铁律3",
    "反AI腔铁律4"
  ]
}"""


def _extract_json_dict(raw_text: str) -> dict[str, object] | None:
    text = raw_text.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if m:
            text = m.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _coerce_llm_str(val: object, max_len: int = 580) -> str:
    if isinstance(val, list):
        joined = "；".join(str(x).strip() for x in val if str(x).strip())
        return joined[:max_len]
    if isinstance(val, dict):
        joined = "；".join(f"{k}: {v}" for k, v in val.items() if str(v).strip())
        return joined[:max_len]
    return str(val).strip()[:max_len]


def _coerce_llm_str_list(val: object) -> list[str]:
    if isinstance(val, list):
        return [str(x).strip()[:250] for x in val if str(x).strip()]
    if isinstance(val, str):
        return [s.strip()[:250] for s in re.split(r"[；;\n]+", val) if s.strip()]
    return []


async def analyze_reference_excerpt_with_llm(
    reference_text: str,
    genre: str = "校园",
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[StyleProfile, dict[str, object], list[str]]:
    """Run hybrid quantitative + LLM 6-dimension style extraction with 7-gram anti-copy sanitization."""
    profile, derived_fields, notes = analyze_reference_excerpt(reference_text, genre=genre)
    m = profile.language.metrics

    if not (base_url and api_key and model):
        notes.append("当前未配置可用大模型，已使用本地规则启发式生成六维描述。")
        return profile, derived_fields, notes

    from app.services.llm.client import complete_chat

    user_prompt = (
        f"【参考样本所属题材】{genre}\n"
        f"【本地精准量化统计指标】\n"
        f"- 样本字数：{m.char_count} 字，共 {m.paragraph_count} 段（平均段长 {m.avg_paragraph_chars} 字，单行/短段占比 {m.single_line_para_ratio}%）\n"
        f"- 句式分布：平均句长 {m.avg_sentence_chars} 字；短句(≤12字) {m.short_sentence_pct}%、中句(13-28字) {m.medium_sentence_pct}%、长句(>28字) {m.long_sentence_pct}%\n"
        f"- 对白占比：{m.dialogue_ratio_pct}%\n"
        f"- 千字口语词频：{m.colloquial_per_kchars} 处；千字修辞词频：{m.rhetoric_per_kchars} 处\n\n"
        f"【参考小说样本片段（仅供提炼高层次文风技法，严禁复刻原句或人名情节）】\n"
        f"{reference_text[:4500]}\n\n"
        "请根据上述样本与统计数据，输出该样本专属的六维文风档案 JSON："
    )

    try:
        res = await complete_chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=_LLM_STYLE_EXTRACT_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.3,
            timeout_sec=45.0,
            task_type="style_profile_analyze",
        )
        parsed = _extract_json_dict(res.content)
        if parsed:
            merged = profile.model_dump()
            for sec_key in ("language", "narrative", "dialogue", "emotion", "pacing", "genre_traits"):
                sec_val = parsed.get(sec_key)
                if isinstance(sec_val, dict) and isinstance(merged.get(sec_key), dict):
                    for k, v in sec_val.items():
                        if k == "metrics" or k not in merged[sec_key] or not v:
                            continue
                        if k == "genre_taboos":
                            coerced_list = _coerce_llm_str_list(v)
                            if coerced_list:
                                merged[sec_key][k] = coerced_list
                        else:
                            max_l = 110 if k == "genre_name" else 580
                            coerced_str = _coerce_llm_str(v, max_len=max_l)
                            if coerced_str:
                                merged[sec_key][k] = coerced_str
            if parsed.get("anti_ai_rules"):
                coerced_rules = _coerce_llm_str_list(parsed["anti_ai_rules"])
                if coerced_rules:
                    merged["anti_ai_rules"] = coerced_rules
            merged["language"]["metrics"] = m.model_dump()
            llm_profile = StyleProfile.model_validate(merged)
            llm_profile = sanitize_profile_against_source(llm_profile, reference_text)
            derived_fields["tone"] = llm_profile.genre_traits.genre_name or derived_fields["tone"]
            derived_fields["desc_focus"] = llm_profile.emotion.action_and_detail or derived_fields["desc_focus"]
            derived_fields["pacing"] = llm_profile.language.paragraph_rhythm or derived_fields["pacing"]
            notes.append(f"已调用模型 ({model}) 深度提炼六维文学技法，并通过 7-gram 原句防抄袭过滤。")
            return llm_profile, derived_fields, notes
        notes.append(f"模型 ({model}) 返回格式未能解析为 JSON，已自动回退至本地统计启发式结果。")
    except Exception as exc:
        notes.append(f"模型调用异常（{exc}），已自动回退至本地统计启发式结果。")

    return profile, derived_fields, notes


def render_style_profile_prompt_block(profile: StyleProfile | dict | str | None) -> str:
    """Render a compact, high-signal 6-dimension Style Profile block for Layer 2 prompt injection."""
    if not profile:
        return ""
    if isinstance(profile, str):
        try:
            raw = json.loads(profile)
        except Exception:
            return ""
        if not isinstance(raw, dict) or not raw:
            return ""
        profile = StyleProfile.model_validate(raw)
    elif isinstance(profile, dict):
        if not profile:
            return ""
        profile = StyleProfile.model_validate(profile)

    taboos = "；".join(profile.genre_traits.genre_taboos[:3])
    lines = [
        "【结构化文风档案（Style Profile）】",
        f"- 语言表达：{profile.language.colloquial_level}；{profile.language.sentence_length_ratio}；{profile.language.rhetoric_density}",
        f"- 叙事方式：{profile.narrative.pov_mode}；{profile.narrative.scene_to_summary_ratio}",
        f"- 人物对话：{profile.dialogue.dialogue_rhythm}；{profile.dialogue.subtext_technique}",
        f"- 情绪与留白：{profile.emotion.action_and_detail}；{profile.emotion.whitespace_and_restraint}",
        f"- 节奏与题材（{profile.genre_traits.genre_name}）：{profile.genre_traits.characteristic_techniques}",
    ]
    if taboos:
        lines.append(f"- 文风避坑：{taboos}")
    return "\n".join(lines)


def select_dynamic_scene_pacing(
    beat: str,
    scene_index: int = 1,
    total_scenes: int = 1,
) -> tuple[str, str]:
    """Dynamically determine narrative pacing mode & craft rules from the current scene beat."""
    b = beat or ""
    if any(k in b for k in ("决定", "判断", "压在心里", "不点破", "不揭穿", "认出", "确认", "秘密", "掉马")):
        return (
            "key_choice_turning",
            "【本场动态节奏：暗涌破绽与抉择】在关键细节暴露处放慢镜头，先写具体的视觉/听觉破绽与一瞬间的反常停顿，"
            "再自然落到人物内心的权衡判断；收束要干脆有力，切忌反复自我解释。",
        )
    if any(k in b for k in ("微信", "聊天", "消息", "论坛", "帖", "回复", "网友", "调侃", "搭话", "闲聊")):
        return (
            "dialogue_spar",
            "【本场动态节奏：高频互动拉扯】提升对话与即时反应占比（约45%-55%），多用短促有来有回的交锋与接梗；"
            "线上消息要写出发送前后的停顿、改字或嘴硬反应，禁止把聊天记录当成干瘪的日志连贴，也禁止一方只用“嗯/行/好”单字敷衍。",
        )
    if any(k in b for k in ("尴尬", "心事", "沉默", "走神", "回忆", "夜里", "独处", "试探")):
        return (
            "emotional_undertow",
            "【本场动态节奏：情绪暗涌与留白】重在“言不由衷”与动作留白——话只说七分，用岔开话题、顺手忙活别的事掩饰真实在意；"
            "禁止直接写“他心里很乱/泛起涟漪”等总结词。",
        )
    position_hint = "开篇迅速切入现场处境" if scene_index == 1 else ("稳住转折余韵" if scene_index >= total_scenes else "紧凑衔接推进")
    return (
        "incident_progression",
        f"【本场动态节奏：现场事件推进（{position_hint}）】聚焦人物之间的具体碰撞与小波折，"
        "走路、排队、填表、搬东西等事务性过程用一句话带过结果，绝不拆成步步报账的微动作清单。",
    )
