import errno
import os
import shutil
import tempfile

from text_sanitize import sanitize_llm_text

EXCLUDED_DIRS = {'.godot', '.import', '.git', '.venv', '__pycache__',
                 'node_modules', '.vs', '.vscode', '.agent_history',
                 # v77: мозг mini-lich (датасет+чекпоинты) меняется сам по себе постояннововремя обучения
                 # — это не внешнее изменение проекта, о котором нужно сообщать модели.
                 'minilich_brain',
                 # v104.3: папка самого плагина (внутри — python-сборка сервера:
                 # build/, dist/_internal/ с numpy, selenium и т.п.) — служебная,
                 # к игре не относится и раздувала мега-промпт десятками строк.
                 # 'Godot_agent' — имя папки из дистрибутива (запасной вариант);
                 # точное имя добавляется динамически из addon_dir при /init
                 # (см. exclude_agent_addon_dirs).
                 'Godot_agent'}
EXCLUDED_FILES = {'.DS_Store'}

HISTORY_DIR_NAME = ".agent_history"


class MoveRecoveryError(RuntimeError):
    """A move could not be restored; its reservation and files must be retained."""


class CaseOnlyDirCasingTransaction:
    """Track case-only parent-directory renames so they can be undone safely.

    Renames are applied top-down while the transaction is created. ``renames``
    contains only operations that actually completed, newest last. A transaction
    is terminal after commit, rollback, or a failed rollback; terminal rollback
    calls are deliberately no-ops so an injected recovery failure is not
    accidentally retried or reported as a successful restoration.
    """

    def __init__(self, project_root, src_rel, dst_rel):
        self.project_root = os.path.realpath(project_root)
        self.source_components = str(src_rel).replace("\\", "/").strip("/").split("/")[:-1]
        self.requested_components = str(dst_rel).replace("\\", "/").strip("/").split("/")[:-1]
        if len(self.source_components) != len(self.requested_components):
            raise ValueError("Case-only rename must keep the path depth: %s -> %s"
                             % (src_rel, dst_rel))
        self.current_parent = self.project_root
        self.renames = []
        self.state = "new"
        self.rollback_succeeded = None
        self.failed_renames = []
        self._apply()

    @property
    def new_parent(self):
        """Absolute parent path with the requested directory casing."""
        return self.current_parent

    def _apply(self):
        try:
            for source_part, requested_part in zip(
                    self.source_components, self.requested_components):
                old_path = os.path.join(self.current_parent, source_part)
                if source_part == requested_part:
                    self.current_parent = old_path
                    continue
                if not os.path.isdir(old_path):
                    raise FileNotFoundError("Каталог не найден: %s" % old_path)
                new_path = os.path.join(self.current_parent, requested_part)
                os.rename(old_path, new_path)
                self.renames.append((old_path, new_path))
                self.current_parent = new_path
        except BaseException as move_error:
            try:
                self.rollback()
            except MoveRecoveryError as recovery_error:
                raise MoveRecoveryError(
                    "Case-only directory casing failed: %s; %s"
                    % (move_error, recovery_error)
                ) from recovery_error
            raise

    def rename(self, old_path, new_path):
        """Apply and track one additional case-only directory rename."""
        if self.state != "new":
            raise RuntimeError("Case-only directory transaction is already finished")
        os.rename(old_path, new_path)
        self.renames.append((old_path, new_path))

    def commit(self):
        """Make the completed renames permanent; repeated calls are harmless."""
        if self.state == "new":
            self.state = "committed"

    def rollback(self):
        """Undo completed renames newest-first exactly once.

        A failed leaf rollback is not followed by a parent rollback: nested
        paths would then be moved underneath a casing different from the paths
        stored in the recovery report. The failed pair and all its ancestors are
        retained for honest manual recovery instead.
        """
        if self.state != "new":
            return

        while self.renames:
            old_path, new_path = self.renames[-1]
            try:
                os.rename(new_path, old_path)
            except OSError as recovery_error:
                self.state = "rolled_back"
                self.rollback_succeeded = False
                self.failed_renames = list(self.renames)
                raise MoveRecoveryError(
                    "Case-only directory casing rollback failed: %s. "
                    "Files and recovery snapshots retained for manual recovery; "
                    "paths not restored: %r -> %r; inspect %r"
                    % (recovery_error, new_path, old_path, self.failed_renames)
                ) from recovery_error
            self.renames.pop()
            self.current_parent = old_path

        self.state = "rolled_back"
        self.rollback_succeeded = True


def begin_case_only_dir_casing(project_root, src_rel, dst_rel):
    """Rename parent components and return their rollback-capable transaction."""
    return CaseOnlyDirCasingTransaction(project_root, src_rel, dst_rel)


def _is_generated_sidecar(path):
    """Godot-managed sidecars are useful locally but only add model noise."""
    return str(path or '').replace('\\', '/').lower().endswith('.uid')


def exclude_agent_addon_dirs(addon_dir):
    """v104.3: исключает папку САМОГО плагина из дерева проекта, сводки,
    search_project и снапшота внешних изменений (все они фильтруют обход по
    EXCLUDED_DIRS). Плагин обычно лежит как addons/<Обёртка>/<папка_аддона> —
    исключаем и папку аддона, и обёртку. Явный read_file по пути внутри
    аддона по-прежнему работает (_resolve_safe_path это не фильтрует)."""
    try:
        norm = os.path.normpath(str(addon_dir or "")).replace(os.sep, "/")
    except Exception:
        return
    parts = [p for p in norm.split("/") if p]
    if not parts:
        return
    if parts[-1] != "addons":
        EXCLUDED_DIRS.add(parts[-1])
    if "addons" in parts:
        i = parts.index("addons")
        if i + 1 < len(parts):
            EXCLUDED_DIRS.add(parts[i + 1])



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
            if f in EXCLUDED_FILES or _is_generated_sidecar(f):
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
    root_identity = os.path.normcase(project_root_abs)
    path_identity = os.path.normcase(abs_path)
    if path_identity != root_identity and not path_identity.startswith(root_identity + os.sep):
        raise ValueError(f"Путь вне проекта отклонен: {godot_path}")
    # Служебная папка истории агента недоступна для чтения/записи через действия.
    rel_norm = os.path.relpath(abs_path, project_root_abs).replace(os.sep, '/')
    if rel_norm.casefold() == HISTORY_DIR_NAME or rel_norm.casefold().startswith(HISTORY_DIR_NAME + '/'):
        raise ValueError("Доступ к служебной папке истории запрещён.")
    return abs_path


def is_addon_path(path, project_root=None):
    """Use resolved identity when available; policy is case-insensitive on every OS."""
    value = str(path or "").replace("\\", "/")
    if project_root:
        value = os.path.relpath(_resolve_safe_path(project_root, value),
                                os.path.realpath(project_root)).replace("\\", "/")
    else:
        import posixpath
        value = posixpath.normpath(value.removeprefix("res://").lstrip("/"))
    return value.casefold() == "addons" or value.casefold().startswith("addons/")


def read_project_file(project_root, godot_path, max_chars=50000):
    """Читает содержимое файла проекта."""
    abs_path = _resolve_safe_path(project_root, godot_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Файл не найден: {godot_path}")
    with open(abs_path, 'r', encoding='utf-8-sig', errors='replace') as f:
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
    # v86.2: страховка на записи — невидимые символы из веб-DOM (NBSP, NUL,
    # zero-width) не должны попасть в файлы проекта, даже если парсер их пропустил.
    _atomic_write_text(abs_path, sanitize_llm_text(content.replace('\r\n', '\n')) or '')
    return existed


def patch_result_text(project_root, godot_path, search_code, replace_code):
    """(старый_текст, новый_текст) для patch_file БЕЗ записи на диск.

    Нужна предпросмотру: карточка диффа в панели обязана показывать ровно то,
    что применится, поэтому нормализация и проверки здесь общие с настоящим
    патчем — patch_project_file вызывает эту же функцию."""
    abs_path = _resolve_safe_path(project_root, godot_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Файл не найден: {godot_path}")
    with open(abs_path, 'r', encoding='utf-8-sig') as f:
        original_content = f.read()
    content = original_content.replace('\r\n', '\n')
    # v86.2: чистим И искомый блок, И замену: файл на диске уже чистый, а блоки из
    # ответа модели могут нести NBSP/zero-width — поиск бы ложно проваливался,
    # а замена заражала бы файл невидимым мусором.
    search_norm = sanitize_llm_text(search_code.replace('\r\n', '\n')) or ''
    replace_norm = sanitize_llm_text(replace_code.replace('\r\n', '\n')) or ''
    occurrences = content.count(search_norm)
    if occurrences == 0:
        raise ValueError("Ошибка: Указанный старый блок кода не найден в файле.")
    if occurrences > 1:
        raise ValueError("Ошибка: Блок кода не уникален (встречается несколько раз).")
    return content, content.replace(search_norm, replace_norm)


def patch_project_file(project_root, godot_path, search_code, replace_code):
    """Точечный патч кода. Резервная копия теперь хранится в журнале
    изменений (.agent_history) — см. history_manager.py."""
    abs_path = _resolve_safe_path(project_root, godot_path)
    _, new_content = patch_result_text(project_root, godot_path, search_code, replace_code)
    # LF как в Godot (см. комментарий в create_project_file).
    _atomic_write_text(abs_path, new_content)


def _atomic_write_text(abs_path, content):
    """Write UTF-8/LF text without truncating the target on failure."""
    parent = os.path.dirname(abs_path)
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".agent-write-", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, abs_path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


_LINK_FALLBACK_ERRNOS = frozenset({
    errno.EXDEV,   # cross-device link
    errno.EPERM,   # hardlinks unsupported (FAT32/exFAT)
    errno.EACCES,  # hardlinks denied by filesystem/policy
    errno.ENOSYS,  # not implemented on this filesystem
    errno.EINVAL,  # CPython mapping of WinError 1/50/87
})
_LINK_FALLBACK_WINERRORS = frozenset({1, 50, 87})  # INVALID_FUNCTION / NOT_SUPPORTED / INVALID_PARAMETER


def _hardlinks_unavailable(exc):
    """True when os.link failed because hardlinks themselves are unavailable."""
    if exc.errno in _LINK_FALLBACK_ERRNOS:
        return True
    return getattr(exc, "winerror", None) in _LINK_FALLBACK_WINERRORS


def _move_via_hardlinks(pairs):
    """Move each (source, target) via link+unlink; restore originals on failure."""
    linked = []
    try:
        for source, target in pairs:
            identity = os.stat(source)
            # link is fail-if-exists, unlike POSIX rename/shutil.move.
            os.link(source, target)
            linked.append([source, target, identity, False])
            os.unlink(source)
            linked[-1][3] = True
    except OSError as move_error:
        try:
            for source, target, identity, removed in reversed(linked):
                # Never clean up a target replaced by another writer.
                if not os.path.samestat(os.stat(target), identity):
                    raise OSError(f"Recovery target changed: {target}")
                if removed:
                    os.link(target, source)
                elif not os.path.samestat(os.stat(source), identity):
                    raise OSError(f"Recovery source changed: {source}")
                os.unlink(target)
        except OSError as recovery_error:
            raise MoveRecoveryError(
                f"Move recovery failed: {recovery_error}; original error: {move_error}. "
                f"Files retained for manual recovery; inspect {pairs!r}"
            ) from recovery_error
        raise


def _move_via_copy(pairs):
    """Fail-if-exists move for filesystems without hardlinks (EXDEV, FAT32/exFAT).

    Targets are created with O_EXCL, so an existing destination is never
    overwritten; sources are unlinked only after every copy succeeded.
    """
    copied = []
    try:
        for source, target in pairs:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            try:
                with os.fdopen(fd, "wb") as out:
                    with open(source, "rb") as inp:
                        shutil.copyfileobj(inp, out)
                    out.flush()
                    os.fsync(out.fileno())
            except BaseException:
                try:
                    os.unlink(target)
                except OSError:
                    pass
                raise
            try:
                shutil.copystat(source, target)
            except OSError:
                pass
            copied.append((source, target))
        for source, _target in copied:
            os.unlink(source)
    except BaseException:
        recovery_errors = []
        for source, target in reversed(copied):
            try:
                if os.path.exists(source):
                    # Source intact: drop only our own copy.
                    os.unlink(target)
                elif os.path.isfile(target):
                    shutil.copy2(target, source)
                    os.unlink(target)
            except OSError as rec_err:
                recovery_errors.append(rec_err)
        if recovery_errors:
            raise MoveRecoveryError(
                f"Move fallback recovery failed: {recovery_errors[0]}. "
                f"Files retained for manual recovery; inspect {pairs!r}"
            ) from recovery_errors[0]
        raise


def _move_case_only(abs_source, abs_dest):
    """Rename a file (and its .uid sidecar) changing only the letter case.

    Hardlink-based moves cannot express this on case-insensitive filesystems:
    source and destination are the same file there. abs_dest must preserve the
    caller-requested letter case (realpath would collapse it to the on-disk one).
    """
    pairs = [(abs_source, abs_dest)]
    src_uid = abs_source + ".uid"
    if os.path.lexists(src_uid):
        if os.path.islink(src_uid) or not os.path.isfile(src_uid):
            raise ValueError("Source UID must be a regular file, not a symlink or directory")
        pairs.append((src_uid, abs_dest + ".uid"))
    for src, dst in pairs:
        if os.path.lexists(dst):
            try:
                same = os.path.samefile(src, dst)
            except OSError:
                same = False
            if not same:
                raise FileExistsError(f"Destination already exists: {dst}")
    done = []
    try:
        for src, dst in pairs:
            os.rename(src, dst)
            done.append((src, dst))
    except OSError as move_error:
        recovery_errors = []
        for src, dst in reversed(done):
            try:
                os.rename(dst, src)
            except OSError as recovery_error:
                recovery_errors.append((dst, src, recovery_error))
        if recovery_errors:
            failed_pairs = [(current, original)
                            for current, original, _error in recovery_errors]
            raise MoveRecoveryError(
                "Case-only file recovery failed: %s; original error: %s. "
                "Files and recovery snapshots retained for manual recovery; "
                "paths not restored: %r; inspect %r"
                % (recovery_errors[0][2], move_error, failed_pairs, pairs)
            ) from recovery_errors[0][2]
        raise



def fix_case_only_dir_casing(project_root, src_rel, dst_rel):
    """Backward-compatible non-transactional parent-casing API.

    Prefer ``begin_case_only_dir_casing`` when a later operation must be able to
    undo these directory renames. This legacy helper immediately commits after
    the constructor has successfully applied all parent changes.
    """
    transaction = begin_case_only_dir_casing(project_root, src_rel, dst_rel)
    transaction.commit()
    return transaction.new_parent


def move_project_file(project_root, source_godot_path, dest_godot_path):
    """Move a file and its UID without clobbering; restore on ordinary I/O failure."""
    abs_source = _resolve_safe_path(project_root, source_godot_path)
    abs_dest = _resolve_safe_path(project_root, dest_godot_path)
    source_uid = _resolve_safe_path(project_root, abs_source + ".uid")
    dest_uid = _resolve_safe_path(project_root, abs_dest + ".uid")
    if not os.path.isfile(abs_source):
        raise FileNotFoundError(f"Исходный файл не найден: {source_godot_path}")
    src_rel = source_godot_path.removeprefix("res://").replace("\\", "/").strip("/")
    dst_rel = dest_godot_path.removeprefix("res://").replace("\\", "/").strip("/")
    if src_rel != dst_rel and src_rel.lower() == dst_rel.lower() and os.path.lexists(abs_dest):
        # Case-only rename on a case-insensitive filesystem (Windows):
        # realpath collapsed both paths to the on-disk casing, so rebuild
        # the destination preserving the requested letter case. Directory
        # components with changed casing must be renamed explicitly --
        # otherwise the leaf rename alone silently keeps the old dir casing
        # while references/journal record the requested one (fresh audit, item 3).
        transaction = begin_case_only_dir_casing(project_root, src_rel, dst_rel)
        abs_dest_requested = os.path.join(
            transaction.new_parent, dst_rel.split("/")[-1])
        try:
            _move_case_only(abs_source, abs_dest_requested)
        except BaseException as move_error:
            try:
                transaction.rollback()
            except MoveRecoveryError as recovery_error:
                raise MoveRecoveryError(
                    "Case-only move failed: %s; %s"
                    % (move_error, recovery_error)
                ) from recovery_error
            raise
        transaction.commit()
        return
    identities = {os.path.normcase(p) for p in (abs_source, abs_dest, source_uid, dest_uid)}
    if len(identities) != 4:
        raise FileExistsError("Source, destination and UID paths must not alias each other")
    # Check the requested slots too: realpath can hide a dangling symlink.
    requested_dest = os.path.join(project_root, dest_godot_path.removeprefix("res://"))
    for target in (requested_dest, requested_dest + ".uid", abs_dest, abs_dest + ".uid"):
        if os.path.lexists(target):
            raise FileExistsError(f"Destination already exists: {target}")
    pairs = [(abs_source, abs_dest)]
    if os.path.lexists(abs_source + ".uid"):
        if os.path.islink(abs_source + ".uid") or not os.path.isfile(source_uid):
            raise ValueError("Source UID must be a regular file, not a symlink or directory")
        pairs.append((source_uid, dest_uid))
    os.makedirs(os.path.dirname(abs_dest), exist_ok=True)
    try:
        _move_via_hardlinks(pairs)
    except OSError as move_error:
        if not _hardlinks_unavailable(move_error):
            raise
        # Hardlinks unavailable (EXDEV / FAT32 / exFAT): originals were already
        # restored by _move_via_hardlinks; fall back to exclusive-create copies.
        _move_via_copy(pairs)


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


def search_project_text(project_root, query, max_results=30, context_lines=2,
                        exclude_rel_prefixes=None, case_insensitive=False,
                        needles=None):
    """Поиск текста по файлам проекта (аналог «Поиска по проекту» в Godot).
    Возвращает (список совпадений, был_ли_список_обрезан).

    exclude_rel_prefixes (v105.10): кортеж/список префиксов ОТНОСИТЕЛЬНЫХ
    путей (например ("addons/",)), которые пропускаются ДО набора квоты
    max_results. Нужно Библиотекарю: раньше он фильтровал аддоны ПОСЛЕ
    поиска, и файлы addons/ (обход идёт по алфавиту, addons почти всегда
    первая) выбирали всю квоту — слои FRAGMENTS/CALLERS/SIGNALS молча
    пустели на любом проекте с установленными аддонами. По умолчанию
    None — поведение для остальных вызывающих не меняется.

    case_insensitive (v105.10): сравнение без учёта регистра. Нужно
    Библиотекарю как фолбэк: MAP регистронезависим, а FRAGMENTS был
    строгим — запрос «health» не находил код с «Health». По умолчанию
    False — точный поиск для инструмента search_project остаётся как был."""
    project_root_abs = os.path.abspath(project_root)
    results = []
    # v105.14 (п.2): одна и та же механика для одной подстроки и для списка:
    # одиночный query — частный случай списка из одного элемента. Двух
    # реализаций обхода быть не должно — иначе фильтры (SEARCH_EXTS,
    # EXCLUDED_DIRS, exclude_rel_prefixes) разъедутся при первой же правке.
    #
    # needles (v105.14, п.2): список подстрок, которые ищутся ЗА ОДИН обход
    # проекта (query тогда игнорируется). Было: слои CALLERS и SIGNALS
    # Библиотекаря вызывали эту функцию отдельно на КАЖДЫЙ шаблон (до 12 и
    # до 24 полных обходов диска на ОДИН ответ) — это, а не размер индекса,
    # давало самые медленные ответы на больших проектах. Каждый результат
    # помечен полем 'needle' (какая подстрока совпала): метка нужна CALLERS
    # (отличить прямой вызов от имени в кавычках) и SIGNALS (_signal_label).
    # max_results считается НА КАЖДУЮ подстроку отдельно — ровно как при
    # отдельных вызовах, чтобы выдача слоёв осталась побайтно той же.
    if needles is not None:
        raw_needles = [str(n) for n in needles if str(n or '').strip()]
    else:
        raw_needles = [query] if str(query or '').strip() else []
    raw_needles = [str(n).replace('\r\n', '\n') for n in raw_needles]
    if not raw_needles:
        return results, False
    keys = [n.lower() if case_insensitive else n for n in raw_needles]
    tagged = needles is not None
    counts = [0] * len(raw_needles)
    truncated = False
    skip = tuple(p.replace('\\', '/').lstrip('/')
                 for p in (exclude_rel_prefixes or ()) if p)
    for dirpath, dirnames, filenames in os.walk(project_root_abs):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith('.'))
        for fname in sorted(filenames):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in SEARCH_EXTS:
                continue
            abs_path = os.path.join(dirpath, fname)
            rel = os.path.relpath(abs_path, project_root_abs).replace(os.sep, '/')
            # v105.10: отсев ДО чтения файла и ДО набора квоты max_results
            if skip and rel.lstrip('/').startswith(skip):
                continue
            try:
                with open(abs_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                    lines = f.read().replace('\r\n', '\n').split('\n')
            except Exception:
                continue
            godot_path = 'res://' + rel
            haystack = [ln.lower() for ln in lines] if case_insensitive else lines
            for ni, needle in enumerate(keys):
                if counts[ni] >= max_results:
                    continue  # эта подстрока уже набрала свою квоту
                hits = [idx for idx, line in enumerate(haystack) if needle in line]
                if not hits:
                    continue
            # v105.12 (раунд 4, п.2): соседние совпадения давали почти
            # одинаковые сниппеты: ключ дедупликации выше по стеку — (path, line),
            # а окно контекста шире одной строки. var health / var health_max /
            # var health_bar подряд съедали три слота бюджета, повторяя друг друга.
            # Склеиваем совпадения, попавшие в окно ±context_lines, в один сниппет.
            # При context_lines=0 разница между соседними строками (1) уже больше
            # окна, поэтому склейки не происходит вообще — CALLERS и SIGNALS,
            # которые ходят с context_lines=0 и рассчитывают на отдельную строку
            # на каждый вызов, работают точно как раньше.
                groups = []
                for idx in hits:
                    if groups and context_lines > 0 and idx - groups[-1][-1] <= context_lines:
                        groups[-1].append(idx)
                    else:
                        groups.append([idx])
                for grp in groups:
                    lo = max(0, grp[0] - context_lines)
                    hi = min(len(lines), grp[-1] + context_lines + 1)
                    snippet = '\n'.join('%d: %s' % (n + 1, lines[n]) for n in range(lo, hi))
                # 'line' — первое совпадение группы: так вывод остаётся
                # стабильным и сортируется по (path, line) как раньше.
                    row = {'path': godot_path, 'line': grp[0] + 1, 'snippet': snippet}
                    if tagged:
                        row['needle'] = raw_needles[ni]
                    results.append(row)
                    counts[ni] += 1
                    if counts[ni] >= max_results:
                        # Одиночный поиск выходил сразу по квоте — сохраняем то же
                        # поведение; при списке ждём, пока квоту наберут все.
                        truncated = True
                        if all(c >= max_results for c in counts):
                            return results, True
                        break
    return results, truncated

def describe_scene(project_root, godot_path, max_chars=12000):
    """Краткая структура сцены .tscn для модели: дерево узлов (имя, тип),
    прикреплённые скрипты, инстансы других сцен и связи сигналов."""
    import re
    abs_path = _resolve_safe_path(project_root, godot_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError("Файл не найден: %s" % godot_path)
    if os.path.splitext(abs_path)[1].lower() not in (".tscn", ".scn"):
        raise ValueError("list_scene работает только со сценами .tscn: %s" % godot_path)
    with open(abs_path, "r", encoding="utf-8-sig", errors="replace") as f:
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
            if f in EXCLUDED_FILES or _is_generated_sidecar(f):
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
            if f in EXCLUDED_FILES or _is_generated_sidecar(f):
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
    """После откатов/удаления файлов убирает из project.godot записи секции
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


HASH_MAX_BYTES = 8 * 1024 * 1024  # файлы крупнее не хэшируются (сравнение по mtime+size)


def _file_digest(abs_path, size):
    """v88.5: md5 содержимого (hex) или None для слишком больших файлов."""
    if size > HASH_MAX_BYTES:
        return None
    import hashlib
    h = hashlib.md5()
    try:
        with open(abs_path, 'rb') as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b''):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def snapshot_files(project_root, prev=None):
    """Отпечаток файлов проекта — для обнаружения изменений, сделанных ВНЕ
    агента (пользователь удалил/поменял файлы руками).

    v88.5: значение — (mtime, size, md5_содержимого). Хэш нужен, чтобы НЕ
    считать файл изменённым, когда поменялось только время правки: Godot
    пересохраняет открытую сцену (.tscn) с тем же содержимым, и раньше это
    давало ложное «файл ИЗМЕНИЛСЯ вне диалога» с просьбой перечитать.
    Дорогое хэширование не повторяется зря: если передан prev (прошлый
    снапшот) и mtime+size файла не менялись — хэш берётся из prev."""
    project_root = os.path.abspath(project_root)
    prev = prev or {}
    snap = {}
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith('.'))
        for f in filenames:
            if f in EXCLUDED_FILES or _is_generated_sidecar(f):
                continue
            abs_path = os.path.join(dirpath, f)
            try:
                st = os.stat(abs_path)
            except OSError:
                continue
            rel = os.path.relpath(abs_path, project_root).replace(os.sep, '/')
            mtime, size = int(st.st_mtime), int(st.st_size)
            old = prev.get(rel)
            if old is not None and len(old) > 2 and old[0] == mtime and old[1] == size:
                digest = old[2]  # mtime+size не менялись — верим прошлому хэшу
            else:
                digest = _file_digest(abs_path, size)
            snap[rel] = (mtime, size, digest)
    return snap


def _entry_content_differs(old_e, new_e):
    """v88.5: изменение = другое СОДЕРЖИМОЕ. Если у обеих записей есть хэш —
    сравниваем хэши (mtime игнорируется: пересохранение без правок, как Godot
    делает с открытой сценой, — НЕ изменение). Без хэша (слишком большой файл
    или снапшот старого формата) — как раньше, по mtime+size."""
    old_h = old_e[2] if len(old_e) > 2 else None
    new_h = new_e[2] if len(new_e) > 2 else None
    if old_h is not None and new_h is not None:
        return old_h != new_h
    return tuple(old_e[:2]) != tuple(new_e[:2])


def diff_snapshots(old, new):
    """Сравнение двух снапшотов: (добавлены, изменены, удалены)."""
    added = sorted(set(new) - set(old))
    deleted = sorted(set(old) - set(new))
    changed = sorted(p for p in new if p in old and _entry_content_differs(old[p], new[p]))
    return added, changed, deleted


def format_fs_changes(added, changed, deleted, limit=12, diffs=None):
    """Сообщение модели о внешних изменениях файлов (или "" если их нет).
    diffs: {rel_path: (diff_text, n_lines)} — точечные diff для изменённых
    файлов, чьё старое содержимое модель уже видела: ей НЕ нужно
    перечитывать весь файл заново (экономия токенов)."""
    # Filter defensively as callers may still hold snapshots made before
    # generated Godot sidecars were excluded from snapshot_files().
    added = [p for p in added if not _is_generated_sidecar(p)]
    changed = [p for p in changed if not _is_generated_sidecar(p)]
    deleted = [p for p in deleted if not _is_generated_sidecar(p)]
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


# ---------------------------------------------------------------------------
# Структурный дифф для карточки предпросмотра в панели Godot.
#
# Модели уходит ТЕКСТОВЫЙ unified-diff (unified_diff_text выше) — ей так
# привычнее. Панели текст не годится: чтобы красить строки и показывать номера,
# ей пришлось бы парсить diff на GDScript. Поэтому здесь дифф отдаётся уже
# разобранным: список [пометка, номер_старой, номер_новой, текст].
#
# Пометки: "+" добавлено, "-" удалено, " " контекст, "@" заголовок куска.
# ---------------------------------------------------------------------------

DIFF_PREVIEW_MAX_LINES = 600


def build_diff_preview(old_text, new_text, context=3, max_lines=DIFF_PREVIEW_MAX_LINES):
    """Структурный дифф для панели или None, если изменений нет.

    old_text=None означает «файла не было» — тогда весь новый текст помечается
    как добавленный (иначе пустая строка «до» превратилась бы в удалённую).
    Счётчики added/removed считаются по ПОЛНОМУ диффу, даже если список строк
    обрезан по max_lines: статистика в шапке карточки должна быть честной."""
    import difflib
    new_lines = _split_lines(new_text)
    if old_text is None:
        head = new_lines[:max_lines]
        return {
            "lines": [["+", None, i + 1, text] for i, text in enumerate(head)],
            "added": len(new_lines),
            "removed": 0,
            "truncated": len(new_lines) > len(head),
        }
    old_lines = _split_lines(old_text)
    if old_lines == new_lines:
        return None
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    out = []
    added = 0
    removed = 0
    for group in matcher.get_grouped_opcodes(context):
        first = group[0]
        last = group[-1]
        old_from, old_len = first[1] + 1, last[2] - first[1]
        new_from, new_len = first[3] + 1, last[4] - first[3]
        out.append(["@", old_from, new_from,
                    "@@ -%d,%d +%d,%d @@" % (old_from, old_len, new_from, new_len)])
        for tag, a1, a2, b1, b2 in group:
            if tag == "equal":
                for k in range(a1, a2):
                    out.append([" ", k + 1, b1 + (k - a1) + 1, old_lines[k]])
                continue
            if tag in ("replace", "delete"):
                for k in range(a1, a2):
                    out.append(["-", k + 1, None, old_lines[k]])
                    removed += 1
            if tag in ("replace", "insert"):
                for k in range(b1, b2):
                    out.append(["+", None, k + 1, new_lines[k]])
                    added += 1
    truncated = len(out) > max_lines
    return {
        "lines": out[:max_lines] if truncated else out,
        "added": added,
        "removed": removed,
        "truncated": truncated,
    }


def _split_lines(text):
    """Строки файла без «хвостовой пустышки».

    'a\\nb\\n'.split('\\n') даёт ['a', 'b', ''] — этот пустой элемент существует
    только из-за перевода строки в конце файла. В диффе он выглядел как лишняя
    добавленная/удалённая строка и врал в счётчике «+N»."""
    body = (text or '').replace('\r\n', '\n')
    lines = body.split('\n')
    if len(lines) > 1 and lines[-1] == '':
        lines.pop()
    return lines


def action_diff_preview(project_root, action):
    """Дифф предлагаемого write-действия для карточки подтверждения, или None.

    Показывается ДО применения, поэтому ничего не пишет на диск: для patch_file
    замена считается в памяти той же функцией, что и настоящий патч. Если патч
    не сойдётся с диском (блок не найден/не уникален), возвращается None —
    панель молча покажет прежний предпросмотр кода, а несовпадение и так
    всплывёт при применении понятной ошибкой."""
    if not isinstance(action, dict) or not project_root:
        return None
    act = action.get("action")
    path = action.get("path", "")
    if not path:
        return None
    try:
        if act == "patch_file":
            old_text, new_text = patch_result_text(
                project_root, path, action.get("search", "") or "", action.get("replace", "") or "")
            preview = build_diff_preview(old_text, new_text)
        elif act == "create_file":
            content = action.get("content", "")
            if not isinstance(content, str):
                return None
            abs_path = _resolve_safe_path(project_root, path)
            old_text = None
            if os.path.isfile(abs_path):
                # Существующий файл create_file ПЕРЕЗАПИСЫВАЕТ целиком —
                # человеку важнее всего увидеть, что при этом потеряется.
                with open(abs_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                    old_text = f.read()
            new_text = sanitize_llm_text(content.replace('\r\n', '\n')) or ''
            preview = build_diff_preview(old_text, new_text)
        else:
            return None
    except Exception:
        return None
    if not preview:
        return None
    preview["path"] = path
    preview["action"] = act
    return preview
