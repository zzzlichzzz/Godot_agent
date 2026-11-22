"""Read-only path policy -> declared raw reader -> pure node resolver/card."""
import errno
from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel
from .domain import core


def call(tool, args, ctx):
    if tool != 'node':
        raise AppError('unknown_tool', 'модуль scene_model.node_info не владеет этим инструментом')
    path = str(args.get('path') or '').strip()
    value = path.removeprefix('res://')
    rel = normalize_rel(value)
    if rel is None or '://' in value:
        raise AppError('invalid_input', 'путь вне проекта',
                       hint='Укажите относительный путь или res://scenes/player.tscn')
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError('denied', reason)
    if not rel.lower().endswith(('.tscn', '.scn')):
        raise AppError('invalid_input', 'node работает только со сценами .tscn/.scn: %s' % path)
    try:
        raw = ctx.port('fs').read_raw(rel)
    except FileNotFoundError:
        raise AppError('not_found', 'Файл сцены не найден: %s' % path) from None
    except PermissionError:
        raise AppError('invalid_input', 'путь недоступен для безопасного чтения') from None
    except OSError as exc:
        if exc.errno == errno.EFBIG:
            raise AppError('invalid_input', 'файл больше лимита чтения',
                           hint='Максимальный размер указан в limits.max_file_bytes') from None
        raise
    try:
        return core.describe(raw, args['node'])
    except ValueError as exc:
        raise AppError('invalid_input', str(exc)) from None
