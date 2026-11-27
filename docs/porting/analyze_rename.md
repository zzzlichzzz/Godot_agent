# analyze_rename — предпросмотр переименования (срез модуля `code_intel.usages`)

**Статус:** этап `7` — **ported** (`selfcheck code_intel.usages` exit 0, корпус
13/13 нового инструмента + 18/18 `usages` без изменений, живая проверка `probe`
и MCP `tools/list`)
**Обновлено:** `2026-10-27`
**Модуль-владелец:** `code_intel.usages` (`docs/parity.md`, строка 23). Отдельной
папки нет: `analyze_rename` — обёртка над тем же `find_references` (R-04, R-08).

## Цель

**D134.** В отчёт по функции или сигналу входят доказанные `callable`, `signal` и `scene_connection`. У подключения с разными владельцами меняется только поле нужного узла. Проверка: два перекрёстных подключения и одноимённые объявления в `tests/py/transfer_t1/test_bound_rename.py`.

Клиент спрашивает: «если переименовать `take_damage` → `apply_damage`, что и где
изменится?» — и получает **read-only** предпросмотр:

- `usages` — тот же список мест, что у `usages` (координаты, `link`, `confidence`, `note`);
- `affected_paths` — файлы с доказанными ссылками, а при `allow_unverified:true` также с вероятными; отсортированы, без дубликатов. Разрешение не повышает уверенность и не убирает `risks` (D133);
- `risks` — **строки** (не объекты) для недоказанных мест:
  `path:line [link, confidence]` и ` — note`, если причина есть;
- счётчики (`by_link`, `proven/probable/dynamic_count`) и разобранный locator
  (`declaration_path`, `declaration_line`).

Ничего не пишет: хеши файлов проекта до и после вызова равны (SEC-11).

## Старый код

| Файл | Что делает | Как делим |
|---|---|---|
| `symbol_refactor_part2.py:685-718` `analyze_rename()` | вызывает `find_references`, собирает `affected_paths` (только `proven`) и `risks` строками, эхом отдаёт `declaration`, `allow_unverified`, `mode` | S4: `domain/core.analyze` — обёртка над `core.find`; второго обхода проекта нет |
| `symbol_refactor_part2.py:583-683` `find_references()` | весь поиск и доказательство ссылок | уже перенесён в S3 (`domain/core.find`), здесь **переиспользуется** |
| `symbol_refactor_part1.py:218-227` `_parse_locator()` | `res://path.gd:line[:col]` → путь и строка | уже перенесён (`domain/core.parse_locator`); `analyze` берёт готовый разбор запроса |
| `symbol_refactor_part1.py:330-368` `_validate_action()` | `mode ∈ {strict, probable}`, строгая проверка типа `allow_unverified` | в S4 — на уровне `ToolSpec` (`enum` + `boolean`); поведение записи — S5 |
| `symbol_refactor_part3.py:477-498` | `mode`/`allow_unverified` реально снимают блокировки при **подготовке/записи** | **не этот срез**: `editing.symbol_rename` |
| `tools/agent_bridge.py:823-862` `cmd_analyze_rename()` | CLI: три обязательных строки (`--declaration`, `--old-name`, `--new-name`), `--kind`, `--mode`, `--allow-unverified` | `ToolSpec.args` + ветка `analyze_rename` в `tools/_reference_runner.py` |

Стоп-условия среза: `prepare_rename`, `apply_prepared_rename`, `exclude`,
`skipped_usages`, `public_prepared`, `history_manager` **не переносятся** — это
`editing.symbol_rename` (следующий срез).

## Поля отчёта (все обязательны)

| Поле | Тип | Источник |
|---|---|---|
| `kind` | enum 7 видов | эхо запроса |
| `old_name` / `new_name` | string | эхо запроса |
| `declaration` | string | locator **как пришёл** |
| `declaration_path` | string | разбор locator'а: `res://src/x.gd` |
| `declaration_line` | integer | разбор locator'а: `12` |
| `allow_unverified` | boolean | флаг из action (`is True` у эталона) |
| `mode` | `strict` \| `probable` | по умолчанию `strict` |
| `usages` | массив мест | `core.find` (тот же формат, что `usages`) |
| `affected_paths` | string[] | пути `proven` и, если включён `allow_unverified`, `probable` |
| `risks` | string[] | строки `path:line [link, confidence] — note` |
| `by_link` | object | счётчик по `link` |
| `proven_count` / `probable_count` / `dynamic_count` | integer | по `confidence` |

## Решения среза

1. **Один модуль, два инструмента.** `analyze_rename` живёт в `code_intel.usages`
   (parity строка 23), `provides_tools=("usages","analyze_rename")`. Отдельная
   папка запрещена: это обёртка над тем же поиском (R-04).
2. **`mode` — эхо, а не поведение.** Проверено по эталону: `analyze_rename`
   (`part2:685-718`) передаёт `action` в `find_references`, который `mode` не
   читает, и возвращает его эхом; `mode` меняет решения только в
   `prepare_rename`/`apply` (`part3:477`, `part3:487`). Поэтому
   `domain/evidence.reference_is_safe` **не получает** параметр `mode`: иначе
   `strict` и `probable` разошлись бы с эталоном и с корпусом (R-09), а
   `usages` 18/18 перестал бы быть доказательством неизменности. Кейсы
   `008/009` корпуса показывают фактическое поведение (отчёты совпадают);
   поведенческая разница появится в `editing.symbol_rename`.
   `mode` валидируется схемой (`enum`), потому что опечатка не должна молча
   ослаблять проверки (R-15) — это отличие от эталонного `analyze`, записано в
   `docs/deviations.md`.
3. **`risks` — строки, не объекты.** Формат эталона
   `path:line [link, confidence]` + ` — note`. Это то, что читают человек и
   модель в предпросмотре; структура была бы отличием, а не улучшением.
4. **`exclude`/`skipped_usages`/`apply` — не здесь.** Относятся к
   `editing.symbol_rename`; в `ToolSpec` этого среза их нет.
5. **Корпус снят с эталона.** Ветка `analyze_rename` в
   `tools/_reference_runner.py` вызывает `symbol_refactor.analyze_rename` и
   повторяет обязательность трёх аргументов моста (`RC_USAGE` →
   `invalid_input`). Корпус лежит в `fixtures/corpus/code_intel/analyze_rename/`
   (отдельная папка: у кейсов свой `tool`, манифест не смешивается с 18 кейсами
   `usages`; `selfcheck` видит оба корпуса модуля — правка `tools/selfcheck.py`).

## Кейсы корпуса (сняты с эталона)

| № | Кейс | Что доказывает |
|---|---|---|
| 001 | `const MAX_HP` → `MAX_VALUE` | все ссылки доказаны → `risks: []`, `affected_paths` заполнен |
| 002 | `variable hp` → `health` | `affected_paths` без дубликатов (несколько строк в одном файле) |
| 003 | `function take_damage` → `apply_damage` | `string`/`dynamic` попадает в `risks` c ` — call() по имени` |
| 004 | `function hit` (lab_dynamic) | `probable` в `risks` c причиной про аннотацию типа |
| 005 | нет `new_name` | `invalid_input` (эталонный мост отвечал `RC_USAGE`) |
| 006 | кривой locator | `invalid_input` |
| 007 | locator без объявления | `not_found` |
| 008 | `take_damage`, `mode=strict` | база для сравнения с 009 |
| 009 | `take_damage`, `mode=probable` | отчёт **совпадает** с 008 (эталон: mode — эхо) |
| 010 | `allow_unverified=true` | D133: добавляется путь вероятной ссылки `res://src/lab_root.gd`; `usages` и `risks` как в 008 |
| 011 | путь вне проекта | `denied` |
| 012 | аддон | `denied` |
| 013 | `class_name LabEntity` | `affected_paths` отсортирован по нескольким файлам |

## Проверки

```
python tools/selfcheck.py code_intel.usages     → ok, exit 0
  module ok (usages, analyze_rename), unit 66 (было 34), corpus 31 (18 + 13)
python tools/snapshot_diff.py                   → usages 18/18 + analyze_rename 13/13, 0 расхождений
python tools/selfcheck.py code_intel.functions  → ok, exit 0 (corpus 17/17)
python tools/selfcheck.py project_text.search   → ok, exit 0 (corpus 16/16)
python -m pytest python/modules tests/py        → 152 passed без флагов (addopts из pyproject)
security_audit / lint_arch / check_limits / gen_contract --check → ok
probe analyze_rename (take_damage @ lab_entity.gd:12) → risks 3 строки, affected 2 файла,
  by_link {declaration:1, member:2, string:1, call:1}, 2/2/1 — совпадает с эталоном строку в строку
MCP stdio tools/list                            → analyze_rename, functions, search, usages
```

## Следующее действие

`editing.symbol_rename` (воронка записи): `prepare_rename` → `preview` →
`apply_prepared_rename` + `exclude`/`skipped_usages`/откат; `mode` и
`allow_unverified` становятся поведением именно там (`part3:477-498`).

## Блокеры и долги

| Что | Где записано |
|---|---|
| Индекс строится на каждый вызов (как у `usages`) | `ToolSpec.cost="heavy"`, `docs/PROGRESS.md` → «Долги» |
| `mode` поведенчески не влияет на предпросмотр — так у эталона | решение 2, `docs/deviations.md` |

