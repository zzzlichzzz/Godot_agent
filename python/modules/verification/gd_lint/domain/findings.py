"""Stable code dictionary and literal reference messages: data, never commands."""
import re

CATALOG = {
    'empty_file': 'итоговый файл получился пустым',
    'damaged_encoding': 'в коде символ повреждённой кодировки (\\ufffd) — текст побился',
    'unclosed_string': 'строка %d: незакрытая кавычка (%s)',
    'extra_closing_bracket': 'строка %d: лишняя закрывающая скобка «%s»',
    'mismatched_bracket': 'строка %d: закрывающая «%s» не соответствует открытой «%s» со строки %d',
    'unclosed_triple_string': 'строка %d: незакрытая тройная кавычка',
    'unclosed_bracket': 'строка %d: скобка «%s» не закрыта',
    'space_before_tab': 'строка %d: в отступе пробел ПЕРЕД табом — Godot такое не примет',
    'missing_colon': 'строка %d: похоже, пропущено двоеточие в конце объявления',
    'type_mismatch': 'строка %d: переменной типа %s присваивается %s — Godot выдаст ошибку типов (Type Mismatch)',
    'mixed_indentation': (
        'смешаны отступы: табы (например, строка %d) и пробелы (например, строка %d) — '
        'Godot выдаст ошибку «Mixed use of tabs and spaces»'),
}

_PATTERNS = {
    code: re.compile(re.escape(template).replace('%d', r'\d+').replace('%s', r'.+?'))
    for code, template in CATALOG.items()
}
_LINE_RE = re.compile(r'^строка (\d+):')


def from_message(message):
    """Project reference prose into codes; no branches on Russian string literals."""
    codes = [code for code, pattern in _PATTERNS.items() if pattern.fullmatch(message)]
    if len(codes) != 1:
        raise ValueError('lint message must belong to exactly one catalog entry')
    match = _LINE_RE.match(message)
    return {'code': codes[0], 'line': int(match.group(1)) if match else None, 'message': message}
