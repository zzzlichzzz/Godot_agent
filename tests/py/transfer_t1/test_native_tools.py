"""Native cases, independently implemented tests; no native test execution."""
from importlib import import_module
import hashlib
import json
import sys
from types import ModuleType
from unittest.mock import patch
import pytest
from .observations import CORPUS, ROOT, TARGETS, observe

REFERENCE = json.loads((CORPUS/'reference.json').read_bytes())

@pytest.mark.parametrize('case',REFERENCE['cases'],ids=lambda c:c['id'])
def test_native_case(case,tmp_path):
    assert observe(case,tmp_path/'observed')==REFERENCE['observations'][case['id']]

@pytest.mark.parametrize('name,target,source',TARGETS,ids=[r[0] for r in TARGETS])
def test_native_source_pin(name,target,source):
    expected=json.loads((CORPUS/'pins.json').read_bytes())[source]
    raw=(ROOT/PathFor(target)).read_bytes()
    assert len(raw)==expected['bytes'] and hashlib.sha256(raw).hexdigest()==expected['sha256']
    assert raw.count(b'\n')==expected['LF'] and raw.count(b'\r\n')==expected['CRLF']

def PathFor(target):
    return target.replace('.','/')+'.py'

def test_append_only_separate_activation_and_identity():
    adapter=import_module('python.substrate.assistant.native_bindings').NativeBindings()
    adapter.register(); before=dict(sys.modules); adapter.register()
    assert sys.modules==before
    assert len(import_module('python.substrate.llm.runtime_bindings').BINDINGS)==50
    for name,target,_ in TARGETS:
        assert sys.modules[name] is import_module(target)

@pytest.mark.parametrize('name',[row[0] for row in TARGETS])
def test_foreign_alias_refused(name):
    adapter=import_module('python.substrate.assistant.native_bindings').NativeBindings()
    foreign=ModuleType('foreign')
    with patch.dict(sys.modules,{name:foreign}):
        with pytest.raises(RuntimeError,match='legacy alias already bound: '+name): adapter.register()
        assert sys.modules[name] is foreign

@pytest.mark.parametrize('failure',[ImportError,KeyboardInterrupt])
def test_activation_rolls_back_owned_extra_aliases(failure):
    module=import_module('python.substrate.assistant.native_bindings')
    adapter=module.NativeBindings()
    real=module.import_module
    def failing(target):
        if target==TARGETS[-1][1]: raise failure('synthetic final native import')
        return real(target)
    with patch.object(module,'import_module',failing),pytest.raises(failure): adapter.register()
    assert all(name not in sys.modules for name,_,_ in TARGETS)

def test_native_prepare_cases_are_not_silent_type_errors():
    for case_id in ('split-gd-inventory','split-py-inventory','node-rename','node-reparent','node-delete','card'):
        assert 'value' in REFERENCE['observations'][case_id],REFERENCE['observations'][case_id]
