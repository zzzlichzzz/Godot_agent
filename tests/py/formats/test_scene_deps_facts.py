"""Native old extractor on EVERY editor/projects/new-corpus gd, plus quirks."""
import hashlib
import json
from pathlib import Path
import pytest
from python.formats import gdscript,tscn

ROOT=Path(__file__).resolve().parents[3]
MANIFEST=json.loads((ROOT/'fixtures/corpus/scene_model/scene_deps/manifest.json').read_bytes())
MANIFEST['script_facts'] += json.loads((ROOT/'fixtures/corpus/scene_model/t1_script_facts/manifest.json').read_bytes())['script_facts']


@pytest.mark.parametrize('fact',MANIFEST['script_facts'],ids=lambda c:c['path'])
def test_handlers_and_code_facts_differential_all_gd(fact):
    raw=(ROOT/fact['path']).read_bytes()
    assert len(raw)==fact['bytes'] and hashlib.sha256(raw).hexdigest()==fact['sha256']
    source=raw.decode('utf-8',errors='replace').replace('\r\n','\n').replace('\r','\n')
    assert gdscript.handlers(source)==fact['handlers']
    assert sorted(gdscript.custom_signals(source))==fact['custom_signals']
    assert {m:gdscript.method_connected(source,m) for m in fact['connected']}==fact['connected']


@pytest.mark.parametrize('fact',MANIFEST['format_facts'],ids=lambda c:repr(c['text']))
def test_literal_regex_quirks_not_semantic_improvements(fact):
    assert gdscript.handlers(fact['text'])==fact['handlers']
    assert sorted(gdscript.custom_signals(fact['text']))==fact['custom_signals']
    assert {m:gdscript.method_connected(fact['text'],m) for m in fact['connected']}==fact['connected']


@pytest.mark.parametrize('fact',MANIFEST['snake_cases'],ids=lambda c:c['name'])
def test_native_to_snake(fact):
    assert tscn.to_snake(fact['name'])==fact['expect']


@pytest.mark.parametrize('fact',MANIFEST['scene_facts'],ids=lambda c:repr(c['text']))
def test_native_coarse_scene_reference_even_in_comments(fact):
    assert tscn.method_referenced(fact['text'],fact['method'])==fact['method_referenced']
    assert tscn.script_referenced(fact['text'],fact['path'])==fact['script_referenced']


def test_capture_covers_every_current_required_gd():
    paths={p.relative_to(ROOT).as_posix() for base in
           (ROOT/'editor',ROOT/'fixtures/projects',ROOT/'fixtures/corpus/scene_model/connections',
            ROOT/'fixtures/corpus/scene_model/scene_deps') for p in base.rglob('*.gd') if p.is_file() and not p.relative_to(ROOT).as_posix().startswith('fixtures/projects/corpus/editing/paths_preview/')}
    assert paths=={f['path'] for f in MANIFEST['script_facts']}
