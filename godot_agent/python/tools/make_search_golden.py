# -*- coding: utf-8 -*-
"""Генератор golden-set для замера качества поиска Библиотекаря (пункт L2).

Запуск (на полигоне):

    python -B -X utf8 godot_agent/python/tools/make_search_golden.py ^
        --project D:\\vajno\\Godot\\yandex-game-dev

Ожидания выводятся из **текста исходников**, а не из индекса: иначе дефект
индекса (потерянный символ, неполный обход) попал бы в эталон и замер
«подтвердил» бы сам себя. Регулярки берутся из `ml_project_index` (те же,
которыми индекс и строится) — расхождение невозможно.

Вёдра запросов (по убыванию «обязано работать»):

| ведро | запрос | ожидание | что ловит |
|---|---|---|---|
| `rare_func` / `rare_class` / `rare_signal` | точное имя символа, объявленного ровно в одном файле | этот файл | регрессии ранжирования (сейчас обязано быть 100 %) |
| `rare_words` | имя, разбитое на слова (`chain_lightning` -> `chain lightning`) | файл-объявление | P1: скор без IDF, шум по generic-словам |
| `ambiguous` | имя, объявленное в 2-5 файлах | все эти файлы | P2: тай-брейк по алфавиту |
| `capped` | имя из файла-переростка (объявлений в файле > 60) | файл-объявление | P3: лимит символов (L5: поднят 60 → 400) |
| `intent` | запрос «на смысл» (2-4 слова) | файл-владелец, размечен вручную | L3/L4: IDF и структурный тай-брейк |

Результат — JSON рядом с тестами; его читает `tests/test_search_quality.py`.
Пишется детерминированно (сортировка по имени, фиксированные лимиты ведёр),
чтобы повторный запуск на неизменённом проекте давал тот же файл.
"""
import argparse
import datetime
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.abspath(os.path.join(_HERE, os.pardir))
sys.path.insert(0, _PY)
import _bootstrap  # noqa: E402,F401  # пути к parsers/, godot_tools/, minilich/
from minilich import ml_project_index as mi  # noqa: E402

DEFAULT_OUT = os.path.join(_PY, "tests", "data",
                           "search_golden_yandex_game_dev.json")

# Лимиты ведёр: суммарно 50-150 запросов (требование пункта L2).
LIMITS = {
    "rare_func": 38,
    "rare_class": 25,
    "rare_signal": 20,
    "rare_words": 25,
    "ambiguous": 15,
    "capped": 10,
}

# Служебные и слишком общие имена: годятся для любого проекта, качество
# поиска по ним ничего не говорит.
GENERIC = {
    "main", "init", "setup", "start", "update", "ready", "process", "print",
    "debug", "test", "tests", "data", "value", "name", "path", "type", "node",
    "enabled", "visible", "position", "size", "color", "config", "settings",
}

_DECL_KINDS = (("func", mi._FUNC_RE), ("class", mi._CLASS_RE),
               ("signal", mi._SIGNAL_RE), ("const", mi._CONST_RE),
               ("var", mi._VAR_RE))

# Ручная разметка «запрос на смысл». Файл-владелец — тот, где тема живёт
# целиком; если тема честно размазана по двум файлам, указаны оба.
# Пропавший файл молча не попадает в набор (см. add() в build()).
INTENT = (
    ("chain lightning artifact", ["scripts/artifacts/chain_lightning.gd"]),
    ("save game progress", ["scripts/autoload/save_manager.gd"]),
    ("shop stock restock", ["scripts/autoload/shop_stock_manager.gd"]),
    ("chest opening reward", ["scripts/autoload/chest_manager.gd",
                              "scripts/ui/chest_screen.gd"]),
    ("boss chest", ["scripts/environment/boss_chest.gd"]),
    ("enemy pool spawn", ["scripts/utils/enemy_pool_manager.gd"]),
    ("skill tree node upgrade", ["scripts/ui/meta_tree/skill_tree_logic.gd",
                                 "scripts/ui/meta_tree/upgrade_node.gd"]),
    ("difficulty selection", ["scripts/ui/difficulty_screen.gd",
                              "scripts/autoload/difficulty_manager.gd"]),
    ("card evolution", ["scripts/logic/card_evolution_manager.gd"]),
    ("floating damage number", ["scripts/utils/damage_number_pool.gd"]),
    ("yandex platform adapter", ["scripts/platform/adapters/yandex_adapter.gd"]),
    ("achievement unlocked", ["scripts/autoload/achievement_manager.gd"]),
    ("knight mastery pool", ["scripts/data/mastery/knight_mastery_pool.gd"]),
    ("event pool act one", ["scripts/events/event_pool_act_1.gd"]),
    ("hit feedback shake", ["scripts/ui/hit_feedback.gd"]),
    ("slow motion effect", ["scripts/autoload/slow_mo_manager.gd"]),
    ("map node selection", ["scripts/ui/map_node_ui.gd",
                            "scripts/autoload/map_manager.gd"]),
)


def _scan(root):
    """Пути .gd относительно root (тот же SKIP_DIRS, что у индекса)."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in mi.SKIP_DIRS]
        for fn in filenames:
            if fn.lower().endswith(".gd"):
                full = os.path.join(dirpath, fn)
                out.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(out)


def _read(root, rel):
    try:
        with open(os.path.join(root, rel.replace("/", os.sep)), "r",
                  encoding="utf-8-sig", errors="replace") as f:
            return f.read(200000)
    except OSError:
        return ""


def _decls(root, rels):
    """name -> {rel: {виды объявлений}}. Один проход по тексту файлов."""
    decls = {}
    for rel in rels:
        text = _read(root, rel)
        if not text:
            continue
        for kind, rx in _DECL_KINDS:
            for m in rx.finditer(text):
                decls.setdefault(m.group(1), {}).setdefault(rel, set()).add(kind)
    return decls


def _words(name):
    """chain_lightning -> [chain, lightning]; BaseArtifact -> [base, artifact]."""
    out = []
    for part in mi._CAMEL_RE.sub(" ", name).replace("_", " ").split():
        if len(part) >= 3:
            out.append(part.lower())
    return out


def _kind_of(files, kind):
    return any(kind in v for v in files.values())


def _unique(decls, kind, min_len=6, public_only=True):
    """Имена с ровно одним файлом-объявлением, отсортированные по имени."""
    out = []
    for name, files in decls.items():
        if len(files) != 1 or len(name) < min_len:
            continue
        if public_only and name.startswith("_"):
            continue
        if name.lower() in GENERIC:
            continue
        if _kind_of(files, kind):
            out.append(name)
    return sorted(out)


# Исторический порог ведра `capped`: лимит символов, с которым проект жил
# до L5 (см. `ml_project_index.MAX_SYMBOLS`). Определение ведра держим на
# этом числе, а не на текущем лимите: иначе после подъёма лимита ведро
# опустеет и регрессия «редкое имя выпало из индекса» останется без покрытия.
CAP_BASELINE = 60


def _lost_to_cap(root, rels, decls):
    """Имена из файлов-переростков: объявлений в файле больше CAP_BASELINE.

    Ведро родилось как «имена, которые вырезал `MAX_SYMBOLS = 60`», и ищет
    их через сам `_build_entry` — то есть по текущему коду индекса. L5
    поднял лимит до 400, и такая формулировка сделала бы ведро пустым:
    символы, потерянные лимитом, теперь в индексе есть, а регрессия
    «редкое имя выпало из индекса» осталась бы без покрытия. Поэтому
    порог берём ИСТОРИЧЕСКИЙ (60) и не зависим от текущего лимита.
    """
    out = []
    for rel in rels:
        text = _read(root, rel)
        if not text:
            continue
        total = sum(len(rx.findall(text)) for _k, rx in _DECL_KINDS)
        if total <= CAP_BASELINE:
            continue
        for name, files in decls.items():
            if rel not in files or len(files) != 1 or len(name) < 6:
                continue
            if name.startswith("_") or name.lower() in GENERIC:
                continue
            out.append(name)
    return sorted(set(out))


def build(root):
    """Собирает golden-set. Возвращает (queries, stats)."""
    rels = _scan(root)
    decls = _decls(root, rels)
    queries = []

    def add(q, expect, bucket):
        expect = [e for e in expect
                  if os.path.isfile(os.path.join(root, e.replace("/", os.sep)))]
        if q and expect:
            queries.append({"q": q, "expect": expect, "bucket": bucket})

    for kind in ("func", "class", "signal"):
        for name in _unique(decls, kind)[:LIMITS["rare_%s" % kind]]:
            add(name, sorted(decls[name]), "rare_%s" % kind)

    # Слова редких имён: тот же ответ, но запрос в 2-3 слова (P1 — нет IDF).
    worded = []
    for kind in ("func", "class"):
        for name in _unique(decls, kind, min_len=10):
            w = _words(name)
            if len(w) >= 2 and len(" ".join(w)) >= 10:
                worded.append((" ".join(w), name))
    for q, name in sorted(worded)[:LIMITS["rare_words"]]:
        add(q, sorted(decls[name]), "rare_words")

    # Неоднозначные: имя живёт в 2-5 файлах, ожидание — все они.
    amb = []
    for name, files in decls.items():
        if 2 <= len(files) <= 5 and len(name) >= 6 and not name.startswith("_"):
            if name.lower() in GENERIC:
                continue
            if any(_kind_of(files, k) for k in ("func", "const", "var")):
                amb.append((name, len(files)))
    amb.sort(key=lambda x: (-x[1], x[0]))
    for name, _n in amb[:LIMITS["ambiguous"]]:
        add(name, sorted(decls[name]), "ambiguous")

    # Файлы-переростки (P3): больше 60 объявлений в файле — именно там
    # лимит символов вырезал имена. С L5 (лимит 400) такие имена в индексе
    # есть, а ведро остаётся регрессией на их потерю.
    for name in _lost_to_cap(root, rels, decls)[:LIMITS["capped"]]:
        add(name, sorted(decls[name]), "capped")

    for q, expect in INTENT:
        add(q, expect, "intent")

    stats = {
        "files_gd": len(rels),
        "names": len(decls),
        "declarations": sum(len(v) for v in decls.values()),
    }
    return queries, stats


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="golden-set для L2 (качество поиска Библиотекаря)")
    ap.add_argument("--project", required=True, help="корень Godot-проекта")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--hint", default=None,
                    help="имя папки проекта для автопоиска в тесте "
                         "(по умолчанию basename проекта)")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.project)
    if not os.path.isfile(os.path.join(root, "project.godot")):
        print("!! нет project.godot в %s" % root)
        return 2
    queries, stats = build(root)
    buckets = {}
    for q in queries:
        buckets[q["bucket"]] = buckets.get(q["bucket"], 0) + 1
    data = {
        "format": 1,
        "project_hint": args.hint or os.path.basename(root),
        "generated": datetime.date.today().isoformat(),
        "stats": stats,
        "buckets": buckets,
        "queries": queries,
    }
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("записано: %s" % out)
    print("файлов .gd: %d, имён: %d, объявлений: %d"
          % (stats["files_gd"], stats["names"], stats["declarations"]))
    print("запросов: %d" % len(queries))
    for b in sorted(buckets):
        print("  %-11s %3d" % (b, buckets[b]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
