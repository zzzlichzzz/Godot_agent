"""runtime/bootstrap.py - композиционный корень (ADR-0003).

Единственное место, которое знает и модули, и адаптеры: создаёт адаптеры, кладёт
их в реестр портов и раздаёт модулям узкий `ModuleContext`. Всё, что здесь
появится сверх сборки (профили, health, teardown, воронка записи), приходит
вместе со своей механикой, а не «на будущее».
"""

import logging
import os
import sys

from python.kernel import result
from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from python.protocol.dispatch import Dispatcher
from python.protocol.registry import Registry
from python.runtime.context import ModuleContext
from python.runtime.module_loader import ROOT, discover
from python.substrate.editor.client import EditorClient
from python.substrate.fs.atomic_write import AtomicFileWriter
from python.substrate.fs.disk_fs import DiskFileSystem
from python.substrate.fs.read_only import ReadOnlyFileSystem
from python.substrate.store.backups import FileBackups
from python.substrate.store.journal import FileJournal
from python.substrate.store.lock import FileLock
from python.substrate.store.api_cache_store import ApiCacheStore
from python.runtime.config import journal_dir

AGENT_DIR = str(ROOT)
PROFILES = ("editor", "headless", "cli", "test")


def resolve_project_root(project_root=None):
    """Корень проекта: явный аргумент → `GODOT_AGENT_PROJECT` → текущий каталог."""
    root = project_root or os.environ.get("GODOT_AGENT_PROJECT") or os.getcwd()
    return os.path.abspath(str(root))


def default_ports(project_root, profile, state_dir=None):
    """Адаптеры профиля: файловая система, журнал и ленивый клиент моста.

    Порт `editor` присутствует во всех профилях (ADR-0007): клиент не
    соединяется, пока его не позовут, поэтому headless живёт без редактора.
    Отключение вклада идёт по профилю (`environment="editor"`), а не по порту.
    """
    from python.modules.verification.gd_lint import lint_gdscript
    from python.modules.scene_model.node_rename import preview_diff
    from python.modules.editing.paths_preview.tools import MAX_FILE_BYTES
    from python.modules.editing.resource_ops.ports import ResourceRead
    from python.modules.project_text.shared.file_index import ProjectTextFileSystem
    from python.substrate.assistant.judge_read import JudgeRead
    from python.substrate.assistant.chat_gateway import ChatGateway
    from python.substrate.assistant.native_planner import NativePlanner
    from python.substrate.engine.structural_overlay import EngineOverlay
    state = os.path.dirname(journal_dir(profile, state_dir))
    return {"gd_lint": lint_gdscript,
            "node_diff": preview_diff,
            "fs": DiskFileSystem(project_root),
            "paths_fs": ReadOnlyFileSystem(project_root, max_bytes=MAX_FILE_BYTES),
            "api_cache": ApiCacheStore(project_root, state_dir=state, addon_dir=AGENT_DIR),
            "librarian": JudgeRead(project_root, state, AGENT_DIR),
            "chat_gateway": ChatGateway(project_root, state, AGENT_DIR),
            "native_planner": NativePlanner(project_root, state, AGENT_DIR,
                engine_overlay=EngineOverlay(project_root, state, AGENT_DIR)),
            "journal": FileJournal(journal_dir(profile, state_dir)),
            "writer": AtomicFileWriter(project_root),
            "backups": FileBackups(os.path.join(state, "backup")),
            "lock": FileLock(state),
            "editor": EditorClient(),
            "resource_read": ResourceRead(DiskFileSystem(project_root, max_bytes=sys.maxsize)),
            "project_text_fs": ProjectTextFileSystem(DiskFileSystem(project_root, max_bytes=sys.maxsize))}


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
    loaded, failed = discover()
    if ports is None:
        ports = default_ports(root, profile, state_dir)
    registry = Registry()
    contexts = []
    for item in loaded:
        ctx = _register(registry, item, profile, ports, policy, settings)
        if ctx is not None:
            contexts.append(ctx)
    registry.mark_failures(failed)
    dispatcher = Dispatcher(registry, roots=(root,))
    for ctx in contexts:
        ctx.bind_caller(_caller(dispatcher))
    _recover(ports)
    return Agent(dispatcher, registry)


def _recover(ports):
    """Recovery WAL на старте: одна точка входа, вызов логируется (ADR-0005)."""
    if "journal" not in ports:
        return
    log = logging.getLogger("godot_agent.recovery")
    try:
        from python.modules.editing.rollback import recover
        log.info("recovery: %s", recover(ports, log))
    except Exception:  # recovery не должен мешать старту, но и молчать нельзя
        log.exception("recovery упал")


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
    if item.spec.environment == "editor" and profile != "editor":
        registry.mark_failures([{"module": item.spec.id,
                                 "reason": "нужен профиль editor (живой редактор)"}])
        return None
    entrypoint = item.spec.entrypoints.get("call")
    internal = (getattr(item.spec, "internal_services", ()) or item.spec.entrypoints)
    if entrypoint is None and (item.spec.provides_tools or not (
            item.spec.contributes_to or internal)):
        registry.mark_failures([{"module": item.spec.id, "reason": "нет entrypoints['call']"}])
        return None
    ctx = ModuleContext(profile=profile,
                        settings=(settings or {}).get(item.spec.id),
                        ports=ports, path_policy=policy,
                        logger=logging.getLogger("godot_agent." + item.spec.id),
                        registry=registry)
    handlers = ({tool.name: _handler(entrypoint, tool.name, ctx)
                 for tool in item.tools} if entrypoint is not None else {})
    registry.add_module(item.spec, item.tools, handlers, item.contributions)
    _bind(item, ctx)
    return ctx


def _bind(item, ctx):
    """Связать вклады модуля с его контекстом: порт достаётся через `ctx`.

    Вклад без `bind` (обычная `ContextSection`) связывать нечего: он собирает
    данные сам. Секции `editor` нужен порт, и его даёт композиция (ADR-0003).
    """
    for contribution in item.contributions:
        binder = getattr(contribution, "bind", None)
        if binder is not None:
            binder(ctx)


def _handler(entrypoint, tool_name, ctx):
    def call(args):
        return entrypoint(tool_name, args, ctx)
    return call
