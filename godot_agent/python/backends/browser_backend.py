# -*- coding: utf-8 -*-
"""Браузерный бэкенд — адаптер над существующими парсерами сайтов.

Ничего не меняет в работе браузерного режима: просто заворачивает вызов
модуля-парсера в тот же интерфейс, что у ApiBackend, чтобы main.py не знал,
с чем именно разговаривает.

ПОЧЕМУ АДАПТЕР, А НЕ ОБЩИЙ БАЗОВЫЙ КЛАСС С НАСЛЕДОВАНИЕМ. У BaseSiteParser
интерфейс целиком браузерный: find_input, submit, wait_for_new_answer,
switch_to_site_window, confirm_sent, try_regenerate. Для работы по ключу это
мёртвый груз, а хуже всего — соблазн переиспользовать wait_for_new_answer
(двести строк эвристик про тишину DOM), который по API не нужен и вреден:
там есть точный finish_reason. Поэтому ApiBackend — СИБЛИНГ этого класса,
а не наследник, и общее у них только два метода ниже.
"""
from server_state import wait_driver


class BrowserBackend(object):
    """Отправка через браузер: печатает промпт на странице сайта и читает ответ."""

    kind = "browser"

    def __init__(self, parser_module):
        self._parser = parser_module

    def describe(self):
        return getattr(self._parser, "__name__", "?")

    def send(self, prompt, progress_cb=None, cancel_cb=None, prefer_url=None):
        """Возвращает то же, что и раньше возвращал парсер: словарь с text,
        action и (для Arena Battle) battle_choice. Форма ответа сохранена
        специально — обработка в main.py остаётся прежней."""
        result = self._parser.send_message_and_get_response(
            wait_driver(), prompt, progress_cb=progress_cb,
            cancel_cb=cancel_cb, prefer_url=prefer_url)
        if isinstance(result, dict):
            return result
        return {"text": result or "", "action": None}

    def pop_rate_limit_status(self):
        """HTTP-статус лимита, замеченный сетевым монитором парсера."""
        try:
            return self._parser.pop_rate_limit_network_status()
        except Exception:
            return None

    def pop_retry_after(self):
        """Сколько ждать по указанию сервиса — в браузерном режиме всегда None.

        Заголовок Retry-After у ответа сайта в принципе есть, но сетевой
        монитор его сейчас не сохраняет (он читает только статус, см.
        BaseNetMonitor._on_response_received). Поэтому здесь честный None:
        расписание пауз rate_limit.SLEEPS остаётся единственным ориентиром,
        как и было до появления работы по ключу.
        """
        return None
