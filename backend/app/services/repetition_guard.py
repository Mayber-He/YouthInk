"""T5: deterministic repetition detection for freshly generated scene text.

Pure functions (no DB / no LLM) so they are unit-testable with fixed samples.

Three independent signals, all configurable via :class:`RepetitionConfig`:

(a) **Reused spans** – maximal runs of text (>= ``ngram`` characters, default 8) that also
    appear in the previous chapter or in what is already written in this chapter. Dialogue
    and chat lines are compared WITHOUT their speaker label (``「吃一口软糖」：``), otherwise
    every chat line would "match" on the label alone.
(b) **Stock action phrases** – configurable list ("手指悬", "盯着", "扣在桌上", "风扇",
    "屏幕暗下去" …) counted across (already written chapter text + this scene). A phrase is
    flagged once its chapter total reaches ``action_word_max``.
(c) **must_not_include overlap** – items the scene plan forbade; a hit means the scene wrote
    material that belongs to a later scene.

Calibration note (real chapters from this project, see docs/loop/PROGRESS.md): whole-text
8-gram *coverage* barely separates a repeating chapter pair (2.9%) from clean ones (0–1.8%),
because the repetition is a handful of signature lines, not bulk copying. So the primary
trigger is the **list of reused spans** (longest span length / count of reused dialogue
lines); coverage is only a coarse safety net.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field

# Speaker label at the start of a chat line: 「名字」： / [名字]： / 名字：
_LABEL = re.compile(
    r"^\s*(?:[「『\[【（(][^」』\]】）)\n]{1,12}[」』\]】）)]\s*[：:]"
    r"|[^\s：:，。！？「」『』]{1,12}[：:])\s*"
)

DEFAULT_ACTION_PHRASES: tuple[str, ...] = (
    "手指悬", "拇指悬", "指尖悬", "手悬在", "盯着", "扣在桌上", "扣在桌面", "往桌上一扣",
    "风扇", "屏幕暗下去", "暗下去", "指节敲", "喉结动",
)


@dataclass
class RepetitionConfig:
    """Thresholds. Defaults come from calibration on real chapters; override via env."""

    enabled: bool = True
    ngram: int = 8
    # (a) a reused span at least this long (alnum chars) counts as a "significant" repeat.
    min_span_len: int = 10
    # (a') a whole dialogue line (speaker label stripped) of at least this many alnum chars that
    #      reappears verbatim counts as a reused line even when shorter than ``min_span_len``.
    min_dialogue_len: int = 6
    # (a') flag when this many dialogue lines are reused.
    max_reused_dialogues: int = 1
    # (a) flag when this many significant spans exist …
    max_significant_spans: int = 1
    # (a) … or when overall 8-gram coverage reaches this ratio (coarse safety net).
    max_coverage: float = 0.15
    # (b) a stock phrase is flagged once its total count in chapter-so-far + scene reaches this.
    action_word_max: int = 3
    action_phrases: tuple[str, ...] = DEFAULT_ACTION_PHRASES
    # (c) a must_not_include item is flagged when this fraction of its n-grams appears in the scene.
    forbidden_overlap: float = 0.5
    auto_rewrite: bool = True

    @classmethod
    def from_env(cls) -> "RepetitionConfig":
        """Env overrides (all optional): YOUTHINK_REPEAT_ENABLED / _AUTO_REWRITE / _NGRAM /
        _MIN_SPAN / _MAX_SPANS / _MAX_COVERAGE / _ACTION_MAX / _FORBIDDEN_OVERLAP / _ACTION_WORDS
        (comma separated)."""
        cfg = cls()

        def _flag(name: str, default: bool) -> bool:
            v = os.environ.get(name)
            return default if v is None else v.strip().lower() not in ("0", "false", "no", "")

        def _num(name: str, default, cast):
            v = os.environ.get(name)
            try:
                return cast(v) if v not in (None, "") else default
            except ValueError:
                return default

        cfg.enabled = _flag("YOUTHINK_REPEAT_ENABLED", cfg.enabled)
        cfg.auto_rewrite = _flag("YOUTHINK_REPEAT_AUTO_REWRITE", cfg.auto_rewrite)
        cfg.ngram = max(4, _num("YOUTHINK_REPEAT_NGRAM", cfg.ngram, int))
        cfg.min_span_len = _num("YOUTHINK_REPEAT_MIN_SPAN", cfg.min_span_len, int)
        cfg.max_significant_spans = _num("YOUTHINK_REPEAT_MAX_SPANS", cfg.max_significant_spans, int)
        cfg.max_coverage = _num("YOUTHINK_REPEAT_MAX_COVERAGE", cfg.max_coverage, float)
        cfg.action_word_max = _num("YOUTHINK_REPEAT_ACTION_MAX", cfg.action_word_max, int)
        cfg.forbidden_overlap = _num("YOUTHINK_REPEAT_FORBIDDEN_OVERLAP", cfg.forbidden_overlap, float)
        words = os.environ.get("YOUTHINK_REPEAT_ACTION_WORDS")
        if words and words.strip():
            cfg.action_phrases = tuple(w.strip() for w in words.split(",") if w.strip())
        return cfg


@dataclass
class RepeatedSpan:
    text: str          # the reused wording as it appears in the NEW text
    length: int        # alnum length
    source: str        # "previous_chapter" | "chapter_so_far"


@dataclass
class ActionPhraseHit:
    phrase: str
    count: int         # total in chapter-so-far + scene


@dataclass
class ForbiddenHit:
    item: str
    overlap: float


@dataclass
class ReusedDialogue:
    text: str          # the dialogue as written in the NEW text (speaker label removed)
    source: str        # "previous_chapter" | "chapter_so_far"


@dataclass
class RepetitionReport:
    triggered: bool = False
    reasons: list[str] = field(default_factory=list)
    coverage: float = 0.0
    spans: list[RepeatedSpan] = field(default_factory=list)
    dialogues: list[ReusedDialogue] = field(default_factory=list)
    action_hits: list[ActionPhraseHit] = field(default_factory=list)
    forbidden_hits: list[ForbiddenHit] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def describe_for_model(self, max_items: int = 8) -> str:
        """Concrete, quotable list of what to avoid when rewriting (fed back to the model)."""
        lines: list[str] = []
        for dl in self.dialogues[:max_items]:
            where = "上一章" if dl.source == "previous_chapter" else "本章前文"
            lines.append(f"- 整句台词与{where}重复：「{dl.text}」")
        for sp in self.spans[:max_items]:
            where = "上一章" if sp.source == "previous_chapter" else "本章前文"
            lines.append(f"- 与{where}重复的原句/片段：「{sp.text}」")
        for ah in self.action_hits[:max_items]:
            lines.append(f"- 固定动作/意象「{ah.phrase}」在本章已出现 {ah.count} 次，请换一种写法或省略")
        for fh in self.forbidden_hits[:max_items]:
            lines.append(f"- 本场景禁止出现的素材「{fh.item}」被写入了，请删除或留给后续场景")
        return "\n".join(lines)


# ---------------------------------------------------------------- helpers

def _units(text: str) -> list[tuple[str, str, list[int]]]:
    """Per line: (raw_line, alnum_only_string_without_label, index_map_into_raw_line)."""
    out: list[tuple[str, str, list[int]]] = []
    for line in (text or "").splitlines():
        m = _LABEL.match(line)
        start = m.end() if m else 0
        idx = [i for i in range(start, len(line)) if line[i].isalnum()]
        s = "".join(line[i] for i in idx)
        if s:
            out.append((line, s, idx))
    return out


def _ngram_set(text: str, n: int) -> set[str]:
    grams: set[str] = set()
    for _raw, s, _idx in _units(text):
        for i in range(len(s) - n + 1):
            grams.add(s[i : i + n])
    return grams


def find_reused_spans(
    new_text: str, reference: str, n: int = 8, source: str = "previous_chapter"
) -> tuple[float, list[RepeatedSpan]]:
    """Return (coverage ratio, maximal reused spans) of ``new_text`` versus ``reference``."""
    ref_grams = _ngram_set(reference, n)
    if not ref_grams:
        return 0.0, []
    total = covered = 0
    spans: list[RepeatedSpan] = []
    seen: set[str] = set()
    for raw, s, idx in _units(new_text):
        mark = [False] * len(s)
        for i in range(len(s) - n + 1):
            if s[i : i + n] in ref_grams:
                for j in range(i, i + n):
                    mark[j] = True
        total += len(s)
        covered += sum(mark)
        i = 0
        while i < len(s):
            if not mark[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(s) and mark[j + 1]:
                j += 1
            shown = raw[idx[i] : idx[j] + 1]
            key = s[i : j + 1]
            if key not in seen:
                seen.add(key)
                spans.append(RepeatedSpan(text=shown, length=j - i + 1, source=source))
            i = j + 1
    spans.sort(key=lambda sp: sp.length, reverse=True)
    return (covered / total if total else 0.0), spans


_CHAT_LINE = re.compile(r"^\s*[「『\[【][^」』\]】\n]{1,12}[」』\]】]\s*[：:]\s*(.+)$")
_QUOTED = re.compile(r"[“\"「『]([^”\"」』\n]{4,})[”\"」』]")


def _dialogue_items(text: str) -> list[tuple[str, str]]:
    """(raw dialogue, alnum-normalized) for chat lines ('「名」：话') and quoted speech."""
    items: list[tuple[str, str]] = []
    for line in (text or "").splitlines():
        m = _CHAT_LINE.match(line)
        candidates = [m.group(1).strip()] if m else _QUOTED.findall(line)
        for raw in candidates:
            norm = "".join(c for c in raw if c.isalnum())
            if norm:
                items.append((raw.strip(), norm))
    return items


def find_reused_dialogues(
    new_text: str, reference: str, min_len: int = 6, source: str = "previous_chapter"
) -> list[ReusedDialogue]:
    """Dialogue lines of ``new_text`` that already appear (whole line) in ``reference``.

    A line counts when its normalized form is at least ``min_len`` long and is contained in
    some reference dialogue (or contains one of at least the same length) — i.e. the same
    sentence is being said again.
    """
    ref = [norm for _raw, norm in _dialogue_items(reference)]
    if not ref:
        return []
    out: list[ReusedDialogue] = []
    seen: set[str] = set()
    for raw, norm in _dialogue_items(new_text):
        if len(norm) < min_len or norm in seen:
            continue
        if any(norm in r or (len(r) >= min_len and r in norm) for r in ref):
            seen.add(norm)
            out.append(ReusedDialogue(text=raw, source=source))
    return out


def count_action_phrases(
    scene_text: str, chapter_so_far: str, phrases: tuple[str, ...]
) -> list[ActionPhraseHit]:
    """Phrases whose occurrences in (chapter_so_far + scene) are NOT merely inherited.

    Only phrases that appear in the new scene are considered, so a phrase overused earlier
    in the chapter does not re-flag a scene that doesn't use it.
    """
    hits: list[ActionPhraseHit] = []
    for p in phrases:
        if not p or p not in scene_text:
            continue
        hits.append(ActionPhraseHit(phrase=p, count=chapter_so_far.count(p) + scene_text.count(p)))
    return hits


def forbidden_overlap(scene_text: str, items: list[str], n: int = 4) -> list[ForbiddenHit]:
    """Share of each forbidden item's character n-grams that also occur in the scene."""
    norm_scene = "".join(c for c in scene_text if c.isalnum())
    hits: list[ForbiddenHit] = []
    for item in items:
        core = "".join(c for c in item if c.isalnum())
        if len(core) < n:
            if core and core in norm_scene:
                hits.append(ForbiddenHit(item=item, overlap=1.0))
            continue
        grams = {core[i : i + n] for i in range(len(core) - n + 1)}
        if not grams:
            continue
        ratio = sum(1 for g in grams if g in norm_scene) / len(grams)
        hits.append(ForbiddenHit(item=item, overlap=round(ratio, 3)))
    return hits


def split_must_not_include(beat: str) -> list[str]:
    """Extract the '本场禁止出现：a；b' items that T3 serializes into ``scenes.beat``."""
    for line in (beat or "").splitlines():
        line = line.strip()
        if line.startswith("本场禁止出现："):
            body = line.split("：", 1)[1]
            return [x.strip() for x in re.split(r"[；;]", body) if x.strip()]
    return []


# ---------------------------------------------------------------- main entry

def analyze_scene_repetition(
    scene_text: str,
    *,
    previous_chapter: str = "",
    chapter_so_far: str = "",
    must_not_include: list[str] | None = None,
    config: RepetitionConfig | None = None,
) -> RepetitionReport:
    """Run all three checks on a freshly generated scene and decide whether it is over threshold."""
    cfg = config or RepetitionConfig()
    report = RepetitionReport()
    if not cfg.enabled or not (scene_text or "").strip():
        return report

    cov_prev, spans_prev = find_reused_spans(scene_text, previous_chapter, cfg.ngram, "previous_chapter")
    cov_here, spans_here = find_reused_spans(scene_text, chapter_so_far, cfg.ngram, "chapter_so_far")
    report.coverage = round(max(cov_prev, cov_here), 4)
    all_spans = sorted(spans_prev + spans_here, key=lambda sp: sp.length, reverse=True)
    report.spans = all_spans

    report.dialogues = (
        find_reused_dialogues(scene_text, previous_chapter, cfg.min_dialogue_len, "previous_chapter")
        + find_reused_dialogues(scene_text, chapter_so_far, cfg.min_dialogue_len, "chapter_so_far")
    )
    if len(report.dialogues) >= cfg.max_reused_dialogues:
        report.reasons.append(f"有 {len(report.dialogues)} 句台词与前文/上一章整句重复")

    significant = [sp for sp in all_spans if sp.length >= cfg.min_span_len]
    if len(significant) >= cfg.max_significant_spans:
        report.reasons.append(
            f"与前文/上一章有 {len(significant)} 处 ≥{cfg.min_span_len} 字的重复片段"
        )
    if report.coverage >= cfg.max_coverage:
        report.reasons.append(f"{cfg.ngram} 字片段重合率 {report.coverage:.1%} ≥ {cfg.max_coverage:.0%}")

    report.action_hits = [
        h for h in count_action_phrases(scene_text, chapter_so_far, cfg.action_phrases)
        if h.count >= cfg.action_word_max
    ]
    if report.action_hits:
        report.reasons.append(
            "固定动作词过多：" + "、".join(f"{h.phrase}×{h.count}" for h in report.action_hits)
        )

    report.forbidden_hits = [
        h for h in forbidden_overlap(scene_text, must_not_include or [])
        if h.overlap >= cfg.forbidden_overlap
    ]
    if report.forbidden_hits:
        report.reasons.append("写入了本场景禁止出现的素材：" + "、".join(h.item for h in report.forbidden_hits))

    report.triggered = bool(report.reasons)
    return report
