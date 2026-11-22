"""modules/code_intel/usages/ports.py - порт, нужный этой фиче (ADR-0003).

Индексу нужны две операции: обойти файлы проекта и прочитать текст одного
файла. Реализация — `substrate/fs` (диск) и память в тестах; модуль адаптер не
импортирует, совпадение структурное (`runtime_checkable`).
"""

from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class ProjectFiles(Protocol):
    """Чтение проекта для индекса символов."""

    def list_files(self) -> Sequence[str]:
        """Относительные пути файлов проекта через `/`, в порядке обхода."""

    def read_text(self, rel_path: str) -> str:
        """Текст файла (BOM и кодировку снимает адаптер)."""
