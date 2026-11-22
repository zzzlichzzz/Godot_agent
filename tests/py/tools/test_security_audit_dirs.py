"""F8/ADR-0012: directories are not readable security-audit artifacts."""
import json
from pathlib import Path

from tools import security_audit


def test_files_excludes_gd_directory_keeps_regular_file(tmp_path):
    (tmp_path / 'x.gd').mkdir()
    regular = tmp_path / 'y.gd'
    regular.write_bytes(b'extends Node\n')
    assert security_audit.files(tmp_path, '.gd') == [regular]


def test_complete_gate_handles_tree_with_gd_directory(tmp_path, monkeypatch, capsys):
    original = security_audit.ROOT
    editor = tmp_path / 'editor'
    editor.mkdir()
    (editor / 'x.gd').mkdir()
    (editor / 'y.gd').write_bytes(b'extends Node\n')
    (tmp_path / '.gitignore').write_bytes((original / '.gitignore').read_bytes())
    contract = tmp_path / 'contract'
    contract.mkdir()
    for name in ('network_allow.json', 'browser_stealth.json'):
        (contract / name).write_bytes((original / 'contract' / name).read_bytes())
    monkeypatch.setattr(security_audit, 'ROOT', tmp_path)
    monkeypatch.setattr(security_audit, 'PY', tmp_path / 'python')
    monkeypatch.setattr(security_audit, 'GD_ROOTS', [editor, tmp_path / 'runtime'])
    assert security_audit.main(['--json']) == 0
    assert json.loads(capsys.readouterr().out) == {'status': 'ok', 'detail': 'нарушений нет'}


def test_exact_existing_regular_file_filter_is_pinned():
    source = Path(security_audit.__file__).read_bytes()
    assert b'        if not path.is_file():\r\n            continue\r\n' in source
