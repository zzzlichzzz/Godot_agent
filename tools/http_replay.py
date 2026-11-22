"""Explicit native HTTP auth reference lane, never a public tool dispatcher."""
from contextlib import redirect_stdout
import hashlib
from importlib import util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]

def observations():
    source=ROOT/'python/substrate/assistant/server/server_auth.py'
    spec=util.spec_from_file_location('_t1_http_auth_reference',source)
    native=util.module_from_spec(spec);spec.loader.exec_module(native)
    answer={}
    with TemporaryDirectory(prefix='godot-http-reference-') as directory,redirect_stdout(io.StringIO()):
        profile=Path(directory);missing=profile/'missing';missing.mkdir()
        token='SYNTHETIC-NATIVE-HTTP-REFERENCE-NOT-A-CREDENTIAL'
        (profile/'godot_agent_token.txt').write_text(token,encoding='utf-8')
        for name,path,value,state in (
            ('open-dashboard','/dashboard',None,None),
            ('unbound-no-project','/chat',None,None),
            ('unbound-missing-token','/chat',None,str(missing)),
            ('wrong-token','/chat','SYNTHETIC-WRONG-REFERENCE',str(profile)),
            ('valid-bind','/chat',token,str(profile)),
        ):
            native.reset();ok,code,message=native.check(path,value,state)
            answer[name]=dict(ok=ok,code=code,bound=bool(native.bound_dir()))
    return answer

def replay(folder,compare):
    folder=Path(folder);reference=json.loads((folder/'reference.json').read_text(encoding='utf-8'))
    source=ROOT/'python/substrate/assistant/server/server_auth.py'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=reference['source']['sha256']:
        return 5,0,['native HTTP auth source pin changed']
    actual=observations();failures=[]
    for name,expected in reference['observations'].items():
        problem=compare(actual.get(name),expected,'')
        if problem:failures.append(name+': '+problem)
    count=len(reference['observations'])
    return count,count-len(failures),failures
