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
import difflib
import json
import math
import os
import random
import re
import shutil
import threading
import time

import numpy as np

from . import ml_data
from . import ml_fix
from .ml_model import TinyTransformer, default_config
from .ml_tokenizer import MiniLichTokenizer

CKPT_KEEP = 3
CKPT_EVERY_STEPS = 50
BURST_STEPS = 10
BURST_PAUSE_SEC = 0.5  # v86.6: было 2.0 — сервер половину времени просто спал; переопределяется в settings.json (train_pause_sec)
REPORT_EVERY_STEPS = 100
EXAM_EVERY_BURSTS = 100
EXAM_EXAMPLES = 3
# v86: проверка «выучено наизусть» эталонных пар (только neural_fix, без adam_step)
# и чтение замороженных экзаменов — оба режима чисто смотровые, не влияют на веса.
REFERENCE_MASTERY_EVERY_BURSTS = 200
REFERENCE_EXAM_EVERY_BURSTS = 300
REFERENCE_MASTERY_SIM = 0.999  # бар «выучено наизусть»: линтер-чисто + практически точное совпадение
MARATHON_ATTEMPTS = 100
MARATHON_EVERY_BURSTS = 500
MARATHON_TIME_BUDGET_SEC = 100
# v86.5: «пульс» — если в логе давно нет строк, сообщаем чем занят сервер
HEARTBEAT_CHECK_SEC = 30
HEARTBEAT_SILENCE_SEC = 120
TRAIN_LOG = "train_log.json"
MAX_LOG_LINES = 200

# --- v85 (GPT review): hard example mining + replay-по-категориям --------
# Каждый шаг выбирает пример НЕ строго случайно, а из одной из трёх корзин:
#   50% — примеры, где mini-lich «недавно проваливался» (loss выше среднего
#         по датасету, либо пример вообще ещё не видели);
#   30% — редкие категории проблем (чтобы модель не забывала их напрочь);
#   20% — лёгкие/уже выученные примеры (низкий loss) — держим их в ротации,
#         а не вычёркиваем, ради стабильности (anti-catastrophic-forgetting).
# Сложность примера — это EMA его loss за последние разы, когда он попадал
# в шаг обучения; хранится отдельно от dataset.jsonl, в example_stats.json.
EXAMPLE_STATS_FILE = "example_stats.json"
RECENT_FAIL_SHARE = 0.5
RARE_CATEGORY_SHARE = 0.3
LOSS_EMA_ALPHA = 0.3

# --- v85 (GPT review): warmup + cosine decay для learning rate -----------
# Обучение фоновое и непрерывное (не «одна эпоха»), поэтому расписание не
# гасит lr до нуля навсегда — после LR_DECAY_STEPS держим положенный минимум
# (LR_MIN_RATIO от базового), это всё ещё лучше константного высокого lr.
LR_WARMUP_STEPS = 200
LR_DECAY_STEPS = 8000
LR_MIN_RATIO = 0.1
ADAM_WEIGHT_DECAY = 0.01
ADAM_CLIP_NORM = 1.0

# --- v85 (GPT review): фиксированный отложенный набор + «лучший» чекпоинт -
# ~1/VALID_HOLDOUT_MOD пар (по стабильному хэшу, а не по времени добавления)
# никогда не участвует в обучении — это validation-набор для честной метрики
# valid_fix_rate (а не loss). Включается только когда пар достаточно много,
# чтобы не отъедать редкие данные у маленьких датасетов на старте.
VALID_HOLDOUT_MOD = 5
VALID_MIN_POOL = 40
VALID_MAX_SIZE = 60
VALID_EVAL_EVERY_BURSTS = 50
BEST_CKPT_FILE = "best.json"
BEST_CKPT_NAME = "ckpt_best.npz"

_TOK = MiniLichTokenizer()
_lock = threading.Lock()
_thread = None
_pulse_thread = None  # v86.5: поток «пульса»
_stop = threading.Event()
_state = {"active": False, "last_loss": None, "steps_done": 0, "last_error": "", "lines": [], "exam": "", "marathon": ""}


def _log(msg):
    """Строка для «консоли обучения»: живёт в памяти процесса (для панели)
    и ОДНОВРЕМЕННО печатается в консоль сервера (server.exe/терминал),
    чтобы прогресс обучения виден без отдельного окна в Godot."""
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    _state["lines"].append(line)
    if len(_state["lines"]) > MAX_LOG_LINES:
        _state["lines"] = _state["lines"][-MAX_LOG_LINES:]
    _state["last_line_ts"] = time.time()  # v86.5: метка для «пульса»
    try:
        print("[minilich-train] %s" % line, flush=True)
    except Exception:
        pass  # консоль недоступна — панель в Godot всё равно получит строку


# --- v84: профиль мозга --------------------------------------------------
# Быстрый профиль убран — он почти не умел чинить длинные сцены (слишком
# узкое окно контекста). «Умный» (окно 1024) — единственный и постоянный
# профиль; чекпоинты остаются в checkpoints_smart, чтобы не терять прогресс,
# накопленный ещё на v83, когда smart уже был профилем по умолчанию.
PROFILES = {
    "smart": {"n_ctx": 1024, "d_model": 128, "d_ff": 256},
}


def _brain_profile(project_root):
    return "smart"


def _brain_profile_config(project_root):
    prof = _brain_profile(project_root)
    cfg = default_config(_TOK.vocab_size)
    cfg.update(PROFILES[prof])
    return prof, cfg


def ckpt_dir(project_root):
    d = os.path.join(ml_data.storage_dir(project_root), "checkpoints_smart")
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


BACKUP_EVERY_STEPS = 200  # v86.3: как часто дублировать чекпоинт в резерв
_ckpt_warned = set()      # v86.3: о нечитаемом файле предупреждаем один раз


def _backup_dir(project_root):
    """v86.3: резервная копия чекпоинта ВНЕ папки плагина. Мозг живёт в
    <addons>/<плагин>/minilich_brain — переустановка/обновление плагина по
    схеме «снести папку и распаковать заново» уносила его вместе с прогрессом
    обучения. Резерв в хранилище истории (user://) это переживает."""
    try:
        base = ml_data.history.get_storage_dir(project_root)
    except Exception:
        base = None
    if not base:
        base = os.path.join(os.path.abspath(project_root or "."), ".agent_history")
    d = os.path.join(base, ml_data.STORAGE_SUBDIR, "ckpt_backup")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def _rescue_checkpoints(project_root):
    """v86.3: если в основном хранилище чекпоинтов нет — ищем их в известных
    прежних местах (резерв вне папки плагина, старые папки мозга) и копируем
    в основное. Возвращает число спасённых файлов."""
    dst = ckpt_dir(project_root)
    bdir = _backup_dir(project_root)
    hist_ml = os.path.dirname(bdir)
    candidates = [
        bdir,
        os.path.join(hist_ml, "checkpoints_smart"),
        os.path.join(hist_ml, "checkpoints"),
        os.path.join(ml_data.storage_dir(project_root), "checkpoints"),
    ]
    rescued = 0
    for src in candidates:
        if not os.path.isdir(src):
            continue
        if os.path.abspath(src) == os.path.abspath(dst):
            continue
        for fn in os.listdir(src):
            if not re.match(r"^ckpt_(\d+)\.npz$", fn):
                continue
            target = os.path.join(dst, fn)
            if os.path.exists(target):
                continue
            try:
                shutil.copy2(os.path.join(src, fn), target)
                rescued += 1
            except OSError:
                pass
    if rescued:
        _log(u"Спасение мозга: восстановлено %d чекпоинт(ов) прежнего обучения -> %s" % (rescued, dst))
    return rescued


def _archive_mismatched_ckpts(project_root, want_cfg):
    """v86.4: чекпоинт другого профиля мозга (например 512x96 из старых
    версий при текущем 1024x128) нельзя загрузить в новую модель, но у него
    самый большой номер шага, поэтому он вечно «затенял» новое обучение:
    при каждом рестарте загружался именно он (и обучение начиналось с нуля),
    а вытеснение старых чекпоинтов удаляло СВЕЖИЕ файлы новой модели (у них
    номер шага меньше). Убираем чужие чекпоинты в архивную подпапку: они
    остаются на диске, но больше не мешают копить прогресс. Возвращает
    число перенесённых чекпоинтов."""
    d = ckpt_dir(project_root)
    moved = 0
    arch = None
    for _step, path in _ckpt_list(project_root):
        try:
            old = TinyTransformer.load(path)
        except Exception:
            continue  # нечитаемые файлы не трогаем: о них уже предупредили
        if (int(old.cfg.get("n_ctx", 0)) == int(want_cfg["n_ctx"])
                and int(old.cfg.get("d_model", 0)) == int(want_cfg["d_model"])):
            continue
        arch = os.path.join(d, "archive_%sx%s" % (old.cfg.get("n_ctx"), old.cfg.get("d_model")))
        try:
            os.makedirs(arch, exist_ok=True)
            os.replace(path, os.path.join(arch, os.path.basename(path)))
            moved += 1
        except OSError:
            pass
    if moved and arch:
        # best-чекпоинт прежнего профиля тоже в архив: его метрики считала другая модель
        for extra in (BEST_CKPT_NAME, BEST_CKPT_FILE):
            src = os.path.join(d, extra)
            if os.path.isfile(src):
                try:
                    os.replace(src, os.path.join(arch, extra))
                except OSError:
                    pass
        _log(u"Чекпоинты прежнего профиля мозга перенесены в архив (%d шт.): %s" % (moved, arch))
        _log(u"Старый мозг несовместим с новым размером сети — знания переедут через датасет (пары обучения сохранены).")
    return moved


def load_latest_model(project_root):
    """Самый свежий ЦЕЛЫЙ чекпоинт. None если нет. v86.3: битые файлы больше
    не пропускаются МОЛЧА (раньше причина «обучения с нуля» была невидима),
    а при пустом хранилище чекпоинты сначала пытаемся спасти из прежних мест
    (резерв вне папки плагина и т.п.)."""
    for attempt in (0, 1):
        for _step, path in reversed(_ckpt_list(project_root)):
            try:
                return TinyTransformer.load(path)
            except Exception as e:
                if path not in _ckpt_warned:
                    _ckpt_warned.add(path)
                    _log(u"ВНИМАНИЕ: чекпоинт %s не читается (%s) — пропускаю."
                         % (os.path.basename(path), e))
                continue
        if attempt == 0 and not _rescue_checkpoints(project_root):
            break
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
    # v86.3: раз в BACKUP_EVERY_STEPS шагов дублируем свежий чекпоинт в резерв
    # ВНЕ папки плагина — при пустом основном хранилище (например, после
    # переустановки плагина) его подберёт _rescue_checkpoints.
    if model.step % BACKUP_EVERY_STEPS == 0:
        try:
            bdir = _backup_dir(project_root)
            dst = os.path.join(bdir, os.path.basename(path))
            tmp = dst + ".tmp"
            shutil.copy2(path, tmp)
            os.replace(tmp, dst)
            for fn in os.listdir(bdir):
                if fn.startswith("ckpt_") and fn.endswith(".npz") and fn != os.path.basename(path):
                    try:
                        os.remove(os.path.join(bdir, fn))
                    except OSError:
                        pass
        except Exception:
            pass


def _stats_path(project_root):
    return os.path.join(ml_data.storage_dir(project_root), EXAMPLE_STATS_FILE)


def _load_example_stats(project_root):
    try:
        with open(_stats_path(project_root), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_example_stats(project_root, stats):
    path = _stats_path(project_root)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False)
    os.replace(tmp, path)


def _example_category(problems):
    """v85: категория проблемы для корзины «редкие категории» — та же
    детерминированная классификация, что и для <think>-плана (ml_fix)."""
    try:
        kind, _node = ml_fix.classify_problem(problems)
        return kind
    except Exception:
        return "other"


def _build_sampling_buckets(hashes, categories, stats):
    """v85: делит индексы 0..n-1 на три корзины (см. константы выше).
    fail — loss_ema выше медианы ИЛИ пример ещё не оценивался (приоритет
    на дообучение); easy — loss_ema не выше медианы (уже выучен, держим для
    стабильности); rare — категория встречается не чаще среднего на
    категорию. Корзины могут пересекаться — это нормально, они просто
    определяют ВЕРОЯТНОСТЬ попадания примера в шаг, а не эксклюзивный раздел."""
    n = len(hashes)
    losses = [(stats.get(h) or {}).get("loss_ema") for h in hashes]
    known = sorted(l for l in losses if l is not None)
    median = known[len(known) // 2] if known else 0.0
    cat_count = {}
    for c in categories:
        cat_count[c] = cat_count.get(c, 0) + 1
    avg_count = (n / float(len(cat_count))) if cat_count else 0.0
    fail_idx = [i for i in range(n) if losses[i] is None or losses[i] > median]
    easy_idx = [i for i in range(n) if losses[i] is not None and losses[i] <= median]
    rare_idx = [i for i in range(n) if cat_count.get(categories[i], 0) <= avg_count]
    return fail_idx, rare_idx, easy_idx


def _pick_weighted_index(rng, fail_idx, rare_idx, easy_idx, n):
    """v85: 50% fail / 30% rare / 20% easy; если выбранная корзина пуста —
    откатываемся на равномерный выбор по всему пулу."""
    r = float(rng.random())
    if r < RECENT_FAIL_SHARE and fail_idx:
        pool = fail_idx
    elif r < RECENT_FAIL_SHARE + RARE_CATEGORY_SHARE and rare_idx:
        pool = rare_idx
    elif easy_idx:
        pool = easy_idx
    else:
        pool = fail_idx or rare_idx or list(range(n))
    return int(pool[int(rng.integers(0, len(pool)))])


def _lr_schedule(step, base_lr):
    """v85 (GPT review): линейный warmup первые LR_WARMUP_STEPS шагов, затем
    косинусное затухание к LR_MIN_RATIO*base_lr к шагу LR_DECAY_STEPS, дальше
    держим минимум (обучение фоновое и бесконечное, а не одна эпоха)."""
    step = max(1, int(step))
    if step <= LR_WARMUP_STEPS:
        return base_lr * step / float(LR_WARMUP_STEPS)
    if step >= LR_DECAY_STEPS:
        return base_lr * LR_MIN_RATIO
    progress = (step - LR_WARMUP_STEPS) / float(max(1, LR_DECAY_STEPS - LR_WARMUP_STEPS))
    cos = 0.5 * (1.0 + math.cos(math.pi * progress))
    return base_lr * (LR_MIN_RATIO + (1.0 - LR_MIN_RATIO) * cos)


def _select_validation_pairs(project_root):
    """v85: делит непротухшие пары на (validation, train) по стабильному
    хэшу пары — держит фиксированный отложенный набор без отдельного файла.
    Если пар мало (< VALID_MIN_POOL) — отдаём всё в train, чтобы не отъедать
    данные у маленьких датасетов на старте."""
    pairs = [e for e in ml_data.load_pairs(project_root) if not e.get("stale") and not e.get("mastered")]
    if len(pairs) < VALID_MIN_POOL:
        return [], pairs
    valid = []
    train = []
    for e in pairs:
        h = ml_data.pair_hash(e.get("broken") or "", e.get("fixed") or "")
        if int(h[:8], 16) % VALID_HOLDOUT_MOD == 0 and len(valid) < VALID_MAX_SIZE:
            valid.append(e)
        else:
            train.append(e)
    return valid, train


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
    # v81: конфиг берём из профиля мозга; чекпоинт другого размера не подхватываем.
    _prof, cfg = _brain_profile_config(project_root)
    model = load_latest_model(project_root)
    if model is not None and int(model.cfg.get("n_ctx", 0)) == int(cfg["n_ctx"]) and int(model.cfg.get("d_model", 0)) == int(cfg["d_model"]):
        # v86.3: раньше «продолжили» и «с нуля» выглядели в консоли одинаково
        _log(u"Чекпоинт загружен: продолжаю обучение с шага %d (%s)."
             % (model.step, ckpt_dir(project_root)))
        return model
    if model is not None:
        _log(u"Чекпоинт (шаг %d) не подходит профилю мозга (окно %s vs %s, ширина %s vs %s) — начинаю новую модель."
             % (model.step, model.cfg.get("n_ctx"), cfg["n_ctx"], model.cfg.get("d_model"), cfg["d_model"]))
        # v86.4: убираем чужие чекпоинты в архив, иначе они вечно затеняют новое обучение
        _archive_mismatched_ckpts(project_root, cfg)
    else:
        _log(u"Чекпоинтов нет (%s) — обучение начинается с нуля." % ckpt_dir(project_root))
    if config_overrides:
        cfg.update(config_overrides)
    return TinyTransformer(cfg, seed=42)


def train_steps(project_root, steps=BURST_STEPS, model=None, lr=1e-3, config_overrides=None):
    """Один всплеск обучения. Возвращает (model, mean_loss | None).
    Примеры берутся из датасета; слишком длинные пропускаются.
    v85 (GPT review): (1) ~1/VALID_HOLDOUT_MOD пар исключены из обучения —
    это отложенный набор для честной метрики (см. _validate_and_track_best);
    (2) каждый шаг выбирает пример по правилу hard-example mining (50% недавно
    проваленные/новые, 30% редкие категории, 20% лёгкие) вместо чистого
    равномерного случайного выбора; (3) lr идёт через warmup+cosine расписание,
    а adam_step получает gradient clipping и decoupled weight decay (AdamW)."""
    _valid_pairs, pairs = _select_validation_pairs(project_root)
    if not pairs:
        return model, None
    if model is None:
        model = _ensure_model(project_root, config_overrides)
    n_ctx = model.cfg["n_ctx"]
    encoded = []
    hashes = []
    categories = []
    for e in pairs:
        probs_e = e.get("problems") or []
        ids, ans = ml_fix.build_training_ids(e["broken"], probs_e, e["fixed"])
        if len(ids) > n_ctx:
            # v79: длинная пара — учимся на обрезанном фрагменте (как в бою)
            try:
                tb, tf = ml_fix.trim_pair_for_context(e["broken"], probs_e, e["fixed"], max(64, n_ctx // 3))
                ids, ans = ml_fix.build_training_ids(tb, probs_e, tf)
            except Exception:
                continue
        if len(ids) <= n_ctx:
            encoded.append((ids, ans))
            hashes.append(ml_data.pair_hash(e.get("broken") or "", e.get("fixed") or ""))
            categories.append(_example_category(probs_e))
    _state["fit_examples"] = len(encoded)  # v79: сколько реально влезло в обучение
    if not encoded:
        return model, None
    n = len(encoded)
    stats = _load_example_stats(project_root)
    fail_idx, rare_idx, easy_idx = _build_sampling_buckets(hashes, categories, stats)
    rng = np.random.default_rng(model.step + 1)
    losses = []
    for _ in range(steps):
        if _stop.is_set():
            break
        idx = _pick_weighted_index(rng, fail_idx, rare_idx, easy_idx, n)
        ids, ans = encoded[idx]
        arr = np.asarray(ids, dtype=np.int64)
        inp = arr[:-1]
        tgt = arr[1:]
        mask = np.zeros(len(inp), dtype=np.float32)
        mask[max(ans - 1, 0):] = 1.0
        loss, grads = model.loss_and_grads(inp, tgt, mask)
        step_lr = _lr_schedule(model.step + 1, lr)
        model.adam_step(grads, lr=step_lr, weight_decay=ADAM_WEIGHT_DECAY, clip_norm=ADAM_CLIP_NORM)
        losses.append(loss)
        h = hashes[idx]
        prev = stats.get(h) or {}
        prev_loss = prev.get("loss_ema")
        new_ema = loss if prev_loss is None else (LOSS_EMA_ALPHA * loss + (1.0 - LOSS_EMA_ALPHA) * prev_loss)
        stats[h] = {"loss_ema": float(new_ema), "seen": int(prev.get("seen", 0)) + 1,
                    "category": categories[idx]}
        if model.step % CKPT_EVERY_STEPS == 0:
            _save_ckpt(project_root, model)
    if losses:
        _save_ckpt(project_root, model)
        # v85: чистим статистику от хэшей, которых больше нет в пуле обучения
        # (вытеснены лимитом/стали stale/уехали в validation) — файл не растёт бесконечно.
        live_hashes = set(hashes)
        stats = {h: v for h, v in stats.items() if h in live_hashes}
        _save_example_stats(project_root, stats)
        mean_loss = max(0.0, float(np.mean(losses)))  # v79: без ложного минуса (-0.0000)
        _write_log(project_root, {"step": model.step, "last_loss": mean_loss,
                                  "examples": len(encoded), "time": time.time()})
        return model, mean_loss
    return model, None


# ---------------------------------------------------------------------------
# Фоновый тренер
# ---------------------------------------------------------------------------

def _norm_scene(s):
    lines = [" ".join(x.split()) for x in (s or "").strip().splitlines()]
    return "\n".join(lines).strip()


def _exam(project_root, addon_dir=None):
    """v79: экзамен из трёх категорий по EXAM_PER_CATEGORY заданий:
    - «память»: короткие пары из датасета (влезают в контекст целиком);
    - «длинные»: длинные пары (модель чинит ��брезанный фрагмент, как в бою);
    - «новые»: свежая порча сцен проекта, которых НЕТ в датасете (обобщение).
    Каждый результат обязан пройти линтер; похожесть на учителя — посимвольно."""
    import tscn_lint
    from . import ml_fix
    model = load_latest_model(project_root)
    if model is None:
        return
    n_ctx = model.cfg["n_ctx"]
    pairs = [x for x in ml_data.load_pairs(project_root) if not x.get("stale") and not x.get("mastered")]
    short_pool = []
    long_pool = []
    for e in pairs:
        try:
            ids, _ans = ml_fix.build_training_ids(e.get("broken") or "", e.get("problems") or [], e.get("fixed") or "")
        except Exception:
            continue
        (short_pool if len(ids) <= n_ctx else long_pool).append(e)
    fresh_pool = _fresh_exam_pairs(project_root, addon_dir)
    cats = [(u"память", short_pool), (u"длинные", long_pool), (u"новые", fresh_pool)]
    total = sum(min(EXAM_PER_CATEGORY, len(p)) for _n, p in cats)
    if not total:
        return
    num = 0
    parts = []
    for cat_name, pool in cats:
        take = random.sample(pool, min(EXAM_PER_CATEGORY, len(pool)))
        if not take:
            parts.append(u"%s: нет заданий" % cat_name)
            continue
        ok_lint = 0
        ok_great = 0
        for e in take:
            num += 1
            if _stop.is_set():
                return
            fix = None
            _state["phase"] = u"экзамен %d/%d [%s]: генерирую починку" % (num, total, cat_name)
            try:
                fix = ml_fix.neural_fix(e.get("broken") or "", e.get("problems") or [], project_root)
            except Exception:
                fix = None
            if not fix:
                _log(u"Экзамен %d/%d [%s]: НЕ СМОГЛА (модель не выдала починку)" % (num, total, cat_name))
                continue
            clean = False
            try:
                _f2, probs2 = tscn_lint.lint_and_fix_tscn(fix, project_root, addon_dir)
                clean = not probs2
            except Exception:
                clean = False
            if not clean:
                _log(u"Экзамен %d/%d [%s]: НЕ СМОГЛА (результат не прошёл линтер)" % (num, total, cat_name))
                continue
            ok_lint += 1
            sim = _similarity(fix, e.get("fixed") or "")
            pct = int(round(sim * 100))
            if sim >= 0.999:
                ok_great += 1
                _log(u"Экзамен %d/%d [%s]: OK — точь-в-точь как учитель (100%%)" % (num, total, cat_name))
            elif sim >= EXAM_GREAT_SIM:
                ok_great += 1
                _log(u"Экзамен %d/%d [%s]: OK — отлично, почти как учитель (похожесть %d%%)" % (num, total, cat_name, pct))
            else:
                _log(u"Экзамен %d/%d [%s]: OK — по-своему, линтер чист (похожесть на учителя %d%%)" % (num, total, cat_name, pct))
        parts.append(u"%s %d/%d (близко к учителю %d)" % (cat_name, ok_lint, len(take), ok_great))
    summary = u", ".join(parts)
    _state["exam"] = summary
    _log(u"Экзамен итог: %s." % summary)


def _fresh_exam_pairs(project_root, addon_dir=None, want=None):
    """v79: свежие экзаменационные задачи — порча случайных ВАЛИДНЫХ сцен
    проекта. Таких пар нет в датасете, поэтому они проверяют обобщение,
    а не зубрёжку. Учителем считается исходная валидная сцена."""
    import tscn_lint
    if want is None:
        want = EXAM_PER_CATEGORY
    out = []
    try:
        scene_paths = ml_data.find_project_scenes(project_root, limit=25)
    except Exception:
        return out
    random.shuffle(scene_paths)
    for path in scene_paths:
        if len(out) >= want:
            break
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                scene = f.read().replace("\r\n", "\n")
        except OSError:
            continue
        if len(scene) > ml_data.MAX_SCENE_CHARS:
            continue
        try:
            fixed0, probs0 = tscn_lint.lint_and_fix_tscn(scene, project_root, addon_dir)
        except Exception:
            continue
        if probs0:
            continue
        base = fixed0
        candidates = []
        b = ml_data._corrupt_drop_instance(base)
        if b:
            candidates.append((b, base))
        b = ml_data._corrupt_duplicate_node(base)
        if b:
            candidates.append((b, base))
        d = ml_data._corrupt_dotted_property(base)
        if d:
            candidates.append(d)
        random.shuffle(candidates)
        for broken, fixed in candidates:
            try:
                _bf, probs = tscn_lint.lint_and_fix_tscn(broken, project_root, addon_dir)
            except Exception:
                continue
            if not probs:
                continue
            out.append({"broken": broken, "problems": [str(p) for p in probs], "fixed": fixed})
            break
    return out


def _check_reference_mastery(project_root, addon_dir=None):
    """v86: для каждой ещё не выученной наизусть эталонной пары — проверка только
    через neural_fix (без adam_step/record_pair!): если результат линтер-чист и
    практически точно совпадает с эталонным ответом (>= REFERENCE_MASTERY_SIM) — пара
    помечается mastered=True и выбывает из активного обучения. Сама сцена-файл
    и строка в датасете остаются навсегда."""
    import tscn_lint
    from . import ml_fix
    model = load_latest_model(project_root)
    if model is None:
        return
    pending = ml_data.load_reference_pairs(project_root, only_unmastered=True)
    for e in pending:
        if _stop.is_set():
            return
        ref_key = e.get("ref_key")
        broken = e.get("broken") or ""
        probs = e.get("problems") or []
        fixed = e.get("fixed") or ""
        _state["phase"] = u"проверка выучивания эталона: %s" % ref_key
        try:
            fix = ml_fix.neural_fix(broken, probs, project_root, model=model)
        except Exception:
            fix = None
        if not fix:
            continue
        try:
            _f2, probs2 = tscn_lint.lint_and_fix_tscn(fix, project_root, addon_dir)
            clean = not probs2
        except Exception:
            clean = False
        if not clean:
            continue
        sim = _similarity(fix, fixed)
        if sim >= REFERENCE_MASTERY_SIM:
            ml_data.mark_pair_mastered(project_root, ref_key)
            _log(u"Эталон «%s» выучен наизусть (сходство %d%%) — снят с активного обучения, сцена и экзамены остаются гарантийно." % (ref_key, int(round(sim * 100))))


def _run_reference_exams(project_root, addon_dir=None):
    """v86: чисто смотровой прогон по всем 9 замороженным экзаменам — проверяет,
    не забыла ли модель эталон после вытеснения из активного обучения. Зовёт
    только neural_fix (читает веса) и линтер; результат уходит только в
    record_reference_exam_result (частный лог, minilich его не видит) — никаких вызовов
    adam_step/record_pair здесь НЕТ."""
    import tscn_lint
    from . import ml_fix
    model = load_latest_model(project_root)
    if model is None:
        return
    exams = ml_data.load_reference_exams(project_root)
    if not exams:
        return
    passed = 0
    for e in exams:
        if _stop.is_set():
            return
        ref_key = e.get("ref_key")
        _state["phase"] = u"экзамен памяти эталонов: %s" % ref_key
        try:
            fix = ml_fix.neural_fix(e.get("broken") or "", e.get("problems") or [], project_root, model=model)
        except Exception:
            fix = None
        ok = False
        sim = 0.0
        if fix:
            try:
                _f2, probs2 = tscn_lint.lint_and_fix_tscn(fix, project_root, addon_dir)
                ok = not probs2
            except Exception:
                ok = False
            sim = _similarity(fix, e.get("fixed") or "")
        ml_data.record_reference_exam_result(project_root, ref_key, ok, sim)
        if ok:
            passed += 1
    _log(u"Экзамен памяти эталонов: %d/%d (результат только в логе, на обучение не влияет)." % (passed, len(exams)))


def _marathon(project_root, addon_dir=None):
    """v69: MARATHON_ATTEMPTS attempts to re-fix the newest dataset pair with
    rising temperature (attempt 1 is strict/greedy). Each attempt is checked
    by the linter and compared (similarity) with the teacher fix. The earlier
    the best attempt, the more points the model earns. Background only."""
    import difflib
    import time as _time
    import tscn_lint
    from . import ml_fix
    pairs = [x for x in ml_data.load_pairs(project_root) if not x.get("mastered")]
    if not pairs:
        return
    e = pairs[-1]
    teacher = _norm_scene(e.get("fixed") or "")
    if not teacher:
        return
    _log(u"Марафон: %d попыток, ~1 попытка/сек, лимит %d сек — итог в конце..." % (MARATHON_ATTEMPTS, MARATHON_TIME_BUDGET_SEC))
    ok_count = 0
    first_ok = 0
    best_att = 0
    best_sim = -1.0
    attempted = 0
    deadline = _time.time() + MARATHON_TIME_BUDGET_SEC
    for i in range(1, MARATHON_ATTEMPTS + 1):
        if _stop.is_set():
            _log(u"Марафон прерван — обучение выключено.")
            return
        if _time.time() > deadline:
            _log(u"Марафон: лимит времени %d сек — досрочный итог по %d попыткам." % (MARATHON_TIME_BUDGET_SEC, attempted))
            break
        attempted = i
        t_att = _time.time()
        if i == 1:
            temp = 0.0
        else:
            temp = 0.1 + 0.9 * (i - 2) / float(max(1, MARATHON_ATTEMPTS - 2))
        try:
            fix = ml_fix.neural_fix(e.get("broken") or "", e.get("problems") or [], project_root, temperature=temp)
        except Exception:
            fix = None
        if fix:
            ok = False
            try:
                _f2, probs2 = tscn_lint.lint_and_fix_tscn(fix, project_root, addon_dir)
                ok = not probs2
            except Exception:
                ok = False
            if ok:
                ok_count += 1
                if not first_ok:
                    first_ok = i
                sim = difflib.SequenceMatcher(None, _norm_scene(fix), teacher).ratio()
                if sim > best_sim:
                    best_sim = sim
                    best_att = i
        _sp = 1.0 - (_time.time() - t_att)
        if _sp > 0:
            _time.sleep(_sp)
        if i % 10 == 0:
            prog = u"попытка %d/%d — удачных %d" % (i, MARATHON_ATTEMPTS, ok_count)
            if best_att:
                prog += u", лучшая — №%d (похожесть %d%%)" % (best_att, int(round(best_sim * 100)))
            _state["marathon"] = u"марафон идёт: " + prog
            _log(u"Марафон: " + prog)
    if best_att:
        points = int(round(100.0 / best_att))
        summary = u"удачных %d/%d, лучшая — попытка №%d (похожесть на учителя %d%%), первая удачная — №%d, очки: %d" % (ok_count, attempted, best_att, int(round(best_sim * 100)), first_ok, points)
    else:
        summary = u"удачных 0/%d — модели нужно ещё обучение, очки: 0" % attempted
    _state["marathon"] = summary
    _log(u"Марафон итог: %s" % summary)


# ---------------------------------------------------------------------------
# v85 (GPT review): честная метрика (valid_fix_rate) на отложенном наборе +
# чекпоинт «лучший по метрике» (отдельно от ротации последних CKPT_KEEP
# чекпоинтов). Фоновый тренер всё равно всегда продолжает обучение с самого
# свежего чекпоинта (как раньше) — лучший только сохраняется и показывается.
# ---------------------------------------------------------------------------

def _best_path(project_root):
    return os.path.join(ckpt_dir(project_root), BEST_CKPT_FILE)


def _load_best(project_root):
    try:
        with open(_best_path(project_root), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "valid_fix_rate" in data:
            return data
    except Exception:
        pass
    return {}


def _save_best(project_root, data):
    path = _best_path(project_root)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def best_checkpoint_path(project_root):
    """v85: путь к чекпоин����у �� лучшим известным valid_fix_rate (или None, если
    такого нет) — для ручной оценки/отладки. Сам фоновый тренер продолжает
    учиться с самого свежего чекпоинта, а не откатывается к лучшему, чтобы не
    остановить прогресс."""
    info = _load_best(project_root)
    name = info.get("path")
    if name and os.path.isfile(os.path.join(ckpt_dir(project_root), name)):
        return os.path.join(ckpt_dir(project_root), name)
    return None


def _evaluate_valid_set(project_root, model, valid_pairs, addon_dir=None):
    """v85: valid_fix_rate = доля примеров отложенного набора, которые
    сама модель починила так, что результат (1) прошёл текущий линтер чисто и
    (2) не выкинул лишние узлы (страховка _keeps_enough_nodes от «ампутации», т.е.
    «ненужных изменений»). Аргмакс строго greedy (temperature=0), как в бою."""
    import tscn_lint
    if not valid_pairs:
        return None
    ok = 0
    for e in valid_pairs:
        try:
            fix = ml_fix.neural_fix(e.get("broken") or "", e.get("problems") or [], project_root,
                                     temperature=0.0)
        except Exception:
            fix = None
        if not fix:
            continue
        try:
            _f2, probs2 = tscn_lint.lint_and_fix_tscn(fix, project_root, addon_dir)
        except Exception:
            continue
        if probs2:
            continue
        if not _keeps_enough_nodes(e.get("broken") or "", fix):
            continue
        ok += 1
    return ok / float(len(valid_pairs))


def _validate_and_track_best(project_root, addon_dir, model):
    """v85: замер валидации valid_fix_rate на отложенном наборе + сохранение
    отдельного «лучшего» чекпоинта, если текущая модель лучше зафиксированного
    лучшего (или его пока нет). Запускается редко (VALID_EVAL_EVERY_BURSTS) — это
    прогон каждого примера через генерацию, затратно как экзамен/марафон."""
    valid_pairs, _train_pairs = _select_validation_pairs(project_root)
    if not valid_pairs:
        return
    rate = _evaluate_valid_set(project_root, model, valid_pairs, addon_dir)
    if rate is None:
        return
    pct = int(round(rate * 100))
    _log(u"Проверка на отложенном наборе (%d примеров): valid_fix_rate=%d%%." % (len(valid_pairs), pct))
    _state["best"] = u"проверка: %d%% (шаг %d)" % (pct, model.step)
    best = _load_best(project_root)
    if best and rate <= float(best.get("valid_fix_rate", -1.0)):
        return
    try:
        model.save(os.path.join(ckpt_dir(project_root), BEST_CKPT_NAME))
    except Exception as e:
        _log(u"Не удалось сохранить лучший чекпоинт: %s" % e)
        return
    _save_best(project_root, {"step": model.step, "valid_fix_rate": rate, "path": BEST_CKPT_NAME})
    _state["best"] = u"лучший: %d%% (шаг %d)" % (pct, model.step)
    _log(u"Новый лучший чекпоинт по valid_fix_rate: %d%% (шаг %d)." % (pct, model.step))


def _worker(project_root, addon_dir):
    model = None
    burst = 0
    last_report = 0
    _state["active"] = True
    _state["last_error"] = ""
    _state["lines"] = []
    _log("Обучение mini-lich запущено.")
    try:
        _prof0, _cfg0 = _brain_profile_config(project_root)
        _log(u"Мозг: профиль «%s» (окно %d, ширина %d)." % (_prof0, _cfg0["n_ctx"], _cfg0["d_model"]))
    except Exception:
        pass
    try:
        try:
            stale_n, total_n = ml_data.revalidate_pairs(project_root, addon_dir)
            if stale_n:
                _log(u"Реви����ия датасета: %d из %d пар устарели (учитель не проходит текущий линтер) — они помечены как ремонтные задачи." % (stale_n, total_n))
        except Exception as e:
            _log(u"Ошибка ревизии датасета: %s" % e)
        try:
            added_p, added_e = ml_data.ensure_reference_material(project_root, addon_dir)
            if added_p or added_e:
                _log(u"Эталонные сцены: +%d обучающих пар, +%d замороженных экзаменов (всего экзаменов: %d)." % (added_p, added_e, len(ml_data.load_reference_exams(project_root))))
        except Exception as e:
            _log(u"Ошибка бутстрапа эталонных сцен: %s" % e)
        while not _stop.is_set():
            _state["phase"] = u"синтетика: порча валидных сцен проекта"
            try:
                added = ml_data.generate_synthetic(project_root, addon_dir, limit=6)
                if added:
                    _log("Синтетика: +%d новых пар." % added)
            except Exception as e:
                _state["last_error"] = "synthetic: %s" % e
                _log("Ошибка синтетики: %s" % e)
            try:
                _state["phase"] = u"шаги обучения"
                model, loss = train_steps(project_root, steps=BURST_STEPS, model=model)
                if loss is not None:
                    _state["last_loss"] = loss
                    _state["steps_done"] = model.step if model else 0
                    if loss < 1e-4:
                        _state["sat_bursts"] = _state.get("sat_bursts", 0) + 1
                        if _state["sat_bursts"] == 20:
                            _log(u"Датасет выучен наизусть (loss≈0): шаги по старым парам больше ничего не дают — жду новых данных (синтетика, ремонт стухших пар, живые починки).")
                    else:
                        _state["sat_bursts"] = 0
                    if model is not None and model.step - last_report >= REPORT_EVERY_STEPS:
                        last_report = model.step
                        _log("Шаг %d: loss=%.4f (примеров: %d, в обучении: %d)" % (model.step, loss, ml_data.dataset_stats(project_root).get("examples", 0), _state.get("fit_examples") or 0))
            except Exception as e:
                _state["last_error"] = "train: %s" % e
                _log("Ошибка обучения: %s" % e)
            burst += 1
            if not _stop.is_set() and model is not None and burst % EXAM_EVERY_BURSTS == 1:
                _state["phase"] = u"экзамен: подготовка заданий"
                try:
                    _exam(project_root, addon_dir)
                except Exception as e:
                    _log(u"Ошибка экзамена: %s" % e)
            if not _stop.is_set() and model is not None and burst % MARATHON_EVERY_BURSTS == 50:
                _state["phase"] = u"марафон: много попыток одной починки"
                try:
                    _marathon(project_root, addon_dir)
                except Exception as e:
                    _log(u"Ошибка марафона: %s" % e)
            if not _stop.is_set() and model is not None and burst % REPAIR_EVERY_BURSTS == 5:
                _state["phase"] = u"ремонт стухшей пары: температурная лестница"
                try:
                    _repair_stale(project_root, addon_dir)
                except Exception as e:
                    _log(u"Ошибка ремонта пары: %s" % e)
            if not _stop.is_set() and model is not None and burst % REFERENCE_MASTERY_EVERY_BURSTS == 7:
                _state["phase"] = u"проверка выучивания эталонов"
                try:
                    _check_reference_mastery(project_root, addon_dir)
                except Exception as e:
                    _log(u"Ошибка проверки эталонной пары: %s" % e)
            if not _stop.is_set() and model is not None and burst % REFERENCE_EXAM_EVERY_BURSTS == 11:
                _state["phase"] = u"экзамен памяти эталонов"
                try:
                    _run_reference_exams(project_root, addon_dir)
                except Exception as e:
                    _log(u"Ошибка экзамена памяти эталонов: %s" % e)
            if not _stop.is_set() and model is not None and burst % VALID_EVAL_EVERY_BURSTS == 25:
                _state["phase"] = u"валидация: отбор лучшей версии"
                try:
                    _validate_and_track_best(project_root, addon_dir, model)
                except Exception as e:
                    _log(u"Ошибка валидации: %s" % e)
            _stop.wait(_burst_pause(project_root))
    finally:
        _state["active"] = False
        _log("Обучение остановлено.")


def _burst_pause(project_root):
    """v86.6: пауза между всплесками обучения. Читается из settings.json
    (ключ train_pause_sec, зажим 0..10 сек) перед каждым бёрстом — можно
    менять на лету, без перезапуска сервера. Меньше пауза — быстрее учится,
    но выше нагрузка на CPU. Без настройки — BURST_PAUSE_SEC."""
    try:
        import json
        path = os.path.join(ml_data.storage_dir(project_root), "settings.json")
        with open(path, "r", encoding="utf-8") as f:
            val = json.load(f).get("train_pause_sec")
        if val is None:
            return BURST_PAUSE_SEC
        return max(0.0, min(10.0, float(val)))
    except Exception:
        return BURST_PAUSE_SEC


def _heartbeat_loop():
    """v86.5: если в консоли обучения давно нет новых строк — печатаем «пульс»:
    чем сервер занят прямо сейчас. Долгая тишина — почти всегда генерация
    длинной сцены на CPU (экзамен/марафон/ремонт), а не зависание. Пишет не
    чаще раза в HEARTBEAT_SILENCE_SEC, потому что _log обновляет метку."""
    while not _stop.wait(HEARTBEAT_CHECK_SEC):
        last = _state.get("last_line_ts") or 0.0
        quiet = time.time() - last
        if last and quiet >= HEARTBEAT_SILENCE_SEC:
            phase = _state.get("phase") or u"шаги обучения"
            _log(u"Пульс: сервер жив, сейчас: %s (тишина %d сек — долгая генерация на CPU, это не зависание)." % (phase, int(quiet)))


def start_background(project_root, addon_dir=None):
    global _thread, _pulse_thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _stop.clear()
        _thread = threading.Thread(target=_worker, args=(project_root, addon_dir),
                                   name="minilich-train", daemon=True)
        _thread.start()
        if _pulse_thread is None or not _pulse_thread.is_alive():
            _pulse_thread = threading.Thread(target=_heartbeat_loop,
                                             name="minilich-pulse", daemon=True)
            _pulse_thread.start()
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


# ---------------------------------------------------------------------------
# v78: похожесть на учителя, страховка от «ампутации», ремонт стухших пар.
# ---------------------------------------------------------------------------

NODE_KEEP_RATIO = 0.9
REPAIR_EVERY_BURSTS = 30
REPAIR_TIME_BUDGET_SEC = 30
REPAIR_TEMPS = (0.0, 0.2, 0.4, 0.7, 1.0)
EXAM_GREAT_SIM = 0.95

_NODE_HDR_RE = re.compile(r'^\[node name="([^"]+)"(?:\s[^\]]*?parent="([^"]*)")?[^\]]*\]', re.M)


def _similarity(a, b):
    """Похожесть двух сцен в долях [0..1] ПО СИМВОЛАМ (не по словам!):
    сцены сперва нормализуются (лишние пробелы/пустые строки не считаются),
    затем difflib сравнивает последовательности символов. Поэтому замена
    одного слова в маленькой сцене стоит лишь несколько процентов: в сцене
    из 2 узлов (~150 символов) слово из 6 символов — это ~4%, а не «1 слово из 7»."""
    return difflib.SequenceMatcher(None, _norm_scene(a), _norm_scene(b)).ratio()


def _node_set(scene):
    out = set()
    for m in _NODE_HDR_RE.finditer(scene or ""):
        out.add((m.group(1), m.group(2) or ""))
    return out


def _keeps_enough_nodes(broken, candidate):
    """Страховка от «взлома награды ампутацией»: самый лёгкий способ пройти
    линтер — выкинуть проблемный узел или пол-сцены. Кандидат обязан сохранить
    почти все узлы исходной сцены: пропасть может максимум 10% узлов (но хотя
    бы один — легальные починки вроде удаления узла-дубля разрешены и для
    крошечных сцен из 2 узлов)."""
    base = _node_set(broken)
    if not base:
        return True
    missing = len(base - _node_set(candidate))
    allowed = max(1, int(round(len(base) * (1.0 - NODE_KEEP_RATIO))))
    return missing <= allowed


def _repair_stale(project_root, addon_dir=None):
    """Ремонт одной стухшей пары: учитель больше не проходит текущий линтер,
    поэтому модель ищет СВОЙ вариант починки — температурная лестница
    REPAIR_TEMPS (сперва строго, потом всё более творчески). Кандидат засчитан,
    если линтер чист И сохранено достаточно узлов; из засчитанных берётся самый
    похожий на учителя и записывается как новый правильный ответ (source=self)."""
    import tscn_lint
    from . import ml_fix
    pairs = ml_data.load_pairs(project_root)
    stale = [e for e in pairs if e.get("stale") and not e.get("mastered")]
    if not stale:
        return False
    e = stale[0]
    teacher = e.get("teacher_fixed") or e.get("fixed") or ""
    broken = e.get("broken") or ""
    _log(u"Ремонт стухшей пары: ответ учителя не проходит текущий линтер — ищу свой вариант...")
    best = None
    best_sim = -1.0
    deadline = time.time() + REPAIR_TIME_BUDGET_SEC
    for temp in REPAIR_TEMPS:
        if _stop.is_set() or time.time() > deadline:
            break
        try:
            fix = ml_fix.neural_fix(broken, e.get("problems") or [], project_root, temperature=temp)
        except Exception:
            fix = None
        if not fix:
            continue
        try:
            _f2, probs2 = tscn_lint.lint_and_fix_tscn(fix, project_root, addon_dir)
        except Exception:
            continue
        if probs2:
            continue
        if not _keeps_enough_nodes(broken, fix):
            continue
        sim = _similarity(fix, teacher)
        if sim > best_sim:
            best_sim = sim
            best = fix
    if best is None:
        _log(u"Ремонт: пока не получилось (температуры %s исчерпаны) — попробую позже." % (REPAIR_TEMPS,))
        return False
    if ml_data.replace_pair_fixed(project_root, broken, best, similarity=best_sim):
        _log(u"Ремонт: найден свой вариант — линтер чист, похожесть на учителя %d%%. Записан как новый правильный ответ (source=self)." % int(round(best_sim * 100)))
        return True
    return False

# --- v79 ---
EXAM_PER_CATEGORY = 2  # заданий на категорию экзамена (память / длинные / новые)
