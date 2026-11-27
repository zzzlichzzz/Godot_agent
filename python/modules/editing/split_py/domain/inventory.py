"""Native AST inventory and source segments (split_refactor:231–346), no IO."""
import ast
import re

from .text import decode as _decode

_CODING_RE = re.compile(r'^#!|^#\s*-\*-')


class SplitError(ValueError):
    """Native deterministic split refusal, translated at the application boundary."""


def decode(raw):
    return _decode(raw).replace('\r\n', '\n').replace('\r', '\n')


def _segment_text(lines, start, end):
    return '\n'.join(lines[start - 1:end])


def _expand_comments(lines, next_lineno):
    """Начало сегмента: строка плюс «липкие» комментарии прямо над ней."""
    start = int(next_lineno)
    while start - 1 >= 1:
        prev = lines[start - 2].strip()
        if not prev.startswith('#') or _CODING_RE.match(prev):
            break
        start -= 1
    return start


def _import_bindings(node):
    """Имена, которые импорт связывает в модуле (для копирования в модули)."""
    names = []
    for alias in node.names:
        if alias.name == '*':
            names.append('*')
        elif isinstance(node, ast.Import):
            names.append(alias.asname or alias.name.split('.')[0])
        else:
            names.append(alias.asname or alias.name)
    return names


def _other_item(lines, node, name):
    """Неперемещаемая верхняя сущность (if/try/expr/dunder-assign/...)."""
    bindings = set()
    for inner in ast.walk(node):
        if isinstance(inner, (ast.Import, ast.ImportFrom)):
            bindings.update(_import_bindings(inner))
    return {'name': name, 'lineno': node.lineno, 'end_lineno': node.end_lineno,
            'text': _segment_text(lines, node.lineno, node.end_lineno),
            'bindings': sorted(bindings)}


def file_inventory(text):
    """Инвентарь модуля: докстрока, импорты, символы верхнего уровня, прочее.

    Символы — def/class (с декораторами) и одиночные assign-имена (кроме
    dunder): lineno/end_lineno, число строк, публичность, признак мутабельного
    state (dict/list/set) и «липкие» комментарии над символом.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as exc:
        raise SplitError('не разобрал .py: %s' % exc)
    lines = text.splitlines()
    body = list(tree.body)
    docstring, docstring_end = None, 0
    if body and isinstance(body[0], ast.Expr) \
            and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        docstring = body[0].value.value
        docstring_end = body[0].end_lineno
        body = body[1:]
    imports, symbols, other = [], [], []
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append({'text': _segment_text(lines, node.lineno,
                                                 node.end_lineno),
                            'bindings': _import_bindings(node),
                            'lineno': node.lineno,
                            'end_lineno': node.end_lineno})
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            base_lineno = node.lineno
            decorators = getattr(node, 'decorator_list', None) or []
            if decorators:
                base_lineno = min([base_lineno]
                                  + [item.lineno for item in decorators])
            start = _expand_comments(lines, base_lineno)
            symbols.append({'name': node.name,
                            'kind': 'class' if isinstance(node, ast.ClassDef)
                            else 'def',
                            'lineno': node.lineno,
                            'end_lineno': node.end_lineno,
                            'line_start': start,
                            'lines': node.end_lineno - start + 1,
                            'is_public': not node.name.startswith('_'),
                            'state': False, 'node': node})
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.startswith('__') and name.endswith('__'):
                other.append(_other_item(lines, node, name))
                continue
            start = _expand_comments(lines, node.lineno)
            symbols.append({'name': name, 'kind': 'assign',
                            'lineno': node.lineno,
                            'end_lineno': node.end_lineno,
                            'line_start': start,
                            'lines': node.end_lineno - start + 1,
                            'is_public': not name.startswith('_'),
                            'state': isinstance(node.value,
                                                (ast.Dict, ast.List, ast.Set)),
                            'node': node})
            continue
        other.append(_other_item(lines, node, None))
    return {'docstring': docstring, 'docstring_end': docstring_end,
            'lines': len(lines), 'imports': imports, 'symbols': symbols,
            'other': other}


def _used_names(node):
    """Имена, читаемые внутри узла (Load-ссылки; локальные тени не различаем)."""
    used = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load):
            used.add(inner.id)
    return used
