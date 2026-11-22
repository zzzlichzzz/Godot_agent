"""tests/py/code_intel/test_symbol_index.py - S2: индекс проекта (R-09, SEC-12).

Индекс — это `{files, skipped}`: обход через порт `fs`, разбор через
`formats/gdscript`, sha256 каждого файла. Кэша на диске нет: индекс живёт один
вызов (долг записан в `PROGRESS.md`).
"""

from pathlib import Path

from python.kernel.paths import PathPolicy
from python.modules.code_intel.shared import symbol_index
from python.substrate.fs.memory_fs import MemoryFileSystem

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "projects" / "minimal"


def _fs(files):
    store = MemoryFileSystem()
    for rel, text in files.items():
        store.add(rel, text)
    return store


def test_only_gd_files_are_indexed():
    fs = _fs({"scripts/a.gd": "extends Node\n\nfunc run() -> void:\n\tpass\n",
              "data/levels.json": "{}",
              "scenes/a.tscn": "[gd_scene]\n",
              "notes/readme.md": "# x\n"})
    index = symbol_index.build(fs, PathPolicy(""))
    assert [entry["rel"] for entry in index["files"]] == ["scripts/a.gd"]
    assert index["skipped"] == []


def test_policy_denied_files_are_skipped_not_indexed():
    fs = _fs({"scripts/a.gd": "extends Node\n",
              "addons/other/plugin.gd": "@tool\nextends EditorPlugin\n"})
    index = symbol_index.build(fs, PathPolicy(""))
    assert [entry["rel"] for entry in index["files"]] == ["scripts/a.gd"]
    assert index["skipped"] == ["addons/other/plugin.gd"]


def test_declarations_carry_path_and_sha256():
    fs = _fs({"scripts/a.gd": "class_name A\nextends Node\n\nfunc run() -> void:\n\tpass\n"})
    index = symbol_index.build(fs, PathPolicy(""))
    entry = index["files"][0]
    assert entry["path"] == "res://scripts/a.gd"
    assert len(entry["sha256"]) == 64
    assert entry["declarations"][0] == dict(entry["declarations"][0],
                                            path="res://scripts/a.gd",
                                            sha256=entry["sha256"])
    assert [item["name"] for item in symbol_index.declarations(index)] == ["A", "run"]


def test_sha256_follows_text():
    first = symbol_index.build(_fs({"a.gd": "extends Node\n"}), PathPolicy(""))
    second = symbol_index.build(_fs({"a.gd": "extends Node\n\n"}), PathPolicy(""))
    assert first["files"][0]["sha256"] != second["files"][0]["sha256"]


def test_extends_facts_are_stored_for_hierarchy():
    fs = _fs({"base.gd": "class_name Base\nextends Node\n",
              "child.gd": "extends Base\n",
              "grand.gd": "extends \"res://child.gd\"\n",
              "free.gd": "extends Node\n"})
    index = symbol_index.build(fs, PathPolicy(""))
    assert index["files"][0]["parent_class"] == "Node"
    assert symbol_index.class_name_for(index["files"][0]) == "Base"
    assert symbol_index.subclasses(index, "res://base.gd", "Base") == {
        "res://child.gd", "res://grand.gd"}
    assert symbol_index.entry_for(index, "res://free.gd")["parent_class"] == "Node"


def test_unreadable_file_does_not_break_the_index():
    class Broken(MemoryFileSystem):
        def read_text(self, rel_path):
            raise OSError("boom")

    store = Broken()
    store.add("a.gd", "extends Node\n")
    index = symbol_index.build(store, PathPolicy(""))
    assert index["files"] == []
    assert index["skipped"] == ["a.gd"]


def test_minimal_project_index_is_repeatable():
    """Один и тот же проект даёт один и тот же индекс (без кэша и без сети)."""
    from python.substrate.fs.disk_fs import DiskFileSystem

    fs = DiskFileSystem(str(FIXTURE))
    policy = PathPolicy(str(FIXTURE))
    first = symbol_index.build(fs, policy)
    second = symbol_index.build(fs, policy)
    assert first == second
    assert all(entry["path"].endswith(".gd") for entry in first["files"])
    assert "addons/other_plugin/plugin.gd" in first["skipped"]
