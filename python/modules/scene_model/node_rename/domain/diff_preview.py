"""Native structured diff, project_tools.py:1854-1917; not kernel.unified."""
from difflib import SequenceMatcher

from ..settings import DIFF_CONTEXT, DIFF_MAX_LINES


def _lines(text):
    lines = (text or '').replace('\r\n', '\n').split('\n')
    if len(lines) > 1 and lines[-1] == '':
        lines.pop()
    return lines


def preview(old, new):
    before, after = _lines(old), _lines(new)
    if before == after:
        return None
    out, added, removed = [], 0, 0
    for group in SequenceMatcher(None, before, after).get_grouped_opcodes(DIFF_CONTEXT):
        first, last = group[0], group[-1]
        a, alen = first[1] + 1, last[2] - first[1]
        b, blen = first[3] + 1, last[4] - first[3]
        out.append(['@', a, b, '@@ -%d,%d +%d,%d @@' % (a, alen, b, blen)])
        for tag, a1, a2, b1, b2 in group:
            if tag == 'equal':
                for k in range(a1, a2):
                    out.append([' ', k + 1, b1 + k - a1 + 1, before[k]])
                continue
            if tag in ('replace', 'delete'):
                for k in range(a1, a2):
                    out.append(['-', k + 1, None, before[k]])
                    removed += 1
            if tag in ('replace', 'insert'):
                for k in range(b1, b2):
                    out.append(['+', None, k + 1, after[k]])
                    added += 1
    return {'lines': out[:DIFF_MAX_LINES], 'added': added, 'removed': removed,
            'truncated': len(out) > DIFF_MAX_LINES}
