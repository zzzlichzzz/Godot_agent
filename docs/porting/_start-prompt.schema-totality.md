# Задача: закрыть доказательные дыры валидатора схем (тотальность) — до части A

**Выполнено, аудит принял 2026-10-27.** Проверено своими прогонами: репро
`validate({'a': 1}, {'type': {'x': 1}})` → `["(аргументы): ожидался {'x': 1}"]` без
исключения; мутация `if not isinstance(expected, str)` валит **два** теста
(`test_garbage_schemas_do_not_raise`, `test_non_string_type_is_refused_not_raised`),
union при этом жив; мутация ветки union валит ровно 4 теста, `_type_ok` не бросает;
подложенный `"type": 5` в `contract/capabilities/write_preview.json` валит
`gen_contract --check` с путём `input_schema.kind`, после возврата — `ok`; в
`python/kernel/schema.py` изменён только докстринг (147 строк, sha256
`629FCE54…4067`, CRLF). Одно замечание к отчёту: он пишет «11 → 14» и «collect 14»,
фактически тестов в файле **13** (11 + 2 новых; 320 = 317 + 2 + 1 сходится только с
13) — записано в handoff и в промпт части A. Промпт оставлен как образец.

**Это не новый срез, а короткая фаза 0.** Код `python/kernel/schema.py` в порядке:
union работает, неизвестный тип — отказ, гейт в `tools/gen_contract.py` стоит,
контракт части A чист. Аудит 2026-10-27 нашёл другое: часть обещаний докстринга
**не защищена тестами**, а отчёт сессии 17 доказывал мутацию не на том файле,
который сдан. Правится не поведение, а доказательство: тесты, мутации, честный отчёт.

## 0. Что найдено (мои прогоны — воспроизведи у себя, прежде чем править)

### 0.1 Защита `isinstance(expected, str)` не покрыта тестом

`python/kernel/schema.py:49-56`:

    def _type_ok(value, expected):
        if isinstance(expected, (list, tuple)):
            return any(_type_ok(value, item) for item in expected)
        if not isinstance(expected, str):        # ← эта защита
            return False
        checker = _TYPES.get(expected)
        if checker is None:
            return False
        return checker(value)

Убери две строки защиты — и все **11** кейсов `tests/py/kernel/test_schema_union.py`
остаются зелёными, а:

    python -B -c "import sys; sys.path.insert(0,'.'); from python.kernel.schema import validate; print(validate({'a': 1}, {'type': {'x': 1}}))"
    → TypeError: cannot use 'dict' as a dict key

Докстринг (`schema.py:16-17`) обещает «`validate` тотальна: мусорная схема
(`type: 5`, `items: "x"`, `required: "path"`, `properties` не-dict) даёт проблемы
или пустой список, но не исключение». Обещание держится на строке, которую сейчас
нельзя покрасить тестом.

Мусорный набор, который есть сейчас (`tests/py/kernel/test_schema_union.py:90-96`):
`{"type": 5}`, `{"items": "x"}`, `{"properties": []}`, `{"required": "path"}`,
`{"properties": {"a": "не схема"}}`, `{"type": ["string", None]}` — `type`-словаря
в нём нет, поэтому дыра не ловится.

### 0.2 Отчёт сессии 17 доказывал не тот файл

Отчёт: «убрал ветку union → `TypeError: unhashable type: 'list'`, `pytest
tests/py/kernel` → FAILED: `test_garbage_schemas_do_not_raise`». На **сданном** файле:

- репро `None` против `["string","null"]` → `["(аргументы).node_path: ожидался
  ['string', 'null']"]`, **exit 0, исключения нет**;
- `pytest tests/py/kernel` → **4 failed, 7 passed**: `test_none_passes_nullable_union`,
  `test_string_passes_nullable_union`, `test_open_scenes_from_contract_are_valid`,
  `test_nullable_fields_of_selection_are_valid`;
- `test_garbage_schemas_do_not_raise` — **зелёный**.

`TypeError` на списке возможен только если вместе с union убрать и
`isinstance(expected, str)` — то есть отчёт снял доказательство со старой версии.
Артефакт при этом защищён (4 теста краснеют), но отчёт как доказательство не годится.

### 0.3 Отчёт описывает другой мусорный набор

В отчёте: `properties: 5` и `type: null`. В сданном файле (`test_schema_union.py:91-92`):
`{"properties": []}` и `{"type": ["string", None]}`; `properties: 5` и `type: null`
в наборе **нет**. Поведение при этом корректное (проверено аудитором):

| Схема | `validate({"a": 1}, schema)` |
|---|---|
| `{"type": {"x": 1}}` | `["(аргументы): ожидался {'x': 1}"]` |
| `{"type": [1, 2]}` | `["(аргументы): ожидался [1, 2]"]` |
| `{"type": None}` | `[]` — тип не задан (не отказ) |
| `{"properties": 5}` | `[]` — поля не проверяются |
| `{"properties": []}` | `[]` |
| `{"required": "path"}` | `[]` — строка не считается списком |
| `{"required": 5}` | `[]` |
| `{"items": 5}` | `[]` |

Защиты `properties` (`schema.py:131-132`) и `required` (`schema.py:133-134`) **уже
покрыты** мусорным набором: убери любую — `test_garbage_schemas_do_not_raise`
краснеет (`argument of type 'NoneType' is not a container or iterable`). Их не
трогать и не «оптимизировать».

## 1. Что сделать (только тесты и документы; поведение не меняется)

**1.1 `tests/py/kernel/test_schema_union.py` — расширить мусорный набор.**
Добавить к `garbage` (строка 91) схемы с не-строковым типом и с не-схемой в
`properties`: `{"type": {"x": 1}}`, `{"type": [{"x": 1}]}`,
`{"properties": {"a": {"type": {"x": 1}}}}`, `{"properties": 5}`, `{"required": 5}`.
Проверки теста остаются прежними (`isinstance(..., list)` на `validate` для dict и
list, на `unknown_schema_types`).

**1.2 Новый тест `test_non_string_type_is_refused_not_raised`.** Он и есть
доказательство, которого не хватало:

    assert validate({"a": 1}, {"type": {"x": 1}}) == ["(аргументы): ожидался {'x': 1}"]
    assert unknown_schema_types({"type": {"x": 1}}) == \
        ["(аргументы): неизвестный тип {'x': 1}"]

Первая строка падает `TypeError` без защиты, вторая ловит ту же дыру на уровне
диагностики схемы. Обе — про отказ, а не про «мягкий пропуск».

**1.3 Гейт: не-строковый тип в записанном артефакте.** В
`tests/py/tools/test_gen_contract_types.py` (рядом с
`test_capability_artifact_with_unknown_type_fails`) добавить тест: файл
`write_preview.json` в `tmp_path` с
`{"input_schema": {"type": "object", "properties": {"path": {"type": 5}}}}` →
`gen_contract.artifact_type_problems(tmp_path)` непусто, в сообщении есть имя файла
и путь `input_schema.path`. Тест на `"date"` оставить.

**1.4 Зафиксировать `type: null` как «тип не задан».** Сейчас
`validate("x", {"type": None}) == []` и `unknown_schema_types({"type": None}) == []` —
осознанное поведение (`_check` входит в ветку только при `expected is not None`,
`_walk_types` так же). Пин-тест в том же файле плюс **одна строка в докстринге**
`schema.py` (только текст): `type: null` — тип не задан; неизвестный тип — это
не-`null` значение вне семи имён. Поведение не меняется (R-08: перенос не улучшает).

**1.5 Отчёт — с доказательством сданного файла.** Обязательны дословные
`stdout`/`stderr` обеих мутаций и списки красных тестов:

| Мутация (на сданном файле) | Ожидание после этой правки |
|---|---|
| удалить ветку `if isinstance(expected, (list, tuple)): return any(...)` | репро `None` → **не** `[]` (`… ожидался ['string', 'null']`), красные **4** теста (перечислены в §0.2), `_type_ok` не бросает |
| удалить `if not isinstance(expected, str): return False` | `test_non_string_type_is_refused_not_raised` **красный** (`TypeError: cannot use 'dict' as a dict key`), остальные зелёные; **до** этой правки та же мутация давала 11 зелёных |

Мутации — на копии, восстановление байтовое (§3); после восстановления sha256 файла
совпадает с исходным (базовый `python/kernel/schema.py` = `926B0467…F182`).

## 2. Границы

- `python/kernel/schema.py` — только строки докстринга (§1.4). Логику, `_TYPES`,
  тексты проблем, порядок проверок не менять.
- Не трогать `python/protocol/validation.py`, `ToolSpec`, `contract/**`
  (`editor_verbs.json`, `capabilities/*.json`), корпуса `fixtures/corpus/**`,
  конвейер записи, `tools/gen_contract.py` (гейт уже стоит), `tools/selfcheck.py`.
- Тесты портера не переписывать — только добавлять (§1.1–1.4). Новый файл не нужен:
  правка ложится в `test_schema_union.py` и `test_gen_contract_types.py`.
- `app.py`/`tools.py` механик не касаются вообще.
- Старый плагин `D:\vajno\Godot\тест-плагина-ии` — **только чтение** (`python -B`):
  там уже лежат два чужих файла (`python/_ref2.log` 5198 Б,
  `python/godot_tools/_excl.log`), их не удалять, новых дампов не создавать —
  временные файлы в `$env:TEMP`.

## 3. Как доказывать (из-за этого срез и вернулся)

1. Бэкап **байтовый**: `shutil.copyfile`, не «прочитал текст и записал». Файлы в
   репозитории с CRLF: пересборка из текста даёт LF и другой sha256 (аудит поймал
   это на `schema.py`: `A402260B…` вместо `926B0467…`).
2. После восстановления — `Get-FileHash -Algorithm SHA256` и сверка с исходным
   значением; в отчёте оба хеша.
3. Мутации — только на файле, который сдаёшь. Если результат не совпал с ожиданием,
   не подгонять текст, а разобраться: возможно, проверяется не тот код.
4. Все прогоны с `PYTHONDONTWRITEBYTECODE=1` и `python -B`, иначе `__pycache__`
   появится в дереве (R-06).

## 4. Стоп-условия

- Не реализовывать JSON Schema (`anyOf`, `$ref`, `format`, `pattern`) — только то,
  что перечислено в докстринге.
- Не менять fail-closed на «мягкий пропуск» и наоборот; не менять поведение для
  `type: null`, `properties: 5`, `required: 5`.
- Не «улучшать» тексты проблем: они попадают в `invalid_input` и в корпус.
- Не добавлять функций и зависимостей; файл остаётся < 400 строк.
- Не сдавать отчёт без фактического вывода команд и без списка красных тестов.
- Не выдавать «проверил глазами»/`needs_live` за приёмку (R-18).

## 5. Что проверит аудитор (своими прогонами)

| Что | Как |
|---|---|
| дыра закрыта | свой репро: `validate({'a': 1}, {'type': {'x': 1}})` → `["(аргументы): ожидался {'x': 1}"]`, без исключения |
| тест держит защиту | мутация: удалить `if not isinstance(expected, str): return False` → `test_non_string_type_is_refused_not_raised` красный (до правки — 11 зелёных) |
| union не сломан | мутация ветки union → репро не `[]`, 4 красных теста; восстановление побайтово, sha256 = значению, зафиксированному в отчёте после правки докстринга (до фазы 0 файл был `926B0467…F182`) |
| гейт | подложить `"type": 5` в `contract/capabilities/write_preview.json` `input_schema.kind` → `gen_contract.py --check` fail с путём поля; вернуть → `ok` |
| регресс | `pytest python/modules tests/py` exit 0, число = `--collect-only` (было 317, станет 317 + новые) ; `snapshot_diff` 99/0; `selfcheck` write_preview 45/16, write_apply 44/15, rollback 24/4 |
| гигиена | `security_audit --json` ok, `lint_arch` 450/0, `check_limits` 450/0, `__pycache__` 0, `.pytest_cache` нет |
| записи | WORKLOG (сессия с числами и хешами), `docs/NOTES.md` (`type: null`), лист `context.editor_context.md` (строка про тотальность), этот файл — пометка «выполнено» |

## 6. Финальный прогон (пиши вывод в отчёт дословно)

    python -m pytest python/modules tests/py                # exit 0, число = collect
    python -m pytest python/modules tests/py --collect-only -q
    python tools/snapshot_diff.py                          # 99 кейсов, 0
    python tools/selfcheck.py editing.write_preview        # ok, 45/16
    python tools/selfcheck.py editing.write_apply          # ok, 44/15
    python tools/selfcheck.py editing.rollback             # ok, 24/4
    python tools/gen_contract.py --check                   # ok + «мост: 0 обработчиков из 3»
    python tools/security_audit.py --json                  # ok
    python tools/lint_arch.py ; python tools/check_limits.py
    Get-ChildItem -Recurse -Directory -Filter __pycache__ | Measure-Object

## 7. Записи после сдачи

- `docs/WORKLOG.md` — сессия «тотальность валидатора: доказательство вместо обещания»:
  что нашёл аудит, что добавлено, вывод обеих мутаций, хеши до/после восстановления.
- `docs/NOTES.md` — решение `type: null` = «тип не задан» (и чем он отличается от
  неизвестного имени).
- `docs/porting/context.editor_context.md` — одна строка в «Инструменты проверки»:
  тотальность покрыта тестом и проверена мутацией.
- `docs/porting/_start-prompt.schema-totality.md` — шапка «выполнено, аудит принял
  <дата>» после приёмки (ставит аудитор, не портер).
