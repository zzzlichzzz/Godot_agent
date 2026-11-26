"""Measure the real wait/settle path without a provider session or wall clock."""
from importlib import import_module

import pytest

from tests.py.browser.runtime_cases import Clock, references


def wait(use_delivery, monkeypatch, *, first='New answer\n===DONE===', changed=None,
         change_at=0, generating_until=0, raw=None, height=0, old=False, wrapped=False):
    clock = Clock()

    class Driver:
        def execute_script(self, script, *args):
            text = changed if changed is not None and clock.now >= change_at else first
            if script == deepseek_parser.JS_EXTRACT:
                return dict(text=text, actionRaw=raw, error=None, blockHeight=height)
            if script == deepseek_parser.JS_IS_GENERATING:
                return clock.now < generating_until
            if 'range.getClientRects()' in script:
                return wrapped
            if script == deepseek_parser.JS_COUNT_ANSWERS:
                return 1 if old and text == first else 2
            if script == deepseek_parser.JS_ANSWER_LEN:
                return len(text)
            if script in (deepseek_parser.JS_ANSWER_STREAM, deepseek_parser.JS_ANSWER_PREVIEW):
                return text
            return None

    with references() as modules, monkeypatch.context() as mp:
        deepseek_parser = modules['deepseek_parser']
        mp.setattr(modules['parser_base'], 'time', clock)
        mp.setattr(deepseek_parser, 'time', clock)
        driver = Driver()
        if use_delivery:
            delivery = import_module('python.substrate.llm.parsers.deepseek_delivery')
            parser = delivery.DeepSeekDelivery(driver)
        else:
            parser = deepseek_parser.DeepSeekParser()
        result = parser.wait_for_new_answer(driver, 1, timeout=120,
                                            baseline={'text': first if old else 'old'})
    return result, clock


def test_idle_text_with_done_avoids_full_reference_settle_delay(monkeypatch):
    before, reference = wait(False, monkeypatch)
    after, delivery = wait(True, monkeypatch)
    assert after == before
    assert reference.sleeps.count(2.0) == 2
    assert reference.now == pytest.approx(4.4)
    assert delivery.now == pytest.approx(1.0)


@pytest.mark.parametrize('opts', [
    {'first': 'New answer without marker'},
    {'generating_until': 0.75, 'changed': 'Final answer\n===DONE===', 'change_at': 0.75},
    {'changed': 'Updated DOM\n===DONE===', 'change_at': 0.1},
    {'raw': '{"action":"read_file","path":"res://main.gd"}'},
    {'old': True, 'changed': 'Actual new answer\n===DONE===', 'change_at': 0.7},
])
def test_uncertain_or_structured_output_is_not_released_early(monkeypatch, opts):
    result, clock = wait(True, monkeypatch, **opts)
    assert result['text'] == opts.get('changed', opts.get('first', 'New answer\n===DONE==='))
    if not opts.get('old'):
        assert 2.0 in clock.sleeps


def test_rendered_read_after_done_measures_real_json_not_placeholder(monkeypatch):
    text='Проверю файлы.\n===DONE===\n[color=#888888]— агент предлагает действие (см. ниже) —[/color]'
    raw='{\n  "action": "read_file",\n  "paths": [\n    "res://a.gd",\n    "res://b.gd"\n  ]\n}'
    opts=dict(first=text,raw=raw,height=155)
    before,slow=wait(False,monkeypatch,**opts)
    after,fast=wait(True,monkeypatch,**opts)
    assert before==after and slow.now>=20 and fast.now<1.5 and 2.5 not in fast.sleeps


def test_wrapped_prose_needs_positive_layout_evidence(monkeypatch):
    opts=dict(first='Длинный ответ. '*260+'\n===DONE===',height=420)
    guarded,slow=wait(True,monkeypatch,**opts)
    after,fast=wait(True,monkeypatch,**opts,wrapped=True)
    assert guarded==after and slow.now>=20 and fast.now<1.5
