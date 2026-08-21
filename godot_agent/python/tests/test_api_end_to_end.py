# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Сквозной тест работы по ключу API через настоящее приложение Flask.

Юнит-тесты проверяют модули по отдельности; здесь проверяется вся связка на
живом проекте: /chats/new -> /chat -> подтверждение действия -> файл на диске.
Именно на этом уровне ловятся ошибки стыков — например, что системный блок
собирается на реальном дереве проекта, что ответ доходит до панели в нужном
виде, что подтверждённая правка действительно применяется и что браузер при
всём этом не запускается.

Провайдера играет локальный HTTP-сервер, поэтому ни сети, ни ключей, ни Chrome
не требуется.
"""
import json
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CFG = tempfile.mkdtemp(prefix="agent_cfg_e2e_")
UDD = tempfile.mkdtemp(prefix="agent_udd_e2e_")
PROJ = tempfile.mkdtemp(prefix="agent_proj_e2e_")
_os0.environ["GODOT_AGENT_CONFIG_DIR"] = CFG

import api_history
import api_keys
import server_auth
import main

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


# ---------------------------------------------------------------------------
# Учебный проект Godot на диске
# ---------------------------------------------------------------------------
PLAYER_BEFORE = (u"extends CharacterBody2D\n"
                 u"\n"
                 u"var jumps := 1\n"
                 u"\n"
                 u"func _physics_process(_delta: float) -> void:\n"
                 u"\tif is_on_floor():\n"
                 u"\t\tjumps = 1\n")
_os0.makedirs(_os0.path.join(PROJ, "src", "scripts"), exist_ok=True)
PLAYER_PATH = _os0.path.join(PROJ, "src", "scripts", "player.gd")
with open(PLAYER_PATH, "w", encoding="utf-8") as f:
    f.write(PLAYER_BEFORE)
with open(_os0.path.join(PROJ, "project.godot"), "w", encoding="utf-8") as f:
    f.write("[application]\nconfig/name=\"e2e\"\n")

TOKEN = "e2e" + "0" * 29
with open(server_auth.token_path(UDD), "w", encoding="utf-8") as f:
    f.write(TOKEN)

# ---------------------------------------------------------------------------
# Локальный «провайдер»
# ---------------------------------------------------------------------------
ANSWER = (
    u"## Двойной прыжок\n\n"
    u"Меняю **jumps** в `player.gd` на 2.\n\n"
    u"```agent_action\n"
    u'{"action": "patch_file", "path": "res://src/scripts/player.gd",'
    u' "search": "var jumps := 1", "replace": "var jumps := 2",'
    u' "summary": "двойной прыжок"}\n'
    u"```\n"
    u"===DONE==="
)

SEEN = {"requests": [], "answer": ANSWER, "cut_times": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            SEEN["requests"].append(json.loads(raw.decode("utf-8")))
        except Exception:
            SEEN["requests"].append(None)
        text = SEEN["answer"]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        # Имитация сбоя сервиса: первые cut_times запросов обрываем на середине
        # ответа, не присылая ни finish_reason, ни [DONE]. Ровно так ведёт себя
        # упавший шлюз, и раньше такой ответ молча принимался за полный.
        if SEEN["cut_times"] > 0:
            SEEN["cut_times"] -= 1
            self.wfile.write(b"data: " + json.dumps({
                "model": "m/e2e",
                "choices": [{"delta": {"content": text[:40]},
                             "finish_reason": None}]}).encode("utf-8") + b"\n\n")
            self.wfile.flush()
            self.close_connection = True
            return
        step = 64
        for i in range(0, len(text), step):
            self.wfile.write(b"data: " + json.dumps({
                "model": "m/e2e",
                "choices": [{"delta": {"content": text[i:i + step]},
                             "finish_reason": None}]}).encode("utf-8") + b"\n\n")
            self.wfile.flush()
        self.wfile.write(b"data: " + json.dumps({
            "model": "m/e2e",
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1234, "completion_tokens": 56}}).encode("utf-8") + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")


srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

cl = main.app.test_client()
BASE_BODY = {"user_data_dir": UDD, "project_root": PROJ}
HEADERS = {server_auth.HEADER: TOKEN}


def post(path, body=None):
    r = cl.post(path, json=dict(BASE_BODY, **(body or {})), headers=HEADERS)
    return r.status_code, r.get_json()


api_keys.set_base_url("custom", "http://127.0.0.1:%d/v1" % PORT)

# ---------------------------------------------------------------------------
# 1) Синхронизация и создание чата по ключу
# ---------------------------------------------------------------------------
st, j = post("/init", {"godot_version": "4.6.0.stable"})
check(u"/init прошёл", st == 200 and j.get("success"), (st, j))
check(u"сервер привязался к проекту", server_auth.bound_dir() == UDD)

st, j = post("/chats/new", {"kind": "api", "provider": "custom",
                            "model": "m/e2e"})
check(u"API-чат создан", st == 200 and j.get("kind") == "api", (st, j))
CID = j["current_id"]

import server_state as S
check(u"браузер не запускался при создании чата", S.get_driver() is None)
check(u"запуск браузера даже не начинался", not S.browser_boot_started())

# ---------------------------------------------------------------------------
# 2) Сообщение пользователю -> ответ модели -> действие на подтверждение
# ---------------------------------------------------------------------------
st, j = post("/chat", {"prompt": u"сделай двойной прыжок"})
check(u"/chat ответил 200", st == 200, (st, j))
answer = str(j.get("answer", ""))
check(u"ответ пришёл", len(answer) > 0)
check(u"Markdown сконвертирован в BBCode", u"[b]jumps[/b]" in answer, answer[:200])
check(u"заголовок сконвертирован", u"[font_size=20]" in answer)
check(u"служебный блок действия скрыт", "agent_action" not in answer)
check(u"маркер ===DONE=== скрыт", "===DONE===" not in answer)
check(u"расход токенов показан", u"1\u2009234" in answer and u"tok" in answer)
check(u"действие ждёт подтверждения",
      bool(j.get("pending_action")), j.get("pending_action"))
check(u"в описании действия виден путь",
      "player.gd" in str(j.get("pending_action_description", "")))
check(u"панели передан дифф", bool(j.get("pending_action_diff")))

# ---------------------------------------------------------------------------
# 3) Что реально ушло провайдеру
# ---------------------------------------------------------------------------
check(u"провайдеру ушёл ровно один запрос", len(SEEN["requests"]) == 1,
      len(SEEN["requests"]))
req = SEEN["requests"][0] or {}
msgs = req.get("messages") or []
check(u"системный блок первым сообщением",
      msgs and msgs[0].get("role") == "system")
sysmsg = msgs[0].get("content", "") if msgs else ""
check(u"в системном блоке правила агента", u"agent_action" in sysmsg)
check(u"в системном блоке дерево реального проекта", u"player.gd" in sysmsg)
check(u"в системном блоке версия движка из /init", u"Godot 4.6" in sysmsg)
check(u"запрос пользователя ушёл последним",
      msgs[-1].get("role") == "user"
      and u"двойной прыжок" in msgs[-1].get("content", ""))
check(u"мега-промпт НЕ подмешан в текст запроса",
      u"agent_action" not in msgs[-1].get("content", ""))
check(u"модель из записи чата", req.get("model") == "m/e2e")
check(u"лимит вывода задан", int(req.get("max_tokens") or 0) > 0)

# ---------------------------------------------------------------------------
# 4) История диалога
# ---------------------------------------------------------------------------
hist = api_history.load_messages(UDD, CID)
check(u"в истории пара запрос+ответ", len(hist) == 2, len(hist))
check(u"в истории СЫРОЙ ответ с блоком действия",
      "```agent_action" in hist[1]["content"])
check(u"в истории нет BBCode", "[b]" not in hist[1]["content"])
check(u"расход токенов накоплен",
      api_history.stats(UDD, CID)["usage_total"]["prompt_tokens"] == 1234)

# ---------------------------------------------------------------------------
# 5) Подтверждение действия -> файл на диске
# ---------------------------------------------------------------------------
SEEN["requests"] = []
SEEN["answer"] = u"Готово, проверьте.\n===DONE==="
st, j = post("/chat/confirm_action", {"approved": True})
check(u"подтверждение прошло", st == 200, (st, j))
ENTRY_ID = str(j.get("history_entry_id", ""))
check(u"панели передан адрес записи журнала (для кнопки отката)",
      ENTRY_ID != "", j)
with open(PLAYER_PATH, "r", encoding="utf-8") as f:
    after = f.read()
check(u"файл на диске изменён", u"var jumps := 2" in after, after)
check(u"остальной код файла не пострадал",
      u"func _physics_process" in after and u"is_on_floor" in after)
# Применение правки НЕ обращается к модели: заметка о результате копится и
# уходит вместе со следующим сообщением пользователя. Это и есть экономия
# запроса, о которой всё это время речь — проверяем, что она не потерялась.
check(u"применение правки не стоило запроса к модели",
      len(SEEN["requests"]) == 0, len(SEEN["requests"]))
check(u"история не выросла от подтверждения",
      len(api_history.load_messages(UDD, CID)) == 2)

# ---------------------------------------------------------------------------
# 6) Следующее сообщение: успех применения по соглашению МОЛЧАЛИВЫЙ
# ---------------------------------------------------------------------------
# Системная заметка модели ставится только при отказе пользователя или откате.
# Успешное применение ничего не досылает — модель видит собственное действие в
# истории и считает его выполненным. Это соглашение существовало до работы по
# ключу; проверяем, что в API-режиме оно не сломалось в обе стороны.
st, j = post("/chat", {"prompt": u"что дальше?"})
check(u"второе сообщение прошло", st == 200, (st, j))
check(u"провайдеру ушёл ровно один новый запрос", len(SEEN["requests"]) == 1)
msgs2 = (SEEN["requests"][0] or {}).get("messages") or []
last_user = msgs2[-1].get("content", "") if msgs2 else ""
check(u"после УСПЕШНОГО применения лишней заметки нет",
      u"[Система" not in last_user, last_user[:200])
check(u"вопрос пользователя на месте", u"что дальше?" in last_user)
check(u"собственное действие модели вернулось ей в истории",
      any("```agent_action" in (m.get("content") or "")
          and m.get("role") == "assistant" for m in msgs2))
check(u"прошлый вопрос пользователя тоже в истории",
      any(u"двойной прыжок" in (m.get("content") or "") for m in msgs2[:-1]))
check(u"системный блок по-прежнему один и первый",
      msgs2 and msgs2[0]["role"] == "system"
      and sum(1 for m in msgs2 if m["role"] == "system") == 1)
check(u"системный блок пересобран со свежим деревом",
      u"player.gd" in msgs2[0].get("content", ""))
check(u"история выросла на второй обмен",
      len(api_history.load_messages(UDD, CID)) == 4)

# ---------------------------------------------------------------------------
# 7) ОТКАЗ пользователя обязан дойти до модели
# ---------------------------------------------------------------------------
SEEN["requests"] = []
SEEN["answer"] = (
    u"Добавлю HUD.\n\n"
    u"```agent_action\n"
    u'{"action": "create_file", "path": "res://src/scripts/hud.gd",'
    u' "content": "extends Control\\n"}\n'
    u"```\n"
    u"===DONE==="
)
st, j = post("/chat", {"prompt": u"добавь HUD"})
check(u"третье сообщение прошло", st == 200, (st, j))
check(u"новое действие ждёт подтверждения", bool(j.get("pending_action")))

SEEN["requests"] = []
st, j = post("/chat/confirm_action", {"approved": False})
check(u"отказ обработан", st == 200, (st, j))
check(u"файл после отказа не создан",
      not _os0.path.isfile(_os0.path.join(PROJ, "src", "scripts", "hud.gd")))
check(u"отказ не стоил запроса к модели", len(SEEN["requests"]) == 0)

SEEN["answer"] = u"Понял, не создаю.\n===DONE==="
st, j = post("/chat", {"prompt": u"ладно, оставь как есть"})
check(u"четвёртое сообщение прошло", st == 200, (st, j))
msgs4 = (SEEN["requests"][0] or {}).get("messages") or []
last4 = msgs4[-1].get("content", "") if msgs4 else ""
check(u"модель УЗНАЛА про отказ пользователя",
      u"[Система" in last4 and u"ОТКЛОНИЛ" in last4.upper(), last4[:300])
check(u"вопрос пользователя не потерялся", u"оставь как есть" in last4)

# ---------------------------------------------------------------------------
# 8) Браузер так и не понадобился
# ---------------------------------------------------------------------------
check(u"драйвер браузера не создан за весь сценарий", S.get_driver() is None)
check(u"запуск браузера не инициировался", not S.browser_boot_started())
st, j = post("/browser/status")
check(u"статус браузера — idle", j.get("state") == "idle", j)

# ---------------------------------------------------------------------------
# 9) АДРЕСНЫЙ откат по кнопке на карточке сообщения
# ---------------------------------------------------------------------------
# Проверяем то, что было сломано: откат отменяет ИМЕННО своё изменение, а не
# самое свежее в проекте. Для этого создаём ВТОРОЕ, более новое изменение в
# ДРУГОМ файле — раньше клик по первому облачку откатывал бы именно его.
SEEN["answer"] = (
    u"Правлю второй файл.\n\n"
    u"```agent_action\n"
    u'{"action": "create_file", "path": "res://src/scripts/other.gd",'
    u' "content": "extends Node\\n"}\n'
    u"```\n"
    u"===DONE==="
)
st, j = post("/chat", {"prompt": u"создай other.gd"})
check(u"пятое сообщение прошло", st == 200, (st, j))
SEEN["answer"] = u"Готово.\n===DONE==="
st, j = post("/chat/confirm_action", {"approved": True})
SECOND_ID = str(j.get("history_entry_id", ""))
OTHER_PATH = _os0.path.join(PROJ, "src", "scripts", "other.gd")
check(u"второе изменение применено",
      _os0.path.isfile(OTHER_PATH) and SECOND_ID != "" and SECOND_ID != ENTRY_ID)

# Предпросмотр по адресу ПЕРВОГО изменения — он должен описывать player.gd,
# а не самое свежее other.gd.
st, j = post("/chat/rollback/preview", {"entry_id": ENTRY_ID})
check(u"предпросмотр нашёл нужную запись", st == 200 and j.get("found") is True, j)
check(u"описан ИМЕННО player.gd, а не последнее изменение",
      "player.gd" in str(j.get("description", "")), j.get("description"))
check(u"адрес возвращён обратно", j.get("entry_id") == ENTRY_ID)
check(u"расширения до всей цепочки плана не предложено",
      not j.get("chain_id"), j)

# Сам откат по адресу.
st, j = post("/chat/rollback", {"entry_id": ENTRY_ID})
check(u"адресный откат выполнен", st == 200 and j.get("success"), (st, j))
with open(PLAYER_PATH, "r", encoding="utf-8") as f:
    reverted = f.read()
check(u"player.gd вернулся к исходному виду", u"var jumps := 1" in reverted, reverted)
check(u"ВТОРОЕ (более свежее) изменение НЕ тронуто — это и был баг",
      _os0.path.isfile(OTHER_PATH))

# Повторный откат того же адреса — понятный отказ, а не откат чего-то другого.
st, j = post("/chat/rollback/preview", {"entry_id": ENTRY_ID})
check(u"повторный предпросмотр: запись уже откачена",
      j.get("found") is False and j.get("gone") is True, j)
st, j = post("/chat/rollback", {"entry_id": ENTRY_ID})
check(u"повторный откат отклонён", st in (200, 409) and not j.get("success"), (st, j))
check(u"other.gd по-прежнему на месте (ничего лишнего не откатилось)",
      _os0.path.isfile(OTHER_PATH))

# Выдуманный адрес не приводит к откату «на всякий случай».
st, j = post("/chat/rollback", {"entry_id": "0123456789ab"})
check(u"выдуманный адрес ничего не откатывает",
      not j.get("success") and _os0.path.isfile(OTHER_PATH), (st, j))

# ---------------------------------------------------------------------------
# 10) Сбой провайдера посреди ответа: агент повторяет запрос САМ
#
# Главное, чего не хватало работе по ключу: сетевой сбой не повторялся вовсе, и
# один упавший запрос стоил пользователю всей задачи. Проверяем сквозным
# путём — через настоящий /chat, а не заглушку бэкенда.
#
# Расписание пауз на время теста укорачиваем до секунды: проверяем НАЛИЧИЕ
# повтора и его результат, а не длину продакшн-паузы (её проверяет
# test_rate_limit_sleep).
# ---------------------------------------------------------------------------
import rate_limit as RL

_OUTAGE_REAL = RL.OUTAGE_SLEEPS
_JITTER_REAL = RL.OUTAGE_JITTER
RL.OUTAGE_SLEEPS = [1, 1, 1, 1]
RL.OUTAGE_JITTER = 0.0

SEEN["answer"] = u"Готово, всё проверил.\n===DONE==="
SEEN["requests"] = []
_HIST_BEFORE_RETRY = len(api_history.load_messages(UDD, CID))
SEEN["cut_times"] = 2  # два обрыва, третий запрос удаётся
st, j = post("/chat", {"prompt": u"проверь проект"})
answer = str(j.get("answer", ""))
check(u"после двух обрывов ответ всё-таки получен", st == 200 and u"Готово" in answer,
      (st, answer[:200]))
check(u"агент сам сделал три попытки (две сорвались)",
      len(SEEN["requests"]) == 3, len(SEEN["requests"]))
check(u"в чат не попало сообщение об обрыве — сбой пережит незаметно",
      u"[Обрыв ответа]" not in answer, answer[:200])
check(u"повторялся ТОТ ЖЕ запрос, а не урезанный",
      all(u"проверь проект" in (r.get("messages") or [{}])[-1].get("content", "")
          for r in SEEN["requests"] if r))
check(u"оборванные попытки не оставили следа в истории (пара только одна)",
      len(api_history.load_messages(UDD, CID)) - _HIST_BEFORE_RETRY == 2,
      len(api_history.load_messages(UDD, CID)) - _HIST_BEFORE_RETRY)

# Сбой, который не проходит: агент обязан честно остановиться, а не висеть.
SEEN["requests"] = []
SEEN["cut_times"] = 99
st, j = post("/chat", {"prompt": u"ещё раз проверь"})
answer = str(j.get("answer", ""))
check(u"непроходящий сбой -> честное сообщение, а не вечный цикл",
      st == 200 and u"[Обрыв ответа]" in answer, (st, answer[:200]))
check(u"число попыток ограничено расписанием",
      len(SEEN["requests"]) == len(RL.OUTAGE_SLEEPS) + 1, len(SEEN["requests"]))
check(u"пользователю сказано, сколько раз повторяли",
      u"повторил запрос" in answer, answer[-300:])
check(u"пришедшая часть ответа не потеряна",
      u"Готово" in answer, answer[-300:])

# Бюджет ожидания на ход: даже при коротком расписании агент не должен
# копить паузы бесконечно, если внутри одного хода запросов много.
_BUDGET_REAL = main.MAX_RETRY_WAIT_PER_TURN
main.MAX_RETRY_WAIT_PER_TURN = 1.5
SEEN["requests"] = []
SEEN["cut_times"] = 99
st, j = post("/chat", {"prompt": u"и ещё раз"})
answer = str(j.get("answer", ""))
check(u"бюджет ожидания хода обрывает повторы раньше расписания",
      st == 200 and len(SEEN["requests"]) < len(RL.OUTAGE_SLEEPS) + 1,
      len(SEEN["requests"]))
check(u"про исчерпанный бюджет сказано прямо",
      u"ожидания" in answer, answer[-300:])
main.MAX_RETRY_WAIT_PER_TURN = _BUDGET_REAL

RL.OUTAGE_SLEEPS = _OUTAGE_REAL
RL.OUTAGE_JITTER = _JITTER_REAL
SEEN["cut_times"] = 0

# ---------------------------------------------------------------------------
# 11) Продолжить ТОТ ЖЕ чат на другой модели
#
# Модель закреплена за чатом намеренно, и агент не меняет её сам. Но тупика быть
# не должно: когда у провайдера кончились ключи, единственным выходом было
# создать новый чат и потерять переписку. Здесь проверяется, что переписка как
# раз НЕ теряется.
# ---------------------------------------------------------------------------
_hist_before = len(api_history.load_messages(UDD, CID))
check(u"до смены модели в чате есть история", _hist_before > 0)

st, j = post("/chats/model", {"model": "m/other"})
check(u"смена модели принята", st == 200 and j.get("ok") is True, (st, j))
check(u"чат отвечает новой моделью", j.get("model") == "m/other")
check(u"подпись чата обновлена", "m/other" in str(j.get("site", "")))
check(u"ПЕРЕПИСКА СОХРАНЕНА — это и есть смысл действия",
      len(api_history.load_messages(UDD, CID)) > _hist_before,
      len(api_history.load_messages(UDD, CID)))
_notes = [m for m in api_history.load_messages(UDD, CID)
          if u"отвечает другая модель" in str(m.get("content", ""))]
check(u"новой модели объяснено, что прежние ответы писала не она",
      len(_notes) == 1, len(_notes))
check(u"в пометке названы обе модели",
      "m/other" in _notes[0]["content"] and "m/e2e" in _notes[0]["content"])

SEEN["requests"] = []
st, j = post("/chat", {"prompt": u"продолжаем"})
check(u"следующий запрос уходит УЖЕ новой моделью",
      (SEEN["requests"][0] or {}).get("model") == "m/other",
      (SEEN["requests"][0] or {}).get("model"))
_msgs = (SEEN["requests"][0] or {}).get("messages") or []
check(u"прежняя переписка ушла новой модели в контексте",
      any(u"двойной прыжок" in str(m.get("content", "")) for m in _msgs))

# Отказы, которые пользователь должен прочитать, приходят с кодом 200: на любой
# не-200 панель уходит в автозапуск второй копии сервера и текст теряется.
st, j = post("/chats/model", {"model": "m/other"})
check(u"смена на ТУ ЖЕ модель — отказ словами, а не 400",
      st == 200 and j.get("ok") is False and j.get("error"), (st, j))
st, j = post("/chats/model", {"model": ""})
# ПУСТАЯ МОДЕЛЬ — ЭТО «ВОЗЬМИ МОДЕЛЬ ПРОВАЙДЕРА», а не ошибка запроса.
#
# Так же ведёт себя создание чата (/chats/new подставляет providers.model_for),
# и раньше эти два маршрута расходились: одно и то же действие человека —
# «переключиться на этого провайдера» — при создании чата работало, а при смене
# модели у открытого отвечало «не выбрана модель». Здесь у провайдера записана
# та же модель, на которую чат уже перешёл, поэтому подстановка приводит к
# честному отказу «это та же модель» — с кодом 200 и словами.
check(u"пустая модель = модель провайдера, а не ошибка запроса",
      st == 200 and j.get("ok") is False
      and u"та же модель" in str(j.get("error", "")), (st, j))
# А вот когда у провайдера не выбрано вообще ничего, отказ обязан объяснить, что
# делать. Это и есть случай только что заведённого провайдера: раньше он
# отвечал 400 «Не выбрана модель», и человек выходил из тупика пересозданием чата.
api_keys.set_model("custom", "")
api_keys.set_defaults("custom", "")
st, j = post("/chats/model", {"provider": "custom", "model": ""})
check(u"у провайдера без модели — отказ словами и подсказкой, а не 400",
      st == 200 and j.get("ok") is False
      and u"не выбрана модель" in str(j.get("error", "")).lower()
      and u"нажмите" in str(j.get("error", "")).lower(), (st, j))
api_keys.set_model("custom", "m/e2e")
st, j = post("/chats/model", {"provider": u"нет-такого", "model": "m/x"})
check(u"неизвестный провайдер — 400", st == 400, (st, j))

# ---------------------------------------------------------------------------
# 9б) НЕДАВНО ВЫБРАННЫЕ МОДЕЛИ
#
# Список из четырёхсот моделей по алфавиту бесполезен для выбора: сверху там
# оказывается то, что начинается на цифру. Панель поднимает наверх те, которыми
# человек работал, и порядок задаёт сервер — он же единственный знает, когда
# модель ДЕЙСТВИТЕЛЬНО закрепили за чатом, а не просто посмотрели в списке.
# ---------------------------------------------------------------------------
_recent = api_keys.get_recent()
check(u"смена модели попала в недавние", _recent[:1] == [
      {"provider": "custom", "model": "m/other"}], _recent)
check(u"прежняя модель осталась в списке ниже новой",
      {"provider": "custom", "model": "m/e2e"} in _recent, _recent)
_st, _payload = post("/api/providers", {})
check(u"недавние уходят в панель вместе с настройками",
      _payload.get("recent") == _recent, _payload.get("recent"))

srv.shutdown()
server_auth.reset()
for d in (CFG, UDD, PROJ):
    shutil.rmtree(d, ignore_errors=True)
n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
