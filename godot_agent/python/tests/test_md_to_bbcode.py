# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты Markdown -> BBCode (md_to_bbcode).

Главное: ответ по API должен выглядеть в панели так же, как ответ из
браузера, а текст модели не должен случайно превращаться в BBCode-теги.
Отдельно проверяется, что подчёркивания в именах GDScript не становятся
курсивом — это самая частая опасность в ответах про Godot.
"""
import re
import sys

import md_to_bbcode as M

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


# ---------------------------------------------------------------------------
# 1) Экранирование скобок
# ---------------------------------------------------------------------------
check(u"открывающая скобка экранирована", M.escape(u"[") == u"[lb]")
check(u"закрывающая скобка экранирована", M.escape(u"]") == u"[rb]")
check(u"обе скобки за ОДИН проход (наивные две замены дают [lb[rb])",
      M.escape(u"[]") == u"[lb][rb]")
check(u"реальный случай: массив в тексте",
      M.escape(u"array[0]") == u"array[lb]0[rb]")
check(u"текст без скобок не меняется", M.escape(u"обычный текст") == u"обычный текст")

# ---------------------------------------------------------------------------
# 2) Инлайн-разметка
# ---------------------------------------------------------------------------
check(u"жирный", M.to_bbcode(u"это **важно** очень") == u"это [b]важно[/b] очень")
check(u"курсив", M.to_bbcode(u"это *важно* очень") == u"это [i]важно[/i] очень")
check(u"зачёркнутый", M.to_bbcode(u"это ~~убрано~~") == u"это [s]убрано[/s]")
check(u"инлайн-код", M.to_bbcode(u"вызови `get_node()`")
      == u"вызови [code]get_node()[/code]")
check(u"жирный курсив ***текст***",
      M.to_bbcode(u"***важно***") == u"[b][i]важно[/i][/b]")
check(u"разметка внутри жирного работает",
      M.to_bbcode(u"**вызови `f()`**") == u"[b]вызови [code]f()[/code][/b]")
check(u"два жирных куска в строке НЕ склеиваются",
      M.to_bbcode(u"**а** и **б**") == u"[b]а[/b] и [b]б[/b]")
# Частичная вложенность «**очень *важно***» требует алгоритма delimiter runs
# CommonMark — не поддержана осознанно (см. докстринг модуля). Проверяем, что
# деградация мягкая: текст цел, теги не поломаны.
partial = M.to_bbcode(u"**очень *важно***")
check(u"частичная вложенность: текст не потерян",
      u"очень" in partial and u"важно" in partial)
check(u"частичная вложенность: теги остаются парными",
      partial.count(u"[b]") == partial.count(u"[/b]"))
check(u"ссылка сводится к подписи (как в браузерном режиме)",
      M.to_bbcode(u"смотри [документацию](https://example.org/x) тут")
      == u"смотри документацию тут")
check(u"звёздочка не парная — остаётся текстом",
      u"[i]" not in M.to_bbcode(u"умножение 2 * 3 * 4"))

# ---------------------------------------------------------------------------
# 3) Подчёркивания в именах GDScript НЕ курсив
# ---------------------------------------------------------------------------
gd = M.to_bbcode(u"Переопредели _ready и _physics_process, потом take_damage.")
check(u"_ready / _physics_process не стали курсивом", u"[i]" not in gd)
check(u"имена сохранены дословно",
      u"_ready" in gd and u"_physics_process" in gd and u"take_damage" in gd)
check(u"__двойное подчёркивание__ тоже не жирный",
      u"[b]" not in M.to_bbcode(u"константа __MAX__ в коде"))

# ---------------------------------------------------------------------------
# 4) Блоки кода
# ---------------------------------------------------------------------------
block = M.to_bbcode(u"Вот код:\n```gdscript\nfunc _ready():\n\tpass\n```\nготово")
check(u"тело блока кода в [code]", u"[code]func _ready():\n\tpass[/code]" in block)
check(u"язык блока в шапке", u"\u25b8 gdscript" in block)
check(u"цвета шапки как у браузерных парсеров",
      u"[bgcolor=#1f2430][color=#8ab4f8]" in block)
check(u"рамка тела как у браузерных парсеров", u"[bgcolor=#2b2b2b]" in block)
check(u"текст до и после блока сохранён",
      block.startswith(u"Вот код:") and block.endswith(u"готово"))

noland = M.to_bbcode(u"```\nprint(1)\n```")
check(u"блок без языка подписан «код»", u"\u25b8 %s" % M.DEFAULT_CODE_LANG in noland)

check(u"внутри блока кода разметка НЕ действует",
      u"[b]" not in M.to_bbcode(u"```\nx = **not bold**\n```"))
check(u"скобки внутри блока кода экранированы",
      u"[lb]0[rb]" in M.to_bbcode(u"```\narr[0] = 1\n```"))
check(u"тильды тоже открывают блок",
      u"[code]" in M.to_bbcode(u"~~~\nprint(1)\n~~~"))

unclosed = M.to_bbcode(u"текст\n```gdscript\nfunc f():\n\tpass")
check(u"незакрытый блок кода не теряет содержимое",
      u"func f():" in unclosed and u"[code]" in unclosed)

action = M.to_bbcode(u"текст\n```agent_action\n{\"action\": \"x\"}\n```")
check(u"блок agent_action не показывается пользователем как JSON",
      u'"action"' not in action and u"предлагает действие" in action)

# ---------------------------------------------------------------------------
# 5) Заголовки, списки, разделители
# ---------------------------------------------------------------------------
check(u"заголовок", M.to_bbcode(u"## Итог") == u"[b][font_size=20]Итог[/font_size][/b]")
check(u"заголовок с разметкой внутри",
      u"[b]" in M.to_bbcode(u"### Что такое **план**"))
check(u"решётка в середине строки — не заголовок",
      u"font_size" not in M.to_bbcode(u"канал #general"))

ul = M.to_bbcode(u"- первый\n- второй")
check(u"маркированный список", ul == u"\u2022  первый\n\u2022  второй")
ol = M.to_bbcode(u"1. первый\n2. второй")
check(u"нумерованный список сохраняет номера", ol == u"1. первый\n2. второй")
check(u"вложенный список сохраняет отступ",
      M.to_bbcode(u"- верх\n  - вложенный").endswith(u"  \u2022  вложенный"))
check(u"разметка внутри пункта работает",
      u"[code]" in M.to_bbcode(u"- вызови `f()`"))

check(u"горизонтальная черта", M.HR_LINE in M.to_bbcode(u"текст\n---\nещё"))
check(u"минус с пробелом — это список, а не черта",
      u"\u2022" in M.to_bbcode(u"- пункт"))

# ---------------------------------------------------------------------------
# 6) Абзацы и пустоты
# ---------------------------------------------------------------------------
check(u"три и более пустых строк сжимаются до одной",
      not re.search(r"\n{3,}", M.to_bbcode(u"а\n\n\n\n\nб")))
check(u"обрамляющие пробелы убраны",
      M.to_bbcode(u"\n\n  текст  \n\n") == u"текст")
check(u"пустой вход -> пустая строка", M.to_bbcode(u"") == u"" and M.to_bbcode(None) == u"")
check(u"перевод строки Windows не оставляет \\r",
      u"\r" not in M.to_bbcode(u"а\r\nб"))
check(u"цитата отдаётся текстом без маркера",
      M.to_bbcode(u"> цитата") == u"цитата")

# ---------------------------------------------------------------------------
# 7) Реалистичный ответ агента целиком
# ---------------------------------------------------------------------------
answer = (u"## Двойной прыжок\n\n"
          u"Правлю **player.gd**: добавляю счётчик `jumps`.\n\n"
          u"1. Считаем прыжки в `_physics_process`\n"
          u"2. Сбрасываем на земле\n\n"
          u"```gdscript\nvar jumps := 0\nfunc _physics_process(_d):\n"
          u"\tif is_on_floor(): jumps = 0\n```\n\n"
          u"Массив `states[0]` не трогаю.\n")
res = M.to_bbcode(answer)
check(u"реалистичный ответ: заголовок", u"[font_size=20]" in res)
check(u"реалистичный ответ: жирный", u"[b]player.gd[/b]" in res)
check(u"реалистичный ответ: нумерация цела", u"1. " in res and u"2. " in res)
check(u"реалистичный ответ: _physics_process не искажён",
      u"_physics_process" in res and u"[i]" not in res)
check(u"реалистичный ответ: код в рамке", u"[bgcolor=#2b2b2b][code]" in res)
check(u"реалистичный ответ: скобки в тексте экранированы",
      u"states[lb]0[rb]" in res)
check(u"реалистичный ответ: незакрытых тегов нет",
      res.count(u"[b]") == res.count(u"[/b]")
      and res.count(u"[code]") == res.count(u"[/code]")
      and res.count(u"[i]") == res.count(u"[/i]"))

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
