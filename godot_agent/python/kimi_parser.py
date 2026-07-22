# -*- coding: utf-8 -*-
"""Kimi (www.kimi.com) parser - v87.1 pilot.

Unlike qwen/deepseek/ai_parser, this parser does NOT read the answer from
the DOM. Instead it reads the model's answer directly from the network:
kimi.com answers POST .../ChatService/Chat with a Connect-RPC stream
(content-type application/connect+json) containing structured JSON events
such as:

  {"op": "set",    "mask": "block.text",         "block": {"id": "1", "text": {"content": "..."}}}
  {"op": "append", "mask": "block.text.content", "block": {"id": "1", "text": {"content": "..."}}}
  {"op": "set",    "mask": "message.status",     "message": {"id": "...", "status": "MESSAGE_STATUS_COMPLETED"}}

This is much more reliable than DOM/height heuristics (v86.19-27): each
event says explicitly what changed, and MESSAGE_STATUS_COMPLETED is an
explicit end-of-generation signal instead of a guess. Schema was reverse
engineered from two real HAR captures of www.kimi.com taken 2026-07-22
(one plain-text answer, one with a tool call + an ```agent_action code
fence) - see README_CHANGES.txt, v87.1, for details.

Selenium's execute_cdp_cmd cannot receive these push events, so a separate
raw WebSocket connection to the same browser debug port is used (cdp_ws.py).

DOM is still used for the parts network capture cannot help with: typing
the prompt into the input box and clicking send. Selectors below come from
HTML snippets of www.kimi.com supplied by the user on 2026-07-22 and are
BEST-EFFORT - they still need to be confirmed against the live site.
"""
import base64
import re
import threading
import time

from parser_base import BaseSiteParser, _safe_execute

from cdp_ws import (CDPSession, decode_connect_frames,
                    decode_connect_frames_partial, find_page_ws_url)


# ---------------------------------------------------------------------------
# Extraction of the agent_action fence from already-assembled markdown text.
# Unlike other sites, this runs on plain text (no DOM/JS needed) because the
# network stream already delivers ready markdown, including the
# ```agent_action fence, verbatim.
# ---------------------------------------------------------------------------

_AGENT_ACTION_FENCE_RE = re.compile(r"```agent_action\s*\n(.*?)\n?```", re.DOTALL)
_DONE_MARKER_RE = re.compile(r"={2,}\s*DONE\s*={2,}", re.IGNORECASE)


def split_text_and_action(full_text):
    """Splits off the LAST ```agent_action fenced block from full_text and
    strips the ===DONE=== marker. Returns (text, action_raw_or_None)."""
    if not full_text:
        return full_text, None
    text = full_text
    action_raw = None
    matches = list(_AGENT_ACTION_FENCE_RE.finditer(text))
    if matches:
        m = matches[-1]
        action_raw = m.group(1)
        text = (text[:m.start()] + text[m.end():])
    text = _DONE_MARKER_RE.sub("", text).strip()
    return text, action_raw


# ---------------------------------------------------------------------------
# Live state assembled from Network.* events - see README_CHANGES.txt v87.1
# for the schema this is based on.
# ---------------------------------------------------------------------------

class KimiChatMonitor:
    """Tracks the live chat state of www.kimi.com purely from network
    events (no DOM access at all)."""

    CHAT_URL_SUBSTR = "ChatService/Chat"

    def __init__(self, cdp):
        self._cdp = cdp
        self._lock = threading.Lock()
        self._active_request_id = None
        self._blocks = {}
        self._block_order = []
        self._message_status = None
        self._current_message_id = None
        self._assistant_message_count = 0
        self._generating = False
        # v87.7: счётчик ИСХОДЯЩИХ POST к ChatService/Chat (Network.requestWillBeSent).
        # Нужен confirm_sent: если после клика по «Отправить» счётчик вырос -
        # сообщение ФАКТИЧЕСКИ ушло в сеть, даже если поле ввода ещё не
        # очистилось (именно ложные «не ушло» порождали повторные POST,
        # обрывавшие чтение настоящего ответа - лог пользователя 2026-07-22).
        self._chat_request_count = 0
        # v87.8: живой захват стрима (Network.streamResourceContent).
        # Причина: тело СТРИМИНГОВОГО ответа (connect+json), которое
        # страница читает через ReadableStream, Chrome НЕ хранит в буфере
        # DevTools: Network.getResponseBody после loadingFinished отдаёт
        # огрызок (живой лог 2026-07-22: ответ виден в чате, а в теле
        # "кадров=1, длина_текста=0" без единого повторного POST).
        # Поэтому чанки тела читаются В РЕАЛЬНОМ ВРЕМЕНИ через
        # Network.dataReceived (поле data появляется после включения
        # streamResourceContent), а getResponseBody остаётся запасным путём
        # для старых Chrome без этого CDP-метода.
        self._stream_bufs = {}    # req_id -> bytearray неразобранного хвоста
        self._stream_mode = {}    # req_id -> True, если стрим включён
        self._stream_done = {}    # req_id -> threading.Event (попытка включения завершена)
        cdp.on_event("Network.requestWillBeSent", self._on_request_will_be_sent)
        cdp.on_event("Network.responseReceived", self._on_response_received)
        cdp.on_event("Network.dataReceived", self._on_data_received)
        cdp.on_event("Network.loadingFinished", self._on_loading_finished)

    def _on_request_will_be_sent(self, params):
        try:
            req = params.get("request") or {}
            url = req.get("url") or ""
            method = req.get("method") or ""
        except Exception:
            return
        if self.CHAT_URL_SUBSTR in url and method.upper() == "POST":
            with self._lock:
                self._chat_request_count += 1
                cnt = self._chat_request_count
            print("[kimi_parser] исходящий POST к ChatService/Chat #%d: %s" % (cnt, params.get("requestId")))

    def chat_request_count(self):
        with self._lock:
            return self._chat_request_count

    def _on_response_received(self, params):
        try:
            resp = params.get("response") or {}
            url = resp.get("url") or ""
            mime = resp.get("mimeType") or ""
        except Exception:
            return
        if self.CHAT_URL_SUBSTR in url and "connect+json" in mime:
            req_id = params.get("requestId")
            with self._lock:
                prev = self._active_request_id
                self._active_request_id = req_id
                self._generating = True
                self._blocks = {}
                self._block_order = []
                self._message_status = None
                self._current_message_id = None
                # v87.8: свежие стрим-буферы только для нового запроса
                self._stream_bufs = {req_id: bytearray()}
                self._stream_mode = {}
                self._stream_done = {req_id: threading.Event()}
            # включение стрима требует send_command - нельзя из read_loop
            # (дедлок, см. v87.4) - уходит в отдельный поток.
            threading.Thread(
                target=self._enable_stream, args=(req_id,), daemon=True
            ).start()
            # v87.6: диагностика - сколько реальных POST-запросов к ChatService/Chat
            # ушло за одну оттравку сообщения - если из-за ложных повторов
            # confirm_sent их несколько, каждый новый заменяет трекаемый активный
            # запрос и сбрасывает уже накопленный текст - причина висания
            # 2026-07-22 могла быть именно в этом (лог показал кадров=1,
            # длина_текста=0 - похоже на оборванный/отменённый предыдущий запрос).
            print("[kimi_parser] новый запрос к ChatService/Chat: %s (был активным: %s)" % (req_id, prev))

    def _enable_stream(self, req_id):
        """v87.8: включает живой стрим тела ответа. bufferedData из ответа
        команды - всё, что пришло ДО включения; оно ПОДКЛЕИВАЕТСЯ СПЕРЕДИ
        к чанкам, которые dataReceived мог успеть добавить, пока этот
        поток просыпался (чанки с data идут только ПОСЛЕ включения,
        поэтому порядок байт сохраняется)."""
        try:
            res = self._cdp.send_command(
                "Network.streamResourceContent", {"requestId": req_id})
            buffered = res.get("bufferedData") or ""
            data = base64.b64decode(buffered) if buffered else b""
            with self._lock:
                buf = self._stream_bufs.get(req_id)
                if buf is None or req_id != self._active_request_id:
                    return
                self._stream_bufs[req_id] = bytearray(data) + buf
                self._stream_mode[req_id] = True
                self._parse_stream_locked(req_id)
            print("[kimi_parser] живой стрим тела включён для %s (буфер %d байт)"
                  % (req_id, len(data)))
        except Exception as e:
            # старый Chrome без Network.streamResourceContent или ответ уже
            # закрыт - остаётся запасной путь через getResponseBody.
            print("[kimi_parser] streamResourceContent недоступен для %s (%s) - запасной путь через getResponseBody"
                  % (req_id, e))
        finally:
            evt = self._stream_done.get(req_id)
            if evt is not None:
                evt.set()

    def _parse_stream_locked(self, req_id):
        """v87.8: разбирает ПОЛНЫЕ Connect-кадры из накопленного буфера и
        применяет события; неполный хвост остаётся ждать следующего чанка.
        Вызывать ТОЛЬКО под self._lock. Без send_command - безопасно из
        read_loop (не повторяет дедлок v87.4)."""
        buf = self._stream_bufs.get(req_id)
        if buf is None:
            return
        frames, consumed = decode_connect_frames_partial(bytes(buf))
        if consumed:
            del buf[:consumed]
        for _flags, obj in frames:
            self._apply_event(obj)

    def _on_data_received(self, params):
        # v87.8: поле data присутствует только когда стрим включён
        # (streamResourceContent); без него это обычное уведомление о
        # размере - игнорируем.
        data = params.get("data")
        if not data:
            return
        req_id = params.get("requestId")
        try:
            chunk = base64.b64decode(data)
        except Exception:
            return
        with self._lock:
            if req_id != self._active_request_id:
                return
            buf = self._stream_bufs.get(req_id)
            if buf is None:
                return
            buf.extend(chunk)
            if self._stream_mode.get(req_id):
                self._parse_stream_locked(req_id)

    def _finalize_stream(self, req_id):
        """v87.8: завершение запроса, чьё тело читалось живым стримом:
        всё уже применено по ходу, getResponseBody не нужен."""
        with self._lock:
            if req_id != self._active_request_id:
                return
            self._parse_stream_locked(req_id)
            self._active_request_id = None
            leftover = len(self._stream_bufs.get(req_id) or b"")
            self._stream_bufs.pop(req_id, None)
            self._stream_mode.pop(req_id, None)
            self._stream_done.pop(req_id, None)
            text_len = sum(len(v) for v in self._blocks.values())
            status = self._message_status
            still_generating = self._generating
        print("[kimi_parser] стрим тела завершён: длина_текста=%d, message_status=%s, generating=%s, неразобранный хвост=%d байт"
              % (text_len, status, still_generating, leftover))
        if still_generating:
            self._reset_after_finish(req_id, "ответ закрыт без явного статуса завершения")

    def _finish_request(self, req_id):
        """v87.8: дожидается исхода попытки включения стрима (чтобы не
        гадать на гонке «быстрый ответ vs медленный streamResourceContent»),
        затем завершает запрос стрим-путём либо запасным getResponseBody."""
        evt = self._stream_done.get(req_id)
        if evt is not None:
            evt.wait(5.0)
        with self._lock:
            streamed = bool(self._stream_mode.get(req_id))
        if streamed:
            self._finalize_stream(req_id)
        else:
            self._fetch_and_apply_body(req_id)

    def _on_loading_finished(self, params):
        req_id = params.get("requestId")
        with self._lock:
            if req_id != self._active_request_id:
                return
        # v87.4: Network.getResponseBody НЕЛьЗЯ звать отсюда напрямую - этот
        # метод вызывается СИНХРОННО из CDPSession._read_loop (см. cdp_ws.py:
        # "for cb in handlers: cb(params)"), а send_command() блокирующе ждёт
        # ответ, который может прочитать с сокета Только этот же _read_loop -
        # он же сейчас занят выполнением этого самого callback'а. Результат -
        # гарантированный дедлок/таймаут на КАЖДОМ запросе (живой лог
        # пользователя: "Timed out waiting for CDP response to
        # Network.getResponseBody", после чего answers/len застревают на 0,
        # а generating=True навечно, потому что _active_request_id/_generating
        # никогда не сбрасывались при ошибке). Чтобы не блокировать читающий
        # поток, сам fetch+разбор тела уходит в отдельный поток.
        # v87.8: вместо прямого _fetch_and_apply_body - сначала стрим-путь,
        # getResponseBody только как запасной (тело стримингового ответа
        # в буфере DevTools не хранится - именно поэтому приходило
        # "кадров=1, длина_текста=0" при ответе, видимом в чате).
        threading.Thread(
            target=self._finish_request, args=(req_id,), daemon=True
        ).start()

    def _reset_after_finish(self, req_id, reason):
        """v87.5: единая точка сброса состояния запроса. Вызывается и при
        ошибке (сеть/декодирование), и при УСПЕШНОМ разборе - Network.
        loadingFinished означает, что HTTP-ответ получен ПОЛНОСТЬЮ, поэтому
        больше данных по этому запросу не придёт: если после разбора кадров
        MESSAGE_STATUS_COMPLETED так и не появился, оставлять generating=True
        значило бы виснуть до общего таймаута (900с), хотя ждать больше
        нечего (именно это произошло 2026-07-22: answers=0, len=0,
        generating=True до самого TimeoutError, без единой строки ошибки -
        значит исключение вылетало где-то ПОСЛЕ send_command и тихо гасилось
        потоком, т.к. decode_connect_frames/_apply_event не были обёрнуты в
        try/except)."""
        with self._lock:
            # v87.7: если активен уже ДРУГОЙ запрос (повторная отправка успела
            # создать новый POST), завершение СТАРОГО запроса не должно
            # сбрасывать состояние нового (раньше generating гасился
            # безусловно - ожидание считало генерацию законченной, хотя
            # настоящий ответ ещё шёл по новому запросу).
            if self._active_request_id is not None and req_id != self._active_request_id:
                print("[kimi_parser] запрос %s завершён (%s), но активен уже %s - состояние не трогаю"
                      % (req_id, reason, self._active_request_id))
                return
            self._active_request_id = None
            self._generating = False
        print("[kimi_parser] запрос %s завершён (%s), generating сброшен" % (req_id, reason))

    def _fetch_and_apply_body(self, req_id):
        # v87.7: если пока мы сюда шли браузер уже отправил НОВЫЙ POST
        # (повтор confirm_sent и т.п.), тело СТАРОГО запроса применять нельзя:
        # раньше оно затирало блоки нового запроса И безусловно обнуляло
        # _active_request_id, из-за чего Network.loadingFinished НОВОГО запроса
        # отбрасывался проверкой req_id != _active_request_id - настоящий ответ
        # (видимый в чате kimi) так никогда и не читался (лог 2026-07-22:
        # "кадров=1, длина_текста=0 ... generating сброшен", дальше тишина).
        with self._lock:
            if req_id != self._active_request_id:
                print("[kimi_parser] тело запроса %s устарело (активен %s) - пропускаю"
                      % (req_id, self._active_request_id))
                return
        try:
            body = self._cdp.send_command("Network.getResponseBody", {"requestId": req_id})
        except Exception as e:
            print("[kimi_parser] Network.getResponseBody failed: %s" % e)
            # v87.4: не оставляем generating=True навечно - без этого сброса
            # is_generating() держит True до общего таймаута (900с), хотя
            # ответ давно готов на странице (сообщение пользователя от
            # 2026-07-22: ответ виден в чате kimi, а агент висит).
            self._reset_after_finish(req_id, "getResponseBody упал")
            return
        # v87.5: всё, что ниже (декодирование base64, разбор Connect-кадров,
        # применение событий), раньше НЕ было обёрнуто в try/except. Если
        # decode_connect_frames или _apply_event падали на неожиданной форме
        # кадра, исключение тихо гасилось в фоновом потоке (Python по
        # умолчанию просто печатает traceback через threading.excepthook,
        # что может быть не видно в логе агента) - НИЧЕГО не печаталось тегом
        # "[kimi_parser]", а _active_request_id/_generating НЕ сбрасывались,
        # то есть жду ответ [стабилизация] крутилось answers=0/len=0/
        # generating=True до полного 900-секундного таймаута без единой
        # диагностической строки - ровно то, что пользователь увидел
        # 2026-07-22 после исправления дедлока v87.4.
        try:
            raw = body.get("body") or ""
            if body.get("base64Encoded"):
                raw_bytes = base64.b64decode(raw)
            else:
                raw_bytes = raw.encode("utf-8")
            frames = decode_connect_frames(raw_bytes)
            with self._lock:
                # v87.7: повторная проверка актуальности УЖЕ ПОСЛЕ скачивания
                # тела: новый POST мог появиться, пока шёл send_command.
                if req_id != self._active_request_id:
                    print("[kimi_parser] тело запроса %s устарело после скачивания (активен %s) - пропускаю"
                          % (req_id, self._active_request_id))
                    return
                for _flags, obj in frames:
                    self._apply_event(obj)
                self._active_request_id = None
                frame_count = len(frames)
                text_len = sum(len(v) for v in self._blocks.values())
                status = self._message_status
                still_generating = self._generating
        except Exception as e:
            import traceback
            print("[kimi_parser] ошибка разбора тела ответа (%d байт): %r" % (len(body.get("body") or ""), e))
            traceback.print_exc()
            self._reset_after_finish(req_id, "ошибка разбора тела")
            return
        print("[kimi_parser] тело ответа разобрано: кадров=%d, длина_текста=%d, message_status=%s, generating=%s"
              % (frame_count, text_len, status, still_generating))
        if still_generating:
            # loadingFinished => HTTP-ответ получен целиком, больше данных по
            # этому requestId не будет. Если статус так и не дошёл до явного
            # завершения, не виснем до общего 900с таймаута - завершение уже
            # физически невозможно на этом соединении.
            # v87.7: раньше было условие status != "MESSAGE_STATUS_GENERATING",
            # и оборванный поток, чей ПОСЛЕДНИЙ увиденный статус -
            # MESSAGE_STATUS_GENERATING (обрыв до COMPLETED), оставлял
            # generating=True навечно - то же зависание до 900с, которое
            # v87.5 чинил для случая status=None.
            self._reset_after_finish(req_id, "ответ закрыт без явного статуса завершения")

    def _apply_event(self, obj):
        if not isinstance(obj, dict):
            return
        op = obj.get("op")
        msg = obj.get("message")
        if isinstance(msg, dict):
            role = msg.get("role")
            status = msg.get("status")
            mid = msg.get("id")
            # The initial "set message" event carries role+id for a new
            # assistant message; later "set message.status" events for the
            # SAME message only repeat id+status, without role - so a
            # message is tracked as "assistant" once its id has been seen
            # with role == "assistant", not by re-checking role every time.
            if role == "assistant" and mid and mid != self._current_message_id:
                self._current_message_id = mid
                self._assistant_message_count += 1
            if status and mid and mid == self._current_message_id:
                self._message_status = status
                self._generating = (status == "MESSAGE_STATUS_GENERATING")
        block = obj.get("block")
        if isinstance(block, dict):
            bid = block.get("id")
            text_obj = block.get("text")
            if block.get("tool") is None and isinstance(text_obj, dict):
                content = text_obj.get("content")
                if content is not None:
                    if op == "set" or bid not in self._blocks:
                        self._blocks[bid] = content
                        if bid not in self._block_order:
                            self._block_order.append(bid)
                    else:
                        self._blocks[bid] = self._blocks.get(bid, "") + content

    def current_text(self):
        with self._lock:
            def _key(bid):
                try:
                    return int(bid)
                except Exception:
                    return 0
            ordered = sorted(self._block_order, key=_key)
            return "".join(self._blocks[b] for b in ordered)

    def is_generating(self):
        with self._lock:
            return bool(self._generating or self._active_request_id is not None)

    def assistant_message_count(self):
        with self._lock:
            return self._assistant_message_count

    def message_status(self):
        with self._lock:
            return self._message_status


# ---------------------------------------------------------------------------
# DOM-side: only used for typing the prompt and clicking send. Selectors are
# best-effort from the HTML snippets supplied 2026-07-22, need live checking.
# ---------------------------------------------------------------------------

JS_FIND_INPUT = r"""
return document.querySelector('div.chat-input-editor[contenteditable="true"]');
"""

JS_SET_INPUT = r"""
var el = arguments[0], text = arguments[1];
el.focus();
document.execCommand('selectAll', false, null);
document.execCommand('insertText', false, text);
"""

JS_FIND_SEND_BUTTON = r"""
var el = document.querySelector('div.send-button-container');
if (el && !el.classList.contains('disabled')) return el;
return null;
"""


class KimiParser(BaseSiteParser):
    """www.kimi.com: DOM only for typing/sending, network (CDP) for reading."""

    LOG_TAG = "kimi_parser"
    WINDOW_URL_MATCH = "kimi.com"
    START_PHASE = u"\u043c\u043e\u0434\u0435\u043b\u044c \u0434\u0443\u043c\u0430\u0435\u0442\u2026"
    QUIET_PERIOD = 4.0
    POLL_INTERVAL = 0.3

    _monitor = None
    _monitor_lock = threading.Lock()

    def _ensure_monitor(self, driver):
        with KimiParser._monitor_lock:
            old = KimiParser._monitor
            if old is not None:
                # v87.7: раньше синглтон возвращался без проверки живости:
                # если CDP-соединение умерл�� (тишина в сокете до v87.7,
                # перезапуск/закрытие вкладки, обрыв сокета), монитор
                # навсегда глох (ни событий, ни тел) до перезапуска сервера.
                if old._cdp.is_alive():
                    return old
                print("[kimi_parser] CDP-сессия мертва - переподключаюсь к вкладке kimi.com...")
                try:
                    old._cdp.close()
                except Exception:
                    pass
                KimiParser._monitor = None
            ws_url = find_page_ws_url("kimi.com")
            if not ws_url:
                raise Exception(
                    "kimi.com tab not found for CDP attach (Network domain "
                    "needed to read the streamed answer).")
            cdp = CDPSession(ws_url)
            # v87.7: подписки монитора регистрируются ДО Network.enable -
            # раньше события, пришедшие между enable и созданием монитора,
            # молча терялись.
            monitor = KimiChatMonitor(cdp)
            cdp.send_command("Network.enable")
            if old is not None:
                # переносим накопленные счётчики, чтобы initial_count в
                # идущем ожидании не «прыгал» после переподключения.
                monitor._assistant_message_count = old.assistant_message_count()
                monitor._chat_request_count = old.chat_request_count()
            KimiParser._monitor = monitor
            return monitor

    def count_answers(self, driver):
        return self._ensure_monitor(driver).assistant_message_count()

    def answer_len(self, driver):
        return len(self._ensure_monitor(driver).current_text())

    def answer_stream(self, driver):
        return self._ensure_monitor(driver).current_text()

    def is_generating(self, driver):
        return self._ensure_monitor(driver).is_generating()

    def extract_answer(self, driver):
        monitor = self._ensure_monitor(driver)
        full_text = monitor.current_text()
        text, action_raw = split_text_and_action(full_text)
        return {"text": text, "actionRaw": action_raw, "error": None}

    def find_input(self, driver):
        return _safe_execute(driver, JS_FIND_INPUT, default=None)

    def insert_input(self, driver, el, prompt):
        driver.execute_script(JS_SET_INPUT, el, prompt)

    def submit(self, driver, el):
        # v87.7: снимок счётчика исходящих POST ДО клика: confirm_sent считает
        # сообщение ушедшим, если после клика появился новый POST к
        # ChatService/Chat - это надёжнее, чем гадать по остатку текста
        # в поле ввода (ложные «не ушло» порождали реальные дубли POST,
        # обрывавшие чтение настоящего ответа - гипотеза v87.6
        # подтверждена разбором кода: см. README v87.7).
        mon = KimiParser._monitor
        self._req_count_before_send = (
            mon.chat_request_count() if mon is not None else None)
        btn = _safe_execute(driver, JS_FIND_SEND_BUTTON, default=None)
        if btn is not None:
            driver.execute_script("arguments[0].click();", btn)
        else:
            from selenium.webdriver.common.keys import Keys
            el.send_keys(Keys.ENTER)

    def _input_leftover(self, driver, el):
        """текст, оставшийся в поле ввода (пусто => сообщение отправлено).
        v87.3: _safe_execute НЕ умеет передавать аргументы в execute_script (и
eго retries позиционно перекрывается WebElement'ом, если его передать
после script) - для скриптов с arguments[0] надо звать driver.execute_script(...)
наврямую, как в deepseek_parser.py._input_leftover."""
        try:
            val = driver.execute_script(
                "var e=arguments[0];"
                " return (e.innerText||e.textContent||'').trim();", el)
        except Exception:
            val = ""
        return (val or "").strip()

    def confirm_sent(self, driver, el):
        # v87.7: главный критерий «ушло/не ушло» - СЕТЬ, а не DOM:
        # если после клика появился новый POST к ChatService/Chat
        # (Network.requestWillBeSent), сообщение точно отправлено -
        # даже если сайт ещё не очистил поле ввода (именно ложные
        # «не ушло» вызывали повторные реальные POST - гипотеза v87.6).
        # DOM-проверка остаётся запасным критерием (если монитора нет).
        before = getattr(self, "_req_count_before_send", None)
        deadline = time.time() + 5.0
        while True:
            mon = KimiParser._monitor
            if (before is not None and mon is not None
                    and mon.chat_request_count() > before):
                return True
            leftover = self._input_leftover(driver, el)
            if not leftover:
                return True
            if time.time() >= deadline:
                break
            time.sleep(0.3)
        # v87.6: диагностика - видим, что именно осталось в поле ввода,
        # когда confirm_sent решает, что сообщение не ушло и надо повторить
        # отправку (повтор теперь возможен только если за 5с не было
        # НИ нового POST в сети, НИ очистки поля - т.е. реальный сбой).
        print("[kimi_parser] confirm_sent: после отправки в поле осталось: %r (%d симв.), новых POST не было - считаю, что не ушло"
              % (leftover[:120], len(leftover)))
        return False


PARSER = KimiParser()


# --- Модульные обёртки для main.py/selfcheck.py: они вызывают эти имена
# На САСАМОМ модуле (как sites.get_parser_module() возвращает модуль, а не
# экземпляр класса), точно так же, как в deepseek_parser.py/ai_parser.py/
# qwen_parser.py. Из-за отсутствия этих обёрток в v87.1 падал send_message_and_
# get_response - исправлено в v87.2.

def count_answers(driver):
    return PARSER.count_answers(driver)


def answer_len(driver):
    return PARSER.answer_len(driver)


def answer_stream(driver):
    return PARSER.answer_stream(driver)


def is_generating(driver):
    return PARSER.is_generating(driver)


def extract_answer(driver):
    return PARSER.extract_answer(driver)


def wait_for_new_answer(driver, initial_count, timeout=900, quiet_period=4.0,
                        hard_quiet_period=45.0, poll_interval=0.3,
                        post_quiet_grace=6.0, progress_cb=None):
    return PARSER.wait_for_new_answer(
        driver, initial_count, timeout=timeout, quiet_period=quiet_period,
        hard_quiet_period=hard_quiet_period, poll_interval=poll_interval,
        post_quiet_grace=post_quiet_grace, progress_cb=progress_cb)


def send_message_and_get_response(driver, prompt, input_retries=3, progress_cb=None, cancel_cb=None, prefer_url=None):
    return PARSER.send_message_and_get_response(
        driver, prompt, input_retries=input_retries, progress_cb=progress_cb,
        cancel_cb=cancel_cb, prefer_url=prefer_url)
