from .common_tool_defs import TEXT, TURN_RESULT, spec

TOOL = spec('assistant_turn','Диалог с нативным парсером; запись только после отдельного подтверждения.',
            {'text':TEXT,'max_turns':{'type':'integer','minimum':1,'maximum':8}},['text'],TURN_RESULT)
