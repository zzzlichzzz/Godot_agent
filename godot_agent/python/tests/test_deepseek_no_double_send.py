"""Offline DeepSeek delivery regressions through the real base send pipeline."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import _fake_selenium

_fake_selenium.install()

import deepseek_parser as deepseek
import parser_base
from selenium.common.exceptions import StaleElementReferenceException


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    time = monotonic

    def sleep(self, seconds):
        self.now += seconds


class Element:
    def __init__(self, driver):
        self.driver = driver

    def send_keys(self, keys):
        driver = self.driver
        if keys != deepseek.Keys.ENTER:
            driver.notes.append(keys)
            driver.field += keys
            return
        driver.submit_attempts += 1
        if driver.stale_once:
            driver.stale_once = False
            driver.element = Element(driver)
            raise StaleElementReferenceException("detached before dispatch")
        if driver.submit_error:
            raise driver.submit_error
        driver.sends += 1
        driver.sent_at = driver.clock.now
        driver.submitted.append((driver.field, driver.attachments))
        if driver.replace_after_send:
            driver.element = Element(driver)


class Driver:
    def __init__(self, clock):
        self.clock = clock
        self.element = Element(self)
        self.field = ""
        self.clear_after = 0.0
        self.sent_at = None
        self.sends = 0
        self.submit_attempts = 0
        self.submit_error = None
        self.stale_once = False
        self.replace_after_send = False
        self.read_after_send = "value"
        self.attachment = False
        self.attachments = 0
        self.notes = []
        self.submitted = []
        self.inserts = 0
        self.mismatch = False
        self.scripts = []

    def execute_script(self, script, *args):
        self.scripts.append(script)
        # Reject *all* synthetic send paths, including future alternatives.
        if script == deepseek.JS_SET_INPUT:
            self.inserts += 1
            self.field = "wrong composer" if self.mismatch else args[1]
            if self.attachment:
                self.attachments += 1
                self.field = "attached.txt"
            return None
        assert "dispatchEvent" not in script and ".click(" not in script, script
        if script == deepseek.JS_FIND_INPUT:
            if self.sent_at is not None and self.read_after_send == "missing":
                return None
            return self.element
        if script == deepseek.JS_IS_GENERATING:
            return False
        if script == deepseek.JS_COUNT_ANSWERS:
            return 0
        if script == deepseek.JS_EXTRACT:
            return {"text": "", "actionRaw": None, "error": None}
        if script == deepseek.JS_ANSWER_STREAM:
            return "answer"
        if "value" in script:
            if self.sent_at is not None:
                if self.read_after_send == "error":
                    raise RuntimeError("composer read failed")
                if self.read_after_send == "null":
                    return None
                if args[0] is not self.element:
                    return ""  # Detached old composer must not confirm delivery.
                if self.clock.now - self.sent_at >= self.clear_after:
                    self.field = ""
                    self.attachments = 0
            return self.field
        raise AssertionError("Unexpected browser operation: " + script)


class DeepSeekDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        for module in (deepseek, parser_base):
            patcher = patch.object(module, "time", self.clock)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.parser = deepseek.DeepSeekParser()
        self.driver = Driver(self.clock)
        self.waits = 0
        self.parser._log = lambda message: None
        self.parser.switch_to_site_window = lambda driver, **kwargs: None
        self.parser._maybe_harden_background_tab = lambda driver: None
        self.parser._focus_input_caret_end = lambda driver, el: None
        self.parser.count_composer_attachments = lambda driver: driver.attachments
        self.parser.insert_input_for_send = self.insert
        self.parser.wait_for_new_answer = self.wait_for_answer

    def insert(self, driver, el, prompt):
        # Stub only clipboard/paste mechanics. Keep actual insertion, attachment
        # detection, note typing, validation, submit and confirmation hooks.
        self.parser._insert_became_attachment = False
        self.parser.insert_input(driver, el, prompt)
        return "insert"

    def wait_for_answer(self, driver, initial_count, **kwargs):
        self.waits += 1
        return {"text": "answer", "actionRaw": None, "error": None}

    def send(self):
        return self.parser.send_message_and_get_response(self.driver, "expected prompt")

    def assert_uncertain(self, result):
        self.assertIsNone(result["action"])
        self.assertIn("DeepSeek", result["text"])
        self.assertIn("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u044c \u0434\u043e\u0441\u0442\u0430\u0432\u043a\u0443", result["text"])
        self.assertEqual(self.driver.sends, 1)
        self.assertEqual(self.driver.submit_attempts, 1)
        self.assertEqual(self.driver.inserts, 1)
        self.assertEqual(self.waits, 0)
        self.assertAlmostEqual(self.clock.now - self.driver.sent_at, 3.2)

    def test_delayed_composer_clearing_never_resubmits(self):
        self.driver.clear_after = 2.0  # Beyond the old 1.2-second fallback.
        self.assertEqual(self.send(), {"text": "answer", "action": None})
        self.assertEqual(self.driver.sends, 1)
        self.assertEqual(self.driver.inserts, 1)
        self.assertEqual(self.waits, 1)
        self.assertGreaterEqual(self.clock.now - self.driver.sent_at, 2.0)

    def test_accepted_but_clears_after_deadline_is_uncertain(self):
        self.driver.clear_after = 10.0
        self.assert_uncertain(self.send())
        self.assertEqual(self.driver.field, "expected prompt")

    def test_no_observable_acceptance_is_not_claimed_failed_or_retried(self):
        self.driver.clear_after = float("inf")
        self.assert_uncertain(self.send())

    def test_confirmed_send_continues_to_answer(self):
        self.assertEqual(self.send(), {"text": "answer", "action": None})
        self.assertEqual(self.driver.sends, 1)
        self.assertEqual(self.waits, 1)

    def test_attachment_with_delayed_clearing_keeps_one_file_and_note(self):
        self.driver.attachment = True
        self.driver.clear_after = 2.0
        self.assertEqual(self.send()["text"], "answer")
        self.assertEqual(self.driver.notes, [self.parser.ATTACHMENT_NOTE])
        self.assertEqual(self.driver.submitted, [
            ("attached.txt" + self.parser.ATTACHMENT_NOTE, 1)])
        self.assertEqual(self.driver.inserts, 1)
        self.assertEqual(self.driver.sends, 1)

    def test_ambiguous_attachment_keeps_one_file_and_note(self):
        self.driver.attachment = True
        self.driver.clear_after = 10.0
        self.assert_uncertain(self.send())
        self.assertEqual(self.driver.attachments, 1)
        self.assertEqual(self.driver.notes, [self.parser.ATTACHMENT_NOTE])

    def test_empty_attachment_body_alone_does_not_confirm_delivery(self):
        self.driver.attachment = True
        original_insert = self.insert

        def paste_as_file(driver, el, prompt):
            original_insert(driver, el, prompt)
            driver.field = ""
            self.parser._insert_became_attachment = True
            return "paste"

        self.parser.insert_input_for_send = paste_as_file
        self.parser.ATTACHMENT_NOTE = ""
        self.driver.clear_after = float("inf")
        self.assert_uncertain(self.send())
        self.assertEqual(self.driver.submitted, [("", 1)])

    def test_missing_unreadable_or_null_composer_is_not_confirmation(self):
        for mode in ("missing", "error", "null"):
            with self.subTest(mode=mode):
                self.driver = Driver(self.clock)
                self.driver.read_after_send = mode
                self.assert_uncertain(self.send())

    def test_replaced_composer_is_read_instead_of_detached_empty_element(self):
        self.driver.replace_after_send = True
        self.driver.clear_after = 10.0
        self.assert_uncertain(self.send())

    def test_stale_failure_before_dispatch_can_recover(self):
        self.driver.stale_once = True
        self.assertEqual(self.send()["text"], "answer")
        self.assertEqual(self.driver.submit_attempts, 2)
        self.assertEqual(self.driver.sends, 1)
        self.assertEqual(self.driver.inserts, 1)

    def test_submit_failure_before_send_remains_original_error(self):
        error = RuntimeError("input cannot accept keys")
        self.driver.submit_error = error
        with self.assertRaises(RuntimeError) as caught:
            self.send()
        self.assertIs(caught.exception, error)
        self.assertEqual(self.driver.sends, 0)
        self.assertEqual(self.driver.submit_attempts, 1)
        self.assertEqual(self.waits, 0)

    def test_invalid_input_is_blocked_before_send(self):
        self.driver.mismatch = True
        with self.assertRaises(Exception):
            self.send()
        self.assertEqual(self.driver.submit_attempts, 0)
        self.assertEqual(self.waits, 0)

    def test_after_submit_is_read_only_and_base_send_retries_are_disabled(self):
        self.parser.after_submit(self.driver, self.driver.element)
        self.assertEqual(self.driver.scripts, [])
        self.assertEqual(self.driver.sends, 0)
        self.assertEqual(self.parser.SEND_RETRIES, 0)


if __name__ == "__main__":
    unittest.main()
