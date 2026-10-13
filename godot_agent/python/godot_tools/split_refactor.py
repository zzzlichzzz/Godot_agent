# -*- coding: utf-8 -*-
"""split_refactor.py — «пила» для .py-модулей: ссылки, план разбиения, фасад.

Зачем. Гейт (arch_map.check_new_file) отклоняет НОВЫЙ файл сверх лимита строк
и советует «раздели функциональность на модули ядра», но инструментов разбиения
не было: вынос кода в новый модуль ломал бы импорты, упоминания в тестах и
доках, а также проверки, читающие исходник модуля (живой пример — selfcheck.py
открывает godot_tools/project_tools.py по строке пути). Пила делает разбиение
управляемым, в духе других рефакторингов ядра (подготовка — только чтение,
запись — отдельным шагом):

  * scan_refs(addon_dir, rel_path) — карта ссылок на файл по всему аддону:
    импорты (hard), строковые упоминания и доки (soft), эвристика «чтение
    исходника» (open(...)/__file__ в строке с именем файла);
  * plan_split(addon_dir, rel_path, groups=None, target_lines=900) — инвентарь
    верхнего уровня (ast), группы-модули (заданные или черновые авто), проверки
    в духе гейта (зона, лимиты строк, дубли имён), кросс-импорты групп,
    предпросмотр текстов новых модулей и файла-фасада; ничего не пишет;
  * apply_prepared_split(prepared) — запись: новые модули + донор становится
    фасадом-реэкспортом. Канонический путь и импортное имя НЕ меняются:
    `import project_tools` и `from project_tools import X` продолжают работать.

Чего пила не делает (осознанные рамки v1): не правит доки/отчёты по ссылкам
(scan_refs даёт список — решает человек), не работает с .gd, не переносит
модули в подпапки (новые модули кладутся рядом с донором), не запускает тесты
(приёмка после apply — на вызывающем), не трогает переносы строк в фасаде
сверх нормализации к LF.
"""

import ast
import hashlib
import os
import re
import sys

import arch_map

SCHEMA = 1

_DEFAULT_TARGET_LINES = 900

# Каталоги (в любой точке дерева), которые скан ссылок не обходит.
_SCAN_SKIP_DIRS = {"__pycache__", ".git", ".godot", ".import", ".agent_history",
                   "dist", "build", "minilich_brain", "parser_corpus",
                   "agent_api_cache", "node_modules", ".venv", "_tmp"}

# Расширения текстовых файлов, в которых ищем ссылки.
_SCAN_EXTS = {".py", ".gd", ".md", ".json", ".cmd", ".bat", ".txt", ".cfg",
              ".godot", ".tscn", ".tres", ".gdshader"}

_MAX_SCAN_FILE_BYTES = 1024 * 1024   # дампы и большие json не сканируем
_MAX_OCCURRENCES = 1000              # предохранитель размера отчёта

_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+")
_CODING_RE = re.compile(r"^#!|^#\s*-\*-")


class SplitError(ValueError):
    """Ошибка входа/применения: план нельзя построить или применить."""


class StaleSplitError(RuntimeError):
    """Донор изменился после plan_split — план устарел, нужен новый."""


def _norm(rel_path):
    return str(rel_path or "").replace("\\", "/").strip("/")


def _read_text(abs_path):
    with open(abs_path, "r", encoding="utf-8-sig", errors="replace") as handle:
        return handle.read()


def _write_text(abs_path, text):
    with open(abs_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _replace_text(abs_path, text):
    """Замена файла через временный + os.replace (одномоментно для читателя)."""
    tmp_path = abs_path + ".split_tmp"
    _write_text(tmp_path, text)
    os.replace(tmp_path, abs_path)


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _files_of(addon_dir):
    """Обход дерева аддона: (относительный путь через «/», абсолютный)."""
    root = os.path.abspath(str(addon_dir))
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(item for item in dirs
                         if item not in _SCAN_SKIP_DIRS
                         and not item.startswith("."))
        for name in sorted(names):
            abs_path = os.path.join(base, name)
            rel = os.path.relpath(abs_path, root).replace("\\", "/")
            yield rel, abs_path


def _imported_modules(line):
    """(модули, alias-имена) из import-строки; иначе ([], [])."""
    if not _IMPORT_RE.match(line):
        return [], []
    stripped = line.strip()
    if stripped.startswith("from "):
        target = stripped[5:].split(" import", 1)[0]
        target = target.strip().strip("()").strip()
        return [target.lstrip(".")], []
    modules, aliases = [], []
    for part in stripped[len("import "):].split(","):
        pieces = part.strip().split(" as ")
        if pieces and pieces[0].strip():
            modules.append(pieces[0].strip().lstrip("."))
        if len(pieces) == 2 and pieces[1].strip():
            aliases.append(pieces[1].strip())
    return modules, aliases


def _module_matches(candidate, stem):
    return candidate == stem or candidate.endswith("." + stem)


def scan_refs(addon_dir, rel_path):
    """Карта ссылок на файл аддона: импорты, строки, доки, чтение исходника.

    Возвращает dict: counts по видам (import/source_read/mention/doc),
    occurrences (rel, line, kind, text), hard_files (импорты и чтение
    исходника — сломаются при смене пути/имени), soft_files (упоминания и
    доки — ревизия человеком), truncated (обрезан ли отчёт предохранителем).
    """
    rel = _norm(rel_path)
    if not os.path.isfile(os.path.join(str(addon_dir), rel)):
        raise SplitError("файл не найден: %s" % rel)
    stem = os.path.splitext(os.path.basename(rel))[0]
    base = os.path.basename(rel)
    name_re = re.compile(r"(?<![\w-])" + re.escape(base) + r"(?![\w])")
    counts = {"import": 0, "source_read": 0, "mention": 0, "doc": 0}
    occurrences, truncated = [], False
    for file_rel, file_abs in _files_of(addon_dir):
        if file_rel == rel:
            continue
        ext = os.path.splitext(file_rel)[1].lower()
        if ext not in _SCAN_EXTS:
            continue
        try:
            if os.path.getsize(file_abs) > _MAX_SCAN_FILE_BYTES:
                continue
            text = _read_text(file_abs)
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            modules, _aliases = _imported_modules(line)
            if any(_module_matches(item, stem) for item in modules):
                kind = "import"
            elif name_re.search(line) or rel in line:
                if ext == ".py" and ("open(" in line or "__file__" in line
                                     or "read_text(" in line):
                    kind = "source_read"
                elif ext == ".md":
                    kind = "doc"
                else:
                    kind = "mention"
            else:
                continue
            counts[kind] += 1
            if len(occurrences) < _MAX_OCCURRENCES:
                occurrences.append({"rel": file_rel, "line": number,
                                    "kind": kind, "text": line.strip()[:200]})
            else:
                truncated = True
    hard_files = sorted({item["rel"] for item in occurrences
                         if item["kind"] in ("import", "source_read")})
    soft_files = sorted({item["rel"] for item in occurrences
                         if item["kind"] in ("mention", "doc")})
    return {"rel": rel, "stem": stem, "counts": counts,
            "occurrences": occurrences, "hard_files": hard_files,
            "soft_files": soft_files, "truncated": truncated}


def _segment_text(lines, start, end):
    return "\n".join(lines[start - 1:end])


def _expand_comments(lines, next_lineno):
    """Начало сегмента: строка плюс «липкие» комментарии прямо над ней."""
    start = int(next_lineno)
    while start - 1 >= 1:
        prev = lines[start - 2].strip()
        if not prev.startswith("#") or _CODING_RE.match(prev):
            break
        start -= 1
    return start


def _import_bindings(node):
    """Имена, которые импорт связывает в модуле (для копирования в модули)."""
    names = []
    for alias in node.names:
        if alias.name == "*":
            names.append("*")
        elif isinstance(node, ast.Import):
            names.append(alias.asname or alias.name.split(".")[0])
        else:
            names.append(alias.asname or alias.name)
    return names


def _other_item(lines, node, name):
    """Неперемещаемая верхняя сущность (if/try/expr/dunder-assign/...)."""
    bindings = set()
    for inner in ast.walk(node):
        if isinstance(inner, (ast.Import, ast.ImportFrom)):
            bindings.update(_import_bindings(inner))
    return {"name": name, "lineno": node.lineno, "end_lineno": node.end_lineno,
            "text": _segment_text(lines, node.lineno, node.end_lineno),
            "bindings": sorted(bindings)}


def file_inventory(text):
    """Инвентарь модуля: докстрока, импорты, символы верхнего уровня, прочее.

    Символы — def/class (с декораторами) и одиночные assign-имена (кроме
    dunder): lineno/end_lineno, число строк, публичность, признак мутабельного
    state (dict/list/set) и «липкие» комментарии над символом.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as exc:
        raise SplitError("не разобрал .py: %s" % exc)
    lines = text.splitlines()
    body = list(tree.body)
    docstring, docstring_end = None, 0
    if body and isinstance(body[0], ast.Expr) \
            and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        docstring = body[0].value.value
        docstring_end = body[0].end_lineno
        body = body[1:]
    imports, symbols, other = [], [], []
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append({"text": _segment_text(lines, node.lineno,
                                                 node.end_lineno),
                            "bindings": _import_bindings(node),
                            "lineno": node.lineno,
                            "end_lineno": node.end_lineno})
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            base_lineno = node.lineno
            decorators = getattr(node, "decorator_list", None) or []
            if decorators:
                base_lineno = min([base_lineno]
                                  + [item.lineno for item in decorators])
            start = _expand_comments(lines, base_lineno)
            symbols.append({"name": node.name,
                            "kind": "class" if isinstance(node, ast.ClassDef)
                            else "def",
                            "lineno": node.lineno,
                            "end_lineno": node.end_lineno,
                            "line_start": start,
                            "lines": node.end_lineno - start + 1,
                            "is_public": not node.name.startswith("_"),
                            "state": False, "node": node})
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.startswith("__") and name.endswith("__"):
                other.append(_other_item(lines, node, name))
                continue
            start = _expand_comments(lines, node.lineno)
            symbols.append({"name": name, "kind": "assign",
                            "lineno": node.lineno,
                            "end_lineno": node.end_lineno,
                            "line_start": start,
                            "lines": node.end_lineno - start + 1,
                            "is_public": not name.startswith("_"),
                            "state": isinstance(node.value,
                                                (ast.Dict, ast.List, ast.Set)),
                            "node": node})
            continue
        other.append(_other_item(lines, node, None))
    return {"docstring": docstring, "docstring_end": docstring_end,
            "lines": len(lines), "imports": imports, "symbols": symbols,
            "other": other}


def _used_names(node):
    """Имена, читаемые внутри узла (Load-ссылки; локальные тени не различаем)."""
    used = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load):
            used.add(inner.id)
    return used


def suggest_groups(inventory, stem, target_lines=_DEFAULT_TARGET_LINES):
    """Черновые группы: символы по порядку, куски не длиннее target_lines."""
    if not inventory["symbols"]:
        raise SplitError("в файле нет символов верхнего уровня для переноса")
    chunks, current, size = [], [], 0
    for item in inventory["symbols"]:
        cost = item["lines"] + 2   # + разделительная пустая строка
        if current and size + cost > target_lines:
            chunks.append(current)
            current, size = [], 0
        current.append(item)
        size += cost
    if current:
        chunks.append(current)
    return [{"module": "%s_part%d" % (stem, index),
             "symbols": [item["name"] for item in chunk]}
            for index, chunk in enumerate(chunks, 1)]


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


def plan_split(addon_dir, rel_path, groups=None,
               target_lines=_DEFAULT_TARGET_LINES):
    """План разбиения .py-модуля (ничего не пишет).

    groups — список {"module": имя, "symbols": [имена]} или None (черновые
    авто-группы по target_lines). Возвращает prepared: тексты модулей и
    фасада, errors (план не применять), warnings (решить человеку),
    donor_sha256 (защита apply от устаревшего плана) и сводку scan_refs.
    """
    addon_dir = os.path.abspath(str(addon_dir))
    rel = _norm(rel_path)
    if not rel.lower().endswith(".py"):
        raise SplitError("пила работает только с .py: %s" % rel)
    abs_donor = os.path.join(addon_dir, rel)
    if not os.path.isfile(abs_donor):
        raise SplitError("файл не найден: %s" % rel)
    text = _read_text(abs_donor)
    inventory = file_inventory(text)
    lines = text.splitlines()
    stem = os.path.splitext(os.path.basename(rel))[0]
    errors, warnings = [], []
    auto = groups is None
    if auto:
        groups = suggest_groups(inventory, stem, target_lines)
        warnings.append("группы черновые (авто, ~%d строк на модуль): "
                        "проверь состав перед apply" % target_lines)
    by_name = {item["name"]: item for item in inventory["symbols"]}
    for item in inventory["symbols"]:
        item["text"] = _segment_text(lines, item["line_start"],
                                     item["end_lineno"])
    folder = os.path.dirname(rel)
    plan_items, group_of = [], {}
    for raw in groups:
        module = str(raw.get("module") or "").strip()
        names = [str(name) for name in (raw.get("symbols") or [])]
        if not re.match(r"^[A-Za-z_]\w*$", module):
            errors.append("группа без корректного имени модуля: %r" % (raw,))
            continue
        if module == stem:
            errors.append("модуль группы %s совпадает с именем донора"
                          % module)
        target_rel = ("%s/%s.py" % (folder, module)) if folder \
            else ("%s.py" % module)
        for name in names:
            if name not in by_name:
                errors.append("группа %s: символ %r не найден среди "
                              "определений верхнего уровня" % (module, name))
            elif name in group_of:
                errors.append("символ %s указан дважды (%s и %s)"
                              % (name, group_of[name], module))
            else:
                group_of[name] = module
        plan_items.append({"module": module, "rel": target_rel,
                           "names": names})
    if not plan_items or not group_of:
        errors.append("план без символов к переносу")
    map_data = arch_map.load_map(addon_dir)
    if map_data is None:
        warnings.append("карта архитектуры не найдена — зоны, лимиты и дубли "
                        "имён не проверены")
    policy = arch_map.line_policy(map_data)
    import_pairs = [(imp, set(imp["bindings"]))
                    for imp in inventory["imports"]]
    future_texts = [imp["text"] for imp, _binds in import_pairs
                    if imp["text"].lstrip().startswith("from __future__")]
    star_texts = [imp["text"] for imp, binds in import_pairs if "*" in binds]
    used_map, siblings, graph = {}, {}, {}
    for item in plan_items:
        used = set()
        for name in item["names"]:
            symbol = by_name.get(name)
            if symbol is not None:
                used |= _used_names(symbol["node"])
        used_map[item["module"]] = used
        item["needed"] = [imp["text"] for imp, binds in import_pairs
                          if binds & used or "*" in binds]
        item["blocks"] = sorted({other["text"] for other in inventory["other"]
                                 if set(other["bindings"]) & used})
        cross = {}
        for name in sorted(used):
            owner = group_of.get(name)
            if owner and owner != item["module"]:
                cross.setdefault(owner, []).append(name)
        siblings[item["module"]] = cross
        graph[item["module"]] = set(cross)
    state_users = {}
    for item in plan_items:
        for name in sorted(used_map[item["module"]]):
            if name in by_name and by_name[name]["state"] \
                    and group_of.get(name):
                state_users.setdefault(name, set()).add(item["module"])
    leftover = sorted(item["name"] for item in inventory["symbols"]
                      if item["name"] not in group_of)
    for item in plan_items:
        lost = sorted(used_map[item["module"]] & set(leftover))
        if lost:
            errors.append("группа %s использует символ(ы) %s, оставшиеся в "
                          "фасаде: импорт модуль->фасад даст цикл — добавь "
                          "их в группу" % (item["module"], ", ".join(lost)))
    if leftover:
        warnings.append("в фасаде остаются не перенесённые символы: %s"
                        % ", ".join(leftover))
    for name in sorted(state_users):
        users = sorted(state_users[name])
        if len(users) > 1:
            errors.append("мутабельный state %s нужен нескольким группам "
                          "(%s): вынеси его отдельным модулем-группой"
                          % (name, ", ".join(users)))
        else:
            warnings.append("мутабельный state %s переезжает в модуль %s — "
                            "проверь, что его больше никто не мутирует"
                            % (name, users[0]))
    cycle = _find_cycle(graph)
    if cycle:
        errors.append("группы ссылаются по кругу: %s — объедини их в одну"
                      % " -> ".join(cycle))
    modules = []
    for item in plan_items:
        if any(name not in by_name for name in item["names"]):
            continue
        bits = ["# -*- coding: utf-8 -*-",
                '"""%s — часть %s (вынесено split_refactor).\n'
                "\n"
                "Фасад и точка входа — %s: он реэкспортирует имена модуля.\n"
                '"""' % (item["module"], rel, rel)]
        if future_texts:
            bits.append("\n".join(future_texts))
        if star_texts:
            bits.append("\n".join(star_texts))
        if item["needed"]:
            bits.append("\n".join(item["needed"]))
        for owner in sorted(siblings.get(item["module"]) or {}):
            bits.append(_format_import(
                owner, sorted(siblings[item["module"]][owner])))
        bits.extend(item["blocks"])
        bits.extend(by_name[name]["text"] for name in item["names"])
        module_text = _join_blocks(bits)
        module_lines = arch_map.count_lines(module_text)
        modules.append({"module": item["module"], "rel": item["rel"],
                        "names": list(item["names"]), "lines": module_lines,
                        "text": module_text})
    for module in modules:
        zone = arch_map.zone_for(map_data, module["rel"]) if map_data else None
        zone = zone or {}
        role = str(zone.get("role") or "unknown")
        new_files = str(zone.get("new_files") or "warn").lower()
        hint = str(zone.get("hint") or "").strip()
        suffix = (" — %s" % hint) if hint else ""
        if new_files == "deny":
            errors.append("%s: зона %s — только генерируемые файлы%s"
                          % (module["rel"], zone.get("glob") or "?", suffix))
        elif new_files == "warn":
            warnings.append("%s: зона %s (%s)%s"
                            % (module["rel"], zone.get("glob") or "?", role,
                               suffix))
        if os.path.exists(os.path.join(addon_dir, module["rel"])):
            errors.append("целевой файл уже существует: %s" % module["rel"])
        if role not in policy["exempt_roles"]:
            if module["lines"] > policy["max"]:
                errors.append("%s: %d строк — больше лимита %d на файл: "
                              "раздели ещё (или подними target_lines)"
                              % (module["rel"], module["lines"],
                                 policy["max"]))
            elif module["lines"] >= policy["warn"]:
                warnings.append("%s: %d строк — близко к лимиту %d"
                                % (module["rel"], module["lines"],
                                   policy["warn"]))
    moved_names = sorted(group_of)
    if map_data is not None:
        index = arch_map.name_index(addon_dir)
        stoplist = set(map_data.get("name_stoplist") or [])
        core_dir = arch_map.core_dir_of(map_data)
        for name in moved_names:
            if name in stoplist:
                continue
            hits = sorted(hit for hit, _kind in (index.get(name) or [])
                          if hit != rel
                          and arch_map.name_checks_enabled(map_data, hit))
            core_hits = [hit for hit in hits if hit.startswith(core_dir)]
            other_hits = [hit for hit in hits if not hit.startswith(core_dir)]
            if core_hits:
                errors.append("дубль из ядра: имя %s уже определено: %s — "
                              "разберись до разбиения"
                              % (name, ", ".join(core_hits)))
            elif other_hits:
                warnings.append("имя %s уже встречается вне ядра: %s"
                                % (name, ", ".join(other_hits)))
    facade_text, reexports = _render_facade(rel, lines, inventory, moved_names,
                                            modules, by_name, warnings)
    for module in modules:
        try:
            compile(module["text"], module["rel"], "exec")
        except (SyntaxError, ValueError) as exc:
            errors.append("%s: текст модуля не компилируется: %s"
                          % (module["rel"], exc))
    try:
        compile(facade_text, rel, "exec")
    except (SyntaxError, ValueError) as exc:
        errors.append("%s: текст фасада не компилируется: %s" % (rel, exc))
    prepared = {
        "schema": SCHEMA,
        "addon_dir": addon_dir,
        "donor": rel,
        "donor_sha256": _sha256(text),
        "donor_lines": arch_map.count_lines(text),
        "target_lines": int(target_lines),
        "auto_groups": auto,
        "modules": modules,
        "facade": {"rel": rel, "text": facade_text,
                   "lines": arch_map.count_lines(facade_text),
                   "reexports": reexports},
        "moved_names": moved_names,
        "errors": errors,
        "warnings": warnings,
        "inventory": {
            "symbols": [{"name": item["name"], "kind": item["kind"],
                         "lines": item["lines"],
                         "is_public": item["is_public"],
                         "state": item["state"]}
                        for item in inventory["symbols"]],
            "imports": len(inventory["imports"]),
            "other": len(inventory["other"]),
            "docstring": bool(inventory["docstring"]),
        },
        "refs": None,
    }
    try:
        scan = scan_refs(addon_dir, rel)
        prepared["refs"] = {"counts": scan["counts"],
                            "hard_files": scan["hard_files"],
                            "soft_files": scan["soft_files"],
                            "truncated": scan["truncated"]}
    except SplitError:
        pass
    return prepared


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


def apply_prepared_split(prepared):
    """Применить план: записать модули и заменить донора фасадом.

    Отказ (SplitError) — если в плане есть errors или текст модуля перестал
    компилироваться; StaleSplitError — если донор изменился после plan_split
    или целевой файл уже появился. Возвращает отчёт:
    {donor, written, moved, facade_lines}.
    """
    errors = list(prepared.get("errors") or [])
    if errors:
        raise SplitError("план не готов к применению: %s" % "; ".join(errors))
    addon_dir = str(prepared.get("addon_dir") or "")
    donor_rel = _norm(prepared.get("donor"))
    donor_abs = os.path.join(addon_dir, donor_rel)
    if not os.path.isfile(donor_abs):
        raise StaleSplitError("файл-донор исчез: %s" % donor_rel)
    if _sha256(_read_text(donor_abs)) != prepared.get("donor_sha256"):
        raise StaleSplitError("файл-донор изменился после plan_split: %s"
                              % donor_rel)
    written = []
    for module in prepared.get("modules") or []:
        rel = _norm(module.get("rel"))
        text = str(module.get("text") or "")
        try:
            compile(text, rel, "exec")
        except (SyntaxError, ValueError) as exc:
            raise SplitError("%s: текст модуля не компилируется: %s"
                             % (rel, exc))
        if os.path.exists(os.path.join(addon_dir, rel)):
            raise StaleSplitError("целевой файл уже существует: %s" % rel)
    for module in prepared.get("modules") or []:
        rel = _norm(module.get("rel"))
        text = str(module.get("text") or "")
        target_abs = os.path.join(addon_dir, rel)
        folder_abs = os.path.dirname(target_abs)
        if folder_abs and not os.path.isdir(folder_abs):
            os.makedirs(folder_abs, exist_ok=True)
        _write_text(target_abs, text)
        written.append(rel)
    facade = prepared.get("facade") or {}
    facade_text = str(facade.get("text") or "")
    try:
        compile(facade_text, donor_rel, "exec")
    except (SyntaxError, ValueError) as exc:
        raise SplitError("%s: текст фасада не компилируется: %s"
                         % (donor_rel, exc))
    _replace_text(donor_abs, facade_text)
    return {"donor": donor_rel, "written": written,
            "moved": list(prepared.get("moved_names") or []),
            "facade_lines": arch_map.count_lines(facade_text)}


def _print_plan_summary(prepared):
    """Человекочитаемая сводка плана (для CLI)."""
    print("донор: %s — %d строк, цель ~%d строк"
          % (prepared["donor"], prepared["donor_lines"],
             prepared["target_lines"]))
    for module in prepared["modules"]:
        print("  модуль %s: %d строк, символов %d"
              % (module["rel"], module["lines"], len(module["names"])))
    print("  фасад %s: %d строк, реэкспорт %d имён"
          % (prepared["facade"]["rel"], prepared["facade"]["lines"],
             len(prepared["facade"]["reexports"])))
    counts = ((prepared.get("refs") or {}).get("counts") or {})
    print("  ссылки: import=%s source_read=%s mention=%s doc=%s"
          % (counts.get("import", 0), counts.get("source_read", 0),
             counts.get("mention", 0), counts.get("doc", 0)))
    for message in prepared["warnings"]:
        print("warning: %s" % message)
    for message in prepared["errors"]:
        print("error: %s" % message)


def _cli(argv=None):
    """CLI «пилы»: scan / plan / apply.

    Коды возврата: 0 — чисто; 2 — есть ошибки плана (или жёсткие ссылки
    при scan); 3 — отказ входа/применения (SplitError/StaleSplitError/IO).
    """
    import argparse
    import json
    parser = argparse.ArgumentParser(
        prog="split_refactor",
        description="Пила .py: scan ссылок, plan разбиения (JSON), "
                    "фасадный apply — донор остаётся точкой входа.")
    sub = parser.add_subparsers(dest="command", required=True)
    scan_p = sub.add_parser("scan", help="карта ссылок на файл: что поедет")
    scan_p.add_argument("--addon", required=True, help="корень аддона")
    scan_p.add_argument("--file", required=True, help="путь внутри аддона")
    scan_p.add_argument("--json", dest="json_out", help="сохранить JSON")
    plan_p = sub.add_parser("plan", help="план разбиения (ничего не пишет)")
    plan_p.add_argument("--addon", required=True)
    plan_p.add_argument("--file", required=True)
    plan_p.add_argument("--groups", help="JSON-файл групп: "
                                         '[{"module": ..., "symbols": [...]}]')
    plan_p.add_argument("--target-lines", type=int,
                        default=_DEFAULT_TARGET_LINES)
    plan_p.add_argument("--json", dest="json_out",
                        help="сохранить prepared (вход для apply)")
    apply_p = sub.add_parser("apply", help="применить prepared из --json")
    apply_p.add_argument("--prepared", required=True,
                         help="prepared.json, сохранённый командой plan")
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            payload = scan_refs(args.addon, args.file)
            counts = payload["counts"]
            print("ссылки: import=%d source_read=%d mention=%d doc=%d"
                  % (counts["import"], counts["source_read"],
                     counts["mention"], counts["doc"]))
            for label, key in (("жёсткие", "hard_files"),
                               ("мягкие", "soft_files")):
                if payload[key]:
                    print("%s файлы (%d): %s"
                          % (label, len(payload[key]),
                             ", ".join(payload[key][:12])))
            if payload["truncated"]:
                print("внимание: список ссылок усечён (лимит %d)"
                      % _MAX_OCCURRENCES)
            code = 2 if payload["hard_files"] else 0
        elif args.command == "plan":
            groups = None
            if args.groups:
                with open(args.groups, "r", encoding="utf-8-sig") as handle:
                    groups = json.load(handle)
            payload = plan_split(args.addon, args.file, groups=groups,
                                 target_lines=args.target_lines)
            _print_plan_summary(payload)
            code = 2 if payload["errors"] else 0
        else:
            with open(args.prepared, "r", encoding="utf-8-sig") as handle:
                prepared = json.load(handle)
            payload = apply_prepared_split(prepared)
            print("применено: %s — фасад %d строк"
                  % (payload["donor"], payload["facade_lines"]))
            for rel in payload["written"]:
                print("  записан: %s" % rel)
            code = 0
    except (SplitError, StaleSplitError) as exc:
        print("отказ: %s" % exc)
        return 3
    except OSError as exc:
        print("ошибка ввода-вывода: %s" % exc)
        return 3
    if getattr(args, "json_out", None):
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        print("json: %s" % args.json_out)
    return code


if __name__ == "__main__":
    sys.exit(_cli())
