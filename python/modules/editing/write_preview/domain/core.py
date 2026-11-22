"""modules/editing/write_preview/domain/core.py - разбор запроса предпросмотра.

Домен не знает ни про диск, ни про Godot: он проверяет вход и нормализует
`exclude`. Проверка имён/ключевых слов и `mode` живёт в компиляторе
(`editing.symbol_rename`), чтобы правила GDScript были в одном месте (R-04).
"""

import re

from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel
from python.modules.editing import symbol_rename

KINDS = ("class_name", "function", "signal", "variable", "const", "enum",
         "enum_member")
MODES = ("strict", "probable")
LOCATOR = re.compile(r"^(res://.+\.gd):(\d+)(?::(\d+))?$")
EXCLUDE = re.compile(r"^(res://.+\.gd):(\d+)$")
#: Абсолютный путь — не «кривой locator», а выход за политику путей (SEC-12).
ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|/|\\\\)")


def build_request(args):
    """Собрать запрос: имена и locator обязательны, `exclude` — список мест."""
    declaration = str(args.get("declaration") or "").strip()
    if ABSOLUTE.match(declaration):
        raise AppError("denied", "путь объявления должен быть относительным res://",
                       hint="абсолютные пути проектом не считаются")
    if not LOCATOR.match(declaration):
        raise AppError("invalid_input",
                       "declaration должен быть res://файл.gd:строка",
                       hint="получено: %r" % (declaration,))
    mode = str(args.get("mode") or "strict").strip().lower()
    allow_unverified = args.get("allow_unverified", False)
    request = {
        "kind": str(args.get("kind") or "").strip(),
        "old_name": str(args.get("old_name") or "").strip(),
        "new_name": str(args.get("new_name") or "").strip(),
        "declaration": declaration,
        "mode": mode,
        "allow_unverified": allow_unverified,
        "exclude": parse_exclude(args.get("exclude")),
    }
    symbol_rename.validate_request(request["kind"], request["old_name"],
                                   request["new_name"], mode, allow_unverified)
    return request


def parse_exclude(items):
    """`["res://a.gd:12"]` → `[(path, 12)]`; формат проверяется здесь."""
    if items is None:
        return []
    if not isinstance(items, (list, tuple)):
        raise AppError("invalid_input", "exclude должен быть массивом locator'ов",
                       hint="пример: [\"res://src/a.gd:12\"]")
    parsed = []
    for item in items:
        text = str(item or "").strip()
        match = EXCLUDE.match(text)
        if not match:
            raise AppError("invalid_input",
                           "exclude: %r не является res://файл.gd:строка" % (text,),
                           hint="exclude снимает конкретные места, а не файлы")
        parsed.append((_checked(match.group(1)), int(match.group(2))))
    return parsed


def _checked(path):
    """`exclude` не выходит за корень проекта — иначе снимать нечего (SEC-12)."""
    if normalize_rel(path[len("res://"):]) is None:
        raise AppError("invalid_input", "exclude: %r выходит за корень проекта" % (path,),
                       hint="путь задаётся относительно res://")
    return path


def analysis_args(request):
    """Аргументы чужого инструмента: поиск делает `analyze_rename` (R-04)."""
    return {"kind": request["kind"], "old_name": request["old_name"],
            "new_name": request["new_name"],
            "declaration": request["declaration"], "mode": request["mode"],
            "allow_unverified": request["allow_unverified"]}
