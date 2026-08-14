import os
import sys
import unittest


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

import _bootstrap  # noqa: E402,F401
import server_state  # noqa: E402


class ChatPendingCleanupTests(unittest.TestCase):
    def test_clear_pending_confirmations_discards_all_chat_scoped_state(self):
        state = server_state.STATE
        keys = ("pending_action", "pending_batch", "pending_plan", "plan_parts", "content_parts")
        previous = {key: state.get(key) for key in keys}
        try:
            for key in keys:
                state[key] = {"chat": "deleted-chat"}

            server_state.clear_pending_confirmations()

            self.assertTrue(all(state.get(key) is None for key in keys))
        finally:
            state.update(previous)


if __name__ == "__main__":
    unittest.main()
