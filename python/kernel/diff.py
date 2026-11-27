"""kernel/diff.py - построение diff для предпросмотра (R-12).

Дифф — не украшение отчёта: по нему пользователь подтверждает план. Поэтому он
строится из ТОГО ЖЕ текста, по которому считались смещения шагов, и не зависит
от времени/путей машины.
"""

import difflib


def split_lines(text):
    """Строки без переводов строк: сравнение не зависит от CRLF."""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def unified(path, old_text, new_text, context=3):
    """Unified diff с заголовками `a/…` `b/…`; пустой текст — правки нет."""
    old_lines = split_lines(old_text)
    new_lines = split_lines(new_text)
    if old_lines == new_lines:
        return ""
    head = "a/%s" % path
    tail = "b/%s" % path
    body = difflib.unified_diff(old_lines, new_lines, fromfile=head,
                                tofile=tail, n=context, lineterm="")
    return "\n".join(body)


def apply_edits(text, edits):
    """Применить правки к тексту: проверка смещений и порядка (для диффа)."""
    out, cursor = [], 0
    for edit in sorted(edits, key=lambda item: (item["start"], item["end"])):
        start, end = int(edit["start"]), int(edit["end"])
        if start < cursor or end < start or end > len(text):
            raise ValueError("смещения пересекаются или выходят за текст")
        out.append(text[cursor:start])
        out.append(str(edit["replacement"]))
        cursor = end
    out.append(text[cursor:])
    return "".join(out)
