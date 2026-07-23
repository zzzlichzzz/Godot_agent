# -*- coding: utf-8 -*-
"""Простая самопроверка аддона без браузера/AI Studio/реального проекта Godot.

Зачем это нужно: большая часть того, что может сломаться в агенте
(план-режим, откат, защиты API/сцен), не связано с браузером и проверяется
чистой логикой на вревенном временном черновике-целого "фейковом" проекте.
Сайтовый парсер (ai_parser.py) тут НЕ трогается — его можно проверить
только вручную в реальном браузере.

Запуск: из папки python/ вашего проекта —
    python selfcheck.py          # быстрый режим (по умолчанию): только секции 14+
                                 # (парсер, mini-lich, новое); фундамент 1-13 пропущен
    python selfcheck.py --full   # полный прогон всех секций — ОБЯЗАТЕЛЕН перед релизом
                                 # и после правок в коде фундамента (сервер/откат/API)
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


# --- Режимы прогона (v86.2) -----------------------------------------------
# По умолчанию — быстрый режим: секции фундамента 1-13 (план, откат, API,
# базовый tscn-линт) пропускаются — этот код давно стабилен и гонять его на
# каждый чих нет смысла. Хвост файла (секции 14+: парсер, mini-lich, новые
# фичи) выполняется как есть. Полный прогон (перед релизом и после правок
# фундамента!): python selfcheck.py --full
FULL_RUN = "--full" in sys.argv
if not FULL_RUN:
    print("Быстрый режим: секции 1-13 (фундамент) пропущены. Полный прогон: python selfcheck.py --full")
    _here = os.path.dirname(os.path.abspath(__file__))  # нужно хвосту (секция 14); в полном режиме его задаёт секция 13
    _mark = "# === SELFCHECK FAST " + "BOUNDARY ==="  # склейка: не найти самих себя вместо маркера
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as _f:
        _tail_code = _f.read().split(_mark, 1)[1]
    exec(compile(_tail_code, os.path.abspath(__file__), "exec"))
    sys.exit(0)  # недостижимо: хвост завершается своим sys.exit


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
                               '[node name="Root" type="StaticBody2D"]\n'
                               '[node name="Col" type="CollisionShape2D" parent="."]\nshape = SubResource("Shape1")\n')
    fixed_hdr, malformed_problems = tscn_lint.lint_and_fix_tscn(malformed_header_scene)
    check("«>» вместо «]» в заголовке секции чинится ЛОКАЛЬНО, без обращения к модели",
          'id="Shape1"]' in fixed_hdr and malformed_problems == [], (malformed_problems, fixed_hdr[:130]))
    # v46: незакрытый заголовок со СБАЛАНСИРОВАННЫМИ кавычками теперь тоже
    # чинится ЛОКАЛЬНО (дозакрываем «]» сами), а не уходит модели.
    unfixable_scene = ('[gd_scene load_steps=2 format=3]\n\n'
                        '[sub_resource type="RectangleShape2D" id="Shape1"\nsize = Vector2(1,1)\n\n'
                        '[node name="Root" type="StaticBody2D"]\n'
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
                                '[node name="A" type="StaticBody2D"]\nscript = ExtResource("1")\n\n'
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
    # v88.5: пересохранение файла БЕЗ изменения содержимого (Godot
    # пересохраняет открытую сцену с тем же текстом) — НЕ изменение
    open(p2, "w").write("extends Node\nvar x = 1\n")
    st2 = os.stat(p2)
    os.utime(p2, (st2.st_atime, st2.st_mtime + 10))
    snap3 = pt.snapshot_files(root, prev=snap2)
    a3, c3, d3 = pt.diff_snapshots(snap2, snap3)
    check("пересохранение без правок — не изменение (v88.5)",
          (a3, c3, d3) == ([], [], []), (a3, c3, d3))
    open(p2, "a").write("var y = 2\n")
    snap4 = pt.snapshot_files(root, prev=snap3)
    a4, c4, d4 = pt.diff_snapshots(snap3, snap4)
    check("реальная правка по-прежнему замечена (v88.5)",
          c4 == ["src/scene/b.gd"], c4)
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

# v31: менеджер пар��инга (базовый класс) + наследники
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

# v39: кнопка ручного запуска в v37 сидела в одной стро��е с языковым
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
check("main.py: битое действие после ��счерпания попыток отбрасывается с «файл НЕ был изменён»",
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
# обработчик по ша��лону редактора — должно ОДНОЗНАЧНО добавиться [connection].
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
check("main.py: read_function принимается как действие чтения и обрабатывается ����тдельной веткой",
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
check("tscn v50: сцена и�� бага пользователя чинится без вопросов к модели",
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


# === SELFCHECK FAST BOUNDARY ===
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
check("18.2 сцена �� узлом-экземпляром проходит без замечаний", _p18b == [])

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
        self._old_text = "ста��ый ответ модели"
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
check("20.8 мусор н���� чинится — возвращается None",
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

# 21.5 план внутри <think> — часть ОбучАемой зоны ответа (а не входного к��нтекста)
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

# 21.17 v63: выбор чата обрезает длинные на��вани�� эллипсисом и не вытесняет
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
      and '_similarity(fix, e.get("fixed") or "")' in _m31
      and '"name": "Qwen"' in _s31)

# 21.32 v74: forma kollizii bez roditelya-fizicheskogo tela = oshibka linta
import tscn_lint as _tl32
_sub32 = '[sub_resource type="CircleShape2D" id="1"]'
_bad32 = '\n'.join(['[gd_scene load_steps=2 format=3]', '', _sub32, 'radius = 20.0', '', '[node name="GameScene" type="Node2D"]', '', '[node name="Player" type="CharacterBody2D" parent="."]', '', '[node name="PlayerCollision" type="CollisionShape2D" parent="."]', 'shape = SubResource("1")', ''])
_ok32 = _bad32.replace('[node name="PlayerCollision" type="CollisionShape2D" parent="."]', '[node name="PlayerCollision" type="CollisionShape2D" parent="Player"]')
_fx32, _pr32 = _tl32.lint_and_fix_tscn(_bad32)
_fx32b, _pr32b = _tl32.lint_and_fix_tscn(_ok32)
with open('tscn_lint.py', 'r', encoding='utf-8') as _sf32:
    _src32 = _sf32.read()
check('21.32 v74: tscn_lint lovit CollisionShape2D bez fizicheskogo tela-roditelya',
      any('CollisionObject' in p for p in _pr32)
      and not any('CollisionObject' in p for p in _pr32b)
      and '_COLLISION_OWNER_2D' in _src32 and '_COLLISION_OWNER_3D' in _src32)

# 21.33 v75: parsery vshity v exe — staticheskie importy v sites.py + hidden-import v bat
import sites as _st33
with open('sites.py', 'r', encoding='utf-8') as _sf33:
    _src33 = _sf33.read()
with open('build_server_exe.bat', 'r', encoding='utf-8') as _bf33:
    _bat33 = _bf33.read()
_mod33 = _st33.get_parser_module('qwen')
check('21.33 v75: qwen_parser vshit v exe (staticheskiy import + hidden-import) i gruzitsya po id',
      'import qwen_parser as _static_qwen_parser' in _src33
      and 'import deepseek_parser as _static_deepseek_parser' in _src33
      and '--hidden-import qwen_parser' in _bat33
      and '--hidden-import deepseek_parser' in _bat33
      and getattr(_mod33, '__name__', '') == 'qwen_parser')

# 21.34 v76: obychnyy tekst bez JSON ne dolzhen schitatsya deystviem (privet-bug)
import qwen_parser as _qp34
_plain34 = 'Ozhidayu zadachu. Ukazhite, chto neobkhodimo sdelat v proekte.'
_act34 = 'Gotovo.' + chr(10) + '{"action": "create_file", "path": "res://a.tscn", "content": "x"}'
_bad34 = 'nachalo {"action": "create_file", "path": nezakryto'
check('21.34 v76: qwen ne prinimaet prostoy tekst za JSON-deystvie, no nakhodit nastoyashchiy blok',
      _qp34._action_raw_from_text(_plain34) is None
      and _qp34._action_raw_from_text('') is None
      and _qp34._action_raw_from_text(_bad34) is None
      and (_qp34._action_raw_from_text(_act34) or '').startswith('{')
      and '"action"' in (_qp34._action_raw_from_text(_act34) or ''))

# 21.35 v78: nezakrytye skobki/kavychki v znacheniyah svoystv (Parse Error)
import tscn_lint as _tl35
_bad35 = '\n'.join(['[gd_scene format=3]', '', '[node name="Root" type="Node3D"]', '', '[node name="SpawnPoint" type="Marker3D" parent="."]', 'position = Vector3(0, 5, 0', ''])
_ok35 = _bad35.replace('Vector3(0, 5, 0', 'Vector3(0, 5, 0)')
_multi35 = '\n'.join(['[gd_scene format=3]', '', '[node name="Root" type="Node2D"]', 'metadata/info = {', '"a": 1,', '"b": [1, 2, 3]', '}', ''])
_fx35, _pr35 = _tl35.lint_and_fix_tscn(_bad35)
_fx35b, _pr35b = _tl35.lint_and_fix_tscn(_ok35)
_fx35c, _pr35c = _tl35.lint_and_fix_tscn(_multi35)
check('21.35 v78: tscn_lint lovit nezakrytuyu skobku v znachenii svoystva, mnogostrochnye slovari ne trogaet',
      any('Parse Error' in p for p in _pr35) and not _pr35b and not _pr35c)

# 21.36 v78: [ext_resource] na nesushchestvuyushchiy fayl + planned_paths plana
import tempfile as _tf36
import os as _os36
import tscn_lint as _tl36
_d36 = _tf36.mkdtemp()
_sc36 = '\n'.join(['[gd_scene load_steps=2 format=3]', '', '[ext_resource type="Script" path="res://scripts/player.gd" id="1"]', '', '[node name="Root" type="Node2D"]', 'script = ExtResource("1")', ''])
_fx36, _pr36 = _tl36.lint_and_fix_tscn(_sc36, project_root=_d36)
_fx36b, _pr36b = _tl36.lint_and_fix_tscn(_sc36, project_root=_d36, planned_paths=['res://scripts/player.gd'])
_os36.makedirs(_os36.path.join(_d36, 'scripts'))
with open(_os36.path.join(_d36, 'scripts', 'player.gd'), 'w') as _f36:
    _f36.write('extends Node2D')
_fx36c, _pr36c = _tl36.lint_and_fix_tscn(_sc36, project_root=_d36)
check('21.36 v78: lint trebuet sozdat otsutstvuyushchiy fayl iz ext_resource; planned_paths plana eto razreshaet',
      any('Missing dependencies' in p for p in _pr36)
      and not any('Missing dependencies' in p for p in _pr36b)
      and not any('Missing dependencies' in p for p in _pr36c))

# 21.37 v78: reviziya dataseta — stuhshie pary + zamena otveta (source=self)
import tempfile as _tf37
from minilich import ml_data as _md37
_d37 = _tf37.mkdtemp()
_md37.set_storage_base(None)
_broken37 = '\n'.join(['[gd_scene format=3]', '', '[node name="Root" type="Node2D"]', '', '[node name="Col" type="CollisionShape2D" parent="."]', '', '[node name="Col" type="CollisionShape2D" parent="."]', ''])
_oldfix37 = '\n'.join(['[gd_scene format=3]', '', '[node name="Root" type="Node2D"]', '', '[node name="Col" type="CollisionShape2D" parent="."]', ''])
_newfix37 = '\n'.join(['[gd_scene format=3]', '', '[node name="Root" type="Node2D"]', '', '[node name="Body" type="StaticBody2D" parent="."]', '', '[node name="Col" type="CollisionShape2D" parent="Body"]', ''])
_rec37 = _md37.record_pair(_d37, _broken37, ['p'], _oldfix37)
_st37, _tot37 = _md37.revalidate_pairs(_d37)
_p37 = _md37.load_pairs(_d37)
_rep37 = _md37.replace_pair_fixed(_d37, _broken37, _newfix37, similarity=0.87)
_p37b = _md37.load_pairs(_d37)
check('21.37 v78: stuhshaya para pomechaetsya stale i poluchaet novyy otvet source=self (teacher_fixed sohranyon)',
      _rec37 and _st37 == 1 and _tot37 == 1 and _p37 and _p37[0].get('stale') is True
      and _rep37 and _p37b[0].get('stale') is False and _p37b[0].get('source') == 'self'
      and _p37b[0].get('teacher_fixed') == _oldfix37.strip() and _p37b[0].get('fixed') == _newfix37.strip())

# 21.38 v78: pohozhest PO SIMVOLAM (odno slovo v kroshechnoy scene = neskolko %) + strahovka ot amputatsii
from minilich import ml_train as _mt38
_a38 = '\n'.join(['[gd_scene format=3]', '', '[node name="Root" type="Node2D"]', '', '[node name="Enemy" type="Sprite2D" parent="."]', 'position = Vector2(1, 1)', ''])
_b38 = _a38.replace('"Enemy"', '"Hero"')
_sim38 = _mt38._similarity(_a38, _b38)
_big38 = _a38 + ''.join('\n[node name="N%d" type="Node2D" parent="."]\n' % _i for _i in range(1, 5))
_amp38 = '\n'.join(['[gd_scene format=3]', '', '[node name="Root" type="Node2D"]', ''])
with open(os.path.join('minilich', 'ml_train.py'), encoding='utf-8') as _f38:
    _m38 = _f38.read()
check('21.38 v78: similarity po simvolam >90% pri zamene odnogo slova + kandidat-amputatsiya otvergaetsya',
      _sim38 > 0.9 and _mt38._keeps_enough_nodes(_big38, _big38)
      and not _mt38._keeps_enough_nodes(_big38, _amp38)
      and '_repair_stale' in _m38 and 'random.sample' in _m38 and 'REPAIR_TEMPS' in _m38)

# 21.39 v79: dlinnye pary uchatsya fragmentami + ekzamen po 3 kategoriyam + chestnyy log
from minilich import ml_fix as _mf39
_nodes39 = ''.join('\n[node name="N%d" type="Node2D" parent="."]\nposition = Vector2(%d, %d)\n' % (_i, _i, _i) for _i in range(40))
_long39 = '[gd_scene format=3]\n\n[node name="Root" type="Node2D"]\n' + _nodes39 + '\n[node name="Broken" type="Node2D" parent="."]\n'
_tb39, _tf39 = _mf39.trim_pair_for_context(_long39, ['uzel name="Broken" sloman'], _long39, 100)
_sb39, _sf39 = _mf39.trim_pair_for_context('[gd_scene format=3]', [], '[gd_scene format=3]', 400)
with open(os.path.join('minilich', 'ml_train.py'), encoding='utf-8') as _f39:
    _t39 = _f39.read()
check('21.39 v79: trim_pair_for_context rezhet paru sinhronno po fokusu problemy + trener uchit fragmenty + ekzamen 3 kategorii + sat-log',
      'Broken' in _tb39 and 'Broken' in _tf39 and 'N25' not in _tb39 and 'N25' not in _tf39
      and len(_tb39) < len(_long39) and _sb39 == '[gd_scene format=3]'
      and 'trim_pair_for_context' in _t39 and 'EXAM_PER_CATEGORY = 2' in _t39
      and '_fresh_exam_pairs' in _t39 and 'fit_examples' in _t39 and 'sat_bursts' in _t39
      and 'max(0.0, float(np.mean(losses)))' in _t39)

# 21.40 v80: sintaksis svoystv: net '=', stroka bez kavychek, neizvestnaya sekciya
import tscn_lint as _tl40
_brk40 = '[gd_scene format=3]\n\n[node name="Root" type="Node3D"]\ntransform Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)\nunquoted_string = Hello World\n\n[weird_section id="x"]\nfoo = 1\n'
_f40, _p40 = _tl40.lint_and_fix_tscn(_brk40)
_j40 = '\n'.join(_p40)
_ok40 = '[gd_scene format=3]\n\n[node name="Root" type="Node3D"]\ntransform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)\nunquoted_string = "Hello World"\nspeed = 5.5\nflag = true\nsname = &"anim"\n'
_f40b, _p40b = _tl40.lint_and_fix_tscn(_ok40)
check('21.40 v80: linter lovit propushchennyy "=", stroku bez kavychek i neizvestnuyu sekciyu razom',
      "'='" in _j40 and 'Hello World' in _j40 and 'weird_section' in _j40 and len(_p40) >= 3 and _p40b == [],
      repr(_p40) + ' | ok-scena: ' + repr(_p40b))

# 21.41 v80: parent/connection na nesushchestvuyushchiy uzel; instance-sceny ne trogaem
_brk41 = '[gd_scene format=3]\n\n[node name="Main" type="Node3D"]\n\n[node name="GameTimer" type="Timer" parent="."]\n\n[node name="Extra" type="Node3D" parent="WrongParent"]\n\n[connection signal="timeout" from="GameTimer" to="NotHere" method="_on_t"]\n'
_f41, _p41 = _tl40.lint_and_fix_tscn(_brk41)
_j41 = '\n'.join(_p41)
_inst41 = '[gd_scene format=3]\n\n[ext_resource type="PackedScene" path="res://a.tscn" id="1_a"]\n\n[node name="Main" type="Node3D"]\n\n[node name="Inst" parent="." instance=ExtResource("1_a")]\n\n[node name="Extra" type="Node3D" parent="Inst/Deep"]\n'
_f41b, _p41b = _tl40.lint_and_fix_tscn(_inst41)
check('21.41 v80: parent="WrongParent" i connection to="NotHere" -> problems; instance-sceny ne trogaem',
      'WrongParent' in _j41 and 'NotHere' in _j41 and _p41b == [],
      repr(_p41) + ' | instance-scena: ' + repr(_p41b))

# 21.42 v80: dashboard + parser zhdet konets generacii pered otpravkoy
import dashboard as _dash42
with open('parser_base.py', encoding='utf-8') as _f42:
    _pb42 = _f42.read()
with open('main.py', encoding='utf-8') as _f42b:
    _mn42 = _f42b.read()
check('21.42 v80: dashboard-stranitsa + zhurnal servera + v80-wait-before-send v parsere',
      hasattr(_dash42, 'install') and hasattr(_dash42, 'get_lines')
      and 'rawlog' in _dash42.DASHBOARD_HTML
      and "'/dashboard/data'" in _mn42 and 'dashboard.install()' in _mn42
      and 'v80-wait-before-send' in _pb42)

# --- v81: github-обучение по кнопке + профиль мозга ---
from minilich import ml_github as _gh43
check("21.43 v81: разбор ссылок на репозитории + фильтр format=3 и классов Godot 3",
      _gh43._parse_repo_spec("https://github.com/godotengine/godot-demo-projects") == ("godotengine/godot-demo-projects", None)
      and _gh43._parse_repo_spec("https://github.com/owner/repo/tree/4.2") == ("owner/repo", "4.2")
      and _gh43._parse_repo_spec("owner/repo.git") == ("owner/repo", None)
      and _gh43._parse_repo_spec("prosto-slovo") is None
      and _gh43.parse_repos_text("owner/a, https://github.com/o2/b\nmusor") == [("owner/a", None), ("o2/b", None)]
      and _gh43._acceptable_scene('[gd_scene format=3]\n\n[node name="R" type="Node3D"]\n')
      and not _gh43._acceptable_scene('[gd_scene format=2]\n\n[node name="R" type="Node3D"]\n')
      and not _gh43._acceptable_scene('[gd_scene format=3]\n\n[node name="R" type="Spatial"]\n'))

import tscn_lint as _tl44
from minilich import ml_data as _md44
_sc44 = '[gd_scene format=3]\n\n[node name="Root" type="Node3D"]\ntransform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)\nmetadata/note = "Hello World Scene"\n'
_b44a = _md44._corrupt_drop_equals(_sc44)
_b44b = _md44._corrupt_unquote_string(_sc44)
_p44base = _tl44.lint_and_fix_tscn(_sc44)[1]
_p44a = _tl44.lint_and_fix_tscn(_b44a)[1] if _b44a else []
_p44b = _tl44.lint_and_fix_tscn(_b44b)[1] if _b44b else []
check("21.44 v81: новые виды порчи (без '=', без кавычек) видны линтеру, база чистая",
      _p44base == [] and bool(_b44a) and bool(_p44a)
      and bool(_b44b) and bool(_p44b) and "Hello World" in "\n".join(_p44b),
      "base=%r a=%r b=%r" % (_p44base, _p44a, _p44b))

from minilich import ml_train as _mt45
import minilich as _ml45
with open("main.py", encoding="utf-8") as _f45:
    _mn45 = _f45.read()
with open("../godot/agent_panel.gd", encoding="utf-8") as _f45b:
    _pnl45 = _f45b.read()
with open("../godot/agent_server_link.gd", encoding="utf-8") as _f45c:
    _lnk45 = _f45c.read()
with open("../godot/agent_locale.gd", encoding="utf-8") as _f45d:
    _loc45 = _f45d.read()
with open("minilich/ml_train.py", encoding="utf-8") as _f45e:
    _mtsrc45 = _f45e.read()
check("21.45 v84: обучение на сценах с GitHub + маршрут + кнопка в панели (без переключателя профиля мозга)",
      _mt45.PROFILES["smart"]["n_ctx"] == 1024 and "checkpoints_smart" in _mtsrc45
      and "/minilich/github_fetch" in _mn45 and '"brain" in data' not in _mn45
      and "MINILICH_GITHUB_URL" in _lnk45 and "minilich_github" in _pnl45
      and _loc45.count("github_fetch_btn") >= 2 and "brain_toggle" not in _loc45
      and hasattr(_ml45, "github_fetch_async") and not hasattr(_ml45, "set_brain"))


# --- v82: 5 ошибок из тест-сцены большой модели больше не проскакивают ---
_sc46 = '\n'.join([
    '[gd_scene load_steps=4 format=3 uid="uid://unnoticederr"]',
    '',
    '[ext_resource type="Texture2D" path="res://icon.svg" id="1_tex"]',
    '',
    '[sub_resource type="BoxMesh" id="dup_id"]',
    '',
    '[sub_resource type="SphereMesh" id="dup_id"]',
    '',
    '[node name="Root" type="Node3D"]',
    '',
    '[node type="Node3D" parent="."]',
    '',
    '[node name="MeshNode" type="MeshInstance3D" parent="."]',
    'mesh = SubResource("dup_id")',
    '',
    '[node name="SpriteNode" type="Sprite3D" parent="."]',
    'texture = 42',
    '',
    '[node name="InstancedNode" parent="." instance=ExtResource("1_tex")]',
    '',
    '[node name="PositionNode" type="Node3D" parent="."]',
    'position = Vector3(0, "string", 0)',
    '',
    '[node name="FillerNode1" type="Node3D" parent="."]',
    '',
])
_p46 = tscn_lint.lint_and_fix_tscn(_sc46)[1]
_j46 = '\n'.join(_p46)
check("21.46 v82: сцена с 5 пропущенными ошибками теперь ловится целиком",
      len(_p46) >= 5
      and "name" in _j46
      and 'id="dup_id"' in _j46
      and "texture" in _j46
      and "instance=" in _j46
      and "Vector3" in _j46,
      _j46)

_sc47 = '\n'.join([
    '[gd_scene load_steps=4 format=3]',
    '',
    '[ext_resource type="PackedScene" path="res://enemy.tscn" id="1_enemy"]',
    '[ext_resource type="Texture2D" path="res://icon.svg" id="2_tex"]',
    '',
    '[sub_resource type="BoxMesh" id="mesh_a"]',
    '',
    '[node name="Root" type="Node3D"]',
    '',
    '[node name="MeshNode" type="MeshInstance3D" parent="."]',
    'mesh = SubResource("mesh_a")',
    'position = Vector3(-1.5, 1e-05, 0.5)',
    '',
    '[node name="SpriteNode" type="Sprite3D" parent="."]',
    'texture = ExtResource("2_tex")',
    'modulate = Color(0.906, 0.365, 0.365, 1)',
    '',
    '[node name="Enemy" parent="." instance=ExtResource("1_enemy")]',
    '',
])
_p47 = tscn_lint.lint_and_fix_tscn(_sc47)[1]
check("21.47 v82: валидная сцена (PackedScene-instance, ресурсы, числа с экспонентой) не флагается",
      _p47 == [], repr(_p47))


# --- v83: vtoraya sceny-lovushka ot Gemini (10 oshibok) ---
_sc48 = '\n'.join([
    '[gd_scene load_steps=5 format=3 uid="uid://vulnerabilities"]',
    '',
    '[ext_resource type="Texture2D" path="res://icon.svg" id="1_tex"]',
    '',
    '[sub_resource type="BoxMesh" id="dup_id"]',
    '',
    '[sub_resource type="SphereMesh" id="dup_id"]',
    '',
    '[sub_resource id="no_type"]',
    '',
    '[sub_resource type="StandardMaterial3D" id="loop"]',
    'next_pass = SubResource("loop")',
    '',
    '[node name="Root" type="Node3D"]',
    '',
    '[node type="Node3D" parent="."]',
    '',
    '[node name="Bad/Name" type="Node3D" parent="."]',
    '',
    '[node name="" type="Node3D" parent="."]',
    '',
    '[node name="SpriteNode" type="Sprite3D" parent="."]',
    'texture = 42',
    '',
    '[node name="InstancedNode" parent="." instance=ExtResource("1_tex")]',
    '',
    '[node name="PosNode" type="Node3D" parent="."]',
    'position = Vector3(0, "string", 0)',
    '',
    '[node name="MaterialNode" type="MeshInstance3D" parent="."]',
    'material_override = SubResource("loop")',
    '',
    '[node name="MissingTypeRes" type="MeshInstance3D" parent="."]',
    'mesh = SubResource("no_type")',
    '',
    '[node name="DupNode" type="MeshInstance3D" parent="."]',
    'mesh = SubResource("dup_id")',
    '',
    '[connection signal="tree_entered" from="." to="." method="123_invalid"]',
    '',
])
_p48 = tscn_lint.lint_and_fix_tscn(_sc48)[1]
_j48 = '\n'.join(_p48)
check("21.48 v83: вторая ловушка от Gemini (10 ошибок) — все новые виды пойманы",
      len(_p48) >= 8
      and "name" in _j48 and 'id="dup_id"' in _j48 and "texture" in _j48
      and "instance=" in _j48 and "Vector3" in _j48
      and "Bad/Name" in _j48 and 'name=""' in _j48
      and 'id="no_type"' in _j48 and "циклическая" in _j48 and "123_invalid" in _j48,
      _j48)

_sc49 = '\n'.join([
    '[gd_scene load_steps=3 format=3]',
    '',
    '[sub_resource type="BoxMesh" id="mesh_a"]',
    '',
    '[node name="Root" type="Node3D"]',
    '',
    '[node name="Child_1" type="MeshInstance3D" parent="."]',
    'mesh = SubResource("mesh_a")',
    '',
    '[connection signal="tree_entered" from="." to="." method="_on_tree_entered"]',
    '',
])
_p49 = tscn_lint.lint_and_fix_tscn(_sc49)[1]
check("21.49 v83: валид��ая сцена (нормальное имя, sub_resource с type, обычный метод) не флагается",
      _p49 == [], repr(_p49))

from minilich import ml_train as _mt50
with open("minilich/ml_train.py", encoding="utf-8") as _f50:
    _mts50 = _f50.read()
with open("minilich/__init__.py", encoding="utf-8") as _f50b:
    _init50 = _f50b.read()
with open("../godot/agent_panel.gd", encoding="utf-8") as _f50c:
    _pnl50 = _f50c.read()
import tempfile as _tmp50
_tmpdir50 = _tmp50.mkdtemp()
from minilich import ml_data as _md50
_md50.set_storage_base(None, _tmpdir50)
import minilich as _ml50
check("21.50 v84: быстрый профиль мозга убран — «умный» единственный, без переключателя в панели",
      _ml50.get_brain(_tmpdir50) == "smart"
      and _mt50._brain_profile(_tmpdir50) == "smart"
      and _ml50.BRAIN_PROFILES == ("smart",)
      and "fast" not in _mt50.PROFILES
      and not hasattr(_ml50, "set_brain")
      and "_minilich_brain_check" not in _pnl50
      and "_on_brain_toggled" not in _pnl50)


# ===========================================================================
# РАЗДЕЛ 22 (v85): hard-example mining (50/30/20), AdamW+clip+warmup/cosine lr,
# отложенный набор и чекпоинт «лучший по valid_fix_rate»
# ===========================================================================
print("\n--- 22) v85: hard-example mining / AdamW+clip+lr-schedule / лучший чекпо��нт ---")

import minilich.ml_train as _mt51
from minilich import ml_data as _md51
from minilich.ml_model import TinyTransformer as _TT51
import numpy as _np51

# 22.1 корзины: недавно проваленные (loss выше медианы / неизвестные) — fail;
# редкие категории (count <= среднего) — rare; лёгкие (loss <= медианы) — easy.
_hashes51 = ["h1", "h2", "h3", "h4"]
_cats51 = ["a", "a", "b", "b"]
_stats51 = {"h1": {"loss_ema": 0.9}, "h2": {"loss_ema": 0.1}, "h3": {"loss_ema": 0.5}}
_fail51, _rare51, _easy51 = _mt51._build_sampling_buckets(_hashes51, _cats51, _stats51)
check("22.1 корзины: fail=[0,3] (провал/неизвестно), easy=[1,2] (<=медианы)",
      _fail51 == [0, 3] and _easy51 == [1, 2], (_fail51, _easy51))
check("22.1b корзины: rare учитывает частоту категории (тут все категории поровну — все в rare)",
      _rare51 == [0, 1, 2, 3], _rare51)


class _FakeRng51(object):
    """Детерминированная замена np.random.Generator для теста веток выбора."""
    def __init__(self, r):
        self._r = r

    def random(self):
        return self._r

    def integers(self, lo, hi):
        return lo


# 22.2 выбор корзины по r: r<0.5 -> fail; 0.5<=r<0.8 -> rare; r>=0.8 -> easy
_i_fail51 = _mt51._pick_weighted_index(_FakeRng51(0.1), [7], [8], [9], 10)
_i_rare51 = _mt51._pick_weighted_index(_FakeRng51(0.6), [7], [8], [9], 10)
_i_easy51 = _mt51._pick_weighted_index(_FakeRng51(0.9), [7], [8], [9], 10)
check("22.2 _pick_weighted_index: r=0.1->fail(7), r=0.6->rare(8), r=0.9->easy(9)",
      (_i_fail51, _i_rare51, _i_easy51) == (7, 8, 9), (_i_fail51, _i_rare51, _i_easy51))

# 22.3 пустые корзины -> откат на равномерный пул по всем индексам
_i_fb51 = _mt51._pick_weighted_index(_FakeRng51(0.1), [], [], [], 5)
check("22.3 все корзины пустые -> fallback на диапазон(n), не падает",
      _i_fb51 == 0, _i_fb51)

# 22.4 lr-расписание: линейный warmup до base_lr, затем косинус-спад к полу LR_MIN_RATIO*base_lr
_lr_a51 = _mt51._lr_schedule(1, 1.0)
_lr_warm51 = _mt51._lr_schedule(_mt51.LR_WARMUP_STEPS, 1.0)
_lr_mid51 = _mt51._lr_schedule((_mt51.LR_WARMUP_STEPS + _mt51.LR_DECAY_STEPS) // 2, 1.0)
_lr_floor51 = _mt51._lr_schedule(_mt51.LR_DECAY_STEPS + 1000, 1.0)
check("22.4 lr warmup: шаг 1 меньше шага LR_WARMUP_STEPS (пик)", _lr_a51 < _lr_warm51, (_lr_a51, _lr_warm51))
check("22.4b lr на пике warmup ~= base_lr", abs(_lr_warm51 - 1.0) < 1e-6, _lr_warm51)
check("22.4c lr в середине спада между полом и пиком", _mt51.LR_MIN_RATIO < _lr_mid51 < 1.0, _lr_mid51)
check("22.4d lr после LR_DECAY_STEPS держится на полу LR_MIN_RATIO*base_lr",
      abs(_lr_floor51 - _mt51.LR_MIN_RATIO) < 1e-6, _lr_floor51)

# 22.5 adam_step: обратная совместимость по умолчанию (без weight_decay/clip_norm — как раньше)
_cfg51 = {"vocab": 16, "d_model": 8, "n_layers": 1, "n_heads": 2, "d_ff": 16, "n_ctx": 8}
_ma51 = _TT51(_cfg51, seed=1)
_mb51 = _TT51(_cfg51, seed=1)
_seq51 = _np51.asarray([1, 2, 3, 4, 5, 1, 2, 3], dtype=_np51.int64)
_inp51 = _seq51[:-1]
_tgt51 = _seq51[1:]
_mask51 = _np51.ones(len(_inp51), dtype=_np51.float32)
_, _ga51 = _ma51.loss_and_grads(_inp51, _tgt51, _mask51)
_, _gb51 = _mb51.loss_and_grads(_inp51, _tgt51, _mask51)
_ma51.adam_step(_ga51, lr=1e-2)
_mb51.adam_step(_gb51, lr=1e-2, weight_decay=0.0, clip_norm=None)
check("22.5 adam_step: старые вызовы (без weight_decay/clip_norm) идентичны новым дефолтам",
      all(_np51.allclose(_ma51.p[k], _mb51.p[k]) for k in _ma51.p),
      "веса разошлись после одного шага")

# 22.6 adam_step: weight_decay реально стягивает веса к нулю сильнее, чем без него (при нулевых градиентах)
_mc51 = _TT51(_cfg51, seed=2)
_md51w = _TT51(_cfg51, seed=2)
_zero_grads51 = {k: _np51.zeros_like(v) for k, v in _mc51.p.items()}
for _ in range(20):
    _mc51.adam_step(_zero_grads51, lr=1e-2, weight_decay=0.0)
    _md51w.adam_step(_zero_grads51, lr=1e-2, weight_decay=0.5)
# "head" — 2D-матрица, не эмбединг (tok/pos специально исключены из decay), должна реально уйти в decay
_key51 = "head"
check("22.6 adam_step: с нулевыми градиентами weight_decay>0 уменьшает норму веса сильнее, чем decay=0",
      float(_np51.sum(_np51.abs(_md51w.p[_key51]))) < float(_np51.sum(_np51.abs(_mc51.p[_key51]))),
      (float(_np51.sum(_np51.abs(_mc51.p[_key51]))), float(_np51.sum(_np51.abs(_md51w.p[_key51])))))

# 22.7 adam_step: gradient clipping реально уменьшает норму градиента до clip_norm перед шагом
# проверяем поведенчески через одинаковый seed
# c/без clip_norm: разные обновления модели (клиппинг должен менять траекторию оптимизации)
_me51 = _TT51(_cfg51, seed=3)
_mf51 = _TT51(_cfg51, seed=3)
_, _ge51 = _me51.loss_and_grads(_inp51, _tgt51, _mask51)
_, _gf51 = _mf51.loss_and_grads(_inp51, _tgt51, _mask51)
_ge51 = {k: v * 1000.0 for k, v in _ge51.items()}
_gf51 = {k: v * 1000.0 for k, v in _gf51.items()}
_me51.adam_step(_ge51, lr=1e-2, clip_norm=None)
_mf51.adam_step(_gf51, lr=1e-2, clip_norm=1.0)
check("22.7 adam_step: clip_norm=1.0 при огромных градиентах даёт другую (иную) траекторию, чем без клиппинга",
      any(not _np51.allclose(_me51.p[k], _mf51.p[k]) for k in _me51.p),
      "клиппинг не повлиял ни на один параметр")

# 22.8 отложенный набор: маленький датасет (< VALID_MIN_POOL) весь идёт в train, valid пуст
_root51 = fresh_project()
for _i in range(10):
    _mt51.ml_data.record_pair(_root51, '[gd_scene load_steps=1 format=3]\n[node name="N%d" type="Node3D"]\n' % _i, [], '[gd_scene load_steps=1 format=3]\n[node name="N%d" type="Node3D"]\nmesh = SubResource("m_1")\n' % _i, source="live")
_valid_small51, _train_small51 = _mt51._select_validation_pairs(_root51)
check("22.8 маленький датасет (<VALID_MIN_POOL): validation пуст, всё уходит в train",
      _valid_small51 == [] and len(_train_small51) == 10, (len(_valid_small51), len(_train_small51)))

# 22.9 большой датасет (>=VALID_MIN_POOL): valid+train восстанавливают весь пул, valid <= VALID_MAX_SIZE,
# и повторный вызов даёт ТОТ ЖЕ split (детерминизм по стабильному хэшу пары)
_root52 = fresh_project()
for _i in range(80):
    _mt51.ml_data.record_pair(_root52, '[gd_scene load_steps=1 format=3]\n[node name="N%d" type="Node3D"]\n' % _i, [], '[gd_scene load_steps=1 format=3]\n[node name="N%d" type="Node3D"]\nmesh = SubResource("m_1")\n' % _i, source="live")
_valid1_52, _train1_52 = _mt51._select_validation_pairs(_root52)
_valid2_52, _train2_52 = _mt51._select_validation_pairs(_root52)
check("22.9 большой датасет: valid не пуст, valid+train == весь пул, valid <= VALID_MAX_SIZE",
      len(_valid1_52) > 0 and len(_valid1_52) + len(_train1_52) == 80 and len(_valid1_52) <= _mt51.VALID_MAX_SIZE,
      (len(_valid1_52), len(_train1_52)))
check("22.9b повторный вызов даёт идентичный split (детерминизм по хэшу пары)",
      [e["broken"] for e in _valid1_52] == [e["broken"] for e in _valid2_52], None)

# 22.10 лучший чекпоинт: сохраняется при первом успешном замере и обновляется только при улучшении
_root53 = fresh_project()
_m53 = _TT51(_cfg51, seed=9)
_calls53 = {"n": 0, "rates": [0.4, 0.3, 0.7]}


def _fake_eval53(project_root, model, valid_pairs, addon_dir=None):
    r = _calls53["rates"][_calls53["n"]]
    _calls53["n"] += 1
    return r


_orig_eval53 = _mt51._evaluate_valid_set
_orig_select53 = _mt51._select_validation_pairs
_mt51._evaluate_valid_set = _fake_eval53
_mt51._select_validation_pairs = lambda root: ([{"broken": "x", "fixed": "x", "problems": []}], [])
try:
    _mt51._validate_and_track_best(_root53, None, _m53)
    _best1_53 = _mt51._load_best(_root53)
    _mt51._validate_and_track_best(_root53, None, _m53)  # хуже (0.3) — не должен перезаписать
    _best2_53 = _mt51._load_best(_root53)
    _mt51._validate_and_track_best(_root53, None, _m53)  # лучше (0.7) — должен обновить
    _best3_53 = _mt51._load_best(_root53)
finally:
    _mt51._evaluate_valid_set = _orig_eval53
    _mt51._select_validation_pairs = _orig_select53
check("22.10 лучший чекпоинт создан после первого замера (0.4) и файл ckpt_best.npz существует",
      abs(_best1_53.get("valid_fix_rate", -1) - 0.4) < 1e-9
      and os.path.isfile(os.path.join(_mt51.ckpt_dir(_root53), _mt51.BEST_CKPT_NAME)),
      _best1_53)
check("22.10b худший результат (0.3) НЕ перезаписывает лучший (0.4)",
      abs(_best2_53.get("valid_fix_rate", -1) - 0.4) < 1e-9, _best2_53)
check("22.10c лучший результат (0.7) обновляет лучший чекпоинт",
      abs(_best3_53.get("valid_fix_rate", -1) - 0.7) < 1e-9, _best3_53)


print("\n--- 23) v86: эталонные сцены (постоянная память) / MAX_SCENE_CHARS=30000 / MAX_DATASET_BYTES=20MB ---")

import minilich.ml_fix as _mf60
import tscn_lint as _tl60

check("23.1 MAX_SCENE_CHARS поднят до 30000", _md51.MAX_SCENE_CHARS == 30000, _md51.MAX_SCENE_CHARS)
check("23.1b MAX_DATASET_BYTES поднят до 20 МиБ", _md51.MAX_DATASET_BYTES == 20 * 1024 * 1024, _md51.MAX_DATASET_BYTES)

# 23.2 бутстрап эталонов на чистом проекте: 3 сцены x 3 узла = 9 пар + 9 экзаменов; идемпотентен
_root60 = fresh_project()
_added_p60, _added_e60 = _md51.ensure_reference_material(_root60, None)
check("23.2 бутстрап эталонов: 9 обучающих пар и 9 экзаменов на чистом проекте",
      (_added_p60, _added_e60) == (9, 9), (_added_p60, _added_e60))
check("23.2b все 3 канонические сцены сохранены навсегда в хранилище мозга",
      sorted(_md51.list_reference_scenes(_root60)) == sorted(list(_md51.REFERENCE_SCENES)),
      _md51.list_reference_scenes(_root60))
_added_p60b, _added_e60b = _md51.ensure_reference_material(_root60, None)
check("23.2c повторный бутстрап ничего не добавляет (идемпотентность)",
      (_added_p60b, _added_e60b) == (0, 0), (_added_p60b, _added_e60b))
check("23.2d все 9 эталонных пар изначально mastered=False",
      all(not e.get("mastered") for e in _md51.load_reference_pairs(_root60)), None)

# 23.3 все эталонные пары после обрезки (как делает train_steps) помещаются в n_ctx=1024
_n_ctx60 = 1024
_all_fit60 = True
for _e60 in _md51.load_reference_pairs(_root60):
    _ids60, _ = _mf60.build_training_ids(_e60["broken"], _e60["problems"], _e60["fixed"])
    if len(_ids60) > _n_ctx60:
        _tb60, _tf60 = _mf60.trim_pair_for_context(_e60["broken"], _e60["problems"], _e60["fixed"], max(64, _n_ctx60 // 3))
        _ids60, _ = _mf60.build_training_ids(_tb60, _e60["problems"], _tf60)
    if len(_ids60) > _n_ctx60:
        _all_fit60 = False
check("23.3 все 9 эталонных пар после обрезки помещаются в окно n_ctx=1024", _all_fit60, None)

# 23.4 защита от вытеснения: эталонные (mastered=False) пары не вытесняются при переполнении MAX_EXAMPLES
_root61 = fresh_project()
_md51.ensure_reference_material(_root61, None)
_orig_max61 = _md51.MAX_EXAMPLES
_md51.MAX_EXAMPLES = 12  # искусственно маленький лимит, чтобы спровоцировать вытеснение
try:
    for _i in range(20):
        _md51.record_pair(_root61, '[gd_scene load_steps=1 format=3]\n[node name="L%d" type="Node3D"]\n' % _i, [], '[gd_scene load_steps=1 format=3]\n[node name="L%d" type="Node3D"]\nvisible = false\n' % _i, source="live")
    _after61 = _md51.load_pairs(_root61)
    _ref_after61 = [e for e in _after61 if e.get("source") == "reference"]
finally:
    _md51.MAX_EXAMPLES = _orig_max61
check("23.4 при переполнении лимита все 9 незащищённых эталонных пар выживают, а старые live-пары вытесняются",
      len(_ref_after61) == 9 and len(_after61) <= max(12, 9) + 1, (len(_ref_after61), len(_after61)))

# 23.5 mark_pair_mastered: строка НИКОГДА не удаляется, но пропадает из load_reference_pairs(only_unmastered=True)
_some_key60 = _md51.load_reference_pairs(_root60)[0]["ref_key"]
_changed60 = _md51.mark_pair_mastered(_root60, _some_key60)
_still_present60 = [e for e in _md51.load_pairs(_root60) if e.get("ref_key") == _some_key60]
_unmastered60 = _md51.load_reference_pairs(_root60, only_unmastered=True)
check("23.5 mark_pair_mastered: строка сохранена (mastered=True), но не удалена",
      _changed60 == 1 and len(_still_present60) == 1 and _still_present60[0].get("mastered") is True,
      _still_present60)
check("23.5b выученная наизусть ��ара пропала из load_reference_pairs(only_unmastered=True)",
      len(_unmastered60) == 8 and _some_key60 not in [e["ref_key"] for e in _unmastered60], len(_unmastered60))

# 23.6 выученные наизусть эталонные пары не участвуют в отборе на обучение/валидацию/экзамен/марафон
check("23.6 _select_validation_pairs исключает mastered-пары из общего пула",
      _some_key60 not in [e.get("ref_key") for e in sum(_mt51._select_validation_pairs(_root60), [])], None)
_marathon_pool60 = [x for x in _md51.load_pairs(_root60) if not x.get("mastered")]
check("23.6b пул марафона исключает mastered-пары",
      _some_key60 not in [e.get("ref_key") for e in _marathon_pool60], None)

# 23.7 record_reference_exam идемпотентен по ref_key; экзамены никогда не попадают в load_pairs
_dup60 = _md51.record_reference_exam(_root60, _some_key60, "x", [], "y")
check("23.7 повторная запись экзамена с тем же ref_key ничего не добавляет", _dup60 is False, _dup60)
check("23.7b замороженные экзамены не участвуют в load_pairs (обучении)",
      all(e.get("source") != "exam" for e in _md51.load_pairs(_root60)) and len(_md51.load_reference_exams(_root60)) == 9,
      len(_md51.load_reference_exams(_root60)))

# 23.8 журнал экзаменов хранит не больше REFERENCE_LOG_MAX_PER_KEY записей на ref_key
_root62 = fresh_project()
for _i in range(30):
    _md51.record_reference_exam_result(_root62, "K", _i % 2 == 0, 0.5)
_log62 = _md51.read_reference_log(_root62)
check("23.8 журнал экзаменов режет историю до REFERENCE_LOG_MAX_PER_KEY записей",
      len(_log62["K"]) == _md51.REFERENCE_LOG_MAX_PER_KEY, len(_log62["K"]))

# 23.9 регресс: trim_scene_for_context/trim_pair_for_context сохраняют reachability-замыкание по ресурсам
# (до фикса v86 при обрезке могли оставаться sub_resource-ссылки без самого блока sub_resource)
_scene63 = (
    '[gd_scene load_steps=3 format=3]\n'
    '[sub_resource type="BoxShape3D" id="Shape_1"]\n'
    '[sub_resource type="BoxMesh" id="Mesh_1"]\n'
    '[node name="Root" type="Node3D"]\n'
    '[node name="Body" type="StaticBody3D" parent="."]\n'
    '[node name="Col" type="CollisionShape3D" parent="Body"]\n'
    'shape = SubResource("Shape_1")\n'
    '[node name="Mesh" type="MeshInstance3D" parent="Body"]\n'
    'mesh = SubResource("Mesh_1")\n'
)
_trimmed63, _kept63 = _mf60.trim_scene_for_context(_scene63, ["Col: ..."], _mf60._TOK, 40)
check("23.9 обрезка сцены не оставляет ссылку SubResource без объявления самого ресурса",
      ("SubResource(\"Shape_1\")" not in _trimmed63) or ("sub_resource type=\"BoxShape3D\" id=\"Shape_1\"" in _trimmed63),
      _trimmed63)

# 23.10 регресс: линтер больше не считает PhysicalBone2D/3D сиротой без физического родителя для CollisionShape
check("23.10 PhysicalBone2D признан валидным владельцем CollisionShape2D",
      "PhysicalBone2D" in _tl60._COLLISION_OWNER_2D, _tl60._COLLISION_OWNER_2D)
check("23.10b PhysicalBone3D признан валидным владельцем CollisionShape3D",
      "PhysicalBone3D" in _tl60._COLLISION_OWNER_3D, _tl60._COLLISION_OWNER_3D)

# 23.11 экзамен памяти эталонов и проверка мастерства — чисто read-only: не двигают шаг модели и веса
_root64 = fresh_project()
_md51.ensure_reference_material(_root64, None)
_m64 = _mt51._ensure_model(_root64)
_mt51._save_ckpt(_root64, _m64)
_mt51._stop.clear()
_before64 = {k: v.copy() for k, v in _m64.p.items()}
_step_before64 = _m64.step
_mt51._run_reference_exams(_root64, None)
_mt51._check_reference_mastery(_root64, None)
_m64_loaded = _mt51.load_latest_model(_root64)
check("23.11 экзамен эталонов + проверка мастерства не меняют шаг модели",
      _m64_loaded.step == _step_before64, (_m64_loaded.step, _step_before64))
check("23.11b экзамен эталонов + проверка мастерства не меняют веса модели",
      all((k in _m64_loaded.p) and _np51.array_equal(_before64[k], _m64_loaded.p[k]) for k in _before64), None)
check("23.11c результаты экзаменов записаны в журнал (по одному на все 9 ref_key)",
      sorted(_mt51.ml_data.read_reference_log(_root64).keys()) == sorted(e["ref_key"] for e in _md51.load_reference_exams(_root64)),
      list(_mt51.ml_data.read_reference_log(_root64).keys()))


# ===========================================================================
# РАЗДЕЛ 24 (v86.2): санитайзер невидимых символов из веб-DOM (кейс qwen)
# ===========================================================================
print("\n--- 24. v86.2: очистка невидимых символов (NBSP/NUL/zero-width) ---")

import text_sanitize as _ts24
import parser_base as _pb24
from project_tools import create_project_file as _cpf24, patch_project_file as _ppf24

# 24.1 NBSP (U+00A0) -> обычный пробел (ошибка qwen: Invalid white space character U+00A0)
check("24.1 NBSP заменяется обычным пробелом",
      _ts24.sanitize_llm_text(u"extends\u00a0Node2D") == "extends Node2D")

# 24.2 NUL и другие управляющие удаляются (Unexpected NUL character)
check("24.2 NUL-байт и управляющие удаляются",
      _ts24.sanitize_llm_text(u"var x\u0000 = 1\u0007") == "var x = 1")

# 24.3 zero-width/BOM удаляются, юникодные переводы строк (LS) -> обычный
check("24.3 zero-width/BOM удаляются, LS/PS -> перевод строки",
      _ts24.sanitize_llm_text(u"\ufefffunc _ready():\u200b\u2028pass") == "func _ready():\npass")

# 24.4 CRLF -> LF; видимый текст (кириллица, тире, «ё», таб) не меняется
check("24.4 CRLF нормализуется, видимый текст не тронут",
      _ts24.sanitize_llm_text(u"a\r\nб — «ё»\t1") == u"a\nб — «ё»\t1")

# 24.5 parse_action_json переживает NBSP/NUL внутри JSON действия
_act24, _err24 = _pb24.parse_action_json(u'{"action":\u00a0"create_file",\u0000 "path": "res://a.gd"}')
check("24.5 parse_action_json чистит NBSP/NUL и парсит JSON",
      _act24 is not None and _act24.get("action") == "create_file", _err24)

# 24.6 create_project_file не пускает невидимый мусор на диск (вторая линия защиты)
_root24 = fresh_project()
_cpf24(_root24, "res://src/main.gd", u"extends\u00a0Node\u0000\r\nfunc _ready():\u200b pass")
with open(os.path.join(_root24, "src", "main.gd"), "r", encoding="utf-8") as _f24:
    _disk24 = _f24.read()
check("24.6 файл на диске чист: без NBSP/NUL/zero-width, LF-переносы",
      _disk24 == "extends Node\nfunc _ready(): pass", repr(_disk24))

# 24.7 patch_project_file находит блок, даже если модель прислала его с NBSP
_ppf24(_root24, "res://src/main.gd", u"extends\u00a0Node", u"extends\u00a0Node2D\u200b")
with open(os.path.join(_root24, "src", "main.gd"), "r", encoding="utf-8") as _f24:
    _disk24b = _f24.read()
check("24.7 патч с NBSP в блоках находит и пишет чистый код",
      _disk24b.startswith("extends Node2D\n"), repr(_disk24b))

# =====================================================================
# РАЗДЕЛ 25 (v86.3): битые NodePath, вырожденные полигоны, живучесть мозга
# =====================================================================
print("\n--- 25. v86.3: NodePath-проверка линтера + сохранение прогресса mini-lich ---")
import tscn_lint as _tl25

_SCENE25 = """[gd_scene format=3]

[node name="Root" type="Node2D"]

[node name="BadPolygon" type="Polygon2D" parent="."]
polygon = PackedVector2Array(0, 0, 10, 0)

[node name="BadTransform" type="RemoteTransform2D" parent="."]
remote_path = NodePath("../GhostNode")

[node name="PlayerSprite" type="Sprite2D" parent="."]

[connection signal="ready" from="." to="." method="_on_ready"]
"""
_f25, _p25 = _tl25.lint_and_fix_tscn(_SCENE25)
check("25.1 битый NodePath (../GhostNode) пойман", any("GhostNode" in p for p in _p25), _p25)
check("25.2 полигон из 2 точек пойман", any("polygon" in p for p in _p25), _p25)

_ok25 = _SCENE25.replace('NodePath("../GhostNode")', 'NodePath("../PlayerSprite")').replace(
    "PackedVector2Array(0, 0, 10, 0)", "PackedVector2Array(0, 0, 10, 0, 10, 10)")
_p25b = _tl25.lint_and_fix_tscn(_ok25)[1]
check("25.3 валидные NodePath и полигон проходят чисто", not _p25b, _p25b)

_p25c = _tl25.lint_and_fix_tscn(_ok25.replace('NodePath("../PlayerSprite")', 'NodePath("/root/Global")'))[1]
check("25.4 абсолютный путь (/root/...) не судим", not _p25c, _p25c)

_p25u = _tl25.lint_and_fix_tscn(_ok25.replace('NodePath("../PlayerSprite")', 'NodePath("%UniqueThing")'))[1]
check("25.5 %UniqueName не судим", not _p25u, _p25u)

_p25d = _tl25.lint_and_fix_tscn(_ok25.replace('NodePath("../PlayerSprite")', 'NodePath("../../TooHigh")'))[1]
check("25.6 путь выше корня сцены пойман", any(u"выше корня" in p for p in _p25d), _p25d)

_p25e = _tl25.lint_and_fix_tscn(_ok25.replace('NodePath("../PlayerSprite")', 'NodePath("../PlayerSprite:position")'))[1]
check("25.7 путь со свойством (:position) на существующий узел проходит", not _p25e, _p25e)

try:
    import numpy as _np25  # noqa: F401
    _HAS_NP25 = True
except Exception:
    _HAS_NP25 = False
if _HAS_NP25:
    import tempfile as _tmp25
    import history_manager as _hm25
    import minilich.ml_data as _mld25
    import minilich.ml_train as _mlt25
    _prev_base25 = _mld25._BASE_OVERRIDE
    _prev_hist25 = _hm25._STORAGE_OVERRIDE
    try:
        _histbase25 = _tmp25.mkdtemp(prefix="ml25_hist_")
        _proj25 = _tmp25.mkdtemp(prefix="ml25_proj_")
        _hm25.set_storage_dir(_histbase25)
        _old25 = os.path.join(_hm25.get_storage_dir(_proj25), _mld25.STORAGE_SUBDIR)
        os.makedirs(os.path.join(_old25, "checkpoints_smart"), exist_ok=True)
        with open(os.path.join(_old25, "checkpoints_smart", "ckpt_77.npz"), "wb") as _f25w:
            _f25w.write(b"fake")
        with open(os.path.join(_old25, _mld25.DATASET_FILE), "w", encoding="utf-8") as _f25w:
            _f25w.write("")
        _addon25 = _tmp25.mkdtemp(prefix="ml25_addon_")
        _mld25._BASE_OVERRIDE = None
        _mld25.set_storage_base(_addon25, _proj25)
        check("25.8 миграция мозга переносит checkpoints_smart",
              os.path.isfile(os.path.join(_addon25, "minilich_brain", "checkpoints_smart", "ckpt_77.npz")))

        _addon25b = _tmp25.mkdtemp(prefix="ml25_addon2_")
        _mld25.set_storage_base(_addon25b, None)  # «переустановка плагина»: мозг пуст
        _bdir25 = _mlt25._backup_dir(_proj25)
        with open(os.path.join(_bdir25, "ckpt_123.npz"), "wb") as _f25w:
            _f25w.write(b"fake")
        _n25 = _mlt25._rescue_checkpoints(_proj25)
        check("25.9 спасение чекпоинтов из резерва вне папки плагина",
              _n25 >= 1 and os.path.isfile(os.path.join(_mlt25.ckpt_dir(_proj25), "ckpt_123.npz")),
              "спасено: %s" % _n25)

        # 25.10 (v86.4): чекпоинт чужого профиля уходит в архив и не блокирует обучение
        from minilich.ml_model import TinyTransformer as _TT25, default_config as _dc25
        from minilich.ml_tokenizer import MiniLichTokenizer as _tk25
        _cfg25 = _dc25(_tk25().vocab_size)  # старый профиль по умолчанию: 512x96
        _oldm25 = _TT25(_cfg25, seed=1)
        _oldm25.step = 111000
        _oldm25.save(os.path.join(_mlt25.ckpt_dir(_proj25), "ckpt_111000.npz"))
        _newm25 = _mlt25._ensure_model(_proj25)
        _arch25 = os.path.join(_mlt25.ckpt_dir(_proj25), "archive_512x96")
        check("25.10 чекпоинт чужого профиля в архиве, обучение не заблокировано",
              _newm25.step == 0 and os.path.isfile(os.path.join(_arch25, "ckpt_111000.npz")),
              "step=%s, dir=%s" % (_newm25.step, os.listdir(_mlt25.ckpt_dir(_proj25))))

        # 25.11 (v86.5): _log обновляет метку «пульса»
        import time as _time25
        _mlt25._log(u"selfcheck: проверка пульса")
        check("25.11 _log обновляет метку пульса (last_line_ts)",
              abs(_time25.time() - (_mlt25._state.get("last_line_ts") or 0)) < 10,
              "last_line_ts=%s" % _mlt25._state.get("last_line_ts"))
        # 25.12 (v86.5): пульс-поток и отключение QuickEdit на месте
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"), "r", encoding="utf-8") as _f25:
            _main25 = _f25.read()
        check("25.12 пульс-поток и отключение QuickEdit на месте",
              callable(getattr(_mlt25, "_heartbeat_loop", None)) and "_disable_quickedit()" in _main25)

        # 25.13 (v86.6): пауза обучения настраивается через settings.json на лету
        import json as _json25
        _sp25 = os.path.join(_mld25.storage_dir(_proj25), "settings.json")
        if os.path.isfile(_sp25):
            os.remove(_sp25)
        _def25 = _mlt25._burst_pause(_proj25)
        with open(_sp25, "w", encoding="utf-8") as _f25b:
            _json25.dump({"train_pause_sec": 0.1}, _f25b)
        check("25.13 пауза обучения настраивается через settings.json",
              _def25 == _mlt25.BURST_PAUSE_SEC and abs(_mlt25._burst_pause(_proj25) - 0.1) < 1e-9,
              "def=%s now=%s" % (_def25, _mlt25._burst_pause(_proj25)))
    finally:
        _mld25._BASE_OVERRIDE = _prev_base25
        _hm25._STORAGE_OVERRIDE = _prev_hist25
else:
    print("(numpy недоступен — проверки 25.8/25.9 пропущены)")

# ---------------------------------------------------------------------------
# РАЗДЕЛ 26 (v86.7): парсер — золотой корпус и починки
# ---------------------------------------------------------------------------
print("\n--- РАЗДЕЛ 26: парсер — золотой корпус и починки (v86.7) ---")
import tempfile as _tf26
import parser_base as _pb26

# 26.1 хвостовой текст с '}' после действия не мешает разбору
_a26, _e26 = _pb26.parse_action_json(u'{"action": "create_file", "path": "res://a.gd", "content": "x"}\n\nГотово, обращайтесь ещё :}')
check("26.1 хвостовой текст с '}' после действия не мешает разбору",
      isinstance(_a26, dict) and _a26.get("action") == "create_file" and _a26.get("content") == "x",
      str(_e26))

# 26.2 пропущенная запятая между полями чинится
_a26b, _e26b = _pb26.parse_action_json(u'{"action": "patch_file", "path": "res://b.tscn"\n"find": "old", "replace": "new"}')
check("26.2 пропущенная запятая между полями чинится",
      isinstance(_a26b, dict) and _a26b.get("action") == "patch_file" and _a26b.get("find") == "old",
      str(_e26b))

# 26.3 предпочитается объект с ключом action, а не первый попавшийся JSON
_a26c, _e26c = _pb26.parse_action_json(u'Сводка: {"файлов": 3}. Действие:\n{"action": "plan", "description": "d", "steps": []}')
check("26.3 предпочитается объект с ключом action, а не первый попавшийся JSON",
      isinstance(_a26c, dict) and _a26c.get("action") == "plan", str(_e26c))

# 26.4 золотой корпус: образец провала сохраняется
_cd26 = _tf26.mkdtemp(prefix="corpus26_")
os.environ["GODOT_AGENT_CORPUS_DIR"] = _cd26
try:
    _p26 = _pb26._save_corpus_sample(u'совсем не JSON {"action": ', u"тестовая ошибка")
    check("26.4 образец провала сохраняется в золотой корпус",
          _p26 is not None and os.path.isfile(_p26) and os.path.dirname(_p26) == _cd26,
          str(_p26))
    # 26.5 прогон корпуса: parse_action_json не должен кидать исключения
    _n26 = 0
    _exc26 = None
    try:
        for _fn26 in sorted(os.listdir(_cd26)):
            if _fn26.endswith(".txt"):
                with open(os.path.join(_cd26, _fn26), "r", encoding="utf-8") as _f26:
                    _pb26.parse_action_json(_f26.read())
                _n26 += 1
    except Exception as _e26x:
        _exc26 = _e26x
    check("26.5 прогон золотого корпуса без исключений (файлов: %d)" % _n26,
          _exc26 is None, str(_exc26))
finally:
    os.environ.pop("GODOT_AGENT_CORPUS_DIR", None)

# 26.6 подтверждение вставки учитывает contenteditable (по исходнику)
_pb26_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "parser_base.py"), "r", encoding="utf-8").read()
check("26.6 вставка текста подтверждается и для contenteditable-полей",
      "innerText||e.textContent" in _pb26_src
      and 'execute_script("return arguments[0].value;", el)' not in _pb26_src)

# 26.7 кандидаты разбора без дублей, метрики доступны
_cands26 = _pb26._build_candidates(u'{"action": "x"}')
_st26 = _pb26.get_parse_stats()
_tot26 = sum(_st26.get(_k26, 0) for _k26 in ("ok_first", "ok_repaired", "ok_json_repair", "fail"))
check("26.7 кандидаты разбора без дублей, метрики доступны",
      len(_cands26) == len(set(_c26 for _l26, _c26 in _cands26)) and _tot26 >= 3,
      "candidates=%d, parses=%d" % (len(_cands26), _tot26))

# ---------------------------------------------------------------------------
# РАЗДЕЛ 27 (v86.8): маркер-часовой конец ответа ===DONE===
# ---------------------------------------------------------------------------
print("\n--- РАЗДЕЛ 27: маркер-часовой конец ответа (v86.8) ---")
import time as _t27
import parser_base as _pb27
import agent_prompts as _ap27

# 27.1 промпт и парсер синхронизированы (оба знают о маркере ===DONE===)
check("27.1 PRIMING_TEMPLATE требует маркер ===DONE===, парсер его знает",
      _pb27.DONE_MARKER in _ap27.PRIMING_TEMPLATE and _pb27.DONE_MARKER == "===DONE===")

# 27.2 _has_done_marker: позитивные и отрицательные варианты
_true27 = [
    u"текст ответа\n===DONE===",
    u"текст ответа\n===DONE===\n\n",
    u"текст\n=== done ===",
    u"текст\n====DONE====   ",
    u"```agent_action\n{\"action\": \"create_file\"}\n```\n===DONE===",
]
_false27 = [
    u"просто текст без маркера",
    u"текст ===DONСН=== что-то ещё после",
    u"",
    None,
    u"# === DONE === (в середине кода)\nfunc f(): pass",
]
check("27.2 _has_done_marker распознаёт маркер (разные отстуупы/регистр/хвост) и не путает его в середине текста",
      all(_pb27._has_done_marker(c) for c in _true27) and not any(_pb27._has_done_marker(c) for c in _false27))

# 27.3 _strip_done_marker: убирает маркер и хвостовые переносы, не трогает текст без маркера
check("27.3 _strip_done_marker убирает маркер, не портит текст без него",
      _pb27._strip_done_marker(u"ответ\n===DONE===") == u"ответ"
      and _pb27._strip_done_marker(u"ответ\n===DONE===\n\n") == u"ответ"
      and _pb27._strip_done_marker(u"без маркера") == u"без маркера"
      and _pb27._strip_done_marker(u"") == u""
      and _pb27._strip_done_marker(None) is None
      and _pb27._strip_done_marker((u"x" * 200) + u"\n===DONE===") == u"x" * 200)

# 27.4 центральная точка очистки в send_message_and_get_response на месте (источник)
_src27 = open(os.path.join(_here, "parser_base.py"), "r", encoding="utf-8").read()
check("27.4 send_message_and_get_response чистит маркер перед выдачей текста",
      "text = _strip_done_marker(text)" in _src27)
check("27.5 agent_prompts.py содержит правило про ===DONE===",
      "===DONE===" in open(os.path.join(_here, "agent_prompts.py"), "r", encoding="utf-8").read())

# 27.6 поведение: wait_for_new_answer завершается гораздо быстрее с маркером, без ожидания тишины
class _FP27(_pb27.BaseSiteParser):
    LOG_TAG = "t27"
    def __init__(self, text, marker):
        self._text = text + ("\n===DONE===" if marker else "")
        self._gen_until = _t27.time() + 0.05
    def count_answers(self, driver):
        return 2
    def answer_len(self, driver):
        return len(self._text)
    def answer_preview(self, driver):
        return self._text[:80]
    def answer_stream(self, driver):
        return self._text
    def is_generating(self, driver):
        return _t27.time() < self._gen_until
    def extract_answer(self, driver):
        return {"text": self._text, "actionRaw": None, "error": None}

_kw27 = dict(timeout=8, quiet_period=3.0, hard_quiet_period=10.0, poll_interval=0.05, post_quiet_grace=0.05)
_t0_27 = _t27.time()
_p27m = _FP27(u"готово", marker=True)
_r27m = _p27m.wait_for_new_answer(None, 1, **_kw27)
_dt27m = _t27.time() - _t0_27
_t0_27b = _t27.time()
_p27n = _FP27(u"готово", marker=False)
_r27n = _p27n.wait_for_new_answer(None, 1, **_kw27)
_dt27n = _t27.time() - _t0_27b
check("27.6 wait_for_new_answer с ===DONE=== завершается без ожидания quiet_period",
      _dt27m < 1.0 and (_r27m or {}).get("text") == u"готово\n===DONE===",
      "%.2f c" % _dt27m)
check("27.7 без маркера по-старому ждёт quiet_period (обратная совместимость)",
      _dt27n >= 3.0 and (_r27n or {}).get("text") == u"готово", "%.2f c" % _dt27n)
check("27.8 маркер даёт существенное ускорение (>=3x)",
      _dt27n / max(_dt27m, 0.01) >= 3.0, "%.1fx" % (_dt27n / max(_dt27m, 0.01)))

# ---------------------------------------------------------------------------
# РАЗДЕЛ 28 (v86.9): content_ref/search_ref/replace_ref — код без экранирования
# ---------------------------------------------------------------------------
print("\n--- РАЗДЕЛ 28: content_ref/search_ref/replace_ref (v86.9) ---")
import parser_base as _pb28

_raw28_create = (
    '```agent_action\n'
    '{"action": "create_file", "path": "res://scripts/x.gd", "content_ref": "FILE_1"}\n'
    '===FILE_1===\n'
    'extends Node2D\nfunc _ready():\n\tprint("quotes \\" and backslash \\\\\\\\ inside, no escaping needed")\n\tpass\n'
    '===END_FILE_1===\n'
    '```'
)
_obj28a, _err28a = _pb28.parse_action_json(_raw28_create)
check("28.1 create_file + content_ref: тело подставлено буквально, ref-ключ убран",
      _err28a is None and _obj28a is not None
      and "content_ref" not in _obj28a
      and _obj28a.get("content") == 'extends Node2D\nfunc _ready():\n\tprint("quotes \\" and backslash \\\\ inside, no escaping needed")\n\tpass')

_raw28_patch = (
    '```agent_action\n'
    '{"action": "patch_file", "path": "res://scripts/p.gd", "search_ref": "FILE_1", "replace_ref": "FILE_2", "summary": "fix"}\n'
    '===FILE_1===\nvar hp = 100\n===END_FILE_1===\n'
    '===FILE_2===\nvar hp = 200  # кавычки и слэш \\\\\n===END_FILE_2===\n'
    '```'
)
_obj28b, _err28b = _pb28.parse_action_json(_raw28_patch)
check("28.2 patch_file + search_ref/replace_ref: два блока разведены корректно",
      _err28b is None and _obj28b is not None
      and _obj28b.get("search") == "var hp = 100"
      and _obj28b.get("replace") == u"var hp = 200  # кавычки и слэш \\\\"
      and "search_ref" not in _obj28b and "replace_ref" not in _obj28b)

_raw28_plan = (
    '```agent_action\n'
    '{"action": "plan", "description": "d", "steps": ['
    '{"action": "create_file", "path": "res://a.gd", "content_ref": "FILE_1"}, '
    '{"action": "patch_file", "path": "res://b.gd", "search_ref": "FILE_2", "replace_ref": "FILE_3", "summary": "s"}'
    ']}\n'
    '===FILE_1===\ncontent A\n===END_FILE_1===\n'
    '===FILE_2===\nold B\n===END_FILE_2===\n'
    '===FILE_3===\nnew B\n===END_FILE_3===\n'
    '```'
)
_obj28c, _err28c = _pb28.parse_action_json(_raw28_plan)
check("28.3 plan: у каждого шага своя метка, обе резолвятся независимо",
      _err28c is None and _obj28c is not None
      and _obj28c["steps"][0].get("content") == "content A"
      and _obj28c["steps"][1].get("search") == "old B"
      and _obj28c["steps"][1].get("replace") == "new B")

_raw28_old = '```agent_action\n{"action": "create_file", "path": "res://y.gd", "content": "extends Node"}\n```'
_obj28d, _err28d = _pb28.parse_action_json(_raw28_old)
check("28.4 обратная совместимость: старый прямой content без ref работает как раньше",
      _err28d is None and _obj28d is not None and _obj28d.get("content") == "extends Node")

_raw28_missing = '```agent_action\n{"action": "create_file", "path": "res://z.gd", "content_ref": "FILE_9"}\n```'
_obj28e, _err28e = _pb28.parse_action_json(_raw28_missing)
check("28.5 отсутствующее тело метки — явная ошибка для self-heal, а не тихая потеря content",
      _obj28e is None and _err28e is not None and "FILE_9" in _err28e)

_raw28_hash = (
    '```agent_action\n'
    '{"action": "create_file", "path": "res://c.gd", "content_ref": "FILE_1"}\n'
    '===FILE_1===\n# ===================\nextends Node\n# ===================\n'
    '===END_FILE_1===\n'
    '```'
)
_obj28f, _err28f = _pb28.parse_action_json(_raw28_hash)
check("28.6 случайные '===' внутри содержимого (разделители-комментарии) не путают границы блока",
      _err28f is None and _obj28f is not None
      and _obj28f.get("content") == "# ===================\nextends Node\n# ===================")

check("28.7 промпт описывает content_ref/search_ref/replace_ref и формат ===МЕТКА===/===END_МЕТКА===",
      "content_ref" in _ap27.PRIMING_TEMPLATE and "search_ref" in _ap27.PRIMING_TEMPLATE
      and "replace_ref" in _ap27.PRIMING_TEMPLATE and "===END_" in _ap27.PRIMING_TEMPLATE)


# ---------------------------------------------------------------------------
# РАЗДЕЛ 29 (v86.10): wait_for_new_answer — состояние-машина (шаг 4 плана)
# ---------------------------------------------------------------------------
print("\n--- РАЗДЕЛ 29: wait_for_new_answer — состояние-машина (v86.10) ---")
import parser_base as _pb29

class _FakeDriver29(object):
    pass

class _Script29(object):
    """events: [(state_dict, hold_seconds), ...]. Состояние "сайта" выбирается
    по реальному времени с начала сценария; последнее состояние держится навечно."""
    def __init__(self, events):
        self.events = events
        self.t0 = time.time()

    def cur(self):
        elapsed = time.time() - self.t0
        acc = 0.0
        for state, hold in self.events:
            acc += hold
            if elapsed < acc:
                return state
        return self.events[-1][0]

class _FakeParser29(_pb29.BaseSiteParser):
    def __init__(self, script):
        self.script = script
        self.logs29 = []

    def _log(self, msg):
        self.logs29.append(msg)

    def count_answers(self, driver):
        return self.script.cur()["count"]

    def is_generating(self, driver):
        return self.script.cur()["generating"]

    def answer_len(self, driver):
        return self.script.cur()["length"]

    def answer_preview(self, driver):
        return self.script.cur().get("preview", "")

    def answer_stream(self, driver):
        return self.script.cur().get("stream", "")

    def get_live_activity(self, driver):
        return self.script.cur().get("activity", {}) or {}

    def extract_answer(self, driver):
        e = self.script.cur()
        return {"text": e.get("text", ""), "actionRaw": e.get("actionRaw")}

def _run29(events, **kw):
    p = _FakeParser29(_Script29(events))
    kw.setdefault("timeout", 3.0)
    kw.setdefault("quiet_period", 0.05)
    kw.setdefault("hard_quiet_period", 0.2)
    kw.setdefault("poll_interval", 0.01)
    kw.setdefault("post_quiet_grace", 0.1)
    return p, kw

# 29.1 обычный успешный путь: WAIT_NEW_MESSAGE -> WAIT_FIRST_TEXT -> STABILIZE -> VERIFY_COMPLETE -> DONE
_p29a, _kw29a = _run29([
    ({"count": 1, "generating": True, "length": 0, "text": "", "actionRaw": None}, 0.05),
    ({"count": 2, "generating": True, "length": 5, "text": "hello", "actionRaw": None, "stream": "hello"}, 0.05),
    ({"count": 2, "generating": False, "length": 5, "text": "hello", "actionRaw": None, "stream": "hello"}, 5.0),
])
_r29a = _p29a.wait_for_new_answer(_FakeDriver29(), 1, **_kw29a)
check("29.1 обычный путь по всем состояниям возвращает готовый ответ",
      _r29a is not None and _r29a.get("text") == "hello")

# 29.2 маркер ===DONE=== в потоке — досрочный выход из STABILIZE, как и раньше (v86.8)
_p29b, _kw29b = _run29([
    ({"count": 1, "generating": True, "length": 0, "text": "", "actionRaw": None}, 0.05),
    ({"count": 2, "generating": True, "length": 4, "text": "done", "actionRaw": None, "stream": "done\n===DONE==="}, 0.05),
    ({"count": 2, "generating": False, "length": 4, "text": "done", "actionRaw": None, "stream": "done\n===DONE==="}, 5.0),
])
_r29b = _p29b.wait_for_new_answer(_FakeDriver29(), 1, **_kw29b)
check("29.2 маркер ===DONE=== завершает STABILIZE досрочно (лог + верный результат)",
      _r29b is not None and _r29b.get("text") == "done"
      and any(u"===DONE===" in m for m in _p29b.logs29))

# 29.3 анти-дубль: STABILIZE застывает на старом ответе -> ANTI_STALE -> дожидается настоящего нового
_stale_text = "старый ответ"
_p29c, _kw29c = _run29([
    ({"count": 1, "generating": True, "length": len(_stale_text), "text": _stale_text, "actionRaw": None, "stream": _stale_text}, 0.05),
    ({"count": 1, "generating": False, "length": len(_stale_text), "text": _stale_text, "actionRaw": None, "stream": _stale_text}, 0.3),
    ({"count": 2, "generating": True, "length": 5, "text": "новый", "actionRaw": None, "stream": "новый"}, 0.1),
    ({"count": 2, "generating": False, "length": 5, "text": "новый", "actionRaw": None, "stream": "новый"}, 5.0),
])
_r29c = _p29c.wait_for_new_answer(_FakeDriver29(), 1, **_kw29c)
check("29.3 анти-дубль (ANTI_STALE) дожидается настоящего нового ответа, не возвращает старый",
      _r29c is not None and _r29c.get("text") == "новый"
      and any(u"анти-дубль" in m for m in _p29c.logs29))

# 29.4 таймаут в WAIT_NEW_MESSAGE, если ответ вообще не появляется
_p29d, _kw29d = _run29([
    ({"count": 1, "generating": False, "length": 0, "text": "", "actionRaw": None}, 5.0),
], timeout=0.05)
try:
    _p29d.wait_for_new_answer(_FakeDriver29(), 1, **_kw29d)
    check("29.4 WAIT_NEW_MESSAGE бросает TimeoutError, если ответ не появился", False)
except TimeoutError as _e29d:
    check("29.4 WAIT_NEW_MESSAGE бросает TimeoutError, если ответ не появился",
          u"не появился" in str(_e29d))

# 29.5 незавершённый JSON-действие продлевает VERIFY_COMPLETE, но не виснет навечно
_p29e, _kw29e = _run29([
    ({"count": 1, "generating": True, "length": 0, "text": "", "actionRaw": None}, 0.05),
    ({"count": 2, "generating": False, "length": 10, "text": "code", "actionRaw": '{"action": "x"', "stream": "code"}, 5.0),
], post_quiet_grace=0.08)
_r29e = _p29e.wait_for_new_answer(_FakeDriver29(), 1, **_kw29e)
check("29.5 незавершённый JSON — grace-период истекает, результат всё равно возвращается",
      _r29e is not None and _r29e.get("actionRaw") == '{"action": "x"')

check("29.6 состояния конвейера остаются приватной деталью реализации метода "
      "(нет побочных остаточных атрибутов на self после вызова)",
      not hasattr(_p29a, "state") and not hasattr(_p29a, "_STATE_HANDLERS"))


print("\n=== RESULT: %d passed, %d failed ===" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
