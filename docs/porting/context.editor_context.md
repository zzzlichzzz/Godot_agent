# context.editor_context — мост редактора, часть A (протокол и снимок)

**Статус:** этап 7 — **часть A исполнена 2026-10-28** (`selfcheck context.editor_context`
ok, unit 27; мутации R-22 сходятся). История: этап 4 — контракт зафиксирован и **принят
аудитом 2026-10-27**; блокер union в `kernel/schema` закрыт; срез исполнения —
`docs/porting/_start-prompt.editor_bridge_a.md` (ревизия 3, база 382/102/8/453).
Лист создан ДО кода, как требует R-07/PORTING.

## Цель

Дать Python-агенту снимок редактора (открытые сцены, ревизии, `dirty`,
выделение) через второй процесс — **ничего не записывая**. Владелец инструмента —
`context.gather` (ADR-0004), `editor_context` — **вклад** в составной `context`
и владелец внутреннего сервиса `editor_bridge`.

## Границы

| Часть | Что | Когда |
|---|---|---|
| **A (сейчас)** | транспорт + `editor_context` (read-only) | этот срез |
| B | `editing.scene_ops`: батч в одном undo, `expected_revision`, квитанции | после A |
| C | `.tscn`/`.tres` как файлы, линт, `formats/tscn.py` | после B |

В A запрещено: `ResourceSaver`, `scene_apply_batch`, undo, `expected_revision`.

## Транспорт (ADR-0007)

Слушает **GDScript** (`editor/`), Python — клиент. Кадр: 4 байта длины
(big-endian) + JSON UTF-8, лимит 1 МиБ. Handshake первым кадром:
`{"hello": {"protocol": 1, "verbs_version": 1, "godot": "4.6",
"project_hash": "…", "token": "…"}}`. Расхождение версии → `engine_down`
(`verbs_mismatch`), чужой проект → `engine_down` (`wrong_project`), обрыв
посреди кадра → `engine_down` (`truncated`), молчание → `engine_down` (`timeout`).
Один in-flight; очередь — в Python-клиенте. Адрес только `127.0.0.1`, порт
случайный, токен в каждом кадре, `user://godot_agent/port.json`.

## Примитивы (только чтение) и словарь

`contract/editor_verbs.json` (`schema_version: 1`, `verbs_version: 1`):

| Verb | Результат | effects | thread |
|---|---|---|---|
| `editor_ping` | `godot, verbs_version, protocol, open_scenes, uptime_s` | read | main |
| `editor_state` | `open_scenes[{path,revision,dirty,active,unsaved_changes}], active_scene, project_hash` | read | main |
| `editor_selection` | `node_path, scene, properties[{name,type,value}], script` | read | main |

Форма результата закреплена: у каждого примитива есть `result_schema` (JSON Schema,
как в `ToolSpec`). У элемента `open_scenes` обязательны `path`, `revision`, `dirty`,
`active`, `unsaved_changes` — часть B опирается на `revision` и `dirty`, а не на
«договоримся по ходу». Имена полей `result_schema.properties` сверяются со списком
`result`; переименование — только с бампом `verbs_version` (§«Инструменты проверки»).

Сверка «словарь ↔ обработчики» — маркер `# verb: <name>` в GDScript, проверка в
`tools/gen_contract.py --check`. Пока в `editor/` нет ни одного маркера, в JSON
стоит `_handlers: "pending-editor-bridge"`: пропуск разрешён, но долг печатается в
`detail` (`мост: 0 обработчиков из 3, ожидаются`). Первый же `# verb:` включает
сверку в обе стороны сам и делает `_handlers` мёртвым выключателем — его надо
снять, иначе `--check` падает («снимите `_handlers: обработчики уже есть»).

## Решения (обязательные к записи)

1. **Кто слушает** — GDScript (ADR-0007), SEC-03 переписан.
2. **`revision`** — счётчик редактора, не mtime файла; в B станет `expected_revision`.
3. **Открытая сцена** — только `EditorInterface.get_open_scenes()` (корни), не все
   загруженные `Node`; `dirty` — из `EditorInterface`, при недоступности — свой
   счётчик в редакторе.
4. **Один in-flight** — очередь в Python-клиенте; сервер второй кадр не ждёт.
5. **Перезагрузка плагина** — сокет закрывается, клиент видит `truncated`/
   `connect_failed`, следующий вызов переподключается.
6. **Логи** — verb, длительность, размер кадра, исход; без токена и без значений
   свойств (SEC-13).

## Секция `context`

`editor: {available: bool, reason: str|null, open_scenes: [...], selection: {...}|null}`.
Редактор недоступен — **не ошибка**: `available=false` с причиной моста; в
headless `context` собирается без секции `editor` (тест, а не пожелание).

## Доказательство (три уровня)

1. Фейковый редактор на Python (`tests/py/integration/fake_editor.py`): молчит,
   рвёт кадр, шлёт чужой `verbs_version`, отвечает дважды, отвечает не в тот
   запрос — проверяется **протокол**.
2. Настоящий Godot headless (`editor/harness/bridge_probe.gd`): `needs_live`, в
   отчёте версия движка. **Приёмка — pytest-прогон**, а не одиночный `-s`
   (2026-10-28, A.1.1): `python -m pytest tests/py/live -v` → `1 passed`, движок
   `4.6.3-stable`, три примитива, `harness_result.json.ok = true`. Одиночный
   `-s` без клиента даёт `ok:false / failure.reason="no_client"` (exit 1,
   подсказка про pytest) — это норма, а не провал: клиент приходит снаружи, и
   до A.1.1 та же команда врала причиной `timeout`.
   **Редакторская ветка (B.0, 2026-10-28)** — второй живой тест
   `tests/py/live/test_editor_branch_live.py`: мост поднимает сам плагин
   (`godot --headless --editor --path <проект>`), сцена открыта аргументом, тест
   видит `open_scenes == 1`, непустой `active_scene`, пустое выделение; после
   выхода редактора `port.json` удалён. `python -m pytest tests/py/live -v` →
   `2 passed`, движок `4.6.3-stable`.
3. `selfcheck`: `module` (манифест + вклад), `unit` (домен и контракт),
   `corpus` — **корпуса нет намеренно** (`uptime`/пути не детерминированы),
   вместо него схемы и сценарии фейка.

Обязательные сценарии: handshake ok / `verbs_mismatch` / `wrong_project`;
частичный кадр; `frame_too_big`; `truncated`; `timeout`; переподключение;
`available=false`; профиль без редактора → модуль `disabled`, `context` зелёный;
main-thread страж по времени `ping`; кадр без токена → отказ + закрытие.

## Инструменты проверки

Починка перед частью B (2026-10-27): инструменты перестали врать, поэтому проверки
ниже — не «посмотреть глазами», а команды с машинным вердиктом.

| Что проверяет | Команда | Что значит провал |
|---|---|---|
| словарь ↔ обработчики, схемы, версия | `python tools/gen_contract.py --check` | примитив без обработчика, обработчик вне словаря, живой `_handlers` при маркерах, `result_schema` не сходится с `result` |
| живой провод (нужен бинарь Godot) | `python -m pytest tests/py/live -v` | не `2 passed`; в `harness_result.json` не `ok:true`; одиночный `-s` без клиента пишет не `no_client`; после выхода редактора остался `port.json` |
| готовность модуля и вклада | `python tools/selfcheck.py context.editor_context` | `fail` — манифест без `provides_tools` и `contributes_to`; `not_implemented` до реализации — норма, а не долг |
| регресс корпусов | `python tools/snapshot_diff.py` | не 102/0 |

**Схемы ответов:** union-типы (`type: ["string","null"]`) поддержаны ядром и
вложенно (`items`, `properties`), неизвестный тип — отказ, а не пропуск, гейт в
`gen_contract` (`unknown_schema_types`): опечатка `"date"` валит `--check`, пока
не исправлена.

**Приёмка аудитом (2026-10-27, свои прогоны):** репро `None` против
`["string","null"]` → `[]`; `5` → одна проблема; `revision: "3"` в `open_scenes[0]` →
проблема с путём `[0].revision`; подложенный `"date"` в четырёх nullable-полях
`contract/editor_verbs.json` → `--check` fail с путём каждого поля, в
`contract/capabilities/write_preview.json` → fail `input_schema.kind`, после
восстановления `ok` и sha256 совпадает; мутация (удаление ветки union в
`_type_ok`) → 4 теста красные, `validate` не бросает, а даёт ложную проблему
(после мутации ожидание — `[]`, а не исключение); `pytest` 317 = `--collect-only`;
корпус 99/0; `selfcheck context.editor_context` → `blocked` (exit 2: модуля нет
— это заготовка, `fail` нет).

**Повторная сверка отчёта портера (2026-10-27, второй заход):** числа сошлись,
доказательство мутации — нет: на сданном файле удаление ветки union не бросает
`TypeError`, а краснит 4 теста; `TypeError` появляется только при удалении ещё и
защиты `isinstance(expected, str)`. Сама защита тестами не покрыта (её удаление
оставляет 11 кейсов зелёными, а `type`-словарь роняет `validate`) — пункт 6 §5
промпта `_start-prompt.editor_bridge_a.md` требует покрыть её мутацией.

**Тотальность (фаза 0, 2026-10-27):** покрыта тестом и проверена мутацией — мусорный
набор (`type`-словарь, `type: [{"x": 1}]`, `properties: 5`, `required: 5`) не бросает
исключений (`test_garbage_schemas_do_not_raise`), отказ на не-строковом типе закреплён
`test_non_string_type_is_refused_not_raised`, `type: null` = «тип не задан» —
`test_type_null_means_type_is_not_set`; удаление любой из трёх защит (`str`-проверка,
`properties`-dict, `required`-список) красит тест.

**При добавлении примитива: бамп `verbs_version` + запись в ADR.** Текст политики
лежит дважды и обязан совпадать: `_change_policy` в `contract/editor_verbs.json` и
§«Версия словаря» ADR-0007. Машинно проверяется только наличие `verbs_version >= 1`
(и `_change_policy` не пуст); сам бамп доказывается диффом версии в ревью.

Тесты инструментов: `tests/py/tools/test_gen_contract.py` — четыре состояния сверки
(пропуск без маркеров, `missing`, `extra`, «снимите `_handlers`») плюс схемы;
`tests/py/tools/test_selfcheck_readiness.py` — четыре состояния `module_readiness`.

## Ход работы

**Сессия 28 (2026-10-28), часть A.**

- Транспорт: `python/substrate/editor/framing.py` (кадр 4 байта BE + JSON, lim 1 МиБ,
  неполный кадр - `partial`), `session.py` (handshake, токен, protocol/verbs_version,
  `wrong_project`), `retry.py` (константы и политика), `verbs_catalog.py` (единственное место
  чтения словаря), `client.py` (фасад, один in-flight через `threading.Lock`, `port.json`
  читается при каждом `call` без живого соединения).
- Сервер: `editor/bridge/server/{socket_server,framing,session,endpoints}.gd`,
  `editor/bridge/dispatch/{dispatcher,router,main_thread_queue,error_codes}.gd`,
  `editor/bridge/verbs/editors/{editor_verbs,context_snapshot}.gd`; три маркера `# verb:`
  (`editor_ping`, `editor_state`, `editor_selection`), `user://godot_agent/port.json`
  (`port`, `token`, `pid`, `protocol`, `verbs_version`), закрытие в `_exit_tree`.
- Вклад: `python/modules/context/editor_context/**` (`TOOLS = ()`,
  `CONTRIBUTIONS = (SECTION,)`, `environment="editor"`, `requires_ports=("editor",)`),
  `app.EditorSection.bind(ctx)` зовёт композиция (`runtime/bootstrap._bind`), домен собирает
  фрагмент и валидирует каждый ответ `kernel.schema.validate` по `result_schema`.
- Порт `editor`: `default_ports` всех профилей, ленивый клиент (соединяется только при
  первом `call`), отключение вкладa - по `environment`.
- Словарь: из `contract/editor_verbs.json` снят `_handlers`; `gen_contract --check` -> ok
  (8 артефактов, строки долга нет).
- SEC-02: `tools/security_audit.py` разрешает петлевой `socket` только
  `python/substrate/editor/**` и отдельно проверяет `HOST`/`EDITOR_HOST` на `127.0.0.1`;
  правило проверяется `tests/py/security/test_bridge_network_rules.py` (мутация «`if False`
  вместо проверки адреса» краснит `test_bridge_with_public_address_is_a_violation`).

**Сессия 29 (2026-10-28), A.1 — живой прогон вместо структурной проверки.**

- Движок в среде есть: `--version` → `4.6.3.stable.official.7d41c59c4`
  (`D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`) и
  `4.6.stable.official.89cea1439` (`...\Godot v4.6\`). Значит шли по §2.1 промпта,
  `tools/gd_guard.py` не писался: структурная проверка была бы дублем живого прогона.
- Харнесс `editor/harness/bridge_probe.gd` (`extends SceneTree`) поднимает настоящий
  `socket_server.gd` (обёртка-диспетчер считает обслуженные примитивы), печатает
  `BRIDGE_PORT {port, token, result, verbs, scripts}` и пишет
  `user://godot_agent/harness_result.json`. Дополнительно грузит **каждый** `.gd` под
  `editor/` (`_scan_scripts`): компилируется весь мост, а не только файлы, которые
  тянет сервер.
- `tests/py/live/test_bridge_live.py` (маркер `needs_live`, объявлен в `pyproject.toml`):
  без бинаря — `skip`, а не «прошло». Бинарь переопределяется `GODOT_BIN`.
- Команда прогона: `godot --headless --path D:\vajno\Godot\agent-rebuild -s
  res://addons/godot_agent/editor/harness/bridge_probe.gd`.
- Результат 4.6.3 (`harness_result.json`): `ok true`, `scripts {total 72, broken []}`,
  `editor_available false`, `editor_ping {"godot":"4.6.3-stable (official)","open_scenes":0,
  "protocol":1,"uptime_s":0.173,"verbs_version":1}`, `editor_state {"active_scene":null,
  "open_scenes":[],"project_hash":"49594e3259b27c4ec4b6d51cb2aebc8a"}`, `editor_selection
  {"node_path":null,"properties":[],"scene":null,"script":null}`. Повтор на 4.6.0 —
  тот же вердикт (`"engine":"4.6-stable (official)"`).
- Три дефекта, которые живой прогон нашёл, а фейк на Python поймать не мог (все три
  исправлены в сдаваемых файлах, каждый закрыт мутацией):
  1. `editor/bridge/server/framing.gd` писал длину кадра через
     `PackedByteArray.encode_u32`, то есть **little-endian**, а `contract/editor_verbs.json`
     → `frame` требует BE: клиент читал `2298478592 > 1048576` (`frame_too_big` уже на
     handshake). Введены явные `_put_u32_be`/`_get_u32_be`.
  2. `editor/bridge/dispatch/router.gd`: `Callable` не удерживает владельца-`RefCounted`,
     поэтому `VerbsScript.new().register(router)` освобождался; вызов падал
     `SCRIPT ERROR: Attempt to call function 'null::ping (Callable)' on a null instance`,
     и клиент получал пустой `{}`. Роутер теперь держит `_owners`.
  3. `editor/bridge/verbs/editors/context_snapshot.gd`: в `-s`-режиме `EditorInterface` —
     заглушка без методов (`Invalid call. Nonexistent function 'get_current_path'`,
     `has_method` в ней тоже нет). `has_editor()` проверяет `Engine.is_editor_hint()` и
     наличие метода; `ClassDB` признаком не годится — он знает класс в обоих режимах
     (проверено `ClassDB.class_get_method_list`: 71 метод).
- Мутации (R-22, строго последовательно, бэкап `shutil.copyfile`, sha256 до/после совпал,
  каждый прогон — только `tests/py/live`): LE-заголовок в `framing.gd`
  (`D559C2E2…4FDE`) → красный живой тест, `AppError: кадр больше лимита: 2013265920`;
  `router.gd` без `_owners.append` (`2C4756D4…6D4E`) → пустой `{}` →
  `мост отказал в 'editor_ping'`; `VERBS_VERSION := 2` в `editor_verbs.gd`
  (`9CDAD7EA…6A2`) → `assert 2 == 1` (строка 122 живого теста); `uptime_s` заменён на
  `uptime_ms` → `нет обязательного поля 'uptime_s'` плюс лишнее поле. Пятая подложка
  (`has_editor()` → `if false:`) осталась **зелёной** — честный результат: headless не
  заходит в редакторскую ветку (см. «Блокеры»).
- Числа финального прогона: `pytest python/modules tests/py` → 418 passed = сумма
  `--collect-only` (40 файлов, из них `tests/py/live/test_bridge_live.py: 1`);
  `snapshot_diff` 102/0; `gen_contract --check` ok (8); `selfcheck
  context.editor_context` ok (unit 27), `context.gather` ok (33), `editing.symbol_rename`
  ok (15); `lint_arch` 453/0; `check_limits` 453/0; `security_audit` ok (9 правил);
  `__pycache__` 0, `.pytest_cache` 0, `*.bak/tmp/orig` 0, файлов 900.

**Решения (из §4 промпта, зафиксированы кодом).** Таймауты: `connect` 2 с, handshake 2 с,
ответ 5 с (`retry.py`). Повторы: `connect_failed`/`truncated` - один, `timeout` - один,
`bad_token`/`verbs_mismatch`/`wrong_project`/`frame_too_big`/`unknown_verb`/`bad_result` -
никогда. Токен: `Crypto.generate_random_bytes(16).hex_encode()` в редакторе, в кадре и в
`port.json`, в логах нет; кадр без токена - отказ и закрытие. Один in-flight - очередь в
Python; сервер второй кадр не буферизует. Устаревший порт - `connect_failed`, не вечное
переподключение. `verbs_version` сверяется в handshake. Валидация ответа - в домене вклада
(`bad_result` + `problems` с путём поля), не в `client.py`. Профиль: `editor` - вклад есть,
`headless`/`cli`/`test` - нет, секция `editor` = `no_module`. «Мост недоступен» -
`available: false` с `reason` (`no_bridge`/`engine_down`/`wrong_project`/`verbs_mismatch`).

**Сценарии (все на фейке, `tests/py/integration/fake_editor.py`).** Годный снимок против
`result_schema`; чужие `verbs_version`/`project_hash` без повтора; обрыв посреди кадра и
молчание - по одному повтору; кадр больше лимита; нет `port.json` -> `no_bridge`;
устаревший порт -> `connect_failed`; кадр без токена -> `denied` и закрытие; двойной ответ;
неизвестный примитив; переподключение после обрыва; второй вызов ждёт первого (один
in-flight). Секция: `editor` с фейком (`available: true`), без моста (`no_bridge`), headless
(`no_module`). Домен: `revision: "3"` -> проблема с путём `open_scenes[0].revision`, `5` на
месте `node_path` -> проблема, `None` в nullable -> `[]`.

**Сессия 32 (2026-10-28), A.1.1 — харнесс сам себя не обманывает.** Одиночный `-s`
больше не врёт `timeout`: `bridge_probe.gd` пишет `ok:false / failure.reason="no_client"`
с подсказкой про pytest (таймаут настраивается `HARNESS_TIMEOUT_MS`), а приёмка живой
ветки — `python -m pytest tests/py/live -v` (тот же единственный тест проверяет и провод,
и соло-режим: `exit 1`, пустые `verbs`, файл на диске совпадает со stdout). Мутация M1
(`has_editor()` → `return false`) оставила живой тест **зелёным** — редакторская ветка им
не покрыта; мутация M2 (`no_client` → `timeout`) его краснит, то есть новая проверка не
пустая. Числа и sha256 — `docs/WORKLOG.md`, сессия 32.

**Сессия 35 (2026-10-28), B.0 — мост в настоящем редакторе.** `plugin.gd` получил
`@tool` и поднимает `editor/core/lifecycle.gd` из `_enter_tree`; `_exit_tree` глушит
мост; `[editor_plugins]` включён в хостовом `project.godot`; `@tool` добавлен в 10
скриптов цепочки загрузки (иначе редактор 4.6 их не инстанцирует). Причина, по которой
мост не поднимался 40+ прогонов: Godot не инстанцирует нетул-скрипт плагина и пытается
показать диалог, невидимый в headless (`Attempting to parent and popup a dialog that
already has a parent`) — это был дефект `plugin.gd`, а не свойство движка. Числа и
мутации — `docs/WORKLOG.md`, сессия 35.

## Следующее действие

Часть B (`editing.scene_ops`): батч правок сцены в одном undo, `expected_revision`,
квитанции; `ResourceSaver` и `undo` появляются только там (в части A их нет). Затем часть C -
`.tscn`/`.tres` как файлы через `formats/tscn.py`.

## Блокеры

- Снят 2026-10-27 (фаза 1): `context.gather` собран — `selfcheck context.gather` ok,
  корпус 3/0; секцию `editor` есть куда вложить (сейчас `unavailable/no_module`).
- В CI движка нет: живой тест `tests/py/live/` без бинаря **пропускается** (`skip`),
  поэтому в CI приёмкой он не считается — прогонять там, где Godot есть. Приёмка
  живой ветки: `python -m pytest tests/py/live -v` → `2 passed` (путь к бинарю
  переопределяется `GODOT_BIN`). Одиночный
  `godot --headless --path <проект> -s res://addons/godot_agent/editor/harness/bridge_probe.gd`
  без клиента штатно возвращает `ok:false / failure.reason="no_client"` (exit 1,
  подсказка про pytest) — это норма, а не провал моста (A.1.1, 2026-10-28).
- **Закрыт 2026-10-28 (B.0):** редакторская ветка доказана живым прогоном. Мост
  поднимает сам плагин: `godot --headless --editor --path <проект>` →
  `user://godot_agent/port.json`, `tests/py/live/test_editor_branch_live.py` открывает
  сцену аргументом и видит `open_scenes == 1`, непустой `active_scene`, пустое
  выделение, валидное по `result_schema`; `python -m pytest tests/py/live -v` →
  `2 passed`, движок `4.6.3-stable`. Прежняя непокрытость была не долгом теста, а
  дефектом: корневой `plugin.gd` без `@tool` редактор 4.6 не инстанцирует вовсе.
  Мутации на сданном файле: `has_editor()` → `false` краснит новый тест (до B.0 он
  оставался зелёным — вот она, дыра), `stop()` без удаления `port.json` краснит
  проверку уборки, `has_editor()` → `true` в `-s` даёт отказ по схеме, а не падение
  моста. Числа и sha256 — `docs/WORKLOG.md`, сессия 35.
