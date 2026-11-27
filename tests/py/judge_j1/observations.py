"""Real native judge and actual build_agent→agent.call observations."""
import base64
from contextlib import contextmanager
from importlib import util
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch
from tests.py.judge_a3.observations import subjects as dependencies
from tests.py.judge_a2.observations import snapshot

ROOT=Path(__file__).resolve().parents[3]
CORPUS=ROOT/'fixtures/corpus/assistant/judge'
def normalize(value,project):
    if isinstance(value,bytes):return {'base64':base64.b64encode(value).decode('ascii')}
    if isinstance(value,str):
        for prefix in (str(project).replace('\\','\\\\')+'\\\\',str(project)+'\\',project.as_posix()+'/'):
            value=value.replace(prefix,'res://')
        return value
    if isinstance(value,dict):return {k:normalize(v,project) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [normalize(v,project) for v in value]
    return value
def cases():return json.loads((CORPUS/'inputs/catalog.json').read_text('utf-8'))
@contextmanager
def native_subject(sandbox,native):
    with dependencies(sandbox,native) as (facade,addon):
        parent=sys.modules['minilich']
        sys.modules['minilich.ml_data']=parent.ml_data
        sys.modules['minilich.ml_project_index']=parent.ml_project_index
        for name in ('tscn_lint','runtime_checks','answer_judge'):
            source=native/'godot_tools'/(name+'.py')
            spec=util.spec_from_file_location('b_native_'+name,source);module=util.module_from_spec(spec)
            sys.modules[name]=module;spec.loader.exec_module(module)
            assert Path(module.__file__).resolve()==source.resolve()
        judge=sys.modules['answer_judge']
        assert judge.symbol_refactor is facade
        assert judge.librarian_search is parent.ml_project_index.search
        assert judge.lint_gdscript is sys.modules['gd_lint'].lint_gdscript
        yield judge
def observe(case,sandbox,native=None):
    sandbox=sandbox.resolve();assert ROOT not in sandbox.parents
    sandbox.mkdir(parents=True,exist_ok=False)
    project=sandbox/'project';shutil.copytree(CORPUS/'project',project)
    before=snapshot(project)
    if native is not None:
        with native_subject(sandbox,native) as judge:
            value=judge.judge_answer(str(project),case['args']['full_text'],addon_dir=str(ROOT))
            again=judge.judge_answer(str(project),case['args']['full_text'],addon_dir=str(ROOT))
            assert normalize(value,project)==normalize(again,project)
            value={'ok':True,'result':value}
    else:
        import socket
        import subprocess
        from python.runtime.bootstrap import build_agent
        def offline(*args,**kwargs):raise AssertionError('public judge activated network/process')
        with patch.object(socket,'getaddrinfo',offline),patch.object(socket.socket,'connect',offline),\
                patch.object(socket.socket,'connect_ex',offline),patch.object(subprocess,'Popen',offline),\
                patch.object(subprocess,'run',offline):
            agent=build_agent(str(project),profile='test',state_dir=str(sandbox/'state'))
            value=agent.call('judge',case['args'])
            assert agent.call('judge',case['args'])==value
    after=snapshot(project);assert before==after,'judge changed project bytes'
    return normalize({'before':before,'answer':value,'after':after},project)
