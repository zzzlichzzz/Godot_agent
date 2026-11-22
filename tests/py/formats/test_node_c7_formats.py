"""Append-only format operations are checked against captured native bytes."""
import base64
import json
from pathlib import Path
import subprocess
import sys

import pytest

from python.formats import gdscript, tscn
from python.modules.scene_model.shared.node_path import find_node_in_scene

ROOT = Path(__file__).resolve().parents[3]
CASES = [json.loads(p.read_text(encoding='utf-8'))
         for feature in ('node_reparent', 'node_delete')
         for p in sorted((ROOT / 'fixtures/corpus/scene_model' / feature).glob('[0-9]*.json'))]
GOOD = [r for r in CASES if r['expect']['ok']]


@pytest.mark.parametrize('record', GOOD, ids=lambda r: r['tool'] + ':' + r['id'])
def test_appended_scene_operations_equal_native_bytes_and_counts(record):
    result = record['expect']['result']
    f = result['files'][0]
    raw = base64.b64decode(f['before_bytes'], validate=True)
    text = raw.decode('utf-8-sig')
    view = tscn.structure(text)
    if result['action'] == 'reparent_node':
        target = find_node_in_scene(view[1], result['old_path'])
        edits, count = tscn.node_reparent_edits(text, view, target, result['new_parent'], result['new_path'])
    else:
        paths = set(result['deleted_nodes'])
        nodes = [next(n for n in view[1] if n['path'] == path) for path in result['deleted_nodes']]
        names = {n['name'] for n in nodes if n['unique_name']}
        edits, count = tscn.node_delete_edits(text, view, nodes, paths, names)
    changed = tscn.patch(text, edits)
    after = (b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'') + changed.encode('utf-8')
    assert after == base64.b64decode(f['after_bytes'], validate=True)
    assert count == f['occurrences']


@pytest.mark.parametrize('destination', ['../New', 'Other-Side/New', 'Ветка/New'])
def test_reparent_unquoted_dollar_uses_native_identifier_rule(destination):
    source = '$Old/Tip\nget_node("Old")\nget_node_or_null(\'Old/Tip\')\nhas_node("Old")\n%Old\n'
    changed, count = gdscript.reparent_node_paths(source, [('Old', destination)])
    dollar = '$"' + destination + '/Tip"' if destination.startswith('..') or '-' in destination else '$' + destination + '/Tip'
    assert changed == (dollar + '\nget_node("' + destination + '")\nget_node_or_null(\'' +
                       destination + '/Tip\')\nhas_node("' + destination + '")\n%Old\n')
    assert count == 4


def test_deletion_facts_are_one_per_noncomment_line_and_keep_order():
    text = '# $Old\n  # %Old\n\n  var a = $Old; var b = get_node("Old")\nvar c = %Old\nvar d = $Oldish\nprint("$Old")\n'
    assert gdscript.deleted_node_references(text, {'Old'}, {'Old'}) == [
        (4, 'var a = $Old; var b = get_node("Old")'), (5, 'var c = %Old'), (7, 'print("$Old")')]


def test_accepted_star_exports_remain_closed():
    assert tscn.__all__ == ('structure', 'fields', 'patch', 'rows')
    assert gdscript.__all__ == ['tokenize', 'parse', 'line_indents', 'script_parent',
                                'exact_string_value', 'handlers', 'custom_signals', 'method_connected']


def test_refactor_components_import_fresh_without_a_cycle():
    for code in ('import python.formats.tscn_refactor', 'import python.formats.tscn'):
        run = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                             capture_output=True, timeout=5)
        assert run.returncode == 0, run.stderr.decode('utf-8')
