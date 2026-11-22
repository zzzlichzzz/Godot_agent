"""modules/project_text/search/tests/test_core.py - домен без IO и без Godot (R-09).

Кейсы взяты из корпуса `fixtures/corpus/project_text/search/` (R-07, R-16): тексты
записаны литералами, потому что домен получает уже прочитанный текст. Ожидания
совпадают с эталоном: их зафиксировал `tools/snapshot_record.py`, а не автор.
"""

from python.modules.project_text.search.domain import core

PLAYER = (
    "extends CharacterBody2D\n"
    "\n"
    "var health := 100\n"
    "var health_max := 100\n"
    "var speed := 300.0\n"
    "\n"
    "\n"
    "func _ready() -> void:\n"
    "\thealth = health_max\n"
    "\tprint(\"player ready\")\n"
    "\n"
    "\n"
    "func take_damage(amount: int) -> void:\n"
    "\thealth = max(0, health - amount)\n"
)

HUD = (
    "class_name HealthHud\n"
    "extends Control\n"
    "\n"
    "signal HealthChanged(value: int)\n"
    "\n"
    "\n"
    "func set_Health(value: int) -> void:\n"
    "\tpass\n"
)

CYRILLIC = (
    "# Заметки о здоровье\n"
    "\n"
    "Здоровье игрока — целое число от 0 до 100.\n"
    "Полоса здоровья обновляется по сигналу HealthChanged.\n"
)

CRLF = ("extends Node\r\n"
        "\r\n"
        "# Файл сохранён с CRLF.\r\n"
        "func _ready() -> void:\r\n"
        "\tprint(\"crlf ok\")\r\n")


def _search(text, query="health", rel="scripts/player.gd", **kwargs):
    """Прогнать один файл так же, как это делает app.py (без портов)."""
    request = core.build_query(query, **kwargs)
    counts = [0] * len(request.needles)
    rows, stop, truncated = core.match_file(request, rel, text, counts)
    return request, rows, stop, truncated


def test_extension_filter_is_the_reference_set():
    query = core.build_query("x")
    assert core.is_candidate(query, "project.godot")
    assert core.is_candidate(query, "scripts/player.gd")
    assert core.is_candidate(query, "scenes/player.tscn")
    assert core.is_candidate(query, "notes/здоровье.md")
    assert core.is_candidate(query, "data/levels.json")
    assert not core.is_candidate(query, "assets/atlas.png")
    assert not core.is_candidate(query, "tools/build.py")


def test_agent_py_is_a_capability_not_an_extension():
    assert not core.is_candidate(core.build_query("x"), "tools/build.py")
    allowed = core.build_query("x", agent_py_allowed=True)
    assert core.is_candidate(allowed, "tools/build.py")


def test_noise_and_hidden_dirs_are_not_scanned():
    query = core.build_query("x")
    assert not core.is_candidate(query, ".godot/editor/state.cfg")
    assert not core.is_candidate(query, "node_modules/pkg/readme.md")
    assert not core.is_candidate(query, "__pycache__/x.json")
    assert not core.is_candidate(query, ".agent_history/notes.md")


def test_exclude_rel_prefixes_are_normalized():
    query = core.build_query("health", exclude_rel_prefixes=["scripts\\", "", None])
    assert query.exclude_prefixes == ("scripts/",)
    assert not core.is_candidate(query, "scripts/player.gd")
    assert core.is_candidate(query, "notes/здоровье.md")


def test_empty_query_is_an_empty_answer_not_an_error():
    query = core.build_query("   ")
    assert query.needles == ()
    assert core.match_file(query, "scripts/player.gd", PLAYER, [0]) == ([], False, False)


def test_happy_path_row_and_snippet():
    _, rows, stop, truncated = _search(PLAYER, query="func _ready", max_results=5,
                                       context_lines=1)
    assert stop is False
    assert truncated is False
    assert rows == [{
        "path": "res://scripts/player.gd",
        "line": 8,
        "snippet": "7: \n8: func _ready() -> void:\n9: \thealth = health_max",
    }]

def test_case_sensitive_by_default():
    _, rows, _, _ = _search(HUD, query="health", max_results=10, context_lines=0)
    assert rows == []
    _, rows, _, _ = _search(HUD, query="Health", max_results=10, context_lines=0)
    assert [row["line"] for row in rows] == [1, 4, 7]


def test_case_insensitive_flag_matches_both_alphabets():
    _, rows, _, _ = _search(PLAYER, query="HEALTH", case_insensitive=True,
                            max_results=10, context_lines=0)
    assert [row["line"] for row in rows] == [3, 4, 9, 14]


def test_context_window_merges_neighbouring_hits():
    _, rows, _, truncated = _search(PLAYER, query="health", max_results=10,
                                    context_lines=2)
    assert truncated is False
    assert [row["line"] for row in rows] == [3, 9, 14]
    assert rows[0]["snippet"].startswith("1: extends CharacterBody2D\n"
                                         "2: \n"
                                         "3: var health := 100\n"
                                         "4: var health_max := 100\n"
                                         "5: var speed := 300.0")


def test_context_zero_keeps_hits_separate():
    _, rows, _, _ = _search(PLAYER, query="health", max_results=10, context_lines=0)
    assert [row["line"] for row in rows] == [3, 4, 9, 14]
    assert rows[0]["snippet"] == "3: var health := 100"


def test_quota_stops_scan_and_marks_truncated():
    _, rows, stop, truncated = _search(PLAYER, query="health", max_results=2,
                                       context_lines=0)
    assert len(rows) == 2
    assert stop is True
    assert truncated is True


def test_exact_quota_is_still_truncated_like_the_reference():
    """Квота, набранная ровно последним совпадением, тоже даёт `truncated`.

    Это не улучшение и не ошибка переноса: так отвечает эталон, и кейс 006
    корпуса фиксирует `truncated=true` при одном совпадении из одного.
    """
    _, rows, stop, truncated = _search(PLAYER, query="health", max_results=4,
                                       context_lines=0)
    assert len(rows) == 4
    assert stop is True
    assert truncated is True


def test_crlf_file_is_normalized_before_matching():
    _, rows, _, _ = _search(CRLF, query="crlf ok", rel="scripts/crlf_line.gd",
                            max_results=5, context_lines=1)
    assert len(rows) == 1
    assert rows[0]["line"] == 5
    assert "\r" not in rows[0]["snippet"]
    assert "5: \tprint(\"crlf ok\")" in rows[0]["snippet"]


def test_cyrillic_query_matches_exact_case():
    _, rows, _, _ = _search(CYRILLIC, query="здоровье", rel="notes/здоровье.md",
                            max_results=10, context_lines=0)
    assert [row["line"] for row in rows] == [1]
    _, rows, _, _ = _search(CYRILLIC, query="Здоровье", rel="notes/здоровье.md",
                            max_results=10, context_lines=0)
    assert [row["line"] for row in rows] == [3]


def test_long_line_is_clipped_with_full_length_note():
    line = "{\"levels\":[" + "{\"id\":\"level_03\",\"enemies\":[1,2,3]}," * 12 + "]}"
    text = "{\"levels\":[]}\n" + line + "\n"
    _, rows, _, _ = _search(text, query="level_03", rel="data/levels.json",
                            max_results=1, context_lines=0)
    assert len(rows) == 1
    assert rows[0]["line"] == 2
    snippet = rows[0]["snippet"]
    assert "… [строка обрезана, всего %d символов]" % len(line) in snippet
    assert len(snippet) < len(line)

