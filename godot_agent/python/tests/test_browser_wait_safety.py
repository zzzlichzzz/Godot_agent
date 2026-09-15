"""Offline deadline and send-boundary regressions; run as a standalone suite."""

import types
import unittest
from unittest.mock import patch

# Reuse the Selenium/browser stubs without running the existing suite.
from test_v87_9_regen import _FakeDriver, _FakeRegenParser
import parser_base


class _Clock:
    def __init__(self):
        self.now = 0.0
        self.on_sleep = None

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.on_sleep is not None:
            self.on_sleep(seconds)


class _WaitParser(_FakeRegenParser):
    TIMEOUT = 8.0
    QUIET_PERIOD = 0.5
    HARD_QUIET_PERIOD = 0.5
    POLL_INTERVAL = 0.25
    POST_QUIET_GRACE = 1.0

    def __init__(self, answer, generating):
        super().__init__()
        self.answer = answer
        self.generating = generating
        self.n = 2
        self.reads = 0

    def extract_answer(self, driver):
        self.reads += 1
        return dict(self.answer())

    def answer_stream(self, driver):
        answer = self.answer()
        return (answer.get("text") or "") + (answer.get("actionRaw") or "")

    def answer_preview(self, driver):
        return self.answer_stream(driver)

    def answer_len(self, driver):
        return len(self.answer_stream(driver))

    def is_generating(self, driver):
        return self.generating()

    def net_answer_ready(self, driver):
        return False

    def _log(self, message):
        pass


class _SendParser(_FakeRegenParser):
    SEND_RETRIES = 1

    def __init__(self):
        super().__init__()
        self.find_calls = 0
        self.insert_calls = 0
        self.submit_calls = 0
        self.cancelled = False

    def find_input(self, driver):
        self.find_calls += 1
        return "composer"

    def insert_input_for_send(self, driver, el, prompt):
        self.insert_calls += 1
        driver.field_text = prompt
        return "insert"

    def submit(self, driver, el):
        self.submit_calls += 1

    def wait_for_new_answer(self, driver, initial_count, **kwargs):
        return {"text": "complete", "actionRaw": None}

    def _log(self, message):
        pass


class BrowserWaitSafetyTests(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        # Replace module attributes, not the process-wide time/random modules.
        time_patch = patch.object(parser_base, "time", self.clock)
        random_patch = patch.object(
            parser_base, "random", types.SimpleNamespace(uniform=lambda a, b: a))
        time_patch.start()
        random_patch.start()
        self.addCleanup(time_patch.stop)
        self.addCleanup(random_patch.stop)

    def wait(self, parser, **kwargs):
        return parser.wait_for_new_answer(
            _FakeDriver(), 1, baseline={"text": "old", "actionRaw": None}, **kwargs)

    def send(self, parser):
        return parser.send_message_and_get_response(
            _FakeDriver(), "prompt", cancel_cb=lambda: parser.cancelled)

    def test_perpetual_generation_never_returns_partial(self):
        for raw in (None, '{"action":"done"}', '{"action":'):
            with self.subTest(raw=raw):
                self.clock.now = 0.0
                parser = _WaitParser(
                    lambda: {"text": "partial", "actionRaw": raw}, lambda: True)
                with self.assertRaises(TimeoutError):
                    self.wait(parser, timeout=100.0)
                self.assertGreater(parser.reads, 1)  # Entered verification.
                self.assertGreaterEqual(self.clock.now, 100.0)
                self.assertLess(self.clock.now, 100.4)

    def test_done_marker_does_not_override_generation(self):
        parser = _WaitParser(lambda: {"text": "partial ===DONE==="}, lambda: True)
        with self.assertRaises(TimeoutError):
            self.wait(parser)
        self.assertLess(self.clock.now, parser.TIMEOUT + 0.4)

    def test_generation_can_finish_before_deadline(self):
        parser = _WaitParser(lambda: {"text": "complete"}, lambda: self.clock.now < 3.0)
        self.assertEqual(self.wait(parser)["text"], "complete")
        self.assertGreaterEqual(self.clock.now, 3.0)
        self.assertLess(self.clock.now, parser.TIMEOUT)

    def test_stopped_malformed_json_returns_after_grace_for_selfheal(self):
        answer = {"text": "stopped", "actionRaw": '{"action":'}
        parser = _WaitParser(lambda: answer, lambda: False)
        self.assertEqual(self.wait(parser), answer)
        self.assertGreaterEqual(self.clock.now, 0.75 + parser.POST_QUIET_GRACE)
        self.assertLess(self.clock.now, parser.TIMEOUT)

    def test_deadline_takes_precedence_over_malformed_grace(self):
        parser = _WaitParser(lambda: {"actionRaw": '{"action":'}, lambda: False)
        with self.assertRaises(TimeoutError):
            self.wait(parser, timeout=1.0, post_quiet_grace=10.0)
        self.assertLess(self.clock.now, 1.4)

    def test_anti_stale_changed_but_generating_times_out(self):
        for raw in (None, '{"action":"done"}', '{"action":'):
            with self.subTest(raw=raw):
                self.clock.now = 0.0
                parser = _WaitParser(
                    lambda: ({"text": "old"} if self.clock.now < 2.0 else
                             {"text": "partial", "actionRaw": raw}),
                    lambda: self.clock.now >= 2.0)
                parser.n = 0  # DOM count shrank: enter stabilization, then anti-stale.
                with self.assertRaises(TimeoutError):
                    self.wait(parser)
                self.assertGreaterEqual(self.clock.now, parser.TIMEOUT)
                self.assertLess(self.clock.now, parser.TIMEOUT + parser.POLL_INTERVAL)

    def test_anti_stale_changed_answer_is_verified(self):
        def answer():
            if self.clock.now < 2.0:
                return {"text": "old"}
            if self.clock.now < 3.5:
                return {"text": "new", "actionRaw": '{"action":'}
            return {"text": "new", "actionRaw": '{"action":"done"}'}

        parser = _WaitParser(answer, lambda: False)
        parser.n = 0
        result = self.wait(parser, post_quiet_grace=2.0)
        self.assertEqual(result["actionRaw"], '{"action":"done"}')
        self.assertGreaterEqual(self.clock.now, 3.5)

    def test_busy_timeout_never_touches_composer(self):
        parser = _SendParser()
        parser.is_generating = lambda driver: True
        with self.assertRaises(TimeoutError):
            self.send(parser)
        self.assertEqual(self.clock.now, 240.0)
        self.assertEqual((parser.find_calls, parser.insert_calls, parser.submit_calls), (0, 0, 0))
        self.assertEqual(parser.regen_clicks, 0)

    def test_generation_check_failure_is_not_idle(self):
        parser = _SendParser()
        failure = RuntimeError("generation state unavailable")

        def fail(driver):
            raise failure

        parser.is_generating = fail
        with self.assertRaises(RuntimeError) as caught:
            self.send(parser)
        self.assertIs(caught.exception, failure)
        self.assertEqual((parser.find_calls, parser.insert_calls, parser.submit_calls), (0, 0, 0))

    def test_idle_control_submits_once(self):
        parser = _SendParser()
        self.assertEqual(self.send(parser), {"text": "complete", "action": None})
        self.assertEqual((parser.insert_calls, parser.submit_calls), (1, 1))

    def test_busy_then_idle_can_submit(self):
        parser = _SendParser()
        parser.is_generating = lambda driver: self.clock.now < 2.0
        self.assertEqual(self.send(parser)["text"], "complete")
        self.assertEqual(parser.submit_calls, 1)
        self.assertGreaterEqual(self.clock.now, 3.5)

    def test_cancellation_during_input_or_presubmit_blocks_send(self):
        for stage in ("input", "before_submit", "snapshot"):
            with self.subTest(stage=stage):
                parser = _SendParser()

                def cancel(*args):
                    parser.cancelled = True

                if stage == "input":
                    self.clock.on_sleep = cancel
                elif stage == "before_submit":
                    parser.before_submit = cancel
                else:
                    parser.extract_answer_snapshot = cancel
                try:
                    with self.assertRaises(parser_base.ParserCancelled):
                        self.send(parser)
                finally:
                    self.clock.on_sleep = None
                self.assertEqual(parser.insert_calls, 1)
                self.assertEqual(parser.submit_calls, 0)

    def test_cancellation_blocks_stale_submit_retry(self):
        parser = _SendParser()

        def stale(driver, el):
            parser.submit_calls += 1
            parser.cancelled = True
            raise parser_base.StaleElementReferenceException("replaced")

        parser.submit = stale
        with self.assertRaises(parser_base.ParserCancelled):
            self.send(parser)
        self.assertEqual(parser.submit_calls, 1)

    def test_cancellation_during_retry_pause_blocks_resubmit(self):
        parser = _SendParser()
        parser.confirm_sent = lambda driver, el: False

        def cancel_after_submit(seconds):
            if parser.submit_calls:
                parser.cancelled = True

        self.clock.on_sleep = cancel_after_submit
        with self.assertRaises(parser_base.ParserCancelled):
            self.send(parser)
        self.assertEqual(parser.submit_calls, 1)

    def test_cancellation_blocks_timeout_and_empty_regeneration(self):
        for reason in ("timeout", "empty"):
            with self.subTest(reason=reason):
                parser = _SendParser()

                def wait(driver, initial_count, **kwargs):
                    parser.cancelled = True
                    if reason == "timeout":
                        raise TimeoutError("no answer")
                    return {"text": "", "actionRaw": None}

                parser.wait_for_new_answer = wait
                parser.extract_answer_robust = lambda driver: {"text": "", "actionRaw": None}
                with self.assertRaises(parser_base.ParserCancelled):
                    self.send(parser)
                self.assertEqual(parser.submit_calls, 1)
                self.assertEqual(parser.regen_clicks, 0)


if __name__ == "__main__":
    unittest.main()
