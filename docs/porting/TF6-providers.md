# T-F.6 — провайдеры, каталог и UID (2026-11-22–23)

## Цель и границы

Мандат: [_start-prompt.TF6-providers.md](_start-prompt.TF6-providers.md).
Непустой `/api/providers` с минимумом aistudio/openrouter/deepseek/qwen;
реальный рендер `/sites/list`; быстрый fail-closed refresh/scan без ключа;
UID `AgentStatusBar.tscn` по фактическому `.gd.uid`.
Запрет rebuild пересмотрен пользователем/аудитором (D107): разрешён офлайн build
установленным PyInstaller 6.21.0. Native backup, installed и sealed-досье —
только чтение; git/sync не разрешены. Frozen изменения только после D106+.
Никаких ключей или вызовов провайдеров; внешний fetch пока не выбран и не выполнен.

## Старый код и судьба тестов

Native `python/main.py:241–246` регистрирует `server/chat_routes.py`:
провайдеры/сайты/refresh/scan определены там, а не в main.py.
Rebuild: `python/substrate/llm/api/{providers,providers_catalog,model_cache}.py`,
`python/substrate/assistant/server/chat_routes.py`, `python/runtime/http_services.py`.
UI: `editor/native/agent_server_link.gd`, `agent_panel_part3.gd`,
`agent_start_screen.gd`, `AgentStatusBar.tscn` и `AgentStatusBar.gd.uid`.
`docs/tests-map.md:141–149,152,163` — replaced (HTTP contract + live);
140/161 — replaced (панель/транспорт). Старый тест-код не переносится.
Это корректирующий HTTP/UI-срез принятого T-F.5, не новая публичная capability
и не закрытие отложенного `assistant.model_choice`/provider-live.

## Пины и инварианты

Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/tf6-20261122/`.
Свежие полные inventories: rebuild 6484, installed 6478, native 953 файла;
каждый файл bytes/SHA256/LF/CRLF, каталоги и reparse entries отдельно.
Exe 30859253 B / `969854a477e143e354fc2e7e96368a275345b5d16c4326ce6895fc00fbf5b320`
одинаков в rebuild/installed. Installed ref прочитан без git-команд:
`ccb03930db8bb569e8e0df74dde5f7f2c5b2cbbb`.
Весь актуальный WORKLOG сохранён: 1114358 B /
`76bd81885a0ce6d10070d0a37ec20db8c943b0df5ed6601f72365d41e39b29c4`.
Сохранение чужих байтов — по этому свежему полному prefix, не старому T-F.5.
Пины seal/receipt/ZIP T-F и T-F.5 сняты заново; публикации не изменяются.
Все probes — отдельные процессы с нейтральным окружением и внешним owned state.

## Актуальный этап: 5 — код/build, финальные прогоны впереди

D108 реализован; targeted34passed (25 additions+9 existing cap cases), eight
mutants killed с exact SHA/EOL restore. Cold source x2: ten providers/no_key,
zero network attempts/config writes. Первый offline exe30866721B/SHA256
`d374b9227a482b7f32e74bb2dffb895e74936f9bf3e79ea88c884d8e77c94427`,
embedded raw closure exact. D109 сохраняет fixture/observer failures и исходный
pre-code RED; неверный auth403 run не принят. D110 уточняет metadata badge:
в scoped HTTP “список без ключа” недопустим, исходный API registry не меняется.

Следующее: scoped badge и повторный offline build → настоящая panel пара без
перекрытия с mutants → regression8483/gates4/selfchecks8 x2 → final security/
ownership/identity → seal LAST/verified sibling ZIP. Installed/native не sync.

## История этапа 2 (не актуальное состояние)

Этап 2: preflight, парные офлайн-наблюдения и observation RED завершены.
**STOP снят пользователем/аудитором; D107/D108 — build и спецификация коррекции.**
Production, exe, installed, native и прежние sealed-досье не менялись.
Native/rebuild ×2 и настоящий pinned exe ×2 возвращают восемь API-провайдеров
при холодном кэше. Пусты вложенные `catalog.providers`/`catalog.models`,
а не верхний `providers`. aistudio/qwen — браузерные site IDs, API Gemini
называется gemini; буквальный минимум API-ID мандата пока не выполнен.
`model_cache.py` хранит живые списки в models_cache.json;
`providers_catalog.py` — вторичный справочник в catalog_cache.json.
В native backup provider/catalog cache не найден; default_api_cache.json — Godot API.
UID сцены `uid://1k5olngje7r8` не совпадает с sidecar `uid://cyv7bxjosjeps`.
Предупреждение воспроизведено в настоящем Godot; исправление не внесено.

## Проверки и доказательства

- `observations/paired-summary.json`: native/rebuild ×2, audit hook до
  urllib/DNS/connect, внешних запросов 0. Refresh без ключа пытается OpenRouter;
  scan — models.dev и публичные endpoints. Это RED, не измерение сетевого timeout.
- `exe/closure-proof.json`: 6 встроенных `.py` byte-exact, 4 compiled PYZ
  модуля исследованы без исполнения/пересборки. Путь `_load` — packaged source.
- `live/round-{7,8}.json`, `live/sites-{7,8}.png`: реальный native sites signal,
  HTTPRequest и шесть **видимых** кнопок. Exe игнорирует три аварийных соседних
  `.py` sentinel. Исправление только исходников в живой exe не попадёт.
- Порт пользователя 5000 занят; процесс не тронут. Live — явные args и
  единственная HOST-подстановка в owned copied UI, не zeroargs acceptance.
  API-tab (автоматический scan) не открывался. Ключей/provider-cache seeds нет,
  только обычный updater TTL. Подробности и неудачи harness: **D106**.
- `diagnostics/observation-red-before-code/`: 13 cases, **9 fail / 4 pass**;
  это проверки снятых наблюдений, не замена будущих unit/contract/live тестов.
- `diagnostics/selfcheck-checkpoint-assistant.chat/output.log`:
  `{"module":"assistant.chat","verdict":"ok"}`; unit **29 passed**,
  corpus **10**, расхождений 0. Предикаты genuine selfcheck неизменны,
  REPORTS внешние, D103 adapter и synthetic offline chat transport явные.
  Это baseline checkpoint, **не** selfcheck завершённого T-F.6.

Следующее действие: завершено в `D:\vajno\Godot\тест-плагина-ии\addons\godot_agent` (этап 7, без авто-коммита и без изменения `agent-rebuild`):
- `D110` (`python/substrate/llm/api/providers_fallback.py`): в HTTP `scope` у скопированных записей с `models_public` (`openrouter`, `opencode_zen`) выставлен `models_public=False` и честные RU/EN-пометки о требовании ключа без мутации нативного `providers.py`; на выходе ссылки реестра/кэша восстанавливаются (`tests/py/panel_tf/test_tf6_d110_models_public.py`, 3/3).
- `D111` (§1.5 `BUG-008`, `python/runtime/chrome_paths.py`, `exe_bootstrap.py`, `app.py`, `interactive_gateway.py`): автоопределение Chrome/Edge на старте сервера (стандартные пути Chrome → `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe` → Edge), запись `GODOT_AGENT_CHROME_PATH` без затирания явного валидного пути и без доступа к `User Data`; при отсутствии бинарника fail-closed «Chrome не найден, укажите путь в настройках» (`test_chrome_autodetect.py`, `test_chrome_autodetect_security.py`, 7/7).
- `D112`/`D113` (`BUG-004`/`010`/`011`, `editor/native/agent_panel.gd:400,418`, `tests/py/panel_tf/source_inputs.py`, `tests/conftest.py`): добавлен `return` в `_locale()` и `_T()`; входов-ревизия `D113` (82171→82185 B) с крипто-сверкой прообраза сохраняет бизнес-эталоны `scene_deps_facts` без правки старых манифестов (`test_panel_locale_live.py` в реальном Godot 4.6.3 подтвердил `_locale()`, `_T()`, `%`-форматирование, `AgentStatusBar.tscn` UID `cyv7bxjosjeps` и кнопки `set_sites()`, 2/2).
- `D107`/`D115` офлайн-сборка `python/dist/godot_agent_server.exe` (PyInstaller 6.21.0, `--collect-submodules selenium`, внешняя работа, без сети): `45864239` B, SHA256 `730fa3245566b527cf1a248355548b1904bab71aa7d25bf2f8bd7e5edf56e61d`; в PYZ проверены все `125` модулей `selenium` (`123` транзитивных при импорте `ChromeOptions`/`ChromeService`/`SeleniumManager`), живой Chrome CDP attach (`about:blank`, `navigator.webdriver=False`), `D114`/`ADR-0092` (`listener.py` архивирует мёртвый loopback `http_endpoint.json` в `.stale-<pid>-<ts>.json`, `test_stale_endpoint_archive.py` 10/10) и реальный zero-arg запуск exe на `тест-плагина-ии` (`port=5000`, `/health 200`, `/server/shutdown` exit `0`).
- Проверки финала: все `10` мутантов (`7` T-F.6/D113 + `2` ADR-0092 + `1` D115) убиты с точным восстановлением SHA/EOL; 4 гейта ×2 `rc=0`; 8 `selfcheck` ×2 все `verdict=ok` (с принятым K1c offline hook и D103); `probe.py read` ok; `tests/py/live/test_panel_locale_live.py` + `test_bridge_live.py` 3/3; полный регресс ×2 (D103+D113): `8601` collected → `8599 passed + 2 skipped (WinError1314) + 0 failed` в обоих раундах. Внешнее досье `%TEMP%\opencode\c8_audit\tf6-20261125\` (seal LAST + sibling postseal ZIP).
- Дополнение `ADR-0093` / `D116` (`BUG-009`/`BUG-012`/`BUG-013`, 2026-11-25): исправлен полный цикл `POST /chat/live_input` (`panel_services.py` `_selection()` и `PARSER` + `kind == 'api'` guard), `/chat` + `/chat/progress` (`routes_chat.py` `'prompt'` и `active=session.busy`), fail-closed политика панели (`agent_panel_part1.gd`/`part4.gd`/`agent_locale.gd` + обратимый пин `D116_REVISIONS`) и script UID во всех 7 `editor/native/*.tscn` при полном сохранении строгого `auth.py` ADR-0091 и `test_panel_tf_security.py`. Остаются вне данного прогона: `BUG-001..003`, `test_editor_branch_live.py` (ожидает старый `plugin.gd` вместо `agent_entry.gd`) и живая интерактивная обкатка ключей/браузера пользователем в окне редактора Godot.
