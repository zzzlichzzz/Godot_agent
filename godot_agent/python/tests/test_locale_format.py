# -*- coding: utf-8 -*-
"""Связка «словарь переводов ↔ места форматирования» в GDScript-панели.

Зачем этот тест. Строка вида

    panel._view.add_system(panel._t("log_auto_ok") % log_info)

в рантайме падает с «not all arguments converted during string formatting in
operator '%'», если в переводе ключа нет плейсхолдера, а панель подставила
аргумент. Падает она в редакторе Godot: в user://logs/godot.log (лог запуска
игры) такое не попадает, gd_lint синтаксис видит корректным, а headless-запуск
панель не исполняет. То есть до агента ошибка доходит только от человека —
ровно так она один раз и «просочилась» в проект.

Здесь она ловится до запуска, на разборе текста:
  * наборы ключей RU и EN совпадают;
  * число плейсхолдеров у одного ключа в RU и EN совпадает;
  * каждый ключ, к которому обращаются как _t("ключ"), есть в словарях;
  * на каждом сайте _t("ключ") % <аргумент> число аргументов равно числу
    плейсхолдеров (у литерального массива считаются элементы, висячая
    запятая не считается);
  * словарь подключается через preload("agent_locale.gd"): тогда он не может
    оказаться null, _t() не может вернуть голый ключ, и форматирование «%»
    на нём невозможно.
"""
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

ADDON_DIR = Path(__file__).resolve().parents[2]
LOCALE_PATH = ADDON_DIR / "agent_locale.gd"
PRELOADED_SCRIPTS = ("agent_panel_part1.gd", "agent_chat_view.gd", "agent_start_screen.gd")

_ENTRY = re.compile(r'^\t"((?:[^"\\]|\\.)*)"\s*:\s*"(.*)$')
_DICT_START = re.compile(r"const (RU|EN) := \{")
# Плейсхолдер GDScript: %s %d %.2f %-5s и т.п. «%%» — литеральный процент,
# поэтому он вырезается заранее и вербом не считается.
_VERB = re.compile(r"%(?:%|[-+ 0#]*\d*(?:\.\d+)?[sdfxXocveEgbBoOtTuU])")
_REF = re.compile(r'_t\("([A-Za-z0-9_]+)"\)')
_SITE = re.compile(r'_t\("([A-Za-z0-9_]+)"\)\s*%')
_OPEN = "[({"
_CLOSE = "])}"
_SKIP_DIRS = {".godot", "dist", "__pycache__", ".git"}


def parse_locale(path=LOCALE_PATH):
    """Разобрать словари RU и EN в словарь {язык: {ключ: значение}}."""
    dicts = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _DICT_START.match(line)
        if m:
            current = m.group(1)
            dicts[current] = {}
            continue
        if current is not None and line.strip() == "}":
            current = None
            continue
        if current is None:
            continue
        m = _ENTRY.match(line)
        if m:
            dicts[current][m.group(1)] = m.group(2)
    return dicts


def placeholders(value):
    """Сколько аргументов ждёт строка формата («%%» — не аргумент)."""
    return len([m for m in _VERB.finditer(value) if m.group(0) != "%%"])


def gd_files():
    for path in sorted(ADDON_DIR.rglob("*.gd")):
        if _SKIP_DIRS & {part.lower() for part in path.parts}:
            continue
        yield path


def _skip_string(text, i):
    quote = text[i]
    i += 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return i


def format_arg(text, pos):
    """Выражение-аргумент сразу после оператора % (может тянуться на строки)."""
    depth = 0
    out = []
    i = pos
    while i < len(text):
        ch = text[i]
        if ch in "\"'":
            j = _skip_string(text, i)
            out.append(text[i:j])
            i = j
            continue
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            if depth == 0:
                break
            depth -= 1
        elif ch == "\n" and depth == 0:
            break
        out.append(ch)
        i += 1
    return "".join(out).strip()


def count_args(arg):
    """Сколько аргументов реально передано: скаляр — один, [..] — элементы."""
    if arg == "":
        return 0
    if not arg.startswith("["):
        return 1
    inner = arg[1:-1] if arg.endswith("]") else arg[1:]
    parts, depth, cur, i = [], 0, [], 0
    while i < len(inner):
        ch = inner[i]
        if ch in "\"'":
            j = _skip_string(inner, i)
            cur.append(inner[i:j])
            i = j
            continue
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return len([part for part in parts if part.strip()])


class LocaleFormatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dicts = parse_locale()
        cls.files = {path: path.read_text(encoding="utf-8") for path in gd_files()}

    @staticmethod
    def _rel(path):
        return os.path.relpath(str(path), str(ADDON_DIR))

    @staticmethod
    def _line(text, pos):
        return text.count("\n", 0, pos) + 1

    def test_dictionaries_have_same_keys(self):
        ru, en = set(self.dicts["RU"]), set(self.dicts["EN"])
        self.assertEqual(sorted(ru - en), [], "ключи есть в RU, но не в EN")
        self.assertEqual(sorted(en - ru), [], "ключи есть в EN, но не в RU")

    def test_dictionaries_have_same_placeholders(self):
        bad = []
        for key in sorted(set(self.dicts["RU"]) & set(self.dicts["EN"])):
            want = placeholders(self.dicts["RU"][key])
            got = placeholders(self.dicts["EN"][key])
            if want != got:
                bad.append("%s: RU=%d EN=%d" % (key, want, got))
        self.assertEqual(bad, [], "число плейсхолдеров расходится между RU и EN")

    def test_used_keys_exist(self):
        missing = set()
        for path, text in self.files.items():
            for m in _REF.finditer(text):
                key = m.group(1)
                if key not in self.dicts["RU"] and key not in self.dicts["EN"]:
                    missing.add("%s:%d %s" % (self._rel(path), self._line(text, m.start()), key))
        self.assertEqual(sorted(missing), [],
                         "ключ используется в .gd, но его нет ни в RU, ни в EN")

    def test_format_arguments_match_placeholders(self):
        problems = []
        for path, text in self.files.items():
            for m in _SITE.finditer(text):
                key = m.group(1)
                if key not in self.dicts["RU"] and key not in self.dicts["EN"]:
                    continue  # о таком ключе уже говорит test_used_keys_exist
                have = count_args(format_arg(text, m.end()))
                value = self.dicts["RU"].get(key, self.dicts["EN"].get(key, ""))
                want = placeholders(value)
                if want != have:
                    problems.append("%s:%d %s — плейсхолдеров %d, аргументов %d"
                                    % (self._rel(path), self._line(text, m.start()),
                                       key, want, have))
        self.assertEqual(problems, [],
                         "вызов вида _t(\"ключ\") % аргумент упадёт в рантайме с "
                         "«not all arguments converted during string formatting»: "
                         "число аргументов не совпало с числом %-плейсхолдеров")

    def test_locale_is_preloaded(self):
        for name in PRELOADED_SCRIPTS:
            text = (ADDON_DIR / name).read_text(encoding="utf-8")
            self.assertIn('preload("agent_locale.gd")', text,
                          "%s должен подключать словарь через preload: иначе при "
                          "сбое load() локаль станет null, _t() вернёт голый ключ "
                          "и форматирование «%%» упадёт" % name)
            self.assertNotIn("load(lp)", text,
                             "%s не должен вычислять путь к словарю через load(): "
                             "сбой возвращает null молча" % name)


if __name__ == "__main__":
    unittest.main()
