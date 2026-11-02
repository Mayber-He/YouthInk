"""T22: narration aliases for characters whose real name the POV does not know.

A scene beat may carry one meta line::

    叙述称呼：裴南栀→白衬衫学姐

When present, the writing prompt shows the character as the alias and forbids
the real name in narration; a real-name occurrence in the generated prose is a
repetition-check reason and the rewrite must replace it with the alias.

The module is pure (no DB/LLM) so planning, prompt assembly and the repetition
guard can share the same parsing.
"""

from __future__ import annotations

import re

_ALIAS_LINE_RE = re.compile(r"^\s*叙述称呼\s*[：:]\s*(.+?)\s*$")
_PAIR_RE = re.compile(r"([^→\s；;，,、]+)\s*→\s*([^；;，,、]+)")


def parse_narration_aliases(beat: str) -> dict[str, str]:
    """Return ``{real_name: alias}`` declared by ``叙述称呼：`` lines in a beat."""
    aliases: dict[str, str] = {}
    for line in (beat or "").splitlines():
        match = _ALIAS_LINE_RE.match(line)
        if not match:
            continue
        for real, alias in _PAIR_RE.findall(match.group(1)):
            real, alias = real.strip(), alias.strip()
            if real and alias and real != alias:
                aliases[real] = alias
    return aliases


def collect_narration_aliases(beats: list[str]) -> dict[str, str]:
    """Merge alias mappings from several scenes (later scenes win on conflicts)."""
    merged: dict[str, str] = {}
    for beat in beats:
        merged.update(parse_narration_aliases(beat))
    return merged


def strip_narration_lines(text: str) -> str:
    """Remove the meta ``叙述称呼：`` lines so they never reach the prose model."""
    return "\n".join(
        line for line in (text or "").splitlines() if not _ALIAS_LINE_RE.match(line)
    )


def apply_aliases(text: str, aliases: dict[str, str]) -> str:
    """Replace every real name with its alias (longest name first)."""
    result = text or ""
    for real in sorted(aliases, key=len, reverse=True):
        result = result.replace(real, aliases[real])
    return result


def alias_rule(aliases: dict[str, str]) -> str:
    """One instruction line appended to the writing task."""
    if not aliases:
        return ""
    pairs = "；".join(f"「{real}」→「{alias}」" for real, alias in aliases.items())
    reals = "、".join(f"「{real}」" for real in aliases)
    return (
        f"【叙述称呼】{pairs}。正文叙述不得出现本名 {reals}，统一用别名指代；"
        "本场不得借叙述、对话或他人称呼提前泄露本名。"
    )
