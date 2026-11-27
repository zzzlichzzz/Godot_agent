"""modules/context/editor_context/tools.py - дескрипторы и вклады модуля.

Своего `ToolSpec` у модуля нет (`TOOLS = ()`): снимок редактора - секция пакета
`context`, а не отдельный инструмент (ADR-0004), поэтому `contract/capabilities`
для него не создаётся. Вклад отдаётся реестру через `CONTRIBUTIONS`, а порт
`editor` связывает композиция (`app.EditorSection.bind`), так что ни схем, ни
доступа к контексту здесь нет. Правила: R-05 (эффекты и стоимость - в
дескрипторе), R-15 (типизированные ошибки - в домене и приложении).
"""

from .app import SECTION

#: Инструментов нет: секция приходит вкладом, а не как `ToolSpec`.
TOOLS = ()

#: Вклад в секцию `context` (владелец инструмента - `context.gather`).
CONTRIBUTIONS = (SECTION,)

