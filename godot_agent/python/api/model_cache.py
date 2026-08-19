# -*- coding: utf-8 -*-
"""Кэш списков моделей провайдеров — отдельным файлом от настроек.

ЗАЧЕМ ЭТО НУЖНО. Панель ищет модель по названию СРАЗУ У ВСЕХ провайдеров:
человек знает, что ему нужен «kimi» или «deepseek», но не знает, кто из
провайдеров его отдаёт. Для такого поиска нужны сами списки моделей, а не
только их количество, — и нужны они по всем провайдерам одновременно, то есть
опрашивать сервисы в момент набора текста нельзя.

ПОЧЕМУ ОТДЕЛЬНЫЙ ФАЙЛ, А НЕ api_keys.json. Файл настроек перечитывается
целиком почти на каждое обращение к нему (api_keys._load вызывается по
несколько раз за один HTTP-запрос: ключ, модель, адрес, наблюдения). Пятьсот
идентификаторов моделей в том же файле означали бы разбор лишних десятков
килобайт JSON на каждое такое обращение. Вторая причина важнее: в настройках
лежат КЛЮЧИ, и чем меньше кода трогает этот файл, тем меньше шансов, что
секрет уедет туда, где его не ждут.

СЕКРЕТОВ ЗДЕСЬ НЕТ: только идентификаторы моделей, признак бесплатности,
дополнения из каталога models.dev (цена, окно контекста, поддержка инструментов)
и время получения списка. Файл можно показывать и пересылать целиком.
"""
import json
import os
import time

import api_keys

_FILE_NAME = "models_cache.json"

# Ограничения на случай сервиса, отдающего неправдоподобно длинный ответ. Файл
# кэша читается панелью целиком, и превращать его в мегабайты из-за одного
# провайдера с мусором в /models незачем. У самого крупного из известных
# (OpenRouter) моделей чуть больше четырёхсот.
MAX_PER_PROVIDER = 2000
MAX_ID_LEN = 200

# ДОПОЛНЕНИЯ ИЗ КАТАЛОГА models.dev, которые запись модели проносит через кэш.
# Живой /models их не присылает (у Opencode Zen там вообще только id), а панель
# показывает их в подсказке на кнопке модели — значит они обязаны переживать
# запись на диск. Набор ЗАКРЫТЫЙ: пропускать сюда всё подряд из чужого ответа
# значит однажды сложить в файл описание модели на три абзаца, а этот файл
# читается целиком на каждый поиск.
#
# catalog_free держится ОТДЕЛЬНО от free намеренно: free измерен по ответу
# провайдера, catalog_free — по справочнику, и на карточке они подписаны
# разными словами. Свести их в одно поле значит потерять ответ на вопрос, кто
# именно утверждает бесплатность.
_CATALOG_NUM_FIELDS = ("cost_in", "cost_out")
_CATALOG_INT_FIELDS = ("context", "max_output")
_CATALOG_BOOL_FIELDS = ("tool_call", "catalog_free")


def cache_path():
    return os.path.join(api_keys.config_dir(), _FILE_NAME)


def _clean_records(records):
    """Список моделей в известном виде: [{"id": str, "free": bool, ...}, ...].

    Через эту функцию проходят и запись, и чтение — иначе набор полей в файле и
    набор полей, уходящий в панель, со временем разъедутся.

    Дополнения из каталога (см. _CATALOG_* выше) переносятся, ЕСЛИ они есть в
    записи, и не выдумываются, если их нет: отсутствие цены в каталоге — это
    «про цену этой модели ничего не известно», а ноль вместо неё означал бы
    «бесплатная».
    """
    out = []
    seen = set()
    for rec in list(records or [])[:MAX_PER_PROVIDER * 2]:
        extra = {}
        if isinstance(rec, dict):
            mid = str(rec.get("id") or "").strip()
            free = bool(rec.get("free"))
            for f in _CATALOG_NUM_FIELDS:
                if isinstance(rec.get(f), (int, float)) and not isinstance(rec.get(f), bool):
                    extra[f] = float(rec[f])
            for f in _CATALOG_INT_FIELDS:
                if isinstance(rec.get(f), (int, float)) and not isinstance(rec.get(f), bool):
                    val = int(rec[f])
                    if val > 0:
                        extra[f] = val
            for f in _CATALOG_BOOL_FIELDS:
                if isinstance(rec.get(f), bool):
                    extra[f] = bool(rec[f])
        else:
            # Строка вместо записи: так выглядит зашитый в реестр список
            # моделей. Про бесплатность в нём ничего не сказано, и придумывать
            # её здесь нельзя — «бесплатная» по догадке это обещание за сервис.
            mid, free = str(rec or "").strip(), False
        if not mid or len(mid) > MAX_ID_LEN or mid in seen:
            continue
        seen.add(mid)
        item = {"id": mid, "free": free}
        item.update(extra)
        out.append(item)
        if len(out) >= MAX_PER_PROVIDER:
            break
    return out


def _load():
    """Кэш с диска. Любая проблема чтения — пустой кэш: поиск моделей это
    удобство, и ронять из-за него сервер или настройки нельзя."""
    p = cache_path()
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("[model_cache] Кэш моделей не читается (%s) — считаю его пустым." % e)
        return {}
    if not isinstance(data, dict):
        return {}
    src = data.get("providers")
    if not isinstance(src, dict):
        return {}
    out = {}
    for pid, rec in src.items():
        if not isinstance(rec, dict):
            continue
        models = _clean_records(rec.get("models"))
        if not models:
            continue
        try:
            at = float(rec.get("at") or 0.0)
        except Exception:
            at = 0.0
        out[str(pid)] = {"models": models, "at": at}
    return out


def _save(cache):
    """Запись через временный файл + os.replace: обрыв на середине не оставляет
    полуфабрикат вместо кэша."""
    p = cache_path()
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"providers": cache}, f, ensure_ascii=False)
        os.replace(tmp, p)
        return True
    except Exception as e:
        print("[model_cache] Не удалось сохранить кэш моделей (%s)" % e)
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


def put_bulk(mapping):
    """Списки моделей сразу нескольких провайдеров — одной записью файла.

    Обход провайдеров касается нескольких сервисов за один запрос панели, а
    «прочитать файл, изменить, записать» на каждого из них — это несколько
    шансов потерять чужое изменение, пришедшее в это же время (сервер поднят с
    threaded=True).

    Провайдер с ПУСТЫМ списком удаляется из кэша, а не остаётся с прежним:
    пустой ответ /models значит «моделей сейчас нет», и показывать вместо этого
    прошлогодний список — врать о том, что можно выбрать.
    """
    if not isinstance(mapping, dict) or not mapping:
        return False
    cache = _load()
    now = time.time()
    changed = False
    for provider_id, records in mapping.items():
        pid = str(provider_id or "").strip()
        if not pid:
            continue
        models = _clean_records(records)
        if models:
            cache[pid] = {"models": models, "at": now}
        elif pid in cache:
            del cache[pid]
        else:
            continue
        changed = True
    if not changed:
        return False
    return _save(cache)


def put(provider_id, records):
    """Список моделей одного провайдера."""
    return put_bulk({provider_id: records})


def get(provider_id):
    """Модели провайдера: [{"id", "free", ...}, ...]. Нет данных — пустой список.

    Кроме id и free запись может нести дополнения из каталога models.dev — но
    только те, которые каталог действительно знает про эту модель."""
    return (_load().get(str(provider_id)) or {}).get("models") or []


def index():
    """Все известные списки: {provider_id: [{"id", "free", ...}, ...]}.

    Именно такой вид уходит в панель: она ищет модель по всем провайдерам сразу
    и должна знать, у КОГО нашлось совпадение.
    """
    return {pid: rec["models"] for pid, rec in _load().items()}


def forget(provider_id):
    """Убирает провайдера из кэша (например, когда сменился его адрес)."""
    cache = _load()
    pid = str(provider_id or "").strip()
    if pid not in cache:
        return False
    del cache[pid]
    return _save(cache)
