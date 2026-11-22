"""D74 exact-source exception: native process, not a listener or arbitrary code."""
from importlib import util
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT=Path(__file__).resolve().parents[3]
CAPS={'python/substrate/editing/arch_map.py':454,
      'python/substrate/editing/node_refactor.py':1095,
      'python/substrate/editing/split_gd.py':1333,
      'python/substrate/editing/split_refactor.py':872,
      'python/substrate/code_intel/function_card.py':751}

def load(name):
    spec=util.spec_from_file_location('t1_'+name,ROOT/'tools'/ (name+'.py'))
    module=util.module_from_spec(spec);spec.loader.exec_module(module);return module

@pytest.mark.parametrize('relative,cap',list(CAPS.items()))
@pytest.mark.parametrize('delta',[0,1])
def test_exact_limit(relative,cap,delta):
    checker=load('check_limits')
    with patch.object(checker,'python_files',return_value=[ROOT/relative]), \
         patch.object(checker,'line_count',return_value=cap+delta):
        assert (checker.check_files()==[]) is (delta==0)
    assert checker.J1_NATIVE_CAPS['python/substrate/editing/file_refactor.py']==1457
    assert checker.FILE_MAX==400 and checker.AREA_MAX==8000

@pytest.mark.parametrize('relative',list(CAPS))
def test_exact_limits_not_basename_exemptions(relative):
    checker=load('check_limits'); path=ROOT/'python/substrate/arbitrary'/Path(relative).name
    with patch.object(checker,'python_files',return_value=[path]),patch.object(checker,'line_count',return_value=401):
        assert checker.check_files()

@pytest.mark.parametrize('change',[None,'extra_run','extra_bind','shell','argv','unicode','rename'])
def test_process_exception_fail_closed(change):
    checker=load('security_audit'); path=ROOT/'python/substrate/editing/split_gd.py'
    text=path.read_bytes().decode('utf-8')
    if change=='extra_run': text+='\nother.run()\n'
    if change=='extra_bind': text+='\nother.bind(("0.0.0.0",1))\n'
    if change=='shell': text=text.replace('capture_output=True','shell=True, capture_output=True')
    if change=='argv': text=text.replace('"--headless"','"--editor"')
    if change=='unicode': text+='\n# чужое изменение\n'
    if change=='rename': path=path.with_name('unapproved.py')
    with patch.object(checker,'files',return_value=[path]),patch.object(Path,'read_bytes',return_value=text.encode('utf-8')):
        found=checker.check_listener()+checker.check_processes()
    assert bool(found) is (change is not None)
