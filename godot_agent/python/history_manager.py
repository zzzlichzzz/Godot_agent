import os
import json
import time
import uuid
import shutil
import hashlib

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


def set_storage_dir(base_dir):
    """Включает хранение журнала/снапшотов вне проекта: <base_dir>/agent_history."""
    global _STORAGE_OVERRIDE
    _STORAGE_OVERRIDE = os.path.join(os.path.abspath(base_dir), "agent_history")


def get_storage_dir(project_root):
    """Абсолютный путь к папке хранения (журнал, снапшоты, служебные файлы)."""
    return _history_dir(project_root)


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


def _load_journal(project_root):
    path = _journal_path(project_root)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # Битый журнал (например, выключили ПК во время записи) не должен
        # ронять сервер — откладываем его в .broken и начинаем заново.
        try:
            os.replace(path, path + ".broken")
        except OSError:
            pass
        return []


def _save_journal(project_root, journal):
    path = _journal_path(project_root)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(journal, f, ensure_ascii=False, indent=1)
    # Атомарная замена: на диске всегда либо старый журнал, либо новый.
    os.replace(tmp, path)


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


def _prune(project_root, journal):
    """Держим не больше MAX_ENTRIES записей; снапшоты старых — удаляем."""
    while len(journal) > MAX_ENTRIES:
        old = journal.pop(0)
        snap = old.get("snapshot")
        if snap:
            try:
                os.remove(os.path.join(_history_dir(project_root), snap))
            except OSError:
                pass


def record_change(project_root, action):
    """Вызывать ДО применения write-действия. Возвращает id записи журнала."""
    act = action.get("action")
    path = action.get("path", "")
    entry = {
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "type": act,
        "path": path,
        "committed": False,
    }
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
    # create_file: снапшот не нужен — файла до действия не существует
    # (create_project_file сама падает, если файл уже есть).

    journal = _load_journal(project_root)
    journal.append(entry)
    _prune(project_root, journal)
    _save_journal(project_root, journal)
    return entry["id"]


def commit_change(project_root, entry_id):
    """Вызывать ПОСЛЕ успешного применения — фиксирует хэш результата."""
    journal = _load_journal(project_root)
    for e in journal:
        if e["id"] == entry_id:
            target = e.get("dest") or e["path"]
            e["after_hash"] = _file_hash(_resolve_safe_path(project_root, target))
            e["committed"] = True
            break
    _save_journal(project_root, journal)


def abort_change(project_root, entry_id):
    """Если применение упало с ошибкой — убираем запись из журнала,
    чтобы не пытаться откатывать то, чего не было."""
    journal = _load_journal(project_root)
    new_journal = [e for e in journal if e["id"] != entry_id]
    if len(new_journal) != len(journal):
        _save_journal(project_root, new_journal)


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
    act = entry["type"]
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
        if os.path.exists(abs_target):
            os.remove(abs_target)
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
    else:
        return False, "Неизвестный тип действия в журнале: %s" % act, False, [], None

    # Убираем запись и её снапшот только после успешного отката.
    snap_rel = entry.get("snapshot")
    journal.remove(entry)
    _save_journal(project_root, journal)
    if snap_rel:
        try:
            os.remove(os.path.join(_history_dir(project_root), snap_rel))
        except OSError:
            pass
    affected = [target] if act != "move_file" else [entry["path"], target]
    diff = None
    if act == "patch_file" and "search" in entry and "replace" in entry:
        # Обратный дифф: блок "replace" снова стал блоком "search".
        diff = {"path": target, "was": entry["replace"], "now": entry["search"]}
    return True, "Откачено: %s (%s)" % (act, target), False, affected, diff
