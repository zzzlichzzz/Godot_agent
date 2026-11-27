"""Startup faults must leave unrelated tools callable, including after a cold import."""
from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from python.kernel.module_spec import ModuleSpec
from python.kernel.tool_spec import ToolSpec
from python.runtime import bootstrap, module_loader
from python.runtime.module_loader import LoadedModule
from tools import gen_contract


def feature(name, tool=None, contributions=(), **kw):
    tools = (ToolSpec(tool, tool, {'type': 'object'}, {}),) if tool else ()
    spec = ModuleSpec(id='demo.' + name, provides_tools=tuple(t.name for t in tools),
                      entrypoints={'call': lambda *_: name}, **kw)
    return LoadedModule(spec, tools, None, contributions)


def agent(items, monkeypatch, tmp_path, **settings):
    monkeypatch.setattr(bootstrap, 'discover', lambda: (items, []))
    monkeypatch.setattr(bootstrap, 'owners', lambda: {})
    return bootstrap.build_agent(tmp_path, ports={'journal': object()}, settings=settings)


def test_cold_start_missing_folder_and_broken_import(tmp_path):
    root = Path(__file__).resolve().parents[3]
    stage = tmp_path / 'source'
    shutil.copytree(root / 'python', stage / 'python', ignore=shutil.ignore_patterns('dist', '__pycache__', 'tests'))
    shutil.copytree(root / 'contract', stage / 'contract')
    shutil.rmtree(stage / 'python/modules/verification/gd_lint')
    (stage / 'python/modules/project_text/read/tools.py').write_text('raise ImportError("broken feature")\n')
    probe = '''from python.runtime.bootstrap import build_agent
from pathlib import Path
project = Path('../project'); project.mkdir(); (project/'hello.gd').write_text('extends Node')
a = build_agent(project_root=project, state_dir='../state')
for tool in ('gd_lint','read','node_rename_preview','node_reparent_preview'):
    assert a.call(tool,{})['kind']=='unavailable', (tool,a.disabled())
assert a.disabled()['verification.gd_lint']=='module_missing'
assert 'broken feature' in a.disabled()['project_text.read']
assert 'dependency_unavailable' in a.disabled()['scene_model.node_reparent']
assert a.call('not_shipped',{})['kind']=='unknown_tool'
assert 'hello.gd' in str(a.call('tree',{})['result'])
'''
    subprocess.run([sys.executable, '-B', '-c', probe], cwd=stage, check=True, timeout=40)


@pytest.mark.parametrize('fault,reason', [({'kernel_api': '^2'}, 'incompatible_kernel_api'),
    ({'godot': '^5.0'}, 'incompatible_godot'), ({'requires_ports': ('absent',)}, 'нет портов'),
    ({'environment': 'editor'}, 'нужен профиль'), ({}, 'disabled_modules')])
def test_transitive_unavailable_even_when_provider_discovered_last(fault, reason, tmp_path, monkeypatch):
    items = [feature('consumer', 'top_tool', requires=('demo.middle',)),
             feature('middle', 'mid_tool', requires=('demo.provider',)), feature('ok', 'ok_tool'),
             feature('provider', 'provider_tool', **fault)]
    a = agent(items, monkeypatch, tmp_path, disabled_modules=[] if fault else ['demo.provider'])
    assert a.call('ok_tool', {})['result'] == 'ok'
    assert reason in a.call('provider_tool', {})['hint']
    for tool in ('mid_tool', 'top_tool'):
        assert a.call(tool, {})['kind'] == 'unavailable' and 'dependency_unavailable' in a.call(tool, {})['hint']


def test_conflicts_cycles_and_contribution_aliases(tmp_path, monkeypatch):
    items = [feature('owner', 'base_tool'), feature('legacy', contributions=('old',), contributes_to=('demo.owner',)),
             feature('modern', contributions=('new',), contributes_to=('base_tool',)),
             feature('typo', 'bad_target', contributes_to=('missing',)),
             feature('left', 'cycle_left', requires=('demo.right',)), feature('right', 'cycle_right', requires=('demo.left',))]
    for name in ('one', 'two', 'three'):
        items.append(feature(name, 'duplicate', contributions=(name,), contributes_to=('base_tool',)))
    a = agent(items, monkeypatch, tmp_path)
    assert a.conflicts() == [{'tool':'duplicate', 'owners':['demo.one','demo.three','demo.two']}]
    assert a.call('duplicate', {})['kind'] == 'unavailable'
    assert a._registry.contributions('demo.owner') == a._registry.contributions('base_tool') == ('old','new')
    assert 'unknown_contribution_target' in a.call('bad_target', {})['hint']
    assert all('dependency_cycle' in a.disabled()['demo.' + n] for n in ('left', 'right'))
    for subset, msg in [(items[-3:]+items[:1], 'duplicate tool_name'), (items[:4], 'unknown contribution target')]:
        monkeypatch.setattr(module_loader, 'discover', lambda: (subset, []))
        with pytest.raises(ValueError, match=msg): gen_contract.rendered()


def test_recovery_only_for_active_module_and_context_per_agent(tmp_path, monkeypatch):
    called=[]
    item = feature('wal', 'wal_tool')
    item = replace(item, spec=replace(item.spec, entrypoints=dict(item.spec.entrypoints, recover=lambda *_: called.append('wal'))))
    with monkeypatch.context() as m:
        agent([item], m, tmp_path, disabled_modules='demo.wal'); assert not called
        agent([item], m, tmp_path); assert called == ['wal']
    first, second = [bootstrap.build_agent(tmp_path, profile='editor', state_dir=tmp_path / n) for n in ('a','b')]
    def section(a): return next(c for c in a._registry.contributions('context') if c.name == 'editor')
    left, right=section(first),section(second)
    assert left is not right and left._ctx.port('editor') is not right._ctx.port('editor')
    assert left.collect.__self__ is left and right.collect.__self__ is right


def test_writes_require_recovery_but_recovery_does_not_require_new_writes(tmp_path):
    def without(owner):
        return bootstrap.build_agent(tmp_path, state_dir=tmp_path/'state', settings={'disabled_modules':[owner]})
    a = without('editing.rollback')
    assert a.call('write_apply', {})['kind'] == a.call('split_apply', {})['kind'] == 'unavailable'
    assert 'write_rollback' in {tool['name'] for tool in without('editing.write_apply').tools()}


def test_faulty_port_factory_disables_only_its_branch(tmp_path, monkeypatch):
    def fail(_fs): raise RuntimeError('fixture adapter unavailable')
    items = [feature('provider', 'adapter_tool', port_factories={'adapter': fail}),
             feature('dependent', 'dependent_tool', requires=('demo.provider',)),
             feature('collision', 'collision_tool', port_factories={'fs': lambda _: None}),
             feature('unrelated', 'unrelated_tool', requires_ports=('fs',))]
    monkeypatch.setattr(bootstrap, 'discover', lambda: (items, []))
    monkeypatch.setattr(bootstrap, 'owners', lambda: {})
    a = bootstrap.build_agent(tmp_path, state_dir=tmp_path / 'state')
    assert 'fixture adapter unavailable' in a.disabled()['demo.provider']
    assert 'port factory conflict' in a.disabled()['demo.collision']
    assert a.disabled()['demo.dependent'] == 'dependency_unavailable: demo.provider'
    assert a.call('adapter_tool', {})['kind'] == 'unavailable'
    assert a.call('unrelated_tool', {})['result'] == 'unrelated'
