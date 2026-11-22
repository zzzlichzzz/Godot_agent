"""Offline executable entrypoint matching the frozen launcher's zero arguments."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import sys

def ordinary(path):
    for item in (path,*path.parents):
        if item.exists() or item.is_symlink():
            stat=item.lstat()
            if item.is_symlink() or getattr(stat,'st_file_attributes',0)&0x400:
                raise ValueError('Deployment and userdata must not traverse links')

def safe_name(value):
    if (not value or value in ('.','..') or value[-1] in ('.',' ') or
        re.search(r'[<>:"/\\|?*\x00-\x1f]',value) or value.split('.')[0].upper() in
        {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}):
        raise ValueError('Ambiguous Godot userdata name; use explicit --state')
    return value

def configuration(argv,executable,environ):
    parser=argparse.ArgumentParser(description='Godot Agent owned HTTP executable')
    parser.add_argument('--project');parser.add_argument('--state');parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args(argv)
    if argv:
        if not args.project or not args.state:raise ValueError('Both --project and --state required')
        project=Path(args.project).absolute();state=Path(args.state).absolute()
        ordinary(project);ordinary(state)
        return project.resolve(),state.resolve(),args.port
    exe=Path(executable).absolute();ordinary(exe)
    addons=[p for p in exe.parents if p.name=='godot_agent' and p.parent.name=='addons']
    if len(addons)!=1:raise ValueError('Exe must belong to one addon deployment')
    addon=addons[0];project=addon.parent.parent;config=project/'project.godot'
    if not (addon/'plugin.cfg').is_file() or not config.is_file():raise ValueError('No bound Godot project')
    ordinary(config)
    if config.stat().st_size>1_000_000:raise ValueError('Project config too large')
    section='';values={}
    for line in config.read_text('utf-8-sig').splitlines():
        line=line.strip()
        if line.startswith('['):section=line
        elif section=='[application]' and '=' in line:
            key,value=line.split('=',1)
            if key.strip() in ('config/name','config/use_custom_user_dir','config/custom_user_dir_name'):
                if key.strip() in values:raise ValueError('Duplicate userdata setting')
                values[key.strip()]=json.loads(value.strip())
    name=values.get('config/name')
    if not isinstance(name,str):raise ValueError('Project config/name is required')
    name=safe_name(name)
    appdata=environ.get('APPDATA')
    if not appdata or not Path(appdata).is_absolute():raise ValueError('Windows APPDATA is required')
    state=Path(appdata)/'Godot/app_userdata'/name
    custom=values.get('config/use_custom_user_dir',False)
    if type(custom) is not bool:raise ValueError('Invalid custom userdata setting')
    if custom:
        custom_name=values.get('config/custom_user_dir_name')
        if not isinstance(custom_name,str):raise ValueError('Custom userdata needs explicit name or --state')
        state=Path(appdata)/safe_name(custom_name)
    ordinary(state)
    return project.resolve(),state.absolute(),5000

def ensure_token(project,state):
    from python.substrate.assistant.server import server_auth
    source=Path(__file__).resolve().parents[2]
    ordinary(state)
    resolved=state.resolve()
    if any(resolved==root or root in resolved.parents for root in (project.resolve(),source)):
        raise ValueError('Token userdata must stay outside project/source')
    path=state/server_auth.TOKEN_FILE;ordinary(path)
    if not path.exists():
        state.mkdir(parents=True,exist_ok=True)
        try:
            with path.open('xb') as out:
                out.write(secrets.token_hex(32).encode('ascii'));out.flush();os.fsync(out.fileno())
        except FileExistsError:pass  # Panel won the exclusive creation race; preserve its token.
    ordinary(path)
    if not path.is_file() or path.stat().st_size>4096:raise ValueError('Invalid panel token file')
    token=server_auth.read_token(str(state))
    if not token or len(token)>4096:raise ValueError('Invalid panel token; never replacing it')
