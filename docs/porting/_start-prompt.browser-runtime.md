# Browser runtime-интеграция + no-focus детерминизм (средний+жёсткий класс, sol)

Один промпт, две части с раздельными вердиктами. Роль портера — та же (WORKLOG,
границы, свои прогоны, досье, честные стоп-условия). Модель: gpt-6.1-sol.

- **Часть A** — детерминизм no-focus: тест-срез усиления (без production-правок).
- **Часть B** — runtime-интеграция браузера: перенос парсеров byte-exact, явные
  sys-связки эталонов, recorded-site live через локальный записанный сервер.
  Вердикты: «A закреплена» и «B готов к независимой приёмке»; final приёмка —
  независимый аудит. Частичный вердикт по B разрешён и честен.

## §0 — пересчитать самим (не верить списку)

- `project.godot` 335 B, SHA `958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`.
- `docs/WORKLOG.md` ≈ 726 984 B, SHA начинается `d13ee943f4c6bcb7`
  (если префикс ушёл вперёд — найдите фактический и укажите в §0 досье).
- `docs/parity.md` LF, ≈194 строки, SHA `5d1cec37…` — не трогать.
- reports/selfcheck = 44; .uid = 86; .pyc = 0; 4 fixture-сентинела
  `fixtures/projects/corpus/editing/**/__pycache__/` НЕ трогать.
- Гейты: lint_arch ok/0 (573 файла), check_limits ok/2 (2 прежних warning:
  split_py 11, editing 8400), gen_contract --check 28/0, security_audit ok/0.
- Тест-файлы: `tests/py/security/test_sec03_nonlistening_probe.py` 72/72,
  `tests/py/browser/test_browser_b2_net_monitor.py` 17/17 (после долг-среза).
- Python 3.14.6; прогоны `python -B -X utf8`, pytest `no:cacheprovider`,
  basetemp/JUnit наружу, `--import-mode=importlib`.
- Frozen byte-exact эталоны и restore-пины: transport `browser_manager.py`
  `4afd245f…`, `cdp_ws.py` `3b5298dd…`, фасад `facade.py` 5333 B,
  `net_monitor.py` 24206 B `54167afbb87d9a9b…`, sites `06da9270…`,
  live_input `cd2c6ccf…`, ai_studio_net `3d9a3fb4…`, qwen_net `57d1ab2b…`,
  browser_backend `21e5e911…`, guard `security_audit.py` `c59e4faf35f1e71e…`.

## Часть A — детерминизм no-focus

Фон: приёмка B-1 (parity.md) зафиксировала гонку старта Chrome: в 1 из 8
live-запусков окно ~0.4 с выходило в foreground до OS-снимка (fresh disposable
профиль, pinned запуск, ноль правок фасада). Решение записано: «детерминизм
no-focus (retry/verify-усиление) закрепить отдельным разрешённым срезом;
unit-пины детерминированы и не страдают».

Задача:
1. Live-харнесс (копия проверенного харнесса B-1, живёт ТОЛЬКО в досье, не в
   репо) усилить: классификация foreground по серии выборок (≥3 с интервалом
   ~0.5 с) вместо одной; краткое (<1.5 с суммарно) собственное foreground-окно
   с последующим свёртыванием считается стартовой гонкой, не нарушением;
   устойчивое foreground в момент проверочных снимков — нарушение. Правила
   D24/D25/D27 не менять. Изменения харнесса задокументировать в вердикте.
2. Прогон: полная live-батарея B-1 ×2 подряд (двойной wire 35/35 + file:// 2/2,
   live 3/3 + sandbox restore 1/1, busy-port refusal, webdriver=false) —
   ожидание 8/8 + 8/8 чисто. Если гонка воспроизводится — НЕ подгонать критерий:
   честный вердикт «гонка воспроизводится на старте Chrome, не механика фасада».
3. Append в `docs/porting/browser.md`: короткий раздел «Детерминизм no-focus
   закреплён» (числа прогонов, критерий, дата). EOL файла — CRLF, чистая добавка.

Граница A: досье + append browser.md + WORKLOG. Ноль правок production, фасада,
transport-эталонов, гейтов. Chrome запускается только по правилам B-1
(D24/D25/D27).

## Часть B — runtime-интеграция

### B.0 Инвентаризация импортного замыкания (первый шаг, до переноса)

Native-источник: `D:/vajno/Godot/random-game/addons/godot_agent/python/`.
Кандидаты и SHA256 (сверить сами, не верить):

| Файл | B | SHA256 |
|---|---|---|
| `parsers/parser_base.py` | 198211 | `7b2ce9f14695416e12da1fe0590858b0e9ae9f96a8301eb5661b19f7364dd4f2` |
| `parsers/arena_parser.py` | 57066 | `cdc01c59d0e85fe88a0145d482d33f84ef4a05838966fd19e04c3ce5dc2265c3` |
| `parsers/ai_parser.py` | 37004 | `20b0cf8749f1089fc1d0b0bb24cfd0b3df554caff95916e84a17806154e465b5` |
| `parsers/qwen_parser.py` | 37217 | `e0b888fe57fb584b0cbd7a24cf0f59bde6d5510a7a1cd4a465917eb8926a36fe` |
| `parsers/kimi_parser.py` | 25355 | `f0db0f5c1da39d24b56a5d1c4591f31a1ca79cbfc908d18e13897f77958e2376` |
| `parsers/deepseek_parser.py` | 14989 | `554b6505d1bc5484261672583c2e5767d0c838a366b915b3a1428abaf7dda971` |
| `parsers/text_sanitize.py` | 3305 | `2c18bbefb0a08f0cf99a31cc27d67f49f7396ffc5fc29017d0733aefed5ac0db` |
| `server/server_state.py` | 39732 | `efecb557b45c4a6e0ea4a4b806027cab20f07af8bda6a6e72f3e297575300c1e` |
| `godot_tools/answer_judge.py` | 25313 | `545639a905fdb2b05c97d25bc720c4835956d997dc0ee27dc9cd817cf1fc0bbc` |

Ожидаемое (проверить, не верить) замыкание:
- Переносятся byte-exact: `parser_base`, `text_sanitize`, `ai_parser`,
  `qwen_parser`, `deepseek_parser`, `kimi_parser` — их импорты замыкаются на
  stdlib + selenium + перенесённые эталоны (`cdp_ws`, `net_monitor`,
  `ai_studio_net`, `qwen_net`) + `parser_base`/`text_sanitize`.
- `arena_parser`: byte-exact перенос разрешён, но его `answer_judge`-импорт
  остаётся инертным (см. ниже) — judge-ветви Arena честно deferred.
- `answer_judge`: НЕ переносить — тянет gd-механики (`gd_api_check`, `gd_lint`,
  `tscn_lint`, `symbol_refactor`, `high_level_actions`, `runtime_debug`,
  `runtime_checks`, `minilich`), которых в новом дереве ещё нет. Честный
  deferred с перечнем недостающего.
- `server_state`: НЕ переносить — тянет серверную подсистему (`history_manager`,
  `chat_store`, `project_tools`, flask-хвост). Связку `browser_backend →
  wait_driver` оформить как явный задокументированный шов: спецификация до
  кода, семантика wait_driver (броски RuntimeError с понятным текстом, поллинг
  holder'а) воспроизводится поверх модели владельца запуска D24 (фасад), пины
  на поведение. Если окажется, что честный шов невозможен — вердикт
  «server_state deferred», без имитаций.

### B.1 Перенос эталонов byte-exact

1. Размещение: `python/substrate/llm/parsers/` (семь файлов выше), `__init__.py`
   по образцу соседних пакетов. Иные размещения — только с фиксацией в
   deviations. Байты = native, SHA по таблице B.0.
2. `check_limits`: добавить классовое правило для verbatim-эталонов
   `substrate/llm/parsers/` по образцу D29 (браузерные эталоны 400→600) —
   достаточный FILE_MAX для parser_base; правку правила зафиксировать в
   deviations. Прежние 2 warning должны остаться прежними.
3. Импорты внутри эталонов не переписывать (байты неизменны) — связывает B.2.

### B.2 Явные sys-связки (не хак)

Эталоны используют старые абсолютные импорты (`from parser_base import …`,
`from net_monitor import BaseNetMonitor`, `from cdp_ws import …`,
`from ai_studio_net import …`, `from qwen_net import …`,
`from text_sanitize import …`, `from sites import …`). Запрещены: meta_path/
PathHook, скрытые хаки, регистрация при импорте пакета. Разрешено и требуется:
ОДИН явный модуль-связка (не-verbatim, ≤ ~60 строк, спецификация до кода в
листе), который при явном его импорте регистрирует в `sys.modules` алиасы
старых имён на substrate-модули; повторная регистрация идемпотентна;
отсутствующий эталон = явная ошибка. Пины: алиас `is` реальный substrate-модуль;
без импорта связки алиасов нет; production-профили/бутстрап связку не импортируют
(substrate, не tool).

### B.3 Корпус и offline-батареи

1. `fixtures/corpus/browser/runtime/manifest.json`: synthetic minimal frames по
   образцу B-3 (инертные CDP/callback-порты, отдельные JSON inputs с bytes/SHA/
   provenance). Покрыть: парсинг ai_studio protobuf (step/thought/answer/finish,
   UTF-8, partial, gzip, tail), qwen SSE/Unicode/thought/dual, deepseek/kimi
   ветви, `text_sanitize` (sanitize_llm_text), общие ветви `parser_base`
   (answer_transfer_incomplete, parse_action_json, best variant, тишина DOM —
   по репро native-тестов, без копирования старого test-кода).
2. Тесты `tests/py/browser/test_browser_runtime_*.py`: парсерные unit-кейсы,
   связки B.2, шов wait_driver, инертность arena-judge (импорт arena_parser не
   взрывается; judge-ветви помечены deferred).
3. tests-map строки 174–202: судьбы менять строка за строкой, только по
   фактическому покрытию кейсов; частичное покрытие — примечание в листе, не
   смена судьбы. Ничего не объявлять закрытым без кейса.

### B.4 Recorded-site live (локальный записанный сервер, БЕЗ внешней сети)

Пользовательское разрешение зафиксировано промптом: live-фаза = локальный
записанный сервер. ЗАПРЕЩЕНА любая внешняя сеть (все URL 127.0.0.1).
1. Записанные ответы — данные корпуса B-3 (`fixtures/corpus/browser/b3`,
   native observations: ai_studio protobuf JSON, qwen SSE) + новые записи при
   необходимости, каждая с bytes/SHA/provenance. Это данные, не код.
2. Оракул: локальный HTTP-сервер (fixture, ephemeral 127.0.0.1 порт) отдаёт
   записанные потоки; страница-оракул (file:// или localhost) воспроизводит
   сценарий страницы (fetch к записанному серверу). Chrome по D24/D25/D27
   (disposable sibling-профиль, pinned, --no-first-run только для live).
3. Live-батарея: net_monitor перехватывает через CDP Network.*, парсер
   разбирает записанный поток, сверка с ожиданиями корпуса (text/thought/
   finish); mirror-ввод live_input против оракул-страницы по возможности —
   при невозможности честно отметить deferred. Selenium-ввод — по native
   семантике против оракул-страницы, без новых маскировок и спуфов.
4. Расхождение live vs записанное — стоп, не «подгонять корпус под ответ».

### B.5 Мутации, гейты, порядок

1. Свои мутации ≥2 на новом коде-связке/оракуле И ≥1 на эталоне (пример:
   вырезать вызов `sanitize_llm_text` в parser_base → red → byte-exact restore
   SHA `7b2ce9f1…` → green). Мутации frozen-файлов — только как временные
   с byte-exact restore по SHA.
2. Гейты ×4 + security_audit ×2 (ok/0); focused прогон новых файлов ×2;
   full non-live прогон (база ~5476 + новые кейсы). Гигиена: 44/86/0/сентинелы.
3. Порядок: §0 → tree-before → A → B.0 → B.1 → B.2 → B.3 → B.4 → B.5 →
   WORKLOG append (CRLF, префикс из §0) → SHA-печать досье последней.
4. Лист: новый `docs/porting/browser-runtime.md` (CRLF, спецификация до кода,
   решения, вердикт). Appends в browser.md/b2/b3-листы — только по факту.

## Границы

Разрешено: `tests/py/browser/**`, `tests/py/security/**` (только новые кейсы
при необходимости), `fixtures/corpus/browser/**`,
`python/substrate/llm/parsers/**`, модуль-связка/шов (имя — решение портера),
`tools/check_limits.py` (классовое правило эталонов), `docs/tests-map.md`
(строки 174–202 по факту), deviations.md, WORKLOG, browser-runtime.md,
appends browser.md, досье. Запрещено: изменение байтов перенесённых эталонов
B-1/B-2/B-3 вне временных мутаций, фасад/transport bytes, `contract/`,
`docs/parity.md`, PROGRESS, таблица 44, native-источники, прочие tools/,
внешняя сеть, реальный профиль Godot_AI_Profile, `reports/selfcheck/`.

## Стоп-условия

- Мутация не красит новый кейс → стоп, не подгонять тест.
- Гейт ok→fail, SHA эталона после restore ≠ исходному → стоп.
- Замыкание тянет незапланированную подсистему (сервер, gd-механики) → честный
  deferred, не «перенести весь сервер».
- Live-гонка/расхождение воспроизводятся → честный вердикт, не подгонять.
- Частичное исполнение B — легитимный вердикт (укажите фазу и причину).
