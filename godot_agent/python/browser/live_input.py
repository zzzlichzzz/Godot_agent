# -*- coding: utf-8 -*-
"""v88.11/v88.14: живой ввод — зеркалирование текста из панели агента в поле сайта.

Пользователь печатает в панели Godot, панель с тротлингом (~0.35 с) шлёт
текущий текст на POST /chat/live_input. Сервер доводит поле сайта до этого
текста КЛАВИШАМИ (Selenium send_keys: BACKSPACE + символы), без submit и
без JS value=/insertText — чтобы сайт видел набор, а не программную подстановку.

Гарантии (проверены тестами test_v88_11_live_input.py):
- никогда не бросает исключения наружу — зеркалирование best effort;
- НЕ трогает браузер, пока идёт обмен «промпт -> ответ» (busy_fn):
  конвейер send_message_and_get_response сам вставляет финальный промпт
  и сверяет его (v88.4) — живой ввод ему не мешает;
- устаревшие обновления отбрасываются по номеру seq (сеть могла переставить
  запросы местами), одинаковый текст не вставляется дважды;
- одновременные запросы сериализуются локом: в браузер пишет один поток.
"""
import threading


class LiveInputMirror(object):
    """Принимает (seq, text) от панели и набирает text в поле ввода сайта."""

    def __init__(self, get_driver, get_parser, busy_fn, prefer_url_fn=None):
        self._get_driver = get_driver        # () -> driver | None (БЕЗ ожидания)
        self._get_parser = get_parser        # () -> BaseSiteParser | None
        self._busy_fn = busy_fn              # () -> bool: идёт обмен «промпт->ответ»
        self._prefer_url_fn = prefer_url_fn  # () -> url вкладки текущего чата | None
        self._lock = threading.Lock()
        self._last_seq = -1
        self._last_text = None               # последний УСПЕШНО применённый текст

    def apply(self, seq, text):
        """Набрать text в поле сайта. Возвращает dict для jsonify:
        {"ok": bool, "applied": bool, "reason": str}."""
        if not isinstance(text, str):
            text = u"" if text is None else str(text)
        try:
            seq = int(seq)
        except (TypeError, ValueError):
            seq = None
        with self._lock:
            return self._apply_locked(seq, text)

    def _apply_locked(self, seq, text):
        if seq is not None:
            if seq <= self._last_seq:
                return {"ok": True, "applied": False, "reason": "stale_seq"}
            self._last_seq = seq
        try:
            busy = bool(self._busy_fn())
        except Exception:
            busy = True
        if busy:
            # Идёт обмен: конвейер отправки сам работает с полем ввода.
            # Текст не потерян — панель дошлёт актуальный после обмена.
            return {"ok": True, "applied": False, "reason": "busy"}
        if text == self._last_text:
            return {"ok": True, "applied": False, "reason": "same_text"}
        try:
            driver = self._get_driver()
        except Exception:
            driver = None
        if driver is None:
            return {"ok": True, "applied": False, "reason": "no_browser"}
        try:
            parser = self._get_parser()
        except Exception:
            parser = None
        if parser is None:
            return {"ok": True, "applied": False, "reason": "no_parser"}
        prefer_url = None
        if self._prefer_url_fn is not None:
            try:
                prefer_url = self._prefer_url_fn()
            except Exception:
                prefer_url = None
        try:
            ok = bool(parser.mirror_input(driver, text, prefer_url=prefer_url))
        except Exception as e:
            return {"ok": False, "applied": False, "reason": "error: %s" % e}
        if not ok:
            return {"ok": True, "applied": False, "reason": "no_input_field"}
        self._last_text = text
        return {"ok": True, "applied": True, "reason": ""}
