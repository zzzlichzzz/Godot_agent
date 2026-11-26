"""Public schema for file transactions and the legacy native action envelope."""
from dataclasses import replace

from .common_tool_defs import ACTION, PLAN_RESULT, TEXT, spec


CONTENT = {'type': 'string', 'maxLength': 200000}
PATH = dict(TEXT, description='Путь в проекте, например res://scripts/player.gd.')


def operation(**fields):
    return {'type': 'object', 'properties': {'path': PATH, **fields},
            'required': ['path', *fields], 'additionalProperties': False}


OPERATIONS = {'type': 'array', 'minItems': 1, 'maxItems': 30, 'items': {
    'type': 'object', 'minProperties': 1, 'maxProperties': 1,
    'properties': {'create_file': operation(content=CONTENT),
                   'patch_file': operation(search=dict(TEXT, description='Точный уникальный фрагмент.'),
                                           replace=CONTENT),
                   'move_file': operation(dest=PATH)},
    'additionalProperties': False,
}}

_BASE = spec('assistant_plan', 'Предпросмотр без записи. Передайте operations для правок текстовых файлов '
             'или action для существующих нативных действий. Для применения требуется явное '
             'подтверждение пользователя через assistant_confirm.',
             {'action': ACTION, 'operations': OPERATIONS}, [], PLAN_RESULT)
TOOL = replace(_BASE, args=dict(_BASE.args, minProperties=1, maxProperties=1))
