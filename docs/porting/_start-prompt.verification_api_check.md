# C.12 — `verification.api_check` (инструмент `api_check`: `self.*` и `connect()` против кэша Godot API)

Ты — **портер**. Аудитор принимает твою работу своими прогонами, поэтому доказательства важнее
«сделано»: числа, sha256, восстановление байт. Ты не ставишь этап сам, не пишешь шапку
«выполнено/принято», не правишь `docs/porting/_audit-handoff.md` и не закрываешь срез.

Перед началом прочитай, в этом порядке: `AGENTS.md` → `RULES.md` (R-01…R-22) →
`docs/architecture.md` → `docs/PORTING.md` → `docs/parity.md` (строка 68 — `check` (API), и 114–118
про вклады) → `docs/tests-map.md` → `docs/PROGRESS.md` (строка 58) → `docs/porting/_template.md` →
соседние листы `docs/porting/verification.gd_lint.md`, `verification.check.md`,
`engine_kb.class_api.md`, `verification.tscn_lint.md` → хвост `docs/WORKLOG.md` (3 последние сессии)
→ `docs/security/invariants.md` → ADR-0004, ADR-0006, ADR-0009.

## §0 База (снято аудитом, сессия 63, 2026-10-31 — не пересчитывать)

Состояние дерева `D:\vajno\Godot\agent-rebuild\addons\godot_agent` на момент выдачи промпта:

- `pytest python/modules tests/py --ignore=tests/py/live` → **2601 passed**, junit `tests=2601 failures=0
  errors=0 skipped=0` (62.4 с), stderr 0; `--collect-only` — **93** файла / 2601 тест (совпадает с junit).
  `tests/py/live` → **3 passed** (~23 с), stderr 0.
- `tools/snapshot_diff.py` → **557 кейсов, 0 расхождений** (`engine_kb/class_api` 26/26,
  `verification/check` 62/62, `verification/gd_lint` 37/37, `verification/tscn_lint` 65/65).
- `tools/gen_contract.py --check` → **20** артефактов (21 файл в `contract/capabilities/` с `_template.json`).
- selfcheck: `engine_kb.class_api` unit 128 / corpus 26, `verification.gd_lint` 126/37,
  `verification.check` 136/62, `verification.tscn_lint` 315/65 — все `ok`; layers **498**,
  limits **498/0**, security ok.
- Дерево: **2233** файла (2234 вместе с двумя служебными в `.godot/`; счёт —
  `python -B` обходом без `__pycache__`/`.pytest_cache`/`.godot`, не `Get-ChildItem`),
  `.gd.uid` **83**, debris 0. Листов механик 22, промптов 30
  (`_start-prompt*`), правил 22, PROGRESS — 44 строки (20 на этапе 7, `editing.symbol_rename` — 6,
  23 на нуле). Мост: 6 примитивов, `verbs_version 3`.
- Цели этого среза: +1 инструмент (`api_check`), +1 карточка (`gen_contract --check` = **21**,
  файлов 22), инвентарь `context.gather` 19 → **20** имён, листов 23, промптов 31, корпус
  `verification/api_check` ≥ 24 кейса.

Замороженные гейты (хеши сверять, не «помнить»): `python/kernel/schema.py` `629FCE54E6FE…` (147 строк,
CRLF), `tools/lint_arch.py` `1FAD8E7470D5…`, `tools/gen_contract.py` `FA7E6E91C872…`,
`tools/security_audit.py` `2CF0D7F6B1AF…`, `tools/snapshot_diff.py`, `contract/editor_verbs.json`
`CDAF8D23A6BF…`, `editor/bridge/verbs/scene/scene_executor.gd` `B7AFF592B75D`.

Принятые артефакты, которые обязаны остаться байт-в-байт (аудитор сверяет по sha256):

| Файл | Байт | sha256 (12) |
|---|---|---|
| `python/formats/tscn.py` | 13960 | `9D69AFECDCC0` |
| `python/modules/verification/tscn_lint/domain/core.py` | 16251 | `F23EDD5A4ED9` |
| `python/modules/verification/tscn_lint/app.py` | 2634 | `50F77ED6B766` |
| `python/modules/verification/gd_lint/domain/core.py` | 6547 | `1873E0A9E687` |
| `python/modules/verification/gd_lint/app.py` | 1619 | `02B8960A161F` |
| `python/modules/verification/check/domain/core.py` | 4345 | `F84018B8EE08` |
| `python/modules/verification/check/app.py` | 2485 | `F1506108E191` |
| `python/modules/verification/check/tools.py` | 1731 | `65974F15AA55` |
| `python/modules/verification/shared/source_text.py` | 489 | `56C397CFC171` |
| `python/modules/verification/shared/check_kind.py` | 868 | `34856E8B3ECC` |
| `python/modules/engine_kb/class_api/domain/core.py` | 1059 | `888BCB485E52` |
| `python/modules/engine_kb/class_api/tools.py` | 1960 | `5FFFE966F159` |
| `python/modules/engine_kb/class_api/app.py` | 936 | `E7CDDA5F4E96` |
| `python/modules/engine_kb/shared/inheritance.py` | 1442 | `5A9BAD5013FB` (LF 38 — только читать) |
| `python/substrate/store/api_cache_store.py` | 3812 | `352F9E9B6BB9` |

Эталон этого среза — старый плагин `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent`:

- `python/godot_tools/gd_api_check.py` — **9137 B, 201 LF, 0 CRLF**, sha256 `B9E0DF9F604C…`
  (`check_api_usage` 145–201, `MAX_PROBLEMS = 6` на 17, `_mask` 39–98, `_local_symbols` 101–110,
  `_find_matching_paren` 113–126, `_count_top_level_args` 129–142, регулярки 26–36);
- вызов эталона — `python/tools/agent_bridge.py:1196–1197` (`text_linted` → `gd_lint` + `gd_api_check`),
  файл 142 171 B, sha256 `a9b1ad832fd0…`, коммит `ba0535d4…`;
- кэш: `<project>/.agent_history/godot_api_cache.json` или бандл
  `agent_api_cache/default_api_cache.json`, запись `{"godot_version": str, "classes": {...}}`.

Git в `agent-rebuild` нет намеренно; единственный git — старый плагин (две чужие untracked-строки
не удалять). Godot: `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`.

Правила среды: команды PowerShell живут ~30 с — длинные прогоны запускай в фоне и опрашивай;
пиши `python -B`; stderr всегда в файл; многострочные отчёты пиши **изнутри Python** (PowerShell
ломает UTF-8 при перенаправлении); JSON-аргументы передавай файлом; **две мутации одновременно
запрещены**; `--collect-only` сверяй с junit; живой прогон создаёт `.gd.uid` в корпусах — удаляй
ровно сгенерированные, 8 исторических (`fixtures/parity/gdscript/`, 2026-10-27) не трогай.


> Проверка перед стартом (30 секунд): `python -B tools/gen_contract.py --check` должен дать
> `артефактов 20`, а `python -B -c "import python.modules.engine_kb.class_api.module"`
> (из корня репозитория) — не падать. Если падает с `SyntaxError` в
> `engine_kb/shared/inheritance.py` — файл затёрт мусором прошлой сессии: восстанови
> побайтово из `%TEMP%\opencode\c11-resume-20261031\submitted\python\modules\engine_kb\shared\inheritance.py`
> (1442 B, `5A9BAD5013FB`, LF 38) и **скажи об этом в ответе**, а не молча.

## §1 Границы среза

Механика **`verification.api_check`** — владелец инструмента **`api_check`**. Имя свободно: в
текущем инвентаре (19 имён) его нет, карточки `contract/capabilities/api_check.json` нет. Модуль
читает **только существующий порт `api_cache`** (принят C.11, ADR-0009) и ничего не пишет.
Скелет `python/modules/verification/api_check/` уже лежит (`app.py`, `module.py`, `tools.py`,
`domain/core.py`, `tests/test_core.py`); его комментарии `# tool: check` и
`# contributes: check (API)` **устарели** — заполняешь папку на месте под фактическую роль и
записываешь расхождение в лист, раздел «Решения по ходу».

В скоупе:

- `python/modules/verification/api_check/{tools.py, module.py, app.py, domain/*.py, tests/*.py}`;
- корпус `fixtures/corpus/verification/api_check/` (кейсы + `manifest.json`) и фикстуры
  `fixtures/projects/corpus/verification/api_check/<variant>/{project.godot,.agent_history/godot_api_cache.json}`
  (путь `fixture` пишется как `../corpus/verification/api_check/<variant>`, иначе `snapshot_diff`
  не найдёт фикстуру);
- лист `docs/porting/verification.api_check.md` (создать первым, этап 1).

Вне скоупа (не трогать даже «на минутку»):

- агрегатор `verification.check` — **вклад `api_check` в `verify` в этом срезе не делается**:
  он меняет ожидания 62 принятых кейсов `verify` и требует их полной пересъёмки. Это отдельный
  срез (кандидат C.13), запиши решение в лист;
- `verification.gd_lint`, `verification.tscn_lint`, `verification.check`, `engine_kb.*`,
  `python/formats/*`, `python/kernel/*`, `python/substrate/*` (все — байт-в-байт по таблице §0);
- `verification.headless`, `runtime_checks`, `action_judge`, `engine_kb.engine_info`,
  `engine_kb.api_cache_refresh`, CLI `agent_bridge.cmd_check`, WAL/undo/редактор;
- `contract/editor_verbs.json`, `python/kernel/schema.py`, `tools/lint_arch.py`,
  `tools/gen_contract.py`, `tools/security_audit.py`, `tools/snapshot_diff.py`.

Разрешённые правки вне новой папки — ровно три (каждую перечислить в листе и в WORKLOG, аудитор
делает обратную проекцию по sha256):

1. `fixtures/corpus/context/gather/001-all-sections.json` — добавить `api_check` с `"read"` в
   `sections.tools.names` и `effects`, `count` 19 → 20 (кейс — эталон инвентаря, порядок имён
   сортированный);
2. `tests/py/integration/test_tscn_lint.py:46–59` — список из 19 имён дополнить `api_check`
   (этот тест пинит инвентарь);
3. тесты, которые пинят число карточек/имён (`test_verify_contract.py`, `test_api_contract.py`,
   `test_gd_lint.py`, `test_scene.py`, `test_node.py`, `test_functions_contract.py`,
   `test_usages_contract.py`, `test_tscn_lint.py` — там, где перечислены имена инструментов) —
   правится только этот список/число, остальные строки байт-в-байт.

Плюс обычные записи среза: лист механики, `docs/parity.md:68`, `docs/tests-map.md`,
`docs/PROGRESS.md` (строка 58), `docs/WORKLOG.md`. `docs/porting/_audit-handoff.md` не править.


## §2 Контракт и раскладка

### 2.1 ToolSpec — дословно

```python
# python/modules/verification/api_check/tools.py
from python.kernel.limits import READ_TEXT_MAX_BYTES  # kernel/limits.py = 4 * 1024 * 1024:
                                                     # переиспользуй, вторую константу не заводи
from python.kernel.tool_spec import ToolSpec

ARGS = {
    'type': 'object', 'required': ['path', 'content'], 'additionalProperties': False,
    'properties': {
        'path': {'type': 'string', 'minLength': 1},     # res:// путь: только эхо и политика
        'content': {'type': 'string'},                  # текст .gd как данные, файл не читается
    },
}
RESULT = {
    'type': 'object',
    'required': ['path', 'problems', 'checked', 'base_class', 'unavailable'],
    'additionalProperties': False,
    'properties': {
        'path': {'type': 'string', 'minLength': 1},
        'problems': {'type': 'array', 'items': {'type': 'string'}},
        'checked': {'type': 'boolean'},
        'base_class': {'type': 'string'},
        'unavailable': {'type': 'array', 'items': {
            'type': 'object', 'required': ['kind', 'reason'], 'additionalProperties': False,
            'properties': {'kind': {'type': 'string', 'minLength': 1},
                           'reason': {'type': 'string', 'minLength': 1}},
        }},
    },
}
API_CHECK = ToolSpec(
    name='api_check',
    description='Сверить self.* и connect() в тексте .gd с кэшем Godot API; честно сказать, что проверено.',
    args=ARGS, result=RESULT, effects='read', idempotent=True,
    errors=('invalid_input',), availability='*', cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES},
)
TOOLS = (API_CHECK,)
```

Смысл полей:

- `path` — эхо нормализованного `res://`-пути (как в C.8/C.9); файла может не быть, `fs` не нужен;
- `problems` — плоские строки в порядке эталона, **не больше 6**, без повторов текста;
- `checked` — `true` только если сравнение реально было (есть `extends`, есть кэш, у базового класса
  есть члены). «Пусто и не проверял» обязано выглядеть как `checked: false`, а не как «чисто»;
- `base_class` — идентификатор из `extends` (`''`, если его нет), ровно `_EXTENDS_RE.group(1)`;
- `unavailable` — почему не проверено: `[{'kind': 'source', 'reason': 'no_extends'}]`,
  `[{'kind': 'api_cache', 'reason': 'no_cache'}]`,
  `[{'kind': 'base_class', 'reason': 'base_not_in_cache'}]`; при `checked: true` — `[]`.

### 2.2 Где что живёт (R-02, R-11)

- `api_check/domain/mask.py` — `mask(text, strings, comments)`: копия текста **той же длины** с
  пробелами вместо содержимого строк и/или комментариев (позиции и номера строк сохраняются).
  Точная копия поведения эталонного `_mask` (39–98): тройные кавычки, экранирование,
  «пробел вместо всего, кроме `\n`».
- `api_check/domain/core.py` — `local_symbols(masked)`, `find_matching_paren(text, i)`,
  `count_top_level_args(masked, lo, hi)`, `check(text, classes)` →
  `(problems, base_class, checked, reason)`. Регулярки объявлений — дословно из эталона, вместе с
  `[^\S\n]*`: это защита от O(n²), а не косметика (на 200 КБ — 6.7 с против мгновенного).
  `re` в `domain/` разрешён; `os/pathlib/socket/subprocess` запрещены (R-11).
- `api_check/app.py` — только оркестрация (≤ 80 строк): `validate` → `path` (`res://`,
  `normalize_rel`, `ctx.path_policy.deny_reason`) → лимит байт `content` →
  `ctx.port('api_cache').snapshot()` → `resolve_chain`/`collect_members` из
  `python/modules/engine_kb/shared/inheritance.py` → `core.check(...)` → Result.
  Ошибки только `invalid_input`/`denied`; исключений наружу нет.
- `api_check/tools.py` — ToolSpec выше; `api_check/module.py` —
  `ModuleSpec(id='verification.api_check', version='0.1.0', kernel_api='^1', godot='^4.6',
  environment='*', provides_tools=('api_check',), requires_ports=('api_cache',),
  capabilities=('verification.api_check',), entrypoints={'call': call}, corpus='corpus')`.
- Переиспользование: `engine_kb/shared/inheritance.py` (`resolve_chain`, `collect_members`) — это
  **shared**, а не чужой `domain/`; импорт разрешён и запланирован ещё в C.11 (файл 1442 B, LF 38 — только
  читать). Импорты `verification/*/domain/` и `engine_kb/*/domain/` запрещены.

### 2.3 Проекция «эталон → порт»

| Эталон (`gd_api_check`) | Порт (`api_check`) |
|---|---|
| `check_api_usage(project_root, text, path='', addon_dir=None)` | `api_check(path, content)`: текст приходит данными, `path` только эхо (в эталоне он тоже не используется) |
| нет `extends` → `[]` | `problems: []`, `checked: false`, `base_class: ''`, `unavailable: [{source, no_extends}]` |
| `has_cache()` ложно → `[]` | `checked: false`, `unavailable: [{api_cache, no_cache}]` |
| базовый класс не в кэше / у него пусто → `[]` | `checked: false`, `unavailable: [{base_class, base_not_in_cache}]`, `base_class` — имя |
| сравнение прошло | `checked: true`, `unavailable: []`, `problems[:6]` |
| дедуп по тексту сообщения, порядок: `self.*`/`super.*` в порядке текста → `self.connect(...)` → `connect(...)` | дословно так же (два прохода по `masked_comments` в этом порядке) |
| `MAX_PROBLEMS = 6` | то же число, отдельной константой в `domain/core.py` |
| сообщение об арности: `строка %d: %s.%s(...) вызван с %d аргумент(ами), а у %s.%s их должно быть %s`, `rng = str(min)`, если `min == max`, иначе `%d-%d` | дословно, включая оба варианта диапазона |
| сообщение о неизвестном члене: `строка %d: %s.%s — такого %s нет у %s и он не объявлен в этом скрипте (возможно, опечатка или несуществующий в этой версии Godot API)`, `kind` = `метода` при `(`, иначе `свойства` | дословно |
| сообщение о сигнале: `строка %d: connect("%s", ...) — сигнала «%s» нет у %s и он не объявлен в этом скрипте` | дословно |
| глобальный `_cache` и `addon_dir` эталона | нет: `ctx.port('api_cache').snapshot()` (ADR-0009), состояние на вызов не удерживается |

### 2.4 Якоря эталона (файл 9137 B, 201 LF, sha256 `B9E0DF9F604C…`)

- 17 `MAX_PROBLEMS = 6`.
- 26–36 регулярки: `_EXTENDS_RE`, `_FUNC_DEF_RE`, `_FIELD_DEF_RE`, `_SIGNAL_DEF_RE`,
  `_ENUM_BLOCK_RE` (`(?ms)`, `\s` внутри скобок остаётся), `_SELF_CALL_RE` (`\b(self|super)\.(\w+)`),
  `_CONNECT_SELF_RE`, `_CONNECT_BARE_RE` (`(?<![.\w])connect\(`).
- 39–98 `_mask(text, mask_strings, mask_comments)` — длина не меняется, `\n` не маскируется,
  escape-пары маскируются вместе с символом, `#` до конца строки.
- 101–110 `_local_symbols(masked_full)` → `(funcs, fields, signals)`; поля включают `const`/`var`
  с `@export`-аннотациями и члены `enum { A, B }` (после `=` обрезаются).
- 113–126 `_find_matching_paren`, 129–142 `_count_top_level_args` (`([{` наращивает глубину, `,`
  на глубине 0 делит; пустая строка внутри → 0).
- 145–201 `check_api_usage`: `_EXTENDS_RE.search` → `has_cache` → `collect_members` →
  `masked_full = _mask(text, True, True)`, `masked_comments = _mask(text, False, True)` →
  `known_members = set(methods) | props | local_funcs | local_fields`,
  `known_signals = signals | local_signals | local_fields` → проход `_SELF_CALL_RE`
  (член известен: проверка арности только если имя есть в `methods`; незакрытая скобка `-1` →
  без проверки арности; иначе — сообщение о неизвестном члене) → проход сигналов →
  `problems[:MAX_PROBLEMS]`.
- Вызов эталона: `agent_bridge.py:1196–1197` — `text_linted` и `.gd` → `gd_lint.lint_gdscript(text)` +
  `gd_api_check.check_api_usage(root, text, path, addon_dir)`. Агрегация нам не нужна (§1).

### 2.5 Вход и ошибки

- `path` обязан быть `res://…`, иначе `invalid_input`; далее `normalize_rel` и
  `ctx.path_policy.deny_reason(rel)` → `denied` (текст причины — из политики, не выдумывать).
  Файл не читается: `not_found` в этом инструменте не бывает, и это записано в листе.
- `content` не строка → `invalid_input` (схема ловит раньше); байт больше `READ_TEXT_MAX_BYTES`
  (4 MiB, `utf-8`) → `invalid_input` — как в C.8/C.9.
- Нет кэша, неизвестный базовый класс, отсутствие `extends` — **не ошибки**: `ok: true`,
  `problems: []`, `checked: false` + `unavailable`.
- Детерминизм: два вызова подряд дают идентичный ответ; кэш не пишется, `mkdir` нет, состояние
  между вызовами не удерживается.


## §3 Шаги

**1. Лист механики — первым.** `docs/porting/verification.api_check.md` по `_template.md`, статус
«этап 1», таблица старого кода (`gd_api_check.py:17,26–36,39–98,101–110,113–126,129–142,145–201`;
`agent_bridge.py:1196–1197` — вызов, не переносится), таблица старых тестов (прямых тестов у
`gd_api_check` в старом плагине **нет** — запиши это, а `repro_check_*.py` относятся к агрегатору,
не к этому срезу), раздел «Решения по ходу» с расхождением из §1. Своя строка в `docs/PROGRESS.md`
(строка 58) — 0 → 1.

**2. Корпус — до кода, снят с эталона.** Одноразовый скрипт только в разрешённой temp-папке
(в репозиторий не класть):
`sys.path` → старый `python/`, `python/godot_tools`, `python/parsers`, `python/tools`;
`import gd_api_cache, gd_api_check`; перед **каждым** кейсом
`gd_api_cache._cache['root'] = None; gd_api_cache._cache['classes'] = {}; gd_api_cache._cache['godot_version'] = ''`;
вызов `gd_api_check.check_api_usage(project_root, text, path, None)` на временной копии проекта.
Фикстуры — свои: `fixtures/projects/corpus/verification/api_check/<variant>/project.godot` +
`.agent_history/godot_api_cache.json`. `reference_result` = сырой список строк, `expect.result` =
проекция §2.1. Манифест — по образцу `fixtures/corpus/verification/tscn_lint/manifest.json`:
`schema_version`, `captured_at`, `module`, `reference_commit ba0535d4…`,
`reference{file, function: check_api_usage:145-201, sha256, bytes: 9137}`, `capture`,
`capture_script{sha256, bytes}`, `contract_refusals`, `cases`, `inputs` (sha256+bytes каждого файла
фикстуры), `fixture_base: fixtures/projects`.

Обязательное покрытие (≥ 24 кейса): чистый скрипт; опечатка в методе `self.nope()`;
опечатка в свойстве `self.nope`; `super.nope`; лишние аргументы; мало аргументов; метод ровно с
одним допустимым числом аргументов (`str(min)`-ветка); локальные `func`/`var`/`const`/`@export`/
`enum`-член/signal — не считаются ошибкой; `connect("known")`; `connect("unknown")`;
`self.connect("unknown")`; маскирование: `self.fake()` в комментарии и в строке, тройные кавычки;
`self.f(` без закрывающей скобки; вложенные вызовы в аргументах (`self.f(self.a(1, 2), 3)`);
член из родительского класса цепочки; сигнал родителя; больше 6 проблем → обрезка; один и тот же
текст дважды → дедуп; нет `extends`; `extends` на скрипт проекта (нет в кэше); пустой кэш
(`classes: {}`); нет кэша вовсе; битый JSON кэша; не-`res://` путь; `res://addons/...` → `denied`;
`content` не строка; `content` больше 4 MiB; идемпотентность.

**3. Красные тесты** (сначала падают): `api_check/tests/test_core.py` (маскирование, локальные
символы, аргументы, сообщения — дословно), `test_mask.py`, `test_app.py` (фейковый порт
`api_cache` с `snapshot()`; отказы до любого порта; лимит байт), `tests/py/integration/test_api_check.py`
(`build_agent(project_root=..., profile='headless')`, диспетчеризация всех кейсов корпуса,
read-only по sha256 фикстуры, идемпотентность, в `ok: False` нет абсолютного пути),
`tests/py/contract/test_api_check_contract.py` (ToolSpec/карточка/схема результата).

**4. Код** в порядке `domain/mask.py` → `domain/core.py` → `app.py` → `tools.py`/`module.py`.
`app.py` ≤ 80 строк, `domain/` без `os/pathlib/socket/subprocess`, без импортов чужих `domain/`.

**5. Контракт:** `python -B tools/gen_contract.py --write` → `contract/capabilities/api_check.json`;
`--check` → «артефактов 21, расхождений нет», остальные 20 карточек байт-в-байт.

**6. Разрешённые правки** (§1) — только после того, как `api_check` отвечает: `context.gather`
19 → 20 имён, инвентарь в `test_tscn_lint.py:46–59`, тесты с числом карточек/имён.

**7. Двойной прогон:** non-live (2601 + новые, junit = collect), `snapshot_diff` (557 + новые),
`selfcheck verification.api_check`, соседи `verification.gd_lint` 126/37, `verification.check`
136/62, `verification.tscn_lint` 315/65, `engine_kb.class_api` 128/26, `tools/lint_arch.py`,
`tools/check_limits.py`, `tools/security_audit.py`, живое = **3** (не больше и не меньше).

**8. Записи:** лист этап 6 («готово к независимому аудиту, не принято»), `docs/parity.md:68`
(`check` (API) → `verification.api_check`, описание среза), `docs/tests-map.md` (новые файлы
тестов, размеры совпадают с фактом), `docs/PROGRESS.md` (строка 58 → 6 с числами),
`docs/WORKLOG.md` (запись среза). Этап 7 не ставить, «принято/ported» не писать,
`docs/porting/_audit-handoff.md` не трогать.


## §4 Решения, которые уже приняты (не пересматривать)

1. **Имя инструмента — `api_check`.** Занятые имена (`check`, `verify`, `gd_lint`, `api`…) не
   трогаем: `check` принадлежит принятому C.8, `verify` — C.9, `api` — C.11; дубль имени в
   `python/protocol/registry.py` отключает обоих владельцев (R-03).
2. **Вклад в `verify` отложен.** Иначе придётся переснимать 62 принятых кейса `verification.check`
   и править принятые `gd_lint`/`check` — это отдельный срез (кандидат C.13). В листе и WORKLOG
   записать явно, чтобы аудитор не считал это забывчивостью.
3. **Текст приходит данными** (`content`), как в C.8 `check`: файл не читается, порт `fs` не нужен,
   `not_found` невозможен. Так инструмент годится и для проверки ещё не записанного кандидата.
4. **Честность вместо молчания.** Эталон возвращает `[]` и в случае «чисто», и в случае «проверить
   нечем». Порт обязан различать это через `checked` + `unavailable` (три причины из §2.1).
   Пустой `unavailable` при `checked: false` — дефект.
5. **Паритет важнее «улучшений».** `MAX_PROBLEMS = 6`, дедуп по тексту, порядок сообщений,
   дословные строки, отсутствие проверки `path` внутри эталона — всё сохраняется. Новые идеи
   (проверка `super` отдельно, сигналы у не-`self`, `await`, аргументы по именам) — только в лист
   «Долги», не в код.
6. **Маскирование — дословно.** `[^\S\n]*` в регулярках объявлений остаётся: это защита от
   O(n²) на больших файлах. `re` в `domain/` разрешён, IO-модули — нет (R-11).
7. **Члены базового класса — по всей цепочке:** `resolve_chain` + `collect_members` из
   `engine_kb/shared/inheritance.py` (`5A9BAD5013FB`, LF 38 — только читать). Это ровно то, что
   делает эталонный `gd_api_cache.collect_members` внутри.
8. **Один порт, никакого состояния.** `ctx.port('api_cache').snapshot()` (ADR-0009) на каждый
   вызов; глобального кэша, как `_cache` в эталоне, в порту нет.

## §5 Доказательства (что положить в лист)

Мутации — по одной, каждая со байтовым бэкапом и сверкой sha256 до/после, scope
`python/modules/verification/api_check` + `tests/py/integration/test_api_check.py` +
`tests/py/contract/test_api_check_contract.py`:

| # | Мутация | Что обязано покраснеть |
|---|---|---|
| M1 | `MAX_PROBLEMS` 6 → 1000 | кейс «больше 6 проблем» |
| M2 | убрать дедуп (`seen`) | кейс «один текст дважды» |
| M3 | не проверять арность | кейсы «лишние/мало аргументов» |
| M4 | не сообщать о неизвестном члене | кейсы опечаток метода/свойства |
| M5 | не проверять сигналы | кейсы `connect("unknown")` (оба варианта) |
| M6 | `_mask` не маскирует строки | кейсы со `self.fake()` в строке/тройных кавычках |
| M7 | `_mask` не маскирует комментарии | кейс со `self.fake()` в комментарии |
| M8 | `checked` всегда `true` | кейсы «нет extends» / «нет кэша» |
| M9 | `unavailable` всегда `[]` | те же кейсы |
| M10 | `known_members` без локальных символов | кейсы локальных func/var/enum |

Подложки: **P1** `ToolSpec.required` без `'checked'` — юнит-тесты молчат, ловит только
`tools/gen_contract.py --check`; **P2** `import os` в `api_check/domain/core.py` — ловит
`tools/lint_arch.py` («domain/ запрещает IO-модуль»); **P3** `app.py` читает кэш напрямую
(`from python.substrate...`) вместо порта — ловит `lint_arch`/`security_audit` (записать, какой
именно гейт сработал, и что юнит-тесты промолчали).

Обратная проекция: sha256+bytes каждого изменённого/добавленного файла; отдельно — доказательство,
что `verification.check`, `gd_lint`, `tscn_lint`, `engine_kb.class_api`, `inheritance.py`,
`api_cache_store.py`, `python/formats/*`, `python/kernel/*` остались байт-в-байт по таблице §0.

Гигиена: дерево = 2233 + новые файлы, `.gd.uid` 83, `__pycache__`/`.pytest_cache`/`.bak|tmp|orig`/
`zz_*` = 0, временных скриптов и логов в репозитории нет.

## §6 Стоп-условия

- понадобилась правка принятых механик, `inheritance.py`, `api_cache_store.py`, `kernel/*` — стоп,
  пиши в лист «Блокеры»;
- проекция требует поля, которого в эталоне нет, или теряет сообщение эталона — стоп
  (сначала сверить с аудитором, а не «додумать»);
- корпус нестабилен без сброса `_cache` — значит фикстуры делят один проект, переделать фикстуры;
- захотелось «заодно связать с `verify`» — это C.13, не этот срез;
- сдвинулись числа соседей из §3.7 — стоп.


## §7 Что будет проверять аудитор

1. **Своя пересъёмка корпуса с эталона** — свой скрипт (не твой), сброс `_cache` перед каждым
   кейсом, сравнение сырых `problems` с `reference_result` и своей независимой проекции с
   `expect.result`; отказы (`invalid_input`/`denied`) сверяются отдельно, потому что у эталона
   такого слоя нет.
2. **Дифференциал шире корпуса:** все `.gd` в `fixtures/**` (≈ 370 файлов) против эталона под
   кэшем своего проекта (где `.agent_history/godot_api_cache.json` есть; где нет — кейс попадает
   в `unavailable`), плюс реальный кэш старого плагина (`agent_api_cache/default_api_cache.json`,
   **2 004 630 B, 1488 классов**) на нескольких `.gd`. Границами считаются только поля, которых у
   эталона нет (`checked`, `unavailable`, `base_class`), и лимит 4 MiB; расхождение в `problems`
   — дефект.
3. **Свои мутации и подложки** (§5) с байтовым восстановлением и сверкой sha256.
4. **Инвентарь:** `gen_contract --check` = **21** артефакт (22 файла), `context.gather` = **20** имён
   с `api_check: read`, `# verb:` = 6, `verbs_version: 3`, `snapshot_diff` = 557 + новый корпус.
5. **Принятые механики без сдвига:** те же selfcheck-числа (126/37, 136/62, 315/65, 128/26) и те
   же sha256 `domain/` из §0; `classes()` и `snapshot()` в `api_cache_store.py` не изменены.
6. **Гигиена и live:** дерево = 2233 + новые, `.gd.uid` 83, debris 0, live = 3.

## §8 Финальный прогон и записи

Один отчёт — в лист `docs/porting/verification.api_check.md` + запись в `docs/WORKLOG.md`. Внутри:

- non-live: число passed, время, collect-файлы (junit = collect), stderr 0;
- `snapshot_diff`: общее число и строка нового корпуса;
- `selfcheck verification.api_check`: таблица + `reports/selfcheck/verification.api_check.json`;
- `gen_contract --check` (21), `lint_arch`, `check_limits`, `security_audit`, live 3;
- дерево / `.gd.uid` / debris, обратная проекция sha256, доказательства §5;
- границы среза и отложенное (вклад в `verify` → C.13).

Записи: лист (этап 6, «готово к независимому аудиту, не принято»), `docs/parity.md:68`,
`docs/tests-map.md`, `docs/PROGRESS.md` (строка 58), `docs/WORKLOG.md`. Не писать
«принято/ported», не ставить этап 7, не править `docs/porting/_audit-handoff.md`,
`contract/editor_verbs.json`, `python/kernel/schema.py`, `tools/lint_arch.py`,
`tools/gen_contract.py`, `tools/security_audit.py`, `tools/snapshot_diff.py`.

