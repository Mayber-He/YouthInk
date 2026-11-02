"""Conservative calendar gaps for chapter time anchors; never infer a year."""

import re
from datetime import date

_NUMBER = r'[0-9一二三四五六七八九十〇零]+'
_DATE = re.compile(
    rf'(?:(?P<year>[0-9〇零一二三四五六七八九]{{4}})年)?(?P<month>{_NUMBER})月(?P<day>{_NUMBER})[日号]'
    r'|(?P<ny>\d{4})[-/](?P<nm>\d{1,2})[-/](?P<nd>\d{1,2})'
)


def _number(value: str) -> int:
    if value.isascii() and value.isdigit():
        return int(value)
    digits = '零一二三四五六七八九'
    value = value.replace('〇', '零')
    if '十' in value:
        tens, units = value.split('十')
        return (digits.index(tens) if tens else 1) * 10 + (digits.index(units) if units else 0)
    return digits.index(value)


def _parse(value: str) -> tuple[int | None, int, int] | None:
    matches = list(_DATE.finditer(value or ''))
    if len(matches) != 1:
        return None
    match = matches[0]
    # Never silently discard an explicit but unsupported year/era prefix.
    if value[:match.start()].rstrip().endswith('年'):
        return None
    try:
        year = match['year'] or match['ny']
        if year and not year.isascii():
            year = ''.join(str('零一二三四五六七八九'.index(ch)) for ch in year.replace('〇', '零'))
        month = _number(match['month'] or match['nm'])
        day = _number(match['day'] or match['nd'])
        date(int(year) if year else 2000, month, day)
        return (int(year) if year else None, month, day)
    except ValueError:
        return None


def story_time_gap(previous: str, current: str) -> int | None:
    before, after = _parse(previous), _parse(current)
    if before is None or after is None:
        return None
    py, pm, pd = before
    cy, cm, cd = after
    if py is not None and cy is not None:
        gap = (date(cy, cm, cd) - date(py, pm, pd)).days
        return gap if gap >= 0 else None
    if py is not None or cy is not None or (cm, cd) < (pm, pd):
        return None
    # Without years only report gaps invariant across leap/non-leap calendars.
    try:
        gaps = {(date(y, cm, cd) - date(y, pm, pd)).days for y in (2000, 2001)}
    except ValueError:
        return None
    return gaps.pop() if len(gaps) == 1 else None


def time_anchor(previous: str | None, current: str) -> tuple[str, list[str]]:
    lines = [f'本章发生时间：{current or "未指定"}']
    warnings: list[str] = []
    if previous is not None:
        lines.insert(0, f'上一章发生时间：{previous or "未指定"}')
        gap = story_time_gap(previous, current)
        lines.append(f'相隔天数：{gap} 天' if gap is not None else '相隔天数：无法确定。')
        unresolved = gap is None
    else:
        unresolved = _parse(current) is None
    if unresolved:
        warning = '时间锚点无法确定：请补充或核对章节的 story_time（明确日期；跨年或闰年有歧义时补充年份），不得猜补时间。'
        warnings.append(warning)
        lines.append(warning)
    lines.append('禁止用“昨晚/昨天/今早”指称上一章的事；须按本章与上一章的实际日期改用“前几天/上周/那天晚上”等相对说法，不要写具体公历日期，不得把章节相邻当成日期相邻。')
    return '\n'.join(lines), warnings
