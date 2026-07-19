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
    srv.STATE["action_note"] = ""
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
    client.post("/chat/plan/step")
    j2 = client.post("/chat/plan/step").get_json()
    check("битый шаг останавливает цепочку, не ломая уже сделанное",
          j2.get("ok") is False and j2.get("stopped") is True and os.path.isfile(os.path.join(root, "c.gd"))
          and not os.path.isfile(os.path.join(root, "d.gd")), j2)
    history.rollback_chain(root, chain_id, force=False)
finally:
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
    jr = client2.post("/chat/plan/step").get_json()
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
    unfixable_scene = ('[gd_scene load_steps=2 format=3]\n\n'
                        '[sub_resource type="RectangleShape2D" id="Shape1"\nsize = Vector2(1,1)\n\n'
                        '[node name="Root" type="Node2D"]\n')
    _, unfixable_problems = tscn_lint.lint_and_fix_tscn(unfixable_scene)
    check("незакрытый заголовок секции без «>» по-прежнему ловится",
          any("не закрыт" in p for p in unfixable_problems), unfixable_problems)

    create_project_file(root, "res://demo.tscn", good_scene)
    desc = describe_scene(root, "res://demo.tscn")
    check("describe_scene показыва��т корень и детей сцены",
          "Root" in desc and "Icon" in desc and "Sprite2D" in desc, desc[:200])
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


print("\n=== RESULT: %d passed, %d failed ===" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
