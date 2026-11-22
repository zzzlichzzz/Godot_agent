# Задача: фаза A.1 — доказать, что мост не «написан, но не проверен»

Ты в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`. Часть A принята аудитом как
`ported` **с долгом**: GDScript-сервер моста (`editor/**`) ни разу не компилировался и не
запускался — в окружении, где сдавалась часть A, Godot не найден, а
`substrate/engine/headless_runner.py` остаётся заглушкой. Пока это так, «работает» —
обещание, а не факт. Эта фаза закрывает ровно этот долг: **либо живой прогон, либо
машинная структурная проверка + честная запись**.

## 0. База (замер аудита 2026-10-28; перепроверь прогоном, числа — из вывода команд)

```
python -B -m pytest python/modules tests/py     # 417 passed (== --collect-only, 39 файлов)
python tools/snapshot_diff.py                   # кейсов 102, расхождений нет
python tools/gen_contract.py --check            # 8 артефактов, ok, verbs_version: 1
python tools/lint_arch.py; python tools/check_limits.py   # 453/0 и 453/0
python tools/selfcheck.py context.editor_context           # ok, unit 27
```

- `contract/editor_verbs.json` sha256 `F73AB2D8…B1E4`; маркеров по регексу
  `gen_contract` — **3** (`editor/bridge/verbs/editors/editor_verbs.gd:13/23/28`).
- `editor/harness/validate.gd` — 46 строк, умеет только «ресурс существует» (manifest →
  `result.json`), к мосту отношения не имеет.
- Godot в этой среде не найден: `Get-Command godot` пусто, `Godot*.exe` в
  `C:\Program Files`, `D:\` (глубина 2) — нет. Проект для запуска есть:
  `D:\vajno\Godot\agent-rebuild\project.godot`.
- Файлов 897, `__pycache__` 0, `schema.py` `629FCE54…4067` — **не трогать**.
- Текущий промпт следующего среза — `_start-prompt.scene_ops_b.md` (часть B). **Его не
  начинай**: эта фаза только про доказательство A.

## 1. Границы

| В фазе A.1 | Не в фазе |
|---|---|
| `editor/harness/**` — сцена/скрипт живого прогона моста | любые новые примитивы и запись в сцену (это B) |
| `tools/gd_guard.py` (новый) — структурная проверка `.gd` без Godot | правки `contract/editor_verbs.json`, `python/kernel/schema.py` |
| `tests/py/tools/test_gd_guard.py` + один прогон в `selfcheck` (если решите встроить) | правки `app.py`/`domain`/`client.py` принятых механик |
| записи: лист, PROGRESS, WORKLOG | второй сокет, HTTP, `ResourceSaver` |

## 2. Что сделать

**2.1 Найти Godot и попробовать живой прогон (первый приоритет).** Проверь в своём
окружении: `godot --version`, `godot4 --version`, `%LOCALAPPDATA%\Programs`, `D:\Godot*`,
`where.exe /R D:\ Godot*.exe` (медленно, но один раз). Если бинарь есть — сделай
`editor/harness/bridge_probe.gd` (`extends SceneTree`): поднимает сервер моста тем же
кодом, что `socket_server.gd`, ждёт один клиент, отвечает на `editor_ping`,
`editor_state`, `editor_selection`, пишет `user://godot_agent/harness_result.json`
(`{"ok", "verbs": {...}, "protocol", "verbs_version"}`) и выходит; Python-сторона —
`tests/py/live/test_bridge_live.py` под маркером `needs_live` (пропуск, если бинаря нет),
запуск `godot --headless --path D:\vajno\Godot\agent-rebuild -s res://addons/godot_agent/editor/harness/bridge_probe.gd`.

**Важно (аудит 2026-10-28):** одиночный `-s` без внешнего клиента даёт `ok:false`,
`failure.reason="timeout"`, `served: []` — это не провал моста. Приёмкой считается
`python -m pytest tests/py/live -v` (он и есть клиент): 1 passed, три примитива,
`harness_result.json.ok = true`. Правка харнесса — в `_start-prompt.harness-selfcheck.md`.
Результат — в отчёт дословно: версия движка, три ответа, время.

**2.2 Если Godot нет — структурная проверка (обязательный минимум).**
`tools/gd_guard.py`, только чтение `editor/**/*.gd`, без Godot и без эвристик «на глаз»:

1. `Markers`: каждый маркер `# verb: <name>` (регекс `^\s*#\s*verb:\s*([a-z_]+)\s*$`)
   обязан стоять **непосредственно перед** `func <name>(` на том же отступе — иначе
   провал «маркер без обработчика». Разбор — через существующий
   `python/formats/gdscript.parse(text, path)` (`declarations.py:150`), а не своим
   парсером; формы объявлений сверь по коду, не по памяти.
2. `Header`: каждый `.gd` в `editor/**` начинается с `extends`/`class_name` (иначе
   `Parse Error` у движка гарантирован).
3. `Brackets`: баланс `()[]{}` **вне строк и комментариев** (учти `"..."`, `'...'`,
   `#`), и `match`/`func` не пустые.
4. `Indent`: файл не смешивает табы и пробелы в отступах (Godot на смешении падает).
5. `Markers count`: по регексу `gen_contract` ровно `len(verbs)` = 3 (сейчас так), и это
   же число печатает `--check` — расхождение = провал.
6. Вердикт в стиле остальных инструментов: `{"status": "ok"|"fail", "detail": "файлов N, …"}`
   и exit 0/1; `--json`; подключить к `selfcheck` как отдельный статический чек **только
   если** он не создаёт ложных срабатываний на других `.gd` (проверь на `editor/**`).

**2.3 Тесты инструмента:** `tests/py/tools/test_gd_guard.py` — 5 кейсов на `tmp_path`:
маркер без `func` → fail с именем; маркер + `func` → ok; смешанные табы/пробелы → fail;
незакрытая скобка в строке-литерале → **не** нарушение; файл без `extends` → fail.
Плюс мутация: сломать `Markers` (сравнение по имени) → тест краснеет.

## 3. Стоп-условия

- Не начинать часть B и не менять примитивы/контракт: `verbs_version` остаётся 1.
- Не трогать `contract/**`, `python/kernel/schema.py`, `python/protocol/**`,
  принятые механики (`context.*`, `editing.*`) — кроме `editor/harness/**`.
- Не выдавать структурную проверку за живой прогон: в отчёте должно быть написано
  «Godot не найден, проверено структурно», а не «мост работает».
- Не править `editor/**` «чтобы guard прошёл» без причины: если guard нашёл настоящую
  ошибку — исправляй её минимально и запиши, какую.
- Старый плагин — только чтение; два чужих лога (`python/_ref2.log`,
  `python/godot_tools/_excl.log`) не удалять; дампы — в `%TEMP%`.

## 4. Что проверит аудитор (своими прогонами)

| Что | Как |
|---|---|
| не сломан регресс | `pytest` = `--collect-only` (было 417 + новые), корпус 102/0, `gen_contract` ok (8), 453/0, `selfcheck context.editor_context` ok (unit 27) |
| guard не фиктивный | подложить `.gd` с маркером без `func` → guard fail с именем; с незакрытой скобкой → fail; со скобкой внутри строки → **ok**; файл вернуть побайтово (`sha256`) |
| guard на реальном коде | `python tools/gd_guard.py` по `editor/**` → ok; мои 8 `.gd` не должны давать ложных срабатываний |
| маркеры | по регексу `gen_contract` 3; грепом `# verb:` по `editor/` 6 (3 маркера + 3 упоминания) — не провал |
| живой прогон | если ты его сделал — у меня нет Godot, проверю по твоему логу (`harness_result.json`, версия движка) и по коду скрипта; если не сделал — долг `needs_live` должен быть в PROGRESS с точной командой запуска |
| гигиена | `__pycache__` 0, `.pytest_cache` 0, `*.bak/tmp/orig` 0, старый плагин — те же две `??` |

## 5. Финальный прогон и записи

```
python -B -m pytest python/modules tests/py
python -m pytest python/modules tests/py --collect-only
python tools/gd_guard.py --json
python tools/snapshot_diff.py
python tools/gen_contract.py --check
python tools/selfcheck.py context.editor_context
python tools/lint_arch.py; python tools/check_limits.py
```

Записи: лист `docs/porting/context.editor_context.md` → раздел «Проверки» (что именно
доказано: живой прогон **или** структурно, с командой и вердиктом) и «Блокеры»
(Godot: найден/нет, где); `docs/PROGRESS.md` → строка `context.editor_context`
(приписка «структурная проверка GDScript: `tools/gd_guard.py`, N файлов, 0 нарушений;
живой прогон — долг `needs_live`, команда …»); `docs/WORKLOG.md` → сессия с выводом
команд; `README.md` и шапки промптов правит аудитор.

**В отчёте обязательны:** вывод `gd_guard` (или лог живого прогона), вывод обеих мутаций
с именами красных тестов, `sha256` восстановленных файлов, числа `pytest` и
`--collect-only` рядом, и явная фраза о том, что **не** доказано.

