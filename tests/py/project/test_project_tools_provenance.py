"""Pinned bytes/manifest independent of the unavailable original machine source."""
import hashlib
import json

from tests.py.project.observations import CORPUS, FIXTURES, ROOT


def test_project_references_preserve_pinned_bytes_and_eol():
    expected = {
        'project_tools.py': (102471, '79e9b035bd211f4a44623573d64f88f5bf47a049725c18dc90d985f47c6a7877', 1960, 1960),
        'project_settings_actions.py': (13735, 'fcdb4635aa8ccb965f0775e6b52f6f339c18809da3a3baac3b9e12da6c8e932f', 251, 0),
    }
    for name, value in expected.items():
        raw = (ROOT / 'python/substrate/project' / name).read_bytes()
        assert (len(raw), hashlib.sha256(raw).hexdigest(), raw.count(b'\n'), raw.count(b'\r\n')) == value


def test_project_manifest_once_only_cases_and_fixture_integrity():
    manifest = json.loads((CORPUS / 'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['cases']) == len({row['id'] for row in manifest['cases']}) == 288
    for row in manifest['cases']:
        raw = (CORPUS / row['file']).read_bytes()
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    for relative, expected in manifest['fixtures'].items():
        raw = (FIXTURES / relative).read_bytes()
        assert len(raw) == expected['bytes'] and hashlib.sha256(raw).hexdigest() == expected['sha256']
