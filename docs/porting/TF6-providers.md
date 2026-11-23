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

Следующее действие: resume-пины/backup старого exe, нормализованный корпус и новые
unit/contract/security RED; затем реализовать D108 и офлайн build.
Static fallback в locked runtime scope: aistudio=Gemini API, qwen=DashScope API,
без live models/verified; принятые API253 goldens/источники неизменны.
Исторический D106 STOP и checkpoint/status.json остаются в досье как история.
Полный регресс 8458+свои ×2, гейты4 ×2, selfcheck8 ×2, seal LAST/ZIP —
условия закрытия, пока не выполнены и не заявлены.
