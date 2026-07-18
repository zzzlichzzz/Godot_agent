import os
import shutil

EXCLUDED_DIRS = {'.godot', '.import', '.git', '.venv', '__pycache__',
                 'node_modules', '.vs', '.vscode', '.agent_history'}
EXCLUDED_FILES = {'.DS_Store'}

HISTORY_DIR_NAME = ".agent_history"


def build_project_tree(project_root, max_depth=8, only_exts=None, max_entries=None):
    """Строит текстовое дерево файлов проекта для контекста ИИ."""
    project_root = os.path.abspath(project_root)
    lines = []
    count = 0
    truncated = False
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
            if only_exts is not None and os.path.splitext(f)[1].lower() not in only_exts:
                continue
            if max_entries is not None and count >= max_entries:
                truncated = True
                break
            lines.append(f"{indent}  {f}")
            count += 1
        if truncated:
            break
    if truncated:
        lines.append("  ... (список обрезан; используй действие list_files для полного дерева)")
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
    """Создаёт файл (и папки на пути к нему). Если файл уже существует —
    ПОЛНОСТЬЮ перезаписывает его. Это безопасно: record_change снимает
    снапшот старой версии ДО вызова этой функции, и откат вернёт её.
    Возвращает True, если файл существовал и был перезаписан."""
    abs_path = _resolve_safe_path(project_root, godot_path)
    if os.path.isdir(abs_path):
        raise IsADirectoryError(f"По этому пути находится папка: {godot_path}")
    existed = os.path.isfile(abs_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    # newline='\n': пишем LF, как это делает сам редактор Godot. Иначе на Windows
    # Python записал бы CRLF, а пересохранение файла в Godot меняло бы
    # каждый перенос строки — и откат ложно считал бы файл "изменённым".
    with open(abs_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content.replace('\r\n', '\n'))
    return existed


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
    # Godot хранит уникальный идентификатор ресурса в соседнем *.uid —
    # переносим его тоже, иначе ссылки на файл в проекте могут сломаться.
    if os.path.exists(abs_source + ".uid") and not os.path.exists(abs_dest + ".uid"):
        try:
            shutil.move(abs_source + ".uid", abs_dest + ".uid")
        except OSError:
            pass


def copy_project_file(project_root, source_godot_path, dest_godot_path):
    """Копирует файл ВНУТРИ проекта (res://) как есть (байты сохраняются).
    Не перезаписывает существующий файл — как и create_project_file."""
    abs_source = _resolve_safe_path(project_root, source_godot_path)
    abs_dest = _resolve_safe_path(project_root, dest_godot_path)
    if not os.path.isfile(abs_source):
        raise FileNotFoundError(f"Исходный файл не найден: {source_godot_path}")
    if os.path.exists(abs_dest):
        raise FileExistsError(f"Файл в месте назначения уже существует: {dest_godot_path}")
    os.makedirs(os.path.dirname(abs_dest), exist_ok=True)
    shutil.copy2(abs_source, abs_dest)


SEARCH_EXTS = {'.gd', '.tscn', '.tres', '.cfg', '.godot', '.json', '.txt',
               '.md', '.gdshader', '.shader', '.csv'}


def search_project_text(project_root, query, max_results=30, context_lines=2):
    """Поиск текста по файлам проекта (аналог «Поиска по проекту» в Godot).
    Возвращает (список совпадений, был_ли_список_обрезан)."""
    project_root_abs = os.path.abspath(project_root)
    query_norm = (query or '').replace('\r\n', '\n')
    results = []
    if not query_norm.strip():
        return results, False
    for dirpath, dirnames, filenames in os.walk(project_root_abs):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith('.'))
        for fname in sorted(filenames):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in SEARCH_EXTS:
                continue
            abs_path = os.path.join(dirpath, fname)
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.read().replace('\r\n', '\n').split('\n')
            except Exception:
                continue
            rel = os.path.relpath(abs_path, project_root_abs).replace(os.sep, '/')
            godot_path = 'res://' + rel
            for idx, line in enumerate(lines):
                if query_norm in line:
                    lo = max(0, idx - context_lines)
                    hi = min(len(lines), idx + context_lines + 1)
                    snippet = '\n'.join('%d: %s' % (n + 1, lines[n]) for n in range(lo, hi))
                    results.append({'path': godot_path, 'line': idx + 1, 'snippet': snippet})
                    if len(results) >= max_results:
                        return results, True
    return results, False

def describe_scene(project_root, godot_path, max_chars=12000):
    """Краткая структура сцены .tscn для модели: дерево узлов (имя, тип),
    прикреплённые скрипты, инстансы других сцен и связи сигналов."""
    import re
    abs_path = _resolve_safe_path(project_root, godot_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError("Файл не найден: %s" % godot_path)
    if os.path.splitext(abs_path)[1].lower() not in (".tscn", ".scn"):
        raise ValueError("list_scene работает только со сценами .tscn: %s" % godot_path)
    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    # id ext-ресурса -> путь (скрипты, вложенные сцены)
    ext = {}
    ext_rows = []
    sub_rows = []
    for m in re.finditer(r'\[ext_resource\b[^\]]*\]', text):
        head = m.group(0)
        pm = re.search(r'path="([^"]+)"', head)
        im = re.search(r'\bid="?([^"\s\]]+)"?', head)
        tm2 = re.search(r'\btype="([^"]+)"', head)
        um = re.search(r'\buid="([^"]+)"', head)
        if pm and im:
            ext[im.group(1)] = pm.group(1)
        ext_rows.append({"id": im.group(1) if im else "?", "type": tm2.group(1) if tm2 else "?",
                          "path": pm.group(1) if pm else "?", "uid": um.group(1) if um else None})
    for m in re.finditer(r'\[sub_resource\b[^\]]*\]', text):
        head = m.group(0)
        im = re.search(r'\bid="?([^"\s\]]+)"?', head)
        tm2 = re.search(r'\btype="([^"]+)"', head)
        sub_rows.append({"id": im.group(1) if im else "?", "type": tm2.group(1) if tm2 else "?"})
    nodes = []
    connections = []
    cur = None
    for line in text.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if s.startswith("[node "):
            nm = re.search(r'name="([^"]+)"', s)
            tm = re.search(r'type="([^"]+)"', s)
            pm = re.search(r'parent="([^"]*)"', s)
            im = re.search(r'instance=ExtResource\(\s*"?([^")\s]+)"?\s*\)', s)
            if pm is None:
                depth = 0
            else:
                parent = pm.group(1)
                depth = 1 if parent == "." else parent.count("/") + 2
            cur = {"depth": depth,
                   "name": nm.group(1) if nm else "?",
                   "type": tm.group(1) if tm else "",
                   "script": None,
                   "instance": ext.get(im.group(1)) if im else None}
            nodes.append(cur)
        elif s.startswith("[connection "):
            sig = re.search(r'signal="([^"]+)"', s)
            frm = re.search(r'from="([^"]*)"', s)
            to = re.search(r'to="([^"]*)"', s)
            met = re.search(r'method="([^"]+)"', s)
            if sig and frm and to and met:
                frm_disp = frm.group(1) if frm.group(1) not in ("", ".") else "<root>"
                to_disp = to.group(1) if to.group(1) not in ("", ".") else "<root>"
                connections.append("%s.%s -> %s.%s()" % (frm_disp, sig.group(1), to_disp, met.group(1)))
            cur = None
        elif s.startswith("["):
            cur = None
        elif cur is not None and re.match(r"script\s*=", s):
            sm = re.search(r'ExtResource\(\s*"?([^")\s]+)"?\s*\)', s)
            if sm:
                cur["script"] = ext.get(sm.group(1))
    if not nodes:
        raise ValueError("В файле не найдено ни одного узла [node].")
    out = []
    for n in nodes:
        extra = []
        if n["type"]:
            extra.append(n["type"])
        if n["instance"]:
            extra.append("инстанс: %s" % n["instance"])
        row = "  " * n["depth"] + "- " + n["name"] + ((" (" + ", ".join(extra) + ")") if extra else "")
        if n["script"]:
            row += "  [скрипт: %s]" % n["script"]
        out.append(row)
    if connections:
        out.append("")
        out.append("Сигналы ([connection]):")
        for c in connections:
            out.append("- " + c)
    if ext_rows or sub_rows:
        out.append("")
        out.append("Ресурсы (id/uid для точных ссылок в ExtResource/SubResource):")
        for r in ext_rows:
            line = "- ext id=%s %s: %s" % (r["id"], r["type"], r["path"])
            if r["uid"]:
                line += " (uid=%s)" % r["uid"]
            out.append(line)
        for r in sub_rows:
            out.append("- sub id=%s %s" % (r["id"], r["type"]))
    result = "\n".join(out)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n… (сводка обрезана — сцена очень большая)"
    return result
