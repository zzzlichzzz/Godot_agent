"""Synthetic context observations, with no Godot, filesystem or network effects."""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from importlib import import_module, util
from pathlib import Path
import socket
from types import SimpleNamespace
from unittest.mock import patch

from tests.py.llm.api_cases import ROOT, normalize

CONTEXT_CORPUS = ROOT / 'fixtures/corpus/context/runtime_reference'
CONTEXT_SOURCES = {
    'runtime_debug': ('godot_tools/runtime_debug.py', 'python.substrate.editor.references.runtime_debug'),
    'editor_context': ('server/editor_context.py', 'python.substrate.editor.references.editor_context'),
}


@contextmanager
def context_references(native=None):
    def denied(*args, **kwargs):
        raise PermissionError('context reference network denied')

    with ExitStack() as stack:
        for owner, attribute in ((socket, 'getaddrinfo'), (socket.socket, 'connect'),
                                 (socket.socket, 'connect_ex')):
            stack.enter_context(patch.object(owner, attribute, denied))
        modules = {}
        for name, (source, target) in CONTEXT_SOURCES.items():
            if native is None:
                module = import_module(target)
            else:
                spec = util.spec_from_file_location('capture_' + name, Path(native) / source)
                module = util.module_from_spec(spec)
                spec.loader.exec_module(module)
            modules[name] = module
        runtime = modules['runtime_debug']
        stack.enter_context(patch.object(runtime, 'time', SimpleNamespace(time=lambda: 1000.0)))
        stack.enter_context(patch.object(runtime, 'secrets', SimpleNamespace(token_hex=lambda n: 'a5' * n)))
        yield modules


def context_observation(case, sandbox, native=None):
    before = deepcopy(case)
    with context_references(native) as modules:
        try:
            module = modules[case['module']]
            if case.get('kind') == 'request':
                pending = module.create_request(case['action'], case['status'], 'synthetic-chat', 7,
                                                timeout_ms=case.get('timeout_ms', 3000))
                result = {'pending': pending, 'public': module.public_request(pending),
                          'runtime': module.runtime_request(pending)}
                if 'snapshot' in case:
                    clean = module.normalize_snapshot(case['snapshot'])
                    module.validate_snapshot_request(clean, pending)
                    result.update(snapshot=clean, report=module.format_snapshot(clean))
            elif case.get('kind') == 'attach_strip':
                attached = module.attach_to_prompt(case['prompt'], case['snapshot'],
                                                   max_chars=case.get('max_chars', 6000))
                result = {'attached': attached, 'stripped': module.user_prompt_without_context(attached[0])}
            else:
                result = getattr(module, case['function'])(*deepcopy(case.get('args', [])),
                                                         **deepcopy(case.get('kwargs', {})))
        except Exception as error:
            result = error
    assert case == before, 'observer mutated its synthetic input'
    return normalize(result, Path(sandbox))
