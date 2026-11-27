"""S1: directories named *.gd are metadata, not secret-scanning file inputs."""
from tools import security_audit


def test_files_keeps_regular_files_and_descendants_not_directory_names(tmp_path):
    (tmp_path / 'module.gd').mkdir()
    nested = tmp_path / 'nested.gd'
    nested.mkdir()
    ordinary = tmp_path / 'ordinary.gd'
    child = nested / 'child.gd'
    ordinary.write_bytes(b'extends Node\n')
    child.write_bytes(b'extends RefCounted\n')
    assert security_audit.files(tmp_path, '.gd') == sorted([ordinary, child])


def test_secret_check_still_checks_ordinary_file_next_to_empty_gd_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(security_audit, 'ROOT', tmp_path)
    fixtures = tmp_path / 'fixtures'
    fixtures.mkdir()
    (fixtures / 'module.gd').mkdir()
    (fixtures / 'ordinary.gd').write_bytes(('sk-' + 'A' * 24).encode())
    assert security_audit.check_secrets() == ['SEC-06 fixtures/ordinary.gd: похоже на секрет']


def test_existing_skip_dirs_and_missing_base_unchanged(tmp_path):
    cache = tmp_path / '__pycache__'
    cache.mkdir()
    (cache / 'ignored.gd').write_bytes(b'fixture\n')
    assert security_audit.files(tmp_path, '.gd') == []
    assert security_audit.files(tmp_path / 'absent', '.gd') == []
