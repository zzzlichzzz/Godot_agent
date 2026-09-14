"""Fault injection for API history transactions and accepted backend replies."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import _fake_selenium

_fake_selenium.install()

import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import api_backend as AB
import api_history as H


class HistoryFailures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="api_history_faults_")
        self.addCleanup(self.temp.cleanup)
        self.base = self.temp.name
        self.cid = "history-faults"
        self.path = Path(H.history_path(self.base, self.cid))

    def seed(self):
        self.assertTrue(H.append_exchange(
            self.base, self.cid, "old question", "old answer",
            usage={"prompt_tokens": 10, "completion_tokens": 2}))
        return self.path.read_bytes()

    def test_absent_history_semantics(self):
        self.assertEqual(H.load_messages(self.base, self.cid), [])
        self.assertEqual(H.stats(self.base, self.cid)["usage_total"]["requests"], 0)
        self.assertFalse(self.path.exists())
        self.assertTrue(H.clear(self.base, self.cid))
        self.assertTrue(H.delete(self.base, self.cid))
        self.assertTrue(H.delete(self.base, self.cid))
        self.assertEqual(H.load_messages("", ""), [])
        self.assertFalse(H.append_exchange("", "", "q", "a"))

    def test_corrupt_history_blocks_reads_and_mutations(self):
        self.path.parent.mkdir()
        for payload in (b"{broken", b"\xff", b"[]", b"{}",
                        b'{"messages": [null]}',
                        b'{"messages": [{"role": "bogus", "content": "x"}]}',
                        b'{"messages": [{"role": "user"}]}',
                        b'{"messages": [{"role": "user", "content": "x", "ts": "bad"}]}',
                        b'{"messages": [], "usage_total": []}',
                        b'{"messages": [], "trimmed": "bad"}'):
            self.path.write_bytes(payload)
            for operation in (
                    lambda: H.load_messages(self.base, self.cid),
                    lambda: H.stats(self.base, self.cid),
                    lambda: H.build_request_messages(self.base, self.cid, "sys", "q"),
                    lambda: H.append(self.base, self.cid, H.ROLE_USER, "note"),
                    lambda: H.append_exchange(self.base, self.cid, "q", "a"),
                    lambda: H.clear(self.base, self.cid)):
                with self.subTest(payload=payload, operation=operation):
                    with self.assertRaises(H.ApiHistoryError):
                        operation()
                    self.assertEqual(self.path.read_bytes(), payload)

    def test_unreadable_existing_history_is_not_empty(self):
        before = self.seed()
        with patch("builtins.open", side_effect=PermissionError("read denied")):
            with self.assertRaises(H.ApiHistoryError):
                H.load_messages(self.base, self.cid)
            with self.assertRaises(H.ApiHistoryError):
                H.append_exchange(self.base, self.cid, "q", "a")
        self.assertEqual(self.path.read_bytes(), before)

    def test_directory_instead_of_history_is_not_empty(self):
        self.path.mkdir(parents=True)
        with self.assertRaises(H.ApiHistoryError):
            H.load_messages(self.base, self.cid)

    def test_atomic_save_failures_preserve_original_and_clean_temp(self):
        before = self.seed()
        for target in ("json.dump", "os.fsync", "os.replace"):
            with self.subTest(target=target):
                with patch("api_history." + target, side_effect=OSError("disk failure")):
                    self.assertFalse(H.append_exchange(self.base, self.cid, "q", "a"))
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_temp_is_unique_sibling_and_synced_before_replace(self):
        self.seed()
        sources = []
        real_replace = os.replace
        real_fsync = os.fsync
        with patch.object(H.os, "fsync", wraps=real_fsync) as sync:
            def replace(src, dst):
                self.assertEqual(sync.call_count, len(sources) + 1)
                self.assertEqual(Path(src).parent, self.path.parent)
                self.assertNotEqual(str(src), str(self.path) + ".tmp")
                self.assertEqual(Path(dst), self.path)
                # Reading valid JSON here also checks that buffered writes were flushed.
                json.loads(Path(src).read_text(encoding="utf-8"))
                sources.append(src)
                real_replace(src, dst)

            with patch.object(H.os, "replace", side_effect=replace):
                for i in range(2):
                    self.assertTrue(H.append_exchange(self.base, self.cid, str(i), "a"))
        self.assertEqual(len(set(sources)), 2)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_concurrent_appends_keep_all_messages_pairs_and_usage(self):
        workers = 12
        barrier = threading.Barrier(workers)
        real_load = H._load

        def slow_load(*args, **kwargs):
            data = real_load(*args, **kwargs)
            time.sleep(0.005)  # Expose lost updates if the transaction lock is removed.
            return data

        def append(i):
            barrier.wait(timeout=10)
            # Equivalent store paths must share the same transaction lock.
            base = self.base if i % 2 else os.path.join(self.base, ".")
            self.assertTrue(H.append_exchange(
                base, self.cid, "q%d" % i, "a%d" % i,
                usage={"prompt_tokens": 3, "completion_tokens": 2}))
            self.assertTrue(H.append(base, self.cid, H.ROLE_USER, "note%d" % i))

        with patch.object(H, "_load", side_effect=slow_load):
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(append, range(workers)))
        messages = H.load_messages(self.base, self.cid)
        self.assertEqual(len(messages), workers * 3)
        contents = [m["content"] for m in messages]
        for i in range(workers):
            self.assertEqual(contents.count("q%d" % i), 1)
            self.assertEqual(contents[contents.index("q%d" % i) + 1], "a%d" % i)
            self.assertEqual(contents.count("note%d" % i), 1)
        self.assertEqual(H.stats(self.base, self.cid)["usage_total"], {
            "prompt_tokens": workers * 3, "completion_tokens": workers * 2,
            "requests": workers})

    def backend(self):
        for target, value in (("providers.base_url_for", "http://unused.invalid"),
                              ("api_keys.usable_keys", []),
                              ("budgets_for", (1000, 16000, 32000, ""))):
            mock = patch("api_backend." + target, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        AB.pop_rate_limit_status()
        AB.pop_retry_after()
        return AB.ApiBackend({"id": self.cid, "provider": "custom", "model": "test"},
                             self.base)

    def test_accepted_response_survives_save_failure_without_retry(self):
        before = self.seed()
        backend = self.backend()
        raw = 'Accepted answer.\n```agent_action\n{"action": "list_files"}\n```\n===DONE==='
        usage = {"prompt_tokens": 20, "completion_tokens": 5}
        response = {"text": raw, "usage": usage, "finish_reason": "stop", "model": "actual"}
        for failure in ("replace", "load", "false", "stats"):
            target, kwargs = {
                "replace": ("api_history.os.replace", {"side_effect": OSError("disk full")}),
                "load": ("api_history.append_exchange", {"side_effect": H.ApiHistoryError("read denied")}),
                "false": ("api_history.append_exchange", {"return_value": False}),
                "stats": ("api_history.stats", {"side_effect": H.ApiHistoryError("read denied")}),
            }[failure]
            with self.subTest(failure=failure):
                with patch.object(backend, "_stream", return_value=response) as provider:
                    with patch(target, **kwargs):
                        result = backend.send("question")
                provider.assert_called_once()
                self.assertEqual(result["raw"], raw)
                self.assertEqual(result["action"], {"action": "list_files"})
                self.assertEqual(result["usage"], usage)
                self.assertEqual(result["finish_reason"], "stop")
                self.assertEqual(result["model"], "actual")
                self.assertIn("Accepted answer.", result["text"])
                self.assertNotIn("tok", result["text"])
                self.assertIsNone(backend.pop_rate_limit_status())
                self.assertIsNone(backend.pop_retry_after())
                if failure != "stats":
                    self.assertIn(AB.HISTORY_SAVE_WARNING, result["text"])
                    self.assertEqual(self.path.read_bytes(), before)
                else:
                    self.assertIn("[color=#c08040]", result["text"])
                    self.assertEqual(H.load_messages(self.base, self.cid)[-1]["content"], raw)

    def test_corruption_after_provider_response_blocks_next_request(self):
        self.seed()
        backend = self.backend()

        def respond(*args):
            self.path.write_bytes(b"{corrupt during request")
            return {"text": "Accepted answer.", "finish_reason": "stop"}

        with patch.object(backend, "_stream", side_effect=respond) as provider:
            accepted = backend.send("question")
            self.assertEqual(accepted["raw"], "Accepted answer.")
            self.assertIn(AB.HISTORY_SAVE_WARNING, accepted["text"])
            blocked = backend.send("next question")
            provider.assert_called_once()
        self.assertEqual(blocked["finish_reason"], "error")
        self.assertEqual(blocked["raw"], "")
        self.assertIsNone(blocked["action"])
        self.assertIsNone(backend.pop_rate_limit_status())
        self.assertEqual(self.path.read_bytes(), b"{corrupt during request")

    def test_rescued_response_survives_persistence_failure(self):
        backend = self.backend()
        raw = 'Accepted.\n```agent_action\n{"action": "list_files"}\n```'
        with patch.object(backend, "_stream", return_value={"text": raw, "truncated": True}) as provider:
            with patch.object(H, "append_exchange", return_value=False):
                result = backend.send("question")
        provider.assert_called_once()
        self.assertEqual(result["raw"], raw)
        self.assertEqual(result["action"], {"action": "list_files"})
        self.assertIn(AB.RESCUE_NOTE, result["text"])
        self.assertIn(AB.HISTORY_SAVE_WARNING, result["text"])
        self.assertIsNone(backend.pop_rate_limit_status())


if __name__ == "__main__":
    unittest.main()
