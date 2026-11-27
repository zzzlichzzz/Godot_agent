"""C.18 fs-only orchestration, including the native F11 refusal precedence."""
import json
from pathlib import Path

import pytest

from python.kernel.errors import AppError
from python.modules.editing.split_py.tests.test_app import FS, invoke

ROOT = Path(__file__).resolve().parents[5]
CORPUS = ROOT/'fixtures/corpus/editing/split_py'


def test_f11_missing_without_addon_before_root():
    case = json.loads((CORPUS/'048-plan-missing-no-addon.json').read_bytes())
    fs = FS({})
    with pytest.raises(AppError) as error:
        invoke(case['args'], fs, tool='split_scan')
    assert error.value.kind == 'not_found'
    assert error.value.message == case['reference_error']['message']
    assert fs.calls == [('is_file', 'missing.py')]


class PlanFS(FS):
    def __init__(self, files=None, fail=None, directories=()):
        super().__init__({'plugin.cfg':b'[plugin]\n','donor.py':b'def fn():\n    return 1\n'} if files is None else files,fail)
        self.directories = set(directories)

    def exists(self, rel):
        self.perform('exists',rel)
        return rel in self.files or rel in self.directories

    def read_raw(self, rel):
        self.perform('read_raw',rel)
        if rel not in self.files:
            raise FileNotFoundError(rel)
        return self.files[rel]


@pytest.mark.parametrize('case', [c for p in sorted(CORPUS.glob('[0-9]*.json'))
                                 if (c := json.loads(p.read_bytes()))['tool']=='split_plan' and not c['expect']['ok']],
                         ids=lambda c:c['id'])
def test_plan_refusals(case):
    from python.modules.editing.split_py.tests.plan_cases import inputs
    folder = ROOT/'fixtures/projects'/case['fixture']
    fs = PlanFS({p.relative_to(folder).as_posix():p.read_bytes() for p in folder.rglob('*') if p.is_file()})
    denied = {'addons/sample/donor.py':'policy denied'}
    with pytest.raises(AppError) as error:
        invoke(case['args'],fs,denied,tool='split_plan')
    assert error.value.kind == case['expect']['kind']
    if 'expected_message' in case:
        assert error.value.message == case.get('app_expected_message',case['expected_message'])


@pytest.mark.parametrize('occupied', ['file','directory'])
def test_occupied_is_native_plan_data(occupied):
    fs = PlanFS(directories=['part.py'] if occupied=='directory' else [])
    if occupied == 'file':
        fs.files['part.py'] = b'# occupied\n'
    answer = invoke({'path':'res://donor.py','groups':[{'module':'part','symbols':['fn']}]},fs,tool='split_plan')
    assert answer['errors'] == ['целевой файл уже существует: part.py']
    assert answer['modules'] == [{'rel':'part.py','names':['fn'],'lines':9}]
    assert ('exists','part.py') in fs.calls
    assert (('read_raw','part.py') in fs.calls) is (occupied=='file')


def test_map_index_fresh_with_same_context():
    fs = PlanFS()
    args = {'path':'res://donor.py','groups':[{'module':'part','symbols':['fn']}]}
    first = invoke(args,fs,tool='split_plan')
    assert 'карта архитектуры не найдена' in first['warnings'][0]
    fs.files['docs/architecture_map.json'] = b'{"zones":[{"glob":"**/*.py","new_files":"allow"}]}'
    fs.files['python/godot_tools/neighbor.py'] = b'def fn(): pass\n'
    assert any('дубль из ядра' in e for e in invoke(args,fs,tool='split_plan')['errors'])
    del fs.files['python/godot_tools/neighbor.py']
    assert invoke(args,fs,tool='split_plan')['errors'] == []


def test_arch_map_uses_native_utf8_sig_not_json_encoding_autodetection():
    fs = PlanFS()
    fs.files['docs/architecture_map.json'] = '{"zones":[{"glob":"**/*.py","new_files":"allow"}]}'.encode('utf-16')
    answer = invoke({'path':'res://donor.py','groups':[{'module':'part','symbols':['fn']}]},fs,tool='split_plan')
    assert answer['warnings'] == ['карта архитектуры не найдена — зоны, лимиты и дубли имён не проверены',
                                  'part.py: зона ? (unknown)']
