# Заметки

Рабочие заметки, которые не должны потеряться, но и не являются правилами.
Правила — в `../RULES.md`, состояние переноса — в `parity.md`, ход работы — в
`WORKLOG.md`.

## 1. Что показал разбор старого агента

Масштаб: 381 файл, ~10 МБ, 265 `.py`, 43 `.gd`, 168 тестовых файлов (2,1 МБ).
Само по себе это не «плохо». Плохо — распределение:

| Файл | Размер | Что это значит |
|---|---|---|
| `python/main.py` | 304 КБ | точка входа, в которой живёт полпроекта |
| `selfcheck.py` | 235 КБ | самопроверка, написанная как второй проект |
| `agent_start_screen.gd` | 204 КБ | экран настроек больше, чем вся панель |
| `parsers/parser_base.py` | 198 КБ | базовый класс парсеров на 5 тысяч строк |
| `tools/agent_bridge.py` | 142 КБ | «мост», в котором и транспорт, и логика |
| `godot_tools/project_tools.py` | 102 КБ | чтение/поиск/список в одном файле |
| `godot_tools/librarian.py` | 96 КБ | справка по проекту + индекс + ранжирование |
| `backends/api_backend.py` | 92 КБ | ветка API целиком в одном файле |
| `godot_tools/tscn_lint.py` | 74 КБ | линт сцен |
| `godot_tools/split_gd.py` | 63 КБ | разбиение файлов |
| `agent_panel_part1..5.gd` | ~265 КБ | панель разрезана по размеру, а не по смыслу |

Следствия, которые новая структура обязана снять:

1. «Найти и починить» требует чтения файла на 3–8 тысяч строк.
2. Тесты есть (168 файлов), но они привязаны к большим модулям, поэтому падают
   пачками от одного изменения.
3. Ветки (API, браузер, MCP, панель) знают про детали домена — отсюда четвёртые
   копии одной логики.
4. Разрезание по размеру (`_part1..5`) — признак того, что границы проводили
   ножом, а не по смыслу.

## 2. Что в старом агенте есть сверх 24 MCP-инструментов

MCP-сервер (`python/tools/godot_agent_mcp.py`, 26 КБ) отдаёт 24 инструмента —
это и есть «функциональный минимум», который переносим: `status`, `engine`,
`api`, `ask`, `search`, `read`, `scene`, `functions`, `usages`,
`analyze_rename`, `context`, `check`, `check_action`, `paths_preview`,
`write_preview`, `write_apply`, `write_rollback`, `node_rename_preview`,
`node_reparent_preview`, `node_delete_preview`, `split_scan`, `split_plan`,
`split_gd_scan`, `split_gd_plan`.

Остальное — не «возможности редактора», а каналы и инфраструктура:

| Блок | Файлы | Решение |
|---|---|---|
| `api/` (7 файлов, 288 КБ) | ключи, провайдеры, каталог моделей, openai/anthropic-совместимость, DoH | в `substrate/llm/`, после паритета редакторных возможностей |
| `backends/` (92 + 3 КБ) | api_backend, browser_backend | в `substrate/llm/` + `channels/`, не раньше второго этапа |
| `browser/` (7 файлов, 87 КБ) | CDP, менеджер браузера, сайты, монитор сети, live input | `substrate/llm/browser/`, отдельным этапом |
| `parsers/` (7 файлов, 364 КБ) | парсеры ответов AI-сайтов (arena, qwen, deepseek, kimi, ai) | `substrate/llm/browser/`, нужны только браузерной ветке |
| `minilich/` (8 файлов, 213 КБ) | локальная модель: индекс проекта, тренировка, токенайзер | **под вопросом**: нужно ли вообще в новой версии |
| `server/` (12 файлов, 269 КБ) | HTTP для панели, чат, история, промпты, авторизация, rate limit | `channels/http/` + `modules/assistant/`, частями |
| `tools/` (12 файлов) | MCP-сервер, мосты, релизные скрипты, аудит | часть в `channels/mcp/`, часть в `tools/` |
| `n8n/`, `reports/`, `tasks/`, `minilich_brain/` | скрипты, отчёты, задачи | не переносить: это рабочая свалка |
| `python/tests/` (168 файлов) | тесты старого | не переносить как файлы; брать как источник кейсов для корпуса |

## 3. Решения, принятые по ходу (не в ADR)

- `plugin.gd` намеренно пустой: включение плагина ничего не делает. Это лучше,
  чем «работающий наполовину» вход, который мешает отладке первого шага.
- `.tscn` не создаются: пустая сцена в Godot выглядит как работающая
  функциональность и вводит в заблуждение.
- Контракт лежит черновиком (`_status: "skeleton"`), чтобы схемы не
  притворялись согласованными до первого переноса.
- В каждой области есть `shared/` — общий код области идёт туда, а не в
  `kernel` (kernel не растёт, R-06).
- Старые имена инструментов сохраняются плоскими (`write_apply`, а не
  `editing.write_apply`): внешний контракт важнее красоты.
- Валидатор схем (`kernel/schema.py`) понимает `type` списком
  (`["string","null"]` — это nullable-ответы моста: «выделения нет», «сцены нет»)
  и считает **неизвестный тип отказом**, а не пропуском. «Мягкая проверка»
  неизвестного типа на деле была дырой: опечатка `"date"` проходила молча, а
  список ронял `TypeError`. Теперь опечатка в контракте ловится гейтом
  `tools/gen_contract.py --check` (`unknown_schema_types`), а не первым ответом.
- `type: null` в схеме — «тип не задан», а не отказ: `validate` не проверяет тип,
  `unknown_schema_types` молчит. Отличие от неизвестного имени: `null` — это
  отсутствие ограничения, `"date"`/`5`/`{"x": 1}` — ошибочное ограничение, и оно
  отказ (fail closed). Поведение зафиксировано пином
  `test_type_null_means_type_is_not_set`, чтобы «пустое место» не превратилось в
  отказ при следующей правке (R-08: перенос не улучшает).
- Тотальность `validate` — обещание докстринга, и оно **доказано тестом**:
  мусорный набор (`type`-словарь, `type: [{"x": 1}]`, `properties: 5`,
  `required: 5`, `items: "x"`, `required: "path"`) не бросает исключений, а мутация
  любой из трёх защит (`str`-проверка типа, `properties`-dict, `required`-список)
  красит `test_non_string_type_is_refused_not_raised` или
  `test_garbage_schemas_do_not_raise`. Пока одна из защит была непокрыта,
  «тотальность» была только словами (аудит 2026-10-27).

## 4. Открытые вопросы

| № | Вопрос | Варианты |
|---|---|---|
| Q-01 | Где хранить рантайм-состояние | `user://godot_agent/` (так и записано в architecture) vs внутри папки плагина |
| Q-02 | Как поставлять Python | системный python vs встроенный рантайм vs собранный exe (старый собирал `build_server_exe.bat`) |
| Q-03 | Имя плагина и порт | `godot_agent` vs `Godot_Agent`; порт фиксированный vs динамический с файлом-маркером |
| Q-04 | Способ регистрации модулей | сканирование (принято, R-03) vs явный список |
| Q-05 | Где хранить снапшоты паритета | репозиторий (корпус + хеши) vs артефакт CI |
| Q-06 | Имена инструментов | плоские — принято; иерархические только как алиасы |
| Q-07 | Что делать с `minilich` (локальная модель) | не переносить / как необязательный модуль |
| Q-08 | Браузерная ветка в первой версии | отложить до паритета редакторных возможностей |

## 5. Риски

| Риск | Как снижаем |
|---|---|
| Скелет разойдётся с реальностью при первом переносе | `parity.md` обновляется вместе с кодом; пустая папка без строки в parity — мусор |
| Захочется «улучшить по пути» | R-08: перенос с улучшениями запрещён; улучшения — после зелёного паритета |
| 44 папки × 7 файлов превращаются в кладбище заготовок | файл создаётся, когда нужен: `settings.py`, `ports.py` и лишние `domain/*` — только по факту |
| Два плагина рядом (старый и новый) | разные id, порты и папки `user://`; одновременно не включать |
| Python-часть не стартует у пользователя | профиль `headless`, явная ошибка `engine_down`, Q-02 закрыть до релиза |
| Сканирование модулей на каждом старте медленное | кэш «путь + mtime» в `runtime/module_loader.py`, инвалидация по времени |

## 6. Идеи на потом (не делать сейчас)

- `tools/check_limits.py` в pre-commit: рост файла сверх лимита виден сразу.
- Генерация `contract/capabilities/*.json` из `ToolSpec` — пока ручной шаг
  (`gen_contract.py`), чтобы контракт не менялся незаметно.
- Метка `ported verbatim` в docstring перенесённых функций: быстрый поиск того,
  что ещё дословно из старого.
- Генератор `docs/map.md` — карта модулей, чтобы дерево не устаревало руками.
- Проверка «в `domain/` нет импортов IO» уже описана в R-11; стоит сделать её
  тестом, а не только линтером.

## 7. Что выяснилось из кода старого агента (сессия 2)

| Наблюдение | Следствие для новой раскладки |
|---|---|
| `main.py` — Flask-хост с 38 роутами, который сам гоняет домен | каналы только переводят протокол; логика — в модулях |
| `tools/agent_bridge.py` — **второй** хост того же домена, со своей политикой доступа и своими квитанциями `plan_id` | один `protocol/dispatch`, одна политика `kernel/paths` |
| `tools/godot_agent_mcp.py` — чистый транспорт (24 tool → argv) | так и оставляем: `channels/mcp` |
| Пять парсеров `.gd` и четыре разбора `.tscn` | `formats/{gdscript,tscn}.py` |
| `project_tools.py` = 8 несвязанных обязанностей | разъезжается по 8 адресам |
| `agent_runtime_bridge.gd` работает **в игре** | отдельный каталог `runtime/` |
| `agent_headless_validator.gd` запускает Python, а не панель | `editor/harness/` |
| `agent_panel_part1..5` — резка по объёму, а не по смыслу | `ui/panel/*` по потокам |
| `agent_start_screen.gd` 204 КБ, 140 функций, 6 разделов | `ui/start/*` по разделам |
| `agent_locale.gd` — два словаря + API языка в одном файле | `core/i18n/{ru,en,locale}.gd` |
| `plugin_universal.gd` и `agent_entry.gd` оба претендуют на вход | Q-09 |
| `history_manager.py` — журнал, квитанции и откат в одном | журнал → `substrate/store`, откат → `editing.rollback` |
| `librarian.py` (96 КБ) — и карта, и фрагменты, и вызовы, и API | `context.ask` + `engine_kb` + `formats` |
| `minilich/`, `browser/`, `parsers/` — отдельные подсистемы | не переносим (Q-07, Q-08) |

## 8. Открытые вопросы сессии 2

- **Q-09. Какой файл — вход плагина?** В старом аддоне `plugin.cfg` указывал на
  `agent_entry.gd`, но шапка `agent_entry.gd` утверждает, что вход —
  `plugin_universal.gd`. Решить до первого запуска: один вход `plugin.gd`.
- **Q-10. Как игровая половина попадает в игру?** `runtime/probe.gd` — это
  autoload, который добавляет сам плагин, или отдельный файл, который пользователь
  кладёт в проект? От ответа зависит, можно ли считать `runtime/` частью аддона.
- **Q-11. `agent_api_export.gd`** — экспорт настроек API наружу: это UI
  (`ui/start/api_settings`) или HTTP-маршрут? Уточнить при переносе.
- **Q-12. Нужен ли `context.runtime_snapshot` в первой версии?** Старый
  `runtime_debug.py` — read-only инспектор, MCP-инструмента у него не было,
  только HTTP. Если игровую половину откладываем, модуль остаётся пустым.

## 9. Решения сессии 3 (после внешнего ревью)

- **Порт живёт в модуле.** `ports.py` рядом с потребителем (`typing.Protocol`),
  реализация — в `substrate`. Глобальной `python/ports/` нет: она бы стала свалкой
  и позволила бы модулю тянуть чужие объявления. Записано в R-02 и R-11.
- **`check` — композиция, а не модуль.** Агрегатор вызывает инструменты реестра
  из `protocol/`; модулю запрещено звать модуль (R-11), поэтому своя папка у
  агрегатора была бы нарушением. Файл: `python/modules/verification/check/`.
- **Инструмент виден из папки.** `# tool:` / `# tools:` в шапке `module.py`:
  поиск по имени инструмента ведёт в папку без посредника-таблицы.
- **`app.py` — оркестрация, ≤ 80 строк.** Правила — в `domain/`; бюджет назван,
  потому что «серединный» файл иначе впитывает логику.
- **`docs/inventory.md` — данные, не код.** Под лимит R-06 не подпадает, имеет
  оглавление по каталогам (16 разделов) и пересобирается по требованию.
- **`.gitignore` лежит внутри плагина** (R-01), а не в корне проекта: мусор
  прогонов Python появляется только здесь.
- **123 `__init__.py` остаются.** Пакетные маркеры делают импорт и сбор тестов
  предсказуемыми; выигрыш «минус 123 файла» не стоит неявных namespace-пакетов.
  Если решим иначе — это отдельное решение с проверкой загрузчика.

## 10. Открытые вопросы сессии 3

- **Q-13. Нужна ли машиночитаемая карта `docs/map.json`?** `tool → module → path →
  status`, генерируемая из `parity.md`/`module.py` и сверяемая в CI. Сейчас карта
  только в Markdown; JSON снял бы расхождения «инструмент ↔ папка» навсегда.
- **Q-14. Нужна ли отдельная карта `.gd`-стороны?** `inventory.md` разбирает `.gd`
  только по шапке и именам функций; для переноса `editor/**` нужен такой же
  разбор с сигналами, `@onready`, сигналами и вызовами.
- **Q-15. Убирать ли `__init__.py` (123 файла)?** Решение отложено: сначала
  загрузчик модулей, потом замер, потом решение.

## 11. Решения сессии 4 (по второму ревью)

Ревью от топовой модели разобрано по существу: «структуру менять не нужно» —
не учитывалось, учитывались только находки.

| Находка | Что зафиксировано |
|---|---|
| порты нечем связать с реализациями | composition root в `runtime/bootstrap.py`, `ModuleContext`, `requires_ports`, структурная типизация, тест `isinstance` (ADR-0003) |
| абсолютный запрет межмодульных связей нереалистичен | публичное API модуля через `__init__.py` + `requires`, чужой `domain/` запрещён, отключение транзитивное (ADR-0004) |
| `check` в `protocol` — прикладная логика не на своём месте | владелец `check` — модуль `verification.check`, остальные дают вклады (ADR-0004) |
| у инструмента несколько «хозяев» | `provides_tools` / `contributes_to` / `internal_services` / `requires`; конфликт владельцев → `disabled` обоим (ADR-0004, R-05) |
| атомарность была обещанием без модели | WAL до эффекта, `PREPARED/APPLYING/COMMITTED`, квитанции, recovery, лок, digest+TTL, редакторский батч, откат не затирает чужое (ADR-0005, R-12) |
| контракт был и источником, и артефактом | источник — `ToolSpec`, артефакт — `contract/*.json`, `module_id`/`capability_id`/`tool_name` разведены (ADR-0006) |
| `kernel` содержал Godot-парсеры | `python/formats/` — отдельный слой без IO и без Godot; в `kernel` конверт `WritePlan` (R-11) |
| жизненный цикл знал только успех | транзитивное отключение, `degraded`, обратный `teardown`, таймауты, `environment="editor"` для сцен (architecture §7) |
| R-03 был абсолютным | разграничено: фича на готовых портах — папка; новый примитив/операция/адаптер — расширение контракта (R-03) |
| критерии паритета были жёстче правды | три класса проверок: наблюдаемый паритет / бюджеты / safety-инварианты; лимиты — предупреждения (R-09, R-06) |

## 12. Открытые вопросы сессии 4

- **Q-16. Кто владеет `contract/editor_verbs.json`?** Примитивы пишутся руками
  (источник — GDScript), но версия у них общая с `contract/` — нужен ли
  `verbs_version` и как ловить расхождение с `# tool:`-строкой в `.gd`?
- **Q-17. Нужен ли отдельный процесс для headless-прогонов?** `verification.headless`
  запускает Godot: это долго и может упасть. Пока решение — таймаут профиля и
  `engine_down`, но при параллельных вызовах может понадобиться очередь.
## 13. Решения сессии 5 (перенос через тесты)

| Вопрос | Решение |
|---|---|
| Переписывать старые тесты или писать новые? | Старый тест — источник **кейсов**, не файл. Кейс извлекается в корпус, новый тест пишется из спецификации (R-16) |
| Что первично — тест или корпус? | Корпус: он снимается со старого агента механически и не зависит от чьего-то мнения о поведении |
| Как гарантировать, что покрытие не потеряется? | `docs/tests-map.md`: строка на каждый из 168 файлов, строки не удаляются, `pending` блокирует статус `ported` (R-17) |
| Где лежат правила, чтобы агент их не пропустил? | `AGENTS.md` в корне плагина: обязательный порядок чтения, стоп-условия, 8 шагов, команды проверки. `RULES.md` — источник истины, `AGENTS.md` — вход |
| Как переносить браузерную часть? | Отложено (Q-08). Корпус — записанные кадры `ai_studio_net` / `qwen_net`, живая проверка разово на DeepSeek. Живой сайт не может быть условием паритета |
| Можно ли закрыть `live`-тест юнит-тестом? | Нет: `live` проверяет то, что подделка не воспроизводит (реальный `.tscn`, undo-скоуп, перезагрузку сцены). `replaced` — только через e2e или живую проверку |

## 14. Открытые вопросы сессии 5

- **Q-19. Где хранить корпус: в репозитории или в артефактах CI?** Предложение:
  малые фиксированные кейсы (< 1 МБ на механику) — в `fixtures/corpus/`, крупные
  прогоны — генерируются скриптом и сверяются по хешу, в репо только манифест.
  Решить на первом прогоне `project_text.search`.
- **Q-20. Как снимать корпус для механик, которым нужен живой редактор?**
  (`node_rename`, `scene_ops`, `mutation_gate`.) Варианты: ручной прогон с записью
  входа/результата, либо headless Godot с тестовым проектом, либо запись
  протокола обмена из старого моста. Предпочтителен третий: он не требует ни
  редактора, ни рук.
- **Q-21. Формат записи корпуса.** Предложение: JSON с нормализованными путями
  (`<PROJECT>/scenes/player.tscn` вместо абсолютного), хешами файлов до/после и
  `kind` ошибки; `manifest.json` — версия, дата снятия, версия старого агента.
  Уточнить, когда появится `tools/snapshot_record.py`.

## 15. Решения сессии 6 (инструменты проверки и статус)

| Вопрос | Решение |
|---|---|
| Кто проверяет перенос? | Сам агент своими инструментами: `probe.py` (вызвать механику) и `selfcheck.py` (вердикт), а не ручные команды (R-18) |
| Что считается доказательством? | Код возврата `0` от `selfcheck` + файл `reports/selfcheck/<module_id>.json`; «посмотрел глазами» — не доказательство |
| Как отличить «не реализовано» от «работает»? | Контракт вердикта: проверка печатает JSON `{"status": ...}`. Нет вердикта — `not_implemented`, а не «зелено» |
| Что делать с механиками, которым нужен редактор? | `selfcheck` ставит `needs_live`; статус `ported` без живой проверки невозможен |
| Где живёт состояние переноса? | `docs/PROGRESS.md` (этап + следующее действие) и лист `docs/porting/<module_id>.md` (ход, решения, вердикт, блокеры) — R-19 |
| Как продолжается работа в новом чате? | `AGENTS.md` → `PROGRESS.md` (первая механика с этапом `< 7`) → её лист → последняя сессия `WORKLOG.md` |
| Хранить ли отчёты `selfcheck` в git? | Нет: `reports/` в `.gitignore`, вердикт переносится в лист механики текстом |

## 16. Открытые вопросы сессии 6

- **Q-22. Как `selfcheck` узнаёт, что механике нужен живой Godot?** Варианты:
  поле в `ToolSpec` (`availability`), явный список в модуле (`needs_live = True`)
  или автоматически по объявленному порту `editor`. Решить на шаге 1 вместе с
  `ToolSpec`.
- **Q-23. Чем запускать тесты, если `pytest` не установлен?** Сейчас
  `selfcheck` сообщает `not_implemented` («нет зависимости»). Варианты: добавить
  `pytest` в dev-зависимости `pyproject.toml`, либо писать тесты на `unittest` из
  stdlib (тогда внешних зависимостей нет вообще). Второе ближе к правилу «kernel
  живёт на stdlib», но `pytest` удобнее для параметризации корпуса.



## 17. Решения сессии 7 (безопасность)

| Вопрос | Решение | Где |
|---|---|---|
| Как не обещать невозможного | модель угроз с разделом «принятые ограничения»: учётка пользователя, видимость кода у провайдера, отсутствие подписи релиза | `docs/security/threat-model.md` |
| Как сделать обещание проверяемым | 18 инвариантов SEC-01…SEC-18, у каждого `P`/`T`/`R` | `docs/security/invariants.md` |
| Куда смотреть машине | `tools/security_audit.py`: 8 статических проверок, вердикт по контракту R-18, входит в `selfcheck` | `tools/` |
| Что считать сетью | всё, кроме `substrate/llm`; список хостов — данные `contract/network_allow.json`; приватные и metadata-адреса запрещены всегда | R-20, SEC-08/09 |
| Данные ≠ команды | запрет `os.system`, `eval`, `exec`, `pickle`, `shell=True`, `OS.execute`/`OS.shell_open` в `.gd` | SEC-01, SEC-05, SEC-14 |
| Секреты | только `user://godot_agent/` или переменные окружения; редакция по шаблонам в логе, ошибке, отчёте и корпусе | SEC-06, SEC-13 |
| Где вход безопасности в цикл | шаг 3 (эффекты и инвариант до кода), шаг 7 (атакующий тест), шаг 8 (`security` в `selfcheck`), шаг 10 (fail closed) | `PORTING.md` §10 |
| Запись и подтверждение | `apply` без `plan_id`/`digest` невозможен; автоподтверждение только из настроек, не из данных | SEC-11, SEC-15 |
| Обновление плагина | без подписи — только показ состава и diff; zip-slip запрещён; код из архива не исполняется | SEC-16 |

## 18. Открытые вопросы сессии 7

- **Q-24. Где хранить ключи провайдеров.** Варианты: `user://godot_agent/secrets.json`
  с правами пользователя (просто, но plaintext), DPAPI через `ctypes` на Windows
  (шифрование ОС, но платформозависимо), переменные окружения (не для GUI-плагина).
  Решать при переносе `assistant.model_choice` и `substrate/llm/secrets.py`.
- **Q-25. Как проверять prompt injection автоматически.** Нужен детерминированный
  «враждебный LLM»: тест подсовывает ответ модели с tool-call на `read .env`,
  на `write` без `plan_id`, на абсолютный путь — и требует `denied`. Вопрос: делать
  это отдельным harness (`tests/py/security/llm_stub.py`) или профилем `test` в
  `runtime/profiles.py`. Скорее первое: враждебность не должна жить в рантайме.
- **Q-26. Нужен ли аудит для `.gd`-стороны сильнее, чем запрет `OS.*`.** Сейчас
  проверяются четыре функции. Кандидаты: `FileAccess` с абсолютным путём,
  `DirAccess.remove_absolute`, `ResourceLoader.load` по пути из данных. Решить,
  когда появится первая редакторная механика (Q-16 рядом).


## 19. Решения сессии 8 (браузер и заметность)

| Вопрос | Решение | Где |
|---|---|---|
| Можно ли «улучшить» маскировку браузера | Нет. Правило-запрет, а не рекомендация | R-21, `security/browser-stealth.md` |
| Что именно разрешено подменять | `visibilityState` → `'visible'` и `hidden` → `false`, на `Document.prototype`, идемпотентно | SEC-19 |
| Почему не `hasFocus` | `toString()` выдаёт подмену: `"() => true"` вместо нативного кода | `browser_manager.py:71-75` |
| Где закреплены значения | `contract/browser_stealth.json`: `needs_visibility_spoof` по 6 сайтам, 8 запрещённых техник | R-21 |
| Как это защищено от случайной правки | `security_audit` проверяет код против контракта и падает; проверено негативным тестом | SEC-20 |
| Что если площадка перестала работать | Сеть, официальный API, отказ от площадки — но не усиление маскировки | R-21 |
| Обещаем ли полную невидимость | Нет: CDP-управление определяется и без `navigator.webdriver` | `browser-stealth.md` |

## 20. Открытые вопросы сессии 8

- **Q-27. ~~Уточнить, какой именно флаг имел в виду пользователь.~~ ЗАКРЫТ
  (сессия 8, уточнение).** Пользователь имел в виду флаг **webdriver**: сейчас
  сайты видят `navigator.webdriver === false`, но `true` сразу выдаёт агента
  защите площадки. Механизм: Chrome запускается обычным процессом, selenium
  только подключается через `debuggerAddress` — поэтому chromedriver не добавляет
  `--enable-automation`. Решение закреплено: `contract/browser_stealth.json` →
  `launch` (`mode: plain_process_then_attach`, `forbidden_args`,
  `selenium_launches_browser: false`) и `webdriver_flag`
  (`expected: false`, `spoof_allowed: false`); проверка — `security_audit` SEC-20,
  в том числе «`webdriver.Chrome()` без `debuggerAddress`».

## 21. Уточнение к сессии 8: флаг — webdriver

| Факт | Значение |
|---|---|
| Что видит площадка сейчас | `navigator.webdriver === false` |
| Почему `false` | Chrome запущен **обычным процессом** (`subprocess.Popen` + `--remote-debugging-port=9222`), selenium только подключился через `debuggerAddress`; chromedriver не стартовал браузер и не добавил `--enable-automation` |
| Что делает `true` | запуск браузера самим selenium: `webdriver.Chrome()` без `debuggerAddress` → chromedriver добавляет `--enable-automation` |
| Что запрещено | `--enable-automation`, `--headless`, `--headless=new`, `--disable-blink-features=AutomationControlled`, `webdriver.Chrome()` без `debuggerAddress`, подмена `navigator.webdriver`, `excludeSwitches`, `useAutomationExtension` |
| Как проверяется | `security_audit` SEC-20: строка из `forbidden_techniques` в коде браузерной ветки → `fail`; `webdriver.Chrome(` без `debuggerAddress` в том же файле → `fail`; комментарии вырезаются перед проверкой, чтобы слово в комментарии не считалось кодом |
| Где данные | `contract/browser_stealth.json` → `launch`, `webdriver_flag`, `forbidden_techniques` |
| Решение пользователя | держать флаг в `false`; `true` — риск обнаружения и бана на площадке |

Открытый вопрос, оставшийся от этой ветки: **Q-29. Кто запускает Chrome.**
Старый агент запускает сам (`subprocess.Popen`) и использует отдельный профиль
`%LOCALAPPDATA%\Godot_AI_Profile`. Вопрос: должен ли новый агент спрашивать
пользователя перед запуском (окно с профилем агента — это отдельная сессия без
его cookies) или подключаться к уже открытому им Chrome. Решать при переносе
`substrate/llm/browser`; сейчас ветка `deferred` (Q-08).

## 22. Ответ по Q-29: вариант «в браузере пользователя» невозможен

| Вопрос | Ответ |
|---|---|
| Можно ли подключиться к обычному Chrome пользователя | Нет. С Chrome 136 `--remote-debugging-port` игнорируется на **стандартном** каталоге данных, обязателен нестандартный `--user-data-dir` (developer.chrome.com/blog/remote-debugging-port, 17.03.2025). Подключение к реальному профилю технически закрыто |
| Хотели бы мы этого | Нет: агент получил бы доступ ко всем залогиненным сессиям пользователя (почта, банк), а «отравленный» файл проекта мог бы этим воспользоваться — прямое нарушение SEC-14/R-20 |
| Что тогда «не мешать пользователю» | Свой профиль остаётся, но окно **свёрнутое и без захвата фокуса** (`STARTUPINFO` + `STARTF_USESHOWMINNOACTIVE`), вкладки — только свои через CDP `Target.createTarget`/`Target.closeTarget`, буфер обмена и чужие вкладки не трогаются |
| Сохраняется ли анонимность | Да, режим запуска тот же → `navigator.webdriver === false`. Сессии площадок живут в профиле агента: вход один раз, «выйти везде» = удалить профиль |
| Почему не вынести окно за экран | `screenX/screenY` за пределами экрана — новый отпечаток; R-21 запрещает рост заметности. Свёрнутое окно + уже разрешённый спуф `visibilityState` — доказанный путь |
| Что теперь проверяется машинно | `security_audit` SEC-20: `forbidden_paths` (`Google\Chrome\User Data`) в коде браузерной ветки → `fail`; проверено негативным тестом |
| Чем платим | отдельный Chrome: +300–500 МБ памяти и своя копия сессий площадок |

Следствие для переноса: `substrate/llm/browser` реализуется как «свой профиль +
своё окно без фокуса», а вопрос Q-29 считается закрытым на уровне решения;
открытым остаётся только UX-деталь — спрашивать ли пользователя перед первым
запуском браузера (записано как Q-30).


- **Q-28. Нужен ли «журнал заметности»** — файл, куда при переносе браузерной
  ветки записывается каждый приём работы с сайтом (что подменяем, что читаем,
  какой парсер) и дата проверки площадки. Полезно, если площадка изменит
  поведение: сразу видно, что менялось. Решать при переносе `substrate/llm/browser`.

## 23. Решение по браузерной ветке (2026-10-27)

Пользователь: «с браузером оставляем старый вариант с отдельным профилем браузера,
он уже обкатан и работает как нужно».

| Что решено | Как записано |
|---|---|
| Профиль — отдельный (`%LOCALAPPDATA%\Godot_AI_Profile`), не браузер пользователя | `contract/browser_stealth.json` → `profile.mode = dedicated`, `user_profile_refused: true`, `decided` |
| Запуск — как в старом агенте: обычный процесс Chrome + attach через `debuggerAddress` | `launch.mode = plain_process_then_attach`, `selenium_launches_browser: false` |
| Спуф — только `visibilityState`/`hidden` и только по флагу сайта | `allowed_masking`, `sites.*.needs_visibility_spoof`, SEC-19 |
| Перенос — «как есть», без улучшений | R-08 «ported verbatim»; запрет улучшать закреплён в R-21 |
| Порядок | не первая волна: `browser/`, `parsers/`, `browser_backend.py` — отложены (Q-08), но не отменены; записано в `docs/parity.md` |
| Q-29 (кто запускает Chrome) | закрыт: агент запускает сам, как раньше |
| Q-30 (спрашивать ли перед первым запуском) | закрыт: поведение как в старом агенте, без лишнего диалога; если понадобится — добавим в настройки панели, не в код ветки |

Что это значит практически: при переносе браузерной ветки **запрещено** «починить»
её архитектуру, заменить selenium на чистый CDP, убрать профиль или поднять
`needs_visibility_spoof`. Допустимо только: перенос файлов в `substrate/llm/browser`,
удаление мёртвого кода, типизация ошибок по R-15 и разбиение по R-06. Любое
поведенческое отличие — запись в `docs/deviations.md`.


## 22. Решения сессии 9 (первый срез: `project_text.search`)

| Вопрос | Решение | Где |
|---|---|---|
| Где хранить корпус (Q-19) | В репозитории, `fixtures/corpus/project_text/search/`: 17 файлов, каждый < 20 КБ; воспроизводимость у следующего чата важнее размера | R-07, лист механики |
| Формат записи корпуса (Q-21) | Один JSON на кейс: `{id, tool, fixture, note, args, expect: {ok, result}}`; `manifest.json` — `schema_version`, дата, `reference.sha256`, sha256 кейсов; пути `<PROJECT>`/`res://`, абсолютных нет | `tools/snapshot_record.py`, `fixtures/corpus/project_text/search/` |
| Чем запускать тесты (Q-23) | `pytest>=8` в `[project.optional-dependencies] dev`, `python -m pytest`, `--import-mode=importlib` (44 одинаковых `tests/test_core.py`), вердикт для `selfcheck` даёт `tools/run_tests.py` | `pyproject.toml`, `tools/` |
| Что первично — код или корпус | Корпус. Все ожидания домена (`line`, `snippet`, `truncated`, окна контекста) взяты из записи эталона, а не из головы | `docs/PORTING.md` §1 |
| Где граница «шум vs доступ» | Шумовые каталоги (`.godot`, `node_modules`, `__pycache__`, скрытые) — домен поиска; аддоны, история и исходники агента — `kernel.paths.PathPolicy` | R-13, лист |
| Почему `.py` — «право», а не расширение | Иначе поиск читает исходник агента в обход developer mode; в срезе `.py` недоступен и это зафиксировано кейсом 009 | SEC-12/R-13, `PathPolicy.agent_py_allowed` |
| Можно ли считать «каркас» готовым | Нет. Написан по спецификации ADR-0003 ровно под `search`; после второго модуля ожидается переделка — это записано, а не замалчивается | лист, «Решения по ходу» |
| Что считается доказательством среза | `selfcheck` exit 0 + `reports/selfcheck/project_text.search.json` + вывод `probe`/MCP в `WORKLOG.md`; «посмотрел глазами» — нет | R-18, R-10 |

**Закрытые вопросы:** Q-19, Q-21, Q-23 (см. таблицу выше).

## 23. Открытые вопросы сессии 9

Нумерация: Q-28 (журнал заметности) и Q-29 (кто запускает Chrome) заняты
браузерной веткой в сессии 8 — поэтому новые вопросы среза начинаются с Q-31.

- **Q-31. `truncated=true` при попадании ровно в квоту.** Эталон выставляет флаг, как
  только счётчик достиг `max_results`, даже если других совпадений в проекте нет
  (кейс 006: одно совпадение, `truncated=true`). Сохранено ради паритета. Вопрос: чинить
  отдельной задачей после паритета (запись в `docs/deviations.md`, новый корпус-кейс) или
  оставить как есть, потому что клиент всё равно перезапрашивает с большей квотой.
- **Q-32. Нужен ли `tests/py/security/path_policy` уже сейчас.** SEC-12 закрыт кодом
  (`normalize_rel` + `realpath` в `disk_fs._resolve`, симлинки не разыменовываются), но
  атакующего набора (`..`, абсолютный путь, junction наружу, UNC, регистр) пока нет:
  для `effects="read"` R-20 его не требует. Кандидат на первый заход в
  `tests/py/security/` вместе с `project_text.read`.
## 24. Решения 2026-10-27 (аудит: minilich, git, порядок срезов)

1. **`minilich` и нейросетевая часть не переносятся.** Из старого плагина берём
   только детерминированную половину: индекс символов строит `code_intel.usages`
   сам, поиск — `project_text.search`. `substrate/llm/local/ml_index.py` и
   `ml_train.py` остаются заглушками и в план не входят; `minilich`-индексы из
   `fixtures/projects/rename/.agent_history/` удалены (их не читал ни код, ни тесты).
2. **Git.** В `D:\vajno\Godot\agent-rebuild` репозитория нет (проверено
   `git rev-parse`); git существует только внутри эталона
   `тест-плагина-ии/addons/Godot_agent`. Это осознанно: работа идёт в новой папке,
   чтобы не испортить старые файлы, из старого берутся только код и тесты, а всё
   переписывается на новую архитектуру. Поэтому аудит не опирается на диффы:
   состояние — файлы, sha256 в отчётах, `reports/selfcheck/*.json`.
3. **Порядок.** Перед частью A (мост редактора) идёт фаза 1 —
   `docs/porting/_start-prompt.context-and-rename.md`: починить `context.gather`
   (владелец составного `context`, иначе `editor_context` некуда вкладываться) и
   оформить `editing.symbol_rename` как модуль-вклад (решение пользователя:
   вариант «свой `MODULE` + тесты», не слияние со `write_preview`).
4. **Числа в отчётах — только из вывода команды.** Три отчёта подряд дали числа
   не из сдаваемого файла (43/14, «TypeError» вместо ложного отказа, «11 → 14» при
   фактических 13). Правило: число копируется из вывода (`pytest`, `--collect-only`,
   `selfcheck`), а не пересчитывается; мутация снимается с того файла, который сдан.
5. **`tests-map.md`.** Секция новых тестов переименована в «Приложение: новые
   тесты (не старые файлы)» с явной строкой: 168 старых файлов + 6 строк
   приложения = 174 строки в файле. Старые строки не удаляются, приложение растёт.
6. **Корпус редакторной механики - политика `live` (вариант A).** Для `editing.scene_ops`
   корпус снапшотов не снимается: эталон исполняется в GDScript редактора, Python-функции
   эталона нет (`_start-prompt.scene_ops_b1.md` §1.2). Решение закреплено данными, а не
   текстом: `ModuleSpec.corpus = "live"` + `CORPUS_POLICIES` в `kernel/module_spec.py`,
   решение `selfcheck` - чистая функция `corpus_readiness(...)` с положительным и
    отрицательным тестом; флаг без живого теста даёт `not_implemented`, а не `ok`.

## 25. C.24 D18/D19: resource transformed bytes (2026-11-02)

- Разрешение аудитора D18/D19 записано в листе `editing.resource_ops`, ADR-0017
  остаётся **proposed**. Module-local section/span producer → ровно один прежний
  `replace_raw` → общий raw-hash/WAL/rollback; editor и shared executor не меняются.
  Явный MODULE `apply` сохранён; registered public TOOLS остаются пустыми.
- Native oracle сравнивает настоящие загрузки/full stored-property projection,
  а не предположение по JSON. Native serializer bytes не объявляются паритетными:
  D18 сохраняет EOL/comments/UID/порядок и untouched spans. Для newline insertion
  dominant EOL с first-wins tie; existing record replacement берёт свой EOL.
- BOM и native-invalid semicolon comment с lone CR дают bounded refusal без
  эффекта. Comment-free lone CR не отвергается и проверен настоящим Godot.
  Byte input неоднозначен — отказ, не обход native loading и не новая deviation.
- Module policy проверяется также непосредственно перед повторным raw IO;
  dependency policy и common guard оба остаются. Мутационный red — настоящий
  execution assertion; первый single-style M3 survivor и первый full card-producer
  red сохраняются в dossier, а не заменяются рассказом об успешной проверке.
- Cohesion ceiling 8400 применяется ко всем areas, AREA_MAX 8000 неизменен.
  Текущие 8400 строк — предел, не разрешение на дальнейший рост или исключение.
  Стадии/ported/accepted и C.23 acceptance-блоки остаются за независимым аудитором.

## 26. Browser-runtime: ручная диагностика Qwen отложена пользователем (2026-11-04)

- Общий перенос плагина не отменяется из-за текущего Qwen recorded-site red.
- Qwen ответ/мысль/finished получены, но terminal FAILED вместо FINISHED;
  наблюдался net::ERR_ABORTED. Причина не установлена; невозможность исправления
  не доказана. Не подгонять корпус/ожидания и не отмечать live как пройденный.
- По решению пользователя ручной разбор причины переносится на время ПОСЛЕ
  полного переноса плагина. Сейчас это известная отложенная live-проблема.
- B.4 needs_live/deferred, mirror/submit не проверены, B.5 не выполнен;
  A/B.0–B.3 принятые границы и sealed D34 evidence сохраняются.
- Решение не меняет условия окончательной приёмки и не разрешает новые Chrome
  launches/мутации, profile/bootstrap/release/Arena/judge/server STATE работы.


## J1a/A1 новые STOP-блокеры (2026-11-13; не санкции)

После D58–D61 внешняя проекция трёх verbatim A1 targets показала actual security_audit fail/exit1: SEC-04 (`subprocess` вне engine/browser) и SEC-03 (строка369 `subprocess.run` для собственного taskkill распознаётся как listener). Checker не менялся, blanket exception запрещён; требуется независимое точечное AST/invariant/security-test/ADR решение или пересогласованное размещение. Дополнительно `_harness_source()` после relocation требует `python/agent_headless_validator.gd`: native primitive 1701 B/799ec9e26f43f65a отсутствует в15-file closure; projected default raises HeadlessValidationError. Explicit native harness работает, но не заменяет default parity. Вариант на рассмотрение: отдельная санкция на exact primitive resource, без Python alias/бизнес-логики. Досье answer-judge-J1-A1-20261113, REQUEST.md. Этап3/A1 STOP, не завершён/не принят.


### J1b / A1 фактическая проверка (2026-11-14)

D62/D63 implemented с exact-path/byte-offset AST-исключениями, B-1/PROC_ALLOWED сохранены; D64 exact1701 B/default+explicit green. Genuine red192 collected/135failed/57passed/0errors → 192 same-ID green, все прежние121 failure ID зелёные; native118×2/canonical118×2/0diff. Real Godot4.6:4 own-sandbox default-harness probes/8 engine processes/0diff/no source writes. Mutants:15 checker+2 D64 killed/0survivors, exact SHA/EOL restore/same-ID green. Full non-live×2:7400passed/2 historical WinError1314 skips; frozen230/API253/project288×2, gates×2 и post-resource gates0. Actual selfcheck assistant.judge fail/exit1 (missing MODULE), probe unknown_tool/exit1; context.ask ok/exit0,104unit/213corpus. Aliases0, MODULE/D59/D60/A2 не implemented. A1 reference mini-seal готовится, MODULE не ported, independent acceptance pending. Все rejected setup/invocation/scope records сохранены, native originals/NN/browser-live/production HTTP нетронуты.

Подэтап reference не закрывает historical verification.check/live fate или assistant.judge MODULE. Frozen230 membership сохранён: browser141 + B-1 AST72 + B217; D51 detector34 дополнительно в full/security/mutations. Мини-seal — integrity, не самостоятельная приёмка.
Следующее действие: После A1 mini-seal: A2 native cases/corpus×2 для scene/editing/actions; D60 genuine red exact-six caps перед переносом.


### J1 / A2 reference boundary (2026-11-15)

A2 reference-read/prepare проверен, не public MODULE. Six sources152941 B/EOL byte-exact; native214+supp1 ×2/canonical214+supp1 ×2/0diff, full snapshots no-write. Genuine A2220/221 red → same221green, D6013/26 red → same26green; restored all249green. 6 A2+4 D60 mutants killed/0final survivors, exact bytes/SHA/LF/CRLF restore/same-ID green. Первый ambiguity survivor сохранён: wrongly named old negative-case не создавал candidates; gap закрыт новым genuine native supplement×2 и теми же mutant bytes, frozen214 не переписан. Full non-live7649passed ×2 + ровно два historical WinError1314 skips, no added skips/xfails; collected7651 и executed IDs/order exact. Frozen230/API253/project288 ×2, все288 manifest IDs. Gates/security ×2 green. Real Godot4.6:4 native/canonical reference probes/8 processes, default harness,0diff/no source writes/owned validation leftovers0; это headless structural validation, не semantic editor apply/rollback и не public judge probes. Actual selfcheck assistant.judge fail/exit1 (missing MODULE) ×2; actual probe judge unknown_tool/exit1 ×2. Actual context.ask selfcheck ok/exit0 ×2,104unit/213corpus. D60 exact-six caps реализованы minimal two-insertion checker delta, old constants/caps сохранены; D59/A3/B/+15 aliases/MODULE/public corpus не реализованы. Rejected baseline assumptions, freeze path, pytest basetemp setup, outer120s partial canonical capture, singular collected-item receipt, double-q collect verbosity и initial survivor сохранены, не засчитаны как successful evidence. A1 accepted record read-only; mini-seal/ZIP фиксируют integrity, не самостоятельную приёмку.

Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/answer-judge-J1-A2-20261114/
Следующее действие: После A2 mini-seal/ZIP: A3 symbol_refactor native cases/observations ×2 до missing-code red; затем B/D59/adapter/MODULE.


### J1 public judge — final submitted parity (2026-11-15)

J1 полностью реализован и передаётся на независимый аудит: public assistant.judge/judge, read/idempotent, fs+librarian, strict input/result envelope, domain pure/app7. Genuine native74×2 → actual build_agent→agent.call74×2/0diff; final ordinary public corpus74×2/0diff. Actual selfcheck assistant.judge ok/exit0×2 (8unit/74corpus), context.ask ok/exit0×2 (104/213). Final full7923collected/7921passed×2, exact ordered once-only IDs, только два исторических symlink WinError1314 gaps. Frozen230/API253/project288×2, все288 IDs, security/layers/limits/contract×2 green. Четыре actual CLI probes: answer0/invalid_input1/denied1/no-write0; owned state only, no project writes. Final185 new tests green;14 current-submitted mutants killed/0survivors, byte/SHA/LF/CRLF restores/same-ID green. Fifteen Python references+GD harness436437 B byte-exact; part1CRLF824; old35 binding prefix exact,total50/rawLF84. D59/D65–D69 только в санкционированных границах. Native parser/quartet/parser_base/security/check_limits и shared snapshot/selfcheck/generator unchanged. A1/A2/A3 full readback/seal/archive pins exact, только уже раскрытая A1 empty-file inode cohort1430. Rejected invocations/full failures/sample-write defect и initial A2 survivor не удалены; D68 genuine2red→same2green, D69 genuine52fail→same-ID green, fixture isolation repaired only in new B scope, no foreign-parent adoption. Один поздний full run дал importlib source_to_code MemoryError: cause unestablished; unchanged node alone exit0, fresh exclusive full7921pass/2oldskips exit0; failed run retained, not counted. Полный final ZIP включает byte-exact7 mini-seals/8 prior archives, включая rejected incomplete A1 ZIP; их наличие не означает принятия rejected artifacts. Prior real Godot reference probes retained; no public apply/rollback/editor semantic/live/NN/browser/HTTP claim. MODULE_ready=true; independent_acceptance=false, audit pending.

Открытые browser-live/NN/STATE/editor долги не расширялись. Judge прогнозирует действие в памяти, не исполняет и не подтверждает применённый результат. Actual final reports расположены в external dossier; pre-existing ROOT selfcheck reports сохранены.
