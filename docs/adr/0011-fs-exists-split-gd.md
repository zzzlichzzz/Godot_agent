# ADR-0011. fs.exists — узкий metadata-шов для split_gd

Статус: решение разрешено пользователем, 2026-10-31 (§9 C.15); приёмка C.15 отдельно.

## Контекст

Actual-old plan_split:1001 проверяет os.path.exists(module_rel): файл и каталог
занимают целевой путь. Принятый fs.is_file видит только обычный файл, list_files
возвращает только файлы, read_raw каталога даёт PermissionError. Преобразовывать
этот отказ в «занят» нельзя: PermissionError обязан оставаться denied. Пустой
каталог module.gd поэтому требует отдельного метаданного булева признака.

## Решение

Добавить exists(rel_path: str) -> bool в DiskFileSystem и consumer-owned FileSystem
editing.split_gd. Единственный production-вызов — проверка целевого module_rel
в оркестрации plan_split. True для файла или каталога даёт AppError invalid_input
с дословным «целевой модуль уже существует: <rel>». Никаких чтения/записи/запуска
Godot, новых режимов ФС, is_dir/stat/mkdir/glob/walk или нового binding.

_resolve возвращает str, не Path. Пользователь отдельно подтвердил эквивалентную
строку return os.path.exists(self._resolve(rel_path)); os уже импортирован.
_resolve и проверки containment, is_file/list_files/read_text/read_raw/конструктор
остаются байт-в-байт. PathPolicy/bootstrap/runtime/kernel не меняются.

## Следствия и доказательства

Сначала новый тест реального каталога module.gd: exists True, is_file False,
дерево неизменно; до метода — красный AttributeError. Затем отдельная мутация
exists -> is_file обязана восстановить исходный дефект и покраснить этот тест
и корпусный existing_module_dir. existing_module_file/dir снимаются actual-old.
Один вызов по python/modules и обратная byte-проекция проверяются в конце C.15.
Старый disk_fs: 3628 B, SHA256
8d2eec86bc9cfaa3459a7579bf998f8935236207df904dc593f75e5fa7c4c1b2;
новый хэш и красные логи записываются в лист/WORKLOG. MemoryFileSystem вне среза.
