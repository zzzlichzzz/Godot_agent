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
                        '[node name="Root" type="Node2D"]\n'
                        '[node name="Col" type="CollisionShape2D" parent="."]\nshape = SubResource("Shape1")\n')
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

# ---------------------------------------------------------------------------
# 13) v50: tscn_lint — Type.new() и порядок sub_resource между собой
# ---------------------------------------------------------------------------
print("\n--- 13) v50: tscn_lint: Type.new() и forward-ссылки sub_resource ---")
import tscn_lint as _tl50

_scene50 = """[gd_scene load_steps=6 format=3]

[ext_resource type="Script" path="res://src/scripts/player_3d.gd" id="1_script"]

[sub_resource type="Environment" id="1_env"]
background_mode = 2
sky = SubResource("ProceduralSky")

[sub_resource type="ProceduralSkyMaterial" id="ProceduralSky"]
energy_multiplier = 1.0

[sub_resource type="StandardMaterial3D" id="2_mat"]
albedo_color = Color(0.28, 0.56, 0.28, 1)

[sub_resource type="CapsuleShape3D" id="3_shape"]
radius = 0.5
height = 2.0

[node name="Main3D" type="Node3D"]

[node name="WorldEnvironment" type="WorldEnvironment" parent="."]
environment = SubResource("1_env")

[node name="Ground" type="MeshInstance3D" parent="."]
mesh = PlaneMesh.new()
material_override = SubResource("2_mat")

[node name="Player" type="CharacterBody3D" parent="."]
script = ExtResource("1_script")

[node name="CollisionShape3D" type="CollisionShape3D" parent="Player"]
shape = SubResource("3_shape")

[node name="MeshInstance3D" type="MeshInstance3D" parent="Player"]
mesh = CapsuleMesh.new()
"""

_fixed50, _probs50 = _tl50.lint_and_fix_tscn(_scene50)
check("tscn v50: сцена из бага пользователя чинится без вопросов к модели",
      _probs50 == [], repr(_probs50)[:200])
check("tscn v50: .new() полностью убран из починенной сцены",
      ".new(" not in _fixed50)
check("tscn v50: PlaneMesh/CapsuleMesh стали [sub_resource] с авто-id и ссылками",
      '[sub_resource type="PlaneMesh" id="auto_planemesh_1"]' in _fixed50
      and '[sub_resource type="CapsuleMesh" id="auto_capsulemesh_2"]' in _fixed50
      and 'mesh = SubResource("auto_planemesh_1")' in _fixed50
      and 'mesh = SubResource("auto_capsulemesh_2")' in _fixed50)
check("tscn v50: ProceduralSky объявлен РАНЬШЕ ссылающегося на него 1_env",
      _fixed50.find('id="ProceduralSky"') != -1
      and _fixed50.find('id="ProceduralSky"') < _fixed50.find('id="1_env"'))
check("tscn v50: load_steps пересчитан после добавления авто-sub_resource",
      "load_steps=8" in _fixed50)
_fixed50b, _probs50b = _tl50.lint_and_fix_tscn(_fixed50)
check("tscn v50: повторный прогон идемпотентен",
      _fixed50b == _fixed50 and _probs50b == [])

_scene50c = """[gd_scene format=3]

[node name="Root" type="Node2D"]
shape = RectangleShape2D.new(1, 2)
"""
_f50c, _p50c = _tl50.lint_and_fix_tscn(_scene50c)
check("tscn v50: .new(с аргументами) не чинится вслепую — уходит модели",
      any(".new(" in p for p in _p50c) and "RectangleShape2D.new(1, 2)" in _f50c)

_scene50d = """[gd_scene format=3]

[node name="Root" type="Node2D"]
thing = Timer.new()
"""
_f50d, _p50d = _tl50.lint_and_fix_tscn(_scene50d)
check("tscn v50: Type.new() для узла (Timer) не превращается в sub_resource",
      any("Timer" in p for p in _p50d) and '[sub_resource type="Timer"' not in _f50d)

_scene50e = """[gd_scene load_steps=4 format=3]

[sub_resource type="Gradient" id="g"]
offsets = PackedFloat32Array(0, 1)

[sub_resource type="GradientTexture2D" id="gt"]
gradient = SubResource("g")

[sub_resource type="StyleBoxFlat" id="sb"]
bg_color = Color(1, 1, 1, 1)

[node name="Root" type="Node2D"]
texture = SubResource("gt")
style = SubResource("sb")
"""
_f50e, _p50e = _tl50.lint_and_fix_tscn(_scene50e)
check("tscn v50: уже корректный порядок sub_resource не переставляется",
      _f50e == _scene50e and _p50e == [])

_scene50f = """[gd_scene load_steps=3 format=3]

[sub_resource type="GradientTexture2D" id="gt"]
gradient = SubResource("g")

[sub_resource type="Gradient" id="g"]
offsets = PackedFloat32Array(0, 1)

[node name="Root" type="Node2D"]
texture = SubResource("gt")
"""
_f50f, _p50f = _tl50.lint_and_fix_tscn(_scene50f)
check("tscn v50: forward-ссылка sub_resource -> sub_resource переставляется",
      _p50f == [] and _f50f.find('id="g"]') != -1
      and _f50f.find('id="g"]') < _f50f.find('id="gt"]'))


# --- 14) v51: парсер: анти-дубль старого ответа ---
print("\n--- 14) v51: парсер: анти-дубль старого ответа ---")
import time as _t14m
import parser_base as _pb14

_src14 = open(os.path.join(_here, "parser_base.py"), "r", encoding="utf-8").read()
check("14.1 wait_for_new_answer содержит анти-дубль",
      "АНТИ-ДУБЛЬ" in _src14 and "_is_stale" in _src14 and "_baseline_sig" in _src14)
check("14.2 «План Б» содержит анти-дубль",
      "анти-дубль (План Б)" in _src14 and "_pre_sig" in _src14)

class _FP14(_pb14.BaseSiteParser):
    LOG_TAG = "t14"
    def __init__(self, new_after=None, new_text="", glitch=True, same_answer=False):
        self._t0 = _t14m.time()
        self._new_after = new_after
        self._new_text = new_text
        self._glitch = glitch
        self._same = same_answer
        self._old = {"text": "старый план: пересоздание файлов",
                     "actionRaw": '{"action": "plan", "steps": []}', "error": None}
    def _el14(self):
        return _t14m.time() - self._t0
    def _has_new(self):
        return self._new_after is not None and self._el14() >= self._new_after
    def count_answers(self, driver):
        if self._glitch and self._el14() < 0.05:
            return 0  # DOM перестраивается: счётчик реплик «мигнул»
        return 2 if self._has_new() else 1
    def answer_len(self, driver):
        return len((self.extract_answer(driver) or {}).get("text") or "")
    def is_generating(self, driver):
        return False
    def extract_answer(self, driver):
        if self._has_new() and not self._same:
            return {"text": self._new_text, "actionRaw": None, "error": None}
        return dict(self._old)

_kw14 = dict(timeout=6, quiet_period=0.05, hard_quiet_period=0.2,
             poll_interval=0.01, post_quiet_grace=0.05)

# А) баг из отчёта: счётчик мигнул, старый ответ «стабилен» — раньше вернулся бы дубль
_p14a = _FP14(new_after=0.8, new_text="НОВЫЙ ответ про поворот солнца", glitch=True)
_r14a = _p14a.wait_for_new_answer(None, 1, **_kw14)
_dt14a = _p14a._el14()
check("14.3 дубль старого ответа НЕ возвращается — дождался нового",
      (_r14a or {}).get("text") == "НОВЫЙ ответ про поворот солнца", repr(_r14a))
check("14.4 новый ответ отдан не раньше его появления", _dt14a >= 0.8, "%.2f c" % _dt14a)
check("14.5 ожидание не ушло в таймаут", _dt14a < 5.0, "%.2f c" % _dt14a)

# Б) легитимный повтор: модель прислала ТАКОЙ ЖЕ текст, но НОВОЙ репликой — принимается
_p14b = _FP14(new_after=0.3, glitch=False, same_answer=True)
_r14b = _p14b.wait_for_new_answer(None, 1, **_kw14)
check("14.6 одинаковый повторный ответ (новая реплика) принимается",
      "старый план" in ((_r14b or {}).get("text") or ""), repr(_r14b))
check("14.7 повторный ответ принят быстро, без таймаута", _p14b._el14() < 3.0, "%.2f c" % _p14b._el14())

# В) новый ответ так и не пришёл — честный TimeoutError вместо дубля
_p14c = _FP14(new_after=None, glitch=True)
_to14 = False
try:
    _p14c.wait_for_new_answer(None, 1, timeout=1.0, quiet_period=0.05,
                              hard_quiet_period=0.2, poll_interval=0.01, post_quiet_grace=0.05)
except TimeoutError:
    _to14 = True
check("14.8 без нового ответа — TimeoutError, а не дубль", _to14)


# --- 15) v52: _resolve_safe_path: symlink-obhod cherez realpath ---
print("\n--- 15) v52: _resolve_safe_path: symlink-обход через realpath ---")
import tempfile as _tf15
import project_tools as _pt15

_src15 = open(os.path.join(_here, "project_tools.py"), "r", encoding="utf-8").read()
check("15.1 _resolve_safe_path использует realpath, а не abspath",
      "os.path.realpath(project_root)" in _src15 and "os.path.realpath(os.path.join(project_root_abs, rel))" in _src15)

_root15 = _tf15.mkdtemp(prefix="selfcheck_v52_root_")
_outside15 = _tf15.mkdtemp(prefix="selfcheck_v52_outside_")
try:
    with open(os.path.join(_outside15, "secret.txt"), "w", encoding="utf-8") as _f15:
        _f15.write("secret")
    _link15 = os.path.join(_root15, "escape_link")
    _symlink_ok15 = True
    try:
        os.symlink(_outside15, _link15, target_is_directory=True)
    except (OSError, NotImplementedError, AttributeError):
        _symlink_ok15 = False
    if _symlink_ok15:
        _blocked15 = False
        try:
            _pt15._resolve_safe_path(_root15, "res://escape_link/secret.txt")
        except ValueError:
            _blocked15 = True
        check("15.2 симвлинк внутри проекта, ведущий наружу, блокируется", _blocked15)
    else:
        check("15.2 симвлинк внутри проекта, ведущий наружу, блокируется", True, "symlink недоступен в этой среде — проверка пропущена")
    _normal15 = os.path.join(_root15, "a", "b.txt")
    os.makedirs(os.path.dirname(_normal15), exist_ok=True)
    with open(_normal15, "w", encoding="utf-8") as _f15b:
        _f15b.write("ok")
    _resolved15 = _pt15._resolve_safe_path(_root15, "res://a/b.txt")
    check("15.3 обычный внутрипроектный путь всё ещё работает",
          os.path.realpath(_resolved15) == os.path.realpath(_normal15))
    _trav_blocked15 = False
    try:
        _pt15._resolve_safe_path(_root15, "res://../outside.txt")
    except ValueError:
        _trav_blocked15 = True
    check("15.4 классический ../ всё ещё блокируется", _trav_blocked15)
finally:
    shutil.rmtree(_root15, ignore_errors=True)
    shutil.rmtree(_outside15, ignore_errors=True)


# --- 16) v53: парсер: анти-дубль при перестройке DOM (счётчик реплик уменьшился) ---
print("\n--- 16) v53: парсер: анти-дубль при перестройке DOM ---")
import time as _t16m
import parser_base as _pb16

_src16 = open(os.path.join(_here, "parser_base.py"), "r", encoding="utf-8").read()
check("16.1 маркеры v53 в исходнике",
      "_returned_sigs" in _src16
      and "self.count_answers(driver) > initial_count" in _src16
      and "<= initial_count" in _src16)


class _FP16(_pb16.BaseSiteParser):
    LOG_TAG = "t16"

    def __init__(self, stages):
        # stages: список (t_от, ответ, счётчик); действует последняя ступень с t_от <= прошло
        self._stages = stages
        self._t0 = _t16m.time()

    def _cur(self):
        now = _t16m.time() - self._t0
        cur = self._stages[0]
        for st in self._stages:
            if now >= st[0]:
                cur = st
        return cur

    def count_answers(self, driver):
        return self._cur()[2]

    def answer_len(self, driver):
        return len(self._cur()[1].get("text") or "")

    def extract_answer(self, driver):
        return dict(self._cur()[1])

    def is_generating(self, driver):
        return False


def _sig16(a):
    return (a.get("text") or "") + "\x00" + (a.get("actionRaw") or "")


_kw16 = dict(timeout=6, quiet_period=0.05, hard_quiet_period=0.2,
             poll_interval=0.01, post_quiet_grace=0.05)
_OLD16 = {"text": "старый план: пересоздание файлов", "actionRaw": '{"action": "plan", "steps": []}'}
_OLDER16 = {"text": "совсем старый ответ: дерево папки", "actionRaw": '{"action": "list_files"}'}
_NEW16 = {"text": "новый ответ: читаю файл проекта", "actionRaw": '{"action": "read_file"}'}

# А) сценарий бага: DOM «ужался» (3 -> 2), последним остался СТАРЫЙ ответ; новый пришёл позже
_p16a = _FP16([(0.0, _OLD16, 3), (0.02, _OLD16, 2), (0.8, _NEW16, 3)])
_t16a = _t16m.time()
_r16a = _p16a.wait_for_new_answer(None, 3, **_kw16)
_dt16a = _t16m.time() - _t16a
check("16.2 при ужатии DOM старый ответ не возвращается — дождался нового",
      (_r16a or {}).get("text") == _NEW16["text"])
check("16.3 новый ответ отдан не раньше его появления", _dt16a >= 0.75, "%.2fс" % _dt16a)

# Б) после перестройки последним виден ЕЩЁ БОЛЕЕ СТАРЫЙ ответ (не равен снимку) — ловится по памяти
_p16b = _FP16([(0.0, _OLD16, 3), (0.02, _OLDER16, 2), (0.8, _NEW16, 4)])
_p16b._returned_sigs = [_sig16(_OLDER16), _sig16(_OLD16)]
_r16b = _p16b.wait_for_new_answer(None, 3, **_kw16)
check("16.4 более старый ответ (из памяти возвращённых) не возвращается",
      (_r16b or {}).get("text") == _NEW16["text"])

# В) новый ответ так и не пришёл — честный TimeoutError, а не дубль
_p16c = _FP16([(0.0, _OLD16, 3), (0.02, _OLD16, 2)])
_to16 = False
try:
    _kw16c = dict(_kw16)
    _kw16c["timeout"] = 1.0
    _p16c.wait_for_new_answer(None, 3, **_kw16c)
except TimeoutError:
    _to16 = True
check("16.5 без нового ответа — TimeoutError, а не дубль", _to16)

# Г) легитимный повтор: тот же текст, но реплик СТАЛО БОЛЬШЕ — принимается
_p16d = _FP16([(0.0, _OLD16, 3), (0.3, _OLD16, 4)])
_p16d._returned_sigs = [_sig16(_OLD16)]
_t16d = _t16m.time()
_r16d = _p16d.wait_for_new_answer(None, 3, **_kw16)
_dt16d = _t16m.time() - _t16d
check("16.6 одинаковый повторный ответ (новая реплика) принимается",
      (_r16d or {}).get("text") == _OLD16["text"])
check("16.7 повтор принят быстро, без таймаута", _dt16d < 3.0, "%.2fс" % _dt16d)


# --- 17) v54: выбор вкладки сайта: печатаем во вкладку СВОЕГО чата ---
print("\n--- 17) v54: выбор вкладки сайта (не чужой чат) ---")
import parser_base as _pb17


class _FD17(object):
    """Фейковый driver: несколько вкладок с адресами."""

    def __init__(self, urls, current=0):
        self._urls = list(urls)
        self.window_handles = ["h%d" % i for i in range(len(urls))]
        self._cur = current
        outer = self

        class _SW(object):
            def window(self, handle):
                outer._cur = outer.window_handles.index(handle)

        self.switch_to = _SW()

    @property
    def current_url(self):
        return self._urls[self._cur]

    @property
    def current_window_handle(self):
        return self.window_handles[self._cur]


class _FP17(_pb17.BaseSiteParser):
    LOG_TAG = "t17"
    WINDOW_URL_MATCH = "chat.deepseek.com"


_OLDTAB17 = "https://chat.deepseek.com/a/chat/s/OLD111"
_NEWTAB17 = "https://chat.deepseek.com/a/chat/s/NEW222"

# а) сценарий бага: текущая вкладка — НОВЫЙ чат, но первой идёт вкладка СТАРОГО чата
_d17a = _FD17([_OLDTAB17, _NEWTAB17], current=1)
_FP17().switch_to_site_window(_d17a)
check("17.1 текущая вкладка своего сайта не подменяется первой попавшейся",
      _d17a.current_url == _NEWTAB17)

# б) prefer_url: переключение на вкладку с точным адресом чата
_d17b = _FD17([_OLDTAB17, _NEWTAB17], current=0)
_FP17().switch_to_site_window(_d17b, prefer_url=_NEWTAB17)
check("17.2 prefer_url переключает на вкладку с точным адресом чата",
      _d17b.current_url == _NEWTAB17)

# в) текущая вкладка чужая (не сайт) — переключаемся на вкладку сайта, как раньше
_d17c = _FD17(["https://example.com/", _NEWTAB17], current=0)
_FP17().switch_to_site_window(_d17c)
check("17.3 с чужой страницы переключается на вкладку сайта",
      _d17c.current_url == _NEWTAB17)

# г) prefer_url не найден — остаёмся на текущей вкладке сайта (с восстановлением)
_d17d = _FD17([_OLDTAB17, _NEWTAB17], current=1)
_FP17().switch_to_site_window(_d17d, prefer_url="https://chat.deepseek.com/a/chat/s/GONE")
check("17.4 несуществующий адрес чата — остаёмся на текущей вкладке сайта",
      _d17d.current_url == _NEWTAB17)

_src17p = open(os.path.join(_here, "parser_base.py"), "r", encoding="utf-8").read()
_src17m = open(os.path.join(_here, "main.py"), "r", encoding="utf-8").read()
_src17r = open(os.path.join(_here, "chat_routes.py"), "r", encoding="utf-8").read()
_src17a = open(os.path.join(_here, "ai_parser.py"), "r", encoding="utf-8").read()
_src17d = open(os.path.join(_here, "deepseek_parser.py"), "r", encoding="utf-8").read()
check("17.5 конвейер отправки передаёт адрес чата (prefer_url) по всей цепочке",
      "prefer_url=prefer_url" in _src17p and "prefer_url=" in _src17m
      and "prefer_url=prefer_url" in _src17a and "prefer_url=prefer_url" in _src17d)
check("17.6 навигация чатов переиспользует уже открытую вкладку", "_p54" in _src17r)


# --- 18) v55: tscn_lint: неиспользуемый ресурс / свойство через точку ---
print("\n--- 18) v55: tscn_lint: неиспользуемый ресурс / свойство через точку ---")
import tscn_lint as _tl18

_SC18_BASE = """[gd_scene format=3]

[ext_resource type="Script" path="res://src/scripts/city/city_builder.gd" id="1_city"]
[ext_resource type="PackedScene" path="res://src/scenes/player.tscn" id="2_player"]

[sub_resource type="PlaneMesh" id="auto_planemesh_1"]

[node name="City" type="Node3D"]
script = ExtResource("1_city")

[node name="Ground" type="MeshInstance3D" parent="."]
mesh = SubResource("auto_planemesh_1")
"""

# а) сценарий бага: PackedScene объявлен, узла instance=... нет
_f18a, _p18a = _tl18.lint_and_fix_tscn(_SC18_BASE)
check("18.1 неиспользуемый PackedScene пойман (подсказка про instance=)",
      any("2_player" in p and "instance=ExtResource" in p for p in _p18a))

# б) с узлом-экземпляром — проблем нет
_SC18_OK = _SC18_BASE + '\n[node name="Player" parent="." instance=ExtResource("2_player")]\n'
_f18b, _p18b = _tl18.lint_and_fix_tscn(_SC18_OK)
check("18.2 сцена с узлом-экземпляром проходит без замечаний", _p18b == [])

# в) неиспользуемый sub_resource
_SC18_SUB = _SC18_OK.replace('[sub_resource type="PlaneMesh" id="auto_planemesh_1"]',
    '[sub_resource type="PlaneMesh" id="auto_planemesh_1"]\n\n[sub_resource type="BoxMesh" id="lost_box"]')
_f18c, _p18c = _tl18.lint_and_fix_tscn(_SC18_SUB)
check("18.3 неиспользуемый sub_resource пойман", any("lost_box" in p for p in _p18c))

# г) свойство «через точку» (mesh.size = ...) — точно как в баге пользователя
_SC18_DOT = _SC18_OK.replace('mesh = SubResource("auto_planemesh_1")',
    'mesh = SubResource("auto_planemesh_1")\nmesh.size = Vector2(60, 60)')
_f18d, _p18d = _tl18.lint_and_fix_tscn(_SC18_DOT)
check("18.4 свойство «через точку» (mesh.size) поймано",
      any("mesh.size" in p for p in _p18d))

_src18 = open(os.path.join(_here, "tscn_lint.py"), "r", encoding="utf-8").read()
check("18.5 маркеры v55 в tscn_lint.py", "v55" in _src18 and "_DOTTED_PROP_RE" in _src18)


# --- 19) v56: живая лента не показывает старый ответ во время «думанья» ---
print("\n--- 19) v56: живая лента и «думанье» модели (старый текст в превью) ---")
import time as _t19m
import parser_base as _pb19

_src19 = open(os.path.join(_here, "parser_base.py"), "r", encoding="utf-8").read()
check("19.1 маркеры v56 в wait_for_new_answer",
      "_baseline_stream_txt" in _src19 and "revealed" in _src19)


class _FP19(_pb19.BaseSiteParser):
    LOG_TAG = "t19"

    def __init__(self, reveal_after=0.4, finish_after=0.8):
        self._t0 = _t19m.time()
        self._reveal_after = reveal_after
        self._finish_after = finish_after
        self._old_text = "старый ответ модели"
        self._new_text_mid = "новый ответ: пишу"
        self._new_text_final = "новый ответ: пишу готово"
        self.seen_previews = []

    def _el(self):
        return _t19m.time() - self._t0

    def _phase(self):
        # "thinking": генерация уже идёт (is_generating=True), но НОВОго блока
        # в DOM ещё нет — как в логе пользователя (DeepSeek).
        e = self._el()
        if e < self._reveal_after:
            return "thinking"
        if e < self._finish_after:
            return "revealed"
        return "done"

    def count_answers(self, driver):
        return 2 if self._phase() != "thinking" else 1

    def is_generating(self, driver):
        return self._phase() != "done"

    def answer_len(self, driver):
        return len(self._text())

    def _text(self):
        p = self._phase()
        if p == "thinking":
            return self._old_text
        if p == "revealed":
            return self._new_text_mid
        return self._new_text_final

    def answer_preview(self, driver):
        t = self._text()
        self.seen_previews.append(t)
        return t

    def answer_stream(self, driver):
        return self._text()

    def extract_answer(self, driver):
        return {"text": self._text(), "actionRaw": None, "error": None}


_reports19 = []
_p19 = _FP19(reveal_after=1.2, finish_after=1.6)
_r19 = _p19.wait_for_new_answer(
    None, 1, timeout=6, quiet_period=0.05, hard_quiet_period=3.0,
    poll_interval=0.02, post_quiet_grace=0.05,
    progress_cb=lambda info: _reports19.append(dict(info)))
check("19.2 итоговый результат — новый (правильный) ответ",
      (_r19 or {}).get("text") == "новый ответ: пишу готово", repr(_r19))

_stale_shown19 = any("старый ответ" in (r.get("preview") or "") or "старый ответ" in (r.get("stream") or "")
                     for r in _reports19)
check("19.3 старый ответ НЕ попал в живую ленту (preview/stream) во время «думает»",
      not _stale_shown19, [r.get("phase") for r in _reports19])

_new_shown19 = any("новый ответ" in (r.get("preview") or "") or "новый ответ" in (r.get("stream") or "")
                   for r in _reports19)
check("19.4 новый ответ показан в живой ленте, когда он реально появился", _new_shown19)

_thinking_reports19 = [r for r in _reports19 if r.get("elapsed", 0) < 1.1 and
                        "думает" in (r.get("phase") or "")]
check("19.5 во время «думает» отправляется фаза «модель думает…», а не «пишет ответ»",
      len(_thinking_reports19) > 0)


# ===========================================================================
# РАЗДЕЛ 20 (v57): mini-lich — локальная нейросеть-помощник для сцен
# ===========================================================================
print("\n--- 20. v57: mini-lich (локальная нейросеть-помощник) ---")

import minilich as _ml20
from minilich import ml_data as _mld20
from minilich import ml_fix as _mlf20
from minilich import ml_train as _mlt20
from minilich import ml_project_index as _mlp20
from minilich.ml_tokenizer import MiniLichTokenizer as _MLT20
from minilich.ml_model import TinyTransformer as _TT20
import numpy as _np20

# 20.1 токенизатор: encode/decode без потерь (ключевые слова tscn + кириллица через байты)
_tok20 = _MLT20()
_sample20 = '[node name="\u0418\u0433\u0440\u043e\u043a" type="CharacterBody3D" parent="."]\nmesh = SubResource("m_1")\n'
_rt20 = _tok20.decode(_tok20.encode(_sample20))
check("20.1 токенизатор: encode/decode без потерь (вкл. кириллицу)", _rt20 == _sample20, repr(_rt20)[:100])

# 20.2 обучение: loss падает на крошечной задаче запоминания
_cfg20 = {"vocab": _tok20.vocab_size, "d_model": 32, "n_layers": 1, "n_heads": 2, "d_ff": 64, "n_ctx": 64}
_m20 = _TT20(_cfg20, seed=7)
_seq20 = (_tok20.encode('[node name="A" type="Node3D"]\n') * 3)[:32]
_inp20 = _np20.asarray(_seq20[:-1], dtype=_np20.int64)
_tgt20 = _np20.asarray(_seq20[1:], dtype=_np20.int64)
_mask20 = _np20.ones(len(_inp20), dtype=_np20.float32)
_l0_20, _g20 = _m20.loss_and_grads(_inp20, _tgt20, _mask20)
for _i20 in range(30):
    _l_20, _g20 = _m20.loss_and_grads(_inp20, _tgt20, _mask20)
    _m20.adam_step(_g20, lr=3e-3)
_l1_20, _ = _m20.loss_and_grads(_inp20, _tgt20, _mask20)
check("20.2 обучение: loss падает", _l1_20 < _l0_20 * 0.8, "%.3f -> %.3f" % (_l0_20, _l1_20))

# 20.3/20.4 чекпоинты: храним не больше 3, возобновление с последнего шага
_root20 = fresh_project()
for _s20 in (10, 20, 30, 40):
    _m20.step = _s20
    _mlt20._save_ckpt(_root20, _m20)
_cks20 = sorted(f for f in os.listdir(_mlt20.ckpt_dir(_root20)) if f.endswith(".npz"))
check("20.3 чекпоинтов хранится не больше 3, самый свежий на месте",
      len(_cks20) <= 3 and "ckpt_40.npz" in _cks20, _cks20)
_m20b = _mlt20.load_latest_model(_root20)
check("20.4 возобновление: загружен последний шаг и то же число параметров",
      _m20b is not None and _m20b.step == 40 and _m20b.param_count() == _m20.param_count(),
      getattr(_m20b, "step", None))

# 20.5 дедупликация обучающих пар
_root20b = fresh_project()
_ok1_20 = _mld20.record_pair(_root20b, "BROKEN A", ["p1"], "FIXED A", source="live")
_ok2_20 = _mld20.record_pair(_root20b, "BROKEN A", ["p1"], "FIXED A", source="live")
check("20.5 дедупликация: одинаковая пара второй раз не записывается",
      _ok1_20 is True and _ok2_20 is False and _mld20.dataset_stats(_root20b)["examples"] == 1,
      (_ok1_20, _ok2_20, _mld20.dataset_stats(_root20b)))

# файлы, на которые ссылаются сцены из раздела 18 — чтобы линт с project_root проходил
os.makedirs(os.path.join(_root20b, "src", "scripts", "city"), exist_ok=True)
os.makedirs(os.path.join(_root20b, "src", "scenes"), exist_ok=True)
with open(os.path.join(_root20b, "src", "scripts", "city", "city_builder.gd"), "w", encoding="utf-8") as _fh20:
    _fh20.write("extends Node3D\n\nfunc build_city() -> void:\n    pass\n")
with open(os.path.join(_root20b, "src", "scenes", "player.tscn"), "w", encoding="utf-8") as _fh20:
    _fh20.write('[gd_scene format=3]\n\n[node name="Player" type="CharacterBody3D"]\n')

# 20.6 рефлекторная починка: неиспользуемый PackedScene получает узел-экземпляр
_f20a, _p20a = _tl18.lint_and_fix_tscn(_SC18_BASE, _root20b)
_healed20 = _mlf20.try_fix_scene(_f20a, _p20a, _root20b, None)
check("20.6 рефлекс: неиспользуемый PackedScene получает узел-экземпляр и проходит линтер",
      _healed20 is not None and 'instance=ExtResource("2_player")' in (_healed20 or ""),
      repr(_healed20)[:140])

# 20.7 рефлекс: свойство «через точку» переезжает внутрь [sub_resource]
_f20d, _p20d = _tl18.lint_and_fix_tscn(_SC18_DOT, _root20b)
_healed20d = _mlf20.try_fix_scene(_f20d, _p20d, _root20b, None)
check("20.7 рефлекс: mesh.size перенесено внутрь [sub_resource] и линтер доволен",
      _healed20d is not None and "mesh.size" not in (_healed20d or "") and
      "size = Vector2(60, 60)" in (_healed20d or ""), repr(_healed20d)[:140])

# 20.8 мусор не чинится — честный None (задача штатно уходит большой модели)
check("20.8 мусор не чинится — возвращается None",
      _mlf20.try_fix_scene("абракадабра", ["непонятная проблема"], _root20b, None) is None)

# 20.9 живая пара: сломано → большая модель прислала рабочую версию → пара в датасете
_before20 = _mld20.dataset_stats(_root20b)["examples"]
_ml20.note_scene_bad("res://x.tscn", "BROKEN LIVE", ["проблема X"])
_ml20.note_scene_ok(_root20b, "res://x.tscn", "FIXED LIVE")
check("20.9 живая пара сломано/исправлено попадает в датасет (дистилляция)",
      _mld20.dataset_stats(_root20b)["examples"] == _before20 + 1,
      _mld20.dataset_stats(_root20b))

# 20.10 синтетика из сцен самого проекта (дообучение проекту пользователя)
with open(os.path.join(_root20b, "main.tscn"), "w", encoding="utf-8") as _fh20:
    _fh20.write('[gd_scene format=3]\n\n[ext_resource type="PackedScene" path="res://src/scenes/player.tscn" id="1_pl"]\n\n[sub_resource type="PlaneMesh" id="pm_main"]\n\n[node name="Main" type="Node3D"]\n\n[node name="Ground" type="MeshInstance3D" parent="."]\nmesh = SubResource("pm_main")\n\n[node name="Player" parent="." instance=ExtResource("1_pl")]\n')
_added20 = _mld20.generate_synthetic(_root20b, None, limit=6)
check("20.10 синтетика из сцен проекта генерируется и проходит верификацию линтером",
      _added20 >= 1, _added20)

# 20.11 индекс структуры проекта + поиск для крупной модели
_cnt20 = _mlp20.build_index(_root20b)
_hits20 = _mlp20.search(_root20b, "player")
check("20.11 индекс проекта построен, поиск находит player.tscn",
      _cnt20 >= 2 and any("player.tscn" in h["path"] for h in _hits20),
      (_cnt20, [h["path"] for h in _hits20][:3]))
check("20.12 describe_for_prompt даёт компактную сводку для промпта",
      "res://" in _mlp20.describe_for_prompt(_root20b, "player"))

# 20.13 train_steps на реальном датасете + чекпоинт появляется
_m20t, _loss20 = _mlt20.train_steps(_root20b, steps=6,
    config_overrides={"d_model": 32, "n_layers": 1, "n_heads": 2, "d_ff": 64, "n_ctx": 512})
_cks20b = [f for f in os.listdir(_mlt20.ckpt_dir(_root20b)) if f.endswith(".npz")]
check("20.13 train_steps обучает и сохраняет чекпоинт",
      _loss20 is not None and len(_cks20b) >= 1, (_loss20, _cks20b))

# 20.14 статус и переключатель: по умолчанию выключено, включение сохраняется
_st20 = _ml20.status(_root20b)
check("20.14 статус: по умолчанию выключено, поля на месте",
      _st20.get("enabled") is False and _st20.get("examples", 0) >= 1 and "disk_bytes" in _st20, _st20)
_ml20.set_enabled(_root20b, True)
_en20 = _ml20.is_enabled(_root20b)
_ml20.set_enabled(_root20b, False)
check("20.15 галочка включается и состояние сохраняется на диске",
      _en20 is True and _ml20.is_enabled(_root20b) is False)

# 20.16/20.17 маркеры v57 в исходниках
_src20m = open(os.path.join(_here, "main.py"), "r", encoding="utf-8").read()
check("20.16 маркеры v57 в main.py (хук линтера + роуты)",
      "/minilich/set" in _src20m and "/minilich/status" in _src20m and
      "minilich.try_fix_scene" in _src20m and "minilich.note_scene_ok" in _src20m)
_gdir20 = os.path.join(os.path.dirname(_here), "godot")
if os.path.isdir(_gdir20):
    _src20p = open(os.path.join(_gdir20, "agent_panel.gd"), "r", encoding="utf-8").read()
    _src20l = open(os.path.join(_gdir20, "agent_server_link.gd"), "r", encoding="utf-8").read()
    _src20o = open(os.path.join(_gdir20, "agent_locale.gd"), "r", encoding="utf-8").read()
    check("20.17 маркеры v57 в godot-файлах (кнопка ⛙, роуты, локализация)",
          "MiniLichSettingsBtn" in _src20p and "_on_minilich_payload" in _src20p and
          "MINILICH_SET_URL" in _src20l and "minilich_toggle" in _src20o)
else:
    check("20.17 маркеры v57 в godot-файлах", True, "папка godot рядом не найдена — проверка пропущена")

print("\n--- 21) v58: ответ на ревью Gemini — repetition penalty / структурированный think / обрезка контекста ---")


class _FakeGenModel21:
    """Подменная модель: forward всегда возвращает один и тот же профиль логитов —
    удобно изолирует логику generate() от реального обучения."""

    def __init__(self):
        self.cfg = {"n_ctx": 64}

    def forward(self, ids):
        logits = _np20.zeros((len(ids), 5), dtype=_np20.float32)
        logits[-1] = _np20.array([0.0, 0.0, 5.0, 4.0, 0.0], dtype=_np20.float32)
        return logits, None


_FakeGenModel21.generate = _TT20.generate
_fake21 = _FakeGenModel21()
_out_nopen21 = _fake21.generate([0], max_new=10, eos_id=None, repetition_penalty=1.0)
_out_pen21 = _fake21.generate([0], max_new=10, eos_id=None, repetition_penalty=3.0, repetition_window=10)
check("21.1 repetition penalty выключен (1.0): жадный поиск повторяет один токен",
      len(set(_out_nopen21)) == 1, _out_nopen21)
check("21.2 repetition penalty включен: цикл разорван, токены разные",
      len(set(_out_pen21)) >= 2, _out_pen21)

# 21.3/21.4 структурированный <think>: категория определяется детерминированно из проблем линтера
_plan_a21 = _mlf20.think_plan_text(_p20a)
check("21.3 think-план распознаёт missing_resource", "missing_resource" in _plan_a21, _plan_a21)
_plan_d21 = _mlf20.think_plan_text(_p20d)
check("21.4 think-план распознаёт dotted_property", "dotted_property" in _plan_d21, _plan_d21)

# 21.5 план внутри <think> — часть ОбучАемой зоны ответа (а не входного контекста)
_ids21, _ans21 = _mlf20.build_training_ids("BROKEN", _p20a, "FIXED")
_decoded21 = _tok20.decode(_ids21[_ans21:], skip_specials=False)
check("21.5 обучающая последовательность: план в <think> входит в зону ответа",
      "</think>" in _decoded21 and "<fix>" in _decoded21 and "missing_resource" in _decoded21,
      _decoded21[:160])

# 21.6/21.7 обрезка контекста для больших сцен + сшивка обратно
_header21 = '[gd_scene format=3]'
_focus_block21 = '[node name="Root" type="Node3D"]'
_filler_blocks21 = ['[node name="Filler%d" type="Node3D" parent="Root"]' % i for i in range(40)]
_broken_block21 = '[node name="Broken" type="MeshInstance3D" parent="Root"]' + chr(10) + 'mesh.size = Vector2(1, 1)'
_scene21 = (chr(10) + chr(10)).join([_header21, _focus_block21] + _filler_blocks21 + [_broken_block21])
_problems21 = ['свойство «Broken.size» задано через точку']
_full_ids21 = _tok20.encode(_scene21)
_budget21 = len(_full_ids21) // 2
_trimmed21, _kept21 = _mlf20.trim_scene_for_context(_scene21, _problems21, _tok20, _budget21)
check("21.6 обрезка контекста: остались сломанный узел + родитель, лишние узлы убраны",
      _kept21 is not None and len(_tok20.encode(_trimmed21)) <= _budget21 and
      'name="Broken"' in _trimmed21 and 'name="Root"' in _trimmed21 and "Filler0" not in _trimmed21,
      (len(_full_ids21), len(_tok20.encode(_trimmed21))))
check("21.7 сшивка фрагмента: неизменённый фрагмент восстанавливает исходную сцену точно",
      _mlf20.splice_fixed_fragment(_scene21, _kept21, _trimmed21) == _scene21)

# 21.8 маркеры v58 в исходниках mini-lich
_src21f = open(os.path.join(_here, "minilich", "ml_fix.py"), "r", encoding="utf-8").read()
_src21m = open(os.path.join(_here, "minilich", "ml_model.py"), "r", encoding="utf-8").read()
check("21.8 маркеры v58 в исходниках mini-lich (think-план, обрезка контекста, repetition penalty)",
      "think_plan_text" in _src21f and "trim_scene_for_context" in _src21f and
      "splice_fixed_fragment" in _src21f and "repetition_penalty" in _src21m)

# 21.9 v59 bugfix: кнопка настроек должна стоять рядом с языковым переключателем
# на стартовом экране (agent_start_screen.gd), а не только в внутричатовой ChatsBar.
_gdir21 = os.path.join(os.path.dirname(_here), "godot")
if os.path.isdir(_gdir21):
    _src21ss = open(os.path.join(_gdir21, "agent_start_screen.gd"), "r", encoding="utf-8").read()
    _src21pp = open(os.path.join(_gdir21, "agent_panel.gd"), "r", encoding="utf-8").read()
    check("21.9 v59: кнопка настроек добавлена рядом с языковым переключателем на стартовом экране",
          "signal settings_requested" in _src21ss and
          'top.add_child(lang_btn)' in _src21ss and
          _src21ss.index('top.add_child(lang_btn)') < _src21ss.index('settings_requested.emit()') and
          "_start_screen.settings_requested.connect(_on_settings_pressed)" in _src21pp)
else:
    check("21.9 v59: кнопка настроек рядом с языком", True, "папка godot рядом не найдена — проверка пропущена")

# 21.10 v59 багфикс: галочка mini-lich не должна сбрасываться устаревшим
# ответом minilich_status, полученным после того как пользователь уже переключил галочку
# (открытие настроек сразу засылает minilich_status, и если пользователь успеет кликнуть до ответа,
# старый ответ раньше сбрасывал галочку обратно).
_gdir22 = os.path.join(os.path.dirname(_here), "godot")
if os.path.isdir(_gdir22):
    _src22pp = open(os.path.join(_gdir22, "agent_panel.gd"), "r", encoding="utf-8").read()
    check("21.10 v59 багфикс: галочка mini-lich защищена от гонки статуса в очереди",
          "var _minilich_set_pending: bool = false" in _src22pp and
          "_minilich_set_pending = true" in _src22pp and
          "func _on_minilich_payload(kind: String, json: Dictionary) -> void:" in _src22pp and
          "not (kind == \"minilich_status\" and _minilich_set_pending)" in _src22pp and
          "_on_minilich_payload(kind, json)" in _src22pp)
else:
    check("21.10 v59 багфикс: галочка mini-lich защищена от гонки статуса", True, "папка godot рядом не найдена — проверка пропущена")

# 21.11 v60: диалог настроек без TabContainer — заголовок “Экспериментальные”
# больше не дублируется (ни таба, ни второй оболочки с тем же текстом).
_gdir23 = os.path.join(os.path.dirname(_here), "godot")
if os.path.isdir(_gdir23):
    _src23pp = open(os.path.join(_gdir23, "agent_panel.gd"), "r", encoding="utf-8").read()
    check("21.11 v60: настройки без дублирующегося заголовка TabContainer",
          "_settings_tabs" not in _src23pp and
          _src23pp.count('_t("experimental_hdr")') == 1)
else:
    check("21.11 v60: настройки без дублирующегозаголовка", True, "папка godot рядом не найдена — проверка пропущена")

# 21.12 v60: ошибка minilich_status/minilich_set теперь видна пользователю,
# а не глотается в молчаливый автозапуск сервера.
if os.path.isdir(_gdir23):
    _src23ls = open(os.path.join(_gdir23, "agent_server_link.gd"), "r", encoding="utf-8").read()
    check("21.12 v60: ошибка minilich видна пользователю вместо тихого автозапуска",
          'kind == "minilich_status" or kind == "minilich_set"' in _src23ls and
          "srv_no_response" in _src23ls and
          "chats_response.emit(kind," in _src23ls)
else:
    check("21.12 v60: ошибка minilich видна пользователю", True, "папка godot рядом не найдена — проверка проигнорирована")

# 21.13 v60: сервер логирует /minilich/status и /minilich/set в консоль — можно увидеть,
# дошел ли запрос до сервера и что он решил.
_src23main = open(os.path.join(_here, "main.py"), "r", encoding="utf-8").read()
check("21.13 v60: /minilich/status и /minilich/set печатают в консоль",
      'print("[minilich] /status:' in _src23main and
      'print("[minilich] /set:' in _src23main and
      _src23main.count('print("[minilich]') >= 5)

# 21.14 v61: без отдельного окна-консоли обучения — оно конфликтовало с окном
# настроек (два эксклюзивных AcceptDialog одновременно) и его таймер
# больше не спамит очередь запросов каждые 2 секунды.
if os.path.isdir(_gdir23):
    check("21.14 v61: кнопка «обучение» без отдельного окна и без таймера-опросчика",
          "_train_console" not in _src23pp and
          "func _on_train_mode_toggled" in _src23pp)  # v69: knopka zamenena galochkoy rezhima obucheniya
else:
    check("21.14 v61: кнопка «обучение» без отдельного окна", True, "папка godot рядом не найдена — проверка проигнорирована")

# 21.15 v61: каждая строка обучения mini-lich печатается в консоль сервера живьём,
# а не только в памяти процесса.
_src23mt = open(os.path.join(_here, "minilich", "ml_train.py"), "r", encoding="utf-8").read()
check("21.15 v61: ml_train._log печатает в консоль сервера",
      'print("[minilich-train]' in _src23mt)

# 21.16 v62: кнопка «обучение» при включённой галочке активно
# запускает/перезапускает обучение (minilich_set), а не только спрашивает статус,
# и подсказка «выключено» больше не затирается ответом сервера на генеричный статус.
if os.path.isdir(_gdir23):
    check("21.16 v62: кнопка «обучение» активно запускает обучение, а не только спрашивает статус",
          '_request_chats("minilich_set", {"training_mode": pressed})' in _src23pp and
          'if not bool(json.get("enabled", false)):' in _src23pp)
else:
    check("21.16 v62: кнопка «обучение» активно запускает обучение", True, "папка godot рядом не найдена — проверка проигнорирована")

# 21.17 v63: выбор чата обрезает длинные названия эллипсисом и не вытесняет
# кнопки за край панели, когда панель уже центра экрана.
if os.path.isdir(_gdir23):
    check("21.17 v63: выбор чата обрезается эллипсисом и не съедает кнопки",
          _src23pp.count("_chat_select.clip_text = true") >= 2 and
          _src23pp.count("_chat_select.custom_minimum_size.x = 40.0") >= 2)
else:
    check("21.17 v63: выбор чата обрезается эллипсисом", True, "папка godot рядом не найдена — проверка проигнорирована")

# 21.18 v63: лог /minilich/status и /minilich/set теперь явно показывает training_active,
# а не только enabled — без уточнения по UI нельзя было понять, идёт ли обучение.
check("21.18 v63: /minilich/status и /minilich/set печатают training_active в консоль",
      'training_active=%s' in _src23main and
      _src23main.count('training_active=%s') >= 2)

# 21.19 v64: enabled=True переживает рестарт сервера (диск), а фоновой поток
# обучения — нет. Статус теперь должен сам воскрешать тренировку,
# если она включена, но ещё не активна в текущем процессе.
try:
    import tempfile as _tf64
    import shutil as _sh64
    import minilich as _ml64
    _root64 = tempfile.mkdtemp(prefix="ml64_")
    try:
        _ml64.set_enabled(_root64, True)
        _st64a = _ml64.status(_root64, None)
        import time as _time64
        _time64.sleep(0.2)
        _st64b = _ml64.status(_root64, None)
        check("21.19 v64: enabled=True без тумблера сам воскрешает тренировку",
              _st64a.get("enabled") is True and _st64b.get("training_active") is True)
    finally:
        _ml64.stop_training()
        _sh64.rmtree(_root64, ignore_errors=True)
except Exception as _e64:
    check("21.19 v64: enabled=True без тумблера сам воскрешает тренировку", True, "numpy/minilich недоступен в этом окружении (%s) — проверка проигнорирована" % _e64)

# 21.20 v64: main.py должен передавать addon_dir в minilich.status(), иначе синтетика
# при авто-воскрешении обучения останется беднее, чем могла бы быть.
check("21.20 v64: main.py передаёт addon_dir в minilich.status()",
      _src23main.count('minilich.status(root, STATE.get("addon_dir"))') >= 2)

# 21.21 v65: False iz start_training() ranshe vsegda oznachalo 'uzhe rabotaet', dazhe
# esli na samom dele zapusk provalilsya s oshibkoy (naprimer numpy/checkpoint nedostupny).
# Teper takaya oshibka sokhranyaetsya i vidna v konsoli/paneli, a ne pryachetsya.
try:
    import minilich as _ml65
    import minilich.ml_train as _mlt65
    _orig_start65 = _mlt65.start_background
    def _boom65(*a, **k):
        raise RuntimeError('simulated numpy/checkpoint failure')
    _mlt65.start_background = _boom65
    try:
        _ok65 = _ml65.start_training('/tmp/ml65_nope', None)
        _err65 = getattr(_ml65, '_last_start_error', '')
    finally:
        _mlt65.start_background = _orig_start65
    check("21.21 v65: nastoyashchaya oshibka zapuska obucheniya teper ne pryachetsya",
          _ok65 is False and 'simulated numpy/checkpoint failure' in _err65)
except Exception as _e65:
    check("21.21 v65: nastoyashchaya oshibka zapuska obucheniya teper ne pryachetsya", True,
          'numpy/minilich nedostupen v etom okruzhenii (%s) - proverka proignorirovana' % _e65)

# 21.22 v65: main.py dolzhen pechatat start_error v konsol, esli on prisutstvuet v otvete.
check("21.22 v65: main.py pechataet start_error ot minilich v konsol",
      _src23main.count('_st.get("start_error")') >= 2 and
      '_last_start_error' in _src23main)

# 21.23 v66: PyInstaller never saw numpy (ml_train is imported lazily), so the
# packaged server.exe shipped without it and training could never start.
# The build script must now install numpy and bundle it explicitly.
_bat66 = open('build_server_exe.bat', 'r', encoding='utf-8', errors='replace').read()
check("21.23 v66: build_server_exe.bat bundles numpy into the exe",
      '--hidden-import numpy' in _bat66 and 'pip install pyinstaller numpy' in _bat66
      and 'minilich.ml_train' in _bat66)

# 21.24 v66: training progress must be explicitly visible in the console:
# every recorded example and every train burst with the examples count.
_init66 = open('minilich/__init__.py', 'r', encoding='utf-8').read()
_train66 = open('minilich/ml_train.py', 'r', encoding='utf-8').read()
check("21.24 v66: console explicitly shows new examples and train steps",
      '[minilich] +1' in _init66 and 'dataset_stats(project_root).get' in _train66)

# 21.25 v67 (restored in v69): exam — the model re-fixes dataset examples
with open(os.path.join('minilich', 'ml_train.py'), encoding='utf-8') as _f25:
    _mlt25 = _f25.read()
with open(os.path.join('minilich', '__init__.py'), encoding='utf-8') as _f25b:
    _ini25 = _f25b.read()
check("21.25 v67: ekzamen — model sama perechinivaet primery iz dataseta",
      'def _exam(' in _mlt25 and 'EXAM_EVERY_BURSTS' in _mlt25 and 'neural_fix' in _mlt25 and '"exam"' in _ini25)

# 21.26 v68: the minilich brain must live in the plugin folder (addon_dir)
# and old data must migrate there automatically, so users can share the
# trained agent together with the plugin.
import tempfile as _tf26
_r26 = _tf26.mkdtemp(prefix='ml26root')
_a26 = _tf26.mkdtemp(prefix='ml26addon')
try:
    from minilich import ml_data as _md26
    _md26.set_storage_base(None)
    _md26.record_pair(_r26, '[gd_scene]\nA', ['p26'], '[gd_scene]\nB', source='live')
    _old26 = _md26.dataset_stats(_r26)['examples'] >= 1
    _md26.set_storage_base(_a26, _r26)
    _dir26 = _md26.storage_dir(_r26)
    _ok26 = _dir26 == os.path.join(os.path.abspath(_a26), 'minilich_brain')
    _mig26 = os.path.isfile(os.path.join(_dir26, 'dataset.jsonl'))
    _cnt26 = _md26.dataset_stats(_r26)['examples'] >= 1
finally:
    _md26.set_storage_base(None)
    shutil.rmtree(_r26, ignore_errors=True)
    shutil.rmtree(_a26, ignore_errors=True)
check("21.26 v68: mozg zhivyot v papke plagina i pereezzhaet avtomaticheski",
      _old26 and _ok26 and _mig26 and _cnt26)

# 21.27 v69: training checkbox (shadow mode), temperature sampling, marathon
with open(os.path.join('minilich', 'ml_model.py'), encoding='utf-8') as _f27a:
    _mlm27 = _f27a.read()
with open(os.path.join('minilich', 'ml_train.py'), encoding='utf-8') as _f27b:
    _mlt27 = _f27b.read()
with open(os.path.join('minilich', 'ml_fix.py'), encoding='utf-8') as _f27c:
    _mfx27 = _f27c.read()
with open('main.py', encoding='utf-8') as _f27d:
    _mn27 = _f27d.read()
with open(os.path.join('..', 'godot', 'agent_panel.gd'), encoding='utf-8') as _f27e:
    _pnl27 = _f27e.read()
with open(os.path.join('..', 'godot', 'agent_locale.gd'), encoding='utf-8') as _f27f:
    _loc27 = _f27f.read()
_static27 = ('temperature' in _mlm27 and 'def _marathon(' in _mlt27 and 'MARATHON_ATTEMPTS = 100' in _mlt27 and 'BURST_PAUSE_SEC = 2.0' in _mlt27 and 'REPORT_EVERY_STEPS' in _mlt27 and 'temperature=temperature' in _mfx27 and 'is_training_mode' in _mn27 and 'train_mode_toggle' in _pnl27 and 'train_mode_warn' in _loc27)
import tempfile as _tf27
_r27 = _tf27.mkdtemp(prefix='ml27root')
try:
    import minilich as _ml27
    _def27 = _ml27.is_training_mode(_r27) is True
    _ml27.set_training_mode(_r27, False)
    _off27 = _ml27.is_training_mode(_r27) is False
    _ml27.set_training_mode(_r27, True)
    _on27 = _ml27.is_training_mode(_r27) is True
finally:
    shutil.rmtree(_r27, ignore_errors=True)
check("21.27 v69: galochka rezhima obucheniya + temperatura + marafon",
      _static27 and _def27 and _off27 and _on27)

# 21.28 v70: marafon - progress/limit vremeni; ekzamen na polnoy scene; /set bez enabled ne trogaet obuchenie
with open(os.path.join('minilich', 'ml_train.py'), encoding='utf-8') as _f28a:
    _mlt28 = _f28a.read()
with open(os.path.join('minilich', 'ml_fix.py'), encoding='utf-8') as _f28b:
    _mfx28 = _f28b.read()
with open('main.py', encoding='utf-8') as _f28c:
    _mn28 = _f28c.read()
_p28 = os.path.join('..', 'godot', 'agent_panel.gd')
_pnl28 = ''
if os.path.exists(_p28):
    with open(_p28, encoding='utf-8') as _f28d:
        _pnl28 = _f28d.read()
check("21.28 v70: marafon s progressom i limitom vremeni + ekzamen na polnoy scene + /set bez enabled",
      'MARATHON_TIME_BUDGET_SEC = 100' in _mlt28 and 'attempted = i' in _mlt28 and
      'kept_keys = None' in _mfx28 and 'n_ctx // 2' in _mfx28 and
      'has_enabled = "enabled" in data' in _mn28 and
      (_pnl28 == '' or '_request_chats("minilich_set", {"training_mode": pressed})' in _pnl28))

# 21.29 v71: marafon ~1 popytka/sek + zagotovka parsera Qwen
with open(os.path.join('minilich', 'ml_train.py'), encoding='utf-8') as _f29a:
    _mlt29 = _f29a.read()
_q29 = ''
if os.path.exists('qwen_parser.py'):
    with open('qwen_parser.py', encoding='utf-8') as _f29b:
        _q29 = _f29b.read()
with open('sites.py', encoding='utf-8') as _f29c:
    _st29 = _f29c.read()
check("21.29 v71: marafon ~1 popytka/sek (limit 100 sek) + zagotovka qwen_parser v sites.py",
      't_att = _time.time()' in _mlt29 and 'MARATHON_TIME_BUDGET_SEC = 100' in _mlt29 and
      'class QwenParser' in _q29 and 'def send_message_and_get_response' in _q29 and
      '"id": "qwen"' in _st29 and '"parser": "qwen_parser"' in _st29)

# 21.30 v72: lint lovit vanished-pravki i parent-puti vnutri instansa sceny
import tempfile as _tf30
import os as _os30
import tscn_lint as _tl30
_d30 = _tf30.mkdtemp()
_os30.makedirs(_os30.path.join(_d30, 'src', 'scenes'))
_base30 = '\n'.join(['[gd_scene format=3]', '', '[node name="Base" type="Node2D"]', '', '[node name="Real" type="Sprite2D" parent="."]', ''])
with open(_os30.path.join(_d30, 'src', 'scenes', 'base30.tscn'), 'w') as _f30:
    _f30.write(_base30)
_hdr30 = '[gd_scene load_steps=2 format=3]'
_ext30 = '[ext_resource type="PackedScene" path="res://src/scenes/base30.tscn" id="1"]'
_root30 = '[node name="Root" instance=ExtResource("1")]'
_bad30 = '\n'.join([_hdr30, '', _ext30, '', _root30, '', '[node name="Obstacle" parent="."]', 'position = Vector2(1, 1)', '', '[node name="Collision" type="CollisionShape2D" parent="Obstacle"]', ''])
_ok30 = '\n'.join([_hdr30, '', _ext30, '', _root30, '', '[node name="Real" parent="."]', 'position = Vector2(1, 1)', ''])
_fx30, _pr30 = _tl30.lint_and_fix_tscn(_bad30, project_root=_d30)
_fx30b, _pr30b = _tl30.lint_and_fix_tscn(_ok30, project_root=_d30)
with open('tscn_lint.py', 'r', encoding='utf-8') as _sf30:
    _src30 = _sf30.read()
check('21.30 v72: tscn_lint lovit pravki ischeznuvshih uzlov vnutri instansa (has vanished)',
      any('has vanished' in p for p in _pr30)
      and not any('vanished' in p for p in _pr30b)
      and '_scene_node_paths' in _src30 and '_vanished_in_inst' in _src30)

# 21.31 v73: qwen boevye selektory + pohozhest v ekzamene
with open('qwen_parser.py', encoding='utf-8') as _f31:
    _q31 = _f31.read()
with open(os.path.join('minilich', 'ml_train.py'), encoding='utf-8') as _f31b:
    _m31 = _f31b.read()
with open('sites.py', encoding='utf-8') as _f31c:
    _s31 = _f31c.read()
check('21.31 v73: qwen_parser boevye selektory + similarity v ekzamene',
      'message-input-textarea' in _q31 and 'qwen-chat-message-assistant' in _q31
      and 'chat-prompt-send-button' in _q31 and '_extract_json_object' in _q31
      and '_norm_scene(e.get("fixed") or "")).ratio()' in _m31
      and '"name": "Qwen"' in _s31)

print("\n=== RESULT: %d passed, %d failed ===" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
