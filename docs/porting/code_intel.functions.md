# code_intel.functions — список и тела функций `.gd`

**Статус:** этап `7` (**ported**: `selfcheck` exit 0, корпус 17/17, живая проверка `probe` + MCP stdio)
**Обновлено:** `2026-10-27`

## Цель

Клиент (модель, панель, другой модуль) спрашивает: «какие функции объявлены в этом
`.gd`-скрипте?» или «дай тела вот этих функций» — и получает по одной структуре
на файл: либо имена в порядке объявления, либо найденные функции с дословным
сниппетом и номерами строк (с 1) плюс список запрошенных имён, которых в файле
нет. Разбор индентационный (не AST): тело — строки с отступом глубже заголовка,
прилегающие сверху `#`-комментарии и `@`-аннотации входят в сниппет. Ничего не
пишет, диск читает только через порт `fs`, аддоны и исходники агента закрыты
политикой путей.

## Старый код

| Файл | Что делает | Как делим |
|---|---|---|
| `python/godot_tools/gd_functions.py:1-27` `_FUNC_RE`, `_indent_width`, `list_functions()` | одно регулярное выражение распознавания `^(\s*)(?:static\s+)?func\s+([A-Za-z_]\w*)\s*[(]`, ширина отступа и список имён в порядке объявления | ядро → `modules/code_intel/functions/domain/core.py` (чистые функции: имена, спаны, извлечение) |
| `gd_functions.py:30-81` `extract_functions()` | скан отступов: тело — строки глубже заголовка, пустые строки внутри тела его не обрывают, хвостовые обрезаются; прилегающие сверху `#`/`@` входят в сниппет; при дубле имени берётся первое объявление; `found` = `{name, snippet, start_line, end_line}` (1-based), `missing` = запрошенные, которых нет | ядро → `domain/core.py` (дословный перенос правил; `formats/gdscript.py` пока нет — см. «Решения по ходу») |
| `python/tools/agent_bridge.py:481-529` `cmd_functions()` | команда `functions [--names a,b] [--card] <res://path.gd>`: `res://`-путь, обязательный `.gd`, политика `assert_can_read_project_path`, чтение `read_project_file` (`utf-8-sig`, `errors=replace`), ветка `--card` → `function_card`, вывод текстом (`path:`, `functions (N): …`, `function: name (lines s-e)` + сниппет + `---`, `missing: name`), коды `RC_OK`/`RC_NOT_FOUND` | сценарий → `app.py` (путь → политика → порт → домен → результат); текстовая печать не переносится (это канал, R-04); ветка `--card` — чужая механика `code_intel.function_card` |
| `python/main.py:1072-1105` `_start_read_batch(read_function)` | пакетное чтение: `path` + `names`\|`functions`, до 10 имён на файл, статусы `blocked`/`missing` | сценарий `app.py` (аргументы `path` + `names`); пакетность и лимит 10 — свойство старого панельного хоста, не этой механики |
| `project_tools.py:778-786` `read_project_file()` | чтение `utf-8-sig`, `errors=replace`, универсальные переводы строк, `max_chars` | адаптер `substrate/fs/disk_fs.read_text()` (BOM/кодировка/лимит) — уже перенесён `project_text.search`, второй адаптер не нужен |
| `project_tools.py:423-462` `assert_can_read_project_path()` | что вообще можно читать: аддоны закрыты, история закрыта, выход за корень запрещён | `kernel/paths.PathPolicy.deny_reason()` (R-13, уже есть) |

Соседние части `agent_bridge.py` (`scene`, `usages`, `analyze_rename`) и
`function_card.py` — не эта механика.

## Старые тесты

| Файл | Семейство | Судьба | Что взяли |
|---|---|---|---|
| `test_function_card.py` | unit | **не эта механика** (`code_intel.function_card`) | В `docs/tests-map.md` строка 62 была приписана `code_intel.functions`. Проверено по файлу: он тестирует `godot_tools/function_card.py` и мост `functions --card` (тело, символы, связи, proven/dynamic). К `list_functions`/`extract_functions` отношения не имеет — механика в карте исправлена |
| `test_gdscript_wiring.py` | unit | **не эта механика** (`verification.gd_lint`) | В карте (строка 65) стояла `code_intel.functions` с пометкой «разбор .gd переехал в formats/gdscript.py». Проверено по файлу: 41 проверка — ключи локализации RU/EN (`_t("…")`), совпадение наборов и порядка `%s`/`%d`, наличие обработчиков, переданных в `.connect()`. К функциям не относится ни одним кейсом |
| `test_agent_bridge.py:1608-1690` | unit (мост) | replaced → `protocol/dispatch` (`tests-map.md` строка 136) | кейс «`functions <res://path.gd>` отвечает rc 0 и не меняет ни один файл проекта» — режим списка без `names`, read-only. Записан кейсом корпуса (список на `scripts/player.gd`) |
| `test_godot_agent_mcp.py:464` | unit (мост) | replaced → `protocol/dispatch` (`tests-map.md` строка 156) | `functions` в списке read-команд MCP — проверяется `tools/list` живого канала на шаге живой проверки |

Прямых тестов `gd_functions` в старом наборе нет (`grep` по
`gd_functions|extract_functions|list_functions` в `python/tests/*.py` — 0
совпадений), поэтому кейсы корпуса строятся по R-07: вход → вызов эталонной
функции → зафиксированный ответ.

## Корпус

`fixtures/corpus/code_intel/functions/` — 17 кейсов, `manifest.json` фиксирует
`reference.source = godot_tools/gd_functions.py:list_functions/extract_functions`,
`sha256` эталонного файла и хеши кейсов. Фикстура — `fixtures/projects/minimal`,
для кейсов 002/005–008 дописан `scripts/func_lab.gd` (47 строк, LF, табы),
для кейса 017 — `scripts/nested_func.gd` (13 строк); ни одного запроса корпуса
`project_text.search` они не содержат.

| № | Кейс | Вход | Ответ эталона (снят) |
|---|---|---|---|
| 001 | `list-declaration-order` | `scripts/player.gd`, без `names` | `names: ["_ready", "take_damage", "die"]` — порядок объявления |
| 002 | `list-static-and-nested` | `scripts/func_lab.gd`, без `names` | `names: ["_process", "make", "compute_score", "rpc_ping", "spaced_lines", "inner_helper", "duplicated", "duplicated"]` — `static func` и вложенный `class Inner` в списке, дубль повторён |
| 003 | `extract-one` | `player.gd`, `["take_damage"]` | `start_line 14`, `end_line 17`, сниппет дословно (`func take_damage(amount: int) -> void:` + 3 строки тела), `missing: []` |
| 004 | `extract-several-missing` | `player.gd`, `["die", "no_such", "take_damage"]` | `functions` в порядке запроса (`die` 20-21, `take_damage` 14-17), `missing: ["no_such"]` |
| 005 | `duplicate-first-declaration` | `func_lab.gd`, `["duplicated"]` | 40-43 — первое объявление; в сниппет попали `# func fake() -> void:` / `# \tpass`, стоящие вплотную над ним (подъём по `#`) |
| 006 | `annotations-in-snippet` | `func_lab.gd`, `["rpc_ping"]` | 19-24, сниппет начинается `# комментарий`, `@tool`, `@rpc("any_peer")` |
| 007 | `blank-lines-in-body` | `func_lab.gd`, `["spaced_lines"]` | 27-31: пустая строка внутри тела сохранена, две хвостовые после тела обрезаны |
| 008 | `nested-class-function` | `func_lab.gd`, `["inner_helper"]` | 36-37, сниппет с ведущим табом (regex разрешает отступ) |
| 009 | `bom-prefix` | `scripts/legacy_bom.gd` | `_ready` 3-5; BOM снят адаптером (`utf-8-sig`) |
| 010 | `crlf-lines` | `scripts/crlf_line.gd` | `_ready` 3-5; номера строк и сниппет не съехали |
| 011 | `commented-function` | `func_lab.gd`, `["fake"]` | `functions: []`, `missing: ["fake"]` — `# func fake():` не объявление |
| 012 | `not-gd-script` | `scenes/player.tscn` | `{"ok": false, "kind": "invalid_input"}` (старый мост: `RC_USAGE` «works only for .gd scripts») |
| 013 | `missing-file` | `scripts/nope.gd` | `{"ok": false, "kind": "not_found"}` |
| 014 | `parent-traversal` | `../outside.gd` | `{"ok": false, "kind": "denied"}` |
| 015 | `absolute-path` | `/etc/absolute.gd` | `{"ok": false, "kind": "denied"}` |
| 016 | `addon-hidden` | `addons/other_plugin/plugin.gd` | `{"ok": false, "kind": "denied"}` |
| 017 | `func-inside-func` | `scripts/nested_func.gd`, `["nested_outer", "nested_inner"]` | `nested_outer` 3-9 (сниппет вместе с прилегающим `#`-комментарием; внутри тела осталась строка `func nested_inner`), `missing: ["nested_inner"]` — вложенное объявление видно в списке (`names`), но телом не считается |


Снятие: `python tools/snapshot_record.py --corpus fixtures/corpus/code_intel/functions`
После аудита корпус снят повторно (17 кейсов); хеши 001–016 до и после совпали
(`Compare-Object` по `Get-FileHash` — расхождение только у нового 017, у которого
появился `expect`), то есть старые ожидания не подменились.


`--reference '<эталон>/python'` → `{"status": "ok", "detail": "корпус снят: 16 кейсов"}`.

Чего в корпусе нет и почему:

- файл больше `READ_TEXT_MAX_BYTES` (4 МиБ) — это бюджет (R-09), а не наблюдаемое
  паритета: старый мост отказывал по `max_chars`, новый — по лимиту адаптера;
- относительный путь без `res://` — старый мост такой вызов запрещал
  (`usage: functions <res://path.gd>`), поэтому кейса «как у эталона» быть не может;
  поддержка относительного пути — требование спецификации, записана отдельным
  решением (в корпусе все пути `res://`, кроме атакующих 014/015);
- `--card` — механика `code_intel.function_card`, у неё свой лист и своя очередь.

## Спецификация

`ToolSpec(name="functions")`: `effects="read"`, `idempotent=True`,
`errors=("invalid_input", "not_found", "denied")`, `availability="*"`, `cost="cheap"`.

| Аргумент | Тип | Правило |
|---|---|---|
| `path` | string, обязательный | `res://scripts/player.gd` или относительный `scripts/player.gd`; не `.gd` → `invalid_input`; `..`, абсолютный, аддоны → `denied` |
| `names` | array[string], default `[]` | пусто — режим списка имён; иначе извлечение в порядке запроса |

Результат — две формы, ровно как у эталонной функции:

| Режим | Поля |
|---|---|
| список (`names == []`) | `{path, names: [string]}` |
| извлечение | `{path, functions: [{name, start_line, end_line, snippet}], missing: [string]}` |

Инварианты:

- SEC-12: путь нормализуется `kernel.paths.normalize_rel`, затем `PathPolicy.deny_reason`;
  `..`, абсолютный путь, `D:/…` и аддоны отклоняются до чтения, ошибка — `denied`;
- SEC-11: записи нет вообще (`effects="read"`), файл открывается только адаптером;
- SEC-13: наружу уходят только `res://`-пути, `kind`/`message`/`hint` без стектрейсов
  и без абсолютных путей;
- R-15: три объявленных `kind` — `invalid_input` (расширение), `not_found` (нет файла,
  файл больше лимита чтения), `denied` (политика).

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-10-27 | Индентационная логика живёт в `domain/core.py`, `formats/gdscript.py` **не создаётся** | Единый парсер `.gd` ещё не перенесён и остаётся отдельной механикой. Создать `formats/` сейчас = переносить две фичи сразу (R-08). Когда появится `formats.gdscript`, эти функции переедут туда отдельным рефакторингом с двойным прогоном корпуса |
| 2026-10-27 | Корпус снимается с **функции** эталона (`list_functions`/`extract_functions`), а не с текста MCP/моста | Эталон печатал текст, новый инструмент отдаёт структуру. Это разделение «домен — канал» (R-04), а не отличие поведения: следующий аудитор не должен искать мнимое расхождение в формате |
| 2026-10-27 | `docs/tests-map.md`: строки 62 и 65 исправлены (`test_function_card.py` → `code_intel.function_card`, `test_gdscript_wiring.py` → `verification.gd_lint`) | Триаж по именам файлов ошибся, как в прошлый раз с `test_search_quality.py`. Правильное поведение — исправить карту, а не подгонять кейсы под неверную строку (R-17) |
| 2026-10-27 | Режим списка отдаёт отдельное поле `names: [string]`, а не те же объекты без `snippet` | Так эталонная `list_functions` и устроена (`→ [names]`), и так это снял корпус (кейсы 001/002). Второй формы объектов пришлось бы «додумывать» поля, которых эталон не возвращает — это была бы новая механика, а не перенос (R-08/R-09). Обе формы описаны в `result`-схеме `ToolSpec`, поэтому контракт остаётся строгим |
| 2026-10-27 | Не-`.gd` путь → `invalid_input` (а не `not_found`), решение принято по `expect`, а не по вкусу | Старый мост отвечал `RC_USAGE` «functions works only for .gd scripts»; снятый кейс 012 это подтвердил. Несуществующий `.gd` отдельно — `not_found` (кейс 013), `..`/абсолютный/аддон — `denied` (014/015/016): политика путей в новом каркасе отдаёт отказ раньше, чем чтение |
| 2026-10-27 | Долг R-03 закрыт этим срезом: `protocol/registry.py` помнит `_owners` (кто объявлял имя) и на `mark_failures` снимает записи через `_disable`; `protocol/dispatch.py` спрашивает `disabled_reason(tool)` и отдаёт `unavailable` с модулем и причиной | Долг воспроизводился именно на втором модуле: пока живой модуль один, `unknown_tool` не отличить от «модуль упал». Поведение зафиксировано тестом `test_disabled_module_answers_unavailable_with_reason` в `tests/py/contract/test_functions_contract.py` |
| 2026-10-27 | «Файл больше лимита чтения» → `not_found`, а не `unavailable` | Эталон отказывал тем же классом: `read_project_file` пробрасывал `OSError` (`file too large`), и мост отдавал `RC_NOT_FOUND`. Класс отказа — наблюдаемое паритета, а не удобство; поэтому ветка `errno.EFBIG` в `app.py` не «улучшается» в другой `kind`, а закрыта тестом `test_oversized_file_is_not_found_like_the_reference` (поддельный порт, без диска) |


## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-27 | 1. лист создан | прочитаны `gd_functions.py` (81 строка, импорт только `re`), `agent_bridge.py:481-529`, `main.py:1072-1105`, `project_tools.py` (`read_project_file`, `assert_can_read_project_path`), старые тесты (`test_function_card.py`, `test_gdscript_wiring.py`, `test_agent_bridge.py`), `docs/tests-map.md` строки 62/65/136/156, `docs/parity.md` |
| 2026-10-27 | 2. корпус | `fixtures/projects/minimal/scripts/func_lab.gd` (48 строк) + 16 кейсов; снятие `snapshot_record.py` → `{"status": "ok", "detail": "корпус снят: 16 кейсов"}`; `__pycache__` в эталоне не появился (проверка встроена в инструмент, `-B` + `PYTHONDONTWRITEBYTECODE=1`) |
| 2026-10-27 | 3. спецификация | `ToolSpec(name="functions")` в `python/modules/code_intel/functions/tools.py`; две формы результата (`names` либо `functions`+`missing`) |
| 2026-10-27 | 4. тесты до кода | `python/modules/code_intel/functions/tests/test_core.py` — 13 тестов домена на строках текста (без диска, без MemoryFS); `tests/py/contract/test_functions_contract.py` — 12 тестов контракта (схемы, `kind`, `denied` на `..`/абсолютный/аддон, `unknown_tool`, два модуля без конфликтов, R-03) |
| 2026-10-27 | 5. код | `domain/core.py` (дословный перенос regex и сканера отступов, импорт только `re` + `kernel.text`), `ports.py` (`TextReader.read_text`, свой протокол), `app.py` (79 строк: путь → политика → порт → домен → результат), `module.py` (`provides_tools=("functions",)`, `requires_ports=("fs",)`) |
| 2026-10-27 | 6. каркас | единственная правка на второй модуль — долг R-03 в `protocol/registry.py` + `protocol/dispatch.py` (профили, health, teardown, HTTP, панель не добавлялись) |
| 2026-10-27 | 7. контракт | `python tools/gen_contract.py --write` → `записано: functions.json, search.json`; `--check` → `артефактов 2, расхождений нет` |
| 2026-10-27 | 8. инструменты | `snapshot_diff.py` переведён на структурное сравнение (старая версия сравнивала только `matches`/`truncated` и второй инструмент прошёл бы корпус ложно) |
| 2026-10-27 | 9. вердикт | `python tools/selfcheck.py code_intel.functions` → exit 0 (см. «Проверки»); `project_text.search` повторно → exit 0 |

## Правки аудита 1–4

| № | Замечание | Что сделано |
|---|---|---|
| 1 | Обещание в описании ToolSpec («`func` внутри `func` виден в `names`, тело не извлекается») без кейса и теста | Новая фикстура `fixtures/projects/minimal/scripts/nested_func.gd` (13 строк; в `func_lab.gd` строки не вставлялись — у него посчитаны `start_line` в кейсах 003–008) + кейс `017-func-inside-func` (`nested_outer` 3-9, `missing: ["nested_inner"]`) + домен-тест `test_func_inside_func_listed_but_not_extractable` |
| 2 | Ветки `PermissionError` и `OSError(EFBIG)` в `app.py` без покрытия | Два теста через поддельный порт (`_BoomPort`, без диска и `MemoryFS`) в `tests/py/contract/test_functions_contract.py`: `PermissionError` → `denied`, `OSError(EFBIG)` → `not_found`; причина выбора `not_found` записана в «Решения по ходу». Проверено мутацией: при удалении обеих веток оба теста падают |
| 3 | `docs/tests-map.md`, строка 65: половина кейсов без дома | Судьба (`corpus`) и строка не менялись; в примечание дописаны адреса: (1)–(3) — `editor/core/i18n`, (4) — `verification.gd_lint` |
| 4 | Числа в отчёте не совпали с фактом | `docs/WORKLOG.md`: сессия 10 не переписана, дописан раздел «Аудит среза — сессия 10» со строкой «Уточнение»; здесь поправлены 47 строк `func_lab.gd` и состав корпуса (17 кейсов) |


## Проверки

`python tools/selfcheck.py code_intel.functions` → exit 0:

```
selfcheck code_intel.functions
  module         ok              code_intel.functions
  layers         ok              файлов 431, нарушений нет
  limits         ok              файлов 431, предупреждений 0
  contract       ok              артефактов 2, расхождений нет
  security       ok              нарушений нет
  unit           ok              59 passed in 0.51s
  corpus         ok              кейсов 32, расхождений нет
вердикт: ok
```

(`corpus ok` считает оба снятых корпуса — 16 search + 16 functions.)

`python tools/snapshot_diff.py code_intel.functions`:

```
fixtures/corpus/code_intel/functions     кейсов  16, совпало  16, расхождений 0
{"status": "ok", "detail": "кейсов 16, расхождений нет"}
```

`python tools/run_tests.py` → `59 passed in 0.55s`, вердикт `{"status": "ok", ...}`.
`lint_arch.py` → `файлов 431, нарушений нет`; `check_limits.py` → `файлов 431,
предупреждений 0`; `security_audit.py` → 9/9 `ok`, `нарушений нет`.
`project_text.search` повторно: `вердикт: ok`, exit 0 — чужая механика цела.

Живая проверка:

- `python tools/probe.py functions --args-file <list> --project fixtures/projects/minimal`
  → `{"ok": true, "result": {"path": "res://scripts/func_lab.gd", "names": ["_process",
  "make", "compute_score", "rpc_ping", "spaced_lines", "inner_helper", "duplicated",
  "duplicated"]}}`, exit 0;
- `python tools/probe.py functions --args-file <extract> ...` → `take_damage` 14-17
  (сниппет дословно) + `missing: ["no_such"]`, exit 0;
- MCP stdio: `python -m python.channels.mcp.stdio fixtures/projects/minimal` →
  `tools/list` отдаёт два инструмента (`functions`, `search`), `tools/call functions`
  с теми же аргументами вернул тот же JSON, что `probe` (`isError: false`), exit 0.

Эталон не тронут: новейший `.pyc` в старом плагине — `python/tools/__pycache__/
godot_agent_mcp.cpython-314.pyc` от `27.10.2026 01:32` (работа среза шла с `18:0x`
того же дня), корпус снимался через `-B`; абсолютных путей в кейсах — `0`
(проверка `\b[A-Za-z]:[\\/]` по `fixtures/corpus/code_intel/functions/*.json`).

### Проверки после аудита (2026-10-27)

`python tools/selfcheck.py code_intel.functions` → exit 0:

```
selfcheck code_intel.functions
  module         ok              code_intel.functions
  layers         ok              файлов 431, нарушений нет
  limits         ok              файлов 431, предупреждений 0
  contract       ok              артефактов 2, расхождений нет
  security       ok              нарушений нет
  unit           ok              62 passed in 0.55s
  corpus         ok              кейсов 33, расхождений нет
вердикт: ok
```

`corpus ok` снова считает оба корпуса: 16 search + 17 functions = 33 (это сумма
двух корпусов, а не дубли).

```
python tools/snapshot_diff.py code_intel.functions
fixtures/corpus/code_intel/functions     кейсов  17, совпало  17, расхождений 0
{"status": "ok", "detail": "кейсов 17, расхождений нет"}

python tools/snapshot_diff.py project_text.search
fixtures/corpus/project_text/search      кейсов  16, совпало  16, расхождений 0
{"status": "ok", "detail": "кейсов 16, расхождений нет"}

python tools/selfcheck.py project_text.search → вердикт: ok, exit 0 (те же 62 passed, corpus 33)
```

Тесты по файлам (`--collect-only`): `python/modules/code_intel/functions/tests/test_core.py: 13`,
`python/modules/project_text/search/tests/test_core.py: 15`,
`tests/py/contract/test_functions_contract.py: 20`, `tests/py/contract/test_search_contract.py: 14`
— сумма 62.

`security_audit.py --json` → `{"status": "ok", "detail": "нарушений нет"}` (exit 0);
`lint_arch.py` → `файлов 431, нарушений нет`; `check_limits.py` → `файлов 431,
предупреждений 0`; `gen_contract.py --check` → `артефактов 2, расхождений нет`.

Живая проверка новой фикстуры (`probe functions`, exit 0 у всех трёх):

```
{"path": "res://scripts/nested_func.gd"}                                    → names: ["nested_outer", "nested_inner", "nested_after"]
{"path": "...", "names": ["nested_outer"]}                                  → nested_outer 3-9, missing: []
{"path": "...", "names": ["nested_outer", "nested_inner"]}                  → nested_outer 3-9, missing: ["nested_inner"]
```

MCP stdio (`python -m python.channels.mcp.stdio fixtures/projects/minimal`):
`tools/list` → два инструмента (`functions`, `search`); `tools/call functions` с
`["nested_outer", "nested_inner"]` вернул тот же JSON, что `probe`, `isError: false`, exit 0.

Мутация (доказательство, что новые тесты держат ветки): из `app.py` временно убраны
`except PermissionError` и ветка `errno.EFBIG` → `2 failed` (оба теста), файл
восстановлен побайтово (`read_text() == original` → `True`).

Старые ожидания не подменились — хеши (`Get-FileHash -Algorithm SHA256`) до и после
повторной съёмки совпали, выборочно: `005` `0841AFBD…`, `006` `4982D92E…`,
`009` `A581268E…`, `010` `2424B4C4…` (те же значения, что в отчёте сессии 10);
`manifest.json` — `cases = 17`, `schema_version = 1`, `reference.source` тот же,
`sha256` эталона `efa80db6…`.



## Следующее действие

`code_intel.usages`: лист `docs/porting/code_intel.usages.md` из `_template.md`, затем
читать `python/godot_tools/symbol_refactor_part1.py`/`part2.py` эталона и снимать корпус
в `fixtures/corpus/code_intel/usages/` до первой строки кода.

## Блокеры

| Что мешает | Кто решает |
|---|---|
| ~~Инструмент отключённого модуля отвечает `unknown_tool`, а не `unavailable` (R-03)~~ — **закрыт** 2026-10-27 этим срезом: `registry._owners` + `dispatch._missing`, тест `test_disabled_module_answers_unavailable_with_reason` | сделано |
