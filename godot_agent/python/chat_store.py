# -*- coding: utf-8 -*-
"""Хранилище чатов агента.

Каждый чат привязан к странице AI Studio (URL) и хранит:
- название (авто из первого сообщения, можно переименовать),
- сохранённый диалог (транскрипт) для восстановления в панели,
- флаг primed (обучен ли агент в этом чате мега-промптом).

Файл: <user_data_dir>/agent_chats.json (в user://, вне проекта).
"""
import json
import os
import time
import uuid

_FILE_NAME = "agent_chats.json"
MAX_TRANSCRIPT = 300
DEFAULT_TITLE = "New chat"
# Старое название по умолчанию — чтобы авто-название работало и для уже созданных чатов.
LEGACY_DEFAULT_TITLES = ("", "New chat", "Новый чат")


def _path(base_dir):
    return os.path.join(base_dir, _FILE_NAME)


def _load(base_dir):
    p = _path(base_dir)
    if not os.path.isfile(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(base_dir, chats):
    try:
        os.makedirs(base_dir, exist_ok=True)
        with open(_path(base_dir), "w", encoding="utf-8") as f:
            json.dump(chats, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def title_from_prompt(prompt):
    """Авто-название чата: первая строка первого сообщения, до 40 символов."""
    text = (prompt or "").strip()
    line = text.splitlines()[0] if text else ""
    line = " ".join(line.split())
    if len(line) > 40:
        line = line[:40].rstrip() + "…"
    return line or DEFAULT_TITLE


def list_chats(base_dir, current_prompt_hash=None):
    """Список чатов для панели (без транскриптов, свежие сверху).
    v48: плюс сайт нейросети, времена и признак устаревшего промпта — чат,
    обученный старой версией PRIMING_TEMPLATE, может не знать новых действий."""
    chats = _load(base_dir)
    chats.sort(key=lambda c: c.get("last_used", 0), reverse=True)
    out = []
    for c in chats:
        stale = bool(c.get("primed")) and bool(current_prompt_hash) \
            and c.get("prompt_hash") != current_prompt_hash
        out.append({"id": c.get("id"), "title": c.get("title", DEFAULT_TITLE),
                    "url": c.get("url", ""), "primed": bool(c.get("primed")),
                    "site_name": c.get("site_name", ""),
                    "created": int(c.get("created", 0) or 0),
                    "last_used": int(c.get("last_used", 0) or 0),
                    "prompt_stale": stale})
    return out


def find_chat(base_dir, chat_id):
    for c in _load(base_dir):
        if c.get("id") == chat_id:
            return c
    return None


def create_chat(base_dir, url="", title=DEFAULT_TITLE, primed=False):
    chats = _load(base_dir)
    rec = {
        "id": uuid.uuid4().hex[:12],
        "title": title or DEFAULT_TITLE,
        "manual_title": False,
        "url": url or "",
        "primed": bool(primed),
        "created": time.time(),
        "last_used": time.time(),
        "transcript": [],
    }
    chats.append(rec)
    _save(base_dir, chats)
    return rec


def update_chat(base_dir, chat_id, **fields):
    chats = _load(base_dir)
    for c in chats:
        if c.get("id") == chat_id:
            c.update(fields)
            c["last_used"] = time.time()
            _save(base_dir, chats)
            return c
    return None


def touch_chat(base_dir, chat_id, url=None, primed=None):
    """Обновляет URL страницы / primed / время использования чата."""
    chats = _load(base_dir)
    for c in chats:
        if c.get("id") == chat_id:
            if url:
                c["url"] = url
            if primed is not None:
                c["primed"] = bool(primed)
            c["last_used"] = time.time()
            _save(base_dir, chats)
            return c
    return None


def touch_file_read(base_dir, chat_id, path):
    """Запоминает: чат видел АКТУАЛЬНОЕ содержимое файла (read_file,
    успешная запись или self-heal показал модели файл с диска).
    Используется защитой от перезаписи файла по устаревшей памяти чата."""
    chats = _load(base_dir)
    for c in chats:
        if c.get("id") == chat_id:
            reads = c.setdefault("file_reads", {})
            reads[path] = time.time()
            # Не даём словарю расти бесконечно: держим 300 самых свежих.
            if len(reads) > 300:
                for stale_path in sorted(reads, key=reads.get)[:len(reads) - 300]:
                    del reads[stale_path]
            _save(base_dir, chats)
            return c
    return None


def append_transcript(base_dir, chat_id, role, text):
    """Дописывает реплику (user/agent/system) в сохранённый диалог чата."""
    chats = _load(base_dir)
    for c in chats:
        if c.get("id") == chat_id:
            tr = c.setdefault("transcript", [])
            tr.append({"role": role, "text": text, "ts": time.time()})
            if len(tr) > MAX_TRANSCRIPT:
                del tr[:len(tr) - MAX_TRANSCRIPT]
            # Авто-название по первому сообщению пользователя.
            if (role == "user" and not c.get("manual_title")
                    and c.get("title") in LEGACY_DEFAULT_TITLES):
                c["title"] = title_from_prompt(text)
            c["last_used"] = time.time()
            _save(base_dir, chats)
            return c
    return None


def delete_chat(base_dir, chat_id):
    chats = [c for c in _load(base_dir) if c.get("id") != chat_id]
    _save(base_dir, chats)
