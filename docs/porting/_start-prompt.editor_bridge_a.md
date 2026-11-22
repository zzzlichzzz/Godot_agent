# Задача: восьмой срез — мост редактора, часть A (исполнение контракта)

> **Выполнено, аудит принял 2026-10-28.** Свои прогоны: 417 тестов = `--collect-only`
> (39 файлов), корпус 102/0, 8 артефактов без строки долга, `selfcheck
> context.editor_context` ok (unit 27), 453/0, `__pycache__` 0, 896 файлов,
> `editor_verbs.json` `F73AB2D8…B1E4`. Проверено аудитором: мутация сверки схемы
> краснит домен, подложенный `# verb: editor_extra` валит `--check`, публичный адрес
> валит `security_audit`; GDScript не компилировался — `needs_live`, приёмкой не
> считается. Промпт оставлен как образец для части B.

**Ревизия 3, 2026-10-28, после приёмки фазы 0.5.** Что изменилось против ревизии 2:
базовая линия поднята до **382** тестов, **891** файла, `lint_arch.py` **224** строки
(`1FAD8E74…8C40`); пункты §0.3 **A1 и A2 закрыты** (правило «в `domain/` нет IO» и
сужение `_same_feature` уже в инструменте, страж — `tests/py/tools/test_lint_arch_guard.py`,
5 кейсов) — в этом срезе `tools/` не трогать; §0.1 дополнен тем, что появилось в фазе 0.5.
Ревизия 2 (2026-10-27, после фазы 1): базовая линия 377/102/8/453, §0.2 «Замечания фазы 1»,
снят пункт про фазу 0, учтено, что `context.gather` собран и реестр умеет вклады.

Ты в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`. Контракт части A зафиксирован
и принят (ADR-0007, `contract/editor_verbs.json`, SEC-03, лист
`docs/porting/context.editor_context.md`). Задача среза — **исполнить** контракт:
транспорт, GDScript-сервер, модуль-вклад, фейк. В сцену ничего не пишется.

## 0. Факты на старте (проверено 2026-10-27 после фазы 1; не перепроверяй «по памяти»)

```powershell
cd D:\vajno\Godot\agent-rebuild\addons\godot_agent
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONIOENCODING='utf-8'
python -B -m pytest python/modules tests/py             # 382 passed (== --collect-only, 34 файла)
python -B tools/snapshot_diff.py                        # кейсов 102, 0 расхождений
python -B tools/gen_contract.py --check                 # артефактов 8, «мост: 0 обработчиков из 3, ожидаются»
python -B tools/security_audit.py --json                # нарушений нет
python -B tools/lint_arch.py; python -B tools/check_limits.py   # файлов 453, 0 / 0
```

Файлов в плагине — **891**, `__pycache__`/`.pytest_cache` — 0. `tools/lint_arch.py` —
224 строки, sha256 `1FAD8E74…8C40`; `tools/gen_contract.py` и `tools/selfcheck.py` —
не трогать (их правки идут отдельными фазами).

| Механика | `selfcheck` | unit | корпус |
|---|---|---|---|
| `project_text.search` | ok | 29 | 16 |
| `code_intel.functions` | ok | 33 | 17 |
| `code_intel.usages` | ok | 66 | 31 |
| `editing.write_preview` | ok | 45 | 16 |
| `editing.write_apply` | ok | 44 | 15 |
| `editing.rollback` | ok | 24 | 4 |
| `context.gather` | ok | 33 | 3 |
| `editing.symbol_rename` | ok | 15 | «корпуса нет: вклад …» (норма) |
| `context.editor_context` | **blocked**, exit 2 (`module not_implemented: нет MODULE (R-05)`) | — | корпуса нет намеренно |

`python/kernel/schema.py` — 147 строк, sha256 `629FCE54…4067`; union-типы, fail closed на
неизвестном типе и тотальность покрыты тестами и мутациями (фаза 0 принята).

## 0.1 Что уже готово — не переделывать

- `context.gather` — владелец инструмента `context`: `python/modules/context/gather/{module,tools,app,ports}.py`
  + `domain/core.py` (13 тестов), корпус `fixtures/corpus/context/gather/` (3 кейса),
  артефакт `contract/capabilities/context.json`.
- `python/modules/context/shared/context_section.py` — интерфейс вклада:
  `ContextSection(name, collect, cost="light")`, `fragment(target)`, `unavailable(reason)`,
  `is_unavailable`/`reason_of`, `NAME_RE`, `COSTS`.
- Реестр вкладов: `Registry.add_module(module, tools, handlers, contributions=())`,
  `Registry.contributions(tool_name)`, `LoadedModule.contributions` (из `tools.CONTRIBUTIONS`),
  `ModuleContext.registry`.
- `python/modules/editing/shared/operation_compiler.py` + модуль-вклад `editing.symbol_rename`
  (образец манифеста без `provides_tools`: `environment`/`contributes_to`/`internal_services`,
  `entrypoints` без `"call"`).
- `tools/lint_arch.py`: (1) `shared` внутри своей области разрешён (дефект `_same_feature`
  исправлен), (2) **новое с фазы 0.5** — правило «в `python/modules/*/*/domain/**` нет
  IO-импортов» и запрет импорта корня чужой области. Страж:
  `tests/py/tools/test_lint_arch_shared.py` + `tests/py/tools/test_lint_arch_guard.py`
  (5 кейсов). Не «чинить» обратно и не расширять правило на `kernel/**`
  (`kernel/paths.py:12 import os`, `kernel/write_plan.py:12 import json` законны).
- `tools/gen_contract.py`: сверка обработчиков условная (`missing` и `extra` обе в
  `problems`), долг печатается в `detail`, гейт `unknown_schema_types` по `verbs[]` и
  `capabilities/*.json`.

## 0.2 Замечания фазы 1, которые нельзя обойти

Это не просьбы, а следствия уже принятых решений. Каждое проверяется командой, а не
глазами.

1. **`_handlers` обязан исчезнуть в этом срезе.** В `contract/editor_verbs.json` стоит
   `"_handlers": "pending-editor-bridge"`. Первый же `# verb:` включает сверку в обе
   стороны сам, и живой `_handlers` при маркерах — это `fail` «снимите `_handlers`:
   обработчики уже есть». Удалять ровно в том изменении, где появляется первый маркер;
   иначе `--check` красный и приёмки нет.
2. **Сверка идёт в обе стороны.** Забытый маркер → `missing: editor_state`; обработчик
   вне словаря → `extra`. Прятать обработчик под другим именем, чем в словаре, нельзя.
3. **Ответ моста валидируется схемой, и это не «улучшение».** `validate(result,
   verb["result_schema"])` на всех трёх примитивах; проблема → ошибка с путём поля
   (`active_scene`, `open_scenes[0].revision`), а не частичный снимок. Именно ради этого
   чинили union: `None` в четырёх nullable-полях — самый частый ответ (нет выделения).
4. **Nullable в контракте не переписывать.** `["string","null"]` остаётся в
   `active_scene`/`node_path`/`scene`/`script`; переименование поля — только с бампом
   `verbs_version` + запись в ADR-0007 (`_change_policy` и §«Версия словаря» — один текст).
5. **Секция `editor` уже известна `context.gather`** (`RESERVED_SECTIONS`), поэтому
   контракт `sections` менять не нужно. В headless вклад не регистрируется
   (`environment="editor"` + строка 119 `_register`), и `context` отвечает
   `unavailable: [{name: "editor", reason: "no_module"}]` — это норма, а не ошибка.
   В профиле `editor` при живом мосте секция собирается; мост молчит → `no_bridge`.
6. **Порт `editor` объявляется до проверки профиля.** `_register` сначала смотрит
   `requires_ports` и только потом `environment`. Если порт `editor` есть не во всех
   профилях, headless получит ложную причину «нет портов: editor» вместо «нужен профиль
   editor». Решение среза: порт `editor` присутствует в `default_ports` **всех** профилей
   как ленивый клиент (не соединяется, пока его не позовут), и отключение в headless идёт
   по `environment`.
7. **Инвентарь headless-профиля не растёт.** Вклад не создаёт инструмента, поэтому пины
   `tests/py/contract/test_functions_contract.py` и `test_usages_contract.py` (точный
   список имён) остаются как есть. Если пришлось их править — срез протёк
   (`provides_tools` у вклада), откати и разберись.
8. **`selfcheck` вклада печатает в `corpus` строку «корпуса нет: вклад …»** — это `ok`,
   а не долг. Корпус `fixtures/corpus/context/editor_context` не создавать: `uptime` и
   абсолютные пути недетерминированы; доказательство — сценарии фейка (§5).
9. **Числа базовой линии сдвинулись** (см. §0): 377 тестов, 102 кейса, 8 артефактов,
   453 файла. Любой отчёт с «320/99/7/450» — из прошлого среза, его не принимают.
10. **`python/dist/**` — посторонние бандлы**; не трогать и не пытаться «починить»
    лимиты по ним. Лимиты и `security_audit` смотрят только `python/`, `editor/`, `runtime/`.

## 0.3. Замечания аудита приёмки фазы 1 (новые, 2026-10-27)

Проверка сделана своими прогонами: 377 passed = `--collect-only`, корпус 102/0,
`gen_contract` ok (8 артефактов), `selfcheck context.gather` ok (33/3), `selfcheck
editing.symbol_rename` ok (15, «корпуса нет»), `security_audit`/`lint_arch`/
`check_limits` ok, `__pycache__` 0, `stray` 0, `probe context` на копии проекта
отдаёт `project`+`tools` и `editor: no_module`, файлы после вызова не меняются.
Хеши сданных файлов совпали с отчётом (`app.py 044ACB62…`, `core.py F08F2D4B…`,
`lint_arch CF76D816…`, `snapshot_diff 31EB5454…`). Проекция `project_context` узкая:
подложенный `res://other.godot` в корпусе 001 поймана с точным путём.

| # | Замечание | Что сделать в этом срезе |
|---|---|---|
| A1 — **закрыто 2026-10-28, не делать** | правило «в `domain/` нет IO»: `tools/lint_arch.py` (`1FAD8E74…8C40`, 224 строки) падает на подложенном `import os` (`….py:125: в domain/ запрещён IO-импорт os`, exit 1), мутация правила краснит `test_domain_io_import_is_a_violation`; `import os` в `app.py` законен | **не трогать `tools/`** в этом срезе: `lint_arch` здесь только замок |
| A2 — **закрыто 2026-10-28, не делать** | лазейка коротких имён в `_same_feature`: `len < 4 → True` убрана, `from python.modules import scene_model` из `domain/` даёт `модуль импортирует чужой модуль python.modules` (exit 1), мутация краснит `test_foreign_module_root_in_domain_is_a_violation`, импорт `<область>/shared` по-прежнему разрешён | **не трогать `tools/`** в этом срезе |
| A3 | Число файлов: в отчёте 888, у аудита 889 (мои прогоны `selfcheck` переписывают `reports/selfcheck/*.json`, но новых файлов не создают). Расхождение на 1 не объяснено | В финальном прогоне печатать `files=` и **список новых файлов** (полные пути), чтобы число сверялось построчно |
| A4 | Смешанные EOL в правленом `python/runtime/context.py` (lf=50, crlf=46) | Не пересохранять целиком: править байтовым патчем и сохранять исходный EOL каждой строки; в отчёте — `lf`/`crlf` до и после |

**Уточнение аудита (тот же день, до исполнения):** требование A1 «и `kernel/**`» —
ошибка аудитора. Покрывается только `python/modules/*/*/domain/**`; в `kernel/`
IO встречается законно (`kernel/paths.py:12 import os`, `kernel/write_plan.py:12
import json`), и правило там дало бы ложные нарушения. Правило и тесты — ровно по
`modules/**/domain/**`.

A1 и A2 — правки **инструмента проверки**, а не механик: поведение агента не меняется,
но без них заявление «R-11 проходит машинно» неверно, а следующая часть A (мост,
много новых файлов) останется без этой стражи.

## 1. Границы среза

| В срезе (A) | Не в срезе |
|---|---|
| `substrate/editor/` (кадр, handshake, таймауты, переподключение, каталог verb'ов) | `ResourceSaver`, `scene_apply_batch`, undo, `expected_revision` (это B) |
| `editor/` GDScript-сервер + 3 обработчика с `# verb:` + токен + `port.json` | разбор `.tscn`/`.gd` в GDScript (R-14) |
| модуль-вклад `context.editor_context` (`contributes_to=["context"]`, без `provides_tools`) | `editing.scene_ops`/`resource_ops` (B/C) |
| ответ моста, проверенный `kernel.schema.validate` по `result_schema` | HTTP/Flask/`requests`, второй слушающий сокет |
| `tests/py/integration/fake_editor.py` + сценарии протокола | корпус `fixtures/corpus/context/editor_context` (его нет намеренно) |

**Заготовки уже лежат** (по 2–5 строк, `# TODO`, `extends`): `python/substrate/editor/{client,framing,retry,session,verbs_catalog}.py`;
`editor/bridge/server/{socket_server,session,framing,endpoints,debugger_session}.gd`;
`editor/bridge/dispatch/{dispatcher,router,main_thread_queue,error_codes}.gd`;
`editor/bridge/verbs/editors/{editor_verbs,context_snapshot}.gd`;
`editor/harness/validate.gd`. Это скелет раскладки — наполняй его, новых каталогов не
## 2. Раскладка и минимальные контракты

Python (слой `substrate`, без импорта `python.modules.*`):

| Файл | Минимум | Запрет |
|---|---|---|
| `substrate/editor/framing.py` | `encode(obj) -> bytes`, `decode(buffer) -> (obj, rest)`; 4 байта BE, лимит `MAX_FRAME = 1048576`; частичный кадр = «данных мало», а не ошибка | без сокета, без JSON-схем |
| `substrate/editor/verbs_catalog.py` | чтение `contract/editor_verbs.json`, `verbs()`, `result_schema(name)`, `version`; сверка `verbs_version` сервера с контрактом | без сети |
| `substrate/editor/session.py` | состояние соединения: handshake, токен, `protocol`, `project_hash`, `in_flight` | без политики повторов |
| `substrate/editor/retry.py` | сколько и как ждать: `connect_failed`, `timeout`, переподключение | без знания примитивов |
| `substrate/editor/client.py` | фасад: `call(verb, args) -> dict`, `close()`; ошибки — `AppError("engine_down", details={"reason": ...})` | без логики снимка |

GDScript (`editor/`, только примитивы и транспорт, R-14):

| Файл | Минимум |
|---|---|
| `bridge/server/socket_server.gd` | `TCPServer` на `127.0.0.1`, случайный порт, запись `user://godot_agent/port.json` (`port`, `token`, `pid`, `protocol`, `verbs_version`), закрытие при `_exit_tree` |
| `bridge/server/framing.gd` | то же кадрирование, что в Python (4 байта BE, лимит 1 МиБ) |
| `bridge/server/session.gd` | handshake первым кадром, проверка токена **в каждом** кадре, один in-flight |
| `bridge/server/endpoints.gd` | `editor_ping`, `editor_state`, `editor_selection` → `# verb: <name>` + делегирование в dispatch; в ответе `{"ok": true, "result": …}` либо `{"ok": false, "error": {kind, reason, message}}` |
| `bridge/dispatch/{dispatcher,router,main_thread_queue}.gd` | разбор кадра, вызов обработчика в главном потоке (`call_deferred`), ответ в тот же сокет |
| `bridge/dispatch/error_codes.gd` | имена причин: `bad_token`, `unknown_verb`, `frame_too_big`, `truncated`, `timeout`, `wrong_project`, `verbs_mismatch` |
| `bridge/verbs/editors/{editor_verbs,context_snapshot}.gd` | снимок: `get_open_scenes()`, `revision`, `dirty`, `active`, `unsaved_changes`, выделение, `script`; имена полей — как в `result_schema`, не как в эталоне |

Модуль-вклад `python/modules/context/editor_context/` (заготовки уже лежат):

- `module.py` — `ModuleSpec(id="context.editor_context", environment="editor",
  provides_tools=(), contributes_to=("context",), internal_services=("editor_bridge",),
  requires_ports=("editor",), capabilities=("context.editor_context",), entrypoints={})`.
  `entrypoints["call"]` не нужен: `_register` разрешает его отсутствие при непустом
  `contributes_to`.
- `tools.py` — `TOOLS = ()`, `CONTRIBUTIONS = (SECTION,)`.
- `domain/core.py` — сборка фрагмента из ответов моста и `result_schema`-валидация
  (без IO); `app.py` — оркестрация через `ctx.port("editor")` (≤ 80 строк);
  фрагмент: `{available, reason, open_scenes, selection}`.

## 3. Шаги (порядок не переставлять)

1. **M0** — прочитать §0, прогнать базовую линию, зафиксировать числа в отчёт. Расхождение
   с §0 — стоп: сначала разберись, потом код.
2. **M1** — лист `docs/porting/context.editor_context.md`: статус → этап 5, «Ход работы» —
   первая запись ДО кода (R-07).
3. **M2** — `framing.py` + unit: длина, частичный кадр, `frame_too_big`, пустой кадр,
   мусор в JSON.
4. **M3** — `verbs_catalog.py`, `session.py`, `retry.py`, `client.py` + unit с фейком:
   handshake, чужой `verbs_version` → `engine_down/verbs_mismatch`, чужой `project_hash` →
   `wrong_project`, молчание → `timeout`, обрыв посреди кадра → `truncated`,
   `connect_failed`, один in-flight, переподключение после обрыва.
5. **M4** — GDScript-сервер и три обработчика с маркерами `# verb:` (+ `error_codes`).
   **В этом же изменении** снять `"_handlers": "pending-editor-bridge"` из
   `contract/editor_verbs.json` и прогнать `gen_contract --check` (ожидается
   «артефактов 8, расхождений нет», без строки долга).
6. **M5** — модуль-вклад: манифест, `CONTRIBUTIONS`, `domain/core.py`, `app.py`,
   порт `editor` в `default_ports` (ленивый клиент, все профили — см. §0.2 п. 6).
   `context.gather` не менять: вклад подхватится через `ctx.registry.contributions("context")`.
7. **M6** — `tests/py/integration/fake_editor.py` и сценарии §5.
8. **M7** — валидация ответа по `result_schema` на всех трёх примитивах, включая nullable
   (`None` → `[]`, `5` → проблема с путём поля) и вложенность (`open_scenes[0].revision`).
9. **M8** — тесты модуля (`tests/test_core.py`), контракт вклада (манифест без
   `provides_tools`, `CONTRIBUTIONS`, отсутствие своего `ToolSpec`), `selfcheck
   context.editor_context` → `ok`, exit 0.
10. **M9** — записи (§8) и финальный прогон.

## 4. Решения, которые обязан принять портер (и записать в лист)

1. **Таймауты.** `connect` (по умолчанию ≤ 2 с), handshake (≤ 2 с), ответ на примитив
   (≤ 5 с, снимок состояния дороже ping). Значения — константами в `retry.py`, не
   «магическими числами» по коду.
2. **Повторы.** Переподключение только на `connect_failed`/`truncated`; `timeout` — один
   повтор, дальше `engine_down`. `bad_token` и `verbs_mismatch` не повторяются никогда.
3. **Токен.** `secrets.token_hex(16)` в GDScript (`Crypto.generate_random_bytes`), пишется
   в `port.json`; в логах — никогда (SEC-13). Кадр без токена → отказ **и** закрытие
   соединения (не «продолжаем без проверки»).
4. **Один in-flight.** Очередь в Python; сервер второй кадр не ждёт и не буферизует.
5. **Кэш `port.json`.** Читается при каждом `call`, если соединения нет; устаревший
   порт → `connect_failed`, а не «вечное переподключение».
6. **`verbs_version`.** Сверяется в handshake (`server.hello.verbs_version` против
   `contract/editor_verbs.json`); расхождение → `engine_down` с `reason="verbs_mismatch"`.
   Каталог (`verbs_catalog.py`) — единственное место, где читается JSON.
7. **Валидация ответа.** В `domain/core.py` вклада, а не в `client.py`: транспорт не знает
   схем. Проблема → `AppError("engine_down", details={"reason": "bad_result", "problems": […]})`.
8. **Профиль.** Вклад живёт только в профиле `editor`; в `headless`/`cli`/`test` — отключён
   по `environment` с причиной «нужен профиль editor», `context` при этом зелёный.
9. **Что считается «мост недоступен».** `available=false` с `reason` из списка
   `no_bridge`/`engine_down`/`wrong_project`/`verbs_mismatch`. Отсутствие файла `port.json` —
   это `no_bridge`, а не ошибка инструмента.

## 5. Сценарии фейка и тесты (без них срез не принимается)

`tests/py/integration/fake_editor.py` (обычный сокет-сервер на Python, тот же кадр):
умеет молчать, рвать кадр на середине, присылать чужой `verbs_version`, чужой
`project_hash`, отвечать дважды, отвечать не на тот запрос, присылать кадр больше лимита,
присылать кадр без токена, отвечать мусором по схеме, отдавать корректный снимок.

Обязательные проверки:

1. handshake ok → `editor_ping` отдаёт `godot`, `verbs_version`, `protocol`,
   `open_scenes`, `uptime_s`; `validate(result, result_schema)` → `[]`.
2. `verbs_mismatch` и `wrong_project` → `engine_down` с точной причиной в `details`.
3. `truncated` (обрыв посреди кадра), `frame_too_big`, `timeout`, `connect_failed`
   без `port.json`, устаревший порт.
4. Один in-flight: второй вызов ждёт, а не теряется и не ломает первый.
5. Переподключение после обрыва: следующий `call` проходит без перезапуска.
6. Кадр без токена → отказ **и** закрытие соединения.
7. Валидация: `revision: "3"` внутри `open_scenes[0]` → проблема с путём `[0].revision`;
   `None` в `active_scene`/`node_path`/`scene`/`script` → `[]`; `5` на месте `node_path` →
   проблема.
8. Вклад: `context` в профиле `editor` с фейком → `available: true`, `open_scenes` на
   месте; без фейка → `available: false`, `reason: "no_bridge"`; в `headless` → секция
   отсутствует, `unavailable: [{name: "editor", reason: "no_module"}]`.
9. `substrate/editor` unit: длина кадра, частичный кадр, лимит, порядок handshake,
   таймаут, мусор в JSON, `encode(decode(x)) == x` для снимка.
10. Контракт вклада: нет своего `ToolSpec`/`contract/capabilities/editor_context.json`;
    `TOOLS == ()`, `CONTRIBUTIONS == (SECTION,)`; инвентарь инструментов не изменился.
11. `gen_contract --check`: три обработчика ↔ три примитива, `_handlers` снят, `detail` без
    строки долга.

## 6. Что взять у эталона (только чтение: `python -B`, `PYTHONDONTWRITEBYTECODE=1`)

Пути от `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\`. Там два чужих
лога от прошлых сессий (`python/_ref2.log`, `python/godot_tools/_excl.log`) — не удалять,
новых дампов не создавать, временные файлы — в `%TEMP%`.

| Файл:строка | Что берём |
|---|---|
| `agent_server.gd:24` (`HOST := "127.0.0.1:5000"`), `:165 url`, `:183 project_token`, `:209 existing_token`, `:239 save_server_pid` | адресация и токен; HTTP+Flask **не берём** |
| `agent_server_link.gd:80 _queue`, `:87 _retry_after_server`, `:112`/`:119` таймауты (180 с / 5 с), `:165 is_inflight` | очередь, ожидания, ретраи, «редактор не отвечает» |
| `agent_editor_context.gd:27 capture`, `:47 get_open_scenes()`, `:58 _capture_selection`, `:92 _capture_properties`, `:104 _capture_script`, `:133` (`dirty`), `:161 _node_path`, `:171 _json_safe`, `:182 _limit_text` | состав снимка и пределы; имена полей — как в `result_schema`, не как в эталоне |
| `agent_scene_executor.gd`, `agent_mutation_gate.gd` | **не переносить** — читать как «что будет в B» |
| `godot_tools/godot_headless_validation.py` + его тесты | приём харнесса: один прогон, `result.json` как вердикт |
| `tests/test_editor_context.py` | кейсы снимка; судьба строки в `docs/tests-map.md` — `replaced` |

## 7. Стоп-условия

- Не писать в сцену, не вызывать `ResourceSaver`, не делать undo/`expected_revision`.
- Не тащить HTTP/Flask/`requests`; не поднимать второй слушающий сокет.
- Никакой логики разбора `.gd`/`.tscn` в GDScript — только примитивы и UI (R-14).
- Не менять `contract/editor_verbs.json` по существу: снимается **только** `_handlers`;
  nullable и схемы остаются. Новый примитив/переименование поля — стоп (это +`verbs_version`
  и запись в ADR, отдельным решением).
- Не трогать корпуса и конвейер записи (`fixtures/corpus/**` кроме чтения,
  `editing/*`, `kernel/*`, `substrate/store`).
- Не менять `context.gather`, `context/shared/context_section.py`,
  `editing/shared/operation_compiler.py` по существу — только использовать.
- Не выдавать `needs_live` за приёмку; не помечать `ported` без `selfcheck` и прогона фейка.
- Не «улучшать» тексты проблем валидатора: они попадают в `invalid_input`.

## 8. Финальный прогон и записи

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONIOENCODING='utf-8'
python -B -m pytest python/modules tests/py -q               # exit 0
python -B -m pytest python/modules tests/py --collect-only -q # то же число
python -B tools/snapshot_diff.py                            # 102 кейса, 0 расхождений
python -B tools/gen_contract.py --check                     # артефактов 8, без строки долга
python -B tools/selfcheck.py context.editor_context         # ok, exit 0
python -B tools/selfcheck.py context.gather                 # ok (33/3)
python -B tools/selfcheck.py editing.write_apply            # ok (44/15)
python -B tools/security_audit.py --json; python -B tools/lint_arch.py; python -B tools/check_limits.py
# счётчики: __pycache__, .pytest_cache, *.bak/*.tmp/*.orig, число файлов, новые файлы списком
```

Записи: лист `docs/porting/context.editor_context.md` (статус → этап 7, решения из §4,
сценарии §5, «Следующее действие» на часть B), `docs/PROGRESS.md` (этап 7 и следующее
действие), `docs/parity.md` (`context.editor_context` → `ported`), `docs/WORKLOG.md`
(сессия с выводом), `docs/tests-map.md` (примечания без удаления строк),
`docs/adr/0007-most-redaktora.md` (только если решение уточнилось — с бампом `verbs_version`
и одинаковым текстом в `_change_policy`), `contract/editor_verbs.json` (снятый `_handlers`).
Шапку «выполнено» в этот промпт не ставить — её ставит аудитор.

## 9. Что проверит аудитор (своими прогонами, не по отчёту)

| Что | Как |
|---|---|
| срез собран | `selfcheck context.editor_context` → `ok`, exit 0; `selfcheck context.gather` → `ok` |
| регресс | тесты (число = `--collect-only`), корпус 102/0, три `selfcheck` записи `ok` |
| валидатор не сломан | репро `None`→`[]`, `5`→проблема; мутация ветки union валит тесты |
| протокол | свои прогоны фейка: частичный кадр, чужой `verbs_version`, двойной ответ, кадр без токена |
| мутации | убрать проверку токена → тест краснеет; убрать сверку `verbs_version` → краснеет; убрать `validate(result, schema)` → краснеет; снять `# verb:` → `--check` даёт `missing`; оставить `_handlers` при маркерах → `fail` «снимите `_handlers`»; файл возвращается побайтово (sha256 до/после) |
| границы | `app.py` ≤ 80, `tools.py` ≤ 150, в `domain/` нет IO, один экземпляр логики |
| гигиена | `__pycache__` = 0, `.pytest_cache` нет, старый плагин: новых файлов нет |
| живой Godot | `needs_live`-прогон с версией движка — отдельно от приёмки |

## 10. Как доказывать (за это возвращали два среза)

1. Числа в отчёте — только из приложенного вывода; итог pytest обязан совпасть с суммой по
   файлам из `--collect-only`.
2. Мутации — только на сдаваемом файле; бэкап `shutil.copyfile` (байты), в отчёте sha256
   до/после и **полный список** красных тестов, а не «упало».
3. `gen_contract`-мутация контракта: sha256 контракта до/после и дословный JSON-ответ
   `--check` в обе стороны.
4. EOL: новые файлы — LF; существующие править байтовым патчем (иначе меняется EOL и
   `sha256` не сверить). `schema.py`, листы, `WORKLOG.md`, `tests-map.md` — CRLF;
   `PROGRESS.md`, `parity.md`, `docs/porting/README.md` — LF.
5. Вывод не совпал с ожиданием — разбирайся, а не подгоняй текст.
