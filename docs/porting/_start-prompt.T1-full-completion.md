# Мандат T1 — полное завершение переноса godot_agent до работающей версии (исполнитель работает автономно)

Класс: жёсткий по дисциплине, СВОБОДНЫЙ по решениям. Приёмка: независимый аудит после полного завершения. Промежуточные приёмки не требуются; отчёт пользователю после каждого пакета — краткий, без ожидания одобрения для продолжения.

ГЛАВНОЕ НОВОВВЕДЕНИЕ (делегирование пользователя, 2026-11-20): STOP-ы разрешаются ИСПОЛНИТЕЛЕМ самостоятельно, без ожидания санкций аудтора/пользователя. Источник истины при любом конфликте — нативный проект D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent (его байты, поведение, тесты). Механизм — §2. Жёсткие инварианты (§3) остаются не делегируемыми.

## §0 Предусловия (пины на момент выдачи)
- Репо D:\vajno\Godot\agent-rebuild\addons\godot_agent; WORKLOG 1 032 789 B sha16 2494134bcd6b371f (хвост CRLF; один исторический bare-LF шов перед записью приёмки K1c — не трогать).
- Принято и заморожено: librarian-квартет byte-exact corrected-native (librarian 97 676 340b5dd2, ml_project_index 65 753 2f7694a9, ml_data 32 324 e13d5680, gd_semantic_parser 15 723 bf35dcea); замыкание judge 16 файлов 436 437 B (A1/A2/A3/B); parsers byte-exact (parser_base 198 211 7b2ce9f1); api-слой byte-exact (substrate/llm/api + backends/api_backend 91 906 93d22fb5); context.ask MODULE1; assistant.judge read-only; assistant.chat/CLI (K1, принят 2026-11-20, WORKLOG 1 032 789).
- Чекеры: tools/security_audit.py 21 639 d9063015 (D62/D63 внутри), tools/check_limits.py 6 933 05f53e40 (D60), bootstrap 8 592 d6d933ee (D65/D72), registry 5 180 b7757da1 (D67), runtime_bindings 4 518 f5c456ec — ровно 50 алиасов, LF84.
- Воспроизведение corpus-полосы: offline-хук досье K1c (offline_hook/sitecustomize.py, K1C_OFFLINE=1, только для snapshot_diff.py+assistant.chat) — задокументированная процедура, сохраняется как образец для новых offline-корпусов.
## §1 Объём работ — пять пакетов, каждый завершается мини-seal + postseal ZIP (порядок свободный, T-E последним)
- **T-A godot_tools добор (byte-exact, ~219 КБ)**: split_gd 63 421, split_refactor 44 114, node_refactor 46 881, arch_map 22 088, gather_context 17 226, gd_functions 3 367. function_card 37 878 — ранее исключён (D48): вернуть ТОЛЬКО если нативная петля/инструменты реально требуют; решение исполнителя с D-записью. Источники кейсов — нативные тесты (test_split_gd, test_rename_symbol*, test_node_refactor*, test_high_level_*). Размещение — по прецеденту J1 (substrate/<area>/ + биндинг-алиасы, токен-правки пин-тестов по D50).
- **T-B write-петля (новый код по нативной семантике)**: plan → подтверждение → исполнение → откат. Образцы семантики: нативный main.py (chat L2624, confirm_action L2812, plan_*/rollback* маршруты), agent_bridge (cmd-обработчики). Исполнители записи УЖЕ портированы байт-точно (file_refactor, scene_actions, resource_actions, transaction_actions, high_level_actions, node_refactor после T-A). Новый MODULE (assistant.write или расширение assistant.chat) с effects write; нативное поведение подтверждения — образец; физический no-unexpected-write тест обязателен.
- **T-C каналы (~205 КБ byte-exact + адаптация)**: HTTP-сервер — server/ (chat_routes 77 333, server_state 39 732, log_reader 13 864, server_auth 12 793, dashboard 10 015, port_guard 7 163) + Python-сторона editor-link; MCP — tools/godot_agent_mcp 32 733 поверх rebuild-агента; нативный main.py 304 431 и selfcheck.py 234 772 — ТОЛЬКО семантический образец (не байт-порт: rebuild имеет собственные tools/selfcheck и channels/cli). agent_bridge 142 171 — образец CLI-харнесса; если переносится — документировать адаптацию. Сеть: привязка к 127.0.0.1, SEC-02/PROC_ALLOWED не ослаблять (файл-scoped расширения по D62-шаблону).
- **T-D GDScript UI/plugin (byte-exact + минимальная адаптация, ~1,11 МБ)**: 42 .gd (agent_panel×5+панель, agent_start_screen 203 876, agent_locale 86 138, agent_chat_view 45 595, executors: scene/resource/project_settings, agent_server/agent_server_link, entry/context-меню, карточки, theme, updater, plugin_universal), plugin.cfg, agent_panel.tscn + 5 карточных .tscn, 3 reference_scenes minilich. Каждое изменённое байтовое место (пути res://, имя аддона, ссылки на python-сервер/CLI) — документируется в D-записи. GD-чекеры (SEC-05) — файл-scoped fail-closed расширения по D51/D62-шаблону (red/green матрица, ADR).
- **T-E финальная интеграция**: все новые модули/каналы в bootstrap/registry/контракт; полный регресс ×2 с exact ordered IDs; gates ×2 + security ×2; docs (parity.md, README, PROGRESS, deviations, WORKLOG, porting/*.md); финальный seal LAST + ZIP.
## §2 Постоянное делегирование — замена STOP-санкций (ядро мандата)
При любом конфликте (frozen bytes, guard-тесты, чекеры/лимиты, размещение, отсутствующий ресурс, порядок стадий, envelope/контракты, имя модуля) исполнитель решает САМ:
1. Измерить противоречие (bytes/sha256/EOL/строки/точный тест).
2. Свериться с нативным проектом как источником истины: что натив делает, какими байтами, где вызывается.
3. Выбрать МИНИМАЛЬНОЕ решение, сохраняющее семантику натива и security-свойства.
4. Оформить D-запись (docs/deviations.md + append-only WORKLOG): противоречие с измерениями, нативное доказательство (пины/строки), решение с точным перечнем правок, red-before-code (репродукция красного тем же пайплайном), green same-ID, ≥1 мутант, строка в ADR.
5. Продолжать без ожидания.
Прецедентные шаблоны (копировать их структуру): D50 (token-edit пин-теста), D51/D62 (fail-closed file-scoped checker-исключение с byte-offset точности), D59 (runtime_parent child-ключи), D60 (check_limits exact-path список), D63 (file-pin импорта), D65/D67/D72 (bootstrap/registry/композиция), D72/D73 (object-result контракта). Записи — вместо разговоров; никаких устных самосанкций.

## §3 Жёсткие инварианты (не делегируются — при конфликте STOP пользователю)
- Реальная сеть/реальные ключи в тестах запрещены. Live-дым только при явных GODOT_AGENT_* env от пользователя, отдельной записью, ключи не хранить в репо/досье. По умолчанию всё offline (SSE-фикстуры, offline-хук).
- NN-файлы minilich (ml_fix 21 319, ml_github 8 619, ml_model 15 124, ml_tokenizer 4 695, ml_train 57 640, весовой __init__ 14 476), doh.py 16 938, n8n/scripts — исключены; пересмотр только явной инструкцией пользователя.
- Принятые seals/досье не переписываются; frozen-байты принятых портов не изменяются (токен-правки пин-тестов — по шаблону D50 с записью).
- SEC-гейты не ослабляются глобально; только file-scoped fail-closed (D51/D62-шаблон, обязательная red/green матрица и мутант).
- Нативные исходники при переносе байт-неизменны (исключения: уже фиксированный corrected-native quartet; документированная минимальная адаптация GDScript/сцен в T-D).
- Слово «принято аудитором» исполнителю запрещено; допустимо «завершено, подано на независимый аудит».

## §4 Дисциплина (неизменна)
red-before-code на каждом новом поведении; мутации ≥3 на пакет (exact restore, same-ID green, surviving фиксируется честно); эталонные прогоны ×2 byte-equal; полный регресс ×2 с exact ordered IDs (актуальный базовый — из последнего принятого среза; расти по мере добавления тестов); gates ×2 + security ×2; WORKLOG append-only CRLF; мини-seal LAST в каждом пакете + postseal ZIP с полной побайтовой проверкой; rejected-попытки сохраняются; инциденты %TEMP%-очистки — восстановление по allowlist без перезаписи + запись.

## §5 Приёмка (аудитор, после T-E)
tree-identity каждого пакета; ревизия ВСЕХ D-записей против натива (выборочно глубоко); самостоятельные прогоны аудитора (selfcheck, pytest, probe/CLI, HTTP/MCP локально); реверификация seals/ZIP побайтно; вердикт по каждому пакету и финальный. Аудитор не выдаёт промежуточных санкций — только финальные вердикты.

## §6 Чек-лист полного завершения
(а) каждый файл из §1 перенесён byte-exact ИЛИ документированно исключён/адаптирован (D-запись); (б) CLI: chat работает end-to-end, write-петля с подтверждением и откатом; (в) HTTP-сервер и MCP поднимаются локально и отвечают; (г) GDScript UI включается в Godot 4.6 (проверка чем доступно: headless/parse/структура); (д) полный регресс ×2 зелёный, gates/security ×2; (е) все seals/ZIP bad=0; (ж) docs/parity доведены до реальности; (з) итоговый отчёт пользователю: что работает, как запустить, что осталось за пределами.

Конец мандата.
