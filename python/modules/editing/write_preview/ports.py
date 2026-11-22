"""modules/editing/write_preview/ports.py - порты модуля (ADR-0003, R-12).

Порты объявляет модуль, адаптеры приносит `runtime/bootstrap.py`:

- `fs` — `ProjectFiles`: чтение проекта — `list_files`, `read_text`
  (нормализованный текст: `\r\n` и `\r` → `\n`, BOM снят) и `read_raw`
  (байты как есть). Два чтения нужны потому, что стиль переводов строк и хеш
  файла «до правки» нельзя восстановить из текста: universal newlines их
  скрывают (этот дефект поймал аудит среза). Записи в интерфейсе нет вообще:
  предпросмотр не может изменить проект.
- `journal` — WAL планов (`write_prepared(plan, detail)`, `read(plan_id)`,
  `path(plan_id)`). Реализация — `substrate/store/journal.py`: один JSONL-файл
  на план в каталоге состояния профиля, вне проекта.
"""


class ProjectFiles(object):
    """Только чтение: интерфейс намеренно уже, чем у файловой системы."""

    def list_files(self):
        raise NotImplementedError

    def read_text(self, rel):
        raise NotImplementedError

    def read_raw(self, rel):
        raise NotImplementedError


class PlanJournal(object):
    """Журнал планов: PREPARED пишется до ответа, читается частью 2."""

    def write_prepared(self, plan, detail=None):
        raise NotImplementedError

    def read(self, plan_id):
        raise NotImplementedError

    def path(self, plan_id):
        raise NotImplementedError
