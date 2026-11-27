"""T-B fail-closed proof for an existing parent after read-only preparation."""
import pytest
from python.runtime.bootstrap import build_agent,default_ports
from python.modules.assistant.write.tests.test_directories import directories
from tests.py.transfer_t1.test_write import client,physical

@pytest.mark.parametrize('fault',['empty-proof','identity-os-error'])
def test_existing_parent_that_cannot_be_proven_plain_is_not_written(client,fault):
    _,root,state=client;(root/'keep').mkdir()
    ports=default_ports(str(root),'test',state_dir=str(state))
    agent=build_agent(project_root=str(root),profile='test',state_dir=str(state),ports=ports)
    preview=agent.call('assistant_plan',dict(action=dict(action='create_file',path='res://keep/file.gd',content='extends Node\n')))
    assert preview['ok'],preview
    plan=preview['result'];assert plan['steps_count']==1
    before=physical(root);dirs=directories(root);attempts=[]
    identity=ports['writer'].directory_identity;create=ports['writer'].create
    def unproven(path):
        if path=='keep':
            if fault=='identity-os-error':raise OSError('Synthetic directory identity unavailable')
            return ''
        return identity(path)
    def effect(path,content):attempts.append(path);return create(path,content)
    ports['writer'].directory_identity=unproven;ports['writer'].create=effect
    answer=agent.call('assistant_confirm',dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=True))
    assert not answer['ok'] and attempts==[] and physical(root)==before and directories(root)==dirs
