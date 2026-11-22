"""modules/code_intel/functions/ports.py - порт, нужный этой фиче (ADR-0003).

Одна операция: текст файла по относительному пути. Реализация — `substrate/fs/`
(диск) и память в тестах; модуль адаптер не импортирует, совпадение структурное,
поэтому `isinstance(adapter, TextReader)` работает через `runtime_checkable`.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class TextReader(Protocol):
    """Чтение текста одного файла проекта."""

    def read_text(self, rel_path: str) -> str:
        """Текст файла (BOM и кодировку снимает адаптер, переводы строк — домен)."""
