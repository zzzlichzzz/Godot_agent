"""tests/py/security/test_write_boundary.py - граница записи (R-12, SEC-06).

Механики воронки пишут только внутрь проекта и каталога состояния. Проверяется,
что путь с `..`, абсолютный путь и путь вне проекта отклоняются ДО появления
файла, а WAL не содержит абсолютных путей и секретов.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path

from python.kernel.paths import PathPolicy
from python.modules.editing.shared import funnel
from python.modules.editing.write_apply import app as apply_app
from python.runtime.bootstrap import build_agent, default_ports

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "projects" / "rename"
RENAME = {"kind": "function", "old_name": "strike", "new_name": "punch",
          "declaration": "res://src/hero.gd:10"}


class _Ctx(object):
    def __init__(self, ports, project):
        self._ports = ports
        self.path_policy = PathPolicy(str(project), allow_addons=True,
                                      allow_self_edit=False)
        self.logger = None

    def port(self, name):
        return self._ports[name]


def _ports(tmp_path):
    project = tmp_path / "project"
    shutil.copytree(str(FIXTURE), str(project))
    return project, default_ports(str(project), "test", str(tmp_path / "state"))


def _tree(root):
    return {path.relative_to(root).as_posix():
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(root).rglob("*")) if path.is_file()}


def test_apply_touches_only_project_and_state(tmp_path):
    project, _ = _ports(tmp_path)
    agent = build_agent(project_root=str(project), profile="test",
                        state_dir=str(tmp_path / "state"))
    before = _tree(tmp_path)
    plan = agent.call("write_preview", dict(RENAME))["result"]
    assert agent.call("write_apply", {"plan_id": plan["plan_id"],
                                      "digest": plan["digest"]})["ok"]
    changed = {rel for rel, value in _tree(tmp_path).items()
               if before.get(rel) != value}
    assert changed, "применение обязано что-то изменить"
    assert all(rel.startswith(("project/", "state/")) for rel in changed), changed
    inside = {rel for rel in changed if rel.startswith("project/")}
    assert inside == {"project/src/hero.gd"}, inside


def test_escape_targets_are_denied_before_any_write(tmp_path):
    project, ports = _ports(tmp_path)
    ctx = _Ctx(ports, project)
    outside = tmp_path / "evil.gd"
    for target in ("res://../evil.gd", "res://C:/evil.gd",
                   "res:///tmp/evil.gd", "res://src/../../evil.gd"):
        try:
            funnel.guard_path(ctx, target[len("res://"):])
        except Exception as exc:  # AppError denied
            assert getattr(exc, "kind", "") == "denied", (target, exc)
        else:
            raise AssertionError("путь вне проекта должен быть отклонён: %s" % target)
    assert not outside.exists()


def test_absolute_target_is_rejected_by_writer(tmp_path):
    project, ports = _ports(tmp_path)
    writer = ports["writer"]
    for rel in ("../evil.gd", "C:/evil.gd", "/tmp/evil.gd", "src/../../x.gd"):
        try:
            writer.write_raw(rel, b"x")
        except (PermissionError, FileNotFoundError, ValueError):
            pass
        else:
            raise AssertionError("запись вне проекта прошла: %s" % rel)
    assert not (tmp_path / "evil.gd").exists()


def test_no_secrets_or_absolute_paths_in_the_wal(tmp_path):
    project, ports = _ports(tmp_path)
    agent = build_agent(project_root=str(project), profile="test",
                        state_dir=str(tmp_path / "state"))
    plan = agent.call("write_preview", dict(RENAME))["result"]
    assert agent.call("write_apply", {"plan_id": plan["plan_id"],
                                      "digest": plan["digest"]})["ok"]
    wal = Path(ports["journal"].path(plan["plan_id"])).read_text(encoding="utf-8")
    assert str(tmp_path) not in wal and "\\\\" not in wal
    assert "password" not in wal.lower() and "secret" not in wal.lower()
    for line in wal.splitlines():
        record = json.loads(line)
        assert record["state"] in ("PREPARED", "APPLYING", "EFFECT_INTENT", "RECEIPT", "COMMITTED")


def test_agent_instance_keeps_the_project_lock_free(tmp_path):
    project, ports = _ports(tmp_path)
    lock = ports["lock"]
    assert not os.path.exists(lock.path)
    agent = build_agent(project_root=str(project), profile="test",
                        state_dir=str(tmp_path / "state"))
    plan = agent.call("write_preview", dict(RENAME))["result"]
    agent.call("write_apply", {"plan_id": plan["plan_id"], "digest": plan["digest"]})
    assert not os.path.exists(lock.path), "лок отпускается в finally"
