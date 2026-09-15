"""Offline full-pipeline regressions for late insertion and send acceptance."""

import types
import unittest
from unittest.mock import patch

from test_browser_wait_safety import _Clock
from test_v87_9_regen import _FakeDriver, _FakeRegenParser
import parser_base


class _AcceptanceParser(_FakeRegenParser):
    SEND_RETRIES = 1
    REGENERATE_RETRIES = 0
    NEEDS_VISIBILITY_SPOOF = False
    ATTACHMENT_NOTE = "Read the attached prompt."

    def __init__(self, clock, driver, acceptance="submit", clear=False,
                 attachment=False):
        super().__init__()
        self.clock = clock
        self.driver = driver
        self.acceptance = acceptance
        self.clear = clear
        self.attachment = attachment
        self.text = "old answer"
        self.insert_calls = 0
        self.submit_calls = 0
        self.after_calls = 0
        self.note_calls = 0
        self.attachments = 0
        self.pending_attachment = False
        self.preparing = False
        self.requests = 0
        self.request_baseline = None
        self.snapshots = []
        self.waits = []
        self.confirmations = []
        self.cancel_stage = None
        self.cancelled = False
        clock.on_sleep = self.on_sleep

    def on_sleep(self, seconds):
        # Conversion happens after the insertion helper returns, without its flag.
        if self.pending_attachment:
            self.pending_attachment = False
            self.attachments += 1
            self.driver.field_text = ""
        if self.submit_calls == 1:
            stage = "preparation" if self.preparing else "delay"
            if self.acceptance == stage and not self.requests:
                self.accept()
            if self.cancel_stage == stage:
                self.cancelled = True

    def accept(self):
        self.requests += 1
        self.n += 1
        self.text = "complete"
        if self.clear:
            self.driver.field_text = ""

    def find_input(self, driver):
        return self

    def insert_input_for_send(self, driver, el, prompt):
        self.insert_input(driver, el, prompt)
        return "insert"

    def insert_input(self, driver, el, prompt):
        self.insert_calls += 1
        driver.field_text = prompt
        self.pending_attachment = self.attachment

    def count_composer_attachments(self, driver):
        return self.attachments

    def send_keys(self, text):
        # Exercise the real attachment-note helper without browser input.
        self.note_calls += 1
        self.driver.field_text += text

    def _focus_input_caret_end(self, driver, el):
        pass

    def before_submit(self, driver, el):
        self.preparing = True
        self.clock.sleep(0.4)
        self.preparing = False
        if self.cancel_stage == "initial" and not self.submit_calls:
            self.cancelled = True

    def submit(self, driver, el):
        self.submit_calls += 1
        # Like site parsers, a second submit would overwrite request freshness.
        self.request_baseline = self.requests
        if self.acceptance == "submit" or (
                self.acceptance == "retry" and self.submit_calls == 2):
            self.accept()

    def after_submit(self, driver, el):
        self.after_calls += 1

    def confirm_sent(self, driver, el):
        sent = self.requests > self.request_baseline
        self.confirmations.append(sent)
        return sent

    def extract_answer_snapshot(self, driver):
        snapshot = super().extract_answer_snapshot(driver)
        self.snapshots.append(dict(snapshot))
        return snapshot

    def wait_for_new_answer(self, driver, initial_count, **kwargs):
        self.waits.append((initial_count, dict(kwargs["baseline"])))
        return super().wait_for_new_answer(driver, initial_count, **kwargs)

    def _log(self, message):
        pass


class BrowserSendAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        self.driver = _FakeDriver()
        self.driver.field_text = ""
        time_patch = patch.object(parser_base, "time", self.clock)
        random_patch = patch.object(
            parser_base, "random", types.SimpleNamespace(uniform=lambda a, b: a))
        time_patch.start()
        random_patch.start()
        self.addCleanup(time_patch.stop)
        self.addCleanup(random_patch.stop)

    def send(self, parser):
        return parser.send_message_and_get_response(
            self.driver, "prompt", input_retries=3,
            cancel_cb=lambda: parser.cancelled)

    def assert_completed(self, parser, submits=1):
        self.assertEqual(self.send(parser), {"text": "complete", "action": None})
        self.assertEqual(parser.insert_calls, 1)
        self.assertEqual(parser.submit_calls, submits)
        self.assertEqual(parser.after_calls, submits)
        self.assertEqual(parser.requests, 1)
        self.assertEqual(parser.request_baseline, 0)
        self.assertEqual(parser.snapshots, [
            {"text": "old answer", "actionRaw": None, "error": None}])
        self.assertEqual(parser.waits, [(1, parser.snapshots[0])])
        self.assertEqual(parser.regen_clicks, 0)

    def test_late_attachment_with_empty_composer_is_inserted_once(self):
        parser = _AcceptanceParser(self.clock, self.driver, attachment=True)
        try:
            self.assert_completed(parser)
        finally:
            self.assertEqual(parser.attachments, 1)
            self.assertEqual(parser.insert_calls, 1)
        self.assertTrue(parser._insert_became_attachment)
        self.assertEqual(parser.note_calls, 1)
        self.assertEqual(self.driver.field_text, parser.ATTACHMENT_NOTE)

    def test_acceptance_during_delay_with_unchanged_composer(self):
        parser = _AcceptanceParser(self.clock, self.driver, acceptance="delay")
        self.assert_completed(parser)
        self.assertEqual(parser.confirmations, [False, True])
        self.assertEqual(self.driver.field_text, "prompt")

    def test_acceptance_during_delay_with_cleared_composer(self):
        parser = _AcceptanceParser(
            self.clock, self.driver, acceptance="delay", clear=True)
        self.assert_completed(parser)
        self.assertEqual(parser.confirmations, [False, True])
        self.assertEqual(self.driver.field_text, "")

    def test_acceptance_during_preparation_with_unchanged_composer(self):
        parser = _AcceptanceParser(self.clock, self.driver, acceptance="preparation")
        self.assert_completed(parser)
        self.assertEqual(parser.confirmations, [False, True])
        self.assertEqual(self.driver.field_text, "prompt")

    def test_acceptance_during_preparation_with_cleared_composer(self):
        parser = _AcceptanceParser(
            self.clock, self.driver, acceptance="preparation", clear=True)
        self.assert_completed(parser)
        self.assertEqual(parser.confirmations, [False, True])
        self.assertEqual(self.driver.field_text, "")

    def test_genuinely_unaccepted_send_can_retry(self):
        parser = _AcceptanceParser(self.clock, self.driver, acceptance="retry")
        self.assert_completed(parser, submits=2)

    def test_exhausted_retry_does_not_wait_for_answer(self):
        parser = _AcceptanceParser(self.clock, self.driver, acceptance="never")
        result = self.send(parser)
        self.assertIsNone(result["action"])
        self.assertEqual(parser.submit_calls, 2)
        self.assertEqual(parser.insert_calls, 1)
        self.assertEqual(parser.waits, [])
        self.assertEqual(parser.requests, 0)

    def test_unaccepted_mismatched_composer_is_not_resubmitted(self):
        parser = _AcceptanceParser(self.clock, self.driver, acceptance="never")

        def change_composer(seconds):
            if parser.submit_calls:
                self.driver.field_text = "foreign text"

        self.clock.on_sleep = change_composer
        with self.assertRaises(Exception):
            self.send(parser)
        self.assertEqual(parser.submit_calls, 1)
        self.assertEqual(parser.waits, [])

    def test_cancellation_before_initial_submit(self):
        parser = _AcceptanceParser(self.clock, self.driver)
        parser.cancel_stage = "initial"
        with self.assertRaises(parser_base.ParserCancelled):
            self.send(parser)
        self.assertEqual(parser.submit_calls, 0)
        self.assertEqual(parser.waits, [])

    def test_cancellation_during_retry_blocks_resubmit(self):
        for stage in ("delay", "preparation"):
            with self.subTest(stage=stage):
                parser = _AcceptanceParser(self.clock, self.driver, acceptance="never")
                parser.cancel_stage = stage
                with self.assertRaises(parser_base.ParserCancelled):
                    self.send(parser)
                self.assertEqual(parser.submit_calls, 1)
                self.assertEqual(parser.waits, [])

    def test_cancellation_during_late_acceptance_is_not_swallowed(self):
        for stage in ("delay", "preparation"):
            with self.subTest(stage=stage):
                parser = _AcceptanceParser(self.clock, self.driver, acceptance=stage)
                parser.cancel_stage = stage
                with self.assertRaises(parser_base.ParserCancelled):
                    self.send(parser)
                self.assertEqual(parser.submit_calls, 1)
                self.assertEqual(parser.waits, [])
                self.assertEqual(parser.request_baseline, 0)


if __name__ == "__main__":
    unittest.main()
