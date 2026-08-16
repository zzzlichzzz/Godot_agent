# -*- coding: utf-8 -*-
"""Транспорт к нейросетям по OpenAI-совместимому протоколу.

ОДИН ТРАНСПОРТ НА ВСЕХ. POST <base_url>/chat/completions с телом
{model, messages, stream} понимают OpenRouter, Groq, Gemini (через слой
совместимости), DeepSeek, Qwen, а также локальные llama-server и Ollama.
Поэтому здесь нет ветвлений по провайдеру: провайдер — это base_url, модель
и ключ, а не отдельный код.

ПОЧЕМУ БЕЗ requests/httpx. В проекте нет ни одной сторонней HTTP-библиотеки:
сеть делается на urllib, а WebSocket для CDP написан руками (cdp_ws.py).
Сборка exe лежит в git, и каждая новая зависимость — лишние мегабайты в
репозитории. urllib для SSE достаточно: поток читается кусками и разбирается
на строки вручную, ровно как в net_monitor.py.

ОТМЕНА ПО КНОПКЕ «СТОП». Поток читает отдельный поток-демон и складывает
куски в очередь, а основной цикл забирает их с коротким таймаутом и между
забором проверяет cancel_cb. Тот же приём, что в net_monitor.py, и по той же
причине — блокирующее чтение нельзя держать в цикле, который должен
реагировать на отмену.

ПОЧЕМУ НЕ «ЧИТАТЬ КУСКАМИ С МАЛЫМ ТАЙМАУТОМ СОКЕТА». Так было сделано
сначала, и это тихо не работает: socket.SocketIO после ПЕРВОГО таймаута
навсегда ставит флаг _timeout_occurred, и любое следующее чтение падает с
OSError("cannot read from timed out object"). То есть «подождал, проверил
отмену, продолжил» с буферизованным ридером urllib невозможно в принципе —
пауза в потоке убивала бы соединение.

ПРОКСИ. Решение «через прокси или напрямую» принимается ЗДЕСЬ, по имени хоста,
а не отдаётся на откуп переменной no_proxy: её семантика на Windows зависит от
реестра и ведёт себя непредсказуемо. Локальные адреса (127.0.0.1, ::1,
localhost) через прокси не идут никогда — иначе сломался бы будущий
llama-server и любой локальный сервис.

TLS. Проверка сертификатов включена всегда, и параметра для её отключения тут
намеренно НЕТ. Через корректный CONNECT-прокси HTTPS остаётся сквозным, и
прокси не может прочитать ключ — но ровно до тех пор, пока проверка включена.
"""
import json
import queue
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

USER_AGENT = "GodotAgent/0.6"

# Сколько секунд ждём установления соединения и заголовков ответа.
DEFAULT_CONNECT_TIMEOUT = 30.0
# Сколько секунд полной тишины в потоке считаем обрывом. Ожидание первого
# токена у «думающих» моделей бывает долгим, а сервисы обычно присылают
# keep-alive (OpenRouter — строки-комментарии ": OPENROUTER PROCESSING"),
# поэтому такая тишина — действительно аномалия, а не медленная модель.
DEFAULT_SILENCE_TIMEOUT = 180.0
# Как часто основной цикл просыпается, чтобы проверить кнопку «Стоп».
_POLL_INTERVAL = 0.25
_READ_CHUNK = 8192


# ---------------------------------------------------------------------------
# Ошибки
# ---------------------------------------------------------------------------

class ApiError(Exception):
    """Базовая ошибка обращения к провайдеру.

    message уже прогнан через api_keys.redact() вызывающей стороной —
    некоторые сервисы возвращают присланный ключ в тексте ошибки, а весь
    stdout сервера виден на HTTP-странице /dashboard.
    """

    def __init__(self, message, status=None, retry_after=None):
        Exception.__init__(self, message)
        self.status = status
        self.retry_after = retry_after


class AuthError(ApiError):
    """401 — ключ неверный, отозван или не имеет прав. Повтор бессмыслен."""


class ForbiddenError(ApiError):
    """403 — доступ запрещён, но НЕ обязательно из-за ключа.

    Отдельный тип от AuthError сознательно. 401 почти всегда означает проблему
    с ключом, а 403 в реальности часто приходит от ПОСРЕДНИКА: фильтра
    интернет-провайдера, корпоративного прокси, антивируса с проверкой HTTPS
    или защиты сервиса от региона. Советовать «проверьте ключ» в таком случае —
    отправлять человека искать причину не там: именно так и вышло с ответом
    «Access denied by security policy» при полностью рабочем ключе.
    """


class PaymentRequiredError(ApiError):
    """402 — кончились кредиты (в том числе бесплатные). Повтор бессмыслен."""


class ModelNotFoundError(ApiError):
    """404 на chat/completions — обычно опечатка в идентификаторе модели
    или модель убрали из сервиса."""


class RateLimitError(ApiError):
    """429 — лимит запросов. daily=True, если лимит суточный: спать до его
    сброса бессмысленно, надо честно остановиться."""

    def __init__(self, message, status=None, retry_after=None, daily=False):
        ApiError.__init__(self, message, status=status, retry_after=retry_after)
        self.daily = daily


class ContextTooLongError(ApiError):
    """Контекст не влез в окно модели. Повтор тем же запросом бесполезен —
    нужен новый чат или обрезка истории."""


class ServerError(ApiError):
    """5xx или перегрузка сервиса — повтор имеет смысл."""


class TransportError(ApiError):
    """Сеть, DNS, прокси, TLS, обрыв потока — до модели не дошло."""


class Cancelled(Exception):
    """Пользователь нажал «Стоп». Отдельный тип, чтобы не путать с ошибкой:
    бэкенд переводит его в parser_base.ParserCancelled, который main.py
    уже умеет обрабатывать."""


# ---------------------------------------------------------------------------
# Соединение
# ---------------------------------------------------------------------------

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]")


def is_local_host(host):
    h = str(host or "").strip().lower().strip("[]")
    if not h:
        return False
    if h in ("localhost", "::1", "0.0.0.0"):
        return True
    if h.endswith(".localhost"):
        return True
    return h.startswith("127.")


def _build_opener(url, proxy):
    """Opener для конкретного адреса.

    Локальный адрес — всегда напрямую. Задан прокси в настройках — только он.
    Прокси не задан — поведение urllib по умолчанию (переменные окружения
    HTTPS_PROXY/HTTP_PROXY), чтобы уже настроенная в системе схема работала
    без дублирования настроек в панели.
    """
    host = urlsplit(url).hostname or ""
    handlers = [urllib.request.HTTPSHandler(context=ssl.create_default_context())]
    if is_local_host(host):
        handlers.append(urllib.request.ProxyHandler({}))
    elif proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)


def _headers(api_key, extra_headers, accept):
    h = {
        "Content-Type": "application/json",
        "Accept": accept,
        # Часть сервисов отклоняет запросы с User-Agent по умолчанию
        # ("Python-urllib/3.x"), принимая их за неаккуратный скрипт. А
        # AgentRouter пускает только клиентов из своего белого списка, поэтому
        # провайдер вправе подменить этот заголовок через extra_headers.
        "User-Agent": USER_AGENT,
    }
    # Сопоставление идёт БЕЗ УЧЁТА РЕГИСТРА и перезаписывает уже имеющийся
    # ключ. Иначе {"user-agent": ...} от провайдера не заменил бы "User-Agent",
    # а добавился бы рядом: urllib привёл бы оба к "User-agent", и какой из
    # двух уйдёт в запрос, зависело бы от порядка словаря.
    lower = {k.lower(): k for k in h}
    for k, v in (extra_headers or {}).items():
        if not v:
            continue
        name = str(k)
        h[lower.get(name.lower(), name)] = str(v)
    if api_key:
        h["Authorization"] = "Bearer %s" % api_key
    return h


def _socket_of(resp):
    """Сырой сокет ответа. Путь до него зависит от реализации, поэтому
    пробуем несколько вариантов и молча отступаем."""
    for getter in (lambda: resp.fp.raw._sock,
                   lambda: resp.fp._sock,
                   lambda: resp._fp.fp.raw._sock):
        try:
            sock = getter()
            if sock is not None:
                return sock
        except Exception:
            continue
    return None


def _set_socket_timeout(resp, seconds):
    """Меняет таймаут сокета УЖЕ УСТАНОВЛЕННОГО соединения.

    Зачем: соединению и TLS-рукопожатию нужен умеренный таймаут, а чтению
    потока — длинный (модель может думать минуты). urllib один таймаут на обе
    фазы разделить не умеет, поэтому меняем его после соединения. Если не
    удалось — работать всё равно будем, просто терпение к тишине окажется
    равно таймауту соединения.
    """
    sock = _socket_of(resp)
    if sock is None:
        return False
    try:
        sock.settimeout(seconds)
        return True
    except Exception:
        return False


def _force_close(resp):
    """Разрывает соединение так, чтобы разблокировать поток-читатель.

    Одного resp.close() на Windows недостаточно: чтение, уже вошедшее в recv,
    может не проснуться. shutdown() гарантированно выводит его из блокировки.
    """
    sock = _socket_of(resp)
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
    try:
        resp.close()
    except Exception:
        pass


def _spawn_reader(resp, q, stop):
    """Поток-демон: блокирующе читает поток и складывает куски в очередь.

    read1() вместо read(): read(n) ждёт, пока наберётся ровно n байт, и
    сгладил бы всю живую трансляцию в редкие крупные порции. read1() отдаёт
    то, что уже пришло.

    В очередь кладётся: bytes — данные, None — конец потока, Exception —
    ошибка чтения (её разбирает основной цикл, здесь ничего не решаем).
    """
    def run():
        reader = getattr(resp, "read1", None) or resp.read
        try:
            while not stop.is_set():
                chunk = reader(_READ_CHUNK)
                if not chunk:
                    q.put(None)
                    return
                q.put(chunk)
        except Exception as e:
            if not stop.is_set():
                q.put(e)
        finally:
            q.put(None)

    t = threading.Thread(target=run, name="api-sse-reader", daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Разбор ошибок провайдера
# ---------------------------------------------------------------------------

_CONTEXT_MARKERS = (
    "context length", "context_length", "maximum context",
    "too many tokens", "tokens exceed", "reduce the length",
    "input is too long", "prompt is too long", "context window",
)
_DAILY_MARKERS = (
    "per day", "per-day", "daily", "requests per day", "rpd",
    "quota exceeded", "free-models-per-day", "resource_exhausted",
)
_OVERLOAD_MARKERS = ("overloaded", "capacity", "try again later", "unavailable")


def _extract_provider_message(raw_body):
    """Человеческий текст ошибки из тела ответа.

    Форматы разные: {"error": {"message": ...}}, {"error": "..."},
    {"message": ...}, иногда просто HTML от балансировщика. Разбираем
    терпимо и в худшем случае отдаём начало тела как есть.
    """
    body = raw_body if isinstance(raw_body, str) else ""
    try:
        data = json.loads(body)
    except Exception:
        return body.strip()[:500]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("code") or ""
            meta = err.get("metadata")
            if not msg and isinstance(meta, dict):
                msg = meta.get("raw") or ""
            if msg:
                return str(msg)[:800]
        if isinstance(err, str) and err:
            return err[:800]
        if data.get("message"):
            return str(data["message"])[:800]
        detail = data.get("detail")
        if isinstance(detail, str) and detail:
            return detail[:800]
    return body.strip()[:500]


def _parse_retry_after(value):
    """Retry-After: либо секунды, либо дата по RFC 7231. Дату переводим в
    остаток секунд; мусор игнорируем."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return max(0, int(float(s)))
    except Exception:
        pass
    try:
        from email.utils import parsedate_to_datetime
        import datetime
        dt = parsedate_to_datetime(s)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        delta = (dt - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        return max(0, int(delta))
    except Exception:
        return None


def classify_http_error(status, body, headers=None):
    """HTTP-статус и тело -> типизированная ошибка.

    Тип важнее текста: по нему вызывающий код решает, повторять запрос,
    спать или честно останавливаться. Раньше это решение принималось по
    угадыванию текста баннера на странице сайта — по API есть точный статус.
    """
    msg = _extract_provider_message(body)
    low = (msg or "").lower()
    retry_after = None
    if headers is not None:
        try:
            retry_after = _parse_retry_after(headers.get("Retry-After"))
        except Exception:
            retry_after = None
    label = msg or ("HTTP %s" % status)
    if status == 401:
        return AuthError(label, status=status)
    if status == 403:
        # Признаки, что 403 всё-таки про ключ. Всё остальное считаем работой
        # посредника: слишком часто это фильтр провайдера или антивирус.
        key_words = ("key", "token", "auth", "credential", "unauthorized",
                     "ключ", "токен", "не авторизов")
        if any(w in low for w in key_words):
            return AuthError(label, status=status)
        return ForbiddenError(label, status=status)
    if status == 402:
        return PaymentRequiredError(label, status=status)
    if status == 404:
        return ModelNotFoundError(label, status=status)
    if status == 429:
        daily = any(m in low for m in _DAILY_MARKERS)
        return RateLimitError(label, status=status,
                              retry_after=retry_after, daily=daily)
    if status == 400 and any(m in low for m in _CONTEXT_MARKERS):
        return ContextTooLongError(label, status=status)
    if status == 413:
        return ContextTooLongError(label, status=status)
    if status >= 500 or any(m in low for m in _OVERLOAD_MARKERS):
        return ServerError(label, status=status, retry_after=retry_after)
    return ApiError(label, status=status)


# ---------------------------------------------------------------------------
# Разбор SSE
# ---------------------------------------------------------------------------

def split_sse_lines(buf):
    """Байтовый буфер -> (готовые строки, непрочитанный хвост).

    Хвост сохраняется до следующего куска: событие может прийти разрезанным
    посередине — та же логика, что у _decode_frames_partial в net_monitor.py.
    """
    lines = []
    while True:
        idx = buf.find(b"\n")
        if idx < 0:
            break
        raw, buf = buf[:idx], buf[idx + 1:]
        lines.append(raw.rstrip(b"\r").decode("utf-8", "replace"))
    return lines, buf


def parse_sse_line(line):
    """Строка SSE -> ("data", payload) | ("done", None) | ("skip", None).

    Строки, начинающиеся с ":" — комментарии-keep-alive (OpenRouter присылает
    ": OPENROUTER PROCESSING", пока модель думает). Их обязательно пропускать,
    иначе они попадут в ответ как текст.
    """
    if line is None:
        return "skip", None
    s = line.strip()
    if not s or s.startswith(":"):
        return "skip", None
    if not s.startswith("data:"):
        # event:/id:/retry: нам не нужны
        return "skip", None
    payload = s[5:].strip()
    if payload == "[DONE]":
        return "done", None
    return "data", payload


def extract_delta(obj):
    """Кусок ответа из одного события SSE.

    Возвращает (content, reasoning, finish_reason, usage, model).

    Про reasoning: «думающие» модели (например R1 через OpenRouter) отдают
    размышления отдельным полем delta.reasoning / delta.reasoning_content.
    В ТЕКСТ ОТВЕТА это попадать не должно — иначе служебный блок agent_action
    окажется вперемешку с рассуждениями и парсер действий их не отличит. Та же
    логика, что у is_thought в ai_studio_net.py.
    """
    content = ""
    reasoning = ""
    finish = None
    usage = None
    model = ""
    if not isinstance(obj, dict):
        return content, reasoning, finish, usage, model
    model = str(obj.get("model") or "")
    if isinstance(obj.get("usage"), dict):
        usage = obj["usage"]
    choices = obj.get("choices")
    if isinstance(choices, list):
        for ch in choices:
            if not isinstance(ch, dict):
                continue
            if ch.get("finish_reason"):
                finish = str(ch["finish_reason"])
            delta = ch.get("delta")
            if not isinstance(delta, dict):
                # Не-потоковый ответ приходит в "message" — поддерживаем,
                # чтобы одной функцией разбирать и поток, и обычный ответ.
                delta = ch.get("message") if isinstance(ch.get("message"), dict) else {}
            piece = delta.get("content")
            if isinstance(piece, str):
                content += piece
            elif isinstance(piece, list):
                # Некоторые слои совместимости отдают content списком частей.
                for part in piece:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        content += part["text"]
            for key in ("reasoning", "reasoning_content"):
                r = delta.get(key)
                if isinstance(r, str):
                    reasoning += r
    return content, reasoning, finish, usage, model


def error_in_event(obj):
    """Ошибка, пришедшая ВНУТРИ потока с кодом 200.

    Так ведут себя шлюзы: соединение открылось, а на середине генерации
    прилетает {"error": {...}}. Без этой проверки мы бы отдали пользователю
    обрезанный ответ как успешный.
    """
    if not isinstance(obj, dict):
        return None
    err = obj.get("error")
    if not err:
        return None
    if isinstance(err, dict):
        status = err.get("code") or err.get("status")
        try:
            status = int(status)
        except Exception:
            status = None
        return classify_http_error(status or 500, json.dumps({"error": err}))
    return ApiError(str(err)[:800])


# ---------------------------------------------------------------------------
# Основной вызов
# ---------------------------------------------------------------------------

def build_body(model, messages, max_tokens=None, temperature=None,
               stream=True, stop=None, extra_body=None):
    """Тело запроса. Необязательные поля добавляются ТОЛЬКО если заданы:
    строгие серверы (в том числе локальные) отвечают 400 на незнакомые или
    пустые параметры."""
    body = {"model": model, "messages": messages}
    if stream:
        body["stream"] = True
    if max_tokens:
        body["max_tokens"] = int(max_tokens)
    if temperature is not None:
        body["temperature"] = float(temperature)
    if stop:
        body["stop"] = list(stop)
    for k, v in (extra_body or {}).items():
        body[k] = v
    return body


def _open(url, api_key, extra_headers, proxy, payload, accept,
          connect_timeout, method="POST"):
    """Открывает соединение и отдаёт ответ либо бросает типизированную ошибку."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers=_headers(api_key, extra_headers, accept))
    opener = _build_opener(url, proxy)
    try:
        return opener.open(req, timeout=connect_timeout)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        raise classify_http_error(e.code, body, getattr(e, "headers", None))
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, ssl.SSLError):
            raise TransportError(
                u"Ошибка TLS: %s. Проверка сертификатов отключаться не должна — "
                u"если соединение идёт через прокси, он должен работать в режиме "
                u"CONNECT, а не подменять сертификаты." % reason)
        raise TransportError(u"Сеть недоступна: %s" % reason)
    except socket.timeout:
        raise TransportError(u"Таймаут соединения (%.0f с)" % connect_timeout)


def stream_chat(base_url, api_key, model, messages,
                max_tokens=None, temperature=None, extra_headers=None,
                proxy=None, connect_timeout=DEFAULT_CONNECT_TIMEOUT,
                silence_timeout=DEFAULT_SILENCE_TIMEOUT,
                cancel_cb=None, on_delta=None, stop=None, extra_body=None):
    """Запрос к модели с потоковым чтением ответа.

    on_delta(text, is_reasoning) вызывается на каждый кусочек — через него
    живая трансляция попадает в progress_cb и дальше в панель тем же
    словарём, что и у браузерных парсеров, поэтому UI менять не нужно.

    Возврат: {"text", "reasoning", "finish_reason", "usage", "model",
              "events", "elapsed"}.

    finish_reason == "length" означает, что модель НЕ ДОГОВОРИЛА из-за лимита
    вывода. В браузерном режиме это приходилось угадывать (для этого и нужен
    механизм "continues": true), здесь это точный факт — вызывающий код может
    сразу попросить продолжение.
    """
    url = base_url.rstrip("/") + "/chat/completions"
    payload = build_body(model, messages, max_tokens=max_tokens,
                         temperature=temperature, stream=True, stop=stop,
                         extra_body=extra_body)
    started = time.time()
    resp = _open(url, api_key, extra_headers, proxy, payload,
                 "text/event-stream", connect_timeout)
    # Терпение сокета делаем чуть больше нашего лимита тишины: за обрывом
    # следим мы сами, а таймаут сокета — только страховка от «полуоткрытого»
    # соединения, когда партнёр исчез, не закрыв его.
    _set_socket_timeout(resp, silence_timeout + 30.0)

    text_parts = []
    reasoning_parts = []
    finish_reason = None
    usage = None
    resp_model = ""
    events = 0
    buf = b""
    last_data = time.time()
    done = False
    q = queue.Queue()
    stop = threading.Event()
    _spawn_reader(resp, q, stop)
    try:
        while not done:
            if cancel_cb is not None and cancel_cb():
                raise Cancelled()
            try:
                item = q.get(timeout=_POLL_INTERVAL)
            except queue.Empty:
                # Данных пока нет — это нормально, модель думает. Вернулись в
                # цикл, чтобы проверить «Стоп», и следим за общей тишиной.
                if time.time() - last_data > silence_timeout:
                    raise TransportError(
                        u"Поток молчит %.0f с — соединение считаю оборванным."
                        % silence_timeout)
                continue
            if item is None:
                break
            if isinstance(item, ssl.SSLError):
                raise TransportError(u"Обрыв TLS при чтении потока: %s" % item)
            if isinstance(item, Exception):
                raise TransportError(u"Обрыв соединения при чтении потока: %s" % item)
            last_data = time.time()
            buf += item
            lines, buf = split_sse_lines(buf)
            for line in lines:
                kind, payload_str = parse_sse_line(line)
                if kind == "skip":
                    continue
                if kind == "done":
                    done = True
                    break
                try:
                    obj = json.loads(payload_str)
                except Exception:
                    # Битое событие пропускаем: терять один кусочек лучше,
                    # чем валить весь уже полученный ответ.
                    continue
                err = error_in_event(obj)
                if err is not None:
                    raise err
                events += 1
                content, reasoning, finish, u, m = extract_delta(obj)
                if m:
                    resp_model = m
                if u:
                    usage = u
                if finish:
                    finish_reason = finish
                if reasoning:
                    reasoning_parts.append(reasoning)
                    if on_delta is not None:
                        on_delta(reasoning, True)
                if content:
                    text_parts.append(content)
                    if on_delta is not None:
                        on_delta(content, False)
    finally:
        stop.set()
        _force_close(resp)

    return {
        "text": "".join(text_parts),
        "reasoning": "".join(reasoning_parts),
        "finish_reason": finish_reason,
        "usage": usage,
        "model": resp_model or model,
        "events": events,
        "elapsed": time.time() - started,
    }


def complete_chat(base_url, api_key, model, messages,
                  max_tokens=None, temperature=None, extra_headers=None,
                  proxy=None, connect_timeout=DEFAULT_CONNECT_TIMEOUT,
                  extra_body=None):
    """Запрос БЕЗ потока. Нужен проверке подключения: короткий ответ, никакой
    живой трансляции, минимум неизвестных в диагностике."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = build_body(model, messages, max_tokens=max_tokens,
                         temperature=temperature, stream=False,
                         extra_body=extra_body)
    started = time.time()
    resp = _open(url, api_key, extra_headers, proxy, payload,
                 "application/json", connect_timeout)
    try:
        raw = resp.read().decode("utf-8", "replace")
    finally:
        try:
            resp.close()
        except Exception:
            pass
    try:
        obj = json.loads(raw)
    except Exception:
        raise TransportError(u"Ответ не является JSON: %s" % raw[:200])
    err = error_in_event(obj)
    if err is not None:
        raise err
    content, reasoning, finish, usage, m = extract_delta(obj)
    return {"text": content, "reasoning": reasoning, "finish_reason": finish,
            "usage": usage, "model": m or model,
            "elapsed": time.time() - started}


def tls_probe(base_url, proxy=None, timeout=10.0):
    """Кто на самом деле отвечает по этому адресу — по TLS-сертификату.

    Зачем. Если между вами и сервисом стоит антивирус или корпоративный шлюз с
    проверкой HTTPS, он подменяет сертификат на свой (его корневой сертификат
    установлен в системе, поэтому проверка проходит и обмана не видно). Внешне
    это выглядит как ответ сервиса — например «Access denied by security
    policy» с кодом 403 при полностью рабочем ключе.

    Издатель сертификата отвечает на этот вопрос однозначно: у настоящего
    сервиса это публичный удостоверяющий центр, у перехватчика — его
    собственное имя. Возвращает {"ok", "host", "issuer", "subject", "error"}.
    """
    from urllib.parse import urlsplit
    parts = urlsplit(base_url if "://" in base_url else "https://" + base_url)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme != "http" else 80)
    out = {"ok": False, "host": host, "issuer": "", "subject": "", "error": ""}
    if not host:
        out["error"] = u"не удалось разобрать адрес"
        return out
    if parts.scheme == "http":
        out["error"] = u"адрес без TLS (http://) — сертификата нет"
        return out
    sock = None
    try:
        if proxy:
            sock = _connect_via_proxy(proxy, host, port, timeout)
        else:
            sock = socket.create_connection((host, port), timeout=timeout)
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            cert = tls.getpeercert() or {}
        sock = None
        out["ok"] = True
        out["issuer"] = _cert_name(cert.get("issuer"))
        out["subject"] = _cert_name(cert.get("subject"))
    except Exception as e:
        out["error"] = str(e)
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
    return out


def _cert_name(rdns):
    """«O=Let's Encrypt, CN=R11» из структуры сертификата."""
    if not rdns:
        return ""
    parts = []
    for rdn in rdns:
        for key, value in rdn:
            if key in ("organizationName", "commonName"):
                parts.append("%s=%s" % ("O" if key == "organizationName" else "CN",
                                        value))
    return ", ".join(parts)


def _connect_via_proxy(proxy, host, port, timeout):
    """TCP-туннель через HTTP-прокси методом CONNECT."""
    from urllib.parse import urlsplit
    p = urlsplit(proxy if "://" in proxy else "http://" + proxy)
    sock = socket.create_connection((p.hostname, p.port or 8080), timeout=timeout)
    req = "CONNECT %s:%d HTTP/1.1\r\nHost: %s:%d\r\n" % (host, port, host, port)
    if p.username:
        import base64
        token = base64.b64encode(
            ("%s:%s" % (p.username, p.password or "")).encode("utf-8")).decode()
        req += "Proxy-Authorization: Basic %s\r\n" % token
    sock.sendall((req + "\r\n").encode("ascii"))
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    first = data.split(b"\r\n", 1)[0].decode("latin-1", "replace")
    if " 200 " not in first:
        sock.close()
        raise OSError(u"прокси отказал в туннеле: %s" % first)
    return sock


def fetch_models(models_url, api_key, extra_headers=None, proxy=None,
                 connect_timeout=DEFAULT_CONNECT_TIMEOUT):
    """Список моделей провайдера (сырой JSON). Разбирает его providers.py —
    знание про формат pricing принадлежит реестру, не транспорту."""
    resp = _open(models_url, api_key, extra_headers, proxy, None,
                 "application/json", connect_timeout, method="GET")
    try:
        raw = resp.read().decode("utf-8", "replace")
    finally:
        try:
            resp.close()
        except Exception:
            pass
    try:
        return json.loads(raw)
    except Exception:
        raise TransportError(u"Список моделей пришёл не в JSON: %s" % raw[:200])
