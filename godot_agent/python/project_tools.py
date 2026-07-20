import os
import shutil

EXCLUDED_DIRS = {'.godot', '.import', '.git', '.venv', '__pycache__',
                 'node_modules', '.vs', '.vscode', '.agent_history'}
EXCLUDED_FILES = {'.DS_Store'}

HISTORY_DIR_NAME = ".agent_history"


def build_project_tree(project_root, max_depth=8, only_exts=None, max_entries=None, subdir=None):
    """Строит текстовое дерево файлов проекта (или ОДНОЙ его папки, если задан
    subdir — например "res://src/scripts/") для контекста ИИ."""
    project_root = os.path.abspath(project_root)
    base = project_root
    if subdir and str(subdir).strip().rstrip('/') in ("", "res:"):
        # "res://" после rstrip('/') превращался в "res:" и «не находился».
        # Корень проекта — валидный запрос: показываем всё дерево.
        subdir = None
    if subdir:
        base = _resolve_safe_path(project_root, subdir.rstrip('/'))
        if not os.path.isdir(base):
            raise FileNotFoundError(f"Папка не найдена: {subdir}")
    lines = []
    count = 0
    truncated = False
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith('.'))
        rel = os.path.relpath(dirpath, base)
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
    # v52: realpath, не abspath — abspath НЕ разрешает симвлинки; симвлинк внутри проекта, ведущая наружу, могла бы обойти проверку ниже.
    project_root_abs = os.path.realpath(project_root)
    abs_path = os.path.realpath(os.path.join(project_root_abs, rel))
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


# ---------------------------------------------------------------------------
# Умный контекст проекта: маленький проект — полное дерево, большой —
# КОМПАКТНАЯ сводка по папкам (счётчики по расширениям), чтобы не сжигать
# токены модели полотном из тысяч файлов. Плюс понимание архитектуры
# проекта и снапшот файлов для обнаружения ВНЕШНИХ изменений.
# ---------------------------------------------------------------------------

ASSET_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.svg', '.wav', '.ogg', '.mp3',
              '.ttf', '.otf', '.glb', '.gltf', '.obj', '.fbx'}

# Стандартная архитектура для НОВОГО игрового проекта (создаётся,
# только если своей архитектуры у проекта ещё нет — см. has_architecture).
STANDARD_ARCHITECTURE_DIRS = [
    "src/scenes",
    "src/scripts",
    "src/scripts/player",
    "src/scripts/ui",
    "src/autoload",
    "assets/sprites",
    "assets/audio",
    "assets/fonts",
]


def build_project_overview(project_root, only_exts=None, max_entries=None, compact_threshold=150):
    """Умный контекст: если файлов мало — полное дерево (как раньше), если
    много — сводка по папкам. Возвращает (текст, is_compact)."""
    project_root = os.path.abspath(project_root)
    total = 0
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith('.'))
        for f in filenames:
            if f in EXCLUDED_FILES:
                continue
            if only_exts is not None and os.path.splitext(f)[1].lower() not in only_exts:
                continue
            total += 1
        if total > compact_threshold:
            break
    if total <= compact_threshold:
        return build_project_tree(project_root, only_exts=only_exts, max_entries=max_entries), False
    # Компактная сводка: папки (до 3 уровней) и счётчики файлов по расширениям.
    per_dir = {}
    root_files = []
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith('.'))
        rel = os.path.relpath(dirpath, project_root).replace(os.sep, '/')
        for f in sorted(filenames):
            if f in EXCLUDED_FILES:
                continue
            ext = os.path.splitext(f)[1].lower() or '(без расширения)'
            if rel == '.':
                root_files.append(f)
            else:
                key = '/'.join(rel.split('/')[:3])
                per_dir.setdefault(key, {})
                per_dir[key][ext] = per_dir[key].get(ext, 0) + 1
    lines = [
        "(Проект БОЛЬШОЙ — вместо полного дерева ниже СВОДКА по папкам.",
        "Точные данные бери АДРЕСНО: list_files с \"dir\" — дерево нужной папки; search_project — где объявлен код; list_scene — структура сцены; read_file — содержимое файла.)",
        "",
    ]
    for f in root_files:
        lines.append(f)
    for key in sorted(per_dir):
        stats = per_dir[key]
        parts = ", ".join("%d %s" % (stats[e], e) for e in sorted(stats))
        lines.append("%s/ — %s" % (key, parts))
    if len(lines) > 400:
        lines = lines[:400] + ["… (сводка обрезана — папок очень много)"]
    return '\n'.join(lines), True


def _parse_project_godot(project_root):
    """Главная сцена и автозагрузки (Autoload) из project.godot."""
    p = os.path.join(os.path.abspath(project_root), 'project.godot')
    main_scene, autoloads, section = '', {}, ''
    if not os.path.isfile(p):
        return main_scene, autoloads
    try:
        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                s = line.strip()
                if s.startswith('[') and s.endswith(']'):
                    section = s[1:-1].strip()
                    continue
                if '=' not in s or s.startswith(';') or s.startswith('#'):
                    continue
                key, val = s.split('=', 1)
                key, val = key.strip(), val.strip().strip('"')
                if section == 'application' and key == 'run/main_scene':
                    main_scene = val
                elif section == 'autoload' and key:
                    autoloads[key] = val.lstrip('*')
    except Exception:
        pass
    return main_scene, autoloads


def clean_dangling_autoloads(project_root):
    """После откат��/удаления файлов убирает из project.godot записи секции
    [autoload], которые ссылаются на файл, которого больше нет на диске
    (например, откат вернул create_file, добавивший автозагрузку, к состоянию
    ДО плана, а сама запись автозагрузки была добавлена другим patch_file и
    осталась, если откат был частичным/по одному действию). Возвращает список
    убранных ключей автозагрузки (пустой список — ничего убирать не пришлось).
    Пустой список также означает, что project.godot НЕ был перезаписан на диске
    (важно для вызывающего кода — не дёргать лишний раз сброс кэша/перезагрузку)."""
    project_root_abs = os.path.abspath(project_root)
    p = os.path.join(project_root_abs, 'project.godot')
    if not os.path.isfile(p):
        return []
    try:
        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return []
    out_lines = []
    section = ''
    removed_keys = []
    changed = False
    for line in lines:
        s = line.strip()
        if s.startswith('[') and s.endswith(']'):
            section = s[1:-1].strip()
            out_lines.append(line)
            continue
        if (section == 'autoload' and '=' in s
                and not s.startswith(';') and not s.startswith('#')):
            key, val = s.split('=', 1)
            key = key.strip()
            val_clean = val.strip().strip('"').lstrip('*')
            # Автозагрузка может уточнять класс через "::" (напр. "*res://x.gd::MyClass").
            target_path = val_clean.split('::')[0] if '::' in val_clean else val_clean
            target_missing = True
            if target_path.startswith('res://'):
                try:
                    target_missing = not os.path.isfile(_resolve_safe_path(project_root, target_path))
                except Exception:
                    target_missing = True
            else:
                target_missing = False  # не res:// путь — не наша забота, не трогаем
            if key and target_missing:
                removed_keys.append(key)
                changed = True
                continue  # пропускаем строку — вычищаем висячую автозагрузку
        out_lines.append(line)
    if changed:
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.writelines(out_lines)
    return removed_keys


def has_architecture(project_root):
    """Есть ли у проекта СВОЯ структура: типовые папки или любой .gd/.tscn
    вне addons/. Если есть — агент ИСПОЛЬЗУЕТ её, а не навязывает свою."""
    project_root = os.path.abspath(project_root)
    for name in ('src', 'scripts', 'scenes', 'game', 'core', 'levels'):
        if os.path.isdir(os.path.join(project_root, name)):
            return True
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames
                       if d not in EXCLUDED_DIRS and not d.startswith('.') and d != 'addons']
        for f in filenames:
            if os.path.splitext(f)[1].lower() in ('.gd', '.tscn'):
                return True
    return False


def ensure_standard_architecture(project_root):
    """Если архитектуры у проекта нет (пустой/новый проект) — создаёт
    стандартную для игр (с пустым .gdkeep в каждой папке, чтобы папки
    не терялись). Возвращает список созданных папок res:// (пустой — ничего не создано)."""
    project_root = os.path.abspath(project_root)
    if has_architecture(project_root):
        return []
    created = []
    for rel in STANDARD_ARCHITECTURE_DIRS:
        abs_dir = os.path.join(project_root, rel.replace('/', os.sep))
        if os.path.isdir(abs_dir):
            continue
        os.makedirs(abs_dir, exist_ok=True)
        try:
            with open(os.path.join(abs_dir, '.gdkeep'), 'w', encoding='utf-8') as f:
                f.write('')
        except OSError:
            pass
        created.append('res://' + rel + '/')
    return created


def describe_architecture(project_root, max_dirs=6):
    """Короткая сводка архитектуры проекта для модели: главная сцена,
    автозагрузки, где живут скрипты/сцены/ассеты (топ папок по числу файлов)."""
    project_root = os.path.abspath(project_root)
    main_scene, autoloads = _parse_project_godot(project_root)
    script_dirs, scene_dirs, asset_dirs = {}, {}, {}
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames
                       if d not in EXCLUDED_DIRS and not d.startswith('.') and d != 'addons']
        rel = os.path.relpath(dirpath, project_root).replace(os.sep, '/')
        key = '(корень res://)' if rel == '.' else '/'.join(rel.split('/')[:2])
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext == '.gd':
                script_dirs[key] = script_dirs.get(key, 0) + 1
            elif ext in ('.tscn', '.scn'):
                scene_dirs[key] = scene_dirs.get(key, 0) + 1
            elif ext in ASSET_EXTS:
                asset_dirs[key] = asset_dirs.get(key, 0) + 1
    lines = []
    if main_scene:
        lines.append('Главная сцена: %s' % main_scene)
    if autoloads:
        lines.append('Автозагрузки (Autoload): ' +
                     '; '.join('%s → %s' % (k, v) for k, v in sorted(autoloads.items())))

    def _top(d, label):
        if not d:
            return
        items = sorted(d.items(), key=lambda kv: -kv[1])[:max_dirs]
        shown = []
        for k, v in items:
            shown.append('%s (%d)' % (k, v) if k.startswith('(') else 'res://%s/ (%d)' % (k, v))
        lines.append(label + ': ' + '; '.join(shown))

    _top(script_dirs, 'Скрипты (.gd)')
    _top(scene_dirs, 'Сцены (.tscn)')
    _top(asset_dirs, 'Ассеты')
    return '\n'.join(lines)


def snapshot_files(project_root):
    """Отпечаток файлов проекта (mtime+size) — для обнаружения изменений,
    сделанных ВНЕ агента (пользователь удалил/поменял файлы руками)."""
    project_root = os.path.abspath(project_root)
    snap = {}
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith('.'))
        for f in filenames:
            if f in EXCLUDED_FILES:
                continue
            abs_path = os.path.join(dirpath, f)
            try:
                st = os.stat(abs_path)
            except OSError:
                continue
            rel = os.path.relpath(abs_path, project_root).replace(os.sep, '/')
            snap[rel] = (int(st.st_mtime), int(st.st_size))
    return snap


def diff_snapshots(old, new):
    """Сравнение двух снапшотов: (добавлены, изменены, удалены)."""
    added = sorted(set(new) - set(old))
    deleted = sorted(set(old) - set(new))
    changed = sorted(p for p in new if p in old and new[p] != old[p])
    return added, changed, deleted


def format_fs_changes(added, changed, deleted, limit=12, diffs=None):
    """Сообщение модели о внешних изменениях файлов (или "" если их нет).
    diffs: {rel_path: (diff_text, n_lines)} — точечные diff для изменённых
    файлов, чьё старое содержимое модель уже видела: ей НЕ нужно
    перечитывать весь файл заново (экономия токенов)."""
    if not (added or changed or deleted):
        return ''
    diffs = diffs or {}

    def _block(title, items):
        rows = ['- %s: res://%s' % (title, p) for p in items[:limit]]
        if len(items) > limit:
            rows.append('- …и ещё %d (%s)' % (len(items) - limit, title))
        return rows

    lines = ['[Система]: файлы проекта ИЗМЕНИЛИСЬ вне этого диалога (пользователь или другая программа):']
    lines += _block('удалён', deleted)
    for p in changed[:limit]:
        if p in diffs:
            d, n = diffs[p]
            lines.append('- изменён: res://%s — точечная правка (строк в diff: %d). Точный diff НИЖЕ — перечитывать файл НЕ нужно:' % (p, n))
            lines.append('```diff')
            lines.append(d)
            lines.append('```')
        else:
            lines.append('- изменён: res://%s (правка большая или неизвестная — перечитай через read_file перед патчем)' % p)
    if len(changed) > limit:
        lines.append('- …и ещё %d (изменён)' % (len(changed) - limit))
    lines += _block('добавлен', added)
    lines.append('Учитывай это: НЕ ссылайся на удалённые файлы; где есть diff — применяй его как новое содержимое; изменённые БЕЗ diff перечитай через read_file, прежде чем патчить.')
    return '\n'.join(lines)


def unified_diff_text(old_text, new_text, rel_path, max_lines=40, context=1):
    """Компактный unified-diff для модели: (diff_text, изменённых строк).
    Если правка слишком большая для точечного diff — (None, изменённых строк):
    тогда модели дешевле перечитать файл целиком через read_file."""
    import difflib
    diff = list(difflib.unified_diff(
        old_text.splitlines(), new_text.splitlines(),
        fromfile='res://%s (было)' % rel_path,
        tofile='res://%s (стало)' % rel_path,
        lineterm='', n=context))
    if not diff:
        return None, 0
    changed = sum(1 for l in diff
                  if (l.startswith('+') or l.startswith('-'))
                  and not l.startswith('+++') and not l.startswith('---'))
    if len(diff) > max_lines:
        return None, changed
    return '\n'.join(diff), changed
