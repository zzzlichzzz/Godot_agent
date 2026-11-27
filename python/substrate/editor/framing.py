"""substrate/editor/framing.py - кадрирование сообщений моста (ADR-0007).

Кадр: 4 байта длины big-endian + JSON UTF-8, лимит 1 МиБ. Сокета и схем здесь
нет: только байты (R-14 - транспорт, не смысл). Неполный кадр - это «данных
мало», а не ошибка: `decode` возвращает `(None, buffer)` и ждёт ещё байт.
"""

import json
import struct

#: Лимит кадра из `contract/editor_verbs.json` (`frame.max_bytes`).
MAX_FRAME = 1048576
#: Длина заголовка: 4 байта длины.
HEADER = 4


class FrameError(Exception):
    """Кадр нарушен: пустой, больше лимита или не JSON. Причина - в `reason`."""

    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


def encode(obj):
    """Объект → кадр; пустой или слишком большой объект - `FrameError`."""
    try:
        payload = json.dumps(obj, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FrameError("truncated", "не сериализуется в JSON: %s" % (exc,)) from None
    if not payload:
        raise FrameError("truncated", "пустой кадр")
    if len(payload) > MAX_FRAME:
        raise FrameError("frame_too_big", "кадр больше лимита: %d > %d"
                         % (len(payload), MAX_FRAME))
    return struct.pack(">I", len(payload)) + payload


def decode(buffer):
    """`(объект, остаток)`; `(None, buffer)` - кадр ещё не собран целиком."""
    if len(buffer) < HEADER:
        return None, buffer
    (size,) = struct.unpack(">I", buffer[:HEADER])
    if size == 0:
        raise FrameError("truncated", "пустой кадр")
    if size > MAX_FRAME:
        raise FrameError("frame_too_big", "кадр больше лимита: %d > %d"
                         % (size, MAX_FRAME))
    if len(buffer) < HEADER + size:
        return None, buffer
    body = buffer[HEADER:HEADER + size]
    try:
        obj = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise FrameError("truncated", "мусор в JSON: %s" % (exc,)) from None
    if not isinstance(obj, dict):
        raise FrameError("truncated", "кадр должен быть JSON-объектом")
    return obj, buffer[HEADER + size:]
