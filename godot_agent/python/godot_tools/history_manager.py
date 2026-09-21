import os
import json
import time
import uuid
import shutil
import hashlib
import tempfile
import threading
from functools import wraps

from project_tools import _resolve_safe_path

# ---------------------------------------------------------------------------
# Журнал изменений агента (многоуровневый откат вместо одноразового .bak).
#
# Структура в корне проекта:
#   .agent_history/
#       journal.json        — список записей (стек изменений)
#       snapshots/          — копии файлов "до" изменения (для patch_file)
#
# Каждое write-действие проходит две фазы:
#   1) record_change()  — ДО применения: снапшот + запись в журнал
#   2) commit_change()  — ПОСЛЕ успешного применения: хэш результата
# Если применение упало — abort_change() убирает запись.
#
# Откат (rollback_last) — это стек: каждый вызов откатывает одно последнее
# применённое действие. Если файл менялся ПОСЛЕ действия агента (руками или
# другим патчем) — откат требует подтверждения (force=True).
# ---------------------------------------------------------------------------

HISTORY_DIR_NAME = ".agent_history"
MAX_ENTRIES = 50

# Если задан set_storage_dir(), журнал и снапшоты живут ВНЕ проекта
# (в папке user:// данных Godot) — их не видит ни сканер редактора,
# ни git, ни модель, и обновление плагина их не задевает.
_STORAGE_OVERRIDE = None

# Максимальный размер search/replace, который храним в журнале ради
# точного диффа отката. Больше — не храним (модель просто перечитает файл).
MAX_DIFF_CHARS = 4000

_JOURNAL_LOCKS = {}
_JOURNAL_LOCKS_GUARD = threading.Lock()


def _journal_transaction(function):
    """Serialize complete transactions, including nested recovery calls."""
    @wraps(function)
    def locked(project_root, *args, **kwargs):
        if not project_root:
            return function(project_root, *args, **kwargs)
        identity = os.path.normcase(os.path.realpath(_journal_path(project_root)))
        with _JOURNAL_LOCKS_GUARD:
            lock = _JOURNAL_LOCKS.setdefault(identity, threading.RLock())
        with lock:
            return function(project_root, *args, **kwargs)
    return locked


def new_chain_id():
    """Новый идентификатор цепочки для plan-режима: все шаги одного плана
    записываются в журнал с одним chain_id, чтобы rollback_chain мог откатить их
    все сразу как одну операцию."""
    return uuid.uuid4().hex[:12]


def set_storage_dir(base_dir):
    """Включает хранение журнала/снапшотов вне проекта: <base_dir>/agent_history."""
    global _STORAGE_OVERRIDE
    _STORAGE_OVERRIDE = os.path.join(os.path.abspath(base_dir), "agent_history")


def get_storage_dir(project_root):
    """Абсолютный путь к папке хранения (журнал, снапшоты, служебные файлы)."""
    return _history_dir(project_root)


@_journal_transaction
def migrate_from_project(project_root):
    """Одноразовый перенос старой .agent_history из корня проекта в новое
    хранилище (user://). Возвращает True, если перенос был выполнен."""
    if not _STORAGE_OVERRIDE or not project_root:
        return False
    old = os.path.join(os.path.abspath(project_root), HISTORY_DIR_NAME)
    old_journal = os.path.join(old, "journal.json")
    if not os.path.isfile(old_journal):
        return False
    if os.path.isfile(os.path.join(_STORAGE_OVERRIDE, "journal.json")):
        return False  # в новом месте уже есть своя история — старую не трогаем
    os.makedirs(os.path.join(_STORAGE_OVERRIDE, "snapshots"), exist_ok=True)
    shutil.move(old_journal, os.path.join(_STORAGE_OVERRIDE, "journal.json"))
    old_snaps = os.path.join(old, "snapshots")
    if os.path.isdir(old_snaps):
        for name in os.listdir(old_snaps):
            shutil.move(os.path.join(old_snaps, name),
                        os.path.join(_STORAGE_OVERRIDE, "snapshots", name))
    shutil.rmtree(old, ignore_errors=True)
    return True


def _history_dir(project_root):
    d = _STORAGE_OVERRIDE or os.path.join(os.path.abspath(project_root), HISTORY_DIR_NAME)
    os.makedirs(os.path.join(d, "snapshots"), exist_ok=True)
    return d


def _journal_path(project_root):
    return os.path.join(_history_dir(project_root), "journal.json")


@_journal_transaction
def _load_journal(project_root):
    path = _journal_path(project_root)
    try:
        with open(path, "r", encoding="utf-8") as f:
            journal = json.load(f)
    except FileNotFoundError:
        # A dangling link is an existing, unreadable journal, not empty history.
        if os.path.lexists(path):
            raise
        return []
    if not isinstance(journal, list) or any(
            not isinstance(entry, dict)
            or any(not isinstance(entry.get(key), str) for key in ("id", "type", "path"))
            or not isinstance(entry.get("committed"), bool)
            for entry in journal):
        raise ValueError("Invalid history journal: expected a list of change entries")
    return journal


@_journal_transaction
def _save_journal(project_root, journal):
    path = _journal_path(project_root)
    fd, tmp = tempfile.mkstemp(prefix=".journal-", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(journal, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _file_hash(abs_path):
    if not os.path.isfile(abs_path):
        return None
    with open(abs_path, "rb") as f:
        data = f.read()
    # Сравниваем без учёта типа переносов строк: редактор Godot сохраняет LF,
    # а запись из Windows-Python могла дать CRLF. Смена только переносов —
    # ЭТО НЕ правка пользователя, она не должна требовать force-откат.
    data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


@_journal_transaction
def _prune(project_root, journal):
    """Cap committed history only; persist before deleting retired snapshots."""
    excess = max(0, sum(bool(entry.get("committed")) for entry in journal) - MAX_ENTRIES)
    removed = []
    retained = []
    for entry in journal:
        if entry.get("committed") and len(removed) < excess:
            removed.append(entry)
        else:
            retained.append(entry)
    _save_journal(project_root, retained)
    journal[:] = retained
    for old in removed:
        snapshots = [old.get("snapshot")] + [f.get("snapshot") for f in old.get("files", [])]
        for snap in snapshots:
            if not snap:
                continue
            try:
                os.remove(os.path.join(_history_dir(project_root), snap))
            except OSError:
                pass


@_journal_transaction
def forget_chat(project_root, chat_id):
    """Убирает связь журнала отката с удалённым чатом, сохраняя сам откат.

    Снапшоты и описание файлового действия нужны пользователю независимо от
    жизни чата. Название и id чата после удаления больше не нужны и не должны
    оставаться в служебном журнале.
    """
    cid = str(chat_id or "").strip()
    if not project_root or not cid:
        return 0
    journal = _load_journal(project_root)
    changed = 0
    for entry in journal:
        if str(entry.get("chat_id") or "") != cid:
            continue
        entry.pop("chat_id", None)
        entry.pop("chat_title", None)
        changed += 1
    if changed:
        _save_journal(project_root, journal)
    return changed


@_journal_transaction
def record_change(project_root, action, chat_id=None, chat_title=None, chain_id=None):
    """Вызывать ДО применения write-действия. Возвращает id записи журнала.
    chat_id/chat_title — какой чат сделал изменение: нужно для предпросмотра
    отката и для сводки «что изменилось» при возврате в старый чат.
    chain_id — общий идентификатор цепочки для шагов plan-режима (см. new_chain_id);
    обычные одиночные действия его не задают."""
    journal = _load_journal(project_root)
    act = action.get("action")
    path = action.get("path", "")
    entry = {
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "type": act,
        "path": path,
        "committed": False,
    }
    if chat_id:
        entry["chat_id"] = chat_id
        entry["chat_title"] = chat_title or ""
    if chain_id:
        entry["chain_id"] = chain_id
    hist = _history_dir(project_root)

    if act == "patch_file":
        abs_path = _resolve_safe_path(project_root, path)
        snap_rel = os.path.join("snapshots", entry["id"] + "_before")
        shutil.copy2(abs_path, os.path.join(hist, snap_rel))
        entry["snapshot"] = snap_rel
        # Сохраняем сам дифф: при откате можно будет точно сказать модели,
        # что именно вернулось, без повторного чтения файла целиком.
        search = action.get("search") or ""
        replace = action.get("replace") or ""
        if len(search) <= MAX_DIFF_CHARS and len(replace) <= MAX_DIFF_CHARS:
            entry["search"] = search
            entry["replace"] = replace
    elif act == "move_file":
        entry["dest"] = action.get("dest", "")
    elif act == "create_file":
        # Если файл уже существует, create_file работает как ПОЛНАЯ перезапись:
        # снимаем снапшот старой версии, чтобы откат вернул её, а не удалял файл.
        abs_path = _resolve_safe_path(project_root, path)
        if os.path.isfile(abs_path):
            snap_rel = os.path.join("snapshots", entry["id"] + "_before")
            shutil.copy2(abs_path, os.path.join(hist, snap_rel))
            entry["snapshot"] = snap_rel
            entry["overwrote"] = True

    journal.append(entry)
    try:
        _save_journal(project_root, journal)
    except Exception:
        if entry.get("snapshot"):
            try:
                os.remove(os.path.join(hist, entry["snapshot"]))
            except OSError:
                pass
        raise
    return entry["id"]


@_journal_transaction
def record_batch_change(project_root, action_type, paths, chat_id=None, chat_title=None,
                        states=None):
    """Create one journal entry and one before-snapshot per affected file."""
    journal = _load_journal(project_root)
    unique_paths = [str(path) for path in paths if path]
    if not unique_paths:
        raise ValueError("Пакетное изменение не содержит файлов")
    identities = [_path_identity(project_root, path) for path in unique_paths]
    if len(set(identities)) != len(identities):
        raise ValueError("Batch change contains duplicate physical paths")
    entry = {"id": uuid.uuid4().hex[:12], "ts": time.time(),
             "type": action_type, "path": unique_paths[0],
             "paths": unique_paths, "files": [], "committed": False}
    if chat_id:
        entry["chat_id"] = chat_id
        entry["chat_title"] = chat_title or ""
    hist = _history_dir(project_root)
    try:
        state_by_path = {item["path"]: item for item in (states or [])}
        for index, path in enumerate(unique_paths):
            absolute = _resolve_safe_path(project_root, path)
            state = state_by_path.get(path)
            before_present = bool(state.get("before_bytes") is not None) if state else os.path.isfile(absolute)
            after_present = bool(state.get("after_bytes") is not None) if state else True
            if not before_present and state is None:
                raise FileNotFoundError(path)
            item = {"path": path, "before_present": before_present,
                    "after_present": after_present}
            if state and state.get("case_only_dest"):
                item["case_only_dest"] = state["case_only_dest"]
            if before_present:
                snap_rel = os.path.join("snapshots", "%s_%d_before" % (entry["id"], index))
                shutil.copy2(absolute, os.path.join(hist, snap_rel))
                item["snapshot"] = snap_rel
            entry["files"].append(item)
        journal.append(entry)
        _save_journal(project_root, journal)
    except Exception:
        for item in entry["files"]:
            if not item.get("snapshot"):
                continue
            try:
                os.remove(os.path.join(hist, item["snapshot"]))
            except OSError:
                pass
        raise
    return entry["id"]


@_journal_transaction
def commit_change(project_root, entry_id):
    """Вызывать ПОСЛЕ успешного применения — фиксирует хэш результата."""
    journal = _load_journal(project_root)
    for e in journal:
        if e["id"] == entry_id:
            if e.get("files"):
                for item in e["files"]:
                    item["after_hash"] = _file_hash(
                        _resolve_safe_path(project_root, item["path"]))
                    item["after_present"] = item["after_hash"] is not None
            else:
                target = e.get("dest") or e["path"]
                e["after_hash"] = _file_hash(_resolve_safe_path(project_root, target))
            e["committed"] = True
            break
    _prune(project_root, journal)


@_journal_transaction
def abort_change(project_root, entry_id):
    """Если применение упало с ошибкой — убираем запись из журнала,
    чтобы не пытаться откатывать то, чего не было."""
    journal = _load_journal(project_root)
    removed = [e for e in journal if e["id"] == entry_id]
    new_journal = [e for e in journal if e["id"] != entry_id]
    if len(new_journal) != len(journal):
        _save_journal(project_root, new_journal)
    for entry in removed:
        snapshot = entry.get("snapshot")
        if snapshot:
            try:
                os.remove(os.path.join(_history_dir(project_root), snapshot))
            except OSError:
                pass
        for item in entry.get("files", []):
            try:
                os.remove(os.path.join(_history_dir(project_root), item.get("snapshot", "")))
            except OSError:
                pass


@_journal_transaction
def restore_reserved_change(project_root, entry_id, current_hash=None,
                            remove_created=False):
    """Restore an uncommitted batch reservation after an editor-side failure.

    The caller may provide the hash reported by Godot. If the file has changed
    again since that report, recovery refuses to overwrite it and keeps the
    reservation/snapshot for manual resolution.
    """
    journal = _load_journal(project_root)
    entry = next((item for item in journal if item.get("id") == entry_id), None)
    if entry is None:
        return False, "Резерв истории не найден", []
    if entry.get("committed"):
        return False, "Изменение уже зафиксировано", []
    files = entry.get("files") or []
    if len(files) != 1:
        return False, "Восстановление editor-транзакции ожидает один файл", []
    item = files[0]
    absolute = _resolve_safe_path(project_root, item["path"])
    # Editor reports hash exact bytes, unlike newline-tolerant rollback checks.
    observed_hash = None
    if os.path.lexists(absolute):
        if not os.path.isfile(absolute) or os.path.islink(absolute):
            return False, "Целевой путь изменился; снапшот сохранён", []
        with open(absolute, "rb") as source:
            observed_hash = hashlib.sha256(source.read()).hexdigest()
    if current_hash and observed_hash != current_hash:
        return False, "Файл изменился после отчёта редактора; снапшот сохранён", []
    if not item.get("before_present", True):
        if os.path.exists(absolute):
            if not remove_created:
                abort_change(project_root, entry_id)
                return True, "Внешний файл сохранён; агент не записывал целевой путь", []
            if not current_hash:
                return False, "Созданный файл не подтверждён хэшем; резерв истории сохранён", []
            try:
                os.remove(absolute)
            except OSError as exc:
                return False, "Не удалось удалить незавершённый созданный файл: %s" % exc, []
        abort_change(project_root, entry_id)
        return True, "Незавершённый созданный файл удалён", [item["path"]]
    if observed_hash is not None and not current_hash:
        return False, "Нет хэша отчёта редактора; существующий файл и снапшот сохранены", []
    snapshot = os.path.join(_history_dir(project_root), item.get("snapshot", ""))
    if not os.path.isfile(snapshot):
        return False, "Снапшот editor-транзакции не найден", []
    parent = os.path.dirname(absolute)
    fd, temporary = tempfile.mkstemp(prefix=".agent_scene_restore_", dir=parent)
    try:
        with os.fdopen(fd, "wb") as output, open(snapshot, "rb") as source:
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
        # Snapshot preparation can take time. Refuse a newly changed target.
        if os.path.lexists(absolute):
            if not os.path.isfile(absolute) or os.path.islink(absolute):
                return False, "Целевой путь изменился во время восстановления", []
            with open(absolute, "rb") as target:
                latest_hash = hashlib.sha256(target.read()).hexdigest()
        else:
            latest_hash = None
        if latest_hash != observed_hash:
            return False, "Файл изменился во время восстановления; снапшот сохранён", []
        os.replace(temporary, absolute)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass
    abort_change(project_root, entry_id)
    return True, "Исходный файл editor-транзакции восстановлен", [item["path"]]


def _entry_public_info(entry, committed):
    """Описание записи журнала для предпросмотра отката в панели."""
    info = {
        "id": entry.get("id", ""),
        "type": entry.get("type", ""),
        "path": entry.get("dest") or entry.get("path", ""),
        "overwrote": bool(entry.get("overwrote")),
        "chat_title": entry.get("chat_title") or "",
        "ts": entry.get("ts", 0),
        "chain_id": "",
        "chain_total": 0,
        "paths": entry.get("paths") or [entry.get("dest") or entry.get("path", "")],
    }
    chain_id = entry.get("chain_id")
    if chain_id:
        info["chain_id"] = chain_id
        info["chain_total"] = sum(
            1 for j in committed if j.get("chain_id") == chain_id)
    return info


def last_committed_info(project_root):
    """Описание последнего применённого действия — для предпросмотра отката
    в панели (что именно будет отменено и из какого чата). Если последнее
    действие — шаг плана (есть chain_id), дополнительно возвращает chain_id и chain_total
    (сколько ещё неоткатанных шагов этой цепочки сейчас в журнале) — панель использует
    это, чтобы предложить откат всей цепочки одной кнопкой вместо одиночного отката."""
    journal = _load_journal(project_root)
    committed = [e for e in journal if e.get("committed")]
    if not committed:
        return None
    return _entry_public_info(committed[-1], committed)


def _requested_case_path(project_root, godot_path):
    """Absolute path preserving the caller's letter case (realpath would
    collapse it to the on-disk casing on Windows)."""
    rel = str(godot_path or "").removeprefix("res://").replace(chr(92), "/").strip("/")
    return os.path.join(os.path.realpath(project_root), *rel.split("/"))


def _path_identity(project_root, path):
    return os.path.normcase(os.path.realpath(_resolve_safe_path(project_root, path)))


def _entry_path_identities(project_root, entry):
    paths = [entry.get("path"), entry.get("dest")]
    paths.extend(entry.get("paths") or [])
    paths.extend(item.get("path") for item in entry.get("files", []))
    return {_path_identity(project_root, path) for path in paths if path}


@_journal_transaction
def entry_info(project_root, entry_id):
    """Описание КОНКРЕТНОЙ записи журнала по её id.

    Нужно адресному откату «по этому сообщению»: раньше панель умела просить
    только «откатить последнее», из-за чего кнопка на старом облачке чата
    отменяла чужое, самое свежее изменение.

    Дополнительно сообщает, что мешает откату именно этой записи:
      newer_same_file — сколько ПОЗДНЕЙШИХ действий агента трогали тот же файл
                        (откатывать через них нельзя: потеряется их работа);
      is_last         — эта запись самая свежая в журнале.
    """
    journal = _load_journal(project_root)
    committed = [e for e in journal if e.get("committed")]
    entry, idx = _find_committed(committed, entry_id)
    if entry is None:
        return None
    info = _entry_public_info(entry, committed)
    info["is_last"] = (idx == len(committed) - 1)
    targets = _entry_path_identities(project_root, entry)
    blockers = []
    for later in committed[idx + 1:]:
        later_paths = _entry_path_identities(project_root, later)
        if targets.intersection(later_paths):
            blockers.append({"type": later.get("type", ""),
                             "path": later.get("dest") or later.get("path", ""),
                             "ts": later.get("ts", 0)})
    info["newer_same_file"] = blockers
    return info


def _find_committed(committed, entry_id):
    """(запись, индекс в списке committed) по id или (None, -1)."""
    for i, e in enumerate(committed):
        if e.get("id") == entry_id:
            return e, i
    return None, -1


@_journal_transaction
def _drop_entry(project_root, journal, entry):
    """Убирает запись и её снапшот. Вызывается только после успешного отката."""
    snap_rel = entry.get("snapshot")
    journal.remove(entry)
    _save_journal(project_root, journal)
    if snap_rel:
        try:
            os.remove(os.path.join(_history_dir(project_root), snap_rel))
        except OSError:
            pass
    for item in entry.get("files", []):
        try:
            os.remove(os.path.join(_history_dir(project_root), item.get("snapshot", "")))
        except OSError:
            pass


@_journal_transaction
def rollback_entry(project_root, entry_id, force=False):
    """Откат КОНКРЕТНОГО действия по id записи журнала.

    Отличие от rollback_last: откатывается ровно то, что попросили, а не
    «самое свежее». Именно этого не хватало кнопке отката на карточке
    сообщения — без адреса она отменяла последнее изменение проекта, каким бы
    оно ни было и из какого чата ни пришло.

    ОТКАЗ ВМЕСТО ПРИНУЖДЕНИЯ. Если тот же файл позже правил САМ АГЕНТ, откат
    через эти правки молча потерял бы их работу. Такой откат не разрешается
    даже с force: сначала надо откатить более свежие действия. force остаётся
    только для случая, когда файл менялся ВРУЧНУЮ (это решает пользователь).

    Возвращает (ok, message, needs_force, paths, diff) — та же семантика, что
    у rollback_last.
    """
    journal = _load_journal(project_root)
    committed = [e for e in journal if e.get("committed")]
    entry, idx = _find_committed(committed, entry_id)
    if entry is None:
        return False, ("Это изменение уже не найдено в журнале — возможно, оно "
                       "уже откачено или вытеснено по лимиту истории."), False, [], None

    targets = _entry_path_identities(project_root, entry)
    blockers = [e for e in committed[idx + 1:]
                if targets.intersection(_entry_path_identities(project_root, e))]
    if blockers:
        return False, (
            "Этот файл (%s) агент правил ещё %d раз(а) ПОСЛЕ этого действия. "
            "Откатить его сейчас — значит потерять более свежие правки. "
            "Сначала откатите их: откат идёт от новых к старым."
            % (", ".join(entry.get("paths") or [entry.get("dest") or entry["path"]]), len(blockers))
        ), False, [], None

    ok, message, needs_force, affected, diff = _revert_entry_on_disk(
        project_root, entry, force=force)
    if not ok:
        return False, message, needs_force, affected, diff
    _drop_entry(project_root, journal, entry)
    return True, message, False, affected, diff


@_journal_transaction
def rollback_last(project_root, force=False):
    """Откат последнего применённого действия.
    Возвращает (ok, message, needs_force, paths, diff):
      paths — затронутые res:// пути (для синхронизации вкладок в Godot);
      diff  — для patch_file: {"path", "was", "now"} — точный обратный дифф
              (блок "was" снова стал блоком "now"), иначе None."""
    journal = _load_journal(project_root)
    committed = [e for e in journal if e.get("committed")]
    if not committed:
        return False, "История изменений пуста — откатывать нечего.", False, [], None
    entry = committed[-1]

    ok, message, needs_force, affected, diff = _revert_entry_on_disk(project_root, entry, force=force)
    if not ok:
        return False, message, needs_force, affected, diff

    # Убираем запись и её снапшот только после успешного отката.
    _drop_entry(project_root, journal, entry)
    return True, message, False, affected, diff


def last_write_ts_by_others(project_root, path, chat_id):
    """Когда файл в последний раз меняли ДРУГИЕ чаты (0 — не меняли).
    Записи без chat_id (сделанные до обновления) не учитываются,
    чтобы не блокировать старые проекты ложными срабатываниями."""
    identity = _path_identity(project_root, path)
    ts = 0
    for e in _load_journal(project_root):
        if not e.get("committed"):
            continue
        if identity not in _entry_path_identities(project_root, e):
            continue
        eid = e.get("chat_id")
        if not eid or eid == chat_id:
            continue
        ts = max(ts, e.get("ts", 0))
    return ts


def summarize_changes_since(project_root, since_ts, exclude_chat_id=None,
                            max_lines=12, collapse_after=30):
    """Компактная сводка изменений проекта после since_ts — для заметки
    модели при возврате в старый чат. None — если изменений не было.
    Защита от «полотна»: группируем по ФАЙЛАМ (не по действиям),
    максимум max_lines строк; если файлов больше collapse_after —
    вместо списка один короткий абзац «проект сильно изменился»."""
    per_file = {}
    order = []
    for e in _load_journal(project_root):
        if not e.get("committed") or e.get("ts", 0) <= since_ts:
            continue
        if exclude_chat_id and e.get("chat_id") == exclude_chat_id:
            continue
        targets = e.get("paths") or [e.get("dest") or e.get("path") or ""]
        for target in targets:
            if not target:
                continue
            rec = per_file.get(target)
            if rec is None:
                rec = {"n": 0, "last": "", "chats": set()}
                per_file[target] = rec
                order.append(target)
            rec["n"] += 1
            rec["last"] = e.get("type", "")
            title = (e.get("chat_title") or "").strip()
            if title:
                rec["chats"].add(title)
    if not per_file:
        return None
    total_files = len(per_file)
    total_changes = sum(r["n"] for r in per_file.values())
    # Журнал хранит не больше MAX_ENTRIES записей, поэтому «как минимум».
    if total_files > collapse_after:
        return ("[Система]: ВНИМАНИЕ. С момента твоей последней активности проект СИЛЬНО изменился "
                "(как минимум %d изменений в %d файлах, в том числе из других чатов). "
                "Твоя память о содержимом файлов и структуре проекта УСТАРЕЛА. "
                "Перед любыми правками сначала запроси list_files, а каждый нужный файл перечитай через read_file."
                % (total_changes, total_files))
    kind_ru = {"create_file": "создан/перезаписан", "patch_file": "изменён",
                "move_file": "перемещён", "rename_symbol": "переименован символ",
                 "edit_scene": "структурно изменена сцена", "create_scene": "создана сцена",
                 "edit_project_settings": "изменены настройки проекта",
                 "edit_resource": "структурно изменён ресурс",
                 "transaction": "применена пакетная транзакция"}
    lines = []
    for p in order[:max_lines]:
        r = per_file[p]
        what = kind_ru.get(r["last"], r["last"])
        extra = " \u00d7%d" % r["n"] if r["n"] > 1 else ""
        by = (" [чат: %s]" % ", ".join(sorted(r["chats"]))) if r["chats"] else ""
        lines.append("- %s — %s%s%s" % (p, what, extra, by))
    if total_files > max_lines:
        lines.append("- …и ещё %d файлов." % (total_files - max_lines))
    return ("[Система]: Пока этот чат был неактивен, в проекте изменились файлы:\n%s\n"
            "Твоя память об их содержимом устарела: перед patch_file или create_file по этим файлам "
            "сначала перечитай их через read_file." % "\n".join(lines))


def _clean_empty_dirs(start_dir, stop_root):
    """Remove empty parent directories up to (but excluding) stop_root."""
    try:
        cur = os.path.abspath(start_dir)
        root = os.path.abspath(stop_root)
        while cur and cur != root and os.path.commonpath([cur, root]) == root:
            if not os.listdir(cur):
                os.rmdir(cur)
                cur = os.path.dirname(cur)
            else:
                break
    except (OSError, ValueError):
        pass


def _revert_entry_on_disk(project_root, entry, force=False):
    """Общая логика отката ОДНОЙ записи журнала НА ДИСКЕ. Не трогает
    сам журнал/снапшоты — только применяет изменения к файлам. Используется
    и для одиночного rollback_last, и для каждого шага в rollback_chain.
    Возвращает (ok, message, needs_force, paths, diff) — та же семантика,
    что раньше возвращал rollback_last целиком."""
    act = entry["type"]
    if entry.get("files"):
        files = entry["files"]
        for item in files:
            absolute = _resolve_safe_path(project_root, item["path"])
            if not force and _file_hash(absolute) != item.get("after_hash"):
                return False, (
                    "Файл %s изменялся ПОСЛЕ этого действия агента. Откат перезапишет "
                    "эти изменения. Нажмите откат ещё раз для подтверждения." % item["path"]
                ), True, [], None
            snapshot = os.path.join(_history_dir(project_root), item.get("snapshot", ""))
            if item.get("before_present", True) and not os.path.isfile(snapshot):
                return False, "Снапшот для отката не найден: %s" % item["path"], False, [], None
        current = {}
        temps = {}
        restored = []
        try:
            for item in files:
                absolute = _resolve_safe_path(project_root, item["path"])
                current[item["path"]] = (os.path.isfile(absolute), None)
                if os.path.isfile(absolute):
                    with open(absolute, "rb") as handle:
                        current[item["path"]] = (True, handle.read())
                if item.get("before_present", True) and not item.get("case_only_dest"):
                    snapshot = os.path.join(_history_dir(project_root), item["snapshot"])
                    parent_dir = os.path.dirname(absolute)
                    os.makedirs(parent_dir, exist_ok=True)
                    descriptor, temp_path = tempfile.mkstemp(
                        prefix=".agent_rollback_", dir=parent_dir)
                    with os.fdopen(descriptor, "wb") as handle:
                        with open(snapshot, "rb") as source:
                            shutil.copyfileobj(source, handle)
                        handle.flush()
                        os.fsync(handle.fileno())
                    temps[item["path"]] = temp_path
            for item in files:
                absolute = _resolve_safe_path(project_root, item["path"])
                case_dest = item.get("case_only_dest")
                if case_dest:
                    # Case-only rename: same physical file — restore the old
                    # letter casing by renaming back (content is unchanged).
                    os.rename(_requested_case_path(project_root, case_dest),
                              _requested_case_path(project_root, item["path"]))
                    restored.append(item["path"])
                    continue
                if item.get("before_present", True):
                    os.replace(temps.pop(item["path"]), absolute)
                elif os.path.exists(absolute):
                    os.remove(absolute)
                    _clean_empty_dirs(os.path.dirname(absolute), project_root)
                restored.append(item["path"])
        except Exception as exc:
            for path in restored:
                try:
                    absolute = _resolve_safe_path(project_root, path)
                    was_present, old_bytes = current[path]
                    if not was_present:
                        if os.path.exists(absolute):
                            os.remove(absolute)
                            _clean_empty_dirs(os.path.dirname(absolute), project_root)
                    else:
                        parent_dir = os.path.dirname(absolute)
                        os.makedirs(parent_dir, exist_ok=True)
                        descriptor, temp_path = tempfile.mkstemp(
                            prefix=".agent_rollback_restore_", dir=parent_dir)
                        with os.fdopen(descriptor, "wb") as handle:
                            handle.write(old_bytes)
                            handle.flush()
                            os.fsync(handle.fileno())
                        os.replace(temp_path, absolute)
                except Exception:
                    pass
            return False, "Пакетный откат не выполнен: %s" % exc, False, [], None
        finally:
            for temp_path in temps.values():
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass
        return True, "Откачено: %s (%d файлов)" % (act, len(files)), False, [f["path"] for f in files], None
    target = entry.get("dest") or entry["path"]
    try:
        abs_target = _resolve_safe_path(project_root, target)
    except Exception as e:
        return False, str(e), False, [], None

    # Защита: файл менялся ПОСЛЕ этого действия агента?
    if not force and _file_hash(abs_target) != entry.get("after_hash"):
        return False, (
            "Файл %s изменялся ПОСЛЕ этого действия агента. Откат перезапишет "
            "эти изменения. Нажмите откат ещё раз для подтверждения." % target
        ), True, [], None

    if act == "create_file":
        if entry.get("overwrote") and entry.get("snapshot"):
            # create_file перезаписал существовавший файл — возвращаем старую версию.
            snap = os.path.join(_history_dir(project_root), entry["snapshot"])
            if not os.path.isfile(snap):
                return False, "Снапшот для отката не найден (возможно, вычищен по лимиту истории).", False, [], None
            shutil.copy2(snap, abs_target)
        else:
            if os.path.exists(abs_target):
                os.remove(abs_target)
            # Godot 4 держит рядом служебные файлы (*.uid, *.import) — удаляем
            # и их, иначе в файловой системе редактора остаются «остатки».
            for leftover in (abs_target + ".uid", abs_target + ".import"):
                if os.path.exists(leftover):
                    try:
                        os.remove(leftover)
                    except OSError:
                        pass
    elif act == "patch_file":
        snap = os.path.join(_history_dir(project_root), entry.get("snapshot", ""))
        if not os.path.isfile(snap):
            return False, "Снапшот для отката не найден (возможно, вычищен по лимиту истории).", False, [], None
        shutil.copy2(snap, abs_target)
    elif act == "move_file":
        abs_src = _resolve_safe_path(project_root, entry["path"])
        if os.path.exists(abs_src) and not force:
            return False, "По старому пути уже существует файл: %s" % entry["path"], True, [], None
        os.makedirs(os.path.dirname(abs_src), exist_ok=True)
        shutil.move(abs_target, abs_src)
        if os.path.exists(abs_target + ".uid") and not os.path.exists(abs_src + ".uid"):
            try:
                shutil.move(abs_target + ".uid", abs_src + ".uid")
            except OSError:
                pass
    else:
        return False, "Неизвестный тип действия в журнале: %s" % act, False, [], None

    affected = [target] if act != "move_file" else [entry["path"], target]
    diff = None
    if act == "patch_file" and "search" in entry and "replace" in entry:
        # Обратный дифф: блок "replace" снова стал блоком "search".
        diff = {"path": target, "was": entry["replace"], "now": entry["search"]}
    return True, "Откачено: %s (%s)" % (act, target), False, affected, diff


@_journal_transaction
def rollback_chain(project_root, chain_id, force=False):
    """Откатывает все шаги plan-цепочки chain_id от ПОСЛЕДНЕГО к ПЕРВОМУ.
    Останавливается на первой ошибке, сохраняя частичную откатку (уже
    откатанные шаги убираются из журнала, оставшиеся — остаются там для
    повторной попытки). Возвращает (ok, message, needs_force, paths,
    reverted_count, total_count)."""
    journal = _load_journal(project_root)
    entries = [e for e in journal if e.get("committed") and e.get("chain_id") == chain_id]
    if not entries:
        return False, "Цепочка не найдена в истории изменений (возможно, уже откачена).", False, [], 0, 0

    # От последнего шага к первому: иначе поздние шаги могут зависеть от
    # ранних (например, patch_file по файлу, созданному ранним create_file).
    entries_sorted = sorted(entries, key=lambda e: e.get("ts", 0), reverse=True)
    total = len(entries_sorted)
    reverted_entries = []
    reverted_paths = []
    error_msg = None
    error_needs_force = False

    for i, entry in enumerate(entries_sorted):
        ok, message, needs_force, affected, diff = _revert_entry_on_disk(project_root, entry, force=force)
        if not ok:
            error_msg = "Откат цепочки прерван на шаге %d из %d: %s" % (i + 1, total, message)
            error_needs_force = needs_force
            break
        reverted_entries.append(entry)
        reverted_paths.extend(affected)

    # Уже откатанные на диске шаги убираем из журнала в ЛЮБОМ случае —
    # и при успехе, и при частичной остановке — иначе повторный откат
    # увидит уже откатанный файл и сломается на hash-проверке.
    if reverted_entries:
        reverted_ids = {e["id"] for e in reverted_entries}
        journal = [e for e in journal if e["id"] not in reverted_ids]
        _save_journal(project_root, journal)
        for e in reverted_entries:
            snap_rel = e.get("snapshot")
            if snap_rel:
                try:
                    os.remove(os.path.join(_history_dir(project_root), snap_rel))
                except OSError:
                    pass

    if error_msg is not None:
        return (
            False,
            error_msg + " Уже откачено шагов: %d из %d." % (len(reverted_entries), total),
            error_needs_force,
            reverted_paths,
            len(reverted_entries),
            total,
        )
    return True, "Цепочка полностью откачена (%d шаг(ов))." % total, False, reverted_paths, total, total
