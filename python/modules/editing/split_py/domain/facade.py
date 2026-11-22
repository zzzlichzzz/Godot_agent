"""Native facade rendering, graph checks and patch warnings; no IO."""
import re


def _warn_patched_attributes(scan, prepared, warnings):
    """Предупреждение о патчах атрибутов переезжающих имён.

    Патч вида `mod.fn = ...` (инъекция сбоя в тестах) после разбиения
    попадает только в фасад: вынесенные функции вызывают собственные
    копии-импорты, и подмена перестаёт действовать. Лечение — патчить
    модуль-владелец: `sys.modules[func.__module__]`.
    """
    stem = prepared["donor"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
    moved = set(prepared.get("moved_names") or [])
    pattern = re.compile(r"(?<![\w.])" + re.escape(stem)
                         + r"\s*\.\s*(\w+)\s*(?:[+\-*/%@|&^]?=)(?!=)")
    names, files = set(), set()
    for item in scan.get("occurrences") or []:
        if item.get("kind") != "patch":
            continue
        files.add(item.get("rel"))
        match = pattern.search(item.get("text") or "")
        if match and match.group(1) in moved:
            names.add(match.group(1))
    if not names:
        return
    warnings.append(
        "атрибут(ы) %s патчат снаружи (%s): после разбиения патч фасада не "
        "долетит до вынесенных функций — переведи патчи на модуль-владелец "
        "(`sys.modules[func.__module__]`) до применения"
        % (", ".join(sorted(names)), ", ".join(sorted(files))))


def _format_import(module, names):
    line = "from %s import %s" % (module, ", ".join(names))
    if len(line) <= 79:
        return line
    return "from %s import (%s)" % (module, ",\n    ".join(names))


def _find_cycle(graph):
    """Первый найденный цикл в графе «модуль -> модули» или None."""
    color, stack = {}, []

    def visit(node):
        color[node] = 1
        stack.append(node)
        for nxt in sorted(graph.get(node) or ()):
            if color.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if color.get(nxt, 0) == 0:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        color[node] = 2
        return None

    for node in sorted(graph):
        if color.get(node, 0) == 0:
            found = visit(node)
            if found:
                return found
    return None


def _join_blocks(blocks):
    cleaned = [str(block).strip("\n") for block in blocks
               if block is not None and str(block).strip()]
    return "\n\n".join(cleaned) + "\n"


def _render_facade(rel, lines, inventory, moved_names, modules, by_name,
                   warnings):
    """Фасад: исходный текст без перенесённых символов + блок реэкспорта.

    Срезаем сегменты перенесённых символов (и старый __all__), блок
    реэкспорта вставляем после последнего import (или докстроки) — остальные
    строки, комментарии и неперемещаемый код остаются как были.
    """
    ranges = [(item["line_start"], item["end_lineno"])
              for item in inventory["symbols"] if item["name"] in moved_names]
    for item in inventory["other"]:
        if item.get("name") == "__all__":
            ranges.append((item["lineno"], item["end_lineno"]))
            warnings.append("старый __all__ заменён генерацией фасада")
    anchor = inventory.get("docstring_end") or 0
    for imp in inventory["imports"]:
        anchor = max(anchor, imp["end_lineno"])
    if anchor == 0:
        firsts = [item["line_start"] for item in inventory["symbols"]] + \
                 [item["lineno"] for item in inventory["other"]]
        anchor = max(0, min(firsts) - 1) if firsts else 0
    block = ["# --- фасад: код разнесён по модулям (split_refactor) ---"]
    reexports = []
    for module in modules:
        names = sorted(name for name in module["names"]
                       if name in moved_names)
        if not names:
            continue
        block.append(_format_import(module["module"], names))
        reexports.append({"module": module["module"], "names": names})
    public_names = sorted(
        {name for name in moved_names if by_name[name]["is_public"]}
        | {item["name"] for item in inventory["symbols"]
           if item["name"] not in moved_names and item["is_public"]})
    if public_names:
        block.append("__all__ = [%s]"
                     % ", ".join('"%s"' % name for name in public_names))
    deleted = set()
    for start, end in ranges:
        deleted.update(range(start, end + 1))
    out = []
    for number, line in enumerate(lines, 1):
        if number not in deleted:
            out.append(line)
        if number == anchor:
            out.extend(block)
    if anchor == 0:
        out = block + out
    squashed, blanks = [], 0
    for line in out:
        if not line.strip():
            blanks += 1
            if blanks > 2:
                continue
        else:
            blanks = 0
        squashed.append(line)
    while squashed and not squashed[-1].strip():
        squashed.pop()
    return "\n".join(squashed) + "\n", reexports
