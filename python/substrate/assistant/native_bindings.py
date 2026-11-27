"""T1 opt-in native tool closure; accepted K1's base fifty aliases stay inert."""
from importlib import import_module
import sys
from threading import RLock

BINDINGS = (
    ('arch_map', 'python.substrate.editing.arch_map'),
    ('gd_functions', 'python.substrate.code_intel.gd_functions'),
    ('log_reader', 'python.substrate.editor.references.log_reader'),
    ('node_refactor', 'python.substrate.editing.node_refactor'),
    ('split_gd', 'python.substrate.editing.split_gd'),
    ('split_refactor', 'python.substrate.editing.split_refactor'),
    ('function_card', 'python.substrate.code_intel.function_card'),
    ('gather_context', 'python.substrate.context.gather_context'),
)
_LOCK = RLock()

class NativeBindings:
    def register(self):
        # Deliberately method-local, never bootstrap/import-time activation.
        from python.substrate.llm import runtime_bindings
        with _LOCK:
            runtime_bindings.register()
            added = []
            try:
                for legacy, target in BINDINGS:
                    module = import_module(target)
                    if legacy in sys.modules and sys.modules[legacy] is not module:
                        raise RuntimeError('legacy alias already bound: ' + legacy)
                    if legacy not in sys.modules:
                        sys.modules[legacy] = module
                        added.append((legacy, module))
            except BaseException:
                for name, module in reversed(added):
                    if sys.modules.get(name) is module:
                        del sys.modules[name]
                raise
