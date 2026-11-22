"""Native-pinned input bytes, repeated observations and complete result parity."""
import hashlib
import json
from pathlib import Path
import pytest
from tests.py.llm.api_cases import CORPUS, ROOT, observe

MANIFEST = json.loads((CORPUS / 'manifest.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('entry', MANIFEST['cases'], ids=lambda item: item['id'])
def test_api_native_corpus(entry, tmp_path):
    raw = (CORPUS / entry['input']['path']).read_bytes()
    assert len(raw) == entry['input']['bytes']
    assert hashlib.sha256(raw).hexdigest() == entry['input']['sha256']
    assert entry['native_pass_1'] == entry['native_pass_2'] == entry['expected']
    assert entry['provenance']['source'] in MANIFEST['sources']
    assert observe(json.loads(raw), tmp_path) == entry['expected']


@pytest.mark.parametrize('source', list(MANIFEST['sources']), ids=list(MANIFEST['sources']))
def test_api_references_are_byte_exact(source):
    record = MANIFEST['sources'][source]
    data = (ROOT / record['destination']).read_bytes()
    assert len(data) == record['pin']['bytes']
    assert hashlib.sha256(data).hexdigest() == record['pin']['sha256']
    assert data.count(b'\n') == record['pin']['LF']
    assert data.count(b'\r\n') == record['pin']['CRLF']
