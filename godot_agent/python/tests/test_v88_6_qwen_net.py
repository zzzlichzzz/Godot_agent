# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v88.5 (хэш-детектор внешних изменений файлов) и v88.6 (сетевой
монитор Qwen).

SSE-образец собран из РЕАЛЬНОГО дампа chat.qwen.ai (пользователь,
23.07.2026): POST /api/v2/chat/completions, text/event-stream; дельты
phase=answer, мысли phase=thinking_summary (НАРАСТАЮЩИЕ списки),
конец — phase=answer + status=finished.
"""
import json
import os
import shutil
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qwen_net import (QwenChatMonitor, decode_qwen_sse_lines,
                      decode_qwen_sse_partial)


def _install_selenium_stub():
    """parser_base импортирует selenium; в тестовой среде его нет — ставим
    заглушку (как в test_v87_9_regen.py / test_v88_0_aistudio.py)."""
    import types
    if "selenium" in sys.modules:
        return
    selenium = types.ModuleType("selenium")
    webdriver = types.ModuleType("selenium.webdriver")
    common = types.ModuleType("selenium.webdriver.common")
    keys_mod = types.ModuleType("selenium.webdriver.common.keys")
    sel_common = types.ModuleType("selenium.common")
    exceptions = types.ModuleType("selenium.common.exceptions")

    class _Keys(object):
        ENTER = u"\ue007"
        CONTROL = u"\ue009"
        SPACE = u" "
        BACKSPACE = u"\ue003"

    keys_mod.Keys = _Keys
    for name in ("WebDriverException", "JavascriptException",
                 "StaleElementReferenceException", "NoSuchWindowException",
                 "TimeoutException"):
        setattr(exceptions, name, type(name, (Exception,), {}))
    sel_common.exceptions = exceptions
    selenium.webdriver = webdriver
    selenium.common = sel_common
    sys.modules.setdefault("selenium", selenium)
    sys.modules.setdefault("selenium.webdriver", webdriver)
    sys.modules.setdefault("selenium.webdriver.common", common)
    sys.modules.setdefault("selenium.webdriver.common.keys", keys_mod)
    sys.modules.setdefault("selenium.common", sel_common)
    sys.modules.setdefault("selenium.common.exceptions", exceptions)


class _FakeCDP(object):
    def on_event(self, *a, **k):
        pass

    def send_command(self, *a, **k):
        return {}

    def is_alive(self):
        return True


def _sse(obj):
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


# дельты ответа — из реального дампа (вкл. разрезанный по чанкам JSON действия)
_ANSWER_CHUNKS = [
    u"\u041f\u0435\u0440\u0435\u0447\u0438\u0442", u"\u044b\u0432\u0430\u044e \u0441",
    u"\u0446\u0435\u043d\u0443, \u0447\u0442\u043e\u0431\u044b", u" \u0443\u0447\u0435\u0441\u0442\u044c \u0430\u043a",
    u"\u0442\u0443\u0430\u043b\u044c\u043d\u044b\u0435 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f \u0432\u043d\u0435",
    u" \u0434\u0438\u0430\u043b\u043e\u0433\u0430.",
    u"\n\n```agent_action", u"\n{\"", u"action\": \"read", u"_file\", \"paths",
    u"\": [\"res://", u"src/scenes/cs", u"2_game.tsc", u"n\"], \"reason",
    u"\": \"\u041f\u043e\u043b", u"\u0443\u0447\u0438\u0442\u044c \u0430\u043a\u0442\u0443",
    u"\u0430\u043b\u044c\u043d\u043e\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u043c",
    u"\u043e\u0435 \u0441\u0446\u0435\u043d\u044b",
    u" \u043f\u043e\u0441\u043b\u0435 \u0435\u0451 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f \u0432\u043d\u0435",
    u" \u0434\u0438\u0430\u043b\u043e\u0433\u0430 \u043f\u0435\u0440\u0435\u0434",
    u" \u043f\u0440\u0430\u0432\u043a\u043e\u0439.\"}",
    u"\n```", u"\n===DONE===", u"", u"",
]
_EXPECTED = u"".join(_ANSWER_CHUNKS)
_THOUGHT_1 = u"\u041c\u044b\u0441\u043b\u044c \u043e\u0434\u0438\u043d."
_THOUGHT_2 = u"\u041c\u044b\u0441\u043b\u044c \u0434\u0432\u0430."


def _build_sse_text():
    parts = [_sse({"response.created": {"chat_id": "x", "parent_id": "p",
                                        "response_id": "r0", "response_index": "0"}})]
    parts.append(_sse({"choices": [{"delta": {
        "role": "assistant", "content": "", "phase": "thinking_summary",
        "extra": {"summary_title": {"content": ["t1"]},
                  "summary_thought": {"content": [_THOUGHT_1]}},
        "status": "typing"}}], "response_id": "r0"}))
    # нарастающий список: второе событие повторяет первую мысль целиком
    parts.append(_sse({"choices": [{"delta": {
        "role": "assistant", "content": "", "phase": "thinking_summary",
        "extra": {"summary_title": {"content": ["t1", "t2"]},
                  "summary_thought": {"content": [_THOUGHT_1, _THOUGHT_2]}},
        "status": "typing"}}], "response_id": "r0"}))
    parts.append(_sse({"choices": [{"delta": {
        "role": "assistant", "content": "", "phase": "thinking_summary",
        "status": "finished"}}], "response_id": "r0"}))
    for ch in _ANSWER_CHUNKS:
        parts.append(_sse({"choices": [{"delta": {
            "role": "assistant", "content": ch, "phase": "answer",
            "status": "typing"}}], "response_id": "r0",
            "usage": {"input_tokens": 1}}))
    parts.append(_sse({"choices": [{"delta": {
        "content": "", "role": "assistant", "status": "finished",
        "phase": "answer"}}], "response_id": "r0"}))
    return u"".join(parts)


def test_sse_full_decode_and_apply():
    mon = QwenChatMonitor(_FakeCDP())
    events = decode_qwen_sse_lines(_build_sse_text())
    assert events, u"события не разобраны"
    for ev in events:
        mon._apply_event(ev)
    assert mon.current_text() == _EXPECTED, repr(mon.current_text()[:120])
    assert mon.is_finished(), u"нет признака завершения"
    assert not mon.is_generating()
    assert mon.assistant_message_count() == 1
    assert _THOUGHT_2 in mon.thought_text()
    assert mon.thought_text().count(_THOUGHT_1) == 1, u"мысли задублировались"
    assert _THOUGHT_1 not in mon.current_text(), u"мысли попали в ответ"


def test_sse_partial_chunks():
    # чанки по 7 байт режут и строки, и многобайтовые UTF-8 символы —
    # проверяем инкрементный разбор с хвостом (как в живом стриме CDP)
    raw = _build_sse_text().encode("utf-8")
    mon = QwenChatMonitor(_FakeCDP())
    buf = bytearray()
    for i in range(0, len(raw), 7):
        buf.extend(raw[i:i + 7])
        events, consumed = mon._decode_frames_partial(bytes(buf))
        if consumed:
            del buf[:consumed]
        for ev in events:
            mon._apply_event(ev)
    assert mon.current_text() == _EXPECTED, repr(mon.current_text()[:120])
    assert mon.is_finished()
    assert not bytes(buf).strip(), u"неразобранный хвост: %r" % bytes(buf[:40])


def test_ignores_service_events():
    mon = QwenChatMonitor(_FakeCDP())
    mon._apply_event({"response.created": {"chat_id": "x"}})
    mon._apply_event({"choices": []})
    mon._apply_event({"choices": [{"delta": None}]})
    mon._apply_event({"choices": [{"delta": {"content": "x", "phase": "web_search", "status": "typing"}}]})
    assert mon.current_text() == ""
    assert not mon.is_finished()


def test_net_text_splits_action():
    _install_selenium_stub()
    from parser_base import split_net_text_and_action
    prose, action_raw = split_net_text_and_action(_EXPECTED)
    assert action_raw and u'"read_file"' in action_raw, repr(action_raw)
    assert u"cs2_game.tscn" in action_raw
    assert prose.startswith(u"\u041f\u0435\u0440\u0435\u0447\u0438\u0442"), repr(prose[:40])
    assert u"```" not in prose and u"===DONE===" not in prose


def test_fs_resave_not_reported():
    # v88.5: Godot пересохранил открытую сцену (новый mtime, то же
    # содержимое) — ложного «файл ИЗМЕНИЛСЯ вне диалога» быть не должно
    import project_tools as pt
    root = tempfile.mkdtemp(prefix="fsdet_")
    try:
        os.makedirs(os.path.join(root, "src", "scenes"))
        p = os.path.join(root, "src", "scenes", "cs2_game.tscn")
        with open(p, "w") as fh:
            fh.write("[gd_scene format=3]\n")
        snap1 = pt.snapshot_files(root)
        st = os.stat(p)
        with open(p, "w") as fh:
            fh.write("[gd_scene format=3]\n")  # то же содержимое
        os.utime(p, (st.st_atime, st.st_mtime + 30))  # но другое mtime
        snap2 = pt.snapshot_files(root, prev=snap1)
        added, changed, deleted = pt.diff_snapshots(snap1, snap2)
        assert (added, changed, deleted) == ([], [], []), (added, changed, deleted)
        # а реальная правка — по-прежнему замечена
        with open(p, "w") as fh:
            fh.write("[gd_scene format=3]\n[node name=\"X\" type=\"Node2D\"]\n")
        snap3 = pt.snapshot_files(root, prev=snap2)
        added, changed, deleted = pt.diff_snapshots(snap2, snap3)
        assert changed == ["src/scenes/cs2_game.tscn"], (added, changed, deleted)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_fs_old_format_snapshot_compat():
    # снапшот старого формата (mtime, size) не роняет сравнение
    import project_tools as pt
    old = {"a.gd": (100, 5)}
    new = {"a.gd": (200, 5, "abc")}
    added, changed, deleted = pt.diff_snapshots(old, new)
    assert changed == ["a.gd"], changed  # без хэша с обеих сторон — по mtime+size


def _run_all():
    tests = [
        test_sse_full_decode_and_apply,
        test_sse_partial_chunks,
        test_ignores_service_events,
        test_net_text_splits_action,
        test_fs_resave_not_reported,
        test_fs_old_format_snapshot_compat,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("OK   %s" % fn.__name__)
        except Exception as e:
            failed += 1
            print("FAIL %s -> %r" % (fn.__name__, e))
            traceback.print_exc()
    if failed:
        print("%d FAILED" % failed)
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    _run_all()
