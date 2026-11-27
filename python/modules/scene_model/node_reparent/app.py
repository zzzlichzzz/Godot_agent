"""Port reads and typed client errors; no project writes or editor calls."""
from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import normalize_rel
from .domain import core
from .settings import UPDATE_SCRIPTS


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
    if tool != 'node_reparent_preview':
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
        core.validate_reparent(view, args['node'], args['new_parent'])
    except ValueError as error:
        raise AppError('invalid_input', str(error)) from None
    scripts = {}
    update = args.get('update_scripts', UPDATE_SCRIPTS)
    if update:
        for resource in core.attached_scripts(view):
            script_rel = _relative(resource)
            if script_rel is None or not ctx.path_policy.can_read(script_rel):
                continue
            try:
                scripts[resource] = _read(fs, script_rel)
            except AppError as error:
                if error.kind not in ('not_found', 'denied'):
                    raise
    try:
        return core.prepare_reparent(raw, 'res://' + rel, args['node'], args['new_parent'],
            scripts, ctx.port('gd_lint'), ctx.port('node_diff'), update_scripts=update, view=view)
    except ValueError as error:
        raise AppError('invalid_input', str(error)) from None
