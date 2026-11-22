# editing.write_preview — план правки и diff без изменения файлов

**Статус:** этап `7` (`ported`, кроме применения — часть 2)
**Обновлено:** `2026-10-27`

## Цель

Показать пользователю, что именно изменит переименование символа: шаги правки,
диффы, затронутые файлы, снятые места и счётчики, — и сохранить этот план в WAL
(`PREPARED`) так, чтобы `write_apply` (часть 2) применил его, **не пересчитывая**.
В проекте не меняется ни одного байта: единственная запись — WAL вне проекта.

## Границы трёх частей воронки

| Часть | Модули | Инструменты | Состояния ADR-0005 |
|---|---|---|---|
| **1 (этот срез)** | `editing.write_preview` (владелец) + `editing.symbol_rename` (компилятор операций) | `write_preview` | `DRAFT → PREPARED` |
| 2 | `editing.write_apply` + `editing.rollback` | `write_apply`, `write_rollback` | `APPLYING`, `COMMITTED`, `ROLLING_BACK`, recovery, лок, идемпотентность |
| 3 | те же + мост редактора и `formats/tscn` | — | — |

`editing.write_apply` в этом срезе остаётся заготовкой: `selfcheck
editing.write_apply` обязан вернуть `not_implemented` (код 2). Это и есть
доказательство, что граница не забыта.

## Старый код

| Файл | Что делает | Как делим |
|---|---|---|
| `symbol_refactor_part3.py:61-615` (`prepare_rename`) | строит правки, проверяет безопасность, готовит диффы | берём `DRAFT → PREPARED`; структуру объекта не переносим — нормализуем в `WritePlan` |
| `part3:473-476` (все ссылки сняты) | отказ, если объявление правится, а ссылок не осталось | `conflict`, `reason=all_usages_excluded` |
| `part3:477-499` (gating) | `strict` + недоказанные → отказ; `strict` + `dynamic` → отказ | `conflict`, `reason=unverified_references` / `dynamic_references` |
| `part2:121-170` (`_collision`, `_is_real_conflict`) | коллизия нового имени | `editing/symbol_rename/domain/collisions.py` (один экземпляр) |
| `part2._project_global_names`, `_engine_class_name` | autoload/InputMap/класс движка | **нет** в этом срезе (нужен `project.godot` и ClassDB; долг) |
| `part3:628+` (`apply_prepared_rename`) | запись | **нет** — часть 2 |
| `_collect_scene_*_edits`, `history_manager` | сцены и старый журнал | **нет**: сцены — риск в отчёте; журнал — WAL по ADR-0005 |

## Нормализация плана: поле эталона → поле плана

| Эталон (`prepare_rename`) | План |
|---|---|
| `files[].path` + `files[].occurrences` | `Step(op="script_edit", target=path, payload={"edits":[{start,end,replacement}], "newline":"lf"|"crlf"}, expected_hash=sha256(нормализованный текст))` |
| правка объявления (в эталоне входит в `occurrences` файла) | обычная правка шага |
| смещения эталона (сырые байты, `before_bytes`/`after_bytes` c CRLF) | **наши** смещения: символы в тексте после `\r\n → \n`; срез обязан быть равен `old_name` |
| `files[].before_hash` (sha256 СЫРЫХ байтов) | **не переносим**: `expected_hash` = sha256 нормализованного текста; стиль переводов строк едет в `payload.newline` — часть 2 читает raw, сверяет хеш, правит и восстанавливает стиль |
| `files[].diff`, `file_rename_diff` | **отбрасываются**: диффы строим из `kernel/diff.py` по нашим смещениям |
| `skipped_usages[]` | `skipped_usages[]` (строки `path:line:column — снято пользователем`) |
| `unverified_references[]` | `skipped_usages` для probable без `allow_unverified`, `stats.probable`, `risks` |
| `dynamic_references[]` | `risks` (строки эталонного формата) и `stats.dynamic` |
| `warnings`, `file_rename`, `file_rename_diff`, `reference_count` | **отбрасываются** (вне границ среза) |
| `renamed_count` | `stats.edits` |
| — | `expected{path: sha256}`, `digest`, `plan_id`, `confirm_ttl` — наши, по ADR-0005 |

В корпусе сравниваются только нормализованные поля: `steps[{path, edits}]`,
`affected_paths`, `stats{files,edits,dynamic}` и `excluded` (число строк
`skipped_usages` со «снято пользователем»). `proven/probable` не сравниваются:
их считает чужой поиск, и он же отдаёт те же места в `risks`.

`digest` = sha256 канонического JSON от `kind`, `declaration`, `old_name`,
`new_name`, `mode`, `allow_unverified`, `steps`, `expected`. Тот же вход → тот же
`digest`; `plan_id` — новый на каждый вызов.

## Соответствие причин отказа

| Эталон | `conflict.details.reason` |
|---|---|
| «Все ссылки сняты пользователем…» | `all_usages_excluded` |
| «Есть недоказанные ссылки…» | `unverified_references` |
| «Найдена динамическая ссылка по строке…» | `dynamic_references` |
| `_collision` + `_is_real_conflict` | `name_conflict` |
| новое имя = старое | `invalid_input` (`reason=same_name`) |
| не идентификатор / ключевое слово / плохой `mode` | `invalid_input` |
| locator не соответствует объявлению | `not_found` (даёт `analyze_rename`) |
| путь вне проекта / аддон | `denied` (даёт `analyze_rename`) |

## Спецификация ToolSpec

- args: `kind` (enum 7), `declaration`, `old_name`, `new_name` (minLength 1),
  `mode` (`strict|probable`), `allow_unverified` (bool), `exclude` (массив
  `res://path.gd:LINE`).
- result: `plan_id`, `digest`, `state="PREPARED"`, эхо `kind/old_name/new_name/
  declaration/mode/allow_unverified`, `steps_count`, `affected_paths`,
  `skipped_usages`, `risks`, `diffs[{path,patch}]`, `stats{files,edits,proven,
  probable,dynamic,skipped}`, `confirm_ttl`.
- effects `write`, `requires_preview=true`, `idempotent=false` (новый `plan_id`),
  errors `invalid_input|not_found|denied|conflict`, availability `*`, cost `heavy`.

Инварианты: ни одной записи в проект; WAL только при успехе; шаги содержат наши
смещения; `exclude` — вход preview, apply не переспрашивает.

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-10-27 | Поиск ссылок — только через `ctx.call_tool("analyze_rename", …)` | R-04: один экземпляр поиска; модуль-агрегатор, `call_tool` уже объявлен в `ModuleContext` |
| 2026-10-27 | Компилятор шагов — публичное API `editing.symbol_rename` (`__init__.py`), реализация в `domain/` | R-11: чужой `domain/` не импортируется, только фасад; в части 2 там же появится `apply` |
| 2026-10-27 | Проверка коллизий — `editing/symbol_rename/domain/collisions.py`, область: целевой файл | второй экземпляр не заводим; проект-wide class_name/autoload/ClassDB — долг, записан в deviations |
| 2026-10-27 | Смещения — символы после `\r\n → \n`; `expected_hash` — sha256 нормализованного текста | иначе apply вставит правку не туда; проверка «срез == old_name» в компиляторе |
| 2026-10-27 | `state_dir` приходит в `build_agent(state_dir=…)`; по умолчанию `%TEMP%/godot_agent/<profile>/journal` | модуль не знает `user://`; тесты дают `tmp_path`; проект не получает ни файла |
| 2026-10-27 | `.tscn` не правим: ссылки сцен попадают в `risks` | `formats/tscn` ещё не перенесён (часть 3) |
| 2026-10-27 | `mode=probable` разрешает только `dynamic` (probable-ссылки по-прежнему требуют `allow_unverified`) | ровно поведение `part3:477-499` |
| 2026-10-27 | `exclude` снимает правку, но **не** отменяет запрет `strict` на `dynamic`: снятая динамическая ссылка всё равно → `dynamic_references` | снятие — про намерение пользователя, запрет — про безопасность; корпус 015 это фиксирует |
| 2026-10-27 | `payload.newline` (`lf`/`crlf`) в каждом шаге | эталон даёт смещения в СЫРЫХ байтах, мы — в нормализованном тексте; без стиля часть 2 не восстановит файл байт-в-байт |
| 2026-10-27 | `app.py` остался оркестрацией, сборка конверта — `report.py` модуля | R-06: `app.py <= 80`; вся арифметика плана в одном месте рядом с `app.py`, не в домене (домен не знает `fs`/`journal`) |
| 2026-10-27 | Коллизии — только в пределах целевого файла (`collisions.name_conflict`) | проект-wide проверки требуют `project.godot`/ClassDB; записано в `docs/deviations.md`, корпус 009 проверяет то, что есть |
| 2026-10-27 | Фикстура `rename` обезличена: ресиверы без аннотаций | иначе наш парсер даёт `probable` там, где эталон видит `proven`, и корпус сравнивал бы разные вещи |

## Старые тесты

| Файл | Семейство | Судьба | Что взяли |
|---|---|---|---|
| `test_rename_analyze_split.py` | rename | частично | «предпросмотр ничего не пишет» (SEC-тесты), `skipped`/`exclude` (кейсы 003/004 корпуса) |
| `test_rename_const_exclude_last_usage.py` | rename | да | «снять последнюю ссылку нельзя» → кейс 004 (`all_usages_excluded`) |
| `test_rename_apply_report.py` | rename | нет (часть 2) | отчёт применения — квитанции `write_apply` |
| `test_rename_index_completeness.py` | rename | нет | полнота индекса — `code_intel.shared.symbol_index` (срез `usages`) |
| `test_rename_*.py` (остальные) | rename | нет | вид-специфичные правила объявлений (`class_name`, `const`, `enum`) — долг `symbol_rename` |

## Корпус

`fixtures/corpus/editing/write_preview/` — 16 кейсов, сняты с эталона
`symbol_refactor.prepare_rename` (`symbol_refactor_part3.py:61-615`) веткой
`run_write_preview` в `tools/_reference_runner.py` и нормализованы
(`_write_preview_result`): файлы → `{path, edits = occurrences}`,
`stats{files,edits,dynamic}`, `excluded` (число `skipped_usages`), отказ →
`{"ok": false, "kind": ...}`. Фикстура — `fixtures/projects/rename/`
(`src/hero.gd` — объявление и вызов, `src/enemy.gd` — наследник с `super` и
динамикой, `src/party.gd` — вызов по имени и `hp`, `addons/other/plugin.gd` —
закрытый аддон).

Покрытие: 001 один файл/strict, 002 два файла (сортировка), 003 `exclude`
одного места, 004 `exclude` всех → `all_usages_excluded`, 005 `strict` +
probable → `unverified_references`, 006 `allow_unverified`, 007 `strict` +
dynamic → `dynamic_references`, 008 `mode=probable`, 009 занятое имя,
010 ключевое слово, 011 `2x y`, 012 locator мимо объявления, 013 аддон,
014 путь вне проекта, 015 снятая динамическая ссылка (всё равно отказ),
016 locator с колонкой.

## Ход работы

1. Лист и границы трёх частей — до кода (`_start-prompt.write_preview.md`).
2. `kernel/write_plan.py` (Step/WritePlan/digest), `substrate/store/journal.py`
   (WAL `jsonl`, `fsync`), `runtime/config.py` (`state_dir` вне проекта).
3. `editing.symbol_rename`: `domain/compiler.py` (смещения, отказы, `stats`),
   `domain/collisions.py`, фасад `__init__.py`.
4. `editing.write_preview`: `domain/core.py` (вход, `exclude`), `app.py`
   (оркестрация через `call_tool("analyze_rename")`), `report.py` (план + WAL
   + диффы), `tools.py` (150 строк), `ports.py` (`fs`, `journal`).
5. Корпус: 16 кейсов сняты с эталона, `snapshot_diff` → 16/16.
6. Живая проверка: `probe write_preview` и MCP stdio `tools/list`.

## Проверки

```
selfcheck editing.write_preview
  module ok · layers ok (440/0) · limits ok (440/0) · contract ok (5/0)
  security ok · unit ok (35 passed) · corpus ok (16, 0 расхождений)   exit 0
selfcheck editing.write_apply → blocked (exit 2): нет MODULE, нет тестов, нет корпуса
snapshot_diff: write_preview 16/16, analyze_rename 13/13, functions 17/17,
               usages 18/18, search 16/16 → 80 кейсов, 0 расхождений
python -m pytest python/modules tests/py → 207 passed
gen_contract --check → 5/0; security_audit --json → ok; lint_arch/check_limits → 440/0
probe write_preview: 3 шага, 6 правок, affected 3, risks 5, stats 2/4/1
MCP stdio tools/list → analyze_rename, functions, search, usages, write_preview
```

Корпусные числа: `--collect-only` даёт те же 35 тестов модуля, что и прогон.

## Следующее действие

Часть 2 воронки: `editing.write_apply` — перечитать `expected`, сверить
`expected_hash`, применить шаги, квитанции `applied_hash`/`undo_token`,
`COMMITTED` и `stale_plan`; затем `editing.rollback` (ADR-0005).

## Блокеры

Нет. Долги, записанные осознанно: проектная проверка коллизий
(`project.godot`, autoload, ClassDB) — `docs/deviations.md`; ссылки из `.tscn`
пока только в `risks` (часть 3); индекс символов пересобирается на каждый
вызов (`cost=heavy`, кеш — отдельный срез).

## Правка аудита (2026-10-27): стиль файла и хеш «до правки»

Дефект, найденный аудитом уже после зелёного среза: `report.read_texts` читал через `read_text`, а он идёт через universal newlines — поэтому `"\r\n" in raw` не срабатывало, `payload.newline` всегда получался `"lf"`, а `expected` считался по нормализованному тексту. На CRLF-файле это дало бы либо переписывание всего файла в LF, либо вечный `stale_plan`.

1. `fs`-порт получил `read_raw` (байты как есть) — в `DiskFileSystem` и в двойнике `MemoryFileSystem`.
2. `report.read_texts` возвращает `(texts, newlines, expected)`: стиль определяется по байтам (`b"\r\n" in raw`), текст нормализуется, `expected[path]` — sha256 сырых байтов.
3. `save` фильтрует `expected` по целевым файлам шагов (stale-check только по тому, что меняем).
4. `steps[].expected_hash` остался sha256 нормализованного текста — это текст, в котором посчитаны смещения; различие двух хешей записано в `ADR-0005` («Что именно хешируется»).
5. Тесты: `tests/py/integration/test_write_preview_crlf.py` — 5 (CRLF, LF, BOM, смешанный файл, смещения в нормализованном тексте). `selfcheck` теперь включает интеграционные тесты модуля в проверку `unit`, иначе они жили отдельно от вердикта.

Живой прогон на CRLF-копии фикстуры: `newline = crlf`, `expected == sha256(сырых байтов)`, `expected != sha256(нормализованного)`, проект не тронут. Паритет не сдвинулся: корпус 16/16, `snapshot_diff` 80/80 — у эталона такого поведения нет, поэтому кейс не в корпус, а в тесты (это наш инвариант, а не поведение старого агента).

