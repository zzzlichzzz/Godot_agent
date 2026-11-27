"""Preserve the first hit as evidence when context would consume a capped snippet."""
from python.kernel.text import clip_snippet_line

from ..settings import SNIPPET_LINE_MAX


def _span(line, haystack, needle):
    start = haystack.index(needle)
    end = start + len(needle)
    if len(haystack) == len(line):
        return start, end
    # Unicode lower() can expand characters (e.g. İ). Slice ORIGINAL text, not folded offsets.
    cursor = 0
    for i, char in enumerate(line):
        following = cursor + len(char.lower())
        if cursor <= start < following:
            left = i
        if following >= end:
            return left, i + 1
        cursor = following


def _focused(line, label, start, end, limit):
    room = min(SNIPPET_LINE_MAX, limit - len(label))
    width = end - start
    left = max(0, start - max(0, room - width - 2) // 2)
    lead = '…' if left and width < room else ''
    remaining = room - len(lead)
    chunk = line[left:left+remaining]
    if left + len(chunk) < len(line) and end - left != remaining:
        chunk = chunk[:-1] + '…'
    return label + lead + chunk


def snippet(lines, group, query, haystack, needle):
    hit = group[0]
    limit = query.snippet_chars
    low = max(0, hit - query.context_lines)
    high = min(len(lines), group[-1] + query.context_lines + 1)
    if limit is not None:
        start, end = _span(lines[hit], haystack, needle)
        label = f'{hit+1}: '
        before = sum(len(f'{i+1}: {clip_snippet_line(lines[i], SNIPPET_LINE_MAX)}\n') for i in range(low, hit))
        if end > SNIPPET_LINE_MAX or before + len(label) + end >= limit:
            return _focused(lines[hit], label, start, end, limit)
    parts = []
    used = 0
    for number in range(low, high):
        part = f'{number+1}: {clip_snippet_line(lines[number], SNIPPET_LINE_MAX)}'
        if parts:
            part = '\n' + part
        if limit is not None and used + len(part) > limit:
            return (''.join(parts) + part)[:limit - 1] + '…'
        parts.append(part)
        used += len(part)
    return ''.join(parts)
