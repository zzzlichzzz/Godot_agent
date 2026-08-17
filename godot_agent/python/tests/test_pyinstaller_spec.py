# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Проверка сборки: все модули доедут до exe и импортируются по коротким именам.

Зачем. Модули лежат по подпапкам (parsers/, server/, api/, backends/, ...), но
импортируются плоско — пути добавляет _bootstrap. PyInstaller такие импорты не
видит: он анализирует статический код, а не sys.path во время работы. Проект уже
дважды на этом обжигался — в сборке не оказывалось парсера, и DeepSeek молча
обслуживался парсером AI Studio («текст вводится, но не отправляется»).

ГЛАВНОЕ ПРО ЭТОТ ТЕСТ: источник истины — build_server_exe.bat, а НЕ .spec.
Скрипт сборки вызывает PyInstaller с main.py и набором флагов, и PyInstaller
при этом перезаписывает .spec своим содержимым. Правка .spec переживает ровно
до следующей сборки и теряется молча — именно так однажды уже пропал набор
модулей работы по ключу API, и собранный exe падал, хотя локально всё работало.
Поэтому здесь проверяются оба файла, но .bat считается обязательным.

Сбой означает: локально всё работает, а собранный godot_agent_server.exe
падает. Поймать это иначе можно только сборкой exe.
"""
import glob
import re
import sys

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


PY = _os0.path.abspath(_os0.path.join(
    _os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir))
SPEC = _os0.path.join(PY, "godot_agent_server.spec")
BAT = _os0.path.join(PY, "build_server_exe.bat")


def read_any(path):
    """Файлы сборки лежат в разных кодировках (bat писался в cp1251), а нам
    нужны только ASCII-флаги — читаем терпимо."""
    with open(path, "rb") as f:
        return f.read().decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# 0) Переводы строк в .bat: cmd.exe требует CRLF
# ---------------------------------------------------------------------------
# Реальная поломка: файл сборки был переписан с переводами строк LF, и cmd.exe
# начал разбирать его построчно неправильно — «'/d' is not recognized as an
# internal or external command» и десяток похожих строк. Внешне файл выглядит
# нормально в любом редакторе, поэтому проверяем байты.
for bat_path in sorted(glob.glob(_os0.path.join(PY, "*.bat"))):
    name = _os0.path.basename(bat_path)
    with open(bat_path, "rb") as f:
        raw = f.read()
    lone_lf = raw.count(b"\n") - raw.count(b"\r\n")
    check(u"%s: переводы строк CRLF (cmd.exe не понимает LF)" % name,
          lone_lf == 0, u"одиночных LF: %d" % lone_lf)
    # BOM в начале .bat приводит к «'п»їecho' is not recognized»: cmd читает
    # байты метки как часть первой команды.
    check(u"%s: нет BOM в начале" % name, raw[:3] != b"\xef\xbb\xbf")
    try:
        raw.decode("utf-8")
        ok_enc = True
    except Exception:
        ok_enc = False
    check(u"%s: текст не побит (валидный UTF-8)" % name, ok_enc)

spec = read_any(SPEC)
bat = read_any(BAT)

check(u"файл сборки .spec найден", _os0.path.isfile(SPEC))
check(u"скрипт сборки .bat найден", _os0.path.isfile(BAT))

hidden = set(re.findall(r"'([A-Za-z0-9_.]+)'", spec))
pathex_m = re.search(r"pathex=\[([^\]]*)\]", spec)
pathex = set(re.findall(r"'([^']+)'", pathex_m.group(1) if pathex_m else ""))
check(u"hiddenimports в .spec разобран", len(hidden) > 10, len(hidden))

# Флаги реального скрипта сборки.
bat_paths = set(re.findall(r"--paths\s+([A-Za-z0-9_]+)", bat))
bat_hidden = set(re.findall(r"--hidden-import\s+([A-Za-z0-9_.]+)", bat))
check(u"флаги --paths в .bat разобраны", len(bat_paths) >= 4, sorted(bat_paths))

# ---------------------------------------------------------------------------
# 1) Папки с плоскими импортами известны _bootstrap, скрипту сборки и .spec
# ---------------------------------------------------------------------------
boot_dirs = set(_bootstrap._PACKAGE_DIRS)
real_dirs = {d for d in _os0.listdir(PY)
             if _os0.path.isdir(_os0.path.join(PY, d))
             and glob.glob(_os0.path.join(PY, d, "*.py"))
             and d not in ("tests", "tools", "dist", "build", "__pycache__",
                           "minilich", "minilich_brain")}
check(u"_bootstrap знает про все папки с модулями",
      real_dirs <= boot_dirs, sorted(real_dirs - boot_dirs))
check(u"СКРИПТ СБОРКИ знает про те же папки (--paths)",
      boot_dirs <= bat_paths, sorted(boot_dirs - bat_paths))
check(u"pathex в .spec знает про те же папки",
      boot_dirs <= pathex | {"."}, sorted(boot_dirs - pathex))

# ---------------------------------------------------------------------------
# 2) Каждый модуль из этих папок либо в hiddenimports, либо статически импортирован
# ---------------------------------------------------------------------------
sources = {}
for d in sorted(boot_dirs):
    for p in glob.glob(_os0.path.join(PY, d, "*.py")):
        name = _os0.path.splitext(_os0.path.basename(p))[0]
        if name.startswith("_"):
            continue
        sources[name] = _os0.path.join(d, _os0.path.basename(p))

all_code = ""
for p in [_os0.path.join(PY, "main.py")] + [
        _os0.path.join(PY, v) for v in sources.values()]:
    try:
        with open(p, "r", encoding="utf-8") as f:
            all_code += f.read() + "\n"
    except Exception:
        pass
imported = set(re.findall(r"^\s*import\s+([A-Za-z0-9_]+)", all_code, re.MULTILINE))
imported |= set(re.findall(r"^\s*from\s+([A-Za-z0-9_]+)\s+import", all_code, re.MULTILINE))

unreachable = sorted(n for n in sources
                     if n not in hidden and n not in imported)
check(u"каждый модуль попадёт в сборку (hiddenimports или import)",
      not unreachable, unreachable)

# ---------------------------------------------------------------------------
# 3) Динамически загружаемые модули перечислены явно
# ---------------------------------------------------------------------------
# Парсеры сайтов грузятся через importlib — их отсутствие в сборке уже
# приводило к подмене парсера, поэтому проверяем и .bat, и .spec.
import sites
parsers = sorted({s["parser"] for s in sites.SITES if s.get("parser")})
absent_bat = [p for p in parsers if p not in bat_hidden]
check(u"все парсеры из реестра перечислены в СКРИПТЕ СБОРКИ",
      not absent_bat, absent_bat)
absent_spec = [p for p in parsers if p not in hidden]
check(u"все парсеры из реестра перечислены в .spec", not absent_spec, absent_spec)

# Модули работы по ключу. --paths их уже находит по цепочке импортов из
# main.py, но цепочку легко порвать (ленивый или условный импорт), поэтому они
# перечислены и явно. Требуем это в ОБОИХ файлах: тогда перегенерированный
# PyInstaller-ом .spec остаётся согласованным после каждой сборки, а не теряет
# список до следующей ручной правки.
must = ["api_keys", "providers", "openai_compat", "api_backend",
        "browser_backend", "api_history", "md_to_bbcode", "server_auth", "doh"]
absent_bat_api = [m for m in must if m not in bat_hidden]
check(u"модули работы по ключу перечислены в СКРИПТЕ СБОРКИ",
      not absent_bat_api, absent_bat_api)
absent = [m for m in must if m not in hidden]
check(u"модули работы по ключу перечислены в .spec", not absent, absent)

# ---------------------------------------------------------------------------
# 4) Плоские импорты действительно работают
# ---------------------------------------------------------------------------
import importlib
broken = []
for name in sorted(sources):
    if name in ("selfcheck",):
        continue
    try:
        importlib.import_module(name)
    except Exception as e:
        broken.append((name, "%s: %s" % (type(e).__name__, e)))
check(u"все модули импортируются по короткому имени", not broken, broken)

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
