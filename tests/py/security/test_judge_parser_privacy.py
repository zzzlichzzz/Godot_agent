"""Genuine SEC-J1 parser-sample red, using real public/native calls."""
import sys
import pytest
from python.runtime.bootstrap import build_agent,default_ports

ANSWER='```agent_action\n{"action":"create_file","path":"res://new.gd","content_ref":"PRIVATE_BODY"}\n```\n===DONE==='

def test_judge_parser_error_never_writes_next_to_launcher(tmp_path,monkeypatch):
    project=tmp_path/'project';project.mkdir()
    monkeypatch.setattr(sys,'argv',[str(project/'launcher.py')])
    agent=build_agent(project,profile='test',state_dir=tmp_path/'state')
    before=list(project.rglob('*'))
    result=agent.call('judge',{'full_text':ANSWER})
    assert result['ok'] and result['result']['blocking']
    assert list(project.rglob('*'))==before

def test_judge_parser_sample_guard_restores_on_interrupt(tmp_path,monkeypatch):
    project=tmp_path/'project';project.mkdir()
    port=default_ports(project,'test',tmp_path/'state')['librarian']
    from python.substrate.llm import runtime_bindings
    runtime_bindings.register()
    from python.substrate.llm.parsers import parser_base
    from python.substrate.assistant import answer_judge
    original=parser_base._save_corpus_sample
    def interrupted(*args,**kwargs):
        assert port.answer.__globals__['_LOCK']._is_owned()
        assert parser_base._save_corpus_sample is not original
        assert parser_base._save_corpus_sample('PRIVATE_SAMPLE','error') is None
        raise KeyboardInterrupt('test interruption')
    monkeypatch.setattr(answer_judge,'judge_answer',interrupted)
    with pytest.raises(KeyboardInterrupt):port.judge(ANSWER)
    assert parser_base._save_corpus_sample is original
