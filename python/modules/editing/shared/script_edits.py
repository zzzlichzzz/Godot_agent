"""modules/editing/shared/script_edits.py - байты ↔ нормализованный текст (ADR-0005).

Чистые функции без портов и диска: обе механики воронки (`write_apply` и
`write_rollback`) обязаны преобразовывать файл одинаково, иначе откат вернёт не
те байты. Стиль (`payload.newline`) и BOM восстанавливаются из сырых байтов:
`read_text` через universal newlines их скрывает.
"""

import base64
import binascii
import hashlib

from python.kernel import diff
from python.kernel.errors import AppError
from python.kernel.text import normalize_newlines

BOM = b"\xef\xbb\xbf"
RES = "res://"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def sha256_text(text):
    return sha256(text.encode("utf-8"))


def rel_of(target):
    """`res://src/x.gd` → `src/x.gd`; иное — ошибка входа."""
    value = str(target or "")
    if not value.startswith(RES) or len(value) <= len(RES):
        raise AppError("invalid_input", "цель шага должна быть res://-путём: %r" % target)
    return value[len(RES):]


def decode(raw):
    """(нормализованный текст, стиль переводов строк, был ли BOM)."""
    bom = raw.startswith(BOM)
    body = raw[len(BOM):] if bom else raw
    newline = "crlf" if b"\r\n" in body else "lf"
    text = normalize_newlines(body.decode("utf-8", "replace"))
    return text, newline, bom


def encode(text, newline, bom):
    """Байты в исходном стиле: CRLF возвращается построчно, BOM — перед текстом."""
    body = text.replace("\n", "\r\n") if newline == "crlf" else text
    raw = body.encode("utf-8")
    return (BOM + raw) if bom else raw


def apply_step(raw, step):
    """Новые байты шага; create/delete не маскируются под script_edit."""
    target = step.get("target") or ""
    op = step.get("op")
    if op == "create":
        if step.get("expected_hash") != "":
            raise AppError("invalid_input", "create требует пустой expected_hash: %s"
                           % target)
        payload = step.get("payload") or {}
        text = payload.get("text")
        newline = payload.get("newline") or "lf"
        if not isinstance(text, str) or newline not in ("lf", "crlf"):
            raise AppError("invalid_input", "некорректный payload create: %s" % target)
        return encode(text, newline, False)
    if op == "delete":
        if raw is None or sha256(raw) != step.get("expected_hash"):
            raise AppError("stale_plan", "файл изменился после плана: %s" % target)
        return None
    if op == "replace_raw":
        payload = step.get("payload") or {}
        value = payload.get("bytes_b64")
        if not isinstance(value, str):
            raise AppError("invalid_input", "replace_raw требует bytes_b64: %s" % target)
        try:
            result = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            raise AppError("invalid_input", "некорректный base64: %s" % target) from None
        if raw is None or sha256(raw) != step.get("expected_hash"):
            raise AppError("stale_plan", "файл изменился после плана: %s" % target)
        return result
    if op != "script_edit":
        raise AppError("invalid_input", "неизвестная файловая операция: %r" % op)
    text, newline, bom = decode(raw)
    if sha256_text(text) != step.get("expected_hash"):
        raise AppError("stale_plan",
                       "файл изменился после предпросмотра: %s" % target,
                       hint="Постройте план заново (`write_preview`)")
    payload = step.get("payload") or {}
    try:
        new_text = diff.apply_edits(text, tuple(payload.get("edits") or ()))
    except ValueError as exc:
        raise AppError("stale_plan", "правки не сходятся: %s" % target,
                       hint=str(exc)) from None
    return encode(new_text, payload.get("newline") or newline, bom)
