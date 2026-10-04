# -*- coding: utf-8 -*-
"""release_prepare.py - версия и changelog релиза по истории коммитов.

ЗАЧЕМ. Релиз Godot Agent собирается вручную: bump в plugin.cfg, текст "что
нового", тег, архив для загрузки. Каждый пункт можно забыть или сделать не тем,
и тогда плагин у пользователей либо не видит обновления (tag младше версии в
plugin.cfg), либо показывает пустой список изменений. Здесь три вывода
считаются из ОДНОГО источника правды - истории коммитов:

  1. next_version()   - bump SemVer по Conventional Commits;
  2. render_notes()   - текст релиза, сгруппированный по типам коммитов;
  3. bump_plugin_cfg() - новая строка version= в plugin.cfg.

ГРАНИЦА. Скрипт НЕ создаёт тег и релиз на GitHub - этим занимается
.github/workflows/release.yml. Здесь нет сети и нет записи в git: только разбор
коммитов, арифметика версии и текст. Поэтому весь модуль проверяется офлайн в
python/tests/test_release_prepare.py.

ФОРМАТ КОММИТОВ. Conventional Commits - ровно тот, что уже есть в истории
репозитория:

    feat(bridge): полные сигнатуры Godot API в выдаче api
    fix(minilich): status() - чистое чтение, без побочного эффекта
    docs: README с реальными возможностями
    fix(api)!: разбор ответа без markdown-обёртки      <- ломающее

Ломающее изменение помечается "!" после типа/скоупа либо строкой
"BREAKING CHANGE:" в теле коммита. Скоуп может быть составным
("feat(settings,refactor): ..." - такой коммит в истории есть). Коммиты без
Conventional-префикса ("Update plugin.cfg") версию не двигают, но попадают в
раздел "Прочее": в changelog полезно знать и про них.

ПРИМЕРЫ (из корня репозитория):

    python -B -X utf8 godot_agent/python/tools/release_prepare.py --dry-run
    python -B -X utf8 godot_agent/python/tools/release_prepare.py \\
        --bump minor --apply

КОДЫ ВОЗВРАТА.
    0 - план релиза построен (--apply записал файлы, если просили);
    3 - релиз не нужен: между базой и HEAD нет коммитов, двигающих версию.
        Это НЕ поломка, поэтому сообщение об ошибке не печатается.
"""
import argparse
import io
import os
import re
import subprocess
import sys
from datetime import date

# ─────────────────────────────────────────────────────────────────────────────
# Константы предметной области
# ─────────────────────────────────────────────────────────────────────────────

REPO_URL = "https://github.com/zzzlichzzz/Godot_agent"

#: Разделитель полей в выводе `git log --pretty`. Символы \x1f/\x1e не встречаются
#: в теме коммита, поэтому разбор не ломается на теме с двоеточием или скобками.
FS = "\x1f"
RS = "\x1e"

#: Тип коммита -> раздел changelog и bump-уровень, от важного к мелкому.
#: Порядок словаря задаёт порядок разделов в тексте релиза.
CATEGORIES = [
    ("breaking", "Ломающие изменения", "Breaking changes", "major"),
    ("feat",    "Новое",               "Features",          "minor"),
    ("fix",     "Исправления",         "Fixes",             "patch"),
    ("perf",    "Производительность",  "Performance",       "patch"),
    ("refactor", "Рефакторинг",        "Refactoring",       "patch"),
    ("docs",    "Документация",        "Documentation",     "none"),
    ("test",    "Тесты",               "Tests",             "none"),
    ("build",   "Сборка",              "Build",             "none"),
    ("ci",      "CI",                  "CI",                "none"),
    ("style",   "Стиль",               "Style",             "none"),
    ("other",   "Прочее",              "Other",             "none"),
]

#: Уровень bump -> множитель номера версии.
BUMP_ORDER = {"none": 0, "patch": 1, "minor": 2, "major": 3}

#: Коммиты с этими маркерами в теле не двигают версию и не попадают в notes.
#: `[skip ci]` — маркер самого workflow: он коммитит bumpplugin.cfg, и такой
#: коммит не должен тут же породить следующий релиз.
SKIP_MARKERS = ("[skip ci]", "[skip release]", "[no release]", "[ci skip]")

CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[A-Za-z]+)"
    r"(?:\((?P<scope>[^)]*)\))?"
    r"(?P<breaking>!)?"
    r":\s*(?P<desc>.+)$"
)
BREAKING_RE = re.compile(r"^BREAKING[ -]CHANGE:\s*(?P<desc>.+)$", re.MULTILINE)
VERSION_RE = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.MULTILINE)
VERSION_LINE_RE = re.compile(r'^(\s*version\s*=\s*")([^"]+)(".*)$', re.MULTILINE)
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


# ─────────────────────────────────────────────────────────────────────────────
# Разбор коммитов
# ─────────────────────────────────────────────────────────────────────────────

class Commit(object):
    """Один коммит, разобранный до полей, нужных для версии и changelog."""

    def __init__(self, sha, subject, body=""):
        self.sha = sha
        self.subject = subject.strip()
        self.body = body or ""
        self.type = "other"
        self.scope = ""
        self.breaking = False
        self.breaking_desc = ""
        self.description = self.subject
        self._parse()

    @property
    def short_sha(self):
        return self.sha[:7]

    @property
    def skipped(self):
        """Коммит помечен маркером пропуска (см. SKIP_MARKERS)."""
        haystack = (self.subject + "\n" + self.body).lower()
        return any(marker in haystack for marker in SKIP_MARKERS)

    def _parse(self):
        match = CONVENTIONAL_RE.match(self.subject)
        if match:
            self.type = match.group("type").lower()
            self.scope = (match.group("scope") or "").strip()
            self.breaking = match.group("breaking") == "!"
            self.description = match.group("desc").strip()
        # BREAKING CHANGE в теле важнее префикса: тема может быть обычной.
        body_breaking = BREAKING_RE.search(self.body)
        if body_breaking:
            self.breaking = True
            self.breaking_desc = body_breaking.group("desc").strip()
        if self.type not in CATEGORY_TYPES:
            # Незнакомый префикс ("Update plugin.cfg", ".") - это не Conventional
            # Commits. Молча считать его "other" нельзя: "Update plugin.cfg"
            # меняет то, что пользователь увидит как версию. Такие коммиты
            # попадают в "Прочее" и появляются в changelog, но версию не двигают.
            self.type = "other"
            self.description = self.subject
            self.scope = ""

    def notes_line(self, repo_url=REPO_URL, text=None):
        """Строка для changelog: `- описание (scope) ([sha](url))`.

        text передаётся для ломающих изменений: там в раздел идёт описание
        из тела коммита, а не его тема.
        """
        text = self.description if text is None else text
        if self.scope:
            text = "%s (%s)" % (text, self.scope)
        if repo_url:
            return "- %s ([%s](%s/commit/%s))" % (
                text, self.short_sha, repo_url, self.sha)
        return "- %s (%s)" % (text, self.short_sha)


CATEGORY_TYPES = set(name for name, _, _, _ in CATEGORIES)


def parse_log(raw):
    """Разбор вывода `git log --pretty` в список Commit.

    Формат строки на коммит: sha<FS>subject<FS>body<RS>.
    """
    commits = []
    for chunk in raw.split(RS):
        chunk = chunk.strip("\n")
        if not chunk.strip():
            continue
        parts = chunk.split(FS)
        if len(parts) < 2:
            continue
        sha = parts[0].strip()
        subject = parts[1]
        body = parts[2] if len(parts) > 2 else ""
        if not sha:
            continue
        commits.append(Commit(sha, subject, body))
    return commits


LOG_FORMAT = "--pretty=format:" + "%H" + FS + "%s" + FS + "%b" + RS


def read_commits(repo_root, since=None, until=None, limit=None):
    """Прочитать коммиты через `git log`. Ничего не знает про сеть."""
    args = ["log", "--no-merges", LOG_FORMAT]
    if since:
        args.append("%s..%s" % (since, until or "HEAD"))
    elif until:
        args.append(until)
    if limit:
        args.append("--max-count=%d" % limit)
    out = _git(repo_root, args)
    return parse_log(out)



def _git(repo_root, args):
    """Запустить git и вернуть stdout. Ошибка git - это ошибка скрипта."""
    try:
        proc = subprocess.run(
            ["git"] + list(args), cwd=repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=True)
    except FileNotFoundError:
        raise SystemExit("git не найден в PATH")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise SystemExit("git %s не удался: %s" % (" ".join(args), detail))
    return proc.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Текст релиза
# ─────────────────────────────────────────────────────────────────────────────

HEADING_TEMPLATES = {
    "ru": "## Что нового в %s (%s)",
    "en": "## What's new in %s (%s)",
}
PREVIOUS_TEMPLATES = {
    "ru": "Обновление с `%s`.",
    "en": "Updated from `%s`.",
}
EMPTY_TEMPLATES = {
    "ru": "_В этом релизе нет пользовательских изменений._",
    "en": "_No user-facing changes in this release._",
}
COMPARE_TEMPLATES = {
    "ru": "[Полный список изменений](%s)",
    "en": "[Full changelog](%s)",
}


def _template(table, lang, *args):
    """Текст по языку. Отдельные шаблоны, а не один с переводом слов:
    русский и английский требуют разной грамматики вокруг версии."""
    return table.get(lang, table["ru"]) % args


def group_commits(commits, lang="ru"):
    """Разложить коммиты по разделам. Порядок разделов задан CATEGORIES.

    Ломающие изменения попадают и в свой раздел, и в раздел своего типа:
    пользователю важно увидеть описание ломки в общем списке, а не искать
    её в конце. Дубли осознанные: в Markdown это две короткие строки.
    """
    buckets = {}
    breaking_bucket = []
    for commit in commits:
        if commit.skipped:
            continue
        if commit.breaking:
            # Описание ломки берётся из тела коммита, но строка остаётся
            # кликабельной, как и остальные пункты.
            breaking_bucket.append(commit.notes_line(
                text=commit.breaking_desc or commit.description))
        buckets.setdefault(commit.type, []).append(commit)
    ordered = []
    for name, ru, en, _level in CATEGORIES:
        if name == "breaking":
            if breaking_bucket:
                ordered.append((ru if lang == "ru" else en, breaking_bucket))
            continue
        items = buckets.get(name)
        if items:
            ordered.append((ru if lang == "ru" else en,
                            [item.notes_line() for item in items]))
    return ordered


def render_notes(version, previous_version, commits, lang="ru", repo_url=REPO_URL,
                 today=None):
    """Markdown-текст релиза: заголовок, разделы, ссылка на сравнение.

    Формат именно Markdown, а не BBCode: его читает и GitHub (страница
    релиза), и панель агента - agent_updater.gd конвертирует его сам.
    """
    today = today or date.today().isoformat()
    lines = [_template(HEADING_TEMPLATES, lang, version, today), ""]
    if previous_version:
        lines.append(_template(PREVIOUS_TEMPLATES, lang, previous_version))
        lines.append("")
    ordered = group_commits(commits, lang=lang)
    if not ordered:
        lines.append(_template(EMPTY_TEMPLATES, lang))
    for heading, items in ordered:
        lines.append("### %s" % heading)
        lines.append("")
        lines.extend(items)
        lines.append("")
    if repo_url and previous_version:
        compare = "%s/compare/%s...%s" % (
            repo_url, _tag(previous_version), _tag(version))
        lines.append("---")
        lines.append("")
        lines.append(_template(COMPARE_TEMPLATES, lang, compare))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _tag(version):
    return version if version.startswith("v") else "v" + version


def render_changelog_section(version, commits, lang="ru", repo_url=REPO_URL,
                              today=None):
    """Кусок для CHANGELOG.md: та же группировка, но с датой и без сравнения."""
    today = today or date.today().isoformat()
    lines = ["## %s - %s" % (version, today), ""]
    ordered = group_commits(commits, lang=lang)
    if not ordered:
        lines.append(_template(EMPTY_TEMPLATES, lang))
    for heading, items in ordered:
        lines.append("### %s" % heading)
        lines.append("")
        lines.extend(items)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def prepend_changelog(existing, section):
    """Вставить новый раздел в CHANGELOG.md после заголовка и вставки « Unreleased».

    Заголовок и пояснение сохраняются: файл перезаписывается целиком при
    каждом релизе, и без этого они бы потерялись на первом же запуске.
    """
    existing = existing or ""
    lines = existing.splitlines()
    insert_at = 0
    if lines and lines[0].startswith("# "):
        insert_at = 1
    # Пропускаем вводный текст под заголовком, но не трогаем следующий раздел.
    while insert_at < len(lines) and not lines[insert_at].startswith("## "):
        insert_at += 1
    head = lines[:insert_at]
    tail = lines[insert_at:]
    block = section.rstrip("\n").splitlines()
    return "\n".join(head + block + [""] + tail).rstrip("\n") + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# plugin.cfg
# ─────────────────────────────────────────────────────────────────────────────

def read_plugin_version(text):
    """Текущая версия из текста plugin.cfg."""
    match = VERSION_RE.search(text or "")
    if not match:
        raise ValueError("в plugin.cfg нет строки version=\"...\"")
    return match.group(1)


def bump_plugin_cfg(text, version):
    """Заменить ТОЛЬКО значение version=, не трогая остальной файл.

    Переписывать plugin.cfg через ConfigFile нельзя: он теряет пустые строки
    и комментарии, а diff релиза должен показывать ровно одну изменённую строку.
    """
    if not VERSION_LINE_RE.search(text or ""):
        raise ValueError("в plugin.cfg нет строки version=\"...\"")
    if read_plugin_version(text) == version:
        return text
    # Подставляем через функцию: в version попадает строка из git-тега.
    return VERSION_LINE_RE.sub(lambda m: m.group(1) + version + m.group(3), text, count=1)


# ─────────────────────────────────────────────────────────────────────────────
# Версия
# ─────────────────────────────────────────────────────────────────────────────

def parse_version(text):
    """'0.8.3' -> (0, 8, 3). Мусор в хвосте ('-beta1', '+build') отбрасывается."""
    match = SEMVER_RE.match((text or "").strip().lstrip("vV"))
    if not match:
        raise ValueError("не похоже на версию: %r" % (text,))
    return tuple(int(part) for part in match.groups())


def format_version(parts):
    return "%d.%d.%d" % parts


def bump_version(current, level):
    """Поднять SemVer на уровень none/patch/minor/major."""
    if level == "none":
        return current
    major, minor, patch = current
    if level == "major":
        return (major + 1, 0, 0)
    if level == "minor":
        return (major, minor + 1, 0)
    if level == "patch":
        return (major, minor, patch + 1)
    raise ValueError("неизвестный уровень bump: %r" % (level,))


def resolve_bump_level(commits, override="auto"):
    """Наибольший bump по всем коммитам. override - принудительный уровень."""
    if override and override != "auto":
        if override not in BUMP_ORDER:
            raise ValueError("неизвестный --bump: %r" % (override,))
        return override
    worst = "none"
    for commit in commits:
        if commit.skipped:
            continue
        if commit.breaking:
            level = "major"
        else:
            level = CATEGORY_LEVELS.get(commit.type, "none")
        if BUMP_ORDER[level] > BUMP_ORDER[worst]:
            worst = level
    return worst


CATEGORY_LEVELS = dict((name, level) for name, _, _, level in CATEGORIES)


# ─────────────────────────────────────────────────────────────────────────────
# Теги и план релиза
# ─────────────────────────────────────────────────────────────────────────────

def list_tags(repo_root):
    """Все теги репозитория, по убыванию разобранной версии.

    Сортировка не лексикографическая: иначе v0.9.0 оказался бы «новее» v0.10.0
    и релиз не был бы создан вовсе.
    """
    out = _git(repo_root, ["tag", "--list", "v*"])
    tags = [line.strip() for line in out.splitlines() if line.strip()]

    def sort_key(tag):
        try:
            return parse_version(tag)
        except ValueError:
            return (-1, -1, -1)

    return sorted(tags, key=sort_key, reverse=True)


def find_previous_tag(repo_root):
    """Самый свежий тег-релиз или None, если релизов ещё не было."""
    tags = list_tags(repo_root)
    return tags[0] if tags else None


def build_plan(repo_root, addon_dir, bump="auto", lang="ru", since=None,
               repo_url=REPO_URL, today=None):
    """Собрать полный план релиза из истории коммитов.

    Порядок чтения важен: текущая версия берётся из plugin.cfg, а не из
    последнего тега. Именно её показывает agent_updater.gd пользователю, и
    расхождение с тегом означало бы предложение обновиться на версию, которая
    уже установлена.
    """
    cfg_path = os.path.join(addon_dir, "plugin.cfg")
    with io.open(cfg_path, "r", encoding="utf-8") as handle:
        cfg_text = handle.read()
    current_version = read_plugin_version(cfg_text)
    current = parse_version(current_version)

    previous_tag = since if since is not None else find_previous_tag(repo_root)
    if previous_tag:
        commits = read_commits(repo_root, since=previous_tag)
    else:
        # Первый релиз: базы нет, берём всю историю ветки.
        commits = read_commits(repo_root)

    level = resolve_bump_level(commits, override=bump)
    new_version = format_version(bump_version(current, level))

    return {
        "current_version": current_version,
        "new_version": new_version,
        "previous_tag": previous_tag,
        "bump_level": level,
        "commits": commits,
        "commit_count": len(commits),
        "notes": render_notes(new_version, current_version, commits, lang=lang,
                              repo_url=repo_url, today=today),
        "changelog_section": render_changelog_section(
            new_version, commits, lang=lang, repo_url=repo_url, today=today),
        "plugin_cfg": bump_plugin_cfg(cfg_text, new_version),
        "tag": _tag(new_version),
        "needed": level != "none" and new_version != current_version,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _repo_root_default():
    """Корень git-репозитория аддона: godot_agent/python/tools -> вверх на 3."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, os.pardir, os.pardir, os.pardir))


def _addon_dir_default(repo_root):
    """Папка аддона с plugin.cfg: в этом репозитории это ./godot_agent."""
    candidate = os.path.join(repo_root, "godot_agent")
    if os.path.isfile(os.path.join(candidate, "plugin.cfg")):
        return candidate
    return repo_root


def _write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Считает версию и changelog релиза по истории коммитов.")
    parser.add_argument("--repo-root", default=None,
                        help="корень git-репозитория (по умолчанию вычисляется)")
    parser.add_argument("--addon-dir", default=None,
                        help="папка аддона с plugin.cfg (по умолчанию ./godot_agent)")
    parser.add_argument("--bump", default="auto",
                        choices=["auto", "major", "minor", "patch", "none"],
                        help="уровень повышения версии (auto - по типам коммитов)")
    parser.add_argument("--lang", default="ru", choices=["ru", "en"],
                        help="язык текста релиза")
    parser.add_argument("--since", default=None,
                        help="база диапазона коммитов; по умолчанию последний тег")
    parser.add_argument("--notes-out", default=None,
                        help="куда писать текст релиза (по умолчанию stdout)")
    parser.add_argument("--changelog", default=None,
                        help="файл CHANGELOG.md для обновления")
    parser.add_argument("--apply", action="store_true",
                        help="записать plugin.cfg и CHANGELOG.md (иначе только печать)")
    parser.add_argument("--print-plan", action="store_true",
                        help="напечатать key=value сводку для workflow")
    args = parser.parse_args(argv)

    repo_root = args.repo_root or _repo_root_default()
    addon_dir = args.addon_dir or _addon_dir_default(repo_root)

    try:
        plan = build_plan(repo_root, addon_dir, bump=args.bump, lang=args.lang,
                          since=args.since)
    except ValueError as exc:
        raise SystemExit(str(exc))

    if args.apply and plan["needed"]:
        _write(os.path.join(addon_dir, "plugin.cfg"), plan["plugin_cfg"])
        if args.changelog:
            existing = ""
            if os.path.isfile(args.changelog):
                with io.open(args.changelog, "r", encoding="utf-8") as handle:
                    existing = handle.read()
            _write(args.changelog,
                   prepend_changelog(existing, plan["changelog_section"]))

    if args.notes_out:
        _write(args.notes_out, plan["notes"])
    elif not args.print_plan:
        sys.stdout.write(plan["notes"])

    if args.print_plan:
        # Формат key=value: workflow читает эти строки через $GITHUB_OUTPUT.
        print("current_version=%s" % plan["current_version"])
        print("new_version=%s" % plan["new_version"])
        print("tag=%s" % plan["tag"])
        print("bump_level=%s" % plan["bump_level"])
        print("previous_tag=%s" % (plan["previous_tag"] or ""))
        print("commit_count=%d" % plan["commit_count"])
        print("needed=%s" % ("true" if plan["needed"] else "false"))

    # 3 - релиз не нужен. Это штатный исход, а не ошибка (см. модульный docstring).
    return 0 if plan["needed"] else 3


if __name__ == "__main__":
    sys.exit(main())

