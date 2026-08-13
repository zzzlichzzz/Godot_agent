import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import chat_store
import server_state


class Driver:
    current_url = "https://arena.ai/c/battle-chat-id?source=ignored"


def test_restore_battle_chat_preserves_site_id_after_restart():
    root = tempfile.mkdtemp(prefix="arena_battle_restore_")
    old_data_dir = server_state.STATE.get("user_data_dir")
    old_chat_id = server_state.STATE.get("current_chat_id")
    old_site_id = server_state.STATE.get("current_site_id")
    old_driver = server_state.get_driver()
    try:
        rec = chat_store.create_chat(root, url="https://arena.ai/c/battle-chat-id",
                                     title="Battle", primed=True)
        chat_store.update_chat(root, rec["id"], site_id="arena_battle")
        server_state.STATE["user_data_dir"] = root
        server_state.STATE["current_chat_id"] = None
        server_state.STATE["current_site_id"] = None
        server_state.set_driver(Driver())

        restored = server_state._ensure_current_chat()

        assert restored["id"] == rec["id"]
        assert server_state.STATE["current_site_id"] == "arena_battle"
    finally:
        server_state.STATE["user_data_dir"] = old_data_dir
        server_state.STATE["current_chat_id"] = old_chat_id
        server_state.STATE["current_site_id"] = old_site_id
        server_state.set_driver(old_driver)
