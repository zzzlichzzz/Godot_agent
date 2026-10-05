# -*- coding: utf-8 -*-
"""MCP-сервер Godot Agent — тонкая обёртка над agent_bridge.py.

Сервер НЕ дублирует логику доступа: каждый tool собирает CLI-аргументы и
вызывает agent_bridge.main(), а тот решает всё сам (capability-policy,
коды возврата, атомарный write с plan_id). Дублировать проверки доступа
здесь означало бы со временем разойтись с мостом — единственным источником
истины.

ПРОФИЛИ. Режим доступа выбирается ОДИН раз при старте сервера и передаётся
мосту флагом --access. В tools параметра access нет вообще: модель не может
переключить профиль, потому что менять нечего — сервер уже собран с ним.

  user       -> --access addon      : обычная работа над Godot-проектом;
                                     исходник агента и его .py не видны,
                                     инструменты записи не публикуются.
  agent-dev  -> --access agent-dev  : саморазвитие агента; дополнительно
                                     видны .py исходника агента и write.
"""

import io
import json
import os
import sys
import contextlib
import tempfile

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import agent_bridge  # noqa: E402

try:
    from mcp.server.mcpserver import MCPServer
    from mcp.types import CallToolResult, TextContent
except ImportError as exc:  # pragma: no cover - зависит от окружения
    raise SystemExit(
        "godot_agent_mcp requires the 'mcp' package (pip install mcp): %s" % exc)

# CallToolResult нужен в области видимости МОДУЛЯ: его используют аннотации
# возвращаемых типов всех tools, а они вычисляются при их регистрации.

# Профиль -> режим доступа моста. Профиль задан пользователем при запуске.
PROFILES = {
    "user": "addon",
    "agent-dev": "agent-dev",
}

# Коды моста: 2 — «запрошенного нет» (это ОТВЕТ, а не сбой), 3/4 — ошибка.
_ERROR_CODES = (agent_bridge.RC_ERROR, agent_bridge.RC_USAGE)

# Пишем во временный файл только потому, что мост принимает --request FILE.
# Модель отдаёт payload, а не путь на своём диске.
_REQUEST_PREFIX = "godot_agent_mcp_request"


class _Profile(object):
    """Зафиксированный настройками запуска профиль сервера."""

    def __init__(self, name, root, udd):
        if name not in PROFILES:
            raise SystemExit(
                "unknown profile %r; expected one of: %s"
                % (name, ", ".join(sorted(PROFILES))))
        self.name = name
        self.access = PROFILES[name]
        self.root = root
        self.udd = udd

    @property
    def can_write(self):
        """Запись публикуется только в developer mode."""
        return self.name == "agent-dev"

    def base_argv(self):
        argv = ["--access", self.access]
        if self.root:
            argv += ["--root", self.root]
        if self.udd:
            argv += ["--udd", self.udd]
        return argv


# --- вызов моста -------------------------------------------------------

def _run_bridge(profile, argv):
    """Вызывает мост в процессе: (код возврата, stdout).

    Мост пишет данные в stdout и одну статусную строку в stderr, поэтому
    потоки разделяются, а не подменяются целиком.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = agent_bridge.main(list(argv))
    return int(code), out.getvalue().strip()


def _tool_result(code, text):
    """Переводит код моста в результат MCP.

    Код 2 означает «запрошенного не существует» — модель должна увидеть это
    как честный ОТВЕТ и не повторять вызов. Ошибкой (isError) он не
    помечается: иначе клиент покажет пользователю сбой там, где всё штатно.
    """
    body = text or "(no output)"
    return CallToolResult(
        content=[TextContent(type="text", text=body)],
        is_error=code in _ERROR_CODES)


def _request_file(payload):
    """Пишет payload во временный файл. Возвращает путь и очистку."""
    if isinstance(payload, (dict, list)):
        blob = json.dumps(payload, ensure_ascii=False)
    else:
        blob = str(payload)
    handle, path = tempfile.mkstemp(prefix=_REQUEST_PREFIX, suffix=".json")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(blob)

    def cleanup():
        try:
            os.unlink(path)
        except OSError:
            pass
    return path, cleanup

# --- сборка сервера ---------------------------------------------------

_USER_INSTRUCTIONS = (
    "Godot Agent MCP: ответы по проекту из тех же источников, что и встроенный "
    "агент. Перед использованием любого класса Godot сверяй сигнатуры через api: "
    "твоя память о Godot API может устареть, а мост отвечает из кэша этого "
    "движка. Код 2 означает «запрошенного не существует» — это ответ, не сбой."
)

_DEV_INSTRUCTIONS = (
    "Godot Agent MCP (developer mode): дополнительно виден собственный "
    "исходник агента, включая .py, и доступны инструменты записи. write "
    "двухфазный: сначала write_preview возвращает plan_id и НЕ меняет файлы, "
    "затем write_apply с тем же plan_id. Переименование файлов применяй через "
    "панель агента: paths_preview только читает."
)


def build_server(profile="user", root=None, udd=None, name=None):
    """Собирает MCP-сервер с зафиксированным профилем доступа."""
    config = _Profile(profile, root, udd)
    server = MCPServer(
        name=name or ("godot-agent-%s" % config.name),
        instructions=(_DEV_INSTRUCTIONS if config.can_write
                      else _USER_INSTRUCTIONS))

    def call(argv, cleanup=None):
        code, text = _run_bridge(config, config.base_argv() + list(argv))
        return _tool_result(code, text)

    def call_request(argv_prefix, payload):
        path, cleanup = _request_file(payload)
        try:
            return call(list(argv_prefix) + ["--request", path])
        finally:
            cleanup()

    # --- чтение и справочные команды (оба профиля) ----------------------

    @server.tool(description="Жив ли сервер плагина в редакторе и какое состояние "
                            "кэша Godot API.")
    def status() -> CallToolResult:
        return call(["status"])

    @server.tool(description="Версия Godot проекта и источник кэша API. Начинай "
                            "с неё: она задаёт версию всех сигнатур ниже.")
    def engine() -> CallToolResult:
        return call(["engine"])

    @server.tool(description="Методы, свойства и сигнатуры класса Godot по ВСЕЙ "
                            "цепочке наследования, с полными сигнатурами "
                            "вызовов. Сверяй здесь перед любым использованием "
                            "класса — память о Godot API ненадёжна.")
    def api(class_name: str) -> CallToolResult:
        return call(["api", class_name])

    @server.tool(description="Компактная справка о проекте от Библиотекаря: карта "
                            "кода, фрагменты, вызовы.")
    def ask(query: str) -> CallToolResult:
        return call(["ask", query])

    @server.tool(description="Поиск подстроки по проекту. Возвращает путь, номер "
                            "строки и фрагмент.")
    def search(query: str, max_results: int = 30) -> CallToolResult:
        return call(["search", "--max", str(int(max_results)), query])

    @server.tool(description="Прочитать один файл проекта по адресу res://. Путь "
                            "проверяется политикой доступа.")
    def read(path: str, max_chars: int = 50000) -> CallToolResult:
        return call(["read", "--max-chars", str(int(max_chars)), path])

    @server.tool(description="Структура сцены .tscn: дерево узлов с типами, "
                            "прикреплённые скрипты, инстансы и связи сигналов. "
                            "Операция только читает, подтверждения не требует.")
    def scene(path: str) -> CallToolResult:
        return call(["scene", path])

    @server.tool(description="Функции .gd-файла: без names — список всех "
                            "объявленных имён; с names — тела запрошенных "
                            "функций дословно. Операция только читает, "
                            "подтверждения не требует.")
    def functions(path: str, names: list = []) -> CallToolResult:
        argv = ["functions"]
        if names:
            argv += ["--names", ",".join(str(n) for n in names)]
        return call(argv + [path])

    @server.tool(description="Где используется символ: файл:строка:колонка, тип "
                            "связи и уверенность (proven/probable/dynamic). "
                            "Операция только читает, подтверждения не требует.")
    def usages(declaration: str, name: str, kind: str = "function",
               new_name: str = "") -> CallToolResult:
        argv = ["usages", "--declaration", declaration, "--name", name,
                "--kind", kind]
        if new_name:
            argv += ["--new-name", new_name]
        return call(argv)

    @server.tool(description="Предпросмотр переименования символа: что и где "
                            "изменится, какие места недоказуемы (риски). "
                            "Операция только читает, подтверждения не требует; "
                            "применение — write_preview (rename_symbol) или "
                            "панель агента.")
    def analyze_rename(kind: str, declaration: str, old_name: str,
                       new_name: str) -> CallToolResult:
        return call(["analyze_rename", "--kind", kind, "--declaration",
                     declaration, "--old-name", old_name,
                     "--new-name", new_name])

    @server.tool(description="Тот же ограниченный пакет контекста, который "
                            "собирает встроенный агент: символы, зависимости, "
                            "diagnostics, project settings. Не пишет ничего.")
    def context(request: dict) -> CallToolResult:
        return call_request(["context"], request)

    @server.tool(description="Детерминированная проверка файлов: gd_lint и "
                            "gd_api_check для .gd, tscn_lint для .tscn, синтаксис "
                            "для .py/.json/.cfg, плюс настоящий headless Godot. "
                            "Ничего не меняет.")
    def check(paths: list) -> CallToolResult:
        return call(["check"] + [str(p) for p in paths])

    @server.tool(description="Локальный судья одного действия модели по переданному "
                            "ответу. Не пишет и не вызывает сеть.")
    def check_action(request: dict) -> CallToolResult:
        return call_request(["check_action"], request)

    @server.tool(description="Предпросмотр последствий переименования или "
                            "перемещения файла. Только чтение; применение — "
                            "кнопкой в панели агента.")
    def paths_preview(old_path: str, new_path: str) -> CallToolResult:
        return call(["paths", "preview", old_path, new_path])

# --- запись: публикуется ТОЛЬКО в developer mode --------------------
    # Инструменты не просто отказывают в профиле user — их нет в списке.
    # Скрытый инструмент модель не «пробует вызвать», а значит не тратит
    # ход и не получает отказ там, где писать и не предполагалось.

    if config.can_write:

        @server.tool(description="Фаза 1 записи: готовит изменение и возвращает "
                                "plan_id с diff. ФАЙЛЫ НЕ МЕНЯЮТСЯ. Дальше "
                                "вызови write_apply с этим plan_id.")
        def write_preview(request: dict) -> CallToolResult:
            return call_request(["write", "preview"], request)

        @server.tool(description="Фаза 2 записи: применяет РОВНО тот план, который "
                                "был проверен в write_preview, и создаёт запись "
                                "журнала. Без plan_id ничего не применится.")
        def write_apply(plan_id: str, request: dict) -> CallToolResult:
            path, cleanup = _request_file(request)
            try:
                return call(["write", "apply", "--request", path,
                             "--plan-id", str(plan_id)])
            finally:
                cleanup()

        @server.tool(description="Откат конкретной записи журнала, сделанной этим "
                                "мостом.")
        def write_rollback(entry_id: str, force: bool = False) -> CallToolResult:
            argv = ["write", "rollback", "--entry-id", str(entry_id)]
            if force:
                argv.append("--force")
            return call(argv)

        @server.tool(description="Предпросмотр переименования узла сцены: "
                                "правит .tscn и прикреплённые скрипты ($Node, "
                                "%Unique, get_node(), parent, connection). "
                                "Только чтение: файлы не меняются до write_apply.")
        def node_rename_preview(scene: str, node: str,
                                new_name: str) -> CallToolResult:
            return call_request(["write", "preview"],
                                {"action": "rename_node", "scene": scene,
                                 "node": node, "new_name": new_name})

        @server.tool(description="Предпросмотр переноса узла сцены к другому "
                                "родителю: пересчитывает пути в .tscn и "
                                "прикреплённых скриптах. Только чтение; "
                                "применение — через write_apply с plan_id.")
        def node_reparent_preview(scene: str, node: str,
                                  new_parent: str) -> CallToolResult:
            return call_request(["write", "preview"],
                                {"action": "reparent_node", "scene": scene,
                                 "node": node, "new_parent": new_parent})

        @server.tool(description="Предпросмотр удаления узла и его поддерева из "
                                "сцены: убирает узел, связи и треки; ссылки в "
                                "скриптах не правятся, а попадают в "
                                "предупреждения. Только чтение; применение — "
                                "через write_apply с plan_id.")
        def node_delete_preview(scene: str, node: str) -> CallToolResult:
            return call_request(["write", "preview"],
                                {"action": "delete_node", "scene": scene,
                                 "node": node})

    return server


# Созданный сервер хранится на уровне модуля, чтобы тесты и main() читали
# один и тот же экземпляр. Импорт модуля его НЕ создаёт.
_SERVER = None


def main(argv=None):
    """Точка входа: собирает сервер по --profile и гоняет stdio-транспорт."""
    global _SERVER
    args = list(sys.argv[1:] if argv is None else argv)
    profile = "user"
    root = None
    udd = None
    index = 0
    while index < len(args):
        option = args[index]
        if option in ("--profile", "--root", "--udd"):
            if index + 1 >= len(args):
                raise SystemExit("%s requires a value" % option)
            key = option[2:]
            if key == "profile":
                profile = args[index + 1]
            elif key == "root":
                root = args[index + 1]
            else:
                udd = args[index + 1]
            index += 2
            continue
        if option in ("--help", "-h"):
            print("usage: godot_agent_mcp.py [--profile user|agent-dev] "
                  "[--root PATH] [--udd PATH]")
            return 0
        raise SystemExit("unknown option %s" % option)
    _SERVER = build_server(profile=profile, root=root, udd=udd)
    _SERVER.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
