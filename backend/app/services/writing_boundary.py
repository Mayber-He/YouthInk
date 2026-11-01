"""Check a writing plan against actual preceding prose before streaming a draft."""
import logging
import os
import re

from pydantic import BaseModel, Field

from app.core.exceptions import AppError
from app.db.repositories.settings_repo import SettingsRepository
from app.services.llm.client import complete_chat
from app.services.llm.json_parser import parse_and_validate_json

logger = logging.getLogger(__name__)


class EvidencedEvent(BaseModel):
    statement: str = Field(min_length=1)
    evidence_quote: str = Field(min_length=1)


# 模型复述原句时极少逐字节一致：标点、引号样式、空白常漂移，但语义是对的。
# 我们要拦的是“编造了前文没有的内容”，而不是格式差异。因此比对前先归一化：
# 去掉所有空白，并把常见中英标点/引号变体折叠成统一形式。归一化后仍找不到才判幻觉。
_PUNCT_FOLD = {
    ord("“"): '"', ord("”"): '"', ord("‘"): "'", ord("’"): "'",
    ord("「"): '"', ord("」"): '"', ord("『"): '"', ord("』"): '"',
    ord("，"): ",", ord("。"): ".", ord("！"): "!", ord("？"): "?",
    ord("；"): ";", ord("："): ":", ord("、"): ",",
    ord("（"): "(", ord("）"): ")", ord("—"): "-", ord("…"): ".",
}


def _normalize_for_match(text: str) -> str:
    folded = text.translate(_PUNCT_FOLD)
    return re.sub(r"\s+", "", folded)


class WritingBoundary(BaseModel):
    # 不限制条数：长章节的已确立事实/重复事件可能很多，截断会让合法响应被判非法。
    # 这些只是生成前的参考信息，列表长短不影响后续正文生成。
    established: list[EvidencedEvent] = Field(default_factory=list)
    repeated_events: list[EvidencedEvent] = Field(default_factory=list)
    next_step: str = Field(min_length=1)
    # T6：由检查模型直接给出“已写过、不要再写”的素材短语（每条 ≤20 字的名词性短语）。
    # 缺省为空：旧输出 / 模型没给时回退到从 repeated_events.statement 里保守地抽取。
    avoid: list[str] = Field(default_factory=list)


# --- T6: 注入正文请求的精简格式 ---------------------------------------------------------------
# 模型返回的完整结构（含大量 evidence_quote 原文）只用于**校验幻觉**，校验通过后不再整段注入。
# 写正文的模型只需要两样东西：本场景从哪里接 + 已写过、不要再写的素材清单（短语）。

BOUNDARY_HEADER = "【生成前章节衔接检查】"
MAX_REPEAT_PHRASES = 8
MAX_PHRASE_CHARS = 24
MAX_CONTINUE_CHARS = 80

# 成对的引号/括号：截断后必须保持配对，否则丢弃悬空的开括号及其后内容。
_PAIRS = {"“": "”", "「": "」", "『": "』", "（": "）", "(": ")", "《": "》", "‘": "’"}
_OPENERS = set(_PAIRS)
_CLOSERS = set(_PAIRS.values())
_QUOTED = re.compile(r"[“「『]([^”」』]{3,}?)[”」』]")
# 句首的元语言：“计划开头再次安排 / 计划中的 / 本次计划重演 / 计划场景再切回 …”，对写作无用。
_PLAN_PREFIX = re.compile(
    r"^(?:本次|按|原)?计划(?:中的|中|里的|里|开头|场景|若|仍|还)?"
    r"(?:再次|重新|又|再|仍|还)?(?:安排|重演|铺陈|罗列|补充|写|描写|切回|回到|交代|解释|介绍)?"
    r"(?:的)?"
)
# 句尾的评语：“…已发生，应跳过 / ，已写已经发生；这些消息不应再… / 属于重复已交代背景”。
_TAIL_MARKERS = (
    "已写已", "已经发生", "已发生", "已经写过", "已写过", "已完整交代", "已写完", "已交代",
    "不宜再", "不应再", "不应重新", "不必再", "不必当作", "应跳过", "属于重复", "会重演", "是重演",
)
_CLAUSE_SPLIT = re.compile(r"[，,；;。！？!?：:]")


def _balanced(text: str) -> str:
    """Drop an unclosed opening quote/bracket and everything after it; strip stray closers."""
    stack: list[tuple[str, int]] = []
    drop_from: int | None = None
    for i, ch in enumerate(text):
        if ch in _OPENERS:
            stack.append((ch, i))
        elif ch in _CLOSERS:
            if stack and _PAIRS[stack[-1][0]] == ch:
                stack.pop()
            else:
                # closer with no opener (cut happened before it): ignore the char
                continue
    if stack:
        drop_from = stack[0][1]
    out = text[:drop_from] if drop_from is not None else text
    return out.strip("，,；;。！？!?：:、 ")


def _cap_on_boundary(text: str, max_chars: int) -> str:
    """Cap to ``max_chars`` at a clause boundary; mark a forced cut with '…'.

    Never leaves an unclosed quote/bracket. If no separator exists in the second half of the
    allowance the text is cut at ``max_chars`` and '…' is appended so the reader can tell it was
    shortened rather than reading a half word as if it were complete.
    """
    if len(text) <= max_chars:
        return _balanced(text)
    cut = text[:max_chars]
    sep = max(cut.rfind(c) for c in "、，,；;")
    if sep >= max_chars // 2:
        return _balanced(cut[:sep])
    return _balanced(cut) + "…"


# 含这些信号的句子表达的是“否定 / 矛盾 / 条件 / 建议”，压成短语会丢掉否定从而**反向误导**
# （如“计划要写A，但前文已写B，不能写A”若只剩“写A”，模型反而会去写A）。这类条目不注入。
_NEGATING_SIGNALS = (
    "但", "却", "不能", "不得", "不可", "切勿", "矛盾", "冲突", "如果", "若是", "倘若", "建议",
    "改成", "改为", "而不是", "并非", "不是",
)


def is_safe_to_phrase(statement: str) -> bool:
    """False when shortening would risk inverting the meaning (see ``_NEGATING_SIGNALS``)."""
    s = re.sub(r"\s+", "", statement or "")
    # “不宜/不应/不必 再…”是在**否定重写**，恰是我们要的“不要再写”语义，不算反向信号。
    s = re.sub(r"不(?:宜|应|必)(?:再|重新|原样|从头)?", "", s)
    return not any(sig in s for sig in _NEGATING_SIGNALS)


def to_phrase(statement: str, max_chars: int = MAX_PHRASE_CHARS) -> str:
    """Compress one full-sentence ``statement`` into a short phrase (deterministic, no model).

    Keeps the sentence's own wording: strip the planning boilerplate ("计划…重演") and the
    trailing verdict ("…已发生，应跳过"), then keep the first clause(s) up to ``max_chars``.
    It deliberately does NOT pull out quoted fragments — a quote is usually an embedded line of
    dialogue, not the repeated event itself, and extracting it loses what actually repeated.
    Never returns an empty string for a non-empty input (falls back to the raw first clause).
    """
    raw = re.sub(r"\s+", "", statement or "")
    if not raw:
        return ""
    # Punctuation INSIDE quotes ("哪所啊？" / “本地，走读。”) must not act as a clause boundary,
    # otherwise the phrase is cut mid-quotation. Mask it, split, then restore.
    raw = _mask_quoted_punct(raw)
    s = _PLAN_PREFIX.sub("", raw, count=1)
    cut_at = min((s.find(m) for m in _TAIL_MARKERS if s.find(m) > 0), default=-1)
    if cut_at > 0:
        s = s[:cut_at]
    s = s.strip("，,；;。！？!?：:、 ")
    if not s:  # everything was boilerplate: fall back to the original first clause
        s = _CLAUSE_SPLIT.split(raw, maxsplit=1)[0].strip("，,；;。！？!?：:、 ")
    if not s:
        return ""
    # keep up to the first two short clauses so an enumeration is not chopped after one item
    parts = [p for p in _CLAUSE_SPLIT.split(s) if p]
    base = parts[0]
    if len(base) < 8 and len(parts) > 1:
        base = base + "，" + parts[1]
    return _unmask(_cap_on_boundary(base, max_chars))


_MASK = {"，": "\x01", ",": "\x02", "；": "\x03", ";": "\x04", "。": "\x05", "！": "\x06", "？": "\x07",
         "!": "\x0b", "?": "\x0c", "：": "\x0e", ":": "\x0f"}
_UNMASK = {v: k for k, v in _MASK.items()}


def _mask_quoted_punct(text: str) -> str:
    """Replace clause punctuation that sits inside a quote/bracket pair with control placeholders."""
    out: list[str] = []
    depth = 0
    for ch in text:
        if ch in _OPENERS:
            depth += 1
        elif ch in _CLOSERS and depth > 0:
            depth -= 1
        out.append(_MASK.get(ch, ch) if depth > 0 and ch in _MASK else ch)
    return "".join(out)


def _unmask(text: str) -> str:
    return "".join(_UNMASK.get(ch, ch) for ch in text)


# 评语尾巴 / 元语言残留：出现在回退抽取的短语里说明抽到的是“判断”而不是“素材”。
_COMMENTARY = (
    "前章", "上一章", "已用过", "已经用过", "已经在", "已写", "已经写", "已发生", "已经发生",
    "不宜", "不应", "不必", "应跳过", "重演", "重复", "计划", "本章", "要写", "已经问过", "已问过",
)


def is_usable_phrase(p: str) -> bool:
    """Quality gate for a rule-extracted phrase; anything dubious is rejected (not injected)."""
    if not p or len(p) < 4:
        return False
    if p.endswith("…") or "…" in p[:-1]:
        return False  # truncated: likely cut inside a commentary sentence
    if any(c in p for c in _COMMENTARY):
        return False
    # an unclosed quote means a clause split landed inside a quotation
    return sum(c in _OPENERS for c in p) == sum(c in _CLOSERS for c in p)


def _clean_model_phrase(raw: str) -> str:
    """Normalize a phrase the model gave us in ``avoid``: trim, cap, keep it quote-safe."""
    p = re.sub(r"\s+", "", raw or "").strip("，,；;。！？!?：:、 ")
    return _cap_on_boundary(p, MAX_PHRASE_CHARS) if len(p) >= 2 else ""


def _first_sentence(text: str, max_chars: int) -> str:
    """First sentence of ``next_step`` — where to pick up — capped, quote-safe.

    The sentence end must be OUTSIDE quotes: ``从已写正文结尾“嗯……不太想说话。”之后续写`` holds a
    full stop inside a quotation and must not be cut there. Anything after the first sentence
    ("下一段可写…") is a concrete script and is intentionally not injected.
    """
    t = re.sub(r"\s+", "", text or "")
    depth = 0
    end = len(t)
    for i, ch in enumerate(t):
        if ch in _OPENERS:
            depth += 1
        elif ch in _CLOSERS and depth > 0:
            depth -= 1
        elif ch in "。！？!?" and depth == 0:
            end = i
            break
    sentence = t[:end]
    return _cap_on_boundary(sentence, max_chars)


def format_boundary_for_prompt(boundary: "WritingBoundary") -> str:
    """Lean text injected into the prose request: where to pick up + what NOT to rewrite.

    * ``next_step`` supplies "本场景从哪里接" (first sentence(s), capped).
    * ``repeated_events`` supply the "已写过不要再写" phrases (deduped, short, capped).
    * ``established`` and every ``evidence_quote`` are NOT injected: the former restates facts
      already present in the chapter-so-far context, the latter is only a hallucination guard.
    """
    continue_from = _first_sentence(boundary.next_step, MAX_CONTINUE_CHARS)
    phrases: list[str] = []
    seen: set[str] = set()

    def _add(p: str) -> None:
        if p and p not in seen and len(phrases) < MAX_REPEAT_PHRASES:
            seen.add(p)
            phrases.append(p)

    # 首选：检查模型直接给出的素材短语（语义由模型负责，不靠正则从评语里抠）。
    for raw in boundary.avoid:
        _add(_clean_model_phrase(raw))

    # 回退：模型没给 avoid（旧输出）。statement 是“判断+理由”的自由评语，规则抽取不可靠，
    # 所以只收通过严格质检的短语，其余宁缺毋滥——绝不注入残片或可能反向误导的片段。
    dropped = 0
    if not phrases:
        for ev in boundary.repeated_events:
            p = ""
            if is_safe_to_phrase(ev.statement):
                p = to_phrase(ev.statement)
            if is_usable_phrase(p):
                _add(p)
            else:
                dropped += 1
    if dropped:
        logger.info("writing boundary: %d repeated_events could not be reduced to a clean phrase", dropped)
    lines = [f"{BOUNDARY_HEADER}从已写内容之后推进，不重演前文。", f"本场景从这里接：{continue_from}"]
    if phrases:
        lines.append("已写过、不要再写：" + "；".join(phrases))
    return "\n".join(lines)


def boundary_slim_enabled() -> bool:
    """Feature switch (default ON). ``YOUTHINK_BOUNDARY_SLIM=0`` restores the full JSON injection."""
    return os.environ.get("YOUTHINK_BOUNDARY_SLIM", "1").strip().lower() not in ("0", "false", "no", "")


def unavailable_notice(reason: str) -> str:
    """User-visible text for 'the continuity check did not run'."""
    return f"衔接检查未生效（{reason}）。本次生成未获得“从哪里接/已写过哪些”的提示，请留意是否重复前文。"


async def check_writing_boundary(
    *, novel_uid: str, chapter_id: int, settings: SettingsRepository,
    history: str, plan: str,
) -> str:
    if not history.strip():
        return ""
    _, base_url, model, api_key = settings.get_credentials_for_task("planning")
    result = await complete_chat(
        base_url=base_url, api_key=api_key, model=model, temperature=0.2,
        system_prompt=(
            "你是小说章节衔接编辑。仅依据已写正文检查本次写作计划，不生成正文。"
            "提取与本次计划有关的已发生事件、人物实际所知、关系、时间地点和物品最终状态；"
            "不要把叙述者知识分给所有角色。发现计划重演前文时，指出已发生的部分，"
            "建议从事件后果继续推进；如果本章目标已写完，建议简短收束，不凑字数、不另造事件。"
            "前文若为草稿，只作衔接参考，不宣称已经定稿。"
        ),
        user_prompt=(
            f"【已写正文】\n{history}\n\n【本次写作计划】\n{plan}\n\n"
            '返回严格 JSON：{"established":[{"statement":"已确立状态",'
            '"evidence_quote":"已写正文的连续原句"}],'
            '"repeated_events":[{"statement":"计划中已经发生、应跳过的事件",'
            '"evidence_quote":"已写正文的连续原句"}],'
            '"next_step":"第一句话只写“从已写正文的哪个落点接着写”，之后再写本次新增推进及结束边界，不改变既定剧情方向",'
            '"avoid":["已写过、不要再写的素材，每条是不超过20字的名词性短语，如“修打印机”“她抱怨冰棍化手”，'
            '不要写评语、理由或建议"]}。'
            "没有证据的项目不要输出，列表可以为空。证据不得拼接、改写或使用省略号。"
        ),
        novel_uid=novel_uid, chapter_id=chapter_id, task_type="writing_boundary",
        timeout_sec=90.0,
    )
    boundary = await parse_and_validate_json(result.content, WritingBoundary)
    history_norm = _normalize_for_match(history)
    for event in boundary.established + boundary.repeated_events:
        if _normalize_for_match(event.evidence_quote) not in history_norm:
            logger.warning(
                "writing boundary evidence not found in history (chapter_id=%s): quote=%r",
                chapter_id, event.evidence_quote,
            )
            raise AppError(
                "BOUNDARY_EVIDENCE_MISMATCH", "章节衔接检查的证据与前文不匹配，请重试；原正文未改动。",
                status_code=502,
            )
    # 证据已校验通过；注入正文请求的只留“从哪里接 + 已写过不要再写的短语”，
    # 不再把 evidence_quote 原文和长长的 established 清单整段塞给写作模型。
    if not boundary_slim_enabled():
        return (
            "【生成前章节衔接检查】以下是基于原文证据的写作边界；与梗概重复时从已发生事件之后推进。\n"
            + boundary.model_dump_json()
        )
    return format_boundary_for_prompt(boundary)
