"""Literal native grouping, rewriting and rendering; generated text stays private."""
import re

from python.kernel.errors import AppError
from .collect import ENGINE_VIRTUALS, collect_locals
from .tokens import KEYWORDS, prev_token, tokenize

PANEL = 'panel'


def suggest_groups(inventory, stem, target_lines=1100):
    funcs = [f for f in inventory['funcs'] if f['name'] not in ENGINE_VIRTUALS]
    if not funcs:
        raise AppError('invalid_input', 'в файле нет методов для выноса')
    chunks, current, size = [], [], 0
    for func in funcs:
        cost = func['end'] - func['block_start'] + 2
        if current and size + cost > target_lines:
            chunks.append(current)
            current, size = [], 0
        current.append(func)
        size += cost
    if current:
        chunks.append(current)
    return [{'module': '%s_part%d' % (stem, index), 'funcs': [f['name'] for f in chunk]}
            for index, chunk in enumerate(chunks, 1)]


def normalize_groups(groups, func_by_name):
    if not groups:
        raise AppError('invalid_input', 'пустой список групп (--groups или auto)')
    if isinstance(groups, dict):
        groups = groups.get('groups')
    result, seen, used = [], set(), {}
    for index, raw in enumerate(groups, 1):
        if not isinstance(raw, dict):
            raise AppError('invalid_input', 'группа %d: ожидается объект {module, funcs}' % index)
        module = str(raw.get('module') or '').strip()
        if not re.match(r'^[a-z][a-z0-9_]*$', module):
            raise AppError('invalid_input', 'группа %d: некорректное имя модуля %r' % (index, module))
        if module in seen:
            raise AppError('invalid_input', 'модуль %s указан дважды' % module)
        seen.add(module)
        names = raw.get('funcs')
        if not isinstance(names, list) or not names:
            raise AppError('invalid_input', 'группа %s: пустой список funcs' % module)
        clean = []
        for name in names:
            name = str(name)
            if name not in func_by_name:
                raise AppError('invalid_input', 'метод %s не найден в доноре' % name)
            if name in used:
                raise AppError('invalid_input', 'метод %s назначен дважды (модули %s и %s)' % (name, used[name], module))
            used[name] = module
            clean.append(name)
        result.append({'module': module, 'funcs': clean})
    return result


def apply_edits(text, edits):
    if not edits:
        return text
    out, cursor = [], 0
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1])):
        if start < cursor:
            continue
        out.append(text[cursor:start])
        out.append(replacement)
        cursor = end
    out.append(text[cursor:])
    return ''.join(out)


def rewrite_body(body, context):
    tokens = tokenize(body)
    locals_ = collect_locals(tokens)
    locals_.update(context.get('params') or ())
    edits, unknowns = [], set()
    index, size = 0, len(tokens)
    while index < size:
        token = tokens[index]
        value = token['value']
        if token['kind'] == 'identifier':
            if value == 'self':
                edits.append((token['start'], token['end'], PANEL))
            elif value not in KEYWORDS and value not in locals_ and value not in context['copies']:
                prev = prev_token(tokens, index)
                if not (prev is not None and prev['value'] == '.'):
                    if value in context['funcs'] or value in context['vars']:
                        edits.append((token['start'], token['start'], PANEL + '.'))
                    elif value in context['methods'] or value in context['props']:
                        edits.append((token['start'], token['start'], PANEL + '.'))
                    else:
                        unknowns.add(value)
            index += 1
            continue
        if token['kind'] == 'symbol' and value == '$':
            if index + 1 < size and tokens[index + 1]['kind'] == 'string':
                path = tokens[index + 1]
                edits.append((token['start'], path['end'], '%s.get_node(%s)' % (PANEL, path['value'])))
                index += 2
                continue
            match = re.match(r'[A-Za-z0-9_/]+', body[token['end']:])
            if match and match.group(0):
                end = token['end'] + len(match.group(0))
                edits.append((token['start'], end, '%s.get_node("%s")' % (PANEL, match.group(0))))
                while index < size and tokens[index]['start'] < end:
                    index += 1
                continue
            index += 1
            continue
        if token['kind'] == 'symbol' and value == '%':
            nxt = tokens[index + 1] if index + 1 < size else None
            raw_prev = tokens[index - 1] if index > 0 else None
            at_line_start = raw_prev is None or raw_prev['kind'] == 'newline'
            prev = prev_token(tokens, index)
            allowed = at_line_start or prev is None or prev['value'] in (
                '(', '[', '{', ',', '=', ':', 'return', 'and', 'or', 'not',
                'if', 'elif', 'while', 'in', '->', ':=', '+', '-', '*', '/',
                '==', '!=', '>', '<', '>=', '<=', '&&', '||')
            if nxt is not None and nxt['kind'] == 'identifier' and allowed:
                edits.append((token['start'], nxt['end'], '%s.get_node("%%%s")' % (PANEL, nxt['value'])))
                index += 2
                continue
            index += 1
            continue
        index += 1
    return apply_edits(body, edits), unknowns


def downgrade_panel_inference(text):
    tokens = tokenize(text)
    entries, size = [], len(tokens)
    for index, token in enumerate(tokens):
        if token['kind'] != 'identifier' or token['value'] != 'var' or index + 2 >= size:
            continue
        name, op = tokens[index + 1], tokens[index + 2]
        if name['kind'] != 'identifier' or op['kind'] != 'symbol' or op['value'] not in (':=', '='):
            continue
        rhs, depth, pos = set(), 0, index + 3
        while pos < size:
            item = tokens[pos]
            if item['kind'] == 'newline' and depth == 0:
                break
            if item['kind'] == 'symbol':
                if item['value'] in ('(', '[', '{'):
                    depth += 1
                elif item['value'] in (')', ']', '}'):
                    depth -= 1
            elif item['kind'] == 'identifier':
                rhs.add(item['value'])
            pos += 1
        entries.append((name['value'], op, rhs))
    tainted, changed = set(), True
    while changed:
        changed = False
        for name, _op, rhs in entries:
            if name not in tainted and (PANEL in rhs or rhs & tainted):
                tainted.add(name)
                changed = True
    edits = [(op['start'], op['end'], '=') for name, op, _rhs in entries
             if name in tainted and op['value'] == ':=']
    return apply_edits(text, edits)


def render_static_sig(func):
    lines = list(func['sig_lines'])
    needle = 'func %s(' % func['name']
    if needle not in lines[0]:
        raise AppError('invalid_input', 'сигнатуру %s не удалось разобрать' % func['name'])
    replacement = 'static func %s(%s%s' % (func['name'], PANEL, ', ' if func['params'] else '')
    lines[0] = lines[0].replace(needle, replacement, 1)
    return lines


def render_wrapper(func, const_name):
    call = '%s.%s(self%s)' % (const_name, func['name'], ''.join(', ' + p['name'] for p in func['params']))
    if func['has_await']:
        call = 'await ' + call
    body = 'return ' + call if func['ret'] and func['ret'] != 'void' else call
    return list(func['sig_lines']) + ['\t' + body]


def render_module(donor, module, const_texts, blocks):
    parts = [
        '@tool', 'extends RefCounted', '',
        '# Модуль %s: методы вынесены «пилой» split_gd из %s.' % (module, donor),
        '# Реализация живёт ЗДЕСЬ; в доноре на месте метода — тонкая обёртка,',
        '# поэтому connect()/call() по исходным именам продолжают работать.',
        '# Тело работает через параметр panel: к членам донора — panel.<член>,',
        '# к другим методам донора — panel.<метод> (через его обёртку).',
    ]
    if const_texts:
        parts.extend(['', '# --- константы, скопированные из донора (неизменяемы) ---'])
        parts.extend(const_texts)
    for _name, lines, _func in blocks:
        parts.append('')
        parts.extend(lines)
    return '\n'.join(parts) + '\n'
