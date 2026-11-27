"""Only an explicitly named project brief is eligible for automatic context."""
from python.kernel.errors import AppError
from python.modules.context.shared.context_section import unavailable


BRIEF = 'res://AGENT_ARCHITECTURE.md'
BRIEF_CHARS = 1200


def project_brief(ctx):
    try:
        data = ctx.call_tool('read', {'path': BRIEF, 'max_chars': BRIEF_CHARS})
    except AppError as error:
        return unavailable('no_module' if error.kind in ('unknown_tool', 'unavailable', 'not_found') else 'failed')
    if not data['content'].strip():
        return unavailable('no_module')
    return {'path': data['path'], 'summary': data['content'], 'truncated': data['truncated']}
