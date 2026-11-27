"""modules/editing/symbol_rename/tools.py - дескрипторы и вклады модуля.

Своего `ToolSpec` у модуля нет (`TOOLS = ()`): он не публикует имя, а реализует
часть чужого инструмента. Вклады отдаются реестру через `CONTRIBUTIONS` (ADR-0004),
чтобы владелец (`editing.write_preview`) не импортировал чужой модуль.
Правила: R-05, R-11, R-12.
"""

from . import COMPILER

TOOLS = ()

CONTRIBUTIONS = (COMPILER,)

