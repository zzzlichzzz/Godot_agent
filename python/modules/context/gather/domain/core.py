"""modules/context/gather/domain/core.py - правила сборки пакета контекста.

Домен не знает ни про диск, ни про реестр: он проверяет запрос, отбирает имена
секций и складывает фрагменты в ответ. Чтение файлов и вызов вкладов — в `app.py`
(R-11: в `domain/` нет ни `os`, ни `pathlib`, ни `json.load`).
"""

from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel

#: Встроенные секции: их собирает владелец, вкладов для них нет.
BUILTIN_SECTIONS = ("project", "tools")
#: Зарезервировано ADR-0004: эти секции придут вкладами других модулей.
RESERVED_SECTIONS = ("editor", "runtime", "architecture")
#: Предел числа секций за один вызов: бюджет ответа, а не форма запроса.
MAX_SECTIONS = 8
#: Стоимость ответа: без живого редактора и рантайма сборка дешёвая.
COST = "light"
#: Причина отказа вклада, когда модуля-вклада нет вовсе.
NO_MODULE = "no_module"


def known_sections(contributions=()):
    """Что владелец умеет отдавать: встроенные + зарезервированные + имена вкладов."""
    names = list(BUILTIN_SECTIONS) + list(RESERVED_SECTIONS)
    for contribution in contributions or ():
        name = str(getattr(contribution, "name", "") or "")
        if name and name not in names:
            names.append(name)
    return tuple(names)


def build_request(args, policy=None, contributions=()):
    """Проверить вход и вернуть `{"sections": [...], "path": <относительный|None>}`.

    Неизвестное имя секции — отказ всего вызова, а не «соберём что сможем»: иначе
    опечатка в имени неотличима от секции, которой просто нет в окружении (она
    попадает в `unavailable` с причиной).
    """
    known = known_sections(contributions)
    raw = args.get("sections")
    if raw is None:
        return {"sections": list(known), "path": _target(args.get("path"), policy)}
    if not isinstance(raw, (list, tuple)):
        raise AppError("invalid_input", "sections должен быть массивом имён",
                       hint="пример: [\"project\", \"tools\"]",
                       details={"reason": "invalid_sections"})
    if len(raw) > MAX_SECTIONS:
        raise AppError("invalid_input", "слишком много секций: %d" % (len(raw),),
                       hint="предел — %d секций за вызов" % (MAX_SECTIONS,),
                       details={"reason": "too_large"})
    names = []
    for item in raw:
        name = str(item or "").strip()
        if name not in known:
            raise AppError("invalid_input", "неизвестная секция: %r" % (name,),
                           hint="известные секции: %s" % ", ".join(known),
                           details={"reason": "unknown_section"})
        if name in names:
            raise AppError("invalid_input", "секция %r запрошена дважды" % (name,),
                           hint="имена секций уникальны: повторов быть не должно",
                           details={"reason": "duplicate_section"})
        names.append(name)
    if not names:
        raise AppError("invalid_input", "нужна хотя бы одна секция",
                       hint="sections: 1…%d имён" % (MAX_SECTIONS,),
                       details={"reason": "empty_sections"})
    return {"sections": names, "path": _target(args.get("path"), policy)}


def _target(path, policy):
    """Цель вызова: относительный путь внутри проекта или `None`."""
    text = str(path or "").strip()
    if not text:
        return None
    if text.startswith("res://"):
        text = text[len("res://"):]
    rel = normalize_rel(text)
    if rel is None:
        raise AppError("denied", "цель вне проекта",
                       hint="путь задаётся относительно res://",
                       details={"reason": "path_escape"})
    reason = policy.deny_reason(rel) if policy is not None else ""
    if reason:
        raise AppError("denied", "цель закрыта политикой: %s" % (reason,),
                       hint="секции читают только проект",
                       details={"reason": "denied"})
    return rel


def project_section(root, project_file):
    """Секция `project`: где мы находимся. `engine: null` — движка в профиле нет."""
    return {"root": str(root or ""), "project_file": project_file,
            "engine": None, "source": "fs"}


def tools_section(rows):
    """Секция `tools`: сколько инструментов у агента и с какими эффектами."""
    effects = {}
    for name, effect in rows or ():
        effects[str(name)] = str(effect)
    names = sorted(effects)
    return {"count": len(names), "names": names,
            "effects": {name: effects[name] for name in names}}


def find_contribution(contributions, name):
    """Вклад по имени секции: владелец ищет его в реестре, а не импортом (R-11)."""
    for contribution in contributions or ():
        if str(getattr(contribution, "name", "") or "") == str(name):
            return contribution
    return None


def assemble(fragments, missing=(), cost=COST):
    """Собрать ответ: секции в порядке запроса, списки — по алфавиту."""
    sections = dict(fragments or {})
    absent = [{"name": str(item.get("name")), "reason": str(item.get("reason"))}
              for item in missing or ()]
    absent.sort(key=lambda item: (item["name"], item["reason"]))
    return {"sections": sections, "available": sorted(sections),
            "unavailable": absent, "cost": cost}

