# Журнал работы

Файл нужен для одной вещи: если чат потерян, работа продолжается с этого места.

## Как продолжить в новом чате

1. Начать с `../AGENTS.md`: карта запуска и документы по задаче (ADR-0094).
2. Открыть нужную строку `PROGRESS.md`, лист механики и последнюю связанную с ней
   запись **«Где остановились»**.
3. Не менять прошлые записи журнала: новая сессия = новый раздел снизу.

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

## Исправления из реестра багов (2026-11-26)

- `BUG-001..003`: изолированный Godot 4.6.3 (`test_ui_bugs_live.py`, 1 passed) проверил три одновременно открытых диалога, пересборку экрана, отсоединение живого узла, повторное добавление, освобождение источника и один док на цикл активации. RED `DETACHED_NODE_STILL_WATCHED` исправлен отключением подписок при выходе узла из дерева. Пины трёх изменённых GDScript-файлов согласованы с оригинальными входами без пересчёта фактов.
- `BUG-007`: три воспроизведённых падения C.21 вызваны семью уже закреплёнными UID ревизии D103. Проверяется точный совокупный инвентарь без перезаписи манифестов и эталонных ответов; в Godot `.gdignore` защитил весь проверяемый корпус от импорта, вне него генерация UID подтверждена. Причина исторического расхождения D105 неизвестна.
- `BUG-014`: 10 тестов HTTP-композиции с подменой транспорта прошли, в том числе первый короткий ответ без DONE, ошибка доставки без повторов, выбор чата и контекст запроса, несовпадающее или оборванное действие без preview. До явного подтверждения записи нет. Авторизация не ослаблена.
- Проверки: корпус/пины/факты сцен — 395 passed; HTTP-канал, управление чатами и политика — 120 passed; `selfcheck assistant.write` и `editing.paths_preview` — `ok`, 43/58 unit, 4/25 corpus, 0 расхождений; read probe — `ok:true`. `security_audit`, `lint_arch`, `check_limits`, `gen_contract --check` и CR-aware `git diff --check` прошли, два прежних предупреждения о лимитах остаются.
- Сборка PyInstaller офлайн. Три реальные socket-проверки (source, EXE, zero-arg EXE в отдельном проекте) прошли: ключи синтетические, сценарии настройки и чатов без сети провайдера, HTTP-границы и owned cleanup проверены. Прежний exe сохранён во внешнем `bugreg-exe-backup`; `python/dist/godot_agent_server.exe` установлен из проверенной сборки, SHA256 `677a1c19977cde0afa1284b7117a2b774430ba43de7e6c0a77d0a4dcbef1011d`. Лаунчер выбирает этот путь. Пользовательский сервер не запускали, `user://` не меняли.

### Где остановились — исправления в реестре

Исправления проверены на изолированном Godot и HTTP-сценариях; этапы паритета не менялись. Реальный DeepSeek не использовали: пользовательская проверка — перезапустить Godot и отправить короткий запрос.

- Широкий регресс без `tests/py/live`: 8391 passed, 180 failed, 72 setup errors, 2 skipped (295,97 с). Трасса обнаружила первые оставшиеся native-алиасы после теста каталогов `test_nested_create_and_rollback_restore_files_and_owned_directories`. Узкий порядок «каталоги → B3» дал 5 passed / 3 failed. Для модульных тестов подключена штатная изоляция T1, уже используемая в группе интеграционных тестов записи.
- Отдельный прогон групп дал 597 passed / 1 failed (TTL). Диагностика показала, что чтение UTF-8-журнала в системной кодировке Windows меняло снимок политики: получалось `denied` вместо `not_found`. Тест теперь читает UTF-8 явно; проверки политики и срока не менялись.
- Повтор «каталоги → B3 + TTL» дал 9 passed (1,24 с). Повторные `selfcheck assistant.write` и `editing.paths_preview` — `ok`. Тот же широкий прогон `python/modules tests/py --ignore=tests/py/live` с новым basetemp `bugreg-python-r2` — 8643 passed, 2 skipped, без падений и ошибок настройки (379,15 с). Это результат текущей ревизии, отдельно от исторического D116 и от ручной проверки реального провайдера.

## 2026-11-26 — D117: `.txt` и неотправленный черновик DeepSeek

- По живому журналу после `/chat` 400 пришёл `live_input` 200; этот статус не является подтверждением отправки. Изолированная форма воспроизвела превращение длинной вставки в `.txt` и повторные вставки до отправки короткого текста (6 RED).
- Точечный адаптер проверяет свой браузер, вкладку и поле, заполняет точный текст без Ctrl+V и посылает не более одного Enter. Служебный промпт предшествует сообщению пользователя; неясная доставка завершает ход. Дополнительно зеркало переключено на текущий чат и неблокирующую проверку занятости; чужая вкладка и существующие вложения не изменяются. Frozen-парсеры, маскировка, авторизация и подтверждение записи не менялись.
- Целевой повтор `deepseek-delivery-r4` — 136 passed (36,90 с). Изолированная форма в Chrome: два точных заполнения, по одному Enter, без paste; существующий файл обнаружен. `selfcheck assistant.write` — `ok`, 43 unit/4 corpus. Read probe — `ok:true`; четыре gates и CR-aware diff check прошли, два прежних предупреждения лимитов остаются.
- PyInstaller собрал первый офлайн EXE; три отдельные socket-сессии source/EXE/zero-arg EXE прошли с синтетической конфигурацией, проверками авторизации и очисткой своего endpoint. Первая сборка имеет SHA256 `7f623deae51bd32b1479fba80655f05c5bdfefe5d42c73a861c480578ac2db88`. Запросов к реальному DeepSeek не было.
- Первый широкий non-live прогон: 8651 passed, 1 failed, 2 skipped (427,58 с). Восстановлен порядок отказов живого ввода API-чата: без активного браузера `no_browser`, с ним `no_parser`, ни в одном случае сайт не открывается. Целевой повтор с политикой HTTP — 165 passed (40,56 с), `selfcheck assistant.write` — `ok`. EXE пересобран после правки.

### Где остановились — D117

- Повторные socket-проверки source/EXE/zero-arg EXE прошли, включая `live_input` → `no_browser` в API-чате. SHA256 установленного `python/dist/godot_agent_server.exe` совпал с проверенной сборкой: `12cd6d1840293485f5a32268a58b56c75dc057d73ae5eb6f34da9d12a561e8f9`. Предыдущий EXE сохранён во внешнем `deepseek-d117-exe-backup`, SHA256 `677a1c19977cde0afa1284b7117a2b774430ba43de7e6c0a77d0a4dcbef1011d`.
- Непосредственно перед установкой не было процесса сервера, PID 20296 и слушателя 5000. С подтверждения пользователя перенесена только эта запись endpoint в `http_endpoint.stale-20296-20261126.json`, исходные байты сохранены. Ключи, токен, настройки, история и браузерный черновик не менялись; пользовательский сервер не запускался.

Повтор широкого non-live прогона D117: 8652 passed, 2 skipped (421,50 с). Последующая проверка пользователя выявила отдельный отказ D118.

## D118 — не найдено поле DeepSeek и не работает живой ввод (2026-11-26)

- Публичный фронтенд подтвердил `textarea[name="search"]`; `textarea[name="user query"]` — редактор прежнего сообщения. До правки три сценария упали: отправка и зеркало на новом поле, восстановление зеркала после отказа без записи.
- Отправка и зеркало используют один строгий выбор поля и сверку вкладки. Подтверждённые карточки вложений, скрытое/readonly поле и неоднозначный выбор приводят к отказу. Отказ до записи больше не удерживает зеркало; при неясной доставке удержание сохранено. Пины нативного браузерного кода, маскировка и политика HTTP не изменены.
- 166 целевых тестов (41,75 с), `selfcheck assistant.write` (43 unit/4 corpus), `probe read`, четыре gates и отдельная форма в Chrome — `ok`. В Chrome проверены оба селектора, кириллица и длинный черновик без paste/submit, защита посторонних полей и вложения. Реальный сайт со входом в аккаунт не тестировался. Новый широкий прогон не выполнялся.
- EXE собран офлайн во внешний `deepseek-d118-exe-stage`, SHA256 `daf547ce7dc9f948892529811de018135a21cb43e92a0f395179e1f96b56d536`. Source и явный EXE прошли изолированные socket-проверки на свободных портах; zero-arg на 5000 не запускался, чтобы не мешать действующему серверу.

### Где остановились — D118

Повторные CIM, проверка порта 5000 и код завершения PID 1320 подтвердили, что старый сервер не работает. С разрешения пользователя оставшийся endpoint сохранён в `http_endpoint.stale-1320-20261126.json` с исходными байтами; прежний EXE сохранён во внешнем `deepseek-d118-exe-backup`. Проверенный EXE установлен в `python/dist/godot_agent_server.exe`; независимый SHA256 совпал со staging. Настройки запуска, ключи, токен, история и браузерный черновик не менялись. Пользователь затем подтвердил отправку и получение ответа; отдельного подтверждения зеркала нет. По его наблюдению, ответ в панели пришёл примерно на две секунды позже, чем в браузере.

## D119 — навигация для моделей и ожидание DeepSeek (2026-11-26)

- Оба цикла используют общий промпт с картой проекта и общую маршрутизацию чтения. Для внешних клиентов добавлены `tree`, диапазоны `read`, фильтры и страницы `search`, поиск однозначного объявления и типизированные файловые предпросмотры. MCP объясняет начальный маршрут в `initialize`. [Статус каждого пункта](ai-usage-status.md); исходный отчёт не переписывался.
- В тесте реальной петли ожидания с часами-симулятором финал стабильного текста DeepSeek занимает 1,0 с вместо 4,4 с. Действия, незавершённые, меняющиеся и сомнительные ответы не выпускаются по быстрому пути. Пины и защита от повторной отправки сохраняются. Это замер финализации, а не времени генерации или живой задержки панели.
- CLI показал 35 инструментов. Изолированные `probe.py` и MCP stdio подтвердили навигацию, схему типизированного предпросмотра и отсутствие записи в проект. Старая проверка `assistant.chat` и инвентаризация `context` падали и на чистом `85c0dab`; после явного offline replay и учёта объявленных добавлений корпуса совпали 10/10 и 3/3 без перезаписи эталонов.
- Семь `selfcheck` — `ok`: `project_text.tree` 23/22, `project_text.read` 38/35, `project_text.search` 29/16, `code_intel.usages` 66/31, `context.gather` 33/3, `assistant.chat` 29/10, `assistant.write` 43/4 (unit/corpus). Четыре статических гейта прошли; 36 артефактов без дрейфа, два прежних предупреждения о размере. Отчёты вне проекта: `%LOCALAPPDATA%\Temp\opencode\d119-selfcheck-r2-le4suupi`.
- Первый широкий прогон без `tests/py/live`: 8655 passed, 25 failed, 2 skipped. Новый тест ожидания подключал native-алиасы при сборе тестов и оставлял глобальное состояние. Подключение ограничено вызовом теста; целевой повтор browser, editor, LLM и chat-тестов прошёл. Широкий повтор: 8680 passed, 2 skipped (401,24 с); пропуски — Windows не разрешила создавать символические ссылки (`WinError 1314`).
- ADR-0094 сократил обязательное стартовое чтение и показал активный runtime. Профиль редактора и `plugin.cfg` не переключались.
- Изолированная сборка: `%LOCALAPPDATA%\Temp\opencode\d119-package-2fgqcod6\source\python\dist\godot_agent_server.exe`, 45 903 126 байт, SHA256 `1739d6f73ce8590c7e2fc6a9885a2443434ef3253bef7de4dbbd19ba8645b475`. Исходники и явный запуск EXE на порту `0` прошли HTTP-проверки: 35 инструментов, фильтр дерева, диапазон чтения, `PREPARED` без изменения проекта и чистое завершение. Провайдер и занятый порт панели не использовались.

### Где остановились — D119

Сборка D119 проверена отдельно; серверные изменения установлены позже в составе D120. Живое время от отправки до показа ответа ещё не замерено. Модульный мост проверять отдельным срезом на живом Godot.

## D120 — повторный запуск HTTP-сервера на Windows (2026-11-26)

- При разборе отчёта сервер не слушал `5000`. Endpoint принадлежал завершившемуся PID 23008; Windows ещё открывала его дескриптор. Старое право доступа давало `WAIT_FAILED` с ошибкой 5, новое право `SYNCHRONIZE` — `WAIT_OBJECT_0`. Это доказывает отказ повторного запуска, но не причину завершения предыдущего сервера.
- [ADR-0095](adr/0095-win32-process-exit-proof.md): решение по статусу ожидания, без вывода из кода выхода. На реальном завершившемся дочернем процессе с удерживаемым дескриптором оба теста (`exit=0`, `exit=259`) сначала упали на эксклюзивном создании endpoint, затем прошли. Неоднозначный статус, живой процесс и ошибки доступа по-прежнему блокируют архивацию.
- `tests/py/{channels_t1,panel_tf,security}` — 890 passed, 2 skipped (Windows запретила symlink, `WinError 1314`). Четыре гейта и `selfcheck assistant.write` (43 unit / 4 corpus) прошли.
- D120 собран отдельно с изменениями D119: `%LOCALAPPDATA%\Temp\opencode\d120-package-9__8wim4\source\python\dist\godot_agent_server.exe`, 45 902 928 байт, SHA256 `982c5159f4babbd6edb4fd08f242d9d25b80ff8c9e0e11a813b251da63c454b0`. На двух изолированных копиях проекта с отдельным `APPDATA` и запуском без аргументов D118 вернул `2`, не меняя endpoint; D120 заархивировал его байт-в-байт, ответил `/health` и на авторизованные discovery и range `read`, завершился с `0` и удалил только свой endpoint. Файлы проекта не изменились; провайдер не вызывался.
- После согласия пользователя `python/dist/godot_agent_server.exe` атомарно заменён на проверенный D120. SHA256 установки совпал со сборкой. Копия D118: `%LOCALAPPDATA%\Temp\opencode\d120-d118-backup-j7j_ntn1\godot_agent_server.exe`, SHA256 `daf547ce7dc9f948892529811de018135a21cb43e92a0f395179e1f96b56d536`.
- Установленный EXE запущен без аргументов на рабочем профиле. Сервер сам заархивировал точные байты старого endpoint в `http_endpoint.stale-23008-20261126T183956Z.json`. На `127.0.0.1:5000` получены `/health` 200 и `/tools/list` 200 (35 инструментов), без токена `/tools/list` вернул 403. У запроса на остановку без `Content-Type: application/json` ожидаемый 400; корректный `/server/shutdown` вернул 200, оба процесса завершились с `0`, порт освобождён. Логи: `%LOCALAPPDATA%\Temp\opencode\d120-installed-check-tkf8fs9e`. Токен, настройки, ключи и историю не редактировали; провайдер не вызывался.

### Где остановились — D120

После установки D120 пользователь отправил сообщение из панели и получил два ответа; исправление описано в D121. Причина остановки исходного процесса не установлена.

## D121 — первый запрос и сценарий пользователя (2026-11-26)

- Пользователь на D120 получил два ответа: на служебную инструкцию и на «привет». `InteractiveGateway` отправлял инструкцию и запрос по очереди. [ADR-0096](adr/0096-browser-prompt-in-first-user-turn.md) объединяет их в одном браузерном сообщении. После ответа в сессии сохраняется пара URL/хеш для этого чата; при изменении инструкции она идёт со следующим запросом. API-поле системы, pinned-парсеры, проверки вкладки и доставки не менялись.
- Из редакторского снимка не передаётся исходник `.tscn`. Путь активной сцены остаётся; `list_scene` и диапазон `read_file` доступны по запросу. Размер подсказки и выдачи инструмента — не предел чтения с диска.
- RED: 4 failed / 6 passed на старой двойной отправке. GREEN: 32 целевых теста HTTP/DeepSeek, BUG-014, снимка редактора и ожидания ответа. `test_new_deepseek_chat_user_journey`: новый чат → отражение черновика без отправки → одно приветствие → структура большой сцены через явный вызов → отказ от предпросмотра → новый предпросмотр и подтверждение → откат. Без дампа сцены и вложений, проект после отката побайтово исходный. Chrome и провайдер имитированы, живая панель не проверялась на D121.
- Четыре гейта: 700 Python-файлов, 36 контрактов, два прежних предупреждения лимитов. `selfcheck` с внешними отчётами прошёл: `assistant.chat` — 29 unit / 10 corpus, `assistant.write` — 43 unit / 4 corpus. HTTP-проба исходников на порту `0`: discovery, дерево, диапазон чтения и `PREPARED` без записи; штатная остановка.
- Отдельный D121 EXE собран во внешней копии: 45 903 567 байт, SHA256 `8322c027913c3e0c4d2ceccaf58a338eee1ea0162bd240695842e0512163ef45`. Проба EXE с явными аргументами запуска на порту `0` прошла: 35 инструментов, фильтр дерева, чтение диапазона, предпросмотр `PREPARED` без записи и штатная остановка. Провайдер не вызывался.
- Регресс `channels_t1`, `panel_tf`, `transfer_t1`, `browser`, `security`: 1193 passed, 2 skipped (симлинки Windows, `WinError 1314`), 125,63 с.
- По просьбе пользователя проверенная D121 атомарно установлена вместо D120 без резервной копии. Размер и SHA256 установленного EXE совпали со сборкой. `python/dist/godot_agent_server.exe` игнорируется Git; установка ничего не отправляла на GitHub. Пользователь предпочитает проверять последнюю сборку на месте, а не запускать две версии отдельно.
- Установленный D121 запущен без аргументов на рабочем профиле. Авторизованные `/health` и `/tools/list` вернули 200 (35 инструментов), без токена `/tools/list` вернул 403. Проверочный процесс штатно завершён с `0`, порт `5000` свободен, токен не изменился. Логи: `%LOCALAPPDATA%\Temp\opencode\d121-installed-check-4jlijik2`. Провайдер не вызывался.

### Где остановились — D121

D121 установлена; следующий шаг — отправить одно «привет» в новом чате панели и проверить, что DeepSeek получает одну отправку, а панель показывает один ответ.

## D122 — задержка показа и согласие на чтение (2026-11-27)

- По живому отчёту и `docs/chat.txt`: редактор добавлял контекст даже в ответ на результат чтения; восемь разных запросов обрабатывались внутри одного `/chat`. Восьмой был корректным запросом модели. Результат `only_exts:["gd"]` был ложно пустым. В логе нет временных отметок для атрибуции живых задержек.
- Панель начинает с инструкции без данных проекта и редактора. Путь сохранённой сцены используется локально лишь для адресации явного `list_scene`. Чтение возвращает промежуточный текст и одноразовый запрос. Отказ не обращается к провайдеру. Каждая восьмая операция требует явного продолжения. Разрешение на чтение не подтверждает предпросмотр правки.
- Одновременно с ожиданием ответа авторизованный `/chat/progress` передаёт ограниченный текст; UI выводит его без очереди побуквенной печати. Для законченного перенесённого текста и отдельного JSON чтения DeepSeek учитывается фактическое содержимое разметки. Две одинаковые полные выборки при остановленной генерации обязательны. Неполный ответ и необъяснимая высота остаются на прежней проверке.
- `test_panel_read_series`: восемь независимых решений до финального ответа, фильтр расширений, отказ от просроченного, заменённого или изменённого запроса и поток до окончания хода. `test_new_deepseek_chat_user_journey`: приветствие без раскрытия, просмотр сцены только после согласия, отказ без отправки, запись через отдельное подтверждение и побайтовый откат. В настоящем Godot проверены кнопки и отзыв плашки; в изолированном Chrome — переносы строк и отказ при пустом пространстве под текстом. Ускорение для воспроизведённого запроса чтения: ≥20 с → <1,5 с по искусственным часам, не полный цикл у провайдера.
- `selfcheck assistant.chat`: `ok`, 29 unit / 10 corpus; `assistant.write`: `ok`, 43 / 4. CLI `tree` на временном проекте вернул только `hero.gd`. Изолированная сборка EXE: 45 914 153 байта, SHA256 `f2b017e2060d4cc3b1c90d4779c9ca7856cf3f26565d02f189d29119d4146880`; loopback `:0` — 35 инструментов, чтение диапазона, `PREPARED` без изменений проекта и штатный выход.

- Регресс каналов, панели, передачи, браузера, безопасности, редактора и форматов: **1782 passed, 2 skipped** за 121,10 с (оба пропуска — создание симлинка без привилегии Windows, `WinError 1314`). Отдельно прошёл тест реальных кнопок Godot.
- После подтверждения D122 установлен вместо D121 без резервной копии; SHA256 установленного `python/dist/godot_agent_server.exe` совпал со сборкой выше. Именно этот файл запущен с временным проектом и портом `0`: `/chat/read/decision` отказал без токена (403) и с несуществующим билетом (409), `/chat/progress` показал свободный сервер. Обнаружены 35 инструментов, прошли чтение диапазона, предпросмотр без изменения проекта и штатное завершение. Обращений к провайдеру не было.

### Где остановились — D122

После перезагрузки панели проверить новый чат с DeepSeek: приветствие → запрос чтения → «Разрешить всегда» → отзыв плашкой → новый запрос. Сравнить появление первого текста и окончательной карточки со временем готовности в браузере.

## D123 — оформление нативного дока

В `origin/experiment` сохранена точка возврата `d32ecda` с D122. Изменения внешнего вида вынесены отдельно. Главное меню начинается сверху, ввод использует тему редактора, а запрос доступа отделён от обычной переписки. Уложили варианты ответа в узкую панель, сохранив раздельные решения «Один раз», «Всегда в этом чате» и «Отказать».

- Godot 4.6.3, отдельные профили: [снимки главной и тестового диалога](../.github/dock-preview/README.md). При ширине 250 и 420 px проверены границы видимых элементов, контраст вторичного текста, фокусируемость и три сигнала навигации. Выявленный выход кнопки чтения за правый край исправлен. Четыре live-теста прошли, включая кнопки решения и отзыв разрешения.
- `selfcheck assistant.write` — `ok` (43 unit, 4 corpus); CLI `read` вернул текст из временного проекта. Гейты архитектуры, безопасности, контрактов и размеров прошли; два прежних предупреждения размеров.

### Где остановились — D123

Для просмотра в рабочей панели переоткрыть проект. Изменения загружает редактор из GDScript; пересборка сервера не требуется.

## D124 — история чата

Панель показывала ответ, но `/chat` не дописывал его в `transcript`, из которого
`/chats/open` восстанавливает переписку. До исправления повторное открытие
возвращало `[]`. Проверены изоляция чатов, один пользовательский запрос на серию
чтений, маскирование секретов и предупреждение при отказе записи без повторной
генерации. Прежние пустые записи не изменялись миграцией.

С подтверждения пользователя установлен EXE D124 без резервной копии, SHA256
`cac8f9ee13c74cdbb9c1a4f1583d9803c597c1d9ff2dc831caf459170e202249`.
На временном профиле: запрос к локальному тестовому API, остановка, запуск
второго процесса, открытие по ID — сохранённые запрос и ответ совпали, вызов
модели был один. `selfcheck` для `assistant.chat` (29 unit / 10 corpus) и
`assistant.write` (43 / 4), CLI `read`, проверки контрактов, архитектуры,
безопасности и размеров прошли; два прежних предупреждения размеров.

### D124 — второй вариант панели

Главная — «Мастерская проекта» с графикой узлов, прямым входом в историю
и двумя способами начать чат. В диалоге текст ответа занимает ширину дока.
Проверены главная и переписка в Godot 4.6.3 на 250 и 420 px в обеих темах
(2 live-теста); [снимки](../.github/dock-preview/README.md). Регресс панели,
каналов, переноса и фактов исходников: 739 тестов прошли. Первый прогон
обнаружил, что отдельный тест D116 проверял текст локализации до добавления новых
подписей; теперь он проверяет тот же исторический текст после обратимого
удаления только добавленных строк из проверенной версии.

### Где остановились — D124

Переоткрыть рабочий проект, начать диалог, затем открыть его по кнопке
«Сохранённые чаты». Исправление истории (`85b28d1`) сохранено отдельно от вида панели.
