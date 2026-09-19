# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(
    _os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401

import editor_context

sys = _sys0

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


snapshot = {
    "schema_version": 1,
    "unknown": "must disappear",
    "scene": {"active": "res://levels/main.tscn",
              "open": ["res://levels/main.tscn", "C:/secret/project.tscn"]},
    "selection": {"nodes": [{
        "path": "Main/Enemies/Enemy",
        "type": "CharacterBody2D",
        "script": "res://enemy.gd",
        "groups": ["enemies"],
        "properties": {"position": "(10, 20)"},
    }]},
    "script": {
        "path": "res://enemy.gd", "dirty": True,
        "caret": {"line": 42, "column": 9},
        "selection": {"from_line": 40, "to_line": 43,
                      "text": "func hit():\n\thealth -= 1"},
        "caret_context": {"start_line": 1, "end_line": 999,
                          "text": "LOW PRIORITY"},
    },
    "run": {"playing": False},
}

block, sizes = editor_context.format_snapshot(snapshot)
normalized = editor_context.normalize_snapshot(snapshot)
check(u"снимок форматируется", block.startswith("[Godot editor context v1"), block)
check(u"активная сцена передана", "res://levels/main.tscn" in block)
check(u"абсолютный путь отфильтрован", "C:/secret" not in block)
check(u"выбранный узел передан", "Main/Enemies/Enemy" in block)
check(u"выделенный код приоритетнее окна курсора",
      "health -= 1" in block and "LOW PRIORITY" not in block)
check(u"позиция курсора однобазовая и сохранена", "line 42, column 9" in block)
check(u"неизвестное поле отброшено", "must disappear" not in block)
check(u"структурированный снимок тоже очищен",
      normalized.get("scene", {}).get("open") == ["res://levels/main.tscn"]
      and "unknown" not in normalized, normalized)
check(u"метаданные содержат только размеры",
      sizes.get("total") == len(block) and "health" not in str(sizes), sizes)

prompt, _ = editor_context.attach_to_prompt("исправь эту функцию", snapshot)
check(u"запрос пользователя явно отделён и остаётся последним",
      prompt.endswith("=== USER REQUEST ===\nисправь эту функцию"), prompt[-100:])
check(u"эфемерный контекст удаляется перед записью API-истории",
      editor_context.user_prompt_without_context(prompt) == "исправь эту функцию")

unrelated_snapshot = dict(snapshot)
unrelated_snapshot["script"] = dict(snapshot["script"])
unrelated_snapshot["script"].pop("selection")
unrelated, _ = editor_context.attach_to_prompt("как устроен InputMap?", unrelated_snapshot)
check(u"открытый скрипт не отправляется без явной ссылки на редактор",
      "Current script:" not in unrelated and "Code near caret" not in unrelated,
      unrelated)
check(u"списки открытых вкладок никогда не попадают в модельный prompt",
      "Open scenes:" not in block and "Other open scripts:" not in block, block)
selected_prompt, _ = editor_context.attach_to_prompt(
    "объясни выделение", snapshot)
check(u"явно выделенный код остаётся доступен",
      "health -= 1" in selected_prompt, selected_prompt)
caret_snapshot = dict(snapshot)
caret_snapshot["script"] = dict(snapshot["script"])
caret_snapshot["script"].pop("selection")
deictic, _ = editor_context.attach_to_prompt("исправь эту функцию", caret_snapshot)
check(u"контекст курсора отправляется только по явной ссылке",
      "LOW PRIORITY" in deictic, deictic)

for malformed in (None, [], {}, {"schema_version": 2},
                  {"schema_version": 1, "script": "bad"}):
    formatted, _ = editor_context.format_snapshot(malformed)
    check(u"повреждённый снимок не ломает форматирование", isinstance(formatted, str))

huge = {"schema_version": 1, "script": {"selection": {"text": "x" * 20000}},
        "selection": {"nodes": [{"path": "Selected", "type": "Node"}]},
        "scene": {"open": ["res://%03d.tscn" % i for i in range(100)]}}
limited, _ = editor_context.format_snapshot(huge, max_chars=700)
check(u"общий бюджет соблюдён", len(limited) <= 700, len(limited))
check(u"выделение узла переживает усечение", "Selected" in limited, limited)
check(u"длинный список сцен отбрасывается раньше", "res://000.tscn" not in limited)

n_ok = sum(1 for result in results if result)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
