# Задача: починить валидатор схем (union-типы) — до части A

> **Выполнено, аудит принял 2026-10-27.** Репро §0 даёт `[]`; мутация (удаление ветки
> union) валит 4 теста `tests/py/kernel/test_schema_union.py`; подложенный `"date"` в
> `contract/editor_verbs.json` (4 nullable-поля) и в `contract/capabilities/write_preview.json`
> валит `gen_contract --check` с полным путём поля, после восстановления — снова `ok`,
> файлы побайтово те же (sha256 сверил аудитор). Промпт оставлен как образец и как
> запись требования.

Ты в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`. Починка инструментов принята,
но аудит нашёл дефект в ядре, который блокирует часть A (мост редактора).

## 0. Что сломано (воспроизводится, проверено аудитором)

`python/kernel/schema.py:13-23`: `_type_ok(value, expected)` сравнивает `expected`
со строкой, затем делает `_TYPES.get(expected)`. Если `type` в схеме — **список**
(`["string","null"]`), `dict.get(list)` бросает `TypeError`.

Воспроизведение (эта команда обязана перестать падать):

```
python -c "import sys; sys.path.insert(0,'.'); from python.kernel.schema import validate; \
print(validate({'node_path': None}, {'type':'object','properties':{'node_path':{'type':['string','null']}}}))"
→ сейчас: TypeError: cannot use 'list' as a dict key (unhashable type: 'list')
→ должно: []
```

В отчёте это названо «nullable-поля валидируются мягко» — на самом деле
**исключение**. Сегодня не регресс: ответы моста ещё не валидируются, поэтому
99/0 и три `selfcheck` зелёные. Но в `contract/editor_verbs.json` nullable стоит в
четырёх местах (`active_scene`, `node_path`, `scene`, `script`) — это «пусто/нет
выделения», то есть самый частый ответ. Как только часть A начнёт проверять ответ
моста схемой, первый же ответ без выделения уронит валидатор.

## 1. Требуемое поведение

1. **Union-тип**: `type: [...]` — валидно, если значение подходит хотя бы под один
   элемент списка. `None` проходит `["string","null"]`; `5` — нет.
2. **Вложенность работает**: union внутри `items`, внутри `properties`, в массивах
   объектов (`open_scenes[]` → `revision`/`dirty`), в `required`-полях.
3. **Неизвестный тип — ошибка, а не пропуск.** Сейчас `_type_ok` на `type: "date"`
   возвращает `True` (молча пропускает). Должно быть: при проверке **данных** —
   `False` (fail closed: лучше отказать, чем принять непроверенное); при проверке
   **схемы** — отдельная функция, которая называет неизвестный тип.
4. `validate()` остаётся тотальной: возвращает список проблем, не бросает исключений
   ни на каком входе, включая мусорные схемы (`type: 5`, `items: "x"`,
   `required: "path"`, `properties` не-dict).
5. `additionalProperties: false`, `enum`, `min/max`, `minLength`, `minItems` ведут
   себя как сейчас — их не трогать.

## 2. Форма кода

Минимальная правка, без нового модуля:

- в `_type_ok` — ветка на список (рекурсивно; любой совпавший элемент → `True`);

## 3. Тесты (обязательно, иначе фикс не считается)

Новый файл `tests/py/kernel/test_schema_union.py` (если каталога нет — создай):

1. `None` против `["string","null"]` → `[]`.
2. `"res://a.tscn"` против `["string","null"]` → `[]`.
3. `5` против `["string","null"]` → одна проблема, текст содержит `node_path`.
4. Массив объектов: `open_scenes: [{"path":"res://a.tscn","revision":3,"dirty":false,
   "active":true,"unsaved_changes":0}]` против `result_schema` из
   `contract/editor_verbs.json` → `[]`; тот же объект с `revision: "3"` → проблема с
   путём вида `[0].revision`.
5. `type: "date"` → при проверке данных проблема (не `True`), `unknown_schema_types`
   называет поле и тип.
6. Мусорные схемы (`type: 5`, `items: "x"`, `properties: []`) → `validate` не бросает,
   возвращает список.
7. Каждый примитив из `contract/editor_verbs.json`: `result_schema` не содержит
   неизвестных типов (защита от опечатки в контракте).

## 4. Гейт в контракте

`tools/gen_contract.py --check`: добавить проверку, что в `verbs[].result_schema`
(и в `schema` инструментов из `contract/capabilities/*.json`, если поле там есть)
нет неизвестных типов — через `unknown_schema_types`. При находке — `fail` с полным
путём поля. Тест рядом с существующими в `tests/py/tools/test_gen_contract.py`.

## 5. Чего не делать

- Не переписывать валидатор на полноценный JSON Schema (`anyOf`/`$ref`/`format` не
  нужны, пока их нет в контрактах).
- Не трогать `protocol/validation.py`, `ToolSpec`, корпуса, конвейер записи.
- Не менять `contract/editor_verbs.json` по существу: nullable остаётся.
- Не «улучшать» тексты ошибок — они попадают в `invalid_input`.

## 6. Приёмка (что проверит аудитор)

| Что | Как проверит |
|---|---|
| union работает | свой прогон репро-команды из §0: `None` → `[]`, `5` → проблема |
| вложенность | `open_scenes[]` с `revision: "3"` → проблема с путём `[0].revision` |
| fail closed | `type: "date"` → проблема, а не `[]` |
| тотальность | мусорные схемы не бросают исключений |
| гейт | подложит в контракт тип `"date"` → `gen_contract --check` падает; после удаления зелёный |
| мутация | убрать ветку union → репро снова падает (докажет, что тесты держат фикс) |
| регресс | 99 кейсов/0; `write_apply` 44/15, `rollback` 24/4, `write_preview` 45/16 — `ok` |

## 7. Финальный прогон и записи

```
python -m pytest python/modules tests/py -q        # exit 0, числа = --collect-only
python tools/snapshot_diff.py                      # 99 кейсов, 0 расхождений
python tools/selfcheck.py editing.write_apply      # ok, exit 0
python tools/selfcheck.py editing.rollback         # ok, exit 0
python tools/selfcheck.py editing.write_preview    # ok, exit 0
python tools/gen_contract.py --check               # ok + строка долга моста
python tools/security_audit.py --json; python tools/lint_arch.py; python tools/check_limits.py
```

Записи: `docs/WORKLOG.md` — короткая сессия «фикс валидатора схем» с репро и выводом;
`docs/porting/context.editor_context.md` → «Инструменты проверки»: строка «union-типы
поддержаны, неизвестный тип = отказ, гейт в `gen_contract`»; `docs/NOTES.md` —
поправить запись про «мягкую валидацию nullable», если она там есть; `__pycache__`
после прогонов — ноль (`PYTHONDONTWRITEBYTECODE=1`).

- `_TYPES` пополняется явно, `_TYPES.get` больше не может получить нехэшируемое
  значение;
- новая функция `unknown_schema_types(schema)` — обход по `type`, `items`,
  `properties` (и по вложенным схемам, которые реально есть в наших контрактах),
  возвращает список вида `["(аргументы).node_path: неизвестный тип 'date'"]`;
- докстринг модуля: что поддерживается и что «неизвестный тип = отказ».

Ограничение объёма: файл остаётся ≤ 400 строк (сейчас ~71), новых зависимостей нет.
