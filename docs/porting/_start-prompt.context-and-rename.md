# Задача: фаза 1 — починить `context.gather` и оформить `editing.symbol_rename` как модуль-вклад

Не новый срез моста: два долга, которые нужно закрыть **до** части A. Решения
пользователя 2026-10-27: (1) заглушку `context.gather` — починить, (2) у
`editing.symbol_rename` — свой `MODULE` + тесты (вариант «отдельная механика»,
не слияние с `write_preview`). Поведение уже принятых механик не меняется.

## 0. Факты на старте (замер аудита 2026-10-27)

```
python -m pytest python/modules tests/py          # 320 passed (== --collect-only)
python tools/snapshot_diff.py                     # кейсов 99, расхождений нет
python tools/gen_contract.py --check              # ok, артефактов 7, мост 0/3
python tools/security_audit.py --json             # нарушений нет
python tools/lint_arch.py ; python tools/check_limits.py   # 450/0 и 450/0
python tools/selfcheck.py editing.symbol_rename   # blocked, exit 2
```

| Что | Состояние |
|---|---|
| `context.gather` | этап 1, листа нет; `python/modules/context/gather/{app,module,tools}.py` — 4/6/3 строки, `domain/core.py` — 3 |
| `context/shared/context_section.py` | **не существует**, хотя ADR-0004 объявляет его интерфейсом вклада |
| `context/editor_context/*` | 4/7/3 строки: контракт есть (ADR-0007), кода нет |
| `editing/shared/operation_compiler.py` | пусто (0 строк) — интерфейс из ADR-0004 |
| `editing/symbol_rename/` | `domain/compiler.py` 164 строки, `collisions.py` 17, фасад `__init__.py` 7, `tests/test_core.py` — заглушка 3 строки, `MODULE` нет |
| `editing.write_preview` | зелёный (unit 45, корпус 16/16), импортирует фасад `from python.modules.editing import symbol_rename` — этот контракт не ломать |
| `code_intel.usages` | зелёный (unit 66, корпус 31), `analyze_rename` — read-only |

Правило чисел (три отчёта подряд дали числа не из файла): любое число в отчёте
копируется из вывода команды, а не пересчитывается; `--collect-only` и `pytest`
должны совпасть; мутация снимается с того файла, который сдан.

## 0.1. Что именно закрывается (проверяемые критерии, а не «сделано»)

| # | Проблема | Критерий приёмки |
|---|---|---|
| P1 | `context.gather` — заглушка, вкладывать `editor_context` некуда | `selfcheck context.gather` → `ok`, exit 0; появился `contract/capabilities/context.json` (артефактов 8); корпус `fixtures/corpus/context/gather` — 3 кейса, `snapshot_diff` = 102/0; `probe.py context --args-file …` отдаёт секции, `editor` → `available:false` |
| P2 | `editing.symbol_rename` — ложный `ported`, нет `MODULE` и тестов | `selfcheck editing.symbol_rename` → `ok` (не `blocked`); ≥10 тестов домена; `provides_tools` пуст, вклад в `editing.write_preview` и `code_intel.usages`; регресс `write_preview` 45/16 и `usages` 66/31 зелёный |
| P3 | Отчёты с числами не из файла (`43/14`, «`TypeError`», «11 → 14») | каждое число в отчёте присутствует в приложенном выводе команды; итог `pytest` = сумма из `--collect-only`; если число не сходится — правится отчёт, а не ожидание |
| P4 | Доказательство мутации снималось не с того файла | мутации только на сдаваемом файле: бэкап `shutil.copyfile` (байты), sha256 до/после, CRLF сохраняется; в отчёте список **всех** красных тестов и фактический stdout репро |
| P5 | Гигиена дерева | `__pycache__` 0, `.pytest_cache` нет, `*.bak/*.tmp/*.orig` 0, новых файлов ровно столько, сколько перечислено в отчёте; старый плагин — только чтение (два чужих лога не трогать, дампы в `%TEMP%`); новые файлы — LF, существующие не пересохранять целиком |
| P6 | Записи | листы `context.gather.md` и `editing.symbol_rename.md` созданы ДО кода и обновлены; `PROGRESS.md` (этап + «следующее действие»), `parity.md` (строка `context`, пометка вклада), `WORKLOG.md` (сессия); шапку «выполнено» в этот промпт НЕ ставить — её ставит аудитор |

## 1. Границы среза

**Внутри** (только это):

1. Лист `docs/porting/context.gather.md` по `_template.md` (R-07: лист до кода) и
   лист `docs/porting/editing.symbol_rename.md`.
2. `python/modules/context/shared/context_section.py` — интерфейс вклада
   (`ContextSection`: имя, стоимость, `collect(target) -> dict`) + проверка имени.
3. `context.gather`: `module.py` (`provides_tools=("context",)`,
   `requires_ports=("fs",)`), `tools.py` (`ToolSpec`), `domain/core.py` (чистые
   правила выбора и склейки), `app.py` (сбор через порты и реестр вкладов).
4. `editing/shared/operation_compiler.py` — `OperationCompiler` из ADR-0004.
5. `editing/symbol_rename`: `MODULE` (`contributes_to=("editing.write_preview",
   "code_intel.usages")`, `TOOLS = ()`), экспорт `COMPILER` в фасаде, настоящие
   unit-тесты домена вместо заглушки.
6. `contract/capabilities/context.json` — сгенерировать (`gen_contract` без
   `--check`), руками не писать.
7. Записи: `PROGRESS.md` (этапы и следующее), `parity.md` (строки
   `context` и `editing.symbol_rename`), `docs/porting/` листы, `WORKLOG`.

**Вне среза**: мост редактора (сокеты, кадры, `editor/`, `substrate/editor/`),
любая запись в проект, LLM/сеть, нейросетевая часть `minilich` (не переносится —
решение пользователя), правки `write_preview`/`usages`/`funnel`, правки схем уже
выпущенных артефактов, новые инструменты кроме `context`.

## 2. Контракт `context` (решено здесь, не изобретать по ходу)

Вход (`additionalProperties: false`):

```json
{"sections": ["project", "tools", "editor"], "path": "res://scenes/main.tscn"}
```

- `sections` — массив уникальных строк, 1…8 элементов, необязательный
  (по умолчанию все доступные); `path` — необязательный `res://`-путь цели.
- Неизвестное имя секции — **отказ всего вызова**, не «пропустить» (fail closed).

Выход:

```json
{"sections": {"project": {...}, "tools": {...}},
 "available": ["project", "tools"],
 "unavailable": [{"name": "editor", "reason": "no_module"}],
 "cost": "light"}
```

- Встроенные секции владельца: `project` → `{"root": "<абсолютный путь>",
  "project_file": "res://project.godot" | null, "engine": null, "source": "fs"}`
  (`engine` пока `null`: `substrate/engine` не перенесён — не выдумывать версию);
  `tools` → `{"count": N, "names": [...], "effects": {"<имя>": "read"|"write"}}`,
  порядок по имени, только загруженные модули.
- Секции вкладов собираются **через реестр** (`ctx.registry.contributions("context")`),
  не импортом. Отказ вклада (исключение) → имя в `unavailable` с `reason`,
  вызов не падает.
- `editor` в этой фазе даёт вклад `context.editor_context` и он отвечает
  `{"available": false, "reason": "no_bridge"}`; в headless вклада нет вовсе →
  `unavailable[].reason = "no_module"`.
- В результате **нет** времени, `uptime`, случайных id — иначе корпус
  невоспроизводим.
- `ToolSpec`: `effects="read"`, `idempotent=true`, `requires_preview=false`,
  `cost="light"`; ошибки `unknown_section` (`invalid_input`), `too_large`
  (`limit`), `path_escape` (`denied`), `denied` для чужих путей.

## 3. `editing.symbol_rename` как модуль-вклад

- `module.py`:

```python
MODULE = ModuleSpec(
    id="editing.symbol_rename",
    description="Компилятор операций переименования символа (без своего инструмента).",
    contributes_to=("editing.write_preview", "code_intel.usages"),
    internal_services=("symbol_rename_compiler",),
    capabilities=("editing.symbol_rename",),
)
```

- `tools.py`: `TOOLS = ()` — автозагрузчик это разрешает (`module_loader.py:48`:
  пустые `TOOLS` допустимы при непустом `contributes_to`).
- `editing/shared/operation_compiler.py` — датакласс `OperationCompiler`
  (`op: str`, `compile(request, texts, mode, allow_unverified, exclude) -> dict | None`),
  фасад модуля экспортирует `COMPILER = OperationCompiler(op="symbol_rename",
  compile=compile_plan)`.
- **Не** добавлять `symbol_rename` в `provides_tools` и не заводить
  `contract/capabilities/symbol_rename.json`: применение идёт через
  `write_preview` → `write_apply`, второго пути записи быть не должно (R-12).
- `tests/test_core.py` — настоящие тесты (≥10): `compile_plan` на анализе с двумя
  файлами (смещения, `newline`), `exclude` места, `mode="strict"` против
  `probable`, отказы `all_usages_excluded`, `unverified_references`,
  `dynamic_references`, `name_conflict`, `validate_request` на пустых именах,
  стабильность `digest` при повторном вызове. Поведение берётся из домена —
  домен не переписывать.
- Регресс: `write_preview` и `usages` остаются зелёными без правок. Если пришлось
  править их код — выбран неверный путь: остановитесь и напишите об этом в отчёте.

## 4. Корпус `fixtures/corpus/context/gather/` — три кейса

Проект — `fixtures/projects/minimal` (6 файлов). Только пути, имена, счётчики.

| Файл | Сценарий | Ожидание |
|---|---|---|
| `001-all-sections.json` | `{"sections": ["project", "tools", "editor"]}` | `available = ["project", "tools"]`, `unavailable = [{"name": "editor", "reason": "no_module"}]`, `sections.tools.names` — все имена по алфавиту, `sections.project.root` — корень проекта |
| `002-project-only.json` | `{"sections": ["project"]}` | `available = ["project"]`, ключей `tools`/`editor` в `sections` нет |
| `003-unknown-section.json` | `{"sections": ["nope"]}` | `{"ok": false, "kind": "invalid_input"}`, в сообщении `nope` |

Частичный результат при отказе не отдаётся. `engine: null` фиксируется,
зависящее от окружения — нет.

## 5. Тесты сверх корпуса

| Файл | Что проверяет |
|---|---|
| `python/modules/context/gather/tests/test_core.py` | домен без портов: порядок секций, дубликат — отказ, >8 — `too_large`, неизвестное имя — `unknown_section`, склейка `available`/`unavailable` |
| `tests/py/contract/test_context_contract.py` | схема из `contract/capabilities/context.json`, `additionalProperties: false`, `effects="read"`, детерминизм (два вызова — одинаковый dict), фикстура не меняется (sha256 до/после) |
| `tests/py/integration/test_context_contributions.py` | реестр вкладов: фейковый вклад виден в `sections`/`available`; вклад, который бросает, попадает в `unavailable` с `reason`; без вкладов `editor` в `unavailable` — не ошибка |
| `python/modules/editing/symbol_rename/tests/test_core.py` | см. §3: ≥10 тестов домена |
| `tests/py/contract/test_symbol_rename_manifest.py` | манифест-вклад: `provides_tools == ()`, `TOOLS == ()`, `contributes_to` содержит оба модуля, `internal_services` содержит `symbol_rename_compiler` |

Корпуса у `editing.symbol_rename` нет по построению (вклад, не инструмент):
`selfcheck` для вклада без корпуса даёт `ok` с пометкой «корпуса нет: вклад в …».

## 6. Стоп-условия

1. Никакой записи в проект: `context` — read-only, `symbol_rename` — компилятор.
2. Не трогать `python/modules/editing/write_preview/**`, `code_intel/usages/**`,
   `editing/shared/funnel.py`, `kernel/write_plan.py` (только чтение).
3. Не добавлять мост редактора, сокеты, кадры, `substrate/editor/` — это часть A.
4. Не выдумывать версию движка и `uptime`: `engine: null` до `substrate/engine`.
5. Не править выпущенные `contract/capabilities/*.json` руками; новые — только
   генерацией `python tools/gen_contract.py`.
6. Никаких LLM/сети/`minilich`; нейросетевая часть не переносится.
7. Старый плагин — только чтение (`python -B`); два чужих лога
   (`python/_ref2.log`, `python/godot_tools/_excl.log`) не удалять и не создавать
   новых.
8. Не ставить `ported` без зелёного `selfcheck` (для `context.gather` — этап 5+
   и живой `probe.py context`), не сдавать отчёт без вывода команд.

## 7. Что проверит аудитор (своими прогонами)

1. `python tools/selfcheck.py context.gather` → `ok`, exit 0: unit, корпус 3/3,
   `contract` с 8 артефактами; `python tools/selfcheck.py editing.symbol_rename` →
   `ok` (вклад, корпуса нет).
2. `python tools/snapshot_diff.py` → **102 кейса** (было 99), расхождений 0.
3. `python -m pytest python/modules tests/py` = сумма `--collect-only` (было 320).
4. `python tools/gen_contract.py --check` → ok, «артефактов 8».
5. **Мутации** (файл восстанавливается побайтово, sha256 сверяется):
   - убрать `contributes_to` в `symbol_rename/module.py` → загрузчик падает
     `нет TOOLS`, `selfcheck` красный;
   - убрать обработку отказа вклада в `app.py` → `test_context_contributions`
     красный;
   - убрать отказ на неизвестную секцию → кейс `003-unknown-section` красный.
6. **Подложенный файл**: лишний ключ в `contract/capabilities/context.json`
   (например, `"sections"` → `"secs"`) → `gen_contract --check` fail с путём;
   после возврата — ok.
7. **Живая проверка**: `python tools/probe.py context --args-file <json> --project
   fixtures/projects/minimal` (в PowerShell `--args` калечится кавычками) →
   `{"ok": true, ...}`; и на копии фикстуры — `context` не меняет файлы, `write_preview`
   после этого по-прежнему зелёный.
8. Чтение кода: `app.py` ≤ 80, `tools.py` ≤ 150, в `domain/` нет `open(`/`Path(`/`json.load`,
   единственный экземпляр правил (второго `compile_plan` нет), `context.gather` не
   импортирует чужой `domain/`, а только фасады и порты.
9. Гигиена: `__pycache__` 0, `.pytest_cache` нет, файлов столько, сколько следует
   из `git`-отсутствия — сверить по списку новых файлов из отчёта, в старом плагине
   по-прежнему только два `??`-лога.

## 8. Финальный прогон и записи

```
python -m pytest python/modules tests/py            # число = --collect-only
python tools/snapshot_diff.py                       # 102 / 0
python tools/selfcheck.py context.gather            # ok
python tools/selfcheck.py editing.symbol_rename     # ok (вклад)
python tools/selfcheck.py editing.write_preview     # регресс: 45 / 16
python tools/selfcheck.py code_intel.usages         # регресс: 66 / 31
python tools/gen_contract.py --check                # артефактов 8
python tools/security_audit.py --json
python tools/lint_arch.py ; python tools/check_limits.py
```

Затем — записи (без них шаг не сдан):

1. `docs/porting/context.gather.md` и `docs/porting/editing.symbol_rename.md`:
   цель, старый код (что читали у эталона и почему не копировали), корпус,
   спецификация, решения, «Проверки» (вывод `selfcheck`), «Следующее действие».
2. `docs/PROGRESS.md`: `context.gather` — этап по факту (5 или 6, `ported` только
   с живой проверкой), `editing.symbol_rename` — этап по факту; в обоих — вывод
   чисел и одна конкретная следующая строка.
3. `docs/parity.md`: строка `context` (было `—`) и `editing.symbol_rename`
   (`skeleton` → «вклад: компилятор, применяется через `write_preview`»).
4. `docs/tests-map.md`: если закрыли старые кейсы (`test_gather_context.py`,
   `test_librarian.py`, `test_editor_context.py`) — строки приложения, не удаление
   старых строк (R-17).
5. `docs/WORKLOG.md`: сессия «фаза 1» с командами и их выводом, мутациями и
   хешами восстановления.
6. `docs/porting/README.md`: пометить этот промпт выполненным **после** приёмки
   аудитом (шапку «выполнено» ставит аудитор, не портер).

