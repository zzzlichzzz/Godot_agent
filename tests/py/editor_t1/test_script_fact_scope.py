"""T1 coverage extends inputs, not the accepted format semantics/corpus."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
BASE_PIN={'bytes':110763,'sha256':'1b8780f63d0433c5cd246da92d4f65059add772c8b29fd1606163d3100cd3ab5','LF':3590,'CRLF':0}

def test_native_script_fact_scope_and_frozen_manifest_are_exact():
    raw=(ROOT/'fixtures/corpus/scene_model/scene_deps/manifest.json').read_bytes()
    assert dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),LF=raw.count(b'\n'),CRLF=raw.count(b'\r\n'))==BASE_PIN
    base=json.loads(raw)
    extra=json.loads((ROOT/'fixtures/corpus/scene_model/t1_script_facts/manifest.json').read_bytes())
    assert extra['frozen_manifest_pin']==BASE_PIN
    assert extra['native_pin']['sha256']==base['reference']['files']['godot_tools/scene_deps.py']['sha256']
    assert extra['native_pin']['bytes']==19866
    known={row['path'] for row in base['script_facts']}
    expected={p.relative_to(ROOT).as_posix() for p in (ROOT/'editor').rglob('*.gd') if p.is_file()}-known
    paths=[row['path'] for row in extra['script_facts']]
    additions=json.loads((ROOT/'fixtures/corpus/scene_model/d122_script_facts/manifest.json').read_bytes())['script_facts']
    assert [row['path'] for row in additions]==['editor/native/agent_read_consent.gd']
    assert len(paths)==len(set(paths))==36 and set(paths)==expected-{additions[0]['path']} and not set(paths)&known
