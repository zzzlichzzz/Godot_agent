"""Native plan algorithm with IO replaced by injected map/index/occupied/scan."""
import hashlib
import re

from . import arch as arch_map
from .facade import _find_cycle, _format_import, _join_blocks, _render_facade, _warn_patched_attributes
from .groups import DEFAULT_TARGET_LINES, suggest_groups
from .inventory import _segment_text, _used_names, file_inventory


def plan_split(rel, text, groups=None, target_lines=DEFAULT_TARGET_LINES, *,
               inventory=None, map_data=None, index=None, occupied=(), scan=None):
    """Native full generated plan; project IO/refusals belong to app.call."""
    inventory = file_inventory(text) if inventory is None else inventory
    lines = text.splitlines()
    stem = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
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
    folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
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
        owner = group_of.get(name)
        if len(users) > 1 and owner in users:
            errors.append("мутабельный state %s нужен нескольким группам "
                          "(%s): вынеси его отдельным модулем-группой"
                          % (name, ", ".join(users)))
        elif len(users) > 1:
            # Рекомендацию «отдельным модулем» выполнили: state живёт в
            # собственном модуле, а потребители лишь импортируют один общий
            # объект — мутации не теряются, поэтому это не ошибка. Опасен
            # был именно случай, когда state уезжает вместе с функциями
            # одной группы, а его мутируют ещё из другой.
            warnings.append("мутабельный state %s вынесен отдельным модулем "
                            "%s и нужен группам (%s) — мутируй его только "
                            "через модуль-владелец"
                            % (name, owner, ", ".join(users)))
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
        if module["rel"] in occupied:
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
        index = index or {}
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
        "donor": rel,
        "donor_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
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
    attach_refs(prepared, scan)
    return prepared


def attach_refs(prepared, scan):
    if scan is not None:
        prepared["refs"] = {key:scan[key] for key in
                            ("counts", "hard_files", "soft_files", "truncated")}
        _warn_patched_attributes(scan, prepared, prepared["warnings"])
