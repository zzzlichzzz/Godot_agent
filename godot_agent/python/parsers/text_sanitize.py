# -*- coding: utf-8 -*-
"""v86.2: очистка текста, пришедшего из веб-DOM (ответы нейросетей).

Зачем: сайты (обнаружено на qwen) подмешивают в код невидимые символы:
неразрывные пробелы U+00A0 (&nbsp; в HTML), нулевые байты, zero-width
символы, битые кодовые точки. GDScript падает на первом же таком символе:
    Parse Error: Invalid white space character U+00A0.
    Unexpected NUL character / Invalid unicode codepoint.
Код при этом «выглядит нормальным» — символы не видны глазом.

Модуль без зависимостей: используется и базовым парсером (parser_base —
первая линия, защищает ВСЕ сайты-наследники), и записью файлов проекта
(project_tools — вторая линия, на случай обходных путей).

Что делаем (консервативно, видимые символы не трогаем):
  - экзотические пробелы (NBSP, U+2000..U+200A и т.п.) -> обычный пробел;
  - юникодные разделители строк (NEL/LS/PS) и CRLF/CR -> \n;
  - невидимый мусор удаляем: NUL и прочие управляющие (кроме \t и \n),
    zero-width/би-ди маркеры, BOM/ZWNBSP, мягкий перенос, одиночные
    суррогаты и юникодные «нехарактеры» (источник ошибок
    Invalid unicode codepoint).
Кириллица, эмодзи, «умные» кавычки в строках — остаются как есть.
"""
import re

# Экзотические пробелы -> обычный пробел (U+00A0 — виновник ошибки на qwen).
_RX_SPACES = re.compile(u"[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]")

# Юникодные разделители строк -> \n (NEL U+0085, LS U+2028, PS U+2029).
_RX_NEWLINES = re.compile(u"[\u0085\u2028\u2029]")

# Невидимый мусор -> удалить:
#   C0-управляющие (включая NUL), кроме \t \n \r; DEL и C1-управляющие;
#   мягкий перенос U+00AD; zero-width и би-ди маркеры; word-joiner'ы;
#   BOM/ZWNBSP U+FEFF; interlinear annotation U+FFF9..U+FFFB;
#   одиночные суррогаты U+D800..U+DFFF; нехарактеры U+FDD0..U+FDEF, U+FFFE/U+FFFF.
_RX_JUNK = re.compile(
    u"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u0084\u0086-\u009f"
    u"\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069"
    u"\ud800-\udfff\ufdd0-\ufdef\ufeff\ufff9-\ufffb\ufffe\uffff]"
)


def sanitize_llm_text(text):
    """Очистить текст ответа нейросети от невидимых символов, ломающих
    GDScript/tscn/JSON. None/пустое возвращается как есть."""
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _RX_NEWLINES.sub("\n", text)
    text = _RX_SPACES.sub(" ", text)
    return _RX_JUNK.sub("", text)
