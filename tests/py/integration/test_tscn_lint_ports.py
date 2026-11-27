"""Red cases before expressly authorized read-only common seams (R-22)."""
import builtins
import hashlib
import json

import pytest

from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.substrate.fs.disk_fs import DiskFileSystem
from python.substrate.store import api_cache_store


def tree(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def test_is_file_checks_metadata_not_large_resource_content(tmp_path, monkeypatch):
    (tmp_path / 'large.bin').write_bytes(b'x' * (READ_TEXT_MAX_BYTES + 1))
    before = tree(tmp_path)
    fs = DiskFileSystem(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('metadata check read resource contents')
    with monkeypatch.context() as guard:
        guard.setattr(builtins, 'open', forbidden)
        assert fs.is_file('large.bin') is True
        assert fs.is_file('absent.bin') is False
    assert tree(tmp_path) == before


def test_is_file_refuses_outside_before_metadata(tmp_path):
    with pytest.raises(PermissionError):
        DiskFileSystem(tmp_path).is_file('../outside')


@pytest.mark.parametrize('classes', [{'Node': {'inherits': 'Object'}},
                                   {'Node': {}, 'Sentinel': {'inherits': 'Object'}}])
def test_cache_snapshot_read_only_without_migration(tmp_path, classes):
    project = tmp_path / 'project'
    history = project / '.agent_history'
    history.mkdir(parents=True)
    (history / 'godot_api_cache.json').write_text(json.dumps({'classes': classes}), encoding='utf-8')
    state = tmp_path / 'absent-state'
    before = tree(tmp_path)
    store = api_cache_store.ApiCacheStore(project, state_dir=state)
    assert store.classes() == classes
    assert store.classes() == classes
    assert tree(tmp_path) == before
    assert not state.exists() and not (history / 'snapshots').exists()


def test_cache_missing_and_broken_empty_without_mkdir(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    store = api_cache_store.ApiCacheStore(project, state_dir=tmp_path / 'absent-state')
    before = tree(tmp_path)
    assert store.classes() == {} and tree(tmp_path) == before
    history = project / '.agent_history'
    history.mkdir()
    (history / 'godot_api_cache.json').write_bytes(b'{broken')
    before = tree(tmp_path)
    assert store.classes() == {} and tree(tmp_path) == before


def test_default_bootstrap_binds_consumer_protocols(tmp_path, no_bundled_api_cache):
    from python.runtime.bootstrap import default_ports
    from python.modules.verification.tscn_lint.ports import SceneReader, ApiCache
    ports = default_ports(str(tmp_path), 'test', state_dir=tmp_path / 'state')
    assert isinstance(ports['fs'], SceneReader)
    assert isinstance(ports['api_cache'], ApiCache)
    assert ports['api_cache'].classes() == {}


def test_bundled_legacy_cache_is_read_without_migration_or_write(tmp_path):
    addon = tmp_path / 'addon'
    addon.mkdir()
    (addon / 'default_api_cache.json').write_text(
        json.dumps({'classes': {'Node': {'inherits': 'Object'}}}), encoding='utf-8')
    project = tmp_path / 'project'
    project.mkdir()
    before = tree(tmp_path)
    cache = api_cache_store.ApiCacheStore(project, state_dir=tmp_path / 'state', addon_dir=addon)
    assert cache.classes() == {'Node': {'inherits': 'Object'}}
    assert tree(tmp_path) == before
    assert not (addon / 'agent_api_cache').exists()


def test_new_external_state_cache_precedes_legacy_project_snapshot(tmp_path):
    project = tmp_path / 'project'
    history = project / '.agent_history'
    history.mkdir(parents=True)
    (history / 'godot_api_cache.json').write_text(
        json.dumps({'classes': {'Legacy': {'inherits': 'Object'}}}), encoding='utf-8')
    store = api_cache_store.ApiCacheStore(project, state_dir=tmp_path / 'state')
    path = store.cache_path
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'classes': {'External': {'inherits': 'Object'}}}), encoding='utf-8')
    before = tree(tmp_path)
    assert store.classes() == {'External': {'inherits': 'Object'}}
    assert tree(tmp_path) == before
