"""kernel/text.py - нормализация текста, отступов и переводов строк.

Здесь же обрезка строки сниппета: через неё проходят ВСЕ выдачи, поэтому она
обязана быть одна (R-04), а не «своя» в каждом модуле. Длину лимита задаёт
механика: ядро не знает, сколько символов позволено её выдаче.
"""


def normalize_newlines(text):
    """`\\r\\n` -> `\\n`. Одиночный `\\r` остаётся как есть (так делает эталон)."""
    return str(text).replace("\r\n", "\n")


def split_lines(text):
    return normalize_newlines(text).split("\n")


def clip_snippet_line(line, limit):
    """Строка сниппета для модели: слишком длинную (minified) режем.

    `limit` приходит от механики (её квота) — числа в ядре нет.
    Пометка называет полную длину: иначе фрагмент примут за целую строку.
    """
    if len(line) <= limit:
        return line
    return line[:limit] + "… [строка обрезана, всего %d символов]" % len(line)


def redact_paths(text, roots=()):
    """Убрать из текста абсолютные корни: клиент не должен видеть пути машины (R-15).

    Путь попадает в текст в трёх видах: обычном (`D:\\proj`), прямом (`D:/proj`)
    и экранированном, каким его печатает `repr` внутри `OSError` (`D:\\\\proj`).
    Экранированный вариант заменяется первым, иначе после замены останутся
    удвоенные разделители.
    """
    value = str(text)
    for root in roots:
        if not root:
            continue
        base = str(root)
        for variant in (base.replace("\\", "\\\\"), base, base.replace("\\", "/")):
            if variant:
                value = value.replace(variant, "<PROJECT>")
    return value

