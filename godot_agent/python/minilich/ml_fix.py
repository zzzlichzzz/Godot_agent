# -*- coding: utf-8 -*-
"""Починка сцен mini-lich: рефлекторный слой + нейрослой + обязательная
проверка линтером.

Архитектура «как у взрослых», только маленькая:
1) Рефлекторный слой — детерминированные шаблонные починки известных
   категорий проблем линтера (быстро, надёжно, без генерации).
2) Нейрослой — крошечный трансформер (если есть обученный чекпоинт)
   генерирует исправленную сцену целиком.
3) Любой кандидат ОБЯЗАН пройти tscn_lint без единой проблемы — иначе
   возвращаем None и агент штатно откатывается к большой модели.
   Модель НИКОГДА не может испортить сцену: без чистого вердикта линтера
   её результат просто не используется.
"""
import os
import re

from . import ml_data
from .ml_tokenizer import MiniLichTokenizer

_TOK = MiniLichTokenizer()
MAX_GEN_TOKENS = 480


# ---------------------------------------------------------------------------
# Рефлекторный слой
# ---------------------------------------------------------------------------

_UNUSED_EXT_RE = re.compile(r"\[ext_resource id=\"([^\"]+)\"\] \(([^,]+), ([^\)]+)\)")
_DUP_NODE_RE = re.compile(r"\u0443\u0437\u0435\u043b \u0441 \u043f\u0443\u0442\u0451\u043c \u00ab([^\u00bb]+)\u00bb \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d \u0434\u0432\u0430\u0436\u0434\u044b")
_DOTTED_RE = re.compile(r"\u00ab([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z0-9_.]+)\u00bb")

_NODE_HDR_RE = re.compile(r"^\[node name=\"([^\"]+)\"([^\]]*)\]\s*$", re.M)


def _existing_node_names(scene):
    return set(m.group(1) for m in _NODE_HDR_RE.finditer(scene))


# ---------------------------------------------------------------------------
# Структурированный <think>: детерминированный шаблон вида вместо свободных
# «рассуждений» (Gemini review, v58).
# ---------------------------------------------------------------------------

def classify_problem(problems):
    """Детерминированно определяет категорию проблемы и (если возможно) имя
    узла по тексту проблем от линтера."""
    node = ""
    kind = "other"
    for problem in problems or []:
        s = str(problem)
        m = _UNUSED_EXT_RE.search(s)
        if m:
            kind = "missing_resource"
            node = os.path.splitext(os.path.basename(m.group(3).strip()))[0]
            break
        m = _DUP_NODE_RE.search(s)
        if m:
            kind = "duplicate_node"
            node = m.group(1).split("/")[-1]
            break
        m = _DOTTED_RE.search(s)
        if m:
            kind = "dotted_property"
            node = m.group(1)
            break
    return kind, node


def think_plan_text(problems):
    """Фиксированный текст для <think>...</think>: «type: ..., node: ...»."""
    kind, node = classify_problem(problems)
    if node:
        return "type: %s, node: %s" % (kind, node)
    return "type: %s" % kind


# ---------------------------------------------------------------------------
# Обрезка контекста для больших сцен (Gemini review, v58).
# ---------------------------------------------------------------------------

_BLOCK_HDR_RE = re.compile(r"^\[(node|ext_resource|sub_resource|connection|gd_scene)\b([^\]]*)\]")
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def _split_blocks(scene):
    return scene.split("\n\n")


def _block_info(block):
    """тип + ключ блока — для сшивки обратно."""
    m = _BLOCK_HDR_RE.match(block.lstrip("\n"))
    if not m:
        return ("other", block)
    kind = m.group(1)
    attrs = dict(_ATTR_RE.findall(m.group(2)))
    if kind == "node":
        return ("node", attrs.get("name", ""), attrs.get("parent", ""))
    if kind in ("ext_resource", "sub_resource"):
        return (kind, attrs.get("id", ""))
    if kind == "gd_scene":
        return ("header",)
    return (kind, block[:40])


def _focus_names(problems):
    """имена/пути узлов, упомянутые в тексте проблем от линтера."""
    names = set()
    for problem in problems or []:
        s = str(problem)
        for m in re.finditer(r"\u00ab([^\u00bb]+)\u00bb", s):
            frag = m.group(1)
            names.add(frag.split("/")[-1].split(".")[0])
        for m in re.finditer(r'name="([^"]+)"', s):
            names.add(m.group(1))
    return names


def trim_scene_for_context(scene, problems, tok, max_ids):
    """если сцена не влезает в max_ids токенов — оставляет сломанный
    узел + ближайших родителей/детей (+ заголовок и ресурсы)."""
    if len(tok.encode(scene)) <= max_ids:
        return scene, None
    blocks = _split_blocks(scene)
    infos = [_block_info(b) for b in blocks]
    focus = _focus_names(problems)
    parent_of = {info[1]: info[2] for info in infos if info[0] == "node"}
    focus_parents = set()
    for name in list(focus):
        par = parent_of.get(name)
        if par:
            focus_parents.add(par.split("/")[-1])
    keep_names = set(focus) | focus_parents
    for info in infos:
        if info[0] == "node":
            par_last = info[2].split("/")[-1] if info[2] else ""
            if par_last in focus:
                keep_names.add(info[1])
    kept_blocks = []
    kept_keys = []
    for block, info in zip(blocks, infos):
        if info[0] in ("header", "ext_resource", "sub_resource"):
            kept_blocks.append(block)
            kept_keys.append(info)
        elif info[0] == "node" and info[1] in keep_names:
            kept_blocks.append(block)
            kept_keys.append(info)
    if not any(info[0] == "node" for info in kept_keys):
        for block, info in zip(blocks, infos):
            if info[0] != "node":
                continue
            trial = kept_blocks + [block]
            if len(tok.encode("\n\n".join(trial))) > max_ids:
                break
            kept_blocks.append(block)
            kept_keys.append(info)
    return "\n\n".join(kept_blocks), kept_keys


def trim_pair_for_context(broken, problems, fixed, max_ids):
    """v79: обрезает ПАРУ (сломано, исправлено) до одинакового набора узлов,
    чтобы длинные пары можно было учить фрагментами — ровно так же, как
    neural_fix обрезает сцену в бою. Если пара влезает целиком — не трогает."""
    trimmed_broken, kept_keys = trim_scene_for_context(broken, problems, _TOK, max_ids)
    if kept_keys is None:
        return broken, fixed
    keep_nodes = set(info[1] for info in kept_keys if info[0] == "node")
    kept = []
    for block in _split_blocks(fixed):
        info = _block_info(block)
        if info[0] in ("header", "ext_resource", "sub_resource"):
            kept.append(block)
        elif info[0] == "node" and info[1] in keep_nodes:
            kept.append(block)
    return trimmed_broken, "\n\n".join(kept)


def splice_fixed_fragment(original_scene, kept_keys, fixed_fragment):
    """сшивает исправленный обрезанный фрагмент обратно в полную сцену."""
    orig_blocks = _split_blocks(original_scene)
    orig_infos = [_block_info(b) for b in orig_blocks]
    fixed_blocks = _split_blocks(fixed_fragment)
    fixed_infos = [_block_info(b) for b in fixed_blocks]
    kept_key_set = set(tuple(k) for k in (kept_keys or []))
    fixed_by_key = {}
    extra_blocks = []
    for blk, info in zip(fixed_blocks, fixed_infos):
        if info in kept_key_set:
            fixed_by_key[info] = blk
        else:
            extra_blocks.append(blk)
    out = [fixed_by_key.get(info, blk) for blk, info in zip(orig_blocks, orig_infos)]
    out.extend(extra_blocks)
    return "\n\n".join(out)


def _fix_unused_packed_scene(scene, problem):
    """Неиспользуемый ext_resource типа PackedScene -> добавляем узел-экземпляр
    в корень сцены (без type= — тип берётся из самой сцены)."""
    m = _UNUSED_EXT_RE.search(problem)
    if not m or "PackedScene" not in m.group(2):
        return None
    rid = m.group(1)
    res_path = m.group(3).strip()
    if 'instance=ExtResource("%s")' % rid in scene:
        return None
    base = os.path.splitext(os.path.basename(res_path))[0] or "Instance"
    name = base[:1].upper() + base[1:]
    names = _existing_node_names(scene)
    if name in names:
        idx = 2
        while "%s%d" % (name, idx) in names:
            idx += 1
        name = "%s%d" % (name, idx)
    block = '[node name="%s" parent="." instance=ExtResource("%s")]\n' % (name, rid)
    return scene.rstrip() + "\n\n" + block


def _fix_duplicate_node(scene, problem):
    """Дублирующийся путь узла -> переименовываем ВТОРОЕ вхождение."""
    m = _DUP_NODE_RE.search(problem)
    if not m:
        return None
    dup_path = m.group(1)
    dup_name = dup_path.split("/")[-1]
    names = _existing_node_names(scene)
    seen = 0
    out = []
    changed = False
    for line in scene.split("\n"):
        hm = _NODE_HDR_RE.match(line)
        if hm and hm.group(1) == dup_name and not changed:
            seen += 1
            if seen >= 2:
                idx = 2
                while "%s%d" % (dup_name, idx) in names:
                    idx += 1
                new_name = "%s%d" % (dup_name, idx)
                line = line.replace('name="%s"' % dup_name, 'name="%s"' % new_name, 1)
                changed = True
        out.append(line)
    return "\n".join(out) if changed else None


_SUBRES_ASSIGN_TPL = r"^%s = SubResource\(\"([^\"]+)\"\)\s*$"


def _fix_dotted_property(scene, problem):
    """Свойство «через точку» (a.b = v): если рядом есть `a = SubResource("id")` —
    переносим `b = v` внутрь этого [sub_resource]; иначе строку убираем
    (Godot всё равно молча удалит её при пересохранении)."""
    m = _DOTTED_RE.search(problem)
    if not m:
        return None
    prop_root = m.group(1)
    line_re = re.compile(r"^%s\.([A-Za-z0-9_.]+)\s*=\s*(.+)$" % re.escape(prop_root), re.M)
    lm = line_re.search(scene)
    if not lm:
        return None
    sub_prop = lm.group(1)
    value = lm.group(2).strip()
    without = scene[:lm.start()].rstrip("\n") + "\n" + scene[lm.end():].lstrip("\n")
    without = without.replace("\n\n\n", "\n\n")
    assign_re = re.compile(_SUBRES_ASSIGN_TPL % re.escape(prop_root), re.M)
    am = assign_re.search(scene)
    if am and "." not in sub_prop:
        sid = am.group(1)
        hdr_re = re.compile(r"^\[sub_resource [^\]]*id=\"%s\"[^\]]*\]\s*$" % re.escape(sid), re.M)
        hm = hdr_re.search(without)
        if hm:
            seg = without[hm.end():hm.end() + 400]
            if re.search(r"^%s\s*=" % re.escape(sub_prop), seg, re.M) is None:
                return without[:hm.end()] + "\n" + sub_prop + " = " + value + without[hm.end():]
    return without


def reflex_fix(scene_text, problems):
    """Применяет шаблонные починки ко всем узнаваемым проблемам.
    Возвращает новый текст или None, если ничего не смог изменить."""
    cur = scene_text
    changed = False
    for problem in problems or []:
        p = str(problem)
        for fixer in (_fix_unused_packed_scene, _fix_duplicate_node, _fix_dotted_property):
            try:
                new = fixer(cur, p)
            except Exception:
                new = None
            if new and new != cur:
                cur = new
                changed = True
                break
    return cur if changed else None


# ---------------------------------------------------------------------------
# Нейрослой
# ---------------------------------------------------------------------------

def build_prompt_ids(broken, problems):
    """Длина промпта заканчивается на <think>: сам план (structured think, v58) и
    починка — это зона ответа, которую должна сгенерировать сама модель:
    <bos> проблемы <sep> сломано <sep> <think> [генерация: план </think> <fix> исправлено <eos>]"""
    t = _TOK
    ids = [t.special("<bos>")]
    ids += t.encode("; ".join(str(p) for p in (problems or []))[:400])
    ids.append(t.special("<sep>"))
    ids += t.encode(broken)
    ids.append(t.special("<sep>"))
    ids.append(t.special("<think>"))
    return ids


def build_training_ids(broken, problems, fixed):
    """Полная последовательность для обучения + граница зоны ответа.
    С v58 зона ответа включает и структурированный план (<think>...</think>), и саму починку
    (<fix>...<eos>). Возвращает (ids, answer_start): лосс считается только с answer_start."""
    t = _TOK
    ids = build_prompt_ids(broken, problems)
    answer_start = len(ids)
    ids += t.encode(think_plan_text(problems))
    ids.append(t.special("</think>"))
    ids.append(t.special("<fix>"))
    ids += t.encode(fixed)
    ids.append(t.eos_id)
    return ids, answer_start


def neural_fix(scene_text, problems, project_root, temperature=0.0):
    """Пытается починить сцену обученной моделью. None, если чекпоинта нет
    или вход не помещается в контекст даже после обрезки (v58).

    v58: большие сцены сначала обрезаются до сломанного узла + ближайшего
    окружения (Gemini review); исправленный фрагмент сшивается обратно в полную
    сцену; итог всё равно должен пройти полный линтер в try_fix_scene (verify)."""
    from . import ml_train
    model = ml_train.load_latest_model(project_root)
    if model is None:
        return None
    # v70: сначала пробуем полную сцену — так модель видит примеры при обучении;
    # обрезаем, только если не помещается в контекст.
    n_ctx = model.cfg["n_ctx"]
    prompt = build_prompt_ids(scene_text, problems)
    kept_keys = None
    if len(prompt) + 48 > n_ctx:
        budget = max(64, n_ctx // 2)
        trimmed_text, kept_keys = trim_scene_for_context(scene_text, problems, _TOK, budget)
        prompt = build_prompt_ids(trimmed_text, problems)
    if len(prompt) + 8 >= model.cfg["n_ctx"]:
        return None  # сцена не помещается — пусть работает большая модель
    try:
        new_ids = model.generate(
            prompt,
            max_new=min(MAX_GEN_TOKENS, model.cfg["n_ctx"] - len(prompt)),
            eos_id=_TOK.eos_id,
            repetition_penalty=1.3,
            repetition_window=24,
            temperature=temperature,
        )
    except Exception:
        return None
    fix_id = _TOK.special("<fix>")
    if fix_id in new_ids:
        fix_ids = new_ids[new_ids.index(fix_id) + 1:]
    else:
        fix_ids = new_ids
    text = _TOK.decode(fix_ids).strip()
    if not text:
        return None
    if kept_keys is None:
        return text
    return splice_fixed_fragment(scene_text, kept_keys, text)


# ---------------------------------------------------------------------------
# Главная точка входа
# ---------------------------------------------------------------------------

def try_fix_scene(scene_text, problems, project_root, addon_dir=None):
    """Главный вход: возвращает исправленную сцену, ПОЛНОСТЬЮ прошедшую
    линтер, либо None (тогда вызывающий код штатно идёт к большой модели)."""
    import tscn_lint

    def verify(candidate):
        if not candidate:
            return None
        try:
            fixed, probs = tscn_lint.lint_and_fix_tscn(candidate, project_root, addon_dir)
        except Exception:
            return None
        return fixed if not probs else None

    # 1) рефлекторный слой — до 3 итераций (одна починка может вскрыть следующую проблему)
    import tscn_lint as _tl
    cur = scene_text
    cur_problems = list(problems or [])
    for _ in range(3):
        cand = reflex_fix(cur, cur_problems)
        if not cand:
            break
        ok = verify(cand)
        if ok is not None:
            ml_data.record_pair(project_root, scene_text, problems, ok, source="reflex")
            return ok
        try:
            cand2, cur_problems = _tl.lint_and_fix_tscn(cand, project_root, addon_dir)
            cur = cand2
        except Exception:
            break
        if not cur_problems:
            return cur
    # 2) нейрослой — только если есть обученный чекпоинт
    cand = neural_fix(scene_text, problems, project_root)
    ok = verify(cand)
    if ok is not None:
        ml_data.record_pair(project_root, scene_text, problems, ok, source="neural")
        return ok
    return None
