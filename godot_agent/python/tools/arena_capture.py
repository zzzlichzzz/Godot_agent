# -*- coding: utf-8 -*-
"""Одноразовый скрипт захвата данных arena.ai для написания парсера.

Что делает:
1. Подключается к браузеру агента (Chrome с --remote-debugging-port=9222,
   профиль %LOCALAPPDATA%\\Godot_AI_Profile).
2. Находит вкладку arena.ai (url содержит "arena.ai").
3. Подключается по CDP WebSocket, подписывается на Network.* события.
4. Ждёт, пока ты на сайте отправишь сообщение (POST /nextjs-api/stream/post-to-evaluation/...).
5. Ловит:
   - тело запроса (request.postData) — как arena_1_payload.json
   - SSE-стрим ответа (через Network.streamResourceContent + dataReceived) — как arena_2_stream.txt
   - DOM селекторы ключевых элементов — как arena_3_dom.json
6. Всё пишет в addons/Godot_agent/временно/ БЕЗ cookie и заголовков авторизации.

Запуск:
    cd addons/Godot_agent/godot_agent/python
    python tools/arena_capture.py

Перед запуском:
- Chrome агента должен быть запущен (или запустится сам при первом вызове).
- Ты должен быть залогинен на arena.ai в этом профиле.
- Открой чат (https://arena.ai/text/direct или https://arena.ai/c/<uuid>).
- После запуска скрипта просто отправь одно-два сообщения на сайте.
- Скрипт сам завершится через 5 сек после первой успешной перехватки стрима.
"""

import base64
import json
import os
import sys
import threading
import time
from pathlib import Path

# Bootstrap пути для плоских импортов (browser, parsers, и т.д.)
_HERE = Path(__file__).resolve().parent.parent
for _d in (_HERE, _HERE / "browser", _HERE / "parsers", _HERE / "godot_tools", _HERE / "server"):
    if _d.is_dir() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from browser.browser_manager import setup_browser, find_chrome
from browser.cdp_ws import CDPSession, find_page_ws_url


OUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "временно"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PAYLOAD_FILE = OUT_DIR / "arena_1_payload.json"
STREAM_FILE = OUT_DIR / "arena_2_stream.txt"
DOM_FILE = OUT_DIR / "arena_3_dom.json"

TARGET_URL_SUBSTR = "post-to-evaluation"
CHAT_URL_SUBSTR = "arena.ai"

_captured = {"payload": False, "stream_done": False}
_stream_buffer = bytearray()
_stream_lock = threading.Lock()
_cdp_session = None
_driver = None


def log(msg):
    print(f"[arena_capture] {msg}")


def save_payload(request_id, post_data):
    if _captured["payload"]:
        return
    try:
        data = json.loads(post_data) if isinstance(post_data, str) else post_data
    except Exception:
        data = {"raw": post_data}
    # Удаляем чувствительные поля, если они вдруг попали в тело
    if isinstance(data, dict):
        for k in list(data.keys()):
            if k.lower() in ("cookie", "authorization", "token", "api_key", "apikey"):
                data[k] = "[REDACTED]"
    PAYLOAD_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Payload сохранён: {PAYLOAD_FILE}")
    _captured["payload"] = True


def decode_sse_chunk(raw_bytes):
    """Возвращает список полных SSE-событий (json-объектов) и число съеденных байт."""
    raw = bytes(raw_bytes)
    idx = raw.rfind(b"\n")
    if idx < 0:
        return [], 0
    head = raw[:idx + 1]
    events = []
    for line in head.split(b"\n"):
        line = line.strip()
        if not line.startswith(b"data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == b"[DONE]":
            continue
        try:
            obj = json.loads(payload.decode("utf-8", "replace"))
        except Exception:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events, len(head)


def on_data_received(params):
    global _stream_buffer
    data_b64 = params.get("data")
    if not data_b64:
        return
    try:
        chunk = base64.b64decode(data_b64)
    except Exception:
        return
    with _stream_lock:
        _stream_buffer.extend(chunk)
        events, consumed = decode_sse_chunk(_stream_buffer)
        if consumed:
            del _stream_buffer[:consumed]
        for ev in events:
            STREAM_FILE.open("a", encoding="utf-8").write(json.dumps(ev, ensure_ascii=False) + "\n")


def on_loading_finished(params):
    req_id = params.get("requestId")
    with _stream_lock:
        # Дочитываем хвост
        events, _ = decode_sse_chunk(_stream_buffer)
        for ev in events:
            STREAM_FILE.open("a", encoding="utf-8").write(json.dumps(ev, ensure_ascii=False) + "\n")
        _stream_buffer.clear()
    log(f"Стрим завершён (requestId={req_id})")
    _captured["stream_done"] = True


def on_response_received(params):
    resp = params.get("response") or {}
    url = resp.get("url") or ""
    mime = resp.get("mimeType") or ""
    req_id = params.get("requestId")
    if TARGET_URL_SUBSTR in url and "event-stream" in mime:
        log(f"Обнаружен SSE-ответ: {url}")
        # Включаем стриминг тела
        try:
            _cdp_session.send_command("Network.streamResourceContent", {"requestId": req_id})
        except Exception as e:
            log(f"streamResourceContent недоступен: {e}")


def on_request_will_be_sent(params):
    req = params.get("request") or {}
    url = req.get("url") or ""
    method = req.get("method") or ""
    post_data = req.get("postData")
    if TARGET_URL_SUBSTR in url and method.upper() == "POST":
        log(f"Перехвачен POST: {url}")
        save_payload(params.get("requestId"), post_data)


def capture_dom(driver):
    """Снимает селекторы ключевых элементов arena.ai."""
    js = r"""
    (function() {
        function cssPath(el) {
            if (!(el instanceof Element)) return '';
            var path = [];
            while (el.nodeType === Node.ELEMENT_NODE) {
                var selector = el.nodeName.toLowerCase();
                if (el.id) {
                    selector += '#' + el.id;
                    path.unshift(selector);
                    break;
                } else {
                    var sib = el, nth = 1;
                    while (sib = sib.previousElementSibling) {
                        if (sib.nodeName.toLowerCase() === selector) nth++;
                    }
                    if (nth !== 1) selector += ':nth-of-type(' + nth + ')';
                }
                path.unshift(selector);
                el = el.parentElement;
            }
            return path.join(' > ');
        }
        var out = {};
        // Поле ввода
        var ta = document.querySelector('textarea[name="message"]');
        if (ta) out.input = cssPath(ta);
        // Кнопка отправки (ищем рядом с textarea)
        if (ta) {
            var form = ta.closest('form');
            if (form) {
                var btn = form.querySelector('button[type="submit"], button[aria-label*="Send" i], button[aria-label*="Отправ" i]');
                if (btn) out.send_button = cssPath(btn);
            }
        }
        // Контейнер ответа (ищем по data-code-block или prose)
        var codeBlocks = document.querySelectorAll('[data-code-block="true"]');
        if (codeBlocks.length) out.code_block = cssPath(codeBlocks[0]);
        var prose = document.querySelector('.prose, [class*="prose"]');
        if (prose) out.prose = cssPath(prose);
        // Кнопка нового чата
        var newChat = document.querySelector('a[href*="/text/direct"], a[href*="/c/"], button[aria-label*="New" i], button[aria-label*="Нов" i]');
        if (newChat) out.new_chat = cssPath(newChat);
        // Индикатор генерации (кнопка стоп)
        var stopBtn = document.querySelector('button[aria-label*="Stop" i], button[aria-label*="Остан" i]');
        if (stopBtn) out.stop_button = cssPath(stopBtn);
        // Like кнопка (признак готового ответа)
        var likeBtn = document.querySelector('button[aria-label*="Like" i], button[aria-label*="Нрав" i]');
        if (likeBtn) out.like_button = cssPath(likeBtn);
        return out;
    })();
    """
    try:
        selectors = driver.execute_script(js)
        DOM_FILE.write_text(json.dumps(selectors, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"DOM селекторы сохранены: {DOM_FILE}")
        log(f"  {selectors}")
    except Exception as e:
        log(f"Ошибка захвата DOM: {e}")


def main():
    global _cdp_session, _driver

    log("Подключение к браузеру агента...")
    _driver = setup_browser()

    # Находим вкладку arena.ai
    log("Поиск вкладки arena.ai...")
    ws_url = None
    for _ in range(30):
        ws_url = find_page_ws_url(CHAT_URL_SUBSTR)
        if ws_url:
            break
        time.sleep(1)
    if not ws_url:
        log("Вкладка arena.ai не найдена. Открой https://arena.ai/text/direct в браузере агента и перезапусти скрипт.")
        return

    log(f"CDP WebSocket: {ws_url}")
    _cdp_session = CDPSession(ws_url)

    # Подписки на Network события
    _cdp_session.on_event("Network.requestWillBeSent", on_request_will_be_sent)
    _cdp_session.on_event("Network.responseReceived", on_response_received)
    _cdp_session.on_event("Network.dataReceived", on_data_received)
    _cdp_session.on_event("Network.loadingFinished", on_loading_finished)

    # Включаем Network домен
    _cdp_session.send_command("Network.enable")
    log("Network.enable отправлен. Жду сообщений на сайте...")

    # Даём время на перехват
    start = time.time()
    while not (_captured["payload"] and _captured["stream_done"]):
        if time.time() - start > 120:
            log("Таймаут 120с — выхожу")
            break
        if not _cdp_session.is_alive():
            log("CDP сессия умерла")
            break
        time.sleep(0.5)

    # Финальный захват DOM
    log("Захват DOM селекторов...")
    capture_dom(_driver)

    # Чистка
    try:
        _cdp_session.close()
    except Exception:
        pass

    log("Готово. Файлы в временно/:")
    for f in (PAYLOAD_FILE, STREAM_FILE, DOM_FILE):
        if f.exists():
            log(f"  {f.name} ({f.stat().st_size} байт)")


if __name__ == "__main__":
    main()