"""Complete a prepared native rename delta before the WAL preview is compiled."""
from python.formats.gdscript.method_guards import selected, tokenize
from python.kernel.errors import AppError


def complete(prepared, action):
    excluded = prepared.get('excluded_places', ())
    if action['kind'] != 'function' or action.get('mode') != 'probable': return
    old, new = action['old_name'], action['new_name']
    for item in prepared['files']:
        path = item['path']
        if not path.endswith('.gd'): continue
        # Keep BOM and line endings. This pass only changes the inside of a literal.
        before, after = (item[k].decode('utf-8') for k in ('before_bytes','after_bytes'))
        left, right = tokenize(before), tokenize(after)
        if len(left) != len(right): raise AppError('conflict', 'Структура токенов изменилась: '+path)
        starts = {a['start'] for a,b in zip(left,right) if a['value']==old and b['value']==new}
        positions = {a['start']:b for a,b in zip(left,right)}
        try: guards = list(selected(left,old,starts,{n for p,n in excluded if p==path}))
        except ValueError as e: raise AppError('conflict', str(e), details={'reason':'partial_guard'}) from e
        for guard in reversed(guards):
            target = positions[guard['start']]; start,end = target['start']+1,target['end']-1
            if after[start:end]!=old: raise AppError('conflict', 'Проверка has_method изменилась: '+path)
            after=after[:start]+new+after[end:]
            prefix='Не переименовано: %s:%s — '%(path,guard['line'])
            prepared['warnings']=[r for r in prepared.get('warnings',[]) if not r.startswith(prefix)]
        item['after_bytes']=after.encode('utf-8')
