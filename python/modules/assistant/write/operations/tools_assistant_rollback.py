from .common_tool_defs import APPLY_RESULT, ID, spec

TOOL = spec('assistant_rollback','Откатить подтверждённую запись по квитанциям.',
            {'plan_id':ID,'entry_id':{'type':'string','minLength':1,'maxLength':150}},['plan_id','entry_id'],APPLY_RESULT,True)
