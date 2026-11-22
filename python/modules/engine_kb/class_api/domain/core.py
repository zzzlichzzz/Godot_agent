"""C.11 by specification: typed, deterministic projection of old class API."""
from python.modules.engine_kb.shared.inheritance import (
    collect_members, collect_signatures, resolve_chain,
)


def _arity(value):
    try:
        return int(value[0]), int(value[1])
    except (TypeError, ValueError, IndexError, KeyError, OverflowError):
        return -1, -1


def assemble(class_name, classes, cache_version):
    chain = resolve_chain(classes, class_name)
    methods, properties, signals = collect_members(classes, chain)
    signatures = collect_signatures(classes, chain)
    entries = []
    for name in sorted(methods):
        lo, hi = _arity(methods[name])
        entries.append({'name': name, 'min_args': lo, 'max_args': hi,
                        'signature': signatures.get(name, '')})
    return {'class_name': class_name, 'found': bool(classes.get(class_name)),
            'cache_version': cache_version, 'inherits': chain, 'methods': entries,
            'properties': sorted(properties), 'signals': sorted(signals), 'unavailable': []}
