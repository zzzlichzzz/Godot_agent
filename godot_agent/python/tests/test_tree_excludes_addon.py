# -*- coding: utf-8 -*-
"""Project scans use canonical policy identities, not mutable global names."""
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


def test_agent_name_is_never_added_to_global_exclusions():
    root = tempfile.mkdtemp()
    _make_project(root, wrapper="MyRenamedAgent", inner="agent_core")
    addon_dir = os.path.join(root, "addons", "MyRenamedAgent", "agent_core")
    before = set(project_tools.EXCLUDED_DIRS)
    project_tools.exclude_agent_addon_dirs(addon_dir)
    assert set(project_tools.EXCLUDED_DIRS) == before
    assert "MyRenamedAgent" not in project_tools.EXCLUDED_DIRS
    assert "agent_core" not in project_tools.EXCLUDED_DIRS
    print("OK: имена addons не становятся глобальной security boundary")


def test_project_scanner_uses_current_project_policy_identity():
    root_a = tempfile.mkdtemp()
    root_b = tempfile.mkdtemp()
    _make_project(root_a, wrapper="SharedName", inner="agent_a")
    _make_project(root_b, wrapper="SharedName", inner="agent_b")
    addon_a = os.path.join(root_a, "addons", "SharedName", "agent_a")
    addon_b = os.path.join(root_b, "addons", "SharedName", "agent_b")
    project_tools.exclude_agent_addon_dirs(addon_a)
    tree_b = project_tools.build_project_tree(
        root_b, allow_addons=True, allow_self_edit=False, addon_dir=addon_b)
    assert "SharedName" in tree_b and "junk.gd" not in tree_b, tree_b
    print("OK: одинаковое имя wrapper в другом проекте не наследует exclusion")


if __name__ == "__main__":
    test_agent_name_is_never_added_to_global_exclusions()
    test_project_scanner_uses_current_project_policy_identity()
    print("ВСЕ ТЕСТЫ ПРОШЛИ")
