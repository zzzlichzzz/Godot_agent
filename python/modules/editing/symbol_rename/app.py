"""modules/editing/symbol_rename/app.py - сценарий вклада: запрос → домен → план.

Своего инструмента у модуля нет (`provides_tools=()`): сценарий зовёт владелец
составного инструмента через реестр (ADR-0004). Правила GDScript — в домене
(`domain/compiler.py`), здесь только порядок «проверить запрос → собрать план»
(R-04); записи нет — только шаги для воронки (R-12).
"""

from .domain.compiler import compile_plan, validate_request


def build_plan(request, texts, mode, allow_unverified, exclude=(), newlines=None):
    """Проверить запрос теми же правилами, что и воронка, и вернуть план."""
    validate_request(request.get("kind"), request.get("old_name"),
                     request.get("new_name"), mode, allow_unverified)
    return compile_plan(request, texts, mode, allow_unverified, exclude, newlines)

