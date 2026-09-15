"""Cancellation is terminal across internal repair/retry calls, not user turns."""
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _bootstrap  # noqa: E402,F401
import main
import server_state as state


class TurnCancellationTests(unittest.TestCase):
    def setUp(self):
        state.clear_request_activity()
        state.clear_cancel()
        self.temp = tempfile.TemporaryDirectory(prefix="browser_cancel_")
        self.backend = Mock(kind="browser")
        self.backend.pop_rate_limit_status.return_value = None
        self.backend.pop_retry_after.return_value = None
        self.patch = patch.object(main, "_current_backend", return_value=self.backend)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(state.clear_cancel)
        self.addCleanup(state.clear_request_activity)

    def test_stop_during_targeted_repair_ends_whole_chain(self):
        for good in ([], [{"index": 0, "step": {"action": "create_file", "path": "res://ok.txt", "content": "ok"}}]):
            with self.subTest(partial_plan=bool(good)):
                state.clear_cancel()
                self.backend.send.reset_mock()
                self.backend.send.side_effect = [
                    {"text": "broken plan", "action": {"action": "parse_error", "raw": "bad"}},
                    main.parser_base.ParserCancelled("stop during repair"),
                    AssertionError("must not send next repair"),
                ]
                plan = {"good_steps": good, "bad_steps": [
                    {"index": 1, "raw": "bad1", "error": "broken"},
                    {"index": 2, "raw": "bad2", "error": "broken"}]}
                with patch.object(main.parser_base, "parse_plan_lenient", return_value=plan):
                    text, action = main._reply_with_self_heal("test", self.temp.name)
                self.assertIn("[\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e]", text)
                self.assertIsNone(action)
                self.assertEqual(self.backend.send.call_count, 2)
                self.assertTrue(state.cancel_requested())
                self.assertFalse(state.exchange_active())
                self.assertFalse(state.STATE["progress"]["active"])
                main._reply_once("late followup")
                self.assertEqual(self.backend.send.call_count, 2)

    def test_cancel_in_rate_limit_wait_does_not_retry(self):
        self.backend.send.side_effect = None
        self.backend.send.return_value = {"text": "busy", "action": None}
        self.backend.pop_rate_limit_status.return_value = 429
        with patch.object(main, "_retry_wait_left", return_value=1000), \
                patch.object(main.time, "sleep", side_effect=lambda _: state.request_cancel()):
            text, action = main._reply_with_self_heal("test", self.temp.name)
        self.assertIsNone(action)
        self.assertEqual(self.backend.send.call_count, 1)
        self.assertTrue(state.cancel_requested())

    def test_new_admitted_turn_resets_stop_but_busy_request_does_not(self):
        state.request_cancel()
        self.assertTrue(state.try_begin_turn_exchange())
        self.assertFalse(state.cancel_requested())
        state.request_cancel()
        self.assertFalse(state.try_begin_turn_exchange())
        self.assertTrue(state.cancel_requested())
        state.clear_request_activity()
        self.assertTrue(state.try_begin_turn_exchange())
        self.assertFalse(state.cancel_requested())
        self.backend.send.side_effect = None
        self.backend.send.return_value = {"text": "new turn", "action": None}
        self.assertEqual(main._reply_once("new turn"), ("new turn", None))
        self.backend.send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
