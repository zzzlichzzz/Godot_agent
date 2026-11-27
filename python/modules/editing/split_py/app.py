"""Consumer-owned read IO, PathPolicy and native plan/scan composition only."""
import errno
import json
from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from .domain import arch, core, groups, inventory, plan, refs, walk
from .ports import FileSystem
from .tools import ARGS, PLAN_ARGS
def _addon_root(fs, rel):
    parent = rel.rsplit('/',1)[0] if '/' in rel else ''
    while True:
        if fs.is_file((parent+'/' if parent else '')+'plugin.cfg'):
            return parent
        if not parent:
            raise AppError('invalid_input','донор не находится внутри аддона с plugin.cfg')
        parent = parent.rsplit('/',1)[0] if '/' in parent else ''

def _sources(fs, paths, prefix, policy, donor, donor_raw, eligible=walk.eligible):
    for path in paths:
        if not path.startswith(prefix):
            continue
        rel = path[len(prefix):]
        if not eligible(rel) or policy.deny_reason(path):
            continue
        try:
            raw = donor_raw if rel == donor else fs.read_raw(path)
        except OSError:
            continue
        yield rel, raw


def call(tool, args, ctx):
    if tool == 'split_apply':
        from . import apply_flow
        return apply_flow.call(args,ctx)
    rel, target = core.read_args(tool,args,PLAN_ARGS if tool=='split_plan' else ARGS)
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError('denied',reason)
    fs: FileSystem = ctx.port('fs')
    try:
        if not fs.is_file(rel):
            raise AppError('not_found','файл не найден: %s' % rel)
        root = _addon_root(fs,rel)
        prefix = root+'/' if root else ''
        donor = rel[len(prefix):]
        try:
            raw = fs.read_raw(rel)
        except FileNotFoundError:
            raise AppError('not_found','файл не найден: %s' % donor) from None
        if len(raw) > READ_TEXT_MAX_BYTES:
            raise AppError('invalid_input','файл больше лимита чтения')
        base = donor.rsplit('/',1)[-1]
        paths = fs.list_files()
        if tool == 'split_plan':
            source = inventory.decode(raw)
            info = inventory.file_inventory(source)
            chosen = args['groups'] if 'groups' in args else groups.suggest_groups(info,walk.stem(base),target)
            occupied = {p for p in groups.targets(donor,chosen) if fs.exists(prefix+p)}
            map_rel = prefix+'docs/architecture_map.json'
            try:
                map_raw = None if ctx.path_policy.deny_reason(map_rel) else json.loads(fs.read_raw(map_rel).decode('utf-8-sig'))
            except (OSError,ValueError):
                map_raw = None
            data = arch.load_map(map_raw)
            index = arch.name_index(_sources(fs,paths,prefix,ctx.path_policy,donor,raw,arch.eligible)) if data else {}
            prepared = plan.plan_split(donor,source,args.get('groups'),target,inventory=info,
                                       map_data=data,index=index,occupied=occupied)
        scan = None
        if tool == 'split_scan' or fs.is_file(rel):
            scan = refs.scan(donor,walk.stem(base),base,_sources(fs,paths,prefix,ctx.path_policy,donor,raw))
        return core.finish(prepared if tool=='split_plan' else None,donor,walk.stem(base),scan)
    except inventory.SplitError as exc:
        raise AppError('invalid_input',str(exc)) from None
    except PermissionError:
        raise AppError('denied','путь недоступен для безопасного чтения') from None
    except OSError as exc:
        if exc.errno == errno.EFBIG:
            raise AppError('invalid_input','файл больше лимита чтения') from None
        raise AppError('internal','не удалось прочитать файлы аддона') from None
