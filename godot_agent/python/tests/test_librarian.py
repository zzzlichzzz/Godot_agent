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
from project_tools import search_project_text


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
    # синонимы должны привести ���� карту, �� фрагменты к orc.gd.
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
    # вызова (game_manager.gd), но БЕЗ ����троки-определения из player.gd.
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
    print("OK: var/const в индексе (символ��, поиск, typo-��одсказка, STRUCTURE)")


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


def test_signal_single_quotes():
    # Шаг 2 (v105.10): в GDScript строка может быть в одинарных кавычках —
    # шаблоны SIGNALS были жёстко зашиты на двойные, и секция не
    # появлялась вообще на валидном коде.
    root = _make_project()
    _write(root, "src/scripts/boss.gd",
           "extends Node\n"
           "\n"
           "signal enraged\n"
           "\n"
           "func _ready():\n"
           "\tconnect('enraged', Callable(self, '_on_enraged'))\n"
           "\n"
           "func rage():\n"
           "\temit_signal('enraged')\n"
           "\n"
           "func _on_enraged():\n"
           "\tpass\n")
    ans = librarian.answer(root, "signal enraged")
    assert "SIGNALS" in ans, ans
    sig = ans.split("SIGNALS", 1)[1].split("Next:", 1)[0]
    assert "emit_signal('enraged')" in sig, sig     # эмит в одинарных
    assert "connect('enraged'" in sig, sig          # подключение в одинарных
    print("OK: SIGNALS видит одинарные кавычки (emit_signal/connect)")


def test_signal_await_disconnect_and_spaced():
    # Раунд 3, п.3: SIGNALS был слеп к трём повседневным формам Godot 4,
    # а disconnect("sig" показывался как (connect) — совпадение по подстроке.
    root = _make_project()
    _write(root, "src/mob.gd", "extends Node\nsignal died\n")
    _write(root, "src/watch.gd",
           "extends Node\n"
           "func _ready():\n"
           "\t$P.died .connect(_a)\n"
           "\tawait $P.died\n"
           "\tif $P.is_connected(\"died\", _a):\n"
           "\t\t$P.disconnect(\"died\", _a)\n"
           "\tvar died_count = 0\n")
    ans = librarian.answer(root, "died")
    assert "SIGNALS" in ans, ans
    sig = ans.split("SIGNALS", 1)[1]
    for key in ("GODOT API", "Next:"):
        sig = sig.split(key, 1)[0]

    assert "died .connect(_a)" in sig, sig          # запись с пробелом
    assert "(await)" in sig, sig                    # await $P.died
    assert "(is_connected)" in sig, sig
    assert "(disconnect)" in sig, sig

    # отписка и проверка НЕ должны выдаваться за подписку
    for line in sig.splitlines():
        if "disconnect(" in line or "is_connected(" in line:
            assert "(connect)" not in line, line
    # died_count — другое имя, не сигнал
    assert "died_count" not in sig, sig
    print("OK: SIGNALS видит await/is_connected/disconnect и не путает метки")


def test_callers_reject_mentions():
    # Раунд 3, п.1: регрессия шага 6. Шаблоны "имя"/'имя' выдавали
    # за места вызова любое упоминание имени в тексте.
    root = _make_project()
    _write(root, "src/noise.gd",
           "extends Node\n"
           "# TODO: rewrite \"take_damage\" someday\n"
           "var log_label = \"take_damage\"\n"
           "\n"
           "func go(p):\n"
           "\tif p.has_method(\"take_damage\"):\n"
           "\t\tprint(\"take_damage\")\n"
           "\tp.callv(\"take_damage\", [2])\n"
           "\tp.take_damage(1)\n")
    ans = librarian.answer(root, "take_damage")
    cal = ans.split("CALLERS", 1)[1] if "CALLERS" in ans else ""
    for key in ("SIGNALS", "GODOT API", "Next:"):
        cal = cal.split(key, 1)[0]
    sites = [l.strip() for l in cal.splitlines() if l.strip().startswith("- ")]
    assert sites, ans

    # НАСТОЯЩИЕ вызовы остаются
    assert any("p.take_damage(1)" in s for s in sites), sites
    assert any('callv("take_damage"' in s for s in sites), sites

    # УПОМИНАНИЯ не должны считаться вызовами
    for bad in ("TODO", "log_label", "has_method", 'print("take_damage")'):
        assert not any(bad in s for s in sites), (bad, sites)

    # вывод отсортирован по файлу и номеру строки
    keys = []
    for s in sites:
        path = s.split(" line ", 1)[0]
        keys.append((path, int(s.split(" line ", 1)[1].split(":", 1)[0])))
    assert keys == sorted(keys), keys
    print("OK: CALLERS отсеивает упоминания и сортирует вывод")


def test_fragments_case_insensitive_both_ways():
    # Шаг 7 (v105.10): фолбэк v105.8 работал только вниз по регистру
    # (Take_Damage -> take_damage). Обратное направление не работало:
    # запрос «health» не находил код с «Health».
    root = _make_project()
    _write(root, "src/health_bar.gd",
           "extends Control\n"
           "\n"
           "var CurrentHealth = 100\n"
           "\n"
           "func RefillHealth():\n"
           "\tCurrentHealth = 100\n")
    # запрос в нижнем регистре -> код в CamelCase
    ans = librarian.answer(root, "refillhealth")
    assert "FRAGMENTS" in ans, ans
    assert "RefillHealth" in ans, ans
    # и обратно: запрос в верхнем регистре -> код в нижнем (регресс v105.8)
    ans2 = librarian.answer(root, "TAKE_DAMAGE")
    assert "take_damage" in ans2, ans2
    print("OK: FRAGMENTS регистронезависим в обе стороны")


def test_callers_indirect_and_spaced():
    # Шаг 6 (v105.10): CALLERS искал только «имя(» вплотную и пропускал
    # пробел перед скобкой и косвенные вызовы по имени-строке.
    root = _make_project()
    _write(root, "src/spawner.gd",
           "extends Node\n"
           "\n"
           "func hit_all(p):\n"
           "\tp.take_damage (7)\n"                      # пробел перед скобкой
           "\tp.callv(\"take_damage\", [3])\n"           # косвенный, двойные
           "\tp.call_deferred('take_damage', 1)\n")     # косвенный, одинарные
    ans = librarian.answer(root, "take_damage")
    assert "CALLERS" in ans, ans
    cal = ans.split("CALLERS", 1)[1].split("SIGNALS", 1)[0].split("Next:", 1)[0]
    assert "take_damage (7)" in cal, cal
    assert 'callv("take_damage"' in cal, cal
    assert "call_deferred('take_damage'" in cal, cal
    # строка-определение по-прежнему не считается вызовом
    assert "func take_damage(" not in cal, cal
    # и нет дублей: каждая строка встречается один раз
    sites = [l for l in cal.splitlines() if l.strip().startswith("- ")]
    assert len(sites) == len(set(sites)), sites
    print("OK: CALLERS видит пробел перед скобкой и косвенные вызовы")


def test_answer_never_raises_on_bad_budget():
    # Шаг 5 (v105.10): докстринг answer() обещает не бросать наружу, но
    # int(budget_chars) падал на None (TypeError) и строке (ValueError).
    # Критично, что падение было ПОСЛЕ сборки всех слоёв — то есть
    # только на ЗАПРОСАХ С СОВПАДЕНИЯМИ (без них есть ранний выход).
    root = _make_project()
    for bad in (None, "много", "", [], 0, -50):
        ans = librarian.answer(root, "take_damage", budget_chars=bad)
        assert isinstance(ans, str) and ans, repr(bad)
        assert "take_damage" in ans, (bad, ans)
    # валидный бюджет по-прежнему ограничивает размер
    big = librarian.answer(root, "take_damage", budget_chars=8000)
    small = librarian.answer(root, "take_damage", budget_chars=1200)
    assert len(small) <= len(big), (len(small), len(big))
    print("OK: answer() не падает на невалидном budget_chars")


def test_ghost_files_from_stale_index():
    # Шаг 4 (v105.10): файл удалён СНАРУЖИ (Git/Проводник), агент об этом
    # не знает и note_files_changed никто не вызвал. До STALE_SEC призрак
    # висел в MAP, а STRUCTURE писал «(read error: Файл не найден)».
    root = _make_project()
    _write(root, "src/ghost_weapon.gd",
           "extends Node\n\nfunc ghost_reload():\n\tpass\n")
    ans_before = librarian.answer(root, "ghost_reload")
    assert "ghost_weapon.gd" in ans_before, ans_before

    # удаляем мимо агента: индекс остаётся со старой записью
    os.remove(os.path.join(root, "src", "ghost_weapon.gd"))

    ans = librarian.answer(root, "ghost_reload")
    assert "ghost_weapon.gd" not in ans, ans
    assert "read error" not in ans, ans

    # индекс должен быть починен на месте, а не только отфильтрован в выдаче
    idx = ml_project_index._load_index(root) or {}
    paths = [e.get("path") for e in (idx.get("files") or [])]
    assert "src/ghost_weapon.gd" not in paths, paths

    # живые файлы не пострадали
    ans2 = librarian.answer(root, "take_damage")
    assert "take_damage" in ans2, ans2
    print("OK: призрачные файлы отсеиваются и чистятся из индекса")


def test_non_ascii_identifiers():
    # Шаг 3 (v105.10): GDScript разрешает юникод в именах. Раньше
    # файл с русскими идентификаторами попадал в MAP, но без символов:
    # STRUCTURE показывал только extends, FRAGMENTS молчал.
    root = _make_project()
    _write(root, "src/здоровье.gd",
           "extends Node\n"
           "\n"
           "signal умер\n"
           "const МАКС_ЗДОРОВЬЕ = 100\n"
           "var текущее = 100\n"
           "\n"
           "func лечить(сколько):\n"
           "\tтекущее += сколько\n")
    # символы должны попасть в индекс
    ml_project_index.build_index(root)
    idx = ml_project_index._load_index(root) or {}
    syms = []
    for e in (idx.get("files") or []):
        if str(e.get("path", "")).endswith("здоровье.gd"):
            syms = e.get("symbols") or []
    assert "func:лечить" in syms, syms
    assert "signal:умер" in syms, syms
    assert "var:текущее" in syms, syms
    assert "const:МАКС_ЗДОРОВЬЕ" in syms, syms
    # и в ответ: STRUCTURE с объявлением func, FRAGMENTS с телом
    ans = librarian.answer(root, "лечить")
    assert "здоровье.gd" in ans, ans
    assert "func лечить" in ans, ans
    # латиница не сломана тем же запросом по старому коду
    ans2 = librarian.answer(root, "take_damage")
    assert "take_damage" in ans2, ans2
    print("OK: юникодные идентификаторы в индексе, STRUCTURE и FRAGMENTS")


def test_addons_do_not_eat_search_quota():
    # Шаг 1 (v105.10): файлы addons/ раньше отсеивались ПОСЛЕ поиска,
    # а os.walk идёт по алфавиту — addons/ почти всегда первая и выбирала
    # всю квоту max_results (3 для FRAGMENTS). На любом проекте с
    # установленным аддоном слой дословных фрагментов молча пропадал.
    root = _make_project()
    for i in range(5):
        _write(root, "addons/a_plugin/f%d.gd" % i,
               "extends Node\n\nfunc _ready():\n\ttake_damage(1)\n")
    ans = librarian.answer(root, "take_damage")
    assert "FRAGMENTS" in ans, ans          # слой не исчез из-за аддонов
    assert "take_damage" in ans, ans
    assert "addons/" not in ans, ans        # и сами аддоны не показываются
    # сам поиск: с фильтром квоту за��имают только файлы проекта
    res, _tr = search_project_text(root, "take_damage", max_results=3,
                                   context_lines=0, exclude_rel_prefixes=("addons/",))
    assert res and all("addons/" not in r["path"] for r in res), res
    # без фильтра поведение прежнее (остальные вызывающие не затронуты)
    res_all, _tr2 = search_project_text(root, "take_damage", max_results=3, context_lines=0)
    assert any("addons/" in r["path"] for r in res_all), res_all
    print("OK: addons/ не съедают квоту поиска (FRAGMENTS жив)")


def test_signal_connect_sites():
    # Пункт 3 (v105.9): слой SIGNALS видит подключения в коде, а не только
    # [connection ...] в .tscn: стиль Godot 4 «died.connect(_on_died)» и
    # legacy «connect("died", ...)». Шаблоны привязаны к имени сигнала —
    # чужие connect (например, timeout таймера) не цепляются.
    root = _make_project()
    _write(root, "src/scripts/game_manager.gd",
           'extends Node\n'
           '\n'
           'func _ready():\n'
           '\tvar player = $Player\n'
           '\tplayer.died.connect(_on_player_died)\n'
           '\tplayer.connect("died", Callable(self, "_legacy_handler"))\n'
           '\tget_tree().create_timer(1.0).timeout.connect(_tick)\n'
           '\n'
           'func _on_player_died():\n'
           '\tpass\n'
           '\n'
           'func _tick():\n'
           '\tpass\n')
    ans = librarian.answer(root, "where is signal died connected")
    assert "died.connect(" in ans, ans          # стиль Godot 4
    assert 'connect("died"' in ans, ans         # legacy-стиль
    assert "(connect)" in ans, ans              # метка источника
    # чужой connect (timeout таймера) не попал в СЕКЦИЮ SIGNALS;
    # в FRAGMENTS он может мелькнуть строкой контекста — это нормально
    sig_sec = ans.split("SIGNALS", 1)[1].split("Next:", 1)[0]
    assert "timeout.connect" not in sig_sec, sig_sec
    print("OK: SIGNALS видит connect-подключения в коде (Godot 4 + legacy)")


def test_symbol_prefixes_not_search_tokens():
    # Пункт 2 (v105.9): служебные префиксы символов (class:/func:/var:/...)
    # были токенами поиска индекса — запрос со словом «class» совпадал с
    # каждым .gd, где есть class_name, и MAP набирал шумный хвост.
    root = _make_project()
    ml_project_index.build_index(root)
    for kw in ("class", "func", "var", "signal", "const"):
        hits = ml_project_index.search(root, kw)
        assert not hits, (kw, [h["path"] for h in hits])
    # имена самих символов ищутся как раньше
    hits = ml_project_index.search(root, "take damage")
    assert any(h["path"].endswith("player.gd") for h in hits), hits
    # имена узлов сцены (до двоеточия в «Имя:Тип») не пострадали
    hits2 = ml_project_index.search(root, "hitbox")
    assert any(h["path"].endswith(".tscn") for h in hits2), hits2
    print("OK: префиксы символов не являются токенами поиска")


def test_gdscript_keywords_not_grepped():
    # Пункт 1 (v105.9): ключевые слова объявлений GDScript (class_name/extends/
    # const/static/onready/export) — стоп-слова: дословный grep по ним съедал
    # слоты FRAGMENTS мусором (совпадает почти каждый .gd проекта),
    # вытесняя содержательные токены запроса.
    root = _make_project()
    ans = librarian.answer(root, "class_name Player")
    assert "matched \u00abclass_name\u00bb" not in ans, ans
    assert "matched \u00abPlayer\u00bb" in ans, ans  # содержательный токен работает
    # то же для остальных ключевых слов: ни одно не должно стать токеном
    for kw in ("extends", "const", "static", "onready", "export"):
        assert not librarian._query_tokens(kw + " health")[0].lower() == kw, kw
    # запрос из ОДНИХ ключевых слов не падает и честно говорит «ничего нет»
    ans2 = librarian.answer(root, "extends class_name")
    assert ans2.startswith("[Librarian]"), ans2
    print("OK: ключевые слова GDScript не съедают слоты FRAGMENTS")


def test_fragments_case_insensitive_without_fallback():
    # Раунд 3, п.2: фолбэк шага 7 запускался только при added == 0.
    # Здесь точное совпадение ЕСТЬ — значит, раньше вариант в другом
    # регистре из ДРУГОГО файла не искался вообще.
    root = _make_project()
    _write(root, "src/a_exact.gd", "extends Node\nvar health = 100\n")
    _write(root, "src/b_upper.gd", "extends Node\nfunc HealthUp():\n\tpass\n")
    ans = librarian.answer(root, "health")
    frag = ans.split("FRAGMENTS", 1)[1] if "FRAGMENTS" in ans else ""
    for key in ("CALLERS", "SIGNALS", "GODOT API", "Next:"):
        frag = frag.split(key, 1)[0]
    assert "var health" in frag, frag           # точное совпадение
    assert "HealthUp" in frag, frag             # и другой регистр тоже
    assert "b_upper.gd" in frag, frag           # именно как отдельная находка,
                                                # а не случайная строка контекста
    print("OK: FRAGMENTS ищет регистронезависимо первым проходом")


def test_structure_nested_class():
    # Раунд 3, п.4: строка «class InnerState:» не выводилась, отступ терялся,
    # поле вложенного класса пропадало — метод выглядел как топ-уровневый.
    root = _make_project()
    _write(root, "src/state.gd",
           "extends Node\n"
           "class InnerState:\n"
           "\tvar inner_var = 1\n"
           "\tfunc enter_state():\n"
           "\t\tvar local_noise = 2\n"
           "\t\treturn local_noise\n"
           "func outer_fn():\n"
           "\tvar another_local = 3\n"
           "\treturn another_local\n")
    ans = librarian.answer(root, "state.gd enter_state")
    st = ans.split("STRUCTURE", 1)[1] if "STRUCTURE" in ans else ""
    for key in ("FRAGMENTS", "CALLERS", "SIGNALS", "GODOT API", "Next:"):
        st = st.split(key, 1)[0]
    assert "state.gd" in st, ans

    assert "class InnerState:" in st, st        # сам вложенный класс
    assert "inner_var" in st, st                # и его поле
    assert "outer_fn" in st, st

    # отступ сохранён: enter_state глубже, чем outer_fn
    def indent_of(needle):
        for ln in st.splitlines():
            if needle in ln:
                body = ln.split(": ", 1)[1]
                return len(body) - len(body.lstrip())
        return None
    assert indent_of("func enter_state") > indent_of("func outer_fn"), st

    # локальные переменные из тел функций НЕ должны шуметь в STRUCTURE
    assert "local_noise" not in st, st
    assert "another_local" not in st, st
    print("OK: STRUCTURE показывает вложенные классы с отступами")


def test_budget_truncation_is_honest():
    # Шаг 8 (v105.10): три дефекта обрезки по бюджету — висячий заголовок
    # секции, неучтённая длина самой пометки, игнор бюджета < 1000.
    root = _make_project()
    for i in range(6):
        _write(root, "src/mob_%d.gd" % i,
               "extends Node\n\nfunc take_damage(x):\n\tprint(\"mob %d hurt\")\n" % i)

    # бюджеты ниже 1000 больше не схлопываются в одно значение
    small = librarian.answer(root, "take_damage", budget_chars=500)
    mid = librarian.answer(root, "take_damage", budget_chars=1000)
    assert len(small) < len(mid), (len(small), len(mid))

    # ответ укладывается в запрошенный размер ВМЕСТЕ с пометкой об обрезке
    for b in (500, 800, 1500, 3000):
        ans = librarian.answer(root, "take_damage", budget_chars=b)
        assert len(ans) <= b, (b, len(ans))
        # ни одного висячего заголовка секции без содержимого.
        # Содержимое бываёт трёх видов: «- res://...» (MAP), «  L3: ...»
        # (тело слоя) и «res://file.gd:» (подзаголовок файла в STRUCTURE/
        # FRAGMENTS). Заголовок считается висячим, если сразу за ним конец
        # ответа, другая секция, пометка об обрезке или FOOTER.
        lines = ans.splitlines()
        for i, ln in enumerate(lines):
            if not librarian._is_section_header(ln):
                continue
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            dangling = (not nxt.strip()
                        or librarian._is_section_header(nxt)
                        or nxt.startswith("… (truncated")
                        or nxt.startswith("Next:"))
            assert not dangling, \
                "висячий заголовок %r при budget=%d" % (ln, b)
    print("OK: обрезка по бюджету честная (без висячих заголовков, в пределах раз��ера)")


def test_huge_file_and_non_string_query():
    # Шаг 9 (v105.10): а) STRUCTURE читает файл лишь до 200000 символов
    # и раньше молчалоб этом; б) нестроковый query шёл в поиск как repr.
    root = _make_project()

    # а) файл гарантированно длиннее 200000 символов: объявление в самом
    # начале (чтобы файл попал в STRUCTURE), дальше балласт из комментариев,
    # и в самом хвосте — ещё одно объявление, которое читатель не увидит.
    ballast = "# %s\n" % ("x" * 90)
    _write(root, "src/huge_boss.gd",
           "extends Node\n\nfunc take_damage(x):\n\tpass\n"
           + ballast * 2400
           + "\nfunc tail_marker_func():\n\tpass\n")
    ans = librarian.answer(root, "take_damage", budget_chars=20000)
    assert "file too large" in ans, ans
    # честность пометки: хвостовое объявление действительно не попало в ответ
    assert "tail_marker_func" not in ans, "хвост всё же прочитан — фикстура мала"

    # б) нестроковые аргументы — честный отказ, а не поиск по repr.
    # v105.11 (раунд 3, п.6): раньше здесь ожидалось empty "query" —
    # этот ассерт закреплял неточное сообщение (запрос не пустой,
    # а неверного типа). Само свойство проверяется по-прежнему:
    # repr аргумента не утекает в поиск и в ответ.
    for bad in (["died"], {"q": "died"}, 42, object()):
        r = librarian.answer(root, bad)
        assert "must be a string" in r, (bad, r[:120])
        assert "[" not in r.split("Resend")[0].replace("[Librarian]", ""), (bad, r[:120])
    print("OK: огромный файл помечен как усечённый, нестроковый query отвергнут")


def test_degenerate_budget_and_query_type():
    # Раунд 3, п.5 и п.6: вырожденный бюджет логировался как result:"ok",
    # а нестроковый query получал сообщение про ПУСТОЙ запрос.
    import json
    from minilich import ml_data
    root = _make_project()

    # п.6: тип важнее пустоты
    for bad in (123, ["died"], {"q": "died"}, None):
        msg = librarian.answer(root, bad)
        assert "must be a string" in msg, (bad, msg)
        assert "empty" not in msg, (bad, msg)
    assert "int" in librarian.answer(root, 123)          # тип назван явно
    # пустая СТРОКА по-прежнему даёт своё, другое сообщение
    empty_msg = librarian.answer(root, "   ")
    assert 'empty "query"' in empty_msg, empty_msg
    assert "must be a string" not in empty_msg, empty_msg

    # п.5: вырожденный бюджет — ответ без данных не должен выглядеть успешным
    log_path = os.path.join(ml_data.storage_dir(root), "librarian_log.jsonl")
    if os.path.exists(log_path):
        os.remove(log_path)
    ans = librarian.answer(root, "player", budget_chars=50)
    assert "budget_chars too small" in ans, ans
    assert "truncated" not in ans, ans      # не врём, будто что-то показано
    recs = [json.loads(l) for l in open(log_path, encoding="utf-8") if l.strip()]
    assert recs and recs[-1]["result"] == "empty_budget", recs[-1]

    # нормальный бюджет по-прежнему логируется как ok
    librarian.answer(root, "player")
    recs = [json.loads(l) for l in open(log_path, encoding="utf-8") if l.strip()]
    assert recs[-1]["result"] == "ok", recs[-1]
    print("OK: вырожденный бюджет логируется честно, тип query назван точно")


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
    # р��сширение запроса ограничено потолком
    _q, extra = librarian._expanded_query("enemy attack damage save menu sound")
    assert len(extra) <= librarian._SYN_EXPAND_LIMIT, extra
    print("OK: словарь синонимов валиден (%d слов, %d групп)" % (
        len(librarian._SYN_LOOKUP), len(librarian._SYNONYM_GROUPS)))


NESTED_FSM_GD = '''extends Node

class Inner:
\tvar field_a := 1
\tconst INNER_MAX = 9

\tfunc inner_method():
\t\tvar local_noise = 5
\t\treturn local_noise + field_a

func top():
\tvar another_local = 1
\treturn another_local
'''


def test_index_nested_class_members():
    """Раунд 4, п.3: регулярки индекса — ^-якорные, и у файла с FSM-паттерном
    символы были только ['func:top'] — файл не попадал в MAP вообще."""
    root = tempfile.mkdtemp()
    _write(root, "src/fsm.gd", NESTED_FSM_GD)
    _write(root, "project.godot", 'config_version=5\n')
    ml_project_index.build_index(root)
    hits = ml_project_index.search(root, "field_a Inner")
    assert hits, "файл с вложенным классом не нашёлся в индексе"
    syms = None
    for h in hits:
        if str(h.get("path", "")).endswith("fsm.gd"):
            syms = list(h.get("symbols") or [])
    assert syms is not None, hits
    assert "class:Inner" in syms, syms
    assert "var:field_a" in syms, syms
    assert "const:INNER_MAX" in syms, syms
    assert "func:inner_method" in syms, syms
    assert "func:top" in syms, syms
    # НЕГАТИВНЫЕ: локальные var внутри тел функций — шум, их брать НЕЛЬЗЯ.
    assert "var:local_noise" not in syms, syms
    assert "var:another_local" not in syms, syms
    # И ответ теперь содержит карту, а не одни FRAGMENTS.
    ans = librarian.answer(root, "field_a Inner")
    assert "MAP" in ans, ans
    print("OK: индекс видит членов вложенных классов (%s)" % syms)


def test_index_plain_script_unchanged():
    """Оборотная сторона п.3: у обычного скрипта без вложенных классов
    набор символов не должен поменяться — шум не просочился."""
    root = tempfile.mkdtemp()
    _write(root, "src/stats.gd",
           "extends Node\n\nvar move_speed := 200\nconst MAX_LEVEL = 50\n\n"
           "func recalc_stats():\n\tvar tmp_local = 1\n\treturn tmp_local\n")
    _write(root, "project.godot", 'config_version=5\n')
    ml_project_index.build_index(root)
    hits = ml_project_index.search(root, "move_speed")
    syms = []
    for h in hits:
        if str(h.get("path", "")).endswith("stats.gd"):
            syms = list(h.get("symbols") or [])
    assert "var:move_speed" in syms, syms
    assert "const:MAX_LEVEL" in syms, syms
    assert "func:recalc_stats" in syms, syms
    # НЕГАТИВНЫЙ: локальная переменная как была шумом, так и осталась.
    assert "var:tmp_local" not in syms, syms
    print("OK: обычный скрипт индексируется без изменений (%s)" % syms)


def test_callers_bind_and_call_forms():
    """Раунд 4, п.4: p.take_damage.bind(4) — повседневная связка Godot 4
    (tween_callback, connect с аргументами). «.bind(» был в _INDIRECT_CALL_CTX,
    но ни один шаблон не совпадал с «имя.bind(» — секции CALLERS не было."""
    root = tempfile.mkdtemp()
    _write(root, "src/player.gd", "extends Node\n\nfunc take_damage(a):\n\tpass\n")
    _write(root, "src/boss.gd",
           "extends Node\n\nfunc _ready():\n\tvar p = $Player\n"
           "\tvar t = create_tween()\n\tt.tween_callback(p.take_damage.bind(4))\n"
           "\tp.take_damage.call_deferred(2)\n")
    _write(root, "src/ui.gd",
           "extends Node\n\nfunc _ready():\n\t# take_damage is called elsewhere\n"
           "\tvar label = \"take_damage\"\n\tprint(label)\n")
    _write(root, "project.godot", 'config_version=5\n')
    ml_project_index.build_index(root)
    ans = librarian.answer(root, "take_damage")
    assert "CALLERS" in ans, ans
    callers = ans.split("CALLERS", 1)[1].split("\n\n")[0]
    assert "p.take_damage.bind(4)" in callers, callers
    assert "call_deferred" in callers, callers
    # НЕГАТИВНЫЕ: комментарий, подпись-строка и само определение — не вызовы.
    assert "is called elsewhere" not in callers, callers
    assert "var label" not in callers, callers
    assert "func take_damage(a)" not in callers, callers
    print("OK: CALLERS видит .bind( и .call, упоминания отсеяны")


def test_signals_sorted_by_path_and_line():
    """Раунд 4, п.5: SIGNALS выводился в порядке перебора шаблонов
    (a_ui:4, z_hud:4, player:6, a_ui:6) — выглядело как сбой."""
    root = tempfile.mkdtemp()
    _write(root, "src/player.gd", "extends Node\n\nsignal died\n\nfunc f():\n\tdied.emit()\n")
    _write(root, "src/a_ui.gd",
           "extends Node\n\nfunc _ready():\n\t$P.died.connect(_x)\n\tpass\n"
           "\tawait $P.died\n\t$P.died.disconnect(_x)\n")
    _write(root, "src/z_hud.gd", "extends Node\n\nfunc _ready():\n\t$P.died.connect(_y)\n")
    _write(root, "project.godot", 'config_version=5\n')
    ml_project_index.build_index(root)
    ans = librarian.answer(root, "died")
    assert "SIGNALS" in ans, ans
    rows = [ln for ln in ans.split("SIGNALS", 1)[1].splitlines() if ln.startswith("- res://")]
    assert len(rows) >= 4, rows
    keys = []
    for ln in rows:
        head = ln[2:].split(" (", 1)[0]
        path, _sep, num = head.partition(" line ")
        keys.append((path, int(num)))
    # ГЛАВНОЕ: порядок строго по (path, line).
    assert keys == sorted(keys), keys
    # НЕГАТИВНЫЙ: метки не потерялись при переходе на сортировку.
    assert "(emit)" in ans and "(connect)" in ans and "(disconnect)" in ans, ans
    print("OK: SIGNALS отсортирован по (path, line): %s" % keys)


def test_fragments_code_beats_docs():
    """Раунд 4, п.1: квоту FRAGMENTS выбирал первый по алфавиту файл (docs/),
    и кода в секции не оставалось вовсе."""
    root = tempfile.mkdtemp()
    _write(root, "src/player.gd",
           "extends Node\n\nvar health := 100\n\nfunc hit():\n\thealth -= 1\n")
    _write(root, "docs/notes.md", "".join("health note %d\n\n" % i for i in range(1, 6)))
    _write(root, "docs/aaa_more.md", "".join("health idea %d\n\n" % i for i in range(1, 6)))
    _write(root, "project.godot", 'config_version=5\n')
    ml_project_index.build_index(root)
    ans = librarian.answer(root, "health")
    frag = ans.split("FRAGMENTS", 1)[1] if "FRAGMENTS" in ans else ""
    heads = [ln for ln in frag.splitlines() if ln.startswith("res://")]
    assert heads, ans
    # ГЛАВНОЕ НЕГАТИВНОЕ: секция не может состоять из одной документации.
    assert not all(".md" in h for h in heads), heads
    assert heads[0].startswith("res://src/player.gd"), heads
    per_file = {}
    for h in heads:
        p = h.split(" line ", 1)[0]
        per_file[p] = per_file.get(p, 0) + 1
    assert max(per_file.values()) <= librarian.FRAG_PER_FILE, per_file
    print("OK: FRAGMENTS — код не вытесняется документацией (%s)" % per_file)


def test_fragments_single_file_not_starved():
    """Оборотная сторона п.1: если совпадения есть ТОЛЬКО в одном файле,
    лимит на файл НЕ должен урезать выдачу — иначе одна потеря данных
    меняется на другую."""
    root = tempfile.mkdtemp()
    # Совпадения разнесены пустыми строками: _grep_token ходит с
    # context_lines=1, а с раунда 4 (п.2) совпадения в окне ±context_lines
    # склеиваются. Этот тест про ДРУГОЕ — про лимит на файл.
    _write(root, "src/only.gd", "extends Node\n" + "".join(
        "\n\nvar aether_field_%d := %d\n" % (i, i) for i in range(1, 7)))
    _write(root, "project.godot", 'config_version=5\n')
    ml_project_index.build_index(root)
    ans = librarian.answer(root, "aether_field_1 aether")
    frag = ans.split("FRAGMENTS", 1)[1] if "FRAGMENTS" in ans else ""
    heads = [ln for ln in frag.splitlines() if ln.startswith("res://")]
    assert len(heads) > librarian.FRAG_PER_FILE, heads
    print("OK: единственный файл не урезан лимитом (%d сниппетов)" % len(heads))


def test_fragments_merge_adjacent_snippets():
    """Раунд 4, п.2: var health / var health_max / var health_bar подряд давали
    три почти одинаковых сниппета. Теперь — один, без потери строк."""
    root = tempfile.mkdtemp()
    _write(root, "src/hud.gd",
           "extends Node\n\nvar health := 100\nvar health_max := 100\nvar health_bar\n")
    _write(root, "project.godot", 'config_version=5\n')
    ml_project_index.build_index(root)
    ans = librarian.answer(root, "health")
    frag = ans.split("FRAGMENTS", 1)[1] if "FRAGMENTS" in ans else ""
    heads = [ln for ln in frag.splitlines() if ln.startswith("res://")]
    hud_heads = [h for h in heads if "hud.gd" in h]
    # ГЛАВНОЕ: три соседних совпадения — один сниппет, а не три.
    assert len(hud_heads) == 1, heads
    # НЕГАТИВНЫЙ к самому себе: склейка не должна СЪЕСТЬ строки.
    assert "var health := 100" in frag, frag
    assert "var health_max := 100" in frag, frag
    assert "var health_bar" in frag, frag
    print("OK: соседние совпадения склеены в 1 сниппет (было 3), строки целы")


def test_callers_not_merged_context_zero():
    """Оборотная сторона п.2: CALLERS/SIGNALS ходят с context_lines=0 и ждут
    ОТДЕЛЬНУЮ строку на каждый вызов — склейка тут срабатывать не должна."""
    root = tempfile.mkdtemp()
    _write(root, "src/player.gd", "extends Node\n\nfunc take_damage(a):\n\tpass\n")
    _write(root, "src/boss.gd",
           "extends Node\n\nfunc _ready():\n\tvar p = $Player\n"
           "\tp.take_damage(1)\n\tp.take_damage(2)\n")
    _write(root, "project.godot", 'config_version=5\n')
    ml_project_index.build_index(root)
    ans = librarian.answer(root, "take_damage")
    callers = ans.split("CALLERS", 1)[1].split("\n\n")[0] if "CALLERS" in ans else ""
    rows = [ln for ln in callers.splitlines() if ln.startswith("- res://")]
    assert len(rows) >= 2, rows
    assert any("line 5" in r for r in rows), rows
    assert any("line 6" in r for r in rows), rows
    print("OK: при context_lines=0 склейки нет, каждый вызов отдельной строкой")


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
    test_gdscript_keywords_not_grepped()
    test_symbol_prefixes_not_search_tokens()
    test_signal_connect_sites()
    test_addons_do_not_eat_search_quota()
    test_signal_single_quotes()
    test_non_ascii_identifiers()
    test_ghost_files_from_stale_index()
    test_answer_never_raises_on_bad_budget()
    test_callers_indirect_and_spaced()
    test_callers_reject_mentions()
    test_signal_await_disconnect_and_spaced()
    test_fragments_case_insensitive_both_ways()
    test_fragments_case_insensitive_without_fallback()
    test_structure_nested_class()
    test_budget_truncation_is_honest()
    test_huge_file_and_non_string_query()
    test_degenerate_budget_and_query_type()
    test_telemetry_log()
    test_synonym_dictionary_sanity()
    test_index_nested_class_members()
    test_index_plain_script_unchanged()
    test_callers_bind_and_call_forms()
    test_signals_sorted_by_path_and_line()
    test_fragments_code_beats_docs()
    test_fragments_single_file_not_starved()
    test_fragments_merge_adjacent_snippets()
    test_callers_not_merged_context_zero()
    test_empty_and_missing()
    print("ВСЕ ТЕСТЫ ПРОШЛИ")
