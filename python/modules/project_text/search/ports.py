"""modules/project_text/search/ports.py - порт, нужный этой фиче (ADR-0003).

Только сигнатуры и типы: реализация живёт в `substrate/fs` (диск) и в тестах
(память). Модуль адаптер не импортирует — совпадение структурное, поэтому
`isinstance(adapter, FileSystem)` работает через `runtime_checkable`.
"""

from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class FileSystem(Protocol):
    """Чтение проекта для поиска: обход файлов и текст файла."""

    def list_files(self) -> Sequence[str]:
        """Относительные пути файлов проекта через `/`, в порядке обхода."""

    def read_text(self, rel_path: str) -> str:
        """Текст файла (BOM и кодировку снимает адаптер, переводы строк — домен)."""
