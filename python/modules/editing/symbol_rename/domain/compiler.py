"""modules/editing/symbol_rename/domain/compiler.py - план правок из отчёта поиска.

Компилятор ничего не ищет: места использования приносит `analyze_rename`
(`code_intel.usages`), здесь они превращаются в шаги `script_edit` с НАШИМИ
смещениями. Смещения считаются в тексте после нормализации переводов строк
(`\\r\\n` и `\\r` → `\\n`) и проверяются срезом: если срез не равен старому
имени, правка не строится (лучше `internal`, чем испорченный файл).

Отказы по существу — `conflict` с `details.reason` (ADR-0005, лист механики):
`name_conflict`, `all_usages_excluded`, `unverified_references`,
`dynamic_references`. Гейтинг ровно эталонный (`symbol_refactor_part3:477-499`).
"""

import hashlib
import re

from python.kernel.errors import AppError
from python.kernel.write_plan import Step
from python.formats.gdscript.method_guards import plan_guards

from .collisions import name_conflict

KINDS = ("class_name", "function", "signal", "variable", "const", "enum",
         "enum_member")
MODES = ("strict", "probable")
IDENTIFIER = re.compile(r"^[^\W\d]\w*$", re.U)
KEYWORDS = frozenset((
    "and", "as", "assert", "await", "break", "breakpoint", "class",
    "class_name", "const", "continue", "elif", "else", "enum", "extends",
    "for", "func", "if", "in", "is", "match", "not", "or", "pass", "preload",
    "return", "self", "signal", "static", "super", "var", "while"))


def validate_request(kind, old_name, new_name, mode, allow_unverified):
    """Правила `_validate_action` (part1:330-368), которые видит пользователь."""
    if kind not in KINDS:
        raise AppError("invalid_input", "неизвестный вид символа: %r" % (kind,),
                       hint="kind — один из: %s" % ", ".join(KINDS))
    for label, value in (("old_name", old_name), ("new_name", new_name)):
        text = str(value or "").strip()
        if not IDENTIFIER.match(text):
            raise AppError("invalid_input",
                           "%s=%r не является допустимым идентификатором GDScript"
                           % (label, value))
        if text in KEYWORDS:
            raise AppError("invalid_input",
                           "%s=%r — ключевое слово GDScript" % (label, text))
    if str(old_name) == str(new_name):
        raise AppError("invalid_input", "новое имя совпадает со старым",
                       details={"reason": "same_name"})
    if mode not in MODES:
        raise AppError("invalid_input", "mode должен быть strict или probable",
                       hint="получено: %r" % (mode,))
    if not isinstance(allow_unverified, bool):
        raise AppError("invalid_input",
                       "allow_unverified должен быть true или false",
                       hint="получено: %r" % (allow_unverified,))


def compile_plan(analysis, texts, mode, allow_unverified, exclude=(),
                 newlines=None):
    """Отчёт поиска + тексты → `{steps, skipped_usages, risks, stats}`."""
    new_name = analysis["new_name"]
    declaration_path = analysis["declaration_path"]
    conflict = name_conflict(texts.get(declaration_path, ""), new_name)
    if conflict:
        raise AppError("conflict", conflict,
                       hint="Переименование остановлено: имя занято",
                       details={"reason": "name_conflict"})
    excluded = set(exclude)
    edits_by_path, skipped = {}, []
    excluded_skips = reference_edits = 0
    uncertain, dynamic = [], []
    for usage in analysis["usages"]:
        path, line = usage["path"], usage["line"]
        column = usage.get("column") or 1
        if usage["link"] == "declaration":
            _add_edit(edits_by_path, texts, usage, analysis["old_name"], new_name)
            continue
        if usage["confidence"] == "dynamic":
            dynamic.append(usage)
            if (path, line) in excluded:
                skipped.append("%s:%s:%s — снято пользователем, имя не "
                               "переименовано" % (path, line, column))
            continue
        if (path, line) in excluded:
            skipped.append("%s:%s:%s — снято пользователем, имя не переименовано"
                           % (path, line, column))
            excluded_skips += 1
            continue
        if usage["confidence"] == "proven":
            _add_edit(edits_by_path, texts, usage, analysis["old_name"], new_name)
            reference_edits += 1
        else:
            uncertain.append(usage)
            if allow_unverified:
                _add_edit(edits_by_path, texts, usage, analysis["old_name"],
                          new_name)
                reference_edits += 1
            else:
                skipped.append(
                    "%s:%s:%s — ссылка не доказана, имя не переименовано"
                    % (path, line, column))
    if excluded_skips and not reference_edits:
        raise AppError("conflict",
                       "Все ссылки сняты пользователем, объявление переименовывать "
                       "нельзя: %s" % "; ".join(skipped[:6]),
                       hint="Сними exclude или переименуй вручную",
                       details={"reason": "all_usages_excluded"})
    if mode == "strict" and uncertain and not allow_unverified:
        raise AppError("conflict",
                       "Есть недоказанные ссылки (%d); переименование остановлено. "
                       "Включи allow_unverified или исправь их вручную: %s"
                       % (len(uncertain),
                          "; ".join(_line(item) for item in uncertain[:6])),
                       hint="allow_unverified=true разрешает такие правки",
                       details={"reason": "unverified_references"})
    if mode == "strict" and dynamic:
        raise AppError("conflict",
                       "Найдена динамическая ссылка по строке, её нельзя "
                       "переименовать автоматически: %s. Таких мест: %d."
                       % (_line(dynamic[0]), len(dynamic)),
                       hint="Правь вручную либо повтори с mode=probable",
                       details={"reason": "dynamic_references"})
    steps = []
    for path in sorted(edits_by_path):
        if mode == 'probable' and analysis.get('kind') == 'function':
            try: plan_guards(edits_by_path[path],path,texts[path],analysis['old_name'],new_name,excluded)
            except ValueError as e: raise AppError('conflict',str(e),details={'reason':'partial_guard'}) from e
        edits = sorted(edits_by_path[path], key=lambda item: item["start"])
        steps.append(Step(op="script_edit", target=path,
                          payload={"edits": edits,
                                   "newline": (newlines or {}).get(path, "lf")},
                          expected_hash=_sha256(texts[path])))
    stats = {"files": len(steps),
        "edits": sum(len(step.payload["edits"]) for step in steps),
        "proven": analysis.get("proven_count", 0),
        "probable": analysis.get("probable_count", 0),
        "dynamic": analysis.get("dynamic_count", 0),
        "skipped": len(skipped),
    }
    return {"steps": steps, "skipped_usages": skipped,
            "risks": list(analysis.get("risks") or []), "stats": stats}


def _line(usage):
    return "%s:%s:%s" % (usage["path"], usage["line"], usage.get("column") or 1)


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _add_edit(edits_by_path, texts, usage, old_name, new_name):
    path = usage["path"]
    text = texts.get(path)
    if text is None:
        raise AppError("internal", "нет текста файла %s" % path)
    start = _offset(text, usage["line"], usage.get("column") or 1, old_name)
    edit = {"start": start, "end": start + len(old_name), "replacement": str(new_name)}
    bucket = edits_by_path.setdefault(path, [])
    if edit not in bucket:
        bucket.append(edit)


def _offset(text, line, column, name):
    """Абсолютное смещение имени: строка/колонка парсера → символы текста."""
    rows = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if line < 1 or line > len(rows):
        raise AppError("internal", "строка %d вне файла с %d строками"
                       % (line, len(rows)))
    row = rows[line - 1]
    base = sum(len(item) + 1 for item in rows[:line - 1])
    for col in (max(column - 1, 0), column, 0):
        if row[col:col + len(name)] == name:
            return base + col
    found = [match.start() for match in
             re.finditer(r"(?<!\w)%s(?!\w)" % re.escape(name), row)]
    if len(found) == 1:
        return base + found[0]
    raise AppError("internal", "имя %r не найдено в строке %d" % (name, line),
                   hint="Проверьте, что файл не менялся во время предпросмотра")
