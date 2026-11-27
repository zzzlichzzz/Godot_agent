"""Read scene summary, strict schema; only new scene.json is generated."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec
from .domain.core import DEFAULT_MAX_CHARS


def _object(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


_STRING = {'type': 'string'}
_NULLABLE = {'type': ['string', 'null']}
SCENE = ToolSpec(
    name='scene',
    description=('Текстовая сводка файла .tscn/.scn: узлы, скрипты, инстансы, сигналы и ресурсы. '
                 'Текст дословно повторяет describe_scene; структура возвращается полностью. '
                 'truncated означает фактическую обрезку по max_chars (символы, не байты); '
                 'суффикс обрезки добавляется сверх квоты. Не запускает Godot и не пишет файлы.'),
    args={'type': 'object', 'properties': {
              'path': {'type': 'string', 'description': 'Относительный путь или res://scenes/player.tscn.'},
              'max_chars': {'type': 'integer', 'minimum': 0, 'default': DEFAULT_MAX_CHARS}},
          'required': ['path'], 'additionalProperties': False},
    result=_object({
        'text': _STRING, 'truncated': {'type': 'boolean'},
        'nodes': {'type': 'array', 'items': _object({
            'name': _STRING, 'type': _STRING, 'parent': _NULLABLE, 'path': _STRING,
            'depth': {'type': 'integer', 'minimum': 0}, 'script': _NULLABLE, 'instance': _NULLABLE})},
        'connections': {'type': 'array', 'items': _object({
            'from': _STRING, 'to': _STRING, 'signal': _STRING, 'method': _STRING})},
        'resources': _object({
            'ext': {'type': 'array', 'items': _object({
                'id': _STRING, 'type': _STRING, 'path': _STRING, 'uid': _NULLABLE})},
            'sub': {'type': 'array', 'items': _object({'id': _STRING, 'type': _STRING})}}),
    }),
    effects='read', idempotent=True, errors=('invalid_input', 'not_found', 'denied'),
    availability='*', cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES, 'max_chars': DEFAULT_MAX_CHARS},
)
TOOLS = (SCENE,)
