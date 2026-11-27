"""Independent projections of frozen native data; never import the old plugin."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORPUS = ROOT / 'fixtures/corpus/editing/split_gd'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('1[0-9][0-9]-*.json'))]
NATIVE = [case for case in CASES if 'reference_inventory' in case]
SUCCESS = [case for case in NATIVE if case['reference_result'] is not None]


def source(case):
    root = ROOT / 'fixtures/projects' / case['fixture'] / case['reference_addon']
    return (root / case['reference_donor']).read_bytes().decode('utf-8-sig', errors='replace').replace('\r\n', '\n').replace('\r', '\n')


def classes(case):
    path = ROOT / 'fixtures/projects' / case['fixture'] / '.agent_history/godot_api_cache.json'
    return json.loads(path.read_bytes())['classes'] if path.is_file() else {}


def project(raw):
    safe = {key: copy.deepcopy(raw[key]) for key in
            ('schema', 'kind', 'donor', 'donor_sha256', 'newline', 'target_lines',
             'groups', 'modules', 'wrappers', 'warnings', 'stats')}
    safe['modules'] = [{k: v for k, v in module.items() if k != 'content'} for module in safe['modules']]
    return safe


def named(name):
    return next(case for case in CASES if case['id'].split('-', 1)[1] == name)
