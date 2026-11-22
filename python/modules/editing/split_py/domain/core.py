"""Pure public projection; file lists are derived from retained occurrences only."""


def assemble(donor, stem, refs):
    occurrences = [{'file': hit['rel'], 'line': hit['line'], 'kind': hit['kind'], 'text': hit['text']}
                   for hit in refs['occurrences']]
    hard = sorted({hit['file'] for hit in occurrences if hit['kind'] in ('import','source_read','patch')})
    soft = sorted({hit['file'] for hit in occurrences if hit['kind'] in ('mention','doc')})
    return {'donor': donor, 'stem': stem, 'counts': dict(refs['counts']),
            'occurrences': occurrences, 'hard_files': hard, 'soft_files': soft,
            'truncated': refs['truncated']}


def assemble_plan(prepared):
    result = {key:prepared[key] for key in ('donor','donor_sha256','donor_lines','target_lines',
              'auto_groups','moved_names','errors','warnings','inventory','refs')}
    result['modules'] = [{key:item[key] for key in ('rel','names','lines')} for item in prepared['modules']]
    result['facade'] = {key:prepared['facade'][key] for key in ('rel','lines','reexports')}
    return result


def read_args(tool, args, schema):
    from python.kernel.errors import AppError
    from python.kernel.paths import normalize_rel
    from python.kernel.schema import validate
    from .groups import target_lines
    if tool not in ('split_scan','split_plan'):
        raise AppError('unknown_tool','модуль editing.split_py не владеет этим инструментом')
    if tool == 'split_plan' and isinstance(args,dict) and 'target_lines' in args:
        target_lines(args['target_lines'])
    if validate(args,schema) or not args['path'].startswith('res://'):
        raise AppError('invalid_input','укажите непустой path в формате res://…py')
    rel = normalize_rel(args['path'][6:])
    if rel is None:
        raise AppError('denied','путь вне проекта')
    if not rel.lower().endswith('.py'):
        message = 'split_scan работает только с .py' if tool == 'split_scan' else 'пила работает только с .py: %s' % rel
        raise AppError('invalid_input',message)
    return rel, args.get('target_lines',900)


def finish(prepared, donor, stem, scan):
    from .plan import attach_refs
    if prepared is None:
        return assemble(donor,stem,scan)
    if scan is not None:
        public = assemble(donor,stem,scan)
        scan.update(hard_files=public['hard_files'],soft_files=public['soft_files'])
        attach_refs(prepared,scan)
    return assemble_plan(prepared)
