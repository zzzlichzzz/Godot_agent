# Задача: починка инструментов и контракта перед частью B

Ты в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`. Седьмой срез остановлен на
стадии 4: контракт моста есть (ADR-0007, `contract/editor_verbs.json`, SEC-03,
лист `docs/porting/context.editor_context.md`), транспорт и модуль не начаты —
`substrate/editor/client.py` 153 байта, `tests/py/integration/fake_editor.py` нет,
маркеров `# verb:` в `editor/` ноль.

Этот шаг — **только починка того, что будет мешать следующим стадиям**. Код моста
(клиент, GDScript-сервер, модуль-вклад, фейк) не начинать: сначала инструменты
перестают врать. Четыре правки, каждая с проверкой; корпуса и конвейер записи не
трогать.

## 1. `gen_contract.py`: `_handlers` — не постоянный выключатель

**Дефект.** `tools/gen_contract.py:68`: `if data.get("_handlers") ==
"pending-editor-bridge": return problems` — сверка обработчиков пропускается
целиком, условие не снимается появлением маркеров. Когда в `editor/` появится
первый `# verb:`, сверка не включится сама: забытый маркер, опечатка, лишний
обработчик пройдут зелёным. `detail` при этом говорит «расхождений нет», не
сообщая о пропуске.

**Требование.** Логика становится условной:

- есть маркеры → сверка **обязательна в обе стороны**: `missing` (примитив без
  обработчика) и `extra` (обработчик вне словаря) — обе в `problems`;
- маркеров нет и `_handlers == "pending-editor-bridge"` → пропуск **разрешён**, но
  долг виден в `detail`: `артефактов N, расхождений нет (мост: 0 обработчиков из 3, ожидаются)`;
- маркеров нет и `_handlers` нет → проблема «нет ни одного обработчика»;
- маркеры есть **и** `_handlers` стоит → проблема `снимите _handlers: обработчики
  уже есть`: мёртвый выключатель обязан удаляться, а не жить дальше.

**Тесты** (вынеси `check_editor_verbs(root)`-часть в тестируемую функцию с
параметром каталога; четыре временных корня): пропуск при нуле маркеров; `missing`
при подмножестве; `extra` при лишнем; «снимите `_handlers`» при маркерах и флаге.

## 2. Схема результата примитивов: `result` строками — это не контракт

**Дефект.** В `editor_verbs.json` у примитива есть только список имён
(`"result": ["open_scenes", "active_scene", "project_hash"]`). Форма элемента
`open_scenes` нигде не зафиксирована, а часть B целиком опирается на `revision` и
`dirty` внутри элемента. Python-клиент и GDScript придумают разные имена.

**Требование.** У каждого примитива — `result_schema` (JSON Schema, как в
`ToolSpec`), минимум:

- `editor_ping`: объект, обязательные `godot`(string), `verbs_version`(int),
  `protocol`(int), `open_scenes`(int), `uptime_s`(number);
- `editor_state`: `open_scenes` — массив объектов с обязательными
  `path`(string), `revision`(int), `dirty`(bool), `active`(bool),
  `unsaved_changes`(int); плюс `active_scene`(string|null), `project_hash`(string);
- `editor_selection`: `node_path`(string|null), `scene`(string|null),
  `properties` — массив объектов `{name, type, value}`, `script`(string|null).

`gen_contract` дополнительно проверяет: у каждого примитива есть `result_schema`
объектного типа; имена в `result_schema.properties` совпадают с прежним списком
`result` (переименование — только с бампом версии, §3). Тест: примитив без
`result_schema` → `fail` с именем примитива.

## 3. `verbs_version`: правило бампа, а не только число

**Дефект.** Версия есть, политики нет. Через два среза примитив добавят без
бампа, и проверка расхождения перестанет ловить.

**Требование.** В `contract/editor_verbs.json` — поле `_change_policy` с текстом,
в ADR-0007 — тот же текст абзацем:

- добавление примитива — `verbs_version + 1`, аддитивно (старый клиент живёт,
  новый клиент на старом сервере получает `engine_down/verbs_mismatch`);
- изменение семантики существующего примитива (значение поля, единицы, момент
  вызова) — `+1`, и старый сервер считается несовместимым;
- изменение только описаний/схем без поведения — версию не меняем.

Машинно проверяется: `gen_contract` падает, если `verbs_version` отсутствует или
`< 1`. Правило «добавил примитив — поднял версию» автоматизировать нельзя, поэтому
оно живёт в ADR и в `_change_policy`, а в листе — строка «при добавлении
примитива: бамп + запись в ADR».


## 4. `selfcheck`: вклад без инструментов — проверяемое поведение

**Дефект.** Логика «нет `provides_tools`, но есть `contributes_to` → не `fail`»
есть в коде, но не проверена ни одним тестом; первый настоящий вклад
(`context.editor_context`) ещё не собирался, поэтому неизвестно, что покажет
таблица.

**Требование.**

1. Вынеси решение в чистую функцию в `tools/selfcheck.py`, например
   `module_readiness(spec, has_tests, has_corpus)` → `(status, detail)`.
   Четыре случая в тесте: заготовка (спеки нет) → `not_implemented`; вклад без
   `tests/` → `not_implemented` с причиной «нет tests»; вклад с `tests/` → `ok`;
   модуль без `provides_tools` и без `contributes_to` → `fail`.
2. Живой прогон `python tools/selfcheck.py context.editor_context` — приложить
   вывод целиком. Ожидаемо: `module ok` (манифест и вклад валидны) либо
   `not_implemented` с внятной причиной; **`fail` быть не должно**. Если сейчас
   `fail` — сначала починить, потом приложить.

## 5. Чего не делать

- Не писать `substrate/editor/client.py`, `fake_editor.py`, GDScript-сервер,
  модуль-вклад. Это следующая стадия.
- Не менять корпуса, конвейер записи, `kernel`, `substrate/store`.
- Не трогать принятые механики: 99 кейсов и три `selfcheck` обязаны остаться `ok`.
- Не «улучшать» формат кадра и список примитивов — только схемы (§2) и политику (§3).
- Старый плагин — только чтение.

## 6. Приёмка (что проверяет аудитор)

| Что | Доказательство |
|---|---|
| пропуск стал условным | четыре теста `check_editor_verbs` зелёные; подложенный маркер без обработчика → `fail` |
| долг виден | `gen_contract.py --check` печатает в `detail`: `мост: 0 обработчиков из 3, ожидаются` |
| мёртвый выключатель ловится | маркер + `_handlers` → `fail` «снимите `_handlers`» |
| схемы есть | у трёх примитивов `result_schema`; тест «без схемы → fail» |
| `open_scenes` описан | `revision`/`dirty`/`active`/`unsaved_changes` в схеме элемента |
| политика версии | `_change_policy` в JSON и абзац в ADR-0007 |
| вклад проверен | четыре теста `module_readiness` + живой вывод `selfcheck context.editor_context` |
| регресс | `snapshot_diff` 99/0; `selfcheck` `write_apply`/`rollback`/`write_preview` ok |
| гигиена | `security_audit` ok; `lint_arch`/`check_limits` зелёные; `__pycache__` 0 |

## 7. Финальный прогон и записи

```
python tools/gen_contract.py --check      # detail содержит долг моста
python tools/snapshot_diff.py             # 99 кейсов, 0 расхождений
python tools/selfcheck.py editing.write_apply
python tools/selfcheck.py editing.rollback
python tools/selfcheck.py editing.write_preview
python tools/selfcheck.py context.editor_context   # вывод приложить
python -m pytest python/modules tests/py -q        # exit 0
python tools/security_audit.py --json; python tools/lint_arch.py; python tools/check_limits.py
```

Записи: `docs/PROGRESS.md` — строка `context.editor_context` остаётся этап 4, но
с пометкой «инструменты починены: `gen_contract`, схемы, политика, `selfcheck`»;
в «Долги» — строка «снять `_handlers: pending-editor-bridge` при первом `# verb:`»
(условие снятия теперь машинное); `docs/WORKLOG.md` — короткая сессия с выводом;
`docs/adr/0007-most-redaktora.md` — политика версии; лист механики — раздел
«Инструменты проверки»; `deviations.md` — только если отступаем от правила.
