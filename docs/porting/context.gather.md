# context.gather — пакет контекста проекта и окружения

**Статус:** этап `6` (см. `docs/PROGRESS.md`) — инструмент собран,
корпус 3/3, живая проверка `probe`; остались вклады секций (часть A)
**Обновлено:** `2026-10-27`

## Цель

Один read-only вызов `context` отдаёт модели ограниченный пакет контекста: что за
проект (корень, `project.godot`, движок), какие инструменты у агента есть сейчас
(имена и эффекты) и — через вклады других модулей — состояние редактора и рантайма.
Вызывается, когда перед ответом не хватает «где мы находимся», а гонять пять разных
инструментов дорого.

## Старый код

| Файл | Что делает | Как делим |
|---|---|---|
| `python/godot_tools/gather_context.py` (370 строк) | собирает пакет: editor snapshot, активная сцена, зависимости, диагностика, `godot_api`, настройки проекта, «PROJECT REFERENCE» из `librarian`; бюджет `max_chars` 2000…20000, `_fit_block` режет секции, отдаёт plain-text | берём **модель секций** и отказ по бюджету, а не текст: секции адресуются именами, результат — JSON, наполнение раздаётся вкладам (ADR-0004) |
| `python/server/editor_context.py` | снимок редактора | не здесь: вклад `context.editor_context` (часть A моста) |
| `python/godot_tools/librarian.py` | карта кода, фрагменты, вызовы | не здесь: `context.ask` |

Старый код держал все секции в одном файле и знал про девять механик сразу
(`gd_api_cache`, `gd_lint`, `tscn_lint`, `log_reader`). Это ровно тот случай, когда
«одна фича» на самом деле область: переносим владельца и интерфейс вклада, а
наполнение приходит модулями.

## Старые тесты

| Файл | Семейство | Судьба | Что взяли |
|---|---|---|---|
| `test_gather_context.py` (6) | unit | corpus | «секции собираются», «отказ при плохом запросе» → кейсы корпуса и тесты домена |
| `test_editor_context.py` (5) | unit | corpus | состояние редактора как отдельная секция → вклад `editor` (часть A); в этом срезе — `unavailable: no_module` |
| `test_librarian.py` (107) | unit | corpus (частично) | кейсы самого поиска сняты ранее в `project_text/search`; ранжирование фрагментов — будущий `context.ask` |

## Корпус

| Что снято | Откуда | Файл |
|---|---|---|
| все секции: `project` + `tools` доступны, `editor` — нет | `fixtures/projects/minimal`, headless-профиль | `fixtures/corpus/context/gather/001-all-sections.json` |
| только `project` | там же | `fixtures/corpus/context/gather/002-project-only.json` |
| неизвестная секция → отказ всего вызова | там же | `fixtures/corpus/context/gather/003-unknown-section.json` |

Чего в корпусе нет и почему:

- живой редактор (`editor` доступен, снимок) — снимается на части A: в headless
  вклада нет вовсе, поэтому кейс фиксирует `no_module`;
- бюджет вывода — проверяется тестами домена: размер текста зависит от машины и в
  корпусе был бы хрупким;
- `runtime_snapshot`, `architecture` — механики ещё не перенесены (этап 0).


## Спецификация

`ToolSpec` (`tools.py`):

| Поле | Значение |
|---|---|
| `name` | `context` |
| `args` | `sections: string[1…8]` (уникальные, по умолчанию все известные), `path: string` (необязательная цель), `additionalProperties: false` |
| `result` | `{sections, available[], unavailable[{name, reason}], cost}` — все поля обязательны |
| `effects` | `read` |
| `idempotent` | `true` |
| `requires_preview` | `false` |
| `errors` | `invalid_input`, `denied`, `not_found` |

Инварианты:

1. Неизвестная секция — отказ **всего** вызова (`invalid_input`,
   `details.reason = "unknown_section"`), а не «пропустим и соберём остальное»:
   иначе клиент не отличит опечатку в имени секции от пустой секции.
2. Порядок `sections` в ответе — порядок запроса; `available` и `unavailable`
   отсортированы по имени, чтобы ответ не зависел от порядка загрузки модулей.
3. Отказ вклада (нет модуля, нет моста, исключение) — не ошибка вызова, а
   `unavailable[{name, reason}]`; `reason` — короткая машинная строка
   (`no_module`, `no_bridge`, `failed`).
4. Встроенные секции `project` и `tools` собираются владельцем и не зависят от
   вкладов; `tools.names` — по алфавиту, `effects` — карта «имя → read/write».
5. `path` валидируется политикой путей (`path_escape` → `denied`), но в этом срезе
   секции его не читают: цель появится у вкладов (`editor`), которые придут частью A.
6. Время и `uptime` в ответ не входят: `context` идемпотентен, а «сейчас» —
   свойство секции `runtime`, а не владельца.

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-10-27 | владелец `context` — `context.gather`, секции приходят вкладом `ContextSection` через `ctx.registry.contributions("context")` | ADR-0004: агрегатор вызывает вклады реестром, а не импортом чужого `domain/` (R-11) |
| 2026-10-27 | известные имена секций = встроенные (`project`, `tools`) + зарезервированные ADR-0004 (`editor`, `runtime`, `architecture`) + имена зарегистрированных вкладов | иначе `sections: ["editor"]` в headless был бы «неизвестной секцией», и кейс 001 врал бы про причину |
| 2026-10-27 | `cost` в ответе и в `ToolSpec` — `"light"` | так записано в ТЗ среза; у ранее перенесённых механик словарь `cheap`/`heavy` — расхождение записано в `docs/NOTES.md`, унификация отдельной задачей (R-08) |
| 2026-10-27 | корпус сравнивает `sections.project.root` как `<PROJECT>` (проекция в `tools/snapshot_diff.py`) | абсолютный путь машины в эталоне сделал бы корпус непереносимым; сам корень пинится тестом контракта |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-27 | 1. лист создан | цель, старый код, корпус, спецификация |
| | 2. корпус | `fixtures/corpus/context/gather` — 3 кейса: 001 all-sections,
002 project-only, 003 unknown-section |
| | 3. спецификация + тесты | `tools.py` (`context`), 13 тестов домена,
13 контракта, 7 интеграции вкладов |
| | 4. код | `domain/core.py`, `app.py` (77 строк), `ports.py`; вклады —
через `ctx.registry.contributions("context")` |
| | 5. двойной прогон | `snapshot_diff` 102 кейса, 0 расхождений;
`selfcheck` ok, exit 0 |
| | 6. живая проверка | `probe.py context --args-file ... --project
fixtures/projects/minimal` → `{"ok": true, ...}`, exit 0 |

## Проверки

Вердикт `python tools/selfcheck.py context.gather`:

```
selfcheck context.gather
  module         ok              context.gather (context)
  layers         ok              файлов 453, нарушений нет
  limits         ok              файлов 453, предупреждений 0
  contract       ok              артефактов 8, расхождений нет (мост: 0 обработчиков из 3, ожидаются)
  security       ok              нарушений нет
  unit           ok              33 passed
  corpus         ok              кейсов 3, расхождений нет
вердикт: ok
```

## Следующее действие

Часть A моста: вклад `context.editor_context` (`ContextSection("editor", ...)`,
`tools.CONTRIBUTIONS`) — тогда `editor` перестанет быть `no_module`, а после
приёмки — этап 7 и `ported` в `docs/parity.md`.

## Блокеры

| Что мешает | Кто решает |
|---|---|
| секция `editor` без моста даёт только `no_module` | часть A (`docs/porting/_start-prompt.editor_bridge_a.md`) |
