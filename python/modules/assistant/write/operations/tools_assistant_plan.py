from .common_tool_defs import ACTION, PLAN_RESULT, spec

TOOL = spec('assistant_plan','Подготовить нативное действие; только preview, без изменения проекта.',
            {'action':ACTION},['action'],PLAN_RESULT)
