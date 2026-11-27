"""Read-only orchestration: path policy -> declared bytes port -> domain."""
import errno
from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel
from .domain import core


def call(tool, args, ctx):
    if tool != 'scene':
        raise AppError('unknown_tool', 'модуль scene_model.tree не владеет этим инструментом')
    path = str(args.get('path') or '').strip()
    value = path.removeprefix('res://')
    rel = normalize_rel(value)
    if rel is None or '://' in value:
        raise AppError('invalid_input', 'путь вне проекта',
                       hint='Укажите относительный путь или res://scenes/player.tscn')
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError('denied', reason)
    try:
        raw = ctx.port('fs').read_raw(rel)
    except FileNotFoundError:
        raise AppError('not_found', 'Файл не найден: %s' % path) from None
    except PermissionError:
        raise AppError('invalid_input', 'путь недоступен для безопасного чтения') from None
    except OSError as exc:
        if exc.errno == errno.EFBIG:
            raise AppError('invalid_input', 'файл больше лимита чтения',
                           hint='Максимальный размер указан в limits.max_file_bytes') from None
        raise
    if not rel.lower().endswith(('.tscn', '.scn')):
        raise AppError('invalid_input', 'list_scene работает только со сценами .tscn: %s' % path)
    try:
        return core.describe(raw, args.get('max_chars', core.DEFAULT_MAX_CHARS))
    except ValueError as exc:
        raise AppError('invalid_input', str(exc)) from None
