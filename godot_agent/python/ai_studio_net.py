# -*- coding: utf-8 -*-
"""Сетевой монитор Google AI Studio: читает ответ модели из СЕТИ (CDP),
а не из DOM. Построен на общей базе net_monitor.BaseNetMonitor (v87.10),
как KimiChatMonitor.

Эндпоинт (подтверждён реальным дампом Response от 2026-07-22):
  POST https://alkalimakersuite-pa.clients6.google.com/$rpc/
       google.internal.alkali.applications.makersuite.v1.
       MakerSuiteService/GenerateContent
  content-type ответа: application/json+protobuf; charset=UTF-8

Формат тела: JSON-массив чанков (позиционный protobuf-JSON, стримится
кусками). Схема одного чанка:

  чанк       = [candidates, null, usage, null, null, null, null, "v1_<токен>"]
  candidates -> вложенные списки -> content = [parts, "model"]
  part       = [null, "текст", ...]
  part[12] == 1              -> кусок «размышлений» (thinking), НЕ ответ
  кандидат вида [content, 1] -> маркер завершения (finishReason=STOP),
                                встречается в последнем чанке

Куски ответа - ДЕЛЬТЫ (дописываются в конец), куски размышлений - целые
абзацы; и те и другие конкатенируются по порядку прихода. content ищется
РЕКУРСИВНО по сигнатуре [parts, "model"] - позиционные индексы чанка не
угадываются, поэтому разбор устойчив к изменению вложенности.
"""
import json
import zlib

from net_monitor import BaseNetMonitor


def _bytes_to_text_prefix(raw_bytes):
    """UTF-8 текст из начала буфера; символ, разрезанный по границе
    сетевого куска, остаётся в хвосте до следующего вызова."""
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        return raw_bytes[:e.start].decode("utf-8", errors="ignore")


def _iter_model_contents(node, out):
    """Рекурсивно собирает content-узлы вида [parts, "model"]."""
    if not isinstance(node, list):
        return
    if len(node) >= 2 and node[1] == "model" and isinstance(node[0], list):
        out.append(node[0])
        return
    for item in node:
        _iter_model_contents(item, out)


def extract_parts(obj):
    """Список (текст, это_размышление) из одного события (чанка)."""
    contents = []
    _iter_model_contents(obj, contents)
    result = []
    for parts in contents:
        for part in parts:
            if (isinstance(part, list) and len(part) >= 2
                    and isinstance(part[1], str)):
                is_thought = len(part) > 12 and part[12] == 1
                result.append((part[1], is_thought))
    return result


def has_finish_marker(node):
    """Ищет маркер завершения: кандидат [content, 1], где content -
    [parts, "model"] (finishReason=STOP, приходит в последнем чанке)."""
    if not isinstance(node, list):
        return False
    if (len(node) >= 2 and node[1] == 1 and isinstance(node[0], list)
            and len(node[0]) >= 2 and node[0][1] == "model"):
        return True
    for item in node:
        if isinstance(item, list) and has_finish_marker(item):
            return True
    return False


def _decode_chunks_from_start(text):
    """Разбор буфера, который ВСЕГДА начинается с НАЧАЛА стрима (целое
    тело или gzip-путь): внешняя «[» отбрасывается детерминированно,
    возвращаются только ПОЛНЫЕ чанки - список стабилен при дорастании
    буфера (важно для отсечения уже применённых событий)."""
    dec = json.JSONDecoder()
    events = []
    i = 0
    n = len(text)
    while i < n and text[i] in " \t\r\n":
        i += 1
    if i < n and text[i] == "[":
        i += 1
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "]":
            break
        try:
            obj, i = dec.raw_decode(text, i)
        except ValueError:
            break  # чанк недокачан - ждём следующие данные
        events.append(obj)
    return events


def decode_aistudio_chunks_partial(raw_bytes):
    """Разбирает НАЧАЛО буфера тела GenerateContent (живой стрим).

    Возвращает (события, съедено_байт); неполный хвост (недокачанный чанк
    или разрезанный UTF-8 символ) остаётся в буфере до следующего вызова.
    Аналог decode_connect_frames_partial из cdp_ws, только кадры здесь -
    элементы JSON-массива, а не Connect-RPC.
    """
    raw_bytes = bytes(raw_bytes)
    text = _bytes_to_text_prefix(raw_bytes)
    dec = json.JSONDecoder()
    events = []
    n = len(text)
    i = 0
    consumed = 0
    while i < n:
        ch = text[i]
        if ch in " \t\r\n,]":
            i += 1
            consumed = i
            continue
        try:
            obj, end = dec.raw_decode(text, i)
        except ValueError:
            # либо это «[» внешнего массива (он закроется только в самом
            # конце стрима), либо чанк недокачан - пробуем шагнуть на один
            # уровень внутрь и разобрать первый вложенный элемент
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if ch == "[" and j < n and text[j] == "[":
                try:
                    obj, end = dec.raw_decode(text, j)
                except ValueError:
                    break  # недокачано - ждём следующий кусок
                events.append(obj)
                i = end
                consumed = end
                continue
            break
        events.append(obj)
        i = end
        consumed = end
    return events, len(text[:consumed].encode("utf-8"))


class AiStudioChatMonitor(BaseNetMonitor):
    """Живое состояние чата AI Studio из Network.* событий CDP.

    Вся общая механика (живой стрим тела, защита от устаревших запросов,
    сбросы generating, дедлок-безопасное завершение, счётчик POST) - в
    BaseNetMonitor; здесь только формат json+protobuf чанков
    GenerateContent (см. шапку файла).
    """

    CHAT_URL_SUBSTR = "MakerSuiteService/GenerateContent"
    RESPONSE_MIME_SUBSTR = "json+protobuf"
    LOG_TAG = "ai_parser"

    def _reset_answer_state_locked(self):
        self._answer_text = ""
        self._thought_text = ""
        self._finished = False
        self._counted_message = False
        # если стрим приходит в исходном gzip-виде (content-encoding: gzip),
        # буфер копится целиком (съедено=0), а уже применённые события
        # отсекаются по этому счётчику - защита от дублей
        self._gzip_events_seen = 0

    def _decode_frames_partial(self, raw_bytes):
        raw_bytes = bytes(raw_bytes)
        if raw_bytes[:2] == b"\x1f\x8b":
            # gzip нельзя резать по байтам: каждый раз распаковываем
            # накопленный буфер целиком и применяем только НОВЫЕ чанки
            try:
                plain = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw_bytes)
            except zlib.error:
                return [], 0
            events = _decode_chunks_from_start(_bytes_to_text_prefix(plain))
            fresh = events[self._gzip_events_seen:]
            self._gzip_events_seen = len(events)
            return fresh, 0
        return decode_aistudio_chunks_partial(raw_bytes)

    def _decode_frames(self, raw_bytes):
        raw_bytes = bytes(raw_bytes)
        if raw_bytes[:2] == b"\x1f\x8b":
            raw_bytes = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw_bytes)
        return _decode_chunks_from_start(_bytes_to_text_prefix(raw_bytes))

    def _answer_len_locked(self):
        return len(self._answer_text)

    def _apply_event(self, obj):
        for text, is_thought in extract_parts(obj):
            if is_thought:
                self._thought_text += text
            elif text:
                self._answer_text += text
                if not self._counted_message:
                    self._counted_message = True
                    self._assistant_message_count += 1
        if has_finish_marker(obj):
            self._finished = True
            self._generating = False
            self._message_status = "FINISHED"

    def current_text(self):
        with self._lock:
            return self._answer_text

    def thought_text(self):
        with self._lock:
            return self._thought_text

    def is_finished(self):
        with self._lock:
            return self._finished
