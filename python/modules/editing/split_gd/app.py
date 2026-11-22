"""PathPolicy -> consumer read ports -> pure scan/plan; payload/AppError, never writes."""
import errno

from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import normalize_rel
from python.kernel.schema import validate

from .domain import core, inventory, refs, text
from . import plan_io
from .ports import FileSystem
from .tools import ARGS, PLAN_ARGS


def _addon_root(fs, rel):
    parent = rel.rsplit('/', 1)[0] if '/' in rel else ''
    while True:
        if fs.is_file((parent + '/' if parent else '') + 'plugin.cfg'):
            return parent
        if not parent:
            raise AppError('invalid_input', 'донор не находится внутри аддона с plugin.cfg')
        parent = parent.rsplit('/', 1)[0] if '/' in parent else ''


def _sources(fs, paths, prefix, policy, donor, donor_raw):
    for path in paths:
        if not path.startswith(prefix):
            continue
        rel = path[len(prefix):]
        if not refs.eligible(rel) or policy.deny_reason(path):
            continue
        try:
            raw = donor_raw if rel == donor else fs.read_raw(path)
        except OSError:
            continue
        yield rel, raw


def call(tool, args, ctx):
    if tool not in ('split_gd_scan', 'split_gd_plan'):
        raise AppError('unknown_tool', 'модуль editing.split_gd не владеет этим инструментом')
    if validate(args, PLAN_ARGS if tool == 'split_gd_plan' else ARGS) or not args['path'].startswith('res://'):
        raise AppError('invalid_input', 'укажите непустой path в формате res://…gd')
    rel = normalize_rel(args['path'][6:])
    if rel is None:
        raise AppError('denied', 'путь вне проекта')
    if not rel.lower().endswith('.gd'):
        raise AppError('invalid_input', '%s работает только с .gd' % tool)
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError('denied', reason)
    target = core.target_lines(args.get('target_lines', 0)) if tool == 'split_gd_plan' else None
    fs: FileSystem = ctx.port('fs')
    try:
        if not fs.is_file(rel):
            raise AppError('not_found', 'донор не найден: res://%s' % rel)
        root = _addon_root(fs, rel)
        try:
            raw = fs.read_raw(rel)
        except FileNotFoundError:
            raise AppError('not_found', 'донор не найден: res://%s' % rel) from None
        if len(raw) > READ_TEXT_MAX_BYTES:
            raise AppError('invalid_input', 'файл больше лимита чтения')
        prefix = root + '/' if root else ''
        donor = rel[len(prefix):]
        info = inventory.file_inventory(text.decode(raw))
        if tool == 'split_gd_plan':
            return plan_io.call(fs, ctx, prefix, donor, raw, info, args.get('groups'), target)
        files = _sources(fs, fs.list_files(), prefix, ctx.path_policy, donor, raw)
        return core.assemble(donor, info, refs.scan(donor, core.public_methods(info), files))
    except PermissionError:
        raise AppError('denied', 'путь недоступен для безопасного чтения') from None
    except OSError as exc:
        if exc.errno == errno.EFBIG:
            raise AppError('invalid_input', 'файл больше лимита чтения') from None
        raise AppError('internal', 'не удалось прочитать файлы аддона') from None
