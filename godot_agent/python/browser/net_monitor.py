# -*- coding: utf-8 -*-
"""Общая сетевая логика чтения ответов нейросетей через CDP (v87.10).

Выделена из kimi_parser (v87.1-v87.8), где схема «читаем ответ из СЕТИ,
а не из DOM» была обкатана впервые. Здесь живёт всё, что НЕ зависит от
конкретного сайта:

  - счётчик исходящих POST к чат-эндпоинту (confirm_sent по факту сети, v87.7);
  - трекинг активного запроса и защита от УСТАРЕВШИХ запросов: тело старого
    запроса не затирает состояние нового (v87.7);
  - живой захват стрима тела (Network.streamResourceContent +
    Network.dataReceived): инкрементный разбор чанков с сохранением
    неполного хвоста до следующего чанка (v87.8);
  - запасной путь через Network.getResponseBody для старых Chrome (v87.8);
  - завершение запроса в ОТДЕЛЬНОМ потоке: send_command нельзя звать из
    read_loop CDP - гарантированный дедлок (v87.4);
  - гарантированный сброс generating при ошибках сети/разбора и при обрыве
    ответа без явного статуса завершения (v87.5/v87.7) - иначе ожидание
    висит до общего 900с таймаута.

Сайт-специфика задаётся подклассом (формат кадров, схема событий, сборка
текста). Примеры: KimiChatMonitor (kimi_parser.py) - Connect-RPC кадры
kimi.com; будущий AiStudioChatMonitor (ai_parser.py) - json+protobuf чанки
Google AI Studio.
"""
import base64
import threading


class BaseNetMonitor:
    """База: собирает состояние чата из Network.* событий CDP.

    Подкласс ОБЯЗАН задать:
      CHAT_URL_SUBSTR - подстрока URL запроса, несущего ответ модели;
      LOG_TAG         - тег логов (обычно совпадает с именем парсера);
      _decode_frames_partial(raw) -> (события, съедено_байт) - разбор
          НАЧАЛА буфера: полные кадры возвращаются, неполный хвост
          остаётся (сколько байт съедено - второй элемент);
      _decode_frames(raw) -> события - разбор ЦЕЛОГО тела (запасной путь);
      _apply_event(obj) - применить одно событие (вызывается ПОД self._lock);
      _reset_answer_state_locked() - обнулить состояние ответа (ПОД lock);
      current_text() - собранный текст текущего ответа.
    Опционально:
      RESPONSE_MIME_SUBSTR - подстрока mimeType ответа ("" = любой);
      _answer_len_locked() - длина текста для диагностики (ПОД lock).
    """

    CHAT_URL_SUBSTR = None
    RESPONSE_MIME_SUBSTR = ""
    LOG_TAG = "net_monitor"

    def __init__(self, cdp):
        if not self.CHAT_URL_SUBSTR:
            raise ValueError("CHAT_URL_SUBSTR must be set by the subclass")
        self._cdp = cdp
        self._lock = threading.Lock()
        self._active_request_id = None
        self._message_status = None
        self._assistant_message_count = 0
        self._generating = False
        self._chat_request_count = 0
        self._request_counts = {}
        # v88.10: номер исходящего POST, которому принадлежит ТЕКУЩИЙ
        # буфер ответа (выставляется при responseReceived вместе со
        # сбросом буфера) — см. answer_request_count().
        self._answer_request_count = 0
        # req_id -> bytearray неразобранного хвоста / признак стрима /
        # threading.Event «попытка включения стрима завершена»
        self._stream_bufs = {}
        self._stream_mode = {}
        self._stream_done = {}
        self._reset_answer_state_locked()
        cdp.on_event("Network.requestWillBeSent", self._on_request_will_be_sent)
        cdp.on_event("Network.responseReceived", self._on_response_received)
        cdp.on_event("Network.dataReceived", self._on_data_received)
        cdp.on_event("Network.loadingFinished", self._on_loading_finished)
        cdp.on_event("Network.loadingFailed", self._on_loading_failed)

    # -- крючки для подкласса ------------------------------------------------

    def _decode_frames_partial(self, raw_bytes):
        raise NotImplementedError

    def _decode_frames(self, raw_bytes):
        raise NotImplementedError

    def _decode_final_tail(self, raw_bytes):
        """Complete events left after the last streaming delimiter.

        Most protocols cannot safely decode an unterminated tail. Line-framed
        protocols may override this because loadingFinished proves no more
        bytes can arrive.
        """
        return []

    def _apply_event(self, obj):
        raise NotImplementedError

    def _reset_answer_state_locked(self):
        raise NotImplementedError

    def current_text(self):
        raise NotImplementedError

    def _answer_len_locked(self):
        return 0

    def _match_request(self, url, method):
        return self.CHAT_URL_SUBSTR in url and method.upper() == "POST"

    def _match_response(self, url, mime):
        if self.CHAT_URL_SUBSTR not in url:
            return False
        return (not self.RESPONSE_MIME_SUBSTR) or (self.RESPONSE_MIME_SUBSTR in mime)

    def _log(self, msg):
        print("[%s] %s" % (self.LOG_TAG, msg))

    # -- общая механика (см. историю фиксов в шапке файла) --------------------

    def _on_request_will_be_sent(self, params):
        try:
            req = params.get("request") or {}
            url = req.get("url") or ""
            method = req.get("method") or ""
        except Exception:
            return
        req_id = params.get("requestId")
        if req_id and self._match_request(url, method):
            with self._lock:
                self._chat_request_count += 1
                cnt = self._chat_request_count
                # Only the latest POST can start a new answer. Keep this
                # bounded even when superseded requests never terminate.
                self._request_counts = {req_id: cnt}
            self._log("исходящий POST к %s #%d: %s"
                      % (self.CHAT_URL_SUBSTR, cnt, params.get("requestId")))

    def chat_request_count(self):
        with self._lock:
            return self._chat_request_count

    def answer_request_count(self):
        """v88.10: номер POST, чей ответ сейчас лежит в буфере.

        Между submit и приходом ответа chat_request_count УЖЕ вырос
        (requestWillBeSent), а буфер ЕЩЁ хранит ПРОШЛЫЙ ответ (сброс —
        только в responseReceived). Сравнение с ЭТИМ счётчиком закрывает
        окно, в котором живая трансляция/быстрый путь могли показать
        старый текст как новый (дубль прошлого ответа в панели)."""
        with self._lock:
            return self._answer_request_count

    def _on_response_received(self, params):
        try:
            resp = params.get("response") or {}
            url = resp.get("url") or ""
            mime = resp.get("mimeType") or ""
        except Exception:
            return
        # v104.12: HTTP 429/5xx на чат-эндпоинте — признак лимита запросов.
        # Ловим ДО проверки mime: ответ-ошибка обычно text/html или json
        # и в _match_response не попадает. Читается однократно через
        # pop_http_error() (спящий режим в main._reply).
        try:
            _status = int(resp.get("status") or 0)
        except (TypeError, ValueError):
            _status = 0
        if (_status == 429 or _status >= 500) and self.CHAT_URL_SUBSTR and \
                self.CHAT_URL_SUBSTR in url:
            with self._lock:
                self._last_http_error = _status
            self._log("HTTP %d на чат-эндпоинте — возможен лимит запросов (v104.12)" % _status)
        if self._match_response(url, mime):
            req_id = params.get("requestId")
            with self._lock:
                count = self._request_counts.get(req_id)
                if count is None or req_id == self._active_request_id:
                    return
                prev = self._active_request_id
                if prev is not None:
                    self._cleanup_request_locked(prev)
                self._active_request_id = req_id
                self._generating = True
                self._message_status = None
                self._reset_answer_state_locked()
                self._answer_request_count = count
                # v87.8: свежие стрим-буферы только для нового запроса
                self._stream_bufs = {req_id: bytearray()}
                self._stream_mode = {}
                self._stream_done = {req_id: threading.Event()}
            # включение стрима требует send_command - нельзя из read_loop
            # (дедлок, см. v87.4) - уходит в отдельный поток.
            threading.Thread(
                target=self._enable_stream, args=(req_id,), daemon=True
            ).start()
            # v87.6: диагностика - сколько реальных POST ушло за одну отправку
            # (каждый новый заменяет трекаемый активный запрос).
            self._log("новый запрос к %s: %s (был активным: %s)"
                      % (self.CHAT_URL_SUBSTR, req_id, prev))

    def _enable_stream(self, req_id):
        """v87.8: включает живой стрим тела ответа. bufferedData из ответа
        команды - всё, что пришло ДО включения; оно ПОДКЛЕИВАЕТСЯ СПЕРЕДИ
        к чанкам, которые dataReceived мог успеть добавить, пока этот
        поток просыпался (чанки с data идут только ПОСЛЕ включения,
        поэтому порядок байт сохраняется)."""
        with self._lock:
            evt = self._stream_done.get(req_id)
            if req_id != self._active_request_id:
                return
        try:
            try:
                res = self._cdp.send_command(
                    "Network.streamResourceContent", {"requestId": req_id})
            except Exception as e:
                self._log("streamResourceContent unavailable for %s (%s) - using getResponseBody"
                          % (req_id, e))
                return
            buffered = res.get("bufferedData") or ""
            data = base64.b64decode(buffered) if buffered else b""
            with self._lock:
                buf = self._stream_bufs.get(req_id)
                if buf is None or req_id != self._active_request_id:
                    return
                self._stream_bufs[req_id] = bytearray(data) + buf
                self._stream_mode[req_id] = True
                self._parse_stream_locked(req_id)
            self._log("живой стрим тела включён для %s (буфер %d байт)"
                      % (req_id, len(data)))
        except Exception as e:
            # Once streaming is enabled, replaying the body could duplicate
            # events already applied by an append-only parser.
            self._reset_after_finish(req_id, "stream parse failed: %s" % e, failed=True)
        finally:
            if evt is not None:
                evt.set()

    def _parse_stream_locked(self, req_id):
        """v87.8: разбирает ПОЛНЫЕ кадры из накопленного буфера и применяет
        события; неполный хвост остаётся ждать следующего чанка.
        Вызывать ТОЛЬКО под self._lock. Без send_command - безопасно из
        read_loop (не повторяет дедлок v87.4)."""
        buf = self._stream_bufs.get(req_id)
        if buf is None:
            return
        events, consumed = self._decode_frames_partial(bytes(buf))
        if consumed:
            del buf[:consumed]
        for obj in events:
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
        try:
            with self._lock:
                if req_id != self._active_request_id:
                    return
                buf = self._stream_bufs.get(req_id)
                if buf is None:
                    return
                buf.extend(chunk)
                if self._stream_mode.get(req_id):
                    self._parse_stream_locked(req_id)
        except Exception as e:
            self._reset_after_finish(req_id, "stream parse failed: %s" % e, failed=True)

    def _finalize_stream(self, req_id):
        """v87.8: завершение запроса, чьё тело читалось живым стримом:
        всё уже применено по ходу, getResponseBody не нужен."""
        with self._lock:
            if req_id != self._active_request_id:
                return
            failed = False
            try:
                self._parse_stream_locked(req_id)
                tail = bytes(self._stream_bufs.get(req_id) or b"")
                if tail:
                    events = self._decode_final_tail(tail)
                    for obj in events:
                        self._apply_event(obj)
                    if events:
                        self._stream_bufs[req_id].clear()
            except Exception as e:
                failed = True
                self._log("stream finalization failed for %s: %s" % (req_id, e))
            finally:
                self._cleanup_request_locked(req_id, failed=failed)
            text_len = self._answer_len_locked()
            status = self._message_status
        self._log("stream closed: text_length=%d, message_status=%s, failed=%s"
                  % (text_len, status, failed))

    def _finish_request(self, req_id):
        """v87.8: дожидается исхода попытки включения стрима (чтобы не
        гадать на гонке «быстрый ответ vs медленный streamResourceContent»),
        затем завершает запрос стрим-путём либо запасным getResponseBody."""
        with self._lock:
            evt = self._stream_done.get(req_id)
        if evt is not None:
            # send_command owns the bounded CDP timeout (15s). Do not race
            # its outcome with a shorter wait and replay an in-flight stream.
            evt.wait()
        with self._lock:
            if req_id != self._active_request_id:
                return
            streamed = bool(self._stream_mode.get(req_id))
        if streamed:
            self._finalize_stream(req_id)
        else:
            self._fetch_and_apply_body(req_id)

    def _on_loading_finished(self, params):
        req_id = params.get("requestId")
        with self._lock:
            if req_id != self._active_request_id:
                self._request_counts.pop(req_id, None)
                return
        # v87.4: Network.getResponseBody НЕЛЬЗЯ звать отсюда напрямую - этот
        # метод вызывается СИНХРОННО из CDPSession._read_loop, а send_command
        # блокирующе ждёт ответ, который может прочитать только этот же
        # read_loop - гарантированный дедлок. Поэтому завершение уходит в
        # отдельный поток. v87.8: сначала стрим-путь, getResponseBody -
        # только запасной (тело стримингового ответа в буфере DevTools
        # не хранится).
        threading.Thread(
            target=self._finish_request, args=(req_id,), daemon=True
        ).start()

    def _on_loading_failed(self, params):
        req_id = params.get("requestId")
        with self._lock:
            if req_id not in self._request_counts and req_id != self._active_request_id:
                return
        self._reset_after_finish(
            req_id,
            "loadingFailed: %s (canceled=%s)" % (
                params.get("errorText") or "network error", bool(params.get("canceled"))),
            failed=True)

    def _cleanup_request_locked(self, req_id, failed=False):
        """Release request resources under the lock, preserving partial text."""
        tail = self._stream_bufs.pop(req_id, None)
        if tail:
            self._log("request %s: discarded stream tail=%d bytes" % (req_id, len(tail)))
        self._stream_mode.pop(req_id, None)
        evt = self._stream_done.pop(req_id, None)
        if evt is not None:
            evt.set()
        self._request_counts.pop(req_id, None)
        if req_id is not None and req_id == self._active_request_id:
            self._active_request_id = None
            self._generating = False
            if failed:
                self._message_status = "FAILED"

    def _reset_after_finish(self, req_id, reason, failed=False):
        """v87.5: единая точка сброса состояния запроса - и при ошибке
        (сеть/декодирование), и при успешном разборе без явного статуса
        завершения: loadingFinished означает, что HTTP-ответ получен
        ПОЛНОСТЬЮ и больше данных не придёт - оставлять generating=True
        значило бы виснуть до общего таймаута (900с)."""
        with self._lock:
            # v87.7: если активен уже ДРУГОЙ запрос (повторная отправка успела
            # создать новый POST), завершение СТАРОГО запроса не должно
            # сбрасывать состояние нового.
            active = self._active_request_id
            self._cleanup_request_locked(req_id, failed=failed)
            if req_id != active:
                self._log("запрос %s завершён (%s), но активен уже %s - состояние не трогаю"
                          % (req_id, reason, self._active_request_id))
                return
        self._log("запрос %s завершён (%s), generating сброшен" % (req_id, reason))

    def _fetch_and_apply_body(self, req_id):
        # v87.7: если пока мы сюда шли, браузер уже отправил НОВЫЙ POST
        # (повтор confirm_sent и т.п.), тело СТАРОГО запроса применять нельзя:
        # оно затирало блоки нового запроса и обнуляло _active_request_id,
        # из-за чего loadingFinished НОВОГО запроса отбрасывался и настоящий
        # ответ так никогда и не читался.
        with self._lock:
            if req_id != self._active_request_id:
                self._log("тело запроса %s устарело (активен %s) - пропускаю"
                          % (req_id, self._active_request_id))
                return
        try:
            body = self._cdp.send_command("Network.getResponseBody", {"requestId": req_id})
        except Exception as e:
            self._log("Network.getResponseBody failed: %s" % e)
            # v87.4: не оставляем generating=True навечно.
            self._reset_after_finish(req_id, "getResponseBody упал", failed=True)
            return
        # v87.5: декодирование и применение событий обёрнуты в try/except:
        # иначе исключение тихо гасится в фоновом потоке, generating не
        # сбрасывается и ожидание висит до 900с без единой строки в логе.
        try:
            raw = body.get("body") or ""
            if body.get("base64Encoded"):
                raw_bytes = base64.b64decode(raw)
            else:
                raw_bytes = raw.encode("utf-8")
            with self._lock:
                # v87.7: повторная проверка актуальности УЖЕ ПОСЛЕ скачивания
                # тела: новый POST мог появиться, пока шёл send_command.
                if req_id != self._active_request_id:
                    self._log("тело запроса %s устарело после скачивания (активен %s) - пропускаю"
                              % (req_id, self._active_request_id))
                    return
                events = self._decode_frames(raw_bytes)
                for obj in events:
                    self._apply_event(obj)
                self._cleanup_request_locked(req_id)
                frame_count = len(events)
                text_len = self._answer_len_locked()
                status = self._message_status
        except Exception as e:
            import traceback
            self._log("ошибка разбора тела ответа (%d байт): %r" % (len(body.get("body") or ""), e))
            traceback.print_exc()
            self._reset_after_finish(req_id, "ошибка разбора тела", failed=True)
            return
        self._log("тело ответа разобрано: кадров=%d, длина_текста=%d, message_status=%s"
                  % (frame_count, text_len, status))

    # -- показания -------------------------------------------------------------

    def pop_http_error(self):
        """v104.12: последний HTTP-статус ошибки (429/5xx) чат-эндпоинта;
        читается ОДИН раз и сбрасывается — чтобы старая ошибка не считалась
        признаком лимита в следующем обмене."""
        with self._lock:
            st = getattr(self, "_last_http_error", None)
            self._last_http_error = None
        return st

    def is_generating(self):
        with self._lock:
            return bool(self._generating or self._active_request_id is not None)

    def assistant_message_count(self):
        with self._lock:
            return self._assistant_message_count

    def message_status(self):
        with self._lock:
            return self._message_status
