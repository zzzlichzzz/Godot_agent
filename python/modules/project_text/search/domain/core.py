"""modules/project_text/search/domain/core.py - чистая логика поиска (R-11).

Ни `os`, ни `pathlib`, ни сокетов: домен получает относительный путь и текст,
возвращает строки ответа. Всё, что касается диска, — в адаптере порта `fs`.
Порядок, окна контекста, квота и обрезка строки воспроизведены по эталону
(`godot_tools/project_tools.py:search_project_text`) — сверка идёт по корпусу
`fixtures/corpus/project_text/search/`, не по памяти.
"""

from dataclasses import dataclass

from python.kernel.text import clip_snippet_line, split_lines

from ..settings import SNIPPET_LINE_MAX

RES_PREFIX = "res://"

#: Что вообще индексируется. `.py` — отдельный набор: это право видеть исходник
#: агента (developer mode), а не «просто расширение».
SEARCH_EXTS = frozenset({".gd", ".tscn", ".tres", ".cfg", ".godot", ".json",
                         ".txt", ".md", ".gdshader", ".shader", ".csv"})
AGENT_ONLY_SEARCH_EXTS = frozenset({".py"})

#: Шумовые каталоги: не политика доступа, а качество выдачи.
EXCLUDED_DIRS = frozenset({".godot", ".import", ".git", ".venv", "__pycache__",
                           "node_modules", ".vs", ".vscode", ".agent_history",
                           "minilich_brain"})


@dataclass(frozen=True)
class SearchQuery:
    """Нормализованный запрос: что искать, где остановиться, что пропустить."""

    needles: tuple
    keys: tuple
    max_results: int
    context_lines: int
    exclude_prefixes: tuple
    case_insensitive: bool
    extensions: frozenset


def build_query(query, max_results=30, context_lines=2, exclude_rel_prefixes=None,
                case_insensitive=False, agent_py_allowed=False):
    """Собрать запрос. Пустой `query` — не ошибка: так эталон отвечает пустым списком."""
    needles = _needles(query)
    keys = tuple(needle.lower() for needle in needles) if case_insensitive else needles
    prefixes = tuple(prefix.replace("\\", "/").lstrip("/")
                     for prefix in (exclude_rel_prefixes or ()) if prefix)
    extensions = set(SEARCH_EXTS)
    if agent_py_allowed:
        extensions |= AGENT_ONLY_SEARCH_EXTS
    return SearchQuery(needles=needles, keys=keys, max_results=int(max_results),
                       context_lines=int(context_lines),
                       exclude_prefixes=prefixes,
                       case_insensitive=bool(case_insensitive),
                       extensions=frozenset(extensions))


def _needles(query):
    raw = str(query or "").strip()
    if not raw:
        return ()
    return (raw.replace("\r\n", "\n"),)


def file_extension(rel):
    name = rel.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    return name[dot:].lower() if dot > 0 else ""


def noisy_dir(rel):
    """Путь проходит через шумовой или скрытый каталог (скрытые — всегда мимо)."""
    return any(part in EXCLUDED_DIRS or part.startswith(".")
               for part in rel.split("/")[:-1])


def is_candidate(query, rel):
    """Стоит ли читать файл: расширение и префиксы-исключения (до набора квоты)."""
    if not rel:
        return False
    if noisy_dir(rel):
        return False
    if query.exclude_prefixes and rel.lstrip("/").startswith(query.exclude_prefixes):
        return False
    return file_extension(rel) in query.extensions


def match_file(query, rel, text, counts):
    """Совпадения одного файла: `(rows, stop, truncated)`.

    `stop` — квоту набрали все подстроки, обход можно прекращать (одиночный
    запрос выходит сразу по квоте, как эталон);
    `truncated` — хотя бы одна подстрока набрала квоту. Квота, набранная ровно
    последним совпадением файла, тоже даёт `truncated=True`: так ведёт себя
    эталон, и корпус это фиксирует (кейс 006).
    """
    if not query.needles:
        return [], False, False
    lines = split_lines(text)
    haystack = [line.lower() for line in lines] if query.case_insensitive else lines
    rows = []
    truncated = False
    path = RES_PREFIX + rel
    for index, needle in enumerate(query.keys):
        if counts[index] >= query.max_results:
            continue
        hits = [number for number, line in enumerate(haystack) if needle in line]
        if not hits:
            continue
        for group in _group(hits, query.context_lines):
            rows.append({"path": path, "line": group[0] + 1,
                         "snippet": _snippet(lines, group, query.context_lines)})
            counts[index] += 1
            if counts[index] >= query.max_results:
                truncated = True
                if all(count >= query.max_results for count in counts):
                    return rows, True, truncated
                break
    return rows, False, truncated


def _group(hits, context_lines):
    """Склеить совпадения, попавшие в окно ±context_lines, в один сниппет.

    При `context_lines=0` склейки нет: разница между соседними строками больше окна.
    """
    groups = []
    for number in hits:
        if groups and context_lines > 0 and number - groups[-1][-1] <= context_lines:
            groups[-1].append(number)
        else:
            groups.append([number])
    return groups


def _snippet(lines, group, context_lines):
    low = max(0, group[0] - context_lines)
    high = min(len(lines), group[-1] + context_lines + 1)
    return "\n".join("%d: %s" % (number + 1, clip_snippet_line(lines[number], SNIPPET_LINE_MAX))
                     for number in range(low, high))

