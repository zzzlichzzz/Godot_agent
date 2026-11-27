"""tests/py/security/test_secret_redaction.py - SEC-13: наружу не течёт лишнее.

Ответ предпросмотра уходит клиенту: в нём не должно быть абсолютных путей,
переменных окружения и содержимого чужих файлов. `digest` — непрозрачный
sha256, `diffs` — только затронутые строки.
"""

import json
import re

import pytest

from python.runtime.bootstrap import build_agent

FIXTURE = "fixtures/projects/rename"
BASE = {"kind": "function", "old_name": "take_damage",
        "new_name": "apply_damage", "declaration": "res://src/hero.gd:6"}
ABS_PATH = re.compile(r"\b[A-Za-z]:[\\/]")
SECRETS = ("USERPROFILE", "APPDATA", "TOKEN", "SECRET", "PASSWORD")


def _flat(**extra):
    args = dict(BASE)
    args.update(extra)
    answer = build_agent(project_root=FIXTURE, profile="test").call("write_preview", args)
    return json.dumps(answer, ensure_ascii=False)


@pytest.mark.parametrize("extra", [
    {"mode": "probable", "allow_unverified": True},
    {},
    {"declaration": "res://src/hero.gd:7"},
])
def test_answers_carry_no_absolute_paths_or_env_names(extra):
    flat = _flat(**extra)
    assert not ABS_PATH.search(flat), flat[:200]
    for word in SECRETS:
        assert word not in flat.upper()


def test_digest_is_an_opaque_sha256():
    result = build_agent(project_root=FIXTURE, profile="test").call(
        "write_preview", dict(BASE, mode="probable", allow_unverified=True))["result"]
    assert re.fullmatch(r"[0-9a-f]{64}", result["digest"])
    assert result["plan_id"].startswith("plan_")
    assert "hero.gd" in json.dumps(result["affected_paths"])


def test_diff_only_mentions_the_symbol_lines():
    result = build_agent(project_root=FIXTURE, profile="test").call(
        "write_preview", dict(BASE, mode="probable", allow_unverified=True))["result"]
    for diff in result["diffs"]:
        for line in diff["patch"].splitlines():
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                assert "damage" in line, line
