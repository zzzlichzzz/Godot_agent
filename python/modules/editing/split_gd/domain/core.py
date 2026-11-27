"""Frozen scan assembly and native plan preparation/public metadata, without IO."""
import hashlib
import re

from python.kernel.errors import AppError
from . import render
from .collect import ENGINE_VIRTUALS, collect_locals
from .tokens import tokenize


def public_methods(inventory):
    return sorted({item['name'] for item in inventory['funcs'] if not item['name'].startswith('_')})


def assemble(donor, inventory, references):
    return {'donor': donor, 'lines': inventory['lines'], 'extends': inventory['extends'],
            'class_name': inventory['class_name'], 'funcs': len(inventory['funcs']),
            'consts': len(inventory['consts']), 'vars': len(inventory['vars']),
             'public_methods': public_methods(inventory), **references}


def target_lines(value=0):
    if value is None:
        return 1100
    if not isinstance(value, int) or isinstance(value, bool):
        raise AppError('invalid_input', 'target_lines must be an integer')
    if value == 0:
        return 1100
    if value < 100 or value > 5000:
        raise AppError('invalid_input', 'target_lines must be between 100 and 5000')
    return value


def plan_groups(donor, inventory, groups, target):
    if inventory['errors']:
        raise AppError('invalid_input', 'разбор донора: ' + '; '.join(inventory['errors']))
    if not inventory['funcs']:
        raise AppError('invalid_input', 'в доноре не найдено методов')
    if not groups:
        stem = donor.rsplit('/', 1)[-1].rsplit('.', 1)[0]
        groups = render.suggest_groups(inventory, stem, target)
    return render.normalize_groups(groups, {f['name']: f for f in inventory['funcs']})


def targets(donor, inventory, groups):
    directory = donor.rsplit('/', 1)[0] + '/' if '/' in donor else ''
    members = {item['name'] for kind in ('consts', 'vars', 'funcs') for item in inventory[kind]}
    for group in groups:
        module = group['module']
        rel = directory + module + '.gd'
        const = ''.join(part[:1].upper() + part[1:] for part in re.split(r'[^0-9A-Za-z]+', module) if part)
        # The caller checks existence before resuming: native existence precedes conflict.
        yield module, rel, const, group['funcs']
        if const in members:
            raise AppError('invalid_input', 'preload-константа %s конфликтует с членом донора' % const)


def _block(func, lines, consts, vars_, funcs, methods, props, warnings):
    name = func['name']
    if name in ENGINE_VIRTUALS:
        warnings.append('%s — движковый виртуальный метод: обёртка сохранит вызов движка' % name)
    if func['anns']:
        raise AppError('invalid_input', 'метод %s: аннотации %s не поддерживаются v1' % (name, ', '.join(func['anns'])))
    if any(p['name'] == render.PANEL for p in func['params']):
        raise AppError('invalid_input', 'метод %s: параметр %s конфликтует с параметром модуля' % (name, render.PANEL))
    body = '\n'.join(lines[func['body_start'] - 1:func['end']])
    if not body.strip():
        raise AppError('invalid_input', 'метод %s: пустое тело — нечего выносить' % name)
    if re.search(r'\bsuper\b', body):
        raise AppError('invalid_input', 'метод %s: super() не поддерживается статическим модулем v1' % name)
    tokens = tokenize(body)
    if render.PANEL in collect_locals(tokens):
        raise AppError('invalid_input', 'метод %s: тело объявляет имя %s — конфликт с параметром модуля' % (name, render.PANEL))
    copies = set()
    for param in func['params']:
        default = (param.get('default') or '').strip()
        if re.match(r'^[A-Za-z_]\w*$', default):
            if default in vars_ or default in funcs:
                raise AppError('invalid_input', 'метод %s: дефолт параметра %s = %s ссылается на член донора (в статике нельзя)' % (name, param['name'], default))
            if default in consts:
                copies.add(default)
    used = {t['value'] for t in tokens if t['kind'] == 'identifier'} & set(consts)
    copies.update(used)
    context = {'funcs': funcs, 'vars': vars_, 'copies': used, 'methods': methods, 'props': props,
               'params': [p['name'] for p in func['params']]}
    rewritten, _unknowns = render.rewrite_body(body, context)
    rewritten = render.downgrade_panel_inference(rewritten)
    block = list(lines[func['block_start'] - 1:func['sig_start'] - 1])
    block.extend(render.render_static_sig(func))
    block.extend(rewritten.split('\n'))
    return copies, (name, block, func)


def prepare(donor, text, inventory, methods, props, groups=None, target=1100):
    groups = plan_groups(donor, inventory, groups, target)
    planned_targets = list(targets(donor, inventory, groups))
    lines = text.split('\n')
    consts = {c['name']: c for c in inventory['consts'] if c['name']}
    vars_ = {v['name'] for v in inventory['vars']}
    funcs = {f['name']: f for f in inventory['funcs']}
    warnings, modules, wrappers, spans = [], [], [], []
    for module, rel, const, names in planned_targets:
        ordered_funcs = sorted((funcs[name] for name in names), key=lambda f: f['block_start'])
        copies, blocks = set(), []
        for func in ordered_funcs:
            used, block = _block(func, lines, consts, vars_, set(funcs), methods, props, warnings)
            copies.update(used)
            blocks.append(block)
            spans.append((func['block_start'], func['end'], func['name']))
        ordered = sorted(spans, key=lambda item: item[0])
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] <= previous[1]:
                raise AppError('invalid_input', 'блоки методов %s и %s пересекаются — разбор донора неточен' % (previous[2], current[2]))
        const_texts = [consts[name]['text'] for name in sorted(copies, key=lambda n: consts[n]['start'])]
        content = render.render_module(donor, module, const_texts, blocks)
        count = content.count('\n') + 1
        if count > 2000:
            raise AppError('invalid_input', 'модуль %s: %d строк — больше максимума %d' % (rel, count, 2000))
        if count > 1500:
            warnings.append('модуль %s: %d строк — больше warn-порога %d' % (rel, count, 1500))
        modules.append({'module': module, 'rel': rel, 'const': const,
                        'funcs': [f['name'] for f in ordered_funcs], 'content': content,
                        'lines': count, '_blocks': blocks})
        wrappers.extend({'name': f['name'], 'module': module, 'await': bool(f['has_await'])} for f in ordered_funcs)
    block_map = {f['block_start']: (module, f) for module in modules for _name, _lines, f in module['_blocks']}
    donor_out, installed = [], False
    number = 1
    while number <= len(lines):
        entry = block_map.get(number)
        if entry:
            module, func = entry
            donor_out.append('# split_gd: тело — %s' % module['rel'])
            donor_out.extend(render.render_wrapper(func, module['const']))
            number = func['end'] + 1
            continue
        donor_out.append(lines[number - 1])
        if number == inventory['header_end'] and modules and not installed:
            installed = True
            donor_out.extend(['', '# --- части (вынесены «пилой» split_gd) ---'])
            for module in modules:
                donor_out.append('const %s = preload("%s")' % (module['const'], module['rel'].rsplit('/', 1)[-1]))
        number += 1
    donor_new = re.sub(r'\n{4,}', '\n\n\n', '\n'.join(donor_out))
    donor_after = donor_new.count('\n') + 1
    if donor_after > 2000:
        warnings.append('донор после раскола: %d строк — всё ещё больше максимума %d' % (donor_after, 2000))
    elif donor_after > 1500:
        warnings.append('донор после раскола: %d строк — всё ещё больше warn-порога %d (следующий шаг: снять обёртки, v2)' % (donor_after, 1500))
    return {'schema': 1, 'kind': 'split_gd', 'donor': donor,
            'donor_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'newline': '\n',
            'target_lines': int(target), 'groups': [{'module': m['module'], 'funcs': m['funcs']} for m in modules],
            'modules': [{k: v for k, v in m.items() if k not in ('module', '_blocks')} for m in modules],
            'donor_content': donor_new, 'wrappers': wrappers, 'warnings': warnings,
            'stats': {'moved': len(wrappers), 'modules': len(modules),
                      'donor_before': inventory['lines'], 'donor_after': donor_after}}


def plan(*args, newline):
    prepared = prepare(*args)
    prepared['newline'] = newline
    prepared.pop('donor_content')
    prepared['modules'] = [{k: v for k, v in m.items() if k != 'content'} for m in prepared['modules']]
    return prepared
