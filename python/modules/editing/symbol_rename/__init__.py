"""Фича editing.symbol_rename: компилятор правок символа (без своего инструмента).

Публичное API для соседей (R-11): чужой `domain/` не импортируется, только фасад.
В этом срезе здесь только план (`DRAFT → PREPARED`); применение плана появится в
`editing.write_apply` (часть 2), откат — в `editing.rollback` (ADR-0005).
"""

from ..shared.operation_compiler import OperationCompiler
from . import app
from .domain.compiler import compile_plan, validate_request

#: Вклад в чужие составные инструменты (ADR-0004): операция и её компилятор.
COMPILER = OperationCompiler(op="symbol_rename", compile=compile_plan)
CONTRIBUTIONS = (COMPILER,)

__all__ = ["COMPILER", "CONTRIBUTIONS", "compile_plan",
           "validate_request"]
