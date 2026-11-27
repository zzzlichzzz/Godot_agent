import pytest
from python.runtime.bootstrap import build_agent,default_ports

@pytest.mark.parametrize('missing',['fs','librarian'])
def test_judge_known_owner_missing_port_is_unavailable(tmp_path,missing):
    ports=default_ports(tmp_path,'test',tmp_path.parent/'state')
    del ports[missing]
    agent=build_agent(tmp_path,profile='test',ports=ports)
    result=agent.call('judge',{'full_text':'===DONE==='})
    assert result['kind']=='unavailable' and 'assistant.judge' in result['message']
    assert missing in result['hint']
    assert all(tool['name']!='judge' for tool in agent.tools())

def test_judge_unknown_name_stays_unknown(tmp_path):
    agent=build_agent(tmp_path,profile='test',state_dir=tmp_path.parent/'state')
    assert agent.call('not_a_j1_tool',{})['kind']=='unknown_tool'
