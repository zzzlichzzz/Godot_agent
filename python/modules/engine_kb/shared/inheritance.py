"""C.11 by specification: pure inheritance/member rules from gd_api_cache."""


def resolve_chain(classes, class_name, max_depth=30):
    """Nearest first; stop at missing/falsy record, cycle or depth budget."""
    chain, seen = [], set()
    current = class_name
    while current and current not in seen and len(chain) < max_depth:
        info = classes.get(current)
        if not info:
            break
        seen.add(current)
        chain.append(current)
        current = info.get('inherits') or None
    return chain


def collect_members(classes, chain):
    """Nearest method wins; properties/signals are independent unions."""
    methods, properties, signals = {}, set(), set()
    for name in chain:
        info = classes.get(name) or {}
        for method, arity in (info.get('methods') or {}).items():
            methods.setdefault(method, arity)
        properties.update(info.get('properties') or [])
        signals.update(info.get('signals') or [])
    return methods, properties, signals


def collect_signatures(classes, chain):
    """Only str/str entries; nearest signature wins, including empty string."""
    signatures = {}
    for name in chain:
        info = classes.get(name) or {}
        for method, signature in (info.get('signatures') or {}).items():
            if isinstance(method, str) and isinstance(signature, str):
                signatures.setdefault(method, signature)
    return signatures
