"""T1 native case recorder. Never loads the excluded minilich initializer."""
import base64
import ast
from contextlib import contextmanager
from importlib import import_module, util
import json
import os
from pathlib import Path
import socket
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/transfer/godot_tools'
TARGETS = (
    ('arch_map', 'python.substrate.editing.arch_map', 'python/godot_tools/arch_map.py'),
    ('gd_functions', 'python.substrate.code_intel.gd_functions', 'python/godot_tools/gd_functions.py'),
    ('log_reader', 'python.substrate.editor.references.log_reader', 'python/server/log_reader.py'),
    ('node_refactor', 'python.substrate.editing.node_refactor', 'python/godot_tools/node_refactor.py'),
    ('split_gd', 'python.substrate.editing.split_gd', 'python/godot_tools/split_gd.py'),
    ('split_refactor', 'python.substrate.editing.split_refactor', 'python/godot_tools/split_refactor.py'),
    ('function_card', 'python.substrate.code_intel.function_card', 'python/godot_tools/function_card.py'),
    ('gather_context', 'python.substrate.context.gather_context', 'python/godot_tools/gather_context.py'),
)
GD = 'extends Node\nclass_name T1Hero\nconst MAX_HEALTH = 10\nvar health = 10\n# exact body\nfunc hit(amount: int = 1):\n\thealth -= amount\n\treturn health\n\nstatic func helper():\n\treturn 2\n'
PY = '"""T1 native case."""\nCONST = 3\n\ndef alpha():\n    return CONST\n\ndef beta():\n    return alpha()\n'
SCENE = '[gd_scene format=3]\n\n[node name="Root" type="Node"]\n\n[node name="Hero" type="Node" parent="."]\nunique_name_in_owner = true\n\n[node name="Weapon" type="Node" parent="Hero"]\n'
CASES = [
    *[dict(id='functions-'+str(i),module='gd_functions',method=method,args=args) for i,(method,args) in enumerate([
        ('list_functions',[GD]),('extract_functions',[GD,['hit','absent','helper']]),
        ('extract_functions',['# comment\n@rpc\nfunc f():\n\tpass\nfunc f():\n\treturn 2\n',['f']]),
        ('list_functions',[None])])],
    *[dict(id='gather-'+str(i),module='gather_context',method='validate_request',args=[value]) for i,value in enumerate([
        None,{},dict(query='  hero  ',symbols=['hit',None],godot_api=['Node','bad class'],max_chars=999999),
        dict(editor=False,active_scene=False,diagnostics=False),dict(max_chars='bad')])],
    *[dict(id='arch-'+str(i),module='arch_map',method=method,args=args) for i,(method,args) in enumerate([
        ('public_names',[PY]),('public_names',['def broken(']),('count_lines',['a\nb\n']),
        ('line_policy',[{'limits':{'line_warn':100,'line_max':1,'line_exts':['.GD','bad']}}]),
        ('line_policy',[{'limits':{'line_warn':'broken','line_max':-1}}])])],
    dict(id='split-gd-inventory',module='split_gd',method='file_inventory',args=[GD]),
    dict(id='split-gd-scan',module='split_gd',method='scan_refs',args=['$project','hero.gd']),
    dict(id='split-gd-plan',module='split_gd',method='plan_split',args=['$project','hero.gd']),
    dict(id='split-py-inventory',module='split_refactor',method='file_inventory',args=[PY]),
    dict(id='split-py-broken',module='split_refactor',method='file_inventory',args=['def broken(']),
    dict(id='split-py-scan',module='split_refactor',method='scan_refs',args=['$project','target.py']),
    dict(id='split-py-plan',module='split_refactor',method='plan_split',args=['$project','target.py']),
    dict(id='node-parse',module='node_refactor',method='parse_tscn_structure',args=[SCENE]),
    dict(id='node-rename',module='node_refactor',method='prepare_node_rename',args=['$project','res://level.tscn','%Hero','Player']),
    dict(id='node-reparent',module='node_refactor',method='prepare_node_reparent',args=['$project','res://level.tscn','Hero/Weapon','.']),
    dict(id='node-delete',module='node_refactor',method='prepare_node_deletion',args=['$project','res://level.tscn','Hero/Weapon']),
    dict(id='node-missing',module='node_refactor',method='prepare_node_rename',args=['$project','res://level.tscn','Absent','Player']),
    dict(id='card',module='function_card',method='build_function_card',args=['$project','res://hero.gd','hit']),
    dict(id='card-missing',module='function_card',method='build_function_card',args=['$project','res://hero.gd','absent']),
    dict(id='log-input',module='log_reader',method='list_input_actions',args=['$project']),
]

def normalize(value, sandbox):
    if isinstance(value,ast.AST): return {'AST':ast.dump(value,include_attributes=True)}
    if isinstance(value,str): return value.replace(str(sandbox),'<sandbox>').replace(sandbox.as_posix(),'<sandbox>')
    if isinstance(value,bytes): return {'base64':base64.b64encode(value).decode('ascii')}
    if isinstance(value,dict): return {k:normalize(v,sandbox) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [normalize(v,sandbox) for v in value]
    if isinstance(value,set): return sorted(normalize(v,sandbox) for v in value)
    return value

@contextmanager
def subjects(sandbox, native=None):
    saved, paths = dict(sys.modules), list(sys.path)
    def offline(*_args,**_kwargs): raise AssertionError('T1 corpus forbids external network')
    try:
        with patch.dict(os.environ,{'GODOT_AGENT_CONFIG_DIR':str(sandbox/'config')},clear=True), \
             patch.object(socket,'getaddrinfo',offline), patch.object(socket.socket,'connect',offline), \
             patch.object(socket.socket,'connect_ex',offline):
            import_module('python.substrate.llm.runtime_bindings').register()
            if native is None:
                import_module('python.substrate.assistant.native_bindings').NativeBindings().register()
            else:
                for name,target,source in TARGETS:
                    spec=util.spec_from_file_location(name,native/source)
                    module=util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module)
            sys.modules['history_manager'].set_storage_dir(str(sandbox/'history'))
            sys.modules['minilich.ml_data'].set_storage_base(str(sandbox/'index'))
            yield {name:sys.modules[name] for name,_,_ in TARGETS}
    finally:
        sys.modules.clear(); sys.modules.update(saved); sys.path[:]=paths

def observe(case,sandbox,native=None):
    sandbox=sandbox.resolve(); assert ROOT not in sandbox.parents and ROOT!=sandbox
    project=sandbox/'project'; project.mkdir(parents=True)
    for name,text in {'project.godot':'[application]\nconfig/name="T1"\n[input]\njump={}\n',
        'hero.gd':GD,'target.py':PY,'consumer.py':'import target\nTAG="target.py"\n',
        'level.tscn':SCENE,'plugin.cfg':'[plugin]\nname="T1"\n'}.items():
        (project/name).write_bytes(text.encode('utf-8'))
    before={p.relative_to(project).as_posix():p.read_bytes() for p in project.rglob('*') if p.is_file()}
    with subjects(sandbox,native) as modules:
        try:
            value=getattr(modules[case['module']],case['method'])(*[str(project) if a=='$project' else a for a in case['args']])
            result={'value':normalize(value,sandbox)}
        except Exception as error:
            result={'error':type(error).__name__,'message':normalize(str(error),sandbox)}
    after={p.relative_to(project).as_posix():p.read_bytes() for p in project.rglob('*') if p.is_file()}
    assert before==after, 'prepare/read unexpectedly wrote project'
    return result
