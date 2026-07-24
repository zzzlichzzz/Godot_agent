# -*- coding: utf-8 -*-
"""v104.12: детект лимита запросов и расписание спящего режима.

Последний из четырёх гардрейлов: сайты бесплатных чатов ограничивают
частоту запросов (HTTP 429, баннеры «Высокая нагрузка», просьбы
подождать). Раньше агент либо висел до таймаута, либо принимал
мусорный ответ за настоящий. Теперь main._reply при признаках лимита
уходит в спящий режим с нарастающей паузой и повторяет ТОТ ЖЕ запрос;
если лимит не отпустил — честно останавливается с сообщением в панель.
"""

# Нарастающие паузы спящего режима, секунд. После исчерпания — остановка.
SLEEPS = [30, 60, 120, 300]

# Маркеры лимита в тексте ответа/баннера (нижний регистр).
MARKERS = [
    u"too many requests",
    u"rate limit",
    u"resource_exhausted",
    u"quota exceeded",
    u"высокая нагрузка",
    u"слишком много запросов",
    u"превышен лимит",
    u"попробуйте позже",
    u"try again later",
]

# Маркеры проверяются только на КОРОТКИХ ответах без действия: настоящий
# ответ модели может легитимно содержать слова «rate limit» (например, при
# работе над кодом самого агента), а баннеры лимита — это ~10 слов.
# v104.13: 400 -> 160 симв. (~15 слов): короткий НАСТОЯЩИЙ ответ вроде
# «Готово. Если снова упрётся в лимит — попробуйте позже» мог ложно
# считаться баннером лимита и усыплять агента на ровном месте.
MAX_TEXT_LEN_FOR_MARKERS = 160


def reason_from_text(text, action=None):
    """Причина лимита по тексту ответа или None."""
    if action:
        return None
    low = (text or u"").strip().lower()
    if not low or len(low) > MAX_TEXT_LEN_FOR_MARKERS:
        return None
    for m in MARKERS:
        if m in low:
            return u"маркер «%s» в ответе" % m
    return None


def reason_from_status(status):
    """Причина лимита по HTTP-статусу чат-эндпоинта или None."""
    if not status:
        return None
    try:
        status = int(status)
    except (TypeError, ValueError):
        return None
    if status == 429:
        return u"HTTP 429 (too many requests)"
    if status >= 500:
        return u"HTTP %d (сервис перегружен)" % status
    return None


def sleep_seconds(attempt):
    """Пауза для попытки attempt (с нуля) или None, когда пора остановиться."""
    if 0 <= attempt < len(SLEEPS):
        return SLEEPS[attempt]
    return None
