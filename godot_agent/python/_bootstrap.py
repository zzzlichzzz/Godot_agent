# -*- coding: utf-8 -*-
"""Настройка путей для плоских импортов (import ai_parser, import sites и т.д.).

Модули разложены по подпапкам (parsers/, browser/, godot_tools/, server/),
но продолжают импортироваться по старым коротким именам — это нужно:
  * всем существующим import-строкам в коде,
  * динамической загрузке парсеров через importlib в sites.py,
  * hidden-imports в PyInstaller-сборке.

Просто импортируйте этот модуль первым: import _bootstrap
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PACKAGE_DIRS = ("parsers", "browser", "godot_tools", "server")

for _d in (_HERE,) + tuple(os.path.join(_HERE, d) for d in _PACKAGE_DIRS):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.insert(0, _d)
