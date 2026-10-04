# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты расчёта версии и changelog релиза (python/tools/release_prepare.py).

ЗАЧЕМ. Релиз собирается автоматически, поэтому ошибка здесь не покажет себя
в редакторе: она тихо опубликует не тот номер версии или потеряет кусок
описаний. Все проверки офлайн и без сети: чистые функции плюс чтение истории
из настоящего временного git-репозитория.

Проверяется:
  1. Разбор Conventional Commits: тип, составной скоуп, "!"-ломание,
     BREAKING CHANGE в теле, не-конвенциональные темы ("Update plugin.cfg");
  2. Выбор уровня bump и сам bump SemVer, включая границу 0.9.0 -> 0.10.0;
  3. Группировка changelog: порядок разделов, ломки в отдельном разделе,
     пропуск коммитов с маркерами;
  4. Тексты ru/en без смешения языков;
  5. plugin.cfg: чтение и точечная замена ТОЛЬКО строки version=;
  6. CHANGELOG.md: заголовок и старые разделы сохраняются, новый сверху;
  7. build_plan на настоящем git-репозитории: since-диапазон, решение
     «релиз не нужен», первая версия без тегов;
  8. Согласованность с agent_updater.gd: собранная версия проходит его
     is_version_newer, иначе обновление предложат дважды или не предложат.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

_TOOLS = _os0.path.abspath(_os0.path.join(
    _os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir, "tools"))
if _TOOLS not in _sys0.path:
    _sys0.path.insert(0, _TOOLS)

import release_prepare as rp  # noqa: E402

results = []


def check(name, cond, detail=None):
    passed = bool(cond)
    print(u"%s -> %s" % (name, u"OK" if passed else u"FAIL"))
    if not passed and detail is not None:
        print(u"     %r" % (detail,))
    results.append(passed)


ADDON = _os0.path.abspath(_os0.path.join(
    _os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir, _os0.pardir))

# ── 1) Разбор коммитов ───────────────────────────────────────────────────────

c = rp.Commit("abc1234def", u"feat(bridge): полные сигнатуры API")
check(u"тип feat", c.type == "feat", c.type)
check(u"скоуп bridge", c.scope == "bridge", c.scope)
check(u"описание без префикса", c.description == u"полные сигнатуры API", c.description)
check(u"не ломающий", c.breaking is False)

c = rp.Commit("abc1234", u"feat(settings,refactor): редизайн настроек")
check(u"составной скоуп целиком в скобках", c.scope == "settings,refactor", c.scope)

c = rp.Commit("abc1234", u"fix(api)!: разбор без markdown")
check(u"! в теме = ломающий", c.breaking is True)
check(u"тип при ! остаётся fix", c.type == "fix", c.type)

c = rp.Commit("abc1234", u"fix(server): краш при переименовании",
              u"BREAKING CHANGE: требует Godot 4.6+")
check(u"BREAKING CHANGE в теле = ломающий", c.breaking is True)
check(u"описание ломки взято из тела",
      c.breaking_desc == u"требует Godot 4.6+", c.breaking_desc)

c = rp.Commit("abc1234", u"fix(server): краш при переименовании")
check(u"тело с чужим текстом не ломает", c.breaking is False)

for subject in (u"Update plugin.cfg", u".", u"Update README.md", u"temp_format_test.gd"):
    c = rp.Commit("abc1234", subject)
    check(u"не-конвенциональная тема %r -> other" % subject, c.type == "other", c.type)
    check(u"не-конвенциональная тема %r сохраняет текст" % subject,
          c.description == subject, c.description)

c = rp.Commit("abc1234def", u"docs: README")
check(u"short_sha 7 символов", c.short_sha == "abc1234", c.short_sha)

# ── 2) Версия ────────────────────────────────────────────────────────────────

check(u"parse_version 0.8.3", rp.parse_version("0.8.3") == (0, 8, 3))
check(u"parse_version с v", rp.parse_version("v1.2.3") == (1, 2, 3))
check(u"parse_version с -beta1", rp.parse_version("0.9.0-beta1") == (0, 9, 0))
check(u"parse_version с +build", rp.parse_version("1.0.0+abc") == (1, 0, 0))
try:
    rp.parse_version(u"не версия")
    check(u"parse_version отвергает мусор", False)
except ValueError:
    check(u"parse_version отвергает мусор", True)

check(u"patch 0.8.3 -> 0.8.4", rp.bump_version((0, 8, 3), "patch") == (0, 8, 4))
check(u"minor обнуляет patch", rp.bump_version((0, 8, 3), "minor") == (0, 9, 0))
check(u"minor 0.9.3 -> 0.10.0, а не 0.9.10",
      rp.bump_version((0, 9, 3), "minor") == (0, 10, 0))
check(u"major обнуляет minor и patch", rp.bump_version((0, 8, 3), "major") == (1, 0, 0))
check(u"none не меняет версию", rp.bump_version((0, 8, 3), "none") == (0, 8, 3))
check(u"format_version", rp.format_version((1, 2, 3)) == "1.2.3")


def level_of(*subjects):
    return rp.resolve_bump_level([rp.Commit("a" * 40, s) for s in subjects])


check(u"только fix -> patch", level_of(u"fix: a", u"fix: b") == "patch")
check(u"feat -> minor", level_of(u"fix: a", u"feat: b") == "minor")
check(u"ломающий -> major", level_of(u"feat: a", u"fix(x)!: b") == "major")
check(u"BREAKING CHANGE в теле -> major", rp.resolve_bump_level(
    [rp.Commit("a" * 40, u"chore: x", u"BREAKING CHANGE: y")]) == "major")
check(u"docs/chore/test/build -> none",
      level_of(u"docs: a", u"chore: b", u"test: c", u"build: d",
               u"Update plugin.cfg") == "none")
check(u"пустой список -> none", level_of() == "none")
check(u"feat важнее fix", level_of(u"fix: a", u"feat: b", u"fix: c") == "minor")
check(u"--bump minor перекрывает авто",
      rp.resolve_bump_level([rp.Commit("a" * 40, u"fix: a")], override="minor") == "minor")
check(u"--bump none перекрывает авто", rp.resolve_bump_level(
    [rp.Commit("a" * 40, u"feat: a")], override="none") == "none")
try:
    rp.resolve_bump_level([], override="epic")
    check(u"неизвестный --bump отвергается", False)
except ValueError:
    check(u"неизвестный --bump отвергается", True)

# ── 3) Группировка changelog ─────────────────────────────────────────────────

COMMITS = [
    rp.Commit("1" * 40, u"feat(tools): бридж"),
    rp.Commit("2" * 40, u"fix(panel): вкладки"),
    rp.Commit("3" * 40, u"docs: README"),
    rp.Commit("4" * 40, u"Update plugin.cfg"),
    rp.Commit("5" * 40, u"chore(release): 0.8.3 [skip ci]"),
    rp.Commit("6" * 40, u"fix(api)!: ломаная правка"),
]
ordered = rp.group_commits(COMMITS, lang="ru")
headings = [h for h, _ in ordered]
check(u"разделы в порядке важности",
      headings == [u"Ломающие изменения", u"Новое", u"Исправления",
                   u"Документация", u"Прочее"], headings)
check(u"ломающая правка попала в раздел ломок",
      u"ломаная правка" in ordered[0][1][0], ordered[0][1])
check(u"ломающая правка видна и в общем разделе fix",
      any(u"ломаная правка" in line for line in dict(ordered)[u"Исправления"]))
check(u"коммит релиза со [skip ci] не попал в notes",
      not any(u"0.8.3" in line for _, items in ordered for line in items))
check(u"не-конвенциональный коммит виден в Прочее",
      any(u"Update plugin.cfg" in line for line in dict(ordered)[u"Прочее"]))
check(u"пустые разделы не выводятся",
      u"Тесты" not in headings and u"Сборка" not in headings, headings)
check(u"skip-маркер узнаётся в теле",
      rp.Commit("a" * 40, u"chore: x", u"please [skip ci]").skipped is True)
check(u"обычный коммит не skipped", rp.Commit("a" * 40, u"chore: x").skipped is False)

# ── 4) Языки ─────────────────────────────────────────────────────────────────

notes_ru = rp.render_notes("0.9.0", "0.8.3", COMMITS, lang="ru", today="2026-01-02")
notes_en = rp.render_notes("0.9.0", "0.8.3", COMMITS, lang="en", today="2026-01-02")
check(u"ru-заголовок с датой",
      notes_ru.startswith(u"## Что нового в 0.9.0 (2026-01-02)"), notes_ru[:60])
check(u"en-заголовок с датой",
      notes_en.startswith(u"## What's new in 0.9.0 (2026-01-02)"), notes_en[:60])
check(u"en не содержит русского заголовка", u"Что нового" not in notes_en)
check(u"ru не содержит английского заголовка", u"What's new" not in notes_ru)
check(u"en-разделы на английском",
      u"### Fixes" in notes_en and u"### Features" in notes_en, notes_en[:400])
check(u"ru-разделы на русском",
      u"### Исправления" in notes_ru and u"### Новое" in notes_ru)
check(u"ссылка на сравнение версий", u"compare/v0.8.3...v0.9.0" in notes_ru, notes_ru[-200:])
check(u"у каждого пункта есть ссылка на коммит",
      all(u"/commit/" in line for _, items in rp.group_commits(COMMITS) for line in items))

empty_notes = rp.render_notes("0.8.4", "0.8.3", [], lang="ru", today="2026-01-02")
check(u"пустой релиз честно говорит об отсутствии изменений",
      u"нет пользовательских изменений" in empty_notes, empty_notes)

no_prev = rp.render_notes("0.9.0", None, COMMITS, lang="ru", repo_url=None)
check(u"без предыдущей версии нет ссылки на compare", u"compare" not in no_prev)
check(u"без предыдущей версии заголовок тот же", no_prev.startswith(u"## Что нового в 0.9.0"))

# ── 5) plugin.cfg ────────────────────────────────────────────────────────────

CFG = (u"[plugin]\n\nname=\"Godot Agent\"\ndescription=\"AI Agent\"\n"
       u"author=\"zzzLichzzz\"\nversion=\"0.8.3\"\nscript=\"plugin_universal.gd\"\n")
check(u"чтение версии из plugin.cfg", rp.read_plugin_version(CFG) == "0.8.3")
bumped = rp.bump_plugin_cfg(CFG, "0.9.0")
check(u"версия заменена", rp.read_plugin_version(bumped) == "0.9.0")
check(u"остальные строки не тронуты",
      bumped.replace(u'version="0.9.0"', u'version="0.8.3"') == CFG, bumped)
check(u"изменена ровно одна строка",
      sum(1 for a, b in zip(CFG.splitlines(), bumped.splitlines()) if a != b) == 1)
check(u"повторная запись той же версии - no-op", rp.bump_plugin_cfg(bumped, "0.9.0") == bumped)
try:
    rp.read_plugin_version(u"[plugin]\nname=\"x\"\n")
    check(u"plugin.cfg без version отвергается", False)
except ValueError:
    check(u"plugin.cfg без version отвергается", True)

with io.open(_os0.path.join(ADDON, "plugin.cfg"), "r", encoding="utf-8") as _f:
    REAL_CFG = _f.read()
REAL_VERSION = rp.read_plugin_version(REAL_CFG)
check(u"настоящий plugin.cfg читается и содержит SemVer",
      rp.SEMVER_RE.match(REAL_VERSION) is not None, REAL_VERSION)

# ── 6) CHANGELOG.md ──────────────────────────────────────────────────────────

OLD_CL = (u"# Changelog\n\nСекции собираются автоматически.\n\n"
          u"## 0.8.0 - 2026-01-01\n\n- старый пункт\n")
new_cl = rp.prepend_changelog(OLD_CL, rp.render_changelog_section(
    "0.9.0", COMMITS, lang="ru", today="2026-01-02"))
check(u"заголовок CHANGELOG сохранён", new_cl.startswith(u"# Changelog"), new_cl[:40])
check(u"пояснение сохранено", u"Секции собираются автоматически." in new_cl)
check(u"старый раздел не потерян", u"## 0.8.0 - 2026-01-01" in new_cl)
check(u"старый пункт не потерян", u"- старый пункт" in new_cl)
check(u"новый раздел выше старого",
      new_cl.index(u"## 0.9.0") < new_cl.index(u"## 0.8.0"), new_cl)
twice = rp.prepend_changelog(new_cl, u"## 1.0.0 - 2026-02-02\n\n- x\n")
check(u"повторная вставка не теряет старые разделы",
      u"## 0.9.0" in twice and u"## 0.8.0 - 2026-01-01" in twice, twice)
check(u"пустой CHANGELOG не падает",
      u"## 0.9.0" in rp.prepend_changelog(u"", u"## 0.9.0 - 2026-01-02\n\n- x\n"))
check(u"CHANGELOG заканчивается переводом строки", new_cl.endswith(u"\n"))

# ── 7) build_plan на настоящем git-репозитории ───────────────────────────────

def git(root, *args):
    subprocess.run(["git"] + list(args), cwd=root, check=True,
                   capture_output=True, text=True, encoding="utf-8", errors="replace")


root = tempfile.mkdtemp(prefix="release_repo_")
addon = _os0.path.join(root, "godot_agent")
_os0.makedirs(addon)
git(root, "init", "-q", "-b", "main")
git(root, "config", "user.email", "test@example.com")
git(root, "config", "user.name", "test")
with io.open(_os0.path.join(addon, "plugin.cfg"), "w", encoding="utf-8") as _f:
    _f.write(u'[plugin]\n\nname="Godot Agent"\nversion="1.0.0"\n')


def commit(subject, body=""):
    with io.open(_os0.path.join(addon, "f.txt"), "a", encoding="utf-8") as _f:
        _f.write(subject + "\n")
    git(root, "add", "-A")
    args = ["commit", "-q", "-m", subject]
    if body:
        args += ["-m", body]
    git(root, *args)


def release_now(tag):
    """Повторяет то, что делает workflow: применить бамп, закоммитить, повесить тег.

    Без этого шага plugin.cfg остался бы на старой версии и следующий план
    посчитал бы bump от неё - тест проверял бы не тот сценарий.
    """
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore(release): %s [skip ci]" % tag)
    git(root, "tag", tag)


commit(u"feat(tools): первая возможность")
commit(u"fix(panel): мелкая правка")
plan = rp.build_plan(root, addon, today="2026-01-02")
check(u"версия берётся из plugin.cfg, а не из тегов",
      plan["current_version"] == "1.0.0", plan["current_version"])
check(u"feat без тегов даёт minor", plan["new_version"] == "1.1.0", plan["new_version"])
check(u"без тегов previous_tag пуст", plan["previous_tag"] is None, plan["previous_tag"])
check(u"в план попали оба коммита", plan["commit_count"] == 2, plan["commit_count"])
check(u"notes содержат обе правки",
      u"первая возможность" in plan["notes"] and u"мелкая правка" in plan["notes"])
check(u"tag с префиксом v", plan["tag"] == "v1.1.0", plan["tag"])
check(u"план помечен как нужный", plan["needed"] is True)

# Релиз 1.1.0: бамп применён, тег повешен.
with io.open(_os0.path.join(addon, "plugin.cfg"), "w", encoding="utf-8") as _f:
    _f.write(plan["plugin_cfg"])
check(u"применённый plugin.cfg содержит новую версию",
      rp.read_plugin_version(plan["plugin_cfg"]) == "1.1.0")
release_now(plan["tag"])

# Тег отсекает старые коммиты.
commit(u"fix(panel): только правка")
plan = rp.build_plan(root, addon, today="2026-01-02")
check(u"since отсекает коммиты до тега",
      u"первая возможность" not in plan["notes"], plan["notes"])
check(u"новый fix даёт patch от версии plugin.cfg",
      plan["new_version"] == "1.1.1", plan["new_version"])
with io.open(_os0.path.join(addon, "plugin.cfg"), "w", encoding="utf-8") as _f:
    _f.write(plan["plugin_cfg"])
release_now(plan["tag"])

# Только служебные коммиты - релиз не нужен.
commit(u"docs: только документация")
plan = rp.build_plan(root, addon, today="2026-01-02")
check(u"docs-only не создаёт релиз", plan["needed"] is False, plan["needed"])
check(u"docs-only не двигает версию", plan["new_version"] == "1.1.1", plan["new_version"])

# Явный запрет релиза даже при feat-коммитах.
commit(u"feat(tools): большая правка")
plan = rp.build_plan(root, addon, bump="none", today="2026-01-02")
check(u"--bump none означает «релиз не нужен»", plan["needed"] is False, plan["needed"])

# Список тегов сортируется по версии, а не лексикографически.
git(root, "tag", "v1.9.0")
git(root, "tag", "v1.10.0")
tags = rp.list_tags(root)
check(u"v1.10.0 считается новее v1.9.0", tags[0] == "v1.10.0", tags)
check(u"старый тег не выбран базой", rp.find_previous_tag(root) == "v1.10.0")
shutil.rmtree(root, ignore_errors=True)

# ── 8) Согласованность с agent_updater.gd ────────────────────────────────────


def is_version_newer(current_ver, remote_ver):
    """Копия parse_semver/is_version_newer из agent_updater.gd.

    Дублируется намеренно: правка GDScript без синхронной правки теста
    прошла бы молча, а расхождение означало бы предложение обновиться на
    уже установленную версию.
    """
    def parse(value):
        cleaned = (value or "").strip()
        while cleaned.startswith("v") or cleaned.startswith("V"):
            cleaned = cleaned[1:]
        for sep in ("-", "+"):
            if sep in cleaned:
                cleaned = cleaned.split(sep, 1)[0]
        parts = cleaned.split(".")
        res = [0, 0, 0]
        for index in range(min(len(parts), 3)):
            try:
                res[index] = int(parts[index])
            except ValueError:
                res[index] = 0
        return res

    cur = parse(current_ver)
    rem = parse(remote_ver)
    for index in range(3):
        if rem[index] > cur[index]:
            return True
        if rem[index] < cur[index]:
            return False
    return False


check(u"SemVer: 0.8.4 новее 0.8.3", is_version_newer("0.8.3", "0.8.4"))
check(u"SemVer: 0.9.0 новее 0.8.9", is_version_newer("0.8.9", "0.9.0"))
check(u"SemVer: 0.10.0 новее 0.9.0 (двузначный minor)",
      is_version_newer("0.9.0", "0.10.0"))
check(u"SemVer: 1.0.0 новее 0.99.99", is_version_newer("0.99.99", "1.0.0"))
check(u"SemVer: равные версии не новее", not is_version_newer("0.8.3", "0.8.3"))
check(u"SemVer: старая не новее новой", not is_version_newer("0.9.0", "0.8.3"))
check(u"SemVer: v-префикс у тега не мешает", is_version_newer("0.8.3", "v0.8.4"))

for level in ("patch", "minor", "major"):
    candidate = rp.format_version(
        rp.bump_version(rp.parse_version(REAL_VERSION), level))
    check(u"SemVer: переход %s (%s -> %s) виден апдейтеру"
          % (level, REAL_VERSION, candidate),
          is_version_newer(REAL_VERSION, candidate))
    updated = rp.read_plugin_version(rp.bump_plugin_cfg(REAL_CFG, candidate))
    check(u"SemVer: после бампа %s обновление больше не предлагается" % level,
          updated == candidate and not is_version_newer(updated, candidate), updated)

print(u"--- ИТОГ test_release_prepare.py: %d/%d пройдено ---"
      % (sum(1 for r in results if r), len(results)))
if not all(results):
    _sys0.exit(1)

check(u"parse_version 0.8.3", rp.parse_version("0.8.3") == (0, 8, 3))
check(u"parse_version с v", rp.parse_version("v1.2.3") == (1, 2, 3))
check(u"parse_version с -beta1", rp.parse_version("0.9.0-beta1") == (0, 9, 0))
check(u"parse_version с +build", rp.parse_version("1.0.0+abc") == (1, 0, 0))
try:
    rp.parse_version(u"не версия")
    check(u"parse_version отвергает мусор", False)
except ValueError:
    check(u"parse_version отвергает мусор", True)

check(u"patch 0.8.3 -> 0.8.4", rp.bump_version((0, 8, 3), "patch") == (0, 8, 4))
check(u"minor обнуляет patch", rp.bump_version((0, 8, 3), "minor") == (0, 9, 0))
check(u"minor 0.9.3 -> 0.10.0, а не 0.9.10",
      rp.bump_version((0, 9, 3), "minor") == (0, 10, 0))
check(u"major обнуляет minor и patch", rp.bump_version((0, 8, 3), "major") == (1, 0, 0))
check(u"none не меняет версию", rp.bump_version((0, 8, 3), "none") == (0, 8, 3))
check(u"format_version", rp.format_version((1, 2, 3)) == "1.2.3")


def level_of(*subjects):
    return rp.resolve_bump_level([rp.Commit("a" * 40, s) for s in subjects])


check(u"только fix -> patch", level_of(u"fix: a", u"fix: b") == "patch")
check(u"feat -> minor", level_of(u"fix: a", u"feat: b") == "minor")
check(u"ломающий -> major", level_of(u"feat: a", u"fix(x)!: b") == "major")
check(u"BREAKING CHANGE в теле -> major", rp.resolve_bump_level(
    [rp.Commit("a" * 40, u"chore: x", u"BREAKING CHANGE: y")]) == "major")
check(u"docs/chore/test/build -> none",
      level_of(u"docs: a", u"chore: b", u"test: c", u"build: d",
               u"Update plugin.cfg") == "none")
check(u"пустой список -> none", level_of() == "none")
check(u"feat важнее fix", level_of(u"fix: a", u"feat: b", u"fix: c") == "minor")
check(u"--bump minor перекрывает авто",
      rp.resolve_bump_level([rp.Commit("a" * 40, u"fix: a")], override="minor") == "minor")
check(u"--bump none перекрывает авто", rp.resolve_bump_level(
    [rp.Commit("a" * 40, u"feat: a")], override="none") == "none")
try:
    rp.resolve_bump_level([], override="epic")
    check(u"неизвестный --bump отвергается", False)
except ValueError:
    check(u"неизвестный --bump отвергается", True)

# ── 3) Группировка changelog ─────────────────────────────────────────────────

COMMITS = [
    rp.Commit("1" * 40, u"feat(tools): бридж"),
    rp.Commit("2" * 40, u"fix(panel): вкладки"),
    rp.Commit("3" * 40, u"docs: README"),
    rp.Commit("4" * 40, u"Update plugin.cfg"),
    rp.Commit("5" * 40, u"chore(release): 0.8.3 [skip ci]"),
    rp.Commit("6" * 40, u"fix(api)!: ломаная правка"),
]
ordered = rp.group_commits(COMMITS, lang="ru")
headings = [h for h, _ in ordered]
check(u"разделы в порядке важности",
      headings == [u"Ломающие изменения", u"Новое", u"Исправления",
                   u"Документация", u"Прочее"], headings)
check(u"ломающая правка попала в раздел ломок",
      u"ломаная правка" in ordered[0][1][0], ordered[0][1])
check(u"ломающая правка видна и в общем разделе fix",
      any(u"ломаная правка" in line for line in dict(ordered)[u"Исправления"]))
check(u"коммит релиза со [skip ci] не попал в notes",
      not any(u"0.8.3" in line for _, items in ordered for line in items))
check(u"не-конвенциональный коммит виден в Прочее",
      any(u"Update plugin.cfg" in line for line in dict(ordered)[u"Прочее"]))
check(u"пустые разделы не выводятся",
      u"Тесты" not in headings and u"Сборка" not in headings, headings)
check(u"skip-маркер узнаётся в теле",
      rp.Commit("a" * 40, u"chore: x", u"please [skip ci]").skipped is True)
check(u"обычный коммит не skipped", rp.Commit("a" * 40, u"chore: x").skipped is False)


c = rp.Commit("abc1234", u"fix(server): краш при переименовании",
              u"BREAKING CHANGE: требует Godot 4.6+")
check(u"BREAKING CHANGE в теле = ломающий", c.breaking is True)
check(u"описание ломки взято из тела",
      c.breaking_desc == u"требует Godot 4.6+", c.breaking_desc)

c = rp.Commit("abc1234", u"fix(server): краш при переименовании")
check(u"тело с чужим текстом не ломает", c.breaking is False)

for subject in (u"Update plugin.cfg", u".", u"Update README.md", u"temp_format_test.gd"):
    c = rp.Commit("abc1234", subject)
    check(u"не-конвенциональная тема %r -> other" % subject, c.type == "other", c.type)
    check(u"не-конвенциональная тема %r сохраняет текст" % subject,
          c.description == subject, c.description)

c = rp.Commit("abc1234def", u"docs: README")
check(u"short_sha 7 символов", c.short_sha == "abc1234", c.short_sha)
