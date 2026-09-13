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
import tempfile
import threading
import uuid
from urllib.parse import urlsplit

_FILE_NAME = "agent_chats.json"
MAX_TRANSCRIPT = 300
DEFAULT_TITLE = "New chat"
# Старое название по умолчанию — чтобы авто-название работало и для уже созданных чатов.
LEGACY_DEFAULT_TITLES = ("", "New chat", "Новый чат")
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


class ChatStoreError(IOError):
    pass


def _lock(base_dir):
    key = os.path.abspath(base_dir or "")
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _path(base_dir):
    return os.path.join(base_dir, _FILE_NAME)


def _load(base_dir):
    with _lock(base_dir):
        p = _path(base_dir)
        if not os.path.isfile(p):
            return []
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            raise ChatStoreError("Хранилище чатов повреждено или недоступно: %s" % exc)
        if not isinstance(data, list):
            raise ChatStoreError("Хранилище чатов имеет неверный формат")
        return data


def _save(base_dir, chats):
    with _lock(base_dir):
        temp_path = ""
        try:
            os.makedirs(base_dir, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(
                prefix=_FILE_NAME + ".", suffix=".tmp", dir=base_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(chats, f, ensure_ascii=False, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, _path(base_dir))
            return True
        except Exception:
            return False
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
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
    with _lock(base_dir):
        chats = _load(base_dir)
    chats.sort(key=lambda c: c.get("last_used", 0), reverse=True)
    out = []
    for c in chats:
        # Чат по ключу API «устареть» по промпту не может: системный блок там
        # собирается заново на КАЖДОМ сообщении, а не один раз за чат. Помечать
        # его устаревшим — вводить пользователя в заблуждение и провоцировать
        # создавать новый чат без причины.
        is_api = (c.get("kind") or "browser") == "api"
        stale = (not is_api) and bool(c.get("primed")) and bool(current_prompt_hash) \
            and c.get("prompt_hash") != current_prompt_hash
        out.append({"id": c.get("id"), "title": c.get("title", DEFAULT_TITLE),
                    "url": c.get("url", ""), "primed": bool(c.get("primed")),
                    "site_name": c.get("site_name", ""),
                    "kind": "api" if is_api else "browser",
                    "created": int(c.get("created", 0) or 0),
                    "last_used": int(c.get("last_used", 0) or 0),
                    "prompt_stale": stale})
    return out


def find_chat(base_dir, chat_id):
    with _lock(base_dir):
        for c in _load(base_dir):
            if c.get("id") == chat_id:
                return c
    return None


def find_chat_by_url(base_dir, url):
    """Find a saved chat for the exact site conversation after a server restart."""
    def normalize(value):
        try:
            parsed = urlsplit(value or "")
            return (parsed.netloc.lower(), parsed.path.rstrip("/"))
        except Exception:
            return None

    wanted = normalize(url)
    if not wanted or not wanted[1]:
        return None
    with _lock(base_dir):
        for chat in _load(base_dir):
            if normalize(chat.get("url")) == wanted:
                return chat
    return None


def create_chat(base_dir, url="", title=DEFAULT_TITLE, primed=False):
    with _lock(base_dir):
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
        if not _save(base_dir, chats):
            raise IOError("Не удалось атомарно сохранить новый чат")
        return rec


def update_chat(base_dir, chat_id, **fields):
    with _lock(base_dir):
        chats = _load(base_dir)
        for c in chats:
            if c.get("id") == chat_id:
                c.update(fields)
                c["last_used"] = time.time()
                if not _save(base_dir, chats):
                    raise IOError("Не удалось атомарно обновить чат")
                return c
    return None


def touch_chat(base_dir, chat_id, url=None, primed=None):
    """Обновляет URL страницы / primed / время использования чата."""
    with _lock(base_dir):
        chats = _load(base_dir)
        for c in chats:
            if c.get("id") != chat_id:
                continue
            if url:
                c["url"] = url
            if primed is not None:
                c["primed"] = bool(primed)
            c["last_used"] = time.time()
            if not _save(base_dir, chats):
                raise IOError("Не удалось атомарно обновить чат")
            return c
    return None


def touch_file_read(base_dir, chat_id, path):
    """Запоминает: чат видел АКТУАЛЬНОЕ содержимое файла (read_file,
    успешная запись или self-heal показал модели файл с диска).
    Используется защитой от перезаписи файла по устаревшей памяти чата."""
    with _lock(base_dir):
        chats = _load(base_dir)
        for c in chats:
            if c.get("id") != chat_id:
                continue
            reads = c.setdefault("file_reads", {})
            reads[path] = time.time()
            # Не даём словарю расти бесконечно: держим 300 самых свежих.
            if len(reads) > 300:
                for stale_path in sorted(reads, key=reads.get)[:len(reads) - 300]:
                    del reads[stale_path]
            if not _save(base_dir, chats):
                raise IOError("Не удалось атомарно сохранить чтение файла")
            return c
    return None


def append_transcript(base_dir, chat_id, role, text):
    """Дописывает реплику (user/agent/system) в сохранённый диалог чата."""
    with _lock(base_dir):
        chats = _load(base_dir)
        for c in chats:
            if c.get("id") != chat_id:
                continue
            tr = c.setdefault("transcript", [])
            tr.append({"role": role, "text": text, "ts": time.time()})
            if len(tr) > MAX_TRANSCRIPT:
                removed = len(tr) - MAX_TRANSCRIPT
                del tr[:removed]
                c["transcript_trimmed"] = int(c.get("transcript_trimmed") or 0) + removed
            # Авто-название по первому сообщению пользователя.
            if (role == "user" and not c.get("manual_title")
                    and c.get("title") in LEGACY_DEFAULT_TITLES):
                c["title"] = title_from_prompt(text)
            c["last_used"] = time.time()
            if not _save(base_dir, chats):
                raise IOError("Не удалось атомарно сохранить сообщение")
            return c
    return None


def append_transcript_entries(base_dir, chat_id, entries):
    """Атомарно дописывает полный ход в исходном порядке ролей."""
    clean = [(str(role), str(text)) for role, text in (entries or []) if text]
    if not clean:
        return find_chat(base_dir, chat_id)
    with _lock(base_dir):
        chats = _load(base_dir)
        for chat in chats:
            if chat.get("id") != chat_id:
                continue
            transcript = chat.setdefault("transcript", [])
            now = time.time()
            for role, text in clean:
                transcript.append({"role": role, "text": text, "ts": now})
                if (role == "user" and not chat.get("manual_title")
                        and chat.get("title") in LEGACY_DEFAULT_TITLES):
                    chat["title"] = title_from_prompt(text)
            if len(transcript) > MAX_TRANSCRIPT:
                removed = len(transcript) - MAX_TRANSCRIPT
                del transcript[:removed]
                chat["transcript_trimmed"] = int(chat.get("transcript_trimmed") or 0) + removed
            chat["last_used"] = now
            if not _save(base_dir, chats):
                raise ChatStoreError("Не удалось атомарно сохранить ход чата")
            return chat
    return None


def delete_chat(base_dir, chat_id):
    with _lock(base_dir):
        chats = _load(base_dir)
        kept = [c for c in chats if c.get("id") != chat_id]
        if len(kept) == len(chats):
            return False
        return _save(base_dir, kept)
