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
import os
import random
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
BURST_STEPS = 10
BURST_PAUSE_SEC = 2.0
REPORT_EVERY_STEPS = 100
EXAM_EVERY_BURSTS = 100
EXAM_EXAMPLES = 3
MARATHON_ATTEMPTS = 100
MARATHON_EVERY_BURSTS = 500
MARATHON_TIME_BUDGET_SEC = 100
TRAIN_LOG = "train_log.json"
MAX_LOG_LINES = 200

_TOK = MiniLichTokenizer()
_lock = threading.Lock()
_thread = None
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
    print("[minilich-train] %s" % line)


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
        if e.get("stale"):
            continue  # v78: ответ учителя не проходит текущий линтер — не учимся на нём
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
    _state["fit_examples"] = len(encoded)  # v79: сколько реально влезло в обучение
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
    - «длинные»: длинные пары (модель чинит обрезанный фрагмент, как в бою);
    - «новые»: свежая порча сцен проекта, которых НЕТ в датасете (обобщение).
    Каждый результат обязан пройти линтер; похожесть на учителя — посимвольно."""
    import tscn_lint
    from . import ml_fix
    model = load_latest_model(project_root)
    if model is None:
        return
    n_ctx = model.cfg["n_ctx"]
    pairs = [x for x in ml_data.load_pairs(project_root) if not x.get("stale")]
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


def _marathon(project_root, addon_dir=None):
    """v69: MARATHON_ATTEMPTS attempts to re-fix the newest dataset pair with
    rising temperature (attempt 1 is strict/greedy). Each attempt is checked
    by the linter and compared (similarity) with the teacher fix. The earlier
    the best attempt, the more points the model earns. Background only."""
    import difflib
    import time as _time
    import tscn_lint
    from . import ml_fix
    pairs = ml_data.load_pairs(project_root)
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


def _worker(project_root, addon_dir):
    model = None
    burst = 0
    last_report = 0
    _state["active"] = True
    _state["last_error"] = ""
    _state["lines"] = []
    _log("Обучение mini-lich запущено.")
    try:
        try:
            stale_n, total_n = ml_data.revalidate_pairs(project_root, addon_dir)
            if stale_n:
                _log(u"Ревизия датасета: %d из %d пар устарели (учитель не проходит текущий линтер) — они помечены как ремонтные задачи." % (stale_n, total_n))
        except Exception as e:
            _log(u"Ошибка ревизии датасета: %s" % e)
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
                try:
                    _exam(project_root, addon_dir)
                except Exception as e:
                    _log(u"Ошибка экзамена: %s" % e)
            if not _stop.is_set() and model is not None and burst % MARATHON_EVERY_BURSTS == 50:
                try:
                    _marathon(project_root, addon_dir)
                except Exception as e:
                    _log(u"Ошибка марафона: %s" % e)
            if not _stop.is_set() and model is not None and burst % REPAIR_EVERY_BURSTS == 5:
                try:
                    _repair_stale(project_root, addon_dir)
                except Exception as e:
                    _log(u"Ошибка ремонта пары: %s" % e)
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
    stale = [e for e in pairs if e.get("stale")]
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
