# Задача: пятый срез — воронка записи, часть 1: `write_preview` + планировщик `symbol_rename`

Ты — портер. Это **первая пишущая механика** проекта и самый ответственный срез:
до сих пор всё было read-only, ошибка стоила неверного ответа; теперь ошибка
стоит испорченных файлов пользователя. Поэтому срез сознательно разрезан на три
части, и ты делаешь **только первую**.

Принятые срезы: `project_text.search` (16 кейсов), `code_intel.functions` (17),
`code_intel.usages` (18 + 13 для `analyze_rename`). Их `selfcheck` обязан
остаться `ok`, корпус — без изменений.

## 0. Что нужно знать перед началом

- `docs/adr/0005-tranzakcionnyj-protokol.md` — **твой главный документ**. Состояния
  `DRAFT → PREPARED → APPLYING → COMMITTED → (ROLLING_BACK → ROLLED_BACK)`, WAL
  `user://godot_agent/journal/<plan_id>.jsonl`, квитанции, recovery, лок,
  идемпотентность. Сейчас ты реализуешь **только `DRAFT → PREPARED`**.
- `python/kernel/write_plan.py` уже содержит типы `WritePlan` / `Step` / `Receipt`
  (универсальный конверт, без сценовых операций) — используй их, не изобретай новые.
- `docs/architecture.md §5` — путь записи; `§7` — границы «предпросмотр ↔ запись»
  (ты реализуешь предпросмотр: он **не решает**, применить ли недоказанную ссылку,
  он готовит план и отчёт).
- Правило R-12: писать файлы проекта можно **только** в `apply`. В этом срезе
  `apply` нет вообще — значит, в проекте не должно измениться ни одного байта.

## 1. Что делает эталон (проверено по коду)

`godot_tools/symbol_refactor_part3.py`:

| Что | Строки | Берём в этом срезе |
|---|---|---|
| `prepare_rename(project_root, action, ...)` | 61–615 | **да**: строит план правок, проверяет безопасность, готовит диффы. В `action` приходят `kind`, `declaration`, `old_name`, `new_name`, `mode`, `allow_unverified`, `exclude` |
| gating `mode`/`allow_unverified` | 477–498 | **да**: `strict` + недоказанные ссылки без флага → отказ; `strict` + `dynamic` → отказ с текстом «повтори с `mode=probable`» |
| «все ссылки сняты» | 473–476 | **да**: если `exclude` снял все ссылки, объявление переименовывать нельзя → отказ |
| `apply_prepared_rename` | 628+ | **нет** — это следующий срез |
| правки `.tscn` (`_collect_scene_property_edits` part1:601, `_collect_scene_connection_edits` part1:766) | part1 | **нет**: для сцен нужен `formats/tscn`, его ещё не переносили |
| `history_manager.record_change/commit/rollback` | 900 строк | **нет**: наш журнал — WAL по ADR-0005, а не старый `history_manager` |

`prepare_rename` возвращает большой объект (правки по файлам, `skipped_usages`,
`edits`, `ambiguities`, `dynamic_references`, диффы). Ты **не переносишь его
структуру дословно** — ты приводишь её к `WritePlan` из ADR-0005. Нормализацию
(какие поля эталона становятся `step`, какие `expected`, что отбрасывается)
опиши в листе механики: это и есть главное решение среза.

## 2. Границы: три части воронки, ты делаешь первую

| Часть | Модули | Инструменты | Состояния ADR-0005 | Когда |
|---|---|---|---|---|
| **1 (сейчас)** | `editing.write_preview` (владелец) + `editing.symbol_rename` (компилятор операций) | `write_preview` | `DRAFT → PREPARED` | этот срез |
| 2 (следующий) | `editing.write_apply` + `editing.rollback` | `write_apply`, `write_rollback` | `APPLYING`, `COMMITTED`, `ROLLING_BACK`, recovery, лок, идемпотентность | после тебя |
| 3 (позже) | те же + GDScript-мост и `formats/tscn` | — | — | когда появятся примитивы редактора |

Цель части 1: инструмент, который **показывает** пользователю план переименования
с диффами, счётчиками и рисками, и **сохраняет** этот план в WAL так, чтобы часть 2
могла его применить, не пересчитывая.

Что это значит практически:

- `write_preview` **не пишет в проект ни байта**;
- `write_preview` пишет **один файл вне проекта** — WAL-запись плана в
  `state_dir/journal/<plan_id>.jsonl` (`state_dir` даёт профиль/конфиг, в тестах —
  временный каталог). Пока этой записи нет, плана не существует;
- `write_preview` возвращает `plan_id`, `digest`, `steps` (кратко), диффы,
  `affected_paths`, `skipped`, счётчики и срок жизни подтверждения (`confirm_ttl`);
- `apply` в этом срезе **отсутствует**: инструмент `write_apply` остаётся
  заглушкой, `selfcheck editing.write_apply` обязан вернуть `blocked` (это
  доказывает, что граница соблюдена, а не забыта).

## 3. План, digest и WAL — то, что делает срез срезом

`WritePlan` (типы уже есть в `python/kernel/write_plan.py`):

| Поле | Смысл в этой механике |
|---|---|
| `plan_id` | случайный идентификатор (hex), имя WAL-файла; новый на каждый `preview` |
| `digest` | sha256 от канонического JSON: `kind`, `declaration`, `old_name`, `new_name`, `mode`, `allow_unverified`, все `steps` (включая смещения и замены), все `expected` хеши. **Тот же вход → тот же digest**, это проверяется кейсом |
| `steps[]` | `Step(op="script_edit", target="res://file.gd", payload={"edits":[{start,end,replacement}]}, expected_hash=<sha256 текста файла>)`. Смещения — **символы в тексте после нормализации переводов строк**, и это надо зафиксировать в листе: иначе apply вставит правку не туда |
| `expected{}` | `path → sha256` каждого затрагиваемого файла на момент preview (это вход stale-check для части 2) |
| `confirm_ttl` | 900 секунд; подтверждение в части 2 будет привязано к `digest` |

WAL: одна JSONL-запись в `state_dir/journal/<plan_id>.jsonl` со `state="PREPARED"`,
планом и временем. Каталог — вне проекта (`user://godot_agent/…` в боевом профиле,
временный каталог в тестах). **Порт `store` объявляется в `ports.py` модуля**:
`journal.write_prepared(plan)`, `journal.read(plan_id)`; реализация — в `substrate/store`.

## 4. ToolSpec: `write_preview`

| Поле | Значение |
|---|---|
| args | `kind` (enum 7), `declaration` (locator), `old_name`, `new_name` (обязателен), `mode` (`strict`\|`probable`, default `strict`), `allow_unverified` (bool, default `false`), `exclude` (массив locator'ов `res://path.gd:LINE`) |
| result | `{plan_id, digest, state:"PREPARED", kind, old_name, new_name, declaration, mode, allow_unverified, steps_count, affected_paths[], skipped_usages[], diffs:[{path, patch}], stats:{files, edits, proven, probable, dynamic, skipped}, confirm_ttl}` |
| effects | **`write`** (это первая механика с таким `effects`; помни про R-20) |
| errors | `invalid_input`, `not_found`, `denied`, `conflict` |
| availability / cost | `*` / `heavy` |

`conflict` здесь — это **отказ по существу** (нельзя безопасно переименовать), а не
сбой: `details.reason` обязателен и берётся из эталона (`unverified_references`,
`dynamic_references`, `all_usages_excluded`, `name_conflict`, …). Соответствие
«причина эталона → наш `reason`» — таблицей в листе.

## 5. Обязательные кейсы корпуса (не меньше 16)

Корпус: `fixtures/corpus/editing/write_preview/`, фикстура —
`fixtures/projects/rename/` (создать: 3–4 `.gd` с объявлением, ссылками в другом
файле, наследником, динамическим `call("...")`, и местом для `exclude`).

1. переименование в одном файле — план из одного шага, дифф содержит замену;
2. переименование в двух файлах — два шага, `affected_paths` отсортирован;
3. `exclude` одной ссылки → она в `skipped_usages`, в `steps` её нет;
4. `exclude` всех ссылок → `conflict` `all_usages_excluded`, WAL-файла нет;
5. `strict` + `probable` без флага → `conflict` `unverified_references`;
6. `allow_unverified=true` → план построен, вероятные ссылки вошли в `steps`;
7. `strict` + `dynamic` (`call("take_damage")`) → `conflict` `dynamic_references`;
8. `mode="probable"` + `dynamic` → план построен (в `stats.dynamic` > 0);
9. `new_name` уже занято в том же скрипте → `conflict` `name_conflict`;
10. `old_name` — ключевое слово GDScript → `invalid_input`;
11. `new_name` — не идентификатор (`"2x y"`) → `invalid_input`;
12. `declaration` не соответствует объявлению → `not_found`;
13. путь вне проекта / аддон → `denied`;
14. **байты проекта не изменились**: sha256 всех файлов фикстуры до/после равны;
15. **идемпотентность digest**: два `preview` подряд с теми же аргументами дают
    одинаковый `digest` и разные `plan_id`;
16. WAL: файл существует, `state="PREPARED"`, `expected` содержит хеши ровно тех
    файлов, которые затрагивает план.

Снимать корпус — с эталона (`symbol_refactor.prepare_rename` через новую ветку
`tools/_reference_runner.py`), **но нормализованно**: тебе нужны не все поля
эталона, а `файлы → смещения/замены`, `skipped_usages` и текст отказа. Как именно
нормализовано — записать в листе, иначе корпус будет сравнивать несравнимое.

## 6. Решения, которые обязан принять и записать

1. **Где живёт проверка коллизий.** В эталоне это `part2._collision`,
   `_is_real_conflict`, `_project_global_names`, `_engine_class_name` — часть
   поиска, часть записи. Реши: переиспользовать существующее в
   `code_intel.usages` (публичное API через `__init__.py`) или положить в
   `editing/symbol_rename/domain/`. **Один экземпляр, не два** (R-04), решение — в лист.
2. **Нормализация плана.** Что из объекта `prepare_rename` становится `Step`,
   что `expected`, что отбрасывается (например диффы строк эталона — ты строишь
   свои из `kernel/diff`). Таблица «поле эталона → поле плана» в листе.
3. **`exclude` — вход preview, а не apply.** Снятые места попадают в
   `skipped_usages` и **не** попадают в план; apply потом не переспрашивает.
4. **Каталог WAL.** `state_dir` приходит из профиля/конфига, а не вычисляется
   модулем; в тестах — временный. Модуль не знает слова `user://`.
5. **`.tscn` не трогаем.** Переименование символа в этом срезе меняет только
   `.gd`. Если в проекте есть сцены, ссылающиеся на переименованное — это
   **риск в отчёте** (`risks`), а не правка. Полная поддержка сцен — часть 3.

## 7. Тесты, которые обязательны именно здесь

- `tests/test_core.py` — домен: построение шагов, сортировка, `skipped`, отказы
  по `mode`/`allow_unverified`, вычисление `digest` на строках (без диска);
- `tests/py/contract/test_write_preview_contract.py` — схема `ToolSpec`, набор
  `kind`, обязательность `new_name`, формат `diff`, отсутствие абсолютных путей
  и стектрейсов в ответе, `details.reason` во всех `conflict`;
- `tests/py/integration/` — прогон на `MemoryFS` + поддельный журнал: план
  строится, WAL-запись появляется, файлы проекта не меняются;
- **`tests/py/security/`** — обязательно (R-20, `effects="write"`):
  `test_path_escape.py` (declaration `res://../outside.gd`, абсолютный путь,
  симлинк → `denied`, ни один байт вне проекта не тронут),
  `test_write_funnel.py` (в модуле нет `open(..., "w")`, нет `os.remove`,
  запись только через `atomic_write` в части 2 — здесь проверяется, что в этом
  срезе записи в проект нет вообще),
  `test_secret_redaction.py` (если в правке встречается строка вида ключа —
  в отчёт она не попадает).
- Домен не должен знать про Godot, файловую систему и `user://`: проверь тестом,
  как в срезе `usages` (`domain_io=0`).

## 8. Стоп-условия

Не реализовывать `apply`, `rollback`, recovery, лок, квитанции — это часть 2.
Не править `.tscn`, `project.godot`, ресурсы. Не переносить `history_manager`.
Не писать в проект ни при `preview`, ни в тестах (фикстуры копируются во
временный каталог, а не правятся на месте). Не менять принятые срезы
(`search`, `functions`, `usages`, `analyze_rename`) и их корпуса. Не ставить
`ported` без зелёного `selfcheck` и живой проверки. Старый плагин — только чтение.

## 9. Что проверит аудитор

| Проверка | Доказательство |
|---|---|
| `selfcheck editing.write_preview` | `ok`, exit 0; `unit`/`contract`/`corpus` (≥16) на месте |
| граница воронки | `selfcheck editing.write_apply` → **`blocked`** (заглушка), `write_preview` не содержит кода применения |
| байты проекта | хеши фикстуры до/после `preview` совпадают (кейс 14) + мой независимый прогон на копии |
| WAL | файл `<plan_id>.jsonl` со `state="PREPARED"`, `expected` и `steps`; при отказе WAL **не** создаётся |
| digest | два прогона — одинаковый digest, разные `plan_id`; изменение одного байта фикстуры → другой digest |
| `mode`/`allow_unverified` теперь поведение | кейсы 5–8 дают разные исходы, и это совпадает с эталоном (`part3:477–498`) |
| целость прошлого | `snapshot_diff` — прежние 64 кейса без изменений; `selfcheck` четырёх срезов `ok` |
| безопасность | 3 атакующих теста зелёные; `security_audit` ok; в домене нет `open(`/`os`/`pathlib` |
| числа в отчёте | совпадают с `--collect-only`; `app.py` ≤ 80, `tools.py` ≤ 150 (не забыть про правило деления схем по инструментам — R-06) |

## 10. Финальный прогон и записи

```
python tools/selfcheck.py editing.write_preview      → exit 0
python tools/selfcheck.py editing.write_apply        → blocked, exit 2   (граница)
python tools/selfcheck.py code_intel.usages          → exit 0
python tools/selfcheck.py code_intel.functions       → exit 0
python tools/selfcheck.py project_text.search        → exit 0
python tools/snapshot_diff.py                        → прошлые 64 без изменений + новый корпус
python -m pytest python/modules tests/py -q          (addopts из pyproject)
python tools/security_audit.py --json; lint_arch; check_limits; gen_contract --check
probe write_preview --args-file <...>; python -m python.channels.mcp.stdio fixtures/projects/rename
```

Записи: лист `docs/porting/write_preview.md` (создать **до** кода: границы трёх
частей, таблица «поле эталона → поле плана», соответствие `reason`, решения §6),
`parity.md` (строки `write_preview` → `ported`; `write_apply`/`rollback` остаются
`skeleton` — и это **правильно**, так и записать), `PROGRESS.md` (этап 7 у
`write_preview`, у `symbol_rename` — этап «компилятор готов, ждёт `write_apply`»,
следующее действие — часть 2: `write_apply` + `rollback` по ADR-0005, с failure-
тестами), `WORKLOG.md` (сессия: что нормализовали, как снимали корпус, вывод команд),
`tests-map.md` (какие старые `test_rename_*` теперь закрыты частично, строки не удалять).


