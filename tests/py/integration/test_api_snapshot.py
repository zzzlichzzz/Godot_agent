"""Red before authorized additive snapshot seam; accepted classes untouched."""
import json

import pytest

from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.substrate.store.api_cache_store import ApiCacheStore


def write(path, version, classes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'godot_version': version, 'classes': classes}), encoding='utf-8')


def test_memoized_classes_unchanged_but_snapshot_fresh(tmp_path):
    project = tmp_path / 'project'
    path = project / '.agent_history/godot_api_cache.json'
    old = {'Old': {'inherits': None}}; new = {'New': {'inherits': None}}
    write(path, 'old', old)
    store = ApiCacheStore(project)
    assert store.classes() == old and store.snapshot() == (old, 'old')
    write(path, 'new', new)
    assert store.classes() == old and store.snapshot() == (new, 'new')
    assert store._classes == old


def test_external_legacy_and_bundled_precedence_same_record(tmp_path):
    project = tmp_path / 'project'; addon = tmp_path / 'addon'
    store = ApiCacheStore(project, state_dir=tmp_path / 'state', addon_dir=addon)
    paths = [store.cache_path, project / '.agent_history/godot_api_cache.json',
             addon / 'agent_api_cache/default_api_cache.json', addon / 'default_api_cache.json']
    for i, path in enumerate(paths):
        write(path, str(i), {'C' + str(i): {'inherits': None}})
    for i, path in enumerate(paths):
        assert store.snapshot() == ({'C' + str(i): {'inherits': None}}, str(i))
        path.unlink()
    assert store.snapshot() == ({}, '')


@pytest.mark.parametrize('raw', [b'{broken', b'[]', b'{"classes":[]}',
                               b'{"godot_version":"x","classes":{}}', b'\xff'])
def test_bad_or_empty_snapshot_no_mkdir(tmp_path, raw):
    project = tmp_path / 'project'; path = project / '.agent_history/godot_api_cache.json'
    path.parent.mkdir(parents=True); path.write_bytes(raw)
    store = ApiCacheStore(project, state_dir=tmp_path / 'absent-state')
    assert store.snapshot() == ({}, '')
    assert path.read_bytes() == raw and not (tmp_path / 'absent-state').exists()
    assert not (path.parent / 'snapshots').exists()


def test_missing_snapshot_no_directories(tmp_path):
    project = tmp_path / 'absent-project'
    store = ApiCacheStore(project, state_dir=tmp_path / 'absent-state')
    assert store.snapshot() == ({}, '')
    assert not project.exists() and not (tmp_path / 'absent-state').exists()


def test_falsy_record_is_retained_and_missing_version_empty(tmp_path):
    project = tmp_path / 'project'; path = project / '.agent_history/godot_api_cache.json'
    write(path, '', {'Some': {}})
    assert ApiCacheStore(project).snapshot() == ({'Some': {}}, '')


def test_snapshot_size_limit_exact_and_excess(tmp_path):
    project = tmp_path / 'project'; path = project / '.agent_history/godot_api_cache.json'
    write(path, '4.6', {'C': {'inherits': None}})
    raw = path.read_bytes()
    path.write_bytes(raw + b' ' * (READ_TEXT_MAX_BYTES - len(raw)))
    store = ApiCacheStore(project)
    assert store.snapshot() == ({'C': {'inherits': None}}, '4.6')
    path.write_bytes(path.read_bytes() + b' ')
    assert store.snapshot() == ({}, '')
