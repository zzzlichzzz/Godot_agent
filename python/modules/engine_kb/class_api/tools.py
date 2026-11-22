"""C.11 by specification: read-only class API, typed legacy projection."""
from python.kernel.tool_spec import ToolSpec

ARGS = {
    'type': 'object', 'required': ['class_name'], 'additionalProperties': False,
    'properties': {'class_name': {'type': 'string', 'minLength': 1, 'maxLength': 120}},
}
RESULT = {
    'type': 'object',
    'required': ['class_name', 'found', 'cache_version', 'inherits',
                 'methods', 'properties', 'signals', 'unavailable'],
    'additionalProperties': False,
    'properties': {
        'class_name': {'type': 'string', 'minLength': 1},
        'found': {'type': 'boolean'}, 'cache_version': {'type': 'string'},
        'inherits': {'type': 'array', 'items': {'type': 'string'}},
        'methods': {'type': 'array', 'items': {
            'type': 'object',
            'required': ['name', 'min_args', 'max_args', 'signature'],
            'additionalProperties': False,
            'properties': {
                'name': {'type': 'string', 'minLength': 1},
                'min_args': {'type': 'integer'}, 'max_args': {'type': 'integer'},
                'signature': {'type': 'string'},
            },
        }},
        'properties': {'type': 'array', 'items': {'type': 'string'}},
        'signals': {'type': 'array', 'items': {'type': 'string'}},
        'unavailable': {'type': 'array', 'items': {
            'type': 'object', 'required': ['kind', 'reason'], 'additionalProperties': False,
            'properties': {'kind': {'type': 'string', 'minLength': 1},
                           'reason': {'type': 'string', 'minLength': 1}},
        }},
    },
}
API = ToolSpec(
    name='api',
    description='Методы, свойства и сигналы класса Godot по всей цепочке наследования из кэша API.',
    args=ARGS, result=RESULT, effects='read', idempotent=True,
    errors=('invalid_input',), availability='*', cost='cheap', limits={},
)
TOOLS = (API,)
