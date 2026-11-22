"""tests/py/security/test_write_funnel.py - SEC-11: запись только через apply.

Проверяется сама воронка: в коде предпросмотра нет ни `open(..., "w")`, ни
`os.remove`, ни записи через порт `fs`; единственный эффект — запись WAL вне
проекта. Отдельно сравниваются хеши копии проекта до и после предпросмотра.
"""

import ast
import hashlib
import shutil
from pathlib import Path

from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
MODULES = ROOT / "python" / "modules" / "editing"
FIXTURE = ROOT / "fixtures" / "projects" / "rename"
WRITE_METHODS = {"write_text", "write_bytes", "unlink"}
FORBIDDEN_CALLS = {"open", "remove", "unlink", "rmtree", "system", "popen"}
BASE = {"kind": "function", "old_name": "take_damage",
        "new_name": "apply_damage", "declaration": "res://src/hero.gd:6"}


def _sources():
    return sorted(list((MODULES / "write_preview").rglob("*.py"))
                  + list((MODULES / "symbol_rename" / "domain").rglob("*.py")))


def test_module_never_opens_files_for_writing():
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            assert name not in FORBIDDEN_CALLS, "%s: %s()" % (path.name, name)
            if name == "open":
                modes = [arg.value for arg in node.args[1:] if isinstance(arg, ast.Constant)]
                assert not any(ch in str(m) for m in modes for ch in "wa+"), path.name


def test_funnel_does_not_write_through_the_fs_port():
    text = (MODULES / "write_preview" / "app.py").read_text(encoding="utf-8")
    for method in WRITE_METHODS:
        assert ".%s(" % method not in text, "порт fs только читает"


def _tree_hash(base):
    digest = hashlib.sha256()
    for path in sorted(base.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(base).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def test_preview_keeps_the_project_byte_identical(tmp_path):
    project = tmp_path / "project"
    shutil.copytree(str(FIXTURE), str(project))
    before = _tree_hash(project)
    agent = build_agent(project_root=str(project), profile="test",
                        state_dir=str(tmp_path / "state"))
    answer = agent.call("write_preview", dict(BASE, mode="probable",
                                              allow_unverified=True))
    assert answer["ok"] is True, answer
    assert _tree_hash(project) == before, "предпросмотр изменил проект"


def test_journal_lives_outside_the_project(tmp_path):
    project = tmp_path / "project"
    shutil.copytree(str(FIXTURE), str(project))
    state = tmp_path / "state"
    agent = build_agent(project_root=str(project), profile="test", state_dir=str(state))
    plan_id = agent.call("write_preview", dict(BASE, mode="probable",
                                              allow_unverified=True))["result"]["plan_id"]
    written = list(state.rglob(plan_id + ".jsonl"))
    assert len(written) == 1, "WAL ровно один и вне проекта"
    assert project not in written[0].parents
