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


def _dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total


def status(project_root):
    """Сводка для панели настроек. Никогда не падает."""
    stats = ml_data.dataset_stats(project_root)
    out = {
        "enabled": is_enabled(project_root),
        "examples": stats["examples"],
        "train_step": 0,
        "last_loss": None,
        "training_active": False,
        "params": 0,
        "disk_bytes": _dir_size(ml_data.storage_dir(project_root)),
        "lines": [],
    }
    try:
        from . import ml_train
        log = ml_train.read_log(project_root)
        train = ml_train.training_state()
        out["train_step"] = int(log.get("step", 0) or 0)
        out["last_loss"] = log.get("last_loss")
        out["training_active"] = bool(train.get("active"))
        out["lines"] = list(train.get("lines", []) or [])
        model = ml_train.load_latest_model(project_root)
        if model is not None:
            out["params"] = model.param_count()
    except Exception:
        pass  # numpy недоступен — показываем базовый статус
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
        ml_data.record_pair(project_root, broken, problems, candidate, source="live")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Публичные обёртки
# ---------------------------------------------------------------------------

def try_fix_scene(scene_text, problems, project_root, addon_dir=None):
    return ml_fix.try_fix_scene(scene_text, problems, project_root, addon_dir)


def search_project(project_root, query, limit=8):
    return ml_project_index.search(project_root, query, limit=limit)


def describe_for_prompt(project_root, query, limit=6):
    return ml_project_index.describe_for_prompt(project_root, query, limit=limit)


def start_training(project_root, addon_dir=None):
    try:
        from . import ml_train
        return ml_train.start_background(project_root, addon_dir)
    except Exception:
        return False


def stop_training():
    try:
        from . import ml_train
        return ml_train.stop_background()
    except Exception:
        return False
