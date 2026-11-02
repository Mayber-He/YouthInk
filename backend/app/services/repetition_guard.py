"""T5: deterministic repetition detection for freshly generated scene text.

Pure functions (no DB / no LLM) so they are unit-testable with fixed samples.

Six independent signals, all configurable via :class:`RepetitionConfig`:

(a) **Reused spans** – maximal runs of text (>= ``ngram`` characters, default 8) that also
    appear in the previous chapter or in what is already written in this chapter. Dialogue
    and chat lines are compared WITHOUT their speaker label (``「吃一口软糖」：``), otherwise
    every chat line would "match" on the label alone. T17: quotes the current beat explicitly
    requires are exempt, but only when the same words already exist verbatim in earlier prose.
(b) **Stock action phrases** – configurable list ("手指悬", "盯着", "扣在桌上", "风扇",
    "屏幕暗下去" …) counted across (already written chapter text + this scene). A phrase is
    flagged once its chapter total reaches ``action_word_max``.
(c) **must_not_include overlap** – items the scene plan forbade; a hit means the scene wrote
    material that belongs to a later scene.
(d) **Recall-reference claims (T17)** – paragraphs claiming "一字不差/一模一样/原话/当时回/
    当时说" must quote the previous chapter verbatim; invented quotes or "…表情" details are
    flagged so the single rewrite can replace them with a summary.
(e) **Scene seam (T18)** – the new scene's first ~200 characters are compared with the previous
    scene's last ~300 characters; any shared run of >=6 characters means the scene restarted by
    re-describing the old ending instead of continuing after it.
(f) **Appearance tags (T19/T20)** – 2–8-character body/expression/posture phrases taken from
    present characters' appearance cards (punctuation-split clauses and word-level sub-phrases)
    whose total count in chapter-so-far + new scene reaches ``appearance_max_count``. Clothing and
    accessories (白衬衫/发圈/校徽 …) are excluded. The rewrite keeps the earliest occurrence and
    rewrites/deletes the rest.

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

# T13: relative time words and the number of days they correctly describe.
# Longest first so "大前天" is not also counted as "前天" after masking.
_TIME_WORDS: tuple[tuple[str, int], ...] = (
    ("大前天", 3),
    ("前一晚", 1), ("前一天", 1), ("前天", 2),
    ("前晚", 1), ("头天", 1), ("隔夜", 1),
    ("昨晚", 1), ("昨天", 1), ("昨夜", 1),
)

# Public view for prompt building (word -> days the word correctly describes).
TIME_WORD_DAYS: dict[str, int] = dict(_TIME_WORDS)


def find_time_mismatches(scene_text: str, gap_days: int | None) -> list[str]:
    """Relative time words that contradict the known chapter gap.

    Only checked when the gap is known and > 1 day (adjacent chapters keep the old behaviour).
    ``昨晚/昨天/昨夜/前一晚/前晚/前一天/头天/隔夜`` describe the immediately preceding day,
    ``前天`` two days before and ``大前天`` three. A word that matches the actual gap is not
    reported (e.g. ``前天`` with a 2-day gap), so the rule follows the calendar instead of a
    fixed word list.
    """
    if gap_days is None or gap_days <= 1 or not (scene_text or "").strip():
        return []
    remaining = scene_text
    hits: list[str] = []
    for word, days in _TIME_WORDS:
        if word not in remaining:
            continue
        if days != gap_days:
            hits.append(word)
        # Mask every occurrence so a longer word is not re-reported by a shorter substring.
        remaining = remaining.replace(word, "　" * len(word))
    return hits


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
    # (d) T18: compare the new scene's opening with the previous scene's ending.
    seam_check: bool = True
    seam_head_chars: int = 200
    seam_tail_chars: int = 300
    seam_ngram: int = 6
    # (f) T19: appearance phrases from present characters' cards that recur in this chapter.
    appearance_check: bool = True
    appearance_max_count: int = 3

    @classmethod
    def from_env(cls) -> "RepetitionConfig":
        """Env overrides (all optional): YOUTHINK_REPEAT_ENABLED / _AUTO_REWRITE / _NGRAM /
        _MIN_SPAN / _MAX_SPANS / _MAX_COVERAGE / _ACTION_MAX / _FORBIDDEN_OVERLAP / _ACTION_WORDS
        / _SEAM_CHECK / _SEAM_HEAD / _SEAM_TAIL / _SEAM_NGRAM /
        _APPEARANCE_CHECK / _APPEARANCE_MAX."""
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
        cfg.seam_check = _flag("YOUTHINK_REPEAT_SEAM_CHECK", cfg.seam_check)
        cfg.seam_head_chars = max(40, _num("YOUTHINK_REPEAT_SEAM_HEAD", cfg.seam_head_chars, int))
        cfg.seam_tail_chars = max(40, _num("YOUTHINK_REPEAT_SEAM_TAIL", cfg.seam_tail_chars, int))
        cfg.seam_ngram = max(4, _num("YOUTHINK_REPEAT_SEAM_NGRAM", cfg.seam_ngram, int))
        cfg.appearance_check = _flag("YOUTHINK_REPEAT_APPEARANCE_CHECK", cfg.appearance_check)
        cfg.appearance_max_count = max(2, _num(
            "YOUTHINK_REPEAT_APPEARANCE_MAX", cfg.appearance_max_count, int
        ))
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
class AppearanceTagHit:
    phrase: str
    count: int         # total in chapter-so-far + scene
    scene_count: int   # occurrences in the new scene only


@dataclass
class RecallMiss:
    text: str          # the claimed quotation / expression as written in the new scene
    kind: str          # "quoted" | "expression"


@dataclass
class RepetitionReport:
    triggered: bool = False
    reasons: list[str] = field(default_factory=list)
    coverage: float = 0.0
    spans: list[RepeatedSpan] = field(default_factory=list)
    dialogues: list[ReusedDialogue] = field(default_factory=list)
    action_hits: list[ActionPhraseHit] = field(default_factory=list)
    forbidden_hits: list[ForbiddenHit] = field(default_factory=list)
    time_hits: list[str] = field(default_factory=list)
    story_time_gap_days: int | None = None
    # T17: beat lines that are verified verbatim in earlier prose are exempt from the
    # dialogue/span checks, but must be preserved by the rewrite.
    required_quotes: list[str] = field(default_factory=list)
    # T17: previous-chapter lines the rewrite may quote verbatim.
    citable_quotes: list[str] = field(default_factory=list)
    # T17: "一字不差/一模一样" claims whose quotation or expression is NOT in the previous chapter.
    recall_misses: list[RecallMiss] = field(default_factory=list)
    # T18: wording shared between this scene's opening and the previous scene's ending.
    seam_spans: list[RepeatedSpan] = field(default_factory=list)
    # T19: appearance-card phrases overused in chapter-so-far + this scene.
    appearance_hits: list[AppearanceTagHit] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def describe_for_model(self, max_items: int = 8) -> str:
        """Concrete, quotable list of what to avoid when rewriting (fed back to the model)."""
        lines: list[str] = []
        if self.time_hits:
            lines.append(f'- 与上一章相隔 {self.story_time_gap_days} 天，正文出现“{"、".join(self.time_hits)}”；请核对日期，不能用这些词指称上一章的事件，改用具体日期或准确的时间间隔。')
        for dl in self.dialogues[:max_items]:
            where = "上一章" if dl.source == "previous_chapter" else "本章前文"
            lines.append(f"- 整句台词与{where}重复：「{dl.text}」")
        for sp in self.spans[:max_items]:
            where = "上一章" if sp.source == "previous_chapter" else "本章前文"
            lines.append(f"- 与{where}重复的原句/片段：「{sp.text}」")
        for sp in self.seam_spans[:max_items]:
            lines.append(
                f"- 本场景开头与上一场景结尾重复：「{sp.text}」；请从上场结束之后的新动作或新状态写起"
            )
        for ah in self.action_hits[:max_items]:
            lines.append(f"- 固定动作/意象「{ah.phrase}」在本章已出现 {ah.count} 次，请换一种写法或省略")
        for ah in self.appearance_hits[:max_items]:
            lines.append(
                f"- 外貌标签「{ah.phrase}」在本章（含本场）已出现 {ah.count} 次（本场 {ah.scene_count} 次）；"
                "保留最早一处，其余在本场改写或删除"
            )
        for fh in self.forbidden_hits[:max_items]:
            lines.append(f"- 本场景禁止出现的素材「{fh.item}」被写入了，请删除或留给后续场景")
        for rm in self.recall_misses[:max_items]:
            lines.append(
                f"- 回忆引用无法在上一章原文中逐字找到：「{rm.text}」；"
                "请改成概括，不得补写表情或台词"
            )
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
    new_text: str,
    reference: str,
    n: int = 8,
    source: str = "previous_chapter",
    denominator_text: str | None = None,
) -> tuple[float, list[RepeatedSpan]]:
    """Return (coverage ratio, maximal reused spans) of ``new_text`` versus ``reference``.

    ``denominator_text`` lets callers mask exempted lines out of ``new_text`` without shrinking
    the coverage denominator (T17 uses it so beat-required quotes do not inflate coverage).
    """
    ref_grams = _ngram_set(reference, n)
    if not ref_grams:
        return 0.0, []
    total = 0
    if denominator_text is not None:
        total = sum(len(s) for _raw, s, _idx in _units(denominator_text))
    covered = 0
    spans: list[RepeatedSpan] = []
    seen: set[str] = set()
    for raw, s, idx in _units(new_text):
        mark = [False] * len(s)
        for i in range(len(s) - n + 1):
            if s[i : i + n] in ref_grams:
                for j in range(i, i + n):
                    mark[j] = True
        if denominator_text is None:
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


def find_scene_seam(
    scene_text: str,
    previous_scene_text: str,
    *,
    head_chars: int = 200,
    tail_chars: int = 300,
    n: int = 6,
) -> list[RepeatedSpan]:
    """T18: wording repeated between the new scene's opening and the previous scene's ending.

    Both sides are character windows (default 200 / 300 raw characters). A shared run of at
    least ``n`` alphanumeric characters is enough — the live sample repeated
    "表格垫在行李袋上，" and restarted the scene by re-describing the previous ending.
    """
    head = (scene_text or "")[: max(0, head_chars)]
    tail = (previous_scene_text or "")[-max(0, tail_chars):] if previous_scene_text else ""
    if not head.strip() or not tail.strip():
        return []
    _coverage, spans = find_reused_spans(head, tail, n, "previous_scene_tail")
    return [sp for sp in spans if sp.length >= n]


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


# T19/T20: appearance cards are free text; keep only short body/expression/posture phrases.
# Clothing/accessory nouns are excluded by the stop list below (T20-a).
_APPEARANCE_HINTS: tuple[str, ...] = (
    "眉", "眼", "脸", "颊", "额头", "鼻", "嘴", "唇", "下巴", "耳", "发",
    "皮肤", "肤", "五官", "手", "指", "肩", "背", "腰", "腿", "脚", "身",
    "胸", "腹", "脖", "颈", "喉", "个子", "高挑", "瘦", "胖",
    "姿", "神情", "神色", "神态", "表情", "目光", "眼神", "睫毛", "瞳",
)
# Non-appearance words that contain an appearance hint character (e.g. 手机 contains 手).
_APPEARANCE_STOP: frozenset[str] = frozenset({
    "手机", "手上", "手里", "手中", "对方", "时候", "一点", "有些", "没有",
    "别的", "东西", "什么", "一个", "一件", "一根", "一支", "上面", "下面",
})
# T20-a: clothing and accessories are not "重复外貌标签" even when they contain a body hint
# (背包/发圈/眼镜/手表 …). Substring matching also rejects descriptive variants like 素色发圈.
_ACCESSORY_STOP: tuple[str, ...] = (
    "发圈", "发带", "发夹", "发卡", "发箍", "发绳", "发簪", "发饰",
    "背包", "书包", "挎包", "手袋", "手提包", "钱包", "手机",
    "眼镜", "墨镜", "耳环", "耳钉", "耳罩",
    "手表", "手链", "手镯", "手套", "手帕",
    "校徽", "徽章", "胸针", "项链", "围巾", "领带", "领结", "腰带", "皮带",
    "衬衫", "外套", "夹克", "卫衣", "毛衣", "校服", "裙子", "裤子", "短裤",
    "鞋子", "袜子", "帽子", "袖口", "领口", "扣子", "拉链", "口袋",
)
# Actions that happen to contain a body-part character (抬眼/低头) are not appearance labels.
_APPEARANCE_ACTIONS: tuple[str, ...] = (
    "低头", "抬头", "回头", "转头", "抬眼", "垂眼", "眯眼",
    "说话", "微笑", "皱眉", "抿嘴",
)


def _looks_like_appearance(phrase: str) -> bool:
    phrase = (phrase or "").strip()
    if not phrase or phrase in _APPEARANCE_STOP:
        return False
    if any(item in phrase for item in _ACCESSORY_STOP):
        return False
    if any(action in phrase for action in _APPEARANCE_ACTIONS):
        return False
    return any(hint in phrase for hint in _APPEARANCE_HINTS)


def extract_appearance_tags(
    appearance: str, min_chars: int = 2, max_chars: int = 8
) -> list[str]:
    """T19: short descriptive phrases from a character's appearance card.

    The card is split on punctuation first; each 2–8-character clause is a candidate, and
    longer clauses contribute their 2–8-character word tokens (jieba) so a distinctive label
    such as "眉心" is found inside "眉心有一点淡淡的褶". Only body/expression/posture phrases
    survive; clothing/accessory nouns, obvious non-appearance words and actions are dropped.
    First-seen order.
    """
    import jieba  # lazy: the other repetition checks never pay the dictionary-load cost

    out: list[str] = []
    seen: set[str] = set()

    def _add(phrase: str) -> None:
        phrase = (phrase or "").strip()
        if not (min_chars <= len(phrase) <= max_chars):
            return
        if phrase in seen or not _looks_like_appearance(phrase):
            return
        seen.add(phrase)
        out.append(phrase)

    clauses = re.split(r"[，。；：！？、,.;:!?\n\r\t（）()【】\[\]《》“”\"'‘’]+", appearance or "")
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        _add(clause)
        for token in jieba.cut(clause):
            _add(token)
    return out


def count_appearance_tags(
    scene_text: str,
    chapter_so_far: str,
    appearances: list[str] | None,
    max_count: int = 3,
) -> list[AppearanceTagHit]:
    """T19: appearance phrases whose chapter-wide count reaches ``max_count``.

    Like the stock-action check, only phrases used in the NEW scene are returned: a scene that
    does not mention the overused tag has nothing for the rewrite to remove.
    """
    if not appearances:
        return []
    seen: set[str] = set()
    hits: list[AppearanceTagHit] = []
    for appearance in appearances:
        for phrase in extract_appearance_tags(appearance):
            if phrase in seen:
                continue
            seen.add(phrase)
            scene_count = scene_text.count(phrase)
            if scene_count <= 0:
                continue
            total = chapter_so_far.count(phrase) + scene_count
            if total >= max_count:
                hits.append(AppearanceTagHit(phrase=phrase, count=total, scene_count=scene_count))
    hits.sort(key=lambda h: (-h.count, h.phrase))
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


# ---------------------------------------------------------------- T17: beat quotes / recall

_ANY_QUOTED = re.compile(r"[“\"「『]([^”\"」』\n]+)[”\"」』]")
_RECALL_MARKER = re.compile(r"一字不差|一模一样|原话|当时回|当时说")
_EXPRESSION_FILLERS = ("一个", "这个", "那个", "这种", "那种", "一种", "个")


def _normalise(text: str) -> str:
    """Compare Chinese prose while ignoring whitespace and punctuation."""
    return "".join(c.lower() for c in (text or "") if c.isalnum())


def extract_quoted_phrases(text: str, min_chars: int = 1) -> list[str]:
    """Quoted bodies in ``text`` (quote marks removed), in first-seen order."""
    out: list[str] = []
    seen: set[str] = set()
    for match in _ANY_QUOTED.finditer(text or ""):
        body = match.group(1).strip()
        norm = _normalise(body)
        if len(norm) < min_chars or norm in seen:
            continue
        seen.add(norm)
        out.append(body)
    return out


def extract_required_quotes(
    beat: str, *references: str, min_chars: int = 4
) -> list[str]:
    """T17: quotes the beat requires, but only those already verbatim in earlier prose.

    A quote that the beat invents is NOT exempt from the repetition checks; only a genuine
    callback to the previous chapter / already-written chapter qualifies.
    """
    refs = [r for r in references if r]
    return [
        q for q in extract_quoted_phrases(beat, min_chars)
        if any(q in ref for ref in refs)
    ]


def extract_citable_quotes(
    previous_chapter: str, min_chars: int = 4, max_items: int = 60
) -> list[str]:
    """T17: verbatim lines from the previous chapter that a rewrite may quote."""
    out: list[str] = []
    seen: set[str] = set()
    for raw, norm in _dialogue_items(previous_chapter):
        if len(norm) < min_chars or norm in seen:
            continue
        seen.add(norm)
        out.append(raw)
        if len(out) >= max_items:
            break
    return out


def _mask_quotes(text: str, quotes: list[str]) -> str:
    """Replace required quotes with a non-alnum placeholder so n-gram checks ignore them."""
    masked = text or ""
    for quote in sorted((q for q in quotes if q), key=len, reverse=True):
        masked = masked.replace(quote, "□" * len(quote))
    return masked


def _expression_phrases(paragraph: str) -> list[str]:
    """Extract short '…表情' descriptions so invented expressions can be checked too."""
    out: list[str] = []
    for segment in re.split(r"[，。；：！？\n]", paragraph or ""):
        pos = segment.find("表情")
        if pos < 0:
            continue
        cut = -1
        for marker in _EXPRESSION_FILLERS:
            found = segment.rfind(marker, 0, pos)
            if found >= 0:
                cut = max(cut, found + len(marker))
        phrase = (segment[cut:pos + 2] if cut >= 0 else segment[max(0, pos - 8):pos + 2]).strip()
        phrase = phrase.lstrip("的了着")
        norm = _normalise(phrase)
        if len(norm) >= 3 and phrase not in out:
            out.append(phrase)
    return out


def find_recall_mismatches(scene_text: str, previous_chapter: str) -> list[RecallMiss]:
    """T17: verify '一字不差/一模一样/原话/当时回/当时说' claims against the previous chapter.

    In any paragraph carrying one of those markers, every quoted body of >=4 characters must
    exist verbatim (after removing punctuation/whitespace) in the previous chapter. Short
    '…表情' descriptions in the same paragraph are checked the same way, because the live sample
    fabricated "歪头的小表情" without putting it in quotes.
    """
    if not (previous_chapter or "").strip():
        return []
    reference = _normalise(previous_chapter)
    paragraphs = [p for p in re.split(r"\n\s*\n", scene_text or "") if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [p for p in (scene_text or "").splitlines() if p.strip()]

    misses: list[RecallMiss] = []
    seen: set[tuple[str, str]] = set()

    def _add(text: str, kind: str) -> None:
        text = (text or "").strip()
        key = (kind, _normalise(text))
        if not key[1] or key in seen:
            return
        if key[1] in reference:
            return
        seen.add(key)
        misses.append(RecallMiss(text=text, kind=kind))

    for paragraph in paragraphs:
        if not _RECALL_MARKER.search(paragraph):
            continue
        for quote in _QUOTED.findall(paragraph):
            if len(_normalise(quote)) >= 4:
                _add(quote, "quoted")
        for expression in _expression_phrases(paragraph):
            _add(expression, "expression")
    return misses


# ---------------------------------------------------------------- main entry

def analyze_scene_repetition(
    scene_text: str,
    *,
    previous_chapter: str = "",
    chapter_so_far: str = "",
    must_not_include: list[str] | None = None,
    config: RepetitionConfig | None = None,
    story_time_gap_days: int | None = None,
    beat: str = "",
    appearances: list[str] | None = None,
) -> RepetitionReport:
    """Run all checks on a freshly generated scene and decide whether it is over threshold.

    ``beat`` (T17) lets quotes the scene plan explicitly requires be exempted from the
    dialogue/span checks — but only when the same words already exist verbatim in the previous
    chapter or in the already-written part of this chapter. ``appearances`` (T19) are the
    appearance cards of the characters present in this scene.
    """
    cfg = config or RepetitionConfig()
    report = RepetitionReport()
    if not cfg.enabled or not (scene_text or "").strip():
        return report

    report.story_time_gap_days = story_time_gap_days
    report.time_hits = find_time_mismatches(scene_text, story_time_gap_days)
    if report.time_hits:
        report.reasons.append(
            f'与上一章相隔 {story_time_gap_days} 天，疑似相对时间错位：' + '、'.join(report.time_hits)
        )

    report.required_quotes = extract_required_quotes(beat, previous_chapter, chapter_so_far)
    report.citable_quotes = extract_citable_quotes(previous_chapter)
    checked_text = _mask_quotes(scene_text, report.required_quotes)

    cov_prev, spans_prev = find_reused_spans(
        checked_text, previous_chapter, cfg.ngram, "previous_chapter",
        denominator_text=scene_text,
    )
    cov_here, spans_here = find_reused_spans(
        checked_text, chapter_so_far, cfg.ngram, "chapter_so_far",
        denominator_text=scene_text,
    )
    report.coverage = round(max(cov_prev, cov_here), 4)
    all_spans = sorted(spans_prev + spans_here, key=lambda sp: sp.length, reverse=True)
    report.spans = all_spans

    report.dialogues = (
        find_reused_dialogues(checked_text, previous_chapter, cfg.min_dialogue_len, "previous_chapter")
        + find_reused_dialogues(checked_text, chapter_so_far, cfg.min_dialogue_len, "chapter_so_far")
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

    if cfg.appearance_check:
        report.appearance_hits = count_appearance_tags(
            scene_text,
            chapter_so_far,
            appearances,
            max_count=cfg.appearance_max_count,
        )
        if report.appearance_hits:
            report.reasons.append(
                "外貌标签重复："
                + "、".join(f"{h.phrase}×{h.count}" for h in report.appearance_hits)
            )

    report.forbidden_hits = [
        h for h in forbidden_overlap(scene_text, must_not_include or [])
        if h.overlap >= cfg.forbidden_overlap
    ]
    if report.forbidden_hits:
        report.reasons.append("写入了本场景禁止出现的素材：" + "、".join(h.item for h in report.forbidden_hits))

    report.recall_misses = find_recall_mismatches(scene_text, previous_chapter)
    if report.recall_misses:
        report.reasons.append(
            "回忆引用无法在上一章原文中找到：" + "、".join(f"「{m.text}」" for m in report.recall_misses)
        )

    if cfg.seam_check and (chapter_so_far or "").strip():
        report.seam_spans = find_scene_seam(
            checked_text,
            chapter_so_far,
            head_chars=cfg.seam_head_chars,
            tail_chars=cfg.seam_tail_chars,
            n=cfg.seam_ngram,
        )
        if report.seam_spans:
            report.reasons.append(
                f"本场景开头与上一场景结尾有 {len(report.seam_spans)} 处 "
                f"≥{cfg.seam_ngram} 字的重复片段："
                + "、".join(f"「{sp.text}」" for sp in report.seam_spans[:3])
            )

    report.triggered = bool(report.reasons)
    return report
