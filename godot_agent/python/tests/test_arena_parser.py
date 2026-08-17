# -*- coding: utf-8 -*-
import inspect
import base64
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


def test_module_response_carries_battle_choice_summary():
    old_send = arena_module.PARSER.send_message_and_get_response
    old_summary = ArenaParser._last_choice_summary
    summary = {
        "selected": "A", "score_a": 87, "score_b": 85,
        "reason": "higher_score", "other": "B",
    }
    arena_module.PARSER.send_message_and_get_response = (
        lambda *args, **kwargs: {"text": "ok", "action": None})
    ArenaParser._last_choice_summary = summary
    try:
        result = arena_module.send_message_and_get_response(None, "prompt")
        assert result["battle_choice"] == summary
    finally:
        arena_module.PARSER.send_message_and_get_response = old_send
        ArenaParser._last_choice_summary = old_summary


def test_battle_collects_two_separate_post_bodies_as_a_and_b():
    body_a = 'a0:"answer A\\n===DONE==="\nad:{"finishReason":"stop"}\n'
    body_b = ('a0:"answer B\\n```agent_action\\n{\\"action\\":'
              '\\"ask_librarian\\",\\"query\\":\\"player\\"}\\n```\\n===DONE==="\n'
              'ad:{"finishReason":"stop"}\n')

    class CDP:
        def on_event(self, method, callback):
            pass

        def send_command(self, method, params=None):
            raw = body_a if params["requestId"] == "A" else body_b
            return {"bufferedData": base64.b64encode(raw.encode()).decode()}

    mon = ArenaChatMonitor(CDP())
    mon.begin_battle_capture(0)
    for request_id in ("A", "B"):
        mon._on_request_will_be_sent({
            "requestId": request_id,
            "request": {"url": "https://arena.ai/nextjs-api/stream/create-evaluation",
                        "method": "POST"},
        })
        mon._on_response_received({
            "requestId": request_id,
            "response": {"url": "https://arena.ai/nextjs-api/stream/create-evaluation",
                         "mimeType": "text/event-stream"},
        })
    old_sleep = arena_module.time.sleep
    arena_module.time.sleep = lambda seconds: None
    try:
        mon._enable_battle_stream("A")
        mon._enable_battle_stream("B")
        mon._finish_battle_request("A")
        mon._finish_battle_request("B")
    finally:
        arena_module.time.sleep = old_sleep
    assert mon.branch_count() == 2
    variants = dict(mon.branch_variants())
    assert "answer A" in variants[0]
    assert "answer B" in variants[1]
    assert "ask_librarian" in variants[1]
    assert mon.is_finished()


def test_battle_hides_done_until_second_post_arrives():
    mon = ArenaChatMonitor(_CDP())
    mon.begin_battle_capture(0)
    mon._battle_request_ids = ["A"]
    mon._answer_text = "first answer\n===DONE==="
    parser = ArenaParser()
    old_monitor = ArenaParser._monitor
    ArenaParser._monitor = mon
    try:
        parser._ensure_monitor = lambda driver=None: mon
        assert "===DONE===" not in parser.answer_stream(None)
        assert parser.extract_answer(None)["error"] == "Arena Battle: ожидаю второй вариант."
    finally:
        ArenaParser._monitor = old_monitor


def test_battle_does_not_judge_or_fallback_before_stream_finishes():
    class Monitor:
        def is_finished(self):
            return False

        def battle_waiting_for_second_branch(self):
            return False

    parser = ArenaParser()
    monitor = Monitor()
    parser._is_battle_mode = lambda: True
    parser._ensure_monitor = lambda driver=None: monitor
    parser._fresh_network_text = lambda: "partial A\n===DONE==="
    parser._judge_and_apply_choice = lambda driver, mon: (_ for _ in ()).throw(
        AssertionError("Judge must not run for a partial Battle response"))
    old_monitor = ArenaParser._monitor
    ArenaParser._monitor = monitor
    try:
        result = parser.extract_answer(None)
        assert result["error"] == "Arena Battle: оба ответа ещё генерируются."
        assert parser.extract_raw_fallback(None) is None
    finally:
        ArenaParser._monitor = old_monitor


def test_battle_does_not_judge_when_only_one_branch_has_finished():
    mon = ArenaChatMonitor(_CDP())
    mon.begin_battle_capture(0)
    mon._battle_request_ids = ["REQ"]
    mon._battle_request_branches = {"REQ": 0}
    mon._answer_request_count = 1
    mon._branch_texts = {
        0: "A is still streaming",
        1: "B is complete\n===DONE===",
    }
    mon._branch_order = [0, 1]
    mon._answer_text = mon._branch_texts[1]
    # Reproduces the live failure: an early branch-level done signal marked
    # the generic state finished while the multiplexed response was still open.
    mon._finished = True
    mon._generating = False

    parser = ArenaParser()
    parser._is_battle_mode = lambda: True
    parser._ensure_monitor = lambda driver=None: mon
    parser._judge_and_apply_choice = lambda driver, monitor: (_ for _ in ()).throw(
        AssertionError("Judge must wait for the complete Battle response"))
    old_monitor = ArenaParser._monitor
    old_before = ArenaParser._req_count_before_send
    ArenaParser._monitor = mon
    ArenaParser._req_count_before_send = 0
    try:
        assert mon.is_generating()
        assert not mon.battle_ready_for_judge()
        assert "===DONE===" not in parser.answer_stream(None)
        result = parser.extract_answer(None)
        assert result["error"] == "Arena Battle: оба ответа ещё генерируются."
        assert parser.net_answer_ready(None) is False
        assert parser.extract_raw_fallback(None) is None
    finally:
        ArenaParser._monitor = old_monitor
        ArenaParser._req_count_before_send = old_before


def test_battle_falls_back_to_finished_single_post_with_a0_and_a1():
    raw = ('a0:"answer A"\na1:"answer B"\nad:{"finishReason":"stop"}\n')

    class CDP:
        def on_event(self, method, callback):
            pass

        def send_command(self, method, params=None):
            if method == "Network.streamResourceContent":
                raise RuntimeError("already finished")
            return {"body": raw, "base64Encoded": False}

    mon = ArenaChatMonitor(CDP())
    mon.begin_battle_capture(0)
    mon._on_request_will_be_sent({
        "requestId": "A", "request": {"method": "POST",
        "url": "https://arena.ai/nextjs-api/stream/create-evaluation"}})
    mon._on_response_received({
        "requestId": "A", "response": {"mimeType": "text/event-stream",
        "url": "https://arena.ai/nextjs-api/stream/create-evaluation"}})
    old_sleep = arena_module.time.sleep
    arena_module.time.sleep = lambda seconds: None
    try:
        mon._finish_battle_request("A")
    finally:
        arena_module.time.sleep = old_sleep
    assert mon.branch_variants() == [(0, "answer A"), (1, "answer B")]
    assert mon.is_finished()
    assert mon.battle_ready_for_judge()


def test_direct_and_battle_sites_share_parser_but_have_distinct_urls():
    import sites
    direct = sites.get_site("arena")
    battle = sites.get_site("arena_battle")
    assert direct["parser"] == battle["parser"] == "arena_parser"
    assert direct["new_chat_url"] == "https://arena.ai/text/direct"
    assert battle["new_chat_url"] == "https://arena.ai/text"
    listed = {item["id"]: item for item in sites.list_sites()}
    assert listed["arena"]["name"] == "Arena AI Direct"
    assert listed["arena_battle"]["name"] == "Arena AI Battle"


def test_json_string_decoding():
    raw = 'a0:"строка 1\\nОн сказал: \\"Привет\\" \\\\ путь"\n'
    events = decode_arena_stream_lines(raw)
    assert events == [{
        "kind": "text", "stream": 0,
        "text": 'строка 1\nОн сказал: "Привет" \\ путь',
    }]


def test_battle_b0_is_variant_b_and_bd_finishes():
    events = decode_arena_stream_lines(
        'a0:"ответ A"\nb0:"ответ B"\n'
        'bd:{"finishReason":"stop"}\n')
    assert events == [
        {"kind": "text", "stream": 0, "text": "ответ A"},
        {"kind": "text", "stream": 1, "text": "ответ B"},
        {"kind": "done", "meta": {"finishReason": "stop"}},
    ]


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


def test_first_battle_submit_enables_battle_capture_before_enter():
    import server_state
    events = []

    class Monitor:
        def chat_request_count(self):
            return 3

        def begin_battle_capture(self, before):
            events.append(("battle", before))

        def end_battle_capture(self):
            events.append(("direct", None))

    class Element:
        def send_keys(self, *keys):
            events.append(("enter", None))

    class Driver:
        current_url = "https://arena.ai/text"

    parser = ArenaParser()
    parser._ensure_monitor = lambda driver=None: Monitor()
    parser._arena_targets = lambda: {}
    parser._follow_first_chat_transition = lambda *args: None
    old_site_id = server_state.STATE.get("current_site_id")
    try:
        parser.submit(Driver(), Element())
        assert events == [("battle", 3), ("enter", None)]
    finally:
        server_state.STATE["current_site_id"] = old_site_id


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


def test_battle_choice_buttons_use_current_site_mode():
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
            return self.buttons

    parser = ArenaParser()
    buttons = [Button("A лучше"), Button("Оба хорошие"), Button("Оба плохие"), Button("B лучше")]
    old_is_battle = parser._is_battle_mode
    try:
        parser._is_battle_mode = lambda: True
        assert parser._click_choice_button(Driver(buttons), "both_good")
        assert [button.clicked for button in buttons] == [False, True, False, False]
        for button in buttons:
            button.clicked = False
        assert parser._click_choice_button(Driver(buttons), "both_bad")
        assert [button.clicked for button in buttons] == [False, False, True, False]
    finally:
        parser._is_battle_mode = old_is_battle


def test_battle_both_bad_votes_without_waiting_for_third_answer():
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
            return self.buttons

    class Monitor:
        def answer_request_count(self):
            return 12

        def branch_count(self):
            return 2

    parser = ArenaParser()
    parser._is_battle_mode = lambda: True
    parser._project_judgments = lambda mon: (
        0, "A", {"score": 10, "acceptable": False},
        [(0, {"score": 10, "acceptable": False,
              "blocking": [{"message": "A invalid"}], "warnings": []}),
         (1, {"score": 20, "acceptable": False,
              "blocking": [{"message": "B invalid"}], "warnings": []})],
    )
    buttons = [Button("A лучше"), Button("Оба хорошие"),
               Button("Оба плохие"), Button("B лучше")]
    old_pending = ArenaParser._skip_pending
    ArenaParser._skip_pending = False
    try:
        result = parser._judge_and_apply_choice(Driver(buttons), Monitor())
        assert result.startswith("reject:")
        assert buttons[2].clicked
        assert ArenaParser._skip_pending is False
    finally:
        ArenaParser._skip_pending = old_pending


def test_battle_plain_answers_are_returned_without_arena_vote():
    class Monitor:
        def __init__(self):
            self.selected = None

        def answer_request_count(self):
            return 13

        def branch_count(self):
            return 2

        def select_stream(self, stream):
            self.selected = stream
            return True

    parser = ArenaParser()
    parser._is_battle_mode = lambda: True
    parser._project_judgments = lambda mon: (
        0, "plain A", {"score": 74, "acceptable": True,
                       "vote_eligible": False},
        [(0, {"score": 74, "acceptable": True, "vote_eligible": False,
              "blocking": [], "warnings": [], "evidence": []}),
         (1, {"score": 74, "acceptable": True, "vote_eligible": False,
              "blocking": [], "warnings": [], "evidence": []})],
    )
    clicks = []
    parser._click_choice_button = lambda driver, choice: clicks.append(choice) or True
    monitor = Monitor()

    result = parser._judge_and_apply_choice(object(), monitor)

    assert result == "no_vote"
    assert monitor.selected == 0
    assert clicks == []
    assert ArenaParser._last_choice_summary == {
        "selected": "A", "score_a": 74, "score_b": 74,
        "reason": "not_verifiable", "other": "B",
    }


def test_battle_action_tie_votes_both_good_and_selects_a_locally():
    class Monitor:
        def __init__(self):
            self.selected = None

        def answer_request_count(self):
            return 14

        def branch_count(self):
            return 2

        def select_stream(self, stream):
            self.selected = stream
            return True

    result = {"score": 90, "acceptable": True, "vote_eligible": True,
              "blocking": [], "warnings": [], "evidence": []}
    parser = ArenaParser()
    parser._is_battle_mode = lambda: True
    parser._project_judgments = lambda mon: (
        0, "action A", result, [(0, dict(result)), (1, dict(result))])
    clicks = []
    parser._click_choice_button = lambda driver, choice: clicks.append(choice) or True
    monitor = Monitor()

    selection = parser._judge_and_apply_choice(object(), monitor)

    assert selection == "choice"
    assert monitor.selected == 0
    assert clicks == ["both_good"]
    assert ArenaParser._last_choice_summary == {
        "selected": "A", "score_a": 90, "score_b": 90,
        "reason": "equal", "other": "B",
    }


def test_battle_choice_summary_explains_required_continuation():
    parser = ArenaParser()
    parser._remember_choice_summary(0, [
        (0, {"score": 87, "action": {"action": "plan"}}),
        (1, {"score": 85, "action": {"action": "plan", "continues": True}}),
    ], "higher_score")

    assert ArenaParser._last_choice_summary == {
        "selected": "A", "score_a": 87, "score_b": 85,
        "reason": "other_continues", "other": "B",
    }


def test_two_unacceptable_variants_click_skip():
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
            return self.buttons

    class Monitor:
        def answer_request_count(self):
            return 5

        def chat_request_count(self):
            return 5

        def branch_count(self):
            return 2

    parser = ArenaParser()
    parser._project_judgments = lambda mon: (
        0, "A", {"score": 20, "acceptable": False, "blocking": [{}]},
        [(0, {"score": 20, "acceptable": False, "blocking": [{}], "warnings": []}),
         (1, {"score": 30, "acceptable": False, "blocking": [{}], "warnings": []})],
    )
    buttons = [Button("Продолжить с A"), Button("Пропустить"),
               Button("Продолжить с B")]
    old_pending = ArenaParser._skip_pending
    old_origin = ArenaParser._skip_origin_request
    old_before = ArenaParser._req_count_before_send
    ArenaParser._skip_pending = False
    try:
        result = parser._judge_and_apply_choice(Driver(buttons), Monitor())
        assert result == "skip"
        assert [button.clicked for button in buttons] == [False, True, False]
        assert ArenaParser._skip_pending
        assert ArenaParser._skip_origin_request == 5
    finally:
        ArenaParser._skip_pending = old_pending
        ArenaParser._skip_origin_request = old_origin
        ArenaParser._req_count_before_send = old_before


def test_incomplete_battle_response_still_uses_battle_vote():
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
            return self.buttons

    class Monitor:
        def answer_request_count(self):
            return 17

        def branch_count(self):
            return 1

        def current_text(self):
            return "valid answer"

    parser = ArenaParser()
    parser._is_battle_mode = lambda: True
    parser._judge_single_current_answer = lambda mon: {"acceptable": True}
    buttons = [Button("A лучше"), Button("Оба хорошие"),
               Button("Оба плохие"), Button("B лучше")]
    old_applied = ArenaParser._choice_applied_for_request
    ArenaParser._choice_applied_for_request = None
    try:
        assert parser._judge_and_apply_choice(Driver(buttons), Monitor()) == "choice"
        assert buttons[0].clicked
    finally:
        ArenaParser._choice_applied_for_request = old_applied


def test_old_ab_is_hidden_while_waiting_for_c():
    class CDP:
        def is_alive(self):
            return True

    class Monitor:
        _cdp = CDP()

        def answer_request_count(self):
            return 5

        def current_text(self):
            return "old A"

        def is_finished(self):
            return True

    parser = ArenaParser()
    old_monitor = ArenaParser._monitor
    old_pending = ArenaParser._skip_pending
    old_origin = ArenaParser._skip_origin_request
    old_before = ArenaParser._req_count_before_send
    ArenaParser._monitor = Monitor()
    ArenaParser._skip_pending = True
    ArenaParser._skip_origin_request = 5
    ArenaParser._req_count_before_send = 5
    try:
        assert parser._fresh_network_text() is None
        assert parser.net_answer_ready(None) is False
    finally:
        ArenaParser._monitor = old_monitor
        ArenaParser._skip_pending = old_pending
        ArenaParser._skip_origin_request = old_origin
        ArenaParser._req_count_before_send = old_before


def run_all():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("All Arena tests passed: %d" % len(tests))


if __name__ == "__main__":
    run_all()
