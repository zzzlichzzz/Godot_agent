# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v104.1: параллельные варианты ответа qwen (Response 1/Response 2).

Воспроизводит багрепорт 23.07.2026: в панель агента уезжала посимвольная
каша из двух ответов сразу («Прagent_action {"action": "readочитаю сцену
HUD,_file…»): дельты обоих вариантов склеивались в один буфер без учёта
response_id.
"""
import sys
import traceback

from qwen_net import QwenChatMonitor


class _FakeCDP(object):
    def __init__(self):
        self.handlers = {}

    def on_event(self, name, cb):
        self.handlers[name] = cb

    def send_command(self, method, params=None):
        return {}

    def is_alive(self):
        return True


def _created(rid, index):
    return {"response.created": {"chat_id": "c", "parent_id": "p",
                                 "response_id": rid, "response_index": index}}


def _delta(rid, content, status="typing", phase="answer"):
    return {"choices": [{"delta": {"role": "assistant", "content": content,
                                   "phase": phase, "status": status}}],
            "response_id": rid}


_R1 = [u"Прочитаю сцену HUD,", u" чтобы понять структуру.",
       u"\n```agent_action\n",
       u'{"action": "list_scene", "path": "res://src/scenes/AI/hud.tscn"}',
       u"\n```\n===DONE==="]
_R2 = [u'```agent_action {"action": "read', u'_file", "paths": ["res://',
       u'src/scenes/AI/hud.tscn"]}', u"```"]


def test_dual_interleaved_shows_only_first():
    """Дельты двух вариантов вперемешку — наружу только Response 1."""
    mon = QwenChatMonitor(_FakeCDP())
    mon._apply_event(_created("r0", "0"))
    mon._apply_event(_created("r1", "1"))
    n = max(len(_R1), len(_R2))
    for i in range(n):
        if i < len(_R1):
            mon._apply_event(_delta("r0", _R1[i]))
        if i < len(_R2):
            mon._apply_event(_delta("r1", _R2[i]))
    mon._apply_event(_delta("r1", "", status="finished"))
    assert mon.current_text() == u"".join(_R1), repr(mon.current_text()[:120])
    assert u"read_file" not in mon.current_text()
    # завершился только ВТОРОЙ вариант — главный ещё пишется
    assert not mon.is_finished()
    mon._apply_event(_delta("r0", "", status="finished"))
    assert mon.is_finished()
    assert mon.current_text() == u"".join(_R1)
    assert mon.assistant_message_count() == 1


def test_second_variant_first_then_primary_wins():
    """Response 2 начал писать РАНЬШЕ — после появления Response 1 побеждает он."""
    mon = QwenChatMonitor(_FakeCDP())
    mon._apply_event(_created("r1", "1"))
    mon._apply_event(_delta("r1", u"вариант два"))
    assert mon.current_text() == u"вариант два"  # пока он единственный
    mon._apply_event(_created("r0", "0"))
    mon._apply_event(_delta("r0", u"вариант один"))
    assert mon.current_text() == u"вариант один"
    mon._apply_event(_delta("r1", u" дописался", status="finished"))
    assert not mon.is_finished()
    mon._apply_event(_delta("r0", u" и ещё", status="finished"))
    assert mon.is_finished()
    assert mon.current_text() == u"вариант один и ещё"


def test_old_format_without_response_id():
    """События без response_id — поведение как раньше (один вариант)."""
    mon = QwenChatMonitor(_FakeCDP())
    mon._apply_event({"choices": [{"delta": {"content": u"привет",
                                             "phase": "answer",
                                             "status": "typing"}}]})
    mon._apply_event({"choices": [{"delta": {"content": u" мир",
                                             "phase": "answer",
                                             "status": "finished"}}]})
    assert mon.current_text() == u"привет мир"
    assert mon.is_finished()
    assert mon.assistant_message_count() == 1


def test_thoughts_follow_primary():
    """Мысли тоже берутся только из главного варианта."""
    mon = QwenChatMonitor(_FakeCDP())
    mon._apply_event(_created("r0", "0"))
    mon._apply_event(_created("r1", "1"))
    mon._apply_event({"choices": [{"delta": {
        "content": "", "phase": "thinking_summary",
        "extra": {"summary_thought": {"content": [u"мысль варианта 2"]}},
        "status": "typing"}}], "response_id": "r1"})
    mon._apply_event({"choices": [{"delta": {
        "content": "", "phase": "thinking_summary",
        "extra": {"summary_thought": {"content": [u"мысль варианта 1"]}},
        "status": "typing"}}], "response_id": "r0"})
    mon._apply_event(_delta("r0", u"текст"))
    assert mon.thought_text() == u"мысль варианта 1"


if __name__ == "__main__":
    failed = 0
    for fn in (test_dual_interleaved_shows_only_first,
               test_second_variant_first_then_primary_wins,
               test_old_format_without_response_id,
               test_thoughts_follow_primary):
        try:
            fn()
            print("OK   %s" % fn.__name__)
        except Exception:
            failed += 1
            print("FAIL %s" % fn.__name__)
            traceback.print_exc()
    sys.exit(1 if failed else 0)
