from pathlib import Path
import base64
import json

import pytest

from python.formats import gdscript, tscn


def test_existing_gdscript_star_exports_are_unchanged():
    assert gdscript.__all__ == ['tokenize', 'parse', 'line_indents', 'script_parent',
                               'exact_string_value', 'handlers', 'custom_signals', 'method_connected']

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/scene_model/node_rename'
RECORD = json.loads((CORPUS / '002-all_spans_and_scripts.json').read_text(encoding='utf-8'))


def test_gdscript_literal_native_replacements_and_count():
    item = next(f for f in RECORD['expect']['result']['files'] if f['path'] == 'res://main.gd')
    before = base64.b64decode(item['before_bytes']).decode('utf-8')
    after, count = gdscript.rename_node_paths(before, 'Arm', 'LongArm', True, [('Arm', 'LongArm')])
    assert after.encode() == base64.b64decode(item['after_bytes'])
    assert count == item['occurrences']


def test_tscn_span_edits_use_accepted_patch_without_reconstruction():
    item = RECORD['expect']['result']['files'][0]
    before = base64.b64decode(item['before_bytes']).decode('utf-8')
    view = tscn.structure(before)
    target = next(n for n in view[1] if n['path'] == 'Arm')
    edits, count = tscn.node_rename_edits(before, view, target, 'LongArm', 'LongArm')
    assert tscn.patch(before, edits).encode() == base64.b64decode(item['after_bytes'])
    assert count == item['occurrences']
    assert tscn.__all__ == ('structure', 'fields', 'patch', 'rows')
