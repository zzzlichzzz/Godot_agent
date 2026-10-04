# -*- coding: utf-8 -*-
"""Живой headless-тест agent_updater.gd: Markdown -> BBCode для панели.

Запуск: python -B godot_agent/python/tests/test_updater_bbcode_live.py [--godot EXE]

ЗАЧЕМ. test_updater_live.py закрывает сетевую часть (GitHub Releases API,
выбор .zip-ассета, распаковку поверх аддона). С появлением автоматических
релизов у agent_updater.gd появилась markdown_to_bbcode(): описание релиза
пишется в Markdown для GitHub, а панель показывает его в RichTextLabel с
bbcode_enabled. Ошибка здесь заметна только глазами - текст выглядит
некрасиво, и ни один offline-тест её не поймает.

Этот набор гоняет НАСТОЯЩИЙ движок по НАСТОЯЩЕМУ скрипту, поэтому ловит и
синтаксис GDScript, и расхождение с ожидаемой разметкой. Ожидаемые значения
не выдуманы: их порождает release_prepare.py (см. test_release_prepare.py).

ГРАНИЦА. Проверяется только подмножество Markdown, которое выпускает
release_prepare.py: заголовки, маркеры, **жирный**, `код`, ссылки, ---.
Вложенность, таблицы и блочные цитаты не разбираются - это заявленная
граница функции, а не недоработка.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SENTINEL = "UPDATER_BBCODE_LIVE "

#: (входной Markdown, ожидаемый BBCode). Порядок задаёт порядок проверок.
CASES = [
    # Заголовок ## из release_prepare.py -> крупный жирный.
    ("## Что нового в 0.9.0 (2026-01-02)",
     "[b][font_size=20]Что нового в 0.9.0 (2026-01-02)[/font_size][/b]"),
    # Подзаголовок раздела ### -> жирный без размера.
    ("### Исправления", "[b]Исправления[/b]"),
    # Маркер списка -> буллет, дефис не остаётся в тексте.
    ("- fix(panel): вкладки", "\u2022 fix(panel): вкладки"),
    # Вложенный маркер сохраняет отступ.
    ("  - второй уровень", "  \u2022 второй уровень"),
    # Ссылка на коммит становится кликабельной.
    ("- правка ([abc1234](https://github.com/o/r/commit/abc1234))",
     "\u2022 правка ([url=https://github.com/o/r/commit/abc1234]abc1234[/url])"),
    # **жирный** и `код`, как в строке "Обновление с `0.8.3`".
    ("- **важно**: вызов `foo()`", "\u2022 [b]важно[/b]: вызов [code]foo()[/code]"),
    # Подчёркивание - обычный текст: _ready это имя в GDScript, а не курсив.
    ("- вызов _ready() и _process", "\u2022 вызов _ready() и _process"),
    # Разделитель.
    ("---", "\u2500" * 10),
    # Скобки экранируются. Ожидается ИМЕННО экранированная форма: RichTextLabel
    # покажет "[lb]lb[rb]" как "[lb]", то есть на экране останется исходный текст.
    ("[lb] и [rb] остаются текстом", "[lb]lb[rb] и [lb]rb[rb] остаются текстом"),
    # Пустое описание не должно ломать разметку.
    ("", ""),
]

#: Мусор, который не должен попасть в результат ни в одном случае.
FORBIDDEN = ["\u0001", "](", "**"]


def build_script() -> str:
    """GDScript, зовущий markdown_to_bbcode и печатающий результат по строке."""
    lines = []
    for index, (md, _expected) in enumerate(CASES):
        lines.append("\temit(%d, Updater.markdown_to_bbcode(%s))"
                     % (index, json.dumps(md, ensure_ascii=False)))
    return (
        "extends SceneTree\n"
        "\n"
        'const Updater = preload("res://addons/Godot_agent/godot_agent/agent_updater.gd")\n'
        "\n"
        "func emit(index: int, value: String) -> void:\n"
        "\tprint(str(\"" + SENTINEL + "\" + str(index) + \"\\t\" + value))\n"
        "\n"
        "func _init() -> void:\n"
        + "\n".join(lines) + "\n"
        "\tquit(0)\n"
    )


def run_godot(executable: str, project_dir: Path) -> str:
    script = project_dir / "emit_bbcode.gd"
    script.write_text(build_script(), encoding="utf-8")
    proc = subprocess.run(
        [executable, "--headless", "--path", str(project_dir), "--script",
         "res://emit_bbcode.gd"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180)
    return proc.stdout + proc.stderr


def collect(output: str):
    """Разобрать строки SENTINEL<index>\\t<результат> в dict {index: результат}."""
    got = {}
    for line in output.splitlines():
        if not line.startswith(SENTINEL):
            continue
        rest = line[len(SENTINEL):]
        if "\t" not in rest:
            continue
        index, value = rest.split("\t", 1)
        try:
            got[int(index)] = value
        except ValueError:
            continue
    return got


def main() -> int:
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT_AGENT_GODOT_EXECUTABLE"))
    args = parser.parse_args()

    default_engine = r"D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe"
    executable = (args.godot or (default_engine if os.path.isfile(default_engine) else None)
                  or shutil.which("godot") or shutil.which("godot4"))
    if not executable or not os.path.isfile(executable):
        print("Godot binary not found. Skipping live BBCode test.")
        return 0

    # python/tests -> python -> godot_agent: это и есть папка аддона, её и копируем.
    addon = Path(__file__).resolve().parent.parent.parent
    project = Path(tempfile.mkdtemp(prefix="updater_bbcode_"))
    results = []
    try:
        (project / "project.godot").write_text(
            'config_version=5\n\n[application]\nconfig/name="bbcode"\n',
            encoding="utf-8")
        # Аддон кладём туда же, куда его кладёт панель: путь в preload должен
        # совпадать с res://-адресом в настоящем проекте.
        target = project / "addons" / "Godot_agent" / "godot_agent"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(addon, target,
                        ignore=shutil.ignore_patterns("python", "*.uid", "dist"))
        output = run_godot(executable, project)
    finally:
        shutil.rmtree(project, ignore_errors=True)

    got = collect(output)
    for index, (md, expected) in enumerate(CASES):
        actual = got.get(index)
        passed = actual == expected
        print("BBCode #%d -> %s" % (index, "OK" if passed else "FAIL"))
        if not passed:
            print("     input:    %r" % md)
            print("     expected: %r" % expected)
            print("     actual:   %r" % actual)
        results.append(passed)

    for marker in FORBIDDEN:
        leaked = [i for i, value in got.items() if marker in value]
        passed = not leaked
        print("нет мусора %r в результате -> %s" % (marker, "OK" if passed else "FAIL"))
        if not passed:
            print("     индексы: %r" % leaked)
        results.append(passed)

    if "Parse Error" in output or "SCRIPT ERROR" in output:
        print("FAIL -> движок сообщил об ошибке скрипта")
        print(output[-2000:])
        results.append(False)

    print("--- ИТОГ test_updater_bbcode_live.py: %d/%d пройдено ---"
          % (sum(1 for r in results if r), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
