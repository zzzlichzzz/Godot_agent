"""kernel/write_plan.py - универсальный конверт плана правки (ADR-0005).

Здесь НЕТ сценовых операций: только общая форма, чтобы editing, scene_model
и project_ops пользовались одним типом, не импортируя чужой shared (R-11).

`digest` — sha256 канонического JSON входа плана: тот же вход даёт тот же
digest, а `plan_id` остаётся случайным (идемпотентность подтверждения в
части 2 привязана к digest, а не к имени файла журнала).
"""

import hashlib
import json
from dataclasses import dataclass, field

#: Состояния ADR-0005. В этом срезе механика доходит только до PREPARED.
STATES = ("DRAFT", "PREPARED", "APPLYING", "COMMITTED", "ROLLING_BACK",
          "ROLLED_BACK", "EXPIRED")
#: Срок жизни подтверждения пользователя: 15 минут (ADR-0005).
CONFIRM_TTL = 900


@dataclass(frozen=True)
class Step(object):
    """Один шаг плана: что сделать с одним файлом и что было до правки."""

    op: str
    target: str
    payload: dict = field(default_factory=dict)
    expected_hash: str = ""
    compensates: str = ""

    def as_dict(self):
        data = {"op": self.op, "target": self.target,
                "payload": dict(self.payload),
                "expected_hash": self.expected_hash}
        if self.compensates:
            data["compensates"] = self.compensates
        return data


@dataclass(frozen=True)
class Receipt(object):
    """Квитанция применённого шага (пишет часть 2, до следующего шага)."""

    step_id: str
    applied_hash: str = ""
    undo_token: str = ""

    def as_dict(self):
        return {"step_id": self.step_id, "applied_hash": self.applied_hash,
                "undo_token": self.undo_token}


@dataclass(frozen=True)
class WritePlan(object):
    """План целиком: шаги, ожидаемые хеши файлов, digest и TTL."""

    plan_id: str
    digest: str
    steps: tuple = ()
    expected: dict = field(default_factory=dict)
    state: str = "PREPARED"
    confirm_ttl: int = CONFIRM_TTL

    def as_dict(self):
        return {"plan_id": self.plan_id, "digest": self.digest,
                "state": self.state,
                "steps": [step.as_dict() for step in self.steps],
                "expected": dict(self.expected),
                "confirm_ttl": int(self.confirm_ttl)}


def canonical_json(data):
    """Строка, которая не зависит от порядка ключей и пробелов."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def digest_of(kind, declaration, old_name, new_name, mode, allow_unverified,
              steps, expected):
    """sha256 канонического входа плана (порядок шагов значим)."""
    body = {
        "kind": str(kind), "declaration": str(declaration),
        "old_name": str(old_name), "new_name": str(new_name),
        "mode": str(mode), "allow_unverified": bool(allow_unverified),
        "steps": [step.as_dict() if hasattr(step, "as_dict") else dict(step)
                  for step in steps],
        "expected": dict(expected or {}),
    }
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
