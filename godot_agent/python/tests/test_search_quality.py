# -*- coding: utf-8 -*-
"""L2: харнесс качества поиска Библиотекаря (recall@8 / MRR@8).

Зачем. Правки L3-L6 (IDF/BM25, структурный тай-брейк, лимит символов, добор
MAP) обязаны **улучшать** поиск, а не «казаться лучше». Харнесс — это
измерительный прибор: golden-set из 150 пар «запрос -> ожидаемые файлы»,
набранный по реальному проекту-полигону, и две метрики на срез top-8.

Два среза, оба с `k = 8` (= `librarian.MAP_LIMIT`):

* `index` — `ml_project_index.search(root, query, limit=8)`. Чистое
  ранжирование индекса: здесь живут L3 (IDF), L4 (тай-брейк), P3
  (MAX_SYMBOLS).
* `map` — порядок файлов в слое MAP Библиотекаря ровно как в
  `librarian.answer()`: `_expanded_query` -> `search(limit=MAP_LIMIT*3)` ->
  фильтр `can_read_project_path` -> `_rerank_hits(...)[:8]`. Здесь живёт
  L6 (добор MAP до 8 слотов) и веса `_rerank_hits`.

Метрики на запрос (ожидание — множество файлов E, выдача — список top-k):

* `hit@k`    = 1, если хотя бы один файл из E попал в top-k (иначе 0);
* `recall@k` = |top-k ∩ E| / |E| — у «неоднозначных» запросов E из 2-5
  файлов, поэтому recall информативнее hit;
* `mrr@k`    = 1 / (позиция первого попадания) или 0, если попаданий нет.

Запуск (одна команда, обе роли):

    python -B -X utf8 godot_agent/python/tests/test_search_quality.py

  — unittest-часть: определения метрик, синтетическое ранжирование, формат
  golden-set и пороги-храповик на полигоне. Полигон печатает таблицу по
  обоим срезам прямо из `setUpClass`.

    python -B -X utf8 .../test_search_quality.py --report [--project P] [--variant both]

  — только отчёт-таблица (по обоим срезам или по одному) и код возврата:
  1 — что-то ниже храповика, 2 — проект-полигон не найден.

Проект-полигон ищется так: `$env:GODOT_AGENT_QUALITY_PROJECT`, иначе
`<любой_родитель_репо>\\<project_hint из golden-set>`. Не нашёлся — тест
помечается skip (в CI полигона нет), синтетическая часть работает всегда.

Пороги-«храповик» в THRESHOLDS — это измеренный базис L2 (см.
docs/librarian_search_plan.md §3.1), слегка ослабленный. Правка поиска,
которая их ломает, — регрессия, даже если «выглядит правильнее».
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, os.pardir)))
import _bootstrap  # noqa: E402,F401
from minilich import ml_project_index  # noqa: E402
from project_tools import can_read_project_path  # noqa: E402
import librarian  # noqa: E402

K = 8                                     # срез метрик = MAP_LIMIT Библиотекаря
GOLDEN_PATH = os.path.join(_HERE, "data", "search_golden_yandex_game_dev.json")

# Храповик: измеренный базис минус запас 0.02, округлённый вниз до сотых.
# Запас меньше одного запроса самой мелкой корзины (1/38 = 0.026), то есть
# падение на два запроса храповик ловит, на один — прощает. Порог — МИНИМУМ
# двух срезов (index, map): слой MAP переставляет выдачу, и падать может любой.
# Значение 0.0 = «не проверяем». Порог НИКОГДА не опускается: храповик
# крутится только вверх, снижение — это осознанная правка с объяснением.
#
# Базис L4c+L3+L10+L6 (15.10.2026, полигон yandex-game-dev, 150 запросов, лимит
# символов 400, структурный тай-брейк индекса + стабильный тай-брейк MAP +
# бонус за склейку слов в пути + признак «запрос целиком = имя объявления»
# в слое MAP + бонус MAP за склейку слов запроса в ПУТИ записи + срез
# шумного хвоста MAP), срез index | срез map:
#   overall    hit 1.000|1.000 recall 1.000|1.000 mrr 0.993|0.978
#   ambiguous  1.000|1.000  1.000|1.000  1.000|0.956
#   capped     1.000|1.000  1.000|1.000  1.000|1.000
#   intent     1.000|1.000  1.000|1.000  0.941|0.843
#   rare_class 1.000|1.000  1.000|1.000  1.000|1.000
#   rare_func  1.000|1.000  1.000|1.000  1.000|1.000
#   rare_signal 1.000|1.000 1.000|1.000  1.000|1.000
#   rare_words 1.000|1.000  1.000|1.000  1.000|1.000
# Против базиса L4c+L3: map mrr .966 → .978 (`intent` .740 → .843; recall
# слоя MAP .997 → 1.000), index не изменился — правка живёт только в MAP.
# Ни одно ведро не просело ни в одном срезе.
# L6 (срез шумного хвоста) в этих числах не виден — он не двигает
# hit/recall/mrr, а убирает ПУСТЫЕ слоты: средняя выдача карты 7.45 → 3.22
# файла, «лишних» записей 6.09 → 1.87, «завсегдатаев» (≥ 10 попаданий,
# < 30 % ожидаемых) 27 → 2. Граница среза измерена: 0.58 теряет ожидаемый
# `upgrade_node.gd` («skill tree node upgrade»), 0.62 роняет mrr до 0.974.
# Узкое место осталось одно — разведочный `intent` в слое MAP (.843):
# шести промахам из 150 нужен не порядок и не чистка хвоста (L6), а
# попадание файла в пул индекса вовсе либо ожидание нескольких файлов
# (ведро `ambiguous`, `sprite`).
# Полное сравнение шагов (L2 → L5 → L4 → L4c/L3 → L10 → L6) — план §3.5,
# §3.6 и §3.7.
THRESHOLDS = {
    "overall": {"hit@8": 0.98, "recall@8": 0.98, "mrr@8": 0.95},
    "rare_func": {"hit@8": 0.98, "recall@8": 0.98, "mrr@8": 0.98},
    "rare_class": {"hit@8": 0.98, "recall@8": 0.98, "mrr@8": 0.98},
    "rare_signal": {"hit@8": 0.98, "recall@8": 0.98, "mrr@8": 0.98},
    "rare_words": {"hit@8": 0.98, "recall@8": 0.98, "mrr@8": 0.98},
    "ambiguous": {"hit@8": 0.98, "recall@8": 0.98, "mrr@8": 0.93},
    "capped": {"hit@8": 0.98, "recall@8": 0.98, "mrr@8": 0.98},
    "intent": {"hit@8": 0.98, "recall@8": 0.98, "mrr@8": 0.82},
}


def metrics(expected, ranked, k=K):
    """Метрики одного запроса: expected — список путей, ranked — порядок выдачи."""
    exp = set(str(e) for e in expected)
    top = [str(p) for p in ranked[:k]]
    found = [i for i, p in enumerate(top, 1) if p in exp]
    return {
        "hit@%d" % k: 1.0 if found else 0.0,
        "recall@%d" % k: (len(set(top) & exp) / float(len(exp))) if exp else 0.0,
        "mrr@%d" % k: (1.0 / found[0]) if found else 0.0,
    }


def _mean(rows, key):
    return (sum(r[key] for r in rows) / float(len(rows))) if rows else 0.0


def rank_index(root, query, k=K):
    """Срез `index`: порядок файлов из индекса (то, чем питается MAP)."""
    hits = ml_project_index.search(root, query, limit=k)
    return [str(h.get("path", "")) for h in hits]


def rank_map(root, query, k=K):
    """Срез `map`: порядок файлов в слое MAP Библиотекаря.

    Повторяет `librarian.answer()` (строки ~952-993) на публичных и
    полупубличных функциях самого модуля, чтобы замер не разошёлся с
    поведением слоя: если `_rerank_hits`/`_expanded_query` переименуют,
    тест упадёт с AttributeError, а не покажет красивую неправду.
    """
    q_exp, syn_used = librarian._expanded_query(query)
    hits = ml_project_index.search(
        root, q_exp, limit=librarian.MAP_LIMIT * librarian._RERANK_POOL)
    hits = [h for h in hits if can_read_project_path(
        "res://" + str(h.get("path", "")), root,
        allow_addons=False, allow_self_edit=False, addon_dir=None)]
    return [str(h.get("path", "")) for h in
            librarian._rerank_hits(hits, query, syn_used)[:k]]


VARIANTS = {"index": rank_index, "map": rank_map}


def load_golden(path=GOLDEN_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _matches(root, golden):
    """Тот ли это проект: хотя бы 60 % ожидаемых файлов на месте."""
    total = present = 0
    for item in golden.get("queries", ()):
        for e in item.get("expect", ()):
            total += 1
            if os.path.isfile(os.path.join(root, str(e).replace("/", os.sep))):
                present += 1
    return total > 0 and present / float(total) >= 0.6


def find_project(golden, hint_path=None):
    """Корень проекта-полигона или None.

    Порядок: явный путь -> переменная окружения -> `<родитель репо>/<hint>`.
    Родителей перебираем вверх (в CI полигона рядом с репо нет — вернётся None,
    и тест корректно уйдёт в skip).
    """
    hint = str(golden.get("project_hint") or "")
    cands = []
    if hint_path:
        cands.append(hint_path)
    env = os.environ.get("GODOT_AGENT_QUALITY_PROJECT")
    if env:
        cands.append(env)
    d = _HERE
    for _ in range(8):
        d = os.path.abspath(os.path.join(d, os.pardir))
        if hint:
            cands.append(os.path.join(d, hint))
    seen = set()
    for c in cands:
        c = os.path.abspath(c)
        if c in seen or not os.path.isfile(os.path.join(c, "project.godot")):
            continue
        seen.add(c)
        if _matches(c, golden):
            return c
    return None


def evaluate(root, golden, rank):
    """Прогон golden-set: строки по запросам + список устаревших записей."""
    rows = []
    stale = []
    for item in golden.get("queries", ()):
        q = str(item.get("q") or "")
        if not q:
            continue
        expect = [str(e) for e in item.get("expect", ())
                  if os.path.isfile(os.path.join(root, str(e).replace("/", os.sep)))]
        if not expect:
            stale.append(item)      # файл переименован/удалён — эталон протух
            continue
        row = metrics(expect, rank(root, q))
        row["q"] = q
        row["bucket"] = str(item.get("bucket") or "?")
        row["expect"] = expect
        row["ranked"] = rank(root, q)
        rows.append(row)
    return rows, stale


def summarize(rows):
    """Средние по ведрам и по всем запросам."""
    keys = ["hit@%d" % K, "recall@%d" % K, "mrr@%d" % K]
    buckets = {}
    for r in rows:
        buckets.setdefault(r["bucket"], []).append(r)
    out = {"n": len(rows), "buckets": {}, "keys": keys}
    for name in sorted(buckets):
        b = {"n": len(buckets[name])}
        for k_ in keys:
            b[k_] = _mean(buckets[name], k_)
        out["buckets"][name] = b
    o = {"n": len(rows)}
    for k_ in keys:
        o[k_] = _mean(rows, k_)
    out["overall"] = o
    return out


def format_report(title, root, golden, rows, stale, misses=8):
    """Текстовая таблица для консоли + сводка для порогов."""
    s = summarize(rows)
    keys = s["keys"]
    lines = ["", "=== %s ===" % title,
             "проект: %s" % root,
             "golden: %s | запросов %d | устаревших %d"
             % (os.path.basename(GOLDEN_PATH), s["n"], len(stale)),
             "%-12s %4s %8s %10s %8s" % ("ведро", "n", keys[0], keys[1], keys[2])]
    for name in sorted(s["buckets"]):
        b = s["buckets"][name]
        lines.append("%-12s %4d %8.3f %10.3f %8.3f"
                     % (name, b["n"], b[keys[0]], b[keys[1]], b[keys[2]]))
    o = s["overall"]
    lines.append("%-12s %4d %8.3f %10.3f %8.3f"
                 % ("ВСЕГО", o["n"], o[keys[0]], o[keys[1]], o[keys[2]]))
    bad = [r for r in rows if r[keys[0]] < 1.0]
    if bad:
        lines.append("промахи (hit@%d < 1): %d из %d" % (K, len(bad), len(rows)))
        for r in sorted(bad, key=lambda x: (x["mrr@%d" % K], x["bucket"]))[:misses]:
            lines.append("  [%s] %r -> ждали %s; выдача %s"
                         % (r["bucket"], r["q"], ", ".join(r["expect"]),
                            ", ".join(r["ranked"][:3]) or "-"))
    return "\n".join(lines), s


class MetricsDefinitionTest(unittest.TestCase):
    """Метрики считаются ровно так, как описано в докстроке модуля."""

    def test_hit_recall_rr(self):
        exp = ["a.gd", "b.gd"]
        m = metrics(exp, ["x.gd", "b.gd", "a.gd"])
        self.assertEqual(1.0, m["hit@8"])
        self.assertEqual(1.0, m["recall@8"])
        self.assertAlmostEqual(0.5, m["mrr@8"])   # первое попадание — 2-е место
        m = metrics(exp, ["x.gd", "y.gd"])
        self.assertEqual(0.0, m["hit@8"])
        self.assertEqual(0.0, m["recall@8"])
        self.assertEqual(0.0, m["mrr@8"])
        m = metrics(exp, ["a.gd"])
        self.assertEqual(1.0, m["mrr@8"])
        self.assertAlmostEqual(0.5, m["recall@8"])  # нашёлся один из двух

    def test_cut_is_exactly_k(self):
        """9-е место не считается попаданием при k=8 — иначе срез врёт."""
        ranked = ["a%d.gd" % i for i in range(8)] + ["z.gd"]
        self.assertEqual(0.0, metrics(["z.gd"], ranked)["hit@8"])
        self.assertEqual(1.0, metrics(["z.gd"], ranked, k=9)["hit@9"])

    def test_empty_expectation_is_not_a_hit(self):
        m = metrics([], ["a.gd"])
        self.assertEqual(0.0, m["hit@8"])
        self.assertEqual(0.0, m["recall@8"])
        self.assertEqual(0.0, m["mrr@8"])


SYNTH_BOSS = """class_name SynthBoss
extends Node

signal minions_called

const MAX_PHASE = 3

func summon_minions(count: int) -> void:
\tminions_called.emit()
"""

SYNTH_UI = """extends CanvasLayer

func _ready() -> void:
\tpass
"""


def _write(root, rel, text):
    full = os.path.join(root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


class SyntheticRankingTest(unittest.TestCase):
    """Свойства ранжирования, которые обязаны держаться всегда.

    Проект синтетический, в tempdir: тест работает в любом окружении,
    включая CI без полигона. Если поиск сломается так, что точное имя
    символа перестанет приводить в свой файл, — это поймается здесь, а не
    на 150 запросах полигона.
    """

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="search_quality_")
        _write(cls.root, "project.godot", "config_version=5\n")
        _write(cls.root, "src/synth_boss.gd", SYNTH_BOSS)
        _write(cls.root, "src/synth_ui.gd", SYNTH_UI)
        ml_project_index.build_index(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_exact_symbol_first_in_both_slices(self):
        for name, rank in sorted(VARIANTS.items()):
            self.assertEqual("src/synth_boss.gd", rank(self.root, "summon_minions")[0], name)

    def test_worded_query_keeps_owner(self):
        for name, rank in sorted(VARIANTS.items()):
            self.assertEqual("src/synth_boss.gd", rank(self.root, "summon minions")[0], name)

    def test_class_name_query_keeps_owner(self):
        for name, rank in sorted(VARIANTS.items()):
            self.assertEqual("src/synth_boss.gd", rank(self.root, "SynthBoss")[0], name)


BIG_DECLS = 140


class OversizedFileTest(unittest.TestCase):
    """L5: файл-переросток не теряет объявления из индекса.

    Регрессия P3: лимит `MAX_SYMBOLS = 60` вырезал из большого скрипта
    десятки объявлений, и они не находились поиском вообще — на полигоне
    так терялось 583 объявления (16 %), включая ВСЕ промахи базового
    замера (план §3.1). Проект синтетический, поэтому тест работает без
    полигона: он держит именно лимит, а не конкретный проект.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="search_quality_big_")
        lines = ["extends Node", "signal big_boss_died"]
        lines += ["func filler_%03d():" % i for i in range(BIG_DECLS)]
        lines += ["func summon_the_ancient_one():", "\tpass"]
        _write(self.root, "project.godot", "config_version=5\n")
        _write(self.root, "src/huge_boss.gd", "\n".join(lines) + "\n")
        # Соседний файл с общим словом: без него проверка «первое место»
        # ничего не проверяла бы — в проекте остался бы один файл.
        _write(self.root, "src/summoner.gd",
               "extends Node\n\nfunc summon_wolf():\n\tpass\n")
        ml_project_index.build_index(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_declarations_survive(self):
        """140+ объявлений в файле — ни одно не должно пропасть."""
        self.assertGreater(BIG_DECLS, 60, "файл обязан быть переростком")
        syms = ml_project_index._build_entry(self.root, "src/huge_boss.gd")["symbols"]
        self.assertEqual(BIG_DECLS + 2, len(syms), len(syms))
        self.assertIn("signal:big_boss_died", syms)
        self.assertIn("func:summon_the_ancient_one", syms)

    def test_rare_name_is_found(self):
        """Имя из хвоста большого файла находится и стоит первым.

        При лимите 60 символа не было в индексе вовсе — поиск по нему
        не возвращал ничего (или отдавал соседний файл по общему слову).
        """
        for query in ("summon_the_ancient_one", "summon the ancient one"):
            for variant, rank in VARIANTS.items():
                ranked = rank(self.root, query)
                self.assertTrue(ranked, "%s/%s: поиск не вернул ничего" % (variant, query))
                self.assertEqual("src/huge_boss.gd", ranked[0], "%s/%s" % (variant, query))


# --- L4: фикстуры структурного тай-брейка ---------------------------------
# Соперники в каждой паре имеют РАВНЫЙ score, а алфавит указывает на неверный
# файл — поэтому тесты падают на прежней сортировке `(-score, path)`.

TIE_ENEMY_BASE = """extends Node

signal bomber_wave

func take_damage() -> void:
	pass
"""

TIE_BOSS_SCRIPT = """extends Node

func open_chest() -> void:
	pass
"""

TIE_BOSS_SCENE = """[gd_scene format=3]

[node name="BossChest" type="Node2D"]
"""

TIE_PHRASE_OWNER = """extends Node

func act_completed() -> void:
	pass
"""

TIE_PHRASE_WORD = """extends Node

var completed = false
"""


class StructuralTieBreakTest(unittest.TestCase):
    """L4: при равном score порядок решает структура записи, а не алфавит.

    Критерий L4 из плана — файл, названный по запросу, не должен проигрывать
    алфавитно более раннему соседу (P2: порядок задавала сортировка строк).

    Срез `index` проверяется всегда, потому что L4 живёт в
    `ml_project_index.search`. Там, где слой MAP решает иначе, тест проверяет
    только `index` и говорит об этом прямо: `_rerank_hits` даёт +5 за
    совпадение с именем СИМВОЛА и всего +2.0/+1.0 за тип файла, поэтому
    сцена с узлом `BossChest` обгоняет одноимённый скрипт — это отдельная
    политика слоя MAP, а не тай-брейк индекса.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="search_quality_tie_")
        _write(self.root, "project.godot", "config_version=5\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _ranked(self, query):
        """Срезы по одному разу на запрос: индекс собирается один раз."""
        ml_project_index.build_index(self.root)
        return dict((name, rank(self.root, query))
                    for name, rank in sorted(VARIANTS.items()))

    def test_file_named_by_query_beats_alphabet(self):
        """`bomber_enemy.gd` впереди `base_enemy.gd` при равном score.

        Оба файла объявляют `signal bomber_wave` (score 2 у каждого), но имя
        запроса несёт только `bomber_enemy.gd`; по алфавиту вперёд шёл
        `base_enemy.gd` — ровно случай из плана (§3, P2).
        """
        _write(self.root, "scripts/base_enemy.gd", TIE_ENEMY_BASE)
        _write(self.root, "scripts/bomber_enemy.gd", TIE_ENEMY_BASE)
        for variant, ranked in self._ranked("bomber wave").items():
            self.assertEqual("scripts/bomber_enemy.gd", ranked[0], variant)

    def test_phrase_query_finds_its_own_declaration(self):
        """`act completed` -> `func act_completed()` раньше файла со словом.

        У обоих файлов score 2, но у одного объявлено ЦЕЛОЕ имя запроса,
        а у другого — только одно его слово; по алфавиту вперёд шёл
        `a_completed_word.gd`.
        """
        _write(self.root, "scripts/z_act_owner.gd", TIE_PHRASE_OWNER)
        _write(self.root, "scripts/a_completed_word.gd", TIE_PHRASE_WORD)
        for variant, ranked in self._ranked("act completed").items():
            self.assertEqual("scripts/z_act_owner.gd", ranked[0], variant)

    def test_script_beats_scene_in_index(self):
        """Скрипт объявляет структуру, сцена её применяет — скрипт первый.

        Здесь проверяется срез `index` (см. докстроку класса): у сцены имя
        узла `BossChest` совпадает с запросом «boss chest», и слой MAP
        поднимает её своим весом символа. Если скрипт объявляет имя запроса
        в коде, слой MAP тоже выбирает его — это L3, `MapPhraseBonusTest`.
        """
        _write(self.root, "scripts/boss_chest.gd", TIE_BOSS_SCRIPT)
        _write(self.root, "scenes/boss_chest.tscn", TIE_BOSS_SCENE)
        ranked = self._ranked("boss chest")["index"]
        self.assertEqual("scripts/boss_chest.gd", ranked[0], ranked)

    def test_order_is_deterministic(self):
        """Тай-брейк не зависит от порядка обхода: два вызова — один ответ."""
        _write(self.root, "scripts/base_enemy.gd", TIE_ENEMY_BASE)
        _write(self.root, "scripts/bomber_enemy.gd", TIE_ENEMY_BASE)
        first = self._ranked("bomber wave")
        second = self._ranked("bomber wave")
        self.assertEqual(first, second)


class MapRerankOrderTest(unittest.TestCase):
    """L4b: при РАВНЫХ весах слой MAP не пересортировывает выдачу по алфавиту.

    Та же первопричина P2, что у L4, но во втором месте — в
    `librarian._rerank_hits`. Проект не нужен: проверяется само правило
    порядка на двух записях с одинаковым весом, где алфавит противоречит
    порядку индекса (в индексе первым идёт тот, кто назван по запросу).
    """

    def test_equal_weights_keep_index_order(self):
        hits = [
            {"path": "scripts/z_enemy.gd", "kind": "gd", "score": 1,
             "symbols": ["func:hit"]},
            {"path": "scripts/a_enemy.gd", "kind": "gd", "score": 1,
             "symbols": ["func:hit"]},
        ]
        out = librarian._rerank_hits(hits, "hit", [])
        self.assertEqual(["scripts/z_enemy.gd", "scripts/a_enemy.gd"],
                         [str(h.get("path")) for h in out])

    def test_weight_still_wins_over_order(self):
        """Тай-брейк не отменяет вес: сильный кандидат обходит порядок индекса."""
        weak = [{"path": "scripts/z_enemy.gd", "kind": "gd", "score": 1,
                 "symbols": ["func:other"]}]
        strong = [{"path": "scripts/a_enemy.gd", "kind": "gd", "score": 1,
                   "symbols": ["func:spawn"]}]
        out = librarian._rerank_hits(weak + strong, "spawn", [])
        self.assertEqual("scripts/a_enemy.gd", str(out[0].get("path")))


class PhraseKeysTest(unittest.TestCase):
    """L4c: ключи признака фразы и ключи бонуса за путь — чистая функция.

    Именно её форма решает, что считается «запросом целиком», а что
    фрагментом: индексу нужны одиночные слова («sprite» — это `var:sprite`),
    а бонусу за путь — только склейки от двух слов, иначе «slow motion
    effect» находил бы файл по слову `motion`.
    """

    def test_whole_query_key(self):
        self.assertEqual("boss_chest", ml_project_index._phrase_key("Boss Chest"))
        self.assertEqual("", ml_project_index._phrase_key("   "))

    def test_phrase_keys_cover_all_runs(self):
        keys = ml_project_index._phrase_keys("slow motion effect")
        self.assertIn("slow_motion", keys)
        self.assertIn("motioneffect", keys)
        self.assertIn("slow_motion_effect", keys)
        self.assertIn("slow", keys)            # одиночные слова — нужны индексу

    def test_min_words_drops_singletons(self):
        keys = ml_project_index._phrase_keys("slow motion effect", min_words=2)
        self.assertNotIn("slow", keys)
        self.assertIn("slow_motion", keys)

    def test_path_keys_keep_query_and_joins_only(self):
        keys = ml_project_index._path_keys("slow motion effect")
        self.assertIn("slow motion effect", keys)   # прежнее поведение цело
        self.assertIn("slow_motion", keys)
        self.assertNotIn("motion", keys)            # одиночное слово — нельзя

    def test_single_word_query_is_unchanged(self):
        """Одиночный запрос: и ключи пути, и ключи фразы — то же слово (как было)."""
        self.assertEqual(("boss",), ml_project_index._path_keys("boss"))
        self.assertEqual(("boss",), ml_project_index._phrase_keys("boss"))


PATH_JOIN_BODY = """extends Node

func unrelated() -> void:
\tpass
"""


class PathJoinBonusTest(unittest.TestCase):
    """L4c: запрос словами узнаёт файл, НАЗВАННЫЙ по запросу.

    Оба файла дают равный score (по одному слову запроса в пути) и равны по
    всем признакам тай-брейка: оба слова есть и в имени, и точного объявления
    нет ни у одного. Различает их только путь: `slow_motion.gd` содержит
    склейку запроса, `motion_slow.gd` — нет. Без бонуса вперёд шёл алфавитно
    ранний `motion_slow.gd`.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="search_quality_path_")
        _write(self.root, "project.godot", "config_version=5\n")
        _write(self.root, "scripts/motion_slow.gd", PATH_JOIN_BODY)
        _write(self.root, "scripts/slow_motion.gd", PATH_JOIN_BODY)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_join_in_path_wins_index(self):
        ml_project_index.build_index(self.root)
        ranked = rank_index(self.root, "slow motion")
        self.assertEqual("scripts/slow_motion.gd", ranked[0], ranked)


MAP_PHRASE_SCRIPT = """class_name BossChest
extends Node

func open_chest() -> void:
\tpass
"""

# Узел `Monster` — синоним слова «boss»: сцена набирает ещё +1.5 и без L3
# обгоняет скрипт, который объявляет имя запроса в коде.
MAP_PHRASE_SCENE = """[gd_scene format=3]

[node name="Boss" type="Node2D"]

[node name="Chest" type="Area2D"]

[node name="Monster" type="Node2D"]
"""


class MapPhraseBonusTest(unittest.TestCase):
    """L3: запрос ЦЕЛИКОМ, совпавший с именем объявления, решает исход в MAP.

    Индекс этот признак считал и раньше (L4 `phrase_name`), но слой MAP его не
    использовал: сцена с узлами `Boss`/`Chest` набирала +10 за токены символов
    и обгоняла скрипт, который это имя ОБЪЯВЛЯЕТ. Фрагменты запроса признак не
    включают — иначе разведочный `intent` («slow motion effect») терял бы
    верный файл.
    """

    def test_phrase_rank_reads_symbols(self):
        self.assertEqual(0, librarian._phrase_rank(["class:BossChest"], "boss_chest", "bosschest"))
        self.assertEqual(0, librarian._phrase_rank(["func:apply_crit"], "apply_crit", "applycrit"))
        self.assertIsNone(librarian._phrase_rank(["Boss:Node2D", "Chest:Area2D"],
                                                 "boss_chest", "bosschest"))
        self.assertIsNone(librarian._phrase_rank(["func:apply_damage"], "apply", "apply"))
        self.assertIsNone(librarian._phrase_rank([], "boss_chest", "bosschest"))

    def test_symbol_name_strips_service_prefix(self):
        self.assertEqual("BossChest", librarian._symbol_name("class:BossChest"))
        self.assertEqual("Boss:Node2D", librarian._symbol_name("Boss:Node2D"))

    def test_declaration_in_code_beats_scene_in_both_slices(self):
        root = tempfile.mkdtemp(prefix="search_quality_phrase_")
        try:
            _write(root, "project.godot", "config_version=5\n")
            _write(root, "scripts/boss_chest.gd", MAP_PHRASE_SCRIPT)
            _write(root, "scenes/boss_chest.tscn", MAP_PHRASE_SCENE)
            ml_project_index.build_index(root)
            for variant, rank in sorted(VARIANTS.items()):
                ranked = rank(root, "boss chest")
                self.assertEqual("scripts/boss_chest.gd", ranked[0],
                                 "%s: %s" % (variant, ranked))
        finally:
            shutil.rmtree(root, ignore_errors=True)


class MapPathJoinBonusTest(unittest.TestCase):
    """L10: слой MAP награждает склейку слов запроса в ПУТИ файла.

    Та же мысль, что у индекса с L4c, но вторым способом: индекс считает
    бонус за путь в «токенах», а MAP — в своих весах (5.0 за символ, 3.0 за
    имя файла), поэтому без этого признака «завсегдатаи» вроде
    `game_manager.gd` остаются впереди файла, названного по запросу.
    Проект не нужен: проверяется само правило на записях с равным базовым
    весом и равными символами.
    """

    def _hits(self):
        return [
            {"path": "scripts/fx/motion_slow.gd", "kind": "gd", "score": 2.0,
             "symbols": ["func:play"]},
            {"path": "scripts/fx/slow_motion.gd", "kind": "gd", "score": 2.0,
             "symbols": ["func:play"]},
        ]

    def test_joined_path_wins_on_equal_weights(self):
        out = librarian._rerank_hits(self._hits(), "slow motion", [])
        self.assertEqual("scripts/fx/slow_motion.gd", str(out[0].get("path")))

    def test_symbol_match_still_outweighs_join(self):
        """Вес бонуса выбран замером (плато 4.0..6.0, берём нижний край): он
        сильнее совпадения с ИМЕНЕМ файла (3.0), но слабее совпадения с
        СИМВОЛОМ (5.0) — объявленное имя важнее, чем название пути."""
        hits = [
            {"path": "scripts/fx/motion_slow.gd", "kind": "gd", "score": 2.0,
             "symbols": ["func:slow_play"]},
            {"path": "scripts/fx/slow_motion.gd", "kind": "gd", "score": 2.0,
             "symbols": ["func:play"]},
        ]
        out = librarian._rerank_hits(hits, "slow motion", [])
        self.assertEqual("scripts/fx/motion_slow.gd", str(out[0].get("path")))

    def test_single_word_query_has_no_join_keys(self):
        """Одиночный запрос ключей-склеек не даёт: бонус за путь не срабатывает.

        Веса записей равны (одно слово запроса в имени файла + вид .gd), L6 их
        не режет, поэтому порядок остаётся тем, что дал индекс.
        """
        self.assertEqual((), librarian._path_join_keys("hit"))
        hits = [
            {"path": "scripts/fx/hit.gd", "kind": "gd", "score": 1,
             "symbols": ["func:play"]},
            {"path": "scripts/fx/hit_play.gd", "kind": "gd", "score": 1,
             "symbols": ["func:play"]},
        ]
        out = librarian._rerank_hits(hits, "hit", [])
        self.assertEqual(["scripts/fx/hit.gd", "scripts/fx/hit_play.gd"],
                         [str(h.get("path")) for h in out])


class MapNoiseCutTest(unittest.TestCase):
    """L6: слой MAP не добивается шумом до 8 слотов.

    Пул кандидатов индекса (24 записи) всегда длиннее карты, и раньше слабый
    хвост занимал все восемь строк: «завсегдатаи» вроде `chain_lightning.gd`
    попадали в ответ на чужие запросы. Теперь остаются записи с весом не ниже
    доли от лучшего (`librarian.MAP_CUT_RATIO`). Доля выбрана замером на
    golden-set (150 запросов, срез `map`): до 0.55 включительно hit@8 1.000,
    recall@8 1.000 и mrr@8 0.978 не меняются, 0.58 теряет ожидаемый
    `upgrade_node.gd` («skill tree node upgrade»). Проект не нужен:
    проверяется само правило на записях с известными весами.
    """

    def setUp(self):
        self.assertTrue(0.0 < librarian.MAP_CUT_RATIO < 1.0,
                        "доля среза вне (0,1): %r" % (librarian.MAP_CUT_RATIO,))

    def test_synonym_only_tail_is_cut(self):
        """Записи без СВОИХ совпадений (только синоним, только .gd-вес) отсекаются.

        `damage_calc.gd` (символ `apply_damage` = 5+5, имя = 3, объявление
        целиком = 6, .gd = 2) набирает 21.0; `base_enemy.gd` совпал лишь
        синонимом `hurt` (1.5 + 2), `game_manager.gd` — только видом файла
        (2.0). Порог 0.55 * 21.0 = 11.55 оставляет одну запись.
        """
        hits = [
            {"path": "scripts/damage_calc.gd", "kind": "gd", "score": 0.0,
             "symbols": ["func:apply_damage"]},
            {"path": "scripts/base/base_enemy.gd", "kind": "gd", "score": 0.0,
             "symbols": ["func:apply_hurt"]},
            {"path": "scripts/autoload/game_manager.gd", "kind": "gd", "score": 0.0,
             "symbols": ["func:start_game"]},
        ]
        out = librarian._rerank_hits(hits, "apply damage", ["hurt"])
        self.assertEqual(["scripts/damage_calc.gd"],
                         [str(h.get("path")) for h in out])

    def test_equal_to_best_survives(self):
        """Сравнение нестрогое: запись с весом, равным лучшему, не режется."""
        hits = [
            {"path": "scripts/damage/apply_damage.gd", "kind": "gd", "score": 0.0,
             "symbols": ["func:tick"]},
            {"path": "scripts/fx/apply_damage.gd", "kind": "gd", "score": 0.0,
             "symbols": ["func:tick"]},
        ]
        out = librarian._rerank_hits(hits, "apply damage", [])
        self.assertEqual(["scripts/damage/apply_damage.gd",
                          "scripts/fx/apply_damage.gd"],
                         [str(h.get("path")) for h in out])

    def test_empty_hits_do_not_crash(self):
        """Пустая выдача индекса остаётся пустой: у среза нет «лучшего»."""
        self.assertEqual([], librarian._rerank_hits([], "apply damage", []))


class GoldenSetFileTest(unittest.TestCase):
    """Сам golden-set: формат и границы (50-150 запросов, без дублей)."""

    @unittest.skipUnless(os.path.isfile(GOLDEN_PATH), "golden-set не сгенерирован")
    def test_golden_set_shape(self):
        g = load_golden()
        self.assertEqual(1, g.get("format"))
        self.assertTrue(g.get("project_hint"))
        qs = g.get("queries") or []
        self.assertTrue(50 <= len(qs) <= 150, "запросов %d, нужно 50-150" % len(qs))
        seen = set()
        for item in qs:
            self.assertTrue(item.get("q"), item)
            self.assertTrue(item.get("expect"), item)
            self.assertTrue(item.get("bucket"), item)
            low = str(item["q"]).lower()
            self.assertNotIn(low, seen, "дубль запроса: %s" % item["q"])
            seen.add(low)
        self.assertEqual(len(qs), sum(g.get("buckets", {}).values()),
                         "buckets в шапке не сходятся с запросами")


@unittest.skipUnless(os.path.isfile(GOLDEN_PATH), "golden-set не сгенерирован")
class GoldenSetQualityTest(unittest.TestCase):
    """Замер на реальном проекте-полигоне. В CI (без полигона) — skip."""

    reports = {}

    @classmethod
    def setUpClass(cls):
        cls.golden = load_golden()
        cls.root = find_project(cls.golden)
        if cls.root is None:
            raise unittest.SkipTest(
                "проект-полигон %r не найден: задайте GODOT_AGENT_QUALITY_PROJECT"
                % cls.golden.get("project_hint"))
        cls.reports = {}
        for name in sorted(VARIANTS):
            rows, stale = evaluate(cls.root, cls.golden, VARIANTS[name])
            text, summary = format_report("L2 / %s" % name, cls.root,
                                          cls.golden, rows, stale)
            cls.reports[name] = summary
            print(text)

    def test_quality_thresholds(self):
        """Храповик: падение ниже измеренного базиса — регрессия поиска."""
        problems = []
        for name in sorted(self.reports):
            s = self.reports[name]
            for key in s["keys"]:
                limit = THRESHOLDS.get("overall", {}).get(key, 0.0)
                if s["overall"][key] < limit - 1e-9:
                    problems.append("%s ВСЕГО %s = %.3f < %.3f"
                                    % (name, key, s["overall"][key], limit))
            for bucket in sorted(s["buckets"]):
                b = s["buckets"][bucket]
                for key in s["keys"]:
                    limit = THRESHOLDS.get(bucket, {}).get(key, 0.0)
                    if b[key] < limit - 1e-9:
                        problems.append("%s %s %s = %.3f < %.3f"
                                        % (name, bucket, key, b[key], limit))
        self.assertEqual([], problems,
                         "регрессия качества поиска:\n  " + "\n  ".join(problems))

    def test_golden_set_not_stale(self):
        """Протухший эталон — не тихий пропуск: перегенерируйте golden-set."""
        rows, stale = evaluate(self.root, self.golden, VARIANTS["index"])
        total = len(rows) + len(stale)
        share = len(stale) / float(total) if total else 0.0
        self.assertLess(share, 0.25,
                        "протухло %d из %d запросов — перегенерируйте "
                        "tools/make_search_golden.py" % (len(stale), total))

    # L6: замер среза шумного хвоста — средняя выдача карты 3.22 файла.
    # Порог округлён вверх: карта длиннее — это осознанная правка с новым
    # замером (как и пороги выше), а не тихий возврат «завсегдатаев».
    MAP_SHOWN_LIMIT = 4.0

    def test_map_is_not_padded_with_noise(self):
        """L6: карта не добивается шумом до 8 слотов (замер: 3.22 из 8)."""
        rows, _stale = evaluate(self.root, self.golden, VARIANTS["map"])
        shown = sum(len(r["ranked"]) for r in rows) / float(len(rows))
        self.assertLessEqual(
            shown, self.MAP_SHOWN_LIMIT,
            "карта снова добивается до 8 слотов: средняя выдача %.2f" % shown)


def main(argv=None):
    """Отчёт-таблица без unittest: `--report [--project P] [--variant index|map|both]`.

    Возвращает 1, если что-то ниже храповика (удобно в скриптах), 2 — если
    проект-полигон не найден.
    """
    ap = argparse.ArgumentParser(description="L2: качество поиска Библиотекаря")
    ap.add_argument("--project", default=None, help="корень проекта-полигона")
    ap.add_argument("--golden", default=GOLDEN_PATH)
    ap.add_argument("--variant", default="both", choices=("index", "map", "both"))
    ap.add_argument("--misses", type=int, default=8, help="сколько промахов печатать")
    args = ap.parse_args(argv)
    golden = load_golden(args.golden)
    root = find_project(golden, args.project)
    if root is None:
        print("проект %r не найден: --project или GODOT_AGENT_QUALITY_PROJECT"
              % golden.get("project_hint"))
        return 2
    names = sorted(VARIANTS) if args.variant == "both" else [args.variant]
    rc = 0
    for name in names:
        rows, stale = evaluate(root, golden, VARIANTS[name])
        text, s = format_report("L2 / %s" % name, root, golden, rows, stale,
                                args.misses)
        print(text)
        for key in s["keys"]:
            limit = THRESHOLDS.get("overall", {}).get(key, 0.0)
            if s["overall"][key] < limit - 1e-9:
                print("  !! ВСЕГО %s = %.3f < храповика %.3f"
                      % (key, s["overall"][key], limit))
                rc = 1
    return rc


def _run_unittest():
    """Обычный прогон тестов модуля (полигон, если он рядом, печатает отчёт)."""
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


_REPORT_FLAGS = ("--report", "--project", "--golden", "--variant", "--misses")

if __name__ == "__main__":
    _argv = sys.argv[1:]
    if any(a.split("=")[0] in _REPORT_FLAGS for a in _argv):
        sys.exit(main([a for a in _argv if a != "--report"]))
    sys.exit(_run_unittest())
