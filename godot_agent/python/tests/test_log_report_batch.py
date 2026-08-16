# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты пакетного отчёта об ошибках запуска игры (log_reader.format_report).

Что изменилось и почему. Раньше модели предписывалось «исправляй ПО ОДНОЙ,
начиная с первой». Причина была верной (сообщения 2..N часто следствие
первого), но цена высокая: пять ошибок = пять обращений к модели, а по API это
пять оплаченных запросов, и на бесплатных тарифах первым упирается именно
лимит числа запросов.

Теперь: исправить ВСЕ НЕЗАВИСИМЫЕ ошибки одним ответом, но не гнаться за
следствиями, плюс группировка ошибок по файлам.
"""
import sys

import log_reader as LR

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


def err(msg, loc="", count=1, context=""):
    return {"message": msg, "location": loc, "count": count, "context": context}


REPORT = {
    "log_time": "12:34:56",
    "age_minutes": 2,
    "already_sent": False,
    "total_unique": 5,
    "errors": [
        err(u"Invalid access to property 'velocity'",
            u"at: _physics_process (res://player.gd:22)", context=u">> velocity.x = 1"),
        err(u"Identifier 'GameManager' not declared",
            u"at: _ready (res://player.gd:8)"),
        err(u"Node not found: /root/Hud",
            u"at: _ready (res://ui/hud.gd:5)", count=3),
        err(u"Something without location"),
    ],
    "input_actions": ["jump", "move_left"],
}

text = LR.format_report(REPORT)

# ---------------------------------------------------------------------------
# 1) Новая стратегия исправления
# ---------------------------------------------------------------------------
check(u"инструкции «исправляй по одной» больше нет",
      u"ПО ОДНОЙ" not in text)
check(u"сказано исправить все независимые одним ответом",
      u"НЕЗАВИСИМЫЕ" in text and u"ОДНИМ ответом" in text)
check(u"план предложен для правок в разных файлах", u"action=plan" in text)
check(u"про общую причину сказано отдельно",
      u"ОДНОЙ причиной" in text and u"ТОЛЬКО причину" in text)
check(u"запрещено заглушать следствия проверками на null",
      u"null" in text and u"заглушай" in text)
check(u"разрешено оставить ошибку, если не уверен", u"не уверен" in text)

# ---------------------------------------------------------------------------
# 2) Группировка по файлам
# ---------------------------------------------------------------------------
check(u"файл с двумя ошибками подписан группой",
      u"--- Файл res://player.gd: 2 ошибок(и)" in text, text[:400])
check(u"файл с одной ошибкой группой не подписан",
      u"res://ui/hud.gd: 1" not in text)
i_player = text.find(u"res://player.gd: 2")
i_first = text.find(u"Invalid access")
i_second = text.find(u"not declared")
i_hud = text.find(u"Node not found")
check(u"ошибки одного файла идут подряд после его подписи",
      0 < i_player < i_first < i_second < i_hud)

check(u"нумерация ошибок сквозная и полная",
      all((u"Ошибка %d/4" % k) in text for k in (1, 2, 3, 4)))
check(u"ошибка без файла тоже попала в отчёт",
      u"Something without location" in text)

# ---------------------------------------------------------------------------
# 3) Всё, что было полезного, сохранилось
# ---------------------------------------------------------------------------
check(u"время лога на месте", u"12:34:56" in text)
check(u"количество уникальных ошибок на месте", u"Уникальных ошибок: 4" in text)
check(u"контекст кода приложен", u">> velocity.x = 1" in text)
check(u"повторы посчитаны", u"повторилась 3 раз" in text)
check(u"справка InputMap на месте", u"InputMap" in text and u'"jump"' in text)
check(u"сказано, что фрагменты равнозначны read_file",
      u"read_file" in text)
check(u"про обрезанные ошибки сказано",
      u"Ещё 1 ошибок обрезано" in text)

# ---------------------------------------------------------------------------
# 4) Определение файла по строке location
# ---------------------------------------------------------------------------
check(u"файл из «at: func (res://x.gd:12)»",
      LR._file_of({"location": u"at: _ready (res://a/b.gd:12)"}) == u"res://a/b.gd")
check(u"файл из строки без скобок",
      LR._file_of({"location": u"res://c.gd"}) == u"res://c.gd")
check(u"нет location -> пустая строка", LR._file_of({}) == u"")
check(u"мусорный location -> пустая строка",
      LR._file_of({"location": u"at: somewhere unknown"}) == u"")

# ---------------------------------------------------------------------------
# 5) Пустой и вырожденный отчёт не ломают форматирование
# ---------------------------------------------------------------------------
empty = LR.format_report({"log_time": "1", "errors": [], "total_unique": 0,
                          "input_actions": None})
check(u"отчёт без ошибок собирается", isinstance(empty, str) and len(empty) > 0)
check(u"в пустом отчёте нет подписей групп", u"--- Файл" not in empty)

one = LR.format_report({"log_time": "1", "total_unique": 1,
                        "errors": [err(u"E", u"at: f (res://a.gd:1)")],
                        "input_actions": []})
check(u"одна ошибка — без подписи группы", u"--- Файл" not in one)
check(u"одна ошибка пронумерована", u"Ошибка 1/1" in one)
check(u"пустой InputMap описан отдельно", u"НЕТ пользовательских действий" in one)

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
