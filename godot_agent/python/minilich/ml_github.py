# -*- coding: utf-8 -*-
"""v77/v81: дообучение mini-lich на сценах с GitHub.

v81: запуск кнопкой из панели; пользователь сам указывает ссылки на
репозитории; берём ТОЛЬКО сцены Godot 4 (format=3, без классов Godot 3);
виды порчи расширены под правила линтера v80. Лимиты датасета (4 МБ /
2000 пар / сцены до 6000 символов) действуют и здесь — гигабайты примеров
записать невозможно. Без сети ничего не ломает — возвращает 0.
"""
import json
import re
import urllib.error
import urllib.request

from . import ml_data

USER_AGENT = "godot-agent-minilich/1.0 (+github-scene-corpus)"
API_TIMEOUT_SEC = 20

DEFAULT_REPOS = [
    "godotengine/godot-demo-projects",
]

_FORMAT3_RE = re.compile(r'\[gd_scene[^\]\n]*\bformat=3\b')
# Классы/типы, которых в Godot 4 нет — значит сцена из Godot 3, учиться на ней вредно.
_GD3_MARKERS = (
    'type="Spatial"', 'type="KinematicBody"', 'type="KinematicBody2D"',
    'type="RigidBody"', 'type="GIProbe"', 'type="ARVROrigin"',
    "PoolStringArray(", "PoolVector2Array(", "PoolVector3Array(",
    "PoolColorArray(", "PoolIntArray(", "PoolRealArray(", "PoolByteArray(",
)


def _parse_repo_spec(spec):
    """«owner/repo», полная ссылка или ссылка с веткой (/tree/branch) ->
    (repo, branch|None). Не похоже на репозиторий -> None."""
    s = (spec or "").strip().strip(",;")
    if not s:
        return None
    s = re.sub(r"^https?://(www\.)?github\.com/", "", s)
    s = re.sub(r"\.git$", "", s.strip("/"))
    parts = s.split("/")
    if len(parts) < 2:
        return None
    repo = "%s/%s" % (parts[0], parts[1])
    if not re.match(r"^[\w.-]+/[\w.-]+$", repo):
        return None
    branch = None
    if len(parts) >= 4 and parts[2] == "tree":
        branch = parts[3]
    return repo, branch


def parse_repos_text(text):
    """Строка из панели (ссылки через запятую/пробел/перевод строки) ->
    список (repo, branch|None) без дублей."""
    out = []
    for tok in re.split(r"[\s,;]+", text or ""):
        parsed = _parse_repo_spec(tok)
        if parsed and parsed not in out:
            out.append(parsed)
    return out


def _acceptable_scene(scene):
    """Только Godot 4: заголовок format=3 и никаких классов Godot 3."""
    if not scene or "[gd_scene" not in scene:
        return False
    if not _FORMAT3_RE.search(scene):
        return False
    for marker in _GD3_MARKERS:
        if marker in scene:
            return False
    return True


def _api_get_json(url, github_token=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    if github_token:
        req.add_header("Authorization", "Bearer %s" % github_token)
    with urllib.request.urlopen(req, timeout=API_TIMEOUT_SEC) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _default_branch(repo, github_token=None):
    try:
        data = _api_get_json("https://api.github.com/repos/%s" % repo, github_token)
        return data.get("default_branch") or None
    except Exception:
        return None


def _list_tscn_files(repo, branch="master", github_token=None, limit=200):
    """Дерево репозитория одним запросом (Git Trees API, recursive) —
    возвращает список путей вида "foo/bar.tscn"."""
    url = "https://api.github.com/repos/%s/git/trees/%s?recursive=1" % (repo, branch)
    try:
        data = _api_get_json(url, github_token)
    except Exception:
        return []
    out = []
    for item in data.get("tree", []) or []:
        path = item.get("path", "")
        if item.get("type") == "blob" and path.endswith(".tscn"):
            out.append(path)
            if len(out) >= limit:
                break
    return out


def _fetch_raw(repo, branch, path):
    url = "https://raw.githubusercontent.com/%s/%s/%s" % (repo, branch, path)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=API_TIMEOUT_SEC) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _corruptions():
    """Виды порчи для учебных пар — включая ошибки, которые ловят правила v80."""
    return (
        ml_data._corrupt_drop_equals,
        ml_data._corrupt_unquote_string,
        ml_data._corrupt_drop_instance,
        ml_data._corrupt_duplicate_node,
    )


def fetch_and_add_examples(project_root, addon_dir=None, repos=None, repos_text=None,
                            branch=None, max_files=15, github_token=None, log=None):
    """Скачивает валидные .tscn (только Godot 4) из указанных репозиториев,
    ломает их теми же правилами, что синтетика, и добавляет пары в датасет
    (source="github"). Возвращает число добавленных пар."""
    import tscn_lint
    _log = log or (lambda *_a, **_k: None)
    if repos_text:
        specs = parse_repos_text(repos_text)
    else:
        specs = [(r, branch) for r in (repos or DEFAULT_REPOS)]
    if not specs:
        _log(u"[github] не понял ни одной ссылки — нужен вид github.com/владелец/репозиторий.")
        return 0
    added = 0
    for repo, br in specs:
        if added >= max_files:
            break
        branches = [br] if br else []
        if not branches:
            db = _default_branch(repo, github_token)
            branches = [db] if db else ["master", "main"]
        paths = []
        used_branch = None
        for b in branches:
            paths = _list_tscn_files(repo, b, github_token, limit=max_files * 6)
            if paths:
                used_branch = b
                break
        if not paths:
            _log(u"[github] %s: не нашёл .tscn (репозиторий закрыт/не существует или нет сети)." % repo)
            continue
        _log(u"[github] %s (ветка %s): найдено сцен: %d — беру только Godot 4 (format=3)." % (repo, used_branch, len(paths)))
        got_here = 0
        for path in paths:
            if added >= max_files:
                break
            try:
                scene = _fetch_raw(repo, used_branch, path).replace("\r\n", "\n")
            except (urllib.error.URLError, urllib.error.HTTPError, OSError):
                continue
            if not _acceptable_scene(scene) or len(scene) > ml_data.MAX_SCENE_CHARS:
                continue
            try:
                fixed0, probs0 = tscn_lint.lint_and_fix_tscn(scene, project_root, addon_dir)
            except Exception:
                continue
            if probs0:
                continue  # за основу берём только уже валидные сцены
            base = fixed0
            for corrupt_fn in _corruptions():
                try:
                    result = corrupt_fn(base)
                except Exception:
                    result = None
                if not result:
                    continue
                broken = result[0] if isinstance(result, tuple) else result
                fixed = result[1] if isinstance(result, tuple) else base
                try:
                    _, probs = tscn_lint.lint_and_fix_tscn(broken, project_root, addon_dir)
                except Exception:
                    continue
                if not probs:
                    continue  # поломка должна давать проблемы, иначе это не учебная пара
                try:
                    if ml_data.record_pair(project_root, broken, probs, fixed, source="github"):
                        added += 1
                        got_here += 1
                        _log(u"[github] +1 пара из %s/%s" % (repo, path))
                except Exception:
                    pass
                break
        if not got_here:
            _log(u"[github] %s: новых пар не добавилось (уже в датасете или сцены не подошли)." % repo)
    return added
