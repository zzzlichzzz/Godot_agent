# -*- coding: utf-8 -*-
"""v77: заготовка базы для дообучения mini-lich на сценах с GitHub.

Идея: бестолковый источник данных — берем реальные, валидные .tscn
из открытых репозиториев, ломаем их теми же правилами, что и synthetic
в ml_data.py, и добавляем в датасет как пары source="github".

Это только фундамент (v77): вызывается вручную / будет подключено к кнопке
"обучиться по GitHub" в панели в отдельной версии; сам по себе во время
тренировки не заводится — требует сети, которой нет в сандбоксе разработки —
но есть у пользователя на его ПК.
"""
import json
import os
import re
import urllib.error
import urllib.request

from . import ml_data

USER_AGENT = "godot-agent-minilich/1.0 (+github-scene-corpus)"
API_TIMEOUT_SEC = 20

# Кураторский список публичных резюме-веток — без авторизации и без какого-либо
# поиска кода (GitHub Code Search требует токен для большинства запросов) — поэтому
# надёжнее читать дерево конкретных открытых репозиториев через Contents API.
DEFAULT_REPOS = [
    "godotengine/godot-demo-projects",
]


def _api_get_json(url, github_token=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    if github_token:
        req.add_header("Authorization", "Bearer %s" % github_token)
    with urllib.request.urlopen(req, timeout=API_TIMEOUT_SEC) as resp:
        return json.loads(resp.read().decode("utf-8"))


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


def fetch_and_add_examples(project_root, addon_dir=None, repos=None, branch="master",
                            max_files=15, github_token=None, log=None):
    """Скацивает валидные .tscn из открытых репозиториев, ломает их
    теми же правилами, что synthetic (ml_data), и добавляет готовые пары в
    датасет с пометкой source="github". Возвращает число добавленных пар.
    Ничего не ломает, если сети нет или GitHub ответил ошибкой — возвращает 0."""
    import tscn_lint
    _log = log or (lambda *_a, **_k: None)
    repos = repos or DEFAULT_REPOS
    added = 0
    for repo in repos:
        if added >= max_files:
            break
        paths = _list_tscn_files(repo, branch, github_token, limit=max_files * 4)
        for path in paths:
            if added >= max_files:
                break
            try:
                scene = _fetch_raw(repo, branch, path).replace("\r\n", "\n")
            except (urllib.error.URLError, urllib.error.HTTPError, OSError):
                continue
            if "[gd_scene" not in scene or len(scene) > ml_data.MAX_SCENE_CHARS:
                continue
            try:
                fixed0, probs0 = tscn_lint.lint_and_fix_tscn(scene, project_root, addon_dir)
            except Exception:
                continue
            if probs0:
                continue  # берём за основу только уже валидные сцены
            base = fixed0
            for corrupt_fn in (ml_data._corrupt_drop_instance, ml_data._corrupt_duplicate_node):
                try:
                    result = corrupt_fn(base)
                except Exception:
                    result = None
                if not result:
                    continue
                broken = result
                try:
                    _, probs = tscn_lint.lint_and_fix_tscn(broken, project_root, addon_dir)
                except Exception:
                    continue
                if not probs:
                    continue  # поломка должна давать проблемы, иначе это не учебная пара
                try:
                    if ml_data.record_pair(project_root, broken, probs, base, source="github"):
                        added += 1
                        _log(u"[github] +1 пара из %s/%s" % (repo, path))
                except Exception:
                    pass
                break
    return added
