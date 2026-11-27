# C.12: descriptor is the source; api_check never reads the supplied path.
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec

ARGS = {
    'type': 'object', 'required': ['path', 'content'], 'additionalProperties': False,
    'properties': {
        'path': {'type': 'string', 'minLength': 1},
        'content': {'type': 'string'},
    },
}
RESULT = {
    'type': 'object',
    'required': ['path', 'problems', 'checked', 'base_class', 'unavailable'],
    'additionalProperties': False,
    'properties': {
        'path': {'type': 'string', 'minLength': 1},
        'problems': {'type': 'array', 'items': {'type': 'string'}},
        'checked': {'type': 'boolean'},
        'base_class': {'type': 'string'},
        'unavailable': {'type': 'array', 'items': {
            'type': 'object', 'required': ['kind', 'reason'], 'additionalProperties': False,
            'properties': {'kind': {'type': 'string', 'minLength': 1},
                           'reason': {'type': 'string', 'minLength': 1}},
        }},
    },
}
API_CHECK = ToolSpec(
    name='api_check',
    description='Сверить self.* и connect() в тексте .gd с кэшем Godot API; честно сказать, что проверено.',
    args=ARGS, result=RESULT, effects='read', idempotent=True,
    errors=('invalid_input', 'denied'), availability='*', cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES},
)
TOOLS = (API_CHECK,)


# C.13 contribution: invoke this module's app; the supplied text is never reread.
from python.modules.verification.shared.check_kind import CheckKind


def _verify_api(text, path, ctx):
    from .app import call
    result = call('api_check', {'path': path, 'content': text}, ctx)
    return {'problems': result['problems'], 'auto_fixable': False,
            'checked': result['checked'], 'unavailable': result['unavailable']}


CONTRIBUTIONS = (CheckKind('api', ('.gd',), _verify_api),)
