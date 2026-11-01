"""T4: leaner, re-ordered prompt pieces for scene/chapter prose generation.

Pure helpers (no DB / no LLM) so they are unit-testable:

* ``core_setting_blurb``  – 1–2 sentence core premise instead of the whole-book
  synopsis (which contains late-plot spoilers that leak into early chapters).
* ``style_layer``         – style layer that ALWAYS carries forbidden expressions
  and up to 2 example paragraphs, even when the author wrote a ``style_note``.
* ``ending_rule``         – closing rule: end on dialogue / action / decision, not
  imagery or feeling; rotate the style between adjacent scenes.

Behaviour is controlled by ``PROSE_PROMPT_V2`` (default ON). Set env
``YOUTHINK_PROSE_PROMPT_V2=0`` to fall back to the previous assembly.
"""

from __future__ import annotations

import os
import re

# 句末标点（含中英文），用于按句截取核心设定。
_SENT_END = re.compile(r"(?<=[。！？!?；;])")

# 收尾方式轮换：相邻场景使用不同的收尾落点，避免每场都以同一种方式收束。
ENDING_MODES: tuple[str, ...] = (
    "一句对话（对方的回应或没说完的半句）",
    "一个具体动作（放下、起身、转身、递出某物）",
    "一个当下做出的决定（说出口的选择或已经迈出的一步）",
)


def prose_prompt_v2_enabled() -> bool:
    """Feature switch, default ON. ``YOUTHINK_PROSE_PROMPT_V2=0`` disables."""
    return os.environ.get("YOUTHINK_PROSE_PROMPT_V2", "1").strip() not in ("0", "false", "False", "")


# 带有“终局/后期走向”色彩的措辞。含这些词的句子不进入核心设定，避免把后期剧情
# 泄露给早期章节。这是启发式（宁可多丢一句），可按作品文风增减。
LATE_PLOT_HINTS: tuple[str, ...] = (
    "最终", "最后", "结局", "终于", "终将", "多年后", "毕业后", "毕业之后",
    "结婚", "步入婚姻", "表白成功", "在一起", "官宣", "真相大白", "揭穿", "掉马",
    "后来", "此后", "从此", "直到", "直至", "不久之后", "几年后",
)


def _split_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", (text or ""))
    return [s for s in _SENT_END.split(compact) if s]


def _first_sentences(text: str, max_sentences: int, max_chars: int, *, skip_late: bool = False) -> str:
    """First ``max_sentences`` sentences of ``text``, never exceeding ``max_chars``.

    With ``skip_late=True`` the FIRST sentence is always kept (it is the premise), but any later
    sentence containing a late-plot hint is dropped rather than included.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return ""
    out = ""
    for i, sent in enumerate(sentences):
        if i >= max_sentences:
            break
        if skip_late and i > 0 and any(h in sent for h in LATE_PLOT_HINTS):
            break  # everything after a spoiler-ish sentence is later story; stop here
        if len(out) + len(sent) > max_chars:
            break
        out += sent
    return out or sentences[0][:max_chars]


def core_setting_blurb(synopsis: str, protagonist_concept: str = "", max_chars: int = 200) -> str:
    """Return a 1–2 sentence core premise.

    Always keeps the first sentence of the synopsis (the premise). A second sentence is added
    only if it fits ``max_chars`` and carries no late-plot hint (see ``LATE_PLOT_HINTS``);
    this keeps endings / later developments out of early chapters. If the first sentence alone
    exceeds the cap it is hard-cut. Falls back to ``protagonist_concept`` when the synopsis
    is empty.
    """
    blurb = _first_sentences(synopsis, 2, max_chars, skip_late=True)
    if blurb:
        return blurb
    return _first_sentences(protagonist_concept, 2, max_chars, skip_late=True)


def protagonist_brief(protagonist_concept: str, max_chars: int = 300) -> str:
    """Cap the protagonist concept for prose prompts.

    The full concept often runs >1000 chars and ends with relationship arcs / "故事核心"
    that describe late-plot developments. Per-character facts are injected separately from
    the character cards, so prose generation only needs the opening of the concept.
    """
    return _first_sentences(protagonist_concept, 6, max_chars)


def style_layer(
    *,
    style_name: str = "",
    pov: str = "",
    tense_feel: str = "",
    tone: str = "",
    sentence_pref: str = "",
    dialogue_ratio: str = "",
    desc_focus: str = "",
    pacing: str = "",
    forbidden_exprs: list[str] | None = None,
    example_paras: list[str] | None = None,
    has_style_note: bool = False,
    max_examples: int = 2,
) -> str:
    """Build the style layer.

    * With NO author ``style_note``: full template (as before) plus forbidden + examples.
    * WITH an author ``style_note``: the template's descriptive fields are skipped (the
      author's note takes precedence) but ``forbidden_exprs`` and up to ``max_examples``
      example paragraphs are STILL injected — previously they were dropped entirely.
    """
    parts: list[str] = []
    if not has_style_note and style_name:
        parts.append(
            f"风格模板：{style_name}\n"
            f"叙事视角：{pov} | 语感：{tense_feel}\n"
            f"基调：{tone} | 句式：{sentence_pref} | 对话比例：{dialogue_ratio}\n"
            f"描写侧重：{desc_focus} | 节奏：{pacing}"
        )
    forb = [f for f in (forbidden_exprs or []) if f]
    if forb:
        parts.append("禁用套话表达：" + "、".join(forb))
    exs = [e for e in (example_paras or []) if e][:max_examples]
    if exs:
        parts.append("风格范文（只学语感与节奏，不照抄句子）：\n" + "\n".join(f"示例：{e}" for e in exs))
    return "\n".join(parts)


def ending_rule(scene_index: int) -> str:
    """Closing rule for the task instruction, rotating the preferred mode by scene index."""
    mode = ENDING_MODES[(max(1, scene_index) - 1) % len(ENDING_MODES)]
    return (
        "\n【收尾规则】最后一句用对话、动作或决定结束，不要以意象、景物或感受收尾；"
        f"本场景优先以{mode}收束，与相邻场景的收尾方式错开。"
    )
