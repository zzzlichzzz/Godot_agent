# Задача: шестой срез — воронка записи, часть 2: `write_apply` + `rollback`

Ты продолжаешь перенос агента в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`.
Приняты и зелены: `project_text.search` (16 кейсов), `code_intel.functions` (17),
`code_intel.usages` (18 + 13), `editing.write_preview` (16). Их корпуса и тесты
обязаны остаться `ok` — это регресс-гейт, а не пожелание.

**Это первая механика, которая реально меняет файлы пользователя.** Ошибка здесь
стоит не «красного теста», а испорченного проекта. Поэтому главный документ
среза — `docs/adr/0005-tranzakcionnyj-protokol.md` целиком, включая раздел
«Что именно хешируется (`expected`)», добавленный аудитом части 1.

## 0. Что уже готово и что нельзя переделывать

- `python/kernel/write_plan.py` — `Step`, `Receipt`, `WritePlan`, `canonical_json`,
  `digest_of`, `STATES`, `CONFIRM_TTL = 900`.
- `editing.write_preview` (принят): пишет `PREPARED` в WAL, возвращает `plan_id`,
  `digest`, `steps`, `diffs`, `expected`, `confirm_ttl`; в проект не пишет ничего.
- Контракт части 1, который ты обязан соблюсти буквально:
  - `expected[path]` — sha256 **сырых байтов** файла (BOM и `\r\n` входят);
  - `steps[].expected_hash` — sha256 **нормализованного** текста (`\r\n`,`\r` → `\n`, BOM снят) — это текст, в котором посчитаны смещения;
  - `payload.newline` — `"crlf"`/`"lf"` по байтам; после правки стиль файла **восстанавливается**;
  - `fs`-порт умеет `read_raw` (байты) и `read_text` (нормализованный текст).
- `substrate/store/journal.py` — `FileJournal`: `write_prepared`, `read`, `path`, `fsync` файла.
- `runtime/context.py` — `ModuleContext` (закрытый список полей: `profile`, `settings`, `ports`, `path_policy`, `logger`, `ids`, `clock`, `call_tool`, `port()`).
- Заготовки `editing.write_apply` и `editing.rollback` — пустые папки; `selfcheck`
  обязан отвечать на них `blocked` и exit 2 (проверь до начала работы: если
  зелёный — инструмент сломан, чинить первым делом).

## 1. Что берём у эталона (только чтение, `python -B`)

| Файл | Строки | Что берём |
|---|---|---|
| `godot_tools/symbol_refactor_part3.py` | 61–615 (`prepare_rename`) | **не берём**: это уже сделано в части 1 |
| `godot_tools/symbol_refactor_part3.py` | 616+, `apply_prepared_rename` | порядок применения, проверка «не изменилось ли», откат при сбое, квитанции |
| `godot_tools/history_manager.py` | 210, 271, 326, 345, 368, 552, 595, 708 | **смысл** журнала: запись до эффекта, rollback по записи, цепочки. Код не переносим (R-08): у нас свой WAL по ADR-0005 |
| `godot_tools/symbol_refactor_part3.py` | 470–505 | гейтинг `mode`/`allow_unverified` — он уже отработал в части 1, здесь только `conflict`, если план нарушает инварианты |

Старые тесты по теме (`docs/tests-map.md`): `test_rename_transitive_hierarchy.py`,
`test_rename_refusal_granularity.py`, `test_variable_refactor.py`,
`test_asset_refactor.py`, `test_rename_policy_default.py`, `test_usage_checklist_honesty.py`,
`repro_plan_gc.py`, `repro_return_codes.py`. Триаж уже сделан: судьба `corpus` или
`replaced` проставлена; строки не удалять, только дополнять примечания.

## 2. Состояния и порядок действий (ADR-0005, буквально)

`PREPARED → APPLYING → COMMITTED`, ветки `ROLLING_BACK → ROLLED_BACK`,
`EXPIRED`. Требования, каждое из которых обязано иметь тест:

1. **WAL до первого эффекта.** `PREPARED` уже записан частью 1; `APPLYING` —
   отдельной строкой **до** первой записи в файл.
2. **Квитанция после эффекта и до следующего шага**: `{step_id, op, applied_hash, undo_token}`.
   Потеря ответа ≠ успех.
3. **Журнал переживает падение**: `flush` + `fsync` файла; при создании нового
   файла — `fsync` каталога (на POSIX; на Windows — `os.replace` + повторное чтение).
4. **Recovery при старте**: `APPLYING` с квитанциями → автооткат и `ROLLED_BACK`;
   `APPLYING` без квитанций → как `PREPARED` (эффекта не было); `PREPARED` старше
   `confirm_ttl` → `EXPIRED`.
5. **Lock на проект** на весь неделимый интервал «перечитать `expected` → сверить →
   применить → записать квитанцию»: два одновременных `apply` не должны
   перемешиваться (второй получает `conflict`, а не «половину»).
6. **Идемпотентность**: повторный `apply` с тем же `digest` при `COMMITTED`
   → та же квитанция, эффекта нет; с другим `digest` → `stale_plan`.
7. **Откат сверяет post-state**: перед восстановлением сравнить текущий хеш с
   `applied_hash`; расхождение (файл правили после `apply`) → `conflict` с путём
   и хешами, восстановление **не выполняется**.
8. **Стиль файла сохраняется**: правки применяются к нормализованному тексту,
   затем текст возвращается в `payload.newline`; CRLF-файл остаётся CRLF
   побайтово, кроме изменённых строк.

## 3. Контракт `write_apply`

| Поле | Значение |
|---|---|
| args | `plan_id` (строка, обязателен), `digest` (строка, обязателен) — подтверждение привязано к плану и его digest |
| result | `entry_id`, `state: "COMMITTED"`, `plan_id`, `digest`, `applied: [{path, applied_hash}]`, `receipts: [{step_id, applied_hash, undo_token}]`, `files_count`, `started_at`, `finished_at` |
| effects | `write` (единственная механика, которой разрешено менять проект) |
| idempotent | `True` — по контракту ADR-0005 (повтор с тем же digest не даёт эффекта) |
| errors | `invalid_input`, `not_found` (плана нет/истёк), `stale_plan`, `conflict`, `denied`, `internal` |
| cost | `heavy` |

`stale_plan` — файл изменился с момента `preview` (или digest не тот).
`conflict` — отказ по существу: `details.reason` из `already_applied`,
`already_rolled_back`, `lock_busy`, `plan_state:<STATE>`.

## 4. Контракт `rollback`

| Поле | Значение |
|---|---|
| args | `entry_id` (строка, обязателен) — идентификатор применённой записи из `write_apply` |
| result | `entry_id`, `state: "ROLLED_BACK"`, `restored: [{path, hash}]`, `removed: []`, `files_count` |
| effects | `write` |
| idempotent | `True` с оговоркой: повторный откат уже откаченного → `conflict`, `details.state = "already_rolled_back"` (ADR-0005), **не** тихий успех |
| errors | `invalid_input`, `not_found`, `conflict`, `denied`, `internal` |

Восстановление — по квитанциям, а не «переименовать файл обратно»: для каждого шага
хранится либо инверсная правка, либо бэкап байтов в каталоге состояния профиля
(решение §6.3). После отката хеши файлов обязаны совпасть с `expected[path]`
побайтово — это и есть доказательство, что воронка замкнута.

## 5. Обязательные кейсы корпуса (не меньше 14)

Корпус снимается **с эталона** (`tools/snapshot_record.py` → `tools/_reference_runner.py`,
новая ветка `write_apply`: эталонный `apply_prepared_rename` на временной копии
фикстуры), ожидаемое — **итоговые байты файлов** после применения, а не текст
ответа. Инварианты ниже (идемпотентность, recovery, лок) у эталона отсутствуют —
они проверяются тестами, а не корпусом: это наш safety-инвариант, а не паритет.

1. однофайловое переименование: файл изменился, хеш = ожидаемому;
2. двухфайловое: оба изменились, `entry_id` один;
3. CRLF-файл: после `apply` остаётся CRLF, изменены ровно нужные строки (сравнение побайтово);
4. BOM-файл: BOM на месте, смещения не поехали;
5. файл изменили после `preview` → `stale_plan`, файл не тронут;
6. `digest` не тот → `stale_plan`, файл не тронут;
7. `plan_id` не существует → `not_found`;
8. план старше `confirm_ttl` → `not_found`/`EXPIRED`, файл не тронут;
9. повторный `apply` с тем же `digest` → та же квитанция, файлы не меняются;
10. откат возвращает байты, равные исходным (sha256 совпал);
11. откат после внешней правки → `conflict`, файл **не** восстановлен;
12. повторный откат → `conflict`, `details.state = "already_rolled_back"`;
13. два шага, второй падает (инъекция сбоя) → первый откачен, проект как до `apply`;
14. после падения процесса в `APPLYING` recovery при старте приводит план в `ROLLED_BACK`
    и проект в исходное состояние.

## 6. Решения, которые обязан принять и записать

1. **Куда пишет `apply`.** Новый порт в `ports.py` модуля (`ProjectWriter.write(rel, data)`
   + `read_raw`), адаптер — в `substrate/fs` (атомарная запись: temp в том же каталоге,
   `os.replace`, `fsync`). Домен не знает ни про диск, ни про `user://`.
2. **`entry_id`.** Формат `"<plan_id>#<n>"`, где `n` — номер записи в WAL; откат
   адресуется по нему. Не менять задним числом: он попадает в панель и в журнал.
3. **Чем откатывать.** Выбери и обоснуй: инверсные правки (компенсирующие `Step`) или
   бэкап байтов в `state_dir/backup/<plan_id>/<n>.bin`. Критерий — побайтовое
   восстановление и отсутствие «умных» решений в момент отката.
4. **Где живёт recovery.** Отдельная функция в модуле (`editing.rollback`) или в
   `runtime/bootstrap` — но точка входа одна, и её вызов логируется. Реши и запиши.
5. **Лок.** Реализация под Windows и POSIX (файл-лок с `O_CREAT|O_EXCL` в каталоге
   состояния профиля, снятие в `finally`). «Лок на процесс» не подходит: два
   экземпляра агента — реальный сценарий.
6. **Частичный откат.** План на 3 файла, откат падает на втором: что возвращаем
   пользователю и что пишем в WAL. Ответ — состояние `ROLLING_BACK` с квитанциями,
   повторный откат продолжает с третьего, а не с первого.

## 7. Тесты, которые обязательны именно здесь

- `tests/test_core.py` — машина состояний на поддельном журнале: переходы
  (`PREPARED→APPLYING→COMMITTED`, `ROLLING_BACK→ROLLED_BACK`), запрет перехода из
  `COMMITTED` в `APPLYING` без нового `digest`, идемпотентность;
- `tests/py/contract/test_write_apply_contract.py` — схема `ToolSpec`, набор ошибок,
  `details.reason` в каждом `conflict`, отсутствие абсолютных путей и стектрейсов;
- `tests/py/integration/test_write_apply_*.py` — **настоящий временный проект на диске**
  (копия фикстуры в `%TEMP%`): применить, откатить, сравнить байты; CRLF и BOM;
- `tests/py/security/` — обязательно (`effects="write"`): запись только внутрь проекта
  и `state_dir`; `..`/абсолютный путь/симлинк → `denied` без создания файла; в WAL и
  отчётах нет секретов (SEC-06/SEC-13);
- failure-injection — шесть строк таблицы ADR-0005: сбой между шагами, `kill` в
  `APPLYING`, повторный `apply`, файл изменён после `apply`, две сессии, сцена
  (последнее — часть 3, здесь только пометить).

## 8. Стоп-условия

- Не переделывать часть 1: `write_preview` уже принят; менять его контракт — только
  через `docs/deviations.md` и с пересъёмом корпуса.
- Не трогать `.tscn`, `project.godot`, ресурсы, открытые сцены: это часть 3
  (GDScript-мост и `formats/tscn.py`).
- Не переносить `history_manager` как файл: у нас WAL по ADR-0005.
- Не «упрощать» stale-check до сравнения mtime: только хеши байтов.
- Не писать в проект нигде, кроме `write_apply.apply` (R-12). В тестах — только во
  временной копии.
- Не выдавать зелёный `selfcheck` за доказательство: без failure-тестов и отката
  побайтово срез не принят.
- Старый плагин — только чтение (`python -B`, `PYTHONDONTWRITEBYTECODE=1`).

## 9. Что проверит аудитор

| Что | Доказательство |
|---|---|
| `write_apply` и `rollback` работают | `selfcheck editing.write_apply` → ok, exit 0; `selfcheck editing.rollback` → ok, exit 0 |
| часть 1 не сломана | `selfcheck editing.write_preview` → ok, exit 0; `snapshot_diff` → 80 прежних + новый корпус, 0 расхождений |
| откат побайтовый | независимо: применить и откатить на копии проекта, сверить sha256 всех файлов с исходными |
| CRLF и BOM | свой прогон на CRLF/BOM-копии: стиль сохранён, изменены только нужные строки |
| recovery реально работает | мутация: отключить recovery → failure-тест обязан упасть; тест-заглушка не принимается |
| лок держит | два параллельных `apply` → один `conflict`, ни одного смешанного состояния |
| WAL честный | `APPLYING` записан до первого эффекта; квитанции после каждого шага; `entry_id` = `plan_id#n` |
| идемпотентность | повторный `apply` с тем же `digest` → та же квитанция, байты не изменились |
| безопасность | `security_audit` ok; запись вне проекта/`state_dir` невозможна; в WAL нет секретов |
| границы и числа | домен без IO; `app.py` ≤ 80, `tools.py` ≤ 150; числа тестов = `--collect-only`; `__pycache__` = 0 |

## 10. Финальный прогон и записи

```
python tools/selfcheck.py editing.write_apply     # exit 0
python tools/selfcheck.py editing.rollback        # exit 0
python tools/selfcheck.py editing.write_preview   # exit 0 (регресс)
python tools/snapshot_diff.py                     # 0 расхождений
python -m pytest python/modules tests/py -q       # addopts уже в pyproject
python tools/security_audit.py --json             # ok
python tools/lint_arch.py; python tools/check_limits.py; python tools/gen_contract.py --check
python tools/probe.py write_apply --args-file … --project fixtures/projects/rename
```

Записи после зелёного прогона: лист `docs/porting/write_apply.md` (создать до кода:
состояния, решения §6, кейсы, откат, recovery), `parity.md` — `write_apply` и
`rollback` → `ported`, `write_preview` остаётся `ported`, `scene_ops`/`resource_ops`
остаются `skeleton` (часть 3); `PROGRESS.md` — этап 7 обоим, следующее —
`editing.scene_ops`/`resource_ops` (часть 3) и `code_intel.function_card`;
`WORKLOG.md` — сессия с выводом команд, принятыми решениями §6 и инцидентами;
`tests-map.md` — дополнять примечания, строки не удалять; `deviations.md` — если
поведение отличается от эталона (например, откат не восстанавливает то, что правили
после `apply`).


