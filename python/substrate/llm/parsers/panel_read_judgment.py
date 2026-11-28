"""Reconcile the frozen judge with enabled panel reads, without executing the read."""


def panel_read_judgment(result, valid_read):
    action = result.get('action') or {}
    issues = result['blocking']
    if (valid_read and isinstance(action, dict) and len(issues) == 1
            and issues[0]['category'] == 'schema'
            and issues[0]['message'] == 'unknown action: ' + str(action.get('action'))
            and valid_read(action)):
        return dict(result, acceptable=True, blocking=[], score=80)
    return result
