# C.17 — `editing.split_py`, половина 1: инструмент `split_scan` (карта ссылок на `.py` агента)

Ты — портер. Твоя работа: перенести одну механику по образцу и доказать паритет. Ты **не** ставишь
себе этапы, не пишешь в шапке «выполнено/принято/ported», не правишь `docs/porting/_audit-handoff.md`
и не объявляешь приёмку — её делает аудитор своими прогонами. Сдаёшь словами
«C.17 готов к независимому аудиту, не принято».

Это **третья** «пила» в порте и вторая, которую мы делим на половины: `editing.split_gd` уже принят
(обе половины, этап 7), `editing.split_py` — этап 0, скелет лежит пустым. Срез C.17 — только
**чтение**: карта ссылок на `.py`-файл агента. План разбиения (`plan_split`, фасад, цикл импортов,
рендер) — отдельный срез **C.18**. Запись (`write_preview`/`write_apply`/`rollback` + проверка Godot) —
**C.19**, и она требует отдельного ADR (см. §10: сегодня воронка записи физически не умеет создавать
файлы и удалять их при откате).

## Читать до первой строки кода

1. `AGENTS.md` — роли и запреты.
2. `RULES.md` — R-01…R-22, особенно R-02 (раскладка областей), R-05 (MODULE обязателен), R-09 (границы
   модуля), R-11 (домен без IO), R-12 (домен не пишет), R-13 (политика путей), R-22 (документы).
3. `docs/architecture.md`, `docs/PORTING.md` — как устроены области и воронка.
4. `docs/parity.md` — строка `split_scan/plan` (`editing.split_py`, эталон `godot_tools/split_refactor.py`).
5. `docs/PROGRESS.md` — строка `editing.split_py` (сейчас 0) и строка `editing.split_gd` (7, принято).
6. `docs/tests-map.md` — судьба старых тестов (`test_split_refactor.py`).
7. `docs/porting/_template.md` — формат листа механики.
8. **`docs/porting/editing.split_gd.md`** — лист уже принятой родственной механики: читай целиком,
   включая разделы приёмок. Твоя механика — та же «пила», только по `.py`, и все решения C.14/C.15/C.16
   про аддон-корень, политику, лимиты и проекцию повторяются дословно.
9. **`docs/porting/_start-prompt.split_gd_scan.md`** — промпт половины 1 «пилы .gd». Структура твоего
   среза — его калька; отличие только в категориях отчёта (у `.py` есть `import` и `patch`, нет `path`
   и `call`).
10. `docs/adr/0004-*`, `0006-*`, `0009-*`, `0010-*`, `0011-*`, `0012-*` — контракт вкладов, TOOLS,
    свежий снапшот кэша, узкий шов импорта, `fs.exists`, каталоги в `security_audit`.
11. `docs/security/invariants.md` — запреты на запись/сеть/исполнение.
12. Хвост `docs/WORKLOG.md` — последние три сессии (69–71): как принимали C.15 и C.16.


## §0 База (снято аудитом, сессия 71, 2026-10-31 — не пересчитывать)

- `pytest python/modules tests/py --ignore=tests/py/live` → **3617 passed**, junit 3617/0/0/0, 89.4 s, stderr пуст; collect/XML совпадают, 102 файла.
- Живое: **3 passed, 0 skipped**, 24.1 s. Перед прогоном внешний `D:\vajno\Godot\agent-rebuild\project.godot`
  (335 B, sha256 `958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`) должен **временно** содержать
  `[editor_plugins]` с `enabled=PackedStringArray("res://addons/godot_agent/plugin.cfg")`, после прогона — восстановлен
  побайтово. Без этого плагин не поднимается и `port.json` не появляется: это предусловие среды, а не дефект порта.
  Godot: `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`.
- `tools/snapshot_diff.py` → **724/0** (`editing/split_gd` 102/102, `verification/check` 75/75, `gd_lint` 37/37, `tscn_lint` 65/65, `api_check` 52/52, `class_api` 26/26).
- `tools/gen_contract.py --check` → **23** артефакта (24 файла с `_template.json`).
- `selfcheck editing.split_gd` → module ok (`split_gd_scan`, `split_gd_plan`), layers ok **522**, limits ok **522/0**, contract ok 23, security ok, unit **625 passed**, corpus **102**, вердикт ok.
- Соседи (числа не должны сдвинуться): `verification.check` 188/75, `verification.api_check` 206/52, `verification.gd_lint` 126/37, `verification.tscn_lint` 315/65, `engine_kb.class_api` 186/26.
  Про 186: это долг **F4** (`tools/selfcheck.py:215` собирает юниты по `test_%s*.py`, из-за чего `class_api` видит и `test_api_check.py`). **F4 в этом срезе не чинить.**
- Дерево **2776** файлов (обход `python -B` без `__pycache__`/`.pytest_cache`/`.godot`), `.gd.uid` **83** (8 исторических из
  `fixtures/parity/gdscript/`, 2026-10-27 — не трогать), debris 0, листов 25, промптов **35 → 36**, ADR **12**, правил 22,
  PROGRESS 44 строки (23 на этапе 7 / 1 на этапе 6 `editing.symbol_rename` / 20 на нуле).
- Мост: 6 примитивов, `verbs_version: 3`, `contract/editor_verbs.json` `CDAF8D23A6BF…` — не менять.
- Замороженные гейты (байт-в-байт): `python/kernel/schema.py` (147 строк, CRLF) `629FCE54E6FE…`,
  `tools/gen_contract.py` `FA7E6E91C872…`, `tools/snapshot_diff.py`, `tools/selfcheck.py`,
  `tools/lint_arch.py` 9842 B `A6C5EDD47650…`, `tools/security_audit.py` 10885 B `77956BE3BE9F…` (после ADR-0012),
  `editor/bridge/verbs/scene/scene_executor.gd` `B7AFF592B75D…`.
- Принятые артефакты соседей (не менять): `python/formats/tscn.py` `9D69AFECDCC0…`; `verification/check/{domain/core.py CFD441D147C3…, app.py F1506108E191…, tools.py 65974F15AA55…}`;
  `verification/shared/{check_kind.py 07396A28C983…, source_text.py 56C397CFC171…}`; `verification/api_check/{domain/core.py 16647249D952…, tools.py 3A78CF6F2989…}`;
  `engine_kb/{shared/inheritance.py 5A9BAD5013FB…, class_api/domain/core.py 888BCB485E52…}`.
- `editing.split_gd` (принят, этап 7) — **не трогать**: `tools.py` 4926 `98C2A6B7714C…`, `app.py` 3525 `9B556F87F60F…`,
  `plan_io.py` 893 `77A96EB9A4D3…`, `domain/core.py` 9266 `673DF0B3F9A8…`, `domain/text.py` 1950 `F20982B9281E…`,
  `domain/render.py` 8964 `457A2C9FDFBB…`, `domain/engine.py` 3002 `783B2B59CE0D…`, `domain/refs.py` 3076 `4E4334AD0BB4…`,
  `domain/inventory.py` 5419 `BB01FB0B14DB…`, `module.py` 480 `6D756C66613D…`, карточки `split_gd_scan.json`/`split_gd_plan.json`,
  корпус `fixtures/corpus/editing/split_gd` (102 кейса).
- Скелет твоего модуля (все файлы — TODO, 200–500 B): `python/modules/editing/split_py/{app.py, module.py, tools.py, __init__.py, domain/core.py, domain/__init__.py, tests/test_core.py}`.
- Git в `agent-rebuild` намеренно **нет**; единственный git — старый плагин. Две чужие untracked-строки в нём не удалять.

## §0.1 Эталон (только чтение, байты не менять)

- `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\python\godot_tools\split_refactor.py`
  — **44 114 B, 872 строки, CRLF 872/872**, sha256 `87cb4d5209c0…` (полный хеш — в манифест корпуса).
- Второй адрес (поведение CLI, не портируется): `…\python\tools\agent_bridge.py` 142 171 B `a9b1ad832fd0…`,
  `_split_target:914` (`ext=".py"`, `tool="split_refactor"`; без `addon_dir`+`allow_self_edit` →
  `BridgeRefused("%s works on the agent's own addon; run the bridge with --access agent-dev")`),
  `cmd_split:934` (scan/plan, печать `refs:`, `next: … (action split_refactor)`), MCP-обёртки
  `godot_agent_mcp.py:464` (`split_scan`) и `:471` (`split_plan`).
- Карта строк эталона: `SCHEMA=1` 38; `_DEFAULT_TARGET_LINES=900` 40; `_SCAN_SKIP_DIRS` 43; `_SCAN_EXTS` 48;
  `_MAX_SCAN_FILE_BYTES=1 MiB` 51; `_MAX_OCCURRENCES=1000` 52; `_IMPORT_RE` 54; `_CODING_RE` 55;
  `SplitError` 58; `StaleSplitError` 62; `_norm` 66; `_read_text` 70; `_sha256` 87; `_files_of` 91;
  `_imported_modules` 104; `_module_matches` 123; **`scan_refs` 127–202**; `_warn_patched_attributes` 202;
  `file_inventory` 270–340; `suggest_groups` 349; `_format_import` 368; `_find_cycle` 375; `_join_blocks` 401;
  **`plan_split` 407–656** (C.18); `_render_facade` 656; `apply_prepared_split` 718 (запись, не в срезе);
  `_print_plan_summary` 770; `_cli` 792.
- Форма ответа эталонного `scan_refs` (проверь живьём на фикстуре, прежде чем писать схему):
  `{rel, stem, counts{import,source_read,patch,mention,doc}, occurrences[{rel,line,kind,text}], hard_files[], soft_files[], truncated}`.

## §1 Границы среза

Срез — **первая половина** механики `editing.split_py`: инструмент `split_scan`, только чтение. Он отвечает
на вопрос «кто пользуется этим `.py` и что поедет при разбиении»: импорты, патчи атрибутов, чтение
исходника, упоминания и доки. План разбиения (модули, фасад, цикл импортов, рендер) — **C.18**, запись — **C.19**.

Почему так: `scan_refs:127-202` опирается только на `_files_of`, `_imported_modules`, `_module_matches`
и не знает ни про AST разбор донора, ни про рендер. `plan_split:407-656` тянет за собой `file_inventory`,
`suggest_groups`, `_find_cycle`, `_render_facade` и `apply_prepared_split` — это другой объём и другие риски.
Делить одну механику на два инструмента в порте законно (`usages` + `analyze_rename` в `code_intel`,
`split_gd_scan` + `split_gd_plan` в уже принятом `editing.split_gd`); карточка одна — на `split_scan`.

### В срезе

- Папка `python/modules/editing/split_py/` — заполняется **на месте**, TODO-скелет не удалять, а заменять.
  Комментарий в `module.py` `# tools: split_scan, split_plan` оставить правдивым (в C.17 заявлен один инструмент,
  второй — C.18; в `provides_tools` попадает только `split_scan`).
- Корпус `fixtures/corpus/editing/split_py/` (кейсы `0xx`, ≥22) + фикстуры
  `fixtures/projects/corpus/editing/split_py/<вариант>/`, каждый вариант — «аддон» с `plugin.cfg` в корне.
- Карточка `contract/capabilities/split_scan.json`.
- Лист механики `docs/porting/editing.split_py.md` — **создаётся первым**, на шаге 1, по `_template.md`.
- Записи: `docs/parity.md` (строка `split_scan/plan`), `docs/PROGRESS.md` (строка `editing.split_py`: 0 → 6),
  `docs/tests-map.md`, `docs/WORKLOG.md` (append, без нормализации EOL).

### Не в срезе

- `plan_split`/`file_inventory`/`suggest_groups`/`_find_cycle`/`_render_facade`/`_format_import`/`_join_blocks`/
  `_segment_text`/`_expand_comments`/`_import_bindings`/`_other_item`/`_used_names`/`_warn_patched_attributes` — **C.18**.
- `apply_prepared_split:718`, `_cli:792`, `StaleSplitError`, воронка `write_preview → write_apply → rollback`,
  `_make_split_gd_prepared`-аналоги в мосте — **C.19** (см. §10).
- `editing.split_gd` (принят), `editing.symbol_rename` (этап 6, не наш), `editing.file_refactor`,
  `editing.paths_preview`, `editing.resource_ops`; `verification.*`, `engine_kb.*`, `code_intel.*`, `scene_model.*`.
- `python/kernel/*`, `python/substrate/*`, `python/runtime/*`, `python/protocol/*`, `contract/editor_verbs.json`,
  `editor/**`.
- Замороженные `tools/{gen_contract,lint_arch,security_audit,snapshot_diff,selfcheck}.py`.
- `docs/porting/_audit-handoff.md` — его правит только аудитор.

### Разрешённые правки вне папки и корпуса — ровно три

1. `fixtures/corpus/context/gather/001-all-sections.json` — добавить `split_scan` с эффектом `"read"`,
   `count` 22 → 23 (и SHA этого кейса в `fixtures/corpus/context/gather/manifest.json`).
2. `tests/py/integration/test_tscn_lint.py` (список имён инструментов, 22 → 23) и любые тесты, которые
   пиннят число карточек/имён — **только эти строки**.
3. `fixtures/corpus/scene_model/scene_deps/manifest.json` — **только дописать** факты (`script_facts`)
   для новых `.gd`, если они появятся; если новых `.gd` нет — правка не нужна. Старые записи, их порядок,
   `format_facts`/`snake_cases`/`scene_facts` и `tests/py/formats/test_scene_deps_facts.py` — не менять.

Всё остальное — байт-в-байт. Список правок дублируй в листе и в WORKLOG: аудитор делает обратную
проекцию по sha256 и обязан видеть каждую строку.

## §2 Контракт и раскладка

### 2.1 ToolSpec — дословно

```python
from python.kernel.limits import READ_TEXT_MAX_BYTES   # 4 * 1024 * 1024 — вторая константа не нужна
from python.kernel.tool_spec import ToolSpec

KINDS = ['import', 'source_read', 'patch', 'mention', 'doc']

ARGS = {
    'type': 'object', 'required': ['path'], 'additionalProperties': False,
    'properties': {'path': {'type': 'string', 'minLength': 1}},
}

COUNTS = {
    'type': 'object',
    'required': list(KINDS),
    'additionalProperties': False,
    'properties': {name: {'type': 'integer'} for name in KINDS},
}

OCCURRENCE = {
    'type': 'object', 'required': ['file', 'line', 'kind', 'text'],
    'additionalProperties': False,
    'properties': {
        'file': {'type': 'string', 'minLength': 1},
        'line': {'type': 'integer'},
        'kind': {'type': 'string', 'enum': list(KINDS)},
        'text': {'type': 'string'},
    },
}

RESULT = {
    'type': 'object',
    'required': ['donor', 'stem', 'counts', 'occurrences', 'truncated',
                 'hard_files', 'soft_files'],
    'additionalProperties': False,
    'properties': {
        'donor': {'type': 'string', 'minLength': 1},
        'stem': {'type': 'string', 'minLength': 1},
        'counts': COUNTS,
        'occurrences': {'type': 'array', 'items': OCCURRENCE},
        'truncated': {'type': 'boolean'},
        'hard_files': {'type': 'array', 'items': {'type': 'string'}},
        'soft_files': {'type': 'array', 'items': {'type': 'string'}},
    },
}

SCAN = ToolSpec(
    name='split_scan',
    description='Карта ссылок на .py агента: импорты, патчи, чтение исходника, упоминания. Только чтение.',
    args=ARGS, result=RESULT, effects='read', idempotent=True,
    errors=('invalid_input', 'not_found', 'denied'),
    availability='*', cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES},
)
TOOLS = (SCAN,)
```

Смысл полей (сверь живьём, прежде чем закреплять):

- `donor` — путь донора **внутри аддона** (`a/b.py`, слэши, без ведущего `/`) — это эталонный `rel`;
  `stem` — имя файла без расширения (эталон отдаёт `stem` отдельным ключом, публикуй как есть).
- `counts` — пять счётчиков эталона **без** `path`/`call` и **с новым** `patch`; `mention` здесь **достижим**
  (в `.gd`-пиле он был мёртвой ветвью — не переноси это заблуждение).
- `occurrences` — до **1000** записей в порядке обхода; `text = line.strip()[:200]` — у `.py`-пилы **200**,
  не 160 (у `.gd` было 160; не унифицируй «для красоты»).
- `hard_files` — файлы с `kind` из (`import`, `source_read`, `patch`), `sorted()`; `soft_files` — с
  (`mention`, `doc`), `sorted()`. Файл может попасть в оба только если в нём есть и жёсткая, и мягкая
  ссылка — тогда он в обоих списках (проверь это кейсом, а не догадкой).
- `truncated` — ровно `len(all hits) > 1000`; на 1000 попаданий ещё `False`.
- `SCHEMA = 1` эталона **не публикуется** (внутренний маркер версии); в корпусе `reference_result`
  остаётся сырым, с `schema`.

### 2.2 Где что живёт (R-02, R-11)

| Файл | Что внутри |
|---|---|
| `domain/text.py` | `decode(raw)` — **свой**, 6 строк: инкрементальный `utf-8-sig` с `errors='replace'` и `final=True` (снимает ровно один ведущий BOM, хвостовой частичный BOM не превращает в `\ufffd`); чужой `verification/shared/source_text.py` **не импортировать** (R-11; ADR-0010 дал единственный шов и он не наш). |
| `domain/walk.py` | `SKIP_DIRS` (13 имён эталона: `__pycache__`, `.git`, `.godot`, `.import`, `.agent_history`, `dist`, `build`, `minilich_brain`, `parser_corpus`, `agent_api_cache`, `node_modules`, `.venv`, `_tmp`), `SCAN_EXTS` (как в эталоне `:48`), `MAX_SCAN_FILE_BYTES = 1024*1024`, `MAX_OCCURRENCES = 1000`, `eligible(rel)` (пропуск каталогов из списка и любых, начинающихся с точки), `imports(line)` → `(modules, aliases)` — дословный перенос `_imported_modules:104`, `module_matches(candidate, stem)` — `_module_matches:123`. |
| `domain/refs.py` | `scan(donor, stem, base, files)` — регулярки `name_re`, `patch_re`, `setattr_re` дословно (`:141-152`), порядок ветвей **строго**: `import` → `patch` (+`setattr(`) → (имя файла или `rel` в строке) → `.py` и (`open(`/`__file__`/`read_text(`) → `source_read`; `.md` → `doc`; иначе `mention`; лимит 1000 и флаг `truncated`, `text[:200]`. |
| `domain/core.py` | `assemble(donor, stem, references)` — публичная проекция (см. 2.1) и `sorted()` для `hard_files`/`soft_files`. |
| `app.py` | только оркестрация ≤ 80 строк: `validate(args, ARGS)` → `res://` → `normalize_rel` → `deny_reason` → аддон-корень по `plugin.cfg` → `fs.is_file` → `fs.read_raw` с лимитом 4 MiB → `text.decode(raw)` → `walk/refs` по `fs.list_files()` → `core.assemble`. |
| `tools.py` | `TOOLS = (SCAN,)` из §2.1, ≤ 150 строк. |
| `module.py` | `ModuleSpec(id='editing.split_py', description=…, provides_tools=('split_scan',), requires_ports=('fs',), capabilities=('editing.split_py',), entrypoints={'call': app.call}, corpus='corpus')`; комментарии `# tools: split_scan, split_plan` и `# ср. editing.split_gd` можно оставить. |
| `ports.py` | `Protocol` с `is_file(rel)`, `read_raw(rel)`, `list_files()` — ровно те методы, что уже есть у `DiskFileSystem`; новый порт не заводить. |

Правила: `domain/` без `os`/`pathlib`/`socket`/`subprocess` (R-11; `re`, `codecs` — можно), IO только в
`app.py` через `ctx.port('fs')`, `app.py` ≤ 80 строк, новый файл ≤ 400 (`kernel/limits.FILE_MAX_LINES`),
папка ≤ 3000. `app.call` возвращает **payload** и поднимает `AppError`; единый `Result` собирает
`Agent.call` (`python/runtime/bootstrap.py:66-71`) — runtime/protocol/kernel не менять (решение C.14, B3).

### 2.3 Аддон-корень и доступ (как в принятом C.14 — не переизобретать)

- `path` обязан быть `res://…` и оканчиваться `.py` — иначе `invalid_input` («донор должен быть `.py`»).
- Аддон-корень = ближайший предок донора (включая его каталог), в котором есть `plugin.cfg`; нет такого —
  `invalid_input` («донор не находится внутри аддона с plugin.cfg»).
- Обход и чтение — **только внутри** аддон-корня (`prefix + '/'`), донор исключается; для каждого файла
  сначала `ctx.path_policy.deny_reason(rel)` — отказ политики → сосед **молча пропускается**; отказ на самом
  доноре → `denied` с текстом политики.
- Права `--access agent-dev` из эталона отдельной проверкой **не** дублируются: доступ решает политика
  (`res://addons/...` без `allow_addons`/`allow_self_edit` → `denied`), поэтому кейсы с `res://addons/...`
  остаются границей контракта, а не «починенным поведением».
- Фикстуры поэтому делаются «аддоном в корне проекта»: `fixtures/projects/corpus/editing/split_py/<вариант>/plugin.cfg`,
  и `snapshot_diff`, который строит `build_agent(project_root=fixture, profile='headless')`, видит обычные файлы проекта.

### 2.4 Проекция «эталон → порт»

| Эталон | Порт |
|---|---|
| `scan_refs(addon_dir, rel_path)` (`:127`) | `split_scan(path)`; `rel` берётся из `path` внутри аддон-корня |
| `os.path.isfile(...)` → `SplitError("файл не найден: %s")` | `fs.is_file` → `not_found` (`AppError('not_found', 'файл не найден: %s' % rel)`) |
| `_files_of(addon_dir)` (os.walk, сортировка каталогов, пропуск `_SCAN_SKIP_DIRS` и точечных) | `fs.list_files()` + фильтр по `SKIP_DIRS`/точечным в `domain/walk.py`, сортировка — как в `DiskFileSystem.list_files` |
| `_read_text` (`utf-8-sig`, `errors='replace'`) | свой `decode(raw)` из §2.2 |
| лимит `_MAX_SCAN_FILE_BYTES` 1 MiB на **соседа** | тот же лимит, `continue` |
| лимит 4 MiB `READ_TEXT_MAX_BYTES` на **донора** | `invalid_input` («файл больше лимита чтения») |
| `occurrences` 1000 + `truncated` | так же, `text[:200]` |
| `hard_files`/`soft_files` | так же, `sorted()` |
| `schema: SCHEMA` | **не публикуется** |
| `_cli:792`, `_print_plan_summary:770` | не портируются (CLI-текст) |

Замечание про эталон, которое нельзя «улучшать»: `_CODING_RE:55` (`^#!|^#\s*-\*-`) объявлен, но в `scan_refs`
не используется. Паритет важнее чистоты — оставь его неиспользуемым (или не переноси вовсе, но не подключай).

### 2.5 Вход и ошибки

- `path` не строка / пустая / без `res://` / не `.py` → `invalid_input` с человеческим текстом; в ответе
  (`ok: False`) **не должно быть** абсолютных путей проекта.
- `normalize_rel(...) is None` → `denied` («путь вне проекта»).
- `ctx.path_policy.deny_reason(rel)` непустой (в т.ч. `addons/...` без `allow_addons`, исходники агента без
  `allow_self_edit`) → `denied` с текстом политики.
- Нет файла → `not_found`; нет аддон-корня (`plugin.cfg` выше донора) → `invalid_input`.
- `fs.read_raw` может поднять `PermissionError` → `denied`, `EFBIG` → `invalid_input`, другой `OSError` → `internal`
  (как в `verification/*/app.py` и в принятом `split_gd/app.py`).
- Непроверяемое расширение донора — **не** «тихий успех»: это `invalid_input` (в отличие от `verify`, где
  `checked: false`; здесь инструмент узкий).
- Ошибки не вылетают наружу: `app.call` → `AppError`, `Agent.call` → `Result`.
- Идемпотентность: два подряд вызова дают равные ответы; sha дерева проекта до/после совпадают
  (докажи тестом, а не обещанием).

### 2.6 Якоря эталона (для листа и для мутаций)

`SCHEMA:38`, `_DEFAULT_TARGET_LINES:40` (=900, C.18), `_SCAN_SKIP_DIRS:43`, `_SCAN_EXTS:48`,
`_MAX_SCAN_FILE_BYTES:51`, `_MAX_OCCURRENCES:52`, `_IMPORT_RE:54`, `_CODING_RE:55`, `SplitError:58`,
`StaleSplitError:62`, `_norm:66`, `_read_text:70`, `_sha256:87`, `_files_of:91`, `_imported_modules:104`,
`_module_matches:123`, `scan_refs:127`, `file_inventory:270`, `suggest_groups:349`, `plan_split:407`,
`apply_prepared_split:718`.

Старые тесты (прочитать, не копировать и не запускать): `tests/test_split_refactor.py` 22 394 B —
их кейсы попадают в корпус через **пересъёмку живого эталона**, а не переносом кода;
`tests/test_split_gd.py`/`test_split_gd_flow.py` — про `.gd`-пилу, к нам не относятся;
`tests/test_agent_bridge.py` (раздел `split`) — host-bridge, судьба «replaced» в `docs/tests-map.md`.

## §3 Шаги

**1. Лист первым.** Создай `docs/porting/editing.split_py.md` по `_template.md`: заголовок, статус
«этап 1; старая логика прочитана», цель, таблица старого кода (`split_refactor.py:38-62,66-91,104-127,127-202`
в срезе; `270-656,718` — C.18/C.19), таблица старых тестов, «корпус ещё не снят», блокеры/решения — пусто.
`docs/PROGRESS.md`: строка `editing.split_py` 0 → **1**. Сразу сними sha256 всех файлов, которые собираешься
менять (база для обратной проекции).

**2. Корпус — до кода.** Одноразовый скрипт в `%TEMP%` (в аддон не класть): копирует вариант-«аддон» во
временный проект и вызывает **живой** эталон `split_refactor.scan_refs(addon_dir=<temp>, rel_path=<донор>)`;
`sys.path` = старый `python/` + `godot_tools` + `parsers` + `tools`. Сохраняй `reference_result` **сырым**
(с `schema`), `expect.result` — проекция по §2.1/§2.4. Минимум **22 кейса**, номера с `001`, покрытие
обязательно такое:

- чисто: одна `.md`-дока ( `doc` ), импорт донора `from x import y` и `import x as z` ( `import` ),
  `mod.fn = ...` и `setattr(mod, "fn", ...)` ( `patch` ), `open(__file__)`/`read_text(` ( `source_read` ),
  простое упоминание имени файла ( `mention` );
- импорт «по хвосту» (`package.donor` при `stem == donor`) и **не** совпадающий (`donor_other`);
- патч через `+=`/`|=` (регулярка эталона это ловит) и **не**-патч (`x = donor.fn` — присваивание слева не от `mod.`);
- донор упомянут сам в себе (исключается) и в соседе без ссылок (не попадает);
- `.md` рядом с `.py`-ссылкой → файл в `hard_files` **и** в `soft_files` (докажи оба списка);
- каталоги из `SKIP_DIRS` (`__pycache__`, `.git`, `node_modules`, `agent_api_cache`) и точечный каталог — не сканируются;
- сосед > 1 MiB — пропущен (без падения); донор > 4 MiB — `invalid_input` границы контракта;
- 1000 попаданий → `truncated: false`, 1001 → `true` (фикстуру сгенерируй скриптом и закоммить готовой);
- `occurrences.text` обрезан на 200 символах (строка-«простыня»);
- BOM у донора и у соседа, CRLF-сосед (`text` без `\r`), lone CR, частичный BOM (`EF BB`) — декодирование как в §2.2;
- донор не `.py` → `invalid_input`; нет файла → `not_found`; нет `plugin.cfg` → `invalid_input`;
  `res://addons/...` → `denied`; не-`res://` → `invalid_input`; лишний/отсутствующий аргумент → `invalid_input`;
- идемпотентность и неизменность дерева.

`fixtures/projects/corpus/editing/split_py/<вариант>/` — «аддон»: `plugin.cfg` в корне, `project.godot` по
желанию, донор и соседи. `manifest.json` — по образцу `fixtures/corpus/editing/split_gd/manifest.json`
(`schema_version`, `captured_at`, `module`, `reference{file, function: 'scan_refs:127-202', sha256, bytes}`,
`capture_script{sha256,bytes}`, `fixture_base: fixtures/projects`, `cases`, `inputs` с sha256+bytes,
`contract_refusals` с расшифровкой). Поле `fixture` пиши **относительно** `fixtures/projects`
(иначе `snapshot_diff` не найдёт фикстуру; в C.15 на этом спотыкались).

**3. Красные тесты — до кода.** `tests/test_core.py` (сборка ответа), `tests/test_walk.py`
(`imports`, `module_matches`, `eligible`), `tests/test_refs.py` (все пять категорий, приоритет ветвей,
лимит 1000/`truncated`, `text[:200]`, оба списка), `tests/test_app.py` (фейковый `fs` с `is_file`/`read_raw`/
`list_files`; отказы **до** чтения: `invalid_input`/`denied`/`not_found`; лимит 4 MiB; `PermissionError`/`EFBIG`),
`tests/py/integration/test_split_scan.py` (корпус через `build_agent(project_root=fixture, profile='headless')`,
хеши дерева до/после, идемпотентность, отсутствие абсолютных путей в отказах),
`tests/py/contract/test_split_scan_contract.py` (карточка, `effects == 'read'`, `errors`, `limits`,
`TOOLS`). Зафиксируй красный прогон (счётчики) в листе.

**4. Код — в порядке** `domain/text.py` → `domain/walk.py` → `domain/refs.py` → `domain/core.py` →
`app.py` → `tools.py`/`module.py`. Лимиты — §2.2.

**5. Контракт.** `python -B tools/gen_contract.py --write` создаёт **только** `contract/capabilities/split_scan.json`;
22 прежние карточки — байт-в-байт; `--check` → **24** артефакта.

**6. Разрешённые правки** из §1 — только после того, как инструмент отвечает.

**7. Двойной прогон.** Full non-live `python/modules tests/py --ignore=tests/py/live` (3617 + новые; junit
только через python-драйвер `subprocess`, не через `Start-Process` — иначе `--junitxml` ломается);
`tools/snapshot_diff.py` (724 + новые кейсы; строка `editing/split_py`); `selfcheck editing.split_py`
(unit растёт, corpus = твои кейсы, layers/limits +~20 файлов, contract 24); соседи не двигаются
(`editing.split_gd` 625/102, `verification.check` 188/75, `api_check` 206/52, `gd_lint` 126/37,
`tscn_lint` 315/65, `class_api` 186/26); `tools/lint_arch.py`, `tools/check_limits.py`,
`tools/security_audit.py`; live = **3** без skip (предусловие §0), затем `.gd.uid` = **83** и debris 0.

**8. Записи.** Лист (этап 6 «готово к независимому аудиту, не принято» + доказательства), `docs/parity.md`,
`docs/tests-map.md`, `docs/PROGRESS.md` (`editing.split_py` = 6), `docs/WORKLOG.md` — **только append в `ab`,
без нормализации EOL** (исторический префикс 4479 CRLF обязателен). «Принято/ported» и этап 7 — **не писать**.

## §4 Решения, которые уже приняты (не пересматривать)

1. Срез — только `scan_refs`. `plan_split:407` (C.18) не «заглядывает» сюда даже частично.
2. `schema` эталона не публикуется; `reference_result` остаётся сырым.
3. Публикуются **оба** ключа эталона: `donor` (из `rel`) и `stem`.
4. Пять категорий — `import`, `source_read`, `patch`, `mention`, `doc`; `mention` достижим, `patch` — новый,
   `path`/`call` (от `.gd`-пилы) **не переносятся**.
5. `text[:200]`, `str.strip()` до обрезки (лимит `.gd`-пилы 160 не унифицируется).
6. Лимиты: сосед — 1 MiB (`continue`), донор — 4 MiB `READ_TEXT_MAX_BYTES` (`invalid_input`).
7. Аддон-корень по `plugin.cfg`, политика путей вместо флага `--access agent-dev`; `PathPolicy`/`bootstrap` не менять.
8. Свой декодер (инкрементальный `utf-8-sig`, `final=True`); чужой `shared` не импортировать.
9. `fs.list_files()` + фильтрация в домене; новых методов порта и новых портов не заводить.
10. `sorted()` для `hard_files`/`soft_files`; `occurrences` — в порядке обхода.
11. `_CODING_RE` не подключается к логике (мёртвый в эталоне).
12. `app.call` → payload/`AppError`; `Result` — в `Agent.call`.

## §5 Доказательства (портер сдаёт, аудитор повторит)

**Мутации (каждая с байтовым бэкапом и сверкой sha256 до/после):**

| # | Мутация | Должна уронить |
|---|---|---|
| M1 | убрать ветвь `import` (импорт падает в `mention`) | кейсы импортов |
| M2 | `patch` сливается с `source_read` / меняется порядок ветвей | кейс патча и кейс приоритета |
| M3 | снять лимит `MAX_OCCURRENCES` | кейс `truncated` (1001) |
| M4 | не исключать донора | кейс «донор упомянут сам в себе» |
| M5 | `hard_files` = все файлы с попаданиями | кейс обоих списков |
| M6 | игнорировать `SKIP_DIRS` | кейс `__pycache__`/`node_modules` |
| M7 | `text[:160]` вместо `[:200]` | кейс длинной строки |
| M8 | `module_matches` = строгое равенство | кейс импорта «по хвосту» |

**Подложки (гейты, а не тесты):**
- P1: убрать `'truncated'` из `RESULT['required']` → тесты зелёные, красный только `tools/gen_contract.py --check`
  (`fail: split_scan.json`).
- P2: `import os` в `domain/refs.py` → `tools/lint_arch.py` («domain/ запрещает IO-модуль os»).
- P3: `app.py` импортирует `python.modules.verification.shared.source_text` → `lint_arch` («импортирует чужой модуль»).

**Обратная проекция:** для каждого добавленного/изменённого файла — bytes и sha256 до/после; отдельно докажи, что
`editing.split_gd` (11 файлов + карточки + 102 кейса), 22 прежние карточки, `contract/editor_verbs.json`,
`python/kernel/*`, `python/substrate/*`, `python/runtime/*`, `python/protocol/*`, `editor/**` и все принятые
области (`verification/*`, `engine_kb/*`, `scene_model/*`, `code_intel/*`, `editing/{scene_ops,symbol_rename,write_*}`)
остались байт-в-байт.

**Гигиена:** дерево = 2776 + новые файлы (промпт, лист, модуль, корпус, фикстуры, карточка, тесты), `.gd.uid` = 83,
`__pycache__`/`.pytest_cache`/`.bak|.tmp|.orig`/`zz_*` = 0, `reports/selfcheck/` — только отчёты механик,
одноразовые скрипты — в `%TEMP%`, в аддоне их быть не должно.

## §6 Стоп-условия (остановись и напиши аудитору, а не «додумывай»)

- Паритет требует правки принятого `editing.split_gd`, `verification/*`, `engine_kb/*`, `python/kernel/*`,
  `python/substrate/*`, `PathPolicy`, `bootstrap` или замороженных `tools/*`.
- Нужен новый метод порта, новый порт или новый ADR-шов для импорта.
- Проекция требует поля, которого в эталоне нет, или теряет поле, которое есть.
- Корпус нестабилен, `snapshot_diff` не находит фикстуру, или кейс проходит только после правки чужого кейса.
- Соседние числа сдвинулись (`editing.split_gd` не 625/102, `verification.check` не 188/75, `gd_lint` не 126/37,
  `tscn_lint` не 315/65, `api_check` не 206/52, `class_api` не 186/26).
- Тянет «улучшить» эталон (подключить `_CODING_RE`, унифицировать `[:200]` с `[:160]`, переименовать категории).
  Паритет выигрывает у красоты; всё, что хочется улучшить, — в лист, раздел «Следующее действие».

## §7 Что будет проверять аудитор (знай заранее)

1. Свою пересъёмку корпуса: своим скриптом заново поднимет эталон (`scan_refs`) на копиях фикстур и сравнит
   с твоими `reference_result`; потом посчитает **свою** проекцию и сравнит с `expect.result`; потом прогонит порт
   по всем кейсам (успехи — равенство словаря, отказы — `kind` + отсутствие абсолютных путей, идемпотентность,
   sha дерева).
2. Свой дифференциал шире корпуса: все `.py`-доноры своих фикстур **плюс** не менее 20 реальных `.py` из порта
   (по одному на область), в двух разрезах — с политикой (`addons/...` → отказ) и без. Разойтись может только
   документированное: лимит 4 MiB, отказы политики, отсутствие `plugin.cfg`.
3. Свои мутации M1–M8 и подложки P1–P3 (включая проверку, что P1 ловится **только** контрактным гейтом).
4. Инвентарь: `gen_contract --check` = **24** артефакта (25 файлов), `contract/capabilities` +1, `context.gather`
   = **23** имени с `split_scan: read`, `# verb:` = 6, `verbs_version: 3`, `snapshot_diff` = 724 + твои кейсы.
5. Неизменность принятого: `editing.split_gd` те же sha256 и selfcheck 625/102; соседи те же числа;
   `editor/**` и `contract/editor_verbs.json` байт-в-байт.
6. Гигиену: дерево, `.gd.uid` = 83 (после live удалить ровно сгенерированные; корневой `plugin.gd.uid` редактор
   удаляет — восстановить побайтово из бэкапа), debris 0, никаких одноразовых скриптов в аддоне.

## §8 Финальный прогон и записи

Один отчёт в листе + запись в `WORKLOG.md`: число non-live (и время, и collect), строка `snapshot_diff` с твоим
корпусом, таблица `selfcheck editing.split_py` + `reports/selfcheck/editing.split_py.json`, `gen_contract --check`
(24), `lint_arch`, `check_limits`, `security_audit`, live = 3, дерево/`.gd.uid`/debris, таблица мутаций со sha256
и обратная проекция.

Обновить: лист (этап 6, «готово к независимому аудиту, не принято»), `docs/parity.md` (строка
`split_scan/plan`: scan — этап 6, plan — C.18), `docs/tests-map.md`, `docs/PROGRESS.md`
(`editing.split_py` = 6), `docs/WORKLOG.md` (append в `ab`, EOL не нормализовать) и три разрешённые правки из §1.

**Не писать:** `docs/porting/_audit-handoff.md`, «принято/ported», этап 7, `contract/editor_verbs.json`,
`python/kernel/schema.py`, `tools/{lint_arch,gen_contract,security_audit,snapshot_diff,selfcheck}.py`.
Сдача: «C.17 готов к независимому аудиту, не принято» + список файлов с bytes/sha256 + перечень
намеренных границ (лимит 4 MiB, отказы политики, `plugin.cfg`).

## §9 Ошибки прошлых срезов — не повторяй их в C.17

Это не гипотезы: каждая строка стоила отдельной сессии аудита.

1. **EOL `WORKLOG.md`.** Мои же патч-скрипты дважды переписывали файл целиком и превращали историю в LF
   (сессии 65 и 67), потом чинились из бэкапа. Правило: `WORKLOG` — только `ab`, EOL не нормализовать;
   после записи проверь `crlf == 4479` в историческом префиксе.
2. **`Start-Process` и `--junitxml`.** PowerShell рвёт склеенный аргумент → pytest пишет
   `ERROR: file or directory not found: …xml`, а прогон выглядит «пустым». Правило: полный прогон —
   только из python-драйвера (`subprocess.run([sys.executable, '-B', '-m', 'pytest', …])`).
3. **`recovery: plan=… action=expired` в stderr.** PowerShell считает это ошибкой команды (exit 1,
   `NativeCommandError`), хотя прогон зелёный. Правило: stderr в файл, `recovery:`-строки отфильтровать
   и сказать об этом в отчёте.
4. **Убийство процесса мутаций.** `Stop-Process` посреди прогона оставил мутацию в живом файле
   (`verification/check/domain/core.py` 4546 B вместо 4551 B). Правило: мутации — последовательно, без
   параллельных прогонов, после каждой — сверка sha256; после всей серии — повторная сверка **всех** файлов.
5. **Вспомогательный скрипт, пишущий в проект.** Мой `hash9.py` открыл `engine_kb/shared/inheritance.py`
   на запись и заменил модуль отчётом (972 B мусора); `gen_contract --check` упал «лишний артефакт».
   Правило: одноразовые скрипты — в `%TEMP%`, проект открывают **только на чтение**, пути — абсолютные
   (относительные в PowerShell уезжают в cwd старого плагина).
6. **Патч-скрипты без проверок.** `between()` не съедал конечный якорь → в handoff появилась склеенная
   строка `Git в agent-rebuild нет намеренно.Git …`; один раз вырезание «от якоря до конца» удалило
   абзац приёмки C.14. Правило: каждый `sub`/`replace_line` — с assert ровно одного попадания, после патча —
   проверка якорей и размера, и только потом «готово».
7. **`editor` и большие куски.** Вставка >6000 символов отклоняется целиком (и ничего не пишет), а
   `insert_line` за EOF отклоняется с диапазоном. Правило: сначала узнать число строк, потом вставлять
   кусками; при отказе — перечитать, а не повторять то же самое.
8. **База пути фикстуры.** В C.15 корпус писал `fixture` как `corpus/...`, а раннер ищет от
   `fixtures/projects`; из-за этого `snapshot_diff` не видел кейсов. Правило: `fixture` —
   **относительно** `fixtures/projects`, и сразу прогони `snapshot_diff` по своему корпусу.
9. **Копия аддона не сканируется.** Дифференциал на копии реального аддона даёт `denied` «корень агента
   неизвестен: аддоны закрыты (fail closed)» — `PathPolicy._agent_rel` указывает на настоящий аддон.
   Правило: либо реальный проект `D:\vajno\Godot\agent-rebuild` с `allow_addons=True, allow_self_edit=True`,
   либо фикстура-аддон внутри проекта (так сделано в C.14/C.15).
10. **Live и `.gd.uid`.** Живой прогон создаёт `.gd.uid` у фикстур (было 83 → 245), а редактор **удаляет**
    корневой `plugin.gd.uid`. Правило: до прогона — список, после — удалить ровно новые, корневой файл
    восстановить побайтово, в конце отчитаться `83`.
11. **Тексты сообщений.** F6 в C.16 появился потому, что мой промпт велел закрепить текст, который не мог
    сработать (его съедала схема аргументов); F10 — потому что я скопировал текст из корпуса, а живой
    эталон печатает его с префиксом `split_gd `. Правило для C.17: каждый текст, который ты закрепляешь
    в `expected_message`, сначала получи **живым вызовом** эталона, и если сокращаешь — запиши это
    в лист и в `manifest` как намеренное расхождение.
12. **Мёртвый код эталона.** В `.gd`-пиле категория `mention` оказалась недостижимой; аудитор потребовал
    перенести её байт-в-байт и закрепить нулём. В `split_refactor` такая же ловушка — `_CODING_RE`.
    Правило: переноси как есть и пинь тестом, а не «исправляй».

## §10 Почему запись (`split_refactor` → файлы) — не этот срез

Факты, снятые аудитором, чтобы ты не начинал её «по инерции»:

- `editing/write_preview` — это **компилятор переименований**, а не общий писатель:
  `app.call` → `core.build_request` → `ctx.call_tool('analyze_rename', …)` → `symbol_rename.compile_plan(...)` →
  `report.save(...)`. Ни `split_gd`, ни `split_py` в этот поток не входят.
- `editing/shared/funnel.py` умеет только **перезаписывать существующие** файлы: `guard_path`,
  `expected_of` (нет хэша → `stale_plan`), `verify_current` (sha256 сырых байт), `abort_plan`, `restore`.
  Создания и удаления файлов в воронке **нет**, а разбиение как раз создаёт новые модули.
- Эталонный `apply_prepared_split:718` пишет модули, гоняет `--headless --path` (таймаут 90 с) и откатывает
  при ошибке; в мосте это `_make_split_gd_prepared:2041` / `cmd_split_gd` (`write preview` c
  `action: "split_gd"`).
- Значит запись — это **отдельный срез (C.19) с ADR** о create/delete-семантике воронки, WAL и откате,
  и он не может быть «побочным эффектом» read-only инструмента.

C.18 — `split_plan` (`plan_split:407`, `suggest_groups:349`, `file_inventory:270`, `_find_cycle:375`,
`_render_facade:656`, `_format_import:368`) — тоже read-only и логично идёт следующим.
