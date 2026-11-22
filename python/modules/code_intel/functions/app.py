"""modules/code_intel/functions/app.py - сценарий: путь → политика → порт → домен.

Только оркестрация (≤ 80 строк): разбор — в `domain/core.py`, чтение — в порту
`fs`, ошибки — `AppError` с типом (R-04, R-15). Текстовая выдача старого моста
(`path: …`, `functions (N): …`, `function: имя (lines s-e)`) не переносится:
структуру собирает модуль, канал только переводит протокол.

Порядок проверок взят из эталона (`tools/agent_bridge.py:cmd_functions`):
расширение → политика путей → существование файла. Поэтому `..` и абсолютный
путь дают `denied`, а отсутствующий `.gd` — `not_found`.
"""

import errno

from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel

from .domain import core

TOOL = "functions"
RES_PREFIX = "res://"
SCRIPT_EXT = ".gd"


def call(tool, args, ctx):
    """Обработчик инструмента `functions` для этого модуля."""
    if tool != TOOL:
        raise AppError("unknown_tool", "модуль code_intel.functions не владеет %r" % (tool,),
                       hint="Список инструментов даёт tools/list")
    rel = _relative(args.get("path"))
    _check_script(rel)
    _check_policy(rel, ctx)
    text = _read(ctx, rel)
    names = [str(name) for name in (args.get("names") or ())]
    if not names:
        return {"path": RES_PREFIX + rel, "names": core.list_names(text)}
    found, missing = core.extract(text, names)
    return {"path": RES_PREFIX + rel, "functions": found, "missing": missing}


def _relative(path):
    text = str(path or "").strip()
    if text.startswith(RES_PREFIX):
        text = text[len(RES_PREFIX):]
    rel = normalize_rel(text)
    if rel is None:
        raise AppError("denied", "путь вне проекта",
                       hint="Путь задаётся как res://scripts/player.gd или относительно корня")
    return rel


def _check_script(rel):
    if not rel.lower().endswith(SCRIPT_EXT):
        raise AppError("invalid_input", "functions работает только с .gd",
                       hint="Для сцен и ресурсов существуют другие инструменты")


def _check_policy(rel, ctx):
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError("denied", reason,
                       hint="Аддоны и исходники агента закрыты политикой путей")


def _read(ctx, rel):
    shown = RES_PREFIX + rel
    try:
        return ctx.port("fs").read_text(rel)
    except FileNotFoundError:
        raise AppError("not_found", "файл не найден: %s" % shown,
                       hint="Проверьте путь: список файлов проекта даёт search") from None
    except PermissionError:
        raise AppError("denied", "чтение файла запрещено политикой путей: %s" % shown) from None
    except OSError as exc:
        if exc.errno == errno.EFBIG:
            raise AppError("not_found", "файл больше лимита чтения: %s" % shown,
                           hint="Эталон отказывал тем же классом (file too large)") from None
        raise

