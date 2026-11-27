"""A genuine native ambiguity case closes an observed mutation coverage gap."""
import json

from .observations import CORPUS, observe
from .test_reference import pin


def test_supplement_integrity():
    folder = CORPUS/'supplement'
    manifest = json.loads((folder/'manifest.json').read_text('utf-8'))
    assert manifest['case_count'] == 1 and manifest['oracle_runs'] == 2
    assert manifest['oracle_differences'] == 0
    assert manifest['initial_survivor_preserved'] and manifest['original214_unchanged']
    assert pin(folder/'case.json') == manifest['case']
    assert pin(folder/'observation.json') == manifest['observation']


def test_native_ambiguity(tmp_path):
    folder = CORPUS/'supplement'
    case = json.loads((folder/'case.json').read_text('utf-8'))
    expected = json.loads((folder/'observation.json').read_text('utf-8'))
    assert observe(case, tmp_path/'canonical-supplement') == expected
