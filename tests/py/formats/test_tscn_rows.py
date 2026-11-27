"""Third reference view; accepted structure/fields corpus stays unchanged."""
import json
from pathlib import Path
import pytest
from python.formats import tscn

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/scene_model/tree'
MANIFEST = json.loads((CORPUS / 'manifest.json').read_bytes())


@pytest.mark.parametrize('name', sorted(MANIFEST['format_rows']))
def test_rows_matches_actual_reference_locals(name):
    raw = (CORPUS / 'project/scenes' / name).read_bytes()
    text = raw.decode('utf-8-sig', errors='replace').replace('\r\n', '\n').replace('\r', '\n')
    assert tscn.rows(text) == MANIFEST['format_rows'][name]


def test_rows_is_additive_to_closed_operations():
    assert tuple(tscn.__all__) == ('structure', 'fields', 'patch', 'rows')
    assert tscn.patch('\ufeffraw\r\n', []) == '\ufeffraw\r\n'
    assert set(tscn.rows('')) == {'nodes', 'connections', 'resources'}
