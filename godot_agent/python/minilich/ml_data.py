# -*- coding: utf-8 -*-
"""Датасет mini-lich: хранение обучающих пар + дедупликация + синтетика.

Каждая пара: (сломанная сцена + список проблем от линтера) -> (исправленная
сцена). Источники пар:
- "live"      — реальные исправления большой модели из self-heal (дистилляция);
- "reflex"    — успешные шаблонные починки самого mini-lich;
- "synthetic" — программная «поломка» валидных сцен проекта по правилам
  линтера (бесплатные данные без единого запроса к большим моделям). Заодно
  это и есть «дообучение проекту пользователя»: синтетика строится из его
  собственных сцен, и модель привыкает именно к его стилю и структуре.

Дедупликация: sha256 от (сломано + исправлено) в манифесте — одна и та же
пара никогда не попадёт в обучение дважды. Повтор КАТЕГОРИИ ошибки на
разных сценах — не дубль, а материал для обобщения.

Лимиты места: датасет — jsonl с потолком по числу примеров и байтам;
при переполнении старейшие примеры вытесняются.
"""
import hashlib
import json
import os
import re

import history_manager as history

STORAGE_SUBDIR = "minilich"
DATASET_FILE = "dataset.jsonl"
MANIFEST_FILE = "manifest.json"
MAX_EXAMPLES = 2000
MAX_DATASET_BYTES = 4 * 1024 * 1024  # 4 МБ — «главное чтобы не занимало много места»
MAX_SCENE_CHARS = 6000  # слишком большие сцены в обучение не берём


def storage_dir(project_root):
    try:
        base = history.get_storage_dir(project_root)
    except Exception:
        base = None
    if not base:
        base = os.path.join(os.path.abspath(project_root or "."), ".agent_history")
    d = os.path.join(base, STORAGE_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


def _dataset_path(project_root):
    return os.path.join(storage_dir(project_root), DATASET_FILE)


def _manifest_path(project_root):
    return os.path.join(storage_dir(project_root), MANIFEST_FILE)


def _load_manifest(project_root):
    try:
        with open(_manifest_path(project_root), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("hashes"), list):
            return data
    except Exception:
        pass
    return {"hashes": []}


def _save_manifest(project_root, manifest):
    path = _manifest_path(project_root)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)
    os.replace(tmp, path)


def pair_hash(broken, fixed):
    h = hashlib.sha256()
    h.update(broken.encode("utf-8", errors="replace"))
    h.update(b"\x00")
    h.update(fixed.encode("utf-8", errors="replace"))
    return h.hexdigest()


def record_pair(project_root, broken, problems, fixed, source="live"):
    """Добавляет обучающую пару. Возвращает True, если пара новая
    (дубли отсекаются по манифесту хэшей и НИКОГДА не попадают в датасет
    повторно — даже если старая копия уже вытеснена из файла лимитом)."""
    broken = (broken or "").strip()
    fixed = (fixed or "").strip()
    if not broken or not fixed or broken == fixed:
        return False
    if len(broken) > MAX_SCENE_CHARS or len(fixed) > MAX_SCENE_CHARS:
        return False
    manifest = _load_manifest(project_root)
    ph = pair_hash(broken, fixed)
    if ph in manifest["hashes"]:
        return False
    entry = {
        "broken": broken,
        "problems": [str(p) for p in (problems or [])][:8],
        "fixed": fixed,
        "source": source,
    }
    path = _dataset_path(project_root)
    line = json.dumps(entry, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    manifest["hashes"].append(ph)
    # Манифест храним без лимита вытеснения датасета (хэши крошечные),
    # но всё же с разумным потолком.
    if len(manifest["hashes"]) > MAX_EXAMPLES * 5:
        manifest["hashes"] = manifest["hashes"][-MAX_EXAMPLES * 5:]
    _save_manifest(project_root, manifest)
    _enforce_limits(project_root)
    return True


def _enforce_limits(project_root):
    path = _dataset_path(project_root)
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    lines = None
    if size > MAX_DATASET_BYTES:
        lines = _read_lines(path)
        while lines and sum(len(l) + 1 for l in lines) > MAX_DATASET_BYTES:
            lines.pop(0)  # вытесняем старейшие
    else:
        lines = _read_lines(path)
        if len(lines) <= MAX_EXAMPLES:
            return
        lines = lines[-MAX_EXAMPLES:]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for l in lines:
            f.write(l + "\n")
    os.replace(tmp, path)


def _read_lines(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [l.rstrip("\n") for l in f if l.strip()]
    except OSError:
        return []


def load_pairs(project_root, limit=None):
    pairs = []
    for line in _read_lines(_dataset_path(project_root)):
        try:
            e = json.loads(line)
        except Exception:
            continue
        if isinstance(e, dict) and e.get("broken") and e.get("fixed"):
            pairs.append(e)
    if limit:
        pairs = pairs[-limit:]
    return pairs


def dataset_stats(project_root):
    path = _dataset_path(project_root)
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    return {"examples": len(_read_lines(path)), "bytes": size}


# ---------------------------------------------------------------------------
# Синтетика: программная поломка валидных сцен проекта по правилам линтера.
# ---------------------------------------------------------------------------

_NODE_RE = re.compile(r"^\[node name=\"([^\"]+)\"([^\]]*)\]\s*$", re.M)
_EXT_PACKED_RE = re.compile(
    r"^\[ext_resource type=\"PackedScene\"[^\]]*?id=\"([^\"]+)\"[^\]]*\]\s*$", re.M)


def _corrupt_drop_instance(scene):
    """Убирает узел-экземпляр PackedScene -> появляется «объявлен, но не
    используется» (точно как в реальном баге из v55)."""
    m = _EXT_PACKED_RE.search(scene)
    if not m:
        return None
    rid = m.group(1)
    blocks = scene.split("\n\n")
    for i, blk in enumerate(blocks):
        if blk.startswith("[node ") and 'instance=ExtResource("%s")' % rid in blk:
            broken = "\n\n".join(blocks[:i] + blocks[i + 1:])
            return broken
    return None


def _corrupt_duplicate_node(scene):
    """Дублирует последний не-корневой узел -> конфликт имён."""
    blocks = scene.split("\n\n")
    for blk in reversed(blocks):
        if blk.startswith("[node ") and 'parent=' in blk:
            return scene.rstrip() + "\n\n" + blk.strip() + "\n"
    return None


_MESH_SUB_RE = re.compile(r"^mesh = SubResource\(\"([^\"]+)\"\)\s*$", re.M)


def _corrupt_dotted_property(scene):
    """Добавляет свойство «через точку» (mesh.size = ...) после mesh =
    SubResource(...) — ровно тот случай, что ловит линтер с v55.
    Возвращает (broken, fixed): в fixed то же значение перенесено ВНУТРЬ
    соответствующего [sub_resource]."""
    m = _MESH_SUB_RE.search(scene)
    if not m:
        return None
    sid = m.group(1)
    header_re = re.compile(r"^\[sub_resource type=\"(PlaneMesh|BoxMesh|QuadMesh)\"[^\]]*id=\"%s\"[^\]]*\]\s*$" % re.escape(sid), re.M)
    hm = header_re.search(scene)
    if not hm:
        return None
    prop_line = "size = Vector2(4, 4)" if hm.group(1) in ("PlaneMesh", "QuadMesh") else "size = Vector3(2, 2, 2)"
    if "\nsize = " in scene[hm.end():hm.end() + 200]:
        return None  # уже есть size — не трогаем
    dotted = "mesh." + prop_line
    broken = scene[:m.end()] + "\n" + dotted + scene[m.end():]
    fixed = scene[:hm.end()] + "\n" + prop_line + scene[hm.end():]
    return broken, fixed


def find_project_scenes(project_root, limit=40):
    """Список .tscn файлов проекта (без служебных папок)."""
    out = []
    skip = {".git", ".godot", ".import", "addons", ".agent_history", "__pycache__"}
    for root, dirs, files in os.walk(os.path.abspath(project_root or ".")):
        dirs[:] = [d for d in dirs if d not in skip]
        for fn in files:
            if fn.endswith(".tscn"):
                out.append(os.path.join(root, fn))
                if len(out) >= limit:
                    return out
    return out


def generate_synthetic(project_root, addon_dir=None, limit=12):
    """Генерирует до limit новых синтетических пар из сцен проекта.
    Каждая пара проверяется линтером: broken ДОЛЖЕН давать проблемы,
    fixed — проходить чисто. Возвращает число добавленных пар."""
    import tscn_lint
    added = 0
    for path in find_project_scenes(project_root):
        if added >= limit:
            break
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                scene = f.read().replace("\r\n", "\n")
        except OSError:
            continue
        if len(scene) > MAX_SCENE_CHARS:
            continue
        try:
            fixed0, probs0 = tscn_lint.lint_and_fix_tscn(scene, project_root, addon_dir)
        except Exception:
            continue
        if probs0:
            continue  # берём за основу только валидные сцены
        base = fixed0
        candidates = []
        b = _corrupt_drop_instance(base)
        if b:
            candidates.append((b, base))
        b = _corrupt_duplicate_node(base)
        if b:
            candidates.append((b, base))
        d = _corrupt_dotted_property(base)
        if d:
            candidates.append(d)
        for broken, fixed in candidates:
            if added >= limit:
                break
            try:
                _, probs = tscn_lint.lint_and_fix_tscn(broken, project_root, addon_dir)
                fixed_ok, probs_fixed = tscn_lint.lint_and_fix_tscn(fixed, project_root, addon_dir)
            except Exception:
                continue
            if not probs or probs_fixed:
                continue
            if record_pair(project_root, broken, probs, fixed_ok, source="synthetic"):
                added += 1
    return added
