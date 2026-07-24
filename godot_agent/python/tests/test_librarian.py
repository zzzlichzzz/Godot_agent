# -*- coding: utf-8 -*-
"""v105: офлайн-тесты Библиотекаря (ask_librarian): слои ответа, бюджет,
подтокены snake_case, микро-обновление индекса, исключение addons/."""
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
import os
import tempfile

import librarian
from minilich import ml_project_index


PLAYER_GD = '''class_name Player
extends CharacterBody2D

signal died

var health := 100

func take_damage(amount: int) -> void:
\thealth -= amount
\tif health <= 0:
\t\tdied.emit()

func _physics_process(delta: float) -> void:
\tmove_and_slide()
'''

GM_GD = '''extends Node

func hurt_player(player, amount):
\tplayer.take_damage(amount)
'''

STATS_GD = '''extends Node

@export var move_speed := 200.0
const MAX_LEVEL = 99
var aether_energy := 50

func recalc_stats():
	var tmp_local = 1
	return tmp_local
'''

PLAYER_TSCN = '''[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://src/scripts/player.gd" id="1"]

[node name="Player" type="CharacterBody2D"]
script = ExtResource("1")

[node name="Hitbox" type="Area2D" parent="."]

[connection signal="died" from="." to="." method="_on_player_died"]
'''

PROJECT_GODOT = '''config_version=5

[application]

config/name="TestGame"

[autoload]

GameManager="*res://src/autoload/game_manager.gd"
'''


def _write(root, rel, content):
    p = os.path.join(root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


ORC_GD = '''extends Node

func kill_enemy(enemy):
\tenemy.queue_free()
'''


def _make_project():
    root = tempfile.mkdtemp()
    _write(root, "src/scripts/player.gd", PLAYER_GD)
    _write(root, "src/scripts/orc.gd", ORC_GD)
    _write(root, "src/scripts/stats.gd", STATS_GD)
    _write(root, "src/autoload/game_manager.gd", GM_GD)
    _write(root, "src/scenes/player.tscn", PLAYER_TSCN)
    _write(root, "project.godot", PROJECT_GODOT)
    _write(root, "docs/damage_notes.md", "notes about damage tuning\n")
    _write(root, "addons/some_addon/tool.gd", "func addon_secret_damage():\n\tpass\n")
    return root


def test_subtokens_find_snake_case():
    root = _make_project()
    ml_project_index.build_index(root)
    hits = ml_project_index.search(root, "damage")
    assert any(h["path"].endswith("player.gd") for h in hits), hits
    print("OK: подтокены snake_case (damage -> take_damage)")


def test_answer_layers_and_budget():
    root = _make_project()
    ans = librarian.answer(root, "player damage take_damage")
    assert ans.startswith("[Librarian]"), ans[:100]
    assert "res://src/scripts/player.gd" in ans, ans
    assert "take_damage" in ans, ans
    assert "player.tscn" in ans, ans  # сцена попала в карту
    assert "MAP" in ans and "STRUCTURE" in ans and "FRAGMENTS" in ans, ans
    assert "L" in ans  # номера строк в сигнатурах
    assert "addon_secret_damage" not in ans and "addons/" not in ans, ans
    assert len(ans) <= librarian.CHAR_BUDGET + 200, len(ans)
    print("OK: слои ответа, addons исключены, бюджет соблюдён")


def test_update_entries_micro_refresh():
    root = _make_project()
    ml_project_index.build_index(root)
    _write(root, "src/scripts/player.gd",
           PLAYER_GD + "\nfunc heal_wounds(x):\n\thealth += x\n")
    assert ml_project_index.update_entries(root, ["src/scripts/player.gd"]) is True
    hits = ml_project_index.search(root, "heal wounds")
    assert any(h["path"].endswith("player.gd") for h in hits), hits
    # удаление файла выкидывает запись из индекса
    os.remove(os.path.join(root, "src", "autoload", "game_manager.gd"))
    ml_project_index.update_entries(root, deleted_rels=["src/autoload/game_manager.gd"])
    hits2 = ml_project_index.search(root, "hurt player")
    assert not any(h["path"].endswith("game_manager.gd") for h in hits2), hits2
    print("OK: микро-обновление индекса (изменение + удаление)")


def test_note_files_changed_res_paths():
    root = _make_project()
    ml_project_index.build_index(root)
    _write(root, "src/scripts/enemy.gd", "func chase_target():\n\tpass\n")
    librarian.note_files_changed(root, ["res://src/scripts/enemy.gd"])
    hits = ml_project_index.search(root, "chase target")
    assert any(h["path"].endswith("enemy.gd") for h in hits), hits
    print("OK: note_files_changed принимает res:// пути")


def test_update_entries_without_index():
    root = _make_project()  # индекс НЕ строим
    assert ml_project_index.update_entries(root, ["src/scripts/player.gd"]) is False
    print("OK: микро-обновление без индекса — тихий no-op (построится лениво)")


def test_synonyms_expand_search():
    # Патч 1: в проекте нет слов monster/death, но есть kill_enemy/queue_free —
    # синонимы должны привести и карту, и фрагменты к orc.gd.
    root = _make_project()
    ans = librarian.answer(root, "monster death")
    assert "orc.gd" in ans, ans
    assert "synonyms also searched" in ans, ans
    assert "matched" in ans, ans  # фрагмент найден по синониму
    # прямые токены по-прежнему работают без изменений
    ans2 = librarian.answer(root, "take_damage")
    assert "player.gd" in ans2, ans2
    print("OK: синонимы (monster death -> kill_enemy via enemy/kill)")


def test_weighted_ranking():
    # Патч 2: скрипт с func take_damage должен стоять в карте ВЫШЕ, чем
    # damage_notes.md, у которого слово damage только в имени файла
    # (без переранжирования индекс ставил md выше за подстроку в пути).
    root = _make_project()
    ans = librarian.answer(root, "damage")
    i_gd = ans.find("src/scripts/player.gd")
    i_md = ans.find("damage_notes.md")
    assert i_gd != -1, ans
    assert i_md == -1 or i_gd < i_md, ans
    print("OK: взвешенный скоринг (func take_damage выше damage_notes.md)")


def test_typo_hint():
    # Патч 2: опечатка dammage — ничего не найдено, но в подсказке есть
    # реальный идентификатор damage из индекса (func take_damage).
    root = _make_project()
    ans = librarian.answer(root, "dammage")
    assert "nothing in the project index" in ans, ans
    assert "Similar identifiers" in ans, ans
    assert "damage" in ans.split("Similar identifiers", 1)[1], ans
    print("OK: подсказка при опечатке (dammage -> damage)")


def test_callers_layer():
    # Патч 3: запрос с точным именем функции даёт слой CALLERS с местами
    # вызова (game_manager.gd), но БЕЗ строки-определения из player.gd.
    root = _make_project()
    ans = librarian.answer(root, "take_damage")
    assert "CALLERS" in ans, ans
    sec = ans.split("CALLERS", 1)[1].split("Next:", 1)[0]
    assert "game_manager.gd" in sec, ans
    assert "func take_damage" not in sec, ans
    # запрос без точного имени функции слой не добавляет
    ans2 = librarian.answer(root, "scenes structure")
    assert "CALLERS" not in ans2, ans2
    print("OK: слой CALLERS (вызовы take_damage без определения)")


def test_autoloads_layer():
    # Патч 4: запрос, задевающий имя автозагрузки (или слово singleton),
    # показывает секцию [autoload] из project.godot; посторонний — нет.
    root = _make_project()
    ans = librarian.answer(root, "game manager singleton")
    assert "AUTOLOADS" in ans, ans
    assert "GameManager -> res://src/autoload/game_manager.gd" in ans, ans
    ans2 = librarian.answer(root, "player health")
    assert "AUTOLOADS" not in ans2, ans2
    print("OK: слой AUTOLOADS (из project.godot, только по делу)")


def test_signal_wiring_layer():
    # Патч 4: запрос с точным именем сигнала даёт слой SIGNALS:
    # связь из .tscn ([connection ... method="_on_player_died"]) + место эмита.
    root = _make_project()
    ans = librarian.answer(root, "died signal")
    assert "SIGNALS" in ans, ans
    sec = ans.split("SIGNALS", 1)[1].split("Next:", 1)[0]
    assert "_on_player_died" in sec, ans
    assert "died.emit()" in sec, ans
    # запрос без имени сигнала слой не добавляет
    ans2 = librarian.answer(root, "take_damage")
    assert "SIGNALS" not in ans2, ans2
    print("OK: слой SIGNALS (связи + эмиты сигнала died)")


def test_vars_and_consts_indexed():
    # v105.7 (багфикс): топ-уровневые var/const/@export должны быть в индексе
    # (раньше индексировались только class/func/signal), а локальные
    # переменные внутри функций — нет (шум).
    root = _make_project()
    ml_project_index.build_index(root)
    data = ml_project_index._read_index_raw(root)
    entry = {e["path"]: e for e in data["files"]}["src/scripts/stats.gd"]
    for sym in ("var:move_speed", "const:MAX_LEVEL", "var:aether_energy"):
        assert sym in entry["symbols"], entry
    assert "var:tmp_local" not in entry["symbols"], entry
    # поиск по имени переменной находит файл
    ans = librarian.answer(root, "move speed")
    assert "stats.gd" in ans, ans
    # опечатка в имени переменной теперь даёт подсказку (helth -> health,
    # где health — именно var из player.gd, не функция)
    ans2 = librarian.answer(root, "helth")
    assert "Similar identifiers" in ans2, ans2
    assert "health" in ans2.split("Similar identifiers", 1)[1], ans2
    # STRUCTURE показывает строку объявления с номером
    ans3 = librarian.answer(root, "health")
    assert "var health" in ans3, ans3
    print("OK: var/const в индексе (символы, поиск, typo-подсказка, STRUCTURE)")


def test_shared_brain_project_isolation():
    # Баг 1 (v105.8): при «мозге в папке плагина» (set_storage_base) индексы
    # всех проектов лежали в одном файле: проект B получал карту
    # проекта A, а update_entries смешивал записи двух проектов.
    from minilich import ml_data
    rootA = _make_project()
    rootB = _make_project()
    _write(rootA, "src/scripts/unique_alpha.gd", "func alpha_only_marker():\n\tpass\n")
    shared = tempfile.mkdtemp()
    ml_data.set_storage_base(shared)
    try:
        ml_project_index.build_index(rootA)
        # микро-обновление для B не должно писать в чужой индекс
        assert ml_project_index.update_entries(rootB, ["src/scripts/player.gd"]) is False
        raw = ml_project_index._read_index_raw(rootB)  # физически тот же файл
        assert raw["root"] == os.path.abspath(rootA), raw["root"]
        # поиск для B пересобирает индекс под B и не выдаёт файлы A
        res = ml_project_index.search(rootB, "alpha only marker")
        assert all("unique_alpha" not in str(r) for r in res), res
        raw2 = ml_project_index._read_index_raw(rootB)
        assert raw2["root"] == os.path.abspath(rootB), raw2["root"]
    finally:
        ml_data.set_storage_base(None)
    print("OK: общий «мозг» плагина не смешивает проекты (root сверяется)")


def test_bom_first_line_indexed():
    # Баг 3 (v105.8): BOM в начале файла ломал ^-регулярки первой строки —
    # терялся class_name. Теперь чтение utf-8-sig, как во всём проекте.
    root = _make_project()
    _write(root, "src/scripts/bom_boss.gd",
           "\ufeffclass_name BomBoss\nextends Node\n\nfunc roar():\n\tpass\n")
    ml_project_index.build_index(root)
    data = ml_project_index._read_index_raw(root)
    entry = {e["path"]: e for e in data["files"]}["src/scripts/bom_boss.gd"]
    assert "class:BomBoss" in entry["symbols"], entry
    print("OK: BOM не ломает индексацию первой строки")


def test_mixed_case_query_fragments():
    # Баг 4 (v105.8): FRAGMENTS был регистрозависим — «Take_Damage» не давал
    # ни одного фрагмента, хотя MAP регистронезависим. Теперь перед
    # синонимами пробуется tok.lower().
    root = _make_project()
    ans = librarian.answer(root, "Take_Damage")
    assert "FRAGMENTS" in ans, ans
    assert "take_damage" in ans, ans
    print("OK: запрос в смешанном регистре даёт FRAGMENTS")


def test_telemetry_log():
    # Патч 5: каждый ответ Библиотекаря пишет строку jsonl в хранилище
    # minilich: успешный запрос (result=ok, секции, hits) и пустой
    # (result=no_matches). Журнал не должен влиять на сам ответ.
    import json as _json
    from minilich import ml_data
    root = _make_project()
    ans = librarian.answer(root, "take_damage")
    assert "[Librarian]" in ans, ans
    librarian.answer(root, "zzzqqq_nonexistent")
    path = os.path.join(ml_data.storage_dir(root), "librarian_log.jsonl")
    assert os.path.isfile(path), path
    with open(path, encoding="utf-8") as f:
        recs = [_json.loads(line) for line in f if line.strip()]
    assert len(recs) == 2, recs
    assert recs[0]["query"] == "take_damage" and recs[0]["result"] == "ok", recs
    assert "MAP" in recs[0]["sections"] and recs[0]["hits"] >= 1, recs
    assert "ts" in recs[0] and isinstance(recs[0]["chars"], int), recs
    # Баг 1 (v105.8): при общем логе каждая запись помечена корнем проекта
    assert recs[0]["root"] == os.path.abspath(root), recs
    assert recs[1]["result"] == "no_matches", recs
    print("OK: телеметрия (2 записи jsonl, поля на месте)")


def test_synonym_dictionary_sanity():
    # Защита от хрупкости при расширении словаря: все слова английские,
    # нижний регистр, длина >= 3 (иначе их отбросит _query_subtokens и они
    # молча не будут работать), без пересечения со стоп-словами.
    import re as _re
    word_re = _re.compile(r"^[a-z][a-z0-9_]{2,}$")
    for g in librarian._SYNONYM_GROUPS:
        assert len(g) >= 2, g
        for w in g:
            assert word_re.match(w), "bad synonym: %r" % w
            assert w not in librarian._STOPWORDS, "stopword in synonyms: %r" % w
    assert len(librarian._SYN_LOOKUP) >= 300, len(librarian._SYN_LOOKUP)
    # расширение запроса ограничено потолком
    _q, extra = librarian._expanded_query("enemy attack damage save menu sound")
    assert len(extra) <= librarian._SYN_EXPAND_LIMIT, extra
    print("OK: словарь синонимов валиден (%d слов, %d групп)" % (
        len(librarian._SYN_LOOKUP), len(librarian._SYNONYM_GROUPS)))


def test_empty_and_missing():
    root = _make_project()
    ans = librarian.answer(root, "")
    assert "empty" in ans, ans
    ans2 = librarian.answer(root, "quaternion blockchain teleport")
    assert ans2.startswith("[Librarian]"), ans2
    print("OK: пустой запрос и запрос без совпадений не падают")


if __name__ == "__main__":
    test_subtokens_find_snake_case()
    test_answer_layers_and_budget()
    test_update_entries_micro_refresh()
    test_note_files_changed_res_paths()
    test_update_entries_without_index()
    test_synonyms_expand_search()
    test_weighted_ranking()
    test_typo_hint()
    test_callers_layer()
    test_autoloads_layer()
    test_signal_wiring_layer()
    test_vars_and_consts_indexed()
    test_shared_brain_project_isolation()
    test_bom_first_line_indexed()
    test_mixed_case_query_fragments()
    test_telemetry_log()
    test_synonym_dictionary_sanity()
    test_empty_and_missing()
    print("ВСЕ ТЕСТЫ ПРОШЛИ")
