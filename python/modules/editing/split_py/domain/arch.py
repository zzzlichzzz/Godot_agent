"""Pure native architecture-map policies; decoded data, fresh index (B7)."""
import ast
import re

_SKIP_DIRS = {'__pycache__', 'dist', 'minilich_brain', 'parser_corpus',
              '.godot', 'agent_api_cache', '.git'}
_DEFAULT_LINE_LIMITS = {'line_warn': 1500, 'line_max': 2000,
                        'line_exts': ['.py', '.gd'],
                        'line_exempt_roles': ['workflow', 'generated',
                                              'tasks', 'reports']}


def _glob_to_re(pattern):
    """Переводит сегментный glob карты в регулярное выражение.

    `**` — любая глубина (включая «/»), `*` — в пределах сегмента, `?` — один
    символ сегмента. Ведущее `**/` допускает и нулевую глубину.
    """
    out = ['^']
    index, length = 0, len(pattern)
    while index < length:
        char = pattern[index]
        if char == '*':
            if index + 1 < length and pattern[index + 1] == '*':
                if index + 2 < length and pattern[index + 2] == '/':
                    out.append('(?:.*/)?')
                    index += 3
                    continue
                out.append('.*')
                index += 2
                continue
            out.append('[^/]*')
            index += 1
            continue
        if char == '?':
            out.append('[^/]')
            index += 1
            continue
        out.append(re.escape(char))
        index += 1
    out.append('$')
    return re.compile(''.join(out))


def load_map(data):
    """Native zone validation; JSON decoding/IO belong to app, without caches."""
    if not isinstance(data, dict) or not isinstance(data.get('zones'), list):
        return None
    compiled = []
    for zone in data['zones']:
        if not isinstance(zone, dict):
            continue
        pattern = str(zone.get('glob') or '').strip()
        if pattern:
            compiled.append((_glob_to_re(pattern), zone))
    data['_compiled'] = compiled
    return data


def zone_for(map_data, rel_path):
    """Зона карты для пути (относительно аддона, через «/») или None."""
    if not map_data:
        return None
    value = str(rel_path or '').replace('\\', '/').lstrip('/')
    for regex, zone in map_data.get('_compiled') or []:
        if regex.match(value):
            return zone
    return None


def core_dir_of(map_data):
    """Каталог ядра из карты (с завершающим «/»), по умолчанию godot_tools."""
    value = str((map_data or {}).get('core_dir') or 'python/godot_tools')
    return value.strip('/').replace('\\', '/') + '/'


def line_policy(map_data):
    """Лимиты размера файла из карты (`limits`) с безопасными значениями.

    Возвращает {"warn": int, "max": int, "exts": [".py", ...],
    "exempt_roles": [...]}. Битые значения и отсутствие карты — дефолт:
    предупреждение 1500 строк, лимит 2000, .py/.gd, генерируемые зоны не
    считаем (их размер диктует экспортёр, а не автор кода).
    """
    limits = (map_data or {}).get('limits')
    limits = limits if isinstance(limits, dict) else {}

    def _int(key, fallback):
        try:
            value = int(limits.get(key))
        except (TypeError, ValueError):
            return fallback
        return value if value > 0 else fallback

    warn = _int('line_warn', _DEFAULT_LINE_LIMITS['line_warn'])
    maximum = _int('line_max', _DEFAULT_LINE_LIMITS['line_max'])
    if maximum < warn:
        maximum = warn
    exts = limits.get('line_exts')
    exts = [str(item).lower() for item in exts
            if str(item).strip().startswith('.')] \
        if isinstance(exts, list) else []
    if not exts:
        exts = list(_DEFAULT_LINE_LIMITS['line_exts'])
    roles = limits.get('line_exempt_roles')
    roles = [str(item) for item in roles if str(item).strip()] \
        if isinstance(roles, list) else list(_DEFAULT_LINE_LIMITS['line_exempt_roles'])
    return {'warn': warn, 'max': maximum, 'exts': exts,
            'exempt_roles': roles}


def count_lines(text):
    """Число строк текста (пустой текст — 0)."""
    if not text:
        return 0
    return len(str(text).splitlines())


def name_checks_enabled(map_data, rel_path):
    """Зона может отключить сверку имён (`check_names: false`).

    Тесты, скрипты n8n и per-site парсеры держат одноимённые локальные
    помощники (`Driver`, `extract_answer`, `load_invoker`) — это норма их
    жанра, а не дубль функциональности ядра.
    """
    zone = zone_for(map_data, rel_path) or {}
    return str(zone.get('check_names', True)).lower() != 'false'


def public_names(text):
    """Публичные имена верхнего уровня .py-текста или None (не разобрался).

    Возвращает [(имя, "def"|"class")]: приватные (`_…`) пропускаются — это
    локальная кухня файла, у ядра она не крадёт имя.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            if node.name.startswith('_'):
                continue
            kind = 'class' if isinstance(node, ast.ClassDef) else 'def'
            names.append((node.name, kind))
    return names


def eligible(rel):
    return (rel.lower().endswith('.py') and
            not any(p in _SKIP_DIRS or p.startswith('.') for p in rel.split('/')[:-1]))


def name_index(sources):
    """Native sorted index from injected source bytes; no persistent snapshot."""
    index = {}
    for rel, raw in sorted(sources):
        if not eligible(rel):
            continue
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            continue
        names = public_names(text)
        if not names:
            continue
        for name, kind in names:
            index.setdefault(name, []).append((rel, kind))
    return index


def _join_hits(hits, limit=3):
    """«файл(а), файл(б)» — короткая и честная ссылка на источники имени."""
    files = sorted({rel for rel, _kind in hits})
    shown = ', '.join(files[:limit])
    if len(files) > limit:
        shown += ', …'
    return shown
