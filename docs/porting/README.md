# docs/porting — рабочие листы механик (R-19)

Один файл на механику: `docs/porting/<module_id>.md` (например
`docs/porting/project_text.search.md`). Лист создаётся **до** первой правки кода
и обновляется в конце каждого шага, а не в конце работы.

Зачем: работа может прерваться в любой момент. Лист — единственное место, где
записано, на чём остановились и что делать дальше, без чтения переписки.

Порядок действий нового чата:

1. `docs/PROGRESS.md` — найти первую механику с этапом `< 7`.
2. Открыть её лист здесь.
3. Прочитать раздел «Следующее действие».
4. Последняя сессия `docs/WORKLOG.md` — контекст, почему так вышло.

Шаблон: `_template.md`. Копировать в новый файл, поля не переименовывать —
по ним же ориентируется `tools/selfcheck.py` и человек.

Стартовые промпты для новой сессии — `_start-prompt.<фича>.md`:

- `_start-prompt.md` — первый срез, `project_text.search` (выполнен, оставлен как образец);
- `_start-prompt.functions.md` — второй срез, `code_intel.functions` (выполнен);
- `_start-prompt.usages.md` — третий срез, `code_intel.usages` (три стадии: `formats/gdscript` → `code_intel/shared/symbol_index` → модуль `usages`);
- `_start-prompt.analyze_rename.md` — четвёртый срез, `analyze_rename` (второй инструмент того же модуля: предпросмотр переименования, риски, `mode`);
- `_start-prompt.write_preview.md` — пятый срез, **воронка записи, часть 1**: `editing.write_preview` + планировщик `editing.symbol_rename` (план, `digest`, WAL `PREPARED`, диффы, `exclude`, отказы; `apply` — часть 2);
- `_start-prompt.write_apply.md` — шестой срез, **воронка записи, часть 2**: `editing.write_apply` + `editing.rollback` (`APPLYING`/`COMMITTED`/`ROLLING_BACK`, квитанции, recovery, лок, идемпотентность, откат побайтово) (выполнен);
- `_start-prompt.scene_bridge.md` — седьмой срез, **мост редактора, часть A**: транспорт между процессами (кадр, handshake, `verbs_version`, таймауты) + `context.editor_context` (`editor_ping`, `editor_state`, `editor_selection`, только чтение); контракт фиксируется сразу для частей B и C. **Выполнена только контрактная стадия** — исполнение см. `_start-prompt.editor_bridge_a.md`;
- `_start-prompt.fixup-bridge.md` — **починка перед частью B** (не новый срез): `_handlers` в `gen_contract` перестаёт быть постоянным выключателем, схемы результата примитивов, политика `verbs_version`, проверяемый путь вклада в `selfcheck` (выполнен, аудит принял 2026-10-27);
- `_start-prompt.schema-union.md` — **фикс до части A**: union-типы в `kernel/schema` (`["string","null"]` бросал `TypeError`), fail-closed на неизвестный тип, гейт в `gen_contract` (выполнен, аудит принял 2026-10-27: репро `[]`, мутация валит 4 теста, гейт ловит `"date"` в `verbs[]` и в `capabilities/*.json`);
- `_start-prompt.schema-totality.md` — **выполнен, аудит принял 2026-10-27**: тотальность доказана (мутация `str`-защиты валит 2 теста, мутация union — 4, гейт ловит `"type": 5`); замечание к отчёту — «11 → 14» и «collect 14», фактически 13 тестов в файле (320 = 317 + 2 + 1);
- `_start-prompt.editor_bridge_a.md` — **восьмой срез, выполнен и принят аудитом 2026-10-28**: мост редактора, часть A (транспорт `substrate/editor/`, GDScript-сервер с 3 маркерами `# verb:`, вклад `context.editor_context`, `fake_editor.py`; 417 тестов, 8 артефактов, `editor_verbs.json` `F73AB2D8…B1E4`); GDScript — `needs_live`;
- `_start-prompt.harness-selfcheck.md` — **фаза A.1.1, выполнена**: харнесс моста обязан доказывать сам себя или честно писать `no_client`; документация — приёмка через `pytest tests/py/live`, а не одиночный `-s`;
- `_start-prompt.bridge-live.md` — **фаза A.1, выполнена**: закрыть долг «GDScript моста не проверен» — живой прогон в Godot (`editor/harness/bridge_probe.gd` + `needs_live`-тест) или, если бинаря нет, структурная проверка `tools/gd_guard.py` (маркер↔`func`, `extends`, скобки вне строк, смешение табов) с тестами и мутацией; часть B не начинать;
- `_start-prompt.editor_live.md` — **фаза B.0, выполнена**: мост внутри настоящего редактора — `plugin.gd` → `lifecycle` (старт/стоп, `port.json`), живой `needs_live`-тест редакторской ветки (`editor_available`, `open_scenes`, `editor_state`, выделение) и мутации `has_editor()` в обе стороны; без неё часть B (запись в сцену) нечем проверять;
- `_start-prompt.scene_ops_b3.md` — **фаза B.3, выполнена и принята аудитом 2026-10-29** (этап 7 за `editing.scene_ops`; свои прогоны аудита: 449 non-live + 3 live, `verbs_version 3`, 6 примитивов, корпус 102/0, подложка `# verb: editor_scene_bogus` → `gen_contract` fail, мутация сверки `expected_revision` в `undo()` → красный живой тест, файл восстановлен побайтово `B7AFF592B75D`) — ставила: доказать «один undo на батч» — новый примитив `editor_scene_undo` (`verbs_version` 2→3), откат обоих свойств батча, `nothing_to_undo` на пустой истории, «после сбоя сцена не изменилась» через undo, и три мутации (`create_action`, `commit_action`, `expected_revision`), которые сейчас зелёные;
- `_start-prompt.tscn_formats.md` — **часть C, выполнена и принята аудитом 2026-10-29** (сессия 46: ожидания пересняты с эталона независимо 16/16, M1/M2/M3/IO красные, формат-тесты 100/0, регрессия 532+3): `.tscn`/`.tres` как файлы — единственный разбор в `python/formats/tscn.py` (167 строк, `BF844574D6E5…`): `structure(text)` = ответ эталона `node_refactor.parse_tscn_structure`, `fields(text)` = ответ `scene_deps.parse_scene`, `patch(text, edits)` по смещениям (пустой набор — тот же текст байт в байт), корпус `fixtures/parity/tscn/` (12+ файлов, включая `.tres`, BOM, CRLF) и постоянные тесты; линт (`verification.tscn_lint`) и механики `scene_model.*` — не в этом срезе;
- `_start-prompt.gd_lint.md` — **C.2, выполнена и принята аудитом 2026-10-29 (сессия 48)**: механика `verification.gd_lint` (эталон `gd_lint.py`, 191 строка: `lint_gdscript` `:69`, `_literal_kind` `:50`, `MAX_ERRORS = 8`, RU-сообщения) — лист механики на этапе 1, корпус снят с эталона, находки как данные (`code`/`line`/`message`), строка `test_gdscript_wiring.py` (`tests-map.md:65`) отдана этой механике; **принято своими прогонами**: corpus 37 переснят с эталона 37/37, дифференциал на 128 живых `.gd` (эталон == порт), M1–M3 и подложки TOOLS/EXPECT/IO красные;
- `_start-prompt.scene_deps.md` — **C.5, выполнена и принята аудитом 2026-10-29 (сессия 54)**: две механики сразу — `scene_model.connections` и `scene_model.scene_deps` (эталон `scene_deps.py`: `to_snake:73`, `parse_scene:120`, `extract_handlers:175`, `analyze_scene_action:271`, `analyze_script_action:362`; старый вход `main.py:1904/1930`), два листа на этапе 1, два корпуса с эталона, `handlers` только в `formats/gdscript/`, `gen_contract` 12→14; **свои прогоны аудита**: `connections` 25/25 (display из `describe_scene`), `scene_deps` 40/40 + дифференциал 81 файл, M1/M2/M4/M5/M6 и подложки TOOLS/EXPECT/IO красные, M3 эквивалентен (исключение своей сцены недостижимо), невосстановленный дрейф `candidates[-1]` поймана selfcheck и откачена байтово (`4D192DD6FDAD`/6683 B, `4F7366C418DD`/761 B);
- `_start-prompt.node_rename.md` — **C.6, выполнена и принята аудитом 2026-10-30 (сессия 56)**: `scene_model.node_rename` (`node_rename_preview`; эталон `node_refactor.prepare_node_rename:225-541`, `apply_prepared_node_refactor:969` — вне среза), заголовок узла, `parent=` детей, `[connection] from/to`, `NodePath` анимаций, `$Путь`/`get_node`/`find_child`, отказ при коллизии и при синтаксической ошибке после правки, `scripts_only`/`previous_name`, `reference_count` без «обещаний сцены»; лист, корпус 36/36, `gen_contract` 14→15; **свои прогоны аудита**: 36/36 пересняты с эталона (полный план, Base64-байты, diff, порядок, буквальные отказы), синтетика 8/8, вложенный `previous_name` 1/1, 1684 non-live + 3 live (= collect-only), M1/M2/M4–M7 красные, M3 эквивалент по корпусу (долг: нет кейса с вложенным `previous_name`), P1–P3 красные, всё восстановлено побайтово;

- `_start-prompt.tscn_lint.md` — **C.8 реализована, этап6, ожидает независимого аудита; не принята**: read-only `verification.tscn_lint/check(path, content, planned_paths=[]) → fixed/changed/stringproblems`, буквальный `lint_and_fix_tscn` целиком, `.tscn/.scn` gate; fixed не записывается/не исполняется, агрегатор/API/headless/repair/WAL/undo/editor вне среза. Actual-old65/0diff,18inputs/83pins;native315/65/ok,2337nonlive+3live exactIDs/0skip,469fullcorpus/0diff,230physicalscenes/0diff,5CLI args-file,20submittedmutationruns/allcaught/byte-restoreexact. `gen_contract`17→18,old17cards exact; [лист](verification.tscn_lint.md), WORKLOG59;
- `_start-prompt.node_reparent.md` — **C.7, выполнена и принята аудитом 2026-10-30 (сессия 58)**: два read-only плана `node_reparent_preview`/`node_delete_preview`, apply969/undo/history/WAL/editor вне среза. Переснято мной 32/32 и 27/27 с `prepare_node_reparent`/`prepare_node_deletion` (полный словарь, Base64, diff, порядок `deleted_nodes`/`warnings`); мои прогоны 2014 non-live + 3 live (= collect-only), selfcheck 155/32 и 131/27, контракт 17, snapshot 404/0, layers/limits 481/0; M2–M8 красные, M1 (вставка `parent=`) и M5 (дубль пары от корня) эквивалентны с доказательством, P1–P3 красные, восстановление побайтовое; `gen_contract` 15→17, frozen и старый плагин не тронуты, дерево 1931/мусор 0;
- `_start-prompt.node_info.md` — **C.4, выполнена и принята аудитом 2026-10-29 (сессия 52)**: механика `scene_model.node_info`, инструмент `node` (эталон `node_refactor.find_node_in_scene:185-222` + `_rel_path_between:163-182`): разрешение спецификации `%unique` / `.` / путь / одинокое имя с типизированными отказами и карточка узла как данные, разбор только через `python/formats/tscn.py`, лист механики на этапе 1, корпус ≥14 случаев с эталона, `gen_contract` 11→12;
- `_start-prompt.scene_tree.md` — **C.3, выполнена и принята аудитом 2026-10-29 (сессия 50)**: механика `scene_model.tree`, инструмент `scene` (эталон `project_tools.describe_scene:1269-1372`): сводка сцены как данные + текст, который обязан совпасть с эталоном побайтово, разбор только через `python/formats/tscn.py`, лист механики на этапе 1, корпус ≥14 сцен с эталона, `gen_contract` 10→11;

- `_start-prompt.scene_ops_b2.md` — **фаза B.2, выполнена (принята в B.3 2026-10-29)**: оживить `editing.scene_ops` в настоящем редакторе — починить парс-ошибки `scene_executor.gd:101/177` (движок: `commit_action()` у `EditorUndoRedoManager` возвращает void), сделать `_scan` харнесса честным (сейчас `broken == []` при некомпилируемом скрипте), доказать живой `plan → apply → undo` на временной сцене;
- `_start-prompt.scene_ops_b1.md` — **фаза B.1, выполнена (вошла в B.3)**: убрать две копии `verbs_version: 1` (фикстура `editor_context/tests/test_core.py:13`, харнесс `bridge_probe.gd:134`, закрепление в `test_bridge_live.py:174`) и решить машинно судьбу корпуса для механик с исполнением в GDScript (`corpus: "live"` с тестом или ветка `REFERENCES`); код части B не переписывается;
- `_start-prompt.scene_ops_b.md` — **девятый срез, текущий**: мост редактора, часть B — `editing.scene_ops` (план/применение батча, один undo на батч, `expected_revision`, `plan_digest`, квитанции, `verbs_version: 2`); живого Godot нет, поэтому приёмка через фейк, схемы и мутации;
- `_audit-handoff.md` — передача роли аудитора: состояние, «дифф» сессии, открытые находки, чеклист проверки и готовый промпт для нового чата-аудитора.
- `_start-prompt.lint-arch-guard.md` — **фаза 0.5, выполнена**: `lint_arch` перестаёт быть «написано, но не проверено» — правило «нет IO в `python/modules/*/*/domain/**`» (в `kernel/` IO законен: `paths.py:12`, `write_plan.py:12`), сужение `_same_feature` (сейчас `from python.modules import scene_model` проходит), по два теста и мутации на правило, отчётность `files=`/EOL по R-22;
- `_start-prompt.context-and-rename.md` — **фаза 1 — принята аудитом 2026-10-27** (`context.gather` — этап 7, `editing.symbol_rename` — модуль-вклад, 377 тестов, корпус 102/0): починить `context.gather` (владелец составного `context`, без него `context.editor_context` вкладываться некуда) — контракт `context`, `ContextSection` в `context/shared/`, встроенные секции `project`/`tools`, вклады через реестр, корпус 3 кейса; и оформить `editing.symbol_rename` как модуль-вклад (решение пользователя 2026-10-27: свой `MODULE` + тесты, не слияние с `write_preview`);

- `_start-prompt.split_py_apply.md` — **C.20, выдан аудитором 2026-11-01 (сессия 76), текущий срез**: запись split-плана — инструмент `split_apply` (эталон `apply_prepared_split:718-767`) плюс операции `create`/`delete` в воронке записи, отдельный ADR-0015 (пять обязательных вопросов), корпус с кейса 097; §10 содержит замечания приёмки C.19: A1 живой прогон требует временно включённого `[editor_plugins]` (иначе 2 из 3 красные по `port.json`), A2 уборка 162 `.gd.uid` из `fixtures/corpus/**` после live, A3 заморозка SHA сдачи после правки записей, A4 числа «20 механик этапа 0» и «ADR 14», A5 приёмка C.19 моими числами (4249/0/0/0, 820/0, 25, 544/0, 64 пина, дельты 186→128 · 352→247 · 168→116);

- `_start-prompt.paths_preview.md` — **C.21, принят аудитом 2026-11-02 (сессия 76)**: read-only механика `editing.paths_preview` (поиск ссылок на путь и проекция внутренних относительных путей, эталон `file_refactor.py:87`/`:181`) плюс шаг 0 — долги приёмки C.20 (F1 пересъёмка отчёта `editing.split_py`, F2 строки `tests-map` для семи файлов C.20, F3 откат/граница переформатированного кейса `context/gather/001`); запись и перенос файлов вынесены в C.22; §9 — восемь уроков прошлых срезов, §10 — семь preflight-вопросов, до ответов аудитора production-код не пишется.

- `_start-prompt.resource_ops.md` — **C.23, выдан аудитором 2026-11-02 (сессия 76), текущий срез**: `editing.resource_ops` — строгая схема правок `.tres` (`normalize_action`, `canonical_digest`, `file_sha256`, `prepare`) и запись **только через общую воронку**; редакторская половина (`agent_resource_executor.gd`, temp-save) не входит. Шаг 0 — три долга C.22 (ячейка `editing.file_refactor` 0→7, `parity` → `ported`, строки C.22 в `tests-map`). §10 — семь preflight-вопросов (регистрация/факт native, где живёт apply, байты `.tres` и выбор `script_edit` vs `replace_raw`, полная схема операций, нужен ли ADR-0017, политика `addons`/`plugin.cfg`/`project.godot`, корпус из старых тестов); production до ответа не пишется.
- `_start-prompt.file_refactor.md` — **C.22, принят аудитом 2026-11-02 (сессия 76)**: `editing.file_refactor` — запись: prepare/apply переименования и переноса файла и каталога, case-only rename, `.import`/`.uid`-компаньоны, синхронизация ссылок; введены операции `move`/`dir_case`/`replace_raw` и фазовый WAL `EFFECT_INTENT` (ADR-0016 принят); read-часть переиспользуется из C.21.
- `_start-prompt.project_text_read_tree.md` — **C.25, preflight; не приёмка**: `project_text.read` + `project_text.tree`, read-only перенос чтения и дерева. Сначала настоящий native MCP `list_tools`/`call_tool` в `user` и `agent-dev`, затем §9.2–9.5; периметр и контракт 27/28 решает пользователь. Листы [read](project_text.read.md) и [tree](project_text.tree.md); production до ответа запрещён, стадии не меняются.
- `_start-prompt.auditor-next.md` — **передача роли аудитора, сессия 77 (2026-11-03)**: где мы (27 механик принято, C.25 в работе), что прочитать, как проверять **своими** прогонами, мандат D19 и классовые разрешения, **сложность задач** (жёсткие / средние / простые и кому какую отдавать), долги аудитора, стоп-условия, формат вердикта.
- `_start-prompt.browser_b1.md` — **B-1, выдан аудитором 2026-11-03 (сессия 77, продолжение), возобновлён после приёмки sec20_js_comments (сессия 78), принят аудитом 2026-11-04 (сессия 78)**: базис браузерной ветки — verbatim `browser_manager.py` + `cdp_ws.py` из native в `substrate/llm/browser/`, контракт-данные `contract/browser_stealth.json` (sites/launch/webdriver_flag/allowed_masking/forbidden_techniques), стражи R-21/SEC-19/SEC-20, read-only фасад и живой запуск Chrome (профиль Godot_AI_Profile, debuggerAddress, webdriver=false) на file://-фикстурах; вне границы — net_monitor/sites/live_input/ai_studio_net/qwen_net/backends и парсеры (B-2/B-3); жёсткий класс, модель gpt-6.1-sol по решению пользователя
- `_start-prompt.sec20_js_comments.md` — **микро-срез SEC-20, выдан аудитором 2026-11-03 (сессия 77, D28), принят аудитом 2026-11-03 (сессия 78)**: ремонт проекции `check_browser_stealth` (JS-комментарии), red-пины на реальные подмены; B-1 возобновляется после его приёмки
- `docs/porting/sec03_nonlistening_probe.md` — **микро-срез SEC-03 (исключение non-listening probe), принят аудитом 2026-11-03 (сессия 78)**: единственный AST-доказанный exclusive bind `127.0.0.1:9222` в `python/substrate/llm/browser/facade.py` (with-закрыт до запуска, OSError → RuntimeError fail-closed), все прочие listener-совпадения и отражение/алиасы отсечены; страж `tools/security_audit.py` (+3822 B), инвариант SEC-03 уточнён, тест-набор 71/71; аудит: двойной корпус 71/71, полный security 237/0/0/2skip, B-1+D28 regression 93/93, гейты ok/0, свои мутации ×2 (сокрытие исключения → 3 красных; reflection-фильтр выживает в наборе — прямой пробник подтверждает его уникальную роль, мелкий долг: нет независимого мутационного покрытия)
- `_start-prompt.browser_b2.md` — **B-2 (net_monitor), промпт поставлен аудитором 2026-11-04 после приёмки B-1 базиса, принят аудитом 2026-11-04 (сессия 78); класс — средний (все решения приняты); Фаза A — D29 классовый допуск FILE_MAX 400→600 для verbatim-эталонов; маршрут D26; долги: live net_monitor (записанный сайт) и независимый кейс pop_http_error
- `_start-prompt.browser_b3.md` — **B-3 (sites/live_input/ai_studio_net/qwen_net/browser_backend), промпт поставлен аудитором 2026-11-04 после приёмки B-2; класс — средний (Фаза A не нужна: все 5 файлов в лимите R-06); SEC-19/R-21-пины по needs_visibility_spoof — главный содержательный блок; verbatim ×5; live — долг с записанным сайтом; последний срез браузерной ветки
- `_start-prompt.debt-cases.md` — **долг-срез, выдан аудитором 2026-11-04 (сессия 78), текущий срез**: закрытие двух мутационных долгов (SEC-03 reflection-кейс, B-2 pop_http_error one-shot); класс простой, модель средняя/дешёвая; после приёмки — срез no-focus детерминизма (B-1) и runtime-интеграция браузера
- `_start-prompt.browser-runtime.md` — **объединённый срез браузерной ветки, выдан 2026-11-04 (сессия 78): часть A (no-focus) ПРИНЯТА; часть B: B.0–B.3 выполнены (7 парсеров byte-exact в substrate/llm/parsers/, связка D33, 141 тест ×2), B.4 STOP разобран — причина нативная семантика switch_to.window/Target.activateTarget, критерий уточнён D34 (двухфазный), B.5/live replay не выполнены — приёмка B после их закрытия**
- `_start-prompt.api-core.md` — **срез «API-ядро LLM», выдан аудитором 2026-11-04, приёмка аудита 2026-11-05: reference-срез принят (11 файлов byte-exact, corpus 210, мутации 5/5, гейты зелёные); полные assistant-модули НЕ ported (MODULE/HTTP — отдельные мандаты)**: byte-exact перенос 11 файлов замкнутого API-слоя (api_keys/providers/catalog→providers_catalog/model_cache/openai_compat/anthropic_compat/agent_prompts/rate_limit/md_to_bbcode/chat_store/api_history) в `substrate/llm/api/` (замена стабов байтами native), расширение связки D33, классовое правило лимитов по D32, corpus + SEC (синтетические ключи, sandbox-каталог, сеть запрещена), мутации ≥2+1; вне границы — chat_routes (flask — ADR интеграционной стадии), api_backend (тянет runtime_debug), server_state/history_manager; класс жёсткий, модель gpt-6.1-sol
- `_start-prompt.routing-runtime.md` — **срез «runtime-контекст + routing», выдан аудитором 2026-11-05 (сессия 78), приёмка аудита 2026-11-05: A+B reference-срез принят (3 файла byte-exact, corpus 241, focused 376×2, полный 6248 passed/2 legacy skip, мутации 5/5, гейты зелёные); context.runtime_snapshot и assistant.routing остаются skeleton — MODULE/HTTP-интеграция отдельные мандаты**: Часть A — context.runtime_snapshot (runtime_debug.py 12251 B ed7d6087…, stdlib-only + editor_context.py 14161 B 32613d28…, ноль импортов — единственные недостающие зависимости api_backend); Часть B — assistant.routing (api_backend.py 91906 B 93d22fb5…) в substrate/llm/backends/, замыкание полностью закрыто после части A; связка runtime_bindings (D33-пины), транспортные тесты только на локальном recorded-сервере 127.0.0.1 (внешняя сеть и реальные ключи запрещены, D37-прецедент), D36: реальный DoH вне среза; вне границ: flask/chat_routes, server_state/history_manager, answer_judge (gd-механики), librarian/context.ask (90f4f664…); класс жёсткий, модель gpt-6.1-sol, приёмка — независимый аудит.
- `_start-prompt.project-core.md` — **срез «проектный фундамент», выдан аудитором 2026-11-05 (сессия 78), приёмка аудита 2026-11-06: reference-срез принят (2 файла byte-exact, corpus 303, мутации 6/6, гейты зелёные); MODULE-интеграция project_ops.* — отдельный мандат**: project_tools.py 102 471 B 79e9b035… (замыкание: errno + text_sanitize — уже ported) + project_settings_actions.py 13 735 B fcdb4635… в `substrate/project/` (D39, spec-before-code); связка runtime_bindings +2 алиаса (D33-пины, порядок после парсерных); SEC-ядро: traversal/симлинки/casing/UTF-8 на fixture-проектах, внешняя сеть запрещена; классовое правило лимитов с red-доказательством; мутации ≥3 (can_read deny→allow, _resolve_safe_path, alias identity); открывает project_ops.*, runtime_checks, headless, answer_judge; parity L95–97 остаются skeleton (прецедент api-core); класс жёсткий, модель gpt-6.1-sol, приёмка — независимый аудит.
- `_start-prompt.engine-cache.md` — **срез «gd-ядро: история + кэш движка», приёмка аудита 2026-11-06: reference-срез принят (5 native byte-exact + данные 2 МБ, corpus, isolation, мутации 7/7, гейты зелёные); MODULE-интеграция engine_kb.* — отдельный мандат**: history_manager.py 48 840 B f6655173… (слой хранения, замыкание закрыто после project-core) + gd_api_cache.py 11 545 B 6e6f5e0c… (engine_kb.engine_info + api_cache_refresh — L42/L44) + gd_api_check.py 9137 B b9e0df9f… + gd_lint.py 9640 B 66618648… в substrate/{store,engine,verification}/ (D40); данные agent_api_cache/default_api_cache.json 2 004 630 B 7352d27c… byte-exact в корень плагина с пином D41 (тесты только в sandbox); связка +4 алиаса (D33); мутации ≥4 (атомарная запись, битый кэш, deny-матрица, эталон gd_lint); классовое правило D42; открывает аудит tscn_lint (C.8) и предпосылки answer_judge; engine_kb.class_api (C.11) не трогается; вне границ flask/api_backend/answer_judge; класс жёсткий, модель gpt-6.1-sol, приёмка — независимый аудит
- `_start-prompt.librarian.md` — **F1 corrected-native reference submission 2026-11-11, independent auditor acceptance pending; context.ask MODULE0/skeleton**: four byte-exact files librarian97676B340b5dd2/index65753B2f7694a9/ml_data32324Be13d5680/parser15723Bbf35dcea; D46–D50 binding35/69lines and narrow context cap; D51 AST SEC03 with true-positive guard/B1 unchanged; corpus141+guard72, focused352×2/native213×2, mutants5/5 exact restores, full7094pass+2same1314skip×2/frozen230/API253/native288×2, gates/security green; selfcheck blocked2/probe unknown_tool1; fresh sealed dossier/ZIP and independent integrity receipt, actual acceptance only by auditor. Following old STOP entry remains historical, not current authority.
- `_start-prompt.librarian.md` — **срез «Библиотекарь», выдан аудитором 2026-11-06, STOP-SEC 2026-11-07 — отложен до фикса native (решение пользователя: гард project_tools в native librarian/индексатор, затем re-port byte-exact; native-дыра чтения вне корня подтверждена sandbox-пробами)**: ml_project_index.py 64 059 B `474dcc3b…` + librarian.py 96 356 B `90f4f664…` в `substrate/context/` (D46); связка +2 алиаса + синтетический родительский пакет `minilich` (без NN; dormant-ветка ml_data падает честно); SEC-ядро: чтения через гард project_tools, traversal/симлинки/casing/UTF-8 матрицы + пин поведения `_log_query`; corpus fixtures/corpus/context/librarian; D47 классовый лимит; мутации ≥3; **предусловие: engine-cache закрыт независимой приёмкой**; вне границ NN-модули и native minilich/__init__; класс жёсткий, модель gpt-6.1-sol, приёмка — независимый аудит.



Внутри: что прочитать, фактическое состояние репозитория на момент старта, шаги M0…M9,
решения, которые портер обязан принять, кейсы корпуса и что аудитор будет требовать
в отчёте. Копировать целиком в чат модели-портера.

Связь с другими файлами:

| Файл | Что даёт листу |
|---|---|
| `docs/tests-map.md` | какие старые тесты относятся к механике и какова их судьба |
| `docs/mapping.md` | какой старый код реализует механику и как его делить |
| `fixtures/corpus/` | эталон поведения |
| `reports/selfcheck/<module_id>.json` | последний машинный вердикт |
| `docs/parity.md` | статус модуля для внешнего обзора |

### Уточнение browser-runtime после единственного D34 live (2026-11-04)

A и B.0–B.3 остаются независимо принятыми. D34 startup/activation focus green;
AI recorded replay matched, Qwen STOP: native terminal FAILED вместо FINISHED
(net::ERR_ABORTED). Новый launch не повторялся; mirror/submit и B.5 не выполнены.
Post-STOP focused141×2/full5619pass+2skip/gates×2 green; external verdict needs_live,
НЕ приёмка B. Продолжение — только после независимого разбора и нового разрешения.
Подробности и evidence: browser-runtime.md, последний «Где остановились» WORKLOG.md,
external browser-b-d34-20261104 dossier. Историческая строка68 не переписывалась.

### Решение пользователя о порядке продолжения (2026-11-04)

Общий перенос плагина НЕ отменён. Qwen live-проблема FAILED/net::ERR_ABORTED
отложена для ручного разбора пользователем после полного переноса; невозможность
исправления не доказана. B.4 needs_live/deferred, B.5 незакрыт, accepted не заявлен.
Продолжать остальные согласованные срезы по их мандатам без текущей диагностики
Qwen. Эта запись не разрешает повтор live/мутации и не меняет условия приёмки.

### Routing-runtime — сдача reference-среза (2026-11-05)

- [routing-runtime.md](routing-runtime.md): A+B завершён в byte-exact reference
  границе, готов к независимому аудиту, **не принят**. Native144+193×2,
  focused376×2, full6248pass/2legacy skip×2, frozen230/API253×2,
  5mutants red→exact restore→green. D38 class3400/3alias, frozen сохранены.
  Actual MODULE selfchecks blocked2, probes unknown_tool1: runtime_snapshot и
  routing остаются skeleton. Досье: routing-runtime-20261105, SHA seal последняя.
  Эта append-запись уточняет статус, не исправляя исходную строку регистрации.

### 2026-11-08 — закрытие отдельного NATIVE-first шага (не перенос)

Доказанный воспроизводимый STOP исправлен в native. Frozen red-2 был
18 pass / 54 fail; SAME frozen suite green-4 и green-5 — каждый 72 pass /
0 fail / exit0. Разрешённые observations и storage/log bytes совпадают
до/после при внешне фиксированных wall-clock/root; native JSONL CRLF
и `_log_query` exception swallowing побайтно неизменны. Настоящие junction
выполнены; обе настоящие symlink-попытки — genuine1314, пробел живого покрытия.

Отдельно ПОСЛЕ green перечитаны source SHA pins, receipt
`corrected-native-source-pins.json` (исторические pins/seals не переписаны):
- librarian.py: 97676 B, SHA256 340b5dd2be96ebc4fd2e920889b275f66d9f70e4e1284bc11676db6a96551ad9; LF=CRLF=1551.
- ml_project_index.py: 65753 B, SHA256 2f7694a91a48e294d40b70ada35feec355c16c7f2889d492900a5ff3839a18cb; LF1120/CRLF866, исходный mixed-EOL вне diff сохранён.
- D48 gd_semantic_parser.py и D49 ml_data.py: исходные bytes/SHA точны.

Независимые неизменённые baselines исполнены дважды, порядок ID/setup/call/
teardown и outcomes совпадают с принятым STOP: full collected/called6833 =
6831 pass / 2 same genuine1314 skips; frozen230/API253/native-project288.
Actual gates: lint604/0; limits604/0 и два прежних warning; contract28/0;
security audit0. Логи/pytest tmp/JUnit/selfcheck reports только в dossier.
Это диагностики repository, а не замена native security red→green.

**Реальный selfcheck:** `context.ask` → blocked / exit2: MODULE отсутствует,
тестов модуля нет, корпуса механики нет. **Реальный probe:** ask →
unknown_tool / exit1. Никакого утверждения полного context.ask parity/live.

Проектные source/binding/checker/D50/tests/corpus, 44 canonical reports,
86 UID, 4 sentinels не изменены; pyc0. Все остальные native sources,
deployed cache/project.godot и исторические STOP/predecessor сохраняются.
Новых transferred files, pytest/corpus, cap-pin red, submitted-byte mutants
нет. Только native две правки и append-only documentation текущего шага.

**Текущий этап:** context.ask MODULE1 — L2a принят независимым аудитором 2026-11-12; stage6/parity skeleton; librarian reference1.
Native воспроизводимый STOP теперь green; librarian byte-exact transfer
ещё НЕ начат и не объявлен принятым. Прежний STOP сохранён как история.

**Следующее действие:** согласовать существующий конфликт native JSONL
CRLF ↔ LF-only port mandate (не менять логгер молча), затем отдельным
шагом выполнить byte-exact transfer из corrected-native pins и заново
доказать binding/D50/F0/корпус/red/green/live; symlink live — при правах ОС.
До этого не переводить librarian/context.ask в ported.

### 2026-11-11 — librarian F1 принят; L2 §0 STOP до реализации

Независимый аудитор принял F1 reference1 в WORKLOG9253–9284; исторический
submission-pending текст выше не является текущим вердиктом. context.ask остаётся
MODULE0/skeleton. Мандат _start-prompt.librarian-L2.md выдан, fresh §0 exact:
5445files/900dirs, native/4pins/corpus/accepted evidence immutable. Actual selfcheck
blocked/exit2, probe unknown_tool/exit1; неизменённый snapshot_diff падает на
catalog.json list (run_corpus312, AttributeError/exit1), не сравнивает213cases.
§4 corpus_folders/alias недостаточен; нужны narrow runner/replay/tests санкция
и уточнение profile-local logger vs отдельный production no-op. Реализация,
module tests/mutations/regressions L2 не начаты; новые D/приёмка не утверждены.
Следующее действие: поправка L2§4/§6 и _log_query у пользователя. Подробности:
porting/librarian.md, PROGRESS, последний WORKLOG; dossier librarian-L2-20261111.

### 2026-11-11 — L2a public ask submission (NOT independent acceptance)

Registered ask MODULE1/read/STRING; actual selfcheck context.ask ok/exit0 twice,
module104 including mandatory real Agent.call/native string/profile CRLF logging,
profile-only legacy history/API-cache, separate immutable reference/native213 twice.
Final six NEW-code mutation kills/exact restores; fresh D57
full7210=7208pass+2 genuine1314skip twice with all accepted7096 IDs/all phases exact;
focused352/frozen230/API253/native-project288 twice, four gates/security twice0.
D52/D53/D54/D55/D56/D57 authorizations and original rejected failures retained.
Only cache migration disabled transiently/restored; native fallback preserved.
Frozen4/corpus141+guard72/goldens/bindings unchanged. Headless probe MAP/FRAGMENTS0,
typed errors1, project exact. Stage6/parity skeleton, independent audit pending.
Dossier: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/librarian-L2a-20261111/.
Seal LAST; subsequent sibling librarian-L2a-20261111-postseal result/ZIP must be
read as integrity verification, NOT auditor acceptance. Next independent review.


### J1 — answer_judge, этап 0 / STOP §0 (2026-11-13)

- [_start-prompt.answer-judge.md](_start-prompt.answer-judge.md): мандат публичного
  assistant.judge/judge; [лист](answer-judge.md) создан, A1/A2/A3/B пока не начаты.
- 12 pins exact; реальная разведка выявила три missing reference dependencies,
  dotted minilich import failure, limits-red6 и forward A2→A3 imports.
- Actual assistant.judge selfcheck fail/exit1 (нет папки), probe unknown_tool/exit1;
  context.ask selfcheck ok/exit0, 104 unit/213 reference; не приёмка judge.
- Следующее: получить пользовательскую поправку closure/child/limits/старых пинов/G,
  затем A1. Native/code/tests/bindings/checkers/corpus не менялись.
