"""Фича editing.write_preview: план записи и diff без изменения файлов.

Владелец инструмента `write_preview` — первая механика с `effects="write"`,
хотя в проекте она не пишет ни байта: единственная запись — WAL `PREPARED`
вне проекта (ADR-0005). Применение плана — часть 2 (`editing.write_apply`).
"""

from . import app

__all__ = ["app"]
