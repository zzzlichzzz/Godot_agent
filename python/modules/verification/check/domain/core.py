"""By specification: agent_bridge._check_one_path (ba0535d4), C.9 + C.13.

Literal syntax/unchecked messages; registry lint -> API, no IO/engine execution.
Headless stays unavailable. Full text <=4 MiB is the approved limit deviation.
"""
import configparser

from python.kernel.errors import AppError
from python.kernel.schema import validate
from python.modules.verification.shared.check_kind import CheckKind

TEXT = {'.gd': 'gd', '.tscn': 'tscn', '.py': 'py', '.json': 'json', '.cfg': 'cfg'}
HEADLESS = ('.gd', '.tscn', '.tres', '.gdshader', '.shader')
ORDER = {'gd': 0, 'tscn': 0, 'api': 10, 'py': 20, 'json': 30, 'cfg': 40}
FRAGMENT = {
    'type': 'object', 'required': ['problems', 'auto_fixable'], 'additionalProperties': False,
    'properties': {'problems': {'type': 'array', 'items': {'type': 'string'}},
                   'auto_fixable': {'type': 'boolean'},
                   'checked': {'type': 'boolean'},
                   'unavailable': {'type': 'array', 'items': {
                       'type': 'object', 'required': ['kind', 'reason'], 'additionalProperties': False,
                       'properties': {'kind': {'type': 'string', 'minLength': 1},
                                      'reason': {'type': 'string', 'minLength': 1}},
                   }}},
}


def extension(path):
    name = path.rsplit('/', 1)[-1]
    stem, dot, suffix = name.rpartition('.')
    return '.' + suffix.lower() if dot and stem.strip('.') else ''


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON key: %s' % key)
        value[key] = item
    return value


def _python(text, path, ctx):
    try:
        compile(text, path, 'exec')
    except Exception as exc:
        return {'problems': ['python syntax: %s' % exc], 'auto_fixable': False}
    return {'problems': [], 'auto_fixable': False}


def _json(text, path, loads):
    try:
        loads(text, object_pairs_hook=_pairs)
    except Exception as exc:
        return {'problems': ['json syntax: %s' % exc], 'auto_fixable': False}
    return {'problems': [], 'auto_fixable': False}


def _cfg(text, path, ctx):
    try:
        configparser.ConfigParser(strict=True, interpolation=None).read_string(text)
    except Exception as exc:
        return {'problems': ['cfg syntax: %s' % exc], 'auto_fixable': False}
    return {'problems': [], 'auto_fixable': False}


def builtins(json_loads):
    """Pure decoder supplied by orchestration: domain cannot import json (R-11)."""
    return (CheckKind('py', ('.py',), _python),
            CheckKind('json', ('.json',), lambda text, path, ctx: _json(text, path, json_loads)),
            CheckKind('cfg', ('.cfg',), _cfg))


def select(ext, kinds, contributions, builtin_checks=()):
    checks = (*contributions, *builtin_checks)
    if any(c.name not in ORDER for c in checks):
        raise AppError('internal', 'вклад проверки вне таблицы порядка')
    return tuple(sorted((c for c in checks
                         if ext in c.extensions and (kinds is None or c.name in kinds)),
                        key=lambda c: (ORDER[c.name], c.name)))


def headless_reason(ext):
    return ('%s проверяется только настоящим Godot, а проверка отключена '
            '(--validation off) — файл НЕ проверен') % ext


def unchecked_reason(ext, requested=None, performed=(), reasons=()):
    if ext in TEXT and requested is not None and not performed:
        return ('ни один из запрошенных kinds (%s) не относится к расширению %s — '
                'файл НЕ проверен') % (', '.join(sorted(set(requested))), ext)
    if ext in TEXT:
        return ('ни одна проверка расширения %s не выполнена (%s) — файл НЕ проверен'
                % (ext, ', '.join(sorted(set(reasons))) or 'no_kind'))
    if ext in HEADLESS:
        return headless_reason(ext)
    supported = ', '.join(sorted(set(TEXT) | set(HEADLESS)))
    return 'расширение %s не проверяется этим каналом (проверяются: %s)' % (
        ext or 'без расширения', supported)


def unavailable(ext, performed, requested):
    absent = []
    text_kind = TEXT.get(ext)
    if text_kind and text_kind not in performed and (requested is None or text_kind in requested):
        absent.append({'kind': text_kind, 'reason': 'no_module'})
    if 'api' not in performed and ((requested is None and ext == '.gd') or
                                   (requested is not None and 'api' in requested)):
        absent.append({'kind': 'api', 'reason': 'no_module'})
    if (requested is None and ext in HEADLESS) or (requested is not None and 'headless' in requested):
        absent.append({'kind': 'headless', 'reason': headless_reason(ext) if ext in HEADLESS else 'no_module'})
    return absent


def assemble(path, ext, reports, requested):
    problems, performed, auto_fixable = [], [], False
    checked, absent, reasons = False, [], []
    for name, fragment in reports:
        if validate(fragment, FRAGMENT):
            raise AppError('internal', 'вклад проверки вернул неверный результат')
        problems.extend(fragment['problems'])
        performed.append(name)
        auto_fixable = auto_fixable or (name == 'tscn' and fragment['auto_fixable'])
        fragment_checked = fragment.get('checked', True)
        checked = checked or fragment_checked
        fragment_absent = fragment.get('unavailable', [])
        absent.extend(fragment_absent)
        if not fragment_checked:
            reasons.extend(item['reason'] for item in fragment_absent)
    result = {'path': path, 'problems': problems, 'checked': checked,
              'auto_fixable': auto_fixable, 'kinds': performed,
              'unavailable': absent + unavailable(ext, performed, requested)}
    if not result['checked']:
        result['unchecked_reason'] = unchecked_reason(ext, requested, performed, reasons)
    return result
