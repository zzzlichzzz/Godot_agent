"""Simulated engine protocol ONLY. Never executes scene/script/case contents."""
import json
from pathlib import Path
import sys
import time


def main():
    root = Path(sys.argv[sys.argv.index('--path') + 1])
    service = root/'.godot_agent_validation'
    manifest = json.loads((service/'manifest.json').read_text('utf-8'))
    malformed = root/'.a1-protocol.json'
    if malformed.is_file():
        (service/'result.json').write_text(malformed.read_text('utf-8'), encoding='utf-8')
        return 0
    diagnostics = []
    for target in manifest['targets']:
        path = root/target[6:]
        if not path.is_file():
            diagnostics.append({'severity': 'error', 'category': 'load',
                                'message': 'Missing synthetic resource', 'path': target})
            continue
        raw = path.read_bytes()
        if b'# A1_SLEEP' in raw:
            time.sleep(3)
        if b'# A1_NORESULT' in raw:
            return 0
        if b'# A1_OUTPUT' in raw:
            print('fixture-output-'*20000)
        for token, severity in ((b'# A1_ERROR', 'error'), (b'# A1_WARNING', 'warning')):
            if token in raw:
                diagnostics.append({'severity': severity, 'category': 'parse',
                                    'message': 'Synthetic resource diagnostic', 'path': target})
    (service/'result.json').write_text(json.dumps({'schema_version': 1, 'diagnostics': diagnostics}),
                                     encoding='utf-8')
    return 1 if any(row['severity'] == 'error' for row in diagnostics) else 0


if __name__ == '__main__':
    raise SystemExit(main())
