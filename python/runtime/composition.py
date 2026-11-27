"""Manifest preflight and dependency-first activation. Failures stay local to their graph."""
from python.kernel.version import compatible, KERNEL_API
from python.protocol.registry import target_alias


def install_feature_ports(loaded, fs, ports, registry):
    """Publish a shared port once, and isolate failed or conflicting providers."""
    factories, ready = {}, {}
    for item in loaded:
        for name, make in item.spec.port_factories.items():
            factories.setdefault(name, []).append((item.spec.id, make))
    for name, providers in factories.items():
        make = providers[0][1]
        try:
            if name in ports or any(other is not make for _, other in providers):
                raise ValueError('port factory conflict')
            ready[name] = make(fs)
            if ready[name] is None:
                raise ValueError('port factory returned None')
        except Exception as exc:
            registry.mark_failures([{'module': owner, 'reason': 'port %s: %s: %s' %
                                    (name, type(exc).__name__, exc)} for owner, _ in providers])
    disabled = registry.disabled()
    for name, value in ready.items():
        if any(owner not in disabled for owner, _ in factories[name]):
            ports[name] = value


def activation_order(loaded, failures, inventory, registry, disabled, godot, profile):
    specs = {item.spec.id: item for item in loaded}
    declared = {owner: set(item.spec.provides_tools) for owner, item in specs.items()}
    for name, owner in inventory.items():
        declared.setdefault(owner, set()).add(name)
    targets = {name for names in declared.values() for name in names}
    targets.update(owner for owner, names in declared.items() if target_alias(owner, names))
    for item in loaded:
        registry.declare(item.spec.id, item.spec.provides_tools)
        registry.targets(item.spec)
    for name, owner in inventory.items():
        registry.declare(owner, (name,))
        if owner in specs and name not in specs[owner].spec.provides_tools:
            registry.mark_failures([{'module': owner, 'reason': 'contract_tool_missing: ' + name}])
    registry.mark_failures(failures)
    for owner in set(inventory.values()) - specs.keys():
        registry.mark_failures([{'module': owner, 'reason': 'module_missing'}])

    ordered, done, path = [], set(), []

    def reject(owner, reason):
        registry.mark_failures([{'module': owner, 'reason': reason}])
        return False

    def visit(owner):
        if owner in done:
            return True
        if owner in registry.disabled() or owner not in specs:
            return False
        if owner in path:
            for member in path[path.index(owner):]:
                reject(member, 'dependency_cycle: ' + ' -> '.join(path[path.index(owner):] + [owner]))
            return False
        spec = specs[owner].spec
        path.append(owner)
        try:
            if owner in disabled:
                return reject(owner, 'disabled_modules')
            if spec.environment not in ('*', profile):
                return reject(owner, 'нужен профиль ' + spec.environment +
                              (' (живой редактор)' if spec.environment == 'editor' else ''))
            for key, actual in [('kernel_api', KERNEL_API), ('godot', godot)]:
                if not compatible(getattr(spec, key), actual):
                    return reject(owner, 'incompatible_%s: %s' % (key, getattr(spec, key)))
            unknown = set(spec.contributes_to) - targets
            if unknown:
                return reject(owner, 'unknown_contribution_target: ' + ', '.join(sorted(unknown)))
            for dependency in spec.requires:
                if not visit(dependency):
                    return reject(owner, 'dependency_unavailable: ' + dependency)
            ordered.append(specs[owner])
            done.add(owner)
            return True
        except Exception as exc:
            return reject(owner, '%s: %s' % (type(exc).__name__, exc))
        finally:
            path.pop()

    for owner in specs:
        visit(owner)
    return ordered
