# -*- coding: utf-8 -*-
"""mini-lich — крошечная локальная нейросеть-помощник (написана с нуля на numpy).

Узкая специализация (нейросеть-поддержка, не главный программист):
1) починка неправильно собранных .tscn сцен без обращения к большим моделям;
2) понимание структуры проекта пользователя (индекс + поиск для крупной модели);
3) фоновое обучение на сценах Godot: дистилляция реальных исправлений больших
   моделей + синтетика из сцен текущего проекта (дообучение проекту).

По умолчанию ВЫКЛЮЧЕНА (галочка в экспериментальных настройках панели).
Всё хозяйство живёт в <storage>/minilich/: settings.json, dataset.jsonl,
manifest.json, checkpoints/, project_index.json, train_log.json.

ВАЖНО: numpy-зависимые модули (ml_model/ml_train) импортируются ЛЕНИВО —
импорт пакета minilich никогда не роняет сервер, даже если numpy нет.
Рефлекторный слой починок работает и без numpy.
"""
import json
import os

from . import ml_data
from . import ml_fix
from . import ml_project_index

SETTINGS_FILE = "settings.json"

# Память последних сломанных кандидатов по пути сцены: когда большая модель
# потом присылает рабочую версию той же сцены — получаем обучающую пару
# (дистилляция больших моделей бесплатно, прямо из рабочего процесса).
_pending_bad = {}
_MAX_PENDING = 16

# v65: start_training() could return False for two very different reasons -
# 'thread already running' (fine) or 'failed to start due to an exception'
# (e.g. numpy or a bundled dependency missing/broken in the packaged exe).
# We now remember the last real startup error so it can be shown to the user
# instead of being hidden behind a falsely reassuring message.
_last_start_error = ""



def _settings_path(project_root):
    return os.path.join(ml_data.storage_dir(project_root), SETTINGS_FILE)


def _load_settings(project_root):
    try:
        with open(_settings_path(project_root), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"enabled": False}


def is_enabled(project_root):
    return bool(_load_settings(project_root).get("enabled"))


def set_enabled(project_root, enabled):
    data = _load_settings(project_root)
    data["enabled"] = bool(enabled)
    path = _settings_path(project_root)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)
    return data


def is_training_mode(project_root):
    """v69: теневой режим обучения: mini-lich учится, но сцены применяет большая модель.
    По умолчанию включён (безопаснее для недоученной модели)."""
    data = _load_settings(project_root)
    if "training_mode" not in data:
        return True
    return bool(data.get("training_mode"))


def set_training_mode(project_root, training):
    data = _load_settings(project_root)
    data["training_mode"] = bool(training)
    path = _settings_path(project_root)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)
    return data


BRAIN_PROFILES = ("smart",)

# v81: фоновый сбор обучающих пар с GitHub (один за раз).
_github_thread = None


def get_brain(project_root):
    # v84: быстрый профиль убран — «умный» (окно 1024) единственный и
    # используется всегда, независимо от старых сохранённых настроек.
    return "smart"


def github_fetch_async(project_root, addon_dir, repos_text):
    """v81: сбор обучающих пар с GitHub в фоне. False — если сбор уже идёт."""
    global _github_thread
    import threading
    if _github_thread is not None and _github_thread.is_alive():
        return False
    if addon_dir:
        try:
            ml_data.set_storage_base(addon_dir, project_root)
        except Exception:
            pass

    def _run():
        log = print
        try:
            from . import ml_train
            log = ml_train._log
        except Exception:
            pass
        try:
            from . import ml_github
            added = ml_github.fetch_and_add_examples(project_root, addon_dir, repos_text=repos_text, log=log)
            log(u"[github] Готово: добавлено пар: %d." % added)
        except Exception as e:
            log(u"[github] Ошибка сбора: %s" % e)

    _github_thread = threading.Thread(target=_run, name="minilich-github", daemon=True)
    _github_thread.start()
    return True


def _dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total


def status(project_root, addon_dir=None):
    """Сводка для панели настроек. Никогда не падает.

    v64: «enabled» — персистентный флаг на диске и переживает перезагрузку сервера, а
    фоновый поток обучения — нет: он живёт только в текущем процессе и заводится лишь
    явным вызовом start_training. Если сервер перезагрузили (новый запуск
    server.exe) и пользователь не переключил галочку вручную в этой сессии — без этого
    самолечения обучение навечно зависало бы выключенным (training_active=False), хотя
    enabled=True и пользователь считает, что оно должно идти. Поэтому каждый вызов status()
    самолечаще: если enabled=True, а training_active=False — тихонько доказывает запустить
    фоновой поток сам — без участия пользователя.
    """
    if addon_dir:
        try:
            ml_data.set_storage_base(addon_dir, project_root)
        except Exception:
            pass
    stats = ml_data.dataset_stats(project_root)
    enabled = is_enabled(project_root)
    out = {
        "enabled": enabled,
        "examples": stats["examples"],
        "train_step": 0,
        "last_loss": None,
        "training_active": False,
        "params": 0,
        "disk_bytes": _dir_size(ml_data.storage_dir(project_root)),
        "lines": [],
    }
    out["start_error"] = ""
    try:
        from . import ml_train
        train = ml_train.training_state()
        if enabled and not train.get("active"):
            start_training(project_root, addon_dir)
            train = ml_train.training_state()
        log = ml_train.read_log(project_root)
        out["train_step"] = int(log.get("step", 0) or 0)
        out["last_loss"] = log.get("last_loss")
        out["training_active"] = bool(train.get("active"))
        out["lines"] = list(train.get("lines", []) or [])
        out["last_error"] = train.get("last_error") or ""
        out["exam"] = train.get("exam") or ""
        out["marathon"] = train.get("marathon") or ""
        model = ml_train.load_latest_model(project_root)
        if model is not None:
            out["params"] = model.param_count()
    except Exception as e:
        out["start_error"] = "status: %s" % e
        pass  # numpy недоступен — показываем базовый статус
    if enabled and not out["training_active"] and _last_start_error and not out["start_error"]:
        out["start_error"] = _last_start_error
    try:
        out["training_mode"] = is_training_mode(project_root)
    except Exception:
        out["training_mode"] = True
    out["brain"] = get_brain(project_root)
    out["github_busy"] = bool(_github_thread is not None and _github_thread.is_alive())
    try:
        out["storage"] = ml_data.storage_dir(project_root)
    except Exception:
        out["storage"] = ""
    return out


# ---------------------------------------------------------------------------
# Сбор обучающих пар из рабочего процесса (вызывается из main.py)
# ---------------------------------------------------------------------------

def note_scene_bad(path, candidate, problems):
    """Запоминает сломанный кандидат сцены (линтер нашёл проблемы)."""
    if not path or not candidate:
        return
    if len(_pending_bad) >= _MAX_PENDING and path not in _pending_bad:
        _pending_bad.pop(next(iter(_pending_bad)), None)
    _pending_bad[path] = (candidate, [str(p) for p in (problems or [])])


def note_scene_ok(project_root, path, candidate):
    """Сцена прошла линтер: если раньше по этому пути был сломанный вариант —
    записываем обучающую пару (исправление большой модели = учитель)."""
    if not path or not candidate:
        return
    prev = _pending_bad.pop(path, None)
    if prev is None:
        return
    broken, problems = prev
    try:
        added = ml_data.record_pair(project_root, broken, problems, candidate, source="live")
        if added:
            stats = ml_data.dataset_stats(project_root)
            print(u"[minilich] +1 обучающий пример (сломано->исправлено, всего: %d) — файл: %s" % (stats["examples"], ml_data._dataset_path(project_root)))
        else:
            print(u"[minilich] пара сломано->исправлено уже была в датасете (дубль) — не добавляю")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Публичные обёртки
# ---------------------------------------------------------------------------

def try_fix_scene(scene_text, problems, project_root, addon_dir=None):
    if addon_dir:
        try:
            ml_data.set_storage_base(addon_dir, project_root)
        except Exception:
            pass
    return ml_fix.try_fix_scene(scene_text, problems, project_root, addon_dir)


def search_project(project_root, query, limit=8):
    return ml_project_index.search(project_root, query, limit=limit)


def describe_for_prompt(project_root, query, limit=6):
    return ml_project_index.describe_for_prompt(project_root, query, limit=limit)


def start_training(project_root, addon_dir=None):
    global _last_start_error
    if addon_dir:
        try:
            ml_data.set_storage_base(addon_dir, project_root)
        except Exception:
            pass
    try:
        from . import ml_train
    except Exception as e:
        _last_start_error = "import ml_train failed (numpy or bundled dependency missing/broken): %s" % e
        return False
    try:
        started = ml_train.start_background(project_root, addon_dir)
        if started:
            _last_start_error = ""
        return started
    except Exception as e:
        _last_start_error = "start_background failed: %s" % e
        return False


def stop_training():
    try:
        from . import ml_train
        return ml_train.stop_background()
    except Exception:
        return False
