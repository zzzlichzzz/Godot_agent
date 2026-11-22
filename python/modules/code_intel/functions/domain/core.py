"""modules/code_intel/functions/domain/core.py - список и тела функций .gd (R-11).

Перенос `godot_tools/gd_functions.py` эталона: распознавание одно (регулярное
выражение заголовка), тело — строки с отступом глубже заголовка, пустые строки
внутри тела его не обрывают, хвостовые обрезаются, прилегающие сверху
`#`-комментарии и `@`-аннотации входят в сниппет. Ни `os`, ни `pathlib`, ни
диска: на вход текст, на выходе данные.

Единый парсер `.gd` (`formats/gdscript.py`) ещё не перенесён, поэтому логика
живёт здесь; переезд — отдельный рефакторинг с двойным прогоном корпуса
(решение записано в `docs/porting/code_intel.functions.md`).
"""

import re

from python.kernel.text import split_lines

#: Заголовок объявления: `func имя(`; отступ и `static` допускаются.
FUNC_RE = re.compile(r"^(\s*)(?:static\s+)?func\s+([A-Za-z_]\w*)\s*[(]")


def indent_width(line):
    """Ширина отступа: табуляция считается одним символом (так делает эталон)."""
    return len(line) - len(line.lstrip(" \t"))


def list_names(text):
    """Имена объявленных функций в порядке объявления (дубли повторяются)."""
    names = []
    for line in split_lines(text or ""):
        match = FUNC_RE.match(line)
        if match is not None:
            names.append(match.group(2))
    return names


def extract(text, names):
    """Тела запрошенных функций: `(found, missing)`.

    `found` — в порядке запроса: `{name, snippet, start_line, end_line}` с
    нумерацией строк с 1. `missing` — запрошенные имена, которых нет в файле.
    При дубле имени берётся первое объявление (так эталон).
    """
    lines = split_lines(text or "")
    spans = _spans(lines)
    found, missing = [], []
    for name in _names(names):
        span = spans.get(name)
        if span is None:
            missing.append(name)
            continue
        start, end = span
        found.append({"name": name,
                      "snippet": "\n".join(lines[start:end + 1]),
                      "start_line": start + 1,
                      "end_line": end + 1})
    return found, missing


def _names(names):
    return [str(name) for name in (names or ())]


def _spans(lines):
    """Границы тел по первому объявлению: `{name: (start, end)}`, индексы с 0."""
    spans = {}
    index, total = 0, len(lines)
    while index < total:
        match = FUNC_RE.match(lines[index])
        if match is None:
            index += 1
            continue
        head = indent_width(lines[index])
        name = match.group(2)
        body, last_body = index + 1, index
        while body < total:
            stripped = lines[body].strip()
            if stripped and indent_width(lines[body]) <= head:
                break
            if stripped:
                last_body = body
            body += 1
        start = index
        while start > 0:
            above = lines[start - 1].strip()
            if above.startswith("#") or above.startswith("@"):
                start -= 1
                continue
            break
        if name not in spans:
            spans[name] = (start, last_body)
        index = body if body > index else index + 1
    return spans

