# -*- coding: utf-8 -*-
"""Arena AI parser: trusted input and network-only answer reading."""
import ctypes
from ctypes import wintypes
import json
import sys
import threading
import time
import base64
from urllib.parse import urlparse

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By

from cdp_ws import CDPSession, find_page_ws_url_for_target, list_targets
from net_monitor import BaseNetMonitor
from parser_base import (DONE_MARKER, BaseSiteParser, select_best_answer_variant,
                         split_net_text_and_action)
from answer_judge import judge_answer, select_best_project_answer


def decode_arena_stream_lines(text):
    """Decode complete lines from Arena's Vercel-style stream."""
    events = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        prefix, payload = line.split(":", 1)
        if prefix == "ad":
            try:
                meta = json.loads(payload)
            except (TypeError, ValueError):
                continue
            if isinstance(meta, dict):
                events.append({"kind": "done", "meta": meta})
            continue
        if prefix.startswith("a") and prefix[1:].isdigit():
            try:
                chunk = json.loads(payload)
            except (TypeError, ValueError):
                continue
            if isinstance(chunk, str):
                events.append({"kind": "text", "stream": int(prefix[1:]),
                               "text": chunk})
    return events


def decode_arena_stream_partial(raw_bytes):
    """Decode complete newline-delimited frames and retain an incomplete tail."""
    raw = bytes(raw_bytes)
    idx = raw.rfind(b"\n")
    if idx < 0:
        return [], 0
    head = raw[:idx + 1]
    return decode_arena_stream_lines(head.decode("utf-8", "replace")), len(head)


class ArenaChatMonitor(BaseNetMonitor):
    # First message: /nextjs-api/stream/create-evaluation
    # Following messages: /nextjs-api/stream/post-to-evaluation/<chat-id>
    CHAT_URL_SUBSTR = "/nextjs-api/stream/"
    RESPONSE_MIME_SUBSTR = "text/event-stream"
    LOG_TAG = "arena_parser"

    def __init__(self, cdp):
        self._battle_capture = False
        self._battle_before_count = 0
        self._battle_request_ids = []
        self._battle_request_branches = {}
        self._battle_completed = set()
        self._battle_stream_bufs = {}
        self._battle_stream_ready = {}
        self._battle_streamed = set()
        super().__init__(cdp)

    def begin_battle_capture(self, before_count):
        with self._lock:
            self._battle_capture = True
            self._battle_before_count = before_count
            self._battle_request_ids = []
            self._battle_request_branches = {}
            self._battle_completed = set()
            self._battle_stream_bufs = {}
            self._battle_stream_ready = {}
            self._battle_streamed = set()
            self._reset_answer_state_locked()

    def end_battle_capture(self):
        with self._lock:
            self._battle_capture = False

    def battle_waiting_for_second_branch(self):
        with self._lock:
            nonempty = sum(1 for text in self._branch_texts.values() if text.strip())
            return self._battle_capture and nonempty < 2

    def _on_request_will_be_sent(self, params):
        super()._on_request_will_be_sent(params)
        if not self._battle_capture:
            return
        req = params.get("request") or {}
        if not self._match_request(req.get("url") or "", req.get("method") or ""):
            return
        req_id = params.get("requestId")
        with self._lock:
            if (self._chat_request_count > self._battle_before_count
                    and req_id not in self._battle_request_branches):
                branch = len(self._battle_request_ids)
                self._battle_request_ids.append(req_id)
                self._battle_request_branches[req_id] = branch

    def _on_response_received(self, params):
        if not self._battle_capture:
            return super()._on_response_received(params)
        resp = params.get("response") or {}
        if not self._match_response(resp.get("url") or "", resp.get("mimeType") or ""):
            return
        req_id = params.get("requestId")
        with self._lock:
            if req_id not in self._battle_request_branches:
                return
            self._generating = True
            self._message_status = None
            self._answer_request_count = self._chat_request_count
            self._battle_stream_bufs[req_id] = bytearray()
            self._battle_stream_ready[req_id] = threading.Event()
        self._log("Battle: принят параллельный ответ %s как вариант %s"
                  % (req_id, "A" if self._battle_request_branches[req_id] == 0 else "B"))
        threading.Thread(target=self._enable_battle_stream,
                         args=(req_id,), daemon=True).start()

    def _on_data_received(self, params):
        if not self._battle_capture:
            return super()._on_data_received(params)
        req_id = params.get("requestId")
        data = params.get("data")
        if not data:
            return
        try:
            chunk = base64.b64decode(data)
        except Exception:
            return
        with self._lock:
            buf = self._battle_stream_bufs.get(req_id)
            if buf is None:
                return
            buf.extend(chunk)
            if req_id in self._battle_streamed:
                self._parse_battle_stream_locked(req_id)

    def _on_loading_finished(self, params):
        if not self._battle_capture:
            return super()._on_loading_finished(params)
        req_id = params.get("requestId")
        with self._lock:
            if req_id not in self._battle_request_branches:
                return
        threading.Thread(target=self._finish_battle_request,
                         args=(req_id,), daemon=True).start()

    def _enable_battle_stream(self, req_id):
        try:
            response = self._cdp.send_command(
                "Network.streamResourceContent", {"requestId": req_id})
            buffered = response.get("bufferedData") or ""
            raw = base64.b64decode(buffered) if buffered else b""
            with self._lock:
                buf = self._battle_stream_bufs.get(req_id)
                if buf is None:
                    return
                self._battle_stream_bufs[req_id] = bytearray(raw) + buf
                self._battle_streamed.add(req_id)
                self._parse_battle_stream_locked(req_id)
        except Exception as exc:
            self._log("Battle: streamResourceContent недоступен для %s: %s" % (req_id, exc))
        finally:
            event = self._battle_stream_ready.get(req_id)
            if event is not None:
                event.set()

    def _parse_battle_stream_locked(self, req_id):
        buf = self._battle_stream_bufs.get(req_id)
        if buf is None:
            return
        events, consumed = self._decode_frames_partial(bytes(buf))
        if consumed:
            del buf[:consumed]
        branch = self._battle_request_branches.get(req_id)
        for event in events:
            if event.get("kind") == "text":
                event = dict(event)
                event["stream"] = branch
                self._apply_event(event)

    def _finish_battle_request(self, req_id):
        event = self._battle_stream_ready.get(req_id)
        if event is not None:
            event.wait(5.0)
        with self._lock:
            streamed = req_id in self._battle_streamed
        fallback_events = []
        if not streamed:
            # Fast Arena replies can finish before streamResourceContent is
            # enabled. Unlike a live SSE body, CDP retains these for the
            # ordinary getResponseBody fallback.
            for attempt in range(3):
                try:
                    body = self._cdp.send_command(
                        "Network.getResponseBody", {"requestId": req_id})
                    raw = body.get("body") or ""
                    raw_bytes = (base64.b64decode(raw) if body.get("base64Encoded")
                                 else raw.encode("utf-8"))
                    fallback_events = self._decode_frames(raw_bytes)
                    if any(item.get("kind") == "text" and item.get("text")
                           for item in fallback_events):
                        self._log("Battle: вариант %s прочитан запасным getResponseBody"
                                  % req_id)
                        break
                except Exception as exc:
                    if attempt == 2:
                        self._log("Battle: не удалось прочитать вариант %s: %s"
                                  % (req_id, exc))
                time.sleep(0.25)
        with self._lock:
            branch = self._battle_request_branches.get(req_id)
            if branch is None:
                return
            if fallback_events:
                # A single Battle POST can contain a0/a1 itself; preserve its
                # stream ids. Separate POST bodies each use a0, so map those
                # to their assigned A/B branch instead.
                preserve_streams = len(self._battle_request_ids) == 1
                for item in fallback_events:
                    if item.get("kind") != "text":
                        continue
                    item = dict(item)
                    if not preserve_streams:
                        item["stream"] = branch
                    self._apply_event(item)
            elif req_id not in self._battle_streamed:
                self._log("Battle: вариант %s не получил тело ответа" % req_id)
            else:
                self._parse_battle_stream_locked(req_id)
                tail = bytes(self._battle_stream_bufs.get(req_id) or b"")
                for item in self._decode_final_tail(tail):
                    if item.get("kind") == "text":
                        item = dict(item)
                        item["stream"] = branch
                        self._apply_event(item)
            self._battle_completed.add(req_id)
        # Arena can start B only after A has already completed. Wait briefly
        # for that second POST instead of finalizing a one-branch Battle.
        time.sleep(1.5)
        with self._lock:
            nonempty = [stream for stream in self._branch_order
                        if self._branch_texts.get(stream, "").strip()]
            # Arena uses both forms in production: two POST bodies (each a0),
            # or one body containing a0 and a1.
            if len(nonempty) < 2:
                self._log("Battle: прочитан только %d из 2 непустых вариантов — продолжаю ждать"
                          % len(nonempty))
                return
            if (not self._battle_request_ids
                    or not set(self._battle_request_ids).issubset(self._battle_completed)):
                return
            self._finish_collected_answer_locked("stop")
            self._log("Battle: собраны варианты A/B из %d отдельных POST"
                      % len(self._battle_request_ids))

    def _reset_answer_state_locked(self):
        self._answer_text = ""
        self._finished = False
        self._finish_reason = None
        self._counted_message = False
        self._branch_texts = {}
        self._branch_order = []
        self._selected_stream = None

    def _decode_frames_partial(self, raw_bytes):
        return decode_arena_stream_partial(raw_bytes)

    def _decode_frames(self, raw_bytes):
        return decode_arena_stream_lines(raw_bytes.decode("utf-8", "replace"))

    def _decode_final_tail(self, raw_bytes):
        return self._decode_frames(raw_bytes)

    def _answer_len_locked(self):
        return len(self._answer_text)

    def _apply_event(self, obj):
        kind = obj.get("kind")
        if kind == "text":
            stream = obj.get("stream")
            text = obj.get("text")
            if text:
                if stream not in self._branch_texts:
                    self._branch_texts[stream] = ""
                    self._branch_order.append(stream)
                    if len(self._branch_order) == 2:
                        self._log("получены два варианта Arena — выбираю лучший "
                                  "по целостности протокола агента")
                self._branch_texts[stream] += text
                # Live progress remains deterministic before final selection.
                primary = self._selected_stream
                if primary is None:
                    primary = self._branch_order[0]
                self._answer_text = self._branch_texts.get(primary, "")
                if not self._counted_message:
                    self._counted_message = True
                    self._assistant_message_count += 1
            return
        if kind == "done":
            reason = str((obj.get("meta") or {}).get("finishReason") or "")
            self._finish_collected_answer_locked(reason)

    def _finish_collected_answer_locked(self, reason):
        self._finish_reason = reason
        best = select_best_answer_variant([
            (stream, self._branch_texts.get(stream, ""))
            for stream in self._branch_order
        ])
        if best is not None:
            self._selected_stream = best[0]
            self._answer_text = best[1]
            if len(self._branch_order) > 1:
                self._log("выбран вариант %s (score=%s)"
                          % ("A" if best[0] == 0 else "B", best[2]))
        self._finished = True
        self._generating = False
        self._message_status = "FINISHED" if reason == "stop" else (
            "FINISHED_%s" % (reason.upper() or "UNKNOWN"))

    def current_text(self):
        with self._lock:
            return self._answer_text

    def is_finished(self):
        with self._lock:
            return self._finished

    def finish_reason(self):
        with self._lock:
            return self._finish_reason

    def branch_count(self):
        with self._lock:
            return len(self._branch_order)

    def selected_stream(self):
        with self._lock:
            return self._selected_stream

    def branch_variants(self):
        with self._lock:
            return [(stream, self._branch_texts.get(stream, ""))
                    for stream in self._branch_order]

    def select_stream(self, stream):
        with self._lock:
            if stream not in self._branch_texts:
                return False
            self._selected_stream = stream
            self._answer_text = self._branch_texts[stream]
            return True


class ArenaParser(BaseSiteParser):
    LOG_TAG = "arena_parser"
    WINDOW_URL_MATCH = "arena.ai"
    NEEDS_VISIBILITY_SPOOF = False
    ALLOW_MIRROR_JS_FALLBACK = False
    PASTE_PLAN_A = True
    START_PHASE = "модель думает..."
    QUIET_PERIOD = 4.0
    POLL_INTERVAL = 0.3
    SEND_RETRIES = 0
    REGENERATE_RETRIES = 0

    _monitor = None
    _monitor_lock = threading.Lock()
    _monitor_next_retry = 0.0
    _req_count_before_send = None
    _choice_applied_for_request = None
    _skip_origin_request = None
    _skip_pending = False

    def __init__(self):
        super().__init__()
        # Arena changes /text to /c/<id> after the first message.
        self._battle_mode_for_session = None

    @staticmethod
    def _arena_targets():
        targets = {}
        try:
            for target in list_targets():
                if target.get("type") != "page":
                    continue
                url = target.get("url") or ""
                try:
                    host = (urlparse(url).hostname or "").lower()
                except Exception:
                    host = ""
                if host == "arena.ai" or host.endswith(".arena.ai"):
                    targets[str(target.get("id") or "").lower()] = target
        except Exception:
            pass
        return targets

    def _connect_monitor(self, target_id, old=None):
        ws_url = find_page_ws_url_for_target(target_id)
        if not ws_url:
            raise Exception("arena.ai target not found: %s" % target_id)
        cdp = CDPSession(ws_url)
        monitor = ArenaChatMonitor(cdp)
        monitor._arena_target_id = target_id
        if old is not None:
            monitor._assistant_message_count = old.assistant_message_count()
            monitor._chat_request_count = old.chat_request_count()
            monitor._battle_capture = old._battle_capture
            monitor._battle_before_count = old._battle_before_count
            monitor._battle_request_ids = list(old._battle_request_ids)
            monitor._battle_request_branches = dict(old._battle_request_branches)
            monitor._battle_completed = set(old._battle_completed)
            monitor._battle_stream_bufs = dict(old._battle_stream_bufs)
            monitor._battle_stream_ready = dict(old._battle_stream_ready)
            monitor._battle_streamed = set(old._battle_streamed)
        cdp.send_command("Network.enable")
        ArenaParser._monitor = monitor
        return monitor

    def _ensure_monitor(self, driver=None):
        with ArenaParser._monitor_lock:
            old = ArenaParser._monitor
            target_id = getattr(driver, "current_window_handle", None)
            try:
                if (old is not None and old._cdp.is_alive()
                        and getattr(old, "_arena_target_id", None) == target_id):
                    return old
            except Exception:
                pass
            if old is not None:
                try:
                    old._cdp.close()
                except Exception:
                    pass
                ArenaParser._monitor = None
            now = time.time()
            if now < ArenaParser._monitor_next_retry:
                return None
            try:
                return self._connect_monitor(target_id, old=old)
            except Exception as e:
                ArenaParser._monitor_next_retry = now + 30.0
                self._log("сетевой монитор недоступен: %s" % e)
                return None

    def _follow_first_chat_transition(self, driver, previous_target_ids,
                                      before_count):
        """Keep network capture attached while /text/direct becomes /c/<id>."""
        deadline = time.time() + 5.0
        reenabled = False
        while time.time() < deadline:
            mon = ArenaParser._monitor
            if mon is not None and mon.chat_request_count() > before_count:
                return
            targets = self._arena_targets()
            new_ids = [target_id for target_id in targets
                       if target_id not in previous_target_ids]
            if new_ids:
                # A newly created page target is the first-chat target. Attach
                # before its fast response completes; do not wait for Selenium.
                target_id = new_ids[0]
                with ArenaParser._monitor_lock:
                    old = ArenaParser._monitor
                    try:
                        new_monitor = self._connect_monitor(target_id, old=old)
                        ArenaParser._monitor = new_monitor
                        handles = {str(handle).lower(): handle
                                   for handle in driver.window_handles}
                        new_handle = handles.get(target_id)
                        if (new_handle is not None
                                and new_handle != driver.current_window_handle):
                            driver.switch_to.window(new_handle)
                        if old is not None:
                            try:
                                old._cdp.close()
                            except Exception:
                                pass
                        self._log("первый чат сменил CDP target — монитор перенесён на /c/<id>")
                    except Exception as e:
                        self._log("не удалось перенести монитор на target первого чата: %s" % e)
                return
            # Some Chrome builds keep the target id but reset Network state on
            # the first client-side route transition. Re-enable once after /c/.
            if not reenabled and mon is not None:
                target = targets.get(str(getattr(mon, "_arena_target_id", "")).lower())
                try:
                    path = urlparse((target or {}).get("url") or "").path
                except Exception:
                    path = ""
                if path.startswith("/c/"):
                    try:
                        mon._cdp.send_command("Network.enable", timeout=3.0)
                        reenabled = True
                    except Exception:
                        pass
            time.sleep(0.05)

    def _fresh_network_text(self):
        mon = ArenaParser._monitor
        if mon is None:
            return None
        try:
            if not mon._cdp.is_alive():
                return None
            before = ArenaParser._req_count_before_send
            if before is not None and mon.answer_request_count() <= before:
                return None
            if (ArenaParser._skip_pending
                    and mon.answer_request_count() == ArenaParser._skip_origin_request):
                return None
            return mon.current_text() or ""
        except Exception:
            return None

    def count_answers(self, driver):
        mon = self._ensure_monitor(driver)
        return mon.assistant_message_count() if mon is not None else 0

    def answer_len(self, driver):
        return len(self._fresh_network_text() or "")

    def answer_preview(self, driver):
        return (self._fresh_network_text() or "")[-160:]

    def answer_stream(self, driver):
        text = self._fresh_network_text() or ""
        mon = ArenaParser._monitor
        # One branch may print DONE while the competing branch is still being
        # streamed. Do not let BaseSiteParser stop before the final `ad` frame
        # selects the best complete variant.
        if (mon is not None and (not mon.is_finished()
                                 or mon.battle_waiting_for_second_branch())):
            return text.replace(DONE_MARKER, "")
        return text

    def is_generating(self, driver):
        mon = self._ensure_monitor(driver)
        return mon.is_generating() if mon is not None else False

    def net_answer_ready(self, driver):
        mon = ArenaParser._monitor
        if mon is None:
            return False
        try:
            before = ArenaParser._req_count_before_send
            return bool(mon._cdp.is_alive()
                        and not mon.battle_waiting_for_second_branch()
                        and (before is None or mon.answer_request_count() > before)
                        and not (ArenaParser._skip_pending
                                 and mon.answer_request_count()
                                 == ArenaParser._skip_origin_request)
                        and mon.is_finished())
        except Exception:
            return False

    def extract_answer(self, driver):
        mon = self._ensure_monitor(driver)
        if mon is None:
            return {"text": "", "actionRaw": None,
                    "error": "Сетевой монитор Arena недоступен; DOM-чтение отключено."}
        text = self._fresh_network_text()
        if text is None:
            return {"text": "", "actionRaw": None,
                    "error": "Свежий сетевой ответ Arena ещё не получен."}
        if mon.battle_waiting_for_second_branch():
            return {"text": "", "actionRaw": None,
                    "error": "Arena Battle: ожидаю второй вариант."}
        selection = self._judge_and_apply_choice(driver, mon)
        if selection == "skip":
            return {"text": "", "actionRaw": None,
                    "error": "Оба варианта Arena отклонены судьёй; ожидаю третий ответ."}
        if selection.startswith("reject:"):
            reason = selection.split(":", 1)[1].strip()
            return {"text": "[Ошибка]: все три варианта Arena отклонены "
                            "локальным Godot Judge. " + reason,
                    "actionRaw": None, "error": None}
        text = mon.current_text() or text
        prose, action_raw = split_net_text_and_action(text)
        return {"text": prose, "actionRaw": action_raw, "error": None}

    def _project_judgments(self, mon):
        if mon.branch_count() < 2:
            return None
        try:
            import server_state
            project_root = server_state.STATE.get("project_root")
            addon_dir = server_state.STATE.get("addon_dir")
        except Exception as e:
            self._log("Godot Judge недоступен: %s" % e)
            return None
        if not project_root:
            return None
        variants = mon.branch_variants()
        try:
            return select_best_project_answer(project_root, variants,
                                              addon_dir=addon_dir)
        except Exception as e:
            self._log("Godot Judge не смог оценить варианты: %s" % e)
            return None

    def _judge_and_apply_choice(self, driver, mon):
        request_no = mon.answer_request_count()
        self._log("режим голосования: %s, вариантов: %d" %
                  ("Battle" if self._is_battle_mode() else "Direct", mon.branch_count()))
        if ArenaParser._skip_pending:
            # This is the single third response generated by Skip. There is no
            # A/B continuation choice; return it if acceptable, otherwise fail
            # closed and let the user decide what to do next.
            if request_no != ArenaParser._skip_origin_request:
                ArenaParser._skip_pending = False
                result = self._judge_single_current_answer(mon)
                if result is not None and not result.get("acceptable"):
                    reasons = [item.get("message") for item in result.get("blocking", [])]
                    return "reject: " + "; ".join(reasons[:3])
            return "third"

        # Battle can render an empty second card while its network branch is
        # missing. Still close the Battle vote instead of using Direct buttons.
        if self._is_battle_mode() and mon.branch_count() < 2:
            result = self._judge_single_current_answer(mon)
            if result is not None and result.get("acceptable"):
                if self._click_choice_button(driver, "A"):
                    ArenaParser._choice_applied_for_request = request_no
                    self._log("неполный Battle: вариант A пригоден — выбрано «A лучше»")
                    return "choice"
            elif self._click_choice_button(driver, "both_bad"):
                ArenaParser._choice_applied_for_request = request_no
                self._log("неполный Battle: пригодных вариантов нет — выбрано «Оба плохие»")
                return "reject: неполный или непригодный Battle-ответ"
            return "choice_failed"

        judged = self._project_judgments(mon)
        if judged is not None:
            key, text, result, all_results = judged
            for branch, branch_result in all_results:
                self._log("Godot Judge %s: score=%d acceptable=%s blockers=%d warnings=%d"
                          % ("A" if branch == 0 else "B", branch_result["score"],
                             branch_result["acceptable"],
                             len(branch_result["blocking"]),
                             len(branch_result["warnings"])))
                details = ([item.get("message") for item in branch_result["blocking"]]
                           + [item.get("message") for item in branch_result["warnings"]]
                           + list(branch_result.get("evidence") or []))
                if details:
                    self._log("Godot Judge %s: %s"
                              % ("A" if branch == 0 else "B",
                                 " | ".join(str(item) for item in details[:3])))
            acceptable = [(branch, branch_result) for branch, branch_result in all_results
                          if branch_result.get("acceptable")]
            if self._is_battle_mode():
                if len(acceptable) == 2:
                    mon.select_stream(key)
                    if self._click_choice_button(driver, "both_good"):
                        ArenaParser._choice_applied_for_request = request_no
                        self._log("оба ответа пригодны — выбрано «Оба хорошие»")
                        return "choice"
                elif len(acceptable) == 1:
                    branch = acceptable[0][0]
                    mon.select_stream(branch)
                    if self._click_choice_button(driver, "A" if branch == 0 else "B"):
                        ArenaParser._choice_applied_for_request = request_no
                        self._log("Arena продолжит диалог с вариантом %s" % ("A" if branch == 0 else "B"))
                        return "choice"
                else:
                    if self._click_choice_button(driver, "both_bad"):
                        ArenaParser._choice_applied_for_request = request_no
                        reasons = []
                        for _, branch_result in all_results:
                            reasons.extend(item.get("message") for item in branch_result.get("blocking", []))
                        self._log("оба ответа непригодны — выбрано «Оба плохие»")
                        return "reject: " + "; ".join(str(reason) for reason in reasons[:3] if reason)
                self._log("не найдена нужная Battle-кнопка голосования")
            elif not acceptable:
                if self._click_choice_button(driver, "skip"):
                    ArenaParser._skip_origin_request = request_no
                    ArenaParser._skip_pending = True
                    ArenaParser._req_count_before_send = mon.chat_request_count()
                    self._log("оба ответа непригодны — запрошен третий вариант через Skip")
                    return "skip"
                self._log("оба ответа непригодны, но кнопка Skip не найдена")
            else:
                mon.select_stream(key)
                return "choice" if self._apply_selected_choice(driver, mon) else "choice_failed"
        return "choice" if self._apply_selected_choice(driver, mon) else "choice_failed"

    def _is_battle_mode(self):
        """The site id is the source of truth after /text becomes /c/<id>."""
        try:
            import server_state
            site_id = server_state.STATE.get("current_site_id")
            if site_id in ("arena", "arena_battle"):
                return site_id == "arena_battle"
            rec = server_state.get_current_chat()
            if rec and rec.get("site_id") in ("arena", "arena_battle"):
                return rec.get("site_id") == "arena_battle"
        except Exception:
            pass
        return bool(self._battle_mode_for_session)

    def _judge_single_current_answer(self, mon):
        try:
            import server_state
            root = server_state.STATE.get("project_root")
            if not root:
                return None
            result = judge_answer(root, mon.current_text(),
                                  addon_dir=server_state.STATE.get("addon_dir"))
            self._log("Godot Judge C: score=%d acceptable=%s"
                      % (result["score"], result["acceptable"]))
            return result
        except Exception as e:
            self._log("Godot Judge C недоступен: %s" % e)
            return None

    def _click_choice_button(self, driver, choice):
        labels = {
            "A": ("Продолжить с A", "Continue with A", "A лучше"),
            "B": ("Продолжить с B", "Continue with B", "B лучше"),
            "skip": ("Пропустить", "Skip"),
            "both_good": ("Оба хорошие", "Both are good", "Both good"),
            "both_bad": ("Оба плохие", "Both are bad", "Both bad"),
        }.get(choice, ())
        deadline = time.time() + 8.0
        while time.time() < deadline:
            try:
                buttons = driver.find_elements(By.TAG_NAME, "button")
            except Exception:
                buttons = []
            for button in buttons:
                try:
                    if ((button.text or "").strip() in labels
                            and button.is_displayed() and button.is_enabled()):
                        button.click()
                        return True
                except Exception:
                    continue
            time.sleep(0.2)
        return False

    def _apply_selected_choice(self, driver, mon):
        """Continue the conversation with the structurally best A/B branch."""
        if mon.branch_count() < 2:
            return True
        request_no = mon.answer_request_count()
        if ArenaParser._choice_applied_for_request == request_no:
            return True
        stream = mon.selected_stream()
        label = "A" if stream == 0 else "B"
        if self._click_choice_button(driver, label):
            ArenaParser._choice_applied_for_request = request_no
            self._log("Arena продолжит диалог с вариантом %s" % label)
            return True
        self._log("не найдена кнопка продолжения с вариантом %s; ответ возвращён, "
                  "но следующий запрос может потребовать ручного выбора" % label)
        return False

    def extract_answer_snapshot(self, driver):
        mon = ArenaParser._monitor
        text = mon.current_text() if mon is not None else ""
        prose, action_raw = split_net_text_and_action(text or "")
        return {"text": prose, "actionRaw": action_raw, "error": None}

    def extract_raw_fallback(self, driver):
        text = self._fresh_network_text()
        if not text:
            return None
        prose, action_raw = split_net_text_and_action(text)
        return {"text": prose, "actionRaw": action_raw}

    def find_input(self, driver):
        return driver.execute_script(
            "return document.querySelector('textarea[name=\"message\"]');")

    def switch_to_site_window(self, driver, prefer_url=None):
        """Select the Arena tab with at most one visible window switch.

        Selenium can only read another tab's URL after switching to it. Doing
        that on every live-input update made unrelated test tabs flash on
        screen. The CDP target list already contains each handle and URL, so we
        choose the target there and switch only once to the final handle.
        """
        def _is_arena(url):
            try:
                host = (urlparse(url or "").hostname or "").lower()
            except Exception:
                return False
            return host == "arena.ai" or host.endswith(".arena.ai")

        def _normalized(url):
            try:
                parsed = urlparse(url or "")
                return (parsed.hostname or "").lower(), parsed.path.rstrip("/")
            except Exception:
                return "", ""

        handles = list(driver.window_handles)
        handle_by_id = {str(handle).lower(): handle for handle in handles}
        try:
            current_handle = driver.current_window_handle
        except Exception:
            current_handle = None

        target_urls = {}
        try:
            for target in list_targets():
                if target.get("type") != "page":
                    continue
                handle = handle_by_id.get(str(target.get("id") or "").lower())
                if handle is not None:
                    target_urls[handle] = target.get("url") or ""
        except Exception as e:
            self._log("не удалось прочитать CDP targets без переключения вкладок: %s" % e)

        wanted = (_normalized(prefer_url) if prefer_url and _is_arena(prefer_url)
                  else None)
        chosen = None
        if wanted:
            for handle, url in target_urls.items():
                if _is_arena(url) and _normalized(url) == wanted:
                    chosen = handle
                    break
        if chosen is None and current_handle in target_urls:
            if _is_arena(target_urls[current_handle]):
                chosen = current_handle
        if chosen is None:
            for handle, url in target_urls.items():
                if _is_arena(url):
                    chosen = handle
                    break

        # If CDP enumeration failed, keeping an already active Arena tab is
        # safe; never probe every Selenium handle because that causes flashing.
        if chosen is None and _is_arena(getattr(driver, "current_url", "")):
            chosen = current_handle
        if chosen is None:
            raise Exception("Вкладка arena.ai не найдена.")
        if chosen != current_handle:
            driver.switch_to.window(chosen)

    @staticmethod
    def _windows_clipboard_write(text):
        if not sys.platform.startswith("win"):
            return False
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        data = (text or "").encode("utf-16-le") + b"\x00\x00"
        if not user32.OpenClipboard(None):
            return False
        handle = None
        try:
            if not user32.EmptyClipboard():
                return False
            handle = kernel32.GlobalAlloc(0x0002, len(data))
            if not handle:
                return False
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return False
            try:
                ctypes.memmove(ptr, data, len(data))
            finally:
                kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(13, handle):
                return False
            handle = None
            return True
        finally:
            if handle:
                kernel32.GlobalFree(handle)
            user32.CloseClipboard()

    @staticmethod
    def _windows_clipboard_read():
        if not sys.platform.startswith("win"):
            return None
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        if not user32.OpenClipboard(None):
            return None
        try:
            handle = user32.GetClipboardData(13)
            if not handle:
                return None
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    def _set_clipboard_text(self, driver, text):
        for _ in range(5):
            if self._windows_clipboard_write(text):
                return True
            time.sleep(0.05)
        return False

    def _verify_clipboard_text(self, driver, text):
        got = self._windows_clipboard_read()
        return False if got is None else self._insert_text_matches(got, text)

    def _clear_input_trusted(self, driver, el):
        """Clear the composer through the browser keyboard pipeline only."""
        if not self._read_field_text_quick(driver, el):
            return True
        for _ in range(3):
            try:
                el.click()
            except Exception:
                pass
            cleared = False
            if hasattr(driver, "execute_cdp_cmd"):
                try:
                    ctrl_a = {
                        "type": "keyDown", "modifiers": 2, "key": "a",
                        "code": "KeyA", "windowsVirtualKeyCode": 65,
                        "nativeVirtualKeyCode": 65,
                        "commands": ["SelectAll"],
                    }
                    driver.execute_cdp_cmd("Input.dispatchKeyEvent", ctrl_a)
                    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {
                        "type": "keyUp", "modifiers": 2, "key": "a",
                        "code": "KeyA", "windowsVirtualKeyCode": 65,
                        "nativeVirtualKeyCode": 65,
                    })
                    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {
                        "type": "keyDown", "key": "Backspace",
                        "code": "Backspace", "windowsVirtualKeyCode": 8,
                        "nativeVirtualKeyCode": 8,
                    })
                    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {
                        "type": "keyUp", "key": "Backspace",
                        "code": "Backspace", "windowsVirtualKeyCode": 8,
                        "nativeVirtualKeyCode": 8,
                    })
                    cleared = True
                except Exception as e:
                    self._log("CDP-очистка поля не удалась: %s" % e)
            if not cleared:
                try:
                    # Concatenated chord keeps Control pressed while A is sent.
                    el.send_keys(Keys.CONTROL + "a")
                    el.send_keys(Keys.BACKSPACE)
                except Exception:
                    pass
            deadline = time.time() + 1.5
            while time.time() < deadline:
                if not self._read_field_text_quick(driver, el):
                    return True
                time.sleep(0.1)
        return False

    def insert_input_paste_like(self, driver, el, prompt):
        """Strict Arena paste: no JS value assignment and no DOM clipboard helper."""
        prompt = "" if prompt is None else str(prompt)
        old_clipboard = self._windows_clipboard_read()
        try:
            for _ in range(2):
                if not self._clear_input_trusted(driver, el):
                    continue
                if not self._set_clipboard_text(driver, prompt):
                    continue
                if not self._verify_clipboard_text(driver, prompt):
                    continue
                el.click()
                if not self._dispatch_ctrl_v(driver, el):
                    try:
                        el.send_keys(Keys.CONTROL, "v")
                    except Exception:
                        continue
                timeout = min(30.0, max(3.0, len(prompt) / 2000.0))
                if self._wait_field_matches(driver, el, prompt, timeout):
                    return True
            self._clear_input_trusted(driver, el)
            return False
        finally:
            if old_clipboard is not None:
                self._windows_clipboard_write(old_clipboard)

    def insert_input(self, driver, el, prompt):
        if not prompt:
            if not self._clear_input_trusted(driver, el):
                raise Exception("не удалось очистить поле доверенными клавишами")
            return
        if not self._clear_input_trusted(driver, el):
            raise Exception("не удалось очистить поле перед Ctrl+V")
        if not self._set_clipboard_text(driver, prompt):
            raise Exception("не удалось записать системный буфер обмена")
        el.click()
        if not self._dispatch_ctrl_v(driver, el):
            el.send_keys(Keys.CONTROL, "v")

    def submit(self, driver, el):
        mon = self._ensure_monitor(driver)
        if mon is None:
            raise Exception("сетевой монитор Arena недоступен; отправка отменена")
        ArenaParser._req_count_before_send = (
            mon.chat_request_count())
        # A new user message starts a fresh judging cycle. Automatic Skip does
        # not pass through submit(), so this cannot clear a live C request.
        ArenaParser._skip_pending = False
        ArenaParser._skip_origin_request = None
        target_ids = set(self._arena_targets())
        try:
            first_path = urlparse(driver.current_url or "").path.rstrip("/")
            first_chat = first_path in ("/text/direct", "/text")
            if first_chat:
                self._battle_mode_for_session = first_path == "/text"
                try:
                    import server_state
                    server_state.STATE["current_site_id"] = (
                        "arena_battle" if self._battle_mode_for_session else "arena")
                except Exception:
                    pass
        except Exception:
            first_chat = False
        if self._is_battle_mode():
            mon.begin_battle_capture(ArenaParser._req_count_before_send)
        else:
            mon.end_battle_capture()
        el.send_keys(Keys.ENTER)
        if first_chat:
            self._follow_first_chat_transition(
                driver, target_ids, ArenaParser._req_count_before_send)

    def confirm_sent(self, driver, el):
        """Confirm UI acceptance or the eventual Arena POST.

        Arena clears the composer before its reCAPTCHA/message-id pipeline
        emits post-to-evaluation. Large prompts can therefore be visibly sent
        while the network counter stays unchanged for more than ten seconds.
        An empty composer sustained for one second is enough to continue into
        the answer wait; SEND_RETRIES=0 guarantees this never creates a duplicate.
        """
        before = ArenaParser._req_count_before_send
        deadline = time.time() + 60.0
        empty_since = None
        while time.time() < deadline:
            mon = ArenaParser._monitor
            if (before is not None and mon is not None
                    and mon.chat_request_count() > before):
                return True
            try:
                empty = not (self._read_field_text_quick(driver, el) or "").strip()
            except Exception:
                empty = False
            if empty:
                if empty_since is None:
                    empty_since = time.time()
                elif time.time() - empty_since >= 1.0:
                    self._log("отправка подтверждена очисткой поля; сетевой POST "
                              "может появиться позже после reCAPTCHA")
                    return True
            else:
                empty_since = None
            time.sleep(0.2)
        return False

    def try_regenerate(self, driver):
        return False


PARSER = ArenaParser()


def send_message_and_get_response(driver, prompt, input_retries=3,
                                  progress_cb=None, cancel_cb=None,
                                  prefer_url=None):
    return PARSER.send_message_and_get_response(
        driver, prompt, input_retries=input_retries, progress_cb=progress_cb,
        cancel_cb=cancel_cb, prefer_url=prefer_url)
