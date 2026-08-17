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
# Локальный «провайдер» для успешных путей
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
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
        if self.path.endswith("/models"):
            self._json(200, {"data": [
                {"id": "vendor/paid", "pricing": {"prompt": "0.01", "completion": "0.02"}},
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

# ---------------------------------------------------------------------------
# 3) Обновление списка моделей
# ---------------------------------------------------------------------------
post("/api/settings/set", {"provider": "custom", "base_url": LOCAL,
                           "model": "vendor/gift:free"})
st, j = post("/api/models/refresh", {"provider": "custom"})
check(u"список моделей получен", st == 200 and "vendor/paid" in j["models"])
check(u"бесплатные модели идут первыми",
      j["models"][0] == "vendor/gift:free")
st, j = post("/api/models/refresh", {"provider": "custom", "free_only": True})
check(u"фильтр «только бесплатные» работает", j["models"] == ["vendor/gift:free"])
st, j = post("/api/models/refresh", {"provider": "нет"})
check(u"обновление моделей неизвестного провайдера -> 400", st == 400)

# ---------------------------------------------------------------------------
# 4) Проверка подключения
# ---------------------------------------------------------------------------
st, j = post("/api/test", {"provider": "custom", "model": "vendor/gift:free"})
check(u"проверка подключения успешна", st == 200 and j["ok"] is True)
check(u"показано время ответа", j["elapsed_ms"] >= 0 and u"мс" in j["message"])
check(u"видно, шёл ли запрос через прокси", j["via_proxy"] is False)

post("/api/settings/set", {"provider": "custom",
                           "base_url": "http://127.0.0.1:1/v1"})
st, j = post("/api/test", {"provider": "custom", "model": "vendor/gift:free"})
check(u"недоступный адрес -> ok=False, а не 500", st == 200 and j["ok"] is False)
check(u"в ошибке есть подсказка про прокси", u"прокси" in j["error"])
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

srv.shutdown()
shutil.rmtree(CFG, ignore_errors=True)
shutil.rmtree(UDD, ignore_errors=True)
n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
