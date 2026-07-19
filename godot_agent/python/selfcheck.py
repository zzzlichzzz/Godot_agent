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

# v30: сайт DeepSeek + выбор парсера по сайту + быстрый повторный запуск сервера
import sites as _sites
check("сайт DeepSeek зарегистрирован",
      (_sites.get_site("deepseek") or {}).get("parser") == "deepseek_parser"
      and (_sites.detect_site("https://chat.deepseek.com/a/chat/s/abc") or {}).get("id") == "deepseek"
      and (_sites.detect_site("https://aistudio.google.com/prompts/new_chat") or {}).get("id") == "aistudio")
check("выбо�� парсера по сайту работает",
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
check("стартовый экран: кнопка/подсказка ручного запуска рядом с языковым переключателем",
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

print("\n=== RESULT: %d passed, %d failed ===" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
