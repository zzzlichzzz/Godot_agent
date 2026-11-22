# C.13 — вклад `api_check` в `verify` (паритет `.gd` = lint + API) плюс правки F2 и F3

Ты — **портер**. Работай строго по этому промпту в проекте
`D:\vajno\Godot\agent-rebuild\addons\godot_agent` (далее «порт»). Аудитор работает в другом
чате: он проверяет, ставит/снимает этап, пишет следующий промпт и ведёт записи. Ты этап сам
себе не ставишь, шапку «выполнено/принято/ported» не пишешь, `docs/porting/_audit-handoff.md`
не правишь, код принятых механик не трогаешь иначе как по §1.

Читать до первой строки кода, по порядку: `AGENTS.md`, `RULES.md` (R-01…R-22),
`docs/architecture.md`, `docs/PORTING.md`, `docs/parity.md` (строка 68 — `api_check`, строки
114–118 — вклады `contributes_to`), `docs/tests-map.md` (приложение, строки 252–263),
`docs/PROGRESS.md` (строки 55–58), `docs/porting/_template.md`,
листы соседей: `docs/porting/verification.check.md` (принят C.9 — это правим),
`docs/porting/verification.api_check.md` (принят C.12 — оттуда берём вклад),
`docs/porting/verification.gd_lint.md`, `docs/porting/verification.tscn_lint.md`,
`docs/porting/engine_kb.class_api.md`; `docs/WORKLOG.md` — три последние сессии;
`docs/security/invariants.md`; ADR-0004 (связывание), ADR-0006 (TOOLS), ADR-0008 (BOM),
ADR-0009 (`snapshot()`), **ADR-0010** (узкий шов `api_check/app.py → engine_kb.shared.inheritance`).

## §0 База (снято аудитом, сессия 64, 2026-10-31 — не пересчитывать)

* non-live: **2815 passed**, `--collect-only` = **99 файлов / 2815 тестов**, 53.96 с, stderr 0.
* live: **3 passed** (24.5 с), Godot `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`.
* `tools/snapshot_diff.py`: **кейсов 609, расхождений нет** (`verification/check` 62/62,
  `verification/gd_lint` 37/37, `verification/tscn_lint` 65/65,
  `verification/api_check` 52/52, `engine_kb/class_api` 26/26, остальные — как в C.11).
* `tools/gen_contract.py --check`: **артефактов 21**, расхождений нет
  (в `contract/capabilities` 22 файла = 21 карточка + `_template.json`).
* `tools/selfcheck.py`: `verification.api_check` unit **206**, corpus **52**;
  `verification.gd_lint` **126 / 37**; `verification.check` **136 / 62**;
  `verification.tscn_lint` **315 / 65**; `engine_kb.class_api` **186 / 26**
  ⚠️ 186 — это артефакт селектора `tools/selfcheck.py:215` (`test_%s*.py` захватывает
  `test_api*.py`); подмножество C.11 (128) зелёное. Править селектор — **вне среза** (долг F4).
* layers **502** / limits **502 / 0** — ok; `security_audit` — ok.
* Дерево: **2310** файлов (на приёмке C.12 мой обход в другой момент дал 2311 — считай прирост от 2310; обход `python -B` без `__pycache__`/`.pytest_cache`/`.godot`,
  не `Get-ChildItem`), `.gd.uid` — **83** (8 исторических в `fixtures/parity/gdscript/`,
  mtime 27.10.2026 — не трогать), мусора 0. Листов механик — 23, промптов — 31, правил — 22.
  `PROGRESS.md` — 44 строки механик: 21 на этапе 7, 1 на 6 (`editing.symbol_rename`), 22 на 0.
* Мост: 6 примитивов, `verbs_version: 3`, `contract/editor_verbs.json`
  sha256 `CDAF8D23A6BF…`. Git в `agent-rebuild` намеренно **нет**.

**Замороженные гейты (менять нельзя):** `python/kernel/schema.py` `629FCE54E6FE…` (147 строк
CRLF), `tools/gen_contract.py` `FA7E6E91C872…`, `tools/security_audit.py` `2CF0D7F6B1AF…`,
`tools/snapshot_diff.py`, `contract/editor_verbs.json` `CDAF8D23A6BF…`,
`editor/bridge/verbs/scene/scene_executor.gd` `B7AFF592B75D…`.
**`tools/lint_arch.py` — сейчас `A6C5EDD47650…` (9842 B, 228 LF)**: это уже не старое значение —
внутри разрешён шов ADR-0010 (в C.13 его **не расширять** и не сужать).

**Файлы среза (сверяй sha256 до и после, это база приёмки):**

| Файл | Байт | sha256[:12] |
|---|---|---|
| `python/modules/verification/check/domain/core.py` | 4345 | `F84018B8EE08` |
| `python/modules/verification/check/app.py` | 2485 | `F1506108E191` |
| `python/modules/verification/check/tools.py` | 1731 | `65974F15AA55` |
| `python/modules/verification/shared/check_kind.py` | 868 | `34856E8B3ECC` |
| `python/modules/verification/api_check/tools.py` | 1468 | `958EF59434CE` |
| `python/modules/verification/api_check/app.py` | 1982 | `45AD39186919` |
| `python/modules/verification/api_check/domain/core.py` | 4551 | `16647249D952` |
| `python/modules/verification/api_check/domain/mask.py` | 1777 | `D933F76EACF7` |
| `python/modules/verification/api_check/module.py` | 449 | `93853387FE6A` |
| `contract/capabilities/check.json` | 1642 | `580B1D18974A` |
| `contract/capabilities/verify.json` | 2261 | `58C34188D6FD` |
| `contract/capabilities/api_check.json` | 1781 | `5EF515DCDB54` |

**Соседи, которые обязаны остаться байт-в-байт:** `verification/gd_lint/domain/core.py` 6493
`1873E0A9E687`, `gd_lint/app.py` 1619 `02B8960A161F`, `gd_lint/tools.py` 2918 `E85C9619D9DD`;
`tscn_lint/app.py` 2634 `50F77ED6B766`, `tscn_lint/domain/core.py` 16251 `F23EDD5A4ED9`,
`tscn_lint/read_inputs.py` 1877 `74119F65825C`, `tscn_lint/tools.py` 1964 `48391FAF81A0`;
`verification/shared/source_text.py` 489 `56C397CFC171`;
`engine_kb/shared/inheritance.py` 1442 `5A9BAD5013FB` (только читать).

**Эталон (только чтение, дампы в `%TEMP%`):** старый плагин
`D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\python\…`, коммит
`ba0535d4dec43c32750e601a6ca86e377abc6af3`.
`tools/agent_bridge.py` — 142 171 B, sha256 `a9b1ad832fd0…`; ветка `.gd`:
`text_linted` — строка **1199**, `gd_lint.lint_gdscript(text)` — **1204**,
`gd_api_check.check_api_usage(root, text, path, policy.get("addon_dir"))` — **1205–1206**
(порядок: сначала сообщения линтера, потом API). `godot_tools/gd_api_check.py` — 9137 B, 201 LF,
sha256 `b9e0df9f604c…` (`MAX_PROBLEMS = 6`, `check_api_usage:145–201`).

`godot_tools/gd_lint.py` — `lint_gdscript`. Кэш API в фикстурах корпуса `verification/check`
**отсутствует** — поэтому сегодня вклад `api` не даёт ни одного сообщения, и все 62 кейса
проходят без него.

## §1 Границы среза

**Цель.** Для `.gd` инструмент `verify` (владелец `verification.check`, принят C.9) должен
выполнять то же, что эталон: `gd_lint` **и** `api_check`, в этом порядке. Сейчас API-часть
честно уходит в `unavailable[{kind: "api", reason: "no_module"}]` — это был документированный
обход C.9, пока `api_check` не существовал. Теперь он есть (C.12, принят), значит обход
закрывается вкладом, а не новым кодом внутри `check/domain`.

**Правки, которые входят в этот срез (это и есть «правки», их не откладывать):**

* **F2 (находка аудита)** — `python/modules/verification/api_check/tools.py` объявляет
  `errors=('invalid_input',)`, но инструмент реально бросает `denied` (кейсы корпуса
  `048-denied_addons`, `049-denied_escape`; путь и `deny_reason` проверяются в `app.py`).
  Все три соседних инструмента объявляют `errors=('invalid_input', 'not_found', 'denied')`.
  Правка: `errors=('invalid_input', 'denied')` — без `not_found`, файл не читается.
  Следствия: перегенерация `contract/capabilities/api_check.json`
  (`--write`) и правка пина в `tests/py/contract/test_api_check_contract.py`
  (`API_CHECK.errors == ('invalid_input', 'denied')`) — это **разрешённая** правка теста.
* **F3 (находка аудита)** — `unchecked_reason` в `check/domain/core.py` сейчас выдаёт текст
  «%s проверяется только настоящим Godot, а проверка отключена (--validation off) — файл
  НЕ проверен» даже тогда, когда `.gd` просто отфильтрован `kinds` (кейсы `018-filtered_gd`
  с `kinds: ["py"]` и `031-only_api`). Для текстового расширения это ложь. Правка — ровно три
  формы причины (см. §2.3, пункт 6), старый текст остаётся **только** для расширений без
  текстового канала (`.tres`, `.scn`, `.gdshader`, `.shader`, без расширения). Затрагивает
  ожидания кейсов `018`, `031` и новые кейсы — это разрешённая перепроекция.

**В срезе (можно менять):**

* `python/modules/verification/api_check/tools.py` — только `errors` и, если нужно, докстринг.
* `python/modules/verification/api_check/module.py` — только `contributes_to=('verify',)`.
* `python/modules/verification/check/domain/core.py` — `FRAGMENT`, `assemble`,
  `unchecked_reason`, `unavailable`, таблица порядка видов (см. §2.3).
* `python/modules/verification/check/tools.py` — только если меняется описание; схемы
  `ARGS`/`RESULT` обязаны остаться **теми же** (`api` уже есть в `enum` kinds).
* `python/modules/verification/check/app.py` — только если без правки не собирается
  (сортировка/вызов вкладов остаётся здесь же, лимит 80 строк).
* `python/modules/verification/shared/check_kind.py` — только докстринг; конструктор
  `CheckKind(name, extensions, lint)` и `__slots__` не меняются (иначе ломаются три вклада).
* Корпус `fixtures/corpus/verification/check/` — перепроекция `expect.result` у `.gd`-кейсов,
  новые кейсы, `manifest.json` (счётчики, `inputs`), новые фикстуры
  `fixtures/projects/corpus/verification/check/<variant>/` с
  `.agent_history/godot_api_cache.json` (маленький, рукописный — как в C.11).
* Тесты: `tests/py/integration/test_verify.py`, `python/modules/verification/check/tests/*`,
  `tests/py/contract/test_api_check_contract.py` (только пин `errors`),
  `tests/py/integration/test_api_check.py` (только если упадёт из-за `errors`).
* Записи: лист `docs/porting/verification.check.md` (дописать раздел C.13),
  `docs/PROGRESS.md`, `docs/parity.md:68`, `docs/tests-map.md`, `docs/WORKLOG.md`.

**Вне среза (не трогать вообще):** `verification/gd_lint/**`, `verification/tscn_lint/**`
(оба приняты), `verification/shared/source_text.py`, `verification/api_check/domain/**`
(логика C.12 — эталон, менять нельзя), `engine_kb/**`, `kernel/**`, `substrate/**`,
`tools/*.py` (в т.ч. селектор `selfcheck.py` — долг F4), `editor/**`,
`contract/editor_verbs.json`, агрегатор `headless`/`api_check`-обёртки CLI, WAL/undo/мост.

**Разрешённые правки вне папки среза — ровно три:**
(1) `fixtures/corpus/context/gather/001-all-sections.json` — **не меняется** (нового
инструмента нет, имён по-прежнему 20); если тест инвентаря падает — значит что-то не так
сделано, а не с тестом;
(2) `tests/py/integration/test_tscn_lint.py:46–59` — список 20 имён, менять только если
действительно поменялся инвентарь (в этом срезе не должен);
(3) `tests/py/contract/test_api_check_contract.py` — пин `errors` (F2).
Всё остальное — байт-в-байт; аудитор сверяет по sha256, поэтому любое изменение вне списка
надо перечислить в листе и WORKLOG отдельной строкой с причиной.


## §2 Контракт и раскладка

### 2.1 ToolSpec — что меняется

`verify` **не меняется**: `ARGS` (в `enum` уже есть `api`) и `RESULT` остаются дословно теми
же, карточки `contract/capabilities/check.json` и `verify.json` обязаны остаться
байт-в-байт (`580B1D18974A…`, `58C34188D6FD…`). Нового инструмента нет, нового порта нет,
`ModuleSpec` у `verification.check` тот же (`requires_ports=('fs',)` — `api_cache` приходит
вкладом через `ctx`).

Меняется только `verification/api_check/tools.py` (F2):

```python
API_CHECK = ToolSpec(
    name='api_check',
    description='Сверить self.* и connect() в тексте .gd с кэшем Godot API; честно сказать, что проверено.',
    args=ARGS, result=RESULT, effects='read', idempotent=True,
    errors=('invalid_input', 'denied'), availability='*', cost='cheap',
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES},
)
```

и `verification/api_check/module.py` — только поле `contributes_to=('verify',)`
(рядом с `provides_tools=('api_check',)`; `capabilities` не меняется, карточка
`api_check.json` остаётся одна).

### 2.2 Вклад (ADR-0004)

`verification/api_check/tools.py` дописывает в конец, по образцу `gd_lint/tools.py`:

```python
from python.modules.verification.shared.check_kind import CheckKind


def _verify_api(text, path, ctx):
    from .app import call
    result = call('api_check', {'path': path, 'content': text}, ctx)
    return {'problems': result['problems'], 'auto_fixable': False,
            'checked': result['checked'], 'unavailable': result['unavailable']}


CONTRIBUTIONS = (CheckKind('api', ('.gd',), _verify_api),)
```

Правила (те же, что для принятых вкладов C.9): вклад **не** делает IO сам, текст уже прочитан
владельцем; своего `ToolSpec`/карточки не создаёт; `ctx.port('fs')` не трогает; в `domain/`
принятого C.12 не лезет; импорт `app.call` — внутри функции (как `_verify_tscn` в
`tscn_lint/tools.py`), чтобы не плодить цикл. `checked`/`unavailable` берутся **из результата
`api_check` дословно**, включая `no_cache`/`base_not_in_cache`/`no_extends` — владелец их
только переносит и не переписывает.

`verification/gd_lint/tools.py` и `verification/tscn_lint/tools.py` **не меняются**: их
фрагменты не содержат `checked`/`unavailable`, и владелец обязан трактовать отсутствие
`checked` как `True`, отсутствие `unavailable` — как пустой список.


### 2.3 Сборка результата (`check/domain/core.py`) — дословно

1. `FRAGMENT` расширяется двумя **необязательными** полями (обязательные
   `problems`/`auto_fixable` не трогаем, `additionalProperties: False` сохраняется):

```python
FRAGMENT = {
    'type': 'object', 'required': ['problems', 'auto_fixable'], 'additionalProperties': False,
    'properties': {
        'problems': {'type': 'array', 'items': {'type': 'string'}},
        'auto_fixable': {'type': 'boolean'},
        'checked': {'type': 'boolean'},
        'unavailable': {'type': 'array', 'items': {
            'type': 'object', 'required': ['kind', 'reason'], 'additionalProperties': False,
            'properties': {'kind': {'type': 'string', 'minLength': 1},
                           'reason': {'type': 'string', 'minLength': 1}}}},
    },
}
```

2. Порядок видов задаёт **владелец**, а не порядок загрузки модулей (иначе алфавит поставит
   `api` перед `gd` и сломает паритет с эталоном, где линтер идёт первым — строки 1204–1206):

```python
ORDER = {'gd': 0, 'tscn': 0, 'api': 10, 'py': 20, 'json': 30, 'cfg': 40}
```

   `select()` возвращает выбранные вклады, отсортированные по `(ORDER[c.name], c.name)`;
   имя, которого нет в `ORDER`, — ошибка разработчика, а не «тихо в конец»:
   `raise AppError('internal', 'вклад проверки вне таблицы порядка')`. Тест обязан
   утверждать, что **каждый** зарегистрированный вклад (`registry.contributions('verify')`)
   есть в `ORDER`.

3. `problems` = конкатенация в порядке ORDER (§2.3, пункт 2): для `.gd` сначала сообщения линтера, потом API.
   Владелец **не** обрезает список (у `api_check` свой `MAX_PROBLEMS = 6`, у `gd_lint` свой
   `MAX_ERRORS = 8` — оба остаются как есть).

4. `checked` = `any(fragment.get('checked', True) for …)`; `kinds` = имена вкладов, которые
   реально вернули фрагмент (в порядке ORDER (§2.3, пункт 2)). Для `.gd` с кэшем: `kinds: ['gd', 'api']`,
   `checked: true`. Для `.gd` **без** кэша: `kinds: ['gd', 'api']`, `checked: true`
   (паритет: эталон считает `.gd` проверенным, потому что текстовый канал был).

5. `unavailable` = сначала записи вкладов (в порядке ORDER (§2.3, пункт 2), дословно), затем прежние
   «расширенческие» записи из `unavailable(ext, performed, requested)`. Существующее правило
   `{kind: 'api', reason: 'no_module'}` **остаётся** как страховка: оно срабатывает, только
   если вклад `api` не загрузился (тогда честно «модуля нет», а не «чисто»).

6. `unchecked_reason` — **только** когда `checked` ложно, ровно три формы:

```python
def unchecked_reason(ext, requested=None, performed=(), reasons=()):
    if ext in TEXT:
        if requested is not None and not performed:
            return ('ни один из запрошенных kinds (%s) не относится к расширению %s — '
                    'файл НЕ проверен' % (', '.join(sorted(set(requested))), ext))
        return ('ни одна проверка расширения %s не выполнена (%s) — файл НЕ проверен'
                % (ext, ', '.join(sorted(set(reasons))) or 'no_kind'))
    if ext in HEADLESS:
        return ('%s проверяется только настоящим Godot, а проверка отключена '
                '(--validation off) — файл НЕ проверен') % ext
    supported = ', '.join(sorted(set(TEXT) | set(HEADLESS)))
    return 'расширение %s не проверяется этим каналом (проверяются: %s)' % (
        ext or 'без расширения', supported)
```

   `reasons` — коды `reason` из `unavailable` тех фрагментов, у которых `checked` ложно
   (`no_cache`, `base_not_in_cache`, `no_extends`, …). Формы 3 и 4 (Godot-only и «канал не
   проверяет расширение») остаются **дословно** прежними.

### 2.4 Проекция «эталон → порт» для `.gd`

| Эталон (`agent_bridge._check_one_path`, 1199–1206) | Порт (`verify`) |
|---|---|
| `text_linted = True` для `.gd` | `checked: true` независимо от кэша |
| `problems.extend(gd_lint.lint_gdscript(text))`, затем `problems.extend(gd_api_check.check_api_usage(...))` | вклад `gd` (`gd_lint`) первым, вклад `api` (`api_check`) вторым; `problems` в том же порядке |
| `check_api_usage` молча возвращает `[]` без кэша/`extends` | `checked: true`, `problems: []` и **обязательно** `unavailable` с кодом причины — молчание не равно «чисто» |
| `result["auto_fixable"]` только для `.tscn` | не меняется: `auto_fixable = … and name == 'tscn'` |
| `headless`-словарь и причина из `--validation off` | как в C.9: `{kind: 'headless', reason: <дословный текст>}` в `unavailable` |
| `kinds` — нет в эталоне (расширение порта) | факт: имена вкладов, которые реально вернули фрагмент |

### 2.5 Вход и ошибки

Ничего не меняется: `path` обязан быть `res://…` (иначе `invalid_input`), `normalize_rel`
→ `denied`, `deny_reason` → `denied`, `fs.is_file` → `not_found`, байты >
`READ_TEXT_MAX_BYTES` → `invalid_input`, `PermissionError` → `denied`, прочий `OSError` →
`internal`. Новое единственное: `internal`, если вклад вне таблицы порядка или фрагмент не
прошёл `FRAGMENT` (это дефект кода, не пользователя). `errors` у `verify` прежние
(`invalid_input`, `not_found`, `denied`) — `internal` в контракте не объявляется.


## §3 Шаги

1. **Лист первым.** Дописать в `docs/porting/verification.check.md` раздел
   «Продолжение C.13 (вклад `api_check`)»: цель, что было обходом C.9, две правки (F2, F3),
   таблица «старый код → что делаем» (эталон 1199–1206), план корпуса. В `docs/PROGRESS.md`
   строку `verification.check` (этап **7**) дополнить пометкой `C.13: вклад api_check, F2/F3`
   — этап не снимается и не поднимается. Лист `verification.api_check.md` только дополняется
   строкой про `errors` (F2) и `contributes_to`.

2. **Корпус до кода.** Скрипт-перепроектор держать **вне аддона** (`%TEMP%\…`), он читает
   `fixtures/corpus/verification/check/*.json`, пересчитывает `expect.result` по §2.3–§2.4 и
   пишет `expect` обратно, `reference_result` **не трогает** (он снят с эталона, где API уже
   работал). Правила перепроекции:
   * `kinds` у `.gd` без фильтра `None` → `['gd', 'api']`;
   * `unavailable`: убрать `{kind: 'api', reason: 'no_module'}`, добавить записи вклада —
     в фикстурах корпуса кэша нет, значит `{kind: 'api_cache', reason: 'no_cache'}`;
     записи `headless` остаются последними;
   * `problems` не меняются (без кэша API молчит) — это удобная проверка, что вклад не врёт;
   * `018-filtered_gd` и `031-only_api` — новые тексты по §2.3.6;
   * `checked`/`auto_fixable` не меняются.
   Затем **новые кейсы** (≥8), фикстуры `fixtures/projects/corpus/verification/check/<variant>/`
   с `project.godot` и рукописным `.agent_history/godot_api_cache.json` (маленький:
   `Node2D → CanvasItem → Node → Object`, пара методов/свойств/сигналов; как C.11):
   * `.gd` с опечаткой в методе — `problems` = [сообщение линтера (если есть), сообщение API],
     порядок именно такой (`kinds: ['gd','api']`);
   * `.gd` чистый линтером, но с API-находкой — одно сообщение, `kinds: ['gd','api']`;
   * `.gd` с корректным `self.*` и кэшем — `problems: []`, `checked: true`, `unavailable`
     без `api_cache`;
   * `.gd`, `extends` которого нет в кэше → `unavailable: [{base_class, base_not_in_cache}]`;
   * `.gd` без `extends` → `unavailable: [{source, no_extends}]`;
   * `kinds: ['api']` с кэшем → `checked: true`, `kinds: ['api']`, только API-сообщения;
   * `kinds: ['gd']` с кэшем → API не запускался, `kinds: ['gd']`;
   * `kinds: ['gd','api']` (дубли и порядок) — паритет с `033-duplicate_kinds`.
   `manifest.json`: обновить `cases`/`inputs` (sha256+bytes), счётчик кейсов, добавить
   `"recut": "C.13: projection-only for .gd; reference results unchanged"` и
   `fixture_base: fixtures/projects` (не менять).

3. **Тесты красными до кода.** `python/modules/verification/check/tests/test_core.py`
   (FRAGMENT с `checked`/`unavailable`, порядок `ORDER`, три формы причины, страховка
   `no_module`, ошибка «вклад вне таблицы»), `tests/test_app.py` (вклад `api` зовётся,
   `problem`-порядок, отсутствие вклада → `no_module`), `tests/py/integration/test_verify.py`
   (`contributions('verify')` = `['api','gd','tscn']` в порядке загрузки, но `kinds` результата
   = `['gd','api']`; инвентарь 20 имён не меняется), `tests/py/contract/test_api_check_contract.py`
   (`errors`).

4. **Код**, в порядке: `check_kind.py` (докстринг) → `api_check/tools.py` (`errors`,
   `_verify_api`, `CONTRIBUTIONS`) → `api_check/module.py` (`contributes_to`) →
   `check/domain/core.py` (`FRAGMENT`, `ORDER`, `select`, `assemble`, `unchecked_reason`).
   `app.py` ≤ 80 строк, `tools.py` ≤ 150, в `domain/` нет IO.

5. **Контракт.** `python -B tools/gen_contract.py --write` → меняется **только**
   `contract/capabilities/api_check.json` (список `errors`), `--check` = 21 артефакт.
   `check.json`/`verify.json` обязаны остаться байт-в-байт — если `--write` их переписал,
   значит схема поехала: откат и разбор.

6. **Двойной прогон.** non-live (2815 + новые тесты), `snapshot_diff` (609 + новые кейсы;
   строка `verification/check` должна стать `62+new`), `selfcheck` для
   `verification.check`, `verification.api_check`, `verification.gd_lint`,
   `verification.tscn_lint` (числа: api_check 206/52, gd_lint 126/37, tscn_lint 315/65 —
   не должны сдвинуться), `lint_arch`/`check_limits`, `security_audit`, live = 3.

7. **Записи.** Лист (раздел C.13, статус по-прежнему этап 7 — «принято аудитом, доработка
   C.13»), `docs/parity.md:68` (дописать «вклад в `verify` принят C.13»),
   `docs/tests-map.md` (новые/изменённые тесты), `docs/PROGRESS.md` (пометка),
   `docs/WORKLOG.md` (сессия). `docs/porting/_audit-handoff.md` **не трогать**.

8. **Чего не делать:** не «улучшать» эталон (порядок, `MAX_PROBLEMS`, тексты), не тащить
   `headless`, не заводить второй `api`-путь в `check/domain`, не трогать
   `tools/selfcheck.py` (долг F4), не копировать 2 МБ кэш в фикстуры — только маленький
   рукописный.


## §4 Решения, которые уже приняты (не пересматривать)

1. **Вклад, а не второй вызов внутри владельца.** `check/domain/core.py` не должен знать про
   `.gd`-специфику: он работает с гомогенными фрагментами, поэтому API приходит вкладом через
   `CONTRIBUTIONS`, как `tscn`. Второй вызов «просто для .gd» сломал бы `kinds`-фильтр.
2. **Порядок задаёт владелец таблицей `ORDER`**, а не `CheckKind`: сигнатура дескриптора
   (`name, extensions, lint`, `__slots__`) принята C.9 и не меняется, иначе придётся править
   три принятых вклада. Таблица + тест полноты (каждый вклад обязан быть в `ORDER`).
3. **`checked` для `.gd` остаётся `true` даже без кэша** — паритет с эталоном
   (`text_linted` делает `.gd` проверенным). «Чего не смогли» показываем в `unavailable`,
   а не через `checked`.
4. **`checked`/`unavailable` вклада переносятся дословно**, коды остаются эталонными
   (`no_cache`, `base_not_in_cache`, `no_extends`). Для старых вкладов действуют умолчания
   (`checked=True`, `unavailable=[]`) — поэтому `gd_lint/tools.py` и `tscn_lint/tools.py`
   остаются байт-в-байт.
5. **F2:** `errors=('invalid_input', 'denied')`. `not_found` не объявляем — инструмент файл
   не читает (путь только нормализуется). Карточка меняется только в этом поле.
6. **F3:** три формы причины (§2.3.6). Текст про «только настоящий Godot» остаётся ровно для
   расширений без текстового канала и не перефразируется.
7. **`kinds` — факт, а не запрос:** перечисляем вклады, которые вернули фрагмент.
8. **Список `problems` владелец не обрезает** — лимиты внутри механик (`MAX_ERRORS = 8`,
   `MAX_PROBLEMS = 6`) сохраняют свой смысл.
9. **Карточки:** `check.json` и `verify.json` — байт-в-байт; `api_check.json` — только `errors`.
   Инвентарь инструментов не меняется (20 имён), новых карточек нет (21 артефакт).
10. **Корпус: `reference_result` не пере-снимаем**, потому что эталон уже включал API
    (строки 1204–1206), и это видно по 62 кейсам: API-сообщений в них нет только потому, что
    в фикстурах нет кэша. Перепроекции подлежит ровно `expect.result`.

## §5 Доказательства (портер сдаёт, аудитор повторит)

| # | Мутация (файл, что ломаем) | Обязательный красный |
|---|---|---|
| M1 | `core.py`: `ORDER` → `{'gd': 10, 'api': 0, …}` (порядок перевёрнут) | кейс «линт + API в одном файле» |
| M2 | `core.py`: `assemble` считает `checked = True` всегда | `kinds: ['py']` на `.gd`, `.tres` |
| M3 | `core.py`: не переносить `unavailable` фрагмента | кейс «`.gd` без кэша» |
| M4 | `core.py`: старая форма причины для текстовых расширений | `018`, `031` |
| M5 | `api_check/tools.py`: вклад возвращает `'\n'.join(problems)` | любой API-кейс |
| M6 | `api_check/tools.py`: вклад не передаёт `checked` | `kinds: ['api']` без кэша |
| M7 | `core.py`: `select` не сортирует (порядок загрузки) | тот же кейс порядка, что M1 |
| M8 | `core.py`: `unavailable` не включает вкладовы записи | кейс «нет кэша» и «базы нет в кэше» |

Подложки (обязаны ловиться **гейтом**, а не юнит-тестом):

* **P1** — `api_check/tools.py`: `errors=('invalid_input',)` (то есть откат F2) →
  `python -B tools/gen_contract.py --check` должен сказать `контракт: api_check.json`, а тесты
  остаться зелёными (это доказывает, что пин `errors` живёт в гейте, а не только в тесте).
* **P2** — `check/domain/core.py`: `import os` → `lint_arch` «domain/ запрещает IO-модуль os».
* **P3** — `check/app.py`: импорт `python.modules.verification.api_check.domain.core` →
  `lint_arch` «чужой модуль» (шов ADR-0010 разрешён только в обратную сторону,
  `api_check/app.py → engine_kb.shared.inheritance`).

Правила прогона (мои грабли из сессии 64, соблюдай):

* мутации — **по одной**, последовательно, с байтовым бэкапом в `%TEMP%` и `sha256` до/после;
* **не убивать** процесс мутаций посередине: `Stop-Process` оставляет мутированный файл
  (у меня так `check/…/core.py` стал 4546 B вместо 4551 и пришлось восстанавливать из бэкапа);
* `--junitxml` передавать из python-драйвера (`subprocess`), а не через
  `Start-Process python -ArgumentList …`: PowerShell ломает склейку аргумента;
* `recovery: plan=… expired` в stderr — это WAL-реплей старых планов, не провал; смотреть на
  `exit code` и на пустой список падений;
* обратная проекция: перечислить каждый изменённый файл с `sha256` и размером, плюс явно
  показать, что `gd_lint/**`, `tscn_lint/**`, `shared/source_text.py`, `api_check/domain/**`,
  `check.json`, `verify.json` не изменились;
* гигиена: `__pycache__`/`.pytest_cache` 0, `*.bak|tmp|orig` 0, `zz_*` 0,
  `.gd.uid` = 83 (live создаёт 111 новых — удалить ровно их, 8 исторических не трогать),
  файлов = 2310 + новые, временных скриптов в аддоне нет.


## §6 Стоп-условия (остановиться и спросить)

* Чтобы получить паритет, нужно **поменять** `verification/gd_lint/**`,
  `verification/tscn_lint/**`, `verification/api_check/domain/**` или
  `verification/shared/source_text.py` — значит проекция выбрана неверно, останавливайся.
* Хочется расширить `CheckKind` (новый обязательный аргумент, новое поле в `__slots__`) или
  переписать принятые вклады — нельзя, порядок задаёт таблица владельца.
* `check.json` или `verify.json` после `gen_contract --write` изменились — схема поехала.
* Корпус нельзя сделать стабильным без правки фикстур C.9 (кроме добавления новых вариантов).
* Числа соседей поехали (`gd_lint` не 126/37, `tscn_lint` не 315/65, `api_check` не 206/52,
  `class_api` не 186/26) — сначала разбор, потом продолжение.
* Появляется соблазн «сделать чисто» при отсутствии кэша (то есть вернуть `problems: []` без
  `unavailable`) — это ровно тот дефект, который срез и убирает.

## §7 Что будет проверять аудитор

1. **Своя пересъёмка** корпуса: мой скрипт читает `reference_result` **и** заново дёргает
   эталон `agent_bridge._check_one_path` (путь `res://…`, `validation: off`) на копии фикстуры,
   затем независимо проецирует и сравнивает с `expect.result`. Расхождение = провал.
2. **Дифференциал шире корпуса**: все `.gd` в `fixtures/**` (в C.12 их было 378) в двух
   режимах — с кэшем фикстуры и с реальным кэшем 2 004 630 B — через `verify` против эталона.
   После C.13 расхождений по `problems` быть **не должно** (кроме документированных границ:
   лимит 4 MiB и `denied` на `addons/`). До среза порт терял API-сообщения — это и есть
   главный признак приёмки.
3. **Свои мутации** M1–M8 и подложки P1–P3, с байтовым восстановлением и сверкой sha256.
4. **Инвентарь:** `gen_contract --check` = 21, в `contract/capabilities` 22 файла,
   `context.gather` = 20 имён (`api_check: read`, `verify: read`), `# verb:` = 6,
   `verbs_version: 3`; изменение `api_check.json` — только `errors`; `check.json`/`verify.json`
   побайтово те же.
5. **Принятые механики**: selfcheck `gd_lint` 126/37, `tscn_lint` 315/65, `api_check` 206/52,
   `class_api` 186/26, `domain/`-хэши из §0 не сдвинулись; `snapshot_diff` = 609 + новые кейсы.
6. **Гигиена и живое:** 3 live, `.gd.uid` 83 после уборки 111, мусора 0, файлы = 2310 + новые.

## §8 Финальный прогон и записи

Один отчёт — в лист `docs/porting/verification.check.md` (раздел C.13) и запись в
`docs/WORKLOG.md`. Обязательные числа в отчёте:

* `pytest --ignore=tests/py/live` (кол-во, время, stderr) и `--collect-only` (файлы/тесты);
* `python -B tools/snapshot_diff.py` — общий счётчик и строка `verification/check`;
* `python -B tools/selfcheck.py verification.check` (unit/corpus/layers/limits/contract/
  security, вердикт) + `reports/selfcheck/verification.check.json`;
* `python -B tools/gen_contract.py --check` = 21;
* `python -B tools/lint_arch.py`, `python -B tools/check_limits.py`, `security_audit`;
* `pytest tests/py/live` = 3;
* дерево/`.gd.uid`/мусор;
* таблица §5 с `sha256` до/после каждой мутации и перечень восстановленных файлов.

Записи: лист (C.13), `docs/parity.md:68`, `docs/tests-map.md`, `docs/PROGRESS.md`,
`docs/WORKLOG.md`. **Не писать**: «принято», «ported», этап 7 в новой строке,
`docs/porting/_audit-handoff.md`, `contract/editor_verbs.json`, `python/kernel/schema.py`,
`tools/lint_arch.py`, `tools/gen_contract.py`, `tools/security_audit.py`,
`tools/snapshot_diff.py`, `tools/selfcheck.py`.

Сдавать так: «C.13 готов к независимому аудиту, не принято» + список изменённых файлов
с `sha256` + честный список границ, которые остались.

