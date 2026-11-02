"""T15: previous-chapter character voice excerpts for scene planning.

Only **spoken lines** — text inside Chinese quotation marks — are eligible. Narration
(however distinctive) is deliberately excluded: the planning rules must cite lines that
were actually said, otherwise prose ends up "remembering" chat that never happened.

The excerpt is a deterministic heuristic, not a model call:

* short colloquial lines carrying sentence-final particles (呀/嘛/呗/…),
* second/first person address,
* one copy per normalized line (punctuation-insensitive dedupe).

No DB, no LLM; callers pass the previous chapter's raw text.
"""

from __future__ import annotations

import re

_SPEECH_RE = re.compile(r"[“「『]([^”」』\n]{1,80})[”」』]")
_STRIP_RE = re.compile(r"[\s，。！？!?；;、,…·—．.「」『』“”\"'：:()（）]+")

# 句尾语气词越多，越像个人口癖；用于排序，而不是硬过滤。
QUIRK_MARKERS: tuple[str, ...] = (
    "呀", "嘛", "呗", "啦", "呢", "吧", "啊", "哦", "咯", "诶", "嘿", "哈", "唔", "唉", "哟",
)

# 纯应答语没有辨识度，不作为“标志性句式”摘录（按去标点后的文本判断）。
_GENERIC = {
    "嗯", "哦", "好", "行", "是", "对", "不", "没有", "可以", "行吧", "好吧",
    "没事", "知道了", "谢谢", "再见",
}

DEFAULT_LIMIT = 5
MIN_CHARS = 3
MAX_CHARS = 40


def _normalize(line: str) -> str:
    return _STRIP_RE.sub("", line)


def _score(line: str) -> int:
    return sum(2 for marker in QUIRK_MARKERS if marker in line) + int("你" in line) + int("我" in line)


def extract_speech_lines(text: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    """Return at most ``limit`` representative spoken lines, in order of appearance."""
    candidates: list[tuple[int, int, int, str]] = []
    seen: set[str] = set()
    for order, match in enumerate(_SPEECH_RE.finditer(text or "")):
        line = match.group(1).strip()
        norm = _normalize(line)
        if not (MIN_CHARS <= len(norm) <= MAX_CHARS):
            continue
        if norm in _GENERIC or norm in seen:
            continue
        seen.add(norm)
        candidates.append((-_score(line), len(norm), order, line))
    chosen = sorted(candidates)[: max(0, limit)]
    chosen.sort(key=lambda item: item[2])
    return [item[3] for item in chosen]


def previous_voice_block(previous_text: str, limit: int = DEFAULT_LIMIT) -> str:
    """Context block for scene planning; degrades explicitly when nothing is available."""
    if not (previous_text or "").strip():
        return "上一章无原文（本章为开篇）：不得引用或虚构“上一章”的台词与口癖。"
    lines = extract_speech_lines(previous_text, limit=limit)
    if not lines:
        return (
            "上一章原文中未提取到可用发言：不得凭空引用或自造上一章台词；"
            "节拍中不要要求正文“沿用前文说法”。"
        )
    body = "\n".join(f"- “{line}”" for line in lines)
    return (
        f"上一章中人物的标志性口癖或句式（仅摘自上一章原文发言，共 {len(lines)} 条）：\n{body}"
    )
