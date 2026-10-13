# -*- coding: utf-8 -*-
"""Тесты MCP-сервера Godot Agent (обёртка над agent_bridge.py).

Контракт, который здесь закрепляется:
  * сервер — тонкая обёртка: проверки доступа не дублируются, всё решает
    agent_bridge и его capability-policy;
  * ПРОФИЛЬ задаёт --access на старте сервера и моделью НЕ передаётся:
    в аргументах tools параметров access/addon_dir/root нет вообще;
  * профиль user не даёт ни доступа к исходнику агента, ни .py в поиске;
  * код возврата моста переводится в isError: 2 — «запрошенного нет»
    (это ОТВЕТ, не сбой), 3/4 — ошибка;
  * inline-JSON запроса пишется во временный файл и удаляется.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import agent_bridge  # noqa: E402
import godot_agent_mcp  # noqa: E402


class McpServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mcp_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = str(Path(self.temp.name))
        self.store = str(Path(self.temp.name, "store"))
        self.agent_dir = Path(self.root, "addons", "Godot_agent", "godot_agent")
        self.external_addon = Path(self.root, "addons", "demo")
        self.agent_dir.mkdir(parents=True)
        self.external_addon.mkdir(parents=True)
        (self.agent_dir / "agent.gd").write_text(
            "extends Node\nconst TOKEN = \"AGENT_ONLY_TOKEN\"\n", encoding="utf-8")
        (self.external_addon / "tool.gd").write_text(
            "extends Node\nconst TOKEN = \"ADDON_ONLY_TOKEN\"\n", encoding="utf-8")
        Path(self.agent_dir, "python").mkdir()
        Path(self.agent_dir, "python", "core.py").write_text(
            "SECRET_PY_TOKEN = 1\n", encoding="utf-8")
        Path(self.external_addon, "helper.py").write_text(
            "EXT_PY_TOKEN = 1\n", encoding="utf-8")
        Path(self.root, "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/name="MCP Test Proj"\n',
            encoding="utf-8")
        Path(self.root, "src").mkdir()
        Path(self.root, "src", "player.gd").write_text(
            "extends Node\nfunc take_damage(amount):\n\tpass\n", encoding="utf-8")
        import gd_api_cache
        gd_api_cache.save_cache(self.root, {
            "Object": {"inherits": "", "methods": {"free": [0, 0]},
                       "properties": [], "signals": []},
            "Node": {"inherits": "Object", "methods": {"add_child": [1, 1]},
                     "properties": ["name"], "signals": []},
        }, godot_version="4.6.3")
        import history_manager
        previous = history_manager._STORAGE_OVERRIDE
        self.addCleanup(setattr, history_manager, "_STORAGE_OVERRIDE", previous)

    def make_server(self, profile="user"):
        return godot_agent_mcp.build_server(
            profile=profile, root=self.root, udd=self.store)

    def call(self, server, tool, **arguments):
        """Вызов tool так, как это делает клиент MCP: call_tool — корутина."""
        import asyncio
        result = asyncio.run(server.call_tool(tool, arguments))
        self.assertFalse(asyncio.iscoroutine(result),
                         "call_tool must be awaited")
        return result

    @staticmethod
    def text_of(result):
        return "".join(getattr(part, "text", "") or ""
                       for part in getattr(result, "content", []) or [])

# --- профили -----------------------------------------------------------

    def test_unknown_profile_fails_closed(self):
        with self.assertRaises(SystemExit) as ctx:
            godot_agent_mcp.build_server(
                profile="superuser", root=self.root, udd=self.store)
        self.assertIn("profile", str(ctx.exception).lower())

    def test_profile_maps_to_bridge_access_mode(self):
        self.assertEqual(godot_agent_mcp.PROFILES["user"], "addon")
        self.assertEqual(godot_agent_mcp.PROFILES["agent-dev"], "agent-dev")

    def test_no_tool_accepts_access_override(self):
        """Граница доверия: модель не может выбрать режим доступа."""
        import asyncio
        for profile in ("user", "agent-dev"):
            server = self.make_server(profile)
            tools = asyncio.run(server.list_tools())
            self.assertTrue(tools)
            for tool in tools:
                properties = (getattr(tool, "inputSchema", None)
                              or getattr(tool, "input_schema", {}) or {})
                names = set((properties.get("properties") or {}).keys())
                self.assertNotIn("access", names,
                                 "%s leaks access in %s" % (profile, tool.name))
                self.assertNotIn("addon_dir", names,
                                 "%s leaks addon_dir in %s" % (profile, tool.name))
                self.assertNotIn("root", names,
                                 "%s leaks root in %s" % (profile, tool.name))

    def test_access_override_argument_is_ignored(self):
        """Даже если модель подсунет 'access', профиль остаётся прежним."""
        server = self.make_server("user")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            result = self.call(server, "search", query="AGENT_ONLY_TOKEN",
                               access="agent-dev")
        self.assertIn("no matches", self.text_of(result))

# --- изоляция профилей ------------------------------------------------

    def test_user_profile_never_sees_agent_source(self):
        server = self.make_server("user")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            self.assertIn("no matches",
                          self.text_of(self.call(server, "search",
                                                 query="AGENT_ONLY_TOKEN")))
            self.assertIn("no matches",
                          self.text_of(self.call(server, "search",
                                                 query="SECRET_PY_TOKEN")))

    def test_user_profile_reads_external_addon_but_not_agent(self):
        server = self.make_server("user")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            result = self.call(server, "search", query="ADDON_ONLY_TOKEN")
            self.assertIn("addons/demo/tool.gd", self.text_of(result))
            result = self.call(
                server, "read",
                path="res://addons/Godot_agent/godot_agent/agent.gd")
            self.assertNotIn("AGENT_ONLY_TOKEN", self.text_of(result))

    def test_user_profile_never_reads_external_addon_python(self):
        server = self.make_server("user")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            result = self.call(server, "search", query="EXT_PY_TOKEN")
            self.assertIn("no matches", self.text_of(result))

    def test_agent_dev_profile_sees_own_python_source(self):
        server = self.make_server("agent-dev")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            result = self.call(server, "search", query="SECRET_PY_TOKEN")
            self.assertIn("python/core.py", self.text_of(result))

    def test_agent_dev_profile_skips_external_addon_python(self):
        server = self.make_server("agent-dev")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            result = self.call(server, "search", query="EXT_PY_TOKEN")
            self.assertIn("no matches", self.text_of(result))

    def test_agent_dev_profile_reads_agent_source(self):
        server = self.make_server("agent-dev")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            result = self.call(
                server, "read",
                path="res://addons/Godot_agent/godot_agent/agent.gd")
            self.assertIn("AGENT_ONLY_TOKEN", self.text_of(result))

# --- коды возврата -----------------------------------------------------

    def test_not_found_is_an_answer_not_an_error(self):
        server = self.make_server("user")
        result = self.call(server, "search", query="zzz_absent_zzz")
        self.assertFalse(getattr(result, "is_error", False), self.text_of(result))
        self.assertIn("no matches", self.text_of(result))

    def test_usage_error_is_reported_as_error(self):
        server = self.make_server("user")
        # Пустой запрос — настоящий usage-код моста (4), а не «не найдено».
        result = self.call(server, "search", query="")
        self.assertTrue(getattr(result, "is_error", False), self.text_of(result))
        self.assertNotIn("Traceback", self.text_of(result))

    def test_unknown_class_is_an_answer_not_an_error(self):
        """Класс вне кэша — честный ответ (код 2), а не сбой инструмента."""
        server = self.make_server("user")
        result = self.call(server, "api", class_name="NoSuchClass123")
        self.assertFalse(getattr(result, "is_error", False), self.text_of(result))
        self.assertIn("NOT IN CACHE", self.text_of(result))

    def test_engine_and_api_work_through_mcp(self):
        server = self.make_server("user")
        self.assertIn("4.6.3", self.text_of(self.call(server, "engine")))
        self.assertIn("add_child",
                      self.text_of(self.call(server, "api", class_name="Node")))

    def test_huge_tool_output_is_clipped_with_honest_marker(self):
        """Предохранитель размера: один ответ не может раздуть контекст.

        Живой прогон n8n (exec 98): ответ поиска в 2.1 МБ (minified-кэш API
        одной строкой) остался в истории агента и пересылался на каждом шаге —
        ~700к токенов на шаг. Предел и пометка — как у сервера «рук» (:8010).
        """
        Path(self.root, "src", "big.gd").write_text(
            "# " + "c" * 120000, encoding="utf-8")
        server = self.make_server()
        text = self.text_of(self.call(
            server, "read", path="res://src/big.gd", max_chars=200000))
        self.assertIn("обрезано: всего", text)
        self.assertLessEqual(len(text), godot_agent_mcp.MAX_TEXT)
        # Хвост сохранён: пометка идёт ПЕРЕД хвостом, а не после.
        self.assertTrue(text.endswith("c" * 100))
        # Короткий ответ не трогается: ни обрезки, ни пометки.
        short = self.text_of(self.call(
            server, "read", path="res://src/player.gd"))
        self.assertNotIn("обрезано", short)

    def test_clip_never_exceeds_limit(self):
        """Граница _clip: пометка входит в бюджет, итог ≤ MAX_TEXT.

        Прогон 102: _clip возвращал 60 041 при MAX_TEXT=60 000, а тест
        закреплял это допуском +100. Теперь лимит соблюдается буквально.
        """
        limit = godot_agent_mcp.MAX_TEXT
        text = godot_agent_mcp._clip("x" * (limit + 1000))
        self.assertLessEqual(len(text), limit)
        self.assertIn("обрезано: всего %d символов" % (limit + 1000), text)
        self.assertLessEqual(
            len(godot_agent_mcp._clip("y" * (limit * 40))), limit)

    def test_search_max_results_is_capped(self):
        """Перебор max_results не доходит до моста: кэп MAX_MATCHES."""
        server = self.make_server("user")
        seen = {}

        def fake_main(argv):
            seen["argv"] = list(argv)
            print("no matches")
            return 0

        with patch.object(godot_agent_mcp.agent_bridge, "main", fake_main):
            self.call(server, "search", query="player",
                      max_results=10 ** 6)
        argv = seen["argv"]
        self.assertEqual(argv[argv.index("--max") + 1],
                         str(godot_agent_mcp.MAX_MATCHES))

    def test_list_inputs_are_limited(self):
        """functions.names и check.paths сверх предела — usage-ответ."""
        server = self.make_server("user")
        names = ["n%d" % i for i in range(godot_agent_mcp.MAX_NAMES + 1)]
        result = self.call(server, "functions", path="res://src/player.gd",
                           names=names)
        self.assertTrue(getattr(result, "is_error", False), self.text_of(result))
        self.assertIn("предел", self.text_of(result))
        result = self.call(
            server, "check",
            paths=["res://src/player.gd"] * (godot_agent_mcp.MAX_PATHS + 1))
        self.assertTrue(getattr(result, "is_error", False), self.text_of(result))
        self.assertIn("предел", self.text_of(result))

    def test_text_arguments_are_limited(self):
        """Длинные строки аргументов не уходят в argv моста."""
        server = self.make_server("user")
        long = "x" * (godot_agent_mcp.MAX_ARG_TEXT + 1)
        result = self.call(server, "search", query=long)
        self.assertTrue(getattr(result, "is_error", False), self.text_of(result))
        self.assertIn("query", self.text_of(result))
        result = self.call(server, "analyze_rename", kind="function",
                           declaration="res://src/player.gd",
                           old_name="take_damage", new_name=long)
        self.assertTrue(getattr(result, "is_error", False), self.text_of(result))
        self.assertIn("new_name", self.text_of(result))

    def test_every_tool_response_stays_within_max_text(self):
        """Перебор всех tools профиля user: ответ ≤ MAX_TEXT, structured пуст.

        Живой прогон 98: один ответ поиска в 2.1 МБ раздувал историю агента
        на каждом шаге. Рубеж — общий _clip; здесь он проверяется на ВСЕХ
        опубликованных инструментах, включая структурные поля результата.
        """
        import asyncio

        def fake_main(argv):
            print("X" * 200000)
            return 0

        arguments = {
            "status": {},
            "engine": {},
            "api": {"class_name": "Node"},
            "ask": {"query": "player"},
            "search": {"query": "player"},
            "read": {"path": "res://src/player.gd"},
            "scene": {"path": "res://src/player.gd"},
            "functions": {"path": "res://src/player.gd"},
            "usages": {"declaration": "res://src/player.gd",
                       "name": "take_damage"},
            "analyze_rename": {"kind": "function",
                               "declaration": "res://src/player.gd",
                               "old_name": "take_damage", "new_name": "hit"},
            "context": {"request": {"text": "player"}},
            "check": {"paths": ["res://src/player.gd"]},
            "check_action": {"request": {"text": "player"}},
            "paths_preview": {"old_path": "res://src/player.gd",
                              "new_path": "res://src/player_hit.gd"},
        }
        server = self.make_server("user")
        published = {tool.name for tool in asyncio.run(server.list_tools())}
        self.assertTrue(set(arguments) <= published, published)
        with patch.object(godot_agent_mcp.agent_bridge, "main", fake_main):
            for tool_name, kwargs in arguments.items():
                result = self.call(server, tool_name, **kwargs)
                text = self.text_of(result)
                self.assertLessEqual(
                    len(text), godot_agent_mcp.MAX_TEXT,
                    "%s: %d символов" % (tool_name, len(text)))
                self.assertIn("обрезано: всего", text)
                self.assertIsNone(
                    getattr(result, "structured_content", None))

    def test_ask_and_context_and_check_work_through_mcp(self):
        server = self.make_server("user")
        self.assertTrue(self.text_of(self.call(server, "ask", query="player")))
        self.assertTrue(self.text_of(
            self.call(server, "context", request={"text": "player"})))
        self.assertTrue(self.text_of(self.call(
            server, "check", paths=["res://src/player.gd"])))

# --- inline-запросы ----------------------------------------------------

    def test_inline_request_leaves_no_temp_file(self):
        server = self.make_server("user")
        marker = tempfile.gettempdir()
        before = set(os.listdir(marker))
        self.call(server, "check_action", request={"text": "текст"})
        leaked = {n for n in (set(os.listdir(marker)) - before)
                  if n.startswith("godot_agent_mcp_request")}
        self.assertFalse(leaked, "temp request file leaked: %s" % leaked)

    def test_inline_request_accepts_json_string(self):
        server = self.make_server("user")
        result = self.call(server, "check_action",
                           request=json.dumps({"text": "текст"}))
        self.assertNotIn("Traceback", self.text_of(result))

# --- write и регистрация ------------------------------------------------

    def test_write_preview_does_not_touch_source(self):
        server = self.make_server("agent-dev")
        target = self.agent_dir / "python" / "made_by_mcp.txt"
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            preview = self.call(server, "write_preview", request={
                "action": "create_file",
                "path": "res://addons/Godot_agent/godot_agent/python/made_by_mcp.txt",
                "content": "made",
            })
        self.assertIn("plan_id", self.text_of(preview))
        self.assertFalse(target.exists(), "preview must not write")

    def test_scene_tool_reads_structure_in_user_profile(self):
        src = Path(self.root, "src")
        src.mkdir(exist_ok=True)
        (src / "scene.tscn").write_text(
            '[gd_scene format=3]\n\n'
            '[node name="Root" type="Node"]\n\n'
            '[node name="Child" type="Node" parent="."]\n',
            encoding="utf-8")
        server = self.make_server("user")
        result = self.call(server, "scene", path="res://src/scene.tscn")
        text = self.text_of(result)
        self.assertIn("Root", text)
        self.assertIn("Child", text)

    def test_node_rename_preview_via_mcp_reports_plan(self):
        src = Path(self.root, "src")
        src.mkdir(exist_ok=True)
        scene = src / "scene.tscn"
        scene.write_text(
            '[gd_scene format=3]\n\n'
            '[node name="Root" type="Node"]\n\n'
            '[node name="Child" type="Node" parent="."]\n',
            encoding="utf-8")
        server = self.make_server("agent-dev")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            result = self.call(server, "node_rename_preview",
                               scene="res://src/scene.tscn", node="Child",
                               new_name="Renamed")
        text = self.text_of(result)
        self.assertIn("plan_id", text)
        self.assertIn('name="Child"', scene.read_text(encoding="utf-8"))

    def test_split_scan_via_mcp_reports_refs(self):
        donor = self.agent_dir / "python" / "probe_split.py"
        donor.write_text("def mcp_probe_one():\n    return 1\n",
                         encoding="utf-8")
        server = self.make_server("agent-dev")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            result = self.call(server, "split_scan", file=(
                "res://addons/Godot_agent/godot_agent/python/probe_split.py"))
        text = self.text_of(result)
        self.assertIn("refs: import=", text)
        self.assertEqual(donor.read_text(encoding="utf-8"),
                         "def mcp_probe_one():\n    return 1\n")

    def test_write_is_not_reachable_in_user_profile(self):
        """Инструмента записи в профиле user нет — вызов обязан честно упасть."""
        import asyncio
        from mcp.server.mcpserver.exceptions import ToolError
        server = self.make_server("user")
        with self.assertRaises(ToolError):
            asyncio.run(server.call_tool("write_preview", {"request": {
                "action": "create_file",
                "path": "res://addons/Godot_agent/godot_agent/python/nope.txt",
                "content": "x",
            }}))
        self.assertFalse((self.agent_dir / "python" / "nope.txt").exists())

    def test_tool_names_are_discoverable(self):
        import asyncio
        server = self.make_server("agent-dev")
        names = {tool.name for tool in asyncio.run(server.list_tools())}
        for expected in ("engine", "api", "ask", "search", "read",
                         "scene", "functions", "usages", "analyze_rename",
                         "context", "check", "check_action",
                         "write_preview", "write_apply", "write_rollback",
                         "node_rename_preview", "node_reparent_preview",
                         "node_delete_preview",
                         "split_scan", "split_plan",
                         "paths_preview"):
            self.assertIn(expected, names)

    def test_write_tools_hidden_from_user_profile(self):
        """Пользователю write не нужен: инструмент скрыт целиком."""
        import asyncio
        server = self.make_server("user")
        names = {tool.name for tool in asyncio.run(server.list_tools())}
        for hidden in ("write_preview", "write_apply", "write_rollback",
                       "node_rename_preview", "node_reparent_preview",
                       "node_delete_preview"):
            self.assertNotIn(hidden, names)

    def test_import_does_not_start_transport(self):
        self.assertTrue(callable(godot_agent_mcp.main))
        self.assertIsNone(getattr(godot_agent_mcp, "_SERVER", None))

    def test_status_is_reported_without_server_plugin(self):
        server = self.make_server("user")
        result = self.call(server, "status")
        self.assertIsNotNone(result)


class McpMainTransportTests(unittest.TestCase):
    """Контракт main(): профиль и транспорт задаются при запуске.

    stdio остаётся умолчанием — так сервер запускают Cline и другие
    MCP-клиенты. HTTP-транспорты (sse|streamable-http) существуют для
    клиентов, которые сами процесс не запускают.
    """

    class RecordingServer(object):
        def __init__(self):
            self.calls = []

        def run(self, transport="stdio", **options):
            self.calls.append((transport, options))

    def setUp(self):
        previous = godot_agent_mcp._SERVER
        self.addCleanup(setattr, godot_agent_mcp, "_SERVER", previous)
        self.server = self.RecordingServer()
        builder = patch.object(godot_agent_mcp, "build_server",
                               return_value=self.server)
        self.build = builder.start()
        self.addCleanup(builder.stop)

    def test_default_transport_is_stdio(self):
        self.assertEqual(0, godot_agent_mcp.main([]))
        self.assertEqual([("stdio", {})], self.server.calls)
        self.build.assert_called_once_with(profile="user", root=None,
                                           udd=None)

    def test_http_transport_receives_host_and_port(self):
        code = godot_agent_mcp.main([
            "--profile", "agent-dev", "--root", "R", "--udd", "U",
            "--transport", "streamable-http",
            "--host", "127.0.0.1", "--port", "8010"])
        self.assertEqual(0, code)
        self.assertEqual([("streamable-http",
                           {"host": "127.0.0.1", "port": 8010})],
                         self.server.calls)
        self.build.assert_called_once_with(profile="agent-dev", root="R",
                                           udd="U")

    def test_sse_transport_without_host_port(self):
        godot_agent_mcp.main(["--transport", "sse"])
        self.assertEqual([("sse", {})], self.server.calls)

    def test_unknown_transport_fails_closed(self):
        with self.assertRaises(SystemExit) as ctx:
            godot_agent_mcp.main(["--transport", "websocket"])
        self.assertIn("transport", str(ctx.exception).lower())
        self.assertEqual([], self.server.calls)
        self.build.assert_not_called()

    def test_host_or_port_requires_http_transport(self):
        with self.assertRaises(SystemExit):
            godot_agent_mcp.main(["--port", "9000"])
        with self.assertRaises(SystemExit):
            godot_agent_mcp.main(["--transport", "stdio",
                                  "--host", "0.0.0.0"])
        self.build.assert_not_called()

    def test_non_integer_port_fails_closed(self):
        with self.assertRaises(SystemExit) as ctx:
            godot_agent_mcp.main(["--transport", "sse", "--port", "nope"])
        self.assertIn("port", str(ctx.exception).lower())

    def test_missing_option_value_fails(self):
        with self.assertRaises(SystemExit):
            godot_agent_mcp.main(["--transport"])

    def test_help_lists_transports(self):
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = godot_agent_mcp.main(["--help"])
        self.assertEqual(0, code)
        self.assertIn("streamable-http", buffer.getvalue())
        self.build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
