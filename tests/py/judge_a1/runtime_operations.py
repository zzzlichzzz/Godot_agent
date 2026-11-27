"""Protocol, cursor and report operations derived from cases, not old test code."""
from tests.py.judge_a1.observations import call


def run(module, project, sandbox, case):
    operation = case['operation']
    if operation == 'normalize':
        return module.normalize_action(str(project), case['action'])
    if operation == 'result':
        return module.normalize_result(case['result'])
    if operation == 'nonfinite':
        action = dict(case['action'])
        action['steps'] = [dict(step) for step in action['steps']]
        action['steps'][0]['expected'] = float('nan')
        return module.normalize_action(str(project), action)
    if operation == 'log':
        folder = sandbox/'user/logs'
        folder.mkdir(parents=True)
        path = folder/'godot.log'
        mode = case['mode']
        if mode != 'missing':
            path.write_bytes(b'old startup\n')
        cursor = module.capture_log_cursor(str(folder.parent))
        initial = dict(cursor)
        if mode == 'append':
            with path.open('ab') as handle:
                handle.write(case['delta'].encode('utf-8'))
        elif mode == 'oversize':
            with path.open('ab') as handle:
                handle.write(b'x'*(module.MAX_LOG_DELTA_BYTES + 1))
        elif mode == 'truncate':
            path.write_bytes(b'x')
        elif mode == 'deleted':
            path.unlink()
        elif mode == 'wrong_inode':
            cursor['inode'] += 1
        elif mode == 'error_cap':
            with path.open('ab') as handle:
                handle.write(b'ERROR: repeated\n'*30)
        errors = module.collect_log_errors(cursor)
        return {'initial': initial, 'cursor': cursor, 'errors': errors,
                'available': module.log_source_available(cursor),
                'invalid_cursor_errors': module.collect_log_errors(None),
                'invalid_cursor_available': module.log_source_available(None)}
    action = module.normalize_action(str(project), case['action'])
    pending = module.create_request(action, 'fixture-chat', 3, str(project), str(sandbox/'user'))
    public = module.public_request(pending)
    pending.update(state='bound', session_id=4, run_id='fixture-run')
    game = module.game_request(pending)
    envelopes = {'pending': pending, 'public': public, 'game': game}
    assert pending['request_id'] == 'a'*32 and pending['result_token'] == 'b'*48
    assert 'result_token' not in game
    if operation == 'request':
        return envelopes
    if operation != 'finalize':
        raise AssertionError('unknown runtime operation')
    report = call(module.finalize_result, pending, case['result'],
                  log_errors=case.get('log_errors'), log_available=case.get('log_available', True))
    return {'envelopes': envelopes, 'report': report,
            'formatted': None if isinstance(report, BaseException) else module.format_report(report)}
