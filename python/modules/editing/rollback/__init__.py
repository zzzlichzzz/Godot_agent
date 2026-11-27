"""Фича editing.rollback: откат по квитанциям и recovery (ADR-0005).

Публичная точка входа recovery — `recover(ports)`: её вызывает композиционный
корень на старте, чтобы `APPLYING` после падения не остался «полуприменённым».
"""

from . import app
from .recovery import recover

__all__ = ["app", "recover"]
