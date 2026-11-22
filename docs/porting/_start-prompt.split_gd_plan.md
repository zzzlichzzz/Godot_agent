# C.15 — `editing.split_gd`, половина 2: инструмент `split_gd_plan` (план разбиения `.gd`, только чтение)

Ты — **портер**. Аудитор ведёт записи и приёмку, ты пишешь код и доказательства.
Этап сам себе **не ставишь**, шапку «выполнено/принято/ported» **не пишешь**,
`docs/porting/_audit-handoff.md` **не правишь**.

Важно про срез: механика `editing.split_gd` **уже принята** (C.14, половина 1 —
`split_gd_scan`, этап 7). Ты **добавляешь второй инструмент** в принятый модуль.
Принятый `split_gd_scan` и его корпус 47/47 должны остаться **байт-в-байт**.

## Читать до первой строки кода

1. `AGENTS.md`, `RULES.md` (R-02, R-05, R-09, R-11, R-12, R-13, R-22).
2. `docs/architecture.md`, `docs/PORTING.md`, ADR-0004, 0006, 0009, 0010.
3. `docs/porting/editing.split_gd.md` — **свой лист**, там уже описаны эталон, решения
   половины 1 и что отложено в C.15 (читай разделы «Старый код», «Решения по ходу»).
4. `docs/parity.md` — строка `split_gd_scan/plan`; `docs/PROGRESS.md` — строка
   `editing.split_gd` (этап 7) и как оформлялось добавление инструмента в принятую
   механику (C.13 добавлял вклад в `verification.check`).
5. `docs/tests-map.md`, `_template.md`, листы `verification.tscn_lint.md` (как выглядит
   лист с эталоном на 1300 строк), `engine_kb.class_api.md` (как читается кэш API).
6. `docs/WORKLOG.md` — последние три сессии (65–67).
7. `docs/security/invariants.md`.

## §0 База (снято аудитом, сессия 67, 2026-10-31 — не пересчитывать)

* `pytest python/modules tests/py --ignore=tests/py/live` → **3164 passed**, файлов-сбора 100, stderr пуст.
* Живое `tests/py/live` → **3 passed**, 21.8 с (Godot `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`).
* `tools/snapshot_diff.py` → **669/0**; `tools/gen_contract.py --check` → **22** артефакта (23 файла с `_template.json`).
* `selfcheck`: `editing.split_gd` **232/47**, `verification.check` 188/75, `verification.api_check` 206/52,
  `verification.gd_lint` 126/37, `verification.tscn_lint` 315/65, `engine_kb.class_api` 186/26
  (186 — долг **F4**: селектор `tools/selfcheck.py:215`; не «исправляй»).
* Слои/лимиты **510/0**, security ok. Дерево **2529** файлов, `.gd.uid` **83**, debris 0;
  листов 24, промптов 33, ADR 10, правил 22; `PROGRESS` 44 строки (22 на этапе 7 / 1 на 6 / 21 на нуле).
* Мост: `contract/editor_verbs.json` `verbs_version: 3`, sha `CDAF8D23A6BF…`.
* Замороженные: `kernel/schema.py` `629FCE54E6FE`, `tools/gen_contract.py` `FA7E6E91C872`,
  `tools/security_audit.py` `2CF0D7F6B1AF`, `tools/snapshot_diff.py`, `tools/selfcheck.py`,
  `tools/lint_arch.py` (**9842 B `A6C5EDD47650`** — уже правлен по ADR-0010, менять нельзя),
  `editor/bridge/verbs/scene/scene_executor.gd` `B7AFF592B75D`.
* Принятое, что нельзя ломать: `editing/split_gd/{tools.py,app.py,module.py,domain/{core,refs,inventory,text}.py}`
  (хэши снять при старте и записать в лист), `fixtures/corpus/editing/split_gd/**` (47 кейсов + manifest),
  карточка `split_gd_scan.json`, а также `verification/*`, `scene_model/*`, `code_intel/*`, `engine_kb/*`,
  `editing/{write_preview,write_apply,rollback,scene_ops}`.
* **Цели среза:** второй инструмент в том же модуле → `provides_tools=('split_gd_scan','split_gd_plan')`,
  карточек **23** (24 файла), `context.gather` **21 → 22** имени, листов 24 → 25, промптов 33 → 34.
  Строка `PROGRESS` `editing.split_gd` **остаётся 7** (механика принята), в неё добавляется
  пометка о второй половине — как в C.13 для `verification.check`.

## §0.1 Эталон (сверять хэши, не помнить)

* `python/godot_tools/split_gd.py` — **63 421 B, 1333 LF, 0 CRLF,
  sha256 `18f05d10b8e875ed77040b8a47beb6ccbdb409b55d791ec0318466473969bfc7`**
  (эталон: `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent`).
  В C.15 нужны: `suggest_groups:557-583`, `_engine_api:583-624`, `_apply_edits:624-640`,
  `_rewrite_body:640-714`, `_downgrade_panel_inference:714-765`, `_render_static_sig:765-780`,
  `_render_wrapper:780-794`, `_normalize_groups:898-932`, `_render_module:932-955`,
  `plan_split:955-1138`, `_public_plan:1138-1148`,
  плюс уже перенесённые в C.14 `tokenize:196-272`, `_prev_token:272`, `_parse_params:280-335`,
  `_collect_locals:335-388`, `_ENGINE_VIRTUAL:388`, `_indent_width:396`, `_code_skeleton:400-432`,
  `_balance:432`, `_leading_comment_start:442`, `file_inventory:454-557`.
  Константы: `SCHEMA:57`, `_DEFAULT_TARGET_LINES:58` (1100), `_LINE_WARN:59` (1500), `_LINE_MAX:60` (2000),
  `_PANEL_PARAM:61`, `_FALLBACK_METHODS:79`, `_FALLBACK_PROPS:105`. Исключения: `SplitGdError:119`,
  `StaleSplitGdError:123`.
* Мост: `tools/agent_bridge.py` (142 171 B, `a9b1ad832fd0…`) — `_split_gd_target_lines:1022`
  (`target_lines` не int → `must be an integer`; вне 100..5000 → `must be between 100 and 5000`),
  ветка plan в `cmd_split_gd:1035`, `_make_split_gd_prepared:2041` (**путь записи, не переносим**).
  MCP: `godot_agent_mcp.py:471` `split_gd_plan(file, groups=[], target_lines=0)`.
* Токенизатор (`tokenize`) и `_collect_locals`/`_parse_params` **уже перенесены** в C.14? — **нет**:
  в C.14 из этого блока перенесены только `_code_skeleton`, `_balance`, `_indent_width`,
  `_leading_comment_start`, `file_inventory`. Всё остальное (`tokenize`, `_prev_token`,

## §1 Границы среза

Срез — **вторая половина** механики `editing.split_gd`: инструмент **`split_gd_plan`**,
только чтение. Он отвечает на вопрос «что поедет»: какие модули получатся, сколько строк
останется донору, какие обёртки и с какими предупреждениями. Он **ничего не пишет**:
ни файлов модулей, ни донора, ни Godot не запускает.

Разделение честное: `scan_refs` (C.14) отвечает «кто пользуется», `plan_split`
(этот срез) — «как разложить». Третий шаг, реальная запись (`_make_split_gd_prepared`
в мосте, дифф-превью, WAL, `apply_prepared_split`, `_godot_check`), — **не здесь**:
это воронка `write_preview → write_apply → rollback`, уже принятая, и подключать
к ней `split_gd` будет отдельный срез.

### В срезе

* папка `python/modules/editing/split_gd/` — **дописывается**: `tools.py` (второй
  `ToolSpec`), `module.py` (второй инструмент в `provides_tools`, `requires_ports`),
  `app.py` (ветка `split_gd_plan`), `domain/`: токенизатор и рендер
  (`domain/tokens.py`, `domain/collect.py`, `domain/engine.py`, `domain/render.py`),
  `domain/core.py` (сборка плана);
* корпус `fixtures/corpus/editing/split_gd/` — **тот же**, кейсы `101-…` и далее;
  фикстуры — `fixtures/projects/corpus/editing/split_gd_plan/<вариант>/`;
* карточка `contract/capabilities/split_gd_plan.json` (генерируется `gen_contract --write`);
* записи: лист `docs/porting/editing.split_gd.md` (раздел C.15), `parity.md`,
  `PROGRESS.md`, `WORKLOG.md`, `tests-map.md`.

### Не в срезе

`_make_split_gd_prepared` и запись; `apply_prepared_split:1177`, `_godot_check:1162`,
`StaleSplitGdError` (нужен только записи); `main.py`-route; `split_refactor`/`split_py`;
`editing.file_refactor`, `editing.paths_preview`; `verification.*`, `engine_kb.*`;
`contract/editor_verbs.json`; замороженные `tools/*`, `kernel/schema.py`;
**долг F4** (`tools/selfcheck.py:215`); `_audit-handoff.md`.

### Разрешённые правки вне папки и корпуса — ровно четыре

1. `fixtures/corpus/context/gather/001-all-sections.json` + `manifest.json`: имя
   `split_gd_plan` с эффектом `"read"`, `count` **21 → 22**, и — **только** — обновление
   `sha256` записи `001-all-sections` в `manifest.json`. Структурная причина: тест
   `test_scene_deps_facts.py` требует точного покрытия `.gd`, а пин `case001` обязан
   следовать за изменением файла (тот же узкий прецедент, что B1 в C.14).
2. `fixtures/corpus/scene_model/scene_deps/manifest.json`: **только дописать** в конец
   `script_facts` факты новых `.gd`-фикстур C.15 (`path`, `bytes`, `sha256`, `handlers`,
   `custom_signals`, `connected`). Прежние 198 записей, их порядок, `format_facts`,
   `snake_cases`, `scene_facts`, EOL — **не трогать**; тест покрытия не менять.
3. Тесты, которые пинят число карточек и список имён инструментов
   (`test_tscn_lint.py`, `test_verify.py`, `test_gd_lint.py`, `test_node.py`,
   `test_scene.py`, `test_functions_contract.py`, `test_usages_contract.py`) — **только**
   число/список, ни одной другой строки.
4. `docs/parity.md` — строка `split_gd_scan/plan`.

Всё остальное — байт-в-байт. Список правок продублируй в листе и WORKLOG: аудитор
делает обратную проекцию по sha256 и сверяет с бэкапом.

  `_parse_params`, `_collect_locals`, `_ENGINE_VIRTUAL`) — **новые файлы этого среза**;
  проверь по листу и по факту, что уже есть в `domain/`, и не дублируй.


## §2 Контракт и раскладка

### 2.1 `ToolSpec` — дословно

```python
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec

GROUP = {
    'type': 'object',
    'required': ['module', 'funcs'],
    'additionalProperties': False,
    'properties': {
        'module': {'type': 'string', 'minLength': 1},
        'funcs': {'type': 'array', 'minItems': 1, 'items': {'type': 'string'}},
    },
}
PLAN_MODULE = {
    'type': 'object',
    'required': ['path', 'lines', 'funcs'],
    'additionalProperties': False,
    'properties': {
        'path': {'type': 'string', 'minLength': 1},
        'lines': {'type': 'integer'},
        'funcs': {'type': 'array', 'items': {'type': 'string'}},
    },
}
ARGS = {
    'type': 'object',
    'required': ['path'],
    'additionalProperties': False,
    'properties': {
        'path': {'type': 'string', 'minLength': 1},
        'groups': {'type': 'array', 'items': GROUP},
        'target_lines': {'type': 'integer', 'minimum': 0, 'maximum': 5000},
    },
}
RESULT = {
    'type': 'object',
    'required': ['donor', 'target_lines', 'lines_before', 'lines_after',
                 'modules', 'wrappers', 'warnings', 'groups'],
    'additionalProperties': False,
    'properties': {
        'donor': {'type': 'string', 'minLength': 1},
        'target_lines': {'type': 'integer'},
        'lines_before': {'type': 'integer'},
        'lines_after': {'type': 'integer'},
        'modules': {'type': 'array', 'items': PLAN_MODULE},
        'wrappers': {'type': 'integer'},
        'warnings': {'type': 'array', 'items': {'type': 'string'}},
        'groups': {'type': 'array', 'items': GROUP},
    },
}
PLAN = ToolSpec(
    name='split_gd_plan',
    description='План разбиения .gd агента: модули, обёртки, строки донора. Только чтение.',
    args=ARGS, result=RESULT, effects='read', idempotent=True,
    errors=('invalid_input', 'not_found', 'denied'), availability='*', cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES},
)
TOOLS = (SCAN, PLAN)          # SCAN из C.14 не меняется ни на байт
```

**Сверь проекцию с фактом.** Поля выше — то, что в эталоне отдаёт `_public_plan:1138`
и ветка plan в `cmd_split_gd`. Первым делом вызови эталон живьём на фикстуре и
посмотри, какие ключи реально возвращает `_public_plan`. Если ключа нет — **не выдумывай**:
убери его из `RESULT` и запиши в лист «Решения по ходу». Если есть лишний ключ, который
не раскрывает содержимое файлов и не требует записи, — **опубликуй** его и допиши в схему.
Содержимое модулей (`content`) **не публикуется**: это заготовка записи, она живёт
внутри и пригодится C.16.

### 2.2 Смысл полей

* `donor` — путь внутри аддона (`editor/panel.gd`), как в C.14 (`_norm` эталона).
* `target_lines` — **фактическое** значение после нормализации: `0`/не пришло → `1100`
  (`_DEFAULT_TARGET_LINES`); int вне `100..5000` → `invalid_input` с текстом как у моста
  (`target_lines must be between 100 and 5000`); не int → `invalid_input`.
* `lines_before` / `lines_after` — `stats.donor_before` / `stats.donor_after` (мост печатает `%d -> %d`).
* `modules` — по одному на модуль, в порядке групп: `path` относительно аддона (`module_rel`),
  `lines`, `funcs` (имена в порядке групп). Никакого `content`.
* `wrappers` — `stats.moved` (мост печатает «обёрток %d»).
* `warnings` — строки эталона **дословно** (`_LINE_WARN`/`_LINE_MAX`, `_downgrade_panel_inference`,
  предупреждения групп), порядок как у эталона.
* `groups` — результат `_normalize_groups`, чтобы вызывающий видел применённое;
  если `groups` не переданы — авто-группы `suggest_groups`.


### 2.3 Где что живёт (R-02, R-11)

| Файл | Что | Откуда |
|---|---|---|
| `domain/tokens.py` | `tokenize:196-272`, `_prev_token:272` — дословно | эталон |
| `domain/collect.py` | `_parse_params:280-335`, `_collect_locals:335-388`, `_ENGINE_VIRTUAL:388` | эталон |
| `domain/engine.py` | `_engine_api:583-624` — **без** `history`/`addon_dir`: классы приходят аргументом; пусто → `_FALLBACK_METHODS:79` / `_FALLBACK_PROPS:105` | эталон + порт |
| `domain/render.py` | `suggest_groups:557`, `_apply_edits:624`, `_rewrite_body:640`, `_downgrade_panel_inference:714`, `_render_static_sig:765`, `_render_wrapper:780`, `_render_module:932-955`, `_normalize_groups:898-932` | эталон |
| `domain/core.py` | `plan(inventory, methods, props, groups, target_lines)` → публичный payload; `content` модулей — локальная, нужна C.16 | `plan_split:955-1138` + `_public_plan:1138` |
| `app.py` | оркестрация ≤ 80 строк: валидация → путь/политика → `plugin.cfg` → `read_raw` (4 MiB) → `api_cache.snapshot()` → `core.plan` | как в C.14 |
| `tools.py` | `SCAN` (не менять) + `PLAN`, `TOOLS = (SCAN, PLAN)` | §2.1 |
| `module.py` | `provides_tools=('split_gd_scan','split_gd_plan')`, `requires_ports=('fs','api_cache')` | аддитивно |
| `ports.py` | `Protocol ApiCache` с `snapshot() -> (dict, str)` | аддитивно |

Правила: `domain/` без `os`/`pathlib`/`socket`/`subprocess` (`re`, `codecs`, `json` можно);
IO только в `app.py` через `ctx.port('fs')`; новый файл ≤ 400 строк
(`kernel/limits.FILE_MAX_LINES`), `app.py` ≤ 80, `tools.py` ≤ 150; чужой
`verification/shared/*` **не импортировать** (R-11: ADR-0010 дал ровно один шов).

### 2.4 Проекция «эталон → порт»

| Эталон | Порт |
|---|---|
| `addon_dir` из моста + `--access agent-dev` | аддон-корень = ближайший предок с `plugin.cfg` (как C.14), право чтения даёт `PathPolicy` |
| `_engine_api(addon_dir, project_root, base_class)` → кэш проекта/бандла | `ctx.port('api_cache').snapshot()` → `classes`; пусто → `_FALLBACK_*` |
| `plan_split(addon_dir, rel, groups, target_lines, project_root)` | `core.plan(...)` — те же аргументы по смыслу, без путей ФС |
| `_public_plan:1138` | `RESULT` (§2.1), сверенный живьём |
| `SplitGdError("донор не найден")` | `not_found` |
| `apply_prepared_split:1177`, `_godot_check:1162`, `StaleSplitGdError` | **не переносим** (запись = C.16) |

### 2.5 Вход и ошибки

`path` не строка / пустой / не `res://` / не `.gd` → `invalid_input` с человеческим текстом,
без абсолютных путей в ответе. `normalize_rel` → None → `denied('путь вне проекта')`.
`deny_reason` непустой (в т.ч. `addons/` без `allow_addons`) → `denied` с текстом политики.
Нет файла → `not_found`. Нет `plugin.cfg` выше → `invalid_input` («донор не находится внутри
аддона с plugin.cfg»). Доннор > `READ_TEXT_MAX_BYTES` (4 MiB по сырым байтам) → `invalid_input`.
`groups` не список / элемент не объект / `funcs` пустой → `invalid_input`; имя функции, которого
нет в доноре, → `invalid_input` с текстом эталона (сверь дословно). `PermissionError` → `denied`,
`EFBIG` → `invalid_input`, прочий `OSError` → `internal`.

`app.call` **возвращает payload и бросает `AppError`**; единый `Result` собирает `Agent.call`
(`python/runtime/bootstrap.py:66-71`) — runtime не трогать (решение B3 из C.14).
Идемпотентность: два вызова подряд дают одинаковый ответ; sha256 всех файлов до/после равны —
план ничего не пишет, и это **доказывается**, а не обещается.


## §3 Шаги

1. **Лист.** В `docs/porting/editing.split_gd.md` добавь раздел «C.15 — вторая половина
   (`split_gd_plan`)»: таблица старого кода (`suggest_groups:557`, `_engine_api:583`,
   `_apply_edits:624`, `_rewrite_body:640`, `_downgrade_panel_inference:714`,
   `_render_static_sig:765`, `_render_wrapper:780`, `_normalize_groups:898`, `_render_module:932`,
   `plan_split:955`, `_public_plan:1138`), старые тесты (`test_split_gd_flow.py` 5 931 B,
   `test_split_gd.py` 29 322 B, `agent_bridge.py` 2076–2130 — читаем, в корпус берём через
   пересъёмку). Первым делом **сними sha256 принятых файлов модуля, корпуса и карточки** —
   база обратной проекции. Статус листа: «этап 7 (половина 1 принята); C.15 в работе».
2. **Корпус до кода.** Скрипт в `%TEMP%` (не в аддоне): копия фикстуры-аддона во временный
   проект, живой вызов `split_gd.plan_split(<addon>, <rel>, groups=…, target_lines=…)` +
   `split_gd._public_plan(...)`; `reference_result` — сырой ответ эталона (с `content`),
   `expect.result` — проекция §2.1/§2.2. Кейсы **≥22**, номера с 101: авто-группы; явные
   группы (2–3 модуля); модуль из одной функции; `target_lines` `0`/не передан (→1100),
   `100`, `5000`, `99`, `5001` (отказы); донор без функций; виртуальные движковые методы
   (`_ready`, `_process`); приватные; статические; `await`; многострочные сигнатуры и дефолты
   (`_parse_params`); аннотации `@export`; лямбды в `_collect_locals`; параметр `panel`
   и `_downgrade_panel_inference`; предупреждения `_LINE_WARN` (>1500) и `_LINE_MAX` (>2000);
   пустой кэш API → `_FALLBACK_*`; кэш с классами → методы движка; `groups` с несуществующей
   функцией; `groups` с пустым `funcs`; `path` не `.gd`; нет `plugin.cfg`; `res://addons/...`
   → `denied`; нет файла → `not_found`; > 4 MiB; BOM/CRLF донора; идемпотентность + sha дерева
   до/после. Фикстуры — `fixtures/projects/corpus/editing/split_gd_plan/<вариант>/`
   (`plugin.cfg` в корне варианта; кэш при нужде — `.agent_history/godot_api_cache.json`).
   `fixture` в кейсе — **относительно `fixtures/projects`**; manifest по образцу корпуса C.14
   (`reference{file,function,sha256,bytes}`, `fixture_base`, `cases`, `inputs`, `contract_refusals`).
3. **Красные тесты до кода.** `tests/test_tokens.py`, `test_collect.py`, `test_engine.py`,
   `test_render.py`, `test_core.py`, `test_app.py` (фейковые `fs`+`api_cache`, отказы до IO,
   лимит 4 MiB, `groups`/`target_lines`), `tests/py/integration/test_split_gd_plan.py`
   (корпус, sha дерева, идемпотентность, отказ без абсолютных путей),
   `tests/py/contract/test_split_gd_plan_contract.py` (карточка, `effects`, `errors`, `TOOLS`).
4. **Код** в порядке `tokens` → `collect` → `engine` → `render` → `core` → `app` → `tools`/`module`.
5. **Контракт.** `python -B tools/gen_contract.py --write` → новый **только**
   `split_gd_plan.json`; остальные 22 карточки байт-в-байт; `--check` → **23**.
6. **Четыре разрешённые правки** (§1) — только после того, как инструмент отвечает.
7. **Двойной прогон.** non-live (3164 + новые); `snapshot_diff` (669 + новые кейсы,
   строка `editing/split_gd` = 47 + N); `selfcheck editing.split_gd` (юниты вырастут,
   **scan-корпус 47/47 остаётся**); соседи `check` 188/75, `api_check` 206/52, `gd_lint` 126/37,
   `tscn_lint` 315/65, `class_api` 186/26 — не двигаются; `lint_arch`, `check_limits`,
   `security_audit`; live = **3**.
8. **Записи.** Лист (этап 7 + C.15 с доказательствами), `parity.md`, `tests-map.md`,
   `PROGRESS.md` (строка остаётся 7, добавляется пометка C.15), `WORKLOG.md` — **append в `ab`,
   без нормализации EOL**: исторический префикс 4479 CRLF обязателен. «Принято/ported»
   и этап 7 **не писать** — это аудитор.


## §4 Решения, которые уже приняты (не пересматривать)

1. Кэш API читается **только** через порт `api_cache.snapshot()` (ADR-0009); `history`,
   `addon_dir`, `agent_api_cache` эталона **не переносятся**; бандл-фолбэк в порте недостижим —
   это норма, «чинить» не надо.
2. `_FALLBACK_METHODS`/`_FALLBACK_PROPS` — **данные**, переносятся списками дословно и
   включаются только при пустых классах, как в эталоне.
3. `content` модулей не публикуется: план — метаданные. Запись — C.16 через принятую воронку
   `write_preview` (`action split_gd`).
4. `target_lines` валидируется на входе (`0` → 1100, вне `100..5000` → `invalid_input`):
   эталон сам его не проверяет, проверяет мост (`_split_gd_target_lines:1022`).
5. `groups` не переданы → авто-группы `suggest_groups`; ответ всегда содержит **применённые**
   группы (`_normalize_groups`).
6. Предупреждения — дословные строки в порядке эталона, без переформатирования;
   `_ENGINE_VIRTUAL` и `_downgrade_panel_inference` переносятся как есть.
7. План **ничего не пишет** и Godot не запускает: `apply_prepared_split`/`_godot_check` — C.16.

## §5 Доказательства

| # | Мутация | Что должно покраснеть |
|---|---|---|
| M1 | снять фильтр `_ENGINE_VIRTUAL` | кейс с `_ready` |
| M2 | не подставлять `_DEFAULT_TARGET_LINES` при `target_lines=0` | кейс 0 |
| M3 | не использовать `_FALLBACK_*` при пустом кэше | кейс пустого кэша |
| M4 | реверс порядка `modules` | многомодульный кейс |
| M5 | пересобрать `warnings` «красиво» | кейс `_LINE_WARN` |
| M6 | `_collect_locals` без лямбд | кейс лямбд |
| M7 | пропустить `_downgrade_panel_inference` | кейс `panel` |
| M8 | `lines_after` = `lines_before` | любой план |

Каждая — свой прогон, байтовый бэкап, sha до/после. Подложки: **P1** убрать `'wrappers'`
из `RESULT.required` → ловит только `gen_contract --check` (`fail: split_gd_plan.json`);
**P2** `import os` в `domain/render.py` → `lint_arch` «domain/ запрещает IO-модуль os»;
**P3** `app.py` импортирует `python.modules.verification.shared.source_text` → `lint_arch`.

Обратная проекция: список добавленных/изменённых файлов с `bytes` + `sha256`; доказательство,
что принятые файлы C.14, 22 карточки, замороженные гейты, `kernel/*`, `substrate/*`,
`editor/` и `verification/*` **не изменились**. Гигиена: дерево 2529 + новые, `.gd.uid` 83,
без `__pycache__`/`.pytest_cache`/`.bak|tmp|orig`/`zz_*`, временных скриптов в аддоне нет.

## §6 Стоп-условия

* проекция требует править принятый `split_gd_scan`, его корпус 47 кейсов или карточку;
* нужен новый порт, новый метод `fs`/`api_cache` или правка `PathPolicy`/`bootstrap`;
* нужен запуск Godot или запись на диск (это C.16);
* без правки замороженных гейтов или `tools/selfcheck.py` (долг F4) срез не закрывается;
* числа соседей сдвинулись (`split_gd` scan 47/47, `check` 188/75, `api_check` 206/52,
  `gd_lint` 126/37, `tscn_lint` 315/65, `class_api` 186/26);
* тянет «доработать» эталон (виртуальные методы, предупреждения, порядок) — паритет выше.

## §7 Что будет проверять аудитор

Своя пересъёмка корпуса (живые `plan_split` + `_public_plan`, сброс `gd_api_cache._cache`
на каждый кейс), своя независимая проекция, порт против `expect`; дифференциал по всем
`.gd`-донорам фикстур (включая донора длиннее `target_lines`) с авто-группами и явными
группами в двух режимах кэша; свои мутации M1–M8 и подложки P1–P3 с байтовым
восстановлением; инвентарь (`gen_contract --check` = 23, 24 файла в `contract/capabilities`,
`gather` = 22 имени с `split_gd_plan: read`, `# verb:` 6, `verbs_version: 3`);
принятые механики — те же числа selfcheck и те же `domain/`-хэши, `snapshot_diff` 669 + новые;
гигиена и live = 3.

## §8 Финальный прогон и записи

Один отчёт в листе + `WORKLOG`: non-live (кол-во, время, файлы-сбора), `snapshot_diff`
(число и новая строка корпуса), `selfcheck editing.split_gd` (таблица) +
`reports/selfcheck/editing.split_gd.json`, `gen_contract --check` = 23, `lint_arch`,
`check_limits`, `security_audit`, live = 3, дерево/`.gd.uid`/debris, таблица мутаций
с sha256 и обратная проекция. Записать: лист (этап 7 + C.15), `parity.md`, `tests-map.md`,
`PROGRESS.md`, `WORKLOG.md`, четыре разрешённые правки (§1). **Не писать**:
`_audit-handoff.md`, «принято/ported», этап 7, `contract/editor_verbs.json`,
`kernel/schema.py`, `tools/{lint_arch,gen_contract,security_audit,snapshot_diff,selfcheck}.py`.

Сдавать словами: «C.15 готов к независимому аудиту, не принято», со списком sha256
изменённых файлов и остатком границы: подключение плана к воронке записи
(`write_preview` с `action split_gd`) — C.16.

## §9 Уточнения аудитора (сессия 68, 2026-10-31) — B1 разрешён, B2 разрешён узко, B3 подтверждён

Остановка на preflight была правильной: B1 и B2 действительно упираются в контракт.

**B1 разрешён узко** — ровно как в C.14, потому что `gather` получает 22-е имя, а покрытие
`script_facts` требует «каждый текущий `.gd`»:
* в `fixtures/corpus/context/gather/manifest.json` меняется **только** `sha256` кейса
  `001-all-sections` (следствие 21→22 имён); список кейсов, `fixture_root`, `reference`,
  `captured_at` и порядок — без изменений;
* в `fixtures/corpus/scene_model/scene_deps/manifest.json` **дописываются** факты только новых
  `.gd` C.15 (`path`, `bytes`, `sha256`, `handlers`, `custom_signals`, `connected`); прежние
  198 записей — побайтово те же и в том же порядке;
* `tests/py/formats/test_scene_deps_facts.py` не правится; EOL файлов сохраняется.

**B2 разрешён узко — один metadata-метод `exists`.** Мой разбор эталона:
`plan_split` на `split_gd.py:1001` делает `os.path.exists(os.path.join(addon_dir, module_rel))`
и бросает `StaleSplitGdError("целевой модуль уже существует: %s")`; `os.path.exists` истинно
и для **каталога**, а `fs.is_file` (`substrate/fs/disk_fs.py`, 3628 B `8D2EEC86BC9C`) видит
только обычный файл — значит план предлагался бы там, где эталон отказывает. Это разрыв
паритета, а не удобство, поэтому шов разрешается, но только такой:

1. В `python/substrate/fs/disk_fs.py` **добавляется** `exists(rel_path: str) -> bool`:
   `return self._resolve(rel_path).exists()` — только метаданные, без чтения, без записи,
   без `mkdir`. Docstring обязан сказать: «истинно для файла **и** каталога; `is_file`
   остаётся строго про обычный файл».
2. В `python/modules/editing/split_gd/ports.py` `exists` добавляется в `Protocol FileSystem`
   рядом с `is_file` (порт потребителя, как `is_file`).
3. Использование — **одно**: проверка `module_rel` в проекции `plan_split`. Существующий
   **файл или каталог** → `AppError('invalid_input', 'целевой модуль уже существует: <rel>')`
   дословно по эталону; отсутствует → план считается как раньше.
4. **Запрещено:** менять `is_file`/`list_files`/`read_text`/`read_raw`; заводить `is_dir`,
   `stat`, `mkdir`, `glob`, `walk`; вызывать `exists` где-либо ещё (в конце среза —
   `grep` по `python/modules`: ровно один вызов); трогать `PathPolicy` и `bootstrap`.
5. **ADR-0011** «`fs.exists` — узкий metadata-шов для `split_gd`» (как ADR-0009 для
   `snapshot()`): контекст (разрыв `os.path.exists` vs `is_file`), решение (один булев
   метаданный метод, один вызов), последствия (никаких новых режимов ФС, `is_file` прежний).
6. **Красные доказательства до кода:** тест субстрата (реальный каталог с именем `module.gd`
   → `exists` истинно, `is_file` ложно); мутация «`exists` делегирует в `is_file`» →
   кейс существующего каталога обязан покраснеть (это и есть исходный дефект); корпусные
   кейсы `1xx-existing_module_file` и `1xx-existing_module_dir` (отказ, `invalid_input`,
   текст дословный).
7. После правки — новый `sha256` `disk_fs.py` в лист и WORKLOG; старый хэш `8D2EEC86BC9C`
   остаётся в §0 как точка «до».

**B3 подтверждён:** `app.call` возвращает payload и поднимает `AppError`, единый `Result`
строит `Agent.call` (`python/runtime/bootstrap.py:66-71`); runtime, protocol, kernel не меняются,
`ToolSpec.errors` остаётся `('invalid_input','not_found','denied')`.

**Порядок после снятия блокеров:** шов `exists` (подложка + ADR-0011 + красный тест) → корпус
(≥22 кейса от 101, плюс два новых про существующий модуль) → red-тесты → код
`tokens → collect → engine → render → core → app` → `gen_contract --write` = 23 → двойной
прогон → записи. `WORKLOG` — только append в `ab`, без нормализации EOL.

