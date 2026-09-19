import json
import os
import sys
import tempfile
import threading


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

import _bootstrap  # noqa: E402,F401
import chat_store  # noqa: E402
import server_state  # noqa: E402


def test_notes_and_turns_are_chat_scoped():
    root = tempfile.mkdtemp(prefix="agent_chat_scope_")
    previous = {key: server_state.STATE.get(key) for key in
                ("user_data_dir", "current_chat_id", "stale_notes", "action_notes")}
    try:
        first = chat_store.create_chat(root, title="First")
        second = chat_store.create_chat(root, title="Second")
        server_state.STATE.update({"user_data_dir": root,
                                   "current_chat_id": second["id"],
                                   "stale_notes": {}, "action_notes": {}})
        server_state.queue_stale_note(first["id"], "first summary")
        server_state.queue_stale_note(second["id"], "second summary")

        server_state.bind_turn_chat(first["id"])
        assert server_state.pop_stale_note_for_current() == "first summary"
        server_state._remember("user", "bound to first")
        assert server_state.turn_chat_is_current() is False
        server_state.clear_turn_chat()

        assert server_state.STATE["stale_notes"] == {second["id"]: "second summary"}
        assert chat_store.find_chat(root, first["id"])["transcript"][-1]["text"] == "bound to first"
        assert chat_store.find_chat(root, second["id"])["transcript"] == []
    finally:
        server_state.clear_turn_chat()
        server_state.STATE.update(previous)


def test_concurrent_transcript_writes_are_not_lost():
    root = tempfile.mkdtemp(prefix="agent_chat_concurrent_")
    chat = chat_store.create_chat(root, title="Concurrent")
    barrier = threading.Barrier(9)
    errors = []

    def writer(index):
        try:
            barrier.wait()
            chat_store.append_transcript(root, chat["id"], "user", "message-%d" % index)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert not errors, errors
    transcript = chat_store.find_chat(root, chat["id"])["transcript"]
    assert sorted(item["text"] for item in transcript) == ["message-%d" % i for i in range(8)]


def test_atomic_save_failure_preserves_previous_json():
    root = tempfile.mkdtemp(prefix="agent_chat_atomic_")
    chat = chat_store.create_chat(root, title="Atomic")
    path = os.path.join(root, "agent_chats.json")
    with open(path, "rb") as handle:
        before = handle.read()

    original_replace = chat_store.os.replace
    chat_store.os.replace = lambda _src, _dst: (_ for _ in ()).throw(OSError("injected"))
    try:
        try:
            chat_store.append_transcript(root, chat["id"], "user", "must not persist")
        except IOError:
            pass
        else:
            raise AssertionError("failed atomic save must be reported")
    finally:
        chat_store.os.replace = original_replace

    with open(path, "rb") as handle:
        assert handle.read() == before
    with open(path, "r", encoding="utf-8") as handle:
        assert isinstance(json.load(handle), list)


def test_transcript_trim_keeps_whole_messages():
    root = tempfile.mkdtemp(prefix="agent_chat_trim_")
    chat = chat_store.create_chat(root, title="Trim")
    long_text = "x" * 5000
    for index in range(chat_store.MAX_TRANSCRIPT + 2):
        chat_store.append_transcript(root, chat["id"], "user", "%d:%s" % (index, long_text))
    stored = chat_store.find_chat(root, chat["id"])
    assert len(stored["transcript"]) == chat_store.MAX_TRANSCRIPT
    assert stored["transcript"][0]["text"] == "2:" + long_text
    assert stored["transcript_trimmed"] == 2


def test_buffered_turn_is_committed_or_discarded_as_one_unit():
    root = tempfile.mkdtemp(prefix="agent_chat_turn_")
    previous = {key: server_state.STATE.get(key) for key in
                ("user_data_dir", "current_chat_id")}
    try:
        chat = chat_store.create_chat(root, title="Turn")
        server_state.STATE.update({"user_data_dir": root,
                                   "current_chat_id": chat["id"]})
        server_state.bind_turn_chat(chat["id"])
        server_state.begin_turn_transcript(chat["id"])
        server_state._remember("user", "failed prompt")
        server_state.discard_turn_transcript()
        assert chat_store.find_chat(root, chat["id"])["transcript"] == []

        server_state.begin_turn_transcript(chat["id"])
        server_state._remember("user", "accepted prompt")
        server_state._remember("agent", "accepted answer")
        server_state.commit_turn_transcript()
        transcript = chat_store.find_chat(root, chat["id"])["transcript"]
        assert [(item["role"], item["text"]) for item in transcript] == [
            ("user", "accepted prompt"), ("agent", "accepted answer")]
    finally:
        server_state.clear_turn_chat()
        server_state.STATE.update(previous)


def test_corrupt_store_fails_closed():
    root = tempfile.mkdtemp(prefix="agent_chat_corrupt_")
    path = os.path.join(root, "agent_chats.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{broken")
    try:
        chat_store.create_chat(root)
    except chat_store.ChatStoreError:
        pass
    else:
        raise AssertionError("corrupt storage must not be treated as an empty chat list")
    with open(path, "r", encoding="utf-8") as handle:
        assert handle.read() == "{broken"


def test_turn_and_navigation_admission_are_exclusive():
    server_state.clear_request_activity()
    assert server_state.try_begin_turn_exchange() is True
    results = []

    def competing_request():
        results.append(server_state.try_begin_turn_exchange())
        results.append(server_state.try_begin_navigation())

    thread = threading.Thread(target=competing_request)
    thread.start()
    thread.join()
    assert results == [False, False]
    assert server_state.exchange_active() is True
    server_state.clear_request_activity()
    assert server_state.exchange_active() is False
    assert server_state.try_begin_navigation() is True
    server_state.clear_request_activity()


def test_transcript_failure_does_not_leave_partial_turn():
    root = tempfile.mkdtemp(prefix="agent_chat_turn_failure_")
    previous = {key: server_state.STATE.get(key) for key in
                ("user_data_dir", "current_chat_id")}
    chat = chat_store.create_chat(root, title="Failure")
    original_append = chat_store.append_transcript_entries
    try:
        server_state.STATE.update({"user_data_dir": root,
                                   "current_chat_id": chat["id"]})
        server_state.bind_turn_chat(chat["id"])
        server_state.begin_turn_transcript(chat["id"])
        server_state._remember("user", "accepted remotely")
        server_state._remember("agent", "visible answer")
        chat_store.append_transcript_entries = lambda *_args, **_kwargs: (_ for _ in ()).throw(IOError("injected"))
        try:
            server_state.commit_turn_transcript()
        except IOError:
            server_state.discard_turn_transcript()
        else:
            raise AssertionError("persistence failure must be observable")
        assert chat_store.find_chat(root, chat["id"])["transcript"] == []
    finally:
        chat_store.append_transcript_entries = original_append
        server_state.clear_turn_chat()
        server_state.STATE.update(previous)


if __name__ == "__main__":
    tests = [test_notes_and_turns_are_chat_scoped,
             test_concurrent_transcript_writes_are_not_lost,
             test_atomic_save_failure_preserves_previous_json,
             test_transcript_trim_keeps_whole_messages,
             test_buffered_turn_is_committed_or_discarded_as_one_unit,
             test_corrupt_store_fails_closed,
             test_turn_and_navigation_admission_are_exclusive,
             test_transcript_failure_does_not_leave_partial_turn]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("PASS: %d tests" % len(tests))
