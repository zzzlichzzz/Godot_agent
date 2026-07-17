import os
import shutil

EXCLUDED_DIRS = {'.godot', '.import', '.git', '.venv', '__pycache__',
                 'node_modules', '.vs', '.vscode', '.agent_history'}
EXCLUDED_FILES = {'.DS_Store'}

HISTORY_DIR_NAME = ".agent_history"


def build_project_tree(project_root, max_depth=8):
    """Строит текстовое дерево файлов проекта для контекста ИИ."""
    project_root = os.path.abspath(project_root)
    lines = []
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith('.'))
        rel = os.path.relpath(dirpath, project_root)
        depth = 0 if rel == '.' else rel.count(os.sep) + 1
        if depth > max_depth:
            dirnames[:] = []
            continue
        indent = '  ' * depth
        if rel != '.':
            lines.append(f"{indent}{os.path.basename(dirpath)}/")
        for f in sorted(filenames):
            if f in EXCLUDED_FILES:
                continue
            lines.append(f"{indent}  {f}")
    return '\n'.join(lines)


def _resolve_safe_path(project_root, godot_path):
    """Защита от Path Traversal — не дает ИИ выйти за рамки проекта."""
    rel = godot_path[len('res://'):] if godot_path.startswith('res://') else godot_path
    project_root_abs = os.path.abspath(project_root)
    abs_path = os.path.abspath(os.path.join(project_root_abs, rel))
    if abs_path != project_root_abs and not abs_path.startswith(project_root_abs + os.sep):
        raise ValueError(f"Путь вне проекта отклонен: {godot_path}")
    # Служебная папка истории агента недоступна для чтения/записи через действия.
    rel_norm = os.path.relpath(abs_path, project_root_abs).replace(os.sep, '/')
    if rel_norm == HISTORY_DIR_NAME or rel_norm.startswith(HISTORY_DIR_NAME + '/'):
        raise ValueError("Доступ к служебной папке истории запрещён.")
    return abs_path


def read_project_file(project_root, godot_path, max_chars=50000):
    """Читает содержимое файла проекта."""
    abs_path = _resolve_safe_path(project_root, godot_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Файл не найден: {godot_path}")
    with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    truncated = len(content) > max_chars
    return content[:max_chars], truncated


def create_project_file(project_root, godot_path, content):
    """Создает новый файл. Если файл существует — возвращает ошибку."""
    abs_path = _resolve_safe_path(project_root, godot_path)
    if os.path.exists(abs_path):
        raise FileExistsError(f"Файл уже существует: {godot_path}")
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    # newline='\n': пишем LF, как это делает сам редактор Godot. Иначе на Windows
    # Python записал бы CRLF, а пересохранение файла в Godot меняло бы
    # каждый перенос строки — и откат ложно считал бы файл "изменённым".
    with open(abs_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content.replace('\r\n', '\n'))


def patch_project_file(project_root, godot_path, search_code, replace_code):
    """Точечный патч кода. Резервная копия теперь хранится в журнале
    изменений (.agent_history) — см. history_manager.py."""
    abs_path = _resolve_safe_path(project_root, godot_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Файл не найден: {godot_path}")
    with open(abs_path, 'r', encoding='utf-8') as f:
        original_content = f.read()
    content = original_content.replace('\r\n', '\n')
    search_norm = search_code.replace('\r\n', '\n')
    replace_norm = replace_code.replace('\r\n', '\n')
    occurrences = content.count(search_norm)
    if occurrences == 0:
        raise ValueError("Ошибка: Указанный старый блок кода не найден в файле.")
    if occurrences > 1:
        raise ValueError("Ошибка: Блок кода не уникален (встречается несколько раз).")
    new_content = content.replace(search_norm, replace_norm)
    # LF как в Godot (см. комментарий в create_project_file).
    with open(abs_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_content)


def move_project_file(project_root, source_godot_path, dest_godot_path):
    """Перемещает или переименовывает файл, создавая папки при необходимости."""
    abs_source = _resolve_safe_path(project_root, source_godot_path)
    abs_dest = _resolve_safe_path(project_root, dest_godot_path)
    if not os.path.isfile(abs_source):
        raise FileNotFoundError(f"Исходный файл не найден: {source_godot_path}")
    if os.path.exists(abs_dest):
        raise FileExistsError(f"Файл в месте назначения уже существует: {dest_godot_path}")
    os.makedirs(os.path.dirname(abs_dest), exist_ok=True)
    shutil.move(abs_source, abs_dest)
