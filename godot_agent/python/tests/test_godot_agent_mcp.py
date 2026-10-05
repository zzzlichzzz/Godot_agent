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

    def call(self, server, name, **arguments):
        """Вызов tool так, как это делает клиент MCP: call_tool — корутина."""
        import asyncio
        result = asyncio.run(server.call_tool(name, arguments))
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


if __name__ == "__main__":
    unittest.main()
