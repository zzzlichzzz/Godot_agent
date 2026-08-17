# -*- coding: utf-8 -*-
"""Markdown -> BBCode для панели агента.

ЗАЧЕМ. Панель рисует ответы через RichTextLabel с bbcode_enabled, и браузерные
парсеры отдают ей именно BBCode: они конвертируют HTML страницы сайта прямо в
JS-экстракторе. По API никакого HTML нет — модель присылает Markdown. Без
конвертации чат поехал бы: «**жирный**» текстом, ``` вместо блоков кода,
«# Заголовок» решёткой.

ЦЕЛЬ — ВИЗУАЛЬНАЯ ИДЕНТИЧНОСТЬ РЕЖИМОВ. Все теги, цвета и разделители взяты
из JS-экстрактора deepseek_parser (JS_EXTRACT): тот же заголовок блока кода,
те же цвета, тот же символ горизонтальной черты. Пользователь не должен
видеть разницы между ответом из браузера и ответом по ключу.

ЧЕГО ЗДЕСЬ СОЗНАТЕЛЬНО НЕТ.
  * Курсив через подчёркивания (_текст_, __текст__). В Markdown это законный
    синтаксис, но агент пишет про GDScript, где подчёркивания в именах —
    норма: _ready, _physics_process, take_damage, MAX_SPEED. Поддержка
    превратила бы «_ready() и _process()» в кашу из курсива. Поддержаны
    только звёздочки — в обычном тексте они почти не встречаются.
  * Полноценный CommonMark. Разбор построчный и намеренно простой: модели
    пишут предсказуемый Markdown, а вложенные конструкции и «ленивые»
    продолжения абзацев здесь только добавили бы способов ошибиться.
  * Алгоритм парных ограничителей CommonMark. Поддержаны: «**жирный**»,
    «*курсив*», «***и то и другое***», разметка внутри жирного («**вызови
    `f()`**»). НЕ поддержана частичная вложенность вида «**очень *важно***»:
    правильно разобрать её можно только настоящим алгоритмом delimiter runs,
    а дешёвые приёмы ломают куда более частый случай «**а** и **б**» (жадный
    поиск склеил бы их в один жирный кусок). Такая строка деградирует мягко:
    текст сохраняется полностью, лишней остаётся одна звёздочка.
  * Ссылки отдаются только текстом, без адреса — ровно как в браузерном
    режиме, где тег <a> сводится к своему содержимому.
"""
import re

# Цвета и разметка — копия из JS_EXTRACT браузерных парсеров.
CODE_HEADER = u"[bgcolor=#1f2430][color=#8ab4f8] \u25b8 %s [/color][/bgcolor]\n"
CODE_BODY = u"[bgcolor=#2b2b2b][code]%s[/code][/bgcolor]"
HR_LINE = u"\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015"
HEADING_FMT = u"[b][font_size=20]%s[/font_size][/b]"
ACTION_PLACEHOLDER = (u"[color=#888888]— агент предлагает действие "
                      u"(см. ниже) —[/color]")
DEFAULT_CODE_LANG = u"код"

_BRACKETS_RE = re.compile(r"[\[\]]")

_FENCE_RE = re.compile(r"^\s*(```+|~~~+)[ \t]*([A-Za-z0-9_+#.-]*)[ \t]*$")
_HEADING_RE = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
_HR_RE = re.compile(r"^[ \t]{0,3}((?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})$")
_UL_RE = re.compile(r"^([ \t]*)[-*+][ \t]+(.*)$")
_OL_RE = re.compile(r"^([ \t]*)(\d{1,3})[.)][ \t]+(.*)$")
_QUOTE_RE = re.compile(r"^[ \t]{0,3}>[ \t]?(.*)$")

# Инлайн-разметка. Порядок важен: сначала код (внутри него разметка не
# действует), потом двойные звёздочки, потом одинарные.
#
# Внутреннее содержимое каждой конструкции — ИМЕНОВАННАЯ группа (bold_in и
# т.д.), а не позиционная. Причина конкретная: при нумерации легко передать
# в рекурсию внешнюю группу вместо внутренней, и тогда «**текст**» подаётся
# сам в себя — бесконечная рекурсия. С именами такая ошибка невозможна.
_INLINE_RE = re.compile(
    r"(?P<code>`+[^`]+?`+)"
    r"|(?P<bolditalic>\*\*\*(?=\S)(?P<bolditalic_in>.+?)(?<=\S)\*\*\*)"
    r"|(?P<bold>\*\*(?=\S)(?P<bold_in>.+?)(?<=\S)\*\*)"
    r"|(?P<strike>~~(?=\S)(?P<strike_in>.+?)(?<=\S)~~)"
    r"|(?P<italic>\*(?=\S)(?P<italic_in>[^*\n]+?)(?<=\S)\*)"
    r"|(?P<link>!?\[(?P<link_in>[^\]\n]*)\]\([^)\s]*(?:[ \t]+\"[^\"]*\")?\))",
    re.DOTALL)


def escape(text):
    """Экранирует квадратные скобки, чтобы текст модели не был прочитан как
    BBCode.

    Одним проходом через callback, а НЕ двумя последовательными заменами:
    подстановка «[» -> «[lb]» сама содержит «]», и второй проход испортил бы
    её, превратив в «[lb[rb]». В JS-экстракторе это сделано так же и по той
    же причине.
    """
    return _BRACKETS_RE.sub(
        lambda m: u"[lb]" if m.group(0) == u"[" else u"[rb]", text or u"")


def _inline(text):
    """Инлайн-разметка одной строки (или содержимого элемента списка)."""
    out = []
    pos = 0
    src = text or u""
    for m in _INLINE_RE.finditer(src):
        if m.start() > pos:
            out.append(escape(src[pos:m.start()]))
        pos = m.end()
        if m.group("code"):
            body = m.group("code").strip("`")
            out.append(u"[code]%s[/code]" % escape(body))
        elif m.group("bolditalic"):
            out.append(u"[b][i]%s[/i][/b]" % _inline(m.group("bolditalic_in")))
        elif m.group("bold"):
            out.append(u"[b]%s[/b]" % _inline(m.group("bold_in")))
        elif m.group("strike"):
            out.append(u"[s]%s[/s]" % _inline(m.group("strike_in")))
        elif m.group("italic"):
            out.append(u"[i]%s[/i]" % _inline(m.group("italic_in")))
        elif m.group("link"):
            # Только подпись: адрес, как и в браузерном режиме, не показываем.
            out.append(_inline(m.group("link_in")))
    if pos < len(src):
        out.append(escape(src[pos:]))
    return u"".join(out)


def _code_block(lang, lines):
    """Блок кода: шапка с языком + тело в рамке, как у браузерных парсеров."""
    body = u"\n".join(lines)
    header = CODE_HEADER % escape(lang or DEFAULT_CODE_LANG)
    return u"\n" + header + (CODE_BODY % escape(body)) + u"\n"


def to_bbcode(text):
    """Markdown ответа модели -> BBCode для панели."""
    src = (text or u"").replace(u"\r\n", u"\n").replace(u"\r", u"\n")
    lines = src.split(u"\n")
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        fence = _FENCE_RE.match(line)
        if fence:
            marker, lang = fence.group(1)[:3], fence.group(2)
            body = []
            i += 1
            while i < n:
                closing = _FENCE_RE.match(lines[i])
                if closing and closing.group(1)[:3] == marker and not closing.group(2):
                    i += 1
                    break
                body.append(lines[i])
                i += 1
            if (lang or "").lower() == "agent_action":
                # Обычно блок действия вырезан раньше (api_backend), но если
                # он всё-таки дошёл сюда — показываем ту же заглушку, а не
                # служебный JSON: пользователю он ничего не говорит.
                out.append(u"\n" + ACTION_PLACEHOLDER + u"\n")
            else:
                out.append(_code_block(lang, body))
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            out.append(HEADING_FMT % _inline(heading.group(2)))
            i += 1
            continue

        if _HR_RE.match(line):
            out.append(u"\n" + HR_LINE + u"\n")
            i += 1
            continue

        ol = _OL_RE.match(line)
        if ol:
            indent, num, body = ol.group(1), ol.group(2), ol.group(3)
            out.append(u"%s%s. %s" % (indent.replace(u"\t", u"  "), num,
                                      _inline(body).strip()))
            i += 1
            continue

        ul = _UL_RE.match(line)
        if ul:
            indent, body = ul.group(1), ul.group(2)
            out.append(u"%s\u2022  %s" % (indent.replace(u"\t", u"  "),
                                          _inline(body).strip()))
            i += 1
            continue

        quote = _QUOTE_RE.match(line)
        if quote:
            out.append(_inline(quote.group(1)))
            i += 1
            continue

        out.append(_inline(line))
        i += 1

    result = u"\n".join(out)
    # Три и более переводов строки подряд -> два: тот же финальный шаг, что
    # в JS-экстракторе, иначе абзацы разъезжаются пустотами.
    result = re.sub(r"\n{3,}", u"\n\n", result)
    return result.strip()
