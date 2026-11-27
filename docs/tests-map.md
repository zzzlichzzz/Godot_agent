# Карта старых тестов: судьба каждого файла (R-17)

Снято с `addons/Godot_agent/godot_agent/python/tests` (проект
`тест-плагина-ии`). Строка есть у каждого файла: отсутствие строки
означает тихую потерю покрытия.

**Как обновлять.** Судьба и механика правятся руками; строки не
удаляются (меняется только судьба). Первичный триаж сгенерирован
скриптом по именам файлов, поэтому `?` и `pending` — это места, где
нужно решение человека, а не автоматика.

**Судьбы.** `corpus` — кейсы снимаются в корпус как эталон;
`ported` — кейсы живут в тестах нового модуля; `replaced` —
проверяется на другом уровне (contract/e2e/живая проверка);
`dropped` — подсистема не переносится (причина обязательна);
`deferred` — переносится позже. `pending` — решения ещё нет.

**Семейства.** `unit` — обычный тест; `flow` — через старый хост
(Flask/мост); `live` — против живого Godot; `repro` — воспроизведение
бага; `helper` — фейк или раннер, не тест.

## Сводка

| Показатель | Значение |
|---|---|
| Всего файлов | 168 |
| судьба `corpus` | 94 |
| судьба `replaced` | 39 |
| судьба `deferred` | 29 |
| судьба `dropped` | 6 |
| семейство `unit` | 134 |
| семейство `flow` | 13 |
| семейство `live` | 12 |
| семейство `repro` | 7 |
| семейство `helper` | 2 |

## Таблица

| Старый тест | КБ | Семья | Группа | Механика (новый модуль) | Судьба | Что делать |
|---|---|---|---|---|---|---|
| `repro_check_blocking.py` | 3 | repro | check | `verification.check` | corpus | C.9: off → unavailable headless в corpus/verification/check (001/015/027/028); required/auto, blocking/infrastructure и CLI rc не закрыты, остаются следующему headless-срезу (пользователь подтвердил 2026-10-30) |
| `repro_check_truncated.py` | 6 | repro | check | `verification.check` | corpus | C.9: corpus/verification/check/036–037 сохраняет сырой truncated-ответ и дефект хвоста; согласовано полное чтение ≤4 МиБ/отказ выше лимита вместо 2 Ми символов. CLI rc/timing не закрыты |
| `repro_check_unchecked.py` | 6 | repro | check | `verification.check` | corpus | C.9: corpus/verification/check/014–018,027–028 — unsupported/headless-only/фильтр, checked=false с буквальным reason. Старые batch-счётчики/CLI rc не закрыты |
| `repro_node_rename_double_intercept.py` | 7 | repro | rename | `editing.symbol_rename` | corpus | repro: воспроизведение бага, кейс в корпус обязателен |
| `repro_plan_cwd.py` | 5 | repro | write | `editing.write_apply` | corpus | repro: воспроизведение бага, кейс в корпус обязателен |
| `repro_plan_gc.py` | 6 | repro | write | `editing.write_apply` | corpus | repro: воспроизведение бага, кейс в корпус обязателен |
| `repro_return_codes.py` | 11 | repro | write | `editing.write_apply` | corpus | repro: воспроизведение бага, кейс в корпус обязателен |
| `test_access_policy_flow.py` | 17 | flow | project | `project_ops.settings_set` | corpus | правки project.godot и политика путей |
| `test_access_policy_state.py` | 6 | unit | project | `project_ops.settings_set` | corpus | правки project.godot и политика путей |
| `test_answer_judge.py` | 16 | unit | check | `verification.check` | corpus | вклады агрегатора check и его findings |
| `test_asset_refactor.py` | 29 | unit | file | `editing.file_refactor` | corpus | переименование/перенос файлов и ссылок |
| `test_asset_refactor_live.py` | 12 | live | file | `editing.file_refactor` | corpus | переименование/перенос файлов и ссылок |
| `test_check_action_disclosure.py` | 8 | unit | check | `verification.check` | corpus | вклады агрегатора check и его findings |
| `test_client_refactor_flow.py` | 10 | flow | file | `editing.file_refactor` | corpus | переименование/перенос файлов и ссылок |
| `test_editor_context.py` | 5 | unit | context | `context.gather` | corpus | сбор контекста и поиск по проекту; **replaced** 2026-10-28: снимок редактора перенесён кейсами `python/modules/context/editor_context/tests/test_core.py`, `tests/py/integration/test_editor_context_bridge.py`, `tests/py/integration/test_editor_context_section.py`, `tests/py/contract/test_editor_context_manifest.py`; разбор `.tscn`/`.gd` в GDScript не переносился (R-14) |
| `test_external_move_sync.py` | 9 | unit | scene | `scene_model.node_rename` | corpus | правки .tscn и путей узлов |
| `test_file_refactor.py` | 13 | unit | file | `editing.file_refactor` | corpus | переименование/перенос файлов и ссылок |
| `test_file_refactor_flow.py` | 7 | flow | file | `editing.file_refactor` | corpus | переименование/перенос файлов и ссылок |
| `test_file_refactor_live.py` | 12 | live | file | `editing.file_refactor` | corpus | переименование/перенос файлов и ссылок |
| `test_find_symbol_usages.py` | 6 | unit | context | `code_intel.usages` | corpus | триаж 2026-10-27: механика была указана неверно (`context.gather`); 10 тестов проверяют ровно `usages` — declaration + ссылки, координаты и confidence, `nothing_is_written`, `dynamic` у строки, `probable` вместо ошибки, запрос без `new_name`, `by_link`, плохой locator, комментарий не ссылка, read-only. Кейсы 1–4, 6–8, 10–12 корпуса `fixtures/corpus/code_intel/usages/` |
| `test_find_usages_reason.py` | 11 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages. Аудит 2026-10-27: доводы/`note` (`probable` с причиной, `proven`) проверяются в `usages` (кейсы 006/013 корпуса), а решение «переименовывать или нет» — `editing.symbol_rename` и `analyze_rename` |
| `test_function_card.py` | 15 | unit | code | `code_intel.function_card` | corpus | триаж 2026-10-27: тестирует `godot_tools/function_card.py` и мост `functions --card` (тело, символы, связи) — это отдельная механика, не `code_intel.functions` |
| `test_gather_context.py` | 6 | unit | context | `context.gather` | corpus | сбор контекста и поиск по проекту |
| `test_gdscript_move_fixes.py` | 5 | unit | scene | `scene_model.node_rename` | corpus | правки .tscn и путей узлов |
| `test_gdscript_wiring.py` | 41 | unit | code | `verification.gd_lint` | corpus | триаж 2026-10-27: 41 проверка — ключи локализации `_t()` RU/EN, порядок `%s`, наличие обработчиков из `.connect()`; к функциям `.gd`, к `code_intel.functions` и к `formats/gdscript.py` отношения нет. Аудит 2026-10-27: четыре группы кейсов живут в двух механиках — (1) существование ключа в RU и EN, (2) совпадение наборов ключей RU/EN, (3) число и порядок `%s`/`%d` → `editor/core/i18n`; (4) каждый обработчик из `.connect()` объявлен в том же файле → `verification.gd_lint` |
| `test_godot_executor_live.py` | 5 | live | check | `verification.check` | corpus | вклады агрегатора check и его findings |
| `test_godot_headless_validation.py` | 10 | unit | check | `verification.check` | corpus | вклады агрегатора check и его findings |
| `test_godot_live.py` | 3 | live | check | `verification.check` | corpus | вклады агрегатора check и его findings |
| `test_headless_validator_live.py` | 4 | live | check | `verification.check` | corpus | вклады агрегатора check и его findings |
| `test_high_level_actions.py` | 5 | unit | plan-insert | `editing.write_preview` | corpus | выбор «вставить/перезаписать» и компиляция действий настроек |
| `test_high_level_flow.py` | 4 | flow | plan-insert | `editing.write_preview` | corpus | выбор «вставить/перезаписать» и компиляция действий настроек |
| `test_history_journal_safety.py` | 13 | unit | write | `editing.write_apply` | corpus | воронка, журнал, откат, stale (ADR-0005) |
| `test_insert_plan_choice.py` | 4 | unit | plan-insert | `editing.write_preview` | corpus | выбор «вставить/перезаписать» и компиляция действий настроек |
| `test_librarian.py` | 107 | unit | context | `context.gather` | corpus | сбор контекста и поиск по проекту; часть кейсов самого поиска (квоты, `context_lines=0`, скрытость аддонов) снята в `fixtures/corpus/project_text/search/` |
| `test_log_report_batch.py` | 6 | unit | logs | `verification.headless` | corpus | чтение лога и отчёт прогона |
| `test_move_dir_safety.py` | 24 | unit | move | `editing.file_refactor` | corpus | перенос каталогов и гонки с редактором |
| `test_move_race_and_agent.py` | 6 | unit | move | `editing.file_refactor` | corpus | перенос каталогов и гонки с редактором |
| `test_move_safety.py` | 21 | unit | move | `editing.file_refactor` | corpus | перенос каталогов и гонки с редактором |
| `test_node_refactor.py` | 17 | unit | scene | `scene_model.node_rename` | corpus | правки .tscn и путей узлов |
| `test_node_refactor_flow.py` | 13 | flow | scene | `scene_model.node_rename` | corpus | правки .tscn и путей узлов |
| `test_node_refactor_live.py` | 10 | live | scene | `scene_model.node_rename` | corpus | правки .tscn и путей узлов |
| `test_node_rename_intercept.py` | 12 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_path_policy_safety.py` | 18 | unit | paths | `kernel/paths.py` | corpus | политика доступа: разрешено/запрещено, probable/proven; скрытость аддонов проверена кейсом 011 корпуса `project_text/search` |
| `test_probable_access.py` | 12 | unit | paths | `kernel/paths.py` | corpus | политика доступа: разрешено/запрещено, probable/proven |
| `test_project_settings_actions.py` | 5 | unit | project | `project_ops.settings_set` | corpus | правки project.godot и политика путей |
| `test_project_settings_flow.py` | 6 | flow | project | `project_ops.settings_set` | corpus | правки project.godot и политика путей |
| `test_rename_analyze_split.py` | 7 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |. Аудит 2026-10-27: разделение «предпросмотр vs запись» — это `analyze_rename` (следующий срез `code_intel.usages`) и `editing.symbol_rename`; `usages` из этих кейсов берёт только состав отчёта (места, by_link, счётчики). Срез `analyze_rename` (2026-10-27) закрыл: «анализ ничего не пишет» (`test_preview_does_not_touch_files`, хеши фикстуры), «в `affected_paths` попадают файлы» и «риски отражаются» (кейсы 001–004 корпуса `fixtures/corpus/code_intel/analyze_rename/`), «анализ не требует права записи» (`effects=read`, `requires_preview=False`). Остаются `exclude`, `skipped_usages`, частичное применение и откат — `editing.symbol_rename` |
| `test_rename_apply_report.py` | 9 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_class_and_file.py` | 13 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_class_name_strings.py` | 12 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_const.py` | 12 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_const_exclude_last_usage.py` | 7 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_const_same_file.py` | 6 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_enum.py` | 8 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_index_completeness.py` | 11 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |. Аудит 2026-10-27: полнота проектного индекса — это S2 `code_intel.usages` (`shared/symbol_index.py`, тест `tests/py/code_intel/test_symbol_index.py`); переименование — `editing.symbol_rename` |
| `test_rename_local_variables.py` | 6 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_name_collisions.py` | 7 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_nested_members.py` | 5 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_policy_default.py` | 15 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_refusal_granularity.py` | 30 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_refusal_kinds.py` | 5 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_refusal_levels.py` | 9 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_scene_connections.py` | 12 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_scene_instances.py` | 10 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_shadowing.py` | 7 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_string_guard.py` | 9 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_symbol.py` | 11 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_symbol_flow.py` | 3 | flow | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_symbol_overrides.py` | 11 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_transitive_hierarchy.py` | 16 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_typed_collections.py` | 6 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_rename_usages_checklist.py` | 12 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_resource_action_flow.py` | 8 | flow | resource | `editing.resource_ops` | corpus | C.23 .tres schema/prepare-only; C.24 D18/D19 отдельно разрешён: genuine native executor prepare/execute/reload, +36 собственных apply/refusal/raw-rollback карточек 236–271 и новый WAL safety уровень. Исторический count8 и судьба сохранены; старый flow не запускался/не копировался, приёмка не выставлена |
| `test_resource_actions.py` | 7 | unit | resource | `editing.resource_ops` | corpus | C.23 .tres normalize/digest/prepare/public/summary:235 native-derived cases +74 diagnostics с provenance, все прежние карточки неизменны. C.24 добавляет шесть операций через общую raw WAL-воронку, byte/EOL/refusal кейсы и strict internal client; новые тесты, не копия старых. Исторический count7 и судьба сохранены |
| `test_rollback_by_entry.py` | 14 | unit | write | `editing.write_apply` | corpus | воронка, журнал, откат, stale (ADR-0005) |. Срез части 2 (2026-10-27) закрыл: «запись до эффекта» (`APPLYING` в WAL до первого `write_raw`), «квитанция после каждого шага» (`test_apply_returns_a_clean_receipt`), «откат по `entry_id`» и `already_rolled_back` (`test_write_rollback_contract.py`), stale по байтам, TTL, чужой лок, сбой шага и recovery — `tests/py/integration/test_write_apply_disk.py`; корпус 14 `write_apply` + 4 `rollback` |
| `test_runtime_check_flow.py` | 6 | flow | check | `verification.check` | corpus | вклады агрегатора check и его findings |
| `test_runtime_checks.py` | 5 | unit | check | `verification.check` | corpus | вклады агрегатора check и его findings |
| `test_runtime_debug.py` | 3 | unit | check | `verification.check` | corpus | вклады агрегатора check и его findings |
| `test_runtime_debug_flow.py` | 6 | flow | check | `verification.check` | corpus | вклады агрегатора check и его findings |
| `test_runtime_ownership_live.py` | 4 | live | check | `verification.check` | corpus | вклады агрегатора check и его findings |
| `test_scene_action_flow.py` | 14 | flow | scene | `scene_model.node_rename` | corpus | правки .tscn и путей узлов |
| `test_scene_actions.py` | 7 | unit | scene | `scene_model.node_rename` | corpus | правки .tscn и путей узлов |
| `test_search_quality.py` | 46 | unit | context | `context.gather` | corpus | сбор контекста и поиск по проекту |
| `test_split_gd.py` | 28 | unit | split | `editing.split_gd` | corpus | C.14 scan: native inventory/refs кейсы в34raw+13contract корпусе; новые тесты не копируют старые; scan этап6/не принято, plan/group/render — C.15. Уточнение 2026-10-31: scan затем принят сессией67; C.15 plan/group/render кейсы переизвлечены в101–155 (25native successes/21native refusals/9contract), новые tests+fullraw differential, не принято. Дополнение C.16,2026-11-01: C.15 затем принят69; F6 exact-message108/109/130 и F7 factual-newline141/142/143 reprojected только в expect, raw oracle/55plan/47scan неизменны; C.16 готов к независимому аудиту, не принято |
| `test_split_gd_flow.py` | 5 | flow | split | `editing.split_gd` | corpus | C.14 scan: read-only/foreign/non-.gd кейсы; транспорт не переносился; plan/apply/journal — C.15; этап6/не принято. Уточнение 2026-10-31: scan принят67; C.15 только read-only plan/idempotence/treeSHA/ошибки,55cases+native recapture; apply/journal/rollback — C.16, не переносились. Дополнение C.16,2026-11-01: C.15 принят69; fixes/read-only differential54donors×1100/100,108native/216port,0unexpected; новых записей/engine-вызовов из plan нет; нумерация write изменена на C.17, он не переносился |
| `test_split_refactor.py` | 21 | unit | split | `editing.split_gd` | corpus | историческая coarse-row «обе пилы»; .py вне C.14, код/кейсы здесь не переносились, исходная судьба corpus сохранена; C.17 scan105–167: 47 actual-native cases/163 inputs; C.18 inventory/plan209–416: ещё 49 cases/101 inputs, selfcheck568/96 — оба среза приняты 2026-11-01. F4/C.19 принят отдельно. Apply419–482 перенесён в C.20: `split_apply` + funnel create/delete, actual-native097–105 и boundary106–108, 12 новых cards/2 inputs, 32 новых tests; selfcheck583/107, полный split_py snapshot108/108. C.20 готов к независимому аудиту, не принят; старые тесты не копировались/не запускались |
| `test_string_reference_criterion.py` | 9 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |. Аудит 2026-10-27: критерий строковой ссылки (call/set/get рядом со строкой, `print` — не ссылка) проверяется в `usages` (кейс 007, `dynamic` + note); переименование строк — `editing.symbol_rename` |
| `test_transaction_actions.py` | 10 | unit | write | `editing.write_apply` | corpus | воронка, журнал, откат, stale (ADR-0005) |
| `test_transaction_flow.py` | 5 | flow | write | `editing.write_apply` | corpus | воронка, журнал, откат, stale (ADR-0005) |
| `test_tree_excludes_addon.py` | 2 | unit | scene | `scene_model.node_rename` | corpus | правки .tscn и путей узлов |
| `test_usage_checklist_honesty.py` | 7 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |. Аудит 2026-10-27: честность отчёта (`probable` не выдаётся за `proven`, причина в note) — это `usages` (кейсы 006/013); чек-лист «что будет переименовано» — `analyze_rename` |
| `test_variable_refactor.py` | 9 | unit | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_variable_refactor_live.py` | 6 | live | rename | `editing.symbol_rename` | corpus | кейсы переименования; анализ - в code_intel.usages |
| `test_write_recovery_safety.py` | 4 | unit | write | `editing.write_apply` | corpus | воронка, журнал, откат, stale (ADR-0005) |
| `run_integration_regressions.py` | 5 | unit | helper-runner | `-` | replaced | заменяется tools/ и CI |
| `test_agent_bridge.py` | 116 | unit | host-bridge | `protocol/dispatch` | replaced | старый мост/транспорт; заменить contract-тестами канала. C.8 (разрешено пользователем 2026-10-30): только сценовый input из test_check_reports_local_problems_and_scene_autofix:1113–1129 → corpus verification.tscn_lint; мост/headless/агрегатор не переносить, владелец и судьба всего файла сохранены |
| `test_agent_entry_context_menu.py` | 15 | unit | host-plugin | `editor/core` | replaced | жизненный цикл плагина: проверить живьём, не юнитом |
| `test_agent_entry_integrations.py` | 15 | unit | host-plugin | `editor/core` | replaced | жизненный цикл плагина: проверить живьём, не юнитом |
| `test_agent_entry_tool_menu.py` | 16 | unit | host-plugin | `editor/core` | replaced | жизненный цикл плагина: проверить живьём, не юнитом |
| `test_agent_server_client.py` | 11 | unit | host-bridge | `protocol/dispatch` | replaced | старый мост/транспорт; заменить contract-тестами канала |
| `test_anthropic_compat.py` | 10 | unit | llm-api | `assistant.model_choice` | replaced | реестр моделей и провайдеры: contract + живой вызов |
| `test_api_backend.py` | 53 | unit | llm-api | `assistant.model_choice` | replaced | реестр моделей и провайдеры: contract + живой вызов |
| `test_api_end_to_end.py` | 31 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_api_history.py` | 13 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_api_history_failures.py` | 10 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_api_route_persistence.py` | 13 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_api_routes.py` | 52 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_api_secrets_and_limits.py` | 17 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_api_transport.py` | 19 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_arch_gate.py` | 8 | unit | self-arch | `tools/check_limits.py` | replaced | гейты аддона стали линтерами tools/ |
| `test_arch_map.py` | 15 | unit | self-arch | `tools/check_limits.py` | replaced | гейты аддона стали линтерами tools/ |
| `test_catalog.py` | 43 | unit | llm-api | `assistant.model_choice` | replaced | реестр моделей и провайдеры: contract + живой вызов |
| `test_chat_pending_cleanup.py` | 1 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_chat_state_isolation.py` | 8 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_chats_list_live.py` | 3 | live | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_godot_agent_mcp.py` | 30 | unit | host-bridge | `protocol/dispatch` | replaced | старый мост/транспорт; заменить contract-тестами канала |
| `test_http_boundary_safety.py` | 7 | unit | http | `channels/http` | replaced | границы HTTP: заменить contract-тестом канала |
| `test_locale_format.py` | 9 | unit | locale | `editor/core/i18n` | replaced | переводы: проверяются в tests/gd |
| `test_md_to_bbcode.py` | 10 | unit | bbc | `editor/ui` | replaced | рендер разметки в панели: живая проверка |
| `test_megaprompt_once.py` | 2 | unit | prompt | `assistant.chat` | replaced | сборка промпта: contract + живой вызов модели |
| `test_panel_short_channel.py` | 4 | unit | panel | `editor/bridge` | replaced | короткий канал панели: живая проверка |
| `test_port_guard.py` | 5 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_provider_catalog.py` | 50 | unit | llm-api | `assistant.model_choice` | replaced | реестр моделей и провайдеры: contract + живой вызов |
| `test_pyinstaller_spec.py` | 10 | unit | pack | `tools/package.py` | replaced | сборка exe больше не нужна: аддон ставится как папка |
| `test_rate_limit_sleep.py` | 9 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_release_prepare.py` | 26 | unit | host-updater | `editor/core` | replaced | обновление аддона: живая проверка, не юнит |
| `test_remaining_work_steps.py` | 30 | unit | self-arch | `tools/check_limits.py` | replaced | гейты аддона стали линтерами tools/ |
| `test_runtime_result_http.py` | 15 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_scan_policy_cost.py` | 9 | unit | self-arch | `tools/check_limits.py` | replaced | гейты аддона стали линтерами tools/; часть кейсов политики сканирования → `fixtures/corpus/project_text/search/` |
| `test_server_auth.py` | 7 | unit | host-flask | `channels/http` | replaced | проверялось через Flask-роуты старого хоста |
| `test_updater.py` | 14 | unit | host-updater | `editor/core` | replaced | обновление аддона: живая проверка, не юнит |
| `test_updater_bbcode_live.py` | 8 | live | host-updater | `editor/core` | replaced | обновление аддона: живая проверка, не юнит |
| `test_updater_live.py` | 9 | live | host-updater | `editor/core` | replaced | обновление аддона: живая проверка, не юнит |
| `test_aistudio_send_acceptance.py` | 4 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_arena_parser.py` | 29 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_browser_send_acceptance.py` | 9 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_browser_target_binding.py` | 3 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_browser_turn_cancel.py` | 3 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_browser_wait_safety.py` | 10 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_chat_site_restore.py` | 1 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_deepseek_no_double_send.py` | 9 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_kimi_stream_fallback.py` | 3 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_mirror_js_fallback.py` | 3 | unit | browser-extra | `channels/mcp` | deferred | браузерная ветка позже (Q-08) |
| `test_mirror_soft_newline.py` | 3 | unit | browser-extra | `channels/mcp` | deferred | браузерная ветка позже (Q-08) |
| `test_net_monitor_lifecycle.py` | 14 | unit | browser-extra | `channels/mcp` | deferred | браузерная ветка позже (Q-08) |
| `test_paste_attachment.py` | 7 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_paste_slow_guard.py` | 3 | unit | browser-extra | `channels/mcp` | deferred | браузерная ветка позже (Q-08) |
| `test_qwen_dual_response.py` | 5 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_qwen_no_double_send.py` | 7 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v105_attachment_note.py` | 5 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v105_net_answer_ready.py` | 7 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v105_spoof_per_site.py` | 7 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v87_1_kimi_cdp.py` | 27 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v87_9_regen.py` | 10 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v88_0_aistudio.py` | 13 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v88_11_live_input.py` | 10 | live | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v88_12_net_confirm.py` | 10 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v88_13_multi_action.py` | 8 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v88_16_paste_fix.py` | 6 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v88_6_qwen_net.py` | 11 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v88_7_input_wait.py` | 5 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `test_v88_8_net_first.py` | 11 | unit | browser | `channels/mcp` | deferred | браузерная ветка позже (Q-08); корпус - записанные кадры протокола |
| `_fake_selenium.py` | 2 | helper | helper-fake | `-` | dropped | фейк для браузерных тестов; не нужен |
| `_probe_doh_win10049.py` | 3 | helper | helper-probe | `-` | dropped | разовый зонд сети |
| `synthetic_card_bench.py` | 4 | unit | bench | `-` | dropped | замер производительности карточек, не поведение |
| `test_doh.py` | 14 | unit | doh | `-` | dropped | DoH-подмена DNS не переносится (api/doh.py) |
| `test_minilich_status_purity.py` | 6 | unit | minilich | `-` | dropped | minilich не входит в агент (Q-07) |
| `test_semantic_index.py` | 3 | unit | minilich | `-` | dropped | minilich не входит в агент (Q-07) |

## Что это значит для работы

- Перед переносом механики открыть её строки здесь и убедиться, что все
  они имеют судьбу, отличную от `pending`.
- `live`-строки нельзя закрыть юнит-тестом: они проверяют то, что
  подделка не воспроизводит (реальный `.tscn`, undo-скоуп, перезагрузка сцены).
- `repro`-строки попадают в корпус целиком: это история багов.


## Приложение: новые тесты (не старые файлы)

Строки этой секции — **наши** тесты, добавленные срезами; в сводку «всего файлов
168» они не входят. После C.12: 168 старых файлов +36 строк приложения =204;
старые строки не удаляются.

| Файл | Тестов | Тип | Область | Модуль | Источник | Что осталось за старыми тестами |
|---|---|---|---|---|---|---|
| `python/modules/editing/write_preview/tests/test_core.py` | 16 | unit | rename | `editing.write_preview` | corpus | домен без диска: наши смещения, `newline`, `exclude`, отказы `mode`/`allow_unverified`, стабильность digest. Старые `test_rename_analyze_split.py`/`test_rename_apply_report.py` частично закрыты здесь (`skipped`, `exclude`), полностью закроются в части 2 |
| `tests/py/contract/test_write_preview_contract.py` | 19 | contract | rename | `editing.write_preview` | corpus | схема входа/выхода, обязательный `details.reason` у `conflict`, диффы без абсолютных путей, digest/plan_id, синхронность `contract/capabilities/write_preview.json` |
| `tests/py/integration/test_write_preview_flow.py` | 5 | integration | rename | `editing.write_preview` | corpus | `MemoryFS` + поддельный журнал: план строится, WAL-запись `PREPARED` появляется, файлы в памяти не меняются, при отказе журнал пуст |
| `tests/py/security/test_path_escape.py` | 6 | security | rename | `editing.write_preview` | corpus | SEC-12: `..`-побег, абсолютные пути, `exclude` вне проекта |
| `tests/py/security/test_write_funnel.py` | 4 | security | rename | `editing.write_preview` | corpus | SEC-11: в модуле нет `open(...,"w")`/`os.remove`, запись в проект не идёт, WAL вне проекта |
| `tests/py/security/test_secret_redaction.py` | 5 | security | rename | `editing.write_preview` | corpus | SEC-13: нет абсолютных путей/имён переменных окружения, digest непрозрачен |
| `python/modules/context/gather/tests/test_core.py` | 13 | unit | context | `context.gather` | corpus | домен без диска: `known_sections`, порядок, `duplicate_section`, `too_large`, `unknown_section` с подсказкой, `path_escape`, аддоны → `denied`, форма `project`/`tools`, `assemble` |
| `tests/py/contract/test_context_contract.py` | 13 | contract | context | `context.gather` | corpus | пины `ToolSpec` (`sections` 1…8, `path`, `additionalProperties: false`), схема результата, синхронность `contract/capabilities/context.json`, `invalid_input` параметризацией, `unknown_section` отказывает весь вызов |
| `tests/py/integration/test_context_contributions.py` | 7 | integration | context | `context.gather` | corpus | вклад в `sections`; отказ вклада → `unavailable`; исключение → `failed`; нет вклада → `no_module`; чтение не пишет; вклад без `contributes_to` не регистрируется |
| `tests/py/contract/test_symbol_rename_manifest.py` | 6 | contract | rename | `editing.symbol_rename` | corpus | манифест-вклад без `provides_tools`, две цели `contributes_to`, `internal_services`, `TOOLS == ()`, `load_one` без `TOOLS`, отсутствие артефакта `symbol_rename.json` |
| `python/modules/editing/symbol_rename/tests/test_core.py` | 18 | unit | rename | `editing.symbol_rename` | corpus | домен: `validate_request`, точные смещения и `sha256` шагов, `name_conflict`, `unverified`/`dynamic`, `all_usages_excluded`, `skipped`, `newline`, `COMPILER.build` |
| `tests/py/tools/test_lint_arch_shared.py` | 3 | tool | arch | — | corpus | регресс `lint_arch`: свой `shared` и свой пакет разрешены, чужая область запрещена (после фикса `_same_feature`) |

| `python/modules/context/editor_context/tests/test_core.py` | 9 | unit | context | `context.editor_context` | corpus | домен вклада: три примитива по порядку, nullable в `active_scene`/`node_path`/`scene`/`script`, отказ по схеме с путём поля (`open_scenes[0].revision`, `node_path`), частичного снимка не бывает |
| `tests/py/integration/test_editor_context_bridge.py` | 15 | integration | context | `context.editor_context` | corpus | мост на фейке: handshake первым кадром, `verbs_mismatch`/`wrong_project` без повтора, `truncated`/`timeout` с одним повтором, `frame_too_big`, `no_bridge`, устаревший порт, кадр без токена, двойной ответ, неизвестный примитив, переподключение после обрыва, один in-flight |
| `tests/py/integration/test_editor_context_section.py` | 3 | integration | context | `context.editor_context` | corpus | секция `editor`: профиль editor с фейком (`available: true`), без моста -> `no_bridge`, headless -> `no_module` |
| `tests/py/contract/test_editor_context_manifest.py` | 4 | contract | context | `context.editor_context` | corpus | манифест-вклад (профиль editor, `provides_tools=()`), `TOOLS == ()`, `CONTRIBUTIONS == (SECTION,)`, нет артефакта возможностей |
| `tests/py/security/test_bridge_network_rules.py` | 4 | security | bridge | `context.editor_context` | corpus | SEC-02: петлевой `socket` разрешён только клиенту моста, `requests` и не-петлевой адрес - нарушения |
| `python/modules/editing/scene_ops/tests/test_core.py` | 13 | unit | scene | `editing.scene_ops` | corpus | домен без IO: канонический JSON совпадает с `json.dumps(sort_keys)`, отпечаток плана стабилен и зависит от порядка операций, неизвестная `op` рушит весь батч, лимиты 64 / 4 КиБ, `apply` требует свой `plan_digest`, сверки сцены и ревизии (`conflict/revision_mismatch`), отказы по схеме ответа, полные квитанции и `applied_revision + 1` |
| `tests/py/integration/test_scene_ops_bridge.py` | 12 | integration | scene | `editing.scene_ops` | corpus | мост на фейке: план ничего не пишет, ревизионный конфликт, `stale_plan` до сети, чужой digest → `bad_result`, сбой на втором шаге без `applied`, `applied` без квитанций отвергнут, `truncate` после `apply` — ровно один повтор, отказной кадр без повтора, ответ не на тот примитив, плохой запрос без кадров, чужой инструмент |
| `python/modules/verification/check/tests/test_core.py` | 44 | unit | verification | `verification.check` | корпус/контракт C.9 + C.13 | ORDER/unknown name, строгие optional checked/unavailable, any/defaults, дословная availability/порядок, 8+6 без усечения, F3; прежние кейсы сохранены; CLI/required/auto не закрыты |
| `python/modules/verification/check/tests/test_app.py` | 24 | unit | verification | `verification.check` | корпус/контракт C.9 + C.13 | отказы до IO, один read_raw, ошибки портов без утечки пути, точная граница4МиБ, CRLF/UTF8 replacement, compile без исполнения; CheckKind-стабы API/GD, порядок/выбор/один read, no_module fallback |
| `tests/py/contract/test_verify_contract.py` | 11 | contract | verification | `verification.check` | корпус/контракт C.9 | descriptor, строгий вход, форма фактического результата; удаление required.checked обнаруживает gen_contract, не этот unit-scope |
| `tests/py/integration/test_verify.py` | 88 | integration | verification | `verification.check` | 38 actual-old C.9 +24 F1 +13 C.13 | реальный registry/dispatch api,gd,tscn против результата gd,api; повтор/read-only SHA, строгий inventory20/ORDER, availability/fallback, 8+6, один owner read и snapshot только выбранного API; №006/038 blind spots сохранены; batch-счётчики/CLIrc не закрыты |
| `python/modules/verification/check/tests/test_source_text.py` | 8 | unit | verification | `verification.check` | F1/ADR-0008 | один ведущий BOM,повторный/внутренний U+FEFF,CRLF/CR,invalid/partial UTF-8; чистый decoder не меняет raw |
| `tests/py/integration/test_verify_bom.py` | 13 | integration | verification | `verification.check` | F1 actual-old 9GD+4candidate | gd_lint/verify одинаковые файловые findings и original checked_bytes; candidate check сохраняет literal BOM,read-only SHA/повтор |
| `python/modules/engine_kb/class_api/tests/test_core.py` | 35 | unit | engine_kb | `engine_kb.class_api` | C.11 actual-old/контракт | 20 успешных наблюдений, int arity/−1, depth/cycle, nearest override/signatures, input immutability и отдельная shared purity; старых class_api тестов нет |
| `python/modules/engine_kb/class_api/tests/test_app.py` | 35 | unit | engine_kb | `engine_kb.class_api` | C.11 actual-old/контракт | 26 кейсов, invalid_input до IO, один snapshot, strip, fresh same-agent ответ; CLI-text/RC не закрыты |
| `tests/py/contract/test_api_contract.py` | 16 | contract | engine_kb | `engine_kb.class_api` | C.11 ToolSpec | read/idempotent, строгие схемы, arity−1; required.found отдельно защищается gen_contract, не этим unit-scope |
| `tests/py/integration/test_api.py` | 32 | integration | engine_kb | `engine_kb.class_api` | C.11 26 actual-old кейсов | registry/dispatch, повтор/read-only SHA, manifest/corpus pins; замена/удаление/поломка/опустошение кэша между вызовами одного агента |
| `tests/py/integration/test_api_snapshot.py` | 10 | integration | engine_kb | `engine_kb.class_api` | C.11 ADR-0009 | coherent fresh snapshot при неизменной memoized classes(), fallback external/project/protected/legacy, ошибки/4МиБ/falsy/version; save/migrate/refresh вне scope |
| `python/modules/verification/api_check/tests/test_core.py` | 56 | unit | verification | `verification.api_check` | C.12 actual-old/контракт | 41 literal API-cache кейс, availability precedence, parentheses/top-level args, declarations и горизонтальный whitespace budget; MAX6/dedup/arity/messages/local members; CLI/verify вклад вне среза |
| `python/modules/verification/api_check/tests/test_mask.py` | 18 | unit | verification | `verification.api_check` | C.12 literal masking | независимые string/comment flags, single/triple/escaped/unclosed, длина и LF-позиции, комментарий не открывает строку |
| `python/modules/verification/api_check/tests/test_app.py` | 61 | unit | verification | `verification.api_check` | C.12 corpus52/ToolSpec | все52кейса, отказы до snapshot, один fresh snapshot, PathPolicy/UTF8/4МиБ, normalized missing path без чтения ФС |
| `tests/py/contract/test_api_check_contract.py` | 13 | contract | verification | `verification.api_check` | C.12 ToolSpec + C.13/F2 | точный errors invalid_input,denied; остальные пины сохранены; required.checked защищается gen_contract. C.13 P1: behavioral357 green, gate red и отдельно exact-pin1 red (уточнение пользователя), не весь suite green |
| `tests/py/integration/test_api_check.py` | 58 | integration | verification | `verification.api_check` | C.12 actual-old52 + companion C.13 | единственная правка пина contributes_to=('verify',), разрешена пользователем; прежние registry/dispatch/read-only/Protocol/fresh-cache/corpus pins сохранены; repro_check_* и test_gdscript_wiring не закрыты |
| `tests/py/tools/test_lint_arch_api_check.py` | 8 | tool | arch | `verification.api_check` | ADR-0010/red-before-edit | разрешён только app.py→engine_kb.shared.inheritance,7соседних forbidden edges; removal мутация red, существующие arch-tests неизменны |
| `tests/py/formats/test_scene_deps_facts.py` | 186 | format | scene_model | `scene_model.scene_deps` | companion C.13, разрешён пользователем | тест не менялся; 7 новых actual-old script_facts/SHA/bytes для GD-фикстур C.13, 133 старых факта и другие поля manifest неизменны; полный инвентарь файлов сохранён |
| `python/modules/editing/split_gd/tests/test_core.py` | 40 | unit | split | `editing.split_gd` | C.14 + C.16/F6 | 35прежних scan-пинов сохранены; 5новых exact99/5001/string и default0/None; M6 bounds99 red |
| `python/modules/editing/split_gd/tests/test_core_plan.py` | 79 | unit | split | `editing.split_gd` | C.15 + C.16/F7 | fullraw prepare по-прежнему nativeLF; public plan получает независимый factual newline; normalized donorSHA неизменен; прежний None-refusal заменён default-пином в test_core |
| `python/modules/editing/split_gd/tests/test_render.py` | 7 | unit | split | `editing.split_gd` | C.15 + C.16/F6 | 5прежних плюс2точных отказа empty funcs с именами part_one/part_two; M7 literal «пустой funcs» red |
| `python/modules/editing/split_gd/tests/test_app_plan.py` | 44 | unit | split | `editing.split_gd` | C.15 + C.16/F6/F7 | native bounds доFS, schema-string отказ, emptyfuncs послеread/доsnapshot; 6newline/BOM и4byte-precedence пина; прежние IO/exists/cache/order сохранены |
| `tests/py/contract/test_split_gd_plan_contract.py` | 54 | contract | split | `editing.split_gd` | C.15 + C.16/ToolSpec | 4domain-refusal аргумента проходят shape; integer/array/item types сохранены, CRenum pinned; P1 required.newline ловит только gen_contract, не behavioral |
| `tests/py/integration/test_split_gd_plan.py` | 57 | integration | split | `editing.split_gd` | C.15 + C.16/6recut | 55cases и2manifest/adapter пина; unconditional108/109/130 exact messages,141–143 rawLF/factualCRLF-or-CR/normalizedSHA; tree/read-only/idempotence сохранены |
| `tests/py/tools/test_security_audit_dirs.py` | 3 | tool | security | `editing.split_gd` | C.16/F8 + ADR-0012 | x.gd directory excluded/y.gd ordinary retained, complete gate ok, exact historical CRLF is_file-filter byte-pin; deletion3red/restoration3green; нет новой постоянной правки гейта |

| `python/modules/editing/split_py/tests/test_core.py` | 35 | unit | split | `editing.split_py` | C.17 native projection | donor/stem/counts/retained occurrences, sorted hard/soft и допустимое overlap; TODO заполнен in-place; план/AST не переносились |
| `python/modules/editing/split_py/tests/test_refs.py` | 52 | unit | split | `editing.split_py` | C.17 native corpus | 38native success observations, свой BOM/partial/invalid decoder,10patch operators; порядок/text200/all-counts/retained1000 |
| `python/modules/editing/split_py/tests/test_walk.py` | 39 | unit | split | `editing.split_py` | C.17 native lexical helpers | lexical imports/aliases, suffix matching,13skip+hidden ancestors, native extensions; tab ожидание исправлено после живого oracle proof |
| `python/modules/editing/split_py/tests/test_app.py` | 32 | unit | split | `editing.split_py` | C.17 safe fs-only adapter | schema/path/policy до IO, nearest plugin.cfg,4MiB/1MiB, safe OSError mapping, neighbor silent skip; no plan entrypoint |
| `tests/py/contract/test_split_scan_contract.py` | 55 | contract | split | `editing.split_py` | C.17 ToolSpec | sole read/idempotent split_scan, input/result shapes, generated card; P1required.truncated ловится только gen_contract, behavioral263green |
| `tests/py/integration/test_split_scan.py` | 50 | integration | split | `editing.split_py` | C.17 actual-native47 | registry/dispatch full success equality/refusal kind+safe text, повтор/treeSHA, manifest163inputs/raw no schema/projection, existing fs Protocol/policy; старые bridge CLI tests1939–2041 заменены policy-контрактом, не запускались |

| `tests/py/tools/test_selfcheck_unit_selector.py` (диагностический архив) | 13 | tool | selfcheck selector | `editing.split_py` / F4 | deferred B6, ADR-0013 proposed | собственные пины: до правки 4fail/9pass; SHA d0e12aa9b3e12bfad7784e83d7c13c500b787e2f85dfe6418da7d4cf2460d9d5; архив внешнего досье `test_selfcheck_unit_selector.py.red`, не активный testpaths; общий longest-prefix дополнительно меняет node_info/tree, запрещённые §6; вернуть после уточнения, старые тесты не менялись |

## C.18 — read-only split_plan и F11 (не принято)

Судьбы всех старых файлов сохранены. Из `test_split_refactor.py:209–416` взяты
кейсы, не код тестов; `arch_map.py` даёт чистые функции и новые map/index-кейсы,
не разрешение переносить старые audit-тесты или подсистему. C.17 шесть файлов
выше по-прежнему дают 263 теста: только фильтр `tool == split_scan`, multi-tool
пины и имя неизвестного инструмента изменены по B5. Числа из фактических
`nonlive-final.collect.json`/JUnit и `selfcheck-final`, не арифметический прогноз.

| Новый файл | Тестов | Уровень | Область | Механика | Основание | Что проверяет |
|---|---:|---|---|---|---|---|
| `python/modules/editing/split_py/tests/test_f11.py` | 3 | unit | split | `editing.split_py` | F11 / native missing | корневой и два вложенных отсутствующих донора: exact not_found до поиска plugin.cfg, один metadata-вызов |
| `python/modules/editing/split_py/tests/test_app_plan.py` | 18 | unit | split | `editing.split_py` | C.18 app / F11 / B4 / B7 | 13 отказов, F11, занятые файл/каталог как errors-data, fresh map/index; UTF-16 карта native-missing, red1→green1 |
| `python/modules/editing/split_py/tests/test_arch.py` | 6 | unit | split | `editing.split_py` | B7 / arch_map | missing/invalid data, независимые карты, native glob/default policy, свежий сортированный индекс, native skip/private/parse |
| `python/modules/editing/split_py/tests/test_inventory.py` | 37 | unit | split | `editing.split_py` | native inventory | 36 native сводок, bool state, AST-границы, sticky comments/decorators/coding header |
| `python/modules/editing/split_py/tests/test_groups.py` | 13 | unit | split | `editing.split_py` | native suggest_groups / контракт | четыре auto-кейса, symbols/порядок/target, четыре bounds и пять strict-type отказов |
| `python/modules/editing/split_py/tests/test_facade.py` | 38 | unit | split | `editing.split_py` | native render/compile | 36 полных текстов модулей/фасада, __all__, object reexports, block/import formatting, sorted cycle |
| `python/modules/editing/split_py/tests/test_plan.py` | 73 | unit | split | `editing.split_py` | native plan_split | 36 полных prepared + 36 public projections без мутации, отдельный исходный hooked refs:null; errors/лимиты/зоны/дубли/normalized SHA |
| `tests/py/contract/test_split_plan_contract.py` | 65 | contract | split | `editing.split_py` | ToolSpec / B1–B3 | strict shapes/схема 49 cases, bool state/object reexports, отсутствие text/line_start, реальный dispatch→schema, карточка; P1 behavioral568 green, gen_contract red |
| `tests/py/integration/test_split_plan.py` | 52 | integration | split | `editing.split_py` | actual-native49 / ADR-0014 | Agent 49 cases дважды/exact payload или refusal, tree/state/read-only, manifest SHA/102calls, ровно два production fs.exists, отдельный строгий hooked refs:null |

`plan_cases.py` — только fixture/projection support, тестов не собирает. Новые
305 + сохранённые C.17 263 подтверждены обычным selfcheck: **568/96, ok**.
F4/13 архивных пинов не активированы; ADR-0013 proposed, отдельный срез C.19.

## C.19 — F4 после разрешения §10 (не принято)

Предыдущая строка описывает историческое состояние C.18. Все168старых
test-file строк и их судьбы сохранены. Это гейт нового агента, не перенос
старых test-files; old plugin/tests не копируются и не запускаются.

| Новый файл | Тестов | Уровень | Владелец | Основание | Что проверяет |
|---|---:|---|---|---|---|
| `tests/py/tools/test_selfcheck_unit_selector.py` | 64 | gate / integration-selection | `tools/selfcheck.py::check_unit` | F4, C.19 §10, ADR-0013 | три real counts128/247/116,44полных списков/41неизменный порядок и кратность, longest known tool/exact/underscore boundary/unknown/api_snapshot/scene_ops, non-tool feature masks и multi-tool split_gd; red64/10failed/54passed→green64 |

Прежний13-case архив C.18 остаётся внешним historical evidence; активен новый
64-case файл C.19. ADR принят по разрешению аудитора75–76, не означает
приёмку реализации C.19. Корпуса/карточки и production механик неизменны.

Финальный64case набор содержит public-mask unknown-owner `test_apix.py`;
64green, полныйcollect4249=4185old+64new/executeonce/0failures/errors/skips.
SubmittedM1/M2/M3/P1 дают10/7/10/30failed,P2unknown/P3boundary дают1/2failed;
scope/sourceSHA/EOL после каждой мутации exact. Все168старых строк
по-прежнему byte-prefix прежней карты; C.19 готов к аудиту, не принято.

## C.20 — долг записи F2 в C.21

Семь новых файлов C.20; все прежние строки и судьбы сохранены без изменений.
Числа сняты новым прогоном 2026-11-01: collect = executed = **32**, passed 32,
failed/error/skipped 0; 1.76 с. Junit: внешний каталог
`%LOCALAPPDATA%/Temp/opencode/c21-paths-preview-20261101/f2-tests.xml`, SHA256
`aa05bb69fe6fc2e941ce8a58987af8f29bc949988f2dd4ae026dc23d4cecfb02`.

| Новый файл | Тестов | Уровень | Механика | Основание | Что проверяет |
|---|---:|---|---|---|---|
| `tests/py/contract/test_split_apply_contract.py` | 3 | contract | `editing.split_py` | C.20 / ToolSpec | эффекты, strict input и native result с квитанциями |
| `tests/py/integration/test_create_delete_funnel.py` | 6 | integration | `editing.write_apply`, `editing.rollback` | C.20 / ADR-0015 | create/delete, stale, точный rollback, recovery и чужая правка |
| `tests/py/integration/test_split_apply.py` | 12 | integration | `editing.split_py` | C.20 / actual-native | apply, отказы без эффектов, compile до записи, BOM/CRLF, rollback при втором сбое |
| `tests/py/security/test_split_apply_write.py` | 3 | security | `editing.split_py` | C.20 / SEC-21 | нет прямой записи, protected/escape targets, неизвестный op не становится edit |
| `tests/py/formats/test_file_system_create_delete.py` | 3 | format / adapter | `editing.write_apply`, `editing.rollback` | C.20 / fs | write/create/delete двух адаптеров, отсутствие, отказ каталогу |
| `tests/py/formats/test_script_edit_ops.py` | 3 | format / shared | `editing.write_apply`, `editing.rollback` | C.20 / ADR-0015 | прежний script_edit, create/delete bytes, неизвестный op |
| `tests/py/tools/test_snapshot_diff_split_apply.py` | 2 | gate / corpus runner | `editing.split_py` | C.20 / snapshot_diff | native result projection и инъекция сбоя второго эффекта |

## C.21 — read-only paths_preview и точные мониторинговые пины D9 (2026-11-02)

Независимые новые tests:65=21+7+30+3+4, collect=executed/pass65. Источники —
actual frozen file_refactor read-пробы и25 карточек/50 вызовов, не копия тестов;
старые строки test_file_refactor* / судьба C.22 не изменены. После D9 checks
bytes/SHA/полного gd-покрытия добавлены в существующие тесты без роста счётчика.
Full4346/0, JUnit `ef5582953468751efe26b521b926c1ade1078fe3fe00358a7f13cad961514ee3`. Срез готов к аудиту, не принят.

| Новый/уточнённый файл | Кейсов | Уровень | Владелец | Происхождение и граница |
|---|---:|---|---|---|
| `python/modules/editing/paths_preview/tests/test_core.py` | 21 | unit | `editing.paths_preview` | native/D5 normalize, utf8-sig/fallback/BOM/endings, missing mapped/unmapped, uid и generic internal |
| `tests/py/contract/test_paths_preview_contract.py` | 7 | contract | `editing.paths_preview` | один read API, metadata, strict D4, invalid args/op/helper absence |
| `tests/py/integration/test_paths_preview.py` | 30 | integration | `editing.paths_preview` |25 actual-native cards/exact replies/repeat/tree; filters, policy,4/5MiB, invalidUTF8 spans; D9 input pins |
| `tests/py/formats/test_paths_preview_fs.py` | 3 | formats | `editing.paths_preview` | readonly adapter/per-tool5MiB, common4MiB unchanged, raw/endings, нет effect methods |
| `tests/py/security/test_paths_preview_read.py` | 4 | security | `editing.paths_preview` | no direct IO/shared funnel, containment/no leak, unknown before ports, paths_fs only |
| `tests/py/formats/test_scene_deps_facts.py` | 1 существующий pin; файл 298 cases | formats | `scene_model.scene_deps` / мониторинг | D9 один literal C.21-root exclusion; count не менялся, bases/MANIFEST/equality/frozen corpus прежние, собственные28 gd запинены |
| `tests/py/integration/test_split_plan.py` | 1 существующий pin; файл 52 cases | integration | `editing.split_py` / мониторинг | D9 count3→4, только paths_preview/ports.py, имя exactly_four; scan/literal/остальные пины прежние |

## C.24 D18 — предварительные новые пины, STOP (2026-11-02)

Строки113–114 и все168старых судьб сохранены: corpus, не копирование старого
test code. Пять новых файлов resource: contract area-limits + case data helper,
formats transform, integration ops_apply, security apply_security; actual47
focused executed/0fail/error/skip. До production corrected red9area(6fail)/
37resource(37fail); отдельные mixed red2fail/45pass сохранены во внешнем досье.
Новый C.24 корпус ещё не записан, старые235cards/manifest byte-exact.
Принятые C.23 manifest/effect-dispatch пины отдельным actual прогоном дали2fail/
2pass; tests не меняются до разрешения §6. Это не удаление/замена старых кейсов,
не acceptance и не завершение механики. Следующее: ответ аудитора на manifest
pin scope, собственный domain-layer repair, actual selfcheck→engine/corpus.

## C.25 D20/D21 — собственные cases, STOP loader (2026-11-03)

Все168 старых строк/судеб сохранены. Собственный cross-reference: строки83
test_path_policy_safety.py,169 test_scan_policy_cost.py,136 test_agent_bridge.py,
156 test_godot_agent_mcp.py,130 test_tree_excludes_addon.py. Последняя историческая
строка/владелец scene_model.node_rename не переписаны; реальные два tree-case
использованы здесь только как источники. Старые тесты не копировались/не запускались.

| Собственный файл | Cases | Уровень/граница |
|---|---:|---|
| `python/modules/project_text/read/tests/test_core.py` | 3 | чистая Unicode projection |
| `python/modules/project_text/read/tests/test_corpus.py` | 35 | actual native read/BOM/EOL/binary/quota/policy/non-effect |
| `python/modules/project_text/tree/tests/test_core.py` | 1 | files-first/file-only quota/empty dir |
| `python/modules/project_text/tree/tests/test_corpus.py` | 22 | actual native tree/depth/exclusion/policy/non-effect |
| `tests/py/contract/test_project_text_read_contract.py` | 10 | public read only/typed/error/root directory |
| `tests/py/contract/test_project_text_tree_registration.py` | 14 | D21 11pins + D22 discover/bootstrap/empty negative3 |
| `tests/py/security/test_project_text_registration.py` | 5 | no public/contribution, ports/profile/empty/public-without-call |
| `tests/py/security/test_project_text_entries.py` | 4 | empty dirs,4realjunctions;2true1314skip, не green symlink coverage |

D19 existing test_verify count pin: actualred27!=26; только26→27, samegreen.
Native read35/tree22 записан до production,57cards не old test count;
не завершение/приёмка. STOP: module_loader.load_one четвёртый guard вне D21.

D22 later разрешён: только load_one refusal guard; actual2red+emptynegative1→
same3green, expanded16/C19pins64green. D23 auditor разрешил only frozen
context/gather001 tools.count26→27/names+read/effects.read и SHA001; 7 corresponding
inventory pins red→green, semantic bans/targets/parameter pools unchanged.
Native tree007 only_exts=[] recaptured без ошибочной подмены на None: count0,
directories retained; owncase red1→green1. Старые168 строк не затронуты.
Active C25 focused94 =61 module cases+33 contract/security cases; два security
symlink cases реально WinError1314 skip,4junction green без skip. Публикация
готовности/приёмка не следуют из этих counts, полный final route обязателен.

Final route выполнен на submitted bytes: nonlive×2collect=executed5225 each,
5223passed/2actual1314skips/errors0; own94cases все учтены по тем же IDs.
Snapshot1237=1180+57 allmatched,read35/tree22;selfchecks38/35 и23/22ok;
44fresh reports и neighbours503/271,124/52,583/107 exact. M1–M3 actual1red/
restored1green each;live3/P1–P3 proven. Старые168 rows/fates/owners unchanged;
готов к независимому аудиту,не принято (stage0/ported не выставлялись).


## API-core — эталонный substrate-срез, 2026-11-05 (не приёмка assistant-модулей)

Все168 старых строк/судеб/владельцев сохранены. Старые test-files не копировались
и не запускались: native поведение снято отдельными синтетическими входами.
Ни одна HTTP/backend/model-choice строка не закрывается одним reference-корпусом.

| Новый файл | Cases | Уровень | Фактическое покрытие |
|---|---:|---|---|
| `tests/py/llm/test_llm_api_limits.py` | 13 | gate | API3400/3401, exact directory boundary, entry caps и прежние классы |
| `tests/py/llm/test_llm_api_binding.py` | 7 | integration | 11 aliases identity/idempotence, foreign/rollback, deferred DNS, no bootstrap |
| `tests/py/llm/test_llm_api_security.py` | 12 | security | sandbox/env/network guard, key masking, lock/decorator/corrupt history, D37 headers |
| `tests/py/llm/test_llm_api_corpus.py` | 221 | parity | 210 native input/response cases +11 complete source byte/SHA/EOL pins |

Helpers api_cases/api_state/api_stream тестов сами не собирают. Итого253;
collect=executed253 ×2; все253 IDs в full5874 ×2 (5872pass/2legacy1314skip).
Частичные источники/не закрыто: test_anthropic_compat — events/errors, не live API;
test_api_transport — OpenAI SSE/UTF8/truncation, не HTTP routes;
test_catalog/test_provider_catalog — offline metadata/cache/defaults, не сетевой
каталог/выбор модели UI; test_api_history — sandbox budget/decorator/storage,
не routes/persistence integration; test_md_to_bbcode — native conversion,
не редакторский renderer. test_api_backend/test_api_end_to_end/chat_routes deferred.
Старые судьбы replaced/deferred/corpus сохранены; manifest хранит provenance.

## Routing-runtime: reference-корпус и новые тесты (2026-11-05)

Historical168строк/owners/fates сохранены целиком. Native tests используются
только как источники synthetic кейсов, их код/host bootstrap не копировался и
не исполнялся. test_editor_context.py остаётся context.gather/corpus с прежней
replaced-аннотацией; runtime_debug/flow — verification.check/corpus;
test_api_backend.py — assistant.model_choice/replaced. HTTP/routes/transport/
runtime ownership не закрыты этим reference-срезом.

| Новый файл | Фактически collected | Доказанная граница |
|---|---:|---|
| tests/py/llm/test_llm_routing_context.py | 149 | native144,2source SHA/EOL,3context safety/composition pins |
| tests/py/llm/test_llm_routing_limits.py | 15 |2narrow directory classes/entry/neighbor/default/previous limits |
| tests/py/llm/test_llm_routing_binding.py | 8 |3newaliases identity/idempotence/foreign refusal/new-only rollback/no bootstrap |
| tests/py/llm/test_llm_routing_backend.py | 204 | native193,3source SHA/EOL,8routing/history/transport safety pins |

Helpers routing_context_cases.py/routing_cases.py/routing_transport.py собирают
0tests. Corpus context/runtime_reference144 и llm/routing193: bytes/SHA/provenance,
native×2 совпал (B exit-coded replay после timeout). Focused376×2, full6250×2
=6248pass/2прежних WinError1314 skips, ordered once-only IDs; все5874старых IDs
сохранены,376дельта ровно новая suite. API253/frozen230×2 без регрессий.
Mutants class/alias/observer/status/shrink killed3/1/2/1/2 с SHA/EOL restore+green.
Coverage — offline substrate references/actual compat SSE recordedIO, не MODULE/
HTTP/live; actual runtime_snapshot/routing selfchecks blocked2, parity skeleton.

## Engine-cache F1: new reference tests, partial STOP (not legacy closure)

269 new tests: history72 actual native corpus; cache36 + narrow class29 + old
limits1 + source/data/SEC06 pin1 + manifest1; API55 (52 old raw observations +3
synthetic), lint65; explicit binding9. Helpers collect0. Native228×2/new focused
269×2/combined583×2/project-native288×2/API253×2 passed; full6833×2 failed25 and
frozen230×2 failed1, so no accepted-reference or MODULE parity conclusion.
Read-only provenance history_journal_safety/rollback_by_entry supplies cases,
never copied/executed old test code. Covers bounded atomic/journal/rollback/
reserved/busy-file/casing/storage/schema/cache/masking/regex branches; no complete
host history/12-worker concurrency/HTTP/Godot/editor-result/training/judge/tscn
integration coverage. Five old API contract-only refusals remain distinct from
raw native checker observations; new suite does not close public path contracts.
Existing legacy rows/fates remain byte-exact; partial foundation does not reassign
editing.write_apply/rollback or gdscript_wiring/i18n debt. Source/native bytes,
all old test assertions except sole F1 count token, existing corpora preserved.

### Engine-cache F2 — actual coverage, no legacy fate closure

Existing269 engine-cache IDs unchanged; dataset-pin ID additionally verifies
actual deployed fallback1488/version4.6.3-stable (official)/no read writes.
Exactly5 integration files get fixture arguments only; all assertions/corpus
expectations exact. Common fixture0tests selects only authorized degradation
cases; no C11/bootstrap/PathPolicy source changes. Browser guard60→72 proven
real73red→exact64restore→green, no EOL conversion. Full6831/2 twice, frozen230
twice, all6564 oldIDs/outcomes/order exact+269delta. Original168 legacy rows/fates
unchanged; host history/concurrency/HTTP/Godot/judges debts remain. Reference audit
pending, engine MODULE0/skeleton; librarian remains queued until acceptance.

### 2026-11-08 — F1 partial transfer STOP-SEC03 (NOT accepted)

Corrected-native четыре файла перенесены byte-exact с исходными SHA/EOL;
явная связка: 35 пар, 69 строк, старые33пары/порядок/алгоритм восстановимы;
synthetic minilich без __path__, canonical data/index identity, owned-only
BaseException rollback, foreign-parent refusal. Native/init/NN/production неизменны.
D47 реальный red2fail/10pass→green12; D50/D43 реальный red2fail/15pass→green17,
accepted-test изменения только разрешённые count/suffix tokens.

Корпус: 141 newly-authored cases измерены genuine native дважды (initial124,
17 quota/exact-budget/ranking/index edges); guard72 genuine native×2 green.
Начальный case111 ошибочно сохранял cached minilich.ml_data; corrected genuine
absence twice молчит и не пишет, заменён лишь этот golden с backup/receipt.
Native/logger не изменены. Golden raw-base64 сохраняет измеренный CRLF JSONL,
ts/root/strict rotation>262144; реальная telemetry только sandbox.
Focused×2: каждый246collected/called/pass, exact ordered unique IDs и одинаковые
setup/call/teardown outcomes. Guard72 входит в каждый. Real junction coverage;
genuine directory/file symlink WinError1314 остаются gaps, НЕ pass.

STOP сработал при первом квартете гейтов: lint610/0; limits610/0 и ровно два
старых warning; contract28/0; security_audit FAIL/exit1, SEC-03 librarian.py.
Неизменённый tools/security_audit.py ищет .bind( в raw text и помечает native
GDScript search literals/comments как слушающий сокет. Actual matches:
librarian.py L111/L853 STRING, L848/L850 COMMENT; AST bind/listen calls=0.
Флаг НЕ подавлен; native/ported bytes НЕ правились ради аудита. Исправление
security-checker запрещено текущим scope (other tools), требует отдельной санкции.

Actual external-report selfcheck context.ask: FAIL/exit1 из-за SEC-03;
MODULE/unit/corpus механики по-прежнему not_implemented. Это не прежний blocked/2:
security fail доминирует. Actual sandbox probe ask: unknown_tool/exit1.
44 canonical reports/86UID/4sentinels/pyc0 сохраняются; diagnostics reports внешние.
context.ask остаётся MODULE0/skeleton; reference transfer НЕ принят, parity не повышен.

После STOP новые мутации НЕ начаты, post-transfer full/frozen/API253/native-project288
регрессии×2 НЕ выполнены, gates×4/security×2 НЕ завершены, независимой приёмки НЕТ.
Ранее принятые native-only baselines и исторические STOP/seals остаются историей,
не выдаются за проверки переноса. Все rejected harness attempts сохранены.

Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/librarian-transfer-20261108/.
**Этап:** context.ask MODULE0/skeleton; librarian reference1, partial STOP-SEC03.
**Следующее действие:** получить отдельное разрешение на узкую корректировку
SEC-03 классификации STRING/COMMENT vs executable calls с red tests настоящих
bind/listen и сохранением B-1 probe exception; без file-wide allowlist. Затем
получить security green и заново продолжить неисполненный цикл переноса.
До санкции не менять security_audit/native/bytes и не заявлять acceptance/parity.

### 2026-11-11 — F1 librarian reference + D51 submitted (no MODULE acceptance)

Old librarian row/fate and all168old rows preserved. New context229 tests:
141native-measured observation cases,72guard cases,12limits,4binding; new D51 detector34.
Focused352×2 includes old72B1 +17accepted engine/project binding tests, exact once-only.
Native/canonical corpus213×2;5submitted-byte mutants killed/exact restores. Full7096×2,
old6833 ID/setup/call/teardown outcomes exact,7094pass/2same genuine1314skips;
frozen230/API253/native-project288 each×2 exact. No old testcase copied/weakened/deleted.
Actual selfcheck blocked2/probe unknown_tool1, context.ask MODULE0/skeleton;
reference submission ready for independent auditor, no full tool parity or acceptance.
Historical STOP/native-only receipts remain immutable, not rewritten as this green.


### J1a A1 — связь native cases с новым reference-corpus (2026-11-13)

Исторические судьбы строк не менялись. `test_runtime_checks.py`, `test_godot_headless_validation.py`, `test_answer_judge.py` использованы только как источники кейсов для `fixtures/corpus/assistant/judge/reference/A1/catalog.json`; новые тесты `tests/py/judge_a1/test_reference.py` (118 parity IDs + 3 native byte pins + integrity). Native118×2/0diff; genuine red121/1. Fake-worker не является `test_headless_validator_live.py`: живое/default-runtime покрытие остаётся STOP и не отмечено завершённым.


### J1b / A1 фактическая проверка (2026-11-14)

D62/D63 implemented с exact-path/byte-offset AST-исключениями, B-1/PROC_ALLOWED сохранены; D64 exact1701 B/default+explicit green. Genuine red192 collected/135failed/57passed/0errors → 192 same-ID green, все прежние121 failure ID зелёные; native118×2/canonical118×2/0diff. Real Godot4.6:4 own-sandbox default-harness probes/8 engine processes/0diff/no source writes. Mutants:15 checker+2 D64 killed/0survivors, exact SHA/EOL restore/same-ID green. Full non-live×2:7400passed/2 historical WinError1314 skips; frozen230/API253/project288×2, gates×2 и post-resource gates0. Actual selfcheck assistant.judge fail/exit1 (missing MODULE), probe unknown_tool/exit1; context.ask ok/exit0,104unit/213corpus. Aliases0, MODULE/D59/D60/A2 не implemented. A1 reference mini-seal готовится, MODULE не ported, independent acceptance pending. Все rejected setup/invocation/scope records сохранены, native originals/NN/browser-live/production HTTP нетронуты.

Подэтап reference не закрывает historical verification.check/live fate или assistant.judge MODULE. Frozen230 membership сохранён: browser141 + B-1 AST72 + B217; D51 detector34 дополнительно в full/security/mutations. Мини-seal — integrity, не самостоятельная приёмка.
Следующее действие: После A1 mini-seal: A2 native cases/corpus×2 для scene/editing/actions; D60 genuine red exact-six caps перед переносом.


### J1 / A2 private reference (2026-11-15)

Новые tests/py/judge_a2/ и private reference/A2: native214 ×2,0diff; scene_deps33/scene_actions61/file_refactor31/resource_actions35/transaction_actions32/high_level_actions22. Case-source фаты старых tests сохранены, код/host bootstrap старых тестов не копировался и не исполнялся. Corpus — реальные read/prepare вызовы и полные before/after bytes, не приёмка MODULE/editor/apply/rollback. D60 pending26 включается новым тестом, не заменяет старые пины; канонический red впереди.


### J1 / A2 final private reference coverage (2026-11-15)

A2 reference-read/prepare проверен, не public MODULE. Six sources152941 B/EOL byte-exact; native214+supp1 ×2/canonical214+supp1 ×2/0diff, full snapshots no-write. Genuine A2220/221 red → same221green, D6013/26 red → same26green; restored all249green. 6 A2+4 D60 mutants killed/0final survivors, exact bytes/SHA/LF/CRLF restore/same-ID green. Первый ambiguity survivor сохранён: wrongly named old negative-case не создавал candidates; gap закрыт новым genuine native supplement×2 и теми же mutant bytes, frozen214 не переписан. Full non-live7649passed ×2 + ровно два historical WinError1314 skips, no added skips/xfails; collected7651 и executed IDs/order exact. Frozen230/API253/project288 ×2, все288 manifest IDs. Gates/security ×2 green. Real Godot4.6:4 native/canonical reference probes/8 processes, default harness,0diff/no source writes/owned validation leftovers0; это headless structural validation, не semantic editor apply/rollback и не public judge probes. Actual selfcheck assistant.judge fail/exit1 (missing MODULE) ×2; actual probe judge unknown_tool/exit1 ×2. Actual context.ask selfcheck ok/exit0 ×2,104unit/213corpus. D60 exact-six caps реализованы minimal two-insertion checker delta, old constants/caps сохранены; D59/A3/B/+15 aliases/MODULE/public corpus не реализованы. Rejected baseline assumptions, freeze path, pytest basetemp setup, outer120s partial canonical capture, singular collected-item receipt, double-q collect verbosity и initial survivor сохранены, не засчитаны как successful evidence. A1 accepted record read-only; mini-seal/ZIP фиксируют integrity, не самостоятельную приёмку.

168 historical rows/fates untouched; all new A2 tests are additional, not native tests copied/executed.
Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/answer-judge-J1-A2-20261114/
Следующее действие: После A2 mini-seal/ZIP: A3 symbol_refactor native cases/observations ×2 до missing-code red; затем B/D59/adapter/MODULE.


### J1 A3 corpus-first (2026-11-15)

Старые rename/usages tests — только case sources, не исполнялись/не копировались. 80 new native read/prepare observations×2/0diff; private reference/A3, не закрытие historical168 live/host fates или public judge. Все пять targets ещё отсутствуют.


### J1 A3 reference evidence (2026-11-15)

A3 reference80 native×2/canonical×2/0diff; genuine85/86 missing-code red → same86 green, four critical mutants killed/0survivors/exact SHA/LF/CRLF/same-ID restore. Five native140474 B byte-exact; part1 CRLF824 сохранён. Real Godot: native/canonical rename prepare→batch,2 probes/4 processes,0diff/no project writes/owned leftovers0. Первый live fixture fail (unscanned class_name) сохранён; только owned fixture получил explicit preload, ни source, ни frozen80 не менялись. Actual gates0; actual selfcheck assistant.judge fail/exit1 missing MODULE и probe unknown_tool/exit1. A3 не закрывает public MODULE, apply/rollback, historical host/editor-live fates; independent acceptance не объявляется. Полный финальный regression×2 остаётся B/final.


### J1 public judge — final submitted parity (2026-11-15)

J1 полностью реализован и передаётся на независимый аудит: public assistant.judge/judge, read/idempotent, fs+librarian, strict input/result envelope, domain pure/app7. Genuine native74×2 → actual build_agent→agent.call74×2/0diff; final ordinary public corpus74×2/0diff. Actual selfcheck assistant.judge ok/exit0×2 (8unit/74corpus), context.ask ok/exit0×2 (104/213). Final full7923collected/7921passed×2, exact ordered once-only IDs, только два исторических symlink WinError1314 gaps. Frozen230/API253/project288×2, все288 IDs, security/layers/limits/contract×2 green. Четыре actual CLI probes: answer0/invalid_input1/denied1/no-write0; owned state only, no project writes. Final185 new tests green;14 current-submitted mutants killed/0survivors, byte/SHA/LF/CRLF restores/same-ID green. Fifteen Python references+GD harness436437 B byte-exact; part1CRLF824; old35 binding prefix exact,total50/rawLF84. D59/D65–D69 только в санкционированных границах. Native parser/quartet/parser_base/security/check_limits и shared snapshot/selfcheck/generator unchanged. A1/A2/A3 full readback/seal/archive pins exact, только уже раскрытая A1 empty-file inode cohort1430. Rejected invocations/full failures/sample-write defect и initial A2 survivor не удалены; D68 genuine2red→same2green, D69 genuine52fail→same-ID green, fixture isolation repaired only in new B scope, no foreign-parent adoption. Один поздний full run дал importlib source_to_code MemoryError: cause unestablished; unchanged node alone exit0, fresh exclusive full7921pass/2oldskips exit0; failed run retained, not counted. Полный final ZIP включает byte-exact7 mini-seals/8 prior archives, включая rejected incomplete A1 ZIP; их наличие не означает принятия rejected artifacts. Prior real Godot reference probes retained; no public apply/rollback/editor semantic/live/NN/browser/HTTP claim. MODULE_ready=true; independent_acceptance=false, audit pending.

Все168 исторических строк/fates сохранены; native tests не копировались и не запускались. Public74 отвечает за judge/read-only; host/editor/apply/rollback/live fates не переименованы и не закрыты. New B185, A3 86, A2 249, A1 accepted scope остаются раздельными; no new skip/xfail.

## T1 / T-A — дополнительные native cases (2026-11-21)

`tests/py/transfer_t1/` и `tests/py/security/test_t1_native_gate.py` добавляют
71 собственный тест: native29 paired observations, byte/EOL/alias/rollback
guards и fail-closed SEC/limits. Код старых тестов не копировался и не исполнялся.
Прежние 168 строк и судьбы сохранены; node/live/apply obligations не закрываются
read/prepare corpus. Фактическая проверка: full8044passed+два исторических skip×2,
точные ordered IDs и setup/call/teardown; лист `T1-godot-tools.md`.

## T1 / T-B — write-loop case provenance

Все старые строки сохранены: test_transaction_actions/flow и rollback_by_entry
имеют fate corpus. Из native main confirmation и native prepare извлечены 13
новых independently authored cases; preparation pair raw/no-write ×2 снят до кода.
Новые transfer_t1 write/turn, security/test_t1_write_confirmation и module unit
tests проверяют реальный Agent, explicit confirmation, rejection, policy/stale,
TTL, compensation/rollback и no-unexpected-write. Старые tests не копировались
и не запускались. B/C/D внешние rehearsal receipts не считаются production
GREEN или live/provider success; лист `assistant.write.md`.
T-B ADR0080 дополнение: module test_directories five-ID actual RED→GREEN×2;
tests/py/security/test_t1_parent_ownership.py — own receipt/foreign-clone/filled
directory/move-UID/recovery/bounded-footprint cases. Не старый код тестов.
Initial security10: 2fail/8pass; equal-byte inverse defect RED исправлен,
native UID count assumption rejected и сохранён; 58paired GREEN IDs.
Unique-bound дополнительный тест убил survivor retry; forward/inverse/bound
raw-restored mutants. Historical168 rows/fates/accepted IDs не изменены.
T-B ADR0081–83: шесть старых integration IDs получили genuine full RED;
разрешены только четыре names/effects/count и native_planner port token.
Own test_followup_pins: шесть strict old-byte SHA/EOL reconstruction cases;
test_t1_parent_plain: два real Agent port attacks, production RED→GREEN×2;
test_parent_preview_bound: actual results+kernel.schema,1pass/3fail→4GREEN×2.
Начальные observer assumptions/failed runs сохранены; старые assertions,
native/corpora и все historical168 rows/fates не ослаблялись и не удалялись.
Три followup safety/byte/bound mutants killed/exact restored/same-ID GREEN.
ADR0084 adds one actual-area RED→GREEN test retaining all original hard caps;
directory safety cases/assertions unchanged, compact-source3 mutants killed
and exact restored. Failed final gates/source-drift batches remain retained.
T-B final A4:8122passed+только два historical WinError1314 skips×2; exact ordered
A+K1 IDs/setup-call-teardown preserved. Selected83/probes×2 и шесть genuine
selfchecks/gates×2 passed. Complete accepted K1 offline helper/config observer
исправлен без изменения K1/native/checker; rejected invocation retained.
T-C own channel cases derive from native server/auth/MCP semantics without copying
old tests: production four entry/corpus RED + nine exact-cap2fail/7pass → own28
GREEN×2/native auth5×2. Native port_guard remains paired unsafe-behavior reference,
never unowned termination. ADR0085/SEC-T1-LOCAL. All historical168 rows/fates stay.
T-C selected production suite71GREEN×2 includes actual child MCP streams, native
session ownership, Host/Origin/control plane, endpoint raw+identity inverse and
project/source profile refusals. Three production current-byte mutants killed/
exact restored; final current raw-proof/owned-close cases complete four current
mutants. Native auth corpus5×2. Full8193passed+only two historical WinError1314
skips×2 preserves A/K1/published-B ordered IDs/phases; frozen230/API253/project288,
six genuine mechanic selfchecks and four static gates×2. Real MCP child pipes/
native-composed WSGI clients×2 restore physical files/directories exactly.
Saved raw results re-read against unchanged production inventory before closure.
No old test code/network/new skip copied; historical168 rows/fates unchanged.

## T1 T-D — new production cases, native drivers remain case sources

33 production overlay/security cases +5 panel contracts (38 IDs); genuine missing
17-ID RED, native SEC05 nine2fail/7control RED, six external/encoded reference RED,
panel five4fail/1control RED. Own attribute/invalid resource fixture/repeated pytest
argv/create-path observers rejected and retained, not counted as valid RED.
Corrected default/file-list cases reproved by exact own integration reversals.
33GREEN×2/security0×2 before final regression. Native A7 seven cases×2 and guarded
production seven cases×2 complete report/raw/transient equality; only proved new
UID/unique_id and matching content hashes normalized, sentinel/refusals retained.
Actual default Agent/B four safe structural cycles +three refusals×2; captured UI
nine cases×2 and configured headless EditorPlugin activation×2. Ten current mutants
killed/exact restored/same-ID GREEN; metadata/literal observer refusals disclosed.
All168 historical rows/fates unchanged. Nine native GDScript drivers are case-source
only, not copied/executed as new tests. NN/DoH/n8n excluded. Script-bearing structural,
visual desktop/browser/provider success not claimed. Fresh final gates pending.

ADR0087 adds7 new IDs (six shader include paths +one owned observer registry)
without changing any previous ID/fate. Genuine six before-engine failures and
one registry failure; separate genuine accepted K1 projection failure. Only exact
own D insert reversal before unchanged old byte/count/EOL/SHA assertions; submitted
C test reconstructs exactly. Paired66GREEN and13 fresh current A3 restored mutants;
initial7163pass/1068fail/2historical skips retained. Native shader null/outside-read
unproved. Fresh full/gates/six selfchecks/client/readback/ZIP still required.

ADR0088 adds36 native script-fact differential IDs and1 own scope/pin ID; all
old facts/assertions preserved via one exact in-memory manifest composition.
Native36×2/source reference SHA exact, original frozen corpus unchanged. ADR0089
adds6 genuine relative plugin/resource pre-engine refusal cases→paired GREEN.
No old168 fate or ID removed/new skip; prior8237pass/1failure/2gaps retained.
Fresh15 current mutants/full/gates/seven selfchecks/client/readback/ZIP next.

T-D final:8281passed+only two historical WinError1314 skips×2; every published
A/K1/B/C ID/order/setup-call-teardown preserved. Four gates/seven selfchecks×2 ok,
current native/B/MCP-WSGI physical restoration/plugin-owned namespace read back;
15 fresh A4 mutants killed/exact-restored.88 new IDs total versus C, including
36 fact parameters; all168 old fates retained. Safe/offline scope and conservative
parity gaps only; failed fulls retained; seal LAST/full ZIP precede T-E.

T-E authored3 new documentation cases: actual CLI parser/canonical external state,
four-tool explicit write authority/read-only K1, truthful native/live/exclusion/
bridge-state/acceptance gaps. Staged before README correction; original bytes
preserved. Existing168 fates and all A–D IDs unchanged. Genuine3RED→paired same3GREEN;
first wrong CLI identifier flags2pass/1fail retained, no parser/assertion changes.
Actual full8284pass+two historical WinError1314 skips×2 and A/K1/B/C/D ID/phase order
exact; frozen230/API253/project288×2, four gates/seven selfchecks×2 ok.91 additional
IDs versus C (88D+3E), no old-fate removal/newskip. Six current E mutants killed/
restored exact bytes/SHA/EOL/mtime/same IDs; actual CLI/local/native pairs/readback
exact. Wrong conflict expectation/zero-collected selector retained, not passed
evidence. Safe/offline/conservative gaps explicit; audit acceptance not claimed.
