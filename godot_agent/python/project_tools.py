import os

EXCLUDED_DIRS = {'.godot', '.import', '.git', '.venv', '__pycache__', 'node_modules', '.vs', '.vscode'}
EXCLUDED_FILES = {'.DS_Store'}


def build_project_tree(project_root, max_depth=8):
    """
    Строит текстовое дерево файлов проекта (без содержимого) —
    отправляется модели ОДИН раз при инициализации сессии.
    """
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
    """Создает новый файл. Если файл уже существует — возвращает ошибку."""
    abs_path = _resolve_safe_path(project_root, godot_path)
    if os.path.exists(abs_path):
        raise FileExistsError(f"Файл уже существует: {godot_path}")
    
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write(content)


def patch_project_file(project_root, godot_path, search_code, replace_code):
    """
    Находит уникальный блок кода (search_code) и заменяет его на (replace_code).
    Автоматически делает резервную копию .bak перед операцией.
    """
    abs_path = _resolve_safe_path(project_root, godot_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Файл для изменения не найден: {godot_path}")

    with open(abs_path, 'r', encoding='utf-8') as f:
        original_content = f.read()

    # Унифицируем переносы строк (\r\n -> \n) для надежного сравнения блоков
    content = original_content.replace('\r\n', '\n')
    search_norm = search_code.replace('\r\n', '\n').strip()
    replace_norm = replace_code.replace('\r\n', '\n')

    occurrences = content.count(search_norm)
    if occurrences == 0:
        raise ValueError("Ошибка: Не удалось найти указанный блок кода в файле.")
    if occurrences > 1:
        raise ValueError("Ошибка: Этот блок кода встречается в файле несколько раз. Замена отменена во избежание ошибок.")

    # Создаем бэкап перед изменением
    backup_path = abs_path + ".bak"
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(original_content)

    # Применяем патч
    new_content = content.replace(search_norm, replace_norm)
    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write(new_content)