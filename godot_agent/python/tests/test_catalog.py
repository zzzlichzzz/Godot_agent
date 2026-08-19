# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
u"""Тесты каталога models.dev — ВТОРИЧНОГО источника сведений о моделях.

ЧТО ЗДЕСЬ ПРОВЕРЯЕТСЯ ПО СУЩЕСТВУ. Каталог обязан только ДОПОЛНЯТЬ живой ответ
провайдера и никогда его не подменять: живой /models говорит, что доступно
ЭТОМУ ключу, каталог — что существует в мире. Замерено 19.08.2026: у Opencode
Zen каталог знает 91 модель, а живой /models отдаёт 62. Если каталог хоть раз
перебьёт живое поле, пользователь выберет модель, которой ему не отдают, и
получит 404 от провайдера.

СЕТИ ЗДЕСЬ НЕТ. Адрес каталога — константа модуля (catalog.CATALOG_URL) именно
для того, чтобы её можно было подменить локальным HTTP-сервером: прогон не
должен падать на машине без интернета и не должен стучаться в чужой сервис при
каждом запуске. Заодно локальный сервер даёт то, чего от настоящего не
добиться: 304 по требованию, битый JSON и точный счёт запросов.

ВАЖНО: папка настроек подменяется через GODOT_AGENT_CONFIG_DIR ДО импорта
модулей, иначе прогон писал бы в настоящий %APPDATA%\\Godot_agent.
"""
import gzip
import json
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CFG = tempfile.mkdtemp(prefix="agent_cfg_modelsdev_")
_os0.environ["GODOT_AGENT_CONFIG_DIR"] = CFG

import api_keys
import catalog
import model_cache
import providers as P

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


# ---------------------------------------------------------------------------
# Поддельный models.dev
#
# Форма записи повторяет настоящую (замерено живым запросом 19.08.2026):
# провайдер — {id, name, api, env, models}, модель — {cost:{input,output,
# cache_read}, limit:{context,output}, tool_call, modalities, description, ...}.
# Лишние поля здесь НАМЕРЕННО: тест проверяет, что в кэш они не попадают.
# ---------------------------------------------------------------------------

FAKE = {
    "openrouter": {
        "id": "openrouter", "name": "OpenRouter",
        "api": "https://openrouter.ai/api/v1",
        "env": ["OPENROUTER_API_KEY"],
        "models": {
            "vendor/paid": {
                "id": "vendor/paid", "name": "Paid",
                "description": u"Описание на три абзаца, которого в кэше быть не должно",
                "family": "vendor", "attachment": False, "reasoning": True,
                "modalities": {"input": ["text"], "output": ["text"]},
                "tool_call": True, "structured_output": True,
                "release_date": "2026-01-01", "open_weights": False,
                "cost": {"input": 1.25, "output": 2.5, "cache_read": 0.1},
                "limit": {"context": 128000, "output": 32000},
            },
            "vendor/gift:free": {
                "id": "vendor/gift:free", "tool_call": False,
                "cost": {"input": 0, "output": 0},
                "limit": {"context": 8000, "output": 4000},
            },
            # Нулевая цена БЕЗ суффикса в имени — то, чего наша эвристика по
            # ответу провайдера не видит. Настоящий случай: Opencode Zen
            # big-pickle (замерено).
            "vendor/quiet-gift": {
                "id": "vendor/quiet-gift", "tool_call": True,
                "cost": {"input": 0.0, "output": 0.0},
                "limit": {"context": 65536, "output": 8192},
            },
            # Поля cost нет вовсе: у настоящих провайдеров таких 15
            # (openrouter/auto, whisper-*, veo-*). Бесплатной такую объявлять
            # НЕЛЬЗЯ.
            "vendor/nocost": {"id": "vendor/nocost", "limit": {"context": 4096}},
            # Цена с ярусами по размеру контекста: верхний уровень input/output
            # заполнен базовым тарифом, и берём именно его.
            "vendor/tiered": {
                "id": "vendor/tiered", "tool_call": True,
                "cost": {"input": 5, "output": 30, "cache_read": 0.5,
                         "tiers": [{"input": 10, "output": 45,
                                    "tier": {"type": "context", "size": 272000}}],
                         "context_over_200k": {"input": 10, "output": 45}},
                "limit": {"context": 272000, "output": 128000},
            },
            # СНЯТАЯ С ОБСЛУЖИВАНИЯ. У настоящего Opencode Zen таких 29 из 91, и
            # это РОВНО те, которых нет в живом /models. Не читая status, легко
            # решить, что каталог завышает число моделей.
            "vendor/retired": {
                "id": "vendor/retired", "status": "deprecated", "tool_call": True,
                "cost": {"input": 1, "output": 2},
                "limit": {"context": 100000, "output": 8000},
            },
            "vendor/beta": {
                "id": "vendor/beta", "status": "beta", "tool_call": True,
                "cost": {"input": 1, "output": 2},
                "limit": {"context": 100000},
            },
            # Значение, которого в схеме каталога нет: молча пропускать слово,
            # которого мы не понимаем, и показывать его пользователю нельзя.
            "vendor/odd-status": {
                "id": "vendor/odd-status", "status": "выдуманный",
                "limit": {"context": 100000},
            },
        },
    },
    # У нас "gemini", у них "google" — соответствие идентификаторов.
    "google": {
        "id": "google", "name": "Google", "api": None,
        "env": ["GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY", "GEMINI_API_KEY"],
        "models": {"gemini-9-pro": {"cost": {"input": 2, "output": 12},
                                    "limit": {"context": 1000000, "output": 65536},
                                    "tool_call": True}},
    },
    # У нас "opencode_zen", у них "opencode".
    "opencode": {
        "id": "opencode", "name": "OpenCode Zen",
        "api": "https://opencode.ai/zen/v1", "env": ["OPENCODE_API_KEY"],
        "models": {"big-pickle": {"cost": {"input": 0, "output": 0},
                                  "limit": {"context": 200000},
                                  "tool_call": True}},
    },
    "deepseek": {
        "id": "deepseek", "name": "DeepSeek",
        # У настоящего каталога адрес БЕЗ "/v1", а у нас в реестре с ним:
        # расхождение печатается в журнал, но реестр не меняется.
        "api": "https://api.deepseek.com", "env": ["DEEPSEEK_API_KEY"],
        "models": {"deepseek-chat": {"cost": {"input": 0.28, "output": 0.42},
                                     "limit": {"context": 128000, "output": 8192},
                                     "tool_call": True}},
    },
    "groq": {"id": "groq", "name": "Groq", "api": None, "env": ["GROQ_API_KEY"],
             "models": {"llama-9-70b": {"cost": {"input": 0.59, "output": 0.79},
                                        "limit": {"context": 131072}}},
    },
    # Один из 185 чужих провайдеров: в кэш он попасть НЕ должен. Список из 192
    # записей, где проверено ноль, хуже семи разобранных — см. catalog.py.
    "stranger-ai": {
        "id": "stranger-ai", "name": "Stranger", "api": "https://stranger.example",
        "env": ["STRANGER_API_KEY"],
        "models": {"stranger/model": {"cost": {"input": 1, "output": 1}}},
    },
}


class Handler(BaseHTTPRequestHandler):
    # Что отдавать: "ok" | "garbage" | "html" | "500"
    mode = "ok"
    etag = 'W/"fake-etag-1"'
    hits = []          # тела запросов: сколько раз ходили в сеть
    headers_seen = []  # заголовки: проверяем, что ключей в них нет

    def log_message(self, *a):
        pass

    def do_GET(self):
        Handler.hits.append(self.path)
        Handler.headers_seen.append({k.lower(): v for k, v in self.headers.items()})
        if Handler.mode == "500":
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if Handler.mode == "html":
            # ЛОВУШКА настоящего models.dev: /api/<id>.json отвечает 200 с HTML
            # самого сайта. Ответ «успешный», а данных в нём нет.
            body = b"<!DOCTYPE html>\n<html><head><title>Models.dev</title></head>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if Handler.mode == "garbage":
            body = b"{ this is not json at all"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if (self.headers.get("If-None-Match") or "") == Handler.etag:
            # Настоящий models.dev отдаёт ETag и понимает If-None-Match;
            # Last-Modified у него нет. urllib считает 304 ОШИБКОЙ — без
            # правильной обработки каждая проверка свежести выглядела бы как
            # неудача загрузки каталога.
            self.send_response(304)
            self.send_header("ETag", Handler.etag)
            self.end_headers()
            return
        raw = json.dumps(FAKE).encode("utf-8")
        # Настоящий каталог отдаёт gzip и urllib его НЕ распаковывает сам —
        # 399 КБ против 4.0 МБ (замерено). Поддельный сервер обязан вести себя
        # так же, иначе тест не поймает пропущенный gzip.decompress.
        if "gzip" in (self.headers.get("Accept-Encoding") or ""):
            raw = gzip.compress(raw)
            enc = "gzip"
        else:
            enc = ""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if enc:
            self.send_header("Content-Encoding", enc)
        self.send_header("ETag", Handler.etag)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

# Подмена адреса каталога — ровно то, ради чего он константа модуля.
REAL_URL = catalog.CATALOG_URL
catalog.CATALOG_URL = "http://127.0.0.1:%d/api.json" % PORT
check(u"настоящий адрес каталога — единственный эндпоинт models.dev",
      REAL_URL == "https://models.dev/api.json", REAL_URL)


def hits():
    return len(Handler.hits)


# ---------------------------------------------------------------------------
# 1) Первая загрузка: разбор, соответствие идентификаторов, отбор своих
# ---------------------------------------------------------------------------
check(u"до первой загрузки каталог считается устаревшим", catalog.is_stale() is True)
check(u"до первой загрузки возраст неизвестен, а не равен нулю",
      catalog.age() == -1.0)
check(u"о моделях провайдера ничего не известно", catalog.get("openrouter") == {})

before = hits()
updated, err = catalog.refresh()
check(u"каталог загрузился", updated is True and err == "", (updated, err))
check(u"загрузка — это ровно один запрос", hits() - before == 1, hits() - before)

orec = catalog.get("openrouter")
check(u"модели провайдера разобраны",
      set(orec) == {"vendor/paid", "vendor/gift:free", "vendor/quiet-gift",
                    "vendor/nocost", "vendor/tiered", "vendor/retired",
                    "vendor/beta", "vendor/odd-status"}, sorted(orec))
check(u"gzip распакован (иначе разбора бы не было)", bool(orec))

# ---------------------------------------------------------------------------
# 1а) ПОЛЕ status: alpha / beta / deprecated
#
# У настоящего Opencode Zen 29 записей из 91 помечены deprecated, и это РОВНО
# те, которых нет в живом /models (сверено, 29 из 29). Не читая status, легко
# решить, что каталог завышает число моделей, — именно так и вышло сначала.
# ---------------------------------------------------------------------------
check(u"status снятой модели прочитан",
      catalog.model_info("openrouter", "vendor/retired").get("status")
      == catalog.STATUS_DEPRECATED)
check(u"status беты прочитан",
      catalog.model_info("openrouter", "vendor/beta").get("status") == "beta")
check(u"у обычной модели статуса нет, а не пустая строка",
      "status" not in catalog.model_info("openrouter", "vendor/paid"))
check(u"неизвестное значение status отброшено, а не показано пользователю",
      "status" not in catalog.model_info("openrouter", "vendor/odd-status"))

# Соответствие идентификаторов применяется ОДИН РАЗ при записи: наружу и в файл
# уходят НАШИ идентификаторы, чтобы каждое место чтения не помнило про
# переименование.
check(u"наш «gemini» находит их «google»",
      "gemini-9-pro" in catalog.get("gemini"))
check(u"наш «opencode_zen» находит их «opencode»",
      "big-pickle" in catalog.get("opencode_zen"))
check(u"чужой идентификатор провайдера наружу не выдаётся",
      catalog.get("google") == {} and catalog.get("opencode") == {})
check(u"соответствие покрывает ровно наши идентификаторы",
      set(catalog.PROVIDER_MAP) == {"openrouter", "groq", "gemini",
                                    "opencode_zen", "deepseek"},
      sorted(catalog.PROVIDER_MAP))

# Провайдер, которого в каталоге нет, обязан быть перечислен ЯВНО: иначе
# «каталог про него не знает» и «про него забыли здесь» выглядят одинаково.
covered = set(catalog.PROVIDER_MAP) | set(catalog.NOT_IN_CATALOG)
check(u"каждый провайдер реестра либо есть в каталоге, либо отсутствует с причиной",
      set(P.provider_ids()) <= covered,
      sorted(set(P.provider_ids()) - covered))
check(u"причина отсутствия записана словами",
      all(bool(v) for v in catalog.NOT_IN_CATALOG.values()))

# ---------------------------------------------------------------------------
# 2) В кэш попали ТОЛЬКО наши провайдеры и ТОЛЬКО нужные поля
#
# 4 МБ полного каталога превращаются в десятки килобайт именно этим отбором.
# ---------------------------------------------------------------------------
with open(catalog.catalog_path(), "r", encoding="utf-8") as f:
    on_disk_raw = f.read()
on_disk = json.loads(on_disk_raw)
check(u"кэш каталога лежит ОТДЕЛЬНО от файла с ключами и от кэша списков",
      catalog.catalog_path() != api_keys.config_path()
      and catalog.catalog_path() != model_cache.cache_path())
check(u"ключи кэша — НАШИ идентификаторы провайдеров",
      set(on_disk["providers"]) == {"openrouter", "groq", "gemini",
                                    "opencode_zen", "deepseek"},
      sorted(on_disk["providers"]))
check(u"МОДЕЛИ чужих провайдеров в кэш не попали — их там 5555 на 680 КБ",
      "stranger/model" not in on_disk_raw
      and "stranger-ai" not in (on_disk.get("providers") or {}))
# А вот МЕТАДАННЫЕ чужого провайдера попасть должны: из них и собирается полный
# список выбора. Модели у него появятся только если пользователь его выберет.
check(u"метаданные чужого провайдера в кэше есть — он пригоден для выбора",
      "stranger-ai" in (on_disk.get("catalog_providers") or {}))
paid = on_disk["providers"]["openrouter"]["models"]["vendor/paid"]
check(u"в записи модели ровно нужные поля",
      set(paid) == {"cost_in", "cost_out", "context", "max_output", "tool_call"},
      sorted(paid))
check(u"у снятой модели к ним добавляется только status",
      set(on_disk["providers"]["openrouter"]["models"]["vendor/retired"])
      == {"cost_in", "cost_out", "context", "max_output", "tool_call", "status"})
check(u"цена и лимиты разобраны верно",
      paid["cost_in"] == 1.25 and paid["cost_out"] == 2.5
      and paid["context"] == 128000 and paid["max_output"] == 32000
      and paid["tool_call"] is True)
check(u"описание модели в кэш не поехало",
      u"трёх абзацев" not in on_disk_raw and "description" not in on_disk_raw)
check(u"необязательные подробности каталога отброшены",
      "modalities" not in on_disk_raw and "cache_read" not in on_disk_raw
      and "release_date" not in on_disk_raw)
check(u"у модели без цены полей цены НЕТ, а не нули",
      set(catalog.model_info("openrouter", "vendor/nocost")) == {"context"},
      catalog.model_info("openrouter", "vendor/nocost"))
check(u"у цены с ярусами взят базовый тариф верхнего уровня",
      catalog.model_info("openrouter", "vendor/tiered").get("cost_in") == 5.0)
check(u"кэш каталога — десятки килобайт, а не мегабайты",
      len(on_disk_raw.encode("utf-8")) < 200 * 1024,
      len(on_disk_raw.encode("utf-8")))

# ---------------------------------------------------------------------------
# 3) Бесплатность ПО КАТАЛОГУ — отдельное утверждение
# ---------------------------------------------------------------------------
check(u"нулевая цена в каталоге — бесплатная",
      catalog.is_free(catalog.model_info("openrouter", "vendor/gift:free")) is True)
check(u"нулевая цена БЕЗ суффикса тоже бесплатная (то, чего не видит эвристика по имени)",
      catalog.is_free(catalog.model_info("openrouter", "vendor/quiet-gift")) is True)
check(u"платная модель платная",
      catalog.is_free(catalog.model_info("openrouter", "vendor/paid")) is False)
check(u"НЕИЗВЕСТНАЯ цена — это не бесплатно",
      catalog.is_free(catalog.model_info("openrouter", "vendor/nocost")) is False)
check(u"мусор вместо записи не объявляется бесплатным",
      catalog.is_free(None) is False and catalog.is_free({"cost_in": "0"}) is False)

# ---------------------------------------------------------------------------
# 4) Точное совпадение идентификатора: суффиксы не приравниваются к базовой модели
#
# Замерено: у OpenRouter 62 модели из 415 не нашлись в каталоге, и все они —
# варианты с суффиксом «:batch», у которых ДРУГОЙ тариф. Подставить им цену
# базовой модели значит показать неверную цену с подписью «по каталогу».
# ---------------------------------------------------------------------------
check(u"варианту с суффиксом цена базовой модели НЕ подставляется",
      catalog.model_info("openrouter", "vendor/paid:batch") == {})
check(u"неизвестной модели — пустой словарь, а не догадка",
      catalog.model_info("openrouter", "нет-такой") == {}
      and catalog.model_info("нет-провайдера", "vendor/paid") == {})

# ---------------------------------------------------------------------------
# 5) enrich(): ЗАПОЛНЯЕТ отсутствующее и НИКОГДА не заменяет живое
# ---------------------------------------------------------------------------
live = [
    {"id": "vendor/paid", "free": False},
    {"id": "vendor/quiet-gift", "free": False},
    {"id": "vendor/gift:free", "free": True},
    # Модели, которой в каталоге нет: живой ответ первичен, и она обязана
    # остаться в списке — просто без цен и лимитов.
    {"id": "vendor/brand-new", "free": False},
]
rich = catalog.enrich("openrouter", live)
by_id = {r["id"]: r for r in rich}
check(u"обогащение не потеряло ни одной живой модели", len(rich) == len(live))
check(u"цена и контекст из каталога добавлены",
      by_id["vendor/paid"]["cost_in"] == 1.25
      and by_id["vendor/paid"]["context"] == 128000
      and by_id["vendor/paid"]["tool_call"] is True)
check(u"признак бесплатности каталога лежит ОТДЕЛЬНЫМ полем",
      by_id["vendor/quiet-gift"]["catalog_free"] is True
      and by_id["vendor/quiet-gift"]["free"] is False)
check(u"живой признак бесплатности каталогом НЕ переписан",
      by_id["vendor/paid"]["free"] is False
      and by_id["vendor/gift:free"]["free"] is True)
check(u"модель, которой нет в каталоге, осталась без дополнений",
      set(by_id["vendor/brand-new"]) == {"id", "free"},
      sorted(by_id["vendor/brand-new"]))
check(u"исходный список не изменён на месте",
      all(set(r) == {"id", "free"} for r in live))

# КАЖДОЕ дописанное поле названо. Без этого списка подпись «по каталогу
# models.dev» встала бы и под живой ценой провайдера — а она точнее: замерено,
# что у moonshotai/kimi-k2.6 каталог отстал и завышал цену на 47% против живого
# ответа OpenRouter.
check(u"каталог перечислил, что дописал",
      set(by_id["vendor/paid"]["from_catalog"])
      == {"cost_in", "cost_out", "context", "max_output", "tool_call"})
check(u"у модели без дополнений списка нет вовсе",
      "from_catalog" not in by_id["vendor/brand-new"])
mixed = catalog.enrich("openrouter", [{"id": "vendor/paid", "free": False,
                                       "cost_in": 7.0, "context": 999}])[0]
check(u"живые поля не перебиты И не приписаны каталогу",
      mixed["cost_in"] == 7.0 and mixed["context"] == 999
      and set(mixed["from_catalog"]) == {"cost_out", "max_output", "tool_call"})

# Снятая модель обязана дойти до панели помеченной: модель закрепляется за
# чатом, и «её вот-вот уберут» человек должен увидеть ДО выбора.
retired = catalog.enrich("openrouter", [{"id": "vendor/retired", "free": False}])[0]
check(u"снятая модель помечена и словом, и признаком",
      retired["deprecated"] is True
      and retired["status"] == catalog.STATUS_DEPRECATED)
beta = catalog.enrich("openrouter", [{"id": "vendor/beta", "free": False}])[0]
check(u"бета помечена статусом, но НЕ снятой",
      beta["status"] == "beta" and "deprecated" not in beta)
check(u"обычная модель не помечена ни статусом, ни снятием",
      "status" not in by_id["vendor/paid"]
      and "deprecated" not in by_id["vendor/paid"])

# Живое поле выигрывает всегда: сейчас /models ни у кого из наших не присылает
# context, но когда пришлёт — каталог не должен его перебивать.
conflict = catalog.enrich("openrouter", [{"id": "vendor/paid", "free": False,
                                          "context": 999, "cost_in": 7.0}])
check(u"живое поле каталогом не перезаписывается",
      conflict[0]["context"] == 999 and conflict[0]["cost_in"] == 7.0)

check(u"строка вместо записи тоже обогащается",
      catalog.enrich("openrouter", ["vendor/paid"])[0]["context"] == 128000)
check(u"без данных о провайдере обогащение просто ничего не добавляет",
      catalog.enrich("custom", [{"id": "x", "free": False}])
      == [{"id": "x", "free": False}])

check(u"бесплатные по каталогу считаются отдельным счётчиком",
      catalog.count_free("openrouter", rich) == 2,
      catalog.count_free("openrouter", rich))
check(u"счёт по необогащённым записям даёт ноль, а не догадку",
      catalog.count_free("openrouter", live) == 0)
# -1, а НЕ ноль: «каталог проверил и бесплатных не нашёл» и «каталог про них
# ничего не сказал» — разные сведения, и вторым нельзя выдавать первое.
check(u"про провайдера, которого каталог не знает, счётчик молчит",
      catalog.count_free("custom", rich) == -1)
check(u"если ни одна живая модель не нашлась в каталоге — тоже молчит",
      catalog.count_free("openrouter",
                         [{"id": "vendor/paid:batch", "free": False}]) == -1)

# ---------------------------------------------------------------------------
# 6) Свежий кэш — НИ ОДНОГО запроса в сеть
# ---------------------------------------------------------------------------
before = hits()
updated, err = catalog.refresh()
check(u"свежий каталог второй раз не запрашивается",
      updated is False and err == "" and hits() == before, hits() - before)
check(u"свежий каталог не считается устаревшим", catalog.is_stale() is False)
check(u"возраст измерения известен и мал", 0.0 <= catalog.age() < 60.0)

# ---------------------------------------------------------------------------
# 7) 304 Not Modified: кэш не потерялся
#
# urllib поднимает 304 ИСКЛЮЧЕНИЕМ. Без правильной обработки это выглядело бы
# как неудача загрузки, и каталог обнулялся бы при каждой проверке свежести.
# ---------------------------------------------------------------------------
before = hits()
updated, err = catalog.refresh(force=True)
check(u"условный запрос ушёл", hits() - before == 1)
check(u"304 — это не ошибка", err == "", err)
check(u"после 304 модели в кэше остались", len(catalog.get("openrouter")) == 8)
check(u"после 304 каталог снова считается свежим", catalog.is_stale() is False)

# ---------------------------------------------------------------------------
# 7а) ВЫБРАННЫЙ ИЗ КАТАЛОГА ПРОВАЙДЕР ДОГРУЖАЕТ СВОИ МОДЕЛИ ДАЖЕ ПРИ 304
#
# Настоящая поломка, найденная живым прогоном: моделей всех 161 записи в кэше
# нет (680 КБ против 100), они догружаются для выбранного. Но каталог при этом
# не менялся, сервер отвечал 304 без тела — и модели брать было негде.
# Пользователь выбирал провайдера и оставался без цен и лимитов до следующего
# изменения каталога, то есть, возможно, на неделю.
# ---------------------------------------------------------------------------
check(u"моделей чужого провайдера в кэше нет — их там 5555 на 680 КБ",
      catalog.get("stranger-ai") == {})
before = hits()
updated, err = catalog.refresh(extra_ids=["stranger-ai"])
check(u"за моделями выбранного идём даже при свежем каталоге", hits() - before == 1)
check(u"и получаем их, а не 304 без тела",
      updated is True and err == ""
      and "stranger/model" in catalog.get("stranger-ai"))
check(u"модели наших пяти при этом на месте",
      len(catalog.get("openrouter")) == 8)
before = hits()
catalog.refresh(extra_ids=["stranger-ai"])
check(u"когда модели уже есть, второй раз не ходим", hits() == before)

# ---------------------------------------------------------------------------
# 8) Битый JSON: прежний кэш выживает, причина запоминается словами
# ---------------------------------------------------------------------------
Handler.mode = "garbage"
Handler.etag = 'W/"fake-etag-2"'  # чтобы ответ не свёлся к 304
updated, err = catalog.refresh(force=True)
check(u"битый JSON — неудача с объяснением", updated is False and err != "", err)
check(u"в объяснении видно, что пришло не JSON", u"JSON" in err, err)
check(u"ПРЕЖНИЙ кэш при неудаче не стёрт", len(catalog.get("openrouter")) == 8)
check(u"неудача видна панели вместе со временем попытки",
      catalog.state()["error"] != "" and catalog.state()["try_at"] > 0)
check(u"после неудачи не долбимся заново сразу", catalog.is_stale() is False)
check(u"через паузу после неудачи попытку повторяем",
      catalog.RETRY_SECONDS < catalog.FRESH_SECONDS)

before = hits()
updated, err = catalog.refresh()
check(u"пауза после неудачи означает НИ ОДНОГО запроса", hits() == before)

# HTML вместо JSON — настоящая ловушка models.dev (/api/<id>.json отвечает 200
# с разметкой сайта). Ответ «успешный», поэтому по коду её не отличить.
Handler.mode = "html"
updated, err = catalog.refresh(force=True)
check(u"HTML с кодом 200 не принят за каталог", updated is False and err != "")
check(u"прежний кэш выжил и после HTML", len(catalog.get("openrouter")) == 8)

Handler.mode = "500"
updated, err = catalog.refresh(force=True)
check(u"ошибка сервера объяснена кодом", u"500" in err, err)
check(u"прежний кэш выжил и после 500", len(catalog.get("openrouter")) == 8)

# ---------------------------------------------------------------------------
# 9) НИ ОДНОГО КЛЮЧА В ЗАПРОСЕ КАТАЛОГА
#
# models.dev — публичный справочник. Отправить туда ключ «на всякий случай»
# значит подарить секрет третьей стороне, и обратно его уже не забрать.
# ---------------------------------------------------------------------------
api_keys.set_key("openrouter", "sk-or-v1-SECRETVALUE0123456789")
api_keys.set_key("deepseek", "sk-DEEPSECRET0123456789")
Handler.mode = "ok"
Handler.etag = 'W/"fake-etag-3"'
Handler.headers_seen = []
catalog.refresh(force=True)
sent = json.dumps(Handler.headers_seen, ensure_ascii=False)
check(u"каталог загрузился при сохранённых ключах",
      len(catalog.get("openrouter")) == 8)
check(u"в запросе каталога нет заголовка Authorization",
      all("authorization" not in h for h in Handler.headers_seen), sent)
check(u"СЫРОГО ключа в запросе каталога нет", "SECRETVALUE" not in sent
      and "DEEPSECRET" not in sent)
check(u"плагин представляется своим именем",
      all("GodotAgent" in (h.get("user-agent") or "")
          for h in Handler.headers_seen))
check(u"gzip запрошен явно — иначе 4 МБ вместо 399 КБ",
      all("gzip" in (h.get("accept-encoding") or "")
          for h in Handler.headers_seen))
api_keys.set_key("openrouter", "")
api_keys.set_key("deepseek", "")

# ---------------------------------------------------------------------------
# 10) Испорченный файл кэша не роняет ничего
# ---------------------------------------------------------------------------
with open(catalog.catalog_path(), "w", encoding="utf-8") as f:
    f.write(u"{ это не JSON")
check(u"битый файл кэша читается как пустой", catalog.get("openrouter") == {})
check(u"и не роняет состояние для панели", catalog.state()["models"] == 0)
check(u"битый файл кэша означает «пора загрузить заново»",
      catalog.is_stale() is True)
with open(catalog.catalog_path(), "w", encoding="utf-8") as f:
    json.dump({"providers": [1, 2, 3], "at": "вчера"}, f)
check(u"чужая форма файла кэша тоже безопасна",
      catalog.get("openrouter") == {} and catalog.age() == -1.0)
catalog.forget()
check(u"кэш можно удалить", not _os0.path.isfile(catalog.catalog_path()))

# Кэш от версии с другим набором провайдеров: чужие ключи отбрасываются при
# чтении, иначе «каталог знает провайдера, которого у нас нет» попало бы в
# интерфейс как знание.
with open(catalog.catalog_path(), "w", encoding="utf-8") as f:
    json.dump({"version": 1, "at": time.time(), "etag": "", "providers": {
        "openrouter": {"models": {"a": {"cost_in": 1.0, "cost_out": 2.0,
                                        "context": 100, "tool_call": True}}},
        # Идентификатор, которого нет ни среди наших пяти, ни среди пригодных
        # записей каталога ниже: такой должен отброситься.
        "выдуманный": {"models": {"b": {"cost_in": 0.0, "cost_out": 0.0}}},
        # А этот пригоден — он есть в catalog_providers, значит пользователь его
        # выбрал и его модели имеют право лежать в кэше.
        "stranger-ai": {"models": {"c": {"cost_in": 3.0, "cost_out": 4.0}}},
    }, "catalog_providers": {
        "stranger-ai": {"id": "stranger-ai", "name": "Stranger",
                        "api": "https://stranger.example/v1",
                        "env": ["STRANGER_API_KEY"], "models_total": 1,
                        "models_free": 0, "transport": "openai"},
    }}, f)
check(u"знакомый провайдер из кэша прочитан",
      catalog.model_info("openrouter", "a")["context"] == 100)
check(u"выбранный из каталога тоже прочитан",
      catalog.model_info("stranger-ai", "c")["cost_in"] == 3.0)
check(u"незнакомый провайдер из кэша отброшен",
      catalog.get("выдуманный") == {}
      and catalog.state()["providers"] == ["openrouter", "stranger-ai"])
check(u"пригодные для выбора записи прочитаны",
      catalog.provider_meta("stranger-ai").get("api")
      == "https://stranger.example/v1"
      and catalog.state()["known_providers"] == 1)

# ---------------------------------------------------------------------------
# 11) Состояние каталога для панели
# ---------------------------------------------------------------------------
catalog.forget()
st = catalog.state()
check(u"без кэша панели сообщается «не загружался»",
      st["at"] == 0.0 and st["models"] == 0 and st["providers"] == [])
check(u"панель видит, ОТКУДА берутся цены", st["url"] == catalog.CATALOG_URL)
Handler.etag = 'W/"fake-etag-4"'
catalog.refresh(force=True)
st = catalog.state()
check(u"панель видит число ДОСТУПНЫХ моделей каталога", st["models"] == 11,
      st["models"])
# Снятые в это число НЕ входят. Иначе строка «сведения о 502 моделях» включала
# бы записи, про которые сам каталог говорит «провайдер их больше не отдаёт», —
# то есть завышала бы полезность справочника. У настоящего Opencode Zen таких
# 29 из 91.
check(u"снятые с обслуживания посчитаны ОТДЕЛЬНО", st["deprecated"] == 1,
      st["deprecated"])
check(u"панель видит, у кого каталог что-то знает",
      st["providers"] == ["deepseek", "gemini", "groq", "opencode_zen",
                          "openrouter"], st["providers"])
check(u"панель видит возраст измерения", st["at"] > 0 and st["error"] == "")
check(u"в состоянии каталога нет секретов",
      "SECRETVALUE" not in json.dumps(st, ensure_ascii=False))

# ---------------------------------------------------------------------------
# 12) Расхождения реестра и каталога — печатаются, а не применяются
#
# Реестр правит человек: адрес в каталоге есть не у всех (у groq и google поле
# "api" равно null), и подмена вслепую сломала бы рабочего провайдера.
# ---------------------------------------------------------------------------
lines = catalog.compare_registry(FAKE)
joined = u"\n".join(lines)
check(u"расхождение адреса замечено", any(u"deepseek" in l and u"адрес" in l
                                          for l in lines), joined)
check(u"лишнее имя переменной окружения замечено",
      "GOOGLE_GENERATIVE_AI_API_KEY" in joined, joined)
check(u"пустое поле api расхождением не считается",
      not any(u"groq" in l and u"адрес" in l for l in lines), joined)
check(u"адрес реестра остался нетронутым",
      P.base_url_for("deepseek") == "https://api.deepseek.com/v1")
check(u"без свежего ответа каталога сравнивать нечего",
      catalog.compare_registry() == [])

srv.shutdown()
catalog.CATALOG_URL = REAL_URL
shutil.rmtree(CFG, ignore_errors=True)
n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
