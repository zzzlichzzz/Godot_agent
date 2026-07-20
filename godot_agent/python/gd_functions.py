# -*- coding: utf-8 -*-
"""v48: точечное чтение функций из GDScript-файлов (action=read_function).

Вместо полного файла модель может запросить только нужные функции —
это экономит токены и лимит файлов за запрос. Разбор индентационный:
тело функции — все строки с отступом глубже заголовка (пустые строки
внутри тела не обрывают его). В сниппет входят прилегающие сверху
комментарии и аннотации (@rpc и т.п.), чтобы блок был самодостаточен
и годился как дословный search для patch_file.
"""
import re

_FUNC_RE = re.compile(r"^(\s*)(?:static\s+)?func\s+([A-Za-z_]\w*)\s*[(]")


def _indent_width(line):
    return len(line) - len(line.lstrip(" \t"))


def list_functions(text):
    """Имена всех функций файла в порядке объявления."""
    names = []
    for line in (text or "").splitlines():
        m = _FUNC_RE.match(line)
        if m:
            names.append(m.group(2))
    return names


def extract_functions(text, names):
    """Возвращает (found, missing):
    found — список словарей {name, snippet, start_line, end_line} (нумерация с 1),
    missing — имена запрошенных функций, которых в файле нет."""
    lines = (text or "").splitlines()
    spans = {}   # name -> (start_idx, end_idx) включительно
    i = 0
    while i < len(lines):
        m = _FUNC_RE.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(2)
        head_indent = _indent_width(lines[i])
        # Тело: всё, что глубже отступа заголовка; пустые строки внутри — часть тела,
        # но хвостовые пустые строки после последней содержательной обрезаются.
        j = i + 1
        last_body = i
        while j < len(lines):
            stripped = lines[j].strip()
            if stripped and _indent_width(lines[j]) <= head_indent:
                break
            if stripped:
                last_body = j
            j += 1
        # Прилегающие сверху комментарии и аннотации входят в сниппет.
        start = i
    
        k = i - 1
        while k >= 0:
            s = lines[k].strip()
            if s.startswith("#") or s.startswith("@"):
                start = k
                k -= 1
            else:
                break
        if name not in spans:  # при дублях имён берём первое объявление
            spans[name] = (start, last_body)
        i = j if j > i else i + 1
    found, missing = [], []
    for want in names:
        if want in spans:
            s, e = spans[want]
            found.append({
                "name": want,
                "snippet": "\n".join(lines[s:e + 1]),
                "start_line": s + 1,
                "end_line": e + 1,
            })
        else:
            missing.append(want)
    return found, missing
