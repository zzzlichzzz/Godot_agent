"""runtime/bootstrap.py - композиционный корень (ADR-0003).

Единственное место, которое знает и модули, и адаптеры: создаёт адаптеры, кладёт
их в реестр портов и раздаёт модулям узкий `ModuleContext`. Всё, что здесь
появится сверх сборки (профили, health, teardown, воронка записи), приходит
вместе со своей механикой, а не «на будущее».
"""

import logging
import os
import sys
from copy import deepcopy

from python.kernel import result
from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from python.kernel.read_limits import PATHS_FILE_BYTES
from python.kernel.version import GODOT_BASELINE
from python.protocol.dispatch import Dispatcher
from python.protocol.registry import Registry
from python.runtime.context import ModuleContext
from python.runtime.module_loader import ROOT, discover
from python.substrate.editor.client import EditorClient
from python.substrate.fs.atomic_write import AtomicFileWriter
from python.substrate.fs.disk_fs import DiskFileSystem
from python.substrate.fs.read_only import ReadOnlyFileSystem
from python.substrate.fs.godot_io import GodotFiles
from python.substrate.fs.godot_writer import GodotWriter
from python.substrate.store.backups import FileBackups
from python.substrate.store.journal import FileJournal
from python.substrate.store.lock import FileLock
from python.substrate.store.api_cache_store import ApiCacheStore
from python.runtime.config import journal_dir
from python.runtime.composition import activation_order, install_feature_ports
from python.runtime.contract_inventory import owners

AGENT_DIR = str(ROOT)
PROFILES = ("editor", "headless", "cli", "test")


def resolve_project_root(project_root=None):
    """Корень проекта: явный аргумент → `GODOT_AGENT_PROJECT` → текущий каталог."""
    root = project_root or os.environ.get("GODOT_AGENT_PROJECT") or os.getcwd()
    return os.path.abspath(str(root))


def _plan(registry, settings, profile):
    disabled = settings.get('disabled_modules', os.environ.get('GODOT_AGENT_DISABLED_MODULES', ''))
    if isinstance(disabled, str):
        disabled = {s.strip() for s in disabled.split(',') if s.strip()}
    godot = settings.get('godot_version') or os.environ.get('GODOT_AGENT_GODOT_VERSION') or GODOT_BASELINE
    return activation_order(*discover(), owners(), registry, disabled or (), godot, profile)


def default_ports(project_root, profile, state_dir=None, *, loaded=None, registry=None):
    """Адаптеры профиля: файловая система, журнал и ленивый клиент моста.

    Порт `editor` присутствует во всех профилях (ADR-0007): клиент не
    соединяется, пока его не позовут, поэтому headless живёт без редактора.
    Отключение вклада идёт по профилю (`environment="editor"`), а не по порту.
    """
    from python.substrate.assistant.judge_read import JudgeRead
    from python.substrate.assistant.chat_gateway import ChatGateway
    from python.substrate.assistant.native_planner import NativePlanner
    from python.substrate.engine.structural_overlay import EngineOverlay
    state = os.path.dirname(journal_dir(profile, state_dir))
    files = DiskFileSystem if profile == 'test' else GodotFiles
    restricted = ReadOnlyFileSystem if profile == 'test' else GodotFiles
    # Internal consumers have their own scan budgets; the public text limit is smaller.
    project_inputs = files(project_root, max_bytes=sys.maxsize)
    ports = {"fs": files(project_root),
             "paths_fs": restricted(project_root, max_bytes=PATHS_FILE_BYTES),
            "api_cache": ApiCacheStore(project_root, state_dir=state, addon_dir=AGENT_DIR),
            "librarian": JudgeRead(project_root, state, AGENT_DIR),
            "chat_gateway": ChatGateway(project_root, state, AGENT_DIR),
            "native_planner": NativePlanner(project_root, state, AGENT_DIR,
                engine_overlay=EngineOverlay(project_root, state, AGENT_DIR)),
            "journal": FileJournal(journal_dir(profile, state_dir)),
             "writer": (AtomicFileWriter if profile == 'test' else GodotWriter)(project_root),
            "backups": FileBackups(os.path.join(state, "backup")),
            "lock": FileLock(state),
            "editor": EditorClient()}
    registry = Registry() if registry is None else registry
    from python.runtime.rename_bindings import complete
    ports['native_planner'].complete_bindings = complete
    if profile != 'test':
        from python.runtime.rename_integrity import HierarchyGuard
        from python.substrate.fs.project_view import project_view
        ports['fs'].check_rename = ports['native_planner'].check_rename = HierarchyGuard(project_inputs, AGENT_DIR)
        for name in ('librarian','native_planner'): ports[name].project_view = project_view
        ports['native_planner']._engine_overlay.files = project_inputs
        ports['api_cache'].files = ports['fs']
    candidates = _plan(registry, {}, profile) if loaded is None else loaded
    install_feature_ports(candidates, project_inputs, ports, registry)
    return ports


class Agent:
    """То, что видит канал: список инструментов и вызов с типизированным ответом."""

    def __init__(self, dispatcher, registry):
        self._dispatcher = dispatcher
        self._registry = registry

    def call(self, tool, args):
        try:
            value = self._dispatcher.call(tool, args if args is not None else {})
        except AppError as exc:
            return result.fail(exc)
        return result.ok(value)

    def tools(self):
        return [entry.spec.mcp() for entry in self._registry.entries()]

    def disabled(self):
        return self._registry.disabled()

    def conflicts(self):
        return self._registry.conflicts()


def build_agent(project_root=None, profile="headless", ports=None, settings=None,
                allow_addons=False, allow_self_edit=False, state_dir=None):
    """Собрать агента под профиль. Профиль выбирает адаптеры, не модули."""
    if profile not in PROFILES:
        raise ValueError("неизвестный профиль: %r (есть %s)" % (profile, PROFILES))
    root = resolve_project_root(project_root)
    policy = PathPolicy(root, allow_addons=allow_addons,
                        allow_self_edit=allow_self_edit, agent_dir=AGENT_DIR)
    settings = settings or {}
    registry = Registry()
    loaded = _plan(registry, settings, profile)
    if ports is None:
        ports = default_ports(root, profile, state_dir, loaded=loaded, registry=registry)
    contexts = []
    active = []
    for item in loaded:
        if item.spec.id in registry.disabled():
            continue
        dependency = next((d for d in item.spec.requires if d in registry.disabled()), None)
        if dependency:
            registry.mark_failures([{'module': item.spec.id, 'reason': 'dependency_unavailable: ' + dependency}])
            continue
        try:
            ctx = _register(registry, item, profile, ports, policy, settings)
            if ctx is not None and item.spec.id not in registry.disabled():
                contexts.append(ctx)
                active.append(item)
        except Exception as exc:
            registry.mark_failures([{'module': item.spec.id, 'reason': type(exc).__name__ + ': ' + str(exc)}])
    dispatcher = Dispatcher(registry, roots=(root,))
    for ctx in contexts:
        ctx.bind_caller(_caller(dispatcher))
    _recover(ports, active)
    return Agent(dispatcher, registry)


def _recover(ports, loaded):
    """Recovery WAL на старте: одна точка входа, вызов логируется (ADR-0005)."""
    if "journal" not in ports:
        return
    log = logging.getLogger("godot_agent.recovery")
    for item in loaded:
        recover = item.spec.entrypoints.get('recover')
        if recover is not None:
            try:
                log.info('recovery: %s', recover(ports, log))
            except Exception:
                log.exception('recovery упал: %s', item.spec.id)


def _caller(dispatcher):
    def call(tool, args):
        return dispatcher.call(tool, args if args is not None else {})
    return call


def _register(registry, item, profile, ports, policy, settings):
    missing = [name for name in item.spec.requires_ports if name not in ports]
    if missing:
        registry.mark_failures([{"module": item.spec.id,
                                 "provides_tools": item.spec.provides_tools,
                                 "reason": "нет портов: %s" % ", ".join(missing)}])
        return None
    if item.spec.environment not in ('*', profile):
        registry.mark_failures([{"module": item.spec.id,
                                 "provides_tools": item.spec.provides_tools,
                                 "reason": ('нужен профиль editor (живой редактор)' if item.spec.environment == 'editor'
                                            else 'нужен профиль ' + item.spec.environment)}])
        return None
    entrypoint = item.spec.entrypoints.get("call")
    internal = (getattr(item.spec, "internal_services", ()) or item.spec.entrypoints or
                getattr(item.spec, 'port_factories', None))
    if entrypoint is None and (item.spec.provides_tools or not (
            item.spec.contributes_to or internal)):
        registry.mark_failures([{"module": item.spec.id, 'provides_tools': item.spec.provides_tools,
                                 "reason": "нет entrypoints['call']"}])
        return None
    ctx = ModuleContext(profile=profile,
                        settings=(settings or {}).get(item.spec.id),
                        ports=ports, path_policy=policy,
                        logger=logging.getLogger("godot_agent." + item.spec.id),
                        registry=registry)
    handlers = ({tool.name: _handler(entrypoint, tool.name, ctx)
                 for tool in item.tools} if entrypoint is not None else {})
    registry.add_module(item.spec, item.tools, handlers, tuple(_bind(item, ctx)))
    return ctx


def _bind(item, ctx):
    """Связать вклады модуля с его контекстом: порт достаётся через `ctx`.

    Вклад без `bind` (обычная `ContextSection`) связывать нечего: он собирает
    данные сам. Секции `editor` нужен порт, и его даёт композиция (ADR-0003).
    """
    for contribution in item.contributions:
        if getattr(contribution, 'bind', None) is not None:
            # A bound editor section must not inherit another project's context.
            contribution = deepcopy(contribution)
            bind_context = contribution.bind
            bind_context(ctx)
        yield contribution


def _handler(entrypoint, tool_name, ctx):
    def call(args):
        return entrypoint(tool_name, args, ctx)
    return call
