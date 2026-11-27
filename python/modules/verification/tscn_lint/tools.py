"""C.8 specification before behavior; returned fixed is data, never written."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec

RESULT = {
    'type': 'object',
    'properties': {'fixed': {'type': 'string'}, 'changed': {'type': 'boolean'},
                   'problems': {'type': 'array', 'items': {'type': 'string'}}},
    'required': ['fixed', 'changed', 'problems'], 'additionalProperties': False,
}
CHECK = ToolSpec(
    name='check',
    description=('Структурная проверка candidate-текста .tscn/.scn: механически '
                 'исправленный fixed, changed и полные упорядоченные строковые '
                 'problems. Это данные: не исполняет текст, не пишет файл, '
                 'не запускает Godot и не является агрегатором проверок.'),
    args={'type': 'object',
          'properties': {'path': {'type': 'string', 'description': 'res:// путь .tscn/.scn.'},
                         'content': {'type': 'string'},
                         'planned_paths': {'type': 'array', 'items': {'type': 'string'}, 'default': []}},
          'required': ['path', 'content'], 'additionalProperties': False},
    result=RESULT, effects='read', idempotent=True,
    errors=('invalid_input', 'not_found', 'denied'), availability='*', cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES},
)
TOOLS = (CHECK,)


# C.9 contribution: candidate is supplied; accepted dependency reads are retained.
from python.modules.verification.shared.check_kind import CheckKind


def _verify_tscn(text, path, ctx):
    from .app import call
    result = call('check', {'path': path, 'content': text}, ctx)
    return {'problems': result['problems'], 'auto_fixable': result['fixed'] != text}


CONTRIBUTIONS = (CheckKind('tscn', ('.tscn',), _verify_tscn),)
