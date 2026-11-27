"""Infer only a unique declaration; ambiguity is never a rename decision."""
from python.kernel.errors import AppError
from python.modules.code_intel.shared import symbol_index

from .core import declaration_kind


def infer_locator(index, kind, name, scope, policy):
    candidates = sorted('%s:%d:%d' % (item['path'], item['line'], item['column'])
                        for item in symbol_index.declarations(index)
                        if item['path'].endswith('.gd') and (scope is None or item['path'] == scope)
                        and item['kind'] == declaration_kind(kind) and item['name'] == name)
    if len(candidates) > 1:
        raise AppError('invalid_input', 'Несколько совпадающих объявлений: ' + ', '.join(candidates[:8]),
                       hint='Уточните declaration_path или передайте точный declaration.')
    if any(rel.lower().endswith('.gd') and (scope is None or scope == 'res://' + rel) and not policy.deny_reason(rel)
           for rel in index['skipped']):
        raise AppError('invalid_input', 'Не все видимые скрипты из области поиска были прочитаны.',
                       hint='Уточните declaration_path или передайте точный declaration.')
    if not candidates:
        raise AppError('not_found', 'В области поиска нет объявления с таким видом и именем.')
    return candidates[0]
