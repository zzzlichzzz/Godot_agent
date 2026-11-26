"""One closed translation table for the read-only side of both chat loops."""
import json

from python.kernel.errors import AppError


# The first item is the registry name. The rest are real public schema fields.
READ_ACTIONS = {
    'list_files': ('tree', 'subdir', 'max_depth', 'max_entries', 'only_exts'),
    'read_file': ('read', 'path', 'max_chars', 'start_line', 'end_line', 'offset'),
    'read_function': ('functions', 'path', 'names'),
    'search_project': ('search', 'query', 'max_results', 'context_lines', 'case_insensitive',
                       'include_rel_prefixes', 'exclude_rel_prefixes', 'only_exts', 'offset', 'snippet_chars'),
    'ask_librarian': ('ask', 'query', 'budget_chars'),
    'list_scene': ('scene', 'path', 'max_chars'),
    'gather_context': ('context', 'sections', 'path'),
    'find_symbol_usages': ('usages', 'kind', 'old_name', 'declaration', 'declaration_path', 'new_name'),
    'analyze_rename': ('analyze_rename', 'kind', 'old_name', 'new_name', 'declaration',
                        'declaration_path', 'mode', 'allow_unverified'),
}
ALIASES = {'list_files': ('dir', 'subdir'), 'list_scene': ('scene', 'path'),
           'read_function': ('name', 'names')}


def available(ctx, name):
    entry = ctx.registry.get(name) if ctx.registry is not None else None
    return entry is not None and entry.spec.effects == 'read'


def read_requests(action, budget):
    kind = action.get('action')
    if not isinstance(kind, str) or kind not in READ_ACTIONS:
        raise AppError('denied', 'действие не входит в read-only allowlist')
    tool, *fields = READ_ACTIONS[kind]
    alias, target = ALIASES.get(kind, (None, None))
    extra = ('paths',) if kind in ('read_file', 'read_function') else ()
    if any(key not in fields and key not in ('action', 'reason', alias, *extra) for key in action):
        raise AppError('invalid_input', 'неподдерживаемые поля для '+kind)
    args = {key: action[key] for key in fields if key in action}
    if isinstance(args.get('only_exts'), list):
        args['only_exts'] = ['.'+ext if isinstance(ext, str) and ext.isalnum() else ext for ext in args['only_exts']]
    if alias in action:
        if target in args:
            raise AppError('invalid_input', 'укажи только одно: '+alias+' или '+target)
        args[target] = [action[alias]] if kind == 'read_function' else action[alias]
    if 'paths' in action and 'path' in args and action['paths'] != [args['path']]:
        # Native parser retains `path` when it synthesizes `paths: [path]`.
        raise AppError('invalid_input', 'path и paths указывают на разные файлы')
    if kind == 'read_file':
        paths = action.get('paths', [args.get('path')])
        if not isinstance(paths, list) or not 1 <= len(paths) <= 5 or not all(
                isinstance(path, str) and path for path in paths):
            raise AppError('invalid_input', 'read_file требует path или от одного до пяти paths')
        paths = list(dict.fromkeys(paths))  # Exact repeats only. Resolve aliases under the tool's policy.
        requested = args.get('max_chars', 30000)
        if type(requested) is int and 1 <= requested <= 200000:
            # Reserve room for metadata and leave the tool responsible for schema validation.
            args['max_chars'] = min(requested, max(1, budget // len(paths) - 320))
        args.setdefault('offset', 0)
        return [(tool, dict(args, path=path)) for path in paths]
    if kind == 'read_function' and 'paths' in action:
        paths = action['paths']
        if not isinstance(paths, list) or len(paths) != 1 or not isinstance(paths[0], str) or not paths[0]:
            raise AppError('invalid_input', 'read_function требует один path')
        args['path'] = paths[0]
    if kind == 'gather_context':
        args.setdefault('sections', ['project', 'tools'])
    if kind == 'search_project':
        args.setdefault('offset', 0)
        count = args.setdefault('max_results', 12)
        if type(count) is int and count > 0:
            args.setdefault('snippet_chars', max(64, min(1000, budget // count - 320)))
    return [(tool, args)]


def execute_read(ctx, action, budget):
    requests = read_requests(action, budget)
    for name, _ in requests:
        if not available(ctx, name):
            raise AppError('denied', 'инструмент не является доступным READ: '+name)
    names, values = [], []
    remaining = budget - 2
    for name, args in requests:
        if remaining <= 0:
            break
        names.append(name)
        try:
            value = ctx.call_tool(name, args)
        except AppError as error:
            value = {'error': {'kind': error.kind, 'message': error.message}}
            if error.details.get('target_type') == 'directory':
                value['error'].update(target_type='directory', hint='Use list_files with subdir.')
        encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        if len(encoded) > remaining:
            encoded = '{"error":"Result exceeds chat budget; narrow the request."}'
        if len(encoded) > remaining:
            break
        values.append(encoded)
        remaining -= len(encoded) + 1
    return names, '['+','.join(values)+']' if budget >= 2 else ''
