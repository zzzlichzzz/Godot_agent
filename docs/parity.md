# Паритет: старый агент → новый

Статусы: `skeleton` (папка есть, кода нет), `ported` (перенесено и доказано),
`deviates` (сделано иначе, причина в `deviations.md`), `dropped` (решено не переносить),
`new` (в старом не было).

Подробности «что делает старый файл» — в `docs/mapping.md`. Здесь только счёт.

## project_text — текст и файлы проекта

| Возможность | Модуль | Старый код | Статус |
|---|---|---|---|
| `read` | `project_text.read` | `godot_tools/project_tools.py` (read/patch) | **ported** (C.25, принято аудитом 2026-11-03, сессия 77): публичный инструмент `read` (артефакт `contract/capabilities/read.json`, контракт 28), selfcheck ok 38/35 ×2, snapshot 35/35, BOM/CRLF→LF/quota — корпус, лист [porting/project_text.read.md](../porting/project_text.read.md) |
| `search` | `project_text.search` | `godot_tools/project_tools.py` (search) | **ported** (2026-10-27) — эталон [corpus/project_text/search](../../fixtures/corpus/project_text/search/manifest.json), лист [porting/project_text.search.md](../porting/project_text.search.md) |
| `tree` | `project_text.tree` | `godot_tools/project_tools.py` (обход, дерево) | **ported** (C.25, принято аудитом 2026-11-03, сессия 77): internal-only сервис без публичного инструмента — `provides_tools=()`, `internal_services=("project_text.tree",)`, `entrypoints={"build": build}` (D21/D22, ADR-0006 уточнён), selfcheck ok 23/22 ×2, snapshot 22/22, лист [porting/project_text.tree.md](../porting/project_text.tree.md) |

## code_intel — понимание кода

| Возможность | Модуль | Старый код | Статус |
|---|---|---|---|
| `functions` | `code_intel.functions` | `godot_tools/gd_functions.py` | **ported** (2026-10-27) — эталон [corpus/code_intel/functions](../../fixtures/corpus/code_intel/functions/manifest.json), лист [porting/code_intel.functions.md](../porting/code_intel.functions.md) |
| `usages` | `code_intel.usages` | `godot_tools/symbol_refactor_part1/part2.py` (find_references) + `gd_semantic_parser.py` | **ported** (2026-10-27) — эталон [corpus/code_intel/usages](../../fixtures/corpus/code_intel/usages/manifest.json), лист [porting/code_intel.usages.md](../porting/code_intel.usages.md) |
| `analyze_rename` | `code_intel.usages` | `symbol_refactor_part2.py` (analyze_rename) | **ported** (2026-10-27) — эталон [corpus/code_intel/analyze_rename](../../fixtures/corpus/code_intel/analyze_rename/manifest.json), лист [porting/analyze_rename.md](../porting/analyze_rename.md) |
| `functions --card` | `code_intel.function_card` | `godot_tools/function_card.py` | skeleton |

## scene_model — модель сцены

| Возможность | Модуль | Старый код | Статус |
|---|---|---|---|
| `scene` | `scene_model.tree` | `project_tools.describe_scene` | ported (C.3: corpus40/40, text bytes + full projection; selfcheck128, read-only; принято аудитом 2026-10-29, сессия 50) |
| `node` | `scene_model.node_info` | `node_refactor.py` | ported — C.4: 65/65, selfcheck unit247, read-only; принято аудитом 2026-10-29 (сессия 52) |
| `connections` | `scene_model.connections` | `scene_deps.py`, display `project_tools.describe_scene` | ported — C.5: corpus25/25, selfcheck108, read-only; принято аудитом 2026-10-29 (сессия 54) |
| `scene_deps` | `scene_model.scene_deps` | `scene_deps.py:271/362`, `main.py:1904/1930` | ported — C.5: corpus40/40, selfcheck176, handlers differential133gd, read-only; принято аудитом 2026-10-29 (сессия 54) |
| `node_rename_preview` | `scene_model.node_rename` | `node_refactor.py` prepare225–541, formats/shared lookup/public lint; apply/undo/executor вне C.6 | **ported** — корпус36/36, selfcheck162ok, read-only CLI8/8; этап7, **принят аудитом (WORKLOG56)** |
| `node_reparent_preview` | `scene_model.node_reparent` | `node_refactor.py` prepare542–797, append-only formats/shared lookup/public diff+lint; apply969/editor вне C.7 | **ported** — C.7 corpus32/32, selfcheck155ok, read-only; **принято аудитом 2026-10-30 (WORKLOG58)** — пересъёмка 32/32, 2014/3 прогоны, M2–M8 красные, M1/M5 эквивалентны с доказательством |
| `node_delete_preview` | `scene_model.node_delete` | `node_refactor.py` prepare800–966, body/full spans, ordered warnings/no script patches; apply969/editor вне C.7 | **ported** — C.7 corpus27/27, selfcheck131ok, read-only; **принято аудитом 2026-10-30 (WORKLOG58)** — пересъёмка 27/27 с порядком warnings, M3/M4/M6/M7 красные |

## engine_kb — знание о движке

| Возможность | Модуль | Старый код | Статус |
|---|---|---|---|
| `engine` | `engine_kb.engine_info` | `gd_api_cache.py`, `agent_api_cache/` | skeleton |
| `api` | `engine_kb.class_api` | `gd_api_cache.py:19–27,115–216`, typed read-only projection | ported (C.11, принят аудитом 2026-10-31): read-only `api` поверх существующего `api_cache` (`snapshot()`, ADR-0009), `classes()` не изменён; корпус 26/26 переснят аудитором, дифференциал 296 запросов на 16 кэшах + реальный кэш 2 004 630 B — 0 расхождений; `docs/porting/engine_kb.class_api.md` |
| (кнопка «обновить справочник») | `engine_kb.api_cache_refresh` | `gd_api_cache.py` | skeleton |

## editing — правки через воронку

| Возможность | Модуль | Старый код | Статус |
|---|---|---|---|
| `write_preview` | `editing.write_preview` | `transaction_actions.py`, `symbol_refactor_part3.py:prepare_rename` | **ported** (корпус 16/16, `effects=write`, в проект не пишет; `write_apply` — часть 2) |
| `write_apply` | `editing.write_apply` | `transaction_actions.py`, `symbol_refactor_part3.py:apply_prepared_rename` | **ported** (корпус 15/15 по итоговым байтам, идемпотентность/лок/recovery — тесты; пишет только этот инструмент, R-12) |
| `write_rollback` | `editing.rollback` | `transaction_actions.py`, `history_manager.py` | **ported** (корпус 4/4 сверяет `before_bytes`: своего отката у эталона нет; побайтовое восстановление, `already_rolled_back`, `recover(ports)`) |
| `paths_preview` | `editing.paths_preview` | `file_refactor.py` | **ported** (C.21, принято аудитом 2026-11-02, сессия 76): read-only preview, selfcheck 58/25, snapshot 25/25; запись и перенос файлов — `editing.file_refactor` (C.22, ported) |
| (переименование файла) | `editing.file_refactor` | `file_refactor.py` | **ported** (C.22, принято аудитом 2026-11-02, сессия 76; ячейка и статус — штатная правка аудитора 2026-11-03, сессия 77): prepare/apply rename/move/dir_case/replace_raw, компаньоны `.import`/`.uid`, EFFECT_INTENT WAL (ADR-0016), selfcheck ok 124/52, snapshot 52/52 |
| `analyze_rename --apply` | `editing.symbol_rename` | `symbol_refactor_part3.py` | **вклад** (этап 6, 2026-10-27): `MODULE` без `provides_tools`, `contributes_to=("editing.write_preview","code_intel.usages")`, `COMPILER = OperationCompiler(op="symbol_rename", compile=compile_plan)`; `selfcheck` ok (unit 15), корпуса нет по построению |
| (правки сцены) | `editing.scene_ops` | `scene_actions.py`, `agent_scene_executor.gd` | **в работе** (этап 4, 2026-10-28) — батч `add_node`/`set_property`/`attach_script`/`connect_signal` **одним** undo через мост (`editor_scene_plan` dry-run + `editor_scene_apply`), лимиты 64 операции / 4 КиБ, `expected_revision` + `plan_digest`, неизвестная `op` рушит батч; доказано фейком (25 тестов), живой `apply` — долг `needs_live`; лист [porting/editing.scene_ops.md](../porting/editing.scene_ops.md) |
| (правки `.tres`) | `editing.resource_ops` | `resource_actions.py`, `agent_resource_executor.gd` | **ported** (C.23+C.24, принято аудитом 2026-11-03, сессия 77): вклад в write_preview — `provides_tools=()`, `contributes_to=("write_preview",)`, `internal_services=("resource_ops",)` (D14–D17), transformed bytes + ограниченный `replace_raw` через общую воронку (ADR-0017, D18/D19), selfcheck ok 503/271, snapshot 271/271 |
| `split_gd_scan/plan` (C.14 scan + C.15 plan + C.16 F6/F7 — принято 2026-10-31) | `editing.split_gd` | `godot_tools/split_gd.py` (`scan_refs`, `file_inventory`, `plan_split`; запись отложена) | ported (C.14/C.15, C.16 принят аудитом 2026-10-31: тексты отказов из домена, `newline` из сырых байтов; запись — C.17) |
| `split_scan/plan` (C.17+C.18 приняты) + `split_apply` (C.20 принят 2026-11-01) | `editing.split_py` | `godot_tools/split_refactor.py` (`scan_refs:127`, `file_inventory:270`, `plan_split:407`, `_render_facade:656`, `apply_prepared_split:718`) + `arch_map.py` | ported относится только к принятым C.17+C.18; C.19/F4 принят 2026-11-01. C.20 реализует strict `split_apply(path, plan)` и transactional `create`/`delete` через ADR-0005 WAL; corpus097–108, selfcheck583/107, non-live4281, snapshot832, live3. C.20 принят аудитом 2026-11-01 (сессия 76): non-live4281, snapshot832, selfcheck583/107, live3 и rollback/recovery проверены независимо; stage 7 не менялся |

## verification — проверки

| Возможность | Модуль | Старый код | Статус |
|---|---|---|---|
| `verify` (агрегатор) | `verification.check` | `tools/agent_bridge.py:_check_one_path` (пайплайн проверок) | ported (C.9, принят аудитом 2026-10-30; C.13 — 2026-10-31: `.gd` = lint + API вкладом `api_check`, F2/F3 закрыты): read-only gd/tscn/py/json/cfg;38actual-old/0diff,selfcheck91,2428nonlive+3live,507fullcorpus/0diff;M1–M8/P1–P3,12reverseSHA; [лист](porting/verification.check.md) |
| `gd_lint` (текст) | `verification.gd_lint` | `gd_lint.py` | **ported** (2026-10-29, C.2) — literal корпус37/37, selfcheck ok/unit126, read-only; [лист](porting/verification.gd_lint.md), [корпус](../../fixtures/corpus/verification/gd_lint/manifest.json); полный wiring-тест не закрыт |
| `check` (сцена) | `verification.tscn_lint` | `tscn_lint.py` | skeleton — **C.8 реализовано, этап6, ожидает независимого аудита (WORKLOG59), не ported**: read-only fixed/changed/stringproblems;65actual-old/0diff,315native,2337nonlive+3live,469fullcorpus/0diff; [лист](porting/verification.tscn_lint.md), промпт `porting/_start-prompt.tscn_lint.md`; агрегатор/API/repair вне среза |
| `api_check` (API) | `verification.api_check` | `gd_api_check.py` | ported (C.12, принят аудитом 2026-10-31): read-only `api_check(path, content)`, `MAX_PROBLEMS 6`/дедуп/дословные сообщения, `checked`+`unavailable`, один `snapshot()` (ADR-0009), узкий app-шов к `inheritance.py` (ADR-0010); пересъёмка 52/52, дифференциал 756 вызовов 0 расхождений, selfcheck 206/52; историческая находка F2 (`errors` без `denied`). **C.13 готов к независимому аудиту, не принято:** вклад в verify, F2 `invalid_input,denied`, F3; selfcheck check188/75 и api_check206/52, snapshot622/0. Приёмка C.12/статус ported сохранены |
| (headless-прогон) | `verification.headless` | `godot_headless_validation.py`, `agent_headless_validator.gd` | skeleton |
| `check_action` | `verification.action_judge` | `answer_judge.py` | skeleton |
| (проверка игры) | `verification.runtime_checks` | `runtime_checks.py` | skeleton |

## context — контекст для модели

| Возможность | Модуль | Старый код | Статус |
|---|---|---|---|
| `ask` | `context.ask` | `librarian.py` | skeleton (L2a MODULE1/public ask submitted 2026-11-11; selfcheck ok0 x2, module104/native strings/profile logs and history/no migration, reference213 separate, six new-code kills and final D57 regressions x2; independent acceptance pending, not ported) |
| `context` | `context.gather` | `gather_context.py` | **ported** (этап 6, 2026-10-27): `selfcheck` ok (unit 33, корпус 3/0), артефакт `contract/capabilities/context.json`; секции `project`/`tools`, вклады через `ctx.registry.contributions("context")`; новые поля (`query`, `symbols`, `diagnostics`) — следующий срез, см. `docs/porting/context.gather.md` |
| `context.editor_context` | `context.editor_context` | `server/editor_context.py`, `agent_editor_context.gd` | **ported** (этап 7, 2026-10-28; контракт — этап 4, принят аудитом 2026-10-27): ADR-0007 (слушает GDScript, Python — клиент; SEC-03 переписан), `contract/editor_verbs.json` (`verbs_version: 1`, три read-примитива, `result_schema`), лист `docs/porting/context.editor_context.md`; владелец `context.gather` собран (этап 6) — вкладу есть куда вкладываться; исполнение — `docs/porting/_start-prompt.editor_bridge_a.md`. **Часть A исполнена 2026-10-28**: транспорт `python/substrate/editor/**` (кадр 4 байта BE, handshake, токен в каждом кадре, один in-flight, `retry`), сервер `editor/bridge/**` на GDScript с тремя `# verb:` и `port.json`, вклад секции `editor` (`TOOLS = ()`, `CONTRIBUTIONS = (SECTION,)`, `environment="editor"`, порт `editor` во всех профилях), ответ проверяется `kernel.schema.validate` по `result_schema`; `_handlers` снят из словаря примитивов (`gen_contract --check` ok, 8 артефактов, без строки долга); `selfcheck context.editor_context` ok (unit 27), корпуса нет намеренно (`uptime_s` и абсолютные пути недетерминированы); живой Godot - харнесс `needs_live`, приёмкой не считается; далее часть B (`editing.scene_ops`) |
| (снимок рантайма) | `context.runtime_snapshot` | `runtime_debug.py` | skeleton |

## assistant — диалог

| Возможность | Модуль | Старый код | Статус |
|---|---|---|---|
| (чат: K1 read-only + CLI, не server/history UI) | `assistant.chat` | native main.py semantic specification; ADR-0021/D70-D73; agent-loop.md | new |
| (история) | `assistant.history` | `server/api_history.py` | skeleton |
| (выбор модели) | `assistant.model_choice` | `api/providers.py`, `api/model_cache.py` | skeleton |
| (какой канал отвечает) | `assistant.routing` | `backends/api_backend.py` | skeleton |

## project_ops — операции с проектом

| Возможность | Модуль | Старый код | Статус |
|---|---|---|---|
| `project_settings` (чтение) | `project_ops.settings_get` | `project_settings_actions.py` | skeleton |
| `project_settings` (запись) | `project_ops.settings_set` | `project_settings_actions.py`, `agent_project_settings_executor.gd` | skeleton |
| (каркас проекта) | `project_ops.architecture` | `project_tools.py` (autoload, обзор) | skeleton |

## Сводка

| Область | Модулей | `ported` |
|---|---|---|
| project_text | 3 | 1 |
| code_intel | 3 | 0 |
| scene_model | 7 | 0 |
| engine_kb | 3 | 0 |
| editing | 10 | 1 |
| verification | 7 | 0 |
| context | 4 | 1 |
| assistant | 4 | 0 |
| project_ops | 3 | 0 |
| **Итого** | **43** | **3** |

Строк-возможностей в таблицах больше, чем модулей: агрегатор `check` — теперь
модуль-владелец `verification.check`, а линт, сцена, API и headless дают в него
вклады `contributes_to: check` (ADR-0004). Два инструмента могут жить в одном
модуле (`split_scan` + `split_plan`, `usages` + `analyze_rename`), поэтому
«инструмент ≠ папка» — но у каждого модуля в шапке `module.py` написано, какие
инструменты он обслуживает (`# tool:` / `# tools:`) и в какие составные входит
(`# contributes:`).

Не переносится (осознанно): `minilich/`, `api/{catalog,doh}`,
`server/{dashboard,server_state,port_guard}`, одноразовые съёмщики, `selfcheck.py`,
`plugin_universal.gd`, `symbol_refactor.py` (фасад).

### Корректирующий срез F1 / C.10

2026-10-31 пользователь разрешил отдельный ремонт BOM-декодирования основного
файла gd_lint/verify. Это дельта принятых C.2/C.9, а не новый инструмент/модуль;
исторические ported не снимаются. Текущая стадия и доказательства —
`docs/PROGRESS.md` → F1 и `docs/porting/verification.bom.md`; независимая приёмка
дельты ещё не выполнена. Candidate/instance tscn остаются byte-identical.

Отложено, но не отменено (Q-08): `browser/`, `parsers/`, `backends/browser_backend.py`,
`tools/{arena_*,capture_*,audit_*}`. Решение от 2026-10-27: переносятся в
`substrate/llm/browser` **как есть** — стратегия «ported verbatim» (R-08), потому что
схема обкатана: отдельный профиль `%LOCALAPPDATA%\Godot_AI_Profile`, Chrome
запускается обычным процессом и selenium подключается через `debuggerAddress`
(`navigator.webdriver === false`), спуф `visibilityState` — только по флагу сайта.
Улучшать при переносе запрещено (R-21); порядок — после первой волны механик.

B-1 базис **принят независимым аудитом** (2026-11-04, сессия 78): transport-эталоны + read-only фасад,
решения D24/D25/D26/D27 и принятый D28, лист `docs/porting/browser.md`.
SEC-03 принят независимым аудитом сессии78; STOP снят. Финальная live-стадия зелёная:
двойной wire35/35/file://2/2, live3/3 + sandbox restore live1/1, bounded owned close;
собственная live-мутация red/exactrestore/green, гейты/focused/security зелёные.
Аудит: tree-final 3937 файлов byte-exact (граница — только parity/лист/WORKLOG), focused 93/93,
full security 237 pass/2 прежних skip, гейты ok/0, двойная собственная live-батарея 3/3 + 1/1.
Замечание: в первом live-прогоне аудита окно Chrome кратко (~0.4 с) вышло в foreground и к снимку
не было свернуто по OS (свежий disposable-профиль, pinned запуск без правок фасада); полный повтор
батареи — 3/3 + 1/1 чисто. Это гонка старта Chrome, а не механика фасада; детерминизм no-focus
усилить отдельным разрешённым срезом до B-2 или в B-2. Принят базис — не ported всего browser;
B-2/B-3 и parser/backend остаются deferred. Таблица 44 механик не меняется.

B-2 (net_monitor) **принят независимым аудитом** (2026-11-04, сессия 78): D29-допуск
FILE_MAX 400→600 для verbatim-эталонов `substrate/llm/browser/` (классовое правило в
check_limits, отклонение в deviations), корпус `fixtures/corpus/browser/b2` (12 кейсов
из native-тестов), verbatim `net_monitor.py` 24206 B `54167afb…` — byte-exact vs native
проверено. Аудит: фокус 16/16 ×2, свои мутации ×2 (не сбрасывать `_generating` — 7 красных
c05/c06/c07/c09/c10/c12 + байт-пин; не сбрасывать `_last_http_error` — 2 красных c02 + байт-пин),
byte-exact restore, green 16/16; гейты ×4 (lint 569/0, limits ok/2 прежние, contract 28/0,
security ×2 ok/0); focused B-1 93/93, full security 237 pass/2 прежних skip. Гигиена: pyc 0
(сняты артефакты пробника), сентинелы 4 файла, reports 44, uid 86, project.godot 335 B.
Долг мутационного покрытия: reset-pop HTTP-ошибки не имеет независимого кейса (найдено
пробником, добавить в B-3-контракт). Live-фаза net_monitor без реального сайта честно
невозможна — нужен live-этап с записанным сайтом; вербатим не имитировался. Это принят
срез, не ported всего browser; B-3 остаётся deferred.
Статус: B-2 принят аудитом; не ported всего browser. Лист
`docs/porting/browser-b2.md`.


B-3 эталонный срез **принят независимым аудитом** (2026-11-04, сессия 78): пять
byte-exact эталонов (sites 06da9270…, live_input cd2c6ccf…, ai_studio_net 3d9a3fb4…,
qwen_net 57d1ab2b…, backends/browser_backend 21e5e911…), корпус 32×2 / фокус 45×2,
полный non-live 5476 pass/2 прежних skip. D30 (SEC-19 многострочные site flags)
принят тем же аудитом: свои мутации — kimi False→True в production sites.py даёт
byte-pin+corpus red 2 и production-страж SEC-20 red 1 («спуф поднят с false на
true»), byte-restore → ok/0; удаление D30-call — ровно 19/28 sec19-красных,
restore → ok/0. Границы соблюдены (B-1/B-2/контракт/стражи frozen). Д31 ограничение:
это эталонный срез — рабочий browser runtime (parsers, server_state, sys-связки,
recorded-site live) — отдельный мандат.

## Порядок переноса (снизу вверх)

1. `kernel` + `formats` + `substrate/fs` — на них опирается всё.
2. `project_text.*` — чтение и поиск: самый простой сквозной путь.
3. `engine_kb.*` — кэш API и справочник класса.
4. `code_intel.*` — функции, ссылки, карточка.
5. `verification.*` — линт, API-проверка, headless.
6. `scene_model.*` + примитивы редактора — первая пара «Python решает, GDScript делает».
7. `editing.*` — воронка записи целиком, включая откат.
8. `context.*`, `assistant.*`, `project_ops.*` — после того как домен устойчив.

Каждый шаг: корпус входов → снапшот → перенос → двойной прогон (R-07…R-09).


## J1 — отдельная регистрация assistant.judge (2026-11-13)

| Возможность | Модуль | Старый код | Статус |
|---|---|---|---|
| judge | assistant.judge | godot_tools/answer_judge.py + native closure | skeleton / stage0 / STOP §0; A1 не начат; лист porting/answer-judge.md |

Это новый публичный judge по мандату J1; исторический check_action /
verification.action_judge остаётся skeleton/stage0 и не закрыт этой регистрацией.
Перенос и независимая приёмка не заявлены; AST/import/limits/G blockers — в листе.


### J1a / A1 STOP (2026-11-13)

`assistant.judge` не ported: A1 этап3, native118×2/0diff и genuine red121/1. Новые STOP: SEC-03/SEC-04 на неизменённой byte-exact headless-проекции; отсутствующий default primitive harness. Следующее действие: независимое точечное решение, затем same-ID A1 green/mini-seal. D58–D61 уже санкционированы; никаких новых исключений checker не принято.


### J1b / A1 фактическая проверка (2026-11-14)

D62/D63 implemented с exact-path/byte-offset AST-исключениями, B-1/PROC_ALLOWED сохранены; D64 exact1701 B/default+explicit green. Genuine red192 collected/135failed/57passed/0errors → 192 same-ID green, все прежние121 failure ID зелёные; native118×2/canonical118×2/0diff. Real Godot4.6:4 own-sandbox default-harness probes/8 engine processes/0diff/no source writes. Mutants:15 checker+2 D64 killed/0survivors, exact SHA/EOL restore/same-ID green. Full non-live×2:7400passed/2 historical WinError1314 skips; frozen230/API253/project288×2, gates×2 и post-resource gates0. Actual selfcheck assistant.judge fail/exit1 (missing MODULE), probe unknown_tool/exit1; context.ask ok/exit0,104unit/213corpus. Aliases0, MODULE/D59/D60/A2 не implemented. A1 reference mini-seal готовится, MODULE не ported, independent acceptance pending. Все rejected setup/invocation/scope records сохранены, native originals/NN/browser-live/production HTTP нетронуты.

Подэтап reference не закрывает historical verification.check/live fate или assistant.judge MODULE. Frozen230 membership сохранён: browser141 + B-1 AST72 + B217; D51 detector34 дополнительно в full/security/mutations. Мини-seal — integrity, не самостоятельная приёмка.
Следующее действие: После A1 mini-seal: A2 native cases/corpus×2 для scene/editing/actions; D60 genuine red exact-six caps перед переносом.


### J1 / A2 corpus-first (2026-11-15)

A1 independently accepted reference остаётся неизменным. A2 private native214 ×2/0diff до переноса, targets6 ещё отсутствуют. assistant.judge не ported; historical scene_ops/resource/apply/live фаты этим корпусом не закрываются.


### J1 / A2 submitted reference evidence (2026-11-15)

A2 reference-read/prepare проверен, не public MODULE. Six sources152941 B/EOL byte-exact; native214+supp1 ×2/canonical214+supp1 ×2/0diff, full snapshots no-write. Genuine A2220/221 red → same221green, D6013/26 red → same26green; restored all249green. 6 A2+4 D60 mutants killed/0final survivors, exact bytes/SHA/LF/CRLF restore/same-ID green. Первый ambiguity survivor сохранён: wrongly named old negative-case не создавал candidates; gap закрыт новым genuine native supplement×2 и теми же mutant bytes, frozen214 не переписан. Full non-live7649passed ×2 + ровно два historical WinError1314 skips, no added skips/xfails; collected7651 и executed IDs/order exact. Frozen230/API253/project288 ×2, все288 manifest IDs. Gates/security ×2 green. Real Godot4.6:4 native/canonical reference probes/8 processes, default harness,0diff/no source writes/owned validation leftovers0; это headless structural validation, не semantic editor apply/rollback и не public judge probes. Actual selfcheck assistant.judge fail/exit1 (missing MODULE) ×2; actual probe judge unknown_tool/exit1 ×2. Actual context.ask selfcheck ok/exit0 ×2,104unit/213corpus. D60 exact-six caps реализованы minimal two-insertion checker delta, old constants/caps сохранены; D59/A3/B/+15 aliases/MODULE/public corpus не реализованы. Rejected baseline assumptions, freeze path, pytest basetemp setup, outer120s partial canonical capture, singular collected-item receipt, double-q collect verbosity и initial survivor сохранены, не засчитаны как successful evidence. A1 accepted record read-only; mini-seal/ZIP фиксируют integrity, не самостоятельную приёмку.

Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/answer-judge-J1-A2-20261114/
Следующее действие: После A2 mini-seal/ZIP: A3 symbol_refactor native cases/observations ×2 до missing-code red; затем B/D59/adapter/MODULE.


### J1 A3 reference evidence (2026-11-15)

A3 reference80 native×2/canonical×2/0diff; genuine85/86 missing-code red → same86 green, four critical mutants killed/0survivors/exact SHA/LF/CRLF/same-ID restore. Five native140474 B byte-exact; part1 CRLF824 сохранён. Real Godot: native/canonical rename prepare→batch,2 probes/4 processes,0diff/no project writes/owned leftovers0. Первый live fixture fail (unscanned class_name) сохранён; только owned fixture получил explicit preload, ни source, ни frozen80 не менялись. Actual gates0; actual selfcheck assistant.judge fail/exit1 missing MODULE и probe unknown_tool/exit1. A3 не закрывает public MODULE, apply/rollback, historical host/editor-live fates; independent acceptance не объявляется. Полный финальный regression×2 остаётся B/final.


### J1 public judge — final submitted parity (2026-11-15)

J1 полностью реализован и передаётся на независимый аудит: public assistant.judge/judge, read/idempotent, fs+librarian, strict input/result envelope, domain pure/app7. Genuine native74×2 → actual build_agent→agent.call74×2/0diff; final ordinary public corpus74×2/0diff. Actual selfcheck assistant.judge ok/exit0×2 (8unit/74corpus), context.ask ok/exit0×2 (104/213). Final full7923collected/7921passed×2, exact ordered once-only IDs, только два исторических symlink WinError1314 gaps. Frozen230/API253/project288×2, все288 IDs, security/layers/limits/contract×2 green. Четыре actual CLI probes: answer0/invalid_input1/denied1/no-write0; owned state only, no project writes. Final185 new tests green;14 current-submitted mutants killed/0survivors, byte/SHA/LF/CRLF restores/same-ID green. Fifteen Python references+GD harness436437 B byte-exact; part1CRLF824; old35 binding prefix exact,total50/rawLF84. D59/D65–D69 только в санкционированных границах. Native parser/quartet/parser_base/security/check_limits и shared snapshot/selfcheck/generator unchanged. A1/A2/A3 full readback/seal/archive pins exact, только уже раскрытая A1 empty-file inode cohort1430. Rejected invocations/full failures/sample-write defect и initial A2 survivor не удалены; D68 genuine2red→same2green, D69 genuine52fail→same-ID green, fixture isolation repaired only in new B scope, no foreign-parent adoption. Один поздний full run дал importlib source_to_code MemoryError: cause unestablished; unchanged node alone exit0, fresh exclusive full7921pass/2oldskips exit0; failed run retained, not counted. Полный final ZIP включает byte-exact7 mini-seals/8 prior archives, включая rejected incomplete A1 ZIP; их наличие не означает принятия rejected artifacts. Prior real Godot reference probes retained; no public apply/rollback/editor semantic/live/NN/browser/HTTP claim. MODULE_ready=true; independent_acceptance=false, audit pending.

| Tool | Module | Status | Evidence |
|---|---|---|---|
| judge | assistant.judge | ported (submitted; independent audit pending) | actual selfcheck0×2/corpus74×2/full7921×2/14killed |

Исторические skeleton/STOP/reference записи сохранены. Это не закрывает отдельные verification.check, runtime/editor apply/live или NN механики.

## T1 / T-A — отдельное native substrate-замыкание (2026-11-21)

Шесть обязательных godot_tools и доказанные зависимости function_card/log_reader
перенесены byte-exact; opt-in NativeBindings не меняет принятые base50/84LF,
K1 gateway или исторические corpus-наблюдения. См. D74/D75, ADR0074 и
`docs/porting/T1-godot-tools.md`. Native29×2; 71 same-ID GREEN×2; три убитых
мутанта с точным восстановлением; full8044passed+два исторических skip×2;
frozen230/API253/project288×2; финальные genuine gates/selfchecks×2; настоящий
probe и пинованный native Godot4.6 вызов×2. Отклонённые попытки сохранены.

Это закрытие T-A substrate-пакета, не доказательство native apply/live-provider
или завершения T-B/T-C/T-D. Исторические строки/судьбы не удалены. Mini-seal/ZIP
публикуется последним отдельно; независимое принятие не заявляется.

## T1 / T-B — specification before implementation

| Инструменты | Модуль | Источник | Статус |
|---|---|---|---|
| assistant_plan/confirm/rollback/turn | assistant.write | native main confirmation + transaction/node/symbol/file prepare; existing WAL funnel | ported in T-B file/WAL scope: native/corpus/clients paired, full8122+2historical skips×2, six selfchecks/gates×2, exact-restored mutants; seal/ZIP published with every physical member exact/bad0 (WORKLOG10909–10916); structural candidate/editor/provider/browser live remain T-D/separate |

См. `docs/porting/assistant.write.md`, SEC-T1-WRITE. Ни native apply, ни model
action не дают разрешения. Старые editing.write_apply/rollback статусы и судьбы
сохраняются; новый public write loop доказывается отдельно.

## T1 / T-C — local HTTP/MCP transport closure

HTTP/MCP entrypoints route to one rebuild Agent; session-owned native references,
external profiles, Host/Origin/auth/body bounds, raw+identity endpoint inverse,
owned gateway close. Native port_guard is reference-only, never an orphan killer.
Production71GREEN×2/native auth5×2; full8193passed+two historical symlink skips×2
preserves A/K1/published-B ordered IDs/phases. Frozen230/API253/project288×2;
six mechanic selfchecks verdict ok/exit0×2 and four genuine gates×2. Real MCP
child pipes/native-composed WSGI clients×2 complete plan/denied bypass/confirm/
rollback and restore physical trees exactly; no real network/provider/browser.
Four current-byte mutants killed/exact restored; saved raw evidence read back
against unchanged repository inventory. See ADR0085/SEC-T1-LOCAL/T1-channels.
This is transport closure, not editor/provider/browser-live or independent
acceptance. Next seal LAST/full sibling ZIP, then T-D production integration.

## T1 / T-D — editor safe/offline closure

33 native production GD+9 case-only drivers=42 accounted;45 exclusive native/
adapted GD/scenes/config/reference files transferred, root config preserved.
Three guarded SDKs only in external owned overlay; actual native/full-report
seven-case parity×2, generated witnessed IDs/raw-hash-only normalization, refusals
and empty sentinel retained. One default Agent/B four confirm/rollback cycles
and three refusals×2; actual UI9 captured cases×2/plugin owned user namespace×2.
Final8281pass+2historical skips×2/A-K1-B-C ordered phases/frozen230/API253/
project288×2/four gates/seven selfchecks×2/15 restored current mutants; raw readback
bound to unchanged source.36 additive native facts, old corpus/tests exact.
Script/binary/escaped/external/protected and conservative scalar/config/parent
inputs fail closed: explicit parity gaps, not full native-editor semantics.
No visual desktop/provider/browser live or independent_acceptance claim. Seal
LAST/full ZIP subsequently published: D seal ed349f701870a43a01484e3060ef8663a54df3e0ee246b08766d3cb60b01cb8d,
ZIP4620f485af8ab08d3803655ac9aaa0c152bfb9303edf30466e441aadfab7af47,
128969files/127510dirs/518links,bad0/every physical member exact; no acceptance.

## T1 / T-E — final safe/offline integration, independent review next

Actual full8284passed+two historical WinError1314 privilege gaps×2, accepted A/K1/
published B/C/D ordered IDs/phases exact; frozen230/API253/project288×2; four gates/
seven selfchecks×2 ok/exit0.688Python/35generated/two original warnings.
Genuine3 documentation RED→paired3GREEN, actual positional CLI health/tools/chat/
repl/turn/plan/reject/approve/rollback×2, MCP child/native WSGI and native guarded
SDK/B/plugin owned-namespace×2; inverse files/directories exact. Six current E
mutants killed/copyfile bytes/SHA/EOL/mtime restored/same IDs GREEN; source/raw
readback exit0. Only README/docs/three new doc cases changed from sealed D;
no native/runtime/old-test/checker semantic changes. Rejected observers retained.
Script/autoload/binary/escaped/external/relative/protected/scalar/config/parent-node
fail-closed gaps, actual-socket/provider/browser/visual gaps, NN/doh.py/n8n exclusions
explicit; not blanket native parity. Final seal LAST/full physical ZIP publication
only in sibling postseal. independent_acceptance=false; final review required.
