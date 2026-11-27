from .common_tool_defs import APPLY_RESULT, DIGEST, ID, spec

TOOL = spec('assistant_confirm','Явно подтвердить или отклонить показанный план.',
            {'plan_id':ID,'digest':DIGEST,'approved':{'type':'boolean'}},['plan_id','digest','approved'],APPLY_RESULT,True)
