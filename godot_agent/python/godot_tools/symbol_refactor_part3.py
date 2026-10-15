# -*- coding: utf-8 -*-

"""symbol_refactor_part3 — часть python/godot_tools/symbol_refactor.py (вынесено split_refactor).

Фасад и точка входа — python/godot_tools/symbol_refactor.py: он реэкспортирует имена модуля.
"""

import os
import re
import tempfile
import gd_api_check
import gd_lint
import gd_semantic_parser
import history_manager
from minilich import ml_project_index
from project_tools import (_resolve_safe_path, build_diff_preview,
                           can_write_project_path)

from symbol_refactor_data import _DECL_KINDS

from symbol_refactor_part1 import (LocatorError,
    RenameError,
    StaleRenameError,
    UnsafeRenameError,
    UnsupportedRenameError,
    _class_name_for_file,
    _collect_path_reference_edits,
    _collect_scene_connection_edits,
    _collect_scene_property_edits,
    _decl_kind,
    _exact_string_value,
    _find_subclasses,
    _move_with_uid,
    _owner_belongs_to_script,
    _owner_is_script_scope,
    _owner_is_top_level,
    _owner_shadows_name,
    _owner_within,
    _plan_file_rename,
    _project_lock,
    _read_source,
    _reference_in_other_scope,
    _replace_file,
    _sha256,
    _typed_receivers,
    _unverified_reason,
    _validate_action)

from symbol_refactor_part2 import (_add_allowed_addon_semantics,
    _assert_hierarchy_renamed,
    _classify_string_reference_kind,
    _collision,
    _engine_class_name,
    _excluded_places,
    _is_real_conflict,
    _project_global_names,
    _reference_is_safe,
    _unwritable_subclass_overrides,
    _usage_excluded)

def prepare_rename(project_root, action, allow_addons=False, addon_dir=None,
                   allow_self_edit=False):
    """Build a private all-file transaction without writing project files."""
    kind, old_name, new_name, target_path, line, column, mode, rename_file, allow_unverified = _validate_action(action)
    if not can_write_project_path(
            target_path, project_root, allow_addons=allow_addons,
            allow_self_edit=allow_self_edit, addon_dir=addon_dir):
        raise RenameError("Путь защищён текущей политикой доступа")
    _resolve_safe_path(project_root, target_path)

    snapshot = _add_allowed_addon_semantics(
        ml_project_index.semantic_snapshot(project_root, refresh=True),
        project_root, allow_addons, allow_self_edit, addon_dir)
    if not snapshot.get("complete"):
        raise RenameError("Семантический индекс неполон; безопасное переименование невозможно")
    # Неполный разбор — не повод отказывать сразу. Старый код отказывал при
    # ЛЮБОМ файле со статусом partial, из-за чего сломанный файл в углу
    # проекта блокировал переименование везде. Измерено: парсер в partial-файле
    # всё равно выдаёт пригодные объявления и ссылки, поэтому отказ здесь
    # выбрасывал доказуемые сведения и заставлял разбираться вручную там, где
    # мы и так всё знаем.
    #
    # Что мы действительно НЕ можем игнорировать: сломанный файл, который
    # входит в иерархию нашего символа (неизвестно, что в нём переименовать)
    # или который упоминает наше имя (неизвестно, все ли вхождения он увидел).
    # Решение принимается ПОСЛЕ того, как известны иерархия и подстрока имени.
    partial_paths = ["res://" + entry["path"] for entry in snapshot["files"]
                     if entry["semantic"].get("parse_status") != "ok"]

    declarations = []
    for entry in snapshot["files"]:
        path = "res://" + entry["path"]
        for item in entry["semantic"].get("declarations", []):
            declarations.append(dict(item, path=path, sha256=entry.get("sha256")))
    candidates = [item for item in declarations
                  if item.get("path") == target_path and item.get("line") == line
                  and item.get("kind") == _decl_kind(kind)
                  and item.get("name") == old_name
                  and (column is None or item.get("column") == column)]
    if len(candidates) != 1:
        # Сообщение должно быть пригодно для модели: что просили, что нашли
        # и что можно попробовать. Раньше тут было «найдено объявлений: 0»,
        # из чего нельзя было понять, в чём дело.
        available = sorted({item.get("name") for item in declarations
                            if item.get("path") == target_path
                            and item.get("kind") in _DECL_KINDS
                            and item.get("name")})
        raise LocatorError(
            "В %s:%d нет объявления вида %s с именем %s. Объявления этого "
            "скрипта: %s. Возьми точную строку объявления из gather_context "
            "или read_function."
            % (target_path, line, kind, old_name,
               ", ".join(available[:12]) or "нет"))
    declaration = candidates[0]
    if kind in ("function", "signal") and declaration.get("owner") != "script":
        # Член вложенного класса допустим, но только если сам класс вложен
        # на верхнем уровне скрипта. Класс, объявленный внутри функции, —
        # локальная сущность времени выполнения, её имя нельзя переименовать
        # безопасным текстовым способом.
        if not _owner_is_top_level(declaration.get("owner"), declarations):
            raise UnsupportedRenameError(
                "Члены вложенных классов переименовываются только для классов "
                "верхнего уровня скрипта")
    if kind == "variable" and declaration.get("owner") != "script":
        # Локальная переменная живёт ровно в своей функции: её объявление и
        # все обращения принадлежат одному scope. Переименование затрагивает
        # только этот scope — одноимённые локальные переменные в других
        # функциях и одноимённые члены скрипта остаются нетронутыми.
        if not _owner_belongs_to_script(declaration.get("owner"), declarations):
            raise UnsupportedRenameError(
                "Локальные переменные переименовываются только внутри функций "
                "верхнего уровня скрипта")
    if kind in ("const", "enum") and declaration.get("owner") != "script":
        # Константа и enum живут на верхнем уровне скрипта. Объявление внутри
        # функции или вложенного класса — это уже другая сущность, и
        # переименование «наружу» сломало бы её использование.
        raise UnsupportedRenameError("Константы и enum переименовываются только на верхнем уровне скрипта")
    if kind == "enum_member" and not _owner_is_top_level(
            declaration.get("owner"), declarations):
        # Member анонимного enum принадлежит скрипту, а member именованного —
        # самому enum. В обоих случаях enum должен быть верхнего уровня.
        raise UnsupportedRenameError("Members enum переименовываются только в enum верхнего уровня")
    # Имя enum, которому принадлежит member: через него идёт обращение
    # State.IDLE, и без него такая ссылка выглядела бы неоднозначной.
    target_enum_name = None
    if kind == "enum_member" and declaration.get("owner") != "script":
        target_enum_name = next(
            (item.get("name") for item in declarations
             if item.get("id") == declaration.get("owner")), None)

    target_entry = next(entry for entry in snapshot["files"]
                        if "res://" + entry["path"] == target_path)
    target_class = _class_name_for_file(target_entry["semantic"])
    subclasses = set()
    all_target_classes = {target_class} if target_class else set()

    # Иерархия нужна для ЛЮБОГО вида членов, а не только для переменных.
    # Раньше subclasses строились только при kind == "variable": вызовы в
    # подклассах обновлялись, а сами объявления-override оставались со старым
    # именем — проект получал вызов несуществующего метода при рапорте «успешно».
    # Для class_name иерархия нужна по другой причине: объявление с тем же
    # именем в наследнике перекрывает ГЛОБАЛЬНОЕ имя класса, и это затенение
    # ломает код наследника — такой случай обязан быть отказом, а не «просто
    # совпадением имени в чужом файле».
    subclasses = _find_subclasses(project_root, target_path, target_class, snapshot)
    if kind in ("function", "signal", "variable", "class_name", "const", "enum"):
        for sc in subclasses:
            sc_entry = next((e for e in snapshot["files"] if "res://" + e["path"] == sc), None)
            if sc_entry:
                sc_cls = _class_name_for_file(sc_entry["semantic"])
                if sc_cls:
                    all_target_classes.add(sc_cls)

    # Собственное одноимённое объявление ДРУГОГО вида в подклассе перекрывает
    # метод/сигнал базового класса: self.take_damage в таком подклассе — уже не
    # метод. Молча переименовывать ссылку здесь нельзя — это разные сущности.
    for sc in sorted(subclasses):
        sc_entry = next((e for e in snapshot["files"] if "res://" + e["path"] == sc), None)
        if not sc_entry:
            continue
        for item in sc_entry["semantic"].get("declarations", []):
            if (item.get("owner") == "script" and item.get("name") == old_name
                    and item.get("kind") != kind):
                raise RenameError(
                    "В подклассе %s есть собственное объявление %s (%s), перекрывающее "
                    "переименовываемое; переименование остановлено"
                    % (sc, old_name, item.get("kind")))

    # Коллизии уровня проекта и движка. _collision смотрит только объявления
    # в .gd, поэтому Hero -> Sprite2D (класс движка) и Hero -> GameState
    # (autoload) проходили, а проект падал в редакторе.
    if _engine_class_name(project_root, new_name, addon_dir=addon_dir):
        raise UnsafeRenameError("Новое имя %s занято классом движка Godot" % new_name)
    autoloads, input_actions = _project_global_names(project_root)
    if new_name in autoloads:
        raise UnsafeRenameError("Новое имя %s совпадает с autoload этого проекта"
                          % new_name)
    if new_name in input_actions:
        raise UnsafeRenameError("Новое имя %s совпадает с действием ввода InputMap"
                          % new_name)

    collided = _collision(declarations, declaration, kind, new_name, subclasses=subclasses)
    warnings = []
    # Здесь известна иерархия, поэтому только теперь решаем, обязаны ли
    # неполностью разобранные файлы останавливать переименование.
    if partial_paths:
        hierarchy_now = {target_path} | subclasses
        blocking = [path for path in partial_paths if path in hierarchy_now]
        mentioning = []
        for path in partial_paths:
            if path in blocking:
                continue
            try:
                _abs, _raw, source, _bom = _read_source(project_root, path)
            except Exception:
                # Не читается вообще: считаем, что имя там может быть.
                mentioning.append(path)
                continue
            # Ищем имя как ОТДЕЛЬНОЕ слово: грубый поиск подстроки давал бы
            # ложные срабатывания (health внутри healthy).
            if re.search(r"\b%s\b" % re.escape(old_name), source):
                mentioning.append(path)
        if blocking:
            raise RenameError(
                "Не удалось разобрать файл в иерархии символа: %s; неизвестно, "
                "что в нём нужно переименовать. Переименование остановлено"
                % ", ".join(sorted(blocking)[:4]))
        if mentioning:
            raise RenameError(
                "Не удалось разобрать файл, где встречается %s: %s; неизвестно, "
                "все ли вхождения найдены. Переименование остановлено"
                % (old_name, ", ".join(sorted(mentioning)[:4])))
        # Остальные сломанные файлы символа не касаются: ни иерархии, ни
        # упоминания имени. Молчать о них нельзя — пользователь должен знать,
        # что часть проекта осталась непроверенной.
        warnings.append(
            "Не удалось полностью разобрать %d файл(ов) вне иерархии и без "
            "упоминания %s (%s); на это переименование они не влияют, но эти "
            "файлы остались непроверенными"
            % (len(partial_paths), old_name, ", ".join(sorted(partial_paths)[:4])))
    if collided and _is_real_conflict(collided, declaration, kind, subclasses):
        raise UnsafeRenameError("Новое имя уже объявлено в том же пространстве: %s:%s"
                          % (collided.get("path"), collided.get("line")))
    if collided:
        # Простое совпадение имени в постороннем файле: локальная переменная
        # или константа чужого скрипта наш символ не задевает. Молчать было бы
        # плохо, отказывать — тем более, поэтому это видимое предупреждение.
        warnings.append(
            "В %s:%s уже есть объявление %s (%s) — имена совпадают, но это "
            "локальное имя чужого скрипта, переименование его не ломает"
            % (collided.get("path"), collided.get("line"), new_name,
               collided.get("kind")))
    if kind == "class_name":
        duplicates = [item for item in declarations
                      if item.get("kind") == kind and item.get("name") == old_name]
        if len(duplicates) != 1:
            raise LocatorError("class_name неоднозначен: найдено объявлений %d" % len(duplicates))
    else:
        # Проверяем вид объявления в терминах парсера: публичный "const"
        # разбирается как "constant" (иначе поиск не нашёл бы ничего).
        duplicates = [item for item in declarations
                      if item.get("path") == target_path
                      and item.get("kind") == _decl_kind(kind)
                      and item.get("name") == old_name
                      # Members разных enum одного скрипта — разные
                      # пространства имён: IDLE в State и IDLE в Mode
                      # не должны считаться одним и тем же объявлением.
                      and (kind != "enum_member"
                           or item.get("owner") == declaration.get("owner"))
                      # Член вложенного класса ищется ТОЛЬКО внутри него:
                      # одноимённый метод внешнего скрипта — другая
                      # сущность, и её переименование было бы поломкой.
                      and (declaration.get("owner") == "script"
                           or item.get("owner") == declaration.get("owner"))]
        if len(duplicates) != 1:
            raise LocatorError("Имя неоднозначно внутри скрипта: найдено объявлений %d" % len(duplicates))

    # Исключение мест (снятые в предпросмотре галочки) разбирается ОДНОЙ
    # точкой правды и ДО регистрации правок: объявление и ссылки ниже
    # сравниваются с одним и тем же множеством (путь, строка).
    excluded = _excluded_places(action.get("exclude") or ())
    if _usage_excluded(excluded, target_path, declaration.get("line")):
        # Снятое объявление нельзя переименовать в одиночку: использования
        # остались бы со старым именем — то есть проект был бы сломан при
        # рапорте «успешно». Отказ честнее половинчатой правки.
        raise RenameError(
            "Место объявления %s:%s снято пользователем: переименование "
            "невозможно — использования остались бы со старым именем. "
            "Снимите галочки с мест использования, а не с объявления"
            % (target_path, declaration.get("line")))
    edits_by_path = {target_path: [(declaration["start"], declaration["end"])]}
    # Объявления-override в подклассах — такие же носители имени, как и сам
    # скрипт: пока они не переименованы, полиморфизм теряется (вызов уходит
    # в несуществующий метод базового класса), поэтому берём их всеми видами,
    # а не только для переменных.
    for sc in sorted(subclasses):
        sc_entry = next((e for e in snapshot["files"] if "res://" + e["path"] == sc), None)
        if not sc_entry:
            continue
        for item in sc_entry["semantic"].get("declarations", []):
            if (item.get("kind") == _decl_kind(kind) and item.get("name") == old_name
                    and item.get("owner") == "script"):
                edits_by_path.setdefault(sc, []).append((item["start"], item["end"]))

    ambiguities = []
    dynamic_references = []
    unverified_references = []
    skipped_usages = []
    # Сколько правок-ССЫЛОК реально попало в план (P2). Объявления сюда не
    # считаются: сам символ и override в подклассах — носители имени, и их
    # наличие не доказывает, что хоть одна ссылка будет переименована.
    reference_edits = 0
    # Адреса уже занятых ДОКАЗАННЫХ правок: (путь, начало, конец). Правку
    # недоказанной ссылки нельзя наложить на уже занятый диапазон — получится
    # двойная замена и порча текста, поэтому проверяем адресно.
    proven_spans = set()
    for span_path, spans in edits_by_path.items():
        for span_start, span_end in spans:
            proven_spans.add((span_path, span_start, span_end))
    # Частичное применение: снятые галочки не меняются, но попадают в отчёт,
    # иначе «переименовано» враньёт пользователю в лицо. Само множество
    # excluded разобрано ВЫШЕ — там же, где принято решение об объявлении:
    # одна точка правды на объявление и на ссылки.

    for entry in snapshot["files"]:
        path = "res://" + entry["path"]
        if not can_write_project_path(
                path, project_root, allow_addons=allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir):
            continue
        _absolute, raw, text, _bom = _read_source(project_root, path)
        if entry.get("sha256") != _sha256(raw):
            raise StaleRenameError("Семантический индекс устарел для %s" % path)
        tokens = gd_semantic_parser.tokenize(text)
        typed = _typed_receivers(text)
        for fact in entry["semantic"].get("references", []):
            if fact.get("name") != old_name:
                continue
            if _usage_excluded(excluded, path, fact.get("line")):
                # Место снято пользователем (галочка снята в предпросмотре):
                # не переименовываем, но честно показываем, что осталось.
                skipped_usages.append(
                    "%s:%s:%s — снято пользователем, имя не переименовано"
                    % (path, fact.get("line"), fact.get("column")))
                continue
            if _reference_is_safe(kind, fact, text, tokens, target_path, path,
                                  target_class, typed,
                                  entry["semantic"].get("declarations", []),
                                  bool(declaration.get("static")),
                                  subclasses=subclasses,
                                  all_target_classes=all_target_classes,
                                  target_enum_name=target_enum_name,
                                  root_owner=declaration.get("owner"),
                                  root_declarations=declarations):
                edits_by_path.setdefault(path, []).append((fact["start"], fact["end"]))
                proven_spans.add((path, fact["start"], fact["end"]))
                reference_edits += 1
            elif (declaration.get("owner") != "script" and kind in ("function", "signal")
                  and not _owner_within(fact.get("owner"), declaration.get("owner"),
                                         declarations)):
                # Ссылка доказанно принадлежит НЕ нашему вложенному классу
                # (например, одноимённый метод внешнего скрипта). Это не
                # неоднозначность, а другая сущность — молча пропускаем.
                continue
            elif _reference_in_other_scope(fact, declaration, kind, declarations):
                # Ссылка живёт в scope, который НЕ является scope нашего
                # объявления: вложенный класс не наследует внешний скрипт,
                # поэтому одноимённый член снаружи — другая сущность.
                continue
            elif (kind in ("variable", "const", "enum", "enum_member", "class_name")
                  and fact.get("context") != "member"
                  and _owner_shadows_name(
                      fact.get("owner"), fact.get("name"),
                      entry["semantic"].get("declarations", []))):
                # Локальная тень: локальная переменная/константа с тем же
                # именем перекрывает нашу ссылку. Это НЕ неоднозначность,
                # а доказанно другая сущность — молча её пропускаем.
                #
                # class_name добавлен в список с Этапом 1 гранулярности отказа.
                # Раньше локальная переменная, названная как класс, попадала в
                # недоказанные, и это давало безопасный ОТКАЗ. Теперь такие
                # ссылки переименовываются, и без этой проверки переименование
                # портило код: `var Enemy = 1` рядом с `return Enemy` — это уже
                # не наш символ, и мы обязаны его не трогать.
                continue
            else:
                # Ссылка наша, но доказать её не удалось. Раньше она
                # отменяла ВСЮ операцию (одна неуверенность — ноль правок).
                # Теперь поведение зависит от флага allow_unverified.
                if (allow_unverified
                        and (path, fact["start"], fact["end"]) not in proven_spans):
                    # Флаг включён: переименовываем, но ОБЯЗАТЕЛЬНО показываем
                    # причину. Молча переименовать недоказанное — это ровно тот
                    # молчаливый ущерб, ради устранения которого этап и делается.
                    edits_by_path.setdefault(path, []).append(
                        (fact["start"], fact["end"]))
                    reference_edits += 1
                    reason = _unverified_reason(
                        kind, fact, text, tokens, target_path, path,
                        target_class, typed,
                        entry["semantic"].get("declarations", []),
                        subclasses, all_target_classes,
                        declaration.get("owner"))
                    ambiguities.append(
                        {"path": path, "line": fact.get("line"),
                         "column": fact.get("column"), "reason": reason})
                else:
                    ambiguities.append(
                        {"path": path, "line": fact.get("line"),
                         "column": fact.get("column"),
                         "reason": "ссылка не доказана, имя не переименовано"})
        for fact in entry["semantic"].get("strings", []):
            if _exact_string_value(str(fact.get("value") or "")) != old_name:
                continue
            # Строка с именем символа — не всегда ссылка. print("Player") —
            # это текст, а ClassDB.instantiate("Player") — обращение к API по
            # имени, которое мы не можем доказать статически. Раньше оба случая
            # давали одинаковый отказ, хотя свойства в .tscn переписываются
            # без вопросов. Теперь обычный текст не мешает, а настоящая
            # dynamic-ссылка попадает в отчёт для ручной проверки.
            reason_kind, reason = _classify_string_reference_kind(
                text, tokens, fact.get("start"), fact.get("end"))
            if not reason:
                continue
            if reason_kind == "class" and kind == "class_name":
                # Доказуемая ссылка на класс: API по контракту принимает имя
                # класса, значит строка обязана меняться вместе с ним. Раньше
                # она попадала в dynamic_references и в strict была отказом,
                # хотя доказать её легко.
                #
                # Правка идёт по ВНУТРЕННОСТИ литерала: диапазон fact покрывает
                # и кавычки (`"Player"`), а замена проверяет, что срез РАВЕН
                # имени. Оставлять кавычки снаружи обязательно, иначе получится
                # `ClassDB.instantiate(Avatar)` — синтаксическая ошибка.
                raw = str(fact.get("value") or "")
                quote = ""
                if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]:
                    quote = raw[0]
                if not quote:
                    # Без кавычек заменять нечего: это не строковый литерал.
                    dynamic_references.append(
                        "%s:%s — %s(\"%s\"); проверьте вручную"
                        % (path, fact.get("line"), reason, old_name))
                    continue
                inner_start = fact["start"] + len(quote)
                inner_end = fact["end"] - len(quote)
                if text[inner_start:inner_end] != old_name:
                    dynamic_references.append(
                        "%s:%s — %s(\"%s\"); проверьте вручную"
                        % (path, fact.get("line"), reason, old_name))
                    continue
                edits_by_path.setdefault(path, []).append(
                    (inner_start, inner_end))
                reference_edits += 1
                proven_spans.add((path, inner_start, inner_end))
                continue
            dynamic_references.append(
                "%s:%s — %s(\"%s\"); проверьте вручную"
                % (path, fact.get("line"), reason, old_name))
    # Отчёт собираем ДО решения об отказе: пользователь должен увидеть причину
    # и в случае отказа, и в случае применения.
    unverified_references = [
        "%s:%s:%s — %s" % (item["path"], item["line"], item["column"],
                           item["reason"])
        for item in ambiguities]
    # P2: половинчатое переименование запрещено. Если объявление цели реально
    # правится, а НИ ОДНОЙ правки-ссылки не набралось, и при этом есть снятые
    # пользователем места — переименовывать нельзя: символ получит новое имя, а
    # его использования останутся со старым. Отказ приходит ДО apply, поэтому
    # файлы проекта остаются байт-в-байт прежними.
    declaration_edited = (declaration["start"], declaration["end"]) in (
        edits_by_path.get(target_path) or [])
    if declaration_edited and reference_edits == 0 and skipped_usages:
        raise RenameError(
            "Все ссылки сняты пользователем, объявление переименовывать нельзя: %s"
            % "; ".join(skipped_usages))
    if ambiguities and mode == "strict" and not allow_unverified:
        # Флаг снят (или не передан): поведение прежнее — одна недоказанная
        # ссылка отменяет всё переименование. Это защищает клиентов, которые
        # флаг не шлют: они получают ровно то, что получали раньше.
        raise UnsafeRenameError(
            "Есть недоказанные ссылки (%d); переименование остановлено. "
            "Включи настройку «переименовывать недоказанные ссылки» или "
            "исправь их вручную: %s"
            % (len(ambiguities),
               ", ".join(unverified_references[:6])))
    if dynamic_references and mode == "strict":
        # Строка рядом с вызовом API Godot по имени — это РЕАЛЬНАЯ ссылка на
        # символ, которую мы не можем ни доказать, ни переписать: ClassDB
        # .instantiate("X"), set("X", ...), call("X") и подобные. Успех здесь
        # означал бы, что проект остался сломанным (вызов несуществующего
        # класса/члена), поэтому в strict это отказ с понятным текстом.
        # В probable пользователь принимает риск осознанно — см. Этап 2.4.
        first = dynamic_references[0]
        raise UnsafeRenameError(
            "Найдена динамическая ссылка по строке, её нельзя переименовать "
            "автоматически: %s. Таких мест: %d. Правь вручную либо повтори с "
            "mode=probable, приняв риск (проверь список мест перед записью)."
            % (first, len(dynamic_references)))
    # Ссылочная правка могла пройти, а объявление-override — нет; проверяем
    # итог по всему плану, а не по одному пути.
    _assert_hierarchy_renamed(
        kind, old_name, new_name, {target_path} | subclasses,
        {(path, start, end) for path, spans in edits_by_path.items()
         for start, end in spans}, declarations,
        owner=declaration.get("owner"))
    # Подклассы вне зоны нашей записи (addons и прочие защищённые .gd) в
    # семантический индекс не попадают — их override мы не обновим, а базу
    # переименуем. Это ровно тот случай, где «успех» ломает проект.
    blocked = _unwritable_subclass_overrides(
        project_root, target_path, target_class, snapshot, kind, old_name,
        allow_addons=allow_addons, allow_self_edit=allow_self_edit,
        addon_dir=addon_dir)
    if blocked:
        raise RenameError(
            "Вне зоны записи есть подкласс с переопределением %s: %s:%s; "
            "переименование остановлено"
            % (old_name, blocked[0][0], blocked[0][1]))

    files = []
    for path in sorted(edits_by_path):
        absolute, raw, before, bom = _read_source(project_root, path)
        ranges = sorted(set(edits_by_path[path]), reverse=True)
        after = before
        for start, end in ranges:
            if after[start:end] != old_name:
                raise StaleRenameError("Диапазон символа устарел для %s" % path)
            after = after[:start] + new_name + after[end:]
        problems = gd_lint.lint_gdscript(after)
        if problems:
            raise RenameError("После переименования %s не проходит gd_lint: %s"
                              % (path, problems[0]))
        before_api = set(gd_api_check.check_api_usage(project_root, before, path, addon_dir))
        after_api = set(gd_api_check.check_api_usage(project_root, after, path, addon_dir))
        introduced = sorted(after_api - before_api)
        if introduced:
            raise RenameError("После переименования %s появилась ошибка API: %s"
                              % (path, introduced[0]))
        encoded = ((b"\xef\xbb\xbf" if bom else b"") + after.encode("utf-8"))
        diff = build_diff_preview(before, after)
        diff["path"] = path
        diff["action"] = "rename_symbol"
        files.append({"path": path, "absolute": absolute,
                      "before_hash": _sha256(raw), "before_bytes": raw,
                      "after_bytes": encoded, "diff": diff,
                      "occurrences": len(ranges)})
    if kind == "variable" and declaration.get("owner") == "script":
        # Только ЧЛЕНЫ скрипта бывают свойствами сцены. Локальная переменная
        # функции в .tscn не записывается, и её имя там может совпадать с
        # совершенно чужым свойством другого скрипта.
        scene_edits = _collect_scene_property_edits(
            project_root, {target_path} | subclasses, old_name, new_name,
            allow_addons=allow_addons, allow_self_edit=allow_self_edit,
            addon_dir=addon_dir)
        files.extend(scene_edits)
    # Связи сцен — такой же носитель имени, как и код: без их обновления
    # Godot теряет подключение молча, а операция рапортует «успешно».
    # Члены вложенных классов сюда не попадают: Inner недоступен узлам сцены,
    # поэтому method такой связи к нашему символу отношения не имеет.
    if not _owner_is_script_scope(declaration, declarations):
        connection_edits = []
    else:
        connection_edits = _collect_scene_connection_edits(
            project_root, {target_path} | subclasses, kind, old_name, new_name,
            allow_addons=allow_addons, allow_self_edit=allow_self_edit,
            addon_dir=addon_dir)
    files.extend(connection_edits)
    # Содержимое, имя файла и .uid едут ОДНОЙ транзакцией: пока класс
    # переименован, а файл нет, проект находится в промежуточном состоянии.
    file_rename = None
    if rename_file:
        file_rename = _plan_file_rename(
            project_root, target_path, new_name, addon_dir)
        if file_rename:
            # Ссылки на переносимый путь обновляем В ТОЙ ЖЕ транзакции.
            # Раньше этого не было: сцена оставалась на несуществующем пути,
            # и узел молча терял скрипт (регрессия, найденная пробой S4).
            files.extend(_collect_path_reference_edits(
                project_root, file_rename, allow_addons=allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir))
        if file_rename:
            # Diff строим вручную: build_diff_preview возвращает None на
            # одинаковых текстах, а здесь изменение — это сам перенос пути.
            diff = {"path": file_rename["from"], "action": "rename_symbol",
                    "dest": file_rename["to"],
                    "lines": [{"type": "info",
                               "text": "Файл переименован в %s (вместе с .uid)"
                                       % file_rename["to"]}]}
    return {
        "kind": kind, "old_name": old_name, "new_name": new_name,
        "declaration": action.get("declaration"), "files": files,
        "file_rename": file_rename,
        "file_rename_diff": diff if file_rename else None,
        # Динамические ссылки не блокируют переименование, но обязаны быть
        # видны пользователю ДО записи — иначе риск остаётся незамеченным.
        "dynamic_references": dynamic_references,
        "warnings": warnings,
        "unverified_references": unverified_references,
        # Счётчики обязаны быть в отчёте: пользователю нужно видеть масштаб
        # правки, а не только список. unverified_count — сколько мест из
        # переименованных мы НЕ смогли доказать.
        "unverified_count": len(unverified_references),
        # renamed_count — сколько мест реально переименовано, ВКЛЮЧАЯ
        # недоказанные. Считаем по фактическим диапазонам правок, а не как
        # `sum(occurrences) - 1`: вычитание единицы считает объявление один раз
        # на весь план, из-за чего счётчик занижался на число затронутых файлов
        # и вводил в заблуждение о масштабе правки.
        "renamed_count": _count_renamed(files, target_path,
                                         declaration.get("start")),
        "skipped_usages": skipped_usages,
        "mode": mode,
        "allow_unverified": allow_unverified,
        "reference_count": sum(item["occurrences"] for item in files) - 1,
    }

def _count_renamed(files, target_path, declaration_start):
    """Сколько мест переименовано на самом деле.

    occurrences у файла — число ПРАВОК в нём, и объявление символа тоже
    является правкой. Значит «сколько мест изменено» — это просто сумма
    правок, без вычитания единицы: прежний reference_count вычитал единицу
    один раз на весь план, из-за чего занижался на (файлы − 1) и вводил в
    заблуждение о масштабе правки. Здесь считаем факт: и доказанные, и
    переименованные без доказательства места.
    """
    return sum(int(item.get("occurrences") or 0) for item in files)

def apply_prepared_rename(project_root, prepared, chat_id=None, chat_title=None):
    """Apply all files or restore every replaced file on a caught failure."""
    files = prepared.get("files") or []
    if not files:
        raise UnsafeRenameError("Подготовленная транзакция не содержит файлов")
    with _project_lock(project_root):
        for item in files:
            with open(item["absolute"], "rb") as handle:
                if _sha256(handle.read()) != item["before_hash"]:
                    raise StaleRenameError("Файл изменился после предпросмотра: %s" % item["path"])
        # Новый путь файла тоже попадает в журнал: на момент записи его ещё
        # нет, поэтому откат удалит его, а старый путь восстановит из
        # снапшота. Вместе это даёт возврат и содержимого, и имени файла.
        file_rename = prepared.get("file_rename")
        history_paths = [item["path"] for item in files]
        states = None
        if file_rename:
            # Новый путь и новый .uid в журнале НЕ существуют на момент
            # записи (before_present = False) — откат их удалит. Старые пути
            # восстановятся из снапшотов. Вместе это возвращает и содержимое,
            # и имя файла, и .uid одной кнопкой отката.
            history_paths.append(file_rename["to"])
            states = [{"path": file_rename["to"], "before_bytes": None,
                       "after_bytes": b""}]
            source_uid = _resolve_safe_path(project_root, file_rename["from"]) + ".uid"
            if os.path.isfile(source_uid):
                with open(source_uid, "rb") as handle:
                    uid_bytes = handle.read()
                history_paths.append(file_rename["from"] + ".uid")
                history_paths.append(file_rename["to"] + ".uid")
                states.append({"path": file_rename["from"] + ".uid",
                               "before_bytes": uid_bytes,
                               "after_bytes": uid_bytes})
                states.append({"path": file_rename["to"] + ".uid",
                               "before_bytes": None, "after_bytes": b""})
        entry_id = history_manager.record_batch_change(
            project_root, "rename_symbol", history_paths,
            chat_id=chat_id, chat_title=chat_title, states=states)
        replaced = []
        temps = []
        moved = []
        try:
            for item in files:
                directory = os.path.dirname(item["absolute"])
                descriptor, temp_path = tempfile.mkstemp(prefix=".agent_rename_", dir=directory)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(item["after_bytes"])
                    handle.flush()
                    os.fsync(handle.fileno())
                temps.append(temp_path)
                item["temp_path"] = temp_path
            for item in files:
                _replace_file(item["temp_path"], item["absolute"])
                replaced.append(item)
            if file_rename:
                _move_with_uid(project_root, file_rename, moved)
            history_manager.commit_change(project_root, entry_id)
        except Exception:
            # Откат в обратном порядке: сначала возвращаем перенесённые файлы
            # на старые места, затем — прежнее содержимое.
            for entry in reversed(moved):
                try:
                    _replace_file(entry["dest_absolute"], entry["source_absolute"])
                    if entry.get("dest_uid") and os.path.isfile(entry["dest_uid"]):
                        _replace_file(entry["dest_uid"], entry["source_uid"])
                except OSError:
                    pass
            for item in reversed(replaced):
                with open(item["absolute"], "wb") as handle:
                    handle.write(item["before_bytes"])
            history_manager.abort_change(project_root, entry_id)
            raise
        finally:
            for temp_path in temps:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass
        paths = [item["path"] for item in files]
        if file_rename:
            # Старый путь исчез, новый появился: индекс обновляем по обоим.
            paths = [file_rename["to"] if path == file_rename["from"] else path
                     for path in paths]
        ml_project_index.update_entries(project_root, changed_rels=paths)
        return {"entry_id": entry_id, "changed_paths": paths,
                "file_count": len(paths), "reference_count": prepared["reference_count"]}
