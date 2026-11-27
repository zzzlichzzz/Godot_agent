"""D60 draft: actual checker on scratch trees, no blanket directory exemption."""
from importlib import util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CAPS = {
    'python/substrate/editing/file_refactor.py': 1457,
    'python/substrate/code_intel/symbol_refactor_part1.py': 824,
    'python/substrate/code_intel/symbol_refactor_part2.py': 718,
    'python/substrate/code_intel/symbol_refactor_part3.py': 714,
    'python/substrate/assistant/answer_judge.py': 492,
    'python/substrate/scene/scene_deps.py': 412,
}


@pytest.fixture
def checker(tmp_path):
    spec = util.spec_from_file_location('d60_checker', ROOT/'tools/check_limits.py')
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_path
    module.PYTHON = tmp_path/'python'
    module.MODULES = module.PYTHON/'modules'
    module.MODULES.mkdir(parents=True)
    return module


def source(checker, relative, count):
    path = checker.ROOT/relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'# measured line\n'*count)
    return path


@pytest.mark.parametrize('relative,count', list(CAPS.items()), ids=list(CAPS))
def test_exact_native_cap_passes(checker, relative, count):
    path = source(checker, relative, count)
    assert checker.line_count(path) == count
    assert checker.check_files() == []


@pytest.mark.parametrize('relative,count', list(CAPS.items()), ids=list(CAPS))
def test_native_cap_plus_one_fails(checker, relative, count):
    source(checker, relative, count+1)
    assert checker.check_files() == [f'{relative}: {count+1} строк (лимит {count})']


@pytest.mark.parametrize('folder', ['editing', 'code_intel', 'assistant', 'scene'])
def test_arbitrary_401_is_not_exempt(checker, folder):
    relative = 'python/substrate/'+folder+'/arbitrary_401.py'
    source(checker, relative, 401)
    assert checker.check_files() == [f'{relative}: 401 строк (лимит 400)']


@pytest.mark.parametrize('relative', list(CAPS), ids=list(CAPS))
def test_same_basename_outside_exact_path_is_not_exempt(checker, relative):
    wrong = 'python/substrate/new_reference/'+Path(relative).name
    source(checker, wrong, 401)
    assert checker.check_files() == [f'{wrong}: 401 строк (лимит 400)']


def test_six_literal_caps_only(checker):
    assert checker.J1_NATIVE_CAPS == CAPS
    assert checker.FILE_MAX == 400
    assert checker.ENTRY_MAX == {'module.py': 150, 'tools.py': 150, 'app.py': 80}
    assert checker.VERBATIM_DIRS == ('python/substrate/llm/browser',)
    assert checker.VERBATIM_FILE_MAX == 600
    assert checker.ENGINE_CACHE_VERBATIM_FILE_MAX == 3400
    assert checker.AREA_MAX == 8000 and checker.AREA_COHESION_MAX == 8400


@pytest.mark.parametrize('filename,cap', [('module.py', 150), ('tools.py', 150), ('app.py', 80)])
def test_entry_caps_unchanged(checker, filename, cap):
    relative = 'python/substrate/editing/'+filename
    source(checker, relative, cap+1)
    assert checker.check_files() == [f'{relative}: {cap+1} строк (лимит {cap})']
