# -*- coding: utf-8 -*-
"""Обучение mini-lich: фоновый тренер + атомарные чекпоинты.

Защита от отключения ПК:
- чекпоинт пишется во временный файл и атомарно переименовывается;
- хранятся ПОСЛЕДНИЕ 3 чекпоинта (если самый свежий повреждён — берётся
  предыдущий);
- в чекпоинте сохраняется и состояние оптимизатора Adam и номер шага —
  обучение продолжается ровно с того места, где остановилось.

Фоновый режим: короткие «всплески» обучения с паузами, чтобы не мешать
основной работе сервера и Godot. Перед каждым всплеском подсыпается свежая
синтетика из сцен текущего проекта (дообучение проекту пользователя).
"""
import json
import os
import re
import threading
import time

import numpy as np

from . import ml_data
from . import ml_fix
from .ml_model import TinyTransformer, default_config
from .ml_tokenizer import MiniLichTokenizer

CKPT_KEEP = 3
CKPT_EVERY_STEPS = 50
BURST_STEPS = 40
BURST_PAUSE_SEC = 20.0
TRAIN_LOG = "train_log.json"
MAX_LOG_LINES = 200

_TOK = MiniLichTokenizer()
_lock = threading.Lock()
_thread = None
_stop = threading.Event()
_state = {"active": False, "last_loss": None, "steps_done": 0, "last_error": "", "lines": []}


def _log(msg):
    """Строка для «консоли обучения» в панели настроек — живёт только в памяти процесса."""
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    _state["lines"].append(line)
    if len(_state["lines"]) > MAX_LOG_LINES:
        _state["lines"] = _state["lines"][-MAX_LOG_LINES:]


def ckpt_dir(project_root):
    d = os.path.join(ml_data.storage_dir(project_root), "checkpoints")
    os.makedirs(d, exist_ok=True)
    return d


def _ckpt_list(project_root):
    d = ckpt_dir(project_root)
    out = []
    for fn in os.listdir(d):
        m = re.match(r"^ckpt_(\d+)\.npz$", fn)
        if m:
            out.append((int(m.group(1)), os.path.join(d, fn)))
    return sorted(out)


def load_latest_model(project_root):
    """Самый свежий ЦЕЛЫЙ чекпоинт (битые пропускаются). None если нет."""
    for step, path in reversed(_ckpt_list(project_root)):
        try:
            return TinyTransformer.load(path)
        except Exception:
            continue
    return None


def _save_ckpt(project_root, model):
    path = os.path.join(ckpt_dir(project_root), "ckpt_%d.npz" % model.step)
    model.save(path)
    # вытесняем старые, оставляя CKPT_KEEP последних
    lst = _ckpt_list(project_root)
    for _, old in lst[:-CKPT_KEEP]:
        try:
            os.remove(old)
        except OSError:
            pass


def _write_log(project_root, data):
    path = os.path.join(ml_data.storage_dir(project_root), TRAIN_LOG)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def read_log(project_root):
    try:
        with open(os.path.join(ml_data.storage_dir(project_root), TRAIN_LOG), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _ensure_model(project_root, config_overrides=None):
    model = load_latest_model(project_root)
    if model is not None:
        return model
    cfg = default_config(_TOK.vocab_size)
    if config_overrides:
        cfg.update(config_overrides)
    return TinyTransformer(cfg, seed=42)


def train_steps(project_root, steps=BURST_STEPS, model=None, lr=1e-3, config_overrides=None):
    """Один всплеск обучения. Возвращает (model, mean_loss | None).
    Примеры берутся из датасета; слишком длинные пропускаются."""
    pairs = ml_data.load_pairs(project_root)
    if not pairs:
        return model, None
    if model is None:
        model = _ensure_model(project_root, config_overrides)
    n_ctx = model.cfg["n_ctx"]
    encoded = []
    for e in pairs:
        ids, ans = ml_fix.build_training_ids(e["broken"], e.get("problems") or [], e["fixed"])
        if len(ids) <= n_ctx:
            encoded.append((ids, ans))
    if not encoded:
        return model, None
    rng = np.random.default_rng(model.step + 1)
    losses = []
    for _ in range(steps):
        if _stop.is_set():
            break
        ids, ans = encoded[int(rng.integers(0, len(encoded)))]
        arr = np.asarray(ids, dtype=np.int64)
        inp = arr[:-1]
        tgt = arr[1:]
        mask = np.zeros(len(inp), dtype=np.float32)
        mask[max(ans - 1, 0):] = 1.0
        loss, grads = model.loss_and_grads(inp, tgt, mask)
        model.adam_step(grads, lr=lr)
        losses.append(loss)
        if model.step % CKPT_EVERY_STEPS == 0:
            _save_ckpt(project_root, model)
    if losses:
        _save_ckpt(project_root, model)
        mean_loss = float(np.mean(losses))
        _write_log(project_root, {"step": model.step, "last_loss": mean_loss,
                                  "examples": len(encoded), "time": time.time()})
        return model, mean_loss
    return model, None


# ---------------------------------------------------------------------------
# Фоновый тренер
# ---------------------------------------------------------------------------

def _worker(project_root, addon_dir):
    model = None
    _state["active"] = True
    _state["last_error"] = ""
    _state["lines"] = []
    _log("Обучение mini-lich запущено.")
    try:
        while not _stop.is_set():
            try:
                added = ml_data.generate_synthetic(project_root, addon_dir, limit=6)
                if added:
                    _log("Синтетика: +%d новых пар." % added)
            except Exception as e:
                _state["last_error"] = "synthetic: %s" % e
                _log("Ошибка синтетики: %s" % e)
            try:
                model, loss = train_steps(project_root, steps=BURST_STEPS, model=model)
                if loss is not None:
                    _state["last_loss"] = loss
                    _state["steps_done"] = model.step if model else 0
                    _log("Шаг %d: loss=%.4f" % (model.step, loss))
            except Exception as e:
                _state["last_error"] = "train: %s" % e
                _log("Ошибка обучения: %s" % e)
            _stop.wait(BURST_PAUSE_SEC)
    finally:
        _state["active"] = False
        _log("Обучение остановлено.")


def start_background(project_root, addon_dir=None):
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _stop.clear()
        _thread = threading.Thread(target=_worker, args=(project_root, addon_dir),
                                   name="minilich-train", daemon=True)
        _thread.start()
        return True


def stop_background(timeout=5.0):
    global _thread
    with _lock:
        _stop.set()
        t = _thread
    if t is not None:
        t.join(timeout)
    with _lock:
        _thread = None
    return True


def training_state():
    return dict(_state)
