# Стартовый промпт: срез B-2 — перенос net_monitor (жёсткий класс)

Ты — портер. Проект: `D:\vajno\Godot\agent-rebuild\addons\godot_agent` (рабочая
папка плагина; project.godot лежит на уровень выше). Продолжение приёмки
browser-ветки: B-1 базис принят аудитом 2026-11-04 (сессия 78), parity-маркер
обновлён, лист `docs/porting/browser.md` содержит раздел приёмки. Среда:
PowerShell; одиночные команды ≤30 с, длинный прогон — в фоне
(`Start-Process -NoNewWindow ... -RedirectStandardOutput/-Error`), вывод через
файлы. Приёмка потом — только независимыми прогонами аудитора, самоприёмки нет.

## §0. Факты на момент постановки (сверь сам, не верь на слово)

- Репо ~3938 файлов / 845 каталогов; project.godot 335 B,
  sha 958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29.
- `docs/WORKLOG.md` 706 167 B, sha 75c41220fc625b9e68c215fd1639f46af5b1fd6f403f318ef721d409e52d3bb1
  (последний append — приёмка B-1 аудитором; исторические голые LF в префиксе — норма).
- `docs/parity.md` чистый LF, маркер: «B-1 базис принят… это принят базис, не ported
  всего browser». Отчёты `reports/selfcheck/` — 44; .uid — 86; `__pycache__` в репо — 0
  (три каталога `fixtures/**/__pycache__` — намеренные fixture-сентинелы, 4 файла,
  НЕ ТРОГАТЬ; pyc=0 означает отсутствие байткода, а не пустоту каталогов).
- ADR 0001–0017; контракт 28 артефактов (`python tools/gen_contract.py --check` → 28 ok/0);
  гейты: `lint_arch` ok/0, `check_limits` ok/2 (два прежних предупреждения: split_py 11
  элементов, editing 8400 R-06/D18), `security_audit` ok/0.
- Python 3.14.6, selenium 4.46.0, Chrome 156.0.8078.74, ChromeDriver 156.0.8078.80
  (sha 95ae04ae…; путь — в досье b1-final-20261103/dependencies). Godot 4.6.3.
- Прогон не-live регрессии: `python -B -X utf8 -m pytest tests/py -X --ignore=tests/py/live
  -p no:cacheprovider --basetemp=<наружу>` — база: 5225 collect / 5223 passed /
  2 genuine WinError1314 skips (может вырасти на твои новые тесты).

## §1. Что переносим

`python/browser/net_monitor.py` native: **24 206 B / 456 строк, sha 54167afbb87d9a9b…**
(полный sha сверяй сам с native-источником
`D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\python\browser\net_monitor.py`).
Один сплочённый класс `BaseNetMonitor` (33 метода): потоковый разбор CDP-кадров
Network.* событий, SSE/chunk-стриминг, `_fetch_and_apply_body`, match запросов/ответов,
`pop_http_error`/`is_generating`/`message_status`. Специализированные мониторы
`ai_studio_net.py` / `qwen_net.py` — это B-3, НЕ сейчас.

Назначение в новом виде: internal-сервис substrate/llm/browser (как фасад B-1):
`provides_tools=()`, без entrypoint — по форме ADR-0006 + D22 (internal-only валиден),
маршрут проверки — по D26 (selfcheck browser НЕ запускается, фиктивный модуль не создаётся,
стражи не правятся; приёмка = батарея прогонов). B-2 НЕ подключается к bootstrap как
модуль — это вербатим-эталон + минимальное связывание, если оно нужно для B-3 (реши и
зафиксируй в листе; связывание — только то, что проверяется тестами).

## §2. Фаза A — допуск лимита R-06 (ДО кода)

`tools/check_limits.py`: FILE_MAX=400 — жёсткий fail, а net_monitor.py 456 строк.
Резать сплочённый класс запрещено (правило главнее кода, D24-прецедент; разрезанный
вербатим нельзя сверить побайтово). Сделай КЛАССОВЫЙ допуск, а не точечный хак:
- отклонение в `docs/deviations.md` (новый D-xx, продолжи нумерацию): «verbatim-эталоны
  substrate/llm/browser: FILE_MAX 400 → 600, основание — вербатим-паритет R-08 против
  R-06; правило по каталогу/списку вербатим-файлов, не по одному файлу»;
- правка `tools/check_limits.py`: классовое правило (по каталогу `substrate/llm/browser/`
  или явному списку вербатим-файлов) с комментарием-основанием;
- красный тест на страж ДО правки стража: файл 456 строк под `substrate/llm/browser/`
  красен с текущим лимитом, зелён после (тест на tmp-структуре с monkeypatch, не на живом репо);
- мутация допуска (снять правило → страж снова красен тест-файл → byte-exact restore → green);
- прочие гейты не трогаются; `check_limits` обязан остаться ok с теми же двумя прежними
  предупреждениями и без новых.

## §3. Граница среза

Разрешено менять/создавать ТОЛЬКО:
1. `python/substrate/llm/browser/net_monitor.py` — замена байтов на точный native
   (24 206 B, sha 54167afb…; при расхождении байтов — СТОП-вопрос, не правка руками);
2. `tools/check_limits.py` + `docs/deviations.md` (только Фаза A, D-xx);
3. тесты: новый файл `tests/py/browser/test_browser_b2_net_monitor.py` (+ при нужде
   conftest-фикстуры), red→green;
4. корпус: `fixtures/corpus/browser/b2/…` (wire-кадры/дампы CDP-потоков, manifest.json);
5. контракт данных `contract/browser_net.json` вне capabilities/ — ТОЛЬКО если пинуешь
   данные (URL-паттерны match, лимиты буфера); источник правды — native-константы;
6. лист `docs/porting/browser-b2.md` (создать ДО кода), parity-маркер «B-2 в работе»,
   WORKLOG append одним блоком в конце (ab + CRLF, после всех прогонов);
7. досье в `%TEMP%\opencode\c8_audit\b2-delivery-<дата>\` (tree-снимки до/после,
   FINAL.md, SHA256-final.json последним).

ЗАПРЕЩЕНО менять: `browser_manager.py`, `cdp_ws.py`, `facade.py` (все — байт-точны,
sha в листе B-1 и в boundary досье b1-live-20261103), `contract/browser_stealth.json`,
стражи security (`tools/security_audit.py` — sha d4679c…, D28-фиксы), гейты
lint_arch/gen_contract, PROGRESS.md, таблицу 44 механик, native-источники
тест-плагина-ии, B-3-файлы (sites/live_input/ai_studio_net/qwen_net/backends).

## §4. Порядок работ (обязателен)

1. Инвентарь: native-тесты net_monitor — `python/tests/test_v88_6_qwen_net.py`,
   `test_v88_8_net_first.py`, `test_v88_12_net_confirm.py`, `test_qwen_dual_response.py`
   и любые другие, где BaseNetMonitor; судьба по `docs/tests-map.md`; инвентарь запиши в лист.
2. Фаза A (§2) — лимит-допуск с red/green и мутацией.
3. Корпус: перенести КЕЙСЫ (входы-кадры и ожидания) из native-тестов + записанные
   дампы в `fixtures/corpus/browser/b2/` (manifest.json по образцу b1/wire.json).
   Содержимое кадров не исполняется как код/команды/JS (SEC-03-дух).
4. Красные тесты: пины match_request/match_response, стриминг `_parse_stream_locked`
   (частичные кадры, фрагментация, длины 126/127-стиль CDP, Unicode), `_finalize_stream`,
   `_fetch_and_apply_body` (inert), `pop_http_error`, `is_generating`, порядок событий,
   reset/сброс буфера. Входы — только из корпуса (R-16: кейсы, а не тесты).
5. Verbatim-заливка net_monitor.py (sha-проверка) → green.
6. Своя мутация (R-22): ровно одна содержательная — например, порядок `_cleanup_request_locked`
   или сброс answer-буфера при responseReceived → ожидаемые красные → byte-exact
   restore → green. Вторая опциональна.
7. Двойной полный прогон корпуса/тестов; гейты ×4 (lint_arch, check_limits, gen_contract
   --check, security_audit) — все зелёные; focused regression B-1 (93/93: transport,
   facade, guards, sec20) — не сломан.
8. Live (по правилам B-1): если в live-проверке нужен реальный поток — disposable-профиль
   по D25, exclusive-bind по D24, STARTUPINFO+SW_SHOWMINNOACTIVE, --no-first-run только
   с тестовым override (D27), webdriver честно false, cleanup только своих PID. Если live
   фазы net_monitor без реального сайта невозможны честно — вердикт «нужен live-этап
   с записанным сайтом по §7 PORTING», не имитируй.
9. Записи: лист, parity-маркер, WORKLOG append, досье, печать. Вердикт портера —
   «готов к независимой приёмке B-2», НЕ ported/accepted.

## §5. Стоп-условия (немедленный стоп-вопрос, а не самостоятельное решение)

- байты native net_monitor.py не совпали с заявленным sha/размером;
- корпус и native-тесты расходятся (корпус главнее, но расхождение фиксируется);
- нужен API-выход net_monitor наружу (tool/entrypoint) или связка с bootstrap;
- любой гейт, который был ok, стал fail (кроме плановой Фазы A и её красных пинов);
- потребность менять стражи security, транспортные файлы или контракт stealth;
- SEC-инвариант не покрывается существующей формой стража;
- live-фаза требует существующего профиля пользователя или внешних сайтов.

## §6. Гигиена

Python -B всегда; pytest: `-p no:cacheprovider`, basetemp и junit наружу, в репо не
писать; `__pycache__` в репо после работ — 0 (кроме 3 fixture-сентинелов); отчёты
selfcheck не перегенерировать (остаться 44); чужие досье не перезаписывать (exclusive);
все записи — python-драйверами с byte-точными вставками (inline `python -c` с кириллицей
ненадёжен). В конце: tree-снимок после, сверка «изменилось ровно граница §3».

