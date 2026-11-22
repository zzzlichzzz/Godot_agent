# Задача: девятый срез — мост редактора, часть B: `editing.scene_ops` (батч в одном undo)

Ты в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`. Часть A принята аудитом
2026-10-28: транспорт `python/substrate/editor/`, GDScript-сервер, три read-примитива
и вклад `context.editor_context` — `ported`. Теперь часть B из листа
`docs/porting/context.editor_context.md` §«Границы»: **запись в сцену**, но только
через GDScript и только в одном undo.

## 0. База (замер аудита 2026-10-28; перепроверь, числа только из вывода команд)

```
python -B -m pytest python/modules tests/py     # 417 passed (== --collect-only, 39 файлов)
python tools/snapshot_diff.py                   # кейсов 102, расхождений нет
python tools/gen_contract.py --check            # 8 артефактов, ok
python tools/lint_arch.py; python tools/check_limits.py   # 453/0 и 453/0
python tools/selfcheck.py context.editor_context          # ok, unit 27
```

- `contract/editor_verbs.json`: `verbs_version: 1`, три примитива, `_handlers` снят;
  маркеров по регексу `gen_contract` — **3** (грепом строки `# verb:` по репозиторию — 8:
  три маркера, три упоминания в комментариях/константах `editor/` и два в тестах).
  sha256 `F73AB2D8…B1E4`.
- `editing.scene_ops` — **заглушки**: `app.py` 2, `module.py` 8, `tools.py` 1,
  `domain/core.py` 1, `tests/test_core.py` 1 строка. Листа механики нет.
- Файлов 896, `__pycache__` 0. `schema.py` `629FCE54…4067` — **не трогать**.
- Живого Godot нет: GDScript не компилируется, всё, что требует редактора, — `needs_live`
  и приёмкой не считается. Поэтому доказывать здесь можно только **фейком** и **схемами**.

## 1. Границы среза

| В срезе (B) | Не в срезе |
|---|---|
| GDScript-примитивы записи: план (dry-run) и применение — в `editor/` | `.tscn`/`.tres` как файлы, линт, `formats/tscn.py` (это C) |
| `editing.scene_ops`: `MODULE`, `ToolSpec`, домен, `app.py`, тесты | `editing.resource_ops`, `project_ops.settings_set` |
| один **батч операций = один undo-шаг** (`begin_undo`/`commit_undo`/`abort_undo`) | второй слушающий сокет, HTTP, свои таймауты «на всякий случай» |
| `expected_revision` (оптимистичная блокировка по `revision` редактора) | переписывание `substrate/editor/*` и `editor/bridge/*` без нового кейса |
| квитанции: `step_id`, `applied_revision`, `changes[]`, `undo_label` | `ResourceSaver` в Python, `scene_apply_batch` мимо гейта |
| bump `verbs_version: 1 → 2` + ADR-0007 (политика лежит дважды) | правки `tools/*`, `python/kernel/schema.py`, принятых механик |

В Python **нет** записи: домен строит нормализованный батч и проверяет ответ; всё, что
касается `Node`, `PackedScene`, `ResourceSaver`, undo, — только GDScript (R-14).

## 2. Контракт части B (решения, которые нельзя менять по ходу)

Два новых примитива в `contract/editor_verbs.json` (`effects: write`, `thread: main`,
у каждого `result_schema`; `verbs_version` → **2**, `_change_policy` и §«Версия словаря»
ADR-0007 правятся одним диффом):

| Verb | Вход | Результат |
|---|---|---|
| `editor_scene_plan` | `scene` (`res://`), `expected_revision` (int), `operations` (1…64) | `scene, revision, plan_digest, steps[{index, op, target_node, preview}], would_change[], warnings[]` — **ничего не пишет** |
| `editor_scene_apply` | то же + `plan_digest`, `undo_label` | `scene, applied_revision, undo_label, receipts[{step_id, op, node_path, applied}], changes[{node_path, field, before, after}]` |

Правила:
- Операции (ровно эти, каждая — словарь с `op`): `add_node` (`parent`, `name`, `type`),
  `set_property` (`node`, `property`, `value`), `attach_script` (`node`, `script`),
  `connect_signal` (`from`, `signal`, `to`, `method`). Неизвестная `op` — отказ всего
  батча (`unknown_operation`), а не «пропустить и продолжить».
- Один батч = **один** undo-шаг: `begin_undo(undo_label, apply, revert)` → все операции →
  `commit_undo()`; любая ошибка → `abort_undo()` и **ни одного изменения** в сцене.
- `expected_revision` не совпал → `conflict` с `details.reason = "revision_mismatch"`
  (текущая ревизия в `details.revision`). Проверка — под гейтом, до первой мутации.
- `plan_digest` — sha256 нормализованного батча (порядок операций значим); применение
  плана с чужим digest → `conflict`/`stale_plan`, эффекта нет.
- `dirty`-сцена: применение **разрешено** только если сцена открыта и ревизия совпала;
  `unsaved_changes` из `editor_state` в ответе не меняется мостом (B не сохраняет файл).
- Транспортные отказы (`truncated`, `timeout`, `engine_down`) не должны оставлять undo
  в состоянии «начат»: `abort_undo` вызывается и на исключении.

## 3. Модуль `editing.scene_ops`

- `MODULE`: `ModuleSpec(id="editing.scene_ops", environment="editor", provides_tools=("scene_ops",),
  contributes_to=(), internal_services=(), requires_ports=("editor",),
  capabilities=("editing.scene_ops",), effects="write")`; `TOOLS = (TOOL,)`.
- `ToolSpec`: имя `scene_ops`, `effects="write"`, `idempotent=False`, `requires_preview=True`
  (вход без `plan_digest` — это `preview`), ошибки `unknown_operation`, `revision_mismatch`,
  `stale_plan`, `engine_down`, `no_bridge`, `limit_exceeded`.
- Домен (`domain/core.py`, без IO): нормализация батча (порядок, дедуп узлов, лимиты
  `MAX_OPERATIONS=64`, `MAX_VALUE_BYTES=4096`), вычисление `plan_digest`, разбор ответа
  через `kernel.schema.validate` по `result_schema` (как в части A: `bad_result` с путём
  поля), маппинг причин в `AppError` (`conflict`, `invalid_input`, `unavailable`).
- `app.py` ≤ 80 строк: `preview` → `editor_scene_plan`, `apply` → `editor_scene_apply`;
  моста нет → `unavailable/no_bridge` (не падение).
- `contract/capabilities/editing.scene_ops.json` генерируется `gen_contract --write`
  (артефактов станет **9**); руками не править.

**Bump `verbs_version: 1 → 2` — это шесть зашитых единиц, а не одна в JSON** (проверено
аудитом 2026-10-28); забыть любую — значит получить `verbs_mismatch` и красный
`selfcheck context.editor_context` (то есть «сломал часть A»):

| Место | Что там |
|---|---|
| `contract/editor_verbs.json` | `verbs_version` (источник правды) |
| `editor/bridge/server/session.gd:12` | `const VERBS_VERSION := 1` (сверка handshake, `:84`) |
| `editor/bridge/verbs/editors/editor_verbs.gd:10` | второй `const VERBS_VERSION := 1` (ответ `editor_ping`) |
| `editor/bridge/server/socket_server.gd:67` | литерал `"verbs_version": 1` в `port.json` |
| `tests/py/integration/fake_editor.py:21` и `:44` | `PING` и дефолт `verbs_version=1` |
| `tests/py/integration/test_editor_context_bridge.py:62` | ожидание `ping["verbs_version"]` |
| `python/modules/context/editor_context/tests/test_core.py:13` | своя копия `PING` (R-11: модуль не импортирует `substrate`) — поправить тем же движением, иначе тест доказывает ответ несуществующей версии |

`protocol` (1) — **другая** константа, её не трогать.

## 4. Что взять у эталона (только чтение; `python -B`, `PYTHONDONTWRITEBYTECODE=1`)

Пути от `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\`.

| Файл:строка | Что берём |
|---|---|
| `agent_scene_executor.gd:38 prepare`, `:56 execute`, `:125 _write_scene`, `:141 _commit_live_scene_undo` | порядок «проверить → открыть сцену → применить пачку → один undo → сохранить» |
| `:175 _scene_reload_would_lose_edits`, `:153 reload_after_recovery` | что считать опасным для `dirty`-сцены (в B — только предупреждение) |
| `:201 _open_target`, `:224 _create_detached`, `:243 _stage_new_scene`, `:267 _load_detached` | как эталон обходится с detached-сценой; в B — **не переносить**, читать как «почему нельзя писать в закрытую сцену» |
| `:277 _apply_operations`, `:294 _apply_operation`, `:309 _node`, `:315 _is_local` | имена и границы операций; `_node`/`_is_local` — источник правил «чужой узел не трогать» |
| `:319 _add_node`, `:339 _set_node_property`, `:367 _attach_script`, `:384 _connect_signal` | ровно четыре операции среза; поля и валидация каждого |
| `agent_mutation_gate.gd:91 classify`, `:109 kind_name`, `:120 is_bulk`, `:129 write_scene`, `:167 begin_undo`, `:187 commit_undo`, `:199 abort_undo`, `:206 undo_pending` | гейт записи и единственный undo на батч; `is_bulk` — почему запись сцены не «мелкая правка» |

Из части A переиспользуй: `substrate/editor/{client,session,retry,framing,verbs_catalog}.py`
(новых классов не плодить — только методы/ветки, если нужен новый verb),
`editor/bridge/dispatch/{dispatcher,router,main_thread_queue}.gd`,
`editor/harness/validate.gd`.

## 5. Чем доказывается B (живого Godot нет — значит фейк и схемы)

1. Фейк `tests/py/integration/fake_editor.py` расширяется **сценариями записи**: принимает
   `editor_scene_plan`/`editor_scene_apply`, умеет: отдать `revision_mismatch`, отдать
   `plan_digest` несовпадающий, упасть на второй операции (→ `abort_undo`), потерять кадр
   после `apply` (→ `truncated`, undo не «начат»), прислать `applied` без `receipts`.
2. Тесты контракта: `input_schema`/`result_schema` обоих примитивов проходят
   `validate` на фикстурах ответов; `gen_contract --check` зелёный с `verbs_version: 2`.
   **Маркеры считать регексом `gen_contract` (`^\s*#\s*verb:\s*([a-z_]+)\s*$`,
   `tools/gen_contract.py:44`): было 3 — станет 5.** Обычный поиск строки `# verb:`
   даёт 8 (в `editor/` 6 вхождений: 3 маркера + 3 упоминания в комментариях и
   `const VERBS_MARKER`) — это не провал.
3. Домен: нормализация (порядок значим, `MAX_OPERATIONS`), `plan_digest` стабилен на
   перестановке ключей и меняется при перестановке операций; `bad_result` с путём поля;
   `unknown_operation` отказывает весь батч.
4. Модуль: `selfcheck editing.scene_ops` → `ok`; `provides_tools=("scene_ops",)`;
   capability-артефакт сгенерирован; `effects="write"` виден в `context.tools`.
5. Мутации (на сдаваемом файле, по R-22): снять сверку `expected_revision` → красный
   тест `revision_mismatch`; снять сверку `plan_digest` → красный `stale_plan`;
   снять `abort_undo` на исключении → красный тест «после сбоя сцена не изменилась».
6. Живой прогон в редакторе — отдельным долгом `needs_live` (записать в лист и PROGRESS),
   приёмкой не считается; GDScript не компилировался — это ограничение, а не «ок».

## 6. Стоп-условия

- Никакой записи из Python: `ResourceSaver`, `PackedScene`, `Node` — только GDScript.
- Не менять `tools/*`, `python/kernel/schema.py`, `python/protocol/{validation,registry,
  dispatch,schema_gen,error_map}.py`, корпуса и принятые механики
  (`write_preview`/`write_apply`/`rollback`/`context.*`). Фикстуры тестов инструмента
  (`tests/py/tools/test_gen_contract.py:50`, `test_gen_contract_types.py:46`) содержат
  свой `"verbs_version": 1` — это их собственные JSON-фикстуры: **проверить прогоном**,
  что они зелёные, и не править ни тесты инструментов без нужды.
- Один undo на батч, без «по одной операции — по одному undo».
- Не открывать второй сокет, не тащить HTTP/`requests`, адрес только `127.0.0.1`.
- Старый плагин — только чтение; два чужих лога (`python/_ref2.log`,
  `python/godot_tools/_excl.log`) не твои, не удалять; свои дампы — в `%TEMP%`.
- Не выдавать `needs_live` за приёмку и не ставить шапку «выполнено» — её ставит аудитор.

## 7. Что проверит аудитор (своими прогонами, не по отчёту)

| Что | Как |
|---|---|
| срез собран | `selfcheck editing.scene_ops` → `ok`, exit 0; `context.editor_context`/`context.gather` не сломаны (unit 27/33) |
| регресс | `pytest` = `--collect-only`; корпус 102/0; `gen_contract` ok, **9** артефактов, `verbs_version: 2`; маркеров по регексу `gen_contract` **5** (грепом `# verb:` будет 8 — не считать провалом) |
| валидатор | репро union `[]`, не-строковый `type` → проблема (фазы 0 и 0.5 не сломаны) |
| undo-инвариант | своим сценарием фейка: сбой на второй операции → сцена не изменилась, `abort_undo` вызван один раз |
| блокировка | подмена `expected_revision` в фейке → `conflict/revision_mismatch`; чужой `plan_digest` → `stale_plan` |
| подложенный файл | `# verb: editor_scene_extra` → `--check` fail «обработчик вне словаря»; `"type": "date"` в новом `result_schema` → fail с путём поля |
| границы | `lint_arch` 453/0 (в `domain/scene_ops` нет IO), `security_audit` ok, `__pycache__` 0, старый плагин — те же две `??` |
| доказательства | по R-22: мутации со сданного файла, `sha256` до/после, EOL сохранены, числа из вывода команд |

## 8. Финальный прогон и записи

```
python -B -m pytest python/modules tests/py       # N passed, N == --collect-only
python -m pytest python/modules tests/py --collect-only
python tools/snapshot_diff.py
python tools/gen_contract.py --check
python tools/selfcheck.py editing.scene_ops
python tools/selfcheck.py context.editor_context
python tools/security_audit.py --json
python tools/lint_arch.py; python tools/check_limits.py
```

Записи после работы: лист `docs/porting/editing.scene_ops.md` (создать **до** кода, по
`_template.md`: цель, старый код `agent_scene_executor.gd`/`agent_mutation_gate.gd`,
корпус «нет — фейк», решения §2, ход, проверки, следующее, блокеры), `docs/PROGRESS.md`
(этап и следующее действие), `docs/parity.md`, `docs/tests-map.md` (строка эталона —
`replaced`, судьба нового теста — приложением, старые строки не удалять),
`docs/adr/0007-most-redaktora.md` (§«Версия словаря», `verbs_version: 2`),
`docs/WORKLOG.md` (сессия). `_audit-handoff.md` и `_start-prompt.*` правит аудитор.

