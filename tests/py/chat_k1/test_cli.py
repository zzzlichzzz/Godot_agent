"""K1 CLI protocol adapter: no provider needed for these unit cases."""
import importlib
import io
import sys
from unittest.mock import patch
import pytest

def cli():
    module=importlib.import_module('python.channels.cli.main')
    assert callable(getattr(module,'main',None)), 'CLI main missing'
    return module

class Client:
    def __init__(self): self.calls=[]
    def call(self,name,args):
        self.calls.append((name,args))
        return {'ok':True,'result':{'text':'plain answer','turns_used':1,'actions_executed':[],
                                   'judge_summary':{'score':74,'acceptable':True}}}
    def tools(self): return [{'name':'chat','effects':['read']},{'name':'read','effects':['read']}]

def invoke(argv,source=''):
    out=io.StringIO(); client=Client()
    code=cli().main(argv,agent_factory=lambda *a,**k:client,stdin=io.StringIO(source),stdout=out)
    return code,out.getvalue(),client.calls

def test_chat_normal_prints_only_text():
    code,out,calls=invoke(['chat','hello'])
    assert code==0 and out=='plain answer\n' and calls==[('chat',{'text':'hello'})]

def test_chat_json_has_full_diagnostics():
    import json
    code,out,calls=invoke(['chat','hello','--json'])
    value=json.loads(out)
    assert code==0 and value['result']['turns_used']==1 and value['result']['actions_executed']==[]

def test_chat_has_explicit_turn_and_char_options():
    code,out,calls=invoke(['chat','hello','--max-turns','2','--budget-chars','20'])
    assert calls==[('chat',{'text':'hello','max_turns':2,'budget_chars':20})]

def test_repl_keeps_one_client_and_stops_on_quit():
    code,out,calls=invoke(['repl'],'first\n\nsecond\n:quit\nthird\n')
    assert code==0 and calls==[('chat',{'text':'first'}),('chat',{'text':'second'})]
    assert out=='plain answer\nplain answer\n'

@pytest.mark.parametrize('argv',[['tools','list'],['tools','list','--json'],['health']])
def test_read_only_diagnostics_never_call_provider(argv):
    code,out,calls=invoke(argv)
    assert code==0 and calls==[] and out

def test_cli_import_does_not_activate_bindings():
    with patch.dict(sys.modules):
        for name in ('python.channels.cli.main','python.substrate.llm.runtime_bindings','api_backend','api_keys'):
            sys.modules.pop(name,None)
        cli()
        assert not {'python.substrate.llm.runtime_bindings','api_backend','api_keys'} & sys.modules.keys()
