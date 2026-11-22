"""Frozen observations only; no reference-plugin imports in new tests."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORPUS = ROOT / 'fixtures/corpus/editing/split_gd'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('[0-9]*.json'))]
CASES = [case for case in CASES if case['tool'] == 'split_gd_scan']
NATIVE = [c for c in CASES if c['reference_result'] is not None]


def inputs(case):
    root = ROOT / 'fixtures/projects' / case['fixture']
    prefix = case['reference_addon'] + '/' if case['reference_addon'] else ''
    return [(p.relative_to(root).as_posix()[len(prefix):], p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file()
            and p.relative_to(root).as_posix().startswith(prefix)]


def ordered_inputs(case):
    # Root files before subdirectories, not global full-path sorting (old os.walk).
    return sorted(inputs(case), key=lambda item: (item[0].split('/')[:-1], item[0].split('/')[-1]))


def named(name):
    return next(c for c in NATIVE if c['id'].split('-', 1)[1] == name)
