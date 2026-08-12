# -*- coding: utf-8 -*-
"""Универсальный скрипт захвата сетевого трафика + DOM для НАПИСАНИЯ парсера.

Использование:
    python tools/capture_site.py --site-addr arena.ai --target post-to-evaluation --prefix arena
    python tools/capture_site.py --site-addr aistudio.google.com --target MakerSuiteService/GenerateContent --prefix aistudio

Что делает:
1. Подключается к браузеру агента (Chrome --remote-debugging-port=9222).
2. Ищет вкладку, url которой содержит --site-addr.
3. Подписывается на Network.* через CDP WebSocket.
4. Ловит POST, url которого содержит --target:
   - тело запроса в <prefix>_1_payload.json (без cookie/авторизации);
   - СЫРОЙ поток ответа в <prefix>_2_stream.raw;
   - текст ответа (после декодов) в <prefix>_2_stream.txt;
   - DOM-селекторы в <prefix>_3_dom.json.
5. Пишет в addons/Godot_agent/временно/.

Валидация на AI Studio (эталон известен):
    python tools/capture_site.py --site-addr aistudio.google.com --target MakerSuiteService/GenerateContent --prefix aistudio
Отправь сообщение на AI Studio. В aistudio_2_stream.txt должен быть ТОТ ЖЕ текст,
что на экране — значит считыватель работает.
"""

import argparse
import base64
import json
import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
for _d in (_HERE, _HERE / "browser", _HERE / "parsers", _HERE / "godot_tools", _HERE / "server"):
    if _d.is_dir() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from browser.browser_manager import setup_browser
from browser.cdp_ws import CDPSession, find_page_ws_url
from browser import qwen_net
from browser import ai_studio_net

OUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "временно"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Парсер аргументов (не парсим здесь — сделаем в main())
ARGS = None

# Состояние захвата — на один requestId
_state = {
    "target_req_id": None,
    "payload_captured": False,
    "stream_raw": bytearray(),
    "stream_done": False,
    "stream_lock": threading.Lock(),
}
CDP = None
DRIVER = None


def log(msg):
    print("[capture] %s" % msg)


def sanitize_post(data):
    """Удаляет чувствительные поля из тела запроса."""
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if k.lower() in ("cookie", "authorization", "token", "api_key", "apikey"):
                out[k] = "[REDACTED]"
            else:
                out[k] = v
        return out
    if isinstance(data, str):
        try:
            return sanitize_post(json.loads(data))
        except Exception:
            return data
    return data


def detect_decoder(head_bytes):
    head = bytes(head_bytes[:64]).lstrip()
    if head[:5] == b"data:" or head[:1] in (b":", b"e"):
        return "sse"
    if head[:2] == b"\x1f\x8b":
        return "gzip"
    if head[:1] == b"[":
        return "aistudio"
    return "raw"


def try_decode_text(raw, kind):
    try:
        if kind == "sse":
            events = qwen_net.decode_qwen_sse_lines(raw.decode("utf-8", "replace"))
            text = ""
            for obj in events:
                delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                c = delta.get("content")
                if isinstance(c, str):
                    text += c
            return text or ("[SSE saved as .raw only]\n" + raw.decode("utf-8", "replace"))
        if kind == "aistudio":
            objs = ai_studio_net._decode_chunks_from_start(raw.decode("utf-8", "replace"))
            text = ""
            for obj in objs:
                for t, is_thought in ai_studio_net.extract_parts(obj):
                    if not is_thought:
                        text += t
            return text or raw.decode("utf-8", "replace")
        return raw.decode("utf-8", "replace")
    except Exception as e:
        return "[decode error: %s] %r" % (e, raw[:200])


def on_request_will_be_sent(params):
    req = params.get("request") or {}
    url = req.get("url") or ""
    method = req.get("method") or ""
    post = req.get("postData")
    req_id = params.get("requestId")
    if ARGS.target in url and method.upper() == "POST":
        if _state["target_req_id"] is None:
            _state["target_req_id"] = req_id
            log("Захватываем requestId=%s: %s" % (req_id, url))
        if req_id != _state["target_req_id"]:
            return  # игнорируем другие POST к тому же эндпоинту
        if _state["payload_captured"]:
            return
        data = sanitize_post(post)
        p_file = OUT_DIR / ("%s_1_payload.json" % ARGS.prefix)
        p_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log("Payload -> %s" % p_file)
        _state["payload_captured"] = True


def on_response_received(params):
    resp = params.get("response") or {}
    url = resp.get("url") or ""
    mime = resp.get("mimeType") or ""
    req_id = params.get("requestId")
    if req_id != _state["target_req_id"]:
        return
    if ARGS.target in url:
        log("Ответ %s (mime=%s) для requestId=%s" % (url, mime, req_id))
        try:
            CDP.send_command("Network.streamResourceContent", {"requestId": req_id})
        except Exception as e:
            log("streamResourceContent недоступен: %s" % e)


def on_data_received(params):
    data_b64 = params.get("data")
    if not data_b64:
        return
    req_id = params.get("requestId")
    if req_id != _state["target_req_id"]:
        return
    try:
        chunk = base64.b64decode(data_b64)
    except Exception:
        return
    with _state["stream_lock"]:
        _state["stream_raw"].extend(chunk)


def _fetch_body_and_save(req_id):
    """Вызывается в отдельном потоке, чтобы не дедлокиться с CDP read-loop."""
    try:
        body = CDP.send_command("Network.getResponseBody", {"requestId": req_id}, timeout=20.0)
    except Exception as e:
        log("getResponseBody failed: %s" % e)
        body = None
    if body:
        b64 = body.get("base64Encoded", False)
        raw = base64.b64decode(body.get("body") or "") if b64 else (body.get("body") or "").encode("utf-8")
        log("getResponseBody получено: %d байт" % len(raw))
    else:
        raw = b""

    raw_file = OUT_DIR / ("%s_2_stream.raw" % ARGS.prefix)
    raw_file.write_bytes(raw)
    log("Raw -> %s" % raw_file)

    txt_file = OUT_DIR / ("%s_2_stream.txt" % ARGS.prefix)
    kind = detect_decoder(raw)
    txt = try_decode_text(raw, kind)
    txt_file.write_text(txt, encoding="utf-8")
    log("Decoded (%s) -> %s" % (kind, txt_file))
    log("Текст: %r" % txt[:500])

    _state["stream_done"] = True


def on_loading_finished(params):
    req_id = params.get("requestId")
    if req_id != _state["target_req_id"]:
        return
    if _state["stream_done"]:
        return
    with _state["stream_lock"]:
        raw = bytes(_state["stream_raw"])
    log("Стрим завершён: %d байт" % len(raw))

    if raw:
        # live-стрим пришёл — сохраняем сразу
        raw_file = OUT_DIR / ("%s_2_stream.raw" % ARGS.prefix)
        raw_file.write_bytes(raw)
        log("Raw -> %s" % raw_file)

        txt_file = OUT_DIR / ("%s_2_stream.txt" % ARGS.prefix)
        kind = detect_decoder(raw)
        txt = try_decode_text(raw, kind)
        txt_file.write_text(txt, encoding="utf-8")
        log("Decoded (%s) -> %s" % (kind, txt_file))
        log("Текст: %r" % txt[:500])

        _state["stream_done"] = True
    else:
        # live-стрим пуст — фоллбэк в отдельном потоке (избегаем дедлок CDP)
        log("Live-стрим пуст — пробую getResponseBody в фоне...")
        threading.Thread(target=_fetch_body_and_save, args=(req_id,), daemon=True).start()


def capture_dom():
    js = r"""
    (function() {
        function cssPath(el) {
            if (!(el instanceof Element)) return '';
            var path = [];
            while (el.nodeType === Node.ELEMENT_NODE) {
                var selector = el.nodeName.toLowerCase();
                if (el.id) { selector += '#' + el.id; path.unshift(selector); break; }
                else {
                    var sib = el, nth = 1;
                    while (sib = sib.previousElementSibling) {
                        if (sib.nodeName.toLowerCase() === selector) nth++;
                    }
                    if (nth !== 1) selector += ':nth-of-type(' + nth + ')';
                }
                path.unshift(selector); el = el.parentElement;
            }
            return path.join(' > ');
        }
        var walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        var txts = [], max = 3000, total = 0, n;
        while ((n = walk.nextNode()) && max > 0) {
            var t = (n.textContent || '').trim();
            if (!t) continue;
            txts.push(t.slice(0, 200));
            max--; total += t.length;
        }
        var ta = document.querySelector('textarea');
        return {
            body: document.body ? document.body.innerHTML.slice(0, 4000) : '',
            texts_seen: txts.slice(0, 60),
            text_total_chars: total,
            textarea: ta ? ('<textarea' + (ta.name ? ' name=' + ta.name : '') + '>') : null,
        };
    })();
    """
    try:
        dom = DRIVER.execute_script(js)
        dom_file = OUT_DIR / ("%s_3_dom.json" % ARGS.prefix)
        dom_file.write_text(json.dumps(dom, ensure_ascii=False, indent=2), encoding="utf-8")
        log("DOM -> %s" % dom_file)
    except Exception as e:
        log("DOM error: %s" % e)


def main():
    global ARGS, CDP, DRIVER

    parser = argparse.ArgumentParser()
    parser.add_argument("--site-addr", required=True, help="подстрока url вкладки (arena.ai / aistudio.google.com)")
    parser.add_argument("--target", required=True, help="подстрока url запроса (post-to-evaluation / MakerSuiteService/GenerateContent)")
    parser.add_argument("--prefix", default="capture", help="префикс файлов")
    parser.add_argument("--wait", type=int, default=120, help="секунд ждать перехвата")
    ARGS = parser.parse_args()

    log("Подключение к браузеру агента...")
    DRIVER = setup_browser()

    ws_url = None
    for _ in range(30):
        ws_url = find_page_ws_url(ARGS.site_addr)
        if ws_url:
            break
        time.sleep(1)
    if not ws_url:
        log("Вкладка с '%s' не найдена. Открой её в браузере агента и повтори." % ARGS.site_addr)
        return

    log("CDP: %s" % ws_url)
    CDP = CDPSession(ws_url)
    CDP.on_event("Network.requestWillBeSent", on_request_will_be_sent)
    CDP.on_event("Network.responseReceived", on_response_received)
    CDP.on_event("Network.dataReceived", on_data_received)
    CDP.on_event("Network.loadingFinished", on_loading_finished)
    CDP.send_command("Network.enable")
    log("Network.enable OK. Отправь сообщение на сайте (%s)..." % ARGS.site_addr)

    start = time.time()
    while not (_state["payload_captured"] and _state["stream_done"]):
        if time.time() - start > ARGS.wait:
            log("Таймаут %ds" % ARGS.wait)
            break
        if not CDP.is_alive():
            log("CDP сессия умерла")
            break
        time.sleep(0.5)

    if _state["payload_captured"] and _state["stream_done"]:
        capture_dom()
    else:
        log("Захват неполный: payload=%s stream=%s — DOM пропущен" % (_state["payload_captured"], _state["stream_done"]))

    try:
        CDP.close()
    except Exception:
        pass
    log("Готово. Файлы в %s" % OUT_DIR)


if __name__ == "__main__":
    main()