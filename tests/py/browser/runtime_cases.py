"""Trusted offline operations for native observations and integrated parser tests."""
from contextlib import contextmanager
import importlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

from tests.py.browser import b3_reference

ROOT = Path(__file__).resolve().parents[3]
NAMES = ('cdp_ws', 'net_monitor', 'sites', 'browser_manager', 'ai_studio_net',
         'qwen_net', 'text_sanitize', 'parser_base', 'kimi_parser', 'ai_parser',
         'qwen_parser', 'deepseek_parser')


@contextmanager
def references(native=None):
    # Scoping is test-only; production's explicit binding is the runtime under test.
    with patch.dict(sys.modules):
        if native is None:
            binding = importlib.import_module('python.substrate.llm.runtime_bindings')
            binding.register()
            yield {name: sys.modules[name] for name in NAMES}
        else:
            modules = {}
            for name in NAMES:
                folder = 'parsers' if name.endswith('_parser') or name in (
                    'parser_base', 'text_sanitize') else 'browser'
                path = Path(native) / folder / (name + '.py')
                assert path.is_file(), path
                spec = importlib.util.spec_from_file_location('_runtime_native_' + name, path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                modules[name] = module
            yield modules


class Clock:
    def __init__(self):
        self.now, self.sleeps = 0.0, []

    def time(self):
        return self.now

    monotonic = time

    def sleep(self, seconds):
        assert seconds > 0
        self.sleeps.append(seconds)
        self.now += seconds


def sanitize(case, modules):
    return modules['text_sanitize'].sanitize_llm_text(case['text'])


def action(case, modules):
    obj, error = modules['parser_base'].parse_action_json(case['raw'])
    return {'action': obj, 'error': error}


def incomplete(case, modules):
    return modules['parser_base'].answer_transfer_incomplete(case['raw'], case['text'])


def best(case, modules):
    return modules['parser_base'].select_best_answer_variant(case['variants'])


def split(case, modules):
    name = case.get('parser', 'parser_base')
    assert name in ('parser_base', 'kimi_parser')
    fn = 'split_net_text_and_action' if name == 'parser_base' else 'split_text_and_action'
    return getattr(modules[name], fn)(case['text'])


def b3(case, modules):
    payload = case['payload']
    assert payload['kind'] in ('decode', 'wire')
    def importer(filename):
        assert filename in ('ai_studio_net.py', 'qwen_net.py')
        return modules[filename[:-3]]
    return b3_reference.RUNNERS[payload['kind']](payload, importer)


def kimi(case, modules):
    module = modules['kimi_parser']
    mon = module.KimiChatMonitor(b3_reference.CDP())
    for event in case['events']:
        mon._apply_event(event)
    result = {'text': mon.current_text(), 'live': mon.live_text(),
              'status': mon.message_status(), 'count': mon.assistant_message_count(),
              'generating': mon.is_generating(), 'events': len(mon._debug_events)}
    if case.get('reset'):
        mon._reset_answer_state_locked()
        result['reset'] = {'text': mon.current_text(), 'live': mon.live_text(),
                           'events': len(mon._debug_events)}
    return result


def dom(case, modules):
    name = case['parser']
    assert name in ('kimi_parser', 'deepseek_parser')
    calls = []
    def execute(script, *args):
        calls.append(script)
        if case.get('failure'):
            raise RuntimeError('inert DOM unavailable')
        return case['dom']
    driver = SimpleNamespace(execute_script=execute)
    if name == 'kimi_parser':
        answer = modules[name].KimiParser().extract_raw_fallback(driver)
    else:
        answer = modules[name].DeepSeekParser().extract_answer_snapshot(driver)
    return {'answer': answer, 'reads': len(calls)}


def ready(case, modules):
    name = case['parser']
    classes = {'ai_parser': 'AiStudioParser', 'qwen_parser': 'QwenParser',
               'kimi_parser': 'KimiParser'}
    assert name in classes
    cls = getattr(modules[name], classes[name])
    counts = []
    def answer_count():
        counts.append('answer')
        return case['answer_count']
    mon = SimpleNamespace(_cdp=SimpleNamespace(is_alive=lambda: case['alive']),
                          answer_request_count=answer_count,
                          chat_request_count=lambda: case.get('sent_count', 999),
                          is_finished=lambda: case['finished'],
                          message_status=lambda: case['status'])
    parser = cls()
    with patch.object(cls, '_monitor', None if case.get('missing') else mon), \
            patch.object(cls, '_req_count_before_send', case['before'], create=True):
        parser._req_count_before_send = case['before']
        return {'ready': parser.net_answer_ready(None), 'count_reads': counts}


def deepseek(case, modules):
    module, clock = modules['deepseek_parser'], Clock()
    parser = module.DeepSeekParser()
    parser._composer_had_text = case['had_text']
    reads = []
    def leftover(driver, element):
        reads.append(clock.now)
        if case.get('clear_at') is not None and clock.now >= case['clear_at']:
            return ''
        return case['leftover']
    with patch.object(module, 'time', clock), patch.object(parser, '_input_leftover', leftover):
        try:
            result = {'confirmed': parser.confirm_sent(None, None)}
        except RuntimeError as error:
            result = {'error_type': type(error).__name__, 'error': str(error)}
    result.update(elapsed=round(clock.now, 6), reads=len(reads))
    return result


def wait(case, modules):
    module, clock = modules['parser_base'], Clock()
    class Parser(module.BaseSiteParser):
        reads = 0
        net_queries = 0
        TIMEOUT = 8.0
        QUIET_PERIOD = 0.5
        HARD_QUIET_PERIOD = 0.5
        POLL_INTERVAL = 0.25
        POST_QUIET_GRACE = 1.0

        def _answer(self):
            if clock.now >= case.get('change_at', float('inf')):
                return dict(case['changed_answer'])
            return dict(case['answer'])

        def count_answers(self, driver):
            return case.get('count', 2)

        def answer_len(self, driver):
            return case.get('length', len(self.answer_stream(driver)))

        def answer_stream(self, driver):
            answer = self._answer()
            return (answer.get('text') or '') + (answer.get('actionRaw') or '')

        answer_preview = answer_stream

        def is_generating(self, driver):
            return clock.now < case.get('generating_until', 0)

        def extract_answer(self, driver):
            self.reads += 1
            return self._answer()

        def net_answer_ready(self, driver):
            self.net_queries += 1
            return case.get('ready', False)

        def _log(self, message):
            pass

    parser = Parser()
    with patch.object(module, 'time', clock):
        try:
            result = {'answer': parser.wait_for_new_answer(None, 1,
                timeout=case.get('timeout', 8.0), baseline=case.get('baseline', {'text': 'old'}),
                cancel_cb=lambda: clock.now >= case.get('cancel_at', float('inf')))}
        except (TimeoutError, module.ParserCancelled) as error:
            result = {'error_type': type(error).__name__, 'error': str(error)}
    result.update(elapsed=round(clock.now, 6), reads=parser.reads,
                  net_queries=parser.net_queries)
    return result


RUNNERS = {'sanitize': sanitize, 'action': action, 'incomplete': incomplete,
           'best': best, 'split': split, 'b3': b3, 'kimi': kimi, 'dom': dom,
           'ready': ready, 'deepseek': deepseek, 'wait': wait}


def observe(case, modules):
    # No expression evaluation or source execution is selected by fixture strings.
    result = RUNNERS[case['op']](case, modules)
    return json.loads(json.dumps(result, ensure_ascii=True))
