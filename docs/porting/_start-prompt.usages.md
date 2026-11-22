# Задача: третий вертикальный срез — механика `code_intel.usages`

Ты — портер. Работа: перенести одну возможность — **read-only поиск использований
символа** (старый MCP-инструмент `usages`) в `code_intel.usages`, доказать
эквивалентность корпусом, получить зелёный `selfcheck`. Предыдущие срезы
(`project_text.search`, `code_intel.functions`) приняты аудитом — их листы,
тесты и код являются планкой качества.

`analyze_rename` **в этот срез не входит** (см. §6, решение 1). Это следующий
срез того же модуля.

## 0. Перед началом: `selfcheck` зелёный на пустом модуле (исправить первым делом)

Проверено аудитором: `python tools/selfcheck.py code_intel.usages` **сейчас даёт
`вердикт: ok`, exit 0** — на модуле, где нет ни строки кода (`tools.py` = TODO,
`MODULE` не определён). Причина в `tools/selfcheck.py`: проверка `module` смотрит
только существование папки и `tests/`, а все `CHECKS` — общие для проекта, поэтому
пустая заготовка проходит. Это дыра в гарантии R-18 («пустая заготовка никогда не
бывает зелёной»), и с ней ты сможешь «принять» пустоту.

Исправь `tools/selfcheck.py` **до** кода механики:

1. `module` больше не `ok` по факту существования папки: подними реальную сборку
   (`runtime.bootstrap.build_agent` на `fixtures/projects/minimal`) и проверь, что
   модуль загружен и его `provides_tools` присутствуют в реестре. Не загрузился или
   `disabled` — `fail` с причиной.
2. `unit` должен считать тесты **самого модуля**: `pytest <module>/tests -q
   --import-mode=importlib --collect-only` → 0 собранных = `not_implemented`
   («тестов модуля нет»), затем прогон только этих тестов.
3. `corpus` ищет корпус модуля (`fixtures/corpus/<область>/<фича>/`); нет корпуса —
   `not_implemented` («нет корпуса механики»), а не «общий корпус проекта зелёный».
4. Правило вердикта не меняется: любой `not_implemented` → `blocked`, exit 2.

Приёмка правки (докажи, не декларируй):
- `selfcheck` на **нетронутой** заготовке (например `editing.write_preview`) → `blocked`,
  exit 2;
- `selfcheck code_intel.functions` и `selfcheck project_text.search` → по-прежнему `ok`,
  exit 0 (ты не сломал уже принятые срезы);
- одна строка в `WORKLOG.md` о правке инструмента и в `tools/README.md`, если поведение
  изменилось.

## 1. Прочитать до первой правки

| Что | Зачем |
|---|---|
| AGENTS.md | стоп-условия, 11 шагов |
| RULES.md | 21 правило; твои: R-02, R-05, R-06, R-08, R-11, R-16, R-17, R-18, R-19 |
| docs/architecture.md §2/§3/§4/§7 | слои, ToolSpec, состав модуля; `modules → formats` разрешено |
| docs/PORTING.md | 10 шагов, DoD, §8/§9 |
| docs/PROGRESS.md | твоя строка — `code_intel.usages`, этап 0 |
| docs/porting/code_intel.functions.md | образец листа и «правки аудита» — не повторяй их ошибки |
| docs/parity.md строки 22 и 54 | что обещано: `usages` vs `analyze_rename --apply` |
| docs/mapping.md, раздел про `symbol_refactor*` | как делить part1/part2/part3 |
| docs/tests-map.md строки 60, 61, 87, 95, 127, 131 | старые тесты; часть судеб требует поправки (§9) |
| docs/security/invariants.md | SEC-11 (только чтение), SEC-12 (пути), SEC-13 (пути в выводе) |

## 2. Что такое `usages` по факту эталона (проверено, не по названиям)

Инструмент отвечает: «где объявлен этот символ и где он ещё используется».
Вход — locator объявления, а не имя: `res://src/player.gd:4` (строка, опционально
`:колонка`). Выход — список мест с координатами, типом связи и уверенностью плюс
счётчики.

| Вид | Значение |
|---|---|
| `link` | `declaration` для самого объявления, `call`, `member`, `identifier` и прочие `context` парсера, `string` для строкового литерала |
| `confidence` | `proven` — доказано, `probable` — вероятно, `dynamic` — только по строке |
| `note` | обязателен для не-`proven`: причина, **почему** не доказано (иначе модель гадает) |

Файлы эталона (только чтение, `python -B`):

| Файл | Строк | Что берём |
|---|---|---|
| `godot_tools/symbol_refactor_part2.py` | 670 | `find_references` (583), `_usage_query` (537), `_locate_declaration` (553), `_reference_is_safe` (35), `exclude_place` (485) |
| `godot_tools/symbol_refactor_part1.py` | 749 | `_unverified_reason` (266), `_typed_receivers` (379), `_find_subclasses` (508), `_owner_shadows_name` (465), `KINDS` (21), `_KIND_TO_DECL` (27) |
| `godot_tools/gd_semantic_parser.py` | 392 | `tokenize(text)` и `parse(text, path="")` → `declarations` / `references` / `strings` — весь разбор |
| `minilich/ml_project_index.py` | 1083 | только смысл `semantic_snapshot`: файлы + `sha256` + `semantic`; **numpy, кэш на диске и обучение не переносим** |

Что делает `find_references` по шагам (part2:583–683):
1. разбор action (kind ∈ 7 видов, `old_name` — валидный идентификатор GDScript,
   не ключевое слово; `new_name` может отсутствовать);
2. snapshot проекта → все объявления всех `.gd`;
3. `_locate_declaration`: ровно одно объявление по locator, иначе ошибка со
   списком того, что в файле объявлено (`LocatorError`);
4. `_find_subclasses` по цепочке `extends` — наследники считаются «своими»;
5. перебор файлов: токенизация, затем по `references` — фильтр по имени, фильтр
   «ссылка в другой области видимости», фильтр локальной тени (одноимённая
   локальная переменная — это **другая** сущность, молча пропускается);
6. `_reference_is_safe` → `proven`/`probable`; для `probable` — `_unverified_reason`
   в `note`;
7. строковые литералы, точно равные имени → `dynamic` + причина классификации;
8. сортировка по `(path, line, column)`, `by_link`, три счётчика.

## 3. Главное: `usages` — не один файл, а три слоя (это и есть сложность среза)

Ты не можешь «просто переписать part2»: он стоит на разборе GDScript и на
проектном индексе, которых в новом репозитории ещё нет. Срез делится на три
стадии, и **каждая следующая начинается только после зелёных тестов предыдущей**:

**S1. `python/formats/gdscript/`** — перенос `gd_semantic_parser.py` (392 строки):
`tokenize` + `parse`. Без IO, без Godot, без знаний о фичах (R-11). Сейчас там
заглушка `formats/gdscript.py` (312 б). Если итог > 400 строк (R-06) — делай
пакет: `formats/gdscript/{__init__.py, tokens.py, declarations.py}` с реэкспортом
в `__init__.py`. Корпус: 8–10 маленьких `.gd` → ожидаемая структура
`declarations/references/strings` (снимается с эталонного `parse`).

**S2. `code_intel/shared/symbol_index.py`** — проект → список файлов
`{path, sha256, declarations, references, strings}`. Обход через порт `fs`
(не `os.walk`), разбор через `formats`, без кэша на диске, без numpy, без
`minilich`. Корпус: мини-проект → состав индекса (все объявления/ссылки).

**S3. `python/modules/code_intel/usages/`** — locator, фильтры, доказательство,
отчёт. Здесь живут `domain/` (чистые правила), `app.py` (≤ 80), `ports.py`
(`fs` + чтение), `tools.py`, `module.py`.

Оценка объёма: 600–800 строк кода против 200 у `functions`. Это нормально для
самой тяжёлой механики первой волны; не пытайся уложиться в один шаг — три
стадии с тремя зелёными `selfcheck` лучше, чем один красный.

## 4. ToolSpec: `usages`

| Поле | Значение |
|---|---|
| `name` | `usages` (плоское, старое имя — клиенты не должны заметить подмены) |
| args | `kind` (enum из 7: `class_name`, `function`, `signal`, `variable`, `const`, `enum`, `enum_member`), `old_name` (строка), `declaration` (locator `res://path.gd:LINE[:COL]`), `new_name` (строка, необязателен — эталон его принимает и возвращает эхом) |
| result | `{kind, old_name, new_name, declaration, usages:[{path,line,column,link,confidence,note}], by_link:{...}, proven_count, probable_count, dynamic_count}` |
| effects | `read`, `idempotent=True` |
| errors | `invalid_input`, `not_found`, `denied` |
| cost | **не** `cheap` — обход всего проекта; выстави по замеру |

`note` — не украшение: для `probable` обязателен текст причины, для `proven` — `null`.

## 5. Обязательные кейсы корпуса (не меньше 18)

1. объявление + вызовы в другом файле → `declaration` proven, вызовы proven;
2. только объявление (нет ссылок) → один элемент;
3. `by_link` и три счётчика сходятся с содержимым `usages`;
4. ссылка в комментарии → **не** попадает в вывод;
5. одноимённая локальная переменная в другой функции → место исключено;
6. неоднозначная ссылка (динамический получатель) → `probable` с непустым `note`;
7. строковый литерал, точно равный имени → `dynamic` + причина в `note`;
8. locator синтаксически кривой (`res://a.gd:abc`) → ошибка, `kind` — как в эталоне;
9. locator указывает на строку без объявления → ошибка со списком объявлений файла;
10. `kind` не из списка → `invalid_input`;
11. `old_name` — ключевое слово GDScript → `invalid_input`;
12. член класса, переопределённый в наследнике → ссылка учтена, наследник «свой»;
13. `enum_member` и `const` (осторожно: парсер называет константу `constant`);
14. `class_name` из другого файла → виден, `extends`-цепочка учтена;
15. путь вне проекта / абсолютный → `denied`;
16. файл в аддоне → скрыт политикой;
17. пустой проект (нет `.gd`) → пустой результат без падения;
18. неизменность: хеши файлов фикстуры до и после вызова равны (read-only, SEC-11).

Кейсы 1–4, 6–8, 10–12 сначала повтори из `test_find_symbol_usages.py` (10 тестов)
и `test_find_usages_reason.py`, затем добавь свои.

## 6. Решения, которые обязан принять и записать

1. **Границы среза.** `analyze_rename` (предпросмотр: затронутые файлы, риски,
   `excluded`) — следующий срез этого же модуля. Раздели строку 22 `parity.md` на две:
   `usages` → `ported` по факту, `analyze_rename` → `skeleton` до своего среза.
2. **`formats/gdscript`: файл или пакет.** Решай по лимиту 400 строк; при разделении
   `__init__.py` реэкспортирует то же публичное API, что эталон (`tokenize`, `parse`).
3. **Проектный индекс.** Никакого кэша на диске и никакого `minilich`. Индекс строится
   на вызов. Замерь время на `fixtures/projects/minimal`, запиши число. Дорого — это
   **долг** в `PROGRESS.md → Долги`, а не повод строить кэш внутри среза.
4. **Коды ошибок locator'а.** Синтаксис → `invalid_input`, «нет такого объявления» →
   `not_found`. Не выдумывай: сними `expect` с эталона и проверь соответствие.
5. **Порядок S1→S2→S3.** Не начинать S3, пока корпуса S1/S2 не зелёные. Соблазн
   «сделать usages, а разбор потом» даст четвёртый разбор `.gd` в проекте.

## 7. Стоп-условия

Не переносить `part1` сцены/файлы (`_collect_scene_*`, `_plan_file_rename`,
`_collect_path_reference_edits`) и `part3` (запись, откат) — это `editing.symbol_rename`
и `scene_model.*`. Не переносить `minilich`, `numpy`, кэш на диске. Не добавлять IO
в `formats/` и в `domain/`. Не менять поведение `search`/`functions`. Не удалять строки
`tests-map.md`. Не ставить `ported` без зелёного `selfcheck` и живой проверки.
Старый плагин — только чтение.

## 8. Что проверит аудитор

| Проверка | Доказательство |
|---|---|
| три стадии зелёные | `selfcheck` после S1, S2, S3 (или один — но с корпусами всех трёх) |
| эквивалентность | «кейсов ≥18, расхождений 0» + выборочная сверка 3 кейсов с эталоном |
| `formats` без IO | в `formats/gdscript*` нет `os`, `pathlib`, `open(`; тесты на строках |
| доказательство держится | мутация: убрать ветку `_reference_is_safe` → тесты `proven/probable` краснеют |
| read-only | хеши фикстуры до/после (кейс 18) |
| лимиты и границы | `lint_arch`, `check_limits`, `gen_contract --check` — ok |
| чужие механики целы | `selfcheck project_text.search` и `code_intel.functions` — exit 0 |
| числа в отчёте | совпадают с `--collect-only` (в срезе `functions` расходились) |

## 9. Поправки триажа (найдены при подготовке среза)

- `test_find_symbol_usages.py` (строка 60) стоит на `context.gather` — **это ошибка**:
  его 10 тестов проверяют ровно `usages` (`declaration` + ссылки, координаты и
  confidence, `nothing_is_written`, `dynamic` у строки, `probable` вместо ошибки,
  запрос без `new_name`, `by_link`, плохой locator, комментарий не ссылка,
  read-only без права записи). Поменяй модуль на `code_intel.usages`, судьбу оставь
  `corpus`, строку не удаляй. Это третья ошибка триажа по именам файлов — фиксируй
  в `WORKLOG.md`, что карта правится, а не подгоняется.
- `test_find_usages_reason.py`, `test_usage_checklist_honesty.py`,
  `test_string_reference_criterion.py`, `test_rename_index_completeness.py`,
  `test_rename_analyze_split.py`: в примечании допиши, какая часть кейсов
  принадлежит `code_intel.usages` (доводы/`note`, полнота индекса, критерий строковой
  ссылки), а какая — `editing.symbol_rename` / будущему `analyze_rename`.
  Судьбы не меняй, строки не удаляй.

## 10. Финальный прогон и записи

```
python tools/selfcheck.py code_intel.usages        → exit 0
python tools/snapshot_diff.py code_intel.usages    → кейсов N, расхождений 0
python tools/selfcheck.py code_intel.functions     → exit 0
python tools/selfcheck.py project_text.search      → exit 0
python -m pytest python/modules tests/py -q --collect-only   (счётчики по файлам)
python tools/security_audit.py --json; lint_arch; check_limits; gen_contract --check
probe usages --args-file <...>; python -m python.channels.mcp.stdio fixtures/projects/minimal
```

Записи: лист `docs/porting/code_intel.usages.md` (создать **до** кода; в нём таблица
трёх стадий, решения, критерии `note`), `PROGRESS.md` (этап 7 — только когда все три
стадии зелёные; иначе этап 4–6 и конкретное «следующее действие»), `parity.md`
(строка 22 разделена на две), `WORKLOG.md` (сессия с командами и выводом),
`tests-map.md` (поправки §9). `__pycache__` и `.pytest_cache` после прогонов — ноль.


