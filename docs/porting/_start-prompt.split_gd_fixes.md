# C.16 — закрытие F6/F7 и ретро-разрешение F8 (тексты отказов, фактический `newline`, каталог в `security_audit`)

Ты — **портер**. Аудитор — отдельный чат, он же ставит этапы. Ты **не** ставишь себе
этап, **не** пишешь «выполнено/принято/ported», **не** правишь `docs/porting/_audit-handoff.md`.
Готовность объявляешь так: «C.16 готов к независимому аудиту, не принято» — и всё.
Приёмка только по **своим** прогонам аудитора; его числа могут отличаться от твоих,
и это нормально.

Этот срез — **исправление найденного аудитором в C.15**: три находки (F6, F7) в
принятой механике `editing.split_gd` и одна процедурная (F8) вокруг замороженного
гейта `tools/security_audit.py`. Новых инструментов, портов и модулей нет.

## Читать до первой строки кода

1. `AGENTS.md`, `RULES.md` (R-02, R-05, R-09, R-11, R-12, R-13, R-22), `docs/architecture.md`,
   `docs/PORTING.md`.
2. `docs/parity.md` — строка `split_gd_scan/plan`; `docs/PROGRESS.md` — строка `editing.split_gd`
   (сейчас **7**); `docs/tests-map.md` — все строки `split_gd*`, `security_audit`.
3. Свой лист `docs/porting/editing.split_gd.md` целиком (там C.14, C.15 и **приёмка
   аудитом сессии 69**, включая описание F6/F7/F8), а также §5 и §6
   `docs/porting/_audit-handoff.md` (находки F6/F7/F8/F9 и долг F4).
4. `docs/adr/0011-fs-exists-split-gd.md`, `docs/security/invariants.md`,
   `docs/WORKLOG.md` — три последние сессии.
5. `python/modules/editing/split_gd/` — `app.py`, `plan_io.py`, `domain/core.py`,
   `domain/render.py`, `domain/text.py`, `tools.py`, `tests/`.
6. `python/modules/verification/check/domain/core.py` — как в проекте уже живут
   `ORDER`, `FRAGMENT` и тексты отказов (образец стиля, не менять).

Ничего не переписывай «по памяти»: числа и пути ниже сняты аудитором в сессии 69.

## §0 База (снято аудитом, сессия 69, 2026-10-31 — не пересчитывать)

- Non-live: **3589** passed (junit 3589/0/0/0, 131.167 s, stderr пуст), collect **102** файла.
- Live: **3** passed, 0 skip (28.004 s). Предусловие: во **внешнем**
  `D:\vajno\Godot\agent-rebuild\project.godot` (335 B, sha256 `958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`)
  должен быть включён `[editor_plugins] enabled=PackedStringArray("res://addons/godot_agent/plugin.cfg")`;
  портер включает его на время прогона и **возвращает файл побайтово** (свойство среды L1, не дефект).
  Godot: `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`.
- `tools/snapshot_diff.py` → **724/0** (в т.ч. `editing/split_gd` 102/102).
- `tools/gen_contract.py --check` → **23** артефакта (24 файла с `_template.json`).
- `selfcheck editing.split_gd` → unit **600 passed**, corpus **102**, layers/limits **522/0**,
  contract 23, security ok, вердикт ok. Соседи: `verification.check` 188/75,
  `verification.api_check` 206/52, `verification.gd_lint` 126/37, `verification.tscn_lint` 315/65,
  `engine_kb.class_api` 186/26 (186 — долг **F4** в `tools/selfcheck.py:215`, **не исправлять**).
- Дерево **2773** файла, `.gd.uid` **83** (8 исторических из `fixtures/parity/gdscript/`, 2026-10-27,
  не трогать), мусора 0, листов 25, промптов **34** → 35, ADR **11** → 12, правил 22,
  строк `PROGRESS` 44 (23 на этапе 7 / 1 на 6 / 20 на нуле).
- Замороженные гейты (байт-в-байт, кроме `security_audit.py` — см. §9):
  `python/kernel/schema.py` `629FCE54E6FE…` (147 строк, CRLF), `tools/gen_contract.py` `FA7E6E91C872…`,
  `tools/snapshot_diff.py`, `tools/selfcheck.py`, `tools/lint_arch.py` 9842 B `A6C5EDD47650…`,
  `contract/editor_verbs.json` `CDAF8D23A6BF…`, `editor/bridge/verbs/scene/scene_executor.gd` `B7AFF592B75D…`.

### §0.1 Файлы среза (размер / sha256-16, снято аудитором)

| Файл | Байт | sha256 (16) |
|---|---|---|
| `python/modules/editing/split_gd/tools.py` | 4966 | `27AEE57AB3D0…` |
| `python/modules/editing/split_gd/app.py` | 3538 | `5200B1AAD45D…` |
| `python/modules/editing/split_gd/plan_io.py` | 823 | `A38175346FFC…` |
| `python/modules/editing/split_gd/domain/core.py` | 9222 | `13DA6E384299…` |
| `python/modules/editing/split_gd/domain/text.py` | 1744 | `6F0C5A835330…` |
| `python/modules/editing/split_gd/domain/render.py` | 8964 | `457A2C9FDFBB…` |
| `python/modules/editing/split_gd/domain/engine.py` | 3002 | `783B2B59CE0D…` |
| `contract/capabilities/split_gd_plan.json` | 4638 | `A7CF999F6FCE…` |
| `tools/security_audit.py` | 10885 | `77956BE3BE9F…` (до C.15 — 10831 / `2CF0D7F6B1AF…`) |
| `python/substrate/fs/disk_fs.py` | 3987 | `4224F2D04175…` (шов `exists`, ADR-0011) |

Эталон (только читать): `python/godot_tools/split_gd.py` — **63 421 B, 1333 LF, 0 CRLF,
sha256 `18f05d10b8e875ed77040b8a47beb6ccbdb409b55d791ec0318466473969bfc7`**;
второй адрес `python/tools/agent_bridge.py` (142 171 B, `a9b1ad832fd0…`),
`_split_gd_target_lines:1022`, `cmd_split_gd:1035`.
Git в `agent-rebuild` нет намеренно.
## §1 Границы среза

Срез — **доводка уже принятой механики** `editing.split_gd` (этап 7, инструменты
`split_gd_scan` и `split_gd_plan`). Ничего нового не добавляется: ни инструмента,
ни карточки, ни порта, ни модуля. Меняются три вещи и ровно они.

**F6 — тексты отказов.** Сейчас отказы по `target_lines` и по пустому `funcs`
отдаёт **схема** `ToolSpec.args`, поэтому текст свой:
`(аргументы).target_lines: больше 5000` вместо эталонного
`target_lines must be between 100 and 5000`, и
`(аргументы).groups[0].funcs: меньше 1 элементов` вместо
`группа part_one: пустой список funcs`.
Проверено аудитором: правильные тексты в коде **уже есть** —
`core.target_lines` (строки 23–29) и `render.normalize_groups`
(`пустой список групп (--groups или auto)`, `группа %d: некорректное имя модуля %r`,
`модуль %s указан дважды`, `группа %s: пустой список funcs`,
`метод %s не найден в доноре`, `метод %s назначен дважды (модули %s и %s)`).
Они недостижимы только потому, что схема отбрасывает вход раньше.

**F7 — `newline`.** Публикуемое поле — артефакт универсальных переводов строк:
`core.plan` берёт `text.newline_of(text)` (~строка 149), а `text.decode` уже свёл
`\r\n`/`\r` к `\n` (строка 8), поэтому в ответе **всегда** `'\n'`. Кейсы
`141-bom_crlf`, `142-crlf` (файл `\r\n`) и `143-cr_only` (файл `\r`) это показывают.
Решение аудитора: поле обязано быть **фактическим** концом файла — им будет
пользоваться запись (C.17). Это **осознанное расхождение с эталоном** (как лимит 4 MiB),
оно фиксируется документально; `decode()` продолжает нормализовать к `\n`
(иначе поедут sha256 и парсер).

**F8 — замороженный гейт.** В C.15 в `tools/security_audit.py` появилась строка
`if not path.is_file(): continue` (10831 → 10885 B). Проверено аудитором: без неё гейт
падает `PermissionError` на каталоге
`fixtures/projects/corpus/editing/split_gd_plan/existing_module_dir/editor/part_one.gd`
(это каталог, нужный паритетному кейсу `140-existing_module_dir`), с ней —
`{"status": "ok", "detail": "нарушений нет"}`. Правка минимальна и верна, но в
разрешении её не было и в листе она не описана. §9 даёт ретро-разрешение и требует
ADR + красный тест; откатывать не нужно.

### В срезе

- `tools.py` — из `PLAN.args` убрать `minimum`/`maximum` у `target_lines` и
  `minItems` у `GROUP.funcs`; `type: 'integer'`/`'array'` **оставить**
  (кейс `152-target_not_integer` держится именно на нём). `RESULT.newline.enum`
  расширить до `['\n', '\r\n', '\r']`.
- `app.py`, `plan_io.py`, `domain/core.py`, `domain/text.py` — фактический `newline`
  из **сырых байт** донора.
- Корпус `fixtures/corpus/editing/split_gd/`: перепроекция `expect` у `108`, `109`, `130`
  (текст теперь пинится) и у `141`, `142`, `143` (фактический `newline`);
  `reference_result`/`reference_public` **не переснимать**, они остаются сырыми;
  обновить `cases`/`inputs` (sha256+bytes) и добавить `c16_recut` с описанием.
- Тесты: `tests/py/integration/test_split_gd_plan.py`,
  `tests/py/contract/test_split_gd_plan_contract.py`,
  `python/modules/editing/split_gd/tests/*` — пины текстов и `newline`;
  новый `tests/py/tools/test_security_audit_dirs.py`.
- `docs/adr/0012-security-audit-directories.md` — новый ADR (§9).
- Записи: лист `docs/porting/editing.split_gd.md` (раздел «C.16»), `docs/parity.md`,
  `docs/tests-map.md`, `docs/PROGRESS.md`, `docs/WORKLOG.md`.

### Не в срезе

Запись и применение (`_make_split_gd_prepared:2041`, `apply_prepared_split:1177`,
`_godot_check:1162`, `write_preview action split_gd`) — это **C.17**;
`split_gd_scan` и его 47 кейсов, `domain/refs.py`, `domain/inventory.py`,
`domain/engine.py`; `editing.split_py`, `editing.file_refactor`;
`verification.*`, `engine_kb.*`, `scene_model.*`, `code_intel.*`;
`python/kernel/*`, `python/substrate/*` (только чтение), `python/runtime/*`,
`python/protocol/*`; `contract/editor_verbs.json`, `editor/**`;
`tools/gen_contract.py`, `tools/lint_arch.py`, `tools/snapshot_diff.py`,
`tools/selfcheck.py` (долг F4); любая правка `tools/security_audit.py` сверх уже
существующей строки; `docs/porting/_audit-handoff.md` — его правит только аудитор.

### Разрешённые правки вне папки и корпуса — ровно три

1. `fixtures/corpus/context/gather/001-all-sections.json` — **не менять** (имён 22).
   Если тест требует обновить SHA записи `001-all-sections` в
   `fixtures/corpus/context/gather/manifest.json` — правь **только** эту запись
   (sha256/bytes), прочие поля и EOL сохрани.
2. `docs/tests-map.md` — строка нового теста и правки пинов (числа фактические).
3. `fixtures/corpus/scene_model/scene_deps/manifest.json` — только если изменённые
   `.gd` попали в покрытие `test_capture_covers_every_current_required_gd`: правки
   **append-only**, прежние 252 факта и их порядок сохраняются.

Всё остальное — байт-в-байт. Фактические правки вне папки перечисли в листе и в
`WORKLOG` (аудитор делает обратную проекцию по sha256).

## §2 Контракт и раскладка

### 2.1 `PLAN.args` — ровно два удалённых ключа

Было (сессия 69) и стало:

```python
    'properties': {
        'path': {'type': 'string', 'minLength': 1},
        'groups': {'type': 'array', 'items': GROUP},
        # было: {'type': 'integer', 'minimum': 0, 'maximum': 5000}
        'target_lines': {'type': 'integer'},
    },
```

```python
GROUP = {
    'type': 'object', 'required': ['module', 'funcs'], 'additionalProperties': False,
    'properties': {
        'module': {'type': 'string', 'minLength': 1},
        # было: {'type': 'array', 'minItems': 1, 'items': {'type': 'string'}}
        'funcs': {'type': 'array', 'items': {'type': 'string'}},
    },
}
```

`SCAN` (`split_gd_scan`) и `TOOLS = (SCAN, PLAN)` не меняются байт-в-байт.

Почему границы уходят из схемы: `schema.validate` срабатывает **до** `app.call`,
поэтому тексты эталона недостижимы. После правки поток такой:
`validate` (структура/типы) → `core.target_lines(args.get('target_lines'))` →
`render.normalize_groups(...)`; оба уже отдают дословные эталонные строки.
Кейс `152-target_not_integer` (`target_lines: '100'`) обязан остаться
`invalid_input` — его ловит `type: 'integer'`, не убирай.

### 2.2 Фактический `newline` (F7)

`domain/text.py`:

```python
def decode(raw):
    """Как сейчас: одна ведущая BOM снимается, CRLF/CR сводятся к LF."""
    ...


def file_newline(raw):
    """Фактический конец файла — по СЫРЫМ байтам, а не по нормализованному тексту."""
    if b'\r\n' in raw:
        return '\r\n'
    if b'\r' in raw:
        return '\r'
    return '\n'
```

`newline_of(text)` удалить (или оставить приватным без использования) — публичный
факт считается только по байтам. `core.plan(...)` получает `newline` **аргументом**
(не вычисляет сам), `app.py`/`plan_io.py` передают результат `file_newline(raw)`,
где `raw` — ответ `fs.read_raw(...)`.

`RESULT.newline`: `{'type': 'string', 'enum': ['\n', '\r\n', '\r']}`.
`donor_sha256` **не менять** — он считается по `decode(raw)` (эталонный `_sha256(_read_text(...))`).

### 2.3 Пины корпуса (F6/F7)

Три кейса вместо свободного текста начинают пинить сообщение:

| Кейс | `expect.kind` | `expect.result` | `expected_message` (пин в тесте) |
|---|---|---|---|
| `108-target_below_minimum` | `invalid_input` | — | `target_lines must be between 100 and 5000` |
| `109-target_above_maximum` | `invalid_input` | — | `target_lines must be between 100 and 5000` |
| `130-empty_funcs` | `invalid_input` | — | `группа part_one: пустой список funcs` |

Три кейса получают фактический `newline` в `expect.result`:
`141-bom_crlf` → `'\r\n'`, `142-crlf` → `'\r\n'`, `143-cr_only` → `'\r'`.
`reference_public.newline` в этих кейсах остаётся `'\n'` — это и есть зафиксированное
расхождение; в `manifest.json` добавь блок `c16_recut` с перечислением шести кейсов
и причиной, `contract_refusals`/`plan_capture` не переписывай.

### 2.4 ADR-0012 и красный тест для F8 (§9)

ADR `docs/adr/0012-security-audit-directories.md` (~40 строк): контекст (гейт обходит
дерево, каталоги с именем `*.gd` существуют как фикстуры точного паритета),
решение (`files()` возвращает только обычные файлы; каталоги пропускаются
до чтения; поведение для файлов не меняется), последствия (гейт не падает на
каталогах; ослабления проверок нет — каталог не является проверяемым артефактом),
границы (не расширять на симлинки/прочие спец-файлы, не менять `SKIP_DIRS`).

Тест `tests/py/tools/test_security_audit_dirs.py`:

1. во временном дереве создать каталог с именем `x.gd` и обычный `y.gd`;
2. `files(base, '.gd')` возвращает только `y.gd` (каталог не попадает);
3. прогон гейта на таком дереве — `status ok` и **без** `PermissionError`;
4. регресс-пин: строка `if not path.is_file(): continue` обязана существовать в
   `tools/security_audit.py` (проверка по тексту файла с точным ожиданием).

## §3 Шаги

1. **Лист первым.** В `docs/porting/editing.split_gd.md` добавь раздел
   «C.16 — F6/F7/F8 (сессия 70)»: три находки, что меняется, что осознанно расходится
   с эталоном и почему. Сними sha256 файлов из §0.1 как базу обратной проекции.
   `PROGRESS` пока не трогай (строка остаётся **7**, аннотацию добавишь в шаге 8).
2. **Корпус до кода.** Перепроектор держи вне аддона (`%TEMP%`). Правило:
   `reference_result`/`reference_public` **не пересчитывать**; меняется только `expect`
   (шесть кейсов из §2.3) + `cases`/`inputs` sha256+bytes + блок `c16_recut`.
   Проверь, что `id` кейсов не изменились, а число кейсов `editing/split_gd`
   по-прежнему **102**.
3. **Красные тесты до кода.**
   - `tests/test_core.py`: `target_lines(99)`/`(5001)`/`('100')` → `AppError` с дословным
     текстом; `(0)` и `(None)` → 1100.
   - `tests/test_render.py`: пустой `funcs` → `группа %s: пустой список funcs`.
   - `tests/test_app_plan.py`: `'100'` → `invalid_input` (схема), `99` → текст эталона.
   - `tests/py/integration/test_split_gd_plan.py`: для `108/109/130` —
     `answer['message'] == case['expected_message']`; для `141/142/143` — `result['newline']`
     и `reference_public['newline'] == '\n'` (расхождение фиксируется явно).
   - `tests/py/contract/test_split_gd_plan_contract.py`: `RESULT.newline.enum` содержит `'\r'`.
   - `tests/py/tools/test_security_audit_dirs.py` (§2.4).
   Зафиксируй, что до правок они красные, и счёт прогона.
4. **Код** в порядке: `domain/text.py` (`file_newline`, убрать использование
   `newline_of`) → `domain/core.py` (`plan(...)` принимает `newline`) →
   `plan_io.py`/`app.py` (передать факт из `read_raw`) → `tools.py` (два удалённых
   ключа + enum). Лимиты: `domain/` без `os`/`pathlib`/`socket`/`subprocess`,
   `app.py` ≤ 80 строк, `tools.py` ≤ 150, файл ≤ 400 (`kernel/limits.FILE_MAX_LINES`).
5. **ADR-0012** + пин-строка гейта (§2.4). Сам `tools/security_audit.py` **не править**:
   нужная строка уже там (10885 B), задача — закрепить её ADR и красным тестом.
6. **Контракт.** `python -B tools/gen_contract.py --write` — меняется **только**
   `contract/capabilities/split_gd_plan.json`; остальные 22 карточки байт-в-байт;
   `--check` → **23**.
7. **Двойной прогон.** `python -B -m pytest python/modules tests/py --ignore=tests/py/live`
   (3589 + новые; junit только через `subprocess`-драйвер, не через `Start-Process`);
   `tools/snapshot_diff.py` (724/0, `editing/split_gd` 102/102);
   `selfcheck editing.split_gd` (unit 600 + новые, corpus 102, layers/limits 522/0,
   contract 23); соседи `verification.check` 188/75, `verification.api_check` 206/52,
   `verification.gd_lint` 126/37, `verification.tscn_lint` 315/65,
   `engine_kb.class_api` 186/26 — числа не должны сдвинуться; `tools/lint_arch.py`,
   `tools/check_limits.py`, `tools/security_audit.py` — ok; live = **3** без skip;
   `.gd.uid` 83 после уборки (удаляй ровно сгенерированные; редактор удаляет корневой
   `plugin.gd.uid` — верни его побайтово).
8. **Записи.** Лист (этап **7** + раздел C.16 с доказательствами), `docs/parity.md`
   (строка `split_gd_scan/plan`: F6/F7 закрыты, запись — C.17), `docs/tests-map.md`,
   `PROGRESS` (строка остаётся **7**, текст дополняется), `WORKLOG` (сессия).
   «Принято/ported» и «этап 7 заново» не писать.

## §4 Решения, которые уже приняты (не пересматривать)

1. Границы валидируются **в домене**, не в схеме: эталонный текст важнее «богатой»
   схемы. `type` остаётся; `minimum`/`maximum` у `target_lines` и `minItems` у
   `GROUP.funcs` уходят.
2. `newline` — **фактический** конец файла из сырых байт. Осознанное расхождение
   с эталоном: `reference_public` не переписывается, `donor_sha256` по-прежнему
   считается по нормализованному тексту.
3. `decode()` продолжает сводить CRLF/CR к LF — на нём держатся sha256, парсер и
   принятые 102 кейса.
4. `152-target_not_integer` (`'100'`) остаётся `invalid_input` за счёт `type: 'integer'`.
5. `security_audit.py` приводится в соответствие **ADR + красным тестом**, не откатом:
   строка нужна, каталог с именем `*.gd` — легальная фикстура паритета.
6. `split_gd_scan` (47 кейсов), `domain/refs.py`, `domain/inventory.py`,
   `domain/engine.py` не трогаются вообще.
7. Новых методов `fs`/`api_cache` не появляется; шов `exists` остаётся один (ADR-0011).

## §5 Доказательства

Мутации (по одной за раз, байтовый бэкап, сверка sha256 после откката):

| # | Мутация | Что обязано покраснеть |
|---|---|---|
| M1 | вернуть `'minimum': 0, 'maximum': 5000` в `target_lines` | `108`, `109` (текст) |
| M2 | вернуть `'minItems': 1` в `GROUP.funcs` | `130` |
| M3 | считать `newline` через `newline_of(text)` | `141`, `142`, `143` |
| M4 | `file_newline` всегда `'\n'` | `141`, `142`, `143` |
| M5 | убрать `'\r'` из `RESULT.newline.enum` | контрактный тест + `gen_contract --check` |
| M6 | `target_lines(99)` без проверки границ | unit `test_core` |
| M7 | вернуть прежний текст «пустой funcs» | `130` + unit `test_render` |
| M8 | `donor_sha256` по сырым байтам | `141` (BOM) |

Подложки:

- **P1** — убрать `'newline'` из `RESULT.required`: юнит-тесты зелёные,
  `gen_contract --check` красный (`fail: split_gd_plan.json`).
- **P2** — `import os` в `domain/core.py`: `lint_arch` красный, тесты зелёные.
- **P3** — удалить `if not path.is_file(): continue` из `tools/security_audit.py`:
  `tests/py/tools/test_security_audit_dirs.py` красный (пин F8); после откката файл
  снова 10885 B байт-в-байт.

Обратная проекция: по каждому изменённому файлу — bytes + sha256 «до/после», плюс
доказательство, что 22 прежние карточки, `split_gd_scan` с 47 кейсами, `editor/`,
`python/kernel/*`, `python/substrate/*`, `python/runtime/*`, `python/protocol/*`,
`verification/*`, `engine_kb/*` байт-в-байт.

Гигиена: дерево = 2773 + новое (этот промпт, ADR-0012, один новый тест), `.gd.uid` 83,
`__pycache__`/`.pytest_cache`/`.bak|.tmp|.orig`/`zz_*` = 0, временных скриптов в аддоне нет.

## §6 Стоп-условия

Остановись и напиши аудитору, если:

1. для паритета нужно менять `python/kernel/schema.py` (формат сообщений `validate`),
   `python/substrate/*`, `python/runtime/*` или `python/protocol/*`;
2. для F7 требуется переснять `reference_public`/`reference_result` (не требуется —
   расхождение фиксируется в `expect`);
3. `snapshot_diff` на `editing/split_gd` перестаёт быть 102/102 без правки кейсов;
4. числа соседей сдвинулись (`check` 188/75, `api_check` 206/52, `gd_lint` 126/37,
   `tscn_lint` 315/65, `class_api` 186/26);
5. чтобы уложиться, хочется тронуть `split_gd_scan` или его кейсы;
6. `security_audit` требует правки сверх одной уже существующей строки;
7. тесты становятся зелёными только при ослаблении пина (например, если из
   `expected_message` убрать текст).

## §7 Что будет проверять аудитор

- Свою пересъёмк эталонных ответов для шести кейсов: `109`/`108` — текст
  `target_lines must be between 100 and 5000`, `130` — `группа part_one: пустой список funcs`
  (через живой `agent_bridge._split_gd_target_lines`/`split_gd._normalize_groups`),
  `141/142/143` — фактический байтовый конец файла; сверка `expect` и того, что
  `reference_public` остался сырым.
- Свой дифференциал по всем 41 `.gd`-донорам фикстур `split_gd_plan` в двух режимах
  (`target_lines` 1100 и 100): расхождения допустимы **только** документированные —
  лимит 4 MiB, отказы политики `addons/`, отсутствие `plugin.cfg`, и `newline`
  у CRLF/CR/BOM-доноров.
- Свои мутации M1–M8 и подложки P1–P3, включая **откат** строки в `security_audit.py`
  (обязана покраснеть и вернуться байт-в-байт).
- Инвентарь: `gen_contract --check` = 23, файлов в `contract/capabilities` 24,
  `context.gather` 22 имени, `# verb:` 6, `verbs_version: 3`; `split_gd_plan.json`
  изменился только в двух местах (`target_lines` без границ, `GROUP.funcs` без `minItems`,
  `newline.enum` с `'\r'`).
- Принятые механики: те же selfcheck-числа и те же sha256 у `domain/` соседей,
  `snapshot_diff` 724 + новые кейсы (число кейсов не меняется).
- Гигиену, `.gd.uid` 83, live 3, дерево.

## §8 Финальный прогон и записи

Один отчёт в листе + `WORKLOG`: non-live (число, время, collect), `snapshot_diff`
(число и строка `editing/split_gd`), таблица `selfcheck editing.split_gd`,
`reports/selfcheck/editing.split_gd.json`, `gen_contract --check` (23),
`lint_arch`, `check_limits`, `security_audit`, live (3), дерево/`.gd.uid`/мусор,
таблица мутаций с sha256 и обратная проекция.

Пиши: лист (этап 7 + раздел C.16), `docs/parity.md`, `docs/tests-map.md`,
`docs/PROGRESS.md`, `docs/WORKLOG.md` (только **append** в режиме `ab`, **без**
нормализации переводов строк — исторический префикс 4479 CRLF обязателен).

Не пиши: `docs/porting/_audit-handoff.md`, «принято/ported», новый этап 7,
`contract/editor_verbs.json`, `python/kernel/schema.py`, `tools/lint_arch.py`,
`tools/gen_contract.py`, `tools/security_audit.py` (сверх уже существующей строки),
`tools/snapshot_diff.py`, `tools/selfcheck.py`.

Сдавай так: «C.16 готов к независимому аудиту, не принято» + список sha256
изменённых файлов + явный перечень осознанных расхождений с эталоном.

## §9 Уточнения аудитора (сессия 70, 2026-10-31)

### F8 — ретро-разрешение на правку `tools/security_audit.py`

Факт: в C.15 портер добавил в `tools/security_audit.py` строку
`if not path.is_file(): continue` сразу после фильтра `SKIP_DIRS` (10831 → 10885 B,
sha256 `77956BE3BE9F…`), в листе и `WORKLOG` это не описано, в разрешении аудитора
этого не было. Аудитор проверил эмпирически: со старой версией гейт падает
`PermissionError: [Errno 13] Permission denied: …existing_module_dir\editor\part_one.gd`
(каталог, нужный кейсу `140-existing_module_dir`), с новой — `{"status": "ok",
"detail": "нарушений нет"}`.

**Решение: оставить строку и оформить её.** Разрешается ровно это:

1. `tools/security_audit.py` — **никаких новых правок**; текущая строка остаётся
   как есть, её bytes/sha256 (`10885` / `77956BE3BE9F…`) фиксируются в листе.
2. Новый ADR `docs/adr/0012-security-audit-directories.md`: контекст (гейт обходит
   дерево и читает каждый `*.gd`; в фикстурах точного паритета встречается **каталог**
   с именем `*.gd`), решение (`files()` отдаёт только обычные файлы; каталоги
   пропускаются до чтения), последствия (гейт не падает, ослабления нет: каталог не
   проверяемый артефакт), границы (не расширять на симлинки и спец-файлы, `SKIP_DIRS`
   не менять, набор проверок не сокращать).
3. Новый тест `tests/py/tools/test_security_audit_dirs.py` (§2.4) — включая строковый
   пин самой строки, чтобы будущее удаление ловилось тестом, а не падением гейта.
4. Запись в листе (раздел C.16, подраздел «F8: ретро-разрешение») и в `WORKLOG`:
   кто и когда добавил строку, кто и когда разрешил, чем доказано.

Запрещено: откатывать строку, менять `SKIP_DIRS`, добавлять `is_dir`/`stat`/`glob`,
переписывать набор проверок гейта, править `tools/gen_contract.py`/`lint_arch.py`/
`snapshot_diff.py`/`selfcheck.py`.

### F9 — `plugin.gd.uid` после live (без действий, только память)

Живой прогон удаляет **корневой** `plugin.gd.uid` (так делает редактор). Аудитор
восстанавливал его побайтово из бэкапа. В C.16: после live пересчитай `.gd.uid`,
удали ровно сгенерированные, а корневой `plugin.gd.uid` верни побайтово и запиши
в доказательства число `83`.

### Что менять в этом срезе нельзя, даже если «так чище»

`expected_message`'ы уже сняты аудитором и являются эталоном; тексты F6 берём из
`core.target_lines`/`render.normalize_groups` **дословно**, включая «ёлочки» и
`%r`-кавычки; `newline` пинится как факт; `reference_public`/`reference_result`
остаются сырыми; `plan_capture` не переписывается — добавляется только `c16_recut`.

