# -*- coding: utf-8 -*-
import inspect
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import arena_parser as arena_module
from arena_parser import (ArenaChatMonitor, ArenaParser,
                          decode_arena_stream_lines,
                          decode_arena_stream_partial)


CAPTURE = (
    'a0:"вопросы "\n'
    'a0:"— "\n'
    'a0:"обращайтесь. "\n'
    'a0:"😊"\n'
    'ad:{"finishReason":"stop"}\n'
).encode("utf-8")


class _CDP:
    def on_event(self, method, callback):
        pass

    def is_alive(self):
        return True


def _apply_capture(raw=CAPTURE):
    mon = ArenaChatMonitor(_CDP())
    for event in mon._decode_frames(raw):
        mon._apply_event(event)
    return mon


def test_exact_capture_text():
    mon = _apply_capture()
    assert mon.current_text() == "вопросы — обращайтесь. 😊"
    assert mon.is_finished()
    assert mon.message_status() == "FINISHED"
    assert mon.assistant_message_count() == 1


def test_monitor_matches_first_and_followup_endpoints():
    mon = ArenaChatMonitor(_CDP())
    assert mon._match_request(
        "https://arena.ai/nextjs-api/stream/create-evaluation", "POST")
    assert mon._match_request(
        "https://arena.ai/nextjs-api/stream/post-to-evaluation/chat-id", "POST")
    assert not mon._match_request("https://arena.ai/rpc/i/v0/e/", "POST")


def test_json_string_decoding():
    raw = 'a0:"строка 1\\nОн сказал: \\"Привет\\" \\\\ путь"\n'
    events = decode_arena_stream_lines(raw)
    assert events == [{
        "kind": "text", "stream": 0,
        "text": 'строка 1\nОн сказал: "Привет" \\ путь',
    }]


def test_arbitrary_utf8_splits():
    for size in (1, 2, 3, 7, 16, 64):
        buf = bytearray()
        events = []
        for pos in range(0, len(CAPTURE), size):
            buf.extend(CAPTURE[pos:pos + size])
            fresh, consumed = decode_arena_stream_partial(buf)
            events.extend(fresh)
            del buf[:consumed]
        assert not buf
        mon = ArenaChatMonitor(_CDP())
        for event in events:
            mon._apply_event(event)
        assert mon.current_text() == "вопросы — обращайтесь. 😊"


def test_final_tail_without_newline():
    mon = ArenaChatMonitor(_CDP())
    for event in mon._decode_final_tail('a0:"хвост"'.encode("utf-8")):
        mon._apply_event(event)
    assert mon.current_text() == "хвост"


def test_additional_stream_is_not_mixed():
    raw = ('a1:"чужой"\na0:"наш"\nad:{"finishReason":"stop"}\n'
           ).encode("utf-8")
    mon = _apply_capture(raw)
    assert mon.current_text() in ("чужой", "наш")
    assert mon.current_text() not in ("чужойнаш", "нашчужой")


def test_dual_response_selects_valid_agent_action():
    weaker = "Просто описание без действия\n===DONE==="
    better = ('Выполняю.\n```agent_action\n'
              '{"action":"read_file","paths":["res://project.godot"]}\n'
              '```\n===DONE===')
    raw = ("a0:%s\na1:%s\nad:{\"finishReason\":\"stop\"}\n"
           % (json.dumps(weaker, ensure_ascii=False),
              json.dumps(better, ensure_ascii=False))).encode("utf-8")
    mon = _apply_capture(raw)
    assert mon.branch_count() == 2
    assert mon.selected_stream() == 1
    assert mon.current_text() == better


def test_dual_response_tie_keeps_a():
    raw = ('a0:"одинаково"\na1:"одинаково"\n'
           'ad:{"finishReason":"stop"}\n').encode("utf-8")
    mon = _apply_capture(raw)
    assert mon.selected_stream() == 0


def test_base_contracts_and_network_only_source():
    parser = ArenaParser()
    assert list(inspect.signature(parser.submit).parameters) == ["driver", "el"]
    parser._ensure_monitor = lambda driver=None: None
    result = parser.extract_answer(object())
    assert isinstance(result, dict)
    assert set(("text", "actionRaw", "error")).issubset(result)
    source = inspect.getsource(ArenaParser)
    assert "Like this response" not in source
    assert "_JS_GET_ANSWER" not in source
    assert "execute_script" not in inspect.getsource(ArenaParser.insert_input_paste_like)
    assert ".clear()" not in inspect.getsource(ArenaParser.insert_input_paste_like)
    assert parser.SEND_RETRIES == 0


def test_trusted_clear_uses_cdp_select_all_and_backspace():
    class Element:
        value = "old text"

        def click(self):
            pass

        def send_keys(self, *keys):
            raise AssertionError("Selenium fallback should not be needed")

    class Driver:
        def __init__(self, element):
            self.element = element
            self.commands = []

        def execute_cdp_cmd(self, method, params):
            self.commands.append((method, params))
            if params.get("key") == "Backspace" and params.get("type") == "keyDown":
                self.element.value = ""

        def execute_script(self, script, element):
            return element.value

    parser = ArenaParser()
    element = Element()
    driver = Driver(element)
    assert parser._clear_input_trusted(driver, element)
    keys = [params.get("key") for _, params in driver.commands
            if params.get("type") == "keyDown"]
    assert keys == ["a", "Backspace"]


def test_window_selection_never_flashes_unrelated_tabs():
    class Switch:
        def __init__(self, driver):
            self.driver = driver

        def window(self, handle):
            self.driver.switches.append(handle)
            self.driver.current_window_handle = handle
            self.driver.current_url = self.driver.urls[handle]

    class Driver:
        def __init__(self):
            self.window_handles = ["TEST", "ARENA_CURRENT", "ARENA_OTHER"]
            self.current_window_handle = "ARENA_CURRENT"
            self.urls = {
                "TEST": "https://aistudio.google.com/prompts/test",
                "ARENA_CURRENT": "https://arena.ai/c/current",
                "ARENA_OTHER": "https://arena.ai/c/other",
            }
            self.current_url = self.urls[self.current_window_handle]
            self.switches = []
            self.switch_to = Switch(self)

    targets = [
        {"type": "page", "id": handle, "url": url}
        for handle, url in Driver().urls.items()
    ]
    original = arena_module.list_targets
    arena_module.list_targets = lambda: targets
    try:
        parser = ArenaParser()
        driver = Driver()
        parser.switch_to_site_window(driver, prefer_url="https://arena.ai/c/missing")
        assert driver.switches == []

        parser.switch_to_site_window(driver, prefer_url="https://arena.ai/c/other")
        assert driver.switches == ["ARENA_OTHER"]
        assert "TEST" not in driver.switches
    finally:
        arena_module.list_targets = original


def test_confirm_sent_accepts_delayed_post_after_composer_clears():
    class Monitor:
        def chat_request_count(self):
            return 10

    class Element:
        value = ""

    class Driver:
        def execute_script(self, script, element):
            return element.value

    parser = ArenaParser()
    old_monitor = ArenaParser._monitor
    old_before = ArenaParser._req_count_before_send
    old_time = arena_module.time.time
    old_sleep = arena_module.time.sleep
    ticks = [0.0]
    arena_module.time.time = lambda: ticks[0]
    arena_module.time.sleep = lambda seconds: ticks.__setitem__(0, ticks[0] + seconds)
    ArenaParser._monitor = Monitor()
    ArenaParser._req_count_before_send = 10
    try:
        assert parser.confirm_sent(Driver(), Element()) is True
        assert ticks[0] >= 1.0
        assert ticks[0] < 60.0
    finally:
        ArenaParser._monitor = old_monitor
        ArenaParser._req_count_before_send = old_before
        arena_module.time.time = old_time
        arena_module.time.sleep = old_sleep


def test_first_direct_chat_moves_monitor_to_new_target():
    class CDP:
        def is_alive(self):
            return True

        def close(self):
            pass

    class Monitor:
        def __init__(self, target_id):
            self._arena_target_id = target_id
            self._cdp = CDP()

        def chat_request_count(self):
            return 0

        def assistant_message_count(self):
            return 0

    class Switch:
        def __init__(self, driver):
            self.driver = driver

        def window(self, handle):
            self.driver.current_window_handle = handle
            self.driver.switches.append(handle)

    class Driver:
        def __init__(self):
            self.window_handles = ["old", "new"]
            self.current_window_handle = "old"
            self.switches = []
            self.switch_to = Switch(self)

    parser = ArenaParser()
    old_monitor = ArenaParser._monitor
    old_targets = parser._arena_targets
    old_connect = parser._connect_monitor
    old_time = arena_module.time.time
    old_sleep = arena_module.time.sleep
    ticks = [0.0]
    connected = []
    calls = [0]

    def targets():
        calls[0] += 1
        result = {"old": {"id": "OLD", "type": "page",
                          "url": "https://arena.ai/text/direct"}}
        if calls[0] >= 2:
            result["new"] = {"id": "NEW", "type": "page",
                             "url": "https://arena.ai/c/chat-id"}
        return result

    def connect(target_id, old=None):
        connected.append(target_id)
        return Monitor(target_id)

    ArenaParser._monitor = Monitor("old")
    parser._arena_targets = targets
    parser._connect_monitor = connect
    arena_module.time.time = lambda: ticks[0]
    arena_module.time.sleep = lambda seconds: ticks.__setitem__(0, ticks[0] + seconds)
    try:
        driver = Driver()
        parser._follow_first_chat_transition(driver, {"old"}, 0)
        assert connected == ["new"]
        assert ArenaParser._monitor._arena_target_id == "new"
        assert driver.current_window_handle == "new"
        assert driver.switches == ["new"]
    finally:
        ArenaParser._monitor = old_monitor
        parser._arena_targets = old_targets
        parser._connect_monitor = old_connect
        arena_module.time.time = old_time
        arena_module.time.sleep = old_sleep


def test_selected_b_clicks_continue_with_b_web_element():
    class Button:
        def __init__(self, text):
            self.text = text
            self.clicked = False

        def is_displayed(self):
            return True

        def is_enabled(self):
            return True

        def click(self):
            self.clicked = True

    class Driver:
        def __init__(self, buttons):
            self.buttons = buttons

        def find_elements(self, by, value):
            assert value == "button"
            return self.buttons

    class Monitor:
        def branch_count(self):
            return 2

        def answer_request_count(self):
            return 91

        def selected_stream(self):
            return 1

    buttons = [Button("Продолжить с A"), Button("Пропустить"),
               Button("Продолжить с B")]
    parser = ArenaParser()
    old_applied = ArenaParser._choice_applied_for_request
    ArenaParser._choice_applied_for_request = None
    try:
        assert parser._apply_selected_choice(Driver(buttons), Monitor())
        assert [button.clicked for button in buttons] == [False, False, True]
    finally:
        ArenaParser._choice_applied_for_request = old_applied


def run_all():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("All Arena tests passed: %d" % len(tests))


if __name__ == "__main__":
    run_all()
