# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Сквозной тест бэкенда работы по ключу API (api_backend).

Проверяется весь путь: send() -> транспорт -> разбор блока agent_action ->
запись истории -> живая трансляция в панель. Провайдером выступает настоящий
локальный HTTP-сервер, поэтому ни сети, ни ключей, ни браузера не нужно.
"""
import json
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import _fake_selenium
_fake_selenium.install()

_os0.environ["GODOT_AGENT_CONFIG_DIR"] = tempfile.mkdtemp(prefix="agent_cfg_")

import api_backend as AB
import api_history as H
import api_keys
import openai_compat as oc
import parser_base
import rate_limit

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


# ---------------------------------------------------------------------------
# Локальный «провайдер»
# ---------------------------------------------------------------------------

MODEL_ANSWER = (
    u"## Двойной прыжок\n\n"
    u"Правлю **player.gd**: счётчик `jumps`, метод `_physics_process` не меняю.\n\n"
    u"```agent_action\n"
    u'{"action": "patch_file", "path": "res://player.gd", '
    u'"search": "var jumps = 1", "replace": "var jumps = 2", '
    u'"summary": "двойной прыжок"}\n'
    u"```\n"
    u"===DONE==="
)

LAST_REQUEST = {"body": None}
MODE = {"name": "ok"}
# Все тела запросов подряд и счётчик вызовов: дописывание ответа и усадка
# контекста — это НЕСКОЛЬКО запросов на один send(), и проверять надо каждый.
ALL_REQUESTS = []
CALLS = {"n": 0}
# Заголовок Authorization каждого запроса: по нему видно, КАКИМ ключом ушёл
# запрос. Сравнивать будем с ожидаемым ключом — это единственный честный способ
# проверить, что ротация подставила именно тот ключ, а не сделала вид.
AUTH_SEEN = []

# Точка обрыва внутри JSON действия: до неё блок заведомо незакрыт и разобрать
# его нельзя — ровно тот случай, для которого дописывание и нужно.
CUT_AT = MODEL_ANSWER.index(u'"search"')
PART1 = MODEL_ANSWER[:CUT_AT]
PART2 = MODEL_ANSWER[CUT_AT:]
# Та же вторая часть, но модель повторила последние 30 символов первой —
# так ведёт себя часть моделей, и перехлёст обязан быть срезан.
PART2_OVERLAP = MODEL_ANSWER[CUT_AT - 30:]

_CTX_BODY = {"error": {"message": "This model's maximum context length is "
                                  "8192 tokens, however you requested more"}}


def sse(obj):
    return b"data: " + json.dumps(obj).encode("utf-8") + b"\n\n"


def _sse_text(text, finish="stop", usage=True, reasoning=False):
    """События SSE для произвольного текста, признака конца и вида содержимого."""
    out = []
    step = 40
    for i in range(0, len(text), step):
        piece = text[i:i + step]
        out.append(sse({"model": "m/test", "choices": [
            {"delta": ({"reasoning": piece} if reasoning else {"content": piece}),
             "finish_reason": None}]}))
    tail = {"model": "m/test", "choices": [{"delta": {}, "finish_reason": finish}]}
    if usage:
        tail["usage"] = {"prompt_tokens": 700, "completion_tokens": 60}
    out.append(sse(tail))
    out.append(b"data: [DONE]\n\n")
    return out


def _chunks_for(text, finish="stop"):
    return _sse_text(text, finish=finish)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send_error(self, status, body, extra=None):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            LAST_REQUEST["body"] = json.loads(raw.decode("utf-8"))
        except Exception:
            LAST_REQUEST["body"] = None
        ALL_REQUESTS.append(LAST_REQUEST["body"])
        AUTH_SEEN.append(self.headers.get("Authorization") or "")
        CALLS["n"] += 1
        mode = MODE["name"]
        # Отказ «контекст не влез»: всегда либо только на первом запросе.
        if mode == "ctx_always" or (mode == "ctx_then_ok" and CALLS["n"] == 1):
            self._send_error(400, _CTX_BODY)
            return
        # Отказ, из-за которого СТОИТ сменить ключ (суточная квота). У rot_ok
        # только на первом запросе — второй ключ обязан сработать.
        if mode == "rot_all" or (mode == "rot_ok" and CALLS["n"] == 1):
            self._send_error(429, {"error": {"message":
                                             "Rate limit: free-models-per-day"}})
            return
        # Отказ, из-за которого ключ менять НЕЛЬЗЯ: сервис лежит.
        if mode == "rot_server":
            self._send_error(503, {"error": {"message": "overloaded"}})
            return
        if mode in ("auth", "ratelimit", "daily", "server"):
            status, body, extra = {
                "auth": (401, {"error": {"message": "Invalid API key"}}, {}),
                "ratelimit": (429, {"error": {"message": "Rate limit exceeded"}},
                              {"Retry-After": "7"}),
                "daily": (429, {"error": {"message": "Rate limit: free-models-per-day"}}, {}),
                "server": (503, {"error": {"message": "overloaded"}}, {}),
            }[mode]
            self._send_error(status, body, extra)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        # Обрыв посреди потока: пишем часть событий и закрываем соединение, НЕ
        # присылая ни [DONE], ни finish_reason. Закрытие именно аккуратное (FIN,
        # а не сброс) — это самый коварный вид обрыва: чтение не падает с
        # ошибкой, и без явной проверки маркеров конца обрезанный ответ
        # выглядит совершенно нормальным успешным ответом.
        if mode in ("cut_after_action", "cut_in_prose", "cut_in_action"):
            text = {
                # Действие успело прийти ЦЕЛИКОМ (блок закрыт) — такой ответ
                # незачем повторять, его надо забрать.
                "cut_after_action": MODEL_ANSWER,
                # Оборвалось на объяснении, действия нет вовсе.
                "cut_in_prose": u"Сейчас посмотрю player.gd и поправлю прыжок, "
                                u"мне нужно свериться со счётчиком",
                # Оборвалось ПОСРЕДИ JSON действия: блок не закрыт, доверия
                # такому обрывку нет — нужен честный повтор.
                "cut_in_action": MODEL_ANSWER[:MODEL_ANSWER.index(u"}\n```")],
            }[mode]
            for i in range(0, len(text), 40):
                try:
                    self.wfile.write(sse({"model": "m/test", "choices": [
                        {"delta": {"content": text[i:i + 40]},
                         "finish_reason": None}]}))
                    self.wfile.flush()
                except Exception:
                    return
            self.close_connection = True
            return
        if mode == "empty":
            chunks = _chunks_for(u"")
        elif mode == "empty_no_events":
            # 200, поток открылся и кончился, не прислав ни одного события —
            # так выглядит сбой шлюза, а не ответ модели.
            chunks = [b"data: [DONE]\n\n"]
        elif mode == "empty_reasoning":
            # «Думающая» модель израсходовала лимит вывода на размышления и до
            # самого ответа не дошла.
            chunks = _sse_text(u"Надо посмотреть player.gd... " * 4,
                               finish="length", reasoning=True)
        elif mode == "cut":
            chunks = _chunks_for(MODEL_ANSWER[:80], finish="length")
        elif mode == "openfence":
            chunks = _chunks_for(u"Начинаю.\n```agent_action\n{\"action\": \"list_files\"",
                                 finish="length")
        elif mode == "length_with_action":
            # Лимит вывода кончился, но блок действия уже ЗАКРЫТ и разобран:
            # дописывать нечего и опасно (второй блок вытеснил бы первый).
            chunks = _chunks_for(MODEL_ANSWER, finish="length")
        elif mode in ("cont", "cont_overlap"):
            if CALLS["n"] == 1:
                chunks = _sse_text(PART1, finish="length")
            else:
                chunks = _sse_text(
                    PART2 if mode == "cont" else PART2_OVERLAP, finish="stop")
        elif mode == "cont_forever":
            # Модель упирается в лимит на каждом дописывании и каждый раз
            # добавляет НОВЫЙ текст: проверяет потолок числа дописываний.
            chunks = _sse_text(u"часть %d, " % CALLS["n"], finish="length")
        elif mode == "slow":
            chunks = _chunks_for(u"a" * 4000)
        else:
            chunks = _chunks_for(MODEL_ANSWER)
        for c in chunks:
            try:
                self.wfile.write(c)
                self.wfile.flush()
            except Exception:
                return
            if mode == "slow":
                time.sleep(0.05)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

# Провайдер «свой адрес» указываем на локальный сервер: ключ ему не нужен.
api_keys.set_base_url("custom", "http://127.0.0.1:%d/v1" % PORT)
BASE = tempfile.mkdtemp(prefix="agent_udd_")
REC = {"id": "chat00000001", "kind": "api", "provider": "custom", "model": "m/test"}
SYS = u"СИСТЕМНЫЙ БЛОК: правила агента и дерево проекта"


def backend(rec=None):
    return AB.ApiBackend(rec or REC, BASE,
                         system_text_provider=lambda: SYS,
                         max_tokens=1000)


# ---------------------------------------------------------------------------
# 1) Разбор ответа модели (чистые функции)
# ---------------------------------------------------------------------------
raw, prose = AB.split_action_block(MODEL_ANSWER)
check(u"блок agent_action найден", raw is not None and '"patch_file"' in raw)
check(u"текст без блока не содержит ```agent_action", "agent_action" not in prose)
check(u"текст-объяснение сохранён", u"Двойной прыжок" in prose)

two = u"пример:\n```agent_action\n{\"action\": \"a\"}\n```\nа теперь настоящее:\n" \
       u"```agent_action\n{\"action\": \"b\"}\n```"
raw2, _ = AB.split_action_block(two)
check(u"из двух блоков берётся ПОСЛЕДНИЙ", '"b"' in raw2 and '"a"' not in raw2)

raw3, prose3 = AB.split_action_block(u"текст\n```agent_action\n{\"action\": \"x\"")
check(u"незакрытый блок тоже извлекается", raw3 is not None and '"x"' in raw3)
check(u"текст перед незакрытым блоком сохранён", prose3.strip() == u"текст")

check(u"нет блока — текст возвращается как есть",
      AB.split_action_block(u"просто ответ") == (None, u"просто ответ"))
check(u"===DONE=== убирается",
      AB.strip_done_marker(u"ответ\n===DONE===") == u"ответ")
check(u"===DONE=== с пробелами тоже убирается",
      AB.strip_done_marker(u"ответ\n  ===DONE===  \n") == u"ответ")
check(u"текст без маркера не портится",
      AB.strip_done_marker(u"ответ про ===DONE=== внутри строки").endswith(u"внутри строки"))

check(u"реплика пользователя опознана как prompt",
      AB._guess_user_kind(u"добавь прыжок") == H.KIND_PROMPT)
check(u"системная вставка опознана как результат инструмента",
      AB._guess_user_kind(u"[Система]: содержимое res://a.gd:\n...") == H.KIND_TOOL_RESULT)

# Разбор действия должен вести себя ТАК ЖЕ, как браузерный путь.
act_ok, _ = AB.parse_action(MODEL_ANSWER)
check(u"нормальный блок -> действие", (act_ok or {}).get("action") == "patch_file")

act_bad, _ = AB.parse_action(u"текст\n```agent_action\n{это, не: json,,}\n```")
check(u"битый JSON -> parse_error (сигнал самоисцелению, а не потеря задачи)",
      (act_bad or {}).get("action") == "parse_error")
check(u"parse_error несёт сырой текст для повторной отправки",
      "не: json" in (act_bad or {}).get("raw", ""))

act_bare, _ = AB.parse_action(
    u'Действие: {"action": "list_files", "dir": "res://src/"} — готово.')
check(u"действие голым текстом вне блока всё равно найдено (страховка «план В»)",
      (act_bare or {}).get("action") == "list_files")

xml_call = u'''Проверяю управление персонажем.
<dots_function_call>
<action>
<server_name>godot</server_name>
<tool_name>ask_librarian</tool_name>
<arguments>{"query": "player movement input control scheme", "reason": "Find movement"}</arguments>
</action>
</dots_function_call>
'''
xml_action, xml_prose = AB.parse_action(xml_call)
check(u"XML tool call преобразуется в ask_librarian",
      (xml_action or {}).get("action") == "ask_librarian")
check(u"аргументы XML tool call сохраняются",
      (xml_action or {}).get("query") == "player movement input control scheme")
check(u"XML tool call удаляется из текста ответа",
      "dots_function_call" not in xml_prose)

xml_bad, _ = AB.parse_action(
    u"<dots_function_call><action><tool_name>ask_librarian</tool_name>"
    u"<arguments>{bad json}</arguments></action></dots_function_call>")
check(u"битый XML tool call передаётся в самоисцеление",
      (xml_bad or {}).get("action") == "parse_error")

xml_cut, xml_cut_prose = AB.parse_action(
    u"Начинаю поиск.\n<dots_function_call><action><tool_name>ask_librarian")
check(u"оборванный XML tool call передаётся в самоисцеление",
      (xml_cut or {}).get("action") == "parse_error")
check(u"оборванный XML не показывается пользователю",
      "dots_function_call" not in xml_cut_prose)

act_none, _ = AB.parse_action(u"просто объяснение без действий")
check(u"нет действия -> None", act_none is None)

# ---------------------------------------------------------------------------
# 2) Успешный обмен
# ---------------------------------------------------------------------------
MODE["name"] = "ok"
seen = []
res = backend().send(u"добавь двойной прыжок",
                     progress_cb=lambda info: seen.append(info),
                     cancel_cb=lambda: False)

check(u"действие разобрано", isinstance(res.get("action"), dict))
check(u"действие то самое", (res["action"] or {}).get("action") == "patch_file")
check(u"путь действия дошёл", (res["action"] or {}).get("path") == "res://player.gd")
check(u"в тексте для панели нет блока действия", "agent_action" not in res["text"])
check(u"в тексте для панели нет ===DONE===", "===DONE===" not in res["text"])
check(u"на месте блока стоит заглушка", u"предлагает действие" in res["text"])
check(u"Markdown сконвертирован в BBCode: жирный",
      u"[b]player.gd[/b]" in res["text"])
check(u"Markdown сконвертирован в BBCode: заголовок",
      u"[font_size=20]" in res["text"])
check(u"Markdown сконвертирован в BBCode: инлайн-код",
      u"[code]jumps[/code]" in res["text"])
check(u"подчёркивания в имени метода не стали курсивом",
      u"_physics_process" in res["text"] and u"[i]" not in res["text"])
check(u"сырые звёздочки Markdown в панель не попали",
      "**" not in res["text"] and "##" not in res["text"])
check(u"сырой ответ отдан отдельным полем", "```agent_action" in res["raw"])
check(u"usage прочитан", (res.get("usage") or {}).get("prompt_tokens") == 700)
check(u"finish_reason прочитан", res.get("finish_reason") == "stop")
check(u"расход токенов показан под ответом",
      u"700" in res["text"] and u"tok" in res["text"])
check(u"показан и накопленный итог по чату", u"\u03a3" in res["text"])
check(u"числа разбиты по разрядам", AB._fmt_num(1234567) == u"1\u2009234\u2009567")
check(u"без usage строка расхода не появляется", AB.usage_line(None, {}) == u"")
check(u"пустой usage не даёт строку расхода", AB.usage_line({}, {}) == u"")

body = LAST_REQUEST["body"] or {}
msgs = body.get("messages") or []
check(u"системный блок ушёл ОТДЕЛЬНЫМ сообщением",
      msgs and msgs[0].get("role") == "system" and msgs[0]["content"] == SYS)
check(u"мега-промпт НЕ подмешан в текст запроса",
      SYS not in (msgs[-1].get("content") or ""))
check(u"запрос пользователя ушёл последним",
      msgs[-1].get("role") == "user" and msgs[-1]["content"] == u"добавь двойной прыжок")
check(u"модель из записи чата, а не из настроек", body.get("model") == "m/test")
check(u"max_tokens дошёл", body.get("max_tokens") == 1000)

# ---------------------------------------------------------------------------
# 3) Живая трансляция
# ---------------------------------------------------------------------------
streams = [str(i.get("stream", "")) for i in seen]
check(u"прогресс сообщался", len(seen) >= 2)
check(u"поток только растёт (панель считает дельту по длине)",
      all(len(streams[i]) <= len(streams[i + 1]) for i in range(len(streams) - 1)))
check(u"итоговый поток равен сырому ответу", streams[-1] == res["raw"])
check(u"есть все поля, которые читает панель",
      all(k in seen[-1] for k in ("phase", "chars", "elapsed", "stream")))
check(u"chars соответствует длине", seen[-1]["chars"] == len(res["raw"]))

# ---------------------------------------------------------------------------
# 4) История: сырой текст, атомарная пара
# ---------------------------------------------------------------------------
hist = H.load_messages(BASE, REC["id"])
check(u"в историю записана пара запрос+ответ", len(hist) == 2)
check(u"в истории СЫРОЙ ответ с блоком действия",
      "```agent_action" in hist[1]["content"] and hist[1]["content"].endswith("===DONE==="))
check(u"в истории нет заглушки для панели",
      u"предлагает действие" not in hist[1]["content"])
check(u"реплика помечена как prompt", hist[0]["kind"] == H.KIND_PROMPT)
check(u"расход токенов накоплен",
      H.stats(BASE, REC["id"])["usage_total"]["prompt_tokens"] == 700)

# Второй обмен: история должна уехать в запрос.
MODE["name"] = "ok"
backend().send(u"теперь тройной", cancel_cb=lambda: False)
msgs2 = (LAST_REQUEST["body"] or {}).get("messages") or []
check(u"история предыдущего обмена ушла в новый запрос",
      any(m.get("content") == u"добавь двойной прыжок" for m in msgs2))
check(u"ответ модели вернулся ей как assistant",
      any(m.get("role") == "assistant" and "```agent_action" in (m.get("content") or "")
          for m in msgs2))
check(u"системный блок по-прежнему один и первый",
      msgs2[0]["role"] == "system"
      and sum(1 for m in msgs2 if m["role"] == "system") == 1)

# ---------------------------------------------------------------------------
# 5) Обрезанный лимитом вывода ответ
# ---------------------------------------------------------------------------
MODE["name"] = "cut"
res_cut = backend({"id": "cut000000001", "kind": "api",
                   "provider": "custom", "model": "m/test"}).send(
    u"длинный файл", cancel_cb=lambda: False)
check(u"обрезанный ответ помечен для пользователя",
      u"обрезан лимитом вывода" in res_cut["text"])
check(u"finish_reason=length виден вызывающему",
      res_cut.get("finish_reason") == "length")

MODE["name"] = "openfence"
res_open = backend({"id": "open00000001", "kind": "api",
                    "provider": "custom", "model": "m/test"}).send(
    u"дай дерево", cancel_cb=lambda: False)
check(u"незакрытый блок всё равно отдан парсеру действий",
      res_open.get("action") is not None)

# ---------------------------------------------------------------------------
# 5a) Дописывание ответа, упёршегося в лимит вывода
#
# finish_reason == "length" — точный факт, известный только по API. Раньше он
# лишь помечался плашкой, а рваный JSON действия разбирал самоисцелитель, прося
# модель прислать ответ ЗАНОВО. Дописать хвост дешевле ровно на один полный
# ответ.
# ---------------------------------------------------------------------------
check(u"обрыв для теста сделан ВНУТРИ JSON (блок незакрыт)",
      AB.usable_action(PART1) is None and AB.usable_action(PART1 + PART2) is not None)

MODE["name"] = "cont"
CALLS["n"] = 0
del ALL_REQUESTS[:]
res_cont = backend({"id": "cont00000001", "kind": "api",
                    "provider": "custom", "model": "m/test"}).send(
    u"почини прыжок", cancel_cb=lambda: False)
check(u"дописанный ответ содержит целое действие",
      isinstance(res_cont["action"], dict)
      and res_cont["action"].get("action") == "patch_file"
      and res_cont["action"].get("search") == "var jumps = 1")
check(u"на дописывание ушёл ровно один дополнительный запрос",
      len(ALL_REQUESTS) == 2)
check(u"плашка «обрезан лимитом» снята: ответ дописан целиком",
      u"обрезан лимитом вывода" not in res_cont["text"])
check(u"вызывающему виден финальный finish, а не промежуточный",
      res_cont.get("finish_reason") == "stop")
_cont_msgs = (ALL_REQUESTS[1] or {}).get("messages") or []
check(u"во втором запросе уже полученный текст ушёл репликой assistant",
      any(m.get("role") == "assistant" and m.get("content") == PART1
          for m in _cont_msgs))
check(u"во втором запросе есть просьба продолжить с места обрыва",
      _cont_msgs and _cont_msgs[-1].get("role") == "user"
      and u"РОВНО с того символа" in _cont_msgs[-1].get("content", ""))
check(u"расход токенов СЛОЖЕН по двум запросам, а не взят от последнего",
      (res_cont.get("usage") or {}).get("prompt_tokens") == 1400)
check(u"в историю ушла ОДНА пара с полным текстом, а не два огрызка",
      len(H.load_messages(BASE, "cont00000001")) == 2
      and H.load_messages(BASE, "cont00000001")[1]["content"] == PART1 + PART2)

# Перехлёст: модель повторила конец предыдущей части.
MODE["name"] = "cont_overlap"
CALLS["n"] = 0
res_ovl = backend({"id": "ovl000000001", "kind": "api",
                   "provider": "custom", "model": "m/test"}).send(
    u"почини прыжок", cancel_cb=lambda: False)
check(u"повторённый моделью перехлёст срезан — текст склеен ровно",
      H.load_messages(BASE, "ovl000000001")[1]["content"] == PART1 + PART2)
check(u"действие из склеенного текста разобралось",
      isinstance(res_ovl["action"], dict)
      and res_ovl["action"].get("action") == "patch_file")

# Готовое действие + лимит вывода: дописывать НЕ надо. Это не экономия, а
# защита: второй блок действия вытеснил бы первый по правилу «побеждает
# последний», и выполнилось бы не то, что модель решила.
MODE["name"] = "length_with_action"
CALLS["n"] = 0
del ALL_REQUESTS[:]
res_lwa = backend({"id": "lwa000000001", "kind": "api",
                   "provider": "custom", "model": "m/test"}).send(
    u"почини прыжок", cancel_cb=lambda: False)
check(u"при готовом действии дописывание НЕ запрашивается",
      len(ALL_REQUESTS) == 1)
check(u"действие взято как есть",
      isinstance(res_lwa["action"], dict)
      and res_lwa["action"].get("action") == "patch_file")
check(u"пользователю всё равно сказано про лимит вывода",
      u"обрезан лимитом вывода" in res_lwa["text"])

# Модель упирается в лимит бесконечно — число дописываний ограничено.
MODE["name"] = "cont_forever"
CALLS["n"] = 0
del ALL_REQUESTS[:]
res_inf = backend({"id": "inf000000001", "kind": "api",
                   "provider": "custom", "model": "m/test"}).send(
    u"пиши много", cancel_cb=lambda: False)
check(u"число дописываний ограничено потолком",
      len(ALL_REQUESTS) == AB.MAX_CONTINUATIONS + 1)
check(u"накопленный текст отдан, а не выброшен",
      u"часть 1" in res_inf["text"] and u"часть 4" in res_inf["text"])
check(u"честная плашка про лимит вывода осталась",
      u"обрезан лимитом вывода" in res_inf["text"])

# ---------------------------------------------------------------------------
# 5b) Усадка контекста вместо тупика «начните новый чат»
# ---------------------------------------------------------------------------
MODE["name"] = "ctx_then_ok"
CALLS["n"] = 0
del ALL_REQUESTS[:]
res_ctx = backend({"id": "ctx000000001", "kind": "api",
                   "provider": "custom", "model": "m/test"}).send(
    u"почини прыжок", cancel_cb=lambda: False)
check(u"после отказа «контекст не влез» запрос прошёл со сжатой историей",
      isinstance(res_ctx["action"], dict) and len(ALL_REQUESTS) == 2)
check(u"пользователю не предложено терять переписку",
      u"Контекст переполнен" not in res_ctx["text"])

MODE["name"] = "ctx_always"
CALLS["n"] = 0
del ALL_REQUESTS[:]
res_ctx2 = backend({"id": "ctx000000002", "kind": "api",
                    "provider": "custom", "model": "m/test"}).send(
    u"почини прыжок", cancel_cb=lambda: False)
check(u"если сжатие не помогло — честный текст, а не бесконечный цикл",
      u"[Контекст переполнен]" in res_ctx2["text"])
check(u"попыток сжатия ровно столько, сколько разрешено",
      len(ALL_REQUESTS) == AB.MAX_HISTORY_SHRINKS + 1)
check(u"неудачная усадка ничего не записала в историю",
      H.load_messages(BASE, "ctx000000002") == [])

# ---------------------------------------------------------------------------
# 6) Пустой ответ
# ---------------------------------------------------------------------------
MODE["name"] = "empty"
res_empty = backend({"id": "empty0000001", "kind": "api",
                     "provider": "custom", "model": "m/test"}).send(
    u"привет", cancel_cb=lambda: False)
check(u"пустой ответ -> честное сообщение", u"Пустой ответ" in res_empty["text"])
check(u"пустой ответ не пишется в историю",
      H.load_messages(BASE, "empty0000001") == [])

# ---------------------------------------------------------------------------
# 7) Ошибки провайдера
# ---------------------------------------------------------------------------
MODE["name"] = "auth"
res_auth = backend().send(u"вопрос", cancel_cb=lambda: False)
check(u"401 -> понятный текст про ключ", u"[Ключ API]" in res_auth["text"])
check(u"401 не считается лимитом", AB.pop_rate_limit_status() is None)
check(u"401 не пишет в историю (пара не полная)",
      len(H.load_messages(BASE, REC["id"])) == 4)

MODE["name"] = "ratelimit"
res_rl = backend().send(u"вопрос", cancel_cb=lambda: False)
check(u"429 -> текст про лимит", u"[Лимит запросов]" in res_rl["text"])
check(u"429 отдаётся существующему спящему режиму",
      AB.pop_rate_limit_status() == 429)
check(u"статус лимита читается один раз", AB.pop_rate_limit_status() is None)

MODE["name"] = "daily"
res_day = backend().send(u"вопрос", cancel_cb=lambda: False)
check(u"суточный лимит -> отдельный текст", u"[Суточный лимит]" in res_day["text"])
check(u"суточный лимит НЕ уводит сервер в бесполезный сон",
      AB.pop_rate_limit_status() is None)

MODE["name"] = "server"
res_srv = backend().send(u"вопрос", cancel_cb=lambda: False)
check(u"5xx -> текст про недоступность", u"[Сервис недоступен]" in res_srv["text"])
check(u"5xx отдаётся спящему режиму (повтор имеет смысл)",
      AB.pop_rate_limit_status() == 503)

# ---------------------------------------------------------------------------
# 7a) Обрыв ответа: повтор и спасение уже пришедшего действия
#
# Самый частый вид отказа по ключу и самый дорогой из бывших: сетевой сбой
# раньше НЕ повторялся вовсе (describe_api_error отдавал None), а обрывок
# ответа выбрасывался, хотя пользователь только что видел его в панели.
# ---------------------------------------------------------------------------
check(u"сетевой сбой теперь уходит в повтор, а не теряет запрос",
      AB.describe_api_error(oc.TransportError(u"обрыв TLS при чтении потока"),
                            u"OpenRouter", u"m/test")[1] == rate_limit.TRANSPORT)
check(u"неверный ключ по-прежнему НЕ повторяется (повтор бессмыслен)",
      AB.describe_api_error(oc.AuthError(u"Invalid API key"),
                            u"OpenRouter", u"m/test")[1] is None)

# Обрыв на объяснении: действия нет — нужен честный повтор.
AB.pop_rate_limit_status()
MODE["name"] = "cut_in_prose"
res_cut = backend({"id": "cutprose0001", "kind": "api",
                   "provider": "custom", "model": "m/test"}).send(
    u"почини прыжок", cancel_cb=lambda: False)
check(u"молчаливый обрыв больше не выдаётся за готовый ответ",
      u"[Обрыв ответа]" in res_cut["text"] and res_cut["action"] is None)
check(u"обрыв отдаётся спящему режиму как сетевой сбой",
      AB.pop_rate_limit_status() == rate_limit.TRANSPORT)
check(u"оборванный ответ НЕ попал в историю как полный",
      H.load_messages(BASE, "cutprose0001") == [])
check(u"пришедшая часть ответа не потеряна — она в сообщении",
      u"свериться со счётчиком" in res_cut["text"])

# Обрыв ПОСРЕДИ JSON действия: блок не закрыт, спасать нечего.
AB.pop_rate_limit_status()
MODE["name"] = "cut_in_action"
res_cut_act = backend({"id": "cutaction001", "kind": "api",
                       "provider": "custom", "model": "m/test"}).send(
    u"почини прыжок", cancel_cb=lambda: False)
check(u"обрыв посреди JSON действия НЕ выдаётся за действие",
      res_cut_act["action"] is None and u"[Обрыв ответа]" in res_cut_act["text"])
check(u"незакрытый блок тоже уходит в повтор",
      AB.pop_rate_limit_status() == rate_limit.TRANSPORT)
check(u"рваное действие не попало в историю",
      H.load_messages(BASE, "cutaction001") == [])

# Обрыв ПОСЛЕ целого блока действия: повторять нечего, работу надо забрать.
AB.pop_rate_limit_status()
MODE["name"] = "cut_after_action"
res_rescue = backend({"id": "rescue000001", "kind": "api",
                      "provider": "custom", "model": "m/test"}).send(
    u"почини прыжок", cancel_cb=lambda: False)
check(u"целое действие из обрывка спасено, а не выброшено",
      isinstance(res_rescue["action"], dict)
      and res_rescue["action"].get("action") == "patch_file"
      and res_rescue["action"].get("path") == "res://player.gd")
check(u"спасённый ответ НЕ уходит в повтор (он уже пригоден)",
      AB.pop_rate_limit_status() is None)
check(u"пользователь предупреждён, что ответ неполный",
      u"оборвалась" in res_rescue["text"])
check(u"спасённый ответ выглядит как обычный: заглушка блока на месте",
      AB.ACTION_PLACEHOLDER.strip() in res_rescue["text"])
check(u"спасённый ответ записан в историю целой парой",
      len(H.load_messages(BASE, "rescue000001")) == 2)
check(u"расход токенов у спасённого ответа не выдумывается",
      res_rescue["usage"] is None and u"tok" not in res_rescue["text"])

# ---------------------------------------------------------------------------
# 8) Отмена
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 7b) Ротация ключей: квота считается НА КЛЮЧ
#
# Главная польза для бесплатных тарифов: когда первый ключ упёрся в суточную
# квоту, второй ключ того же провайдера работает как ни в чём не бывало. Смена
# ключа мгновенна, поэтому пробовать её надо ДО того, как уходить в паузу.
# ---------------------------------------------------------------------------
RK1 = "sk-or-v1-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
RK2 = "sk-or-v1-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
api_keys.set_base_url("openrouter", "http://127.0.0.1:%d/v1" % PORT)
api_keys.set_key("openrouter", RK1)
api_keys.add_key("openrouter", RK2)
ROT_REC = {"id": "rot000000001", "kind": "api",
           "provider": "openrouter", "model": "m/test"}

MODE["name"] = "rot_ok"
CALLS["n"] = 0
del ALL_REQUESTS[:]
del AUTH_SEEN[:]
AB.pop_rate_limit_status()
res_rot = AB.ApiBackend(ROT_REC, BASE, system_text_provider=lambda: SYS,
                        max_tokens=1000).send(u"вопрос", cancel_cb=lambda: False)
check(u"после исчерпания первого ключа ответ получен вторым",
      isinstance(res_rot["action"], dict))
check(u"запросов было два: по одному на ключ", len(ALL_REQUESTS) == 2)
check(u"первый запрос ушёл ПЕРВЫМ ключом",
      AUTH_SEEN[0] == "Bearer " + RK1)
check(u"второй запрос ушёл ВТОРЫМ ключом — ротация настоящая",
      AUTH_SEEN[1] == "Bearer " + RK2)
check(u"смена ключа НЕ уводит сервер в паузу (она мгновенна)",
      AB.pop_rate_limit_status() is None)
check(u"пользователю сказано про смену ключа — это факт про деньги",
      u"перешёл на" in res_rot["text"])
check(u"в пометке названа причина, а не просто «исчерпан»",
      u"суточная квота" in res_rot["text"])
check(u"сырых ключей в тексте для панели нет",
      RK1 not in res_rot["text"] and RK2 not in res_rot["text"])
check(u"исчерпанный ключ выпал из кандидатов и в следующий раз не пробуется",
      [k for _i, k in api_keys.usable_keys("openrouter")] == [RK2])

# Сервис лежит — ключ менять НЕЛЬЗЯ, иначе все ключи объявятся исчерпанными
# из-за чужой поломки.
api_keys.clear_key_cooldowns("openrouter")
MODE["name"] = "rot_server"
CALLS["n"] = 0
del ALL_REQUESTS[:]
AB.pop_rate_limit_status()
res_rs = AB.ApiBackend(ROT_REC, BASE, system_text_provider=lambda: SYS,
                       max_tokens=1000).send(u"вопрос", cancel_cb=lambda: False)
check(u"на 5xx ключи НЕ перебираются", len(ALL_REQUESTS) == 1)
check(u"5xx по-прежнему уходит в спящий режим",
      AB.pop_rate_limit_status() == 503)
check(u"ни один ключ не объявлен исчерпанным из-за поломки сервиса",
      len(api_keys.usable_keys("openrouter")) == 2)
check(u"про смену ключа ничего не сказано", u"перешёл на" not in res_rs["text"])

# Все ключи исчерпаны — честное перечисление, а не «поверьте на слово».
MODE["name"] = "rot_all"
CALLS["n"] = 0
del ALL_REQUESTS[:]
AB.pop_rate_limit_status()
res_ra = AB.ApiBackend(ROT_REC, BASE, system_text_provider=lambda: SYS,
                       max_tokens=1000).send(u"вопрос", cancel_cb=lambda: False)
check(u"перебраны оба ключа и не больше", len(ALL_REQUESTS) == 2)
check(u"суточная квота не уводит в бесполезный сон",
      AB.pop_rate_limit_status() is None)
check(u"оба ключа помечены исчерпанными",
      api_keys.usable_keys("openrouter") == [])

# Следующий запрос при пустом списке кандидатов: ни одного обращения к сети.
CALLS["n"] = 0
del ALL_REQUESTS[:]
res_spent = AB.ApiBackend(ROT_REC, BASE, system_text_provider=lambda: SYS,
                          max_tokens=1000).send(u"вопрос", cancel_cb=lambda: False)
check(u"при исчерпанных ключах запрос к провайдеру не уходит вовсе",
      len(ALL_REQUESTS) == 0)
check(u"текст отличает «ключи кончились» от «ключ не задан»",
      u"[Ключи кончились]" in res_spent["text"]
      and u"не задан ключ" not in res_spent["text"])
check(u"перечислены оба ключа масками", res_spent["text"].count(u"•") == 2)
check(u"предложена смена модели — модель закреплена за чатом",
      u"другой модели" in res_spent["text"])
check(u"сырых ключей в объяснении нет",
      RK1 not in res_spent["text"] and RK2 not in res_spent["text"])

api_keys.clear_key_cooldowns("openrouter")
api_keys.set_key("openrouter", "")
api_keys.set_base_url("openrouter", "")

MODE["name"] = "slow"
state = {"n": 0}


def cancel_soon(*_a):
    state["n"] += 1
    return state["n"] > 3


t0 = time.time()
try:
    backend().send(u"вопрос", cancel_cb=cancel_soon)
    check(u"отмена бросает ParserCancelled (её ловит main.py)", False)
except parser_base.ParserCancelled:
    check(u"отмена бросает ParserCancelled (её ловит main.py)", True)
check(u"отмена быстрая", time.time() - t0 < 6.0)

# ---------------------------------------------------------------------------
# 9) Не настроенный провайдер
# ---------------------------------------------------------------------------
res_cfg = AB.ApiBackend({"id": "x", "kind": "api", "provider": "custom", "model": ""},
                        BASE, system_text_provider=lambda: SYS).send(
    u"вопрос", cancel_cb=lambda: False)
check(u"нет модели -> понятная подсказка, а не падение",
      u"[Настройки API]" in res_cfg["text"] and res_cfg["action"] is None)

res_key = AB.ApiBackend({"id": "y", "kind": "api", "provider": "openrouter",
                         "model": "a/b"}, BASE,
                        system_text_provider=lambda: SYS).send(
    u"вопрос", cancel_cb=lambda: False)
check(u"нет ключа -> понятная подсказка", u"[Настройки API]" in res_key["text"])

# ---------------------------------------------------------------------------
# 10) БЮДЖЕТЫ ТОКЕНОВ ПО КАТАЛОГУ models.dev (Этап 2)
#
# Зашитые в agent_prompts числа (окно 32000, история 16000, вывод 8000) — это
# ДОГАДКА, и замер по 502 моделям наших провайдеров показал, что она неверна в
# обе стороны: у 27 моделей окно МЕНЬШЕ, чем история+вывод (phi-4 — 16384,
# gemma-2-27b-it — 8192, gpt-3.5-turbo-16k — 16385), а у 472 — БОЛЬШЕ (медиана
# 262144). Первое означало гарантированный отказ провайдера посреди задачи,
# второе — историю, схлопнутую в разы раньше, чем нужно.
#
# ГЛАВНОЕ ЗДЕСЬ — первая проверка: без данных каталога числа обязаны остаться
# РОВНО прежними. Этап 2 трогает путь чата, и «улучшение», которое меняет
# поведение там, где о модели ничего не известно, — это не улучшение.
# ---------------------------------------------------------------------------
import catalog as CAT
from agent_prompts import (API_CONTEXT_WINDOW as W0, API_MAX_TOKENS as OUT0,
                           API_HISTORY_BUDGET as HIST0)

check(u"без каталога бюджеты РОВНО прежние",
      AB.budgets_for("openrouter", u"нет-такой-модели", OUT0, HIST0)
      == (OUT0, HIST0, W0, ""))
check(u"и у провайдера, которого каталог не знает вовсе",
      AB.budgets_for("custom", "m/test", OUT0, HIST0) == (OUT0, HIST0, W0, ""))

# Кэш каталога пишем прямо файлом: это его задокументированный формат (см.
# test_catalog.py), а поднимать здесь ещё и поддельный models.dev значит
# проверять загрузку второй раз вместо бюджетов.
with open(CAT.catalog_path(), "w", encoding="utf-8") as f:
    json.dump({"version": 1, "at": time.time(), "etag": "", "error": "",
               "try_at": 0.0, "providers": {"openrouter": {
                   "catalog_id": "openrouter", "name": "OpenRouter", "models": {
                       # Окно как у настоящего microsoft/phi-4: зашитые
                       # 16000+8000 в него НЕ влезали.
                       "vendor/phi-like": {"context": 16384, "max_output": 16384,
                                           "cost_in": 0.0, "cost_out": 0.0},
                       # Предел вывода МЕНЬШЕ доли окна: у настоящих таких 28
                       # (claude-3-haiku, command-r-plus и прочие).
                       "vendor/short-answer": {"context": 200000, "max_output": 4096},
                       # Огромное окно: история должна вырасти, но не до
                       # половины окна — иначе каждый шаг агента стоил бы как
                       # сто тысяч входных токенов.
                       "vendor/huge": {"context": 1000000, "max_output": 500000},
                       # Окно, в которое не влезает даже инструкция агента:
                       # veo-3.1-* (480), llama-prompt-guard-2-* (512).
                       "vendor/tiny": {"context": 480, "max_output": 480},
                   }}}}, f)

out_s, hist_s, win_s, src_s = AB.budgets_for("openrouter", "vendor/phi-like",
                                             OUT0, HIST0)
check(u"маленькое окно: числа взяты из каталога, а не из догадки",
      src_s == "catalog" and win_s == 16384)
check(u"история и вывод УМЕНЬШЕНЫ под настоящее окно",
      hist_s == 8192 and out_s == 4096)
check(u"история+вывод теперь влезают в окно", hist_s + out_s <= win_s)

out_h, hist_h, win_h, _src = AB.budgets_for("openrouter", "vendor/huge",
                                            OUT0, HIST0)
check(u"огромное окно: история выросла, но упёрлась в потолок",
      hist_h == AB.HISTORY_CAP and hist_h > HIST0)
check(u"вывод НЕ раздувается: 8000 хватает на план и крупный файл",
      out_h == OUT0)
check(u"потолок истории не выдуман: системный блок + один полный результат "
      u"инструмента (~30 500 токенов) в него влезают",
      AB.HISTORY_CAP >= H.estimate_tokens("x" * 80000) + 3800)

out_p, _hist_p, _win_p, _s = AB.budgets_for("openrouter", "vendor/short-answer",
                                            OUT0, HIST0)
check(u"предел вывода САМОЙ модели сильнее нашей доли окна", out_p == 4096)
check(u"переданный max_tokens остаётся потолком, а не заменяется каталогом",
      AB.budgets_for("openrouter", "vendor/huge", 1000, HIST0)[0] == 1000)

# Модель, в окно которой не влезает даже инструкция агента. Отказ обязан прийти
# ДО запроса: платить провайдеру за гарантированный отказ и показывать
# пользователю невнятную ошибку про длину контекста незачем.
api_keys.set_base_url("openrouter", "http://127.0.0.1:%d/v1" % PORT)
api_keys.set_key("openrouter", "sk-or-v1-TESTVALUE0123456789")
LAST_REQUEST["body"] = None
res_tiny = AB.ApiBackend({"id": "tiny01", "kind": "api", "provider": "openrouter",
                          "model": "vendor/tiny"}, BASE,
                         system_text_provider=lambda: SYS * 200,
                         max_tokens=OUT0).send(u"вопрос", cancel_cb=lambda: False)
check(u"окно меньше инструкции -> отказ словами, а не 500",
      u"[Модель не подходит]" in res_tiny["text"] and res_tiny["action"] is None)
check(u"в отказе названы оба числа и источник",
      "480" in res_tiny["text"] and u"models.dev" in res_tiny["text"])
check(u"ни одного запроса к провайдеру при этом не ушло",
      LAST_REQUEST["body"] is None)

# А пригодная модель с маленьким окном обязана РАБОТАТЬ, и в запрос должен уйти
# уменьшенный max_tokens. Режим сервера возвращаем в «ok»: выше его оставили в
# «slow» для проверки отмены, и без сброса сюда пришёл бы поток без действия.
MODE["name"] = "ok"
LAST_REQUEST["body"] = None
res_small = AB.ApiBackend({"id": "small01", "kind": "api", "provider": "openrouter",
                           "model": "vendor/phi-like"}, BASE,
                          system_text_provider=lambda: SYS,
                          max_tokens=OUT0).send(u"вопрос", cancel_cb=lambda: False)
check(u"модель с окном 16384 работает", res_small["action"] is not None)
check(u"в запрос ушёл УМЕНЬШЕННЫЙ max_tokens, а не зашитые 8000",
      (LAST_REQUEST["body"] or {}).get("max_tokens") == 4096)
api_keys.set_key("openrouter", "")
api_keys.set_base_url("openrouter", "")
CAT.forget()

srv.shutdown()
shutil.rmtree(BASE, ignore_errors=True)
n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
