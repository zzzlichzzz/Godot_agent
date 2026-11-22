"""The frozen launcher invokes the executable with zero arguments."""
from importlib import import_module
from pathlib import Path
import pytest

def deployed(tmp_path):
    project=tmp_path/'project';addon=project/'addons/godot_agent'
    executable=addon/'python/dist/godot_agent_server/godot_agent_server.exe'
    executable.parent.mkdir(parents=True);executable.write_bytes(b'SYNTHETIC-NOT-AN-EXE')
    (project/'project.godot').write_text('[application]\nconfig/name="c14d"\n','utf-8')
    (addon/'plugin.cfg').write_text('[plugin]\n','utf-8')
    return project,executable

def test_noarg_lookup_binds_exe_project_real_godot_userdata_and_5000(tmp_path):
    module=import_module('python.channels.http.exe_bootstrap')
    project,exe=deployed(tmp_path);appdata=tmp_path/'roaming'
    root,state,port=module.configuration([],exe,{'APPDATA':str(appdata)})
    assert root==project.resolve() and state==appdata/'Godot/app_userdata/c14d' and port==5000

def test_explicit_args_keep_ephemeral_port_and_external_state(tmp_path):
    module=import_module('python.channels.http.exe_bootstrap')
    project,exe=deployed(tmp_path);state=tmp_path/'external'
    assert module.configuration(['--project',str(project),'--state',str(state)],exe,{})==(project.resolve(),state.resolve(),0)

@pytest.mark.parametrize('config',[ 'config/name="../foreign"','config/name="c14d"\nconfig/use_custom_user_dir=true',
    'config/name="c14d"\nconfig/use_custom_user_dir=true\nconfig/custom_user_dir_name="../foreign"'],ids=['traversal','ambiguous-custom','custom-traversal'])
def test_noarg_ambiguous_godot_config_refuses_not_guess(tmp_path,config):
    module=import_module('python.channels.http.exe_bootstrap')
    project,exe=deployed(tmp_path);(project/'project.godot').write_text('[application]\n'+config+'\n','utf-8')
    with pytest.raises(ValueError):module.configuration([],exe,{'APPDATA':str(tmp_path/'roaming')})

def test_token_create_read_native_semantics_never_overwrites_existing(tmp_path,monkeypatch):
    module=import_module('python.channels.http.exe_bootstrap')
    monkeypatch.setattr(module.secrets,'token_hex',lambda n:'SYNTHETIC-TF-TOKEN-NOT-A-REAL-SECRET')
    project,_=deployed(tmp_path);state=tmp_path/'external'
    module.ensure_token(project,state)
    token=state/'godot_agent_token.txt';before=token.read_bytes()
    assert before==b'SYNTHETIC-TF-TOKEN-NOT-A-REAL-SECRET'
    module.ensure_token(project,state);assert token.read_bytes()==before

def test_token_state_inside_project_refuses_before_effect(tmp_path):
    module=import_module('python.channels.http.exe_bootstrap')
    project,_=deployed(tmp_path);state=project/'unsafe'
    with pytest.raises(ValueError):module.ensure_token(project,state)
    assert not state.exists()
