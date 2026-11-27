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


def test_saved_editor_is_project_scoped_and_must_still_match(tmp_path):
    from python.runtime.launcher_engine import ENGINE_ENV, remember, restore
    project, _ = deployed(tmp_path)
    editor = tmp_path/'portable Godot.exe'; editor.write_bytes(b'fixture')
    env = {'LOCALAPPDATA':str(tmp_path/'local'), ENGINE_ENV:str(editor)}
    remember(project,env); env.pop(ENGINE_ENV)
    restore(tmp_path/'other',env); assert ENGINE_ENV not in env
    restore(project,env); assert env.pop(ENGINE_ENV)==str(editor)
    editor.write_bytes(b'changed file'); restore(project,env); assert ENGINE_ENV not in env
    local = project/'unexpected.exe'; local.write_bytes(b'fixture')
    env[ENGINE_ENV]=str(local); remember(project,env); env.pop(ENGINE_ENV)
    restore(project,env); assert ENGINE_ENV not in env


def test_first_standalone_console_can_select_editor(tmp_path,monkeypatch):
    import io
    import os
    entry=import_module('python.channels.http.exe_bootstrap')
    editor=import_module('python.substrate.fs.godot_io').engine()
    project, exe = deployed(tmp_path)
    class Console(io.StringIO):
        def isatty(self): return True
    monkeypatch.setattr(entry.sys,'executable',str(exe))
    monkeypatch.setattr(entry.sys,'stdin',Console(f'"{editor}"\n'))
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local')); monkeypatch.setenv('APPDATA',str(tmp_path/'roaming'))
    monkeypatch.delenv('GODOT_AGENT_GODOT_BIN',raising=False); monkeypatch.setenv('PATH','')
    assert entry._configuration([])==(project,tmp_path/'roaming/Godot/app_userdata/c14d',5000)
    assert os.environ['GODOT_AGENT_GODOT_BIN']==str(editor)
