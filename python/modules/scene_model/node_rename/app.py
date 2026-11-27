"""Raw reads through consumer ports; pure planner owns all rename decisions."""
from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import normalize_rel
from .domain import core


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
    if tool != 'node_rename_preview':
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
        core.validate_rename(view, args['node'], args['new_name'], args.get('previous_name', ''))
    except ValueError as error:
        raise AppError('invalid_input', str(error)) from None
    scripts = {}
    if args.get('update_scripts', True):
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
        return core.prepare_rename(raw, 'res://' + rel, args['node'], args['new_name'], scripts, ctx.port('gd_lint'),
            update_scripts=args.get('update_scripts', True), scripts_only=args.get('scripts_only', False),
            previous_name=args.get('previous_name', ''), view=view)
    except ValueError as error:
        raise AppError('invalid_input', str(error)) from None
