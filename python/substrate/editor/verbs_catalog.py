"""substrate/editor/verbs_catalog.py - словарь примитивов моста (R-14, ADR-0007).

Единственное место, где читается `contract/editor_verbs.json`: схемами ответа
пользуется валидация, версией - handshake. Сети и сокетов здесь нет, смысла
примитивов тоже: только словарь и его версия.
"""

import json
from pathlib import Path

from python.kernel.errors import AppError

#: Файл словаря от корня плагина.
CONTRACT = Path(__file__).resolve().parents[3] / "contract" / "editor_verbs.json"


def load():
    """Словарь целиком; нет файла или мусор - отказ, а не пустой словарь."""
    try:
        with CONTRACT.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError:
        raise AppError("unavailable", "нет словаря примитивов моста",
                       hint="Ожидался %s" % CONTRACT.name,
                       details={"reason": "no_contract"}) from None
    except ValueError:
        raise AppError("internal", "словарь примитивов моста не JSON",
                       details={"reason": "bad_contract"}) from None
    if not isinstance(data, dict):
        raise AppError("internal", "словарь примитивов моста испорчен",
                       details={"reason": "bad_contract"})
    return data


def version():
    """`verbs_version` контракта - версия, которую обязан назвать сервер."""
    raw = load().get("verbs_version")
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1:
        raise AppError("internal", "verbs_version в словаре не целое ≥ 1",
                       details={"reason": "bad_contract"})
    return raw


def verbs():
    """Объявленные примитивы как есть (порядок словаря сохраняется)."""
    items = load().get("verbs")
    return tuple(item for item in items or () if isinstance(item, dict))


def names():
    """Имена примитивов - для сверки с обработчиками и для тестов."""
    return tuple(str(item.get("name") or "") for item in verbs())


def result_schema(name):
    """`result_schema` примитива; неизвестный примитив - отказ `unknown_verb`."""
    for item in verbs():
        if item.get("name") == name:
            schema = item.get("result_schema")
            if not isinstance(schema, dict):
                raise AppError("internal", "у %r нет result_schema" % (name,),
                               details={"reason": "bad_contract"})
            return schema
    raise AppError("engine_down", "мост не знает примитив %r" % (name,),
                   hint="Словарь примитивов: contract/editor_verbs.json",
                   details={"reason": "unknown_verb"})
