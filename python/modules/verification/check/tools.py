"""C.9 specification: read-only single-path verification, not C.8 check."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec

ARGS = {
    'type': 'object', 'required': ['path'], 'additionalProperties': False,
    'properties': {
        'path': {'type': 'string', 'minLength': 1},
        'kinds': {'type': 'array', 'minItems': 1, 'items': {
            'type': 'string', 'enum': ['gd', 'tscn', 'py', 'json', 'cfg', 'api', 'headless']}},
    },
}
RESULT = {
    'type': 'object',
    'required': ['path', 'problems', 'checked', 'auto_fixable', 'kinds', 'unavailable'],
    'additionalProperties': False,
    'properties': {
        'path': {'type': 'string', 'minLength': 1},
        'problems': {'type': 'array', 'items': {'type': 'string'}},
        'checked': {'type': 'boolean'}, 'auto_fixable': {'type': 'boolean'},
        'kinds': {'type': 'array', 'items': {'type': 'string'}},
        'unavailable': {'type': 'array', 'items': {
            'type': 'object', 'required': ['kind', 'reason'], 'additionalProperties': False,
            'properties': {'kind': {'type': 'string', 'minLength': 1},
                           'reason': {'type': 'string', 'minLength': 1}}}},
        'unchecked_reason': {'type': 'string', 'minLength': 1},
    },
}
VERIFY = ToolSpec(
    name='verify',
    description='Проверить один файл проекта текстовыми проверками и честно сказать, что проверено.',
    args=ARGS, result=RESULT, effects='read', idempotent=True,
    errors=('invalid_input', 'not_found', 'denied'), availability='*', cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES},
)
TOOLS = (VERIFY,)
