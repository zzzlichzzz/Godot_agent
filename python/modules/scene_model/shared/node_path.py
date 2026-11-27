"""Single C.4 lookup/path implementation, moved verbatim under approved C.6 reuse."""


def rel_path_between(from_node, to_node):
    if from_node == to_node:
        return '.'
    from_parts = [] if from_node == '.' else from_node.split('/')
    to_parts = [] if to_node == '.' else to_node.split('/')
    i = 0
    while i < len(from_parts) and i < len(to_parts) and from_parts[i] == to_parts[i]:
        i += 1
    up_count = len(from_parts) - i
    downs = to_parts[i:]
    ups = ['..'] * up_count
    parts = ups + downs
    return '/'.join(parts) if parts else '.'


def find_node_in_scene(nodes, target_spec):
    spec = target_spec.strip().replace('\\', '/')
    if spec.startswith('%'):
        uname = spec[1:]
        for n in nodes:
            if n['unique_name'] and n['name'] == uname:
                return n
        raise ValueError('Уникальный узел %%%s не найден в сцене' % uname)
    if spec in ('.', ''):
        for n in nodes:
            if n['parent'] is None:
                return n
        raise ValueError('Корневой узел сцены не найден')
    for n in nodes:
        if n['path'] == spec:
            return n
    matches = [n for n in nodes if n['name'] == spec]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        raise ValueError("Имя узла '%s' неоднозначно (%d совпадений). Укажите полный путь: %s"
                         % (spec, len(matches), ', '.join(m['path'] for m in matches)))
    raise ValueError("Узел '%s' не найден в сцене" % spec)
