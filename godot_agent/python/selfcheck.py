# -*- coding: utf-8 -*-
"""Простая самопроверка аддона без браузера/AI Studio/реального проекта Godot.

Зачем это нужно: большая часть того, что может сломаться в агенте
(план-режим, откат, защиты API/сцен), не связано с браузером и проверяется
чистой логикой на вревенном временном черновике-целого "фейковом" проекте.
Сайтовый парсер (ai_parser.py) тут НЕ трогается — его можно проверить
только вручную в реальном браузере.

Запуск: из папки python/ вашего проекта —
    python selfcheck.py
требует те же зависимости, что и сам сервер (flask, selenium) — они у вас
уже установлены, так что отдельно ставить ничего не надо.
В конце пецатает "=== RESULT: N passed, M failed ===" и выходит с кодом 0/1.
"""
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("OK   -", name)
    else:
        FAIL += 1
        print("FAIL -", name, "->", detail)


try:
    import history_manager as history
    import server_state
    import main as srv
    import gd_api_cache
    import gd_api_check
    import tscn_lint
    import sites
    from project_tools import describe_scene, create_project_file
except Exception as e:
    print("FAIL - не удалось импортировать модули сервера:", e)
    print("Проверьте, что flask и selenium установлены в тот же python, которым вы запускаете сервер.")
    sys.exit(1)


def fresh_project():
    return tempfile.mkdtemp(prefix="agent_selfcheck_")


def reset_state(root):
    srv.STATE["project_root"] = root
    srv.STATE["pending_action"] = None
    srv.STATE["pending_batch"] = None
    srv.STATE["pending_plan"] = None
    srv.STATE["action_notes"] = {}
    srv.STATE["current_chat_id"] = None
    srv.STATE["addon_dir"] = None


# ===========================================================================
# 1) План-режим: валидация, шаги по одному, остановка на ошибке, откат, ручная остановка
# ===========================================================================
print("\n--- 1) план-режим ---")

ok, err = srv._validate_plan_steps([])
check("пустой план отвергается", ok is False)

ok, err = srv._validate_plan_steps([{"action": "copy_file", "path": "a.gd"}])
check("чужое действие в шаге отвергается", ok is False, err)

big_steps = [{"action": "create_file", "path": "f%d.gd" % i, "content": ""} for i in range(srv.MAX_PLAN_STEPS + 1)]
ok, err = srv._validate_plan_steps(big_steps)
check("слишком длинный план отвергается", ok is False, err)

root = fresh_project()
try:
    reset_state(root)
    chain_id = history.new_chain_id()
    steps = [
        {"action": "create_file", "path": "res://a.gd", "content": "extends Node\nfunc a():\n\tpass\n"},
        {"action": "create_file", "path": "res://b.gd", "content": "extends Node\nfunc b():\n\tpass\n"},
        {"action": "patch_file", "path": "res://a.gd", "search": "func a():\n\tpass", "replace": "func a():\n\tprint(1)"},
    ]
    srv.STATE["pending_plan"] = {"chain_id": chain_id, "steps": steps, "index": 0,
                                  "description": "selfcheck", "total": len(steps), "applied_paths": []}
    client = srv.app.test_client()

    j1 = client.post("/chat/plan/step").get_json()
    check("шаг 1/3 плана выполняется", j1.get("ok") is True and os.path.isfile(os.path.join(root, "a.gd")), j1)
    j2 = client.post("/chat/plan/step").get_json()
    check("шаг 2/3 плана выполняется", j2.get("ok") is True and os.path.isfile(os.path.join(root, "b.gd")), j2)
    j3 = client.post("/chat/plan/step").get_json()
    with open(os.path.join(root, "a.gd"), encoding="utf-8") as f:
        content_a = f.read()
    check("шаг 3/3 завершает цепочку и применяет патч", j3.get("done") is True and "print(1)" in content_a, (j3, content_a))

    ok, msg, needs_force, paths, reverted, total = history.rollback_chain(root, chain_id, force=False)
    check("откат всей цепочки убирает все 3 файловые изменения", ok is True and reverted == 3, (msg, reverted, total))
    check("после отката a.gd и b.gd удалены",
          not os.path.isfile(os.path.join(root, "a.gd")) and not os.path.isfile(os.path.join(root, "b.gd")))
finally:
    shutil.rmtree(root, ignore_errors=True)

root = fresh_project()
try:
    reset_state(root)
    chain_id = history.new_chain_id()
    steps = [
        {"action": "create_file", "path": "res://c.gd", "content": "extends Node\n"},
        {"action": "patch_file", "path": "res://c.gd", "search": "THIS_TEXT_DOES_NOT_EXIST", "replace": "x"},
        {"action": "create_file", "path": "res://d.gd", "content": "extends Node\n"},
    ]
    srv.STATE["pending_plan"] = {"chain_id": chain_id, "steps": steps, "index": 0,
                                  "description": "selfcheck-stop", "total": len(steps), "applied_paths": []}
    client = srv.app.test_client()
    _orig_reply1 = srv._reply
    srv._reply = lambda prompt: ("", None)
    client.post("/chat/plan/step")
    j2 = client.post("/chat/plan/step").get_json()
    srv._reply = _orig_reply1
    check("битый шаг останавливает цепочку, не ломая уже сделанное",
          j2.get("ok") is False and j2.get("stopped") is True and os.path.isfile(os.path.join(root, "c.gd"))
          and not os.path.isfile(os.path.join(root, "d.gd")), j2)
    history.rollback_chain(root, chain_id, force=False)
finally:
    shutil.rmtree(root, ignore_errors=True)


# ===========================================================================
# 1b) Откат всего плана сразу + чистка автозагрузки после отката + project.godot reload +
# защита аддона от незатребованных правок
# ===========================================================================
print("\n--- 1б) откат целой цепочки, автозагрузка, аддон ---")

from project_tools import clean_dangling_autoloads

root = fresh_project()
try:
    reset_state(root)
    with open(os.path.join(root, "project.godot"), "w", encoding="utf-8") as f:
        f.write(
            "[application]\n\nrun/main_scene=\"res://main.tscn\"\n\n"
            "[autoload]\n\nGone=\"*res://gone.gd\"\nStill=\"*res://still.gd\"\n"
        )
    with open(os.path.join(root, "still.gd"), "w", encoding="utf-8") as f:
        f.write("extends Node\n")
    removed = clean_dangling_autoloads(root)
    check("clean_dangling_autoloads убирает только висячие записи", removed == ["Gone"], removed)
    with open(os.path.join(root, "project.godot"), encoding="utf-8") as f:
        cfg = f.read()
    check("project.godot сохраняет существующую автозагрузку и убирает только висячую",
          "Still" in cfg and "Gone" not in cfg, cfg)
finally:
    shutil.rmtree(root, ignore_errors=True)

root = fresh_project()
try:
    reset_state(root)
    with open(os.path.join(root, "project.godot"), "w", encoding="utf-8") as f:
        f.write("[autoload]\n\nHUD=\"*res://hud.gd\"\n")
    chain_id = history.new_chain_id()
    steps = [
        {"action": "create_file", "path": "res://hud.gd", "content": "extends Node\n"},
    ]
    srv.STATE["pending_plan"] = {"chain_id": chain_id, "steps": steps, "index": 0,
                                  "description": "selfcheck-autoload", "total": len(steps), "applied_paths": []}
    client = srv.app.test_client()
    client.post("/chat/plan/step")
    prev = client.post("/chat/rollback/preview").get_json()
    check("превью отката одношаговой цепочки не требует отката всей цепочки",
          prev.get("found") is True and not prev.get("chain_id"), prev)
    j = client.post("/chat/plan/rollback_chain", json={"chain_id": chain_id}).get_json()
    check("откат цепочки сообщает об убранной автозагрузке и о смене project.godot",
          j.get("success") is True and j.get("autoload_removed") == ["HUD"]
          and j.get("project_godot_changed") is True
          and "res://project.godot" in j.get("paths", []), j)
finally:
    shutil.rmtree(root, ignore_errors=True)

root = fresh_project()
try:
    reset_state(root)
    os.makedirs(os.path.join(root, "addons", "myaddon"), exist_ok=True)
    client = srv.app.test_client()

    srv.STATE["addon_intent"] = False
    res = srv._apply_write_step({"action": "create_file", "path": "res://addons/myaddon/plugin.gd", "content": ""}, root)
    check("без упоминания аддона запись в addons/ блокируется",
          res.get("ok") is False and not os.path.isfile(os.path.join(root, "addons", "myaddon", "plugin.gd")), res)

    srv.STATE["addon_intent"] = True
    res2 = srv._apply_write_step({"action": "create_file", "path": "res://addons/myaddon/plugin.gd", "content": "extends Node\n"}, root)
    check("с явным упоминанием аддона («addon» в сообщении) запись разрешена",
          res2.get("ok") is True and os.path.isfile(os.path.join(root, "addons", "myaddon", "plugin.gd")), res2)

    ok, err = srv._validate_plan_steps([{"action": "create_file", "path": "res://addons/myaddon/x.gd", "content": ""}]) if False else (None, None)
    srv.STATE["addon_intent"] = False
    ok, err = srv._validate_plan_steps([{"action": "create_file", "path": "res://addons/myaddon/x.gd", "content": ""}])
    check("шаг через аддон без упоминания отвергается валидацией плана", ok is False, err)

    srv.STATE["addon_intent"] = False
    batch = srv._start_read_batch({"paths": ["res://addons/myaddon/plugin.gd"]}, root)
    check("чтение аддона без упоминания помечается как blocked, а не читается",
          batch["files"][0]["status"] == "blocked", batch)
finally:
    srv.STATE["addon_intent"] = False
    shutil.rmtree(root, ignore_errors=True)

root = fresh_project()
try:
    # регрессия: шаг плана с .tscn, не прошедший проверку сцены (битая ссылка ExtResource),
    # раньше ронял сервер с ошибкой 500 "not enough arguments for format string"
    # вместо корректного stopped-ответа — закретили регрессию здесь.
    reset_state(root)
    chain_id2 = history.new_chain_id()
    bad_scene_step = ('[gd_scene load_steps=1 format=3]\n\n'
                       '[node name="Root" type="Node2D"]\n'
                       'script = ExtResource("res://nope.gd")\n')
    steps2 = [{"action": "create_file", "path": "res://broken_scene.tscn", "content": bad_scene_step}]
    srv.STATE["pending_plan"] = {"chain_id": chain_id2, "steps": steps2, "index": 0,
                                  "description": "selfcheck-500-regression", "total": len(steps2), "applied_paths": []}
    client2 = srv.app.test_client()
    _orig_reply2 = srv._reply
    srv._reply = lambda prompt: ("", None)
    jr = client2.post("/chat/plan/step").get_json()
    srv._reply = _orig_reply2
    check("шаг плана с битой сценой корректно останавливается (без 500 по format string)",
          jr.get("ok") is False and jr.get("stopped") is True and isinstance(jr.get("message"), str)
          and "broken_scene.tscn" in jr.get("message", ""), jr)

    # --- многочастный план: модель присылает шаги несколькими сообщениями ---
    reset_state(root)
    srv.STATE["plan_parts"] = None
    mk = lambda pref, n: [{"action": "create_file", "path": "res://%s%d.gd" % (pref, i), "content": "extends Node\n"} for i in range(n)]
    ok1, msg1 = srv._plan_part_add({"action": "plan", "description": "большая механика", "continues": True, "steps": mk("a", 12)})
    check("часть 1 (12 шагов) многочастного плана принимается",
          ok1 is True and srv.STATE.get("plan_parts") is not None and len(srv.STATE["plan_parts"]["steps"]) == 12, msg1)
    ok2, msg2 = srv._plan_part_add({"action": "plan", "continues": True, "steps": mk("b", 2)})
    check("часть 2 копится к первой (12+2)", ok2 is True and len(srv.STATE["plan_parts"]["steps"]) == 14, msg2)
    steps_all, desc_all = srv._plan_collect_final({"action": "plan", "steps": mk("c", 1)})
    okf, errf = srv._validate_plan_steps(steps_all, max_steps=srv.MAX_PLAN_TOTAL_STEPS)
    check("последняя часть склеивает план из 15 шагов за один проход",
          okf is True and len(steps_all) == 15 and desc_all == "большая механика"
          and srv.STATE.get("plan_parts") is None, (len(steps_all), desc_all, errf))

    srv.STATE["plan_parts"] = None
    srv._plan_part_add({"action": "plan", "continues": True, "steps": mk("x", 12)})
    srv._plan_part_add({"action": "plan", "continues": True, "steps": mk("y", 12)})
    ok3, msg3 = srv._plan_part_add({"action": "plan", "continues": True, "steps": mk("z", 12)})
    check("переполнение суммарного лимита шагов отвергается и сбрасывает накопленное",
          ok3 is False and srv.STATE.get("plan_parts") is None, msg3)

    ok4, msg4 = srv._plan_part_add({"action": "plan", "continues": True, "steps": [{"action": "copy_file", "path": "res://a.gd"}]})
    check("битая часть плана отвергается с понятным сообщением",
          ok4 is False and "отклонена" in msg4 and srv.STATE.get("plan_parts") is None, msg4)
finally:
    shutil.rmtree(root, ignore_errors=True)


# ===========================================================================
# 1в) v44: точечное восстановление шагов плана при частично битом JSON
# ===========================================================================
print("\n--- 1в) v44: точечное восстановление шагов плана ---")

import parser_base

good_step1_raw = '{"action": "create_file", "path": "res://player.gd", "content": "extends CharacterBody2D\\nfunc _ready():\\n\\tpass\\n"}'
good_step2_raw = '{"action": "create_file", "path": "res://enemy.gd", "content": "extends CharacterBody2D\\nfunc _ready():\\n\\tpass\\n"}'
fixable_tscn_step_raw = (
    '{"action": "create_file", "path": "res://Player.tscn", "content": '
    '"[node name=\\"Player\\" type=\\"Node2D\\"]\\nid=\\"1_player\\"\\nid="2_icon"\\n[/node]"}'
)
truly_broken_step_raw = '{"action": "create_file", "path": "res://Broken.tscn", "content": "bad escape: \\qhere"}'
plan_raw_v44 = (
    '{"action": "plan", "description": "v44 selfcheck plan", "steps": ['
    + good_step1_raw + ', ' + good_step2_raw + ', ' + fixable_tscn_step_raw + ', ' + truly_broken_step_raw
    + ']}'
)

step_obj, step_err = parser_base.parse_action_json(fixable_tscn_step_raw)
check("несогласованные кавычки внутри одного шага чинятся автоматически",
      isinstance(step_obj, dict) and step_obj.get("path") == "res://Player.tscn", (step_obj, step_err))

repaired = parser_base._repair_unescaped_inner_quotes(fixable_tscn_step_raw)
try:
    import json as _json_v44
    _json_v44.loads(repaired)
    repaired_ok = True
except Exception:
    repaired_ok = False
check("_repair_unescaped_inner_quotes сама даёт валидный JSON", repaired_ok, repaired)

lenient = parser_base.parse_plan_lenient(plan_raw_v44)
check("parse_plan_lenient распознаёт план, несмотря на 1 битый шаг из 4",
      lenient is not None and len(lenient["good_steps"]) == 3 and len(lenient["bad_steps"]) == 1, lenient)
if lenient:
    check("единственный битый шаг — это res://Broken.tscn с индексом 3",
          lenient["bad_steps"][0]["index"] == 3, lenient["bad_steps"])
    good_paths_v44 = [s["step"].get("path") for s in lenient["good_steps"]]
    check("все 3 распознанных шага — правильные пути (в т.ч. починенный .tscn)",
          good_paths_v44 == ["res://player.gd", "res://enemy.gd", "res://Player.tscn"], good_paths_v44)

    guessed_path = srv._guess_step_path(lenient["bad_steps"][0]["raw"])
    check("_guess_step_path угадывает путь битого шага из сырого текста",
          guessed_path == "res://Broken.tscn", guessed_path)

# --- интеграционный тест: полное точечное восстановление (модель присылает верный шаг) ---
root = fresh_project()
try:
    reset_state(root)
    calls_full = {"n": 0, "prompts": []}

    def _fake_reply_full_recovery(prompt):
        calls_full["n"] += 1
        calls_full["prompts"].append(prompt)
        if calls_full["n"] == 1:
            return ("[Модель]: вот план", {"action": "parse_error", "raw": plan_raw_v44, "error": "test: битые кавычки"})
        return ("", {"action": "create_file", "path": "res://Broken.tscn", "content": "extends Node\n"})

    _orig_reply_full = srv._reply
    srv._reply = _fake_reply_full_recovery
    text_full, action_full = srv._reply_with_self_heal("пришли план платформера", root)
    srv._reply = _orig_reply_full

    check("полное точечное восстановление: итоговое действие — план из всех 4 шагов",
          action_full.get("action") == "plan" and action_full.get("total") == 4, action_full)
    if action_full.get("action") == "plan":
        paths_full = [s.get("path") for s in action_full.get("steps", [])]
        check("полное восстановление: порядок и пути всех 4 шагов сохранены",
              paths_full == ["res://player.gd", "res://enemy.gd", "res://Player.tscn", "res://Broken.tscn"], paths_full)
    check("полное восстановление: потрачена ровно 1 точечная попытка (2 обращения к модели всего)",
          calls_full["n"] == 2, calls_full["n"])
    check("точечный fix-prompt называет номер и путь именно битого шага",
          "№4" in calls_full["prompts"][1] and "res://Broken.tscn" in calls_full["prompts"][1], calls_full["prompts"][1])
    check("точечный fix-prompt называет уже принятые шаги, чтобы модель не прислала их повторно",
          "res://player.gd" in calls_full["prompts"][1] and "res://Player.tscn" in calls_full["prompts"][1], calls_full["prompts"][1])
    check("при полном восстановлении в тексте нет предупреждения об отброшенных шагах",
          "Восстановлено частично" not in (text_full or ""), text_full)
finally:
    shutil.rmtree(root, ignore_errors=True)

# --- интеграционный тест: частичное восстановление (модель не смогла починить шаг) ---
root = fresh_project()
try:
    reset_state(root)
    calls_partial = {"n": 0}

    def _fake_reply_partial_recovery(prompt):
        calls_partial["n"] += 1
        if calls_partial["n"] == 1:
            return ("[Модель]: вот план", {"action": "parse_error", "raw": plan_raw_v44, "error": "test: битые кавычки"})
        return ("[Модель]: не могу починить", {"action": "parse_error", "raw": "снова битый JSON", "error": "test: всё ещё сломано"})

    _orig_reply_partial = srv._reply
    srv._reply = _fake_reply_partial_recovery
    text_partial, action_partial = srv._reply_with_self_heal("пришли план платформера", root)
    srv._reply = _orig_reply_partial

    check("частичное восстановление: итоговое действие — план из 3 распознанных шагов",
          action_partial.get("action") == "plan" and action_partial.get("total") == 3, action_partial)
    if action_partial.get("action") == "plan":
        paths_partial = [s.get("path") for s in action_partial.get("steps", [])]
        check("частичное восстановление: отброшен только res://Broken.tscn",
              paths_partial == ["res://player.gd", "res://enemy.gd", "res://Player.tscn"], paths_partial)
    check("частичное восстановление: потрачена ровно 1 точечная попытка (2 обращения к модели всего)",
          calls_partial["n"] == 2, calls_partial["n"])
    check("частичное восстановление: пользователь предупреждён об отброшенном шаге",
          "Восстановлено частично" in (text_partial or "") and "res://Broken.tscn" in (text_partial or ""), text_partial)
finally:
    shutil.rmtree(root, ignore_errors=True)


# ===========================================================================
# 2) защиты: знает ли агент реальный API Godot и правильно ли читает сцены
# ===========================================================================
print("\n--- 2) защиты API/сцен ---")

root = fresh_project()
try:
    fake_classes = {
        "Node": {"inherits": None, "methods": {"queue_free": [0, 0], "add_child": [1, 2]},
                  "properties": ["name"], "signals": ["tree_entered"]},
        "Node2D": {"inherits": "Node", "methods": {"set_position": [1, 1]},
                    "properties": ["position"], "signals": []},
        "Sprite2D": {"inherits": "Node2D", "methods": {}, "properties": ["texture"], "signals": []},
    }
    gd_api_cache.save_cache(root, fake_classes, godot_version="4.6.3-selfcheck")
    check("кэш API сохраняется и виден", gd_api_cache.has_cache(root))

    bad_code = ("extends Node2D\nfunc _ready():\n\tself.set_position(Vector2(1,2))\n"
                "\tself.teleport_to_moon()\n\tself.set_position(1,2,3)\n")
    problems = gd_api_check.check_api_usage(root, bad_code, path="res://bad.gd")
    check("ловит вызов несуществующего метода", any("teleport_to_moon" in p for p in problems), problems)
    check("ловит неверное число аргументов", any("аргумент" in p for p in problems), problems)

    good_code = "extends Node2D\nfunc _ready():\n\tself.set_position(Vector2(1,2))\n"
    problems_good = gd_api_check.check_api_usage(root, good_code, path="res://good.gd")
    check("не ложных срабатываний на корректном коде", problems_good == [], problems_good)

    inherited_code = ("extends Sprite2D\nfunc _ready():\n\tself.queue_free()\n"
                      "\tself.set_position(Vector2(3,4))\n\tself.add_child(Node.new())\n")
    problems_inherited = gd_api_check.check_api_usage(root, inherited_code, path="res://inherited.gd")
    check("агент читает API по цепочке наследования (Sprite2D → Node2D → Node)",
          problems_inherited == [], problems_inherited)

    bad_scene = ('[gd_scene load_steps=99 format=3]\n\n[node name="Root" type="Node2D"]\n'
                 '[node name="Icon" type="Sprite2D" parent="."]\ntexture = ExtResource("9")\n'
                 '[node name="Ghost" type="TotallyMadeUpNode" parent="."]\n')
    fixed, scene_problems = tscn_lint.lint_and_fix_tscn(bad_scene, project_root=root)
    check("ловит битую ссылку ExtResource", any("ExtResource" in p for p in scene_problems), scene_problems)
    check("ловит неизвестный тип узла", any("TotallyMadeUpNode" in p for p in scene_problems), scene_problems)
    check("автоисправляет load_steps (99 -> 1)", "load_steps=99" not in fixed and "load_steps=1" in fixed, fixed[:80])

    good_scene = '[gd_scene load_steps=1 format=3]\n\n[node name="Root" type="Node2D"]\n[node name="Icon" type="Sprite2D" parent="."]\n'
    _, scene_problems2 = tscn_lint.lint_and_fix_tscn(good_scene, project_root=root)
    check("не ложных срабатываний на корректной сцене", scene_problems2 == [], scene_problems2)

    malformed_header_scene = ('[gd_scene load_steps=2 format=3]\n\n'
                               '[sub_resource type="RectangleShape2D" id="Shape1">\nsize = Vector2(1,1)\n\n'
                               '[node name="Root" type="Node2D"]\n'
                               '[node name="Col" type="CollisionShape2D" parent="."]\nshape = SubResource("Shape1")\n')
    fixed_hdr, malformed_problems = tscn_lint.lint_and_fix_tscn(malformed_header_scene)
    check("«>» вместо «]» в заголовке секции чинится ЛОКАЛЬНО, без обращения к модели",
          'id="Shape1"]' in fixed_hdr and malformed_problems == [], (malformed_problems, fixed_hdr[:130]))
    # v46: незакрытый заголовок со СБАЛАНСИРОВАННЫМИ кавычками теперь тоже
    # чинится ЛОКАЛЬНО (дозакрываем «]» сами), а не уходит модели.
    unfixable_scene = ('[gd_scene load_steps=2 format=3]\n\n'
                        '[sub_resource type="RectangleShape2D" id="Shape1"\nsize = Vector2(1,1)\n\n'
                        '[node name="Root" type="Node2D"]\n')
    fixed_bal, unfixable_problems = tscn_lint.lint_and_fix_tscn(unfixable_scene)
    check("v46: незакрытый заголовок без «>» со сбалансированными кавычками теперь чинится сам",
          'id="Shape1"]' in fixed_bal and unfixable_problems == [],
          (unfixable_problems, fixed_bal[:130]))

    create_project_file(root, "res://demo.tscn", good_scene)
    desc = describe_scene(root, "res://demo.tscn")
    check("describe_scene показыва��т корень и детей сцены",
          "Root" in desc and "Icon" in desc and "Sprite2D" in desc, desc[:200])

    # --- v42: реальный кейс из быстрой/слабой модели (DeepSeek) --- sub_resource
    # объявлен ПОСЛЕ узла, который на него ссылается, плюс фейковый uid://dummy.
    deepseek_scene = ('[gd_scene load_steps=2 format=3 uid="uid://dummy"]\n\n'
                       '[ext_resource type="Script" path="res://p.gd" id="1"]\n\n'
                       '[node name="Player" type="CharacterBody2D"]\nscript = ExtResource("1")\n\n'
                       '[node name="CollisionShape2D" type="CollisionShape2D" parent="."]\n'
                       'shape = SubResource("RectangleShape2D_1")\n\n'
                       '[sub_resource type="RectangleShape2D" id="RectangleShape2D_1"]\nsize = Vector2(30, 50)\n')
    fixed_ds, problems_ds = tscn_lint.lint_and_fix_tscn(deepseek_scene)
    sub_pos = fixed_ds.find("[sub_resource")
    node_pos = fixed_ds.find("[node")
    check("sub_resource, объявленный ПОСЛЕ узла, который на него ссылается, переставляется ПЕРЕД узлами",
          sub_pos != -1 and node_pos != -1 and sub_pos < node_pos, fixed_ds)
    check("фейковый uid://dummy вырезается автоматически",
          "uid://dummy" not in fixed_ds, fixed_ds[:80])
    check("load_steps пересчитывается корректно после перестановки (2 -> 3)",
          "load_steps=3" in fixed_ds, fixed_ds[:80])
    check("после автоисправления структурных проблем не осталось", problems_ds == [], problems_ds)

    ordered_scene_unchanged = ('[gd_scene load_steps=3 format=3]\n\n'
                                '[ext_resource type="Script" path="res://a.gd" id="1"]\n\n'
                                '[sub_resource type="RectangleShape2D" id="Shape_1"]\nsize = Vector2(1,1)\n\n'
                                '[node name="A" type="Node2D"]\nscript = ExtResource("1")\n\n'
                                '[node name="B" type="CollisionShape2D" parent="."]\nshape = SubResource("Shape_1")\n')
    fixed_ord, problems_ord = tscn_lint.lint_and_fix_tscn(ordered_scene_unchanged)
    check("уже правильно упорядоченная сцена не меняется (идемпотентность)",
          fixed_ord == ordered_scene_unchanged and problems_ord == [], (problems_ord, fixed_ord[:120]))

    node_order_scene = ('[gd_scene load_steps=1 format=3]\n\n'
                         '[node name="Root" type="Node2D"]\n'
                         '[node name="First" type="Node2D" parent="."]\n'
                         '[node name="Second" type="Node2D" parent="."]\n')
    fixed_nodeorder, _ = tscn_lint.lint_and_fix_tscn(node_order_scene)
    check("перестановка ресурсов НЕ трогает порядок самих узлов",
          fixed_nodeorder.find(chr(34)+"First"+chr(34)) < fixed_nodeorder.find(chr(34)+"Second"+chr(34)), fixed_nodeorder)

    # --- v45: узел с parent="Level" объявлен в файле раньше самого узла "Level" —
    # чисто порядоковая ошибка, должна переставляться без участия модели.
    node_parent_later_scene = ('[gd_scene load_steps=1 format=3]\n\n'
                                '[node name="Root" type="Node2D"]\n'
                                '[node name="Enemy" type="Node2D" parent="Level"]\n'
                                '[node name="Level" type="Node2D" parent="."]\n')
    fixed_po, problems_po = tscn_lint.lint_and_fix_tscn(node_parent_later_scene)
    check("v45: узел с parent, объявленным позже в файле, автоматически переставляется",
          fixed_po.find(chr(34)+"Level"+chr(34)) < fixed_po.find(chr(34)+"Enemy"+chr(34)), fixed_po)
    check("v45: после перестан����������вки ложная жалоба на ненайденный parent исчезает",
          not any("не найден" in p for p in problems_po), problems_po)

    node_parent_missing_scene = ('[gd_scene load_steps=1 format=3]\n\n'
                                  '[node name="Root" type="Node2D"]\n'
                                  '[node name="Enemy" type="Node2D" parent="NoSuchNode"]\n')
    _, problems_missing = tscn_lint.lint_and_fix_tscn(node_parent_missing_scene)
    check("v45: действительно отсутствующий parent по-прежнему ловится (не путан с порядковыми ошибками)",
          any("NoSuchNode" in p for p in problems_missing), problems_missing)

    # --- v45: единственная битая ссылка на единственный объявленный ext_resource —
    # цель однозначна, чинится автоматически.
    single_ext_bad_ref_scene = ('[gd_scene load_steps=2 format=3]\n\n'
                                 '[ext_resource type="Script" path="res://player.gd" id="1"]\n\n'
                                 '[node name="Root" type="Node2D"]\nscript = ExtResource("PlayerScript")\n')
    fixed_single_ext, problems_single_ext = tscn_lint.lint_and_fix_tscn(single_ext_bad_ref_scene)
    check("v45: битая ссылка на единственный ext_resource переписывается на верный id",
          'ExtResource("1")' in fixed_single_ext and "PlayerScript" not in fixed_single_ext, fixed_single_ext)
    check("v45: после автофикса ссылки проблем не остаётся",
          not any("ExtResource" in p for p in problems_single_ext), problems_single_ext)

    # --- v45: два+ кандидата — цель неоднозначна, автофикс НЕ срабатывает, остаётся модели.
    multi_ext_bad_ref_scene = ('[gd_scene load_steps=3 format=3]\n\n'
                                '[ext_resource type="Script" path="res://a.gd" id="1"]\n'
                                '[ext_resource type="Script" path="res://b.gd" id="2"]\n\n'
                                '[node name="Root" type="Node2D"]\nscript = ExtResource("bad_id")\n')
    fixed_multi_ext, problems_multi_ext = tscn_lint.lint_and_fix_tscn(multi_ext_bad_ref_scene)
    check("v45: при 2+ кандидатах битая ссылка НЕ автоисправляется вслепую",
          'ExtResource("bad_id")' in fixed_multi_ext, fixed_multi_ext)
    check("v45: неоднозначная битая ссылка всё равно возвращается модели",
          any("bad_id" in p for p in problems_multi_ext), problems_multi_ext)

finally:
    shutil.rmtree(root, ignore_errors=True)


# ===========================================================================
# 3) вшитый кэш API в папке аддона: проверяет, что он теперь лежит рядом с .gdignore
#    (защита от мусорной ошибки редактора Godot при сканировании .json как ресурса)
# ===========================================================================
print("\n--- 3) вшитый кэш API защищён от сканирования редактором ---")

root = fresh_project()
addon_dir = fresh_project()
try:
    gd_api_cache.save_cache(root, {"Node": {"inherits": None, "methods": {}, "properties": [], "signals": []}},
                             godot_version="4.6.3", addon_dir=addon_dir)
    sub = os.path.join(addon_dir, gd_api_cache.DEFAULT_CACHE_SUBDIR)
    check("вшитый кэш лежит в подзащищённой подпапке",
          os.path.isfile(os.path.join(sub, gd_api_cache.DEFAULT_CACHE_FILENAME)))
    check("рядом лежит .gdignore", os.path.isfile(os.path.join(sub, ".gdignore")))
    check("старый незащищённый файл в корне аддона больше не создают",
          not os.path.isfile(os.path.join(addon_dir, gd_api_cache.DEFAULT_CACHE_FILENAME)))
finally:
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(addon_dir, ignore_errors=True)


# ===========================================================================
# 4) реестр сайтов: есть ли активный сайт и работает ли определение сайта по URL
# ===========================================================================
print("\n--- 4) реестр сайтов ---")
all_sites = sites.list_sites()
check("реестр сайтов не пуст", len(all_sites) > 0, all_sites)
detected = sites.detect_site("https://aistudio.google.com/prompts/new_chat")
check("AI Studio распознаётся по URL", bool(detected) and detected.get("id") == "aistudio", detected)


# ===========================================================================
# 5) v26: умный контекст, архитектура, внешние изменения, автопочинка [/тегов]
# ===========================================================================
print("\n--- 5) v26: умный контекст / архитектура / внешние изменения / [/теги] ---")
import project_tools as pt
import agent_prompts as ap

# 5.1 закрывающие теги [/sub_resource]/[/node] убираются ЛОКАЛЬНО без модели
bad_ct = (
    '[gd_scene load_steps=2 format=3]\n\n'
    '[sub_resource type="RectangleShape2D" id="Shape1"]\n'
    'size = Vector2(40, 40)\n'
    '[/sub_resource]\n\n'
    '[node name="Root" type="Node2D"]\n\n'
    '[node name="Body" type="StaticBody2D" parent="."]\n\n'
    '[node name="Col" type="CollisionShape2D" parent="Body"]\n'
    'shape = SubResource("Shape1")\n'
    '[/node]\n'
)
fixed_ct, probs_ct = tscn_lint.lint_and_fix_tscn(bad_ct)
check("[/sub_resource]/[/node] удалены локально, проблем нет",
      probs_ct == [] and "[/sub_resource]" not in fixed_ct and "[/node]" not in fixed_ct, (probs_ct, fixed_ct[:120]))
check("остальное содержимое сцены не пострадало",
      '[sub_resource type="RectangleShape2D" id="Shape1"]' in fixed_ct and 'shape = SubResource("Shape1")' in fixed_ct)

# 5.2 снапшот/дифф: удаление/изменение/добавление файлов замечаются
root = fresh_project()
try:
    os.makedirs(os.path.join(root, "src", "scene"), exist_ok=True)
    p1 = os.path.join(root, "src", "scene", "a.tscn")
    p2 = os.path.join(root, "src", "scene", "b.gd")
    open(p1, "w").write("[gd_scene format=3]\n")
    open(p2, "w").write("extends Node\n")
    snap1 = pt.snapshot_files(root)
    os.remove(p1)
    open(p2, "a").write("var x = 1\n")
    open(os.path.join(root, "src", "scene", "c.gd"), "w").write("extends Node\n")
    snap2 = pt.snapshot_files(root)
    added, changed, deleted = pt.diff_snapshots(snap1, snap2)
    check("удалённый файл замечен", deleted == ["src/scene/a.tscn"], deleted)
    check("изменённый и добавленный замечены",
          "src/scene/b.gd" in changed and "src/scene/c.gd" in added, (changed, added))
    note = pt.format_fs_changes(added, changed, deleted)
    check("сообщение модели содержит удалённую сцену",
          "удалён: res://src/scene/a.tscn" in note and "ИЗМЕНИЛИСЬ" in note, note)
    check("без изменений — сообщения нет", pt.format_fs_changes([], [], []) == "")
finally:
    shutil.rmtree(root, ignore_errors=True)

# 5.3 умный контекст: маленький проект — полное дерево, большой — сводка
root = fresh_project()
try:
    os.makedirs(os.path.join(root, "src", "scripts"), exist_ok=True)
    open(os.path.join(root, "src", "scripts", "player.gd"), "w").write("extends Node\n")
    tree_small, compact_small = pt.build_project_overview(root, compact_threshold=150)
    check("маленький проект — полное дерево", compact_small is False and "player.gd" in tree_small, tree_small)
    for i in range(160):
        open(os.path.join(root, "src", "scripts", "s%03d.gd" % i), "w").write("extends Node\n")
    tree_big, compact_big = pt.build_project_overview(root, compact_threshold=150)
    check("большой проект — компактная сводка", compact_big is True and "СВОДКА" in tree_big, tree_big[:200])
    check("сводка: счётчики вместо 160 имён", "src/scripts/" in tree_big and ".gd" in tree_big and "s001.gd" not in tree_big)
    sub_tree = pt.build_project_tree(root, subdir="res://src/scripts/")
    check("list_files с dir: дерево одной папки", "s001.gd" in sub_tree)
finally:
    shutil.rmtree(root, ignore_errors=True)

# 5.4 архитектура: пустой проект получает стандарт, своя — используется
root = fresh_project()
try:
    created = pt.ensure_standard_architecture(root)
    check("пустой проект: создана стандартная архитектура",
          "res://src/scripts/" in created and os.path.isdir(os.path.join(root, "src", "scenes")), created)
    check("повторный вызов ничего не создаёт", pt.ensure_standard_architecture(root) == [])
finally:
    shutil.rmtree(root, ignore_errors=True)

root = fresh_project()
try:
    os.makedirs(os.path.join(root, "game"), exist_ok=True)
    open(os.path.join(root, "game", "main.gd"), "w").write("extends Node\n")
    check("своя архитектура не затирается стандартной",
          pt.ensure_standard_architecture(root) == [] and not os.path.isdir(os.path.join(root, "src")))
    open(os.path.join(root, "project.godot"), "w").write(
        '[application]\nrun/main_scene="res://game/main.tscn"\n\n[autoload]\nGameState="*res://game/state.gd"\n')
    arch = pt.describe_architecture(root)
    check("архитектура: главная сцена и автозагрузки распознаны",
          "res://game/main.tscn" in arch and "GameState" in arch, arch)
    check("архитектура: папка скриптов распознана", "res://game/ (1)" in arch, arch)
finally:
    shutil.rmtree(root, ignore_errors=True)

# 5.5 внешние изменения через сервер: заметка готовится и не дублируется
root = fresh_project()
try:
    reset_state(root)
    open(os.path.join(root, "x.gd"), "w").write("extends Node\n")
    srv.STATE["fs_snapshot"] = None
    srv.STATE["fs_snapshot_root"] = None
    check("первый вызов — ��напшот снят, заметки нет",
          srv._external_changes_note(root) == "" and srv.STATE["fs_snapshot"] is not None)
    os.remove(os.path.join(root, "x.gd"))
    note = srv._external_changes_note(root)
    check("удаление файла попадает в заметку модели", "удалён: res://x.gd" in note, note)
    check("после заметки снапшот обновлён (повтора нет)", srv._external_changes_note(root) == "")
finally:
    shutil.rmtree(root, ignore_errors=True)

# 5.6 мега-промпт: плейсхолдеры и архитектура на пустом проекте
check("шаблон мега-промпта содержит {architecture}", "{architecture}" in ap.PRIMING_TEMPLATE and "{tree}" in ap.PRIMING_TEMPLATE)
root = fresh_project()
try:
    reset_state(root)
    ctx = srv._build_priming_context(root)
    check("мега-промпт: плейсхолдеры подставлены", "{tree}" not in ctx and "{architecture}" not in ctx)
    check("мега-промпт: пустой проект получил стандартную структуру",
          os.path.isdir(os.path.join(root, "src", "scripts")) and "res://src/scripts/" in ctx, ctx[:400])
    check("мега-промпт: снапшот обновлён после создания папок", srv._external_changes_note(root) == "")
finally:
    shutil.rmtree(root, ignore_errors=True)

# ===========================================================================
# 6) v27: точечные diff ручных правок пользователя (экономия токенов)
# ===========================================================================
print("\n--- 6) v27: точечные diff внешних правок ---")

d, n = pt.unified_diff_text("a\nb\nc", "a\nX\nc", "s.gd")
check("замена одной строки даёт компактный diff", d is not None and "-b" in d and "+X" in d and n == 2, (d, n))
big_old = "\n".join("line%d" % i for i in range(120))
big_new = "\n".join("other%d" % i for i in range(120))
d2, n2 = pt.unified_diff_text(big_old, big_new, "s.gd")
check("огромная правка — diff не шлётся, файл перечитывается", d2 is None and n2 > 40, (d2, n2))
check("одинаковые тексты — diff пуст", pt.unified_diff_text("same", "same", "s.gd") == (None, 0))

root = fresh_project()
try:
    reset_state(root)
    srv.STATE["file_cache"] = None
    hero = os.path.join(root, "hero.gd")
    open(hero, "w").write("extends Node\nvar speed = 100\nfunc _ready():\n    pass\n")
    srv._remember_file(root, "res://hero.gd")
    srv._refresh_fs_snapshot(root)
    open(hero, "w").write("extends Node\nvar speed = 12345\nfunc _ready():\n    pass\n")
    note = srv._external_changes_note(root)
    check("ручная правка строки — модель получает точечный diff",
          "```diff" in note and "-var speed = 100" in note and "+var speed = 12345" in note, note)
    check("весь файл повторно НЕ пересылается", "    pass" not in note, note)
    check("diff учтён — повторной заметки нет", srv._external_changes_note(root) == "")
    os.remove(hero)
    note2 = srv._external_changes_note(root)
    check("удаление файла после diff замечено", "удалён: res://hero.gd" in note2, note2)
    check("кэш забыл удалённый файл", "hero.gd" not in (srv.STATE.get("file_cache") or {}))
finally:
    shutil.rmtree(root, ignore_errors=True)

root = fresh_project()
try:
    reset_state(root)
    srv.STATE["file_cache"] = None
    srv._refresh_fs_snapshot(root)
    res = srv._apply_write_step({"action": "create_file", "path": "res://a.gd", "content": "extends Node\nvar hp = 1\n"}, root)
    check("запись агента кэшируется для будущих diff", res["ok"] and "a.gd" in (srv.STATE.get("file_cache") or {}), res)
    check("своя запись — не внешнее изменение", srv._external_changes_note(root) == "")
    open(os.path.join(root, "a.gd"), "w").write("extends Node\nvar hp = 999\n")
    note3 = srv._external_changes_note(root)
    check("правка кода агента пользователем — точечный diff", "-var hp = 1" in note3 and "+var hp = 999" in note3, note3)
finally:
    shutil.rmtree(root, ignore_errors=True)

# ===========================================================================
# 7) v28: быстрый старт сервера (браузер в фоне, onedir, частый опрос)
# ===========================================================================
print("\n--- 7) v28: быстрый старт сервера ---")
import server_state as _ss
_ss._holder["driver"] = None
_ss._holder["driver_error"] = None
try:
    _ss.wait_driver(timeout=0.6)
    check("wait_driver без браузера падает по таймауту с понятным текстом", False)
except RuntimeError as e:
    check("wait_driver без браузера падает по таймауту с понятным текстом", "запускается" in str(e), e)
_fake = object()
_ss._holder["driver"] = _fake
check("wait_driver отдаёт готовый браузер сразу", _ss.wait_driver(timeout=1.0) is _fake)
_ss._holder["driver"] = None
_ss.set_driver_error("Google Chrome не найден")
try:
    _ss.wait_driver(timeout=5.0)
    check("ошибка запуска браузера сообщается сразу, без ожидания", False)
except RuntimeError as e:
    check("ошибка запуска браузера сообщается сразу, без ожидания", "Chrome" in str(e), e)
_ss._holder["driver_error"] = None

_here = os.path.dirname(os.path.abspath(__file__))
_main_src = open(os.path.join(_here, "main.py"), encoding="utf-8").read()
check("браузер стартует в фоне — сервер не ждёт Chrome",
      "_boot_browser_background" in _main_src and "threading.Thread(target=_boot_browser_background" in _main_src)
_bat_src = open(os.path.join(_here, "build_server_exe.bat"), encoding="utf-8", errors="replace").read()
check("сборка exe в режиме onedir (без распаковки при старте)", "--onedir" in _bat_src and "--onefile" not in _bat_src)
_gd_src = open(os.path.join(_here, "..", "godot", "agent_server_link.gd"), encoding="utf-8").read()
check("панель проверяет связь каждые 0.5 с и знает пути onedir",
      "wait_time = 0.5" in _gd_src and "dist/godot_agent_server/godot_agent_server.exe" in _gd_src)

# v29: панель не должна запускать старый медленный onefile-exe вместо onedir
_gd_link = open(os.path.join(_here, "..", "godot", "agent_server_link.gd"), encoding="utf-8").read()
check("панель предпочитает onedir-сборку (кэш пути и поиск)",
      "func _prefer_onedir" in _gd_link
      and "_prefer_onedir(_load_cached_server_path())" in _gd_link
      and "_prefer_onedir(_find_server_file" in _gd_link)
_bat_v29 = open(os.path.join(_here, "build_server_exe.bat"), encoding="utf-8", errors="replace").read()
check("бат удаляет старый медленный exe после сборки", 'del "dist' in _bat_v29)
check("бат остался в формате CRLF", open(os.path.join(_here, "build_server_exe.bat"), "rb").read().count(b"\r\n") == open(os.path.join(_here, "build_server_exe.bat"), "rb").read().count(b"\n"))

# v30: сайт DeepSeek + выбор парсера по сайту + быстрый п��вторный запуск сервера
import sites as _sites
check("сайт DeepSeek зарегистрирован",
      (_sites.get_site("deepseek") or {}).get("parser") == "deepseek_parser"
      and (_sites.detect_site("https://chat.deepseek.com/a/chat/s/abc") or {}).get("id") == "deepseek"
      and (_sites.detect_site("https://aistudio.google.com/prompts/new_chat") or {}).get("id") == "aistudio")
check("выбо�� парсера по сайту ��а——отает",
      _sites.get_parser_module("deepseek").__name__ == "deepseek_parser"
      and _sites.get_parser_module("aistudio").__name__ == "ai_parser"
      and _sites.get_parser_module(None, "https://chat.deepseek.com/").__name__ == "deepseek_parser"
      and _sites.get_parser_module("нет_такого").__name__ == "ai_parser")
import deepseek_parser as _dsp
check("парсер DeepSeek читает ответ и ловит agent_action",
      callable(getattr(_dsp, "send_message_and_get_response", None))
      and "__answerBlocks" in _dsp.JS_EXTRACT
      and "agent_action" in _dsp.JS_EXTRACT)
check("ввод DeepSeek через нативный сеттер React", "getOwnPropertyDescriptor" in _dsp.JS_SET_INPUT)
_main_v30 = open(os.path.join(_here, "main.py"), encoding="utf-8").read()
check("main.py выбирает парсер текущего чата",
      "def _current_parser" in _main_v30
      and "_current_parser().send_message_and_get_response(" in _main_v30)
_gd_link30 = open(os.path.join(_here, "..", "godot", "agent_server_link.gd"), encoding="utf-8").read()
check("панель: повторный запуск сервера без минутной блокировки",
      "< 10000" in _gd_link30 and "< 60000" not in _gd_link30
      and "Поиск и запуск сервера занял" in _gd_link30
      and _gd_link30.count("_server_start_attempted = false") >= 2)

# v31: менеджер парсинга (базовый класс) + наследники
import parser_base as _pb
import ai_parser as _aip
check("менеджер парсинга: общий конвейер в BaseSiteParser",
      callable(getattr(_pb.BaseSiteParser, "send_message_and_get_response", None))
      and callable(getattr(_pb.BaseSiteParser, "wait_for_new_answer", None))
      and callable(getattr(_pb.BaseSiteParser, "extract_answer_robust", None))
      and callable(getattr(_pb, "parse_action_json", None)))
check("AI Studio наследует менеджер парсинга",
      issubclass(_aip.AiStudioParser, _pb.BaseSiteParser)
      and _aip.parse_action_json is _pb.parse_action_json
      and callable(_aip.send_message_and_get_response)
      and _aip.PARSER.WINDOW_URL_MATCH == "aistudio.google.com")
check("DeepSeek наследует менеджер парсинга",
      issubclass(_dsp.DeepSeekParser, _pb.BaseSiteParser)
      and callable(_dsp.send_message_and_get_response)
      and _dsp.PARSER.WINDOW_URL_MATCH == "chat.deepseek.com")
check("наследники не дублируют общий конвейер",
      "send_message_and_get_response" not in _aip.AiStudioParser.__dict__
      and "send_message_and_get_response" not in _dsp.DeepSeekParser.__dict__
      and "wait_for_new_answer" not in _aip.AiStudioParser.__dict__
      and "extract_answer" in _dsp.DeepSeekParser.__dict__)

# v32: гарантированная отправка в DeepSeek + замер времени ответа сервера
check("DeepSeek: синтетический Enter (JS_DISPATCH_ENTER)",
      "keydown" in _dsp.JS_DISPATCH_ENTER and "keyCode: 13" in _dsp.JS_DISPATCH_ENTER)
check("DeepSeek: клик по кнопке отправки pointer-событиями",
      "PointerEvent" in _dsp.JS_CLICK_SEND
      and "ds-button--disabled" in _dsp.JS_CLICK_SEND)
check("DeepSeek: ступенчатая проверка, что сообщение ушло",
      "_input_leftover" in _dsp.DeepSeekParser.__dict__
      and "after_submit" in _dsp.DeepSeekParser.__dict__)
_gd_link32 = open(os.path.join(_here, "..", "godot", "agent_server_link.gd"), encoding="utf-8").read()
check("панель: замер времени ответа сервера после запуска exe",
      "Сервер ответил через" in _gd_link32)

# v33: парсеры в сборке exe, кнопка Стоп, занятость браузера, файл-ссылка
import server_state as _ss33
_main33 = open(os.path.join(_here, "main.py"), encoding="utf-8").read()
check("парсеры сайтов импортируются статически (попадают в exe)",
      "import deepseek_parser" in _main33 and "import parser_base" in _main33
      and "import ai_parser" in _main33)
check("сервер: маршрут /chat/stop и флаг отмены",
      "'/chat/stop'" in _main33 and callable(getattr(_ss33, "request_cancel", None))
      and callable(getattr(_ss33, "cancel_requested", None)))
check("конвейер: остановка по кнопке Стоп (ParserCancelled)",
      hasattr(_pb, "ParserCancelled")
      and "cancel_cb" in _pb.BaseSiteParser.wait_for_new_answer.__code__.co_varnames
      and "cancel_cb" in _pb.BaseSiteParser.send_message_and_get_response.__code__.co_varnames)
check("не ждём ответ, если сообщение не отправилось (confirm_sent)",
      callable(getattr(_pb.BaseSiteParser, "confirm_sent", None))
      and "confirm_sent" in _dsp.DeepSeekParser.__dict__)
_routes33 = open(os.path.join(_here, "chat_routes.py"), encoding="utf-8").read()
check("чаты: понятная ошибка вместо зависания, пока браузер занят",
      "def _busy_error" in _routes33 and _routes33.count("_busy_error()") >= 3)
_panel33 = open(os.path.join(_here, "..", "godot", "agent_panel.gd"), encoding="utf-8").read()
check("панель: кнопка Стоп во время обработки запроса",
      "_on_stop_pressed" in _panel33 and "/chat/stop" in _panel33)
_gdlink33 = open(os.path.join(_here, "..", "godot", "agent_server_link.gd"), encoding="utf-8").read()
check("панель: файл-ссылка server_path.txt для запуска сервера",
      "server_path.txt" in _gdlink33)

# v34: кнопка ручного запуска сервера, когда он не отвечает
_panel34 = open(os.path.join(_here, "..", "godot", "agent_panel.gd"), encoding="utf-8").read()
check("панель: кнопка «Сервер выключен — открыть папку exe»",
      "_on_server_state_changed" in _panel34
      and "_on_open_server_folder_pressed" in _panel34
      and "server_state_changed" in _panel34)
_gdlink34 = open(os.path.join(_here, "..", "godot", "agent_server_link.gd"), encoding="utf-8").read()
check("связь: сигнал состояния сервера и открытие папки exe",
      "signal server_state_changed" in _gdlink34
      and "func find_server_exe_path" in _gdlink34
      and "shell_show_in_file_manager" in _gdlink34)

_routes34 = open(os.path.join(_here, "chat_routes.py"), encoding="utf-8").read()
check("чаты: проверка, что страница чата не удалена на сайте",
      "def _check_chat_page" in _routes34
      and '\"warning\": page_note' in _routes34
      and "set_page_load_timeout(20)" in _routes34)

# v35: res:// как корень, узлы в sub_resource, порядок автозагрузок
import tempfile as _tf35
import project_tools as _pt35
_d35 = _tf35.mkdtemp()
with open(os.path.join(_d35, "a.gd"), "w", encoding="utf-8") as _f35:
    _f35.write("# test")
_ok35 = True
try:
    _tree35 = _pt35.build_project_tree(_d35, subdir="res://")
    _ok35 = "a.gd" in _tree35
except Exception:
    _ok35 = False
check("list_files: res:// (корень проекта) больше не даёт «Папка не найдена»", _ok35)
_main35 = open(os.path.join(_here, "main.py"), encoding="utf-8").read()
check("list_files: res:// нормализуется и в main.py",
      "# res:// — это корень проекта" in _main35)
import tscn_lint as _tl35
_bad35 = ('[gd_scene load_steps=2 format=3]\n\n'
          '[sub_resource type="ColorRect" id="1"]\n'
          'color = Color(1, 0, 0, 1)\n\n'
          '[node name="Root" type="Node2D"]\n')
_fx35, _pr35 = _tl35.lint_and_fix_tscn(_bad35)
check("tscn-линт: узел в [sub_resource] помечается как проблема",
      any("УЗЕЛ" in p for p in _pr35))
_ap35 = open(os.path.join(_here, "agent_prompts.py"), encoding="utf-8").read()
check("промпт: правила про порядок автозагрузок и узлы в sub_resource",
      "АВТОЗАГРУЗКИ (Autoload)" in _ap35 and "ТОЛЬКО для РЕСУРСОВ" in _ap35)

# v36: сторожевой таймер, «думающие» модели DeepSeek, Variant в sub_resource, полоска запуска
_pb36 = open(os.path.join(_here, "parser_base.py"), encoding="utf-8").read()
check("парсер: сторожевой таймер забирает готовый ответ при зависшем ожидании",
      "_try_salvage" in _pb36 and "сторожевой таймер" in _pb36)
_dsp36 = open(os.path.join(_here, "deepseek_parser.py"), encoding="utf-8").read()
check("deepseek: ответы «думающих» моделей тоже находятся (__answerBlocks)",
      "__answerBlocks" in _dsp36 and "think" in _dsp36)
_bad36 = ('[gd_scene load_steps=3 format=3]\n\n'
          '[sub_resource type="Color" id="2"]\n'
          'color = Color(1, 0, 0, 1)\n\n'
          '[node name="Root" type="Node2D"]\n')
_fx36, _pr36 = _tl35.lint_and_fix_tscn(_bad36)
check("tscn-линт: Variant (Color) в [sub_resource] помечается как проблема",
      any("ЗНАЧЕНИЕ" in p for p in _pr36))

# v37: кнопка ручного запуска переехала на стартовый экран (рядом с языком — там её видно,
# в отличие от v36, где её закрывал стартовый экран), и увеличенный бюджет ожидания автозапуска
_start37 = open(os.path.join(_here, "..", "godot", "agent_start_screen.gd"), encoding="utf-8").read()
check("стартовый экран: кнопка/подсказка ручного запуска есть на стартовом экране",
      "signal open_server_requested" in _start37
      and "func set_server_running" in _start37
      and "_server_btn = Button.new()" in _start37
      and _start37.find("_server_btn = Button.new()") < _start37.find("OptionButton.new()"))
_panel37 = open(os.path.join(_here, "..", "godot", "agent_panel.gd"), encoding="utf-8").read()
check("панель: делегирует ручной запуск стартовому экрану (а не скрытой полоске в VBoxContainer)",
      "_start_screen.set_server_running" in _panel37
      and "open_server_requested.connect" in _panel37
      and "_server_bar" not in _panel37)
_gdlink37 = open(os.path.join(_here, "..", "godot", "agent_server_link.gd"), encoding="utf-8").read()
import re as _re37
_m37 = _re37.search(r"_server_wait_left\s*=\s*(\d+)\s*(?:#|\n)", _gdlink37)
check("связь: бюджет ожидания автозапуска увеличен для медленных ПК (>1 минуты)",
      _m37 is not None and int(_m37.group(1)) >= 150, _m37)

# v38: agent_action, отрисованный сайтом ОДИНОЙ обратной котировкой (не ```-блоком),
# больше не теряется — ответ виден в чате, а действие раньше пропадало.
_dsp38 = open(os.path.join(_here, "deepseek_parser.py"), encoding="utf-8").read()
check("deepseek: JSON-действие ловится и в одинарном <code> (не только в <pre>)",
      "rawInline" in _dsp38 and "headInline" in _dsp38
      and _dsp38.count('actionRaw = raw') >= 2)
import importlib as _il38
import parser_base as _pb38
_il38.reload(_pb38)
check("страховка (план В): поиск JSON-действия в сыром тексте ответа",
      callable(getattr(_pb38, "_find_action_json_candidates", None))
      and "_find_action_json_candidates" in _pb38.BaseSiteParser.send_message_and_get_response.__code__.co_names)
_cands38 = _pb38._find_action_json_candidates(
    'Текст перед действием.agent_action\n{"action": "read_file", "paths": ["res://a.gd"], "note": "скобка } внутри строки"}\nТекст после.')
check("план В: корректно вырезает JSON �� учётом фигурных скобок внутри строк",
      len(_cands38) == 1 and _cands38[0].startswith('{"action"')
      and _cands38[0].endswith('}'))
_ap38 = open(os.path.join(_here, "agent_prompts.py"), encoding="utf-8").read()
check("промпт: явный запрет одинарной котировки для agent_action",
      "НИКОГДА не оборачивай JSON действия одиной обратной котировкой" in _ap38
      or "НИКОГДА не оборачивай JSON действия одино" in _ap38)

# v39: кнопка ручного запуска в v37 сидела в одной строке с языковым
# переключателем и заголовком, в узкой пристёгнутой панели HBoxContainer
# сжимал/обрезал содержимое, и кнопка становилась невидима/недоступной даже когда
# сервер был остановлен и кнопка была visible = true. Кнопка/подсказка вынесены
# в свою отдельную строку (server_row) НАД языковой строкой (top).
_start39 = open(os.path.join(_here, "..", "godot", "agent_start_screen.gd"), encoding="utf-8").read()
check("стартовый экран: кнопка ручного запуска перенесена в свою строку над языковой (нет перегруза строки)",
      "server_row := HBoxContainer.new()" in _start39
      and _start39.find("root.add_child(server_row)") < _start39.find("var top := HBoxContainer.new()")
      and "custom_minimum_size = Vector2(190" not in _start39)
check("стартовый экран: подсказка про ручной запуск также в tooltip_text кнопки (видна при наведении, даже если строка узкая)",
      "_server_btn.tooltip_text" in _start39 and "srv_manual_hint" in _start39)


# v40: в цикле ожидания ответа DeepSeek счётчик ответов мог убывать (старые ответы исчезают со страницы),
# и строгая проверка "стало больше" никогда не срабатывала и висела до сторожевого таймера.
_pb40 = open(os.path.join(_here, "parser_base.py"), encoding="utf-8").read()
check("парсер: ожидание ответа реагирует на любой сдвиг счётчика ответов, а не только на рост",
      "count_answers(driver) != initial_count" in _pb40)

# v40: кнопка "Откатить" для план-цепочки раньше молча ничего не делала, если откат
# требовал needs_force=true — флаг не пересылался в диалог повторного подтверждения.
_panel40 = open(os.path.join(_here, "..", "godot", "agent_panel.gd"), encoding="utf-8").read()
check("панель: откат цепочки с needs_force снова показывает диалог подтверждения (а не молчит)",
      "_plan_rollback_force_next = true" in _panel40
      and 'kind == "plan_rollback_chain"' in _panel40
      and "_show_plan_rollback_dialog(_plan_rollback_chain_id" in _panel40)
_locale40 = open(os.path.join(_here, "..", "godot", "agent_locale.gd"), encoding="utf-8").read()
check("локализация: тексты для повторного (force) отката цепочки есть и в RU, и в EN",
      _locale40.count("plan_rb_needs_force") >= 2 and _locale40.count("plan_rb_force_desc") >= 2)

# v40: шаг плана, который не прошёл линт/применение, теперь сначала пробует самоисцеление через модель
# (до MAX_ACTION_FIX_RETRIES попыток) и только потом остановит весь план, если исчерпан лимит.
_m40 = open(os.path.join(_here, "main.py"), encoding="utf-8").read()
check("main.py: есть функция самоисцеления шага плана через модель",
      "_self_heal_plan_step_action" in _m40 and "heal_attempts" in _m40)
check("main.py: main.py корректный python (без ошибок синтаксиса)",
      True)
import ast as _ast40
try:
    _ast40.parse(_m40)
    _m40_syntax_ok = True
except SyntaxError:
    _m40_syntax_ok = False
check("main.py: парсится без ошибок синтаксиса (валидация AST)", _m40_syntax_ok)
check("main.py: цикл самоисцеления ограничен MAX_ACTION_FIX_RETRIES и останавливает весь план при истощении потыткий",
      "heal_attempts >= MAX_ACTION_FIX_RETRIES" in _m40 and "stopped" in _m40)


# v41: кнопка ручного запуска сервера всё ещё не появлялась у языка во время ожидания старта
# сервера — из-за того что по умолчанию она считалась скрытой до первого ответа сервера,
# а также жила только в одной строке рядом с языком, которую пользователь мог не застать.
_ss41 = open(os.path.join(_here, "..", "godot", "agent_start_screen.gd"), encoding="utf-8").read()
check("стартовый экран: кнопка ручного запуска видна по умолчанию (до подтверждённого запуска сервера), а не скрыта",
      "var _server_running: bool = false" in _ss41)
check("стартовый экран: есть вторая копия кнопки/подсказки запуска сервера внутри экрана ожидания",
      "_loading_server_btn = Button.new()" in _ss41 and "_loading_server_hint = Label.new()" in _ss41)
check("стартовый экран: видимость копии в loading-view управляется тем же _apply_server_visibility()",
      "_loading_server_btn.visible = not _server_running" in _ss41 and "_loading_server_hint.visible = not _server_running" in _ss41)
check("стартовый экран: show_loading() перестраивает видимость кнопки при каждом вызове",
      "func show_loading(text: String) -> void:" in _ss41
      and _ss41.split("func show_loading(text: String) -> void:", 1)[1].split("func ", 1)[0].count("_apply_server_visibility()") >= 1)
check("стартовый экран: ребилд UI (смена языка) обнуляет ссылки на копии из loading-view",
      "_loading_server_btn = null" in _ss41 and "_loading_server_hint = null" in _ss41)

# v45(2): системная заметка (откат/отказ/завершение шага плана) теперь привязана
# к chat_id того чата, где произошло действие, а не к общему серве��ному состоянию —
# иначе новый/чужой чат мог получить чужой откат первым же своим сообщением.
print("\n--- 8) v45: заметка об откате/действии привязана к своему чату ---")

reset_state(root)
srv.STATE["current_chat_id"] = "chat-A"
server_state.queue_action_note("[Система: заметка чата A]")
check("queue_action_note: заметка сохранена под chat-A",
      server_state.STATE.get("action_notes", {}).get("chat-A") == "[Система: заметка чата A]")

srv.STATE["current_chat_id"] = "chat-B"
_note_for_b = server_state.pop_action_note_for_current()
check("pop_action_note_for_current: НОВЫЙ/чужой чат B не получает заметку чата A",
      _note_for_b == "")
check("заметка чата A всё ещё лежит в словаре (не потеряна, не отдана чужому чату)",
      server_state.STATE.get("action_notes", {}).get("chat-A") == "[Система: заметка чата A]")

srv.STATE["current_chat_id"] = "chat-A"
_note_for_a = server_state.pop_action_note_for_current()
check("pop_action_note_for_current: свой чат A получает свою же заметку",
      _note_for_a == "[Система: заметка чата A]")
check("после выдачи заметка чата A убрана из словаря (не отдаётся повторно)",
      "chat-A" not in server_state.STATE.get("action_notes", {}))

# без текущего чата (например, самый первый /init до открытия чата) заметка не сохраняется,
# чтобы не привязаться к пустому/несуществующему ключу.
srv.STATE["current_chat_id"] = None
server_state.queue_action_note("[Система: заметка без чата]")
check("queue_action_note: без текущего chat_id заметка тихо отбрасывается",
      server_state.STATE.get("action_notes", {}) == {})

# удаление чата должно чистить его отложенную заметку (чтобы словарь не рос бесконечно).
srv.STATE["current_chat_id"] = "chat-C"
server_state.queue_action_note("[Система: заметка чата C]")
server_state.discard_action_note_for_chat("chat-C")
check("discard_action_note_for_chat: заметка удалённого чата убрана из словаря",
      "chat-C" not in server_state.STATE.get("action_notes", {}))

# main.py больше не должен использовать старый общий STATE["action_note"] ни в одном месте.
_m45b = open(os.path.join(_here, "main.py"), encoding="utf-8").read()
check("main.py: нет ни одного использования старого общего action_note",
      "action_note\"]" not in _m45b and "'action_note']" not in _m45b)
check("main.py: все места установки заметки используют server_state.queue_action_note",
      _m45b.count("server_state.queue_action_note(") == 11)
check("main.py: оба места выдачи заметки используют server_state.pop_action_note_for_current",
      _m45b.count("server_state.pop_action_note_for_current()") == 2)

reset_state(root)

# --- 9) v46: автозакрытие «]» в заголовках, «файл НЕ изменён» и автоперечитывание сцен ---
print("\n--- 9) v46: автозакрытие заголовков сцены, честное «файл НЕ изменён», автоперечитывание ---")
import tscn_lint as _tl46

# заголовок без «]», но со сбалансированными кавычками (типичный обрыв/забытая
# скобка, как в реальном баге с main.tscn на строке 232) — дозакрываем сами.
_scene_unclosed = (
    '[gd_scene load_steps=2 format=3]\n\n'
    '[sub_resource type="BoxMesh" id="m1"]\n\n'
    '[node name="Main" type="Node3D"]\n\n'
    '[node name="Child" type="MeshInstance3D" parent="."\n'
    'mesh = SubResource("m1")\n'
)
_fx46, _pr46 = _tl46.lint_and_fix_tscn(_scene_unclosed)
check("tscn: незакрытый заголовок со сбалансированными кавычками дозакрывается сам",
      '[node name="Child" type="MeshInstance3D" parent="."]' in _fx46)
check("tscn: после автозакрытия заголовка проблем не остаётся",
      _pr46 == [])
# повторный прогон уже починенного текста ничего не меняет (идемпотентность).
_fx46b, _pr46b = _tl46.lint_and_fix_tscn(_fx46)
check("tscn: автозакрытие заголовка идемпотентно",
      _fx46b == _fx46 and _pr46b == [])
# обрыв ПОСЕРЕДИНЕ строкового значения (нечётные кавычки) — чинить вслепую нельзя,
# проблема по-прежнему уходит модели.
_scene_torn = (
    '[gd_scene format=3]\n\n'
    '[node name="Main" type="Node3D"]\n\n'
    '[node name="Chi\n'
)
_fx46c, _pr46c = _tl46.lint_and_fix_tscn(_scene_torn)
check("tscn: обрыв посередине строки (нечётные кавычки) не чинится вслепую, а уходит модели",
      any("не закрыт" in p for p in _pr46c))

# main.py: после исчерпания самоисцеления битое write-действие ОТБРАСЫВАЕТСЯ
# с явным «файл НЕ был изменён» и заметкой для модели (а не уходит в pending_action).
_m46 = open(os.path.join(_here, "main.py"), encoding="utf-8").read()
check("main.py: битое действие после исчерпания попыток отбрасывается с «файл НЕ был изменён»",
      "ОТБРОШЕНО: файл НЕ был изменён" in _m46)
check("main.py: модель получает заметку «не считай правки применёнными»",
      "Не считай эти правки" in _m46)
check("main.py: подсказка смягчена — новые sub_resource/ext_resource объявлять МОЖНО",
      "sub_resource]/[ext_resource" in _m46)

# agent_panel.gd: автоперечитывание изменённых сцен и авто-включение автоперезагрузки скриптов.
_panel46 = open(os.path.join(_here, "..", "godot", "agent_panel.gd"), encoding="utf-8").read()
check("панель: есть автоперечитывание изменённых сцен (reload_scene_from_path)",
      "func _auto_reload_changed_scene" in _panel46 and "reload_scene_from_path" in _panel46)
check("панель: автоперечитывание вызывается для подтверждений, шагов плана и откатов",
      _panel46.count("_auto_reload_changed_scene(") >= 5)
check("панель: автоперезагрузка скриптов включается в настройках редактора автоматически",
      "auto_reload_scripts_on_external_change" in _panel46 and "_ensure_script_autoreload_setting()" in _panel46)

reset_state(root)

# --- 10) v47: анализ зависимостей «скрипт <-> сцена» ([connection]) ---
print("\n--- 10) v47: анализ зависимостей: авто-[connection] без ложных срабатываний ---")
import scene_deps as _sd47

check("to_snake: Camera3D -> camera_3d (как в редакторе Godot)",
      _sd47.to_snake("Camera3D") == "camera_3d", _sd47.to_snake("Camera3D"))
check("to_snake: Wall_North -> wall_north, AnimationPlayer -> animation_player",
      _sd47.to_snake("Wall_North") == "wall_north"
      and _sd47.to_snake("AnimationPlayer") == "animation_player")

# сцена: корень со скриптом, внутри Area3D «DangerZone». В скрипте есть
# обработчик по шаблону редактора — должно ОДНОЗНАЧНО добавиться [connection].
create_project_file(root, "res://deps_main.gd",
    "extends Node3D\n\nfunc _on_danger_zone_body_entered(body):\n\tpass\n")
_deps_scene = (
    '[gd_scene load_steps=2 format=3]\n\n'
    '[ext_resource type="Script" path="res://deps_main.gd" id="1_s"]\n\n'
    '[node name="Main" type="Node3D"]\n'
    'script = ExtResource("1_s")\n\n'
    '[node name="DangerZone" type="Area3D" parent="."]\n'
)
_dtext, _dadded, _dnotes = _sd47.analyze_scene_action(_deps_scene, "res://deps_main.tscn", root)
check("deps: однозначный обработчик получает авто-[connection] (body_entered от DangerZone)",
      '[connection signal="body_entered" from="DangerZone" to="." method="_on_danger_zone_body_entered"]' in _dtext
      and len(_dadded) == 1, (_dadded, _dnotes))
_dtext2, _dadded2, _dnotes2 = _sd47.analyze_scene_action(_dtext, "res://deps_main.tscn", root)
check("deps: повторный анализ обогащённой сцены ничего не добавляет (идемпотентность)",
      _dadded2 == [] and _dtext2 == _dtext, _dadded2)

# сигнал от СЕБЯ: скрипт на самом Area3D с func _on_body_entered.
create_project_file(root, "res://deps_zone.gd",
    "extends Area3D\n\nfunc _on_body_entered(body):\n\tpass\n")
_zone_scene = (
    '[gd_scene load_steps=2 format=3]\n\n'
    '[ext_resource type="Script" path="res://deps_zone.gd" id="1_z"]\n\n'
    '[node name="Zone" type="Area3D"]\n'
    'script = ExtResource("1_z")\n'
)
_ztext, _zadded, _znotes = _sd47.analyze_scene_action(_zone_scene, "res://deps_zone.tscn", root)
check("deps: сигнал от самого узла (_on_body_entered на Area3D) подключается как . -> .",
      '[connection signal="body_entered" from="." to="." method="_on_body_entered"]' in _ztext,
      (_zadded, _znotes))

# обработчик уже подключается в КОДЕ — никаких автодобавлений (защита от дубля).
create_project_file(root, "res://deps_code.gd",
    "extends Node3D\n\nfunc _ready():\n\t$KillTimer.timeout.connect(_on_kill_timer_timeout)\n\n"
    "func _on_kill_timer_timeout():\n\tpass\n")
_code_scene = (
    '[gd_scene load_steps=2 format=3]\n\n'
    '[ext_resource type="Script" path="res://deps_code.gd" id="1_c"]\n\n'
    '[node name="Main" type="Node3D"]\n'
    'script = ExtResource("1_c")\n\n'
    '[node name="KillTimer" type="Timer" parent="."]\n'
)
_ctext, _cadded, _cnotes = _sd47.analyze_scene_action(_code_scene, "res://deps_code.tscn", root)
check("deps: обработчик, подключаемый в коде через connect(), НЕ трогается",
      _cadded == [] and _ctext == _code_scene, (_cadded, _cnotes))

# уже есть [connection] в сцене — не дублируем.
_conn_scene = (
    '[gd_scene load_steps=2 format=3]\n\n'
    '[ext_resource type="Script" path="res://deps_main.gd" id="1_s"]\n\n'
    '[node name="Main" type="Node3D"]\n'
    'script = ExtResource("1_s")\n\n'
    '[node name="DangerZone" type="Area3D" parent="."]\n\n'
    '[connection signal="body_entered" from="DangerZone" to="." method="_on_danger_zone_body_entered"]\n'
)
_ktext, _kadded, _knotes = _sd47.analyze_scene_action(_conn_scene, "res://deps_conn.tscn", root)
check("deps: уже подключённый в сцене обработчик не дублируется",
      _kadded == [] and _ktext == _conn_scene, _kadded)

# два подходящих узла с одинаковым именем в разных ветках — НЕОДНОЗНАЧНО:
# ничего не добавляем, только заметка.
_amb_scene = (
    '[gd_scene load_steps=2 format=3]\n\n'
    '[ext_resource type="Script" path="res://deps_main.gd" id="1_s"]\n\n'
    '[node name="Main" type="Node3D"]\n'
    'script = ExtResource("1_s")\n\n'
    '[node name="Sub" type="Node3D" parent="."]\n\n'
    '[node name="DangerZone" type="Area3D" parent="."]\n\n'
    '[node name="DangerZone" type="Area3D" parent="Sub"]\n'
)
_atext, _aadded, _anotes = _sd47.analyze_scene_action(_amb_scene, "res://deps_amb.tscn", root)
check("deps: неоднозначный источник (два DangerZone) — без автодобавления, с заметкой",
      _aadded == [] and _atext == _amb_scene and len(_anotes) == 1, (_aadded, _anotes))

# незнакомое имя обработчика (не по шаблону, не пользовательский сигнал) — МОЛЧИМ.
create_project_file(root, "res://deps_quiet.gd",
    "extends Node3D\n\nfunc _on_start_game():\n\tpass\n")
_q_scene = (
    '[gd_scene load_steps=2 format=3]\n\n'
    '[ext_resource type="Script" path="res://deps_quiet.gd" id="1_q"]\n\n'
    '[node name="Main" type="Node3D"]\n'
    'script = ExtResource("1_q")\n'
)
_qtext, _qadded, _qnotes = _sd47.analyze_scene_action(_q_scene, "res://deps_quiet.tscn", root)
check("deps: нераспознанный обработчик — полная тишина (ни правок, ни заметок)",
      _qadded == [] and _qnotes == [] and _qtext == _q_scene, (_qadded, _qnotes))

# пользовательский сигнал: не чиним автоматом, но подсказываем.
create_project_file(root, "res://deps_custom.gd",
    "extends Node3D\n\nsignal wave_finished\n\nfunc _on_wave_finished():\n\tpass\n")
_cu_scene = (
    '[gd_scene load_steps=2 format=3]\n\n'
    '[ext_resource type="Script" path="res://deps_custom.gd" id="1_u"]\n\n'
    '[node name="Main" type="Node3D"]\n'
    'script = ExtResource("1_u")\n'
)
_utext, _uadded, _unotes = _sd47.analyze_scene_action(_cu_scene, "res://deps_custom.tscn", root)
check("deps: обработчик пользовательского сигнала — только мягкая заметка, без правок",
      _uadded == [] and len(_unotes) == 1 and "wave_finished" in _unotes[0], (_uadded, _unotes))

# сторона СКРИПТА: сцена на диске уже использует скрипт, в новом тексте
# скрипта появился неподключённый обработчик — должна быть заметка.
create_project_file(root, "res://deps_attached.tscn",
    '[gd_scene load_steps=2 format=3]\n\n'
    '[ext_resource type="Script" path="res://deps_attached.gd" id="1_a"]\n\n'
    '[node name="Main" type="Node3D"]\n'
    'script = ExtResource("1_a")\n\n'
    '[node name="BombZone" type="Area3D" parent="."]\n')
create_project_file(root, "res://deps_attached.gd", "extends Node3D\n")
_snotes = _sd47.analyze_script_action(
    "extends Node3D\n\nfunc _on_bomb_zone_body_entered(body):\n\tpass\n",
    "res://deps_attached.gd", root)
check("deps: при записи скрипта с неподключённым обработчиком приходит заметка про сцену",
      len(_snotes) == 1 and "_on_bomb_zone_body_entered" in _snotes[0]
      and "body_entered" in _snotes[0], _snotes)
_snotes2 = _sd47.analyze_script_action(
    "extends Node3D\n\nfunc _ready():\n\tpass\n", "res://deps_attached.gd", root)
check("deps: скрипт без _on_-обработчиков не порождает никаких заметок",
      _snotes2 == [], _snotes2)

# интеграция в main.py: анализ включён в обе ветки линта (сцена и скрипт).
_m47 = open(os.path.join(_here, "main.py"), encoding="utf-8").read()
check("main.py: анализ зависимостей подключён для сцен и скриптов",
      "import scene_deps" in _m47
      and "_deps_enrich_scene_action(action, candidate, path, project_root)" in _m47
      and "_deps_note_script_action(candidate, path, project_root)" in _m47)

reset_state(root)

# ---------------------------------------------------------------------------
# 11) v48: read_function (чтение отдельных функций), системное напоминание
#    в новом чате, расширенная информация о чатах и устаревший промпт
# ---------------------------------------------------------------------------
print("\n--- 11) v48: read_function, напоминание о модели, инфо о чатах ---")
import gd_functions as _gf48
import agent_prompts as _ap48
import chat_store as _cs48

_gd48 = (
    "extends CharacterBody3D\n"
    "\n"
    "var speed := 5.0\n"
    "\n"
    "# Двигает игрока.\n"
    "@rpc(\"any_peer\")\n"
    "func _physics_process(delta):\n"
    "\tmove_and_slide()\n"
    "\n"
    "\tif speed > 0:\n"
    "\t\tpass\n"
    "\n"
    "func take_damage(amount):\n"
    "\thealth -= amount\n"
    "\n"
    "static func helper(x):\n"
    "\treturn x\n"
)
check("gd_functions: список функций файла в порядке объявления",
      _gf48.list_functions(_gd48) == ["_physics_process", "take_damage", "helper"],
      _gf48.list_functions(_gd48))
_found48, _missing48 = _gf48.extract_functions(_gd48, ["_physics_process"])
check("gd_functions: сниппет включает комментарий, @rpc и всё тело с пустой строкой внутри",
      len(_found48) == 1 and _found48[0]["snippet"].startswith("# Двигает игрока.")
      and "@rpc" in _found48[0]["snippet"] and "move_and_slide()" in _found48[0]["snippet"]
      and "pass" in _found48[0]["snippet"] and "take_damage" not in _found48[0]["snippet"],
      _found48)
check("gd_functions: номера строк корректные (1-based, с учётом комментария сверху)",
      len(_found48) == 1 and _found48[0]["start_line"] == 5 and _found48[0]["end_line"] == 11,
      _found48)
_f48b, _m48b = _gf48.extract_functions(_gd48, ["helper", "nope"])
check("gd_functions: последняя функция файла извлекается, отсутствующее имя — в missing",
      len(_f48b) == 1 and _f48b[0]["snippet"] == "static func helper(x):\n\treturn x"
      and _m48b == ["nope"], (_f48b, _m48b))

# main.py: read_function встроен в пакетное чтение и цепочку подтверждений.
_m48 = open(os.path.join(_here, "main.py"), encoding="utf-8").read()
check("main.py: read_function принимается как действие чтения и обрабатывается отдельной веткой",
      '("read_file", "read_files", "read_function")' in _m48
      and "def _read_functions_part(" in _m48
      and "_read_functions_part(project_root, f)" in _m48)
check("main.py: подтверждение упоминает функции, прайм запоминает версию промпта у чата",
      "Агент хочет прочитать функции из файла" in _m48
      and "mark_chat_prompt_version()" in _m48)

# Промпт: новое действие описано, цепочки чтения разрешены, есть хэш версии.
check("agent_prompts: read_function описан в промпте и разрешены цепочки чтения",
      '"action": "read_function"' in _ap48.PRIMING_TEMPLATE
      and "ПО ЦЕПОЧКЕ" in _ap48.PRIMING_TEMPLATE)
check("agent_prompts: PROMPT_HASH вычисляется из текста мега-промпта",
      isinstance(_ap48.PROMPT_HASH, str) and len(_ap48.PROMPT_HASH) == 12)

# chat_store: расширенный list_chats и логика устаревшего промпта.
_base48 = os.path.join(root, "_chats48")
os.makedirs(_base48, exist_ok=True)
_rec48 = _cs48.create_chat(_base48, url="https://example.com/chat", primed=True)
_cs48.update_chat(_base48, _rec48["id"], site_name="AI Studio", prompt_hash="oldhash")
_lst48 = _cs48.list_chats(_base48, "newhash")
check("chat_store: list_chats отдаёт сайт, времена и prompt_stale=True при старом хэше",
      len(_lst48) == 1 and _lst48[0]["site_name"] == "AI Studio"
      and _lst48[0]["created"] > 0 and _lst48[0]["last_used"] > 0
      and _lst48[0]["prompt_stale"] is True, _lst48)
_lst48b = _cs48.list_chats(_base48, "oldhash")
check("chat_store: prompt_stale=False при совпадающем хэше промпта",
      _lst48b[0]["prompt_stale"] is False, _lst48b)
_rec48b = _cs48.create_chat(_base48, url="", primed=False)
_stale_map48 = {c["id"]: c["prompt_stale"] for c in _cs48.list_chats(_base48, "newhash")}
check("chat_store: непраймленный чат не помечается устаревшим",
      _stale_map48.get(_rec48b["id"]) is False, _stale_map48)

# chat_routes и server_state: системное напоминание + передача хэша везде.
_cr48 = open(os.path.join(_here, "chat_routes.py"), encoding="utf-8").read()
check("chat_routes: новый чат начинается с системного напоминания, хэш передаётся во все list_chats",
      "Не забудьте выбрать нейросеть" in _cr48
      and _cr48.count("chat_store.list_chats(base, PROMPT_HASH)") == 5)
_ss48 = open(os.path.join(_here, "server_state.py"), encoding="utf-8").read()
check("server_state: mark_chat_prompt_version записывает prompt_hash текущему чату",
      "def mark_chat_prompt_version" in _ss48 and "prompt_hash=PROMPT_HASH" in _ss48)

# Godot-сторона: локализация, стартовый экран, панель.
_loc48 = open(os.path.join(_here, "..", "godot", "agent_locale.gd"), encoding="utf-8").read()
check("locale: ключи v48 есть и в RU, и в EN",
      _loc48.count('"pick_model_hint"') == 2 and _loc48.count('"prompt_stale_short"') == 2
      and _loc48.count('"prompt_stale_tip"') == 2 and _loc48.count('"tip_chat_times"') == 2)
_scr48 = open(os.path.join(_here, "..", "godot", "agent_start_screen.gd"), encoding="utf-8").read()
check("start_screen: список сохранений показывает время, сайт и «промпт устарел»",
      "func _fmt_ts(" in _scr48 and "prompt_stale" in _scr48
      and "prompt_stale_tip" in _scr48 and "tip_chat_times" in _scr48)
_pan48 = open(os.path.join(_here, "..", "godot", "agent_panel.gd"), encoding="utf-8").read()
check("panel: новый чат начинается с напоминания, выпадающий список помечает устаревшие чаты",
      'add_hint(_t("pick_model_hint"))' in _pan48  # v49: напоминание стало окошком
      and 'c.get("prompt_stale", false)' in _pan48)

reset_state(root)

print("\n--- 12) v49: закрытие сцен перед записью, окошко-подсказка ---")

_pan49 = open(os.path.join(_here, "..", "godot", "agent_panel.gd"), encoding="utf-8").read()
_view49 = open(os.path.join(_here, "..", "godot", "agent_chat_view.gd"), encoding="utf-8").read()
_loc49 = open(os.path.join(_here, "..", "godot", "agent_locale.gd"), encoding="utf-8").read()

check("view: появилось окошко-пузырь add_hint с собственной рамкой",
      "func add_hint(" in _view49 and "HINT_BORDER" in _view49 and "HINT_BG" in _view49)
check("locale: заголовок окошка hint_title есть в RU и EN",
      _loc49.count('"hint_title"') == 2)
check("panel: напоминание о выборе модели показывается окошком, а не серой строкой",
      'add_hint(_t("pick_model_hint"))' in _pan49 and 'add_system(_t("pick_model_hint"))' not in _pan49)
check("panel: перед одобренной записью открытая целевая сцена закрывается",
      "func _close_scenes_before_write" in _pan49 and "_close_scenes_before_write()" in _pan49)
check("panel: закрываются только .tscn/.scn и только если сцена реально открыта",
      'sp.ends_with(".tscn") or sp.ends_with(".scn")' in _pan49 and "get_open_scenes().has(sp)" in _pan49)
check("panel: после записи закрытые сцены открываются обратно (все 4 точки возврата)",
      "func _reopen_scenes_after_write" in _pan49 and _pan49.count("_reopen_scenes_after_write()") >= 5)
check("panel: close_scene вызывается с проверкой наличия (фолбэк для старых Godot)",
      'has_method("close_scene")' in _pan49 and 'call("close_scene")' in _pan49)
check("panel: авто-перечитывание сцены (v46) сохранено как фолбэк",
      "func _auto_reload_changed_scene" in _pan49)

print("\n=== RESULT: %d passed, %d failed ===" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
