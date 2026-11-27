"""Module-owned tool aggregate; each schema lives with its single tool."""
from .schemas.tools_split_scan import ARGS, COUNTS, KINDS, OCCURRENCE, RESULT, SCAN
from .schemas.tools_split_plan import PLAN, PLAN_ARGS, PLAN_RESULT
from .schemas.tools_split_apply import APPLY, APPLY_ARGS, APPLY_RESULT

TOOLS = (SCAN, PLAN, APPLY)
