"""Precedence, full counts, quota edges, skip set, and native traversal ordering."""
import pytest

from python.modules.editing.split_gd.domain.refs import eligible, scan
from .corpus import NATIVE, named, ordered_inputs


@pytest.mark.parametrize('case', NATIVE, ids=lambda c: c['id'])
def test_reference_scan(case):
    raw = case['reference_result']
    result = scan(raw['donor'], raw['public_methods'], ordered_inputs(case))
    assert result == {k: raw[k] for k in ('counts', 'occurrences', 'truncated', 'hard_files', 'soft_files')}


@pytest.mark.parametrize('name,counts', [('no_refs', {'path': 1}), ('doc_priority', {'doc': 2}),
    ('source_markers', {'source_read': 8}), ('mention_zero', {'call': 2, 'mention': 0})])
def test_category_pins(name, counts):
    case = named(name); raw = case['reference_result']
    result = scan(raw['donor'], raw['public_methods'], ordered_inputs(case))
    for kind, expected in counts.items():
        assert result['counts'][kind] == expected


@pytest.mark.parametrize('n,truncated', [(999, False), (1000, False), (1001, True), (1200, True)])
def test_occurrence_quota_counts_do_not_stop(n, truncated):
    result = scan('donor.gd', ['ping'], [('a.txt', b'.ping()\n' * n)])
    assert result['counts']['call'] == n and len(result['occurrences']) == min(1000, n)
    assert result['truncated'] is truncated and result['soft_files'] == ['a.txt']


@pytest.mark.parametrize('path,expected', [('node_modules/a.gd', False), ('.hidden/a.txt', False),
    ('nested/build/a.py', False), ('agent_api_cache/a.json', False), ('.file.TXT', True),
    ('node_modulesish/a.gd', True), ('a.bin', False), ('x/no_extension', False)])
def test_eligible(path, expected):
    assert eligible(path) is expected


def test_read_markers_require_file_name_not_stem():
    result = scan('donor.gd', [], [('a.txt', b'donor read_text\ndonor.gd read_text\n')])
    assert result['counts']['path'] == result['counts']['source_read'] == 1
    assert result['hard_files'] == ['a.txt'] and result['soft_files'] == []


def test_scanner_does_not_reorder_supplied_native_walk():
    result = scan('donor.gd', [], [('z.txt', b'donor.gd'), ('a/ref.txt', b'donor.gd')])
    assert [o['file'] for o in result['occurrences']] == ['z.txt', 'a/ref.txt']
    assert result['soft_files'] == ['a/ref.txt', 'z.txt']
