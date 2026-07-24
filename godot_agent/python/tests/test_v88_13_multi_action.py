# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""v88.13: qwen (и любой сайт, использующий split_net_text_and_action) иногда присылает
НЕСКОЛЬКО отдельных ```agent_action блоков вместо одного action=plan.
Раньше выживал только один блок (последний в сетевом пути, первый в DOM-пути),
остальные молча терялись. Этот тест воспроизводит реальный инцидент из лога
пользователя (3 patch_file подряд) и проверяет слияние в один план.
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_selenium_stub():
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


_install_selenium_stub()

import parser_base
import qwen_parser

_FAILS = []


def _check(name, cond, detail=""):
    if cond:
        print("OK   %s" % name)
    else:
        print("FAIL %s -> %s" % (name, detail))
        _FAILS.append(name)


def _block(path, search, replace, summary):
    return json.dumps({
        "action": "patch_file",
        "path": path,
        "search": search,
        "replace": replace,
        "summary": summary,
    }, ensure_ascii=False)


def test_three_separate_blocks_merge_into_plan():
    """Реплей инцидента: 3 отдельных ```agent_action блока в одном сетевом
    ответе должны собраться в один план из 3 шагов, а не отбросить первые два."""
    b1 = _block("res://a.gd", "s1", "r1", "collision_mask")
    b2 = _block("res://a.gd", "s2", "r2", "self collision check + muzzle flash call")
    b3 = _block("res://a.gd", "s3", "r3", "muzzle flash + tracer resize")
    full_text = (
        "Проблемы с трассерами:\n1. ...\n2. ...\n3. ...\n\n"
        "Применю комплексное исправление:\n\n"
        "```agent_action\n%s\n```\n\n"
        "```agent_action\n%s\n```\n\n"
        "```agent_action\n%s\n```\n\n===DONE===" % (b1, b2, b3)
    )
    text, action_raw = parser_base.split_net_text_and_action(full_text)
    _check("three_blocks: action_raw is not None", action_raw is not None)
    obj, err = parser_base.parse_action_json(action_raw)
    _check("three_blocks: parses without error", err is None, err)
    _check("three_blocks: synthesized as plan", obj.get("action") == "plan", obj)
    steps = obj.get("steps") or []
    _check("three_blocks: all 3 steps present", len(steps) == 3, len(steps))
    _check("three_blocks: step order preserved",
           [s.get("summary") for s in steps] == ["collision_mask",
                                                   "self collision check + muzzle flash call",
                                                   "muzzle flash + tracer resize"],
           [s.get("summary") for s in steps])
    _check("three_blocks: prose has no leftover agent_action fences",
           "agent_action" not in text, text)
    _check("three_blocks: DONE marker stripped", "DONE" not in text, text)


def test_single_block_unchanged():
    """Один блок всё ещё возвращается как одиночное действие (не обёрнуто
    в план) — старые одношаговые ответы не должны изменить поведение."""
    b1 = _block("res://a.gd", "s1", "r1", "only one")
    full_text = "Готово:\n\n```agent_action\n%s\n```\n\n===DONE===" % b1
    text, action_raw = parser_base.split_net_text_and_action(full_text)
    obj, err = parser_base.parse_action_json(action_raw)
    _check("single_block: no error", err is None, err)
    _check("single_block: still plain action (not wrapped in plan)",
           obj.get("action") == "patch_file", obj)


def test_one_bad_block_falls_back_to_last():
    """Если один из нескольких блоков — не валидное действие, слияние НЕ должно
    произойти — возвращаемся к прежнему поведению (последний блок)."""
    b1 = _block("res://a.gd", "s1", "r1", "good one")
    bad = "{not json at all"
    full_text = "```agent_action\n%s\n```\n\n```agent_action\n%s\n```" % (bad, b1)
    text, action_raw = parser_base.split_net_text_and_action(full_text)
    obj, err = parser_base.parse_action_json(action_raw)
    _check("bad_block: falls back, still parses the LAST block",
           err is None and obj.get("action") == "patch_file" and obj.get("summary") == "good one",
           (err, obj))


def test_nested_plan_block_not_merged():
    """Если один из блоков сам — уже action=plan, не пытаемся склеивать вложенные
    планы — безопаснее откатиться к прежнему поведению."""
    b1 = _block("res://a.gd", "s1", "r1", "first")
    plan_block = json.dumps({"action": "plan", "steps": [json.loads(b1)]}, ensure_ascii=False)
    full_text = "```agent_action\n%s\n```\n\n```agent_action\n%s\n```" % (b1, plan_block)
    text, action_raw = parser_base.split_net_text_and_action(full_text)
    obj, err = parser_base.parse_action_json(action_raw)
    _check("nested_plan: falls back to last block (the plan itself)",
           err is None and obj.get("action") == "plan", (err, obj))


def test_dom_path_merges_fenceless_blocks():
    """DOM-путь qwen (_action_raw_from_text): составной текст без оград ```
    с несколькими JSON-блоками подряд тоже должен собраться в план, а не
    отдать только ПЕРВЫЙ блок."""
    b1 = _block("res://a.gd", "s1", "r1", "first fix")
    b2 = _block("res://a.gd", "s2", "r2", "second fix")
    text = "Прочитал код.\n%s\n%s\n===DONE===" % (b1, b2)
    raw = qwen_parser._action_raw_from_text(text)
    _check("dom_multi: got a raw candidate", raw is not None)
    obj, err = parser_base.parse_action_json(raw)
    _check("dom_multi: parses without error", err is None, err)
    _check("dom_multi: synthesized as plan with both steps",
           obj.get("action") == "plan" and len(obj.get("steps") or []) == 2,
           obj)


def test_dom_path_single_block_still_supports_refs_tail():
    """Старый случай (один блок) не должен сломаться — по-прежнему возвращается
    весь хвост текста после первой '{' (там могут жить тела ===МЕТОК===)."""
    b1 = _block("res://a.gd", "s1", "r1", "only")
    text = "%s\n===SOME_LABEL===\nbody\n===END_SOME_LABEL===\n===DONE===" % b1
    raw = qwen_parser._action_raw_from_text(text)
    _check("dom_single: raw extends to end of text (ref tail preserved)",
           raw is not None and "END_SOME_LABEL" in raw, raw)


def _run_all():
    test_three_separate_blocks_merge_into_plan()
    test_single_block_unchanged()
    test_one_bad_block_falls_back_to_last()
    test_nested_plan_block_not_merged()
    test_dom_path_merges_fenceless_blocks()
    test_dom_path_single_block_still_supports_refs_tail()
    if _FAILS:
        print("FAILED: %s" % ", ".join(_FAILS))
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    _run_all()
