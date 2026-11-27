"""Фича editing.write_apply: применение плана и квитанции (ADR-0005).

Владелец инструмента `write_apply` — единственное место, где агент пишет в
проект. Обратная операция — `editing.rollback` по `entry_id`.
"""

from . import app

__all__ = ["app"]
