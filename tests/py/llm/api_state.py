"""Deterministic sandbox-only reference state transactions."""
import json


def state_observation(modules, case, sandbox, clock):
    base = sandbox / 'state'
    base.mkdir()
    for name, data in case.get('files', {}).items():
        target = sandbox / name
        assert sandbox.resolve() in target.resolve().parents
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    trace = []
    for operation in case['operations']:
        if operation.get('clock') is not None:
            clock[0] = operation['clock']
            trace.append(None)
            continue
        module = modules[operation['module']]
        args = list(operation.get('args', []))
        if operation.get('base'):
            args.insert(0, str(base))
        try:
            trace.append(getattr(module, operation['function'])(*args, **operation.get('kwargs', {})))
        except Exception as exc:
            trace.append({'error': type(exc).__name__, 'message': str(exc)})
    files = {}
    for path in sorted(sandbox.rglob('*')):
        if path.is_file():
            try:
                files[path.relative_to(sandbox).as_posix()] = json.loads(path.read_text(encoding='utf-8'))
            except ValueError:
                files[path.relative_to(sandbox).as_posix()] = path.read_text(encoding='utf-8')
    return {'trace': trace, 'files': files}
