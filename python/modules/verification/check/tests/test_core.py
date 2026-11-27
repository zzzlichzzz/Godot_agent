"""New pure-rule tests from C.9 contract; legacy test code is not reused."""
import pytest

from python.kernel.errors import AppError


def contribution(name='gd', extensions=('.gd',), problems=None):
    from python.modules.verification.shared.check_kind import CheckKind
    return CheckKind(name, extensions, lambda text, path, ctx: {
        'problems': problems or [], 'auto_fixable': False})


@pytest.mark.parametrize('path,ext', [('res://A.GD', '.gd'), ('res://a.b/README', ''),
                                    ('res://a.scn', '.scn'), ('res://.hidden', '')])
def test_extension(path, ext):
    from python.modules.verification.check.domain import core
    assert core.extension(path) == ext


def test_selection_uses_extension_filter_and_registry_order():
    from python.modules.verification.check.domain import core
    first, second, scene = contribution(), contribution(), contribution('tscn', ('.tscn',))
    assert core.select('.gd', None, [first, scene, second]) == (first, second)
    assert core.select('.gd', ['py'], [first]) == ()
    assert core.select('.gd', ['gd', 'gd'], [first]) == (first,)
    assert core.select('.scn', None, [scene]) == ()


def test_absent_contribution_is_not_a_clean_check():
    from python.modules.verification.check.domain import core
    result = core.assemble('res://x.gd', '.gd', [], None)
    assert result['checked'] is False and result['kinds'] == []
    assert result['unavailable'][0] == {'kind': 'gd', 'reason': 'no_module'}
    assert [x['kind'] for x in result['unavailable']] == ['gd', 'api', 'headless']
    assert result['unchecked_reason']


def test_two_contributions_preserve_all_problem_order():
    from python.modules.verification.check.domain import core
    reports = [('gd', {'problems': ['first', 'second'], 'auto_fixable': False}),
               ('gd', {'problems': ['third'], 'auto_fixable': False})]
    result = core.assemble('res://x.gd', '.gd', reports, ['gd'])
    assert result['problems'] == ['first', 'second', 'third']
    assert result['checked'] is True and 'unchecked_reason' not in result


@pytest.mark.parametrize('fragment', [None, 'oops', {}, {'problems': 'oops', 'auto_fixable': False},
                                     {'problems': [1], 'auto_fixable': False},
                                     {'problems': [], 'auto_fixable': 1}])
def test_bad_contribution_is_not_silently_clean(fragment):
    from python.modules.verification.check.domain import core
    with pytest.raises(AppError) as error:
        core.assemble('res://x.tscn', '.tscn', [('tscn', fragment)], None)
    assert error.value.kind == 'internal'


@pytest.mark.parametrize('name,ext,lint', [('Bad', ('.gd',), lambda *a: None),
    ('gd', (), lambda *a: None), ('gd', ['.gd'], lambda *a: None),
    ('gd', ('.GD',), lambda *a: None), ('gd', ('gd',), lambda *a: None), ('gd', ('.gd',), 4)])
def test_invalid_contribution_descriptor_is_refused(name, ext, lint):
    from python.modules.verification.shared.check_kind import CheckKind
    with pytest.raises(ValueError):
        CheckKind(name, ext, lint)


def test_owner_order_is_explicit_not_registration_or_request_order():
    from python.modules.verification.check.domain import core
    assert core.ORDER == {'gd': 0, 'tscn': 0, 'api': 10, 'py': 20, 'json': 30, 'cfg': 40}
    api, gd = contribution('api'), contribution('gd')
    for requested in (None, ['api', 'gd', 'api']):
        assert core.select('.gd', requested, [api, gd]) == (gd, api)


@pytest.mark.parametrize('ext,requested', [('.gd', None), ('.json', ['json'])])
def test_unknown_order_name_is_developer_error_even_when_filtered(ext, requested):
    from python.modules.verification.check.domain import core
    with pytest.raises(AppError) as error:
        core.select(ext, requested, [contribution('future')])
    assert error.value.kind == 'internal'
    assert str(error.value) == 'вклад проверки вне таблицы порядка'


@pytest.mark.parametrize('bad', [
    {'checked': 1}, {'unavailable': None}, {'unavailable': 'no_cache'},
    {'unavailable': [{'kind': 'api_cache'}]},
    {'unavailable': [{'kind': '', 'reason': 'no_cache'}]},
    {'unavailable': [{'kind': 'api_cache', 'reason': ''}]},
    {'unavailable': [{'kind': 'api_cache', 'reason': 'no_cache', 'extra': 1}]},
    {'extra': False},
])
def test_optional_fragment_fields_are_strict(bad):
    from python.modules.verification.check.domain import core
    fragment = {'problems': [], 'auto_fixable': False, **bad}
    with pytest.raises(AppError) as error:
        core.assemble('res://x.gd', '.gd', [('api', fragment)], ['api'])
    assert error.value.kind == 'internal'


@pytest.mark.parametrize('reports,checked', [
    ([], False),
    ([('api', {'problems': [], 'auto_fixable': False, 'checked': False})], False),
    ([('api', {'problems': [], 'auto_fixable': False, 'checked': True})], True),
    ([('gd', {'problems': [], 'auto_fixable': False}),
      ('api', {'problems': [], 'auto_fixable': False, 'checked': False})], True),
])
def test_checked_is_any_fragment_with_legacy_default(reports, checked):
    from python.modules.verification.check.domain import core
    result = core.assemble('res://x.gd', '.gd', reports, None)
    assert result['checked'] is checked
    assert ('unchecked_reason' in result) is not checked
    assert result['kinds'] == [name for name, _ in reports]


def test_unavailable_is_verbatim_before_extension_entries_and_no_module_is_fallback():
    from python.modules.verification.check.domain import core
    absent = [{'kind': 'base_class', 'reason': 'base_not_in_cache'},
              {'kind': 'source', 'reason': 'no_extends'}]
    reports = [('gd', {'problems': [], 'auto_fixable': False}),
               ('api', {'problems': [], 'auto_fixable': False, 'checked': False,
                        'unavailable': absent})]
    result = core.assemble('res://x.gd', '.gd', reports, None)
    assert result['unavailable'][:2] == absent
    assert result['unavailable'][2] == {'kind': 'headless', 'reason':
        '.gd проверяется только настоящим Godot, а проверка отключена (--validation off) — файл НЕ проверен'}
    assert {'kind': 'api', 'reason': 'no_module'} not in result['unavailable']
    fallback = core.assemble('res://x.gd', '.gd', reports[:1], None)
    assert fallback['unavailable'][0] == {'kind': 'api', 'reason': 'no_module'}


def test_owner_does_not_truncate_either_scanners_quota():
    from python.modules.verification.check.domain import core
    lint, api = ['lint%d' % i for i in range(8)], ['api%d' % i for i in range(6)]
    result = core.assemble('res://x.gd', '.gd', [
        ('gd', {'problems': lint, 'auto_fixable': False}),
        ('api', {'problems': api, 'auto_fixable': True, 'checked': True, 'unavailable': []})], None)
    assert result['problems'] == lint + api
    assert result['auto_fixable'] is False


@pytest.mark.parametrize('ext,requested,performed,reasons,expected', [
    ('.gd', ['py', 'json', 'py'], (), (),
     'ни один из запрошенных kinds (json, py) не относится к расширению .gd — файл НЕ проверен'),
    ('.tscn', ['headless'], (), (),
     'ни один из запрошенных kinds (headless) не относится к расширению .tscn — файл НЕ проверен'),
    ('.gd', ['api'], ('api',), ('no_cache',),
     'ни одна проверка расширения .gd не выполнена (no_cache) — файл НЕ проверен'),
    ('.gd', None, (), ('no_extends', 'no_cache', 'no_extends'),
     'ни одна проверка расширения .gd не выполнена (no_cache, no_extends) — файл НЕ проверен'),
    ('.json', None, (), (),
     'ни одна проверка расширения .json не выполнена (no_kind) — файл НЕ проверен'),
    ('.tres', ['py'], (), (),
     '.tres проверяется только настоящим Godot, а проверка отключена (--validation off) — файл НЕ проверен'),
    ('.scn', None, (), (),
     'расширение .scn не проверяется этим каналом (проверяются: .cfg, .gd, .gdshader, .json, .py, .shader, .tres, .tscn)'),
])
def test_unchecked_reason_exact_forms(ext, requested, performed, reasons, expected):
    from python.modules.verification.check.domain import core
    assert core.unchecked_reason(ext, requested, performed, reasons) == expected


def test_reason_codes_only_come_from_unchecked_fragments():
    from python.modules.verification.check.domain import core
    fragment = {'problems': [], 'auto_fixable': False, 'checked': False,
                'unavailable': [{'kind': 'api_cache', 'reason': 'no_cache'}]}
    result = core.assemble('res://x.gd', '.gd', [('api', fragment)], ['api'])
    assert result['unchecked_reason'] == (
        'ни одна проверка расширения .gd не выполнена (no_cache) — файл НЕ проверен')
