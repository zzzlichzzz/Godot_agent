"""One binding across script/scene boundaries, both public previews and the engine's signal dispatcher."""
import os
import subprocess
import pytest
from tests.py.transfer_t1.test_write import client, ok, physical

SOURCE = '''extends Node
signal struck
var hits = 0
func on_struck():
	hits += 1
func exercise():
	Callable(self, &"on_struck").call()
	Signal(self, "struck").emit()
	return hits
'''
OTHER = '''extends Node
signal struck
var hits = 0
func on_struck():
	hits += 1
'''
SCENE = '''[gd_scene load_steps=3 format=3]
[ext_resource type="Script" path="res://actor.gd" id="a"]
[ext_resource type="Script" path="res://other.gd" id="b"]
[node name="Actor" type="Node"]
script = ExtResource("a")
[node name="Other" type="Node" parent="."]
script = ExtResource("b")
[connection signal="struck" from="Other" to="." method="on_struck"]
[connection signal="struck" from="." to="Other" method="on_struck"]
'''
RUN = '''extends SceneTree
func _initialize():
	var actor = load("res://cross.tscn").instantiate()
	var other = actor.get_node("Other")
	other.struck.emit()
	var passed = actor.exercise() == 2 and other.hits == 1
	actor.free()
	if passed: print("BINDINGS_OK")
	quit(0 if passed else 3)
'''

@pytest.mark.parametrize('kind,old,new,line,link,scene_line',[
    ('function','on_struck','on_impact',4,'callable',8),('signal','struck','impacted',2,'signal',9)])
def test_bound_name_through_both_previews_and_godot(client,kind,old,new,line,link,scene_line):
    agent,project,_=client
    for name,text in [('actor.gd',SOURCE),('other.gd',OTHER),('cross.tscn',SCENE)]:
        (project/name).write_bytes(text.replace('\n','\r\n').encode('utf-8'))
    before=physical(project); qry=dict(kind=kind,old_name=old,declaration=f'res://actor.gd:{line}')
    places=ok(agent,'usages',qry)['usages']; args=dict(qry,new_name=new)
    assert places==ok(agent,'analyze_rename',args)['usages']
    assert [(x['path'],x['line']) for x in places if x['link']=='scene_connection']==[('res://cross.tscn',scene_line)]
    assert sum(x['link']==link and x['confidence']=='proven' for x in places)==1
    preview=ok(agent,'write_preview',args); assert preview['stats']['edits']==3
    plan=ok(agent,'assistant_plan',dict(action=dict(action='rename_symbol',**args)))
    assert physical(project)==before
    edited=ok(agent,'assistant_confirm',dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=True))
    assert (project/'actor.gd').read_bytes()==before['actor.gd'].replace(old.encode() if kind=='function' else b'"struck"',new.encode() if kind=='function' else b'"impacted"').replace(b'signal struck',('signal '+new).encode() if kind=='signal' else b'signal struck')
    lines=before['cross.tscn'].splitlines(True); field='method' if kind=='function' else 'signal'
    lines[scene_line-1]=lines[scene_line-1].replace(f'{field}="{old}"'.encode(),f'{field}="{new}"'.encode())
    assert (project/'cross.tscn').read_bytes()==b''.join(lines) and (project/'other.gd').read_bytes()==before['other.gd']
    runner=project.parent/'verify.gd'; runner.write_text(RUN,'utf-8')
    result=subprocess.run([os.environ['GODOT_AGENT_GODOT_BIN'],'--headless','--path',str(project),'--script',str(runner)],capture_output=True,timeout=20)
    assert result.returncode==0 and b'BINDINGS_OK' in result.stdout,(result.stdout,result.stderr)
    ok(agent,'assistant_rollback',dict(plan_id=plan['plan_id'],entry_id=edited['entry_id']))
    assert all((project/p).read_bytes()==raw for p,raw in before.items())


def test_closed_override_vetoes_both_plans_without_export(client):
    agent,project,_=client
    (project/'actor.gd').write_text(SOURCE,'utf-8')
    closed=project/'addons/private/hidden.gd'; closed.parent.mkdir(parents=True)
    closed.write_text('extends "res://actor.gd"\nfunc on_struck():\n\tpass # private-canary\n','utf-8')
    args=dict(kind='function',old_name='on_struck',new_name='on_impact',declaration='res://actor.gd:4')
    before=physical(project)
    for tool,request in [('write_preview',args),('assistant_plan',{'action':dict(action='rename_symbol',**args)})]:
        result=agent.call(tool,request)
        assert not result['ok'] and result['kind']=='conflict',result
        assert 'hidden.gd' not in str(result) and 'private-canary' not in str(result)
    assert physical(project)==before


def test_large_unrelated_addon_script_does_not_block_a_rename(client):
    from python.kernel.limits import READ_TEXT_MAX_BYTES
    agent,project,_=client
    (project/'actor.gd').write_text(SOURCE,'utf-8')
    closed=project/'addons/private/large.gd'; closed.parent.mkdir(parents=True)
    closed.write_bytes(b'extends Node\n#'+b'x'*READ_TEXT_MAX_BYTES+b'\n')
    args=dict(kind='function',old_name='on_struck',new_name='on_impact',declaration='res://actor.gd:4')
    assert ok(agent,'write_preview',args)['affected_paths']==['res://actor.gd']
    assert [d['path'] for d in ok(agent,'assistant_plan',{'action':dict(action='rename_symbol',**args)})['diffs']]==['res://actor.gd']


def test_panel_renames_callable_owned_by_a_co_renamed_override(client):
    agent,project,_=client
    (project/'actor.gd').write_text(SOURCE,'utf-8')
    child='extends "res://actor.gd"\nfunc on_struck():\n\tpass\nfunc as_callback():\n\treturn Callable(self, &"on_struck")\n'
    child = child.replace('\n','\r\n'); (project/'child.gd').write_bytes(child.encode())
    action=dict(action='rename_symbol',kind='function',old_name='on_struck',new_name='on_impact',declaration='res://actor.gd:4')
    diffs=ok(agent,'assistant_plan',{'action':action})['diffs']
    assert next(d['after'] for d in diffs if d['path']=='res://child.gd')==child.replace('on_struck','on_impact')
