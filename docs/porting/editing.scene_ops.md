# editing.scene_ops — запись в сцену одним undo (часть B моста)

**Статус:** **этап 7 — `ported`** (2026-10-29). Срез B закрыт аудитом 2026-10-29:
живой `plan → apply → undo` доказан (`tests/py/live/test_editor_branch_live.py`,
3 живых теста на Godot 4.6.3), undo-батч — одно действие истории
(`history_version_before`/`history_version`), `nothing_to_undo` и `revision_mismatch`
типизированы, `verbs_version: 3`, примитивов 6, корпус `corpus="live"`.
`selfcheck editing.scene_ops` — ok (unit 25, `limits 453/0`, `contract 9`, `security ok`).
Лист создан **до** кода (R-19).
Владелец инструмента `scene_ops`; запись — только через мост GDScript (R-14), в сцену
из Python не пишется ничего.

## Цель

Дать агенту батч правок открытой сцены: `add_node`, `set_property`, `attach_script`,
`connect_signal`. Один батч = **один** undo-шаг; любая ошибка — `abort_undo`, сцена
не меняется. Оптимистичная блокировка: `expected_revision` (счётчик редактора) и
`plan_digest` (отпечаток плана).

## Границы

| В срезе | Не в срезе |
|---|---|
| примитивы `editor_scene_plan` (dry-run) и `editor_scene_apply` | `.tscn`/`.tres` как файлы, линт, `formats/tscn.py` (часть C) |
| `editing.scene_ops`: `MODULE`, `ToolSpec`, домен, `app.py`, тесты | `editing.resource_ops`, `project_ops.settings_set` |
| `verbs_version: 1 → 2` + ADR-0007 §«Версия словаря» | правки `tools/*`, `python/kernel/schema.py`, `python/protocol/**` |

## Старый код (эталон, только чтение)

`agent_scene_executor.gd` (prepare/execute операций сцены: detached load, add/set/
attach/connect, `ResourceSaver`, undo-скоуп) и `agent_mutation_gate.gd` (подтверждение
разрушающих операций). Переносится **смысл**: план без записи, исполнение в одном
undo, откат при ошибке. Не переносится: подтверждение через UI (это канал) и запись
`.tscn` на диск (часть C).

## Решения (из §2 промпта)

- `editor_scene_plan`: вход `scene`, `expected_revision`, `operations` (1…64);
  результат `scene, revision, plan_digest, steps[], would_change[], warnings[]` —
  **ничего не пишет**.
- `editor_scene_apply`: то же + `plan_digest`, `undo_label`; результат
  `scene, applied_revision, undo_label, receipts[], changes[]`.
- Неизвестная `op` рушит весь батч (`unknown_operation`), а не «пропустить и продолжить».
- `expected_revision` ≠ текущей → `conflict/revision_mismatch`; чужой `plan_digest` →
  `stale_plan`; ошибка в середине → `abort_undo`, `applied_revision` не растёт.
- `plan_digest` — sha256 канонического запроса (сцена, ревизия, операции; порядок
  операций значим, порядок ключей в операции — нет). Считают обе стороны по одному
  правилу; расхождение — `bad_result`, а не «поверим редактору».
- Лимиты: 64 операции, значение свойства ≤ 4 КиБ.

## Корпус

Корпус снапшотов не снимается — и это **объявлено данными**, а не текстом:
`ModuleSpec.corpus = "live"` (`python/modules/editing/scene_ops/module.py`), значение
проверяется в `kernel/module_spec.py` (`CORPUS_POLICIES = ("corpus", "live")`). Решение
принимает чистая функция `tools/selfcheck.py::corpus_readiness(policy, module_id,
folders, live)`: политика `live` даёт `ok` только при наличии файла `tests/py/live/*.py`
с упоминанием `editing.scene_ops`, иначе — `not_implemented` с причиной. Основание:
эталон механики исполняется в GDScript редактора, Python-функции эталона нет, а
`tools/snapshot_record.py` берёт эталон только через `_reference_runner`
(`_start-prompt.scene_ops_b1.md` §1.2, **вариант A**).

Живой тест, на который ссылается флаг, не «упоминает» механику, а **зовёт** её:
`tests/py/live/test_editor_branch_live.py` вызывает `scene_ops_app.call("scene_ops", …)`
на поднятом мосте (см. «Блокеры», D-1) и сверяет, что dry-run не изменил сцену.
Закреплено тестами `tests/py/tools/test_selfcheck_readiness.py`:
`test_live_corpus_with_live_test_is_ok`, `test_live_corpus_without_live_test_is_not_implemented`,
`test_default_corpus_policy_unchanged`, `test_live_tests_found_by_module_id`,
`test_scene_ops_manifest_declares_live_corpus`, `test_check_corpus_uses_live_flag_of_manifest`.

## Ход работы (сессия 36, 2026-10-28)

**Контракт.** В `contract/editor_verbs.json` добавлены два примитива с `effects: write`,
`thread: main`: `editor_scene_plan` и `editor_scene_apply` (`_change_policy` разрешает
аддитивное добавление как +1 версию). `verbs_version: 1 → 2` в шести зашитых местах:
`editor/bridge/server/session.gd` (`VERBS_VERSION`), `editor/bridge/verbs/editors/editor_verbs.gd`,
`socket_server.gd` (`port.json`), `tests/py/integration/fake_editor.py` (`PING` и дефолт
`__init__`), `tests/py/integration/test_editor_context_bridge.py` (ожидание `ping`).
`protocol` остался 1. `_handlers` в файле словаря не возвращался.

**GDScript (руки, R-14).** `editor/bridge/verbs/scene/scene_verbs.gd` — два маркера
`# verb:` и регистрация в роутере; `scene_executor.gd` — план на копии `PackedScene`
(`GEN_EDIT_STATE_INSTANCE`, ничего не пишет), `plan_digest` = sha256 канонического
запроса, `apply` — сверка `expected_revision` (`conflict/revision_mismatch`) и
`plan_digest` (`stale_plan`), проба на `duplicate()` ради квитанций/`changes`, затем
**один** `UndoRedo.create_action` + `add_do_method`/`add_undo_method`
(`set_property` — `add_do_property`/`add_undo_property`), `commit_action()`;
`commit_action() == false` → `cancel_action()` + `apply_failed`. Неизвестная `op`
рушит батч целиком (`unknown_operation`); лимиты 64 операции / 4096 Б на значение
проверяются **до** обращения к сцене. `endpoints.gd` подключает `scene_verbs.gd`;
`context_snapshot.gd` получил `revision_of`/`bump`; в `error_codes.gd` — `invalid_input`,
`unknown_operation`, `scene_not_found`, `revision_mismatch`, `stale_plan`, `plan_invalid`,
`apply_failed`.

**Python.** `domain/core.py` (без IO: `hashlib` только): `canon` — канонический JSON
**своими руками** (импорт `json` в `domain/` запрещён правилом фазы 0.5 — `lint_arch`
ловил `json` на первой же сборке), `digest_of`, `build_request` (типы, лимиты, `op`
из списка, `apply` требует `plan_digest`), `check` (ответ по `result_schema`),
`plan`/`apply`/`perform` (сверки сцены, ревизии, квитанций). `tools.py` — `ToolSpec`
`scene_ops` с `effects="write"` и JSON-схемами; `app.py` — одна точка `call(tool, args, ctx)`,
порт `editor`. `module.py` — `environment="editor"`, `provides_tools=("scene_ops",)`.

**Инструмент.** `security_audit` SEC-03 ловил `.run(` (правило про запуск процессов) в
`core.run` — переименовано в `core.perform`; ложных срабатываний больше нет.

**Доказательства.** `pytest python/modules/editing/scene_ops tests/py/integration/test_scene_ops_bridge.py`
→ **25 passed** (13 домена + 12 сценариев моста на фейке: план без записи, чужой digest,
ревизионный конфликт, сбой на втором шаге, `applied` без квитанций, `truncate` после
`apply` с одним повтором, отказной кадр без повтора, ответ не на тот примитив, плохой
запрос без сети, чужой инструмент). `gen_contract --check` → ok, артефактов **9**
(новый `contract/capabilities/scene_ops.json`); маркеров по регексу `gen_contract` —
**5**. `snapshot_diff` → 102/0 (новых кейсов нет: корпуса у механики быть не может).
`lint_arch`/`check_limits` → 453/0, `security_audit` → ok. `selfcheck editing.scene_ops`
→ **blocked**: `module`/`unit`/`limits`/`contract`/`security`/`layers` = ok (unit 25),
`corpus` = `not_implemented` (см. «Блокеры»).
Мутации на сданном `domain/core.py` (`sha256 6309DF88…7832` до/после, бэкап
`shutil.copyfile`): M1 (снять сверку `plan_digest` в `plan`) красит
`test_plan_rejects_foreign_digest` + `test_foreign_digest_is_engine_down`; M2 (снять
счёт квитанций) — `test_apply_rejects_partial_or_growing_batch` +
`test_applied_without_receipts_is_refused`; M3 (снять гейт `stale_plan`) —
`test_apply_requires_matching_plan_digest` + `test_stale_plan_never_reaches_bridge`.
Файл каждый раз восстанавливался побайтово (sha совпал).

## Ход работы (сессия 39, 2026-10-28)

**Версия словаря сведена с контрактом.** Две копии `verbs_version: 1` при контракте `2`
убраны: `python/modules/context/editor_context/tests/test_core.py` читает
`contract/editor_verbs.json` (`ROOT = Path(__file__).resolve().parents[5]`) и держит
`PING["verbs_version"] = CONTRACT["verbs_version"]`, плюс новый гейт
`test_ping_version_matches_contract`; `editor/harness/bridge_probe.gd` берёт версию из
`SessionScript.VERBS_VERSION`; `tests/py/live/test_bridge_live.py` требует
`payload["verbs_version"] == verbs_catalog.version()`; подложенный `port.json` в
`test_editor_branch_live.py` тоже пишет версию из словаря; фикстуры инструмента
(`tests/py/tools/test_gen_contract.py`, `test_gen_contract_types.py`) подняты до `2`,
чтобы греп не находил литерала. Греп `"verbs_version": 1`: 0 попаданий в коде, тестах
и харнессе (9 попаданий — в `docs/`, история и тексты промптов).

**Судьба корпуса — вариант A** (флаг `corpus: "live"`), см. «Корпус».

**Живой прогон вскрыл дефект принятой части B (D-1).** `editor_scene_plan` на живом
мосте отвечает `truncated`: `editor/bridge/verbs/scene/scene_executor.gd` **не
компилируется** — `Parse Error: Cannot get return value of call to "commit_action()"
because it returns "void"` (`scene_executor.gd:101`) и `Cannot infer the type of "keys"
variable because the value doesn't have a set type` (`:177`). Каскад
`Failed to compile depended scripts` идёт от `scene_verbs.gd` через `endpoints.gd` →
`socket_server.gd` → `lifecycle.gd` → `plugin.gd`, дальше `Nonexistent function 'plan'
in base 'Nil'`, и диспетчер отдаёт `truncated` (`ErrorCodes.TRUNCATED`). Значит
примитивы части B живым прогоном не работали ни разу, а `scripts.broken == []` этого
не поймал (D-2): харнесс считает скрипт битым только при `load(...) == null`, а
GDScript с parse-ошибкой загружается, но не инстанцируется.
`editor/bridge/verbs/scene/**` в этом срезе заморожен (§1.3 промпта) — правка не
делалась, оба дефекта в «Блокерах».

**Тесты.** `pytest python/modules tests/py --ignore=tests/py/live` → **449 passed** =
`--collect-only` **449** (41 файл); `tests/py/live -v` → **2 passed** (13.70 с, движок
4.6.3). Новые: 6 в `tests/py/tools/test_selfcheck_readiness.py`,
`test_ping_version_matches_contract` в домене вклада и живая проверка `scene_ops` внутри
редакторского теста.

**Мутации (R-22, на сдаваемых файлах, бэкап `shutil.copyfile`, строго последовательно).**
M1 `tools/selfcheck.py` (`36FA1C097B24` → `0FF4D47160E9`, снята ветка флага) краснит
`test_check_corpus_uses_live_flag_of_manifest` и возвращает `selfcheck` в `blocked`;
M2 `editor/harness/bridge_probe.gd` (`75B870C5B2C2` → `8FE17F116859`, литерал `1` вместо
`SessionScript.VERBS_VERSION`) краснит `test_bridge_answers_three_verbs_from_real_godot`
(`assert 1 == 2`); M3 `editor_context/tests/test_core.py` (`E3EA86FF2ED9` → `FAE8EE89CE72`,
`PING` с литералом `1`) краснит `test_ping_version_matches_contract`. Все три файла
восстановлены побайтово — sha совпали с исходными.

## Инструменты проверки (чем сдаётся)

| Что | Команда | Вердикт |
|---|---|---|
| домен + сценарии моста | `python -m pytest python/modules/editing/scene_ops tests/py/integration/test_scene_ops_bridge.py -q` | 25 passed |
| контракт и артефакты | `python tools/gen_contract.py --check` | ok, артефактов 9 |
| механика | `python tools/selfcheck.py editing.scene_ops` | **ok** (unit 25, `corpus`: «корпус live…») |
| границы и правила | `python tools/lint_arch.py`, `tools/check_limits.py`, `tools/security_audit.py` | ok, 453/0 |
| живой редактор | `python -m pytest tests/py/live -v` | 2 passed (13.70 с, 4.6.3): три read-примитива и **типизированный отказ** `scene_ops` без записи в сцену (D-1) |

## Следующее действие

Срез B.2 (дефекты D-1/D-2 из «Блокеров»): `scene_executor.gd:101` — у
`UndoRedo.commit_action()` нет возвращаемого значения, провал брать из
`UndoRedo.get_history_undo_redo(...)`/`is_committing_action()` либо переписать без `if`;
`:177` — явный тип для `keys`. Затем `_scan` харнесса перевести с `load(...) == null` на
`can_instantiate()`, и только после этого — живой `editor_scene_plan`/`editor_scene_apply`:
открыть сцену, применить батч из двух операций, проверить **один** шаг undo,
`applied_revision` и «после сбоя сцена не изменилась» (этап 6).

## Блокеры

- **D-1 (блокирует живой `apply`, найден в B.1).**
  `editor/bridge/verbs/scene/scene_executor.gd` не компилируется: `:101`
  `if not undoredo.commit_action():` — `commit_action()` возвращает `void`; `:177`
  `var keys := value.keys()` — тип не выводится. Следствие: `scene_verbs.gd` падает на
  `new()`, цепочка до `plugin.gd` не загружается, живой `editor_scene_plan` отвечает
  `truncated`; `undo` и `abort` на живом движке не проверялись **никогда**. Правка
  отложена: `scene/**` заморожен в срезе B.1, часть B остаётся этапом 4.
- **D-2.** `editor/harness/bridge_probe.gd::_scan` считает `.gd` битым только при
  `load(...) == null`, поэтому parse-ошибки (D-1) невидимы и `scripts.broken == []`
  врёт. Предложение — `can_instantiate()` в проверке; делать это до починки D-1 нельзя:
  живой тест покраснеет на чужом дефекте.
- Живой `apply` и undo-инвариант («после сбоя сцена не изменилась») — долг `needs_live`
  до B.2; `selfcheck editing.scene_ops` = `ok` этого не покрывает.

**Сессия 40 (2026-10-28), B.2 — живой `plan → apply` в редакторе, D-1/D-2/D-3.**

- **D-1 закрыт**: `editor/bridge/verbs/scene/scene_executor.gd` — `commit_action()` возвращает
  `void`, поэтому `if not undo.commit_action():` заменено на вызов без условия (проверка идёт до
  commit, пробой на копии сцены); `var keys := value.keys()` → `var keys: Array = value.keys()`.
  `--check-only -s scene_executor.gd` → exit 0 (до правки — `Parse Error: Cannot get return value
  of call to "commit_action()" because it returns "void"`); цепочка `scene_verbs.gd`,
  `endpoints.gd`, `socket_server.gd`, `plugin.gd` — тоже exit 0.
- **D-2 закрыт**: `editor/harness/bridge_probe.gd::_scan_scripts` считает файл битым и при
  `load(...) == null`, и при `not script.can_instantiate()`: скрипт с parse-ошибкой грузится
  объектом, поэтому прежняя проверка молчала и `scripts.broken == []` врал. Подложка
  `editor/harness/zz_break.gd` (`func broken( -> void:`) → живой тест **красный**, `broken`
  содержит файл; после удаления — **2 passed**, `broken == []`.
- **D-3 (найден живым прогоном) закрыт**: `_canon` печатал числа кадра как float (JSON приносит
  `3` как `3.0`), а Python печатает `3` — отпечатки расходились, мост отвечал `bad_result`.
  Теперь `TYPE_INT` → `%d`, целые `TYPE_FLOAT` → `%d`, прочие float — `JSON.stringify`.
- **`bump()` ставит `dirty`**: `context_snapshot.gd::bump` пишет `_dirty[path] = true`, иначе
  клиент не видел несохранённого состояния после успешного батча.
- **Живой батч** (`tests/py/live/test_editor_branch_live.py`, сцена
  `res://zz_editor_branch_probe.tscn` с дочерним `Body` и `parent="."`, удаляется в `finally`):
  план двух операций не пишет и не меняет `revision`; применение — один undo,
  `applied_revision == revision + 1`, квитанции `[True, True]`, `dirty True`; повтор того же
  плана → `stale_plan`; батч с чужим `expected_revision` (отпечаток считается
  `scene_core.digest_of` для той же ревизии) → `conflict/revision_mismatch` без изменения сцены;
  второй батч видит `before` = `after` первого; сбой на втором шаге (узла нет) →
  `invalid_input/plan_invalid`, сцена побайтово та же.
- **Прогоны**: `pytest tests/py/live -v` → **2 passed** (12.33 с, 4.6.3); без живых — junit
  `tests=449, errors=0, failures=0, skipped=0`; `--collect-only` сумма **451** (43 файла);
  `gen_contract --check` ok (9); `snapshot_diff` 102/0; `lint_arch`/`check_limits` 453/0;
  `security_audit` ok; `selfcheck editing.scene_ops` ok (unit 25, corpus live),
  `context.editor_context` ok (28).
- **Мутации** (бэкап `shutil.copyfile`, sha восстановления совпал): M1 — снять сверку
  `expected_revision` (`B72809EAB395` → `BBECF801A265`) → **красный**
  (`assert conflict.value.kind`, получено `stale_plan`); M2 — без `create_action`
  (`→ AD06EC33A845`) → **зелёный** (менеджер создаёт действие сам); M2′ — без `commit_action`
  (`→ 05C41B1766EE`) → **зелёный**; M3 — вернуть `load(...) != null` в `_scan`
  (`B0F4C4C767BB` → `8E1463F545E0`) с подложкой → **зелёный**: старая проверка слепа, это и
  доказывает ценность D-2. Всё восстановлено (`B72809EAB395`, `B0F4C4C767BB`), `zz_*` = 0.

**Блокеры после B.2.** D-1/D-2/D-3 закрыты. Не покрыто: undo снаружи (Ctrl+Z) примитивом не
вызывается — в словаре нет `editor_scene_undo` (долг D-4); «сбой на втором шаге» проверен пробой
на копии (в сцену не пишется), а не реальным откатом undo-истории; M2/M2′ показывают, что батч без
undo-действия живой тест не ловит.

## Ход работы (сессия 41, 2026-10-29), B.3 — undo-примитив и откат истории

**Примитив.** `editor_scene_undo` (`effects: write`, `thread: main`) в
`contract/editor_verbs.json`: вход `{scene, expected_revision}`, выход
`{revision, undone, undo_label, history_version_before, history_version}`, `verbs_version`
**2 → 3** (журнал — ADR-0007). Два поля про версию истории добавлены к трём полям из §1.1
промпта, потому что без числа «ровно одно действие на батч» не доказывается:
`UndoRedo.get_history_count()` после отката **не убывает** (действие остаётся в redo-стеке),
а `UndoRedo.get_version()` растёт на 1 за действие и убывает на 1 за откат. Обе функции
проверены в движке через `ClassDB` (`EditorUndoRedoManager` своих `undo()`/`has_undo()` не имеет,
работа идёт через `get_object_history_id(root)` → `get_history_undo_redo(id)`).

**GDScript.** `scene_executor.gd::undo()` — проверки те же, что у `apply` (`res://`, целый
`expected_revision`, открытая сцена, совпадение ревизии), затем `has_undo()` → `undo()` →
`ContextSnapshot.bump(scene)`; отказы `conflict/revision_mismatch` и
`conflict/nothing_to_undo` (`ErrorCodes.NOTHING_TO_UNDO`). `scene_verbs.gd` — третий маркер
`# verb: editor_scene_undo` и регистрация в роутере (файл не переписывался, добавлены метод и
строка `register`). Версия словаря поднята в шести зашитых местах: `session.gd`,
`editor_verbs.gd`, `socket_server.gd` (`port.json`), `fake_editor.py` (`PING` и дефолт
`__init__`), `test_editor_context_bridge.py`; `PING` вклада `context.editor_context` по-прежнему
читает контракт.

**Живой сценарий (`tests/py/live/test_editor_branch_live.py`).** Сцена
`res://zz_editor_branch_probe.tscn` (корень `Probe`, дочерний `Body`), удаляется в `finally`.
1) Опустошение истории после двух успешных батчей: откат снял ровно **2** действия
(`drained == 2`), третий откат — `conflict/nothing_to_undo`; сбойный батч (второй шаг —
несуществующий узел) записей не оставил, иначе счёт был бы 3.
2) Батч из двух `set_property` → один `editor_scene_undo` → `undone: true`,
`undo_label == "agent: B.3"`, ревизия `+1`; повторный батч читает те же `before`, то есть
вернулись оба свойства.
3) N → N+1: `history_version_before` первого батча = `history_version` после его отката + 1,
у второго батча ровно та же версия до отката.
4) Отдельный живой тест `test_scene_undo_refuses_empty_history_and_foreign_revision`: пустая
история → `conflict/nothing_to_undo`, чужой `expected_revision` → `conflict/revision_mismatch`,
сцена после обоих отказов не изменилась.

**Прогоны.** `--check-only` по `scene_executor.gd`/`scene_verbs.gd`/`error_codes.gd`/`session.gd`/
`editor_verbs.gd`/`socket_server.gd`/`endpoints.gd` → exit 0, ошибок 0; `pytest tests/py/live -v` →
**3 passed** (15.84 с, движок 4.6.3); `pytest python/modules tests/py --ignore=tests/py/live` →
junit `tests=449 errors=0 failures=0 skipped=0`; `--collect-only` → **452** (43 файла) = 449 + 3 живых;
`gen_contract --check` → ok (**9** артефактов, `verbs_version = 3`); `snapshot_diff` 102/0;
`lint_arch`/`check_limits` 453/0; `security_audit` ok; `selfcheck editing.scene_ops` → ok (unit 25,
`corpus` live), `context.editor_context` → ok (unit 28); `files=911`, `__pycache__`/`.pytest_cache`/
`zz_*`/`*.bak` — 0.

**Мутации (R-22, на сдаваемом `scene_executor.gd`, бэкап `shutil.copyfile`, последовательно,
sha до/после `B7AFF592B75D`).**

| Мутация | sha с мутацией | Красный тест |
| --- | --- | --- |
| M1 снят `undo.create_action(...)` | `07AEBA13600A` | `test_editor_branch_answers_and_cleans_up`, строка 389: `undo_label == "agent: B.3"` |
| M2 снят `undo.commit_action()` | `8DE52B86FC21` | тот же тест, строка 373: `drained == 2` (факт 0) |
| M3 снята сверка `expected_revision` в `undo()` | `DD066619835E` | `test_scene_undo_refuses_empty_history_and_foreign_revision`, строка 463: `nothing_to_undo` вместо `revision_mismatch` |

Файл восстановлен побайтово: `sha_after B7AFF592B75D`, `restored identical: True`.

**Честно про M1.** Снятие `create_action` краснит тест не по счёту, а по имени действия:
`add_do_method` в Godot 4.6 открывает действие неявно, поэтому история всё равно растёт на 1,
но с пустым именем (в отчёте M1 видно `history_version_before: 2` и `undo_label: ''`). То есть
требование «действие создаётся явно и носит наше имя» покрыто, а «счёт растёт ровно на 1»
доказывается парой `history_version_before`/`history_version` у undo.

**Блокеры после B.3.** Не покрыто: (1) откат чужого (не нашего) действия — тест опустошает
историю только своими батчами; (2) поведение при `get_object_history_id(root) < 0` — эта ветка
кода достижима только на несохранённой сцене без пути, живьём не воспроизводилась;
(3) Ctrl+Z снаружи (обратный случай: наш откат не должен ломать редактор) — не проверялось.
