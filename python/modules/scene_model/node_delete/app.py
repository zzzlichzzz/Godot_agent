"""Port reads and typed errors; deletion never obtains a writer/editor port."""
from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import normalize_rel
from .domain import core
from .settings import CLEANUP_CODE


def _relative(path):
    return normalize_rel(path[6:] if path.startswith('res://') else path)


def _read(fs, rel):
    try:
        raw = fs.read_raw(rel)
    except FileNotFoundError:
        raise AppError('not_found', 'Файл сцены не найден: res://' + rel) from None
    except PermissionError:
        raise AppError('denied', 'Сцена защищена текущей политикой доступа') from None
    except OSError:
        raise AppError('invalid_input', 'Не удалось прочитать файл проекта') from None
    if len(raw) > READ_TEXT_MAX_BYTES:
        raise AppError('invalid_input', 'Файл превышает лимит чтения')
    return raw


def call(tool, args, ctx):
    if tool != 'node_delete_preview':
        raise AppError('unknown_tool', 'Неизвестный инструмент')
    path = args['path'].strip().replace('\\', '/')
    if not path.startswith('res://') or not path.lower().endswith(('.tscn', '.scn')):
        shown = path if path.startswith('res://') else '[путь]'
        raise AppError('invalid_input', 'scene должен быть res:// путём к .tscn: ' + shown)
    rel = _relative(path)
    if rel is None or not ctx.path_policy.can_read(rel):
        raise AppError('denied', 'Сцена защищена текущей политикой доступа')
    fs = ctx.port('fs')
    raw = _read(fs, rel)
    view = core.prepare_scene(raw)
    try:
        _, deleted = core.validate_delete(view, args['node'])
    except ValueError as error:
        raise AppError('invalid_input', str(error)) from None
    scripts = {}
    cleanup = args.get('cleanup_code', CLEANUP_CODE)
    if cleanup:
        for resource in core.script_groups(view, deleted):
            script_rel = _relative(resource)
            if script_rel is None or not ctx.path_policy.can_read(script_rel):
                continue
            try:
                scripts[resource] = _read(fs, script_rel)
            except AppError as error:
                if error.kind not in ('not_found', 'denied'):
                    raise
    try:
        return core.prepare_delete(raw, 'res://' + rel, args['node'], scripts,
            ctx.port('node_diff'), cleanup_code=cleanup, view=view)
    except ValueError as error:
        raise AppError('invalid_input', str(error)) from None
