# -*- coding: utf-8 -*-
"""Синтетический полигон FUNC CARD: базовый класс + N наследников.

Цель: проверить поведение глубокой карточки `func:имя` на большом графе
(сотни наследников, десятки вызовов, переопределения, dynamic-строки).

Использование (из корня репо):
    python -X utf8 godot_agent/python/tests/synthetic_card_bench.py gen 120
    python -X utf8 godot_agent/python/tests/synthetic_card_bench.py query func:take_damage

Проект создаётся в %TEMP%/fcsynth и там же остаётся answer.txt.
"""

import json
import os
import sys
import time
import urllib.request

ROOT = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", "/tmp")),
                    "fcsynth")

BASE_GD = '''class_name Enemy
extends Node2D

signal died(enemy)

const MAX_HP := 100

var hp: int = MAX_HP
var armor: int = 0

func take_damage(amount: int) -> void:
\tvar real: int = maxi(amount - armor, 1)
\thp -= real
\tGameState.register_hit(self, real)
\tif hp <= 0:
\t\tdied.emit(self)

func heal(amount: int) -> void:
\thp = mini(hp + amount, MAX_HP)
'''

SUB = '''extends Enemy

var rage: int = 0

func _ready() -> void:
\trage = {i}
'''

SUB_OVERRIDE = SUB + '''
func take_damage(amount: int) -> void:
\trage += 1
\tsuper.take_damage(amount)
'''

SUB_CALLER = SUB + '''
func provoke() -> void:
\ttake_damage(0)
'''

SUB_DYNAMIC = SUB + '''
func provoke() -> void:
\tvar method: String = "take_damage"
\tcall(method, 0)
'''


def gen(n_sub: int = 120) -> None:
    import shutil
    shutil.rmtree(ROOT, ignore_errors=True)
    os.makedirs(os.path.join(ROOT, "scripts", "enemies"))
    os.makedirs(os.path.join(ROOT, "autoload"))
    with open(os.path.join(ROOT, "project.godot"), "w", encoding="utf-8") as f:
        f.write(
            "config_version=5\n\n"
            "[application]\nconfig/name=\"fcsynth\"\n\n"
            "[autoload]\nGameState=\"*res://autoload/game_state.gd\"\n")
    with open(os.path.join(ROOT, "autoload", "game_state.gd"), "w",
              encoding="utf-8") as f:
        f.write("extends Node\n\nvar hits: int = 0\n\n"
                "func register_hit(_enemy: Node, amount: int) -> void:\n"
                "\thits += amount\n")
    with open(os.path.join(ROOT, "scripts", "player.gd"), "w",
              encoding="utf-8") as f:
        f.write("extends Node\n\n"
                "func _ready() -> void:\n"
                "\tvar foe: Enemy = Enemy.new()\n"
                "\tfoe.take_damage(5)\n")
    with open(os.path.join(ROOT, "scripts", "enemy.gd"), "w",
              encoding="utf-8") as f:
        f.write(BASE_GD)
    n_over = n_call = n_dyn = 0
    for i in range(1, n_sub + 1):
        name = "enemy_%03d" % i
        if i % 3 == 0:
            body = SUB_OVERRIDE
            n_over += 1
        elif i % 3 == 1:
            body = SUB_CALLER
            n_call += 1
        else:
            body = SUB_DYNAMIC
            n_dyn += 1
        with open(os.path.join(ROOT, "scripts", "enemies", name + ".gd"),
                  "w", encoding="utf-8") as f:
            f.write(body.format(i=i))
    print("project: %s (%d subclasses: %d override, %d direct call, %d dynamic)"
          % (ROOT, n_sub, n_over, n_call, n_dyn))


def query(query_text: str) -> None:
    payload = json.dumps({"project_root": ROOT,
                          "query": query_text}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:5000/librarian/query", data=payload,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as resp:
        answer = json.loads(resp.read().decode("utf-8"))["answer"]
    dt = time.time() - t0
    out = os.path.join(ROOT, "answer.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(answer)
    lines = answer.splitlines()
    print("answer: %d chars, %d lines, %.1f s -> %s"
          % (len(answer), len(lines), dt, out))
    for ln in lines:
        s = ln.strip()
        if (s.startswith(("[CALLERS]", "[SUBCLASSES]", "[OVERRIDES]",
                          "[FUNC ", "[SYMBOL", "[FILE", "[BODY]"))
                or s.startswith("…(")):
            print("  " + s)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "gen":
        gen(int(sys.argv[2]) if len(sys.argv) > 2 else 120)
    elif len(sys.argv) >= 3 and sys.argv[1] == "query":
        query(sys.argv[2])
    else:
        print(__doc__)
