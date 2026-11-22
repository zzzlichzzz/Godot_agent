"""Captured C.18 inputs; no reference code is imported or executed by tests."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORPUS = ROOT/'fixtures/corpus/editing/split_py'
CASES = [c for p in sorted(CORPUS.glob('[0-9]*.json'))
         if (c := json.loads(p.read_bytes()))['tool'] == 'split_plan']
SUCCESSES = [c for c in CASES if c['expect']['ok']]


def inputs(case):
    folder = ROOT/'fixtures/projects'/case['fixture']
    donor = case['args']['path'][6:]
    raw = (folder/donor).read_bytes()
    files = [(p.relative_to(folder).as_posix(), p.read_bytes())
             for p in sorted(folder.rglob('*')) if p.is_file()]
    return folder, donor, raw, files


def prepared(case, hook=False):
    from python.modules.editing.split_py.domain import arch, core, inventory, plan, refs, walk
    folder, donor, raw, files = inputs(case)
    map_path = folder/'docs/architecture_map.json'
    try:
        map_data = arch.load_map(json.loads(map_path.read_bytes()))
    except (OSError,ValueError):
        map_data = None
    occupied = [p.relative_to(folder).as_posix() for p in folder.rglob('*')]
    base = donor.rsplit('/', 1)[-1]
    scan = refs.scan(donor, walk.stem(base), base, [(p, b) for p, b in files if walk.eligible(p)])
    public = core.assemble(donor, walk.stem(base), scan)
    scan.update(hard_files=public['hard_files'], soft_files=public['soft_files'])
    if hook and case.get('reference_hook') == 'second_donor_metadata_false':
        scan = None
    return plan.plan_split(donor, inventory.decode(raw), case['args'].get('groups'),
                           case['args'].get('target_lines', 900), map_data=map_data,
                           index=arch.name_index(files), occupied=occupied, scan=scan)
