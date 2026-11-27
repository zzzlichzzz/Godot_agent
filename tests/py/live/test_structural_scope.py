"""D137: exercise the panel write loop in a game whose main scene has a script."""
import pytest

from tests.py.panel_tf.test_qwen_turn import setup
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client, physical


@pytest.mark.needs_live
def test_scoped_scene_material_and_settings(client,cold_tf6,monkeypatch):
    from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    _,root,_=client
    (root/'project.godot').write_text('config_version=5\n[application]\nconfig/name="T1"\nrun/main_scene="res://level.tscn"\n','utf-8')
    (root/'level.tscn').write_text('[gd_scene format=3]\n[ext_resource type="Script" path="res://hero.gd" id="1"]\n[node name="Hero" type="Node"]\nscript = ExtResource("1")\n','utf-8')
    (root/'material.tres').write_bytes(b'[gd_resource type="StandardMaterial3D" format=3 uid="uid://cyncsb"]\n\n[resource]\nroughness = 0.8\n')
    app,cid,post=setup(client,cold_tf6,monkeypatch)
    scene='res://test.tscn'; marker=dict(op='add_node',parent='.',name='Marker',type='Marker2D')
    def commit(action,path,after):
        before=physical(root)
        monkeypatch.setattr(BrowserBackend,'send',lambda *a,**kw:dict(text='Подготовлю.',action=action))
        preview=post('/chat',chat_id=cid,prompt=action['action'])
        assert preview.status_code==200 and preview.json['pending_confirmation'],preview.json
        assert [row['path'] for row in preview.json['preview']['diffs']]==[path] and physical(root)==before
        receipt=post('/chat/confirm_action',chat_id=cid,approved=True).json
        assert receipt['state']=='COMMITTED' and receipt['changed_paths']==[path]
        disk=physical(root); changed=path[6:]
        assert after in disk[changed] and {k:v for k,v in disk.items() if k!=changed}=={k:v for k,v in before.items() if k!=changed}
        return before,receipt
    def undo(saved):
        before,r=saved
        from tests.py.transfer_t1.test_write import ok
        ok(app.extensions['godot_agent'],'assistant_rollback',{'plan_id':r['plan_id'],'entry_id':r['entry_id']})
        assert physical(root)==before
    created=commit(dict(action='create_scene',scene=scene,root=dict(name='Test',type='Node2D'),operations=[]),scene,b'name="Test"')
    undo(commit(dict(action='edit_scene',scene=scene,operations=[marker]),scene,b'name="Marker"'))
    undo(created)
    undo(commit(dict(action='edit_resource',resource='res://material.tres',operations=[dict(op='set_property',target=[],property='roughness',value=dict(type='float',value=0.5))]),'res://material.tres',b'roughness = 0.5'))
    undo(commit(dict(action='edit_project_settings',operations=[dict(op='add_input_action',name='agent_test',deadzone=0.2)]),'res://project.godot',b'agent_test={'))
