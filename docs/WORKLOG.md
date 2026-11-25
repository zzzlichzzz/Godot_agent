# Журнал работы

Файл нужен для одной вещи: если чат потерян, работа продолжается с этого места.

## Как продолжить в новом чате

1. Прочитать `../RULES.md` (15 правил, короткие).
2. Прочитать `architecture.md` (слои и путь вызова).
3. Прочитать здесь раздел **«Где остановились»** и последнюю сессию.
4. Прочитать `NOTES.md`, раздел «Открытые вопросы» — там то, что ещё не решено.
5. Не менять прошлые записи журнала: новая сессия = новый раздел снизу.

## Правила ведения журнала

- Один раздел на сессию: дата, цель, что сделано, что сломалось, чем закончилось.
- В разделе «Сделано» — только проверяемые факты (файлы, числа, команды).
- Инциденты записываются честно, вместе со способом устранения: это самая
  полезная часть журнала.
- «Где остановились» переписывается в конце каждой сессии; остальное — только
  дописывается.

---

> Исторические сессии 1–80+ (`2026-10-27`–`2026-11-22`) доступны в git-истории (до `7a279f1`) и убраны при мягкой чистке `docs/` `2026-11-25`.

## T-F.6 resume-authorization (2026-11-23T14:10:47.033255+00:00)

Пользователь/аудитор снял STOP и разрешил offline rebuild exe (PyInstaller6.21.0). D107/D108 записаны до production. Static fallback: aistudio=Gemini API, qwen=DashScope; API253 source/goldens сохраняются. Следующее: corpus/new RED до кода, build и проверки ×2. Installed/native/git/предыдущие sealed-досье не разрешены к изменению.
2026-11-23 - Auditor: plugin.cfg pereklyuchen na native agent_entry.gd (red: 0 script errors in editor probe), fixtures/.gdignore v obe kopii, commit ea669a1. Polzovatel otkroet proekt - panel zapustit server cherez exe, polnyy native UI budet vidna.

## 2026-11-23 — исправление HTTP 403 по логу пользователя (ADR-0090)

Причина подтверждена: saved allow_addons=true из external policy попадает в общую
обёртку POST; ProjectAuth отказывает ещё до list/providers/status. На шести точных
metadata routes оба UI-поля удаляются после auth/project/JSON checks; никакого
расширения прав Agent/PathPolicy, native/GDScript/ToolSpec edits нет.
Genuine RED30fail/9pass → same-ID GREEN39pass. Связанный прогон302pass/1fail
выявил unsafe preexisting-endpoint cleanup. Ещё RED4fail; listener restored
exclusive create/refusal/owned cleanup. Связанные suites307passed.

Четыре гейта exit0 (security/layers/limits/contract; два прежних limits warnings),
genuine selfcheck assistant.write verdict=ok/unit43pass/corpus4, read-only probe ok.
REPORTS external, запечатанные repo reports сохранены. Offline PyInstaller6.21.0
rebuild завершён; python/dist/godot_agent_server.exe SHA256
a5e8a4206b0d3b644fa6346c131c1ea399cafb1f15d1d8a69326c4f959deadf0.
Old exe preserved in external http403-exe-backup-20261123; no install sync/git action.

Socket source/exe/isolated-zeroarg-exe GREEN: шесть POST200 и progress200,
auth/Host/Origin403/project409, sensitive-policy403/no_key denied. Contender exit2
с exact чужим endpoint, owned shutdown exit0/endpoint removed, project/token/policy
exact. Zeroarg port5000/external APPDATA; production user state/server/UI не запускали.
Первый helper ошибся путём shutdown; fail/logs retained, production не меняли,
исправлен только helper на /server/shutdown, затем три цикла GREEN.

Отдельно с разрешения пользователя stale endpoint PID18332 переименован в том же
userdata в http_endpoint.stale-18332-20261123.json после проверки отсутствия
процесса/listener. Bytes preserved, token/settings untouched; auto-cleanup запрещён.

### Где остановились — HTTP correction

Код и exe исправлены; python/modules: 2569passed (40.38s); tests/py ещё выполняется,
его GREEN не заявлен. Final gates4/git diff--check ok. Read-only launcher check:
cached exe отсутствует, manual/onedir/старшие priority candidates отсутствуют;
fallback — пересобранный python/dist exe с повторно exact SHA, user cache не менялся.
Следующее действие: записать actual pytest verdict tests/py; затем пользователь
перезапускает Godot/сервер. Общая независимая приёмка T-F.6 не заявляется и не меняется.

## 2026-11-23 — продолжение: key save403 и chat list500 (ADR-0091)

Предыдущее исправление охватило неполную envelope: без addon_dir и settings.
По новому пользовательскому логу получены RED r2:32failed/14passed (settings403,
SessionContextError500, linked-key input/temp200). Первый RED содержал missing client
fixture errors2; исправлен только импорт fixture, отказ/вывод не скрыт.
Полная точная таблица14 POST удаляет пять UI project-policy fields после auth/Host/
Origin/JSON/лимита/project/userdata checks. Перед native IO ExternalPanelState
проверяет api_config/key/model/catalog/temp против symlink/reparse/hardlink.
Native/GDScript/ToolSpec/Agent/PathPolicy bytes/правила не менялись.

Same IDs GREEN46. Offline API-chat lifecycle выявил неосвобождённую navigation:
new200→rename409. Дополнительный RED3fail/1pass; существующий clear_request_activity
подключён в runtime finally. Чужой thread exchange не освобождается. Own50passed,
связанные353passed до cleanup → final357passed (300.28s) после него.
Четыре genuine gates exit0 (два прежних limits warnings), final selfcheck
assistant.write verdict=ok/unit43/corpus4/differences0; REPORTS external, sealed repo
reports untouched. Read-only probe ok на отдельном synthetic project.godot.

Offline PyInstaller6.21.0/Python3.14.6 build в external staged dist; после final
cleanup выполнен новый build r2. Genuine build изменяет только distpath, inputs
и build script неизменны. Actual source/explicit-exe/isolated-zeroarg-exe sockets3
GREEN с полной panel envelope: synthetic key save/add200, masked responses/external
persistence; existing chat list200; new/list/rename/open/model/delete200;
browser/status idle. No-key refresh/scan до key save denied; configured api/test/
refresh не вызывали, реальных provider/browser requests0. Negative auth/Host/Origin403,
foreign-project409/sensitive-policy403; contender exit2/foreign endpoint exact,
owned shutdown exit0/cleanup/project-token-policy unchanged. Zeroarg synthetic
deployment/external APPDATA/port5000, не production Godot UI. Helper/logs external.

С разрешения пользователя stale endpoint PID26668/session9a273edb903f4a2084c9dbd173d18810
после fresh identity/process/listener checks переименован в той же userdata в
http_endpoint.stale-26668-20261123.json: bytes preserved, token/policy exact.
Автоматического удаления чужих endpoints нет. Предыдущий exe сохранён в external
control-envelope-exe-backup-20261123; verified staged exe установлен в
python/dist/godot_agent_server.exe, SHA256
26de3c038b13f5b44f401df67b3c7110a0f520ee1cfd74b3089f2f87b0165334.
User server не запускали; реальные ключи/переписка не изменялись.

### Где остановились — HTTP control correction

Оба пользовательских дефекта исправлены и сборка установлена; следующий шаг —
пользователь перезапускает Godot и проверяет key save/chat list в реальной панели.
Отложенный предыдущий tests/py завершился5952passed/6failed/2skipped (1029.48s),
не GREEN: три integration paths-preview native corpus cases (004/005/009),
два editor-branch-live port.json, transfer_t1 write TTL denied!=not_found.
Это не исправлялось/не исключалось ради GREEN данного HTTP-запроса.
python/modules прежнего среза2569passed; повторный whole-inventory после ADR-0091
не запускался. Общая приёмка/этап T-F.6 и parity не меняются; UI/provider live
не подменяются synthetic socket evidence.
Final docs-only повтор: security/layers/limits/contract exit0, git diff--check ok;
SHA256 установленного exe повторно совпадает с проверенной socket-сборкой.

## T-F.6 + §1.5 + D110–D113 (2026-11-25)

Работа по прямому указанию пользователя выполнена непосредственно в `D:\vajno\Godot\тест-плагина-ии\addons\godot_agent` поверх коммита `7a279f1` (ADR-0090/ADR-0091), `agent-rebuild` и `agent-backups` не изменялись.

1. **RED-до-кода**: записаны `tests/py/panel_tf/test_tf6_d110_models_public.py`, `tests/py/panel_tf/test_chrome_autodetect.py`, `tests/py/security/test_chrome_autodetect_security.py`, `tests/py/live/test_panel_locale_live.py` — исходный прогон дал честные **12 failed** (включая живой Godot 4.6.3 `loc_nonnull: False`).
2. **D110 (`providers_fallback.py`)**: в `scope(registry)` записи копируются без мутации нативного `PROVIDERS`, для `openrouter` и `opencode_zen` выставлены `models_public=False` и честные RU/EN-пометки о требовании ключа; на выходе ссылки и кэш точно восстанавливаются.
3. **D111 / §1.5 (`BUG-008`)**: добавлен `python/runtime/chrome_paths.py`, подключённый на старте сервера в `exe_bootstrap.py` и `app.py` (при сохранении лимита 80 строк `app.py`). Порядок поиска: стандартные пути Chrome → `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe` → стандартные пути Edge (`msedge.exe`); валидный существующий `GODOT_AGENT_CHROME_PATH` не перезаписывается, пути с `User Data` отклоняются (`SEC-20`). При отсутствии бинарника `InteractiveGateway` отказывает fail-closed сообщением «Chrome не найден, укажите путь в настройках».
4. **D112 / D113 (`BUG-004`/`010`/`011`)**: исправлен системный пропуск `return` в `editor/native/agent_panel.gd` для `_locale()` (строка 400) и `_T()` (строка 418). Входные факты `D113` (`tests/py/panel_tf/source_inputs.py`, `tests/conftest.py`, `tests/py/panel_tf/test_panel_source_input.py`) проверяют обратимость к прообразу `82171` B (`a751d654...`) и точный размер/SHA256 `82185` B (`c160c677...`), не изменяя принятые бизнес-эталоны `scene_deps_facts` и старые манифесты; `tests/py/live/test_panel_locale_live.py` в реальном Godot 4.6.3 подтвердил `_locale()`, `_T()`, форматирование строк, `AgentStatusBar.tscn` UID `cyv7bxjosjeps` и рендер кнопок `/sites/list`.
5. **Офлайн-сборка exe (PyInstaller 6.21.0, сеть заблокирована)**: пересобран `python/dist/godot_agent_server.exe` (`30873899` B, SHA256 `ee02608fa33eb24778c733c6568ad6e81cde9368f79b093d6013af66522dd917`; прежний `26de3c03...` сохранён в `%TEMP%\opencode\c8_audit\tf6-20261125\exe-backup\`); проверены 5 модулей в PYZ и живой сокет-цикл (`/health`, 10 провайдеров, 6 сайтов, fail-closed `no_key`, `/server/shutdown` exit 0).
6. **Верификация**: 7/7 мутантов убиты с точным восстановлением байтов/SHA/EOL; 4 гейта ×2 (`security_audit`, `lint_arch`, `check_limits`, `gen_contract --check`) все exit 0; 8 модульных `selfcheck` ×2 все `verdict=ok` (с принятым K1c offline hook и D103); `probe.py read` ok; `tests/py/live/test_panel_locale_live.py` + `test_bridge_live.py` 3/3 passed; полный парный регресс ×2 (`tests/py` + `python/modules`, `--ignore=tests/py/live`, с D103 + D113): `8589` collected → **8587 passed + 2 skipped (WinError1314) + 0 failed** в обоих раундах. Запечатывание `SHA256-final.json` LAST и соседний проверенный ZIP выполнены во внешнем досье `%TEMP%\opencode\c8_audit\tf6-20261125\`.

### Где остановились — T-F.6 завершён

Код, exe, тесты, досье и документация (`TF6-providers.md`, `bugs-register.md`, `deviations.md`, `invariants.md`, `PROGRESS.md`, `WORKLOG.md`) синхронизированы; `git` изменения оставлены незакоммиченными для просмотра/коммита пользователем. Открытыми за пределами этого прогона остаются `BUG-009` (`/chat/live_input` 403), `BUG-001..003`, `test_editor_branch_live.py` (ждёт `plugin.gd` вместо `agent_entry.gd`) и живая ручная проверка панели с реальными ключами.

## Дополнение: ADR-0092 / D114 (архивация мёртвого http_endpoint.json) и D115 (--collect-submodules selenium) (2026-11-25)

1. **Сервер не запускался (`FileExistsError`)**: в `%APPDATA%\Godot\app_userdata\тест плагина ИИ` оставался `http_endpoint.json` от завершившегося `PID 29240`; по разрешению пользователя архивирован в `http_endpoint.stale-29240-20261125.json`. Записан `ADR-0092` / `D114` (`docs/adr/0092-http-stale-dead-pid-endpoint-archive.md`, `docs/security/invariants.md`), реализован в `python/channels/http/listener.py` (`_pid_alive` + `_archive_stale_endpoint`: переносит только plain single-link 4-польный loopback-файл заведомо мёртвого PID с сохранением сырых байтов; живые/`ERROR_ACCESS_DENIED`/неполные/линкованные/битые по-прежнему падают `FileExistsError`). Тесты `tests/py/channels_t1/test_stale_endpoint_archive.py` (`RED 2→GREEN 10/10`), 2 мутанта убиты с точным SHA/EOL-восстановлением; `test_endpoint_owner.py` и `test_http_metadata_policy.py` сохранены и зелёные.
2. **Браузер при `/chats/new` падал с `No module named 'selenium.webdriver.chrome.options'`** (`D115`): `selenium 4.46.0` загружает `options`/`webdriver`/`driver_finder`/`selenium_manager` лениво; в `tools/build_http_exe.py` добавлен `--collect-submodules selenium` (`tests/py/panel_tf/test_exe_selenium_closure.py`: `RED 2→GREEN 2`, 1 мутант убит). Пересобран `python/dist/godot_agent_server.exe` (`45864239` B, SHA256 `730fa3245566b527cf1a248355548b1904bab71aa7d25bf2f8bd7e5edf56e61d`, `125` модулей `selenium` и `123` транзитивные зависимости подтверждены в PYZ).
3. **Итоговые проверки после всех правок**: реальный zero-arg запуск exe на `тест-плагина-ии` (`port=5000`, автоархивация `PID 25112`, `/health 200`, `/server/shutdown` exit `0`), изолированный zero-arg со stale `http_endpoint.json`, живой Chrome + Selenium CDP attach (`url=about:blank`, `navigator.webdriver=False`), 4 гейта ×2 `rc=0`, 8 `selfcheck` ×2 `verdict=ok`, `probe.py read` ok, `tests/py/live/test_panel_locale_live.py` + `test_bridge_live.py` `3 passed`, полный регресс ×2 (`tests/py` + `python/modules`, `--ignore=tests/py/live`, D103+D113): **`8601` collected → `8599 passed + 2 skipped (WinError1314) + 0 failed`** в обоих раундах.

## Дополнение: ADR-0093 / D116 — /chat prompt, live_input PARSER, fail-closed UI-политика и UID 7 сцен (2026-11-25)

1. **Причина `403` на `/chat/live_input` и `/chat`**: у пользователя `user://godot_agent_policy.txt` содержал `"1"`, панель (`agent_panel_part1.gd`) отправляла `"allow_addons": true` во всех POST-запросах, а `auth.py` сбрасывал политику только на 14 `_CONTROL_POSTS`. Кроме того, `routes_chat.py:15` читал только `message`/`text`, игнорируя `'prompt'` панели (`400`), `/chat/progress` не отдавал `active`, а `panel_services.live_input` не читал `_selection()` до первого `/chat` и передавал модуль парсера вместо экземпляра `PARSER` (из-за чего живой ввод на DeepSeek падал в `AttributeError` → `Mirror unavailable`). В 7 сценах `editor/native/*.tscn` (`UserMessageCard.tscn` и др.) стояли устаревшие `uid://` скриптов.
2. **Изменения (`ADR-0093`, `SEC-HTTP-CHAT-POLICY`, `D116`)**:
   - `python/channels/http/auth.py`: строгий список `_CONTROL_POSTS` (14 маршрутов ADR-0091) сохранён без ослабления — `test_panel_tf_security.py` и `test_http_chat_policy.py` подтверждают `403` при попытке HTTP-повышения на `/chat`, `/chat/live_input`, `/chat/stop`, `/server/shutdown`, `/minilich/*`, `/init`, `/tools/call`, `/project/*`.
   - `python/channels/http/routes_chat.py` и `python/runtime/panel_services.py`: поддержка `message`/`prompt`/`text`, `active=session.busy`, выбор `_record` или `_selection()`, отказ от `'qwen'` при `kind == 'api'`, развёртывание `getattr(module, 'PARSER', module)`.
   - `editor/native/agent_panel_part1.gd`, `agent_panel_part4.gd`, `agent_locale.gd`: принудительный fail-closed старт `_allow_addons = false`, `_allow_self_edit = false`, блокировка чекбоксов с RU/EN-подсказкой; обратимая проверка байтов `D116_REVISIONS` в `tests/py/panel_tf/source_inputs.py` и `tests/conftest.py` (334/334 `test_scene_deps_facts.py` без правки эталонов).
   - Выравнены script UID во всех 7 `editor/native/*.tscn` (`tests/py/live/test_scene_uids_and_policy_live.py` и `godot --editor --headless --quit` — `0` предупреждений).
3. **Проверка и сборка**: после восстановления строгого `auth.py` пересобран `python/dist/godot_agent_server.exe`, пройдены мутанты, живой Chrome DeepSeek `/chats/new` + `/chat/live_input` (`allow_addons=False` → `applied=True`), zero-arg `port=5000`, а также запускается полный финальный цикл проверок (`gates ×2`, `selfcheck ×2`, `live`, `regression ×2`).


## Дополнение: BUG-014 и мягкая чистка docs/ (2026-11-25)

1. После проверки сборки (`ADR-0093 / D116`: `8633 passed`, `2 skipped`, `0 failed`, `4` гейта и `8` `selfcheck` зелёные) при первом коротком запросе в чате зафиксирован `BUG-014`: `GET /chat/progress -> 200`, `POST /chat -> 400`, `POST /chat/live_input -> 200` с сообщением в панели «исчерпан лимит шагов диалога». Код по указанию пользователя не патчился; симптом и вероятные причины в `turn.py`/`routes_chat.py`/`answer_judge.py`/`interactive_gateway.py`/`deepseek_parser.py` внесены в `docs/bugs-register.md`.
2. По решению пользователя выполнена мягкая чистка документации без изменения правил `AGENTS.md`/`RULES.md`:
   - `docs/bugs-register.md` очищен от закрытых записей (оставлены актуальные `BUG-001..003`, `BUG-007`, `BUG-014` и `## ОГРАНИЧЕНИЯ`);
   - удалены 65 устаревших промптов и handoff (`docs/porting/_start-prompt*.md`, `_audit-handoff.md`);
   - почищены `docs/README.md` и `docs/porting/README.md`;
   - сжаты `docs/PROGRESS.md` (до таблицы 44 механик и долгов) и `docs/WORKLOG.md` (оставлена ветка `T-F.6` / `ADR-0090..0093`).

### Где остановились — BUG-014 зафиксирован, документация очищена

Код и `python/dist/godot_agent_server.exe` не изменялись со времени проверки `ADR-0093 / D116`. Открыт `BUG-014` (`POST /chat -> 400`, «исчерпан лимит шагов диалога»); ждём команды на диагностику/исправление `BUG-014` или дальнейшую чистку `docs/`.
