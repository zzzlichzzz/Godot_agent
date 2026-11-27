"""New read/prepare envelopes, preserving native errors, bytes and no-op counts."""
import copy
from .observations import call, HarnessInvocationError


def run(module, project, addon, case):
    group = case['group']
    action = copy.deepcopy(case.get('action'))
    original = copy.deepcopy(action)
    options = dict(case.get('options', {}), addon_dir=str(addon))
    if case.get('function') == 'normalize_variant':
        variant = copy.deepcopy(case['variant'])
        if case.get('special_float'):
            variant['value'] = float(case['special_float'])
        return call(module.normalize_variant, variant)
    if case.get('function') == 'normalize_node_path':
        return call(module.normalize_node_path, case['path'])
    if group == 'high_level_actions':
        result = call(module.compile_action, str(project), action, **options)
        assert action == original, 'compiler mutated its input'
        return {'compiled': result, 'again': call(module.compile_action, str(project),
                                                 copy.deepcopy(original), **options)}
    normalize_options = dict(options)
    if case.get('normalize_only'):
        normalize_options.update(case.get('normalize_options', {}))
    normalized = call(module.normalize_action, str(project), action, **normalize_options)
    assert action == original, 'normalizer mutated its input'
    if isinstance(normalized, BaseException):
        return normalized
    result = {'normalized': normalized}
    if group in ('scene_actions', 'resource_actions'):
        canonical, absolute = normalized
        result['digest'] = call(module.canonical_digest, canonical)
        result['summary'] = call(module.operation_summary, canonical)
    elif group == 'transaction_actions':
        canonical = normalized
    else:
        raise HarnessInvocationError('unknown action group')
    result['normalized_again'] = call(module.normalize_action, str(project),
                                      copy.deepcopy(canonical), **normalize_options)
    if case.get('normalize_only'):
        return result
    prepared = call(module.prepare, str(project), copy.deepcopy(original), **options)
    result['prepared'] = prepared
    if isinstance(prepared, BaseException):
        return result
    result['public'] = call(module.public_prepared, prepared)
    result['prepared_again'] = call(module.prepare, str(project), copy.deepcopy(original), **options)
    if group == 'transaction_actions':
        result['diffs'] = call(module.prepared_diffs, prepared)
    return result
