# C.14 — `editing.split_gd`, половина 1: инструмент `split_gd_scan` (карта ссылок на `.gd` агента)

Ты — **портер**. Аудитор ведёт записи и приёмку, ты пишешь код и доказательства.
Этап сам себе **не ставишь**, шапку «выполнено/принято/ported» **не пишешь**,
`docs/porting/_audit-handoff.md` **не правишь**. Приёмка — своими прогонами
(`231 failed` в прошлом срезе не пугает: red-фаза по замыслу, но приёмки нет, пока
не объявишь готовность).

## Читать до первой строки кода

1. `AGENTS.md`, `RULES.md` (R-01…R-22, особенно R-02, R-05, R-09, R-11, R-12, R-13).
2. `docs/architecture.md`, `docs/PORTING.md`.
3. `docs/parity.md` — строка `split_gd_scan/plan` → `editing.split_gd` (skeleton) и
   §про вклады; `docs/PROGRESS.md` — строка `editing.split_gd` (этап 0) и соседи.
4. `docs/tests-map.md` — судьба старых тестов (там же ищи `split_gd`).
5. `docs/porting/_template.md` — структура листа.
6. Листы соседей: `editing.symbol_rename.md`, `verification.tscn_lint.md`,
   `verification.check.md` (C.13), `engine_kb.class_api.md`.
7. `docs/WORKLOG.md` — последние три сессии (58–65).
8. `docs/security/invariants.md`, ADR-0004, 0006, 0009, 0010.

## §0 База (снято аудитом, сессия 65, 2026-10-31 — не пересчитывать)

* `pytest python/modules tests/py --ignore=tests/py/live` → **2874 passed**, файлов-сбора **99**, 74.5 с, stderr пуст.
* Живое `tests/py/live` → **3 passed**, 29.4 с (Godot `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`).
* `tools/snapshot_diff.py` → **622/0**; `tools/gen_contract.py --check` → **21** артефакт (22 файла с `_template.json`).
* `selfcheck`: `verification.check` 188/75, `verification.api_check` 206/52, `verification.gd_lint` 126/37,
  `verification.tscn_lint` 315/65, `engine_kb.class_api` 186/26 (186 — это долг F4: селектор
  `tools/selfcheck.py:215` берёт `test_api_check.py`; не «исправляй» его в этом срезе).
* Слои/лимиты **502/0**, security ok. Дерево: **2333** файла, `.gd.uid` **83**, debris 0;
  листов 23, промптов 32, ADR 10, правил 22; `PROGRESS` 44 строки (21 на этапе 7 / 1 на 6 / 22 на нуле).
* Мост: 6 примитивов, `contract/editor_verbs.json` `verbs_version: 3`, sha `CDAF8D23A6BF…`.
* Замороженные: `kernel/schema.py` 147 строк `629FCE54E6FE`, `tools/gen_contract.py` `FA7E6E91C872`,
  `tools/security_audit.py` `2CF0D7F6B1AF`, `tools/snapshot_diff.py`, `editor/bridge/verbs/scene/scene_executor.gd`
  `B7AFF592B75D`; гейт `tools/lint_arch.py` уже изменён по ADR-0010 — **9842 B `A6C5EDD47650`**, менять нельзя.
* Принятые артефакты (сверять, не помнить): `formats/tscn.py` `9D69AFECDCC0`; `verification/check/{domain/core
  F84018B8EE08 → после C.13 CFD441D147C3, app F1506108E191, tools 65974F15AA55}`; `verification/shared/source_text.py`
  `56C397CFC171`; `verification/api_check/{domain/core 16647249D952, app 45AD39186919, tools 3A78CF6F2989}`;
  `engine_kb/shared/inheritance.py` `5A9BAD5013FB`; `engine_kb/class_api/{domain/core 888BCB485E52, tools 5FFFE966F159}`;
  карточки `check.json 580B1D18974A`, `verify.json 58C34188D6FD`, `api_check.json 118D81D1736D`.
* Цели среза: **+1 инструмент** → карточек **22** (23 файла), `context.gather` **20 → 21** имя,
  листов 23 → 24, промптов 32 → 33; строка `editing.split_gd` в `PROGRESS` — 0 → 1 (этап 7 ставит аудитор).
* Эталон среза: `python/godot_tools/split_gd.py` — **63 421 B, 1333 LF, 0 CRLF, sha256 `18F05D10B8E8…`**
  (полный хеш снимешь сам и запишешь в manifest; эталон — старый плагин
  `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent`). Второй адрес:
  `python/tools/agent_bridge.py` (`142 171 B`, `a9b1ad832fd0…`) — `cmd_split_gd:1035`, `_split_gd_target_lines:1022`;
  MCP-обёртка `python/tools/godot_agent_mcp.py:464`, маршрут `python/main.py:4349`.
* Git в `agent-rebuild` намеренно **нет**; единственный git — старый плагин (две чужие untracked-строки не удалять).
* Среда: PowerShell 5.1, лимит команды ~30 с (длинное — в фон через `Start-Process`, junit — только
  через python-драйвер `subprocess`), stderr в файл, `python -B -X utf8`, логи писать **изнутри** Python
  (перенаправление PowerShell ломает UTF-8), JSON — через файл, **одна мутация за раз**,
  `.gd`-подложка убирается вместе с `.gd.uid` (живой прогон создаёт UID в корпусах: удалять ровно
  сгенерированные, 8 исторических от 2026-10-27 не трогать).

## §1 Границы среза

Срез — **первая половина** механики `editing.split_gd`: только **чтение**. Инструмент
`split_gd_scan` отвечает на вопрос «кто и как ссылается на этот `.gd` агента и что поедет при разбиении».
Вторая половина (`split_gd_plan`: `plan_split`, `suggest_groups`, рендер модулей и обёрток,
`_engine_api` с таблицами `_FALLBACK_*`) — **отдельный срез C.15**, здесь её нет.

Почему так: `scan_refs` (эталон `:794-881`) опирается только на `file_inventory` (`:454-557`) и обход
дерева, а `plan_split` (`:955-1138`) тянет токенизатор, рендер, движковые таблицы и `apply`-путь
(`apply_prepared_split:1177` пишет файлы и гоняет Godot) — это второй полноценный срез со своим корпусом.
Дробить механику на два инструмента законно: `ModuleSpec` может объявлять несколько `provides_tools`
(пример — `usages` + `analyze_rename`), карточка появится одна — на `split_gd_scan`.

**В срезе:**
* папка `python/modules/editing/split_gd/` (заглушки уже стоят: `module.py`, `tools.py`, `app.py`,
  `domain/core.py` с TODO — заполняешь на месте; комментарий `# tools: split_gd_scan, split_gd_plan`
  оставь правдой, второй инструмент придёт в C.15);
* корпус `fixtures/corpus/editing/split_gd/` + фикстуры `fixtures/projects/corpus/editing/split_gd/<вариант>/`;
* лист `docs/porting/editing.split_gd.md` (создать **первым**, этап 1);
* записи: `docs/parity.md` (строка `split_gd_scan/plan`), `docs/PROGRESS.md` (строка `editing.split_gd`),
  `docs/WORKLOG.md`, `docs/tests-map.md`.

**Вне среза:** `plan_split`/`suggest_groups`/`_render_*`/`_rewrite_body`/`_downgrade_panel_inference`/
`_engine_api`/`_FALLBACK_*`/`tokenize`/`_collect_locals` (C.15); `_code_skeleton` — **в срезе**: это зависимость `_balance:432-439` и `file_inventory`, разрешено §9 (B2); `apply_prepared_split`,
`_godot_check`, funnel `write_preview/apply/rollback` (там уже принятые механики); `_make_split_gd_prepared`
моста (пишущий путь моста — не портируется); `editing.split_py`, `editing.file_refactor`,
`editing.paths_preview`; `verification.*`, `engine_kb.*`; `contract/editor_verbs.json`; `tools/gen_contract.py`,
`kernel/schema.py`, `tools/lint_arch.py`, `tools/security_audit.py`, `tools/snapshot_diff.py`,
`tools/selfcheck.py` (долг F4 — отдельный срез); `_audit-handoff.md`.

**Разрешённые правки вне новой папки — ровно четыре:**

1. `fixtures/corpus/context/gather/001-all-sections.json` — добавить имя инструмента `split_gd_scan`
   с эффектом `"read"`, `count` 20 → 21 (список имён — по фактическому `registry`).
2. `tests/py/integration/test_tscn_lint.py` — пин инвентаря инструментов (20 → 21 имя).
3. Тесты, которые пинят «21 карточка» / `len(names())` — меняется **только** это число/список.
4. `docs/parity.md` — строка `split_gd_scan/plan` (статус этапа), и всё.

Всё остальное — байт-в-байт. Список правок дублируй в листе и в `WORKLOG` (аудитор делает
обратную проекцию по sha256 и такие правки ищет первым делом).

## §2 Контракт и раскладка

### 2.1 ToolSpec — дословно

```python
# python/modules/editing/split_gd/tools.py
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec

KINDS = ['path', 'source_read', 'call', 'doc', 'mention']

ARGS = {
    'type': 'object',
    'required': ['path'],
    'additionalProperties': False,
    'properties': {
        'path': {'type': 'string', 'minLength': 1},
    },
}

COUNTS = {
    'type': 'object',
    'required': ['path', 'source_read', 'call', 'doc', 'mention'],
    'additionalProperties': False,
    'properties': {name: {'type': 'integer'} for name in KINDS},
}

OCCURRENCE = {
    'type': 'object',
    'required': ['file', 'line', 'kind', 'text'],
    'additionalProperties': False,
    'properties': {
        'file': {'type': 'string', 'minLength': 1},
        'line': {'type': 'integer'},
        'kind': {'type': 'string', 'enum': KINDS},
        'text': {'type': 'string'},
    },
}

RESULT = {
    'type': 'object',
    'required': ['donor', 'lines', 'extends', 'class_name', 'funcs', 'consts',
                 'vars', 'public_methods', 'counts', 'occurrences',
                 'truncated', 'hard_files', 'soft_files'],
    'additionalProperties': False,
    'properties': {
        'donor': {'type': 'string', 'minLength': 1},
        'lines': {'type': 'integer'},
        'extends': {'type': 'string'},
        'class_name': {'type': 'string'},
        'funcs': {'type': 'integer'},
        'consts': {'type': 'integer'},
        'vars': {'type': 'integer'},
        'public_methods': {'type': 'array', 'items': {'type': 'string'}},
        'counts': COUNTS,
        'occurrences': {'type': 'array', 'items': OCCURRENCE},
        'truncated': {'type': 'boolean'},
        'hard_files': {'type': 'array', 'items': {'type': 'string'}},
        'soft_files': {'type': 'array', 'items': {'type': 'string'}},
    },
}

SCAN = ToolSpec(
    name='split_gd_scan',
    description='Карта ссылок на .gd агента: кто им пользуется и что поедет при разбиении. Только чтение.',
    args=ARGS,
    result=RESULT,
    effects='read',
    idempotent=True,
    errors=('invalid_input', 'not_found', 'denied'),
    availability='*',
    cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES},
)

TOOLS = (SCAN,)
```

Поля — **дословный** перенос payload эталона (`split_gd.scan_refs`, `:868-881`), кроме
`schema` (внутренний маркер версии формата эталона — в контракт порта не выходит; в листе
записать как решение, `reference_result` в корпусе остаётся сырым). `donor` — относительный
путь донора внутри аддона в виде `a/b.gd` (как `_norm(rel_path)`), `lines`/`funcs`/`consts`/`vars`
— **числа** (в эталоне это длины списков), `public_methods` — имена без префикса `_`, отсортированы,
`counts` — счётчики по категориям, `occurrences` — до **1000** записей, `text` — `line.strip()[:160]`,
`hard_files` — файлы с признаком чтения исходника, `soft_files` — остальные файлы с попаданиями.

### 2.2 Где что живёт (R-02, R-11, лимит 400 строк на файл)

```
python/modules/editing/split_gd/
  module.py            ModuleSpec(id='editing.split_gd', version='0.1.0', kernel_api='^1',
                       godot='^4.6', environment='*', provides_tools=('split_gd_scan',),
                       requires_ports=('fs',), capabilities=('editing.split_gd',),
                       entrypoints={'call': call}, corpus='corpus')
  tools.py             ToolSpec (см. §2.1) + TOOLS = (SCAN,)
  app.py               оркестрация ≤ 80 строк: validate → policy → аддон-корень → обход →
                       чтение → core.assemble; никакой логики разбора
  domain/text.py       чистый: decode(raw) (incremental 'utf-8-sig', errors='replace', final=True),
                       indent_width, leading_comment_start, balance, newline_of
  domain/inventory.py  file_inventory(text) (дословный перенос :454-557) + parse_params (:280-335)
  domain/refs.py       сбор ссылок: skip-каталоги/расширения, 1 MiB на файл, 1000 попаданий,
                       категории (порядок ветвей как в эталоне)
  domain/core.py       assemble(donor, rel, inventory, refs) → payload RESULT; больше ничего
  ports.py             Protocol FileSystem: is_file(rel), read_raw(rel), list_files()
  tests/               test_core.py, test_inventory.py, test_refs.py, test_app.py, corpus.py
```

Правила: `domain/` — без `os`, `pathlib`, `socket`, `subprocess` (R-11; `re`, `codecs` можно —
так уже живёт `verification/gd_lint/domain/core.py`); IO только в `app.py` через `ctx.port('fs')`;
`tools.py` ≤ 150 строк, новый файл ≤ 400 строк (`kernel/limits.FILE_MAX_LINES`), папка ≤ 3000.
**Не тянуть** `verification/shared/source_text.py` — это чужой `shared` (R-11, ср. ADR-0010:
единственный разрешённый межобластной шов — `api_check → engine_kb.shared.inheritance`, второй шов
без ADR запрещён). Декодер пишется свой, 6 строк, поведение F1 (C.10) — то же: ровно один ведущий BOM.

### 2.3 Аддон-корень и доступ (решение среза)

Эталон работает по `addon_dir`: `cmd_split_gd` берёт его из `policy["addon_dir"]` и требует
`--access agent-dev` (`allow_self_edit`), а `_split_target` отказывает всему, что не `.gd` и не
внутри аддона. Порт не заводит нового режима доступа, но и не тащит `addon_dir` из моста:

* `path` обязан быть `res://…` и заканчиваться `.gd` (иначе `invalid_input`);
* **аддон-корень** = ближайший предок донора (включая сам файл как базу), в каталоге которого есть
  `plugin.cfg`; если такого нет — `invalid_input` («доннор не внутри аддона: нет `plugin.cfg`»);
* обход и чтение — только внутри аддон-корня (префикс `addon_root + '/'`), сам донор из скана исключён;
* каждый файл проверяется `ctx.path_policy.deny_reason(rel)`: отказ политики → файл **молча пропускается**
  (он не «ссылка», а недоступный источник); донор при отказе → ошибка `denied` с текстом политики;
* аддон, лежащий в `addons/`, читается только при `allow_self_edit`/`allow_addons` — это и есть паритет
  с `--access agent-dev`, отдельной проверки прав в модуле нет.

Такое правило даёт корпус без правок продакшена: фикстура-«аддон» = каталог проекта с `plugin.cfg`
в корне, поэтому `snapshot_diff` (он поднимает `build_agent(project_root=fixture, profile='headless')`)
видит её как обычные файлы проекта. Случаи с `res://addons/...` остаются кейсами отказа `denied` —
как уже принято в шести других корпусах.

### 2.4 Проекция «эталон → порт»

| Эталон (`split_gd.scan_refs`, `:794-881`) | Порт (`split_gd_scan`) |
|---|---|
| `addon_dir` из `policy["addon_dir"]` | аддон-корень по `plugin.cfg` (§2.3) |
| `SplitGdError("донор не найден: %s")` | `not_found` (текст ядра, путь относительный) |
| обход `_files_of(addon_dir)` | `fs.list_files()` + фильтр по префиксу аддон-корня |
| `_SCAN_SKIP_DIRS` / `_SCAN_EXTS` | тот же набор, дословно |
| `> _MAX_SCAN_FILE_BYTES` (1 MiB) → `continue` | тот же пропуск |
| `_read_text` = `utf-8-sig`, `errors="replace"` | свой `decode` (incremental, `final=True`) |
| ранний отсев файла (`file_name`/`stem`/`call_re`) | дословно (важно для скорости) |
| порядок ветвей: `.md` → `source_read` → `call` → `path` → `mention` | дословно |
| `_MAX_OCCURRENCES` = 1000, дальше `truncated = True` | дословно |
| `hard_files` = файлы с `source_read`; `soft_files` = прочие | дословно, оба отсортированы |
| `"schema": SCHEMA` | не публикуется (см. §2.1) |
| `apply_prepared_split`, `_godot_check` | вне среза (C.15 / funnel) |

**Категория `mention` в эталоне недостижима:** `relevant` требует `has_name` или `call_re`, а ветвь
`call` ловит все случаи `call_re`, поэтому до `mention` управление не доходит — `counts["mention"]`
всегда `0`. Паритет важнее правки: ветвь сохраняется байт-в-байт, и в корпусе есть кейс, который это
**пинит** (строка-«попадание», которая иначе стала бы `mention`). Находку записать в лист и в `WORKLOG`.

### 2.5 Вход и ошибки

* `path` — не строка / пустая / не `res://…` / не `.gd` → `invalid_input` (человеческий текст,
  без абсолютных путей в ответе; ядро `AppError`);
* `normalize_rel` вернул `None` (путь вне проекта, `..`, `\0`) → `denied`;
* `ctx.path_policy.deny_reason(rel)` непустой (в т.ч. `addons/` без `allow_addons`,
  исходники агента без `allow_self_edit`) → `denied` с текстом политики;
* донора нет → `not_found`; аддон-корня нет (`plugin.cfg` не найден до корня проекта) → `invalid_input`;
* донор больше `READ_TEXT_MAX_BYTES` (4 MiB, на **сырых** байтах) → `invalid_input`;
* `PermissionError → denied`, `EFBIG → invalid_input`, остальные `OSError → internal`
  (как в `verification/*/app.py`);
* `app.call` возвращает **payload** и поднимает `AppError`; единый `Result` собирает
  `Agent.call` (`python/runtime/bootstrap.py:66-71`), классификацию — `Dispatcher`;
  `domain/` — чистые функции; `Result` внутри модуля не строить (§9, B3);
* вызов идемпотентен: два подряд одинаковых вызова дают одинаковый ответ и не меняют дерево
  (`sha256` всех файлов корня до/после — доказательство «только чтение»).

### 2.6 Якоря эталона (строки — для сверки, не для чтения вслух)

```
57  SCHEMA = 1                        1022 bridge: _split_gd_target_lines (scan не нужен)
58  _DEFAULT_TARGET_LINES = 1100      1035 bridge: cmd_split_gd  ← scan + plan, только чтение
59  _LINE_WARN = 1500                 2041 bridge: _make_split_gd_prepared ← пишущий путь, вне среза
60  _LINE_MAX = 2000                  464  mcp: split_gd_scan(file) → call(["split_gd","scan",file])
64  _SCAN_SKIP_DIRS = {__pycache__, .git, .godot, .import, .agent_history, dist, build,
                      minilich_brain, parser_corpus, agent_api_cache, node_modules, .venv, _tmp}
69  _SCAN_EXTS = {.gd, .tscn, .tres, .godot, .md, .json, .py, .cfg, .txt, .bat, .cmd}
72  _MAX_SCAN_FILE_BYTES = 1024 * 1024  73  _MAX_OCCURRENCES = 1000
75  _FUNC_RE  ^(?:static\s+)?func\s+([A-Za-z_]\w*)\s*\(
127 _norm      131 _read_text (utf-8-sig)     156 _files_of (обход, skip-каталоги, sorted)
280 _parse_params  396 _indent_width  442 _leading_comment_start  432 _balance
454 file_inventory  ← нужен целиком (extends/class_name/consts/vars/funcs/errors/lines)
794 scan_refs      ← предмет среза     955 plan_split  ← C.15
1177 apply_prepared_split  ← вне среза (пишет + Godot --check-only)
```

Старые тесты (судьба — в `tests-map.md`): `tests/test_agent_bridge.py:2076-2130` — `scan` пишет ничего,
нужен `agent-dev`, отказ `.py` и чужому файлу, `plan` только читает; `tests/test_split_gd.py` (29 322 B)
и `tests/test_split_gd_flow.py` (5 931 B) — покрывают и scan, и plan; их кейсы идут в корпус
**пересъёмкой эталона**, а не переносом кода.

## §3 Шаги

**1. Лист первым.** `docs/porting/editing.split_gd.md` по `_template.md`, статус — «этап 1; старая
логика прочитана», таблица старого кода (`split_gd.py:57-119,127-178,280-335,396-442,454-557,794-881`),
таблица старых тестов, «вторая половина (`plan_split`) — C.15», `PROGRESS` 0 → 1.

**2. Корпус раньше кода.** Одноразовый скрипт **вне** аддона (`%TEMP%`), который для каждого кейса
копирует фикстуру-аддон в temp-проект и зовёт **живой** эталон
`split_gd.scan_refs(addon_dir=<temp>/…, rel_path=<донор>)`, результат кладёт сырым в `reference_result`.
Импорт: `sys.path` → старый `python/`, `python/godot_tools`, `python/parsers`, `python/tools`.
Фикстуры: `fixtures/projects/corpus/editing/split_gd/<вариант>/` — в корне `plugin.cfg`, внутри
`.gd`-донор и «соседи» со ссылками. Не тащить в корпус реальный аддон и ни одного
`agent_api_cache/*.json`.

Минимум **20 кейсов**, обязательное покрытие:
донор без ссылок; `path`-ссылка (имя файла в `.tscn`/`.json`/`.cfg`); `call` (`.panel.m()` из другого
`.gd`); строковая форма `"m"`; `doc` в `.md`; `source_read` (имя файла + `open(`/`read_text`/`get_script`);
приватный `_x` не попадает в `public_methods`; `extends`/`class_name` в payload; многострочный `const`
с балансом скобок; аннотации `@export` перед `var`; многострочная сигнатура `func`; `errors` из
`file_inventory` (незакрытая сигнатура) не ломает scan; skip-каталоги (`.godot`, `__pycache__`,
`node_modules`, `agent_api_cache`) не сканируются; файл > 1 MiB пропускается; 1000 попаданий →
`truncated: true` (фикстуру генерировать скриптом, но **класть** в корпус готовой); `mention` пинится
нулём; донор не `.gd`; донор без `plugin.cfg`; донора нет; `addons/…` → `denied`; не-`res://` →
`invalid_input`; BOM у донора и у соседа; CRLF у соседа (`text` без `\r`); идемпотентность.
`manifest.json` — по образцу `fixtures/corpus/verification/tscn_lint/manifest.json`
(`schema_version`, `captured_at`, `module`, `reference{file,function,sha256,bytes}`,
`capture_script{sha256,bytes}`, `fixture_base: fixtures/projects`, `cases`, `inputs` со sha256/bytes,
`contract_refusals` с объяснением, что отказы — новый контракт; `reference_result` сохранён отдельно).
`fixture` пишется **относительно** `fixtures/projects` (иначе `snapshot_diff` не найдёт фикстуру).

**3. Красные тесты до кода.** `tests/test_core.py` (сборка payload), `test_inventory.py`
(`file_inventory`/`parse_params` на образцах), `test_refs.py` (категории, лимиты, порядок),
`test_app.py` (фейковый порт `fs` с `is_file`/`read_raw`/`list_files`, политика: `invalid_input`/
`denied`/`not_found` до любого чтения, лимит 4 MiB), `tests/py/integration/test_split_gd_scan.py`
(корпус через `build_agent(project_root=fixture, profile='headless')`, хеши дерева до/после,
идемпотентность, `ok: False` без абсолютных путей), `tests/py/contract/test_split_gd_scan_contract.py`
(карточка, `effects == 'read'`, `errors`, `limits`). Сначала — красные, затем код.

**4. Код** в порядке `domain/text.py` → `domain/inventory.py` → `domain/refs.py` → `domain/core.py` →
`app.py` → `tools.py`/`module.py`.

**5. Контракт.** `python -B tools/gen_contract.py --write` — появляется **только**
`contract/capabilities/split_gd_scan.json`, остальные 21 карточка байт-в-байт; `--check` → **22**.

**6. Четыре разрешённые правки** (§1) — после того как инструмент отвечает; до этого не трогать.

**7. Двойной прогон.** non-live (2874 + новые), `snapshot_diff` (622 + новый корпус),
`selfcheck editing.split_gd` и соседи (`verification.check` 188/75, `api_check` 206/52,
`gd_lint` 126/37, `tscn_lint` 315/65, `engine_kb.class_api` 186/26 — числа не должны сдвинуться),
`tools/lint_arch.py`, `tools/check_limits.py`, `tools/security_audit.py`, живое — **3** (не больше).

**8. Записи.** Лист (этап 6 + доказательства), `parity.md`, `tests-map.md`, `PROGRESS` (строка
`editing.split_gd`: 6), `WORKLOG` (сессия). «Принято/ported» и этап 7 **не писать**.

## §4 Решения, которые уже приняты (не пересматривать)

1. **Срез = только `split_gd_scan`.** `split_gd_plan` — C.15. Механика одна, инструментов будет два;
   карточка одна — на `split_gd_scan` (как `usages` + `analyze_rename`).
2. **`schema` не публикуется.** Внутренний маркер формата эталона; остальные поля — дословно.
3. **`mention` сохраняется мёртвой ветвью.** Паритет; кейс корпуса это пинит. «Починить» — значит
   разойтись с эталоном и сломать будущий `plan`.
4. **Аддон-корень по `plugin.cfg`** (§2.3). Не тащить `addon_dir` из моста, не заводить порт
   `addon_dir`, не менять `PathPolicy` и не править `runtime/bootstrap.py`.
5. **Свой декодер** (incremental `utf-8-sig`, `final=True`), без импорта
   `verification/shared/source_text.py`: межобластной `shared` без ADR запрещён.
6. **Список файлов — `fs.list_files()`** (он уже есть в `substrate/fs/disk_fs.py`), фильтр по
   skip-каталогам и расширениям делает домен. Новых методов порта не заводить.
7. **Отказы политики на соседних файлах — молчаливый пропуск**, на доноре — ошибка `denied`.
8. **Лимит чтения 4 MiB** (`READ_TEXT_MAX_BYTES`), а не 1 MiB как «пропуск файла»: 1 MiB — это
   `_MAX_SCAN_FILE_BYTES` для соседей (паритет), 4 MiB — лимит адаптера для донора (контракт).
9. **Сортировки**: `occurrences` — в порядке обхода (`_files_of` сортирует каталоги и имена),
   `hard_files`/`soft_files`/`public_methods` — `sorted()`, как в эталоне.

## §5 Доказательства (предъявить в листе, с sha256 до/после)

Мутации (одна за раз, восстановление байт-в-байт, sha256 до/после в журнале):

| # | Мутация | Что обязано покраснеть |
|---|---|---|
| M1 | ветвь `.md` → `doc` убрана (`.md` падает в `path`) | кейс `doc` |
| M2 | ветвь `source_read` убрана | кейс `source_read` + `hard_files` |
| M3 | `len(occurrences) < _MAX_OCCURRENCES` → всегда добавлять | кейс `truncated` |
| M4 | донор не исключается из скана (`if rel == rel_path` убран) | кейс «донор без ссылок» |
| M5 | `public_methods` без фильтра `_` | кейс с `_private` |
| M6 | skip-каталоги игнорируются | кейс `.godot`/`node_modules` |
| M7 | `hard_files` = все файлы с попаданиями | кейс смешанных категорий |
| M8 | `soft_files` без `sorted()` (обратный порядок) | кейс с двумя файлами |

Подложки: **P1** — в `RESULT.required` убрать `'hard_files'` → юниты зелёные, красный **только**
`gen_contract --check` (`fail: split_gd_scan.json`); **P2** — `import os` в `domain/refs.py` →
`lint_arch` («domain/ запрещает IO-модуль os»); **P3** — `app.py` импортирует
`python.modules.verification.shared.source_text` → `lint_arch` (чужой `shared` без ADR).

Обратная проекция: список всех добавленных/изменённых файлов с `bytes` + `sha256` и явное
доказательство, что 21 прежняя карточка, `contract/editor_verbs.json`, `kernel/*`, `substrate/*`,
принятые `verification/*`, `engine_kb/*`, `scene_model/*`, `code_intel/*`, `editing/{scene_ops,
symbol_rename,write_*,rollback}` — байт-в-байт.

Гигиена: дерево = 2333 + новые, `.gd.uid` = 83, `__pycache__`/`.pytest_cache`/`.bak|.tmp|.orig`/`zz_*` = 0,
временных скриптов в аддоне нет (всё в `%TEMP%`), `reports/selfcheck/` содержит только отчёты механик.

## §6 Стоп-условия

* Паритет требует править `domain/` принятых механик, `kernel/*`, `substrate/*` или `PathPolicy`, —
  остановиться и описать в листе: это блокер, а не «небольшая правка».
* Понадобился ADR/новый порт/новый метод `fs` — остановиться и вынести пользователю.
* Проекция требует полей, которых нет в эталоне, или теряет поле эталона.
* Корпус нестабилен, кейсы требуют правки продакшна, или `snapshot_diff` не находит фикстуру.
* Сдвинулись числа соседей (`126/37`, `136/62`… `188/75`, `206/52`, `315/65`, `186/26`).
* Захотелось «улучшить» эталон (починить `mention`, добавить фильтры, имена, тексты).

## §7 Что будет проверять аудитор

1. Своя пересъёмка корпуса **своим** скриптом (живой `split_gd.scan_refs`), своя независимая
   проекция и сверка порта с `expect` — по всем кейсам.
2. Дифференциал шире корпуса: **каждый `.gd`-донор реального аддона порта** (72 файла `editor/*.gd`
   + корневой `plugin.gd`) — эталон и порт на одной копии аддона, сверка полей payload; плюс
   несколько доноров из `fixtures/**` внутри аддон-подобных каталогов.
3. Свои мутации M1–M8 и подложки P1–P3, восстановление по sha256.
4. Инвентарь: `gen_contract --check` = **22**, файлов в `contract/capabilities` = 23, `context.gather`
   = **21** имя с `split_gd_scan: read`, `# verb:` = 6, `verbs_version: 3`.
5. Принятые механики: те же `selfcheck`-числа и те же sha256 `domain/`; `snapshot_diff` = 622 + новый корпус.
6. Гигиена и живое (3 теста, `.gd.uid` 83, debris 0).

## §8 Финальный прогон и записи

Один отчёт в листе + `WORKLOG`: число non-live (и `collect`), `snapshot_diff` с новой строкой корпуса,
таблица `selfcheck editing.split_gd` (+ `reports/selfcheck/editing.split_gd.json`),
`gen_contract --check` = 22, `lint_arch`, `check_limits`, `security_audit`, живое = 3, дерево/`.gd.uid`/debris,
таблица мутаций с sha256 и обратная проекция.

Пишешь: лист (этап 6, «готово к независимому аудиту, не принято»), `docs/parity.md`, `docs/tests-map.md`,
`docs/PROGRESS.md`, `docs/WORKLOG.md`, четыре разрешённые правки. **Не пишешь**: `_audit-handoff.md`,
«принято/ported», этап 7, `contract/editor_verbs.json`, `kernel/schema.py`, `tools/lint_arch.py`,
`tools/gen_contract.py`, `tools/security_audit.py`, `tools/snapshot_diff.py`, `tools/selfcheck.py`.

Сдача: «C.14 половина 1 готова к независимому аудиту, не принято» + список изменённых файлов
с sha256 + что осталось за границей среза (C.15: `split_gd_plan`).

## §9 Уточнения аудитора (сессия 66, 2026-10-31) — блокеры B1–B3 сняты

Портер остановился на preflight и вынес три вопроса; решения ниже **обязательны**,
лист `docs/porting/editing.split_gd.md` держи их в «Решениях по ходу».

**B1 (companion-правки) — разрешено, ровно две и только append/точечно.**
Причина структурная, а не косметическая: `tests/py/formats/test_scene_deps_facts.py`
(`test_capture_covers_every_current_required_gd`) сравнивает **множество** `.gd` под
`editor/`, `fixtures/projects/`, `fixtures/corpus/scene_model/{connections,scene_deps}`
с `manifest.json::script_facts` — любой новый `.gd`-фикстур обязан получить там запись,
а `context/gather/manifest.json::cases[001-all-sections].sha256` обязан обновиться,
потому что кейс меняется (имён 20 → 21).
* Разрешено: (а) `sha256` записи `001-all-sections` в `fixtures/corpus/context/gather/manifest.json`;
  (б) **append** actual-old `script_facts` для **каждого** нового `.gd` фикстуры
  (`path`, `bytes`, `sha256`, `handlers`, `custom_signals`, `connected`) в
  `fixtures/corpus/scene_model/scene_deps/manifest.json`.
* Запрещено: править 140 прежних фактов, их порядок, `format_facts`/`snake_cases`/`scene_facts`,
  EOL; править сам тест `test_scene_deps_facts.py`; «догонять» дерево удалением чужих файлов.
* Порядок работ: сначала **фикстуры `.gd` заморожены**, потом снимаются манифесты
  (иначе хеши уедут), и только потом тесты/код.
* Дельту (до/после `sha256` каждого затронутого файла + число добавленных фактов)
  записать в лист и `WORKLOG`.

**B2 (`code_skeleton`) — не исключение, а исправление промпта.** Проверено:
`_balance:432` вызывает `_code_skeleton:400`, `file_inventory` вызывает `_balance`
(`:490`, `:516`). Токенизатора внутри нет — это стриппер строк/комментариев на ~30 строк.
Переносить дословно в `domain/text.py` как зависимость инвентаря, включая
`i += min(2, size - i)` для escape и сохранение `\n` на месте `#`-комментария.
`tokenize`/`_collect_locals`/`_rewrite_body`/рендер/`_engine_api` остаются C.15.

**B3 (контракт вызова) — портер прав, формулировка §2.5 была моя и неверная.**
`python/runtime/bootstrap.py:66-71`: `Agent.call` делает `result.ok(value)` и
`result.fail(exc)` на `AppError`. Значит: `app.call(tool, args, ctx)` → payload dict,
отказы — `AppError('invalid_input'|'not_found'|'denied'|'internal', …)`,
наружу единый `Result` собирает `Agent.call`. Runtime/protocol/kernel **не менять**;
`ToolSpec.errors` остаётся `('invalid_input','not_found','denied')` (как у `check`/`api_check`).

Дальше по плану: корпус (≥20 кейсов, сырой `reference_result` с `schema`), red-тесты,
код, `gen_contract --write` → 22, двойной прогон, записи. Сдача — «этап 6, не принято».
