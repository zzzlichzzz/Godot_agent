# -*- coding: utf-8 -*-
"""Синтетические тесты: опрос статуса mini-lich НЕ должен запускать обучение.

Баг (репорт: «после нажатия „Обновить справочник API Godot“ в логах сервера
началось обучение нейросети»): minilich.status() «самолечился» — при
enabled=True и неактивном потоке сам звал start_training(). Статус опрашивают
эндпоинты, не имеющие отношения к управлению обучением:
  * POST /minilich/status — панель шлёт его при КАЖДОМ открытии настроек
    (а кнопка «Обновить справочник API» живёт именно в этом диалоге);
  * GET  /dashboard/data  — открытая страница дашборда опрашивает его сама.
Итог: любой взгляд в настройки молча включал CPU-тяжёлое фоновое обучение,
хотя секция mini-lich в UI скрыта (exp_box.visible = false) и пользователь
даже не видит галочку, которая это разрешает.

Контракт после фикса: status() — ЧИСТОЕ чтение. Запуск обучения остаётся
только явным действием (POST /minilich/set с enabled=true).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import minilich  # noqa: E402
from minilich import ml_data  # noqa: E402

try:
    from minilich import ml_train  # noqa: E402
    _NUMPY_OK = True
except Exception:
    ml_train = None
    _NUMPY_OK = False


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ml_status_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
        # «Мозг» во временной папке вместо реальной папки аддона.
        self.addon = Path(self.temp.name, "addon")
        self.addon.mkdir()
        self.addCleanup(ml_data.set_storage_base, None, None)
        ml_data.set_storage_base(str(self.addon), str(self.root))
        self.brain = Path(ml_data.storage_dir(str(self.root)))
        self._write_settings({"enabled": True})

    def _write_settings(self, data):
        (self.brain / "settings.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")


class StatusIsReadOnly(_Fixture):
    """Статус — чтение, а не скрытый пульт управления обучением."""

    def test_status_poll_does_not_start_training(self):
        if not _NUMPY_OK:
            self.skipTest("numpy/ml_train недоступны — самолечение в этом окружении не воспроизводится")
        with mock.patch.object(minilich, "start_training",
                               return_value=True) as started:
            out = minilich.status(str(self.root), str(self.addon))
        self.assertEqual(started.call_count, 0,
                         "опрос статуса запустил фоновое обучение (репорт: открытие "
                         "настроек с кнопкой «Обновить справочник API» включало обучение)")
        self.assertTrue(out["enabled"])
        self.assertFalse(out["training_active"])

    def test_status_reports_active_training_without_restarting_it(self):
        if not _NUMPY_OK:
            self.skipTest("numpy/ml_train недоступны")
        with mock.patch.object(ml_train, "training_state",
                               return_value={"active": True, "lines": ["[x] уже учится"],
                                             "last_error": "", "exam": "", "marathon": ""}), \
                mock.patch.object(minilich, "start_training",
                                  return_value=True) as started:
            out = minilich.status(str(self.root), str(self.addon))
        self.assertEqual(started.call_count, 0)
        self.assertTrue(out["training_active"])
        self.assertEqual(out["lines"], ["[x] уже учится"])

    def test_status_with_disabled_setting_never_touches_training(self):
        self._write_settings({"enabled": False})
        with mock.patch.object(minilich, "start_training",
                               return_value=True) as started:
            out = minilich.status(str(self.root), str(self.addon))
        self.assertEqual(started.call_count, 0)
        self.assertFalse(out["enabled"])

    def test_explicit_set_enabled_still_starts_training_elsewhere(self):
        """Явный запуск не пострадал: это делает только /minilich/set (main.py).

        Здесь закрепляем, что сам по себе set_enabled не пинает поток — запуск
        остаётся в обработчике маршрута, а не в статусе."""
        with mock.patch.object(minilich, "start_training",
                               return_value=True) as started:
            minilich.set_enabled(str(self.root), True)
        self.assertEqual(started.call_count, 0)

    def test_routes_start_training_only_in_explicit_set_handler(self):
        """Сторож проводки: start_training не должен снова появиться в
        читающих маршрутах (/minilich/status, /dashboard/data)."""
        main_py = Path(__file__).resolve().parents[1] / "main.py"
        src = main_py.read_text(encoding="utf-8")
        self.assertEqual(src.count("minilich.start_training("), 1,
                         "start_training вызван не только из /minilich/set")
        set_pos = src.index("def minilich_set(")
        call_pos = src.index("minilich.start_training(")
        next_def = src.index("def minilich_github_fetch(")
        self.assertTrue(set_pos < call_pos < next_def,
                        "вызов start_training уехал за пределы обработчика /minilich/set")


if __name__ == "__main__":
    unittest.main()
