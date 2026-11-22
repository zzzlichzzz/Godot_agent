# Задача: четвёртый срез — `analyze_rename` (предпросмотр переименования)

Ты — портер. Работа: добавить **второй инструмент** в уже принятый модуль
`code_intel.usages` — `analyze_rename`. Это read-only предпросмотр: «что и где
изменится, если переименовать», с списком затронутых файлов и рисками. Ничего не
пишется, ничего не применяется.

Важно: `analyze_rename` — не новая логика поиска. По эталону это **обёртка над
`find_references`** (который ты уже перенёс в срез `usages`): тот же обход, те же
доказательства, только другой отчёт. Ожидаемый объём — 150–200 строк, не 600.
Если получается больше, ты дублируешь уже перенесённое (R-04).

Принятые срезы: `project_text.search` (16 кейсов), `code_intel.functions`
(17), `code_intel.usages` (18). Их `selfcheck` обязан остаться `ok`.

## 0. Три гигиенические правки перед началом (15 минут, они же долги аудита)

1. **`pyproject.toml`**: добавь
   ```toml
   [tool.pytest.ini_options]
   addopts = "--import-mode=importlib -p no:cacheprovider"
   ```
   Без этого `pytest` без флагов падает на сборе (44 одноимённых `tests/test_core.py`),
   и это дважды стоило времени аудитору. Проверь: `python -m pytest python/modules tests/py -q`
   без флагов собирает **120+** тестов.
2. **`fixtures/` README (или `docs/PORTING.md §4`)**: опиши **два вида** фикстур,
   которые уже существуют: `fixtures/corpus/<область>/<фича>/` — корпус инструмента
   (снимается с эталона), и `fixtures/parity/<формат>/` — корпус формата (`gdscript`,
   снят с эталонного `parse`). Сейчас второй вид нигде не объявлен, следующий портер
   будет искать его не там.
3. **`tools/_reference_runner.py`**: в шапке перечислены только `search` и `functions`,
   ветка `usages` добавлена без строки. Допиши `usages` (и `analyze_rename`, который
   добавишь в этом срезе).

## 1. Прочитать до первой правки

| Что | Зачем |
|---|---|
| AGENTS.md | стоп-условия, 11 шагов |
| RULES.md | 21 правило; твои: R-02, R-04, R-05, R-06, R-08, R-11, R-16–R-19 |
| docs/architecture.md §3/§4/§7 | ToolSpec, путь вызова, состав модуля |
| docs/PORTING.md | шаги, DoD, §8/§9 |
| docs/porting/code_intel.usages.md | **лист того же модуля** — твоя отправная точка и стиль |
| docs/parity.md строка 23 | обещание: `analyze_rename` → `code_intel.usages`, skeleton |
| docs/PROGRESS.md | твоя строка, этап 0 |
| docs/tests-map.md строки 61, 87, 95, 127, 131 | старые тесты `*_rename_*`, у них уже дописано разделение |
| python/modules/code_intel/usages/ | что уже написано: `domain/core.py`, `domain/evidence.py`, `app.py`, `module.py`, `ports.py` |

## 2. Что такое `analyze_rename` по факту эталона (проверено)

`godot_tools/symbol_refactor_part2.py:685–718` — 34 строки:

```python
def analyze_rename(project_root, action, allow_addons=False, addon_dir=None,
                   allow_self_edit=False):
    result = find_references(...)                 # тот же поиск, что в `usages`
    target_path, line, _column = _parse_locator(action["declaration"])
    affected_paths = sorted({p["path"] for p in result["usages"]
                             if p["confidence"] == "proven"})
    risks = [ "%s:%s [%s, %s]%s" % (p["path"], p["line"], p["link"], p["confidence"],
                                    (" — " + p["note"]) if p.get("note") else "")
              for p in result["usages"] if p["confidence"] != "proven" ]
```

Выход (все поля обязательны): `action="analyze_rename"`, `kind`, `old_name`,
`new_name`, `declaration` (эхом, как пришёл), `allow_unverified` (флаг из action),
`mode` (`"strict"` по умолчанию), `usages` (тот же формат, что в `usages`),
`affected_paths` (**отсортировано**, только `proven`, дубликаты убраны),
`risks` (**строки**, не объекты), `by_link`, `proven_count`, `probable_count`,
`dynamic_count`, `declaration_path`, `declaration_line` (результат разбора locator'а).

Мост эталона (`agent_bridge.py:823–862`) требует **все три** строки: `--declaration`,
`--old-name`, `--new-name` — иначе `RC_USAGE`. Флаги: `--kind`, `--mode strict|probable`,
`--allow-unverified`. `mode` и `allow_unverified` в анализ **проходят** и влияют на
то, какие ссылки считаются доказанными (комментарий эталона: чеклист мест должен
знать, переименуются ли недоказанные ссылки, иначе обещает несуществующее).

Что относят к этому срезу старые тесты (`test_rename_analyze_split.py`, 9 тестов):
сюда — «анализ ничего не пишет», «в `affected_paths` попадают файлы», «риски
отражаются», «анализ не требует права записи»; **не сюда** — `exclude`,
`skipped_usages`, частичное применение и откат (это `editing.symbol_rename`).

## 3. Что уже есть в модуле (не переписывай, используй)

- `domain/core.py` (268) — locator, валидация входа, фильтры;
- `domain/evidence.py` (189) — доказательство ссылки (`proven`/`probable`) и причины;
- `symbol_index` (`code_intel/shared/`) — проектный индекс, 11.4 мс на мини-проекте;
- `formats/gdscript/` — разбор `.gd` (пакет, реэкспорт `tokenize`/`parse`);
- `ports.py` — чтение через порт `fs`; `app.py` (40) — тонкая оркестрация;
- `module.py` — сейчас `provides_tools=("usages",)`.

Твоя работа — **второй инструмент в том же модуле**: `app.call` получает `tool` и
разводит по двум обработчикам, `module.py` объявляет `provides_tools=("usages", "analyze_rename")`,
`tools.py` добавляет второй `ToolSpec`. Реестр знает правило «одно имя — один
владелец» (ADR-0004), поэтому конфликта не будет, но проверь на живом `tools/list`.

## 4. ToolSpec: `analyze_rename`

| Поле | Значение |
|---|---|
| args | `kind` (enum 7, как в `usages`), `declaration` (locator), `old_name`, **`new_name` — обязательный**, `mode` (enum `strict`\|`probable`, default `strict`), `allow_unverified` (bool, default `false`) |
| result | `{kind, old_name, new_name, declaration, declaration_path, declaration_line, allow_unverified, mode, usages, affected_paths, risks, by_link, proven_count, probable_count, dynamic_count}` |
| effects | `read`, `idempotent=True` |
| errors | `invalid_input` (нет `new_name`, кривой locator, неизвестный `kind`/`mode`), `not_found`, `denied` |
| availability / cost | `*` / `heavy` (тот же полный обход, что у `usages`) |

`risks` — **строки ровно в формате эталона**: `path:line [link, confidence]`,
и ` — note`, если `note` есть. Не переделывай в объекты: это то, что читает
человек и модель в предпросмотре, и это часть поведения (паритет по корпусу).

## 5. Обязательные кейсы корпуса (не меньше 10)

Корпус: `fixtures/corpus/code_intel/analyze_rename/`, фикстуры — переиспользуй
`fixtures/projects/usages/` (там уже есть `lab_entity.gd`, `lab_root.gd`,
`lab_turret.gd`, `lab_dynamic.gd`); новую фикстуру создавай только если нужного
случая в них нет.

1. все ссылки доказаны → `risks: []`, `affected_paths` содержит все файлы с proven;
2. `affected_paths` **отсортирован** и без дубликатов (файл с двумя ссылками — один раз);
3. есть `dynamic` (строка `call()`/`ClassDB.instantiate`) → `risks` непуст, строка с `[string, dynamic]` и ` — call() по имени`;
4. есть `probable` → строка риска с `[member, probable]` и причиной в ` — ...`;
5. `new_name` отсутствует → `invalid_input` (эталон отвечал `RC_USAGE`);
6. кривой locator → `invalid_input`; locator без объявления → `not_found`;
7. `declaration_path`/`declaration_line` разобраны из locator'а (например `res://src/lab_entity.gd:12` → `res://src/lab_entity.gd`, `12`);
8. `mode="probable"` → отчёт отличается от `strict` так же, как в эталоне (сравни оба снятия);
9. `allow_unverified=true` → поле в отчёте `true`, и (если эталон меняет `affected_paths`) изменение видно;
10. ничего не пишется: хеши файлов фикстуры до и после равны;
11. путь вне проекта / аддон → `denied`;
12. **регресс `usages`**: прогон `snapshot_diff` по корпусу `usages` — 18/18 без изменений.

## 6. Решения, которые обязан принять и записать

1. **Один модуль, два инструмента.** `analyze_rename` живёт в `code_intel.usages`
   (parity строка 23). Отдельную папку не создавать: это обёртка над тем же поиском (R-04).
2. **`mode` — не только эхо.** Проверь `domain/evidence.py`: если `reference_is_safe`
   не принимает `mode`, добавь параметр (default `strict`) и проведи его из
   `analyze_rename`. Доказательство: кейс 8 показывает различие, а корпус `usages`
   остаётся 18/18 (значит, поведение `usages` не сдвинулось).
3. **`risks` строкой, а не структурой.** Обоснование — паритет и читаемость.
   Если решишь иначе, это отличие в `docs/deviations.md`, не «улучшение по вкусу».
4. **`exclude`/`skipped_usages`/apply — не здесь.** Они относятся к
   `editing.symbol_rename` (следующий срез). В `ToolSpec` этого среза их нет.
5. **Корпус снимать с эталона** через новую ветку `analyze_rename` в
   `tools/_reference_runner.py` (вызов `symbol_refactor.analyze_rename`), а не
   через новый код — иначе корпус будет проверять сам себя.

## 7. Стоп-условия

Не переносить `prepare_rename`, `apply_prepared_rename`, `exclude`, `skipped_usages`,
`public_prepared`, `history_manager` — это `editing.symbol_rename`, следующий срез.
Не менять корпус и поведение `usages`, `functions`, `search`. Не добавлять IO в
`domain/` и `formats/`. Не превращать `risks` в объекты и не «улучшать» формат
строк. Не удалять строки `tests-map.md`. Не ставить `ported` без зелёного
`selfcheck` и живой проверки. Старый плагин — только чтение (`python -B`).

## 8. Что проверит аудитор

| Проверка | Доказательство |
|---|---|
| `selfcheck code_intel.usages` | `ok`, exit 0; `unit` вырос (было 34), `corpus` ≥ 28 (18 + ≥10) |
| `selfcheck` трёх прошлых срезов | `search`, `functions` — по-прежнему `ok`, exit 0 |
| `snapshot_diff` | `usages 18/18` **без изменений** + новый корпус без расхождений |
| один модуль, два инструмента | `tools/list` MCP показывает `usages` и `analyze_rename` из одного модуля |
| `risks` в формате эталона | выборочное сравнение 2 кейсов с выводом эталона, строка в строку |
| `mode` действительно работает | кейс 8: `strict` и `probable` дают разные отчёты, как в эталоне |
| read-only | хеши фикстуры до/после (кейс 10) |
| нет дублирования поиска | в `app.py`/`domain/` нет второго обхода файлов; `analyze` вызывает существующую функцию `usages` |
| числа в отчёте | совпадают с `--collect-only` и `ReadAllLines` (за прошлые срезы расходились дважды) |
| гигиена | `pytest` без флагов собирает тесты; `fixtures` двух видов описаны; шапка `_reference_runner` полная; `__pycache__`/`.pytest_cache` = 0 |

## 9. Финальный прогон и записи

```
python tools/selfcheck.py code_intel.usages        → exit 0
python tools/snapshot_diff.py                      → usages 18/18 без изменений + analyze_rename N/N
python tools/selfcheck.py code_intel.functions     → exit 0
python tools/selfcheck.py project_text.search      → exit 0
python -m pytest python/modules tests/py -q        (без флагов — addopts из pyproject)
python tools/security_audit.py --json; lint_arch; check_limits; gen_contract --check
probe analyze_rename --args-file <...>; python -m python.channels.mcp.stdio fixtures/projects/usages
```

Записи: лист `docs/porting/analyze_rename.md` (создать **до** кода; в нём таблица
полей отчёта, 5 решений, список кейсов), **строка 23 `parity.md` → `ported`**,
`PROGRESS.md` (этап 7 + следующее действие — `editing.symbol_rename`: воронка,
`exclude`, `skipped_usages`, откат), `WORKLOG.md` (сессия с выводом команд),
`tests-map.md` (при необходимости — какая часть кейсов `test_rename_analyze_split.py`
теперь закрыта; строки не удалять).


