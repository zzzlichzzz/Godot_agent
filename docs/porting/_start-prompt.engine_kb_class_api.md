# C.11 — `engine_kb.class_api` (инструмент `api`: класс Godot по кэшу, с цепочкой наследования)

Ты — портер. Продолжаешь перенос Godot-агента по эталону из старого плагина
`D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\` (HEAD `ba0535d4`).
Ты **не аудитор**: этап сам себе не ставишь, шапку «выполнено/принято» не пишешь,
`docs/porting/_audit-handoff.md` не правишь. Этап 7 ставит аудитор своими прогонами.

Обязательное чтение до кода: `AGENTS.md` → `RULES.md` (R-01…R-22) → `docs/architecture.md` →
`docs/PORTING.md` → `docs/parity.md` (строки 38–44 и 146) → `docs/tests-map.md` →
`docs/PROGRESS.md` (строка `engine_kb.class_api`) → `docs/porting/_template.md` →
листы соседей `docs/porting/verification.tscn_lint.md`, `docs/porting/verification.check.md`,
`docs/porting/verification.bom.md` (эталон оформления среза) → `docs/WORKLOG.md` (последние 3 сессии) →
`docs/security/invariants.md` → `docs/adr/` (ADR-0004 вклады, ADR-0006 контракт, ADR-0008 декодирование).

## §0 База (снято аудитом, сессия 62, 2026-10-31 — не пересчитывай «на глаз»)

- pytest non-live (`python -B -m pytest python/modules tests/py --ignore=tests/py/live -q
  -p no:cacheprovider`) → **2473 passed**, 0 fail/err/skip (~61 с); `--collect-only` — **88** файлов.
- `tests/py/live` → **3 passed** (~25 с; Godot `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`).
  Живой прогон создаёт `.gd.uid` в корпусах: удаляй ровно сгенерированные, 8 старых
  (`fixtures/parity/gdscript/`, 27.10.2026) не трогай.
- `python -B tools/snapshot_diff.py` → **531** кейс, 0 расхождений (в т.ч. `verification/check` 62/62,
  `gd_lint` 37/37, `tscn_lint` 65/65).
- `python -B tools/gen_contract.py --check` → **19** артефактов ok (цель среза — **20**).
- `python -B tools/lint_arch.py` / `tools/check_limits.py` → **497** файлов, 0 нарушений, 0 предупреждений.
- `python -B tools/security_audit.py` → ok.
- selfcheck: `verification.gd_lint` ok (unit **126**, corpus **37**), `verification.check` ok
  (unit **136**, corpus **62**), `verification.tscn_lint` ok (unit **315**, corpus **65**),
  `scene_model.*` ok. Вердикт `verification.check`: `reports/selfcheck/verification.check.json`.
- Дерево — **2170** файлов, `.gd.uid` **83**, `__pycache__` 0, `.pytest_cache` 0,
  `.bak/.tmp/.orig` 0, `zz_*` 0. Правил 22, промптов 29 (+1 = 30), листов механик 21 (+1 = 22),
  `contract/capabilities` 20 файлов (19 карточек + `_template.json`), механик 44 → **19** на этапе 7,
  1 на этапе 6 (`editing.symbol_rename`), **24 на нуле** (`engine_kb.class_api` — как раз этот срез).
- Мост не трогаем: `contract/editor_verbs.json` `CDAF8D23A6BF…`, `verbs_version: 3`, 6 примитивов,
  `protocol: 1`; `editor/bridge/verbs/scene/scene_executor.gd` `B7AFF592B75D…`.
- Замороженные файлы (менять нельзя): `python/kernel/schema.py 629FCE54E6FE…` (147 строк),
  `tools/lint_arch.py 1FAD8E7470D5…`, `tools/gen_contract.py FA7E6E91C872…`,
  `tools/security_audit.py 2CF0D7F6B1AF…`, `tools/snapshot_diff.py`.
- Принятые артефакты, которые нельзя сломать: `python/formats/tscn.py 9D69AFECDCC0…`,
  `formats/tscn_refactor.py E4A9F60A6381…`, `formats/gdscript/node_paths.py 92531952FD26…`,
  `scene_model/shared/node_path.py E747FB1B2E50…`, `node_rename/domain/core.py B5F370906049…`,
  `node_reparent/domain/core.py f53a3384f34e…`, `node_delete/domain/core.py fe63bc232bbc…`,
  `verification/tscn_lint/{app.py 50F77ED6B766…, read_inputs.py 74119F65825C…, domain/core.py F23EDD5A4ED9…}`,
  `verification/gd_lint/domain/core.py 1873E0A9E687…`, `verification/check/{app.py F1506108E191…,
  domain/core.py F84018B8EE08…, tools.py 65974F15AA55…}`, `verification/shared/source_text.py 56C397CFC171…`,
  `contract/capabilities/check.json 580B1D18974A…`, `contract/capabilities/verify.json 58C34188D6FD…`.
- Эталон этого среза: `python/godot_tools/gd_api_cache.py` — **11545 B**, 216 LF / 0 CRLF,
  `sha256 6e6f5e0c83de40d2469e167554cfa1084952f0812175bc4f67239a259650b65a`.
  Второй адрес: `python/tools/agent_bridge.py:534–581` (`cmd_api`, только текст CLI — не портируется);
  файл целиком `142171 B`, `sha256 a9b1ad832fd0…` (не подменяй).
- Git в `agent-rebuild` нет намеренно — историю не ищи, сверяйся с этим промптом и листами.

## §1 Границы среза

**Механика:** `engine_kb.class_api` — **владелец** инструмента `api`. Читает кэш Godot API
(уже существующий порт `api_cache`) и отдаёт типизированный ответ: цепочку наследования,
методы с арностью и сигнатурами, свойства, сигналы. Только чтение: кэш не пишется, не
мигрируется, каталог не создаётся, ничего не «обновляется».

**Имя инструмента — `api`** (не `class_api`, не `engine`). Оно свободно:
в `contract/capabilities/` нет `api.json`, в корпусе `context.gather` его нет.
`engine`/`api_cache_refresh` — другие механики, не этот срез.

**Что в scope:**
- `python/modules/engine_kb/class_api/` — манифест, ToolSpec, оркестрация, домен (скелет уже есть).
- `python/modules/engine_kb/shared/inheritance.py` — **чистая** логика области: цепочка наследования
  и сбор членов по цепочке (этот же файл позже возьмёт `verification.api_check`).
- `python/substrate/store/api_cache_store.py` — **аддитивно**: метод версии кэша (см. §1 «разрешённые правки»).
- Корпус `fixtures/corpus/engine_kb/class_api/` (фикстуры-проекты с маленькими `.agent_history/godot_api_cache.json`).
- Лист `docs/porting/engine_kb.class_api.md` (этап 1 — первым делом).

**Вне scope (не трогать и не «заодно»):** `engine_kb.engine_info`, `engine_kb.api_cache_refresh`
(нужен живой Godot и запись), `verification.api_check`, `agent_bridge.cmd_api` как CLI,
запись кэша `gd_api_cache.save_cache`, миграция `_migrate_legacy_addon_cache` (эталон там **пишет**),
мост, WAL/undo, редактор, `contract/editor_verbs.json`, `tools/gen_contract.py`, `kernel/schema.py`.

**Разрешённые правки принятых артефактов (только эти, поимённо):**
1. `python/substrate/store/api_cache_store.py` — добавить `version()` (возвращает строку `godot_version`
   из той же записи, что читает `classes()`) и, если нужно, `has_cache()`; **`classes()` менять нельзя**
   (её поведение — контракт принятого C.8: тот же путь, те же фолбэки, truthy-классы и falsy-записи).
   Никаких `mkdir`/`write`/`migrate`; ошибки чтения по-прежнему → `{}`/`""`.
2. `fixtures/corpus/context/gather/001-all-sections.json` — в `expect.result.sections.tools` добавить
   имя `api` (`effects: "read"`), `count` 18 → **19**.
3. `tests/py/integration/test_tscn_lint.py:48–59` — список имён инвентаря (туда же `api`).
4. Любой тест, который пинит «19 карточек»/«19 имён»/`len(names())` — правится ровно в этой части.
   Всё остальное в этих файлах — байт-в-байт.

Ничего больше в принятых механиках не меняется; список правок — в лист и в WORKLOG
(аудитор делает обратную проекцию по sha256).

## §2 Контракт и раскладка

### 2.1 ToolSpec — дословно

```python
# python/modules/engine_kb/class_api/tools.py
ARGS = {
    'type': 'object',
    'required': ['class_name'],
    'additionalProperties': False,
    'properties': {
        'class_name': {'type': 'string', 'minLength': 1, 'maxLength': 120},
    },
}

RESULT = {
    'type': 'object',
    'required': ['class_name', 'found', 'cache_version', 'inherits',
                 'methods', 'properties', 'signals', 'unavailable'],
    'additionalProperties': False,
    'properties': {
        'class_name': {'type': 'string', 'minLength': 1},
        'found': {'type': 'boolean'},
        'cache_version': {'type': 'string'},
        'inherits': {'type': 'array', 'items': {'type': 'string'}},
        'methods': {'type': 'array', 'items': {
            'type': 'object',
            'required': ['name', 'min_args', 'max_args', 'signature'],
            'additionalProperties': False,
            'properties': {
                'name': {'type': 'string', 'minLength': 1},
                'min_args': {'type': 'integer'},
                'max_args': {'type': 'integer'},
                'signature': {'type': 'string'},
            },
        }},
        'properties': {'type': 'array', 'items': {'type': 'string'}},
        'signals': {'type': 'array', 'items': {'type': 'string'}},
        'unavailable': {'type': 'array', 'items': {
            'type': 'object',
            'required': ['kind', 'reason'],
            'additionalProperties': False,
            'properties': {
                'kind': {'type': 'string', 'minLength': 1},
                'reason': {'type': 'string', 'minLength': 1},
            },
        }},
    },
}

API = ToolSpec(
    name='api',
    description='Методы, свойства и сигналы класса Godot по всей цепочке наследования из кэша API.',
    args=ARGS, result=RESULT, effects='read', idempotent=True,
    errors=('invalid_input',), availability='*', cost='cheap', limits={},
)
TOOLS = (API,)
```

**Семантика полей** (каждое — проверяемо тестом):
- `class_name` — эхо запроса (нормализованное: `strip()`; пусто после нормализации → `invalid_input`).
- `found` = `bool(record)`, где `record = classes.get(class_name)`. Именно `bool(...)`, как в эталоне:
  falsy-запись `{}` — это **не найдено** (`if not info:` в `get_class`-ветке), а не «класс без членов».
- `cache_version` = `godot_version` из записи кэша, `""` если кэша нет или поле пустое.
- `inherits` — цепочка **в порядке эталона**: `[class_name, родитель, …]`, ровно как `resolve_chain`
  (обрыв на отсутствующей записи, guard от циклов, предел `max_depth=30`).
- `methods` — по всей цепочке, `setdefault` (ближний класс побеждает), **отсортировано по `name`**;
  `min_args`/`max_args` из пары арности; `signature` из `signatures` или `""`;
  битая/нечисловая арность → `min_args = max_args = -1` (документируй это в листе: «арность неизвестна»).
- `properties`, `signals` — объединение по цепочке, отсортировано.
- `unavailable` — **только** когда кэша нет вовсе: `[{'kind': 'api_cache', 'reason': 'no_cache'}]`
  (тогда `found: false`, `cache_version: ""`, все списки пустые). Класс, которого нет в существующем
  кэше — это ответ, а не `unavailable`: `found: false`, `unavailable: []`, `cache_version` заполнен.
- `limits={}` — файлов проекта инструмент не читает (`fs` не нужен), лимит байт живёт в порту.

### 2.2 Где что живёт (R-02, R-11)

```
python/modules/engine_kb/shared/inheritance.py   # чисто, без IO: chain/members/signatures над dict
python/modules/engine_kb/class_api/domain/core.py# чисто: assemble(class_name, classes, cache_version)
python/modules/engine_kb/class_api/app.py        # оркестрация <= 80 строк
python/modules/engine_kb/class_api/tools.py      # ToolSpec (§2.1)
python/modules/engine_kb/class_api/module.py     # ModuleSpec
```

`inheritance.py` (чистые функции над `classes: dict`, никаких `os/pathlib/io`, R-11):

```python
def resolve_chain(classes, class_name, max_depth=30):
    """[class_name, …, корень] — обрыв на отсутствующей записи, guard от циклов, предел глубины."""

def collect_members(classes, chain):
    """(methods: {name: arity}, properties: set[str], signals: set[str]) — setdefault по цепочке."""

def collect_signatures(classes, chain):
    """{name: signature} — только пары str/str, setdefault по цепочке."""
```

`domain/core.py` — `assemble(class_name, classes, cache_version) -> dict` (валидирует типы арности,
строит отсортированные списки в схему §2.1; `found = bool(record)`; пустой `classes` не его забота —
это решает `app.py` через `unavailable`).

`app.py` — только оркестрация: `validate(args, API.args)` → `class_name = args['class_name'].strip()`
(пусто → `invalid_input`) → `cache = ctx.port('api_cache')` → `classes = cache.classes()` →
если `not classes` → результат с `unavailable=[{'kind': 'api_cache', 'reason': 'no_cache'}]`
и `found: false` (порт не кидает исключений: он отдаёт `{}` при любой ошибке чтения) →
иначе `version = cache.version()` (см. §1 правка 1) → `core.assemble(...)` → `Result`.

`module.py`:

```python
module_spec = ModuleSpec(
    id='engine_kb.class_api', version='0.1.0', kernel_api='^1', godot='^4.6',
    environment='*', provides_tools=('api',), requires_ports=('api_cache',),
    capabilities=('engine_kb.class_api',), entrypoints={'call': app.call}, corpus='corpus',
)
```

Новый порт **не заводить** — `api_cache` уже есть в `python/runtime/bootstrap.py`
(`ApiCacheStore(project_root, state_dir=state, addon_dir=AGENT_DIR)`).

### 2.3 Проекция «эталон → порт» (что именно переносим)

| Эталон (`gd_api_cache.py` / `cmd_api`) | Порт |
|---|---|
| `has_cache()` == False → `RC_ERROR "no API cache available"` | `ok: true`, `found: false`, `unavailable: [{kind: api_cache, reason: no_cache}]` |
| `get_class()` → falsy (None **или** `{}`) | `found: false`; при существующем кэше — `unavailable: []`, `cache_version` заполнен |
| `resolve_chain(root, name, 30)` | `inherits` — тот же список, тот же порядок, тот же guard |
| `collect_members` (methods/setdefault, props∪, signals∪) | `methods`/`properties`/`signals`, **сортировка по имени** (детерминизм) |
| `collect_signatures` (только `str→str`) | `methods[].signature`, `""` если сигнатуры нет (старый кэш) |
| `_fmt_method`: `[lo, hi]` → `name(lo..hi)` / `name()` при `hi` falsy; исключение → просто имя | `min_args`/`max_args`; исключение → `-1`/`-1` |
| `get_cached_version` (версия только если классы есть) | `cache_version` |
| `_migrate_legacy_addon_cache` — **пишет** файл и `.gdignore` | **не портируется** (store read-only, это уже принято в C.8) |
| модульная переменная `_cache` (в процессе может отдать устаревшее) | **нет** глобального состояния: каждый вызов читает факт с диска (идемпотентность > кэш) |
| `cmd_api` печатает текст (`"%s [cache Godot %s]"`, `inherits: A -> B`, …) | в результат не переносим: типизированные поля вместо текста; текст формата — только в лист как справка |

### 2.4 Якоря эталона (читать, не угадывать)

`python/godot_tools/gd_api_cache.py` (11545 B, 216 LF, sha `6e6f5e0c…`):

- строки 19–27 — константы (`CACHE_FILENAME = "godot_api_cache.json"`,
  `DEFAULT_CACHE_FILENAME = "default_api_cache.json"`, `DEFAULT_CACHE_SUBDIR = "agent_api_cache"`);
- 32 — `_migrate_legacy_addon_cache` (пишет! не портировать), 61 — `_cache_path`
  (через `history.get_storage_dir(project_root)` → `.agent_history/godot_api_cache.json`),
  71 — `save_cache` (запись, не портировать);
- 115 — `_load_if_needed` (порядок: проектный кэш → бандл аддона `agent_api_cache/default_api_cache.json`
  → легаси `default_api_cache.json`; ранний выход по `_cache["root"]`), 150 — `get_cached_version`,
  156 — `has_cache`, 162 — `get_class`, 167 — `resolve_chain`, 186 — `collect_members`,
  202 — `collect_signatures`;
- форма записи: `{"godot_version": <str>, "classes": {<name>: {"inherits": <str|null>,
  "methods": {<name>: [<min>, <max>]}, "properties": [<str>], "signals": [<str>],
  "signatures": {<name>: <str>}}}}`; всё, кроме `classes`, может отсутствовать.
- `python/tools/agent_bridge.py:534–581` — `cmd_api` (порядок вывода, `NOT IN CACHE`-текст, RC-коды).
- Полный реальный кэш живёт **только в старом плагине**: `<OLD>\agent_api_cache\default_api_cache.json`,
  **2 004 630 B**. В порт его **не копировать** (это был бы новый файл аддона вне среза) и в корпус
  не тащить. Для живого probe можно скопировать его в temp-проект как
  `.agent_history/godot_api_cache.json` и прогнать `api` по `Node2D`; в отчёте — sha256 файла и ответ.
  Бандл-фолбэк (`addon_dir/agent_api_cache/default_api_cache.json`) в порту недостижим — его
  отсутствие это норма, «чинить» не надо.

### 2.5 Вход и ошибки

- `class_name`: не строка / пустая / >120 симв. → `invalid_input` (схема ловит до кода; после `strip()`
  пусто → свой `invalid_input` с человеческим текстом).
- «Нет кэша» — **не ошибка** (`ok: true` + `unavailable`), «класс не в кэше» — **ответ** (`found: false`).
- Исключений наружу нет: порт возвращает `{}` при `OSError/UnicodeError/ValueError` и при файле
  > `READ_TEXT_MAX_BYTES` (4 МиБ) — это уже поведение принятого `ApiCacheStore`, не переписывай его.
- Файлов проекта инструмент не читает, `path`-политика не участвует (нет путей) — `denied/not_found`
  в этом срезе не появляются, `errors=('invalid_input',)`.

## §3 Шаги

**1. Лист — первым.** `docs/porting/engine_kb.class_api.md` по `_template.md`, статус `этап 1`,
отдельная строка `PROGRESS.md` (`engine_kb.class_api` 0 → 1). В листе: таблица старого кода
(`gd_api_cache.py:19–27,115–217`, `agent_bridge.py:534–581`), таблица старых тестов (их нет —
так и напиши; `py_compile`/CLI не в счёт), цель среза, что вне scope.

**2. Корпус — до кода, actual-old.** Одноразовый скрипт в согласованном temp (не в репозитории),
через **библиотеку эталона**, а не CLI:

```python
sys.path.insert(0, OLD)              # OLD = ...\Godot_agent\godot_agent\python
sys.path.insert(0, OLD + '/tools')
import gd_api_cache
gd_api_cache._cache['root'] = None   # ОБЯЗАТЕЛЬНО перед каждым кейсом
gd_api_cache._cache['classes'] = {}
res = {
    'has_cache': gd_api_cache.has_cache(root),
    'version': gd_api_cache.get_cached_version(root),
    'record': gd_api_cache.get_class(root, name),
    'chain': gd_api_cache.resolve_chain(root, name),
    'members': gd_api_cache.collect_members(root, name),
    'signatures': gd_api_cache.collect_signatures(root, name),
}
```

Ловушка: у эталона **модульный** кэш — без сброса `_cache` между кейсами получишь данные чужого
проекта. Сброс — обязательный, повторяемый, и он же в скрипте пересъёмки аудитора.

Корпус: `fixtures/corpus/engine_kb/class_api/`, манифест по образцу
`fixtures/corpus/verification/tscn_lint/manifest.json` (`schema_version`, `captured_at`, `module`,
`reference_commit`, `reference{file,function,lines,sha256,bytes}`, `capture`, `capture_script{sha256,bytes}`,
`cases`, `inputs{sha256,bytes}`, `fixture_base: fixtures/projects`); кейсы — плоские JSON
(`id`, `tool: "api"`, `fixture`, `args`, `expect{ok,result}`, `reference_result`).

Фикстуры — **свои маленькие проекты**: `fixtures/projects/corpus/engine_kb/class_api/<variant>/`
с `project.godot` и `.agent_history/godot_api_cache.json` (несколько десятков строк, не 2 МБ).
Обязательное покрытие (≥18 кейсов):
- полная цепочка `Node2D → CanvasItem → Node → Object` с методами/свойствами/сигналами на разных уровнях;
- перекрытие имени метода в двух классах (докажи `setdefault`: побеждает ближний);
- старый кэш без `signatures` (`signature: ""`) и кэш с `signatures` (точная строка);
- битая арность (`"methods": {"foo": "x"}` или `[1]`) → `-1/-1`;
- `inherits: null` (корень), цикл `A→B→A` (guard + предел);
- класса нет в существующем кэше → `found: false`, `unavailable: []`;
- falsy-запись `{"Some": {}}` → `found: false` (это `bool(record)`, а не «пустой класс»);
- нет кэша вовсе (проект без `.agent_history`) → `unavailable: [{api_cache, no_cache}]`;
- кэш с `classes: {}` и кэш с мусором (не JSON / список вместо объекта) → `no_cache`;
- пустой `class_name` и отсутствующий `class_name` → `invalid_input`;
- идемпотентность (два вызова подряд — байт-в-байт), отсутствие записи на диск (хеши фикстуры до/после).

**3. Спека и красные тесты.** `python/modules/engine_kb/class_api/tests/test_core.py` (чистые правила),
`tests/test_app.py` (поддельный порт `api_cache` + корпус через `app.call`), `tests/py/integration/test_api.py`
(`build_agent(project_root=…, profile='headless')`, `agent.call('api', case['args'])` == `case['expect']`,
плюс `MODULE.provides_tools == ('api',)`, `requires_ports == ('api_cache',)`, карточка `api.json` есть).
Сначала — красные (инструмента нет).

**4. Код** по §2.1–§2.2 (сначала `inheritance.py` + домен, потом `app.py`, потом `tools.py`/`module.py`).
`app.py` ≤ 80 строк, весь `domain/` и `inheritance.py` — без IO (R-11).

**5. Контракт.** `python -B tools/gen_contract.py --write` → `contract/capabilities/api.json`,
прогон `--check` → **20** артефактов; все прежние карточки — байт-в-байт.

**6. Правки принятого** (§1, ровно четыре пункта) — после того как `api` уже отвечает; каждая правка
с бэкапом байт и обратной проекцией sha256.

**7. Двойной прогон:** non-live (`2473` + новые), `snapshot_diff` (`531` + новые кейсы, строка нового
корпуса — в отчёт), `selfcheck engine_kb.class_api`, `selfcheck` трёх соседей (`126/37`, `136/62`, `315/65`
без сдвига), `lint_arch`/`check_limits`, `security_audit`, `tests/py/live` (всё ещё 3).

**8. Записи:** лист → этап 6 «готово к независимому аудиту, не принято», `docs/parity.md` (строки 42–44
области `engine_kb` — строка `api`), `docs/tests-map.md`, `docs/PROGRESS.md`, `docs/WORKLOG.md`.
Шапку «принято/ported», этап 7 и `_audit-handoff.md` — **не писать и не править**.

## §4 Решения, которые уже приняты (не пересматривать)

1. **Имя `api`.** `class_api` — это id механики, а не имя инструмента. Свободно, коротко, совпадает
   с эталонным CLI (`api <Class>`) и с живым MCP-инструментом.
2. **Нет глобального кэша.** Эталон держит `_cache` в модуле и может отдать устаревшее в пределах
   процесса; порт читает факт на каждый вызов. Это осознанный отказ от кэша в пользу идемпотентности —
   фиксируется в листе в разделе «Решения по ходу».
3. **Только чтение.** `save_cache`, `_migrate_legacy_addon_cache`, `api_cache_refresh` — не портируются
   в этом срезе: запись в проект и миграция файлов это отдельная механика с WAL/preview.
4. **`found = bool(record)`.** Не «ключ есть» — эталон на falsy-записи говорит «класса нет», и это
   ловится кейсом.
5. **Сортировка.** `methods`/`properties`/`signals` сортируются по имени: у эталона порядок зависит
   от порядка ключей в JSON, детерминизм результата важнее буквального порядка.
6. **`-1` вместо исключения.** `_fmt_method` при битой арности печатает просто имя; в типизированном
   результате это `min_args = max_args = -1` («арность неизвестна»), иначе поле не описать честно.
7. **Версия кэша — только при непустых `classes`** (как `get_cached_version`): нет классов → `""`.
8. **Никаких новых портов/файлов аддона.** `api_cache` уже есть; бандл-кэш не заводим.

## §5 Доказательства, которые ты обязан собрать

**Мутации** (каждая — байтовый бэкап, `sha256` до/после, одна за раз, обязательный красный прогон):

| # | Мутация | Куда | Что обязано покраснеть |
|---|---|---|---|
| D1 | `found` всегда `True` | `class_api/domain/core.py` | кейсы «класса нет», falsy-запись |
| D2 | убрать сортировку (`sorted(...)` → `list(...)`) | `class_api/domain/core.py` | кейс с двумя методами в обратном порядке |
| D3 | снять guard циклов в `resolve_chain` | `engine_kb/shared/inheritance.py` | кейс `A→B→A` (зависание/дубли) |
| D4 | `collect_members` только по своему классу (не по цепочке) | `inheritance.py` | кейс с методами у родителя |
| D5 | игнорировать `signatures` | `inheritance.py` | кейс с сигнатурами |
| D6 | битая арность → `0/0` вместо `-1/-1` | `class_api/domain/core.py` | кейс битой арности |
| D7 | `unavailable` всегда `[]` | `class_api/app.py` | кейс «нет кэша» |
| D8 | `cache_version` всегда `""` | `class_api/app.py` | любой кейс с `godot_version` |

**Подложки:**
- P1 — `ToolSpec.required` без `'found'`: юнит-тесты зелёные, краснеет **только** `gen_contract --check`
  (так же было в C.8/C.9 — это доказательство, что гейт живой).
- P2 — `class_api/app.py` импортирует чужой `domain/` (например `from python.modules.verification...`):
  краснеет `tools/lint_arch.py` (R-11).
- P3 — `inheritance.py` получает `import pathlib`: краснеет `lint_arch` «domain/ запрещает IO-модуль».

**Обратная проекция:** список всех изменённых/добавленных файлов со `sha256` и байтами; отдельно —
доказательство, что `api_cache_store.classes()` не изменился по поведению (тот же путь, те же фолбэки),
и что принятые `tscn_lint`/`gd_lint`/`verify`/`scene_model` остались байт-в-байт.

**Гигиена:** дерево = 2170 + новые файлы (не больше), `.gd.uid` 83, `__pycache__`/`.pytest_cache`/
`.bak|tmp|orig`/`zz_*` — 0, временных скриптов в репозитории нет.

## §6 Стоп-условия (останавливайся и спрашивай)

- Понадобилось менять поведение `ApiCacheStore.classes()` или трогать `verification/*/domain/`.
- Проекция требует полей, которых нет в эталоне (например «список параметров по отдельности»), —
  значит срез расширяют, а не «додумывают».
- Хочется завести бандл-кэш аддона, чтобы «работало без проекта».
- В корпусе не получается стабильный результат без снятия `_cache` — это сигнал, что фикстуры
  переиспользуют проект; разводи по разным проектам.
- Числа соседей (`126/37`, `136/62`, `315/65`) поехали.

## §7 Что будет проверять аудитор (готовься к этому)

1. **Своя пересъёмка корпуса** своим скриптом через `gd_api_cache` со сбросом `_cache` перед каждым
   кейсом: `reference_result` должен совпасть, и `expect.result` должен быть проекцией **моей**, а не твоей.
2. **Дифференциал шире корпуса:** `api` против эталона на всех `godot_api_cache.json` в `fixtures/**`
   (включая кэши C.8-корпуса `api`, `api_broken`, `api_falsy`) и на реальном 2 МБ кэше из temp-копии;
   каждое расхождение — либо баг, либо документированная граница (`unavailable` вместо RC_ERROR,
   сортировка, `-1`).
3. **Свои мутации** (мой набор, не твой D1–D8) с байтовым бэкапом и сверкой `sha256`.
4. **Инвентарь:** `gen_contract --check` = **20**, в `contract/capabilities` 21 файл (20 + `_template`),
   `context.gather` — **19** имён с `api: read`, `# verb:` = 6, `verbs_version: 3`.
5. **Принятые механики:** те же числа selfcheck и те же sha256 `domain/` (список в §0).
6. **Гигиена и live** (3 теста, `.gd.uid` 83, debris 0), затем — записи.

## §8 Финальный прогон и записи

Один отчёт в листе + запись в WORKLOG: non-live (число, время, `collect`), `snapshot_diff` (число
и строка нового корпуса), `selfcheck engine_kb.class_api` таблицей + `reports/selfcheck/engine_kb.class_api.json`,
`gen_contract --check` (20), `lint_arch`/`check_limits`, `security_audit`, live, дерево/`.gd.uid`/debris,
плюс §5-доказательства со `sha256`.

Пишешь: лист (этап 6, «готово к независимому аудиту, не принято»), `docs/parity.md`, `docs/tests-map.md`,
`docs/PROGRESS.md`, `docs/WORKLOG.md`. Не пишешь: `docs/porting/_audit-handoff.md`, шапки
«принято/ported», этап 7, `contract/editor_verbs.json`, `python/kernel/schema.py`, `tools/lint_arch.py`,
`tools/gen_contract.py`, `tools/security_audit.py`, `tools/snapshot_diff.py`.

- Среда: PowerShell; команда дольше ~30 с умирает — дроби; в каждой команде `python -B`;
  stderr считай ошибкой — пиши вывод в файл (PowerShell-редирект ломает UTF-8: логируй изнутри Python);
  JSON только через `--args-file`; две мутации одновременно запрещены; подложку `.gd` убирай вместе с `.uid`.
