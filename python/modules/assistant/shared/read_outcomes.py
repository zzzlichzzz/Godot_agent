"""Project the bounded tool feedback into labels before crossing the diagnostics port."""
import json


def _label(value):
    error = value.get('error')
    if isinstance(error, dict):
        if error.get('target_type') == 'directory':
            return 'directory'
        kind = error.get('kind')
        return kind if kind in ('not_found', 'denied', 'invalid_input', 'unavailable') else 'error'
    if error:
        return 'budget' if error == 'Result exceeds chat budget; narrow the request.' else 'error'
    if value.get('missing'):
        return 'missing_names'
    if value.get('truncated'):
        return 'truncated'
    if value.get('content') == '':
        return 'empty'
    return 'ok'


def read_outcomes(tool, feedback):
    parsed = json.loads(feedback)
    rows = parsed if isinstance(parsed, list) else [parsed]
    def outcome(row):
        if isinstance(row, dict):
            return _label(row) if tool != 'ask' or 'error' in row else 'error'
        if tool == 'ask' and isinstance(row, str):
            return 'ok' if row.strip() else 'empty'
        return 'error'
    return [outcome(row) for row in rows[:5]]
