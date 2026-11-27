"""describe_scene rendering ported verbatim, project_tools.py:1309-1367.

Frozen ba0535d4dec43c32750e601a6ca86e377abc6af3. Parsing only in formats;
original quirks/order retained. Data projection stays complete after text cut.
"""
from python.formats import tscn

DEFAULT_MAX_CHARS = 12000
TRUNCATION_SUFFIX = '\n… (сводка обрезана — сцена очень большая)'


def describe(raw, max_chars=DEFAULT_MAX_CHARS):
    text = raw.decode('utf-8-sig', errors='replace').replace('\r\n', '\n').replace('\r', '\n')
    parsed = tscn.rows(text)
    nodes = []
    for n in parsed['nodes']:
        parent = n['parent']
        depth = 0 if parent is None else 1 if parent == '.' else parent.count('/') + 2
        path = '.' if parent is None else n['name'] if parent == '.' else parent + '/' + n['name']
        nodes.append(dict(n, depth=depth, path=path))
    if not nodes:
        raise ValueError('В файле не найдено ни одного узла [node].')
    out = []
    for n in nodes:
        extra = []
        if n['type']:
            extra.append(n['type'])
        if n['instance']:
            extra.append('инстанс: %s' % n['instance'])
        row = '  ' * n['depth'] + '- ' + n['name'] + ((' (' + ', '.join(extra) + ')') if extra else '')
        if n['script']:
            row += '  [скрипт: %s]' % n['script']
        out.append(row)
    connections = parsed['connections']
    if connections:
        out.append('')
        out.append('Сигналы ([connection]):')
        for c in connections:
            frm = c['from'] if c['from'] not in ('', '.') else '<root>'
            to = c['to'] if c['to'] not in ('', '.') else '<root>'
            out.append('- %s.%s -> %s.%s()' % (frm, c['signal'], to, c['method']))
    resources = parsed['resources']
    if resources['ext'] or resources['sub']:
        out.append('')
        out.append('Ресурсы (id/uid для точных ссылок в ExtResource/SubResource):')
        for r in resources['ext']:
            line = '- ext id=%s %s: %s' % (r['id'], r['type'], r['path'])
            if r['uid']:
                line += ' (uid=%s)' % r['uid']
            out.append(line)
        for r in resources['sub']:
            out.append('- sub id=%s %s' % (r['id'], r['type']))
    result = '\n'.join(out)
    truncated = len(result) > max_chars
    if truncated:
        result = result[:max_chars] + TRUNCATION_SUFFIX
    return {'text': result, 'truncated': truncated, 'nodes': nodes,
            'connections': connections, 'resources': resources}
