"""Actual batch/receipt/process orchestration; the fake worker is labelled simulated."""
import hashlib
import json
from pathlib import Path
import sys
from tests.py.judge_a1.observations import CORPUS, call, snapshot


def run(module, project, sandbox, case):
    if case['operation'] == 'rename':
        data = b'extends Node\nfunc renamed():\n\tpass\n'
        prepared = {'files': [{'path': 'res://player.gd', 'after_bytes': data,
                              'before_hash': hashlib.sha256((project/'player.gd').read_bytes()).hexdigest()}]}
        return module.batch_from_rename(str(project), prepared)
    if case['operation'] == 'empty_rename':
        return module.batch_from_rename(str(project), {'files': []})
    if case['operation'] == 'make':
        return module.make_batch('transaction', [], case['targets'], {}, case.get('required', []))
    if case['operation'] == 'required':
        batch = module.make_batch('transaction', [], ['res://player.gd'], {}, ['res://player.gd'])
    else:
        batch = module.batch_from_action(str(project), case['action'])
    if case.get('batch_only'):
        return batch
    temp = sandbox/'runs'
    temp.mkdir()
    mode = case.get('mode', 'required')
    if case.get('stale_before'):
        with (project/'player.gd').open('ab') as handle:
            handle.write(b'# changed before validation\n')
    before = snapshot(project)
    receipt = call(module.validate_batch, str(project), batch,
                   mode=mode, executable=str(sandbox/'no-engine.exe'),
                   command_prefix=[] if case.get('unavailable') else
                   [sys.executable, '-B', str(Path(__file__).with_name('process_worker.py'))],
                   harness_path=str(CORPUS/'fixtures/harness.gd'), temp_root=str(temp),
                   timeout=case.get('timeout', 4.0))
    after = snapshot(project)
    assert before == after, 'validate_batch wrote the source project'
    assert list(temp.iterdir()) == [], 'owned validation tree was not removed'
    result = {'batch': batch, 'receipt': receipt, 'project_unchanged': True, 'owned_leftovers': []}
    if isinstance(receipt, BaseException):
        return result
    if case.get('mutate_after'):
        path = project/('player.gd' if case['mutate_after'] == 'player' else 'scenes/main.tscn')
        with path.open('ab') as handle:
            handle.write(b'# external edit\n')
    result['verify'] = call(module.verify_receipt, str(project), batch, receipt)
    result['message'] = module.blocking_message(receipt)
    mismatch = dict(receipt, candidate_digest='0'*64)
    result['mismatch'] = call(module.verify_receipt, str(project), batch, mismatch)
    return result
