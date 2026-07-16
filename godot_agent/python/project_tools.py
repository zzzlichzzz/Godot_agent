import os

EXCLUDED_DIRS = {'.godot', '.import', '.git', '.venv', '__pycache__', 'node_modules', '.vs', '.vscode'}
EXCLUDED_FILES = {'.DS_Store'}


def build_project_tree(project_root, max_depth=8):
    """Строит текстовое дерево файлов проекта (без содержимого) —
    отправляется модели ОДИН раз при инициализации сессии."""
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
    """
    Превращает res://путь (или относительный путь) в абсолютный и
    проверяет, что он НЕ выходит за пределы project_root.
    Это защита от path traversal — модель в теории может предложить
    путь вроде "res://../../../etc/passwd" или содержащий "..", и без
    этой проверки мы бы читали/писали файлы вне проекта.
    """
    rel = godot_path[len('res://'):] if godot_path.startswith('res://') else godot_path
    project_root_abs = os.path.abspath(project_root)
    abs_path = os.path.abspath(os.path.join(project_root_abs, rel))

    if abs_path != project_root_abs and not abs_path.startswith(project_root_abs + os.sep):
        raise ValueError(f"Путь вне проекта, отклонено: {godot_path}")

    return abs_path


def read_project_file(project_root, godot_path, max_chars=50000):
    abs_path = _resolve_safe_path(project_root, godot_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Файл не найден: {godot_path}")

    with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]

    return content, truncated


def write_project_file(project_root, godot_path, content):
    abs_path = _resolve_safe_path(project_root, godot_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write(content)
