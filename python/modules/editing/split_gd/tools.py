"""Frozen scan contract plus additive read-only C.15 plan metadata."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec

ARGS = {
    'type': 'object', 'required': ['path'], 'additionalProperties': False,
    'properties': {'path': {'type': 'string', 'minLength': 1}},
}
COUNTS = {
    'type': 'object', 'required': ['path', 'source_read', 'call', 'doc', 'mention'],
    'additionalProperties': False,
    'properties': {kind: {'type': 'integer'}
                   for kind in ('path', 'source_read', 'call', 'doc', 'mention')},
}
OCCURRENCE = {
    'type': 'object', 'required': ['file', 'line', 'kind', 'text'],
    'additionalProperties': False,
    'properties': {
        'file': {'type': 'string', 'minLength': 1}, 'line': {'type': 'integer'},
        'kind': {'type': 'string', 'enum': ['path', 'source_read', 'call', 'doc', 'mention']},
        'text': {'type': 'string'},
    },
}
RESULT = {
    'type': 'object',
    'required': ['donor', 'lines', 'extends', 'class_name', 'funcs', 'consts',
                 'vars', 'public_methods', 'counts', 'occurrences',
                 'truncated', 'hard_files', 'soft_files'],
    'additionalProperties': False,
    'properties': {
        'donor': {'type': 'string', 'minLength': 1}, 'lines': {'type': 'integer'},
        'extends': {'type': 'string'}, 'class_name': {'type': 'string'},
        'funcs': {'type': 'integer'}, 'consts': {'type': 'integer'}, 'vars': {'type': 'integer'},
        'public_methods': {'type': 'array', 'items': {'type': 'string'}},
        'counts': COUNTS, 'occurrences': {'type': 'array', 'items': OCCURRENCE},
        'truncated': {'type': 'boolean'},
        'hard_files': {'type': 'array', 'items': {'type': 'string'}},
        'soft_files': {'type': 'array', 'items': {'type': 'string'}},
    },
}
SCAN = ToolSpec(
    name='split_gd_scan',
    description='Карта ссылок на .gd агента: кто им пользуется и что поедет при разбиении. Только чтение.',
    args=ARGS, result=RESULT, effects='read', idempotent=True,
    errors=('invalid_input', 'not_found', 'denied'), availability='*', cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES},
)

GROUP = {
    'type': 'object', 'required': ['module', 'funcs'], 'additionalProperties': False,
    'properties': {'module': {'type': 'string', 'minLength': 1},
                   'funcs': {'type': 'array', 'items': {'type': 'string'}}},
}
PLAN_ARGS = {
    'type': 'object', 'required': ['path'], 'additionalProperties': False,
    'properties': {'path': {'type': 'string', 'minLength': 1},
                   'groups': {'type': 'array', 'items': GROUP},
                   'target_lines': {'type': 'integer'}},
}
PLAN_MODULE = {
    'type': 'object', 'required': ['rel', 'const', 'funcs', 'lines'],
    'additionalProperties': False,
    'properties': {'rel': {'type': 'string', 'minLength': 1},
                   'const': {'type': 'string', 'minLength': 1},
                   'funcs': {'type': 'array', 'items': {'type': 'string'}},
                   'lines': {'type': 'integer'}},
}
WRAPPER = {
    'type': 'object', 'required': ['name', 'module', 'await'], 'additionalProperties': False,
    'properties': {'name': {'type': 'string'}, 'module': {'type': 'string'},
                   'await': {'type': 'boolean'}},
}
STATS = {
    'type': 'object', 'required': ['moved', 'modules', 'donor_before', 'donor_after'],
    'additionalProperties': False,
    'properties': {key: {'type': 'integer'}
                   for key in ('moved', 'modules', 'donor_before', 'donor_after')},
}
PLAN_RESULT = {
    'type': 'object', 'additionalProperties': False,
    'required': ['schema', 'kind', 'donor', 'donor_sha256', 'newline', 'target_lines',
                 'groups', 'modules', 'wrappers', 'warnings', 'stats'],
    'properties': {
        'schema': {'type': 'integer', 'enum': [1]},
        'kind': {'type': 'string', 'enum': ['split_gd']},
        'donor': {'type': 'string', 'minLength': 1},
        'donor_sha256': {'type': 'string', 'minLength': 64, 'maxLength': 64},
        'newline': {'type': 'string', 'enum': ['\n', '\r\n', '\r']},
        'target_lines': {'type': 'integer'}, 'groups': {'type': 'array', 'items': GROUP},
        'modules': {'type': 'array', 'items': PLAN_MODULE},
        'wrappers': {'type': 'array', 'items': WRAPPER},
        'warnings': {'type': 'array', 'items': {'type': 'string'}}, 'stats': STATS,
    },
}
PLAN = ToolSpec(
    name='split_gd_plan',
    description='План разбиения .gd агента: модули, обёртки, строки донора. Только чтение.',
    args=PLAN_ARGS, result=PLAN_RESULT, effects='read', idempotent=True,
    errors=('invalid_input', 'not_found', 'denied'), availability='*', cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES},
)
TOOLS = (SCAN, PLAN)
