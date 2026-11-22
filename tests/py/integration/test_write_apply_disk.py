"""РџСЂРёРјРµРЅРµРЅРёРµ Рё РѕС‚РєР°С‚ РЅР° РќРђРЎРўРћРЇР©Р•Рњ РІСЂРµРјРµРЅРЅРѕРј РїСЂРѕРµРєС‚Рµ (ADR-0005).

РљРѕРїРёСЏ С„РёРєСЃС‚СѓСЂС‹ РІ `tmp_path`: preview в†’ apply в†’ rollback, РїРѕР±Р°Р№С‚РѕРІРѕ. Р—РґРµСЃСЊ Р¶Рµ
CRLF/BOM, stale, TTL, РёРґРµРјРїРѕС‚РµРЅС‚РЅРѕСЃС‚СЊ, Р»РѕРє, СЃР±РѕР№ С€Р°РіР° Рё recovery.
"""

import hashlib
import os
import shutil
from pathlib import Path

import pytest

from python.modules.editing.rollback import recover
from python.runtime.bootstrap import build_agent, default_ports

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "projects" / "rename"
RENAME = {"kind": "function", "old_name": "strike", "new_name": "punch",
          "declaration": "res://src/hero.gd:10"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(str(FIXTURE), str(root))
    return root


@pytest.fixture()
def state(tmp_path):
    return tmp_path / "state"


def make_agent(project, state):
    return build_agent(project_root=str(project), profile="test", state_dir=str(state))


def journal_path(state, plan_id):
    return state / "test" / "journal" / (plan_id + ".jsonl")


def preview(agent, args=None):
    answer = agent.call("write_preview", dict(RENAME, **(args or {})))
    assert answer["ok"], answer
    return answer["result"]


def test_apply_changes_bytes_and_rollback_restores_them(project, state):
    agent = make_agent(project, state)
    plan = preview(agent)
    before = {path: sha(path) for path in project.rglob("*.gd")}
    applied = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                         "digest": plan["digest"]})
    assert applied["ok"], applied
    result = applied["result"]
    assert result["state"] == "COMMITTED" and result["files_count"] >= 1
    assert result["entry_id"].startswith(plan["plan_id"] + "#")
    assert sha(project / "src" / "hero.gd") != before[project / "src" / "hero.gd"]
    assert b"func punch" in (project / "src" / "hero.gd").read_bytes()
    rolled = agent.call("write_rollback", {"entry_id": result["entry_id"]})
    assert rolled["ok"], rolled
    assert {path: sha(path) for path in before} == before


def test_second_apply_is_idempotent(project, state):
    agent = make_agent(project, state)
    plan = preview(agent)
    args = {"plan_id": plan["plan_id"], "digest": plan["digest"]}
    first = agent.call("write_apply", args)["result"]
    hashes = {path: sha(path) for path in project.rglob("*.gd")}
    second = agent.call("write_apply", args)
    assert second["ok"] and second["result"]["entry_id"] == first["entry_id"]
    assert {path: sha(path) for path in project.rglob("*.gd")} == hashes


def test_file_changed_after_preview_is_stale_and_untouched(project, state):
    agent = make_agent(project, state)
    plan = preview(agent)
    hero = project / "src" / "hero.gd"
    hero.write_bytes(hero.read_bytes() + b"\n# user edit\n")
    changed = sha(hero)
    answer = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                        "digest": plan["digest"]})
    assert answer["ok"] is False and answer["kind"] == "stale_plan"
    assert sha(hero) == changed


def test_wrong_digest_is_stale_plan(project, state):
    agent = make_agent(project, state)
    plan = preview(agent)
    answer = agent.call("write_apply", {"plan_id": plan["plan_id"], "digest": "x"})
    assert answer["ok"] is False and answer["kind"] == "stale_plan"
    assert b"func strike" in (project / "src" / "hero.gd").read_bytes()


def test_expired_plan_is_not_found(project, state):
    agent = make_agent(project, state)
    plan = preview(agent)
    path = journal_path(state, plan["plan_id"])
    old = os.path.getmtime(str(path)) - 1000  # plan older than confirm_ttl
    os.utime(str(path), (old, old))
    answer = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                        "digest": plan["digest"]})
    assert answer["ok"] is False and answer["kind"] == "not_found"
    assert answer["details"]["state"] == "EXPIRED"


def test_unknown_plan_is_not_found(project, state):
    agent = make_agent(project, state)
    answer = agent.call("write_apply", {"plan_id": "plan_nope", "digest": "d"})
    assert answer["ok"] is False and answer["kind"] == "not_found"


def test_foreign_lock_gives_conflict(project, state):
    agent = make_agent(project, state)
    plan = preview(agent)
    lock_path = state / "test" / "project.lock"
    lock_path.write_text("{}", encoding="utf-8")
    try:
        answer = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                            "digest": plan["digest"]})
    finally:
        lock_path.unlink()
    assert answer["ok"] is False and answer["kind"] == "conflict"
    assert answer["details"]["reason"] == "lock_busy"


def test_rollback_after_external_edit_is_conflict(project, state):
    agent = make_agent(project, state)
    plan = preview(agent)
    result = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                        "digest": plan["digest"]})["result"]
    hero = project / "src" / "hero.gd"
    hero.write_bytes(hero.read_bytes() + b"\n# later\n")
    changed = sha(hero)
    answer = agent.call("write_rollback", {"entry_id": result["entry_id"]})
    assert answer["ok"] is False and answer["kind"] == "conflict"
    assert answer["details"]["reason"] == "post_state_mismatch"
    assert sha(hero) == changed


def test_repeat_rollback_is_conflict(project, state):
    agent = make_agent(project, state)
    plan = preview(agent)
    result = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                        "digest": plan["digest"]})["result"]
    assert agent.call("write_rollback", {"entry_id": result["entry_id"]})["ok"]
    again = agent.call("write_rollback", {"entry_id": result["entry_id"]})
    assert again["ok"] is False and again["kind"] == "conflict"
    assert again["details"]["reason"] == "already_rolled_back"


def test_crlf_and_bom_are_restored(project, state):
    hero = project / "src" / "hero.gd"
    hero.write_bytes(hero.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    party = project / "src" / "party.gd"
    party.write_bytes(b"\xef\xbb\xbf" + party.read_bytes())
    originals = {path: path.read_bytes() for path in (hero, party)}
    agent = make_agent(project, state)
    plan = preview(agent, {"kind": "variable", "old_name": "hp", "new_name": "health",
                           "declaration": "res://src/hero.gd:4", "mode": "probable",
                           "allow_unverified": True})
    applied = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                         "digest": plan["digest"]})
    assert applied["ok"], applied
    assert b"\r\n" in hero.read_bytes()
    assert party.read_bytes().startswith(b"\xef\xbb\xbf")
    rolled = agent.call("write_rollback", {"entry_id": applied["result"]["entry_id"]})
    assert rolled["ok"], rolled
    assert {path: path.read_bytes() for path in originals} == originals


def test_failing_second_step_rolls_back_first(project, state, monkeypatch):
    agent = make_agent(project, state)
    plan = preview(agent, {"kind": "variable", "old_name": "hp", "new_name": "health",
                           "declaration": "res://src/hero.gd:4", "mode": "probable",
                           "allow_unverified": True})
    before = {path: sha(path) for path in project.rglob("*.gd")}
    module = "python.substrate.fs.atomic_write.AtomicFileWriter.write_raw"
    real = __import__("python.substrate.fs.atomic_write",
                      fromlist=["AtomicFileWriter"]).AtomicFileWriter.write_raw
    calls = {"n": 0}

    def flaky(self, rel, data):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("РёРЅСЉРµРєС†РёСЏ СЃР±РѕСЏ")
        return real(self, rel, data)

    monkeypatch.setattr(module, flaky)
    answer = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                        "digest": plan["digest"]})
    assert answer["ok"] is False
    assert {path: sha(path) for path in project.rglob("*.gd")} == before
    wal = journal_path(state, plan["plan_id"])
    assert "ROLLED_BACK" in wal.read_text(encoding="utf-8")


def test_recovery_rolls_back_interrupted_apply(project, state):
    agent = make_agent(project, state)
    plan = preview(agent)
    ports = default_ports(str(project), "test", str(state))
    journal, writer, backups = ports["journal"], ports["writer"], ports["backups"]
    target = plan["steps"][0]["target"]
    rel = target[len("res://"):]
    raw = writer.read_raw(rel)
    new_raw = raw.replace(b"strike", b"punch")
    token = backups.put(plan["plan_id"], 1, raw)
    writer.write_raw(rel, new_raw)
    entry_id = plan["plan_id"] + "#1"
    journal.append(plan["plan_id"], {"state": "APPLYING", "entry_id": entry_id})
    journal.append(plan["plan_id"], {
        "state": "RECEIPT", "entry_id": entry_id,
        "receipt": {"step_id": target, "undo_token": token,
                    "applied_hash": hashlib.sha256(new_raw).hexdigest()}})
    report = recover(ports)
    assert {"plan_id": plan["plan_id"], "action": "rolled_back"} in report
    assert writer.read_raw(rel) == raw


def test_recovery_expires_stale_prepared(project, state):
    agent = make_agent(project, state)
    plan = preview(agent)
    path = journal_path(state, plan["plan_id"])
    old = os.path.getmtime(str(path)) - 1000  # plan older than confirm_ttl
    os.utime(str(path), (old, old))
    report = recover(default_ports(str(project), "test", str(state)))
    assert {"plan_id": plan["plan_id"], "action": "expired"} in report

