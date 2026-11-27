"""Recorded-site fixture pins; no local server or real Chrome in offline tests."""
import hashlib
import json

from tests.py.browser.runtime_cases import ROOT


def test_oracle_is_pinned_local_fixture_not_recorded_executable_response():
    corpus = ROOT / 'fixtures/corpus/browser/runtime'
    manifest = json.loads((corpus / 'manifest.json').read_bytes())
    entry = manifest['oracle']
    assert entry['file'] == 'oracle.html'
    raw = (corpus / entry['file']).read_bytes()
    assert len(raw) == entry['bytes'] and hashlib.sha256(raw).hexdigest() == entry['sha256']
    text = raw.decode('utf-8')
    assert "connect-src http://127.0.0.1:*" in text
    assert "fetch('http://127.0.0.1:' + port + paths[kind]" in text
    assert not any(token in text for token in ('https://', 'visibilityState', 'webdriver', 'clipboard', 'eval('))
