# B-3 — sites / live_input / ai_studio_net / qwen_net / browser_backend: закрытие браузерной ветки

Статус: выдан аудитором 2026-11-04 (сессия 78, продолжение). Сложность: **средняя**.
Модель: средняя (gpt-5.x-класс) — sol НЕ нужен: все архитектурные решения приняты
(verbatim-стратегия, маршрут проверки D26, live-правила D24/D25/D27, D29-допуск уже
действует), Фаза A с правкой лимитов НЕ требуется — все пять файлов в лимите R-06.

## Где мы

B-1 базис и B-2 (net_monitor) приняты аудитом. WORKLOG 713 456 B, SHA
`ddc65356bd0132c429b6da14a9d82f6f032ac37421098de840b4a0b2b0b29b65`; parity sha
`e6c1d73791754a33…` (B-1/B-2 «приняты», B-3 deferred); net_monitor.py 24 206 B
`54167afb…` byte-exact vs native; фасад 100 LF `6abe81d…`; страж `d4679c…` (D28+SEC-03);
контракт `browser_stealth.json` (skeleton: 10 forbidden_techniques, pinned site flags);
гейты ok/0 + ok/2; non-live база 5225/5223/2; reports 44; uid 86; pyc 0 (3 сентинела);
project.godot 335 B `958b3a92…`. Открытые долги: live-фаза net_monitor и независимый
кейс одноразовости pop_http_error (см. ниже).

## Что перенести (verbatim, R-08) — все ≤400 строк, sha сверять с native

| Native-файл | Размер | Строк | SHA256 |
|---|---|---|---|
| `browser/sites.py` | 9 906 B | 214 | `06da927025fd1825…` |
| `browser/live_input.py` | 4 437 B | 83 | `cd2c6ccfc12c371b…` |
| `browser/ai_studio_net.py` | 9 735 B | 224 | `3d9a3fb4b62a1071…` |
| `browser/qwen_net.py` | 12 199 B | 238 | `57d1ab2bfaea6226…` |
| `backends/browser_backend.py` | 3 380 B | 58 | `21e5e911d139b4d1…` |

Размещение: `python/substrate/llm/browser/` (sites/live_input/ai_studio_net/qwen_net)
и `python/substrate/llm/browser/backends/browser_backend.py` — exact-структуру сверить
с parity-строкой «ported verbatim» и NOTES.md; при расхождении — стоп-вопрос, не выбирать
самовольно. Это внутренние сервисы ветки (ADR-0006+D22): в контракте capabilities артефактов
не появляется, к bootstrap модуль не подключается — B-3-подклассы импортируют net_monitor
напрямую (связывание не выполняется — осознанное решение среза B-2, продолжается).

## Граница

Разрешено: 5 verbatim-файлов (замена заглушек), корпус `fixtures/corpus/browser/b3/`,
тесты `tests/py/browser/test_browser_b3_sites_net.py` (или разбить по файлам), лист
`docs/porting/browser-b3.md` ДО кода, parity-маркер «B-3 в работе», WORKLOG append,
досье `b3-delivery-<дата>`. Запрещено: B-1 файлы (sha в листе B-1/boundary
b1-live-20261103), net_monitor (`54167afb…`), контракт stealth, стражи (`d4679c…`),
гейты, PROGRESS и таблица 44, native-источники, внешние сайты, чужие профили.

## Порядок работ

1. Инвентарь native-тестов по этим файлам (tests-map: deferred Q-08 — `test_arena_parser`
   29 кейсов, `test_aistudio_send_acceptance` 4, qwen-тесты и др.); судьбу по R-17 записать
   в лист; кейсы поведения → корпус (R-16), кадры/HTML — данные, НЕ исполняются.
2. **SEC-19/R-21-пины — главный содержательный блок среза**: `sites.py` содержит
   `needs_visibility_spoof`-флаги — сверить побайтно-уровень с pinned site flags
   `contract/browser_stealth.json`; поднимание спуфа с false запрещено; маскировка
   только там, где ответ читается из DOM. Красный пин до кода: правка флага → страж красный.
3. Красные пины до verbatim: match сайтов (ai_studio/qwen), селекторы как данные
   (не исполняются), `live_input` — CDP Input-команды (данные команд, не ввод),
   `browser_backend` — сборка сообщений, отказ при отсутствии парсера.
4. Verbatim-заливка каждого файла с sha-проверкой (портеровский приём — драйвер).
5. Своя мутация ×2: (а) в `sites.py` — подмена needs_visibility_spoof → SEC-19 красный;
   (б) в `qwen_net`/`ai_studio_net` — точку по выбору (например, разбор кадра) → корпус красный.
   Byte-exact restore, по одной команде на вызов (гонка батчей!).
6. Двойной корпус, гейты ×4 (check_limits остаётся ok/2), B-1+B-2 regression
   (93+16=109), full security 237/2, security_audit ×2.
7. Live-фаза: внешние сайты запрещены промптом — вербатим не имитировать; вердикт
   «нужен live-этап с записанным сайтом» (или пользователь отдельно разрешит ручную
   проверку на разрешённом провайдере без VPN — до того решения production live не заявлять).
8. Записи: parity-маркер, лист (журнал+вердикт), WORKLOG append (prefix 713 456 B,
   `ddc65356…`), досье, SHA-печать последним файлом. Гигиена: -B, pyc 0 (кроме сентинелов),
   отчёты не перегенерировать, чужие досье не перезаписывать (exclusive).

## Стоп-условия

sha не совпал; корпус расходится (корпус главнее); SEC-19/R-21 не покрыт; страж/гейт
ok→fail без планового отклонения; размещение файлов отличается от parity/NOTES; нужен
выход в сеть или чужой профиль; verbatim конфликтует с чем-либо — стоп-вопрос.

## Приёмка

Вердикт портера — «готов к независимой приёмке B-3»; не ported/accepted (это решит
аудит; после него браузерная ветка закрыта — останется только общий live-этап с
записанным сайтом как отдельная задача пользователя).
