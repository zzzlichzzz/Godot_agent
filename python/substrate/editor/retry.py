"""substrate/editor/retry.py - сколько ждать и когда повторять (ADR-0007).

Таймауты и политика повторов живут здесь и только здесь: клиент спрашивает
`attempts(reason)`, а не решает сам. Повторяются только безопасные отказы -
соединения ещё нет (`connect_failed`) или оно оборвалось (`truncated`);
`timeout` получает один повтор, потому что сервер жив и мог не успеть.
`bad_token`, `verbs_mismatch`, `wrong_project` и `frame_too_big` не повторяются
никогда: ответ не изменится. Правила: R-14, R-15.
"""

#: Установить соединение (секунды).
CONNECT_TIMEOUT = 2.0
#: Дождаться ответа на hello (секунды).
HANDSHAKE_TIMEOUT = 2.0
#: Дождаться ответа на примитив (секунды).
REPLY_TIMEOUT = 5.0

#: Отказы, после которых соединение пересоздаётся один раз.
RETRY_ON = ("connect_failed", "truncated")
#: Сколько раз повторять после `timeout`.
TIMEOUT_RETRIES = 1
#: Отказы, которые не повторяются: лечится не повтором, а человеком.
NO_RETRY = ("bad_token", "verbs_mismatch", "wrong_project", "frame_too_big",
            "unknown_verb", "bad_result", "no_bridge")


def attempts(reason):
    """Сколько повторов разрешено после отказа с причиной `reason`."""
    if reason in NO_RETRY:
        return 0
    if reason == "timeout":
        return TIMEOUT_RETRIES
    return 1 if reason in RETRY_ON else 0
