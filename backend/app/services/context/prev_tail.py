"""T16: configurable previous-chapter ending excerpt.

The assembler injects only the tail of the previous chapter (facts come from the
synopsis). Two strategies:

* ``tail`` (default, unchanged): the last ``YOUTHINK_PREV_TAIL_CHARS`` characters.
* ``dialogue_action``: within the same window, drop long scenery-only sentences,
  keeping speech and actions — less raw prose for the model to copy while the
  continuity hooks (what was said / done) survive.

Env vars (invalid values fall back to the defaults and are logged):

* ``YOUTHINK_PREV_TAIL_CHARS``    default 1500, clamped to 200–4000.
* ``YOUTHINK_PREV_TAIL_STRATEGY`` ``tail`` (default) or ``dialogue_action``.

Pure helpers, no DB / no LLM.
"""

from __future__ import annotations

import logging
import os
import re

DEFAULT_MAX_CHARS = 1500
MIN_MAX_CHARS = 200
MAX_MAX_CHARS = 4000
DEFAULT_STRATEGY = "tail"
STRATEGIES = ("tail", "dialogue_action")

_logger = logging.getLogger(__name__)

_SENTENCE_END = re.compile(r"(?<=[。！？!?；;\n])")
_DIALOGUE_RE = re.compile(r"[“「『][^”」』]*[”」』]")
_SCENERY_HINTS = (
    "天空", "云", "风", "雨", "雪", "阳光", "夕阳", "暮色", "夜色", "街道", "树",
    "花", "草", "灯", "影子", "远处", "窗外", "空气", "气味", "城市", "校园", "楼",
    "光", "海", "河", "山", "月光",
)
_ACTION_HINTS = (
    "走", "跑", "站", "坐", "转身", "推", "拉", "拿", "放", "递", "接", "抬", "低",
    "点", "摇", "握", "松", "关门", "开门", "起身", "停下", "看向", "回头", "伸手",
    "掏出", "收起", "靠近", "退", "停",
)


def prev_tail_max_chars() -> int:
    raw = os.environ.get("YOUTHINK_PREV_TAIL_CHARS", "").strip()
    if not raw:
        return DEFAULT_MAX_CHARS
    try:
        value = int(raw)
    except ValueError:
        _logger.warning(
            "invalid YOUTHINK_PREV_TAIL_CHARS=%r; using %d", raw, DEFAULT_MAX_CHARS
        )
        return DEFAULT_MAX_CHARS
    clamped = max(MIN_MAX_CHARS, min(MAX_MAX_CHARS, value))
    if clamped != value:
        _logger.warning(
            "YOUTHINK_PREV_TAIL_CHARS=%d out of range; clamped to %d", value, clamped
        )
    return clamped


def prev_tail_strategy() -> str:
    raw = os.environ.get("YOUTHINK_PREV_TAIL_STRATEGY", "").strip().lower()
    if not raw or raw == DEFAULT_STRATEGY:
        return DEFAULT_STRATEGY
    if raw in STRATEGIES:
        return raw
    _logger.warning(
        "invalid YOUTHINK_PREV_TAIL_STRATEGY=%r; using %s", raw, DEFAULT_STRATEGY
    )
    return DEFAULT_STRATEGY


def _plain_tail(text: str, max_chars: int) -> str:
    if len(text) > max_chars:
        return "……\n" + text[-max_chars:]
    return text


def _is_large_scenery(sentence: str) -> bool:
    """A long sentence with scenery words but neither speech nor action."""
    compact = re.sub(r"\s+", "", sentence)
    if len(compact) < 20:
        return False
    if _DIALOGUE_RE.search(sentence):
        return False
    if any(word in sentence for word in _ACTION_HINTS):
        return False
    return any(word in sentence for word in _SCENERY_HINTS)


def _dialogue_action_tail(text: str, max_chars: int) -> str:
    truncated = len(text) > max_chars
    window = text[-max_chars:] if truncated else text
    sentences = [s for s in _SENTENCE_END.split(window) if s]
    kept: list[str] = []
    dropped = False
    for index, sentence in enumerate(sentences):
        # The very last sentence is the chapter hook; keep it even if it is scenery.
        if index < len(sentences) - 1 and _is_large_scenery(sentence):
            dropped = True
            continue
        kept.append(sentence)
    out = "".join(kept).strip()
    if len(out) > max_chars:
        out = out[-max_chars:]
    if not out:
        # Everything in the window was scenery: never inject an empty excerpt.
        return _plain_tail(text, max_chars)
    if truncated or dropped:
        out = "……\n" + out
    return out


def select_previous_tail(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    strategy: str = DEFAULT_STRATEGY,
) -> str:
    """Return the excerpt to inject for the previous chapter."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    limit = max(MIN_MAX_CHARS, min(MAX_MAX_CHARS, int(max_chars)))
    if strategy == "dialogue_action":
        return _dialogue_action_tail(cleaned, limit)
    return _plain_tail(cleaned, limit)
