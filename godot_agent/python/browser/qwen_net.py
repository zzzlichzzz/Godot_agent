# -*- coding: utf-8 -*-
"""Сетевой монитор Qwen (chat.qwen.ai) — v104.1 (база v88.6).

Читает ответ модели из СЕТИ (SSE-стрим), а не из DOM — как у kimi (v87.x)
и AI Studio (v88.0). Формат снят с реального обмена (июль 2026):

  POST https://chat.qwen.ai/api/v2/chat/completions?chat_id=<uuid>
  Content-Type: text/event-stream; charset=utf-8

  data: {"response.created": {...}}                       - начало ответа
  data: {"choices":[{"delta":{"content":"","phase":"thinking_summary",
        "extra":{"summary_thought":{"content":[...]}},"status":"typing"}}]}
  data: {"choices":[{"delta":{"content":"кусок","phase":"answer",
        "status":"typing"}}]}                             - дельты ответа
  data: {"choices":[{"delta":{"content":"","phase":"answer",
        "status":"finished"}}]}                           - конец ответа

Важное:
  - текст ответа несут ТОЛЬКО дельты phase=="answer" (конкатенация content);
  - phase=="thinking_summary" — мысли; списки в extra.summary_thought.content
    НАРАСТАЮЩИЕ (каждое событие повторяет предыдущие целиком) — храним
    последний снимок, а не конкатенацию;
  - конец ответа: phase=="answer" и status=="finished";
  - на проводе Content-Encoding: br, но CDP-стрим отдаёт РАСПАКОВАННЫЕ байты
    (как у kimi); на случай сырого brotli есть защитная ветка (аналог
    gzip-ветки AI Studio), если модуль brotli установлен.
  - v104.1: qwen может стримить ДВА параллельных варианта ответа ("Response 1"/
    "Response 2", чаще на первом сообщении в чате, см. v86.12 в qwen_parser); их
    дельты идут вперемешку в ОДНОМ SSE и различаются top-level полем
    response_id — копим варианты раздельно и наружу отдаём вариант с
    наименьшим response_index (Response 1), иначе в панель уезжает
    посимвольная каша из двух ответов сразу (багрепорт 23.07.2026:
    «Прagent_action {"action": "readочитаю сцену HUD,_file…»).
"""
import json

from net_monitor import BaseNetMonitor

try:
    import brotli as _brotli  # опционален: только для защитной ветки
except Exception:
    _brotli = None


def decode_qwen_sse_lines(text):
    """Все события из SSE-текста: строки вида «data: {json}»."""
    events = []
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except ValueError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def decode_qwen_sse_partial(raw_bytes):
    """Разбор НАЧАЛА буфера: полные строки (до последнего \\n) разбираются,
    неполный хвост остаётся ждать следующего чанка. Резать по \\n безопасно
    и для UTF-8: байт 0x0A не встречается внутри многобайтового символа."""
    raw = bytes(raw_bytes)
    idx = raw.rfind(b"\n")
    if idx < 0:
        return [], 0
    head = raw[: idx + 1]
    return decode_qwen_sse_lines(head.decode("utf-8", "replace")), len(head)


def _looks_like_sse(raw):
    head = bytes(raw[:32]).lstrip()
    # ":" — SSE-комментарий/keep-alive, "e" — строки "event:"
    return head[:5] == b"data:" or head[:1] in (b":", b"e")


class QwenChatMonitor(BaseNetMonitor):
    """Живое состояние чата Qwen из Network.* событий CDP.

    Вся общая механика (живой стрим тела, защита от устаревших запросов,
    сбросы generating, дедлок-безопасное завершение, счётчик POST) — в
    BaseNetMonitor; здесь только формат SSE-событий chat/completions.
    Пользователь подтвердил (23.07): ответ несёт /api/v2/chat/completions,
    а не /chats — берём первый."""

    CHAT_URL_SUBSTR = "/api/v2/chat/completions"
    RESPONSE_MIME_SUBSTR = "text/event-stream"
    LOG_TAG = "qwen_parser"

    def _reset_answer_state_locked(self):
        self._answer_text = ""
        self._thought_text = ""
        self._finished = False
        self._counted_message = False
        # если стрим приходит в сыром br-виде, буфер копится целиком
        # (съедено=0), а уже применённые события отсекаются по счётчику —
        # защита от дублей (как gzip-ветка AI Studio)
        self._compressed_events_seen = 0
        # v104.1: параллельные варианты ответа (Response 1/Response 2). Каждый
        # вариант копится отдельно; наружу через зеркала _answer_text/_thought_text/
        # _finished отдаётся только ГЛАВНЫЙ (см. _refresh_primary_locked).
        self._branch_texts = {}      # response_id -> текст ответа
        self._branch_thoughts = {}   # response_id -> текст мыслей
        self._branch_finished = {}   # response_id -> получен status=finished
        self._branch_order = []      # response_id в порядке появления
        self._branch_index = {}      # response_id -> response_index (если был в response.created)
        self._dual_logged = False

    def _decode_frames_partial(self, raw_bytes):
        raw = bytes(raw_bytes)
        if raw and not _looks_like_sse(raw):
            if _brotli is None:
                return [], 0  # дожмёт запасной путь getResponseBody
            try:
                plain = _brotli.decompress(raw)
            except Exception:
                return [], 0  # br докачается — попробуем на следующем чанке
            events = decode_qwen_sse_lines(plain.decode("utf-8", "replace"))
            fresh = events[self._compressed_events_seen:]
            self._compressed_events_seen = len(events)
            return fresh, 0
        return decode_qwen_sse_partial(raw)

    def _decode_frames(self, raw_bytes):
        raw = bytes(raw_bytes)
        if raw and not _looks_like_sse(raw) and _brotli is not None:
            try:
                raw = _brotli.decompress(raw)
            except Exception:
                pass
        return decode_qwen_sse_lines(raw.decode("utf-8", "replace"))

    def _answer_len_locked(self):
        return len(self._answer_text)

    # -- v104.1: параллельные варианты ответа -------------------------------------

    _NO_RID = "__no_response_id__"  # события старого формата без response_id

    def _register_branch_locked(self, rid, index=None):
        if rid not in self._branch_texts:
            self._branch_texts[rid] = ""
            self._branch_thoughts[rid] = ""
            self._branch_finished[rid] = False
            self._branch_order.append(rid)
            if len(self._branch_order) == 2 and not self._dual_logged:
                self._dual_logged = True
                self._log(u"в стриме ДВА параллельных варианта ответа "
                          u"(Response 1/Response 2) — показываю только первый (v104.1)")
        if index is not None and rid not in self._branch_index:
            self._branch_index[rid] = index

    def _primary_branch_locked(self):
        """Какой вариант показывать: наименьший response_index («Response 1» —
        его же автоматика qwen_parser выбирает кнопкой «I prefer this response»,
        v86.12); среди вариантов без индекса — первый, давший текст ответа."""
        with_text = [r for r in self._branch_order if self._branch_texts.get(r)]
        pool = with_text or self._branch_order
        if not pool:
            return None

        def _key(rid):
            idx = self._branch_index.get(rid)
            try:
                return (0, int(idx), self._branch_order.index(rid))
            except (TypeError, ValueError):
                return (1, 0, self._branch_order.index(rid))

        return min(pool, key=_key)

    def _refresh_primary_locked(self):
        """Зеркалит состояние ГЛАВНОГО варианта в _answer_text/_thought_text/
        _finished — весь остальной код (current_text, is_finished, answer_len)
        читает только зеркала и о вариантах не знает."""
        rid = self._primary_branch_locked()
        if rid is None:
            return
        self._answer_text = self._branch_texts.get(rid, "")
        self._thought_text = self._branch_thoughts.get(rid, "")
        self._finished = bool(self._branch_finished.get(rid))
        if self._finished:
            self._generating = False
            self._message_status = "FINISHED"

    def _apply_event(self, obj):
        created = obj.get("response.created")
        if isinstance(created, dict) and created.get("response_id"):
            # начало одного из вариантов ответа: запоминаем его номер (response_index)
            self._register_branch_locked(created.get("response_id"),
                                         created.get("response_index"))
            return
        choices = obj.get("choices")
        if not isinstance(choices, list) or not choices:
            return  # служебные события
        delta = (choices[0] or {}).get("delta")
        if not isinstance(delta, dict):
            return
        # v104.1: дельты параллельных вариантов различаются top-level response_id;
        # копим КАЖДЫЙ вариант отдельно, иначе их куски склеиваются посимвольно
        # (багрепорт 23.07.2026: «Прagent_action {"action": "readочитаю…»)
        rid = obj.get("response_id") or self._NO_RID
        self._register_branch_locked(rid)
        phase = str(delta.get("phase") or "")
        status = str(delta.get("status") or "")
        content = delta.get("content") or ""
        if phase == "answer":
            if content:
                self._branch_texts[rid] += content
                if not self._counted_message:
                    self._counted_message = True
                    self._assistant_message_count += 1
            if status == "finished":
                self._branch_finished[rid] = True
        elif phase.startswith("think"):
            extra = delta.get("extra") or {}
            thoughts = (extra.get("summary_thought") or {}).get("content")
            if isinstance(thoughts, list) and thoughts:
                # список нарастающий — заменяем, а не дописываем
                self._branch_thoughts[rid] = "\n\n".join(
                    str(x) for x in thoughts if x)
        self._refresh_primary_locked()

    def current_text(self):
        with self._lock:
            return self._answer_text

    def thought_text(self):
        with self._lock:
            return self._thought_text

    def is_finished(self):
        with self._lock:
            return self._finished
