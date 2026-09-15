"""Offline request-order and terminal-state regressions for BaseNetMonitor."""
import base64
import contextlib
import io
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _bootstrap  # noqa: E402,F401
from net_monitor import BaseNetMonitor


URL = "https://example.invalid/chat"


class FakeCDP:
    def __init__(self):
        self.handlers = {}
        self.calls = []
        self.stream_entered = threading.Event()
        self.stream_release = threading.Event()
        self.stream_error = None
        self.buffered = b""
        self.body = "answer\n"

    def on_event(self, name, callback):
        self.handlers[name] = callback

    def emit(self, name, **params):
        self.handlers["Network." + name](params)

    def send_command(self, method, params=None):
        self.calls.append((method, params["requestId"]))
        if method == "Network.streamResourceContent":
            self.stream_entered.set()
            if not self.stream_release.wait(2):
                raise AssertionError("test did not release stream setup")
            if self.stream_error:
                raise self.stream_error
            return {"bufferedData": base64.b64encode(self.buffered).decode("ascii")}
        if method == "Network.getResponseBody":
            return {"body": self.body}
        raise AssertionError(method)


class AppendMonitor(BaseNetMonitor):
    CHAT_URL_SUBSTR = "/chat"

    def __init__(self, cdp):
        self.logs = []
        self.partial_error = False
        self.tail_error = False
        self.accept_tail = False
        self.enable_done = threading.Event()
        self.finish_done = threading.Event()
        super().__init__(cdp)

    def _reset_answer_state_locked(self):
        self.text = ""

    def _decode_frames_partial(self, raw):
        if self.partial_error:
            raise ValueError("partial decode failed")
        consumed = raw.rfind(b"\n") + 1
        return raw[:consumed].decode("ascii").splitlines(), consumed

    def _decode_frames(self, raw):
        return raw.decode("ascii").splitlines()

    def _decode_final_tail(self, raw):
        if self.tail_error:
            raise ValueError("tail decode failed")
        return [raw.decode("ascii")] if self.accept_tail else []

    def _apply_event(self, obj):
        if obj == "RAISE":
            raise ValueError("event application failed")
        if obj == "DONE":
            self._message_status = "FINISHED"
            self._generating = False
            self._assistant_message_count += 1
        else:
            self.text += obj

    def current_text(self):
        with self._lock:
            return self.text

    def _log(self, message):
        self.logs.append(message)

    def _enable_stream(self, req_id):
        try:
            super()._enable_stream(req_id)
        finally:
            self.enable_done.set()

    def _finish_request(self, req_id):
        try:
            super()._finish_request(req_id)
        finally:
            self.finish_done.set()


class ObservedSetupEvent:
    """Observe the finish worker waiting without a wall-clock delay."""
    def __init__(self, event):
        self.event = event
        self.wait_entered = threading.Event()
        self.timeout = "not called"

    def wait(self, timeout=None):
        self.timeout = timeout
        self.wait_entered.set()
        # Reproduce the former 5s deadline immediately, not with a long sleep.
        if timeout is not None:
            return False
        return self.event.wait(2)

    def set(self):
        self.event.set()


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.cdp = FakeCDP()
        self.mon = AppendMonitor(self.cdp)
        self.addCleanup(self.cdp.stream_release.set)

    def post(self, req_id):
        self.cdp.emit("requestWillBeSent", requestId=req_id,
                      request={"url": URL, "method": "POST"})

    def response(self, req_id):
        self.cdp.emit("responseReceived", requestId=req_id,
                      response={"url": URL, "mimeType": "text/plain"})

    def start(self, req_id="r1", release=True):
        self.mon.enable_done.clear()
        self.cdp.stream_release.clear()
        self.cdp.stream_entered.clear()
        self.post(req_id)
        self.response(req_id)
        self.assertTrue(self.cdp.stream_entered.wait(2))
        event = self.mon._stream_done[req_id]
        if release:
            self.cdp.stream_release.set()
            self.assertTrue(event.wait(2))
            self.assertTrue(self.mon.enable_done.wait(2))
        return event

    def feed(self, raw, req_id="r1"):
        self.cdp.emit("dataReceived", requestId=req_id,
                      data=base64.b64encode(raw).decode("ascii"))

    def finish(self, req_id="r1"):
        self.mon.finish_done.clear()
        self.cdp.emit("loadingFinished", requestId=req_id)
        self.assertTrue(self.mon.finish_done.wait(2))

    def assert_clean(self):
        self.assertFalse(self.mon.is_generating())
        self.assertIsNone(self.mon._active_request_id)
        self.assertEqual(self.mon._request_counts, {})
        self.assertEqual(self.mon._stream_bufs, {})
        self.assertEqual(self.mon._stream_mode, {})
        self.assertEqual(self.mon._stream_done, {})

    def assert_no_body(self):
        self.assertFalse(any(method == "Network.getResponseBody"
                             for method, _ in self.cdp.calls))

    def test_unobserved_response_is_not_assigned_an_ordinal(self):
        self.response("unobserved")
        self.assertEqual(self.mon.answer_request_count(), 0)
        self.assertEqual(self.cdp.calls, [])
        self.assert_clean()

    def test_delayed_old_response_after_two_posts_is_ignored(self):
        self.post("old")
        self.post("new")
        self.response("old")
        self.assertEqual(self.mon.chat_request_count(), 2)
        self.assertEqual(self.mon.answer_request_count(), 0)
        self.assertIsNone(self.mon._active_request_id)
        self.assertEqual(self.cdp.calls, [])
        self.response("new")
        event = self.mon._stream_done["new"]
        self.cdp.stream_release.set()
        self.assertTrue(event.wait(2))
        self.assertEqual(self.mon.answer_request_count(), 2)
        self.finish("new")
        self.assert_clean()

    def test_reordered_responses_cannot_replace_new_answer(self):
        self.post("old")
        self.start("new")
        self.feed(b"new text\n", "new")
        self.response("old")
        self.cdp.emit("loadingFailed", requestId="old", errorText="old failure")
        self.cdp.emit("loadingFinished", requestId="old")
        self.assertEqual(self.mon.current_text(), "new text")
        self.assertEqual(self.mon.answer_request_count(), 2)
        self.assertEqual(self.mon._active_request_id, "new")
        self.finish("new")
        self.assert_clean()

    def test_previous_buffer_keeps_its_ordinal_until_new_response(self):
        self.start("old")
        self.feed(b"old text\n", "old")
        self.finish("old")
        self.post("new")
        self.response("old")
        self.assertEqual(self.mon.current_text(), "old text")
        self.assertEqual(self.mon.answer_request_count(), 1)
        self.assertEqual(self.mon.chat_request_count(), 2)
        self.cdp.emit("loadingFailed", requestId="new", errorText="no response")
        self.assert_clean()

    def test_request_identity_storage_is_bounded(self):
        for index in range(100):
            self.post(str(index))
        self.assertEqual(self.mon._request_counts, {"99": 100})
        self.cdp.emit("loadingFinished", requestId="99")
        self.assert_clean()

    def test_loading_failed_cleans_only_its_request_without_success(self):
        self.start()
        self.feed(b"partial\nunfinished")
        self.cdp.emit("loadingFailed", requestId="r1", errorText="net::ERR_ABORTED",
                      canceled=True)
        self.assert_clean()
        self.assertEqual(self.mon.current_text(), "partial")
        self.assertEqual(self.mon.message_status(), "FAILED")
        self.assertEqual(self.mon.assistant_message_count(), 0)
        self.assertTrue(any("net::ERR_ABORTED" in log for log in self.mon.logs))
        self.assertTrue(any("discarded stream tail=10 bytes" in log
                            for log in self.mon.logs))
        self.feed(b"late\n")
        self.mon._finish_request("r1")
        self.assert_no_body()
        self.assertEqual(self.mon.current_text(), "partial")

    def test_delayed_stream_setup_does_not_select_body_fallback(self):
        self.cdp.buffered = b"prefix\n"
        setup = self.start(release=False)
        observed = ObservedSetupEvent(setup)
        with self.mon._lock:
            self.mon._stream_done["r1"] = observed
        self.feed(b"suffix\nDONE\n")
        self.cdp.emit("loadingFinished", requestId="r1")
        self.assertTrue(observed.wait_entered.wait(2))
        self.assertIsNone(observed.timeout, "finish must wait for the CDP outcome")
        self.assert_no_body()
        self.cdp.stream_release.set()
        self.assertTrue(self.mon.finish_done.wait(2))
        self.assertEqual(self.mon.current_text(), "prefixsuffix")
        self.assertEqual(self.mon.assistant_message_count(), 1)
        self.assert_no_body()
        self.assert_clean()

    def test_failure_during_setup_releases_waiter_and_ignores_late_bytes(self):
        self.cdp.buffered = b"late\nDONE\n"
        setup = self.start(release=False)
        observed = ObservedSetupEvent(setup)
        with self.mon._lock:
            self.mon._stream_done["r1"] = observed
        self.cdp.emit("loadingFinished", requestId="r1")
        self.assertTrue(observed.wait_entered.wait(2))
        self.cdp.emit("loadingFailed", requestId="r1", errorText="connection reset")
        self.assertTrue(self.mon.finish_done.wait(2))
        self.cdp.stream_release.set()
        self.assertTrue(self.mon.enable_done.wait(2))
        self.assert_clean()
        self.assertEqual(self.mon.message_status(), "FAILED")
        self.assertEqual(self.mon.current_text(), "")
        self.assertEqual(self.mon.assistant_message_count(), 0)
        self.assert_no_body()

    def test_unsupported_stream_fallback_applies_append_only_body_once(self):
        self.cdp.stream_error = RuntimeError("method not supported")
        self.cdp.body = "answer\nDONE\n"
        setup = self.start(release=False)
        self.feed(b"answer\nDONE\n")
        self.cdp.stream_release.set()
        self.assertTrue(setup.wait(2))
        self.finish()
        self.mon._finish_request("r1")
        self.assertEqual(self.mon.current_text(), "answer")
        self.assertEqual(self.mon.assistant_message_count(), 1)
        self.assertEqual(self.cdp.calls.count(("Network.getResponseBody", "r1")), 1)
        self.assert_clean()

    def test_parse_exception_at_finalization_always_cleans_up(self):
        for stage in ("partial", "tail", "apply"):
            with self.subTest(stage=stage):
                self.cdp = FakeCDP()
                self.mon = AppendMonitor(self.cdp)
                self.addCleanup(self.cdp.stream_release.set)
                self.start()
                self.feed(b"RAISE" if stage == "apply" else b"tail")
                self.mon.partial_error = stage == "partial"
                self.mon.tail_error = stage == "tail"
                self.mon.accept_tail = stage == "apply"
                self.finish()
                self.assert_clean()
                self.assertEqual(self.mon.message_status(), "FAILED")
                self.assertEqual(self.mon.assistant_message_count(), 0)
                self.assertTrue(any("discarded stream tail=" in log
                                    for log in self.mon.logs))
                self.assert_no_body()

    def test_stream_setup_parse_failure_does_not_replay_partial_text(self):
        self.cdp.buffered = b"answer\nRAISE\n"
        self.cdp.body = "answer\nDONE\n"
        self.start()
        self.mon._finish_request("r1")
        self.assert_clean()
        self.assertEqual(self.mon.current_text(), "answer")
        self.assertEqual(self.mon.message_status(), "FAILED")
        self.assertEqual(self.mon.assistant_message_count(), 0)
        self.assert_no_body()

    def test_incremental_parse_exception_is_terminal(self):
        self.start()
        self.mon.partial_error = True
        self.feed(b"broken\n")
        self.assert_clean()
        self.assertEqual(self.mon.message_status(), "FAILED")
        self.assert_no_body()

    def test_fallback_parse_exception_cleans_resources_without_success(self):
        self.cdp.stream_error = RuntimeError("method not supported")
        self.cdp.body = "partial\nRAISE\nDONE\n"
        self.start()
        with contextlib.redirect_stderr(io.StringIO()):
            self.finish()
        self.assert_clean()
        self.assertEqual(self.mon.current_text(), "partial")
        self.assertEqual(self.mon.message_status(), "FAILED")
        self.assertEqual(self.mon.assistant_message_count(), 0)

    def test_unhandled_final_tail_is_logged_not_reported_consumed(self):
        self.start()
        self.feed(b"answer\ntail")
        self.finish()
        self.assert_clean()
        self.assertEqual(self.mon.current_text(), "answer")
        self.assertIsNone(self.mon.message_status())
        self.assertEqual(self.mon.assistant_message_count(), 0)
        self.assertTrue(any("discarded stream tail=4 bytes" in log
                            for log in self.mon.logs))

    def test_decoded_final_tail_is_applied_once_and_not_logged_discarded(self):
        self.start()
        self.mon.accept_tail = True
        self.feed(b"answer\nDONE")
        self.finish()
        self.mon._finish_request("r1")
        logs_before_failure = list(self.mon.logs)
        self.cdp.emit("loadingFailed", requestId="stale", errorText="late failure")
        self.assertEqual(self.mon.logs, logs_before_failure)
        self.assert_clean()
        self.assertEqual(self.mon.message_status(), "FINISHED")
        self.assertEqual(self.mon.assistant_message_count(), 1)
        self.assertFalse(any("discarded stream tail=" in log for log in self.mon.logs))
        self.assert_no_body()


if __name__ == "__main__":
    unittest.main(verbosity=2)
