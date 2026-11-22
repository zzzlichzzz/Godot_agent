# C.9 — `verification.check` (агрегатор `verify` поверх вкладов `gd_lint` и `tscn_lint`)

Ты — портер. Продолжаешь перенос Godot-агента по эталону из старого плагина
`D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\` (HEAD `ba0535d4`).
Ты **не аудитор**: этап сам себе не ставишь, шапку «выполнено/принято» не пишешь,
`docs/porting/_audit-handoff.md` не правишь. Этап 7 ставит аудитор своими прогонами.

Обязательное чтение до кода: `AGENTS.md` → `RULES.md` (R-01…R-22) → `docs/architecture.md` →
`docs/PORTING.md` → `docs/parity.md` (строка 65) → `docs/tests-map.md` → `docs/PROGRESS.md`
(строка `verification.check`) → `docs/porting/_template.md` → лист соседа
`docs/porting/verification.tscn_lint.md` (эталон того, как оформляется срез) →
`docs/WORKLOG.md` (последние 3 сессии) → `docs/security/invariants.md` →
`docs/adr/` (ADR-0004 «вклады», ADR-0006 «контракт»).

## §0 База (снято аудитом, сессия 60, 2026-10-30 — не пересчитывай «на глаз»)

- pytest non-live (`python -B -m pytest python/modules tests/py --ignore=tests/py/live -q
  -p no:cacheprovider`) → **2337 passed**, 0 fail/err/skip; `--collect-only` — 2337 в **82** файлах.
- `tests/py/live` → **3 passed** (~17 с; Godot `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`).
  Живой прогон создаёт `.gd.uid` в корпусах: удаляй ровно сгенерированные, 8 старых
  (`fixtures/parity/gdscript/`, 27.10.2026) не трогай.
- `python -B tools/snapshot_diff.py` → **469** кейсов, 0 расхождений.
- `python -B tools/gen_contract.py --check` → **18** артефактов, 0 расхождений (цель среза — **19**).
- `python -B tools/lint_arch.py` / `tools/check_limits.py` → **492** файла, 0 нарушений, 0 предупреждений.
- `python -B tools/security_audit.py` → ok.
- selfcheck: `verification.tscn_lint` ok (unit 315, corpus 65), `verification.gd_lint` ok (unit 37,
  corpus 37), `scene_model.*` ok.
- Дерево — **2034** файла, `.gd.uid` **83**, `__pycache__` 0, `.pytest_cache` 0,
  `.bak/.tmp/.orig` 0, `zz_*` 0. Правил 22, промптов 28 (+1 = 29), листов механик 19 (+1 = 20),
  `contract/capabilities` 18 карточек + `_template.json`, механик 44 → **18** на этапе 7,
  1 на этапе 6 (`editing.symbol_rename`), 25 на нуле (`verification.check` — как раз этот срез).
- Мост не трогаем: `contract/editor_verbs.json` sha `CDAF8D23A6BF…`, `verbs_version: 3`,
  6 примитивов (`# verb:` ровно 6), `protocol: 1`; `editor/bridge/verbs/scene/scene_executor.gd`
  `B7AFF592B75D…`.
- Замороженные файлы (менять нельзя): `python/kernel/schema.py 629FCE54E6FE…` (147 строк),
  `tools/lint_arch.py 1FAD8E7470D5…`, `tools/gen_contract.py FA7E6E91C872…`,
  `tools/security_audit.py 2CF0D7F6B1AF…`, `tools/snapshot_diff.py`.
- Принятые артефакты, которые нельзя сломать: `python/formats/tscn.py 9D69AFECDCC0…` (345 строк),
  `python/formats/tscn_refactor.py E4A9F60A6381…`, `python/formats/gdscript/node_paths.py
  92531952FD26…`, `python/modules/scene_model/shared/node_path.py E747FB1B2E50…`,
  `python/modules/verification/tscn_lint/domain/core.py F23EDD5A4ED9DE01…`,
  `python/modules/verification/tscn_lint/tools.py 78CE27C8DED17083…`,
  `python/modules/verification/gd_lint/domain/core.py`, `node_rename/domain/core.py B5F370906049…`,
  `node_reparent/domain/core.py f53a3384f34e…`, `node_delete/domain/core.py fe63bc232bbc…`.
- Git в `agent-rebuild` нет намеренно — историю не ищи, сверяйся с этим промптом и листами.
- Среда: PowerShell; команда дольше ~30 с умирает — дроби; в каждой команде
  `PYTHONDONTWRITEBYTECODE=1`/`python -B`; stderr считай ошибкой — пиши вывод в файл
  (PowerShell-редирект ломает UTF-8: логируй изнутри Python); JSON только через `--args-file`;
  две мутации одновременно запрещены; подложку `.gd` убирай вместе с `.uid`.

## §1 Границы среза

- Механика: **`verification.check`** — модуль-владелец агрегатора проверок. Он не пишет на
  диск, не выполняет код и не чинит файлы: собирает проблемы по одному пути и честно говорит,
  что именно проверено, а что в этом окружении недоступно (ADR-0004, `docs/parity.md:65`).
- **Имя инструмента — `verify`, а не `check`.** Причина, а не вкус: имя `check` уже занял
  принятый C.8 (`python/modules/verification/tscn_lint/tools.py`), а `python/protocol/registry.py:50-56`
  на дубль `tool_name` отключает **обоих** владельцев — агент потерял бы и линтер сцен, и
  агрегатор. Переименовывать принятый `contract/capabilities/check.json` запрещено.
  Скелет `python/modules/verification/check/tools.py` (`TODO: ToolSpec(name="check", …)`)
  писался до C.8: расхождение зафиксируй в листе (§ «Решения по ходу») и обнови
  `docs/parity.md:65` (имя инструмента), сам контракт C.8 не трогай.
- Модуль уже существует скелетом: `python/modules/verification/check/` (`module.py`, `tools.py`,
  `app.py`, `domain/core.py`, `domain/__init__.py`, `tests/test_core.py` — одни комментарии/TODO).
  Заполняешь его, папку не переименовываешь.
- Лист механики: `docs/porting/verification.check.md` — создаёшь **первым**, статус «этап 1»,
  дальше обновляешь по ходу (R-19).
- Корпус: `fixtures/corpus/verification/check/` (`NNN-id.json` + `manifest.json`). Ожидания
  снимаешь с эталона одноразовым скриптом `python -B` (в репозиторий он не попадает), как в
  C.2/C.6/C.7/C.8. `tools/snapshot_diff.py` находит корпус сам по `fixtures/corpus/*/*/manifest.json` —
  регистрировать нечего, но прогон должен показать новую строку корпуса.
- **В скоупе ровно пять текстовых видов проверки:** `gd`, `tscn`, `py`, `json`, `cfg`
  (эталонные `CHECK_TEXT_EXTENSIONS`), причём `gd` и `tscn` приходят **вкладами** принятых
  механик, а `py`/`json`/`cfg` реализует сам владелец (это ~20 строк, не отдельные механики).
- **Вне скоупа:** `verification.api_check` и `verification.headless` (обе на этапе 0),
  `verification.runtime_checks`, `verification.action_judge`; агрегатор не воспроизводит
  write-гейты `main.py:1987,2038–2064`; мост/WAL/undo/редактор не трогаются,
  `contract/editor_verbs.json` не меняется.
- **Разрешённые правки принятых механик (owner-fate, минимальные, ничего не удаляя):**
  1. `python/modules/verification/gd_lint/module.py` + `tools.py` — добавить `contributes_to=('verify',)`
     и `CONTRIBUTIONS=(CheckKind(...),)`; содержимое `domain/` — байт-в-байт.
  2. `python/modules/verification/tscn_lint/module.py` + `tools.py` — то же самое (вклад в `verify`);
     `domain/core.py`, `app.py`, `read_inputs.py`, `ports.py`, корпус и карточка `check.json` — байт-в-байт.
  3. `fixtures/corpus/context/gather/001-all-sections.json` — `names`/`effects`/`count`:
     добавить `verify` (`"read"`), `count` 17 → 18; больше в файле ничего не меняется.
  4. Тесты, которые пинят `MODULE.contributes_to == MODULE.requires == ()` у `tscn_lint`
     и инвентарь инструментов на 17 имён — поправить **ровно в этих утверждениях**.
  Всё остальное содержимое перечисленных файлов остаётся байт-в-байт; в листе и в WORKLOG
  перечисли, что именно ты добавил в принятые файлы (аудитор сверит обратной проекцией).

## §2 Контракт и раскладка

### 2.1 `ToolSpec` инструмента `verify` (literal)

```python
# python/kernel/limits.py: READ_TEXT_MAX_BYTES = 4 * 1024 * 1024 — переиспользуй,
# вторую константу не заводи.

ARGS = {
    'type': 'object',
    'required': ['path'],
    'additionalProperties': False,
    'properties': {
        'path': {'type': 'string', 'minLength': 1},
        'kinds': {'type': 'array', 'minItems': 1,
                  'items': {'type': 'string',
                            'enum': ['gd', 'tscn', 'py', 'json', 'cfg', 'api', 'headless']}},
    },
}

RESULT = {
    'type': 'object',
    'required': ['path', 'problems', 'checked', 'auto_fixable', 'kinds', 'unavailable'],
    'additionalProperties': False,
    'properties': {
        'path': {'type': 'string', 'minLength': 1},
        'problems': {'type': 'array', 'items': {'type': 'string'}},
        'checked': {'type': 'boolean'},
        'auto_fixable': {'type': 'boolean'},
        'kinds': {'type': 'array', 'items': {'type': 'string'}},
        'unavailable': {'type': 'array', 'items': {
            'type': 'object', 'required': ['kind', 'reason'], 'additionalProperties': False,
            'properties': {'kind': {'type': 'string', 'minLength': 1},
                           'reason': {'type': 'string', 'minLength': 1}}}},
        'unchecked_reason': {'type': 'string', 'minLength': 1},
    },
}

VERIFY = ToolSpec(
    name='verify',
    description='Проверить один файл проекта текстовыми проверками и честно сказать, что проверено.',
    args=ARGS, result=RESULT,
    effects='read', idempotent=True,
    errors=('invalid_input', 'not_found', 'denied'),
    availability='*', cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES},
)
TOOLS = (VERIFY,)
```

Семантика полей результата — это и есть контракт, отступать нельзя:

- `path` — тот же `res://`-путь, что пришёл (нормализованный так же, как в `tscn_lint`).
- `problems` — плоский список строк в порядке **как в эталоне**: сначала всё, что дал вклад
  по расширению, строки — дословно эталонные (2.4).
- `checked` — `True` только если реально выполнилась хотя бы одна проверка (эталон:
  `bool(text_linted or headless_ran)`). «Чисто» без проверки — запрещено: ровно этот дефект
  старого моста и лечится полем `checked`.
- `auto_fixable` — `True` только когда вклад сцен вернул исправленный текст, отличный от
  исходного (эталон: `fixed != text`). Для `.gd/.py/.json/.cfg` — всегда `False`.
- `kinds` — фактически выполненные виды в порядке выполнения (`['gd']`, `['tscn']`, `['py']`,
  `['json']`, `['cfg']`, либо `[]` для непроверяемого расширения).
- `unavailable` — виды, которые по расширению полагались или были запрошены, но которых в этом
  окружении нет (`api`, `headless`), с машинной причиной. Никогда не превращается в «clean».
- `unchecked_reason` — **только** при `checked == False`, текст дословно эталонный (2.4).

### 2.2 Вклад (ADR-0004) — `python/modules/verification/shared/check_kind.py`

```python
class CheckKind:
    """Вид проверки: имя, расширения и функция, дающая проблемы по тексту."""
    __slots__ = ('name', 'extensions', 'lint')

    def __init__(self, name, extensions, lint):
        # name: [a-z][a-z0-9_]*; extensions: непустой tuple в нижнем регистре, с точкой;
        # lint: callable(text, path, ctx) -> {'problems': [str, ...], 'auto_fixable': bool}
```

- Вклад **не** читает диск и не знает про порты: текст ему передаёт владелец одним чтением.
- Вклад не импортирует чужой `domain/` (R-11) и не поднимает свой `ToolSpec`: у вклада нет
  своего имени инструмента, карточка контракта для него не создаётся (как у
  `context.editor_context`, у которого `TOOLS = ()` и `CONTRIBUTIONS = (SECTION,)`).
- `gd_lint` отдаёт `CheckKind('gd', ('.gd',), <свой app.call>)`, `tscn_lint` —
  `CheckKind('tscn', ('.tscn',), <свой app.call>)`; оба вызывают **свой** `app.call`
  (`gd_lint` / `check`) с уже прочитанным текстом, поэтому их контракты, корпуса и карточки
  остаются нетронутыми.
- Владелец берёт вклады только из реестра: `ctx.registry.contributions('verify')`.
  Пустой список вкладов — валидное состояние: тогда `kinds == []`, `checked == False`,
  а `unavailable` перечисляет всё, что не смогло.

### 2.3 Проекция результата порта на результат эталона

| Поле эталона (`_check_one_path`) | В порте |
|---|---|
| `path`, `problems`, `auto_fixable`, `checked` | те же имена, те же значения |
| `unchecked_reason` | `unchecked_reason` (только при `checked == False`) |
| `truncated` + проблема «частичная проверка…» | **граница контракта:** файл больше `max_file_bytes` → отказ `invalid_input` (как в C.8 для `content`); в корпусе такой кейс помечается `contract_refusal`, `reference_result` сохраняется отдельно |
| `headless` (`{status, mode, new_diagnostics, pre_existing_diagnostics}`) | `unavailable[{kind: 'headless', reason: <текст причины>}]` — причина берётся из эталонного `_unchecked_reason` |
| вызов `gd_api_check.check_api_usage` внутри `.gd` | `unavailable[{kind: 'api', reason: '…'}]` |

### 2.4 Якоря эталона (строки — старый плагин `python/tools/agent_bridge.py`)

- `83` `CHECK_LINT_MAX_CHARS = 2 * 1024 * 1024`
- `86` `CHECK_TEXT_EXTENSIONS = (".gd", ".tscn", ".py", ".json", ".cfg")`
- `87` `CHECK_HEADLESS_EXTENSIONS = (".gd", ".tscn", ".tres", ".gdshader", ".shader")`
- `1173–1264` `_check_one_path(root, path, policy, opts)` — единственный настоящий агрегатор
- `1267–1279` `_unchecked_reason(extension, text_linted, report)`
- `1301–1320+` `cmd_check` — CLI-обёртка (rc и печать), **не** переносится

Дословные строки (снял аудитор 2026-10-30 живым вызовом эталона, а не по памяти):

- `python syntax: %s` — `compile(text, path, 'exec')`, в сообщении путь как пришёл
  (пример: `python syntax: invalid syntax (res://e.py, line 1)`)
- `json syntax: %s` — `json.loads` с отказом на дубли ключей
  (пример: `json syntax: duplicate JSON key: a`)
- `cfg syntax: %s` — `configparser.ConfigParser(strict=True, interpolation=None)`
  (пример: `cfg syntax: While reading from '<string>' [line  3]: option 'a' in section 'x' already exists`)
- `расширение %s не проверяется этим каналом (проверяются: %s)` — список =
  `sorted(set(текстовые) | set(headless))`, то есть ровно
  `.cfg, .gd, .gdshader, .json, .py, .shader, .tres, .tscn`; для файла без расширения —
  `без расширения` (пример: `расширение .md не проверяется этим каналом (проверяются: .cfg, .gd, .gdshader, .json, .py, .shader, .tres, .tscn)`)
- `%s проверяется только настоящим Godot, а проверка отключена (--validation off) — файл НЕ проверен`
- `%s проверяется только настоящим Godot, а он не дал вердикта (headless: %s) — файл НЕ проверен`

Снятое аудитом поведение эталона при `validation off` на мини-проекте (факт, не чтение):

| файл | результат эталона |
|---|---|
| `a.gd` (`extends Node` + неиспользуемая переменная) | `problems []`, `checked true`, `headless {status: skipped, mode: off}`, `auto_fixable false` |
| `b.tscn` с неверным `load_steps=9` | `problems []`, **`auto_fixable true`**, `checked true` |
| `c.json` с дублем ключа | `problems ['json syntax: duplicate JSON key: a']`, `checked true` |
| `d.cfg` с дублем опции | `problems ['cfg syntax: While reading from '<string>' …']`, `checked true` |
| `e.py` с синтаксической ошибкой | `problems ['python syntax: invalid syntax (res://e.py, line 1)']`, `checked true` |
| `f.md` | `problems []`, **`checked false`**, `unchecked_reason` «…не проверяется этим каналом…» |

- `.scn` в эталоне **не** текстовый канал (в списке только `.tscn`) — не «улучшай», паритет
  важнее удобства. `.tres/.gdshader/.shader` идут только headless-каналом, которого в порте
  нет → `checked false` + `unchecked_reason` из строки про отключённую проверку.
- `headless_blocking`/`blocking_message`/`_headless_infrastructure_failure` — вне скоупа.

### 2.5 Вход и ошибки

- `path` обязан быть `res://…` (иначе `invalid_input`), нормализуется как в C.8, затем
  `ctx.path_policy.deny_reason(rel)` → `denied` (текст причины — политики, не твой),
  `fs.is_file` → `not_found`, превышение лимита байт → `invalid_input`,
  `PermissionError` → `denied`, прочий `OSError` → `internal`.
- Неизвестный `kind` → `invalid_input` со списком допустимых (схема `enum` откажет раньше,
  но в `app` отказ должен быть человеческим).
- Непроверяемое расширение — **не** ошибка: `ok: true`, `checked: false`, `unchecked_reason`.
- `kinds` фильтрует: вид, не относящийся к расширению, просто не выполняется; `kinds` в
  результате — фактически выполненные. Фильтр оставил пусто — `checked: false`.
- Декодирование как в C.8 (`utf-8`, `errors='replace'`), CRLF не нормализуются молча:
  вклад получает текст в том виде, в каком его ждёт его собственный контракт.
- Два вызова подряд дают одинаковый ответ; хеши фикстуры до и после совпадают (read-only).

## §3 Шаги

1. **Лист** `docs/porting/verification.check.md` по `_template.md`, статус «этап 1»: цель, старый
   код (`agent_bridge.py:1173–1279` + кто вызывает `_check_one_path`), судьба старых тестов
   (`repro_check_{blocking,truncated,unchecked}.py` — это про агрегатор, они закрываются здесь,
   а не линтером сцен), таблица корпуса, спецификация, решения.
2. **Корпус до кода.** Одноразовый скрипт (только в одобренном temp, в репозиторий не попадает):
   `sys.path` → старый `python/`, `import agent_bridge`, `policy = agent_bridge._access_policy({}, root,
   lambda *a, **k: None)`, `agent_bridge._check_one_path(root, 'res://…', policy,
   {'validation': 'off', 'godot': None})`, где `root` — копия мини-проекта в temp (старый
   `history_manager` создаёт снапшоты на чтении — на живом дереве этого делать нельзя).
   `reference_result` = сырой dict как есть (включая `headless`); `expect.result` = проекция по
   2.3. Кейсов **не меньше 26**, манифест по образцу `fixtures/corpus/verification/tscn_lint/manifest.json`
   (`schema_version`, `captured_at`, `module`, `reference_commit ba0535d4…`, `reference`
   {file/function/sha256/bytes}, `capture`, `capture_script` {sha256, bytes}, `contract_refusals`,
   `cases`, `inputs` с sha256/bytes каждого входного файла, `fixture_base: fixtures/projects`).
   Фикстура — `fixtures/corpus/verification/check/project/…`, `fixture` в кейсе пишется как
   `../corpus/verification/check/project/…` (база — `fixtures/projects`, иначе `snapshot_diff`
   не найдёт файлы). Покрытие: каждый из `.gd/.tscn/.py/.json/.cfg`; чистый `.gd`; `.gd` с
   находкой `gd_lint`; валидный `.tscn`; `.tscn` с исправимым `load_steps` (`auto_fixable true`);
   `.tscn` с незакрытым заголовком (проблемы, не исправимо); `.py` с синтаксической ошибкой;
   `.json` с дублем ключа; `.cfg` с дублем опции; `.md` (непроверяемое расширение);
   `.tres` (только headless-канал); `.scn` (не проверяется); файл без расширения; `kinds`
   фильтр (`['py']` на `.gd` → пусто, `checked false`); неизвестный `kind` → `invalid_input`;
   `path` вне `res://` → `invalid_input`; отсутствующий файл → `not_found`; путь в `addons/`
   → `denied`; не-UTF8 байты; CRLF-файл; пустой файл; файл больше лимита → `invalid_input`
   (`contract_refusal`); повторный вызов идентичен (идемпотентность).
3. **Спецификация + красные тесты.** `tools.py` по 2.1; `tests/py/integration/test_verification_check.py`
   (реальный диспатч через `build_agent(project_root=…, profile='headless')`, хеши фикстуры
   до/после, `ok: False` не содержит абсолютного пути) + `python/modules/verification/check/tests/test_app.py`
   (фейковые порты, отказы до IO, лимит байт, маппинг ошибок) + `tests/test_core.py`
   (чистые правила: выбор вклада по расширению, фильтр `kinds`, сборка `unavailable`,
   `unchecked_reason`). Все тесты сначала **красные** — это нормальный этап 3.
4. **Код.** `domain/core.py` — чистые правила (никакого IO, `pathlib`, `os`); `app.py` — только
   оркестрация (≤80 строк): `validate` → путь/policy → `fs.is_file` → чтение с лимитом →
   вклады из реестра → `core.assemble(...)` → Result; `ports.py` — только то, что нужно.
5. **Вклады.** `verification/shared/check_kind.py`; `CONTRIBUTIONS` в `gd_lint/tools.py` и
   `tscn_lint/tools.py`; `contributes_to=('verify',)` в обоих `module.py`. Прогони
   `selfcheck verification.gd_lint` и `selfcheck verification.tscn_lint` — оба обязаны остаться
   `ok` с прежними числами (unit 37/корпус 37 и unit 315/корпус 65).
6. **Карточка контракта:** `python -B tools/gen_contract.py --write` → в `contract/capabilities/`
   появляется `verify.json`, артефактов **19**; правь только новый файл, чужие карточки —
   байт-в-байт.
7. **Двойной прогон:** полный non-live (`2337 + новые`), `snapshot_diff` (`469 + новые`, строка
   нового корпуса без расхождений), `selfcheck verification.check`, `lint_arch`/`check_limits`,
   `security_audit`, `live` (остаётся **3**, новых живых тестов этот срез не требует — движок
   не задействован; если всё же добавил, объясни в листе и докажи, что `.gd.uid` убраны).
8. **Записи:** лист (этап 6, вердикт selfcheck, решения), `docs/parity.md:65`,
   `docs/tests-map.md` (строка нового модуля и новых тестов), `docs/PROGRESS.md` (своя строка,
   этап 6), `docs/WORKLOG.md` (сессия). Шапку «принято» и этап 7 не пишешь — это аудитор.

## §4 Решения, которые нужно принять до кода (и записать в лист)

1. **Имя `verify`** (2.1). Альтернатива «переименовать принятый `check` в `lint_scene`» —
   запрещена: ломает принятый контракт C.8, карточку и корпус. Обе строки (`check` у
   `tscn_lint`, `verify` у `verification.check`) должны попасть в `docs/parity.md`.
2. **Что делает `unavailable`.** В эталоне `headless` — словарь со `status: skipped`; в порте
   это `unavailable[]`. Не подменяй на пустой список: молчание = «clean», а это дефект, ради
   которого поле `checked` и вводится.
3. **`.scn` не проверяется** (паритет с `CHECK_TEXT_EXTENSIONS`). Записать в лист как
   осознанное ограничение, а не как баг.
4. **Лимит байт вместо лимита символов**: эталон режет по 2 Ми **символов**
   (`CHECK_LINT_MAX_CHARS`) и дописывает проблему «частичная проверка…»; в порте лимит —
   `max_file_bytes` из `python/kernel/limits.py` (**4 МиБ**), а превышение — отказ
   `invalid_input`. Поведение «частичная проверка» не переносится: это осознанная граница
   контракта, отметь её в листе.
5. **Кто читает текст** — только владелец, один раз; вклады не ходят на диск.
6. **Порядок `problems`** — порядок вкладов из реестра (порядок загрузки модулей), внутри
   вклада — как отдаёт его собственный линтер. Перестановка = расхождение с эталоном.
7. **`kinds` в результате — факт, а не запрос.** Запросили `['gd']` на `.tscn` → `kinds []`,
   `checked false`, `unchecked_reason` не нужен только если вид был выполнен.

## §5 Доказательства, которые обязан предъявить (по одному за прогон, файлы восстанавливать побайтово)

Мутации делаешь по одной, после каждой — `sha256` до/после и полный прогон скоупа
(`pytest python/modules/verification/check tests/py/integration/test_verification_check.py
python/modules/verification/gd_lint python/modules/verification/tscn_lint -q`):

| # | Мутация | Обязана покраснеть |
|---|---|---|
| M1 | `checked` всегда `True` | кейсы `.md/.tres/.scn` (там `checked false`) |
| M2 | `problems` склеить в одну строку | все кейсы с находками |
| M3 | убрать ветку `py` (или `json`, или `cfg`) | соответствующий кейс |
| M4 | `auto_fixable` всегда `False` | кейс `.tscn` с исправимым `load_steps` |
| M5 | выкинуть `unavailable` (пустой список) | кейсы `.gd`/`.tres` (там `api`/`headless`) |
| M6 | игнорировать фильтр `kinds` | кейс «`['py']` на `.gd`» |
| M7 | снять проверку `deny_reason` (читать `addons/`) | кейс `denied` |
| M8 | перевернуть порядок `problems` | кейс, где проблем больше одной, либо двойной вклад |

Подложки (обязаны покраснеть **гейты**, а не только тесты):

- P1: `ToolSpec.required` без `'checked'` → `python -B tools/gen_contract.py --check` должен
  сказать «расхождение» (юнит-тесты это не ловят — так и было в C.8, это нормально, но
  записать обязательно).
- P2: вклад `tscn` возвращает `problems` строкой вместо списка → красный интеграционный кейс
  (и это доказывает, что вклад реально вызывается через реестр, а не заглушкой).
- P3: `app.py` импортирует чужой `domain/` (например `from ..tscn_lint.domain import core`) →
  `python -B tools/lint_arch.py` должен дать нарушение (R-11).

Плюс к этому:

- Обратная проекция: список всех изменённых файлов (`Get-ChildItem` по дате + `sha256`),
  отдельно — правки принятых файлов (их ровно те, что разрешены §1) и доказательство, что
  остальные байты не поехали (сравнение с копией до правки).
- Гигиена: `__pycache__` 0, `.pytest_cache` 0, `.bak/.tmp/.orig` 0, `zz_*` 0,
  `.gd.uid` ровно **83**, дерево = 2034 + твои новые файлы (`fixtures/corpus/verification/check/*`,
  `python/modules/verification/check/*`, тесты, `contract/capabilities/verify.json`,
  `python/modules/verification/shared/check_kind.py`, лист, промпт уже есть).
- Никаких временных скриптов и логов в репозитории: они живут в одобренном temp.

## §6 Стоп-условия

Останавливайся и спрашивай, если:

1. Хочется переименовать принятый `check`/`check.json`/`tscn_lint` — это ломает accepted-артефакт.
2. Проекция на эталон расходится так, что нужно менять `problems`/`checked`/`unchecked_reason`
   (значит, задача понята неверно).
3. Для `gd`-вклада требуется `api_cache` или второй порт (контракт `verify` читает только `fs`).
4. Числа `selfcheck verification.gd_lint` / `verification.tscn_lint` изменились (значит, вклад
   задел чужое поведение).
5. Появляется соблазн «заглушки чисто»: пустой `problems` без выполненной проверки.

## §7 Что проверит аудитор (своими прогонами, не по твоему отчёту)

1. **Независимая пересъёмка корпуса** с эталона: свой одноразовый скрипт с
   `_access_policy`/`_check_one_path` (аудитор уже проверил, что эталон вызывается так и даёт
   ровно те строки, что в 2.4) → сравнит `reference_result` во всех кейсах и `expect.result`
   во всех, где ожидание есть.
2. **Дифференциал шире корпуса:** прогон `verify` по всем `.gd/.tscn/.py/.json/.cfg` из
   `fixtures/**` (корпус + parity) и сравнение с эталоном на тех же файлах; расхождения
   допускаются только документированные (границы контракта: лимит байт, `unavailable`,
   `denied`-политика).
3. **Свои мутации** (свой набор, не твой) + подложки на гейты.
4. **Инвентарь:** `gen_contract --check` = 19, `contract/capabilities` = 19 карточек + `_template`,
   `context.gather` кейс с 18 именами, `# verb:` = 6, `verbs_version 3`.
5. **Принятые механики:** `selfcheck verification.gd_lint` и `verification.tscn_lint` — те же
   числа; `sha256` их `domain/` совпадает с §0.
6. **Гигиена и живые:** `live` = 3, `.gd.uid` = 83, дерево без мусора.

## §8 Финальный прогон и записи

Собери один отчёт (в лист + WORKLOG), где по пунктам: non-live (число, 0 fail), `snapshot_diff`
(число и строка нового корпуса), `selfcheck verification.check` (таблица вердикта и
`reports/selfcheck/verification.check.json`), `gen_contract --check` (19), `lint_arch`/`check_limits`,
`security_audit`, `live` (3), дерево/`.gd.uid`/мусор, и отдельно — доказательства §5 с `sha256`.

Записи: `docs/porting/verification.check.md` (этап **6**, «готово к независимому аудиту, не
принято»), `docs/parity.md`, `docs/tests-map.md`, `docs/PROGRESS.md` (своя строка, этап 6),
`docs/WORKLOG.md`. Не трогай: `docs/porting/_audit-handoff.md`, шапки «принято/ported», этап 7,
`contract/editor_verbs.json`, `python/kernel/schema.py`, `tools/lint_arch.py`,
`tools/gen_contract.py`, `tools/security_audit.py`, `tools/snapshot_diff.py`.
