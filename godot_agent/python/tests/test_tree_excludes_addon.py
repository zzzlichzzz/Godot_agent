# -*- coding: utf-8 -*-
"""Дерево/сводка проекта не должны включать папку самого плагина
(python-сборка сервера раздувала мега-промпт)."""
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
import os
import tempfile

import project_tools
import server_state


def _make_project(root, wrapper="Godot_agent", inner="godot_agent"):
    junk = os.path.join(root, "addons", wrapper, inner, "python", "dist",
                        "godot_agent_server", "_internal", "numpy")
    os.makedirs(junk)
    with open(os.path.join(junk, "junk.gd"), "w", encoding="utf-8") as f:
        f.write("# junk\n")
    scripts = os.path.join(root, "src", "scripts")
    os.makedirs(scripts)
    with open(os.path.join(scripts, "player.gd"), "w", encoding="utf-8") as f:
        f.write("extends Node\n")


def test_static_exclusion_of_distributed_folder_name():
    root = tempfile.mkdtemp()
    _make_project(root)
    tree = project_tools.build_project_tree(root, only_exts={".gd", ".tscn"})
    assert "player.gd" in tree, tree
    assert "Godot_agent" not in tree, tree
    assert "dist" not in tree and "numpy" not in tree, tree
    print("OK: дистрибутивная папка Godot_agent исключена статически")


def test_dynamic_exclusion_via_addon_dir():
    root = tempfile.mkdtemp()
    _make_project(root, wrapper="MyRenamedAgent", inner="agent_core")
    addon_dir = os.path.join(root, "addons", "MyRenamedAgent", "agent_core")
    tree_before = project_tools.build_project_tree(root, only_exts={".gd"})
    assert "MyRenamedAgent" in tree_before, tree_before
    project_tools.exclude_agent_addon_dirs(addon_dir)
    assert "MyRenamedAgent" in project_tools.EXCLUDED_DIRS
    assert "agent_core" in project_tools.EXCLUDED_DIRS
    tree = project_tools.build_project_tree(root, only_exts={".gd"})
    assert "MyRenamedAgent" not in tree and "junk.gd" not in tree, tree
    assert "player.gd" in tree, tree
    print("OK: переименованный аддон исключается динамически по addon_dir")


def test_apply_session_context_registers_exclusion():
    root = tempfile.mkdtemp()
    _make_project(root, wrapper="AnotherWrap", inner="another_inner")
    addon_dir = os.path.join(root, "addons", "AnotherWrap", "another_inner")
    server_state._apply_session_context({"project_root": root, "addon_dir": addon_dir})
    assert "AnotherWrap" in project_tools.EXCLUDED_DIRS
    assert "another_inner" in project_tools.EXCLUDED_DIRS
    print("OK: /init (_apply_session_context) регистрирует исключение")


if __name__ == "__main__":
    test_static_exclusion_of_distributed_folder_name()
    test_dynamic_exclusion_via_addon_dir()
    test_apply_session_context_registers_exclusion()
    print("ВСЕ ТЕСТЫ ПРОШЛИ")
