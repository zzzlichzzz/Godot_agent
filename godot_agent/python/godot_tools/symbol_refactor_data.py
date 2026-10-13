# -*- coding: utf-8 -*-

"""symbol_refactor_data — часть python/godot_tools/symbol_refactor.py (вынесено split_refactor).

Фасад и точка входа — python/godot_tools/symbol_refactor.py: он реэкспортирует имена модуля.
"""

_KEYWORDS = {
    "and", "as", "assert", "await", "break", "breakpoint", "class",
    "class_name", "const", "continue", "elif", "else", "enum", "extends",
    "for", "func", "if", "in", "is", "match", "not", "or", "pass",
    "preload", "return", "self", "signal", "static", "super", "var", "while",
}

# Все виды объявлений, которые парсер вообще отдаёт: нужны для подсказки
# в сообщении об ошибке («что этот скрипт объявляет на самом деле»).
_DECL_KINDS = {"class_name", "class", "function", "signal", "variable",
               "constant", "enum", "enum_member", "parameter"}
