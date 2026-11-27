"""Keep earlier inventory/bootstrap proofs verifiable after the D130 composition change."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def before_d130(path):
    raw = (ROOT / path).read_bytes()
    revisions = json.loads((ROOT / 'fixtures/corpus/runtime/d130_revision.json').read_bytes())
    if path not in revisions:
        return raw
    spec = revisions[path]
    assert [len(raw), hashlib.sha256(raw).hexdigest()] == spec['after'], path
    lines = raw.decode('utf-8').splitlines(keepends=True)
    for start, end, previous in reversed(spec['reverse']):
        lines[start:end] = [previous]
    raw = ''.join(lines).encode('utf-8')
    assert [len(raw), hashlib.sha256(raw).hexdigest()] == spec['before'], path
    return raw
