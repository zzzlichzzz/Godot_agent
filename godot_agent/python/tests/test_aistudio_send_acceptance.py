"""AI Studio acceptance signals; no browser or model requests."""
import types
import unittest
from unittest.mock import Mock, patch

from test_browser_wait_safety import _Clock
import ai_parser
import parser_base


class AiStudioAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        clock = types.SimpleNamespace(time=self.clock.time, monotonic=self.clock.time,
                                      sleep=self.clock.sleep)
        for module in (ai_parser, parser_base):
            p = patch.object(module, "time", clock)
            p.start()
            self.addCleanup(p.stop)
        self.parser = ai_parser.AiStudioParser()
        self.driver = Mock(current_window_handle="current")
        self.driver.execute_script.return_value = 2
        self.element = Mock()
        self.monitor = Mock()
        self.monitor.chat_request_count.return_value = 5
        self.parser._ensure_monitor = Mock(return_value=self.monitor)
        for name, value in (("_monitor", self.monitor), ("_req_count_before_send", None)):
            p = patch.object(ai_parser.AiStudioParser, name, value)
            p.start()
            self.addCleanup(p.stop)

    def submit(self):
        self.parser.submit(self.driver, self.element)
        self.element.send_keys.assert_called_once_with(ai_parser.Keys.CONTROL, ai_parser.Keys.ENTER)

    def test_keyboard_dispatch_alone_is_not_acceptance(self):
        self.submit()
        with self.assertRaises(RuntimeError):
            self.parser.confirm_sent(self.driver, self.element)
        self.assertGreaterEqual(self.clock.now, 5)
        self.element.send_keys.assert_called_once()

    def test_new_post_accepts_even_before_ui_changes(self):
        self.submit()
        self.monitor.chat_request_count.return_value = 6
        self.assertTrue(self.parser.confirm_sent(self.driver, self.element))
        self.assertEqual(self.clock.now, 0)

    def test_late_post_accepts_without_another_submit(self):
        self.submit()
        self.clock.on_sleep = lambda _: setattr(
            self.monitor.chat_request_count, "return_value", 6)
        self.assertTrue(self.parser.confirm_sent(self.driver, self.element))
        self.assertGreater(self.clock.now, 0)
        self.element.send_keys.assert_called_once()

    def test_dom_only_mode_requires_new_user_turn(self):
        self.parser._ensure_monitor.return_value = None
        ai_parser.AiStudioParser._monitor = None
        self.submit()
        self.driver.execute_script.return_value = 3
        self.assertTrue(self.parser.confirm_sent(self.driver, self.element))

    def test_unknown_dom_baseline_is_not_zero(self):
        self.parser._ensure_monitor.return_value = None
        ai_parser.AiStudioParser._monitor = None
        self.driver.execute_script.side_effect = ai_parser.WebDriverException("unreadable")
        self.submit()
        self.driver.execute_script.side_effect = None
        self.driver.execute_script.return_value = 2
        with self.assertRaises(RuntimeError):
            self.parser.confirm_sent(self.driver, self.element)

    def test_changed_window_does_not_confirm_from_another_chat(self):
        self.submit()
        self.driver.current_window_handle = "other"
        self.driver.execute_script.return_value = 99
        with self.assertRaises(RuntimeError):
            self.parser.confirm_sent(self.driver, self.element)

    def test_unreadable_page_does_not_confirm_delivery(self):
        self.submit()
        self.driver.execute_script.side_effect = ai_parser.WebDriverException("closed")
        with self.assertRaises(RuntimeError):
            self.parser.confirm_sent(self.driver, self.element)

    def test_unconfirmed_pipeline_returns_error_without_wait_or_retry(self):
        self.parser.switch_to_site_window = Mock()
        self.parser._maybe_harden_background_tab = Mock()
        self.parser.is_generating = Mock(return_value=False)
        self.parser.find_input = Mock(return_value=self.element)
        self.parser.insert_input_for_send = Mock(return_value="insert")
        self.parser._read_input_text = Mock(return_value="prompt")
        self.parser.before_submit = Mock()
        self.parser.extract_answer_snapshot = Mock(return_value={"text": "old"})
        self.parser.count_answers = Mock(return_value=2)
        self.parser.wait_for_new_answer = Mock(return_value={"text": "must not return"})
        self.parser.answer_stream = Mock(return_value="")
        self.driver.execute_script.side_effect = lambda script, *args: (
            2 if "data-turn-role" in script else "prompt")
        result = self.parser.send_message_and_get_response(self.driver, "prompt")
        self.assertIsNone(result["action"])
        self.assertIn("AI Studio", result["text"])
        self.parser.wait_for_new_answer.assert_not_called()
        self.parser.insert_input_for_send.assert_called_once()
        self.element.send_keys.assert_called_once()


if __name__ == "__main__":
    unittest.main()
