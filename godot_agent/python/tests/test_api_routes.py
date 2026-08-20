# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты HTTP-маршрутов настроек API (/api/*) и создания API-чата.

ВАЖНО ДЛЯ ЭТОГО ТЕСТА: папка настроек подменяется через переменную окружения
GODOT_AGENT_CONFIG_DIR ДО импорта модулей. Без этого прогон писал бы ключи и
прокси в настоящий %APPDATA%\\Godot_agent разработчика.
"""
import json
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CFG = tempfile.mkdtemp(prefix="agent_cfg_routes_")
UDD = tempfile.mkdtemp(prefix="agent_udd_routes_")
_os0.environ["GODOT_AGENT_CONFIG_DIR"] = CFG

# Заглушку selenium здесь НЕ ставим: main.py импортирует все парсеры сайтов, а
# им нужен настоящий пакет selenium (он в requirements.txt). Браузер при этом
# не запускается — теперь он поднимается только по требованию, из wait_driver().
import api_history
import main

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


# ---------------------------------------------------------------------------
# Локальный «провайдер» для успешных путей + поддельный каталог models.dev
#
# ПОЧЕМУ КАТАЛОГ ТОЖЕ ЗДЕСЬ. Обход провайдеров (/api/models/scan) с этой версии
# обновляет и каталог. Без подмены адреса прогон полез бы на models.dev — то
# есть падал бы на машине без сети и стучался бы в чужой сервис при каждом
# запуске. Ловушка _guard_outside ниже это и поймала.
#
# Содержимое каталога подобрано так, чтобы числа РАСХОДИЛИСЬ с живым ответом:
# «vendor/paid» по ответу провайдера платная (pricing 0.01/0.02), а по каталогу
# бесплатная. Ровно такое расхождение измерено у Opencode Zen (big-pickle), и
# именно поэтому счётчики держатся отдельно.
# ---------------------------------------------------------------------------

CATALOG_PATH = "/models.dev/api.json"
FAKE_CATALOG = {
    "openrouter": {
        "id": "openrouter", "name": "OpenRouter",
        "api": "https://openrouter.ai/api/v1", "env": ["OPENROUTER_API_KEY"],
        "models": {
            "vendor/paid": {"cost": {"input": 0, "output": 0},
                            "limit": {"context": 128000, "output": 32000},
                            "tool_call": True,
                            "description": u"это в кэш попасть не должно"},
            "vendor/gift:free": {"cost": {"input": 0, "output": 0},
                                 "limit": {"context": 8000, "output": 4000},
                                 "tool_call": False},
            # Модель, которой у живого /models НЕТ. В список выбора она попасть
            # не должна: пользователь выбрал бы модель, которой его ключу не
            # отдают, и получил бы 404 от провайдера.
            "vendor/only-in-catalog": {"cost": {"input": 5, "output": 10},
                                       "limit": {"context": 1000},
                                       "tool_call": True},
        },
    },
    # У нас "opencode_zen", у них "opencode" — соответствие идентификаторов.
    "opencode": {
        "id": "opencode", "name": "OpenCode Zen",
        "api": "https://opencode.ai/zen/v1", "env": ["OPENCODE_API_KEY"],
        "models": {"vendor/paid": {"cost": {"input": 3, "output": 6},
                                   "limit": {"context": 64000},
                                   "tool_call": True}},
    },
    # Чужой пригодный провайдер: из таких и собирается полный список выбора.
    # Живьём их 163 сверх наших семи; про них не проверено ничего, поэтому они
    # показываются только по явному включению и своей группой.
    "stranger-ai": {
        "id": "stranger-ai", "name": "Stranger AI",
        "api": "https://stranger.example/v1", "env": ["STRANGER_API_KEY"],
        "npm": "@ai-sdk/openai-compatible", "doc": "https://docs.stranger.example",
        "models": {"stranger/model": {"cost": {"input": 1, "output": 2},
                                      "limit": {"context": 32000}}},
    },
    # Записи без адреса в список попадать не должны: им нужен родной SDK
    # провайдера, а у нас единственный транспорт это HTTP. Таких в каталоге 26.
    "sdk-only": {
        "id": "sdk-only", "name": "SDK Only", "api": None,
        "env": ["SDK_ONLY_API_KEY"], "npm": "@ai-sdk/azure",
        "models": {"sdk/model": {"limit": {"context": 1000}}},
    },
}


class Handler(BaseHTTPRequestHandler):
    catalog_headers = []  # заголовки запросов каталога: ключей в них быть не должно

    def log_message(self, *a):
        pass

    def _json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == CATALOG_PATH:
            Handler.catalog_headers.append(
                {k.lower(): v for k, v in self.headers.items()})
            self._json(200, FAKE_CATALOG)
            return
        if self.path.endswith("/models"):
            # Ответ в стиле OpenRouter: цена строкой в долларах ЗА ТОКЕН,
            # окно контекста и supported_parameters. Это ПЕРВИЧНЫЕ числа —
            # каталог не имеет права их перебивать. У «vendor/paid» они есть, у
            # «vendor/gift:free» специально нет: на одной паре видно оба
            # направления — где живой ответ выигрывает и где каталог дополняет.
            self._json(200, {"data": [
                {"id": "vendor/paid",
                 "pricing": {"prompt": "0.0000015", "completion": "0.000006"},
                 "context_length": 999000,
                 "supported_parameters": ["tools", "temperature"]},
                {"id": "vendor/gift:free", "pricing": {"prompt": "0", "completion": "0"}},
            ]})
            return
        self._json(404, {"error": {"message": "no"}})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n) if n else b""
        self._json(200, {"model": "vendor/gift:free", "choices": [
            {"message": {"content": "pong"}, "finish_reason": "stop"}]})


srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
LOCAL = "http://127.0.0.1:%d/v1" % PORT

import catalog as _catalog

_REAL_CATALOG_URL = _catalog.CATALOG_URL
_catalog.CATALOG_URL = "http://127.0.0.1:%d%s" % (PORT, CATALOG_PATH)
check(u"настоящий адрес каталога — единственный эндпоинт models.dev",
      _REAL_CATALOG_URL == "https://models.dev/api.json")

cl = main.app.test_client()


def post(path, body=None):
    r = cl.post(path, json=dict(body or {}, user_data_dir=UDD,
                                project_root=UDD))
    return r.status_code, r.get_json()


# ---------------------------------------------------------------------------
# 1) Список провайдеров
# ---------------------------------------------------------------------------
st, j = post("/api/providers")
ids = [p["id"] for p in j["providers"]]
check(u"/api/providers отвечает 200", st == 200)
check(u"OpenRouter первым в списке", ids and ids[0] == "openrouter")
check(u"AgentRouter добавлен в список", "agentrouter" in ids)
agentrouter_rec = [p for p in j["providers"] if p["id"] == "agentrouter"][0]
check(u"AgentRouter предлагает GPT 5.6 Sol по умолчанию",
      agentrouter_rec["model"] == "gpt-5.6-sol")
check(u"есть «свой адрес» для локального сервера в будущем", "custom" in ids)
check(u"путь к файлу настроек показан пользователю",
      j["config_path"].startswith(CFG))
check(u"незаданный ключ помечен как не настроенный",
      not [p for p in j["providers"] if p["id"] == "openrouter"][0]["configured"])
check(u"причина неготовности объяснена",
      bool([p for p in j["providers"] if p["id"] == "openrouter"][0]["not_ready_reason"]))
check(u"AgentRouter помечен недоступным вместе с причиной",
      bool(agentrouter_rec["unavailable"]) and agentrouter_rec["ready"] is False)
check(u"причина неготовности — недоступность сервиса, а не нехватка ключа",
      agentrouter_rec["not_ready_reason"] == agentrouter_rec["unavailable"])

# ---------------------------------------------------------------------------
# 1а) НИ ОДНОГО ЗАПРОСА К НЕДОСТУПНОМУ ПРОВАЙДЕРУ
#
# Сервис принимает только клиентов из своего белого списка, и Godot Agent в него
# пока не входит. Отказ должен приходить ИЗ ПЛАГИНА, до сети: иначе в логах
# сервиса копятся отказы, а пользователь ждёт таймаут ради предсказуемого 401.
# Ловушка на socket.getaddrinfo надёжнее проверки текста: она поймает попытку
# соединения из любого места кода, включая DoH и прокси.
# ---------------------------------------------------------------------------
import socket as _socket

_reached = []
_real_getaddrinfo = _socket.getaddrinfo


def _guard_getaddrinfo(host, *a, **kw):
    if "agentrouter" in str(host).lower():
        _reached.append(str(host))
    return _real_getaddrinfo(host, *a, **kw)


_socket.getaddrinfo = _guard_getaddrinfo
try:
    st_t, j_t = post("/api/test", {"provider": "agentrouter",
                                   "model": "claude-opus-5"})
    st_m, j_m = post("/api/models/refresh", {"provider": "agentrouter"})
    st_c, j_c = post("/chats/new", {"kind": "api", "provider": "agentrouter",
                                    "model": "claude-opus-5"})
finally:
    _socket.getaddrinfo = _real_getaddrinfo

check(u"проверка подключения отказывает сама, без похода в сеть",
      st_t == 200 and j_t.get("ok") is False and u"недоступен" in j_t.get("error", ""))
check(u"обновление моделей отказывает сама, без похода в сеть",
      st_m == 200 and u"недоступен" in str(j_m.get("error", "")))
check(u"чат с недоступным провайдером не создаётся",
      st_c == 400 and u"error" in j_c)
check(u"к agentrouter.org не было ни одной попытки соединения", _reached == [])

# ---------------------------------------------------------------------------
# 2) Сохранение настроек
# ---------------------------------------------------------------------------
st, j = post("/api/settings/set", {"provider": "openrouter",
                                   "key": "sk-or-v1-SECRETVALUE0123456789",
                                   "model": "vendor/gift:free",
                                   "make_default": True})
rec = [p for p in j["providers"] if p["id"] == "openrouter"][0]
check(u"ключ сохранён", rec["configured"] and rec["key_source"] == "file")
check(u"наружу уходит только маска", rec["masked"].startswith("sk-or-")
      and rec["masked"].endswith("6789"))
check(u"СЫРОГО ключа в ответе нет", "SECRETVALUE" not in json.dumps(j))
check(u"модель сохранена", rec["model"] == "vendor/gift:free")
check(u"провайдер стал предложением по умолчанию",
      j["defaults"]["provider"] == "openrouter")
check(u"провайдер готов к работе", rec["ready"])

st, j = post("/api/settings/set", {"proxy": {"enabled": True, "host": "p.local",
                                             "port": 3128, "user": "u",
                                             "password": "proxypass"}})
check(u"прокси сохранён", j["proxy"]["enabled"] and j["proxy"]["host"] == "p.local")
check(u"наличие пароля показано флагом", j["proxy"]["has_password"] is True)
check(u"САМ пароль прокси в ответе не появляется", "proxypass" not in json.dumps(j))

st, j = post("/api/settings/set", {"proxy": {"host": "p2.local"}})
check(u"частичное обновление меняет только присланное поле",
      j["proxy"]["host"] == "p2.local" and j["proxy"]["port"] == 3128)
check(u"пароль не затёрся при правке хоста", j["proxy"]["has_password"] is True)
post("/api/settings/set", {"proxy": {"enabled": False}})

st, j = post("/api/settings/set", {"provider": "нет-такого"})
check(u"неизвестный провайдер -> 400 с понятным текстом",
      st == 400 and u"Неизвестный провайдер" in j["error"])

# Испорченный адрес endpoint'а: отказ ОТДЕЛЬНЫМ полем, как и у прокси. Поле
# адреса открыто у всех провайдеров (сервис может переехать), поэтому опечатка
# в нём не должна молча превращать рабочего провайдера в неотвечающий.
st, j = post("/api/settings/set", {"provider": "openrouter",
                                   "base_url": "openrouter.ai/api/v1"})
check(u"адрес без схемы -> base_url_error, а не общий отказ формы",
      st == 200 and u"http://" in j.get("base_url_error", ""))
orec = [p for p in j["providers"] if p["id"] == "openrouter"][0]
check(u"отклонённый адрес не подменил рабочий",
      orec["base_url"] == "https://openrouter.ai/api/v1")
check(u"панель знает, что адрес можно править, и к чему вернёт очистка",
      orec["base_url_editable"] is True
      and orec["base_url_default"] == "https://openrouter.ai/api/v1")

# ---------------------------------------------------------------------------
# 2a) Несколько ключей на провайдера
#
# Квота бесплатных тарифов считается НА КЛЮЧ, поэтому панель обязана уметь
# добавить второй ключ и показать состояние каждого. Сырых ключей в ответе не
# бывает ни на одном шаге — это тот же барьер, что и для одиночного ключа.
# ---------------------------------------------------------------------------
_K_A = "sk-or-v1-KEYAAAAAAAAAAAAAAAAAAAAAAAA1111"
_K_B = "sk-or-v1-KEYBBBBBBBBBBBBBBBBBBBBBBBB2222"
import api_keys as _ak_keys  # исчерпание ключа отмечает бэкенд, не маршрут
st, j = post("/api/settings/set", {"provider": "openrouter", "key": _K_A})
st, j = post("/api/settings/set", {"provider": "openrouter", "add_key": _K_B})
rec2 = [p for p in j["providers"] if p["id"] == "openrouter"][0]
check(u"второй ключ добавлен", rec2["keys_total"] == 2)
check(u"СЫРЫХ ключей в ответе нет", "KEYAAAA" not in json.dumps(j)
      and "KEYBBBB" not in json.dumps(j))
check(u"каждый ключ пришёл маской и позицией",
      [k["index"] for k in rec2["keys"]] == [0, 1]
      and all(k["masked"].startswith("sk-or-") for k in rec2["keys"]))
check(u"исчерпанных пока нет", rec2["keys_spent"] == 0
      and all(k["spent"] is False for k in rec2["keys"]))
check(u"добавление ключа не тронуло модель", rec2["model"] == "vendor/gift:free")

# Исчерпание отмечает бэкенд; панель должна увидеть это в том же ответе.
_ak_keys.note_key_exhausted("openrouter", 0, reason=u"free-models-per-day")
st, j = post("/api/settings/set", {"provider": "openrouter"})
rec3 = [p for p in j["providers"] if p["id"] == "openrouter"][0]
check(u"панель видит, какой ключ исчерпан и почему",
      rec3["keys"][0]["spent"] is True
      and u"free-models-per-day" in rec3["keys"][0]["reason"]
      and rec3["keys"][1]["spent"] is False)
check(u"счётчик исчерпанных отдан отдельно", rec3["keys_spent"] == 1)
check(u"действующая маска — от РАБОЧЕГО ключа, а не от исчерпанного",
      rec3["masked"].endswith("2222"))

st, j = post("/api/settings/set", {"provider": "openrouter",
                                   "clear_cooldowns": True})
rec4 = [p for p in j["providers"] if p["id"] == "openrouter"][0]
check(u"«пробуй заново» возвращает ключи в игру", rec4["keys_spent"] == 0)

st, j = post("/api/settings/set", {"provider": "openrouter",
                                   "delete_key_index": 0})
rec5 = [p for p in j["providers"] if p["id"] == "openrouter"][0]
check(u"удалён именно указанный ключ",
      rec5["keys_total"] == 1 and rec5["keys"][0]["masked"].endswith("2222"))
st, j = post("/api/settings/set", {"provider": "openrouter",
                                   "delete_key_index": 7})
check(u"удаление несуществующей позиции — понятный отказ полем",
      st == 200 and j.get("key_error"))
check(u"единственный ключ при этом не пострадал",
      [p for p in j["providers"] if p["id"] == "openrouter"][0]["keys_total"] == 1)

# Правка одиночного поля «ключ» по-прежнему ЗАМЕНЯЕТ список: панель сохраняет
# форму целиком, и «сохранить» там всегда означало «пусть будет вот этот».
st, j = post("/api/settings/set", {"provider": "openrouter",
                                   "key": "sk-or-v1-SECRETVALUE0123456789"})
check(u"сохранение одного ключа заменяет список, а не добавляет",
      [p for p in j["providers"] if p["id"] == "openrouter"][0]["keys_total"] == 1)

# ---------------------------------------------------------------------------
# 3) Обновление списка моделей
# ---------------------------------------------------------------------------
post("/api/settings/set", {"provider": "custom", "base_url": LOCAL,
                           "model": "vendor/gift:free"})
st, j = post("/api/models/refresh", {"provider": "custom"})
check(u"список моделей получен", st == 200 and "vendor/paid" in j["models"])
check(u"бесплатные модели идут первыми",
      j["models"][0] == "vendor/gift:free")
# Признак бесплатности доходит до панели отдельным полем. Без него бесплатную
# модель можно было отличить только по суффиксу в имени, а модель с нулевой
# ценой без суффикса выглядела платной.
info = {r["id"]: r["free"] for r in j["models_info"]}
check(u"признак бесплатности пришёл вместе со списком",
      info.get("vendor/gift:free") is True and info.get("vendor/paid") is False)
check(u"прежний список строк остался на месте (панель ещё читает его)",
      j["models"] == [r["id"] for r in j["models_info"]])
crec = [p for p in j["providers"] if p["id"] == "custom"][0]
check(u"числа моделей записаны в наблюдения о провайдере",
      crec["stats"]["models_total"] == 2 and crec["stats"]["models_free"] == 1)

st, j = post("/api/models/refresh", {"provider": "custom", "free_only": True})
check(u"фильтр «только бесплатные» работает", j["models"] == ["vendor/gift:free"])
# Ловушка счётчика: посчитать «всего» по уже отфильтрованному списку. Тогда у
# любого платного сервиса в списке провайдеров было бы «все модели бесплатные».
crec = [p for p in j["providers"] if p["id"] == "custom"][0]
check(u"счётчик «всего» считается по ПОЛНОМУ списку, а не по отфильтрованному",
      crec["stats"]["models_total"] == 2 and crec["stats"]["models_free"] == 1)

st, j = post("/api/models/refresh", {"provider": "нет"})
check(u"обновление моделей неизвестного провайдера -> 400", st == 400)

# ---------------------------------------------------------------------------
# 3а) Автообновление списков моделей (/api/models/scan)
#
# ЗАЧЕМ ЭТО ЕСТЬ. Числа «моделей столько, бесплатных столько» брались ТОЛЬКО из
# ручного нажатия «Обновить список». Значит они были у провайдеров, которых
# пользователь и так открывал, и отсутствовали у остальных — а фильтр «с
# бесплатными» в списке провайдеров отбирает как раз по этим числам. Снаружи
# это выглядит как утверждение «бесплатные модели есть только у Opencode Zen»,
# хотя на самом деле остальных просто ни разу не спрашивали.
# ---------------------------------------------------------------------------
import api_keys as _ak
import providers as _P

_ak.record_stats_bulk({"custom": {"models_total": -1, "models_free": -1,
                                  "models_at": 0.0, "models_error": "",
                                  "models_try_at": 0.0}})
check(u"провайдер без чисел моделей считается устаревшим",
      _P.models_stale("custom"))
check(u"«свой адрес» с заданным адресом можно спросить молча",
      _P.can_fetch_models("custom") is True)
check(u"недоступного провайдера не спрашивают даже за списком моделей",
      _P.can_fetch_models("agentrouter") is False)
check(u"провайдера без ключа и без публичного /models не спрашивают",
      _P.can_fetch_models("groq") is False)
check(u"устаревший провайдер попал в список на обновление",
      "custom" in _P.autoscan_targets())

# ПОЧЕМУ ЗДЕСЬ ПОДМЕНЯЮТСЯ АДРЕСА. В обход попадают все, кого можно спросить
# молча: у openrouter в этом прогоне сохранён ключ, а у opencode_zen список
# моделей публичный. Оба указывают на настоящие сервисы, и тест без подмены
# полез бы в интернет — то есть падал бы на машине без сети и стучался бы в
# чужие сервисы при каждом прогоне.
post("/api/settings/set", {"provider": "openrouter", "base_url": LOCAL})
post("/api/settings/set", {"provider": "opencode_zen", "base_url": LOCAL})
_outside = []


def _guard_outside(host, *a, **kw):
    if "127.0.0.1" not in str(host):
        _outside.append(str(host))
    return _real_getaddrinfo(host, *a, **kw)


_socket.getaddrinfo = _guard_outside
try:
    st, j = post("/api/models/scan")
finally:
    _socket.getaddrinfo = _real_getaddrinfo
check(u"обход провайдеров отвечает 200", st == 200)
check(u"обход прошёл по всем, кого можно спросить молча",
      set(j["scanned"]) == {"custom", "openrouter", "opencode_zen"})
check(u"к провайдерам, которых спросить нельзя, обход не ходил", _outside == [])
check(u"провайдер без ключа не попал в обход ни удачей, ни неудачей",
      "groq" not in j["scanned"] and "groq" not in j["failed"])
check(u"недоступный провайдер не попал в обход",
      "agentrouter" not in j["scanned"] and "agentrouter" not in j["failed"])
crec = [p for p in j["providers"] if p["id"] == "custom"][0]
check(u"числа моделей появились БЕЗ нажатия «Обновить» у провайдера",
      crec["stats"]["models_total"] == 2 and crec["stats"]["models_free"] == 1)
orec = [p for p in j["providers"] if p["id"] == "openrouter"][0]
check(u"у OpenRouter числа тоже появились сами — фильтру «с бесплатными» есть по чему отбирать",
      orec["stats"]["models_free"] == 1)
check(u"ошибок отдельных провайдеров нет в общем поле error",
      "error" not in j)

# ---------------------------------------------------------------------------
# 3а-2) КАТАЛОГ models.dev как ВТОРИЧНЫЙ источник
#
# Живой ответ провайдера — первичная правда о том, что доступно ЭТОМУ ключу.
# Каталог только ДОПОЛНЯЕТ поля, которых в живом ответе нет (цена, окно
# контекста, поддержка инструментов), и никогда их не заменяет. Проверяем три
# вещи, каждая из которых при поломке врёт пользователю по-своему:
#   * дополнения доехали до записей моделей — иначе цен и лимитов нет вовсе;
#   * счётчики бесплатных считаются РАЗДЕЛЬНО — иначе утверждение каталога
#     выдаётся за ответ провайдера;
#   * в запрос каталога не ушёл ни один ключ — models.dev публичный справочник,
#     и подаренный ему секрет обратно не забрать.
# ---------------------------------------------------------------------------
cst = j.get("catalog") or {}
import model_cache

check(u"состояние каталога приходит вместе с настройками",
      cst.get("at", 0) > 0 and not cst.get("error"))
check(u"панель видит, ОТКУДА взялись цены и лимиты",
      "127.0.0.1" in str(cst.get("url", "")))
check(u"каталог знает про наших провайдеров под НАШИМИ идентификаторами",
      set(cst.get("providers") or []) == {"openrouter", "opencode_zen"})
check(u"каталог обновился САМ, внутри обхода, без отдельного маршрута",
      len(Handler.catalog_headers) == 1)
_cat_sent = json.dumps(Handler.catalog_headers, ensure_ascii=False)
check(u"в запросе каталога нет заголовка Authorization",
      all("authorization" not in h for h in Handler.catalog_headers))
check(u"СЫРОГО ключа в запросе каталога нет", "SECRETVALUE" not in _cat_sent)

_oidx = {r["id"]: r for r in (j.get("models_index") or {}).get("openrouter", [])}
_paid = _oidx.get("vendor/paid") or {}
_gift = _oidx.get("vendor/gift:free") or {}
# ЖИВОЙ ОТВЕТ ПЕРВИЧЕН. Цена за токен переведена в цену за миллион по единице из
# реестра, окно взято его, каталог со своими 128000 в это НЕ вмешался.
check(u"цена и окно из живого ответа не перебиты каталогом",
      _paid.get("cost_in") == 1.5 and _paid.get("cost_out") == 6.0
      and _paid.get("context") == 999000 and _paid.get("tool_call") is True)
# А чего провайдер не присылает — дополняет каталог.
check(u"каталог дописал то, чего в живом ответе не было",
      _paid.get("max_output") == 32000
      and _gift.get("context") == 8000 and _gift.get("max_output") == 4000
      and _gift.get("tool_call") is False)
# И КАЖДОЕ дописанное поле названо. Без этого списка подпись «по каталогу
# models.dev» встала бы и под живой ценой провайдера, а она точнее: замерено, что
# у moonshotai/kimi-k2.6 каталог отстал и завышал цену на 47%.
check(u"каталог перечислил, ЧТО именно он дописал, и не приписал себе живое",
      set(_paid.get("from_catalog") or []) == {"max_output"}
      and set(_gift.get("from_catalog") or [])
      == {"context", "max_output", "tool_call"})
# ГЛАВНОЕ: каталог не даёт список для выбора. У него есть модель, которой живой
# /models не отдаёт, и попасть в панель она не должна — иначе пользователь
# выберет её и получит 404 от провайдера.
check(u"модель, которая есть ТОЛЬКО в каталоге, в список выбора не попала",
      "vendor/only-in-catalog" not in _oidx)
check(u"признак бесплатности каталога лежит ОТДЕЛЬНЫМ полем от живого",
      _oidx.get("vendor/paid", {}).get("catalog_free") is True
      and _oidx.get("vendor/paid", {}).get("free") is False)

orec = [p for p in j["providers"] if p["id"] == "openrouter"][0]
check(u"счётчик бесплатных ПО ОТВЕТУ ПРОВАЙДЕРА остался измеренным по нему",
      orec["stats"]["models_free"] == 1 and orec["stats"]["models_total"] == 2)
check(u"счётчик бесплатных ПО КАТАЛОГУ — отдельное число, и оно другое",
      orec["stats"]["models_free_catalog"] == 2)
zrec = [p for p in j["providers"] if p["id"] == "opencode_zen"][0]
check(u"у другого провайдера каталог даёт своё число, а не то же самое",
      zrec["stats"]["models_free"] == 1
      and zrec["stats"]["models_free_catalog"] == 0)
crec = [p for p in j["providers"] if p["id"] == "custom"][0]
check(u"про провайдера, которого каталог не знает, счётчик МОЛЧИТ (-1), а не пишет ноль",
      crec["stats"]["models_free_catalog"] == -1)
# В КЭШ УХОДИТ ЖИВОЙ ОТВЕТ, БЕЗ УТВЕРЖДЕНИЙ КАТАЛОГА. Попав на диск, поля
# каталога стали бы неотличимы от присланных провайдером, и подпись «по каталогу
# models.dev» встала бы под живой ценой. Дополнения прикладываются на выходе и
# сами сообщают, что дописали. Побочная выгода: обновление каталога действует
# сразу, не дожидаясь нового опроса провайдеров.
_cached = {r["id"]: r for r in model_cache.get("openrouter")}
check(u"в кэш попали ЖИВЫЕ числа провайдера",
      set(_cached) == {"vendor/gift:free", "vendor/paid"}
      and _cached["vendor/paid"]["context"] == 999000
      and _cached["vendor/paid"]["cost_in"] == 1.5)
check(u"а утверждения каталога в кэш НЕ попали — иначе подпись об источнике соврёт",
      not any(k in _cached["vendor/paid"]
              for k in ("catalog_free", "from_catalog", "status", "deprecated"))
      and "context" not in _cached["vendor/gift:free"])
with open(_ak.config_path(), "r", encoding="utf-8") as f:
    check(u"каталог не поселился в файле с ключами",
          "vendor/only-in-catalog" not in f.read())
check(u"кэш каталога — отдельный файл",
      _catalog.catalog_path() != _ak.config_path()
      and _catalog.catalog_path() != model_cache.cache_path()
      and _os0.path.isfile(_catalog.catalog_path()))

# Свежий каталог (неделя свежести против суток у списков моделей) при обычном
# обходе повторно не запрашивается: 400 КБ на каждое открытие окна — это трата
# чужого трафика ради подписи под названием.
_cat_before = len(Handler.catalog_headers)
post("/api/models/scan")
check(u"свежий каталог повторно не загружается",
      len(Handler.catalog_headers) == _cat_before)
# А по ЯВНОЙ просьбе («Обновить все списки») — загружается, не глядя на
# свежесть. Отдельного маршрута и отдельной кнопки для каталога нет намеренно:
# нужен он ровно тогда, когда обновляют списки моделей.
post("/api/models/scan", {"force": True})
check(u"«обновить всё» обновляет и каталог тоже",
      len(Handler.catalog_headers) == _cat_before + 1)

# Повторный обход СРАЗУ ЖЕ ничего не делает: числа свежие. Иначе открытие окна
# выбора провайдера превращалось бы в поход по всем сервисам каждый раз, то
# есть в трату чужих лимитов запросов ради подписи под названием.
st, j = post("/api/models/scan")
check(u"свежие числа второй раз не перезапрашиваются",
      j["scanned"] == [] and j["scan_skipped"] is True)
# А по явной просьбе — обновляются, не глядя на свежесть.
st, j = post("/api/models/scan", {"force": True})
check(u"«обновить всё» обходит провайдеров и при свежих числах",
      "custom" in j["scanned"])

# Неудача обхода ЗАПОМИНАЕТСЯ вместе с причиной. Без этого в карточке
# провайдера осталось бы «список ещё не загружался» — то есть плагин выглядел
# бы бездействующим, хотя он сходил и получил отказ.
post("/api/settings/set", {"provider": "custom",
                           "base_url": "http://127.0.0.1:1/v1"})
# Числа проставляем ПОСЛЕ смены адреса: сама смена их обнуляет (прежние
# относились к прежнему сервису), а проверить надо другое — что их не стирает
# НЕУДАЧНАЯ попытка. Список, полученный вчера, полезнее пустоты, а сегодняшний
# отказ показывается рядом с ним.
_ak.record_models_stats("custom", 2, 1)
st, j = post("/api/models/scan", {"force": True})
crec = [p for p in j["providers"] if p["id"] == "custom"][0]
check(u"неудача обхода объяснена словами в карточке провайдера",
      "custom" in j["failed"] and bool(crec["stats"].get("models_error")))
check(u"прежние числа моделей при неудаче не стёрты",
      crec["stats"]["models_total"] == 2)
check(u"после неудачи не долбимся сразу заново",
      _P.models_stale("custom") is False)
post("/api/settings/set", {"provider": "custom", "base_url": LOCAL})
post("/api/models/scan", {"force": True})
_st, _j = post("/api/providers")
crec = [p for p in _j["providers"] if p["id"] == "custom"][0]
check(u"удачный обход снимает прежнюю ошибку, а не показывает её рядом с числами",
      not crec["stats"].get("models_error"))

# ---------------------------------------------------------------------------
# 3б) Индекс моделей для поиска по всем провайдерам сразу
#
# ЗАЧЕМ. Человек помнит «мне нужен kimi» или «deepseek», но не знает, кто из
# провайдеров это отдаёт. Без индекса узнать это можно было только открыв
# каждого провайдера по очереди и нажав «Обновить список» — то есть поиск
# существовал, но искал только названия провайдеров.
# ---------------------------------------------------------------------------
import model_cache

st, j = post("/api/models/scan", {"force": True})
idx = j.get("models_index") or {}
check(u"индекс моделей приходит вместе с обходом", isinstance(idx, dict) and bool(idx))
check(u"в индексе есть модели опрошенных провайдеров",
      [r["id"] for r in idx.get("custom", [])] == ["vendor/gift:free", "vendor/paid"])
check(u"признак бесплатности доехал до индекса",
      {r["id"]: r["free"] for r in idx.get("custom", [])}
      == {"vendor/gift:free": True, "vendor/paid": False})
check(u"индекс лежит ОТДЕЛЬНО от файла с ключами",
      model_cache.cache_path() != _ak.config_path()
      and _os0.path.isfile(model_cache.cache_path()))
with open(_ak.config_path(), "r", encoding="utf-8") as f:
    check(u"списки моделей не попали в файл настроек с ключами",
          "vendor/paid" not in f.read())

# Ловушка индекса: обновление с флажком «только бесплатные». Список для панели
# фильтруется, но в кэш обязан уйти ПОЛНЫЙ — иначе поиск перестанет находить
# платные модели у провайдера, которого один раз обновили с этим флажком.
st, j = post("/api/models/refresh", {"provider": "custom", "free_only": True})
check(u"панели ушёл отфильтрованный список", j["models"] == ["vendor/gift:free"])
check(u"а в индекс — полный, вместе с платными",
      [r["id"] for r in (j.get("models_index") or {}).get("custom", [])]
      == ["vendor/gift:free", "vendor/paid"])

# Смена адреса endpoint'а: прежние модели относились к ПРЕЖНЕМУ адресу. Оставить
# их значит выдать факты об одном сервисе за факты о другом, а пользователь при
# этом выбирал бы модель, которой на новом адресе может не быть.
post("/api/settings/set", {"provider": "custom",
                           "base_url": "http://127.0.0.1:2/v1"})
_st, _j = post("/api/providers")
crec = [p for p in _j["providers"] if p["id"] == "custom"][0]
check(u"смена адреса забывает список моделей",
      model_cache.get("custom") == [])
check(u"и обнуляет числа моделей, чтобы их спросили заново",
      crec["stats"]["models_total"] == -1 and _P.models_stale("custom") is True)
post("/api/settings/set", {"provider": "custom", "base_url": LOCAL})
post("/api/models/scan", {"force": True})
check(u"после возврата адреса список снова на месте",
      len(model_cache.get("custom")) == 2)
# Подменённые адреса возвращаем реестру: дальше идут проверки, которым важно,
# что у провайдера стоит его настоящий адрес.
post("/api/settings/set", {"provider": "openrouter", "base_url": ""})
post("/api/settings/set", {"provider": "opencode_zen", "base_url": ""})

# ---------------------------------------------------------------------------
# 4) Проверка подключения
# ---------------------------------------------------------------------------
st, j = post("/api/test", {"provider": "custom", "model": "vendor/gift:free"})
check(u"проверка подключения успешна", st == 200 and j["ok"] is True)
check(u"показано время ответа", j["elapsed_ms"] >= 0 and u"мс" in j["message"])
check(u"видно, шёл ли запрос через прокси", j["via_proxy"] is False)
# Исход проверки запоминается: это единственное место, где точно известно, что
# провайдер отвечает ИМЕННО У ЭТОГО пользователя — с его ключом и его сетью.
_st, _j = post("/api/providers")
crec = [p for p in _j["providers"] if p["id"] == "custom"][0]
check(u"удачная проверка запомнена в наблюдениях",
      crec["stats"]["test_ok"] is True and crec["stats"]["test_at"] > 0)

post("/api/settings/set", {"provider": "custom",
                           "base_url": "http://127.0.0.1:1/v1"})
st, j = post("/api/test", {"provider": "custom", "model": "vendor/gift:free"})
check(u"недоступный адрес -> ok=False, а не 500", st == 200 and j["ok"] is False)
check(u"в ошибке есть подсказка про прокси", u"прокси" in j["error"])
_st, _j = post("/api/providers")
crec = [p for p in _j["providers"] if p["id"] == "custom"][0]
check(u"неудачная проверка тоже запомнена, а не выдана за нейтральную",
      crec["stats"]["test_ok"] is False)
post("/api/settings/set", {"provider": "custom", "base_url": LOCAL})

# ---------------------------------------------------------------------------
# 5) Создание API-чата
# ---------------------------------------------------------------------------
st, j = post("/chats/new", {"kind": "api", "provider": "custom",
                            "model": "vendor/gift:free"})
check(u"API-чат создан без браузера", st == 200 and j.get("kind") == "api")
cid = j["current_id"]
check(u"провайдер и модель закреплены за чатом",
      j["provider"] == "custom" and j["model"] == "vendor/gift:free")
check(u"в подписи чата видны провайдер и модель",
      "vendor/gift:free" in j["site"])

import chat_store
rec = chat_store.find_chat(UDD, cid)
check(u"в записи чата сохранён kind=api", rec.get("kind") == "api")
check(u"модель записана в сам чат", rec.get("model") == "vendor/gift:free")
check(u"адреса страницы у API-чата нет", not rec.get("url"))
tr = rec.get("transcript") or []
check(u"пользователю объяснено, что модель закреплена",
      tr and u"закреплена" in tr[0]["text"])

st, j = post("/chats/new", {"kind": "api", "provider": "groq"})
check(u"чат на ненастроенном провайдере не создаётся",
      st == 400 and u"не готов" in j["error"])

# ---------------------------------------------------------------------------
# 6) Браузер НЕ поднимается из-за API-режима
# ---------------------------------------------------------------------------
import server_state as S
check(u"драйвер браузера так и не создан", S.get_driver() is None)
check(u"запуск браузера даже не начинался", not S.browser_boot_started())
st, j = post("/browser/status")
check(u"статус браузера — «idle», а не «booting»", j["state"] == "idle")

# ---------------------------------------------------------------------------
# 7) Удаление чата убирает и его историю
# ---------------------------------------------------------------------------
secret_phrase = u"DELETE-ME-TRANSCRIPT-9f3a"
chat_store.append_transcript(UDD, cid, "user", secret_phrase)
api_history.append_exchange(UDD, cid, u"вопрос", u"ответ")
check(u"история чата создана",
      _os0.path.isfile(api_history.history_path(UDD, cid)))
main.history.record_change(
    UDD, {"action": "create_file", "path": "res://delete-test.gd"},
    chat_id=cid, chat_title=u"Секретное название удаляемого чата")
st, j = post("/chats/delete", {"id": cid})
check(u"чат удалён", st == 200 and chat_store.find_chat(UDD, cid) is None)
check(u"файл истории удалён вместе с чатом",
      not _os0.path.isfile(api_history.history_path(UDD, cid)))
with open(_os0.path.join(UDD, "agent_chats.json"), "r", encoding="utf-8") as f:
    raw_chats = f.read()
check(u"текст удалённой переписки физически отсутствует в хранилище",
      secret_phrase not in raw_chats and cid not in raw_chats)
journal = main.history._load_journal(UDD)
check(u"журнал отката сохранён, но обезличен от удалённого чата",
      bool(journal)
      and all(e.get("chat_id") != cid for e in journal)
      and u"Секретное название удаляемого чата" not in json.dumps(journal, ensure_ascii=False))
st_missing, _ = post("/chats/delete", {"id": cid})
check(u"повторное удаление не изображает успех", st_missing == 404)

# ---------------------------------------------------------------------------
# 8) ПОЛНЫЙ СПИСОК ПРОВАЙДЕРОВ ИЗ КАТАЛОГА через маршруты
#
# Замерено: из 192 записей каталога 166 имеют адрес endpoint'а. Включение
# полного списка НЕ должно означать поход к незнакомым сервисам — проверяем это
# ловушкой на разрешение имён, как и в остальных местах этого файла.
# ---------------------------------------------------------------------------
st, j = post("/api/providers")
check(u"по умолчанию полный список выключен",
      (j.get("catalog") or {}).get("show_all") is False)
_base_ids = [p["id"] for p in j["providers"]]
check(u"и провайдеров ровно семь разобранных", len(_base_ids) == 7)
check(u"панель знает, сколько записей добавит включение",
      int((j.get("catalog") or {}).get("known_providers", 0)) >= 1)

_socket.getaddrinfo = _guard_outside
_outside = []
try:
    st, j = post("/api/settings/set", {"catalog": {"enabled": True}})
    ids_all = [p["id"] for p in j["providers"]]
finally:
    _socket.getaddrinfo = _real_getaddrinfo
check(u"включение добавило провайдеров из каталога",
      len(ids_all) > len(_base_ids) and "stranger-ai" in ids_all)
check(u"переключатель вернулся включённым", (j.get("catalog") or {}).get("show_all") is True)
check(u"запись без адреса endpoint'а в список НЕ попала",
      "sdk-only" not in ids_all)
check(u"САМО включение не делает ни одного запроса в сеть", _outside == [])
# Обход провайдеров сюда не идёт НЕ потому, что мы его не позвали, а потому что
# каталожным записям не выставляется models_public: без ключа спрашивать их
# нельзя. Иначе включение полного списка означало бы сто шестьдесят запросов к
# незнакомым сервисам при открытии окна выбора.
check(u"без ключа список моделей каталожной записи не спрашивают",
      _P.can_fetch_models("stranger-ai") is False)
check(u"и в автообход она не попадает",
      "stranger-ai" not in _P.autoscan_targets())
_srec = [p for p in j["providers"] if p["id"] == "stranger-ai"][0]
check(u"каталожная запись помечена и без обещания публичного списка моделей",
      _srec["from_catalog"] is True and _srec["models_public"] is False
      and _srec["verified"] is False)
check(u"её адрес взят из каталога",
      _srec["base_url"] == "https://stranger.example/v1")
check(u"причина неготовности — нет ключа, а не «неизвестный провайдер»",
      _srec["not_ready_code"] == "no_key")

# Выбор каталожного провайдера — обычное сохранение настроек. Проверяем, что
# маршрут его принимает (раньше любой незнакомый идентификатор давал 400).
st, j = post("/api/settings/set", {"provider": "stranger-ai",
                                   "key": "sk-CATALOGSECRET0123456789",
                                   "model": "stranger/model"})
_srec = [p for p in j["providers"] if p["id"] == "stranger-ai"][0]
check(u"каталожного провайдера можно настроить как любого другого",
      st == 200 and _srec["configured"] is True and _srec["ready"] is True)
check(u"СЫРОГО ключа каталожного провайдера в ответе нет",
      "CATALOGSECRET" not in json.dumps(j))
st, j = post("/api/settings/set", {"catalog": {"enabled": False}})
ids_off = [p["id"] for p in j["providers"]]
check(u"после выключения списка настроенный каталожный остаётся видимым",
      "stranger-ai" in ids_off and len(ids_off) == 8)
st, j = post("/api/settings/set", {"provider": "stranger-ai", "key": "",
                                   "model": ""})
check(u"а без ключа и модели исчезает",
      "stranger-ai" not in [p["id"] for p in j["providers"]])
st, j = post("/api/settings/set", {"provider": "нет-такого-нигде"})
check(u"выдуманный идентификатор по-прежнему отклоняется",
      st == 400 and u"Неизвестный провайдер" in j["error"])

srv.shutdown()
_catalog.CATALOG_URL = _REAL_CATALOG_URL
shutil.rmtree(CFG, ignore_errors=True)
shutil.rmtree(UDD, ignore_errors=True)
n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
