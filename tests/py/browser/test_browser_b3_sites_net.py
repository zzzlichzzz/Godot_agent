"""B-3 byte-exact reference parity; no production runtime/live claim (D31)."""
import hashlib
import importlib
import json
import sys
from types import SimpleNamespace

import pytest

from tests.py.browser import b3_reference as reference

CORPUS = reference.ROOT / 'fixtures/corpus/browser/b3'
MANIFEST = json.loads((CORPUS / 'manifest.json').read_bytes())
PINS = {
    'sites.py': '06da927025fd18253b9e4a820b276ae8e2db834314938e2a2bd8b4993285dd41',
    'live_input.py': 'cd2c6ccfc12c371b9cbce0905addeb27d60264decaabbce2b2310b23b9f13e80',
    'ai_studio_net.py': '3d9a3fb4b62a1071c7e769b91e70947036f05f0e67b74e4642379ef585db710c',
    'qwen_net.py': '57d1ab2bfaea6226c478ffe3b05ba46badd49c67427ed6e3575791f13457b751',
    'backends/browser_backend.py': '21e5e911d139b4d136ef619a44ea401a757b27b83befe5907b37cfccee0a48b1',
    'net_monitor.py': '54167afbb87d9a9bf862df0a74c5a7bd24bb129661968682201c329d4297866b',
}


@pytest.mark.parametrize('filename', PINS)
def test_fixed_native_byte_pin(filename):
    path = reference.TARGET / filename
    assert path.is_file(), 'verbatim reference missing: ' + filename
    assert hashlib.sha256(path.read_bytes()).hexdigest() == PINS[filename]


@pytest.mark.parametrize('entry', MANIFEST['cases'], ids=lambda entry: entry['id'])
def test_native_observation_corpus(entry):
    raw = (CORPUS / entry['file']).read_bytes()
    assert len(raw) == entry['bytes']
    assert hashlib.sha256(raw).hexdigest() == entry['sha256']
    case = json.loads(raw)
    assert case['id'] == entry['id']
    assert reference.observe(case) == entry['expected']


@pytest.mark.parametrize(('module', 'missing'), [
    ('ai_studio_net', 'net_monitor'), ('qwen_net', 'net_monitor'),
    ('backends.browser_backend', 'server_state'),
])
def test_package_import_remains_explicitly_unintegrated(module, missing):
    # Expected missing dependency is a documented debt, NOT runtime success.
    with pytest.raises(ModuleNotFoundError) as caught:
        importlib.import_module('python.substrate.llm.browser.' + module)
    assert caught.value.name == missing


def test_reference_aliases_restore_even_on_failure():
    keys = ['net_monitor', 'server_state', 'ai_parser', 'deepseek_parser',
            'qwen_parser', 'kimi_parser', 'arena_parser']
    old = {key: sys.modules[key] for key in keys if key in sys.modules}
    with pytest.raises(RuntimeError, match='inert failure'):
        with reference.references():
            raise RuntimeError('inert failure')
    assert {key: sys.modules[key] for key in keys if key in sys.modules} == old


def test_public_http_pop_normative_not_destructive_snapshot():
    entry = next(item for item in MANIFEST['cases'] if item['id'] == 'base-independent-http-pop-once')
    case = json.loads((CORPUS / entry['file']).read_bytes())
    assert reference.observe(case) == {'values': [None, 429, None, None, 503, None, None, None],
                                      'cdp_calls': []}


def test_backend_dictionary_is_passed_by_identity():
    with reference.references() as importer:
        module = importer('backends/browser_backend.py')
        result = {'text': 'данные', 'battle_choice': 'left'}
        parser = SimpleNamespace(send_message_and_get_response=lambda *args, **kwargs: result)
        assert module.BrowserBackend(parser).send('inert prompt') is result


def test_harness_mirror_preserves_sequence_and_text():
    calls = []

    class Mirror:
        def __init__(self, **callbacks):
            pass

        def apply(self, seq, text):
            calls.append((seq, text))
            return {'ok': True, 'applied': True, 'reason': ''}

    case = {'steps': [{'seq': 5, 'text': 'ёж 🦔'}, {'seq': 'bad', 'text': None}]}
    reference.mirror(case, lambda filename: SimpleNamespace(LiveInputMirror=Mirror))
    assert calls == [(5, 'ёж 🦔'), ('bad', None)]
