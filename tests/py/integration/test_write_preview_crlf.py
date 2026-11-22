"""tests/py/integration/test_write_preview_crlf.py - стиль файла и хеш «до правки».

Дефект, который эти тесты закрывают (найден аудитом среза): `read_text` идёт
через universal newlines, поэтому `\\r\\n` в тексте не виден — признак
`payload.newline` всегда получался `"lf"`, а хеш «до правки» считался по
нормализованному тексту. Часть 2 на таких данных либо переписала бы CRLF-файл
в LF, либо получала вечный `stale_plan`.

Здесь проверяется чтение (`report.read_texts`) на двойнике `MemoryFileSystem`:
стиль по байтам, текст нормализован, `expected` — sha256 сырых байтов.
"""

import hashlib

from python.modules.editing.write_preview import report
from python.substrate.fs.memory_fs import MemoryFileSystem

PATH = "res://src/hero.gd"


class FakeContext(object):
    """Минимальный контекст: модулю нужен только порт `fs`."""

    def __init__(self, fs):
        self._fs = fs

    def port(self, name):
        assert name == "fs", name
        return self._fs


def analysis(*paths):
    return {"usages": [{"path": path, "line": 1, "column": 1,
                        "link": "declaration", "confidence": "proven",
                        "note": None} for path in paths]}


def read(text):
    fs = MemoryFileSystem({"src/hero.gd": text})
    return report.read_texts(FakeContext(fs), analysis(PATH))


def test_crlf_file_is_marked_crlf_and_hashes_raw_bytes():
    crlf = "func take_damage(x):\r\n\tpass\r\n"
    texts, newlines, expected = read(crlf)
    assert newlines[PATH] == "crlf"
    assert texts[PATH] == "func take_damage(x):\n\tpass\n"
    assert expected[PATH] == hashlib.sha256(crlf.encode("utf-8")).hexdigest()


def test_lf_file_is_marked_lf():
    texts, newlines, expected = read("func a():\n\tpass\n")
    assert newlines[PATH] == "lf"
    assert texts[PATH] == "func a():\n\tpass\n"
    assert expected[PATH] == hashlib.sha256(b"func a():\n\tpass\n").hexdigest()


def test_bom_is_stripped_from_text_but_stays_in_hash():
    raw = "\ufefffunc a():\n\tpass\n"
    texts, newlines, expected = read(raw)
    assert texts[PATH].startswith("func a():")
    assert "\ufeff" not in texts[PATH]
    assert expected[PATH] == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert expected[PATH] != hashlib.sha256(texts[PATH].encode("utf-8")).hexdigest()


def test_mixed_file_counts_as_crlf_and_text_is_uniform():
    raw = "func a():\r\n\tpass\nfunc b():\n\tpass\r\n"
    texts, newlines, _ = read(raw)
    assert newlines[PATH] == "crlf"
    assert "\r" not in texts[PATH]


def test_offsets_of_normalized_text_still_point_at_the_name():
    crlf = "func take_damage(x):\r\n\tpass\r\n"
    texts, _, _ = read(crlf)
    text = texts[PATH]
    start = text.index("take_damage")
    assert text[start:start + len("take_damage")] == "take_damage"
    assert len(text) < len(crlf)
