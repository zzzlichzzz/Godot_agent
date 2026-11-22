# Мандат T-F: панель↔сервер (27 маршрутов), godot_agent_server.exe, live-дефект observer

Роль: ты — портёр (исполнитель) пакета T-F проекта godot_agent. Работаешь
автономно: STOP-ы решаешь сам (измерить → сверить с нативом → минимальное
решение → D-запись в docs/porting/deviations.md → продолжать), как делегировал
пользователь в мандате T1 (§2). Формулировки «принято аудитором», «parity»,
«released» запрещены — приёмку выполняет аудитор после тебя.

## §0. Контекст и пины

T1 ПРИНЯТ АУДИТОРОМ С УСЛОВИЕМ (2026-11-22, вердикт в WORKLOG): пакеты
T-A…T-E приняты как reference. Условие приёмки — данный пакет T-F.
Всё запечатанное неизменно; прежние seals/ZIP/досье не переписываются.

Пины на момент выдачи (проверь prefix-assert'ом, не верь на слово):
- Рабочий WORKLOG: D:\vajno\Godot\agent-rebuild\addons\godot_agent\docs\WORKLOG.md
  = 1 082 333 B, sha16 6c32e0b79a2e88f7, хвост CRLF. Append-only, CRLF,
  каждая запись скриптом с prefix-assert.
- Git-репозиторий установленной копии: ветка experiment, HEAD 42edc07
  («полная замена нативного агента портированной версией»), status чист.
- Артефакты финальной приёмки T1 (читай, не меняй):
  C:\Users\Lich\AppData\Local\Temp\c8_audit\t1-final-audit-20261122\
  — a10_routes.json (доказанный список 27 необслуженных маршрутов),
  a7b_summary.json (живые сокеты HTTP), a5b_full_*.junit.xml (регресс ×2).
- Полный регресс-состав для сверки: 8286 = 8281 passed + 3 failed
  (test_paths_preview[004/005/009], внешний .uid-дрейф) + 2 skip
  (WinError1314) ×2.

## §0.1. Пути (карта проекта)

- Рабочее дерево — ЗДЕСЬ РАБОТАЕШЬ ТЫ:
  D:\vajno\Godot\agent-rebuild\addons\godot_agent
- Натив-источник истины (заморожен, для сверок семантики):
  D:\vajno\Godot\agent-backups\20261122\godot_agent_native_original\godot_agent
- Дубль натива с git-историей (ветка experiment):
  D:\vajno\Godot\agent-backups\20261122\godot_agent_native_moved\godot_agent
- Установленный агент + git-репо (GitHub origin zzzlichzzz/Godot_agent):
  D:\vajno\Godot\тест-плагина-ии\addons\godot_agent
  ЗАПРЕЩЕНО: любые git-действия (add/commit/push/checkout) и любая запись
  в эту копию — git-домен пользователя. УРОК ИНЦИДЕНТА №3: robocopy в
  СУЩЕСТВУЮЩИЙ каталог = слияние деревьев; никогда не синхронизируй копии
  копированием поверх — при необходимости сообщи аудитору/пользователю.
- ПОЧЕМУ работаешь в рабочей копии (agent-rebuild), а не в git-копии:
  вся дисциплина переноса живёт здесь — непрерывный WORKLOG с
  prefix-цепочкой пинов, досье, RULES.md; все принятые срезы (K1c,
  T-A…T-E) исполнялись здесь. Git-копия — снимок для GitHub пользователя:
  код идентичен рабочей копии на момент свопа, отличается только тремя
  аудиторскими записями в WORKLOG (коммит зафиксировал состояние до них).
  Синхронизация принятого результата T-F в git-репозиторий — задача
  аудитора ПОСЛЕ приёмки; исполнителю в git не входить.
- Игровой проект, где агент установлен: D:\vajno\Godot\тест-плагина-ии
- Godot: D:\vajno\Godot\Godot v4.6.3\ (console.exe; точное имя файла найди
  в каталоге) — для --check-only и headless-проб.
- Python: %LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe (флаги -B -X utf8)
- Досье: C:\Users\Lich\AppData\Local\Temp\opencode\c8_audit\<имя>\ (+ -postseal\)
- Ключи/состояние: %APPDATA%\godot_agent — живые провайдеры НЕ вызывать.
- Ключевые документы: docs\WORKLOG.md, docs\PROGRESS.md, docs\porting\
  (мандаты _start-prompt.*, parity.md, deviations.md — нумерация D дошла
  до D89, продолжай с D90), RULES.md.

## §1. Состав T-F

### T-F.1 Маршруты панель↔сервер (главная задача)

Панель (editor/native/*.gd, байт-точная, пакет T-D) адресует 51 URL-константу
через agent_server.gd; HTTP-канал обслуживает только 33; 27 отсутствуют (404).
Список (совпадает с a10_routes.json):

/chat/confirm_action, /chat/editor_action/result, /chat/live_input,
/chat/runtime_check/bind, /chat/runtime_check/result,
/chat/runtime_inspect/result, /librarian/query, /minilich/github_fetch,
/minilich/set, /minilich/status, /project/api_cache_status,
/project/check_log, /project/refactor/file/apply,
/project/refactor/file/post_move_sync, /project/refactor/file/preview,
/project/send_log_errors, /project/split_gd/apply, /project/split_gd/plan,
/project/split_gd/scan, /project/update_api_cache,
/scene/refactor/node/apply, /scene/refactor/node/delete/apply,
/scene/refactor/node/delete/preview, /scene/refactor/node/preview,
/scene/refactor/node/reparent/apply, /scene/refactor/node/reparent/preview,
/server/shutdown

Правила:
- Панель заморожена — адаптируется СЕРВЕР, не GDScript. Ни одного изменения
  .gd ради маршрутов.
- Семантика каждого маршрута берётся из нативного main.py (304 431 B,
  натив-источник; в rebuild он намеренно не перенесён — «семантический
  образец»). Извлеки точную обработку: payload, коды ответов, побочные
  эффекты, порядок операций — и адаптируй на архитектуру rebuild
  (python/channels/http/app.py + register_chat_routes + ProjectAuth +
  agent.call/tool-инструменты).
- /chat/confirm_action — КРИТИЧНО (кнопка подтверждения плана панели).
  Смотри agent_panel.gd байт-точно: что именно отправляет и что ждёт в
  ответе. В rebuild есть /chat/confirm (plan_id+digest+approved,
  requires_confirmation, USER_CONFIRMED, WAL). Сделай честную адаптацию
  native-контракта confirm_action поверх rebuild-петли; «тупой алиас»
  запрещён, если payload-контракты различаются — нужны тесты ОБОИХ
  контрактов. Ослабление подтверждений недопустимо.
- /minilich/* — нейросети исключены (F0): fail-closed ответы
  {"ok":false,"kind":"unavailable", ...} с честным текстом (панель покажет
  сообщение), имитация успеха запрещена. D-запись.
- /librarian/query — librarian принят (F1/D51): маршрут оборачивает
  существующий публичный вызов (сверь с нативом, что звал native).
- /project/split_gd/*, /project/refactor/file/*, /scene/refactor/node/* —
  оборачивают байт-точные godot_tools (T-A). ЛЮБАЯ запись в проект — только
  через write-петлю (plan → confirm → WAL) или уже санкционированных
  исполнителей; прямые записи из HTTP-слоя запрещены.
- /server/shutdown — native main.py L4861 server_shutdown: корректное
  завершение listener + удаление endpoint-файла (сейчас 500).
- Auth: все новые маршруты за ProjectAuth (X-Agent-Token), запрет эскалации
  как в /init (allow_addons/allow_self_edit → 403), проверка Host сохраняется.
- Размещение кода: новый python/channels/http/routes_project.py (+ при
  необходимости ещё один файл; каждый ≤400 строк, лимит check_limits) —
  rebuild-authored. Байт-точные python/substrate/assistant/server/*.py
  (T-C) НЕ изменять — только регистрация из app.py.
- Постоянный контракт-тест: tests/py/.../test_panel_route_contract.py —
  парсит 51 URL-константу из editor/native/agent_server.gd и требует, чтобы
  каждая обслуживалась приложением (сейчас 27 red → после 51/51 green).
  Это превращает находку приёмки в постоянную защиту от регресса.
- red-before-code на каждый маршрут: тест падает (404/отсутствие) →
  реализация → тот же тест green ×2 (paired same-ID).

### T-F.2 godot_agent_server.exe (запуск панели «одним кликом»)

Собери godot_agent_server.exe (PyInstaller) вокруг python.channels.http и
размести внутри аддона по пути, который ищет байт-точный
agent_server_link.gd. Порядок:
- Сначала прочитай agent_server_link.gd (_launch_server_process): какие
  ИМЕННО пути он перебирает (editor/native/python/dist/, python/dist/,
  кэш SERVER_PATH_CACHE, override editor/native/server_path.txt) и какие
  аргументы передаёт exe. exe обязан принять родные аргументы панели; при
  расхождении с argparse channels.http (--project/--state/--port) сделай
  тонкую обёртку-транслятор аргументов (rebuild-authored), а не правку .gd.
- Токен: панель читает user://godot_agent_token.txt (user-data dir
  ПРОЕКТА, напр. %APPDATA%\Godot\app_userdata\<имя проекта>\).
  bootstrap сервера должен создавать/читать токен через байт-точный
  server_auth.py (binding user_data_dir+token, D85) — сверись с нативным
  main.py, как токен создавался при старте.
- Preflight: если PyInstaller не установлен — STOP: запроси у пользователя
  разрешение на `pip install pyinstaller` (или offline-колесо). Без явного
  разрешения в чате сеть не использовать.
- Офлайн-проверка exe: поднять на свободном порту; /health 200; auth
  403/403/200; один полный цикл /tools/call plan → write_apply(denied) →
  confirm(COMMITTED, физическая запись в копии проекта) → rollback
  (ROLLED_BACK, физически точно) → /server/shutdown → процесс завершён,
  endpoint-файл удалён. Всё ×2.
- Антивирус/SmartScreen может предупреждать о новом exe — ожидаемо,
  отметь в отчёте.

### T-F.3 observer.gd (live-дефект приёмки)

editor/core/resource_publication_observer.gd (370 B, rebuild-only обёртка):
extends относительный не резолвится — Godot 4.6.3 --check-only даёт
«Parse Error: Could not resolve super class path
"res://addons/godot_agent/editor/core/agent_resource_executor.gd"»
(реальный файл в editor/native/agent_resource_executor.gd, 32 576 B).
- Почини путь extends (на res://addons/godot_agent/editor/native/...),
  минимальной правкой; D90-запись (файл rebuild-authored, правка разрешена,
  задокументируй).
- red-before-code: tests/py/live/test_bridge_live.py сейчас red (broken:
  observer) → тот же тест green ×2; Godot --check-only green.
- После любых Godot-проб удаляй появившиеся посторонние *.uid в fixtures/
  (внешний дрейф; дерево должно соответствовать T-E), фиксируй в WORKLOG.

### T-F.4 (опционально, только по отдельной просьбе пользователя)

Восстановление 0-байтовых файлов досье из ZIP по seals-allowlist
(T-A 1435, T-B 3157 — класс pytest-temp). Без просьбы — не делать.

## §2. Инварианты

- Сеть: НЕТ. Единственное исключение — явное пользовательское разрешение
  на pip install pyinstaller в чате (запись в WORKLOG).
- Ключи/живые провайдеры: НЕТ. NN (minilich ml_*), doh.py, n8n исключены
  навсегда (F0).
- Запечатанные досье, seals, ZIP и байт-точные файлы принятых срезов
  (api-core, routing-runtime, project-core, engine-cache, librarian F1/D51,
  J1, K1c, T-A…T-E) — не изменять. Мандаты docs/porting/_start-prompt.* —
  не изменять.
- git установленной копии — не трогать (домен пользователя).
- Инциденты: измерить → инцидент-запись в WORKLOG → минимальное безопасное
  восстановление по прецедентам (восстановление пустых файлов по
  seals-allowlist разрешено) → продолжать.

## §3. Дисциплина

- red-before-code на каждый новый маршрут/обёртку/фикс; paired same-ID
  green ×2 (два независимых прогона, идентичные списки тестов).
- Мутации ≥3 с точным восстановлением bytes/SHA/EOL. Минимум: (1) обход
  auth на новом маршруте (должен быть красным — ProjectAuth обязателен);
  (2) confirm_action без/с неверным digest (отказ обязателен); (3) прямой
  обход WAL из нового проектного маршрута (запрещён — тест ловит).
- Полный регресс ×2: состав и ordered IDs == 8286 (8281 pass + 2
  WinError1314 skip) + твои новые тесты. Если test_paths_preview
  [004/005/009] падают из-за .uid-дрейва в fixtures — удали посторонние
  .uid (восстановление дерева T-E, разрешено, опиши) и перегони; НЕ
  «чинись» под дрейф изменением эталонов.
- Гейты ×2: security_audit, lint_arch, check_limits, gen_contract --check.
- Selfcheck ×2: assistant.chat, context.ask, assistant.judge,
  assistant.write, editing.write_apply, editing.rollback,
  scene_model.scene_deps (для assistant.chat corpus — offline-хук K1c +
  K1C_OFFLINE=1, как в K1c-досье).
- Новые файлы ≤400 строк (check_limits); статические contract-записи
  обновляй через gen_contract, не руками.
- D-записи с D90 в docs/porting/deviations.md; WORKLOG — append-only,
  CRLF, prefix-assert на текущий размер/хэш.
- Seal ПОСЛЕДНИМ: досье C:\Users\Lich\AppData\Local\Temp\opencode\c8_audit\tf-<дата>\
  (evidence: все прогоны, красные/зелёные, диффы, перед/после),
  SHA256-final.json в самом конце; затем postseal-папка: ZIP +
  publication.json + полная побайтовая сверка ZIP-членов (bad=0).
- В финальном отчёте: что сделано, что сознательно не сделано, границы,
  номера D-записей, пины. Короткими сообщениями.

## §4. Приёмка

После твоего финала аудитор проведёт независимую приёмку T-F: ревизия
D-записей против натива, собственные прогоны (контракт 51/51, живые сокеты,
exe-цикл, observer --check-only, регресс), вердикт. Не объявляй приёмку сам.

## §5. Чек-лист

1. §0: пины пересчитаны prefix-assert'ом; tree-identity рабочей копии.
2. T-F.1: 27 маршрутов red→green ×2; контракт-тест 51/51; auth на всех
   новых маршрутах; NN-маршруты fail-closed; запись только через WAL.
3. T-F.2: exe собран (или STOP на pip), аргументы/токен сверены с
   agent_server_link.gd, офлайн-цикл ×2 включая /server/shutdown.
4. T-F.3: observer D90, live-тест red→green ×2, --check-only green.
5. Мутации ≥3 убиты, восстановления точны.
6. Регресс ×2 + гейты ×2 + selfcheck ×2 — зелёные, ID точные.
7. D-записи (D90+) + WORKLOG append-only.
8. Seal LAST + postseal ZIP + побайтовая сверка.
9. Финальный отчёт пользователю (коротко, честно).



