"""K1 fresh semantic tests: domain returns STRING; app alone wraps diagnostics."""
from importlib import import_module
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError

CORE = 'python.modules.assistant.chat.domain.core'

def reply(text='answer', action=None, done=True, finish='stop', error=''):
    return dict(text=text, raw=text+('\n===DONE===' if done else ''), action=action,
                done=done, finish_reason=finish, parse_error=error)

class Scripted:
    def __init__(self, values):
        self.values=iter(values); self.prompts=[]; self.systems=[]
    def system_prompt(self, **kwargs): return 'native-system'
    def send(self, prompt, **kwargs):
        self.prompts.append(prompt); self.systems.append(kwargs.get('system_text'))
        return next(self.values)

def run(values, *, turns=8, budget=80000, scores=None):
    port=Scripted(values); trace={}; executed=[]; judged=[]
    judgments=iter(scores or [dict(score=74,acceptable=True)]*8)
    def judge(raw): judged.append(raw); return next(judgments)
    def execute(action,limit):
        executed.append((action,limit)); return (['read'], 'read-content')
    result=import_module(CORE).run_turn('user-text',port.send,port.system_prompt,
        execute,judge,max_turns=turns,budget_chars=budget,trace=trace)
    return result,trace,port,executed,judged

def test_final_is_string_and_done_uses_raw_response():
    result,trace,port,executed,judged=run([reply()])
    assert result=='answer' and isinstance(result,str)
    assert trace==dict(turns_used=1,actions_executed=[],judge_summary={'score':74,'acceptable':True})
    assert port.prompts==['user-text'] and executed==[] and judged==['answer\n===DONE===']

def test_read_action_even_with_done_runs_then_final_answer():
    action={'action':'read_file','paths':['res://a.gd']}
    result,trace,port,executed,judged=run([reply('read first',action),reply('final')])
    assert result=='final' and trace['turns_used']==2 and trace['actions_executed']==['read']
    assert executed==[(action,80000)] and 'read-content' in port.prompts[1]
    assert all(system=='native-system' for system in port.systems)
    assert len(judged)==2

@pytest.mark.parametrize('name', ['create_file','patch_file','move_file','copy_file','rename_symbol',
                                  'plan','write_apply','rollback','project_command','run_check','chat'])
def test_write_plan_exec_and_recursive_requests_are_polite_refusals(name):
    result,trace,port,executed,judged=run([reply('request',{'action':name})])
    assert isinstance(result,str) and 'read-only' in result and executed==[]
    assert trace['actions_executed']==[] and trace['turns_used']==1

def test_low_native_judge_score_retries_despite_done():
    result,trace,port,executed,judged=run([reply('bad'),reply('correct')],
        scores=[dict(score=20,acceptable=False),dict(score=74,acceptable=True)])
    assert result=='correct' and trace['turns_used']==2
    assert '20' in port.prompts[1] and trace['judge_summary']=={'score':74,'acceptable':True}

def test_unknown_action_is_explained_and_bounded():
    result,trace,port,executed,judged=run([reply('unknown',{'action':'invented'})]*2,turns=2)
    assert trace['turns_used']==2 and not executed and 'Неизвестное действие' in result

@pytest.mark.parametrize('finish', ['error','interrupted'])
def test_error_and_incomplete_do_not_execute_partial_action(finish):
    result,trace,port,executed,judged=run([reply('partial',{'action':'read_file','paths':['res://a.gd']},False,finish),reply('recovered')])
    assert result=='recovered' and not executed and trace['turns_used']==2

def test_budget_truncates_output_and_tool_feedback():
    result,trace,port,executed,judged=run([reply('x'*40)],budget=7)
    assert len(result)<=7

def test_turn_budget_stops_missing_done():
    result,trace,port,executed,judged=run([reply('unfinished',done=False)]*2,turns=2)
    assert trace['turns_used']==2 and 'Лимит ходов' in result

def test_synthetic_multi_action_plan_never_expands_steps():
    result,trace,port,executed,judged=run([reply('multi',{'action':'plan','steps':[{'action':'read_file','paths':['res://a.gd']}]} )])
    assert 'read-only' in result and not executed

def test_registry_effect_is_checked_before_dispatch():
    calls=[]
    ctx=SimpleNamespace(registry=SimpleNamespace(get=lambda name:SimpleNamespace(spec=SimpleNamespace(effects='write'))),
                        call_tool=lambda *args:calls.append(args))
    with pytest.raises(AppError) as caught:
        import_module('python.modules.assistant.chat.app').execute_read(ctx,{'action':'read_file','paths':['res://a.gd']},80000)
    assert caught.value.kind=='denied' and calls==[]
