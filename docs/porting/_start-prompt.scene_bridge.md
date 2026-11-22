# Задача: седьмой срез — мост редактора, часть 1: транспорт + `context.editor_context`

> **Заменён промптом `_start-prompt.editor_bridge_a.md` (2026-10-27).** Этот файл
> описывал срез вместе с гигиеной `§0` и контрактом: гигиена закрыта, контракт
> зафиксирован и принят, ядро схемы починено (`_start-prompt.schema-union.md`).
> Исполнение части A продолжается по новому промпту; §3–§7 ниже остаются
> обязательными решениями (они перенесены туда же).

Ты продолжаешь перенос агента в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`.
Приняты и зелены: `project_text.search` (16), `code_intel.functions` (17),
`code_intel.usages` (18+13), `editing.write_preview` (16), `editing.write_apply` (14),
`editing.rollback` (4). Их корпуса и тесты обязаны остаться `ok`.

Это первый срез, где появляется **второй процесс**. До сих пор всё доказывалось
байтами на диске; теперь придётся доказывать протоколом. Поэтому главное правило
среза: **сначала контракт кадра и примитива, потом код**. Если примитив и транспорт
сделать «по ходу», часть 2 воронки придётся переделывать вместе с ними.

## 0. Гигиена: закрыть до новой работы (5 правок по аудиту части 2 + 2 новые)

1. **`hint` при `already_rolled_back`.** Сейчас `conflict` без подсказки. Добавь:
   «план уже откачен — сделай новый `write_preview`». Тест: `hint` непустой.
2. **Список причин `conflict` — в одном месте.** `post_state_mismatch` появился в
   коде (это правильно), но нигде не перечислен. Заведи один набор причин
   (`editing/shared`), добавь `post_state_mismatch` и `plan_state:<STATE>` в лист и
   ADR-0005, и контрактный тест «`reason` из известного набора» — иначе шестая
   причина появится молча.
3. **Инвариант `step_id`.** Сейчас `step_id` = путь файла, то есть «один шаг на
   файл». Запиши это в ADR-0005 явно; если решаешь `path#k` — сделай сейчас,
   потому что часть 3 добавит второй вид операции на тот же файл-проект.
4. **Кейс 15 корпуса `write_apply`:** `apply → rollback → apply тем же digest` →
   `conflict/already_rolled_back` (поведение верное, кейса нет).
5. **Долг в `PROGRESS.md`:** журнал растёт (`RESTORED` на каждый файл) и не
   чистится. Строка в «Долги».
6. **`selfcheck` и модуль-вклад.** `ModuleSpec` без `provides_tools`, но с
   `contributes_to` сейчас получает `fail`. Это ломает ровно нужный этому срезу
   случай (`editor_context` — вклад в составной `context`, своего инструмента нет).
   Требование: `fail` только если пусто и то, и другое; для вклада обязательны
   `tests/`. Тест: заготовка → `not_implemented`, вклад без тестов →
   `not_implemented`, вклад с тестами → `ok`.
7. **Версия словаря примитивов.** `contract/editor_verbs.json` сейчас
   `{"verbs": []}`. В этом срезе он становится настоящим контрактом (§4), и
   расхождение версий Python ↔ GDScript обязано давать `engine_down` с причиной.

## 1. Границы: что сейчас, а что после

| Часть | Механики | Суть |
|---|---|---|
| **A (сейчас)** | транспорт + `context.editor_context` | два процесса разговаривают; Python видит открытые сцены, ревизии, `dirty`, выделение; **ничего не пишется** |
| B | `editing.scene_ops` | правка открытой сцены батчем в одном undo-скоупе: `plan_id`, `expected_revision`, идемпотентная квитанция |
| C | `editing.resource_ops`, `verification.tscn_lint`, `python/formats/tscn.py` | `.tres`/`.tscn` как файлы: схема правок, canonical digest, линт, разбор формата |

В A запрещено: писать в сцену, вызывать `ResourceSaver.save`, делать
`scene_apply_batch`, реализовывать undo. Если окажется, что A без записи
недоказуема — это повод переписать ожидание (§6), а не добавить запись.

## 2. Что берём у эталона (только чтение, `python -B`)

| Файл | Что там | Что берём |
|---|---|---|
| `agent_server.gd` (13 КБ) | реестр адресов и маршрутов, `project_token`, JSON-заголовки, сохранение pid | идею адресации и токена; **формат вызова не берём** (там HTTP+Flask) |
| `agent_server_link.gd` (29 КБ) | `HTTPRequest`-клиент: очередь, ожидание старта, ретраи, автостарт процесса | поведение: очередь, ожидание, ретраи, «редактор не отвечает» |
| `agent_editor_context.gd` (6 КБ) | `static capture()`: открытые сцены, выделение, свойства, скрипт | состав снимка: какие поля реально нужны потребителям |
| `agent_mutation_gate.gd` (12 КБ) | `classify(path)` → вид записи, undo, журнал | только классификацию «что за файл» (нужна в B); в A не реализуется |
| `agent_scene_executor.gd` (25 КБ) | `prepare`/`execute`, detached load, `ResourceSaver.save`, хеш, откат | читать как «что будет в B», код не переносить |
| `godot_headless_validation.py` (22 КБ) | копия проекта + встроенный GDScript-харнесс + `result.json` | приём харнесса: один скрипт, один прогон, вердикт JSON |
| `scene_actions.py` (17 КБ) | схема правок сцены, `normalize_variant`, staged-файл | читать как «что будет в B» |

Старые тесты по теме (`docs/tests-map.md`): `test_godot_headless_live.py`,
`test_editor_context*.py`, `test_panel_short_channel.py`,
`test_context_menu_*_live.py`. Триаж проставлен; строки не удалять.

## 3. Транспорт: решение, которое надо принять и записать (ADR-0007)

В старом агенте слушал **Python** (Flask на `127.0.0.1:5000`), редактор был
клиентом на `HTTPRequest`. В новой архитектуре примитивы и главный поток — на
стороне редактора, поэтому предлагается обратное: **слушает GDScript, Python —
клиент**. Обоснование: редактор владеет ресурсом, его жизненный цикл — источник
правды о том, «жив ли мост»; не остаётся процесса-сироты, держащего порт, как в
старом агенте; Python может перезапускаться свободно.

Но это меняет `SEC-03` («слушающий сокет только `channels/http` и `127.0.0.1`»).
Поэтому:

- `docs/adr/0007-most-redaktora.md` со сравнением двух вариантов (кто слушает) и
  решением **с обоснованием**; если факты эталона против моего предложения —
  прими другое и запиши почему (правило главнее автора);
- если слушает GDScript — дополни `docs/security/invariants.md` (SEC-03): адрес
  только `127.0.0.1`, порт случайный, токен в каждом кадре, `user://godot_agent/port.json`,
  отказ на первом кадре без токена; проверяется тестом, а не обещанием;
- если слушает Python — SEC-03 не меняй, но опиши, кто запускает процесс
  (открытый вопрос Q-02 — в лист, не решай по ходу).

Формат кадра (в ADR и в `contract/editor_verbs.json`):

- кадр = 4 байта длины (big-endian) + JSON UTF-8; максимум кадра — лимит;
- handshake первым кадром: `{"hello": {"protocol": 1, "verbs_version": N,
  "godot": "4.6", "project_hash": "…", "token": "…"}}`; несовпадение
  `verbs_version` → `engine_down` (`verbs_mismatch`), `project_hash` →
  `engine_down` (`wrong_project`);
- один in-flight запрос на соединение; параллельные вызовы — очередь клиента;
- таймаут кадра — настройка профиля; по таймауту `engine_down` (`timeout`);
- разрыв посреди кадра → `engine_down` (`truncated`), а не «битый JSON».

## 4. Примитивы части A (только чтение) и контракт словаря

`contract/editor_verbs.json`:

```
{"schema_version": 1, "verbs_version": 1,
 "verbs": [{"name": "editor_ping",  "effects": "read", "thread": "main", ...},
           {"name": "editor_state", "effects": "read", "thread": "main", ...},
           {"name": "editor_selection", "effects": "read", "thread": "main", ...}]}
```

Три примитива, и ни одного сверх:

1. `editor_ping` → `{godot, verbs_version, protocol, open_scenes, uptime_s}` —
   доказательство, что мост жив и что версии совпали.
2. `editor_state` → `{open_scenes: [{path, revision:int, dirty:bool, active:bool,
   unsaved_changes:int}], active_scene, project_hash}`. `revision` — счётчик
   изменений сцены, который редактор увеличивает сам; в B он станет
   `expected_revision`.
3. `editor_selection` → `{node_path, scene, properties: [{name, type, value}],
   script}` — снимок выделения для секции `editor` составного `context`.

Сверка словаря с кодом — как `# tool:` у модулей: в GDScript-обработчике строка
`# verb: editor_state`; `tools/gen_contract.py --check` дополняется сверкой
«каждый `verb` из JSON имеет обработчик, каждый обработчик есть в JSON». Это
единственная защита от «примитив есть в контракте, но не реализован».

## 5. Модуль `context.editor_context` и что он отдаёт

Своего инструмента у него нет: он **вклад** в составной `context` (владелец —
`context.gather`, ADR-0004) и владелец внутреннего сервиса моста.

- `ModuleSpec(provides_tools=(), contributes_to=("context",),
  internal_services=("editor_bridge",), environment="editor",
  requires_ports=("editor",))`;
- секция `editor` в ответе `context`: `{available: bool, reason: str|null,
  open_scenes: [...], selection: {...}|null}`. Если редактор не отвечает —
  **не ошибка**, а `available=false` с причиной из моста: контекст обязан
  собираться и без живого редактора (в headless-профиле);
- порт: `editor` в `ports.py` модуля — `ping()`, `state()`, `selection()`;
  реализация — `substrate/editor/client.py` (сокет, framing, таймауты,
  переподключение), объявление структурное (ADR-0003), связывает `bootstrap`;
- `environment="editor"`: в профиле без редактора модуль `disabled` с причиной,
  и `context` работает без секции `editor` (это тест, а не пожелание).


## 6. Чем доказывается часть A (важнее, чем кажется)

Живого Godot в CI нет, поэтому доказательство трёхуровневое, и только второй
уровень «настоящий».

1. **Фейковый редактор на Python** (`tests/py/integration/fake_editor.py`):
   говорит по протоколу и умеет ломаться — молчать, оборвать кадр посередине,
   прислать чужой `verbs_version`, ответить дважды, ответить не в тот запрос.
   Это основа unit/contract/integration-тестов: она проверяет **протокол**.
2. **Настоящий Godot headless** (`editor/harness/`): скрипт поднимает
   `SceneTree`, включает мост, отвечает на `editor_ping`/`editor_state`. Помечается
   `needs_live` и **не считается приёмкой** (R-18), но обязан существовать: без
   него нельзя утверждать, что фейк не разошёлся с реальностью. В отчёт — версия Godot.
3. **`selfcheck`**: `module` (манифест + вклад), `unit` (домен и контракт),
   `corpus` — корпуса **нет**, и это решение: `editor_state` не детерминирован
   (uptime, пути). Вместо корпуса — контрактные схемы и сценарии фейка. Запиши
   это в лист.

Обязательные сценарии (каждый — тест):

- handshake: совпал → `ok`; чужой `verbs_version` → `engine_down/verbs_mismatch`
  с обоими номерами в `details`; чужой `project_hash` → `engine_down/wrong_project`;
- кадр: приходит по частям (по 1 байту) → собирается; длина больше лимита →
  `engine_down/frame_too_big`; соединение закрыто посередине → `engine_down/truncated`;
- таймаут: фейк молчит → `engine_down/timeout` за время профиля, без зависания;
- переподключение: фейк закрыл соединение, поднялся снова → следующий вызов работает;
- `available=false`: редактора нет → секция `editor: {available: false,
  reason: "connect_failed"}`, а не `engine_down`;
- профиль без редактора: модуль `disabled` с причиной, `context` зелёный;
- main-thread: ни один обработчик в GDScript не блокирует дольше лимита —
  тест-страж по времени ответа на `ping`;
- токен (если слушает GDScript): кадр без токена → отказ и **закрытие
  соединения**, в лог одна строка без значения токена.

## 7. Решения, которые обязан принять и записать

1. **Кто слушает** (§3) — ADR-0007, с последствиями для SEC-03 и Q-02.
2. **Где живёт `revision`.** Редактор увеличивает при любом своём изменении
   сцены; `editor_state` только читает. В B `revision` станет
   `expected_revision`; если сейчас сделать его «по mtime файла», B будет неверным.
3. **Что считать «открытой сценой».** Только `EditorInterface.get_open_scenes()`
   (корни), а не все загруженные `Node`. `dirty` — через `EditorInterface` или
   собственный счётчик; выбери и обоснуй: от этого зависит stale-check в B.
4. **Один in-flight.** Где очередь: в клиенте (Python) или в сервере (GDScript).
   Одна из сторон обязана её иметь, вторая не должна присылать второй кадр.
5. **Что происходит при перезагрузке плагина.** Сокет закрывается, клиент видит
   `truncated`/`connect_failed`, следующий вызов переподключается. Никакого
   «повисшего состояния» в Python.
6. **Логи.** Одна строка на вызов: verb, длительность, размер кадра, исход. Без
   значений токена и без содержимого свойств выделения (SEC-13).

## 8. Стоп-условия

- Не писать в сцену и не вызывать `ResourceSaver`/`ResourceLoader.save` нигде.
- Не реализовывать `scene_apply_batch`, undo, проверку `expected_revision` — это B.
- Не тащить HTTP, Flask, `requests`; не поднимать второй слушающий сокет.
- Никакой логики разбора `.tscn`/`.gd` в GDScript (R-14): только примитивы.
- Не менять конвейер записи, кроме правок §0.
- Не выдавать `needs_live` за приёмку; не помечать `ported` без `selfcheck` и прогона фейка.
- Старый плагин — только чтение (`python -B`, `PYTHONDONTWRITEBYTECODE=1`).


## 9. Что проверит аудитор

| Что | Доказательство |
|---|---|
| срез собран | `selfcheck context.editor_context` → `ok`, exit 0 |
| вклад не сломал `context` | `selfcheck context.gather` → `ok`; `context` зелёный при `available=false` |
| регресс воронки | три `selfcheck` записи + `snapshot_diff` (98 кейсов + кейс 15 §0) |
| протокол, а не «работает у меня» | свои прогоны с фейком: частичный кадр, таймаут, чужой `verbs_version`, двойной ответ |
| мутация | убрать проверку токена → тест падает; убрать проверку `verbs_version` → падает |
| живой Godot | `needs_live`-прогон с версией движка, отдельно от приёмки |
| GDScript без логики | в `.gd` нет разбора `.gd`/`.tscn`, нет работы с файлами проекта |
| безопасность | `security_audit` ok; в логах нет токенов; сокет не в проекте |
| границы и числа | домен без IO; `app.py` ≤ 80; числа тестов = `--collect-only`; `__pycache__` = 0 |
| документы | ADR-0007, SEC-03, лист, `PROGRESS.md`, `parity.md`, `WORKLOG.md` |

## 10. Финальный прогон и записи

```
python tools/selfcheck.py context.editor_context    # exit 0
python tools/selfcheck.py context.gather            # exit 0
python tools/selfcheck.py editing.write_apply       # exit 0 (+ кейс 15)
python tools/snapshot_diff.py                       # 0 расхождений
python -m pytest python/modules tests/py -q         # exit 0
python tools/security_audit.py --json               # ok
python tools/lint_arch.py; python tools/check_limits.py; python tools/gen_contract.py --check
python tools/probe.py context --args-file … --project fixtures/projects/minimal
```

Записи после зелёного прогона: лист `docs/porting/context.editor_context.md`
(создать до кода: протокол, примитивы, решения §7, сценарии фейка, что будет в B);
`docs/adr/0007-most-redaktora.md`; `docs/security/invariants.md` (SEC-03);
`contract/editor_verbs.json` (`verbs_version: 1`, три примитива);
`docs/parity.md` — `context.editor_context` → `ported`, `scene_ops`/`resource_ops`
остаются `skeleton` с пометкой «часть B/C»; `PROGRESS.md` — этап 7, следующее —
часть B (`editing.scene_ops`); `WORKLOG.md` — сессия с выводом команд, решением
«кто слушает» и инцидентами; `tests-map.md` — примечания без удаления строк;
`deviations.md` — если отличаемся от эталона (там HTTP, здесь сокет).

## 11. Что будет в части B (не делать сейчас, но контракт не должен мешать)

`editing.scene_ops` = `scene_apply_batch(plan_id, digest, expected_revision,
steps[])` в одном undo-скоупе; квитанция на шаг (`applied_hash` сцены,
`undo_token`), потеря ответа ≠ успех (перечитывается `editor_state`), `revision`
изменился между preview и apply → `stale_plan`. Плюс `mutation_gate` с
`classify(path)` и журналом редактора. Поэтому уже сейчас: `revision` — счётчик
редактора, а не mtime; примитивы — с явным `effects` и `thread`; словарь
версионирован.

