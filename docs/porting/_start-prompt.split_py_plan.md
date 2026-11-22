# C.18 — `editing.split_py`, половина 2: инструмент `split_plan` (план разбиения `.py`, только чтение) + исправления F11 и F4

Ты — **портер**. Ты пишешь код и доказательства в рабочем дереве
`D:\vajno\Godot\agent-rebuild\addons\godot_agent`, и только там. Эталон — старый плагин
`D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent` (только читать, ничего не менять).

Правила роли (не обсуждаются):
- этап сам себе **не ставишь**; шапку «выполнено/принято/ported» не пишешь;
- `docs/porting/_audit-handoff.md` не правишь — его ведёт аудитор;
- по завершении объявляешь ровно одно: «C.18 готов к независимому аудиту, не принято»;
- приёмка — только мои (аудитора) собственные прогоны: своя пересъёмка корпуса с эталона,
  своя проекция, свои мутации и подложки, сверка сохранности принятого кода по sha256.

Состояние на входе: `editing.split_py` — **этап 7 по половине 1** (`split_scan` принят аудитом
2026-11-01, сессия 73). Половина 2 (`split_plan`) не начата: в папке модуля пока один инструмент.
`editing.split_gd` принят полностью (C.14 + C.15 + C.16) — это образец того, как две половины одной
механики живут в одном модуле, и как оформляется запись (она там **не** в срезе пилы, а в отдельном
C.19-подобном срезе).

## Читать до первой строки кода (обязательно)

1. `AGENTS.md` — правила репозитория.
2. `RULES.md` — R-01…R-22; особенно R-02 (общий код живёт в `shared/` области), R-05 (`MODULE`),
   R-09 (границы модуля), R-11 (`domain/` без ввода-вывода), R-12 (воронка записи), R-13 (лимиты),
   R-22 (документы).
3. `docs/architecture.md`, `docs/PORTING.md` — устройство моста и правила переноса.
4. `docs/parity.md` — строка `split_scan/plan`; там же 114–118 про вклады и владельцев инструментов.
5. `docs/PROGRESS.md` — строки `editing.split_py` (7, половина 1) и `editing.split_gd` (7).
6. `docs/tests-map.md` — строки `split_gd*`, `split_scan`, `test_split_refactor.py`.
7. `docs/porting/_template.md` — шаблон листа механики.
8. Лист `docs/porting/editing.split_py.md` **целиком** (там половина 1, её решения и приёмка).
9. Лист `docs/porting/editing.split_gd.md` — как оформлялись две половины `.gd`-пилы (C.15).
10. Промпт `docs/porting/_start-prompt.split_gd_plan.md` — прямой образец структуры этого среза.
11. ADR: `docs/adr/0004*`, `0006*`, `0009*`, `0010*`, `0011*`, `0012*`.
12. `docs/security/invariants.md`.
13. `docs/WORKLOG.md` — последние три сессии (69, 71, 73).

## §0 База (снято аудитом, сессия 73, 2026-11-01 — не пересчитывать)

- non-live: **3880** passed (junit 3880/0/0/0, 55.0 с, stderr пуст), collect 103 файла.
- live: **3** passed / 0 skip (17.954 с). Живое требует временного `[editor_plugins]` во внешнем
  `D:\vajno\Godot\agent-rebuild\project.godot` (335 B, sha256
  `958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`) и побайтового восстановления.
  Godot: `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`.
- `tools/snapshot_diff.py` → **771/0** (в т.ч. `editing/split_py` 47/47, `editing/split_gd` 102/102,
  `verification/check` 75/75, `gd_lint` 37/37, `tscn_lint` 65/65, `api_check` 52/52, `class_api` 26/26).
- `tools/gen_contract.py --check` → **24** артефакта (25 файлов с `_template.json`).
- `selfcheck editing.split_py` → module ok (`split_scan`), layers 529, limits 529/0, contract 24,
  security ok, unit **263**, corpus **47**, вердикт ok.
- Соседи, которые **не должны сдвинуться**: `editing.split_gd` 625/102, `verification.check` 188/75,
  `verification.api_check` 206/52, `verification.gd_lint` 126/37, `verification.tscn_lint` 315/65,
  `engine_kb.class_api` 186/26 (после исправления F4 в этом срезе станет **128/26** — это ожидаемо,
  см. §3 шаг 7; больше ни у кого число меняться не должно).
- Гейты: `tools/lint_arch.py` 529 ok, `tools/check_limits.py` 529/0, `tools/security_audit.py` ok.
- Дерево: **2999** файлов (обход `python -B` без `__pycache__`/`.pytest_cache`/`.godot`; не
  `Get-ChildItem`), `.gd.uid` **83** (8 исторических фикстур `fixtures/parity/gdscript/`, 2026-10-27,
  не трогать), debris 0, листов 26, промптов 36, ADR 12, правил 22, PROGRESS 44 строки (24/1/19).
- Git в `agent-rebuild` намеренно **нет**; единственный git — старый плагин (две чужие

### §0.1 Файлы среза (размер / sha256-16, снято аудитором)

| Файл | Размер | sha256-16 | Notes |
| --- | --- | --- | --- |
| `python/modules/editing/split_py/app.py` | 3149 | `4800C2091D4B…` | **правится**: второй инструмент + фикс F11 |
| `python/modules/editing/split_py/tools.py` | 1812 | `ED392103A9BB…` | **правится**: второй `ToolSpec` |
| `python/modules/editing/split_py/module.py` | 462 | — | **правится**: `provides_tools` (+`split_plan`) |
| `python/modules/editing/split_py/domain/core.py` | 671 | `E0DC77EFE26C…` | **правится**: `assemble_plan` |
| `python/modules/editing/split_py/domain/refs.py` | 1801 | `4998C8A1DEB0…` | **не трогать** (принято в C.17) |
| `python/modules/editing/split_py/domain/walk.py` | 1534 | — | читается (`imports`, `module_matches`, `stem`) |
| `python/modules/editing/split_py/domain/text.py` | 232 | — | читается (`decode`) |
| `contract/capabilities/split_scan.json` | — | — | **не менять** |
| `tools/selfcheck.py` | — | — | **правится только по F4** (§3 шаг 7), самый узкий селектор |

Эталон (только чтение): `python/godot_tools/split_refactor.py` — **44 114 B, 872 строки, CRLF 872/872,
sha256 `87cb4d5209c070f2f65ad45c16086e7c99b561ce677c6f8b1d1fd57b545526e7`**.
Второй адрес: `python/tools/agent_bridge.py` (142 171 B, `a9b1ad832fd0…`), `_split_target:914`,
`cmd_split:934` — **CLI не переносится**, читается только чтобы снять живые тексты отказов.

## §1 Границы среза

Срез — **вторая половина** механики `editing.split_py`: инструмент **`split_plan`**, только чтение.
Он отвечает на вопрос «что поедет»: модули, имена, фасад, ошибки плана, предупреждения, сводка
инвентаря и ссылок. Ничего не пишет, Godot не запускает.

Плюс к этому в срезе **два исправления найденных дефектов** (второй — в замороженном гейте, поэтому
с ADR и отдельным доказательством):

- **F11 (дефект принятого кода C.17).** В `split_py/app.py` порядок проверок неверен: `_addon_root()`
  вызывается **до** проверки существования файла. Из-за этого для отсутствующего файла **вне аддона**
  порт отвечает `invalid_input` («донор не находится внутри аддона с plugin.cfg»), а эталон —
  `not_found` («файл не найден: …»). Найдено аудитором при приёмке C.17 (handoff §5, строка F11).
  Исправление — поменять порядок: сначала `not_found`, затем аддон-корень; поведение для
  существующих файлов не меняется.
- **F4 (долг гейта `tools/selfcheck.py`).** Селектор юнит-тестов собирает интеграционные файлы по
  маске `test_<имя>*.py`, где `<имя>` — имя фичи и имена инструментов. Из-за этого
  `engine_kb.class_api` (инструмент `api`) затягивает в свои юниты `test_api.py`,
  `test_api_check.py` и `test_api_snapshot.py` — и показывает **186** тестов вместо 128. Исправление —
  правило «самый длинный префикс выигрывает»: файл `test_<X>_<rest>.py` принадлежит инструменту
  `<X>_<rest>`, если `<X>_<rest>` — имя известного инструмента реестра, и не принадлежит `<X>`.

**В срезе** (`python/modules/editing/split_py/`):
- `domain/inventory.py` — `file_inventory:270-340` (верхнеуровневые символы, импорты, `other`,
  `__all__`, докстрока, `used_names`), `_segment_text:231`, `_expand_comments:235`,
  `_import_bindings:246`, `_other_item:259`;
- `domain/groups.py` — `suggest_groups:349` (`_DEFAULT_TARGET_LINES = 900`) и нормализация
  `groups` (ключ **`symbols`**, не `funcs`!);
- `domain/facade.py` — `_render_facade:656` + `_format_import:368` + `_join_blocks:401` +
  `_find_cycle:375` (проверка цикла), `_warn_patched_attributes:202`;
- `domain/plan.py` — сборка `prepared` (поля §2.1) без текстов модулей/фасада;
- `domain/core.py` — `assemble_plan(...)` (публикация), `app.py` — вторая ветка `call`,
  `tools.py` — второй `ToolSpec`, `module.py` — `provides_tools=('split_scan', 'split_plan')`,
  `requires_ports` без изменений (`('fs',)` — кэш API `.py`-пиле не нужен);
- корпус `fixtures/corpus/editing/split_py/` — новые кейсы **с 048** (нумерация после C.17);
- карточка `contract/capabilities/split_plan.json` (25-я);
- лист `docs/porting/editing.split_py.md` — раздел C.18 и раздел про F11/F4;
- ADR `docs/adr/0013-selfcheck-unit-selector.md` (для F4);
- записи: `docs/parity.md`, `docs/PROGRESS.md`, `docs/tests-map.md`, `docs/WORKLOG.md`.

**Не в срезе**: запись плана и всё про создание файлов (`apply_prepared_split:718`, `_cli:792`,
`StaleSplitError`), Godot-проверка — это **C.19** и требует своего ADR, потому что воронка
`editing/shared/funnel.py` умеет только перезапись существующих файлов, а тут нужны **create**;
принятая половина 1 (`split_scan`, её 47 кейсов и карточка) — байт-в-байт; `editing.split_gd` целиком;
`editing.symbol_rename` (этап 6); `verification.*`, `engine_kb.*`, `code_intel.*`, `scene_model.*`;
`python/kernel/*`, `python/substrate/*`, `python/runtime/*`, `python/protocol/*`;
`contract/editor_verbs.json`; `editor/**`; прочие замороженные `tools/*`; `_audit-handoff.md`.

**Разрешённые правки вне папки — ровно три** (+ отдельно F4, §3 шаг 7):
1. `fixtures/corpus/context/gather/001-all-sections.json` — добавить `split_plan` с эффектом
   `"read"`, `count` 23 → 24, и обновить **только** sha256 кейса `001-all-sections` в
   `fixtures/corpus/context/gather/manifest.json`.
2. Тесты, пиннящие инвентарь имён и число карточек (`tests/py/integration/test_tscn_lint.py` и
   аналогичные) — только эти строки.
3. `fixtures/corpus/scene_model/scene_deps/manifest.json` — **только append** `script_facts` для
   новых `.gd` (если такие появятся); старые записи, их порядок, `format_facts`/`snake_cases`/
   `scene_facts` и `tests/py/formats/test_scene_deps_facts.py` — не трогать.

Список всех правок вне папки — в лист и в `WORKLOG`, побайтовый базис — сразу, до правок:
аудитор делает обратную проекцию по sha256.


## §2 Контракт и раскладка

### 2.1 ToolSpec — дословно

```python
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec

GROUP = {
    'type': 'object',
    'required': ['module', 'symbols'],
    'additionalProperties': False,
    'properties': {
        'module': {'type': 'string', 'minLength': 1},
        'symbols': {'type': 'array', 'items': {'type': 'string'}},
    },
}

PLAN_MODULE = {
    'type': 'object',
    'required': ['rel', 'names', 'lines'],
    'additionalProperties': False,
    'properties': {
        'rel': {'type': 'string', 'minLength': 1},
        'names': {'type': 'array', 'items': {'type': 'string'}},
        'lines': {'type': 'integer'},
    },
}.

PLAN_RESULT = {
    'type': 'object',
    'required': ['donor', 'donor_sha256', 'donor_lines', 'target_lines', 'auto_groups',
                 'modules', 'facade', 'moved_names', 'errors', 'warnings', 'inventory', 'refs'],
    'additionalProperties': False,
    'properties': {
        'donor': {'type': 'string', 'minLength': 1},
        'donor_sha256': {'type': 'string', 'minLength': 64, 'maxLength': 64},
        'donor_lines': {'type': 'integer'},
        'target_lines': {'type': 'integer'},
        'auto_groups': {'type': 'boolean'},
        'modules': {'type': 'array', 'items': PLAN_MODULE},
        'facade': {'type': 'object', 'required': ['rel', 'lines', 'reexports'],
                   'additionalProperties': False,
                   'properties': {'rel': {'type': 'string', 'minLength': 1},
                                  'lines': {'type': 'integer'},
                                  'reexports': {'type': 'array', 'items': {'type': 'string'}}}},
        'moved_names': {'type': 'array', 'items': {'type': 'string'}},
        'errors': {'type': 'array', 'items': {'type': 'string'}},
        'warnings': {'type': 'array', 'items': {'type': 'string'}},
        'inventory': {'type': 'object',
                      'required': ['symbols', 'imports', 'other', 'docstring'],
                      'additionalProperties': False,
                      'properties': {
                          'symbols': {'type': 'array', 'items': {
                              'type': 'object',
                              'required': ['name', 'kind', 'lines', 'is_public', 'state'],
                              'additionalProperties': False,
                              'properties': {'name': {'type': 'string', 'minLength': 1},
                                             'kind': {'type': 'string'},
                                             'lines': {'type': 'integer'},
                                             'is_public': {'type': 'boolean'},
                                             'state': {'type': 'string'}}}},
                          'imports': {'type': 'integer'},
                          'other': {'type': 'integer'},
                          'docstring': {'type': 'boolean'}}},
        'refs': {'type': ['object', 'null']},
    },
}

PLAN = ToolSpec(
    name='split_plan',
    description='План разбиения .py агента: модули, имена, фасад, ошибки плана. Только чтение.',
    args=PLAN_ARGS, result=PLAN_RESULT, effects='read', idempotent=True,
    errors=('invalid_input', 'not_found', 'denied'), availability='*', cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES},
)
TOOLS = (SCAN, PLAN)   # SCAN из C.17 не меняется ни на байт
```

`PLAN_ARGS` (рядом с `ARGS` из C.17, отдельной константой):

```python
PLAN_ARGS = {
    'type': 'object', 'required': ['path'], 'additionalProperties': False,
    'properties': {
        'path': {'type': 'string', 'minLength': 1},
        'groups': {'type': 'array', 'items': GROUP},
        'target_lines': {'type': 'integer'},
    },
}
```

Семантика полей:
- `groups` — ключ **`symbols`** (эталон `.py`-пилы), не `funcs` (как у `.gd`); при `groups=None`
  группы черновые (`suggest_groups`), и `auto_groups: true`;
- `target_lines` — как в `cmd_split:934`: приводится `int()`, мусор → `invalid_input` с живым текстом
  моста, диапазон **100..5000**; по умолчанию (поле не передано) — `_DEFAULT_TARGET_LINES = 900`;
- `errors` — **это данные, не исключение**: если план неприменим, инструмент отвечает `ok: true`
  с непустым `errors` (эталон так и делает: `errors` копятся, `apply` их запрещает). `AppError`
  остаётся только для контрактных отказов (путь, политика, нет `plugin.cfg`, лимит, аргументы);
- тексты модулей (`modules[].text`) и фасада (`facade.text`) **не публикуются** — это payload записи,
  он понадобится C.19;
- `refs` — сводка `scan_refs` (`counts`/`hard_files`/`soft_files`/`truncated`) или `null`, если
  эталонный `scan_refs` бросил `SplitError` (эталон оборачивает его в `try/except` и оставляет `None`);
- `schema` эталона не публикуется, `reference_result` в корпусе остаётся сырым.


### 2.2 Где что живёт (R-02, R-11)

| Файл | Содержимое |
| --- | --- |
| `domain/inventory.py` | `file_inventory:270-340` дословно: символы верхнего уровня (`name`, `kind`, `line_start`, `end_lineno`, `lines`, `is_public`, `state`), `imports[{…, end_lineno}]`, `other[{…, name?, lineno}]`, `docstring_end`, `__all__`; плюс `_segment_text:231`, `_expand_comments:235`, `_import_bindings:246`, `_other_item:259`, `used_names:340` |
| `domain/groups.py` | `DEFAULT_TARGET_LINES = 900`, `suggest_groups:349` дословно, `_normalize_groups`-эквивалент: ключ `symbols`, ошибки текстом эталона |
| `domain/facade.py` | `_render_facade:656`, `_format_import:368`, `_find_cycle:375`, `_join_blocks:401`, `_warn_patched_attributes:202` — дословно, без «улучшений» |
| `domain/plan.py` | сборка `prepared`: `donor`, `donor_sha256`, `donor_lines` (`count_lines` — считай как эталон: `len(text.splitlines())`), `target_lines`, `auto_groups`, `modules`, `facade`, `moved_names`, `errors`, `warnings`, `inventory`-сводка, `refs`; `compile()` модулей и фасада в `errors` при `SyntaxError` — как эталон |
| `domain/core.py` | `assemble_plan(prepared)` — публикация без `schema`/`addon_dir`/`text`, плюс существующий `assemble` из C.17 не меняется |
| `app.py` | вторая ветка `call('split_plan', …)`: `validate` → `res://` → `normalize_rel` → `.py` → политика → **`is_file`→`not_found`** → аддон-корень → `read_raw` → лимит → инвентарь/группы/план → `core.assemble_plan`; оркестрация ≤ 80 строк |
| `tools.py` | `SCAN` байт-в-байт + `PLAN_ARGS`/`GROUP`/`PLAN_MODULE`/`PLAN_RESULT`/`PLAN` из §2.1, `TOOLS = (SCAN, PLAN)` |
| `module.py` | `provides_tools=('split_scan', 'split_plan')`, `requires_ports=('fs',)`, `capabilities=('editing.split_py',)`, `entrypoints={'call': app.call}`, `corpus='corpus'` |

Правила: `domain/` без `os`/`pathlib`/`socket`/`subprocess` (R-11; `re`, `codecs`, `ast` — можно,
`ast` здесь и есть суть эталона); ввод-вывод только в `app.py` через `ctx.port('fs')`; новый файл
≤ 400 строк (`kernel/limits.FILE_MAX_LINES`), `app.py` ≤ 80, `tools.py` ≤ 150; чужой `shared` не
импортировать (R-11; ADR-0010 дал ровно один шов `api_check → engine_kb.shared.inheritance`);
`app.call` возвращает payload и кидает `AppError`, единственный `Result` строит `Agent.call`
(`python/runtime/bootstrap.py:66-71`) — runtime/protocol/kernel не трогать.

### 2.3 Проекция «эталон → порт»

| Эталон `plan_split:407-655` | Порт |
| --- | --- |
| `plan_split(addon_dir, rel_path, groups, target_lines)` (без `project_root`!) | `split_plan(path, groups?, target_lines?)`; `addon_dir` берётся из `plugin.cfg` |
| `SplitError("пила работает только с .py: %s")` | `invalid_input` с тем же текстом |
| `SplitError("файл не найден: %s")` | `not_found` (проверка **до** аддон-корня) |
| `prepared["schema"]` | не публикуется (`reference_result` сырой) |
| `prepared["addon_dir"]` | не публикуется |
| `modules[].text`, `facade.text` | не публикуются (payload записи, C.19) |
| `errors` (список) | публикуется как есть, `ok: true` |
| `refs=None` при `SplitError` в `scan_refs` | `refs: null` |
| `inventory` (полный) | сводка: `symbols` без `line_start`/`end_lineno`, `imports`/`other` числами, `docstring` bool |
| `_warn_patched_attributes:202` | дословно, дописывает в `warnings` |

### 2.4 Вход и ошибки

- `path` не строка / пустой / без `res://` → `invalid_input`; не `.py` → `invalid_input`
  («пила работает только с .py: …»); `normalize_rel(...) is None` → `denied` («путь вне проекта»);
  непустой `deny_reason` → `denied` с текстом политики (в т.ч. `addons/…` без `allow_addons`).
- Порядок (важен, см. F11): политика → `is_file` (`not_found`) → аддон-корень (`invalid_input`) →
  чтение → лимит `READ_TEXT_MAX_BYTES` 4 MiB (`invalid_input`) → работа.
- `groups` не список / элемент не объект / пустой `module` → `invalid_input` с живым текстом эталона
  (снимается живым вызовом, не по памяти).
- `target_lines`: не int-совместимое → `invalid_input` («target_lines must be an integer»),
  вне 100..5000 → `invalid_input` («target_lines must be between 100 and 5000»). Как и в C.16/F10,
  эталонная строка моста содержит префикс команды — если живая строка длиннее, зафиксируй это в листе
  как **границу**, а в корпусе пинни тот вариант, который выбрал, и запиши выбор.
- `PermissionError` → `denied`, `EFBIG` → `invalid_input`, прочие `OSError` → `internal`.
- Идемпотентность и равный sha256 дерева до/после — доказать тестом, не обещанием.

### 2.5 Якоря эталона

`SCHEMA:38`, `_DEFAULT_TARGET_LINES:40` (=900), `_SCAN_SKIP_DIRS:43`, `_SCAN_EXTS:48`,
`_MAX_SCAN_FILE_BYTES:51`, `_MAX_OCCURRENCES:52`, `SplitError:58`, `StaleSplitError:62`,
`_norm:66`, `_read_text:70`, `_sha256:87`, `_files_of:91`, `_imported_modules:104`,
`_module_matches:123`, `scan_refs:127`, `_warn_patched_attributes:202`, `_segment_text:231`,
`_expand_comments:235`, `_import_bindings:246`, `_other_item:259`, `file_inventory:270`,
`used_names:340`, `suggest_groups:349`, `_format_import:368`, `_find_cycle:375`, `_join_blocks:401`,
`plan_split:407`, `_render_facade:656`, `apply_prepared_split:718` (C.19), `_cli:792`.
Старые тесты (`tests/test_split_refactor.py` 22 394 B) в корпус попадают только через пересъёмку
живым эталоном, не копированием.


## §3 Шаги

1. **Лист.** В `docs/porting/editing.split_py.md` добавь раздел «C.18 — вторая половина (`split_plan`)»
   с таблицей старого кода (`split_refactor.py:38-62,66-91,202,231-259,270-340,349-401,407-655,656-716`)
   и раздел «F11 и F4» (что найдено, кем, как исправить). Статус листа: «этап 7 (половина 1 принята);
   C.18 в работе». Сразу сними sha256 всех файлов, которые будешь менять (базис обратной проекции).
2. **Корпус — до кода.** Одноразовым скриптом в `%TEMP%` (в репозиторий не класть) вызови **живой**
   `split_refactor.plan_split(addon_dir=<temp-копия>, rel_path=<донор>, groups=…, target_lines=…)`
   и сохрани сырой ответ как `reference_result`, а проекцию по §2.1/§2.3 — как `expect.result`.
   Фикстуры: `fixtures/projects/corpus/editing/split_py/<вариант>/` (в корне `plugin.cfg`),
   `fixture` пишется **относительно `fixtures/projects`**. Кейсы нумеруй с **048**, минимум **20**:
   авто-группы и явные группы; один символ; фасад с реэкспортом; `__all__` в доноре; докстрока;
   приватные символы; `_other_item`-код верхнего уровня; импорты и `_import_bindings`;
   `_join_blocks`/`_find_cycle` (цикл → `errors`); дубль символа в двух группах (→ `errors`);
   символ не найден (→ `errors`); модуль с именем донора (→ `errors`); невалидное имя модуля (→ `errors`);
   `target_lines` 0/499/5001 (границы), мусор в `target_lines`; модуль, который не компилируется
   (синтаксическая ошибка после сборки → `errors`); `refs: null`; `truncated` в `refs`;
   BOM/CRLF/лone CR донора; отсутствующий донор без `plugin.cfg` (**F11** — ждём `not_found`);
   `res://addons/…` → `denied`; не-`.py`; > 4 MiB; идемпотентность и равный sha дерева.
   Манифест — как у C.17 (`schema_version`, `captured_at`, `module`, `reference{file,function,sha256,bytes}`,
   `capture_script{sha256,bytes}`, `fixture_base: fixtures/projects`, `cases`, `inputs`, `contract_refusals`);
   добавь ключ `c18_recut` (что именно переснято).
3. **Красные тесты до кода:** `tests/test_inventory.py`, `tests/test_groups.py`, `tests/test_facade.py`,
   `tests/test_plan.py`, `tests/test_app_plan.py` (второй инструмент, отказы до чтения, лимит 4 MiB,
   `groups`/`target_lines`), `tests/py/integration/test_split_plan.py` (корпус, дерево, идемпотентность),
   `tests/py/contract/test_split_plan_contract.py` (карточка, `effects`, `errors`, `limits`, `TOOLS`).
   Зафиксируй в листе счётчики красного прогона.
4. **Код** в порядке `inventory` → `groups` → `facade` → `plan` → `core.assemble_plan` → `app` → `tools`/`module`.
5. **Контракт:** `python -B tools/gen_contract.py --write` создаёт только
   `contract/capabilities/split_plan.json`; 24 старые карточки байт-в-байт; `--check` → **25**.
6. **F11 (исправление дефекта).** В `split_py/app.py` переставь проверки: `present = fs.is_file(rel)`
   и `raise AppError('not_found', 'файл не найден: %s' % rel)` — **до** `_addon_root(...)`.
   Тексты не менять, поведение для существующих файлов не менять. Добавь в корпус кейс «отсутствующий
   файл в проекте без `plugin.cfg`» → `not_found`, и в тест — пин порядка. В лист: «F11 закрыт, кем/когда
   найден, что изменилось, чем доказано».
7. **F4 (долг гейта).** В `tools/selfcheck.py` (строка ~215) замени
   `for extra in sorted(integration.glob("test_%s*.py" % name))` на выбор по правилу **самого длинного
   префикса**: файл `test_<X>_<rest>.py` принадлежит инструменту `<X>_<rest>`, если `<X>_<rest>` есть
   среди имён известных инструментов всех `ModuleSpec`, и не принадлежит `<X>`. Требуется:
   ADR `docs/adr/0013-selfcheck-unit-selector.md` (контекст — F4, решение, последствия, границы:
   не менять порядок проверок, не трогать `corpus`/`contract` логику), новый тест в
   `tests/py/tools/` (пин: `engine_kb.class_api` считает ровно свои 128; `editing.split_gd` не теряет
   `test_split_gd_scan.py`/`test_split_gd_plan.py`), и **таблица до/после** юнит-счётчиков для всех
   механик в листе (`python -B tools/selfcheck.py <id>` до правки и после). Ожидаемо меняется только
   `engine_kb.class_api` 186 → 128.
8. **Двойной прогон:** полный non-live (3880 + новые; junit только через python-драйвер),
   `tools/snapshot_diff.py` (771 + новые, строка `editing/split_py` = 47 + N),
   `selfcheck editing.split_py` (юниты вырастут, **scan-корпус 47/47 цел**), соседи по §0
   (кроме `class_api` → 128/26), `lint_arch`, `check_limits`, `security_audit`, live = **3** без skip,
   `.gd.uid` = 83, debris 0.
9. **Записи:** лист (этап 7 + C.18 + F11/F4 с доказательствами), `docs/parity.md`,
   `docs/tests-map.md`, `docs/PROGRESS.md` (строка остаётся 7, текст дополняется),
   `docs/WORKLOG.md` — только append в `ab`, **без нормализации EOL**.
   «Принято/ported» и этап 7 заново **не писать**.


## §4 Решения, которые уже приняты (не пересматривать)

1. Ключ групп — **`symbols`** (эталон `.py`); `funcs` — это `.gd`-пила, не путать.
2. `errors` плана — **данные**, не исключение: `ok: true` + непустой список. `AppError` только для
   контрактных отказов.
3. Тексты модулей и фасада не публикуются (payload записи C.19); `donor_sha256` публикуется — он
   защитит будущий apply от устаревшего плана.
4. `refs: null` допустим (эталон так делает, когда `scan_refs` бросил `SplitError`).
5. `inventory` публикуется **сводкой** (без `line_start`/`end_lineno`), потому что эти поля — адреса
   внутри донора и нужны только записи.
6. `compile()` модулей/фасада остаётся в `domain/` (`ast`/`compile` — чистые), ошибки идут в `errors`
   дословным текстом эталона.
7. F11 — **перестановка проверок**, а не новый код; F4 — правка **только** селектора, с ADR и пином.
8. Никаких «улучшений» эталона: странности (`used_names` шире, `_other_item` эвристики) переносятся
   дословно и пиннятся тестом.

## §5 Доказательства

Мутации (каждая — байтовый бэкап и сверка sha256 до/после):

| # | Правка | Что должно покраснеть |
| --- | --- | --- |
| M1 | `symbols` → `funcs` в разборе групп | кейсы с явными группами |
| M2 | `errors` заменены на `raise AppError(...)` | кейсы с непустым `errors` |
| M3 | `donor_sha256` считается по нормализованному тексту | кейс CRLF/BOM-донора |
| M4 | `refs` всегда `{}` вместо `null` | кейс `refs: null` |
| M5 | `_render_facade` без переноса `__all__` | кейс `__all__` |
| M6 | `_find_cycle` отключён | кейс цикла |
| M7 | `suggest_groups` игнорирует `target_lines` | кейс авто-групп с 900 |
| M8 | инвентарь публикует `line_start` | контрактный тест схемы |

Подложки: **P1** убрать `'wrappers'`-аналог (`'moved_names'`) из `PLAN_RESULT.required` → ловится
**только** `gen_contract --check` (`fail: split_plan.json`); **P2** `import os` в `domain/facade.py` →
`lint_arch`; **P3** `app.py` импортирует `python.modules.verification.shared.source_text` → `lint_arch`.
Для F11: **P4** вернуть старый порядок проверок → красный корпусный кейс. Для F4: **P5** вернуть старый
селектор → красный тест пина и счётчик `class_api` 186.

Обратная проекция: для каждого добавленного/изменённого файла — bytes + sha256 до и после; доказать,
что принятая половина 1 (`refs.py`, `walk.py`, `text.py`, `split_scan.json`, 47 кейсов), `editing.split_gd`
целиком, 24 старые карточки, `python/kernel/*`, `python/substrate/*`, `python/runtime/*`,
`python/protocol/*`, `editor/**` и `verification/*`/`engine_kb/*` — байт-в-байт.

Гигиена: дерево 2999 + новые файлы; `.gd.uid` 83; ни `__pycache__`, ни `.pytest_cache`, ни
`.bak/.tmp/.orig`, ни `zz_*`; одноразовые скрипты — только в `%TEMP%`.

## §6 Стоп-условия

Остановись и спроси, если:
- для паритета нужно править `python/kernel/*`, `python/substrate/*`, `python/runtime/*`,
  `python/protocol/*` или `editing/shared/*`;
- проекция требует поля, которого в эталоне нет, или теряется текст эталонного сообщения;
- `snapshot_diff` для `editing/split_py` перестал быть 47/47 по scan-кейсам;
- соседние selfcheck поехали (кроме ожидаемого `class_api` 186 → 128);
- правка F4 требует менять больше, чем селектор (тогда — отдельный срез, а не «заодно»);
- хочется применить план к диску или запустить Godot (это C.19 и ADR).


## §7 Что будет проверять аудитор

1. Своя пересъёмка корпуса: живой `split_refactor.plan_split` на копии фикстуры, своя проекция,
   порт по всем кейсам; отказы — по `kind`, а где пин есть — по дословному тексту.
2. Свой дифференциал шире корпуса: все `.py`-доноры фикстур + ≥ 6 реальных `.py` порта,
   в двух режимах (`groups=None` и явные группы), плюс `target_lines` 900 и 100.
3. Свои мутации M1–M8 и подложки P1–P5 (P1/P5 ловятся только гейтами/пинами).
4. Инвентарь: `gen_contract --check` = **25**, 26 файлов в `contract/capabilities`,
   `context.gather` = 24 имени с `split_plan: read`, `# verb:` = 6, `verbs_version: 3`.
5. Неизменность: `editing.split_gd` 625/102, `verification.check` 188/75, `api_check` 206/52,
   `gd_lint` 126/37, `tscn_lint` 315/65; `engine_kb.class_api` — **128/26** (после F4);
   sha256 принятых `domain/` совпадают с §0.
6. Гигиена: дерево, `.gd.uid` 83, debris 0; live 3 без skip (с временным `[editor_plugins]`
   и побайтовым восстановлением `project.godot`).

## §8 Финальный прогон и записи

Один отчёт: лист + `docs/WORKLOG.md`. В отчёте — non-live (число, время, collect), `snapshot_diff`
с новой строкой корпуса, таблица `selfcheck editing.split_py`, `reports/selfcheck/editing.split_py.json`,
`gen_contract --check` = 25, `lint_arch`, `check_limits`, `security_audit`, live = 3,
дерево/`.gd.uid`/debris, таблица мутаций с sha256, обратная проекция и таблица юнит-счётчиков
до/после для F4. Записи: лист (этап 7 + C.18 + F11/F4), `docs/parity.md`, `docs/tests-map.md`,
`docs/PROGRESS.md`, `docs/WORKLOG.md` (append, без EOL-нормализации), три разрешённые правки.
Не писать: «принято/ported», новый этап 7, `docs/porting/_audit-handoff.md`,
`contract/editor_verbs.json`, `python/kernel/schema.py`, `tools/lint_arch.py`, `tools/gen_contract.py`,
`tools/security_audit.py`, `tools/snapshot_diff.py`; `tools/selfcheck.py` — **только** селектор F4.
Сдача: «C.18 готов к независимому аудиту, не принято» + список sha256 изменённых файлов
и перечень намеренных границ.

## §9 Ошибки прошлых срезов — не повторять

Это список **моих** промахов (аудитор), из-за которых срезы возвращались. Читай перед работой:

1. **F11 (сейчас в этом срезе):** в `split_py/app.py` проверка аддон-корня стоит **до** `is_file`,
   поэтому отсутствующий файл вне аддона даёт `invalid_input` про `plugin.cfg` вместо `not_found`.
   Порядок проверок — часть паритета; снимай тексты отказов **живым** вызовом эталона.
2. **F10/F6:** тексты сообщений я формулировал по памяти; эталонная строка моста содержит префикс
   команды. Любой пин текста — только из живого вызова, иначе это граница, а её надо документировать.
3. **EOL `WORKLOG`:** дважды нормализовал весь файл; исторический префикс 4479 CRLF обязателен,
   писать только `append` в `ab`.
4. **`--junitxml`:** `Start-Process` рвёт склеенный аргумент — только python-драйвер через `subprocess`.
5. **`recovery: plan=… expired`** в stderr — не падение прогона.
6. **Мутации:** без параллельных прогонов и без `Stop-Process` (однажды оставил мутацию в принятом файле).
7. **Одноразовые скрипты** — только в `%TEMP%`: мой `hash9.py` однажды перезаписал принятый
   `engine_kb/shared/inheritance.py`.
8. **Патч-скрипты** — с `assert` ровно одного попадания: `between()` не съедал якорь и дважды
   дублировал строку в handoff.
9. **`fixture`** — всегда относительно `fixtures/projects`; копия реального аддона не сканируется
   (`PathPolicy._agent_rel` → `None`, «аддоны закрыты fail closed»).
10. **Live:** требует временного `[editor_plugins]` во внешнем `project.godot`
    (335 B, sha `958b3a92d706…`) и побайтового восстановления; live-прогон удаляет корневой
    `plugin.gd.uid` — восстанавливать из бэкапа, `.gd.uid` держать 83.


## §10 Уточнения аудитора (сессия 74) — блокеры B1–B7 сняты

Портер остановился правильно: §2.1 был написан по памяти и расходится с живым эталоном.
**Приоритет §10 выше §2.1/§3.7**; ниже — что отменяется и что разрешается.

### B1 — `state` это `bool`, а не строка (моя ошибка в §2.1)

В `PLAN_RESULT.properties.inventory.properties.symbols.items.properties` заменить
`'state': {'type': 'string'}` на `'state': {'type': 'boolean'}`. Публикуется native-значение
(`split_refactor.py:633-636`), никакого строкового кодирования не выдумывать.

### B2 — `reexports` это объекты (моя ошибка в §2.1)

`facade.properties.reexports` = `{'type': 'array', 'items': REEXPORT}`, где

```python
REEXPORT = {
    'type': 'object',
    'required': ['module', 'names'],
    'additionalProperties': False,
    'properties': {'module': {'type': 'string', 'minLength': 1},
                   'names': {'type': 'array', 'items': {'type': 'string'}}},
}
```

Native `:685` возвращает `{module, names}[]` — публикуется как есть, порядок эталонный.

### B3 — `donor_sha256` считается по нормализованному тексту (моя ошибка в M3)

`plan_split` хэширует `_sha256(text)` после `_read_text` (utf-8-sig + universal newlines):
native normalized SHA. Значит мутация **M3 инвертируется**: красной должна быть
«sha по сырым байтам», а не наоборот. Правило: `donor_sha256` = sha256 от `decode(raw)`
(как в принятом C.17 для `split_scan` и как в C.16 для `.gd`), сырой SHA в публикацию не идёт.

### B4 — второй production-вызов `fs.exists` разрешён узко

Native `:573` считает занятым целевой путь **и файл, и каталог** (`os.path.exists`), а ADR-0011
разрешил единственный вызов только `.gd`-пиле. Разрешаю:

- новый ADR `docs/adr/0014-fs-exists-split-py.md` (контекст — B4, решение, последствия, границы);
- **один** дополнительный production-вызов `fs.exists(...)` в `python/modules/editing/split_py/`
  (файл на твой выбор, например `plan_io.py`), до записи — только проверка занятости цели;
- `python/substrate/fs/disk_fs.py` **не менять** (метод уже есть), старый вызов в `split_gd/plan_io.py`
  **не трогать**;
- пин: grep-тест, что production-вызовов `exists(` ровно **два** (split_gd + split_py), и тест,
  что каталог с именем `<module>.py` даёт `AppError('invalid_input', 'целевой файл уже существует: <rel>')`
  (текст снять живым эталоном, у `.gd`-пилы была формулировка «целевой модуль»);
- корпус: кейсы «цель уже существует файлом» и «цель уже существует каталогом».

### B5 — узкие фильтры по `tool` в существующих scan-тестах разрешены

Разрешаю в **существующих** тестах `split_py`, которые читают все numbered JSON как scan-кейсы,
добавить фильтр `case['tool'] == 'split_scan'` и multi-tool пины (`provides_tools == ('split_scan','split_plan')`):
`tests/py/integration/test_split_scan.py`, `tests/py/contract/test_split_scan_contract.py`,
`python/modules/editing/split_py/tests/*` (scan-часть). Запрещено: менять 47 старых кейсов,
`SCAN` ToolSpec, `contract/capabilities/split_scan.json`, `domain/refs.py`/`walk.py`/`text.py`,
счётчики scan-корпуса (должно остаться 47/47). Это та же узкая правка, что была разрешена в C.15 для `.gd`.


### B6 — F4 выходит из C.18 (моя ошибка проектирования)

Ты измерил: общий «longest known tool prefix» меняет не только `engine_kb.class_api` 186 → 128,
но и `scene_model.node_info` 352 → 247 (`test_node_delete_preview.py`, `test_node_rename_preview.py`,
`test_node_reparent_preview.py`) и `scene_model.tree` 168 → 116 (`test_scene_deps.py`,
`test_scene_ops_bridge.py`). Это **корректные** дельты по существу (эти файлы принадлежат другим
инструментам), но менять счётчики соседей внутри среза механики запрещено — поэтому:

- **F4 из C.18 удаляется полностью**: `tools/selfcheck.py` в этом срезе **не трогать**,
  `engine_kb.class_api` остаётся **186/26**, ADR-0013 остаётся `proposed` и в C.18 не активируется,
  `tests/py/tools/test_selfcheck_unit_selector.py` в C.18 не добавляется (твой архив `.red` — правильное
  решение, оставь его внешним досье);
- F4 становится отдельным срезом **C.19 (`tools/selfcheck.py`, долг F4)**, где я заранее разрешаю
  **ровно три** дельты: `class_api` 186→128, `node_info` 352→247, `tree` 168→116 — и требую, чтобы
  все остальные 41 механика остались байт-в-байт по счётчикам; там же ADR-0013 → accepted, красные пины,
  P5 и полная таблица 44 «до/после»;
- запись split-плана после этого сдвигается в **C.20** (нужен ADR о create/delete в воронке).

Отменяю этим пунктом: §0 «`class_api` … → 128/26», §3.7 целиком, §5 P5, §6 «кроме ожидаемого
`class_api` 186 → 128», §7.5 «`class_api` — 128/26 (после F4)». В C.18 требование обратное:
**все 24 механики, включая `class_api` 186/26, остаются с прежними числами.**

### B7 — зависимость от `arch_map` входит в срез (моя недоработка: не заметил в §2.2)

`plan_split` вызывает `arch_map.*`: `load_map:81` (читает `<addon>/docs/architecture_map.json`,
utf-8-sig, валидирует `dict` + `zones: list`, компилирует glob'ы, битый/отсутствующий → `None`),
`zone_for:117`, `core_dir_of:128`, `line_policy:134`, `count_lines:169` (`len(text.splitlines())`,
пусто → 0), `name_checks_enabled:176`, `name_index:234` (индекс «имя → [(rel, "def"|"class")]» по
`.py` аддона, с `public_names(text)`), `_join_hits` (текст ссылок). Разрешаю:

- новый `python/modules/editing/split_py/domain/arch.py` — **дословный** перенос перечисленных чистых
  функций (`glob_to_re`, `zone_for`, `core_dir_of`, `line_policy`, `count_lines`, `name_checks_enabled`,
  `public_names`, `name_index`, `join_hits`), без `os`/`pathlib`;
- ввод-вывод — только в `app.py`: чтение `docs/architecture_map.json` через `fs.read_raw`
  (отсутствует/битый → `None`, как эталон) и список файлов для индекса имён через `fs.list_files()`;
  `name_index` принимает `(files, texts)` или аналог, но семантика эталонная;
- **никакого module-global кэша** (`_MAP_CACHE`/`_INDEX_CACHE` эталона не переносим): карта и индекс
  читаются на каждый вызов — это осознанное решение в духе ADR-0009, записать в лист;
- корпус: кейсы «карты нет» (`zone` unknown, `new_files: warn`), «зона превышает лимит строк» → текст
  ошибки эталона, «`new_files: deny`», «`check_names: false`», «имя дублирует ядро» → ошибка
  core-duplicate, «generated-only»; фикстуры могут содержать `docs/architecture_map.json`;
- тексты зон/лимитов/дублей снимать **живым** вызовом эталона, не по памяти (см. §9.1–§9.2).

Если что-то из `arch_map` окажется тяжелее, чем чистая функция + чтение файла (например, ему нужен
`tools/arch_audit.py`), — **остановись и спроси**, а не тяни половину подсистемы.

### Порядок продолжения

1. F11 — перестановка проверок + корпусный кейс (B5 уже разрешает новые numbered cases).
2. Схема по B1/B2, `donor_sha256` по B3, мутация M3 наоборот.
3. `domain/arch.py` + `app.py`-IO по B7, затем инвентарь/группы/фасад/план.
4. `fs.exists` по B4 (ADR-0014, пин на два вызова, кейсы файла и каталога).
5. Контракт: `gen_contract --write` → только `split_plan.json`, `--check` = **25** (26 файлов).
6. Двойной прогон по §7/§8, но с числами §10: соседи не двигаются, включая `class_api` 186/26.
7. Записи: лист (этап 7 + C.18 + F11 + B1–B7 с доказательствами), `parity.md`, `tests-map.md`,
   `PROGRESS.md`, `WORKLOG.md` (append, без EOL-нормализации).
8. Сдача: «C.18 готов к независимому аудиту, не принято» + sha256-список + список намеренных границ.

  untracked-строки там не удалять).
