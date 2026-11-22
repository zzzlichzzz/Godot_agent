"""Frozen inputs and outputs only; never import the reference plugin."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORPUS = ROOT / 'fixtures/corpus/verification/tscn_lint'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('[0-9]*.json'))]


def inputs(case):
    project = ROOT / 'fixtures/projects' / case['fixture']
    return {p.relative_to(project).as_posix(): p.read_bytes()
            for p in project.rglob('*') if p.is_file()}


def domain_args(case):
    files = inputs(case)
    return {'existing_paths': set(files),
            'instance_texts': {name: raw.decode('utf-8', errors='replace')
                               for name, raw in files.items()
                               if name.lower().endswith(('.tscn', '.scn'))},
            'api_classes': case['reference_api_classes'] or {},
            'planned_paths': case['args'].get('planned_paths', [])}
