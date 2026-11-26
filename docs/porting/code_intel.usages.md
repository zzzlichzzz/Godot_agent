# code_intel.usages — где объявлен символ и где он используется

**Статус:** этап `7` (**ported**: `selfcheck` exit 0, корпус 18/18, живая проверка
`probe` + MCP stdio); `analyze_rename` в этом срезе **не** переносился
**Обновлено:** `2026-10-27`

## D119 — поиск однозначного объявления (2026-11-26)

`usages` и `analyze_rename` допускают вызов без точного `declaration`, в том
числе в пределах одного `declaration_path`. Неоднозначность и неполный индекс
не разрешаются догадкой; операции записи по-прежнему требуют точный локатор.
`selfcheck code_intel.usages` прошёл (66 unit / 31 corpus), CLI подтвердил `usages`
с автоподбором. Исторические этапы не менялись.

## Цель

Клиент спрашивает: «вот объявление символа (`res://src/player.gd:14`) — где он
ещё используется?» — и получает список мест с координатами (путь, строка,
колонка), типом связи (`declaration`, `call`, `member`, `identifier`, `type`,
`string`) и уверенностью: `proven` — связь доказана, `probable` — вероятна
(в `note` причина, чего не хватает), `dynamic` — ссылка по строковому литералу
рядом с API, работающим по имени. Плюс `by_link` и три счётчика. Ничего не
меняет: файлы проекта после вызова побайтово те же (SEC-11).

## Старый код

| Файл | Что делает | Как делим |
|---|---|---|
| `symbol_refactor_part2.py:583-683` `find_references()` | вход — locator + `kind` + `old_name`, снимок проекта, поиск объявления, наследники, фильтры, доказательство, строки, сортировка и счётчики | S3: `code_intel/usages/{app,domain}` — читаемая половина перенесена целиком |
| `symbol_refactor_part2.py:537-551` `_usage_query()`, `:553-570` `_locate_declaration()` | проверка `kind`/имени/locator'а и поиск единственного объявления; отказ со списком того, что файл объявляет | S3: `domain/core.build_query`, `parse_locator`, `locate` (`invalid_input` / `not_found`) |
| `symbol_refactor_part2.py:35-119` `_reference_is_safe()`, `:293-359` `_classify_string_reference()` | доказательство ссылки (`proven`/`probable`) и критерий строковой ссылки (`call`/`set`/`get` рядом, `print` — не ссылка) | S3: `domain/evidence.reference_is_safe`, `domain/core.classify_string_reference` |
| `symbol_refactor_part1.py:53-89` `_owner_within`, `_owner_in_script`, `_owner_belongs_to_script`, `_reference_in_other_scope`; `:423-468` тень имени | владение scope, вложенные классы, локальная тень — иначе одноимённая переменная считается ссылкой | S3: `domain/evidence` |
| `symbol_refactor_part1.py:266-322` `_unverified_reason()` | текст причины для `probable` — модель по нему решает, доверять ли месту | S3: `domain/evidence.unverified_reason` (тексты сверены корпусом) |
| `symbol_refactor_part1.py:508-548` `_find_subclasses()` | наследники по цепочке `extends` (путь или `class_name`), транзитивно | S2: `shared/symbol_index.subclasses` по фактам индекса |
| `godot_tools/gd_semantic_parser.py` (392 строки) | `tokenize` + `parse`: объявления, параметры, enum-члены, ссылки с контекстом, строки, ошибки | S1: `python/formats/gdscript/` (пакет: `tokens`, `declarations`, `parent`) |
| `minilich/ml_project_index.py` `semantic_snapshot` | снимок проекта: файлы + `sha256` + разбор; кэш на диске, `numpy`, обучение | S2: `shared/symbol_index.py` — только смысл снимка; **кэш, numpy и `minilich` не переносились** (долг в `PROGRESS.md`) |
| `tools/agent_bridge.py:790-822` `cmd_usages()` | CLI `usages --declaration <locator> --name <имя> [--kind K] [--new-name N]`: политика доступа, `find_references`, печать текстом | S3: `app.py` (политика → индекс → домен) + канал; текстовая печать не переносится (R-04) |

Не берём: `symbol_refactor_part1` сцены/файлы (`_collect_scene_*`, `_plan_file_rename`,
`_collect_path_reference_edits`), `part3` (`prepare_rename`, `apply_prepared_rename`)
и сам `analyze_rename` — это `editing.symbol_rename` и следующий срез
`code_intel.usages` (R-08: один перенос — одна фича).

## Старые тесты

| Файл | Семейство | Судьба | Что взяли |
|---|---|---|---|
| `test_find_symbol_usages.py` | unit | corpus (механика в карте исправлена: было `context.gather`) | 10 проверок: declaration + ссылки, координаты и confidence, `nothing_is_written`, `dynamic` у строки, `probable` вместо ошибки, запрос без `new_name`, `by_link`, плохой locator, комментарий не ссылка, read-only → кейсы 001–004, 006–008, 010–012 |
| `test_find_usages_reason.py` | unit | corpus (часть) | доводы/`note` для `probable` → кейсы 006 и 013; решение «переименовывать» — `editing.symbol_rename` |
| `test_string_reference_criterion.py` | unit | corpus (часть) | критерий строковой ссылки → кейс 007 |
| `test_rename_index_completeness.py` | unit | corpus (часть) | полнота индекса → S2 `tests/py/code_intel/test_symbol_index.py` |
| `test_rename_analyze_split.py`, `test_usage_checklist_honesty.py` | unit | corpus (часть) | состав отчёта (места, `by_link`, счётчики) → кейс 003; чек-лист и разделение «анализ/запись» — `analyze_rename` / `editing.symbol_rename` |
| `test_agent_bridge.py:1668-1685` | unit (мост) | replaced → `protocol/dispatch` | read-only вызов `project usages --declaration … --name …` и «файлы не изменились» → кейс 018 + contract-тест хешей |


## Корпус

Три слоя — три корпуса, каждый снят с эталона (R-07), ни один не подгонялся.

**S1 — разбор `.gd`.** `fixtures/parity/gdscript/` — 8 файлов (`declarations`,
`strings`, `inner_class`, `comments`, `annotations`, `typing`, `bom`, `crlf`) и
`expected.json` с полным ответом эталонного `gd_semantic_parser.parse`
(объявления, параметры, enum-члены, ссылки с контекстом, строки, ошибка
`declaration without a name`/незакрытой строки). Снято одноразовым скриптом
через `-B` (скрипт удалён), сравнение постоянное —
`tests/py/formats/test_gdscript_parity.py` (17 тестов).

**S2 — индекс проекта.** `tests/py/code_intel/test_symbol_index.py` (7 тестов):
только `.gd`, аддоны в `skipped`, `sha256` в объявлениях, факты `extends`,
транзитивные наследники, нечитаемый файл, повторяемость на
`fixtures/projects/minimal` (6 файлов, 32 объявления, **11.4 мс** на сборку).

**S3 — `usages`.** `fixtures/corpus/code_intel/usages/` — 18 кейсов, фикстуры
`fixtures/projects/usages/` (9 `.gd` + аддон) и `usages_empty/`. `manifest.json`:
`reference.source = godot_tools/symbol_refactor.py:find_references`, sha256
`symbol_refactor_part2.py`.

| № | Кейс | Вход | Ответ эталона (снят) |
|---|---|---|---|
| 001 | `function-declaration-and-calls` | `function take_damage` @ `lab_entity.gd:12` | 5 мест: declaration proven, вызов proven, 2 member probable (получатель без типа), 1 string dynamic |
| 002 | `only-declaration` | `function reset` @ `:17` | одно место — declaration proven; `reset()` в комментарии не считается |
| 003 | `by-link-and-counters` | `const MAX_HP` @ `:6` | 2 места proven; `by_link {declaration:1, identifier:1}`, счётчики сходятся |
| 004 | `comment-is-not-a-usage` | `function fire` @ `lab_turret.gd:6` | одно место: ссылка есть только в комментарии |
| 005 | `local-shadow-excluded` | `variable counter` @ `lab_shadow.gd:3` | declaration + ссылка из `bump`; одноимённая локальная в другой функции исключена |
| 006 | `probable-dynamic-receiver` | `function hit` @ `lab_dynamic.gd:3` | 1 proven, 2 probable с note «не удалось доказать тип ресивера …» |
| 007 | `string-literal-dynamic` | `function on_hit` @ `lab_strings.gd:6` | declaration + `string` dynamic, note `call() по имени` |
| 008 | `locator-syntax` | `res://src/lab_entity.gd:abc` | `invalid_input` |
| 009 | `locator-without-declaration` | `res://src/lab_entity.gd:3` | `not_found` со списком объявлений файла |
| 010 | `unknown-kind` | `kind: method` | `invalid_input` |
| 011 | `old-name-keyword` | `old_name: func` | `invalid_input` |
| 012 | `override-in-subclass` | `function take_damage` @ `lab_turret.gd:3` | 5 мест: свой вызов proven, `super.take_damage` probable (ресивер «super»), вызов из другого файла probable, строка dynamic |
| 013 | `enum-member` | `enum_member IDLE` @ `:10` | declaration proven + `State.IDLE` probable с причиной (эталон не передаёт имя enum в доказательство) |
| 014 | `class-name-hierarchy` | `class_name LabEntity` @ `:1` | 8 мест proven: `extends` в наследнике, `is`/`as`, `LabEntity.new()`, аннотация параметра |
| 015 | `path-outside` | `res://../outside.gd:1` | `denied` |
| 016 | `addon-hidden` | `res://addons/other/plugin.gd:4` | `denied` |
| 017 | `empty-project` | фикстура `usages_empty`, `res://src/none.gd:1` | `not_found` (типизированный отказ, не падение) |
| 018 | `new-name-echo` | `take_damage` + `new_name: apply_damage` | тот же отчёт, `new_name` возвращён эхом |

Снятие: `python tools/snapshot_record.py --corpus fixtures/corpus/code_intel/usages
--reference '<эталон>/python'` → `корпус снят: 18 кейсов`. После добавления
`src/lab_state.gd` (ссылка `State.IDLE` для кейса 013) корпус снят повторно:
хеши 17 кейсов совпали, изменился только 013 — проверено `Compare-Object`.

Чего в корпусе нет и почему:

- файл больше лимита чтения — бюджет (R-09), как и в предыдущих срезах;
- кэш индекса и его инвалидация — не механика `usages` (долг в `PROGRESS.md`);
- `analyze_rename` (затронутые файлы, риски, снятые места) — следующий срез;
- режимы `strict`/`probable` переименования — свойство записи (`editing.symbol_rename`).

## Спецификация

`ToolSpec(name="usages")`: `effects="read"`, `idempotent=True`,
`errors=("invalid_input", "not_found", "denied")`, `availability="*"`,
`cost="heavy"` (обход всего проекта; на минимальном проекте 11.4 мс, на большом
будет заметно — долг записан).

| Аргумент | Тип | Правило |
|---|---|---|
| `kind` | enum из 7 | `class_name`, `function`, `signal`, `variable`, `const`, `enum`, `enum_member`; иначе `invalid_input` |
| `old_name` | string | идентификатор GDScript, не ключевое слово; иначе `invalid_input` |
| `declaration` | string | `res://path.gd:LINE[:COL]`; синтаксис → `invalid_input`, нет объявления → `not_found`, вне корня/аддон → `denied` |
| `new_name` | string, необязателен | эталон принимает и возвращает эхом; на поиск не влияет |

Результат: `{kind, old_name, new_name, declaration, usages:[{path, line, column,
link, confidence, note}], by_link, proven_count, probable_count, dynamic_count}`.
`note` обязателен для `probable`/`dynamic` и `null` для `proven`.

Инварианты: SEC-11 (ни одной записи: индекс в памяти на вызов, contract-тест
сверяет хеши дерева до/после); SEC-12 (`..`, аддон, отсутствующий файл
отклоняются политикой/локатором до чтения); SEC-13 (в выдаче только `res://`
пути, в отказе — `kind/message/hint` без стектрейсов и абсолютных путей);
R-15 (три объявленных `kind`).

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-10-27 | Граница среза: `usages` — здесь, `analyze_rename` — следующий срез этого же модуля; строка 22 `parity.md` разделена на две | R-08: один перенос — одна фича. `analyze_rename` отвечает на другой вопрос (что изменится, риски, снятые места) и строит план, а не отчёт; смешивать его с поиском значило бы держать модуль красным до готовности обоих |
| 2026-10-27 | `formats/gdscript` — **пакет** (`tokens.py`, `declarations.py`, `parent.py`), а не файл | 392 строки эталона плюс шапки не влезают в лимит 400 строк (R-06). `__init__.py` реэкспортирует ровно публичное API эталона: `tokenize`, `parse` (+ `script_parent` для наследников) |
| 2026-10-27 | Проектный индекс без кэша: сборка на каждый вызов, замер на минимальном проекте — **11.4 мс** (6 `.gd`, 32 объявления) | Кэш на диске + `minilich` + `numpy` — отдельная механика с инвалидацией и своей ценой по безопасности (R-08). Дорого на большом проекте → **долг** в `PROGRESS.md`, а не повод строить кэш внутри среза; `cost="heavy"` в `ToolSpec` |
| 2026-10-27 | Коды ошибок locator'а: синтаксис → `invalid_input`, «нет объявления» → `not_found`; абсолютный путь в locator — синтаксическая ошибка, выход за корень — `denied` | Снято с эталона: `_parse_locator` бросает `LocatorError` на синтаксисе, `_locate_declaration` — на отсутствии объявления, `_resolve_safe_path`/политика — на пути. Иначе `denied` и `not_found` смешались бы и клиент не понял бы, что чинить |
| 2026-10-27 | Порядок S1 → S2 → S3, каждая стадия с зелёными тестами до следующей | Иначе в проекте появился бы четвёртый разбор `.gd`: соблазн «сначала usages, разбор потом» даёт дублирующий парсер, который расходится с `formats` на первом краевом случае |
| 2026-10-27 | `selfcheck` исправлен **до** кода механики | Дыра в R-18: пустая заготовка получала `ok` на общих проверках проекта. Пока инструмент врал, вердикт среза ничего не доказывал |


## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-27 | S0. инструмент | `tools/selfcheck.py`: `module` поднимает `build_agent` и сверяет `provides_tools` с реестром; `unit` собирает и гоняет тесты модуля + его contract-тесты; `corpus` требует корпус механики. Доказано: `editing.write_preview` → `blocked`/exit 2, `code_intel.functions` и `project_text.search` → `ok`/exit 0. Записи: `tools/README.md`, `WORKLOG.md` |
| 2026-10-27 | S1. разбор | `python/formats/gdscript/` (4 файла) вместо заглушки 312 б; корпус `fixtures/parity/gdscript/` (8 файлов + `expected.json`); `tests/py/formats/test_gdscript_parity.py` — 17 тестов, совпадение полное, включая смещения |
| 2026-10-27 | S2. индекс | `code_intel/shared/symbol_index.py` (обход порта, `PathPolicy`, `sha256`, `extends`, наследники); 7 тестов; замер 11.4 мс |
| 2026-10-27 | S3. механика | `code_intel/usages/{domain/core,domain/evidence,ports,app,tools,module}.py`; `domain/core.py` 268 строк, `domain/evidence.py` 189 (разделено под R-06), `app.py` 46 строк |
| 2026-10-27 | 4. корпус | 18 кейсов + фикстуры `usages`/`usages_empty`; `snapshot_record.py` → `корпус снят: 18 кейсов`; повторная съёмка после `lab_state.gd` — 17 хешей совпали |
| 2026-10-27 | 5. тесты | 14 тестов домена, 20 contract-тестов, включая read-only по хешам дерева |
| 2026-10-27 | 6. вердикт | `selfcheck code_intel.usages` → exit 0; `snapshot_diff` → 18/18 |
| 2026-10-27 | 7. живая проверка | `probe usages` (5 мест, `proven=2 probable=2 dynamic=1`), MCP stdio: 3 инструмента, `isError:false`; мутация `reference_is_safe` → 3 теста краснеют, файл восстановлен побайтово |
| 2026-10-27 | 8. триаж | `tests-map.md`: строка 60 переведена на `code_intel.usages`; строкам 61, 87, 95, 127, 131 дописано, какая часть кейсов — `usages`, какая — `analyze_rename`/`editing.symbol_rename` |

## Проверки

```
selfcheck code_intel.usages
  module         ok              code_intel.usages (usages)
  layers         ok              файлов 436, нарушений нет
  limits         ok              файлов 436, предупреждений 0
  contract       ok              артефактов 3, расхождений нет
  security       ok              нарушений нет
  unit           ok              34 passed in 0.28s
  corpus         ok              кейсов 18, расхождений нет
вердикт: ok                                       exit 0

snapshot_diff: functions 17/17, usages 18/18, search 16/16 → кейсов 51, расхождений нет
selfcheck code_intel.functions → ok (unit 33, corpus 17), exit 0
selfcheck project_text.search  → ok (unit 29, corpus 16), exit 0
selfcheck editing.write_preview → blocked, exit 2 (заготовка не зелёная)

lint_arch → 436 файлов, 0 нарушений;  check_limits → 436 файлов, 0 предупреждений
gen_contract --check → 3 артефакта, 0 расхождений;  security_audit --json → ok
pytest --collect-only: 13 + 14 + 15 + 7 + 20 + 14 + 20 + 17 = 120 тестов
```

Живая проверка (`fixtures/projects/usages`, `take_damage` @ `lab_entity.gd:12`):

```
{"ok": true, "result": {"kind": "function", "old_name": "take_damage", ...
 "usages": [declaration proven (12:6), member probable (lab_root 6:9, note про аннотацию),
            string dynamic (lab_root 8:14, "call() по имени"),
            member probable (lab_turret 4:15, ресивер «super»), call proven (lab_turret 7:2)],
 "by_link": {"declaration":1,"member":2,"string":1,"call":1},
 "proven_count": 2, "probable_count": 2, "dynamic_count": 1}}
```

MCP stdio: `initialize` → `2024-11-05`; `tools/list` → `functions,search,usages`;
`tools/call usages` → тот же JSON, `isError: false`, exit 0.

## Следующее действие

`analyze_rename` (тот же модуль): прочитать `symbol_refactor_part2.py:685+`
(`analyze_rename`, `_collision`, `_is_real_conflict`, `_project_global_names`,
`_engine_class_name`, `_excluded_places`) и снять корпус в
`fixtures/corpus/code_intel/usages/` с `tool="analyze_rename"` **до** первой
строки кода.

## Блокеры и долги

| Что | Где записано |
|---|---|
| Индекс строится на каждый вызов (11.4 мс на 6 файлах): на проекте >1000 `.gd` это станет заметно, кэш — отдельный срез | `docs/PROGRESS.md` → «Долги», `ToolSpec.cost="heavy"` |
| `analyze_rename` не перенесён — `parity.md` держит его `skeleton` | `parity.md`, строка `analyze_rename` |

