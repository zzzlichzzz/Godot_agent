# B-2 — net_monitor (жёсткий класс)

Статус: **B-2 в работе**, не ported и не принят. Промпт:
`docs/porting/_start-prompt.browser_b2.md`. Продолжение browser-ветки; B-1 базис
принят аудитом 2026-11-04 (сессия 78). Таблица 44 механик не меняется.

## Цель и граница

Native-источник:
`D:/vajno/Godot/тест-плагина-ии/addons/Godot_agent/godot_agent/python/browser/net_monitor.py` —
24206 B, 456 строк, SHA256 `54167afbb87d9a9bf862df0a74c5a7bd24bb129661968682201c329d4297866b`
(сверено 2026-11-04, совпадает с промптом). Один сплочённый класс `BaseNetMonitor`
(33 метода): потоковый разбор CDP-кадров Network.*, SSE/chunk-стриминг,
`_fetch_and_apply_body`, match запросов/ответов, `pop_http_error`/`is_generating`/
`message_status`. Назначение в новом виде: internal-сервис substrate/llm/browser
(как фасад B-1): `provides_tools=()`, без entrypoint (ADR-0006 + D22, D26-маршрут
проверки — selfcheck browser не запускается, фиктивный модуль не создаётся).
B-2 к bootstrap не подключается — вербатим-эталон без связывания (связывание не
нужно для B-3: подклассы импортируют модуль напрямую по native-форме).

Замена байтов: в `python/substrate/llm/browser/net_monitor.py` сейчас 151-байтный
стаб (SHA256 `bba6a040b15ea17475159cc871b5fe1cf7a2eeeec96f6e566e20de6b86ce0fa6d`,
placeholder B-1) — заменяется точным native по §3 п.1 промпта. Сайтовые подклассы
(`ai_studio_net.py`, `qwen_net.py`, `sites.py`, `live_input.py`, backends) — B-3,
НЕ трогаются.

## Сверка фактов §0 (2026-11-04, до кода)

| Факт | Промпт | Фактически | Вердикт |
|---|---|---|---|
| `project.godot` | 335 B, `958b3a92…` | 335 B, `958b3a92…` | совпало |
| `WORKLOG.md` | 706167 B, `75c41220…` | 708237 B, `e5aef9e9…` | объяснимо: два append сессии 78 после фиксации промпта (приёмка B-1 + постановка B-2); хвост проверен, посторонних вставок нет |
| native `net_monitor.py` | 24206 B, `54167afb…` | 24206 B, `54167afb…` | совпало |
| selfcheck-отчёты | 44 | 44 | совпало |
| `.uid` | 86 | 86 | совпало |
| `__pycache__` | 3 каталога-сентинела, pyc=0 | 3 сентинела fixtures/** (4 файла) + **пустой каталог `tools/__pycache__` (0 файлов)** | байткода по-прежнему 0; пустой каталог не код, зафиксировано, удалён по гигиене |

## Инвентарь native-тестов (§4.1)

Судьба по `docs/tests-map.md` (все — deferred Q-08, «браузерная ветка позже»):

- `test_v88_6_qwen_net.py` (11) — упомянут в промпте; корпус-источник;
- `test_v88_8_net_first.py` (11) — упомянут в промпте; корпус-источник;
- `test_v88_12_net_confirm.py` (10) — упомянут в промпте; корпус-источник;
- `test_qwen_dual_response.py` (5) — упомянут в промпте; корпус-источник;
- прочие, где `BaseNetMonitor`: `test_net_monitor_lifecycle.py` (14, browser-extra),
  `test_rate_limit_sleep.py` (fake `Mon(BaseNetMonitor)`, суть — rate_limit, не B-2),
  `test_qwen_no_double_send.py`, `test_v105_net_answer_ready.py`,
  `test_kimi_stream_fallback.py`, `test_v88_0_aistudio.py`,
  `test_v87_1_kimi_cdp.py` (сайт-специфичный KimiChatMonitor — B-3),
  `test_arena_parser.py`, `test_browser_target_binding.py`,
  `test_aistudio_send_acceptance.py` — сайт-специфичные подклассы/смежные механики,
  в корпус B-2 идут только те кейсы, которые exercising-уют поведение самой базы
  (match, стриминг, `_fetch_and_apply_body`, pop_http_error, is_generating,
  порядок событий, reset) через минимальный подкласс-фейк.

## Фаза A — допуск лимита R-06 (до кода)

- Новое отклонение **D29** в `docs/deviations.md`: verbatim-эталоны
  `substrate/llm/browser/` — FILE_MAX 400 → 600, основание — вербатим-паритет R-08
  против R-06; правило по каталогу, не по одному файлу.
- Правка `tools/check_limits.py`: классовое правило по каталогу
  `python/substrate/llm/browser/` с комментарием-основанием.
- Красный тест стража до правки: файл 456 строк под tmp-структурой
  `substrate/llm/browser/` красен с текущим лимитом, зелен после (tmp + monkeypatch,
  не живое репо). Мутация допуска: снять правило → снова красен → byte-exact
  restore → green. `check_limits` обязан остаться ok с теми же двумя прежними
  предупреждениями (split_py 11, editing 8400) и без новых.

## Корпус и тесты

- `fixtures/corpus/browser/b2/`: входы-кадры и ожидания из native-тестов
  v88_6/v88_8/v88_12/qwen_dual + lifecycle, manifest.json по образцу b1/wire.json.
  Содержимое кадров не исполняется (SEC-03-дух).
- `tests/py/browser/test_browser_b2_net_monitor.py` (+ conftest при нужде):
  красные пины match_request/match_response, `_parse_stream_locked` (частичные
  кадры, фрагментация, длины 126/127 CDP, Unicode), `_finalize_stream`,
  `_fetch_and_apply_body` (inert), `pop_http_error`, `is_generating`, порядок
  событий, reset/сброс буфера. Входы — только из корпуса (R-16).

## Мутации и прогоны

- Собственная мутация (R-22): одна содержательная (порядок `_cleanup_request_locked`
  или сброс answer-буфера при responseReceived) → ожидаемые красные → byte-exact
  restore → green; вторая опциональна.
- Двойной полный прогон; гейты ×4 (lint_arch, check_limits, gen_contract --check,
  security_audit) — зелёные; focused regression B-1 (93/93) — не сломан.
- Live: по правилам B-1 (D24/D25/D27); если live-фаза без реального сайта
  невозможна честно — вердикт «нужен live-этап с записанным сайтом», не имитировать.

## Журнал исполнения портера

### 2026-11-04 — Фаза A исполнена (до кода B-2)

- Красные пины стража (`tests/py/browser/test_browser_b2_net_monitor.py`,
  tmp-структура + monkeypatch, не живое репо): red подтверждён —
  `test_guard_allows_verbatim_browser_456_lines` и
  `test_guard_verbatim_limit_is_600_not_unlimited` красные, пин
  `test_guard_400_still_applies_outside_verbatim_dir` зелёный (1 passed).
- Правка `tools/check_limits.py`: `VERBATIM_DIRS=("python/substrate/llm/browser",)`,
  `VERBATIM_FILE_MAX=600`, правило по префиксу rel-пути (классовое). Файл чистый LF.
- Отклонение D29 добавлено в `docs/deviations.md` python-драйвером (append,
  LF сохранён, 38237→40124 B, before `088f3c10eb…` → after `ef6979d0dd…`).
- Green: 3/3; `check_limits` ok/2 — файлов 569, предупреждений 2 (прежние:
  split_py 11 элементов, editing 8400; новых нет).
- Мутация допуска: снятие правила (−108 байт) → ровно 2 ожидаемых пина красных
  → byte-exact restore → sha `dbcc94bef739082151be90941da4dbeb1b5d53d26a24eb8418c3182ad788a0c0`
  → green 3/3.
- Методическая заметка: параллельный вызов нескольких shell-команд в одном
  батче гоняется конкурентно — мутационные прогоны выполнять по одной команде
  на вызов (иначе гонка мутация/прогон даёт ложный green).

### 2026-11-04 — Корпус создан (§4.3)

- `fixtures/corpus/browser/b2/manifest.json`: 6839 B,
  sha256 `c1aa6bef9cbea47154c9210552bb3e87e22af24be9e777c438fd86110db18d16`,
  12 кейсов; source_sha256 = native `54167afb…`. Файлы кейсов — LF, UTF-8 без BOM,
  кадры — данные (SEC-03-дух), не исполняются как код/JS.
- Покрытие: c01 match (POST/GET/чужой url), c02 pop_http_error 429 однократно
  (+200, +чужой url), c03 инкрементальный стрим: юникод + частичные кадры,
  c04 границы чанков 126/127 байт, c05 устаревшее тело игнорируется
  (getResponseBody=0), c06 сброс буфера при responseReceived (v88.10,
  answer_request_count), c07 loadingFailed → FAILED с сохранением partial,
  c08 запасной getResponseBody, c09 исключение разбора терминально,
  c10 финальный хвост отбрасывается, c11 хвост применяется один раз +
  поздний loadingFailed игнорируется, c12 сбой разбора буфера не реплеит partial.

### 2026-11-04 — Красные тесты, вербатим, green, мутация, прогоны (§4.4–§4.8)

- Красный прогон (§4.4) на стабе: 13 red / 3 green — byte-exactness-пин и все
  12 кейсов красные (на стабе нет `BaseNetMonitor`), guard-пины зелёные.
  Дефект харнесса (нет ветки `pin` в `apply_step`) найден на green-прогоне
  и исправлен; сам харнесс — не вербатим, правится.
- Verbatim-заливка (§4.5): стаб 151 B `bba6a040…` → native 24206 B
  `54167afb…` (python-драйвер с sha-проверкой до и после).
- Green (§4.5): батарея 16/16 (3 guard-пина D29 + byte-exactness + 12 кейсов).
- Мутация R-22 (§4.6): удаление `self._reset_answer_state_locked()` из
  `_on_response_received` (строка 186 native; 24206→24156 B,
  мутант `53e4211d…`) → ровно c06 красный (сброс буфера) + коллатеральный
  byte-exactness-пин → byte-exact restore sha `54167afb…` → green 16/16.
- Двойной полный прогон (§4.7): 16/16 ×2.
- Гейты ×4 (§4.7): lint_arch ok/0 (файлов 569); check_limits ok/2 (файлов
  569, предупреждений 2 — прежние); gen_contract --check 28 ok/0;
  security_audit ok/0 (SEC-01…SEC-08, SEC-20 все ok).
- Focused B-1 regression (§4.7): transport + facade + guards + sec20 =
  93/93 (exit 0).
- Live (§4.8): вердикт — **нужен live-этап с записанным сайтом**. `BaseNetMonitor`
  — substrate-класс без tool-выхода; его live-фаза требует реального
  стримящегося сайта (SSE/CDP Network.*) — имитация запрещена; live-батарея
  переносится на срез с сайтами (B-3) по §7 PORTING.

### 2026-11-04 — Граница и гигиена (tree-дифф против tree-stop b1-final)

- Базлайн «до»: `tree-stop.json` досье b1-final-20261103 (аудиторская база B-1,
  3914 файлов; собственный tree-before сессии не снимался — начало сессии
  равно принятому B-1 базису + documented appends сессии 78, см. дельту).
- tree-after: 3953 файлов, 848 каталогов; delta в досье
  (`tree-after.json`, `boundary-delta.json`). Изменения моей сессии — ровно:
  production `net_monitor.py` (151→24206), `tools/check_limits.py` (D29-правило),
  `docs/deviations.md` (append D29), `fixtures/corpus/browser/b2/**` (13 файлов),
  `tests/py/browser/test_browser_b2_net_monitor.py`, `docs/porting/browser-b2.md`,
  appends `docs/parity.md` + `docs/WORKLOG.md`. Остальные позиции дельты —
  исполнение сессии 78 (B-1 файлы, D28/SEC-03, промпты) относительно
  более раннего tree-stop.
- Гигиена в конце: `__pycache__` — 3 сентинела fixtures/** (4 файла), pyc=0;
  selfcheck-отчёты 44; `.uid` 86; `.pytest_cache` отсутствует; временные
  каталоги и junit — в `%TEMP%\opencode\c8_audit\b2-delivery-20261104\work\`.

## Вердикт портера (2026-11-04)

B-2 исполнен по §4 промпта в установленном порядке: Фаза A (D29 red → green →
мутация → byte-exact restore → green), инвентарь native-тестов, корпус 12 кейсов
из native-тестов (R-16: кейсы, не тесты; кадры — данные), красные пины →
verbatim-заливка sha `54167afb…` → green 16/16 ×2 → мутация R-22 red →
byte-exact restore → green → гейты ×4 зелёные → focused B-1 93/93 → tree-дифф
границы → гигиена.

**Вердикт: «готов к независимой приёмке B-2» — НЕ ported, НЕ accepted.**
Приёмка — независимыми прогонами аудитора (самоприёмки нет). Live-фаза
net_monitor: нужен live-этап с записанным сайтом; вербатим не имитировался.
Связывание с bootstrap не выполнялось (не нужно для B-3 — подклассы импортируют
модуль напрямую), fixирую отсутствие связывания как осознанное решение среза.


## Приёмка B-2 аудитом (2026-11-04, сессия 78)

Досье `b2-delivery-20261104` проверено: 3 печати byte-exact, tree-after 3953 файлов —
0 расхождений с репо (4 mojibake-пути резолвлены по SHA), граница среза подтверждена.
Свои прогоны: фокус 16/16 ×2, D29-стражи и byte-exact пин — зелёные; гейты ×4 и
security_audit ×2 ok/0; focused B-1 93/93; full security 237 pass/2 прежних skip.
Свои мутации ×2: не сбрасывать `_generating` в `_cleanup_request_locked` → 7 красных
(c05/c06/c07/c09/c10/c12 + байт-пин); не сбрасывать `_last_http_error` в `pop_http_error`
→ 2 красных (c02 + байт-пин); обе восстановлены byte-exact → 16/16. Урок: первые
прогоны «выжили» из-за конкурентного батча mutate/run/restore (гонка, замеченная
портером) — мутации строго по одной команде на вызов. Долг: независимый кейс
одноразовости pop_http_error (в B-3-контракте). Гигиена: pyc 0 (сняты 2 артефакта
пробника), сентинелы 4 файла, reports 44, uid 86, project.godot 335 B.
Статус: **B-2 принят аудитом** (не ported всего browser); live-фаза net_monitor —
долг: нужен live-этап с записанным сайтом (в B-3 или отдельным срезом).
Следующий срез — B-3: sites/live_input/ai_studio_net/qwen_net/browser_backend.
## Долг закрыт: независимый one-shot кейс pop_http_error (2026-11-04, долг-срез debt-cases)

В tests/py/browser/test_browser_b2_net_monitor.py добавлен test_pop_http_error_is_one_shot (helpers make_monitor/apply_step/snapshot, корпусной сценарий c02: post → response 429 chat → wait_done; pop возвращает 429 ровно один раз, повторный pop — None). Файл 16+1=17 зелёный. Мутация «удалить сброс _last_http_error из pop_http_error» красит 3 (новый кейс, byte-pin, c02); restore byte-exact SHA 54167afbb87d9a9bf862df0a74c5a7bd24bb129661968682201c329d4297866b 24206B → 17/17 зелёный. Статус не менялся: B-2 принят аудитором, не ported; live-фаза остаётся долгом.


## Долг pop_http_error: принято аудитом (2026-11-04, сессия 78)

Кейс one-shot добавлен (429 ровно один раз, повторный pop — None); мутация удаления сброса _last_http_error даёт 3 красных (новый кейс, byte-pin, корпусный c02), restore byte-exact (net_monitor 54167afbb87d9a9bf862df0a74c5a7bd24bb129661968682201c329d4297866b) → 17/17.
