# -*- coding: utf-8 -*-
"""Обход проекта не открывает handle на каждую запись файловой системы.

Регрессия 0.8.11: фильтр доступа классифицировал каждую запись несколько раз,
и каждый раз через ``os.path.realpath`` (на Windows — ``GetFinalPathNameByHandle``).
На проекте в 6.5 тыс. записей это давало 43 844 системных вызова, и поиск
редкого символа занимал 2.7 с вместо 25 мс (у частого шаблона срабатывал
ранний выход по квоте и регрессия маскировалась).

Тесты держат два инварианта правки: решения политики остаются теми же, что у
публичного ``classify_project_path``, а число ``realpath`` не растёт линейно по
числу записей обхода. Плюс проверяется, что junction (для ``os.walk`` это
обычный каталог) не открывает доступ ни наружу проекта, ни в ``addons``.
"""
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import project_tools


def _write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _make_project(root, files=120):
    _write(root, "project.godot", "config_version=5\n")
    _write(root, "src/game.gd", "extends Node\n\nvar NEEDLE = 1\n")
    _write(root, "addons/demo/demo.gd", "extends Node\n")
    _write(root, "addons/Godot_agent/godot_agent/agent_entry.gd", "extends Node\n")
    _write(root, "addons/Godot_agent/plugin.cfg", "[plugin]\n")
    _write(root, ".agent_history/log.json", "{}\n")
    _write(root, "minilich_brain/project_index.json", "{}\n")
    _write(root, ".godot/uid_cache.bin", "x\n")
    _write(root, "__pycache__/mod.cpython-314.pyc", "x\n")
    for index in range(files):
        _write(root, "src/part%02d/file%03d.gd" % (index % 12, index),
               "extends Node\n\nfunc f%d():\n\tpass\n" % index)


def _make_junction(link, target):
    if os.path.exists(link):
        return False
    done = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                          capture_output=True)
    return done.returncode == 0 and os.path.exists(link)


class ScanPolicyContextParity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scan_policy_")
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        _make_project(self.root)
        self.addon = os.path.join(
            self.root, "addons", "Godot_agent", "godot_agent")

    def test_context_classification_matches_public_classifier(self):
        ctx = project_tools._ScanPolicyContext(self.root, self.addon)
        seen = 0
        for dirpath, dirnames, filenames in os.walk(self.root):
            for name in list(dirnames) + list(filenames):
                entry = ctx.lookup(dirpath, name, name in dirnames)
                self.assertIsNotNone(
                    entry, "контекст потерял запись %s" % name)
                fast = ctx.classify(entry[0], entry[1], entry[2])
                slow = project_tools.classify_project_path(
                    entry[0], self.root, self.addon)
                self.assertEqual(fast, slow, "расхождение для %s" % entry[0])
                seen += 1
        self.assertGreater(seen, 100)

    def test_policy_decisions_unchanged(self):
        addon = self.addon
        combos = ((False, False), (True, False), (False, True), (True, True))
        matrix = (
            # путь, ожидаемые (чтение, запись) для каждой комбинации флагов:
            # addons/self = (выкл,выкл), (вкл,выкл), (выкл,вкл), (вкл,вкл)
            ("res://src/game.gd", ((True, True),) * 4),
            ("res://project.godot", ((True, False),) * 4),
            ("res://addons/demo/demo.gd",
             ((False, False), (True, True), (False, False), (True, True))),
            ("res://addons/Godot_agent/plugin.cfg",
             ((False, False), (True, True), (False, False), (True, True))),
            ("res://addons/Godot_agent/godot_agent/agent_entry.gd",
             ((False, False), (False, False), (True, True), (True, True))),
            ("res://.agent_history/log.json", ((False, False),) * 4),
            ("res://minilich_brain/project_index.json", ((True, True),) * 4),
            ("res://.godot/uid_cache.bin", ((True, True),) * 4),
            ("res://../outside.txt", ((False, False),) * 4),
        )
        for path, expected in matrix:
            for (allow_addons, allow_self_edit), (read, write) in zip(
                    combos, expected):
                note = "%s при addons=%s self=%s" % (
                    path, allow_addons, allow_self_edit)
                self.assertEqual(
                    project_tools.can_read_project_path(
                        path, self.root, allow_addons, allow_self_edit, addon),
                    read, "чтение " + note)
                self.assertEqual(
                    project_tools.can_write_project_path(
                        path, self.root, allow_addons, allow_self_edit, addon),
                    write, "запись " + note)

    def test_walk_does_not_canonicalise_every_entry(self):
        original = os.path.realpath
        calls = []

        def counting(path, *args, **kwargs):
            calls.append(path)
            return original(path, *args, **kwargs)

        directories = 0
        for _dirpath, dirnames, _filenames in os.walk(self.root):
            directories += 1
        with patch.object(os.path, "realpath", counting):
            snapshot = project_tools.snapshot_files(self.root)
        self.assertGreaterEqual(
            len(snapshot), 100, "обход не прошёл по всему проекту")
        self.assertLessEqual(
            len(calls), 2 * directories + 20,
            "обход канонизирует каждую запись: %d realpath на %d каталогов"
            % (len(calls), directories))


class ScanPolicyReparsePoints(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scan_reparse_")
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        _make_project(self.root, files=4)
        self.outside = tempfile.mkdtemp(prefix="scan_outside_")
        self.addCleanup(shutil.rmtree, self.outside, True)
        with open(os.path.join(self.outside, "secret.gd"), "w",
                  encoding="utf-8", newline="\n") as handle:
            handle.write("OUTSIDE_TOKEN\n")

    def test_junction_outside_project_is_not_traversed(self):
        link = os.path.join(self.root, "link_out")
        if not _make_junction(link, self.outside):
            self.skipTest("junction недоступен в этой среде")
        rows, _truncated = project_tools.search_project_text(
            self.root, "OUTSIDE_TOKEN", max_results=5, context_lines=0)
        self.assertEqual(rows, [], "содержимое за junction наружу попало в выдачу")
        self.assertFalse(project_tools.can_read_project_path(
            "res://link_out/secret.gd", self.root, False, False, None))

    def test_junction_into_addons_keeps_addon_policy(self):
        link = os.path.join(self.root, "link_addons")
        if not _make_junction(link, os.path.join(self.root, "addons")):
            self.skipTest("junction недоступен в этой среде")
        rows, _truncated = project_tools.search_project_text(
            self.root, "extends", max_results=50, context_lines=0)
        leaked = [row for row in rows if "link_addons" in json.dumps(row)]
        self.assertEqual(leaked, [], "addons отдались через junction-ссылку")
        self.assertTrue(rows, "поиск по проекту не дал ни одной строки")

    def test_junction_into_project_keeps_content_readable(self):
        link = os.path.join(self.root, "link_src")
        if not _make_junction(link, os.path.join(self.root, "src")):
            self.skipTest("junction недоступен в этой среде")
        rows, _truncated = project_tools.search_project_text(
            self.root, "NEEDLE", max_results=5, context_lines=0)
        self.assertTrue(rows, "содержимое за junction внутрь проекта потерялось")
        self.assertTrue(project_tools.can_read_project_path(
            "res://link_src/game.gd", self.root, False, False, None))


if __name__ == "__main__":
    unittest.main()
