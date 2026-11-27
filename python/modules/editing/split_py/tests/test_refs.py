"""Raw scan parity over captured immutable inputs plus adversarial boundaries."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
CORPUS = ROOT / 'fixtures/corpus/editing/split_py'
CASES = [c for p in sorted(CORPUS.glob('[0-9]*.json')) if (c := json.loads(p.read_bytes()))['tool']=='split_scan']
CASES = [c for c in CASES if c['reference_result'] is not None]


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_scan_native(case):
    from python.modules.editing.split_py.domain.refs import scan
    from python.modules.editing.split_py.domain.walk import eligible
    fixture = ROOT / 'fixtures/projects' / case['fixture']
    fixture /= case['reference_args']['addon_root']
    def files(folder):
        for p in sorted(folder.iterdir()):
            if p.is_file():
                rel = p.relative_to(fixture).as_posix()
                if eligible(rel):
                    yield rel, p.read_bytes()
        for p in sorted(folder.iterdir()):
            if p.is_dir():
                yield from files(p)
    raw = case['reference_result']
    answer = scan(raw['rel'], raw['stem'], raw['rel'].rsplit('/',1)[-1], files(fixture))
    assert answer == {k: raw[k] for k in ('counts','occurrences','truncated')}


@pytest.mark.parametrize('raw, text', [(b'\xef\xbb\xbfimport donor\r\n','import donor\r\n'),
    (b'\xef\xbb',''), (b'\xef\xbb\xbf\xef\xbb\xbfX','\ufeffX'), (b'\xff','\ufffd')])
def test_local_decode(raw, text):
    from python.modules.editing.split_py.domain.text import decode
    assert decode(raw) == text


@pytest.mark.parametrize('operator', ['=','+=','-=','*=','/=','%=','@=','|=','&=','^='])
def test_native_patch_operators(operator):
    from python.modules.editing.split_py.domain.refs import scan
    result = scan('donor.py','donor','donor.py',[('ref.py',('donor . fn '+operator+' 1\n').encode())])
    assert result['counts']['patch'] == 1
