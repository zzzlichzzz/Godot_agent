# editing.symbol_rename — компилятор переименования символа (модуль-вклад)

**Статус:** этап `6` (см. `docs/PROGRESS.md`) — модуль-вклад собран,
`selfcheck` ok; своего инструмента и корпуса нет по построению
**Обновлено:** `2026-10-27`

## Цель

Превратить отчёт анализа (`code_intel.usages` → `analyze_rename`) в шаги плана
записи: какие файлы и какие смещения правятся, какие ссылки не доказаны и почему
переименование запрещено. Своего инструмента у механики нет: пользователь видит
`write_preview`/`write_apply`, а `symbol_rename` — компилятор операции внутри них
(ADR-0004, вклад `OperationCompiler`).

## Старый код

| Файл | Что делает | Как делим |
|---|---|---|
| `python/godot_tools/rename_symbol.py` | находит ссылки, проверяет конфликты, строит правки, пишет файлы сам | поиск ссылок уже перенесён в `code_intel.usages`; здесь — только компиляция плана (`domain/compiler.py`), запись — воронка `editing.*` |
| `python/godot_tools/_rename_plan.py` | оффсеты строк, `\r\n`, проверка срезов | перенесено в `domain/compiler.py` (`_offset`, `_line`, нормализация переводов строк) |
| `python/godot_tools/rename_collisions.py` | конфликт имени в скрипте | перенесено в `domain/collisions.py` |

## Старые тесты

| Файл | Семейство | Судьба | Что взяли |
|---|---|---|---|
| `test_rename_*` (~30 файлов) | unit | переписано | 13 кейсов корпуса `code_intel/analyze_rename` (поиск) + 15 корпуса `write_preview` (план) + тесты домена `symbol_rename` |
| `test_rename_plan.py` | unit | переписано | оффсеты/переводы строк/срезы → `tests/test_core.py` модуля |

## Корпус

Корпуса у механики нет и не будет: `symbol_rename` не публикует инструмент, его
поведение видно через корпус владельца — `fixtures/corpus/editing/write_preview`
(16 кейсов) и `fixtures/corpus/code_intel/analyze_rename` (13 кейсов). Это
зафиксировано в `tools/selfcheck.py`: вклад без корпуса — `ok`, если манифест и
тесты на месте.

## Спецификация

Манифест (`module.py`):

| Поле | Значение |
|---|---|
| `id` | `editing.symbol_rename` |
| `provides_tools` | `()` — своего инструмента нет |
| `contributes_to` | `("editing.write_preview", "code_intel.usages")` |
| `internal_services` | `("symbol_rename_compiler",)` |
| `capabilities` | `("editing.symbol_rename",)` — артефакта `contract/capabilities/*.json` не будет: нет `provides_tools` |

Вклад (`__init__.py`): `COMPILER = OperationCompiler(op="symbol_rename",
`compile=compile_plan)`; `tools.py` публикует `TOOLS = ()` и
`CONTRIBUTIONS = (COMPILER,)`.

Инварианты:

1. Компилятор только читает тексты и возвращает план; записи нет (R-12: пишет
   воронка `editing.write_apply`).
2. Правила GDScript (идентификатор, ключевое слово, конфликт имени) живут в одном
   месте — `domain/compiler.py` и `domain/collisions.py`; владелец инструмента их
   не повторяет (R-04).
3. Отказы типизированы: `invalid_input` (плохой запрос) и `conflict` с
   `details.reason` (`name_conflict`, `all_usages_excluded`,
   `unverified_references`, `dynamic_references`).
4. `probable`-ссылки правятся только с `allow_unverified`, `dynamic` — никогда
   (только запрет в `strict`).
5. Свой `ToolSpec` и своя capability не заводятся: имена инструментов публикует
   владелец.

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-10-27 | механика становится модулем-вкладом с манифестом, а не «библиотекой в области» | R-05: общий код знает про механику только из манифеста; `selfcheck` получает что проверять |
| 2026-10-27 | вклад отдаётся через `tools.CONTRIBUTIONS`, реестр раскладывает его по `contributes_to` | загрузчик уже читает `tools.py`; новый канал не нужен, а `domain/` остаётся чистым |
| 2026-10-27 | `write_preview` продолжает импортировать фасад `editing.symbol_rename` | принятое поведение не меняем (99/0 → 102/0); вклад — дополнительный путь, а не замена |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-27 | 1. лист создан | цель, старый код, инварианты |
| | 2. корпус | не нужен: вклад без своего инструмента |
| | 3. спецификация + тесты | 18 тестов домена, 6 контракта манифеста |
| | 4. код | `shared/operation_compiler.py`, `module.py`,
`tools.CONTRIBUTIONS`, `app.build_plan` |
| | 5. двойной прогон | 102/0, `write_preview` 45/16, `usages` 66/31 |
| | 6. живая проверка | `probe write_preview` на фикстуре `rename`:
план строится тем же компилятором |

## Проверки

Вердикт `python tools/selfcheck.py editing.symbol_rename`:

```
selfcheck editing.symbol_rename
  module         ok              editing.symbol_rename (вклад в editing.write_preview, code_intel.usages)
  layers         ok              файлов 453, нарушений нет
  limits         ok              файлов 453, предупреждений 0
  contract       ok              артефактов 8, расхождений нет (мост: 0 обработчиков из 3, ожидаются)
  security       ok              нарушений нет
  unit           ok              15 passed
  corpus         ok              корпуса нет: вклад в editing.write_preview, code_intel.usages (схемы и фейк вместо корпуса)
вердикт: ok
```

## Следующее действие

Часть A: `editing.write_preview` забирает компилятор через
`ctx.registry.contributions("editing.write_preview")`; сейчас владелец
импортирует фасад — принятое поведение, менять только вместе с корпусом.

## Блокеры

| Что мешает | Кто решает |
|---|---|
| конфликты имён на уровне проекта (только внутри файла) | долг из `docs/PROGRESS.md`, отдельный срез `code_intel.usages` |
