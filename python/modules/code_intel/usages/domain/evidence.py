"""modules/code_intel/usages/domain/evidence.py - доказательство ссылок (R-11).

Вторая половина переноса `symbol_refactor_part1/part2`: правила владения
scope, тень имени и решение `proven` / `probable`. Вынесено из `core.py`,
чтобы файл не превышал лимит R-06; публичное поведение то же.
"""

def owner_within(owner, root, declarations):
    """Владелец ссылки находится внутри `root` (сам root — объявление класса)."""
    if root is None:
        return owner == "script"
    current = owner
    for _ in range(64):
        if current == root:
            return True
        parent = next((item.get("owner") for item in declarations
                       if item.get("id") == current), None)
        if parent is None or parent == current:
            return False
        current = parent
    return False


def owner_in_script(owner, declarations):
    """Ссылка принадлежит этому же скрипту, включая вложенные классы."""
    by_id = {item.get("id"): item for item in declarations}
    current = owner
    seen = set()
    while current and current != "script" and current not in seen:
        seen.add(current)
        declaration = by_id.get(current)
        if not declaration:
            return False
        current = declaration.get("owner")
    return current == "script"


def owner_belongs_to_script(owner, declarations):
    """Владелец не пересекает вложенный класс: он не наследует внешний скрипт."""
    by_id = {item.get("id"): item for item in declarations}
    current = owner
    seen = set()
    while current and current != "script" and current not in seen:
        seen.add(current)
        declaration = by_id.get(current)
        if not declaration or declaration.get("kind") == "class":
            return False
        current = declaration.get("owner")
    return current == "script"


def owner_shadows_name(owner, name, declarations):
    """Одноимённая локальная сущность в том же owner — это ДРУГОЙ символ."""
    return any(item.get("owner") == owner and item.get("name") == name
               and item.get("kind") in ("variable", "constant", "parameter")
               for item in declarations)


def reference_in_other_scope(fact, declaration, kind, declarations):
    """Ссылка принадлежит scope, отличному от scope нашего объявления."""
    if kind not in ("function", "signal", "variable", "const", "enum"):
        return False
    owner = declaration.get("owner")
    if owner == "script":
        return not owner_belongs_to_script(fact.get("owner"), declarations)
    return not owner_within(fact.get("owner"), owner, declarations)



def super_method(index, name):
    """Resolve only an explicit super.method() with a unique indexed parent chain."""
    by_path = {entry['path']: entry for entry in index['files']}
    by_class = {}
    for entry in index['files']:
        for decl in entry['declarations']:
            if decl['kind'] == 'class_name':
                by_class.setdefault(decl['name'], []).append(entry)

    def resolve(entry, fact, tokens):
        recv, dot, call = token_neighbors(tokens, fact['start'])
        if [(t or {}).get('value') for t in (recv, dot, call)] != ['super', '.', '(']:
            return None
        seen = {entry['path']}
        while True:
            parents = by_class.get(entry['parent_class'], [])
            entry = (by_path.get(entry['parent_path']) if entry['parent_path'] else
                     parents[0] if len(parents) == 1 else None)
            if not entry or entry['path'] in seen:
                return None
            seen.add(entry['path'])
            matches = [d for d in entry['declarations'] if d['owner'] == 'script'
                       and d['name'] == name and d['kind'] == 'function']
            if matches:
                return matches[0] if len(matches) == 1 else None
    return resolve


def reference_is_safe(kind, fact, tokens, target_path, path, target_class,
                      declarations, subclasses, all_target_classes, root_owner,
                      typed=None):
    """Доказана ли связь ссылки с нашим символом (`proven` / `probable`)."""
    prev2, prev, nxt = token_neighbors(tokens, fact.get("start"))
    prev_value = prev.get("value") if prev else None
    prev2_value = prev2.get("value") if prev2 else None
    next_value = nxt.get("value") if nxt else None
    typed = typed or {}
    shadowed = owner_shadows_name(fact.get("owner"), fact.get("name"), declarations)
    if kind == "variable" and root_owner not in (None, "script"):
        # У локальной переменной объявление и ссылки живут в одном scope:
        # проверка тени нашла бы само объявление.
        shadowed = False
    in_script = owner_in_script(fact.get("owner"), declarations)
    in_root = owner_within(fact.get("owner"), root_owner, declarations)
    if root_owner is not None and kind in ("function", "signal", "variable",
                                           "const", "enum"):
        if root_owner == "script":
            if not owner_belongs_to_script(fact.get("owner"), declarations):
                return False
        elif not in_root:
            return False
    if kind == "class_name":
        return fact.get("context") == "type" or (next_value == "." and not shadowed)
    hierarchy = path == target_path or bool(subclasses and path in subclasses)
    if prev_value == ".":
        receiver = prev2_value
        if hierarchy and receiver == "self" and in_script:
            return True
        if all_target_classes and typed.get(receiver) in all_target_classes:
            return True
        if target_class and typed.get(receiver) == target_class:
            return True
        if target_class and receiver == target_class and not shadowed:
            return True
        return False
    if kind == "function":
        return (hierarchy and in_script and not shadowed
                and fact.get("context") == "call")
    if kind == "signal":
        return (hierarchy and in_script and not shadowed
                and (next_value == "." or prev_value == "await"))
    if kind in ("variable", "const", "enum", "enum_member"):
        return (hierarchy and in_script and not shadowed
                and fact.get("context") != "member")
    return False




def unverified_reason(kind, fact, tokens, target_path, path, target_class,
                      declarations, subclasses, all_target_classes, root_owner,
                      typed=None):
    """Почему ссылка НЕ доказана: причина, которую модель видит в `note`."""
    prev2, prev, nxt = token_neighbors(tokens, fact.get("start"))
    prev_value = prev.get("value") if prev else None
    prev2_value = prev2.get("value") if prev2 else None
    next_value = nxt.get("value") if nxt else None
    typed = typed or {}
    shadowed = owner_shadows_name(fact.get("owner"), fact.get("name"), declarations)
    if kind == "variable" and root_owner not in (None, "script"):
        shadowed = False
    in_script = owner_in_script(fact.get("owner"), declarations)
    in_root = owner_within(fact.get("owner"), root_owner, declarations)
    if root_owner is not None and kind in ("function", "signal", "variable",
                                           "const", "enum"):
        if root_owner == "script" and not owner_belongs_to_script(
                fact.get("owner"), declarations):
            return "вложенный класс не наследует внешний скрипт"
        if root_owner != "script" and not in_root:
            return "ссылка вне вложенного класса, чей член переименовывается"
    if kind == "class_name":
        if fact.get("context") != "type" and next_value != ".":
            return ("использование имени класса не как типа и не как префикса "
                    "(%s)" % (fact.get("context"),))
    hierarchy = path == target_path or bool(subclasses and path in subclasses)
    if prev_value == ".":
        if hierarchy and prev2_value == "self" and in_script:
            return None
        if all_target_classes and typed.get(prev2_value) in all_target_classes:
            return None
        if target_class and typed.get(prev2_value) == target_class:
            return None
        if target_class and prev2_value == target_class and not shadowed:
            return None
        if shadowed:
            return "имя перекрыто одноимённым объявлением"
        return ("не удалось доказать тип ресивера «%s»: добавь аннотацию типа, "
                "и ссылка переименуется сама" % (prev2_value,))
    if kind in ("function", "signal", "variable", "const", "enum", "enum_member"):
        if not hierarchy:
            return "файл не входит в иерархию символа"
        if shadowed:
            return "имя перекрыто одноимённым объявлением"
        if kind == "function" and fact.get("context") != "call":
            return ("упоминание функции не как вызова (%s); такой вызов по "
                    "имени мы переписать не можем" % (fact.get("context"),))
        if fact.get("context") == "member":
            return "член по ссылке на неизвестный объект"
    return "причина не установлена"


def token_neighbors(tokens, start):
    """Токен до/через один/после по точному `start` (контекст ссылки)."""
    for index, token in enumerate(tokens):
        if token.get("start") == start:
            prev = tokens[index - 1] if index else None
            prev2 = tokens[index - 2] if index > 1 else None
            nxt = tokens[index + 1] if index + 1 < len(tokens) else None
            return prev2, prev, nxt
    return None, None, None

    if kind == "signal":
        return (hierarchy and in_script and not shadowed
                and (next_value == "." or prev_value == "await"))
    if kind in ("variable", "const", "enum", "enum_member"):
        return (hierarchy and in_script and not shadowed
                and fact.get("context") != "member")
    return False
