"""D64: real default lookup and explicit lookup, without a fake engine claim."""
import hashlib
from pathlib import Path

import pytest

from .observations import ROOT, subjects

SHA = '799ec9e26f43f65aa8208a1cf1e5379b8d5c3ca80fbd3ad7a0a8e87251da895e'


def test_resource_verbatim_pin():
    raw = (ROOT/'python/agent_headless_validator.gd').read_bytes()
    assert (len(raw), hashlib.sha256(raw).hexdigest(), raw.count(b'\n'), raw.count(b'\r\n')) == (1701, SHA, 39, 0)


def test_real_default_harness_lookup(tmp_path):
    with subjects(tmp_path/'default') as (modules, _):
        path = Path(modules['godot_headless_validation']._harness_source())
        assert path.resolve() == (ROOT/'python/agent_headless_validator.gd').resolve()
        raw = path.read_bytes()
        assert len(raw) == 1701 and hashlib.sha256(raw).hexdigest() == SHA


@pytest.mark.parametrize('relative', ['python/agent_headless_validator.gd',
                                   'fixtures/corpus/assistant/judge/reference/A1/fixtures/harness.gd'])
def test_real_explicit_lookup(tmp_path, relative):
    explicit = ROOT/relative
    with subjects(tmp_path/'explicit') as (modules, _):
        path = Path(modules['godot_headless_validation']._harness_source(str(explicit)))
        assert path.resolve() == explicit.resolve()
        assert path.read_bytes() == explicit.read_bytes()
