"""Local debugger discovery and AI Studio page ownership, without a browser."""
import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap
import ai_parser
import browser_manager


class BrowserTargetTests(unittest.TestCase):
    def setUp(self):
        self.parser = ai_parser.AiStudioParser()
        for name, value in (("_monitor", None), ("_monitor_window", None),
                            ("_monitor_next_retry", 0), ("_req_count_before_send", None)):
            original = getattr(ai_parser.AiStudioParser, name)
            self.addCleanup(setattr, ai_parser.AiStudioParser, name, original)
            setattr(ai_parser.AiStudioParser, name, value)
        self.driver = Mock(current_window_handle="window-B")
        self.driver.execute_cdp_cmd.return_value = {"targetInfo": {"targetId": "B"}}
        self.targets = [
            {"id": "A", "type": "page", "webSocketDebuggerUrl": "ws://wrong"},
            {"id": "B", "type": "page", "webSocketDebuggerUrl": "ws://correct"},
        ]

    def test_current_target_not_first_tab_and_reused(self):
        with patch.object(ai_parser, "list_targets", return_value=self.targets), \
                patch.object(ai_parser, "CDPSession") as connect:
            monitor = self.parser._ensure_monitor(self.driver)
            self.assertIsNotNone(monitor)
            connect.assert_called_once_with("ws://correct")
            connect.return_value.send_command.assert_called_once_with("Network.enable")
            self.assertIs(self.parser._ensure_monitor(self.driver), monitor)
            self.driver.execute_cdp_cmd.assert_called_once_with("Target.getTargetInfo", {})

    def test_switch_retires_previous_buffer_even_if_target_is_missing(self):
        old = Mock()
        ai_parser.AiStudioParser._monitor = old
        ai_parser.AiStudioParser._monitor_window = "window-A"
        ai_parser.AiStudioParser._req_count_before_send = 3
        with patch.object(ai_parser, "list_targets", return_value=self.targets[:1]), \
                patch.object(ai_parser, "CDPSession") as connect:
            self.assertIsNone(self.parser._ensure_monitor(self.driver))
            connect.assert_not_called()
        old._cdp.close.assert_called_once()
        self.assertIsNone(ai_parser.AiStudioParser._monitor)
        self.assertIsNone(ai_parser.AiStudioParser._req_count_before_send)

    def test_failed_enable_closes_connection(self):
        with patch.object(ai_parser, "list_targets", return_value=self.targets), \
                patch.object(ai_parser, "CDPSession") as connect:
            connect.return_value.send_command.side_effect = RuntimeError("disconnected")
            self.assertIsNone(self.parser._ensure_monitor(self.driver))
            connect.return_value.close.assert_called_once()

    def test_debug_probe_bypasses_proxy_and_closes_response(self):
        with patch.object(browser_manager.socket, "create_connection"), \
                patch.object(browser_manager.urllib.request, "ProxyHandler") as proxy, \
                patch.object(browser_manager.urllib.request, "build_opener") as build:
            self.assertTrue(browser_manager._wait_for_debug_port())
            proxy.assert_called_once_with({})
            build.assert_called_once_with(proxy.return_value)
            build.return_value.open.assert_called_once_with(
                "http://127.0.0.1:9222/json/version", timeout=0.5)
            build.return_value.open.return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
