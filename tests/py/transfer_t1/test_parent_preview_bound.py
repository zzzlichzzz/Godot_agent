"""Public schema must cover already-allowed compiler steps; no real deep-path claim."""
import pytest
from python.kernel.schema import validate
from python.modules.assistant.write.operations.tools_assistant_plan import TOOL
from python.runtime.bootstrap import build_agent,default_ports
from tests.py.transfer_t1.test_write import client,physical

@pytest.mark.parametrize('count',[99,100,101,256])
def test_public_preview_accepts_bounded_directory_steps_without_effects(client,count):
    _,root,state=client;before=physical(root)
    parents=['res://'+'/'.join('p'+str(n) for n in range(size)) for size in range(1,count+1)]
    path=parents[-1]+'/file.gd'
    class Prepared:
        def prepare(self,action,**policy):
            return {'files':[{'path':path,'before_bytes':None,'after_bytes':b'extends Node\n'}],
                    'parents':parents,'warnings':[]}
    ports=default_ports(str(root),'test',state_dir=str(state));ports['native_planner']=Prepared()
    agent=build_agent(project_root=str(root),profile='test',state_dir=str(state),ports=ports)
    answer=agent.call('assistant_plan',{'action':{'action':'create_file','path':path,'content':'extends Node\n'}})
    assert answer['ok'],answer
    assert answer['result']['steps_count']==count+1 and physical(root)==before
    assert not validate(answer['result'],TOOL.result)
