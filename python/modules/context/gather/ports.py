"""modules/context/gather/ports.py - порт, нужный этой фиче (ADR-0003).

Только сигнатуры: реализация живёт в `substrate/fs` (диск) и в тестах (память).
Модуль адаптер не импортирует — совпадение структурное (`runtime_checkable`).

Пакету контекста нужен не обход проекта, а два факта: есть ли `project.godot`
(`read_text`) и что за файлы в проекте (`list_files`) — этого достаточно, чтобы
не заводить «свой файловый интерфейс».
"""

from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class FileSystem(Protocol):
    """Чтение проекта для секций контекста."""

    def list_files(self) -> Sequence[str]:
        """Относительные пути файлов проекта через `/`."""

    def read_text(self, rel_path: str) -> str:
        """Текст файла (кодировку и BOM снимает адаптер)."""
