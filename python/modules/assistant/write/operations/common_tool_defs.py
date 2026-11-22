"""Shared closed fields, not aggregate tool schemas."""
from python.kernel.tool_spec import ToolSpec
from ..domain.core import MAX_FILES,MAX_PARENTS
"""T1 assistant write contracts; model actions are data, approval is explicit."""

TEXT={'type':'string','minLength':1,'maxLength':200000}

ID={'type':'string','pattern':'^[a-zA-Z0-9_-]{1,100}$'}

DIGEST={'type':'string','pattern':'^[0-9a-f]{64}$'}

ACTION={'type':'object','properties':{'action':TEXT},'required':['action'],'additionalProperties':True}

DIFF={'type':'object','properties':{'path':TEXT,'before':{'type':['string','null']},'after':{'type':['string','null']}},
      'required':['path','before','after'],'additionalProperties':False}

PLAN_RESULT={'type':'object','properties':{'state':{'type':'string','enum':['PREPARED','ALREADY_SATISFIED']},
    'plan_id':ID,'digest':DIGEST,'diffs':{'type':'array','items':DIFF,'maxItems':100},
    'steps_count':{'type':'integer','minimum':0,'maximum':MAX_FILES+MAX_PARENTS},'confirm_ttl':{'type':'integer'},
    'warnings':{'type':'array','items':{'type':'string'}}},
    'required':['state','plan_id','digest','diffs','steps_count','confirm_ttl','warnings'],'additionalProperties':False}

APPLY_RESULT={'type':'object','properties':{'state':{'type':'string','enum':['REJECTED','COMMITTED','ROLLED_BACK']},
    'plan_id':ID,'entry_id':{'type':'string'},'result':{'type':'object','additionalProperties':True}},
    'required':['state','plan_id','entry_id','result'],'additionalProperties':False}

TURN_RESULT={'type':'object','properties':{'state':{'type':'string','enum':['final','pending_confirmation']},
    'text':{'type':'string'},'action':{'type':['object','null'],'additionalProperties':True},
     'plan':dict(PLAN_RESULT,type=['object','null']),'turns_used':{'type':'integer','minimum':1,'maximum':8}},
    'required':['state','text','action','plan','turns_used'],'additionalProperties':False}

ERRORS=('invalid_input','not_found','denied','stale_plan','conflict','unavailable','internal')

def spec(name,description,properties,required,result,preview=False):
    return ToolSpec(name=name,description=description,
        args={'type':'object','properties':properties,'required':required,'additionalProperties':False},
        result=result,effects='write',idempotent=False,errors=ERRORS,cost='bounded',requires_preview=preview,
        limits={'max_files':100,'max_action_chars':200000})
