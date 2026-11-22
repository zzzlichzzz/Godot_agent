# verification.api_check — C.12, сверка текста .gd с Godot API

**Статус:** этап 7 — принято аудитом 2026-10-31 (сессия 64).
**Обновлено:** 2026-10-31.

## Цель

Read-only инструмент `api_check(path, content)` сверяет `self.*`, `super.*`
и `connect()` с существующим кэшем Godot API. Возвращает дословные проблемы,
`base_class`, честные `checked` и `unavailable`; содержимое — данные, не файл
для чтения/исполнения. Основание: `_start-prompt.verification_api_check.md`.
Портер не принимает срез, не ставит этап7 и не правит `_audit-handoff.md`.

## Старый код

Эталон: `D:/vajno/Godot/тест-плагина-ии/addons/Godot_agent/godot_agent/`.
`gd_api_check.py` прочитан целиком:9137B,201LF/0CRLF,SHA256
`b9e0df9f604ce376aeddcf248a95f1334a1ea0427a98967a0bf680782ca14e5e`.

| Файл | Что переносим / граница |
|---|---|
| `python/godot_tools/gd_api_check.py:17,26–36` | MAX_PROBLEMS6, literal regex и горизонтальные `[ ^ ]` без изменения поведения; точный whitespace-якорь эталона — `[^\S\n]*` |
| `gd_api_check.py:39–98` | mask: та же длина, позиции/newline, escapes/triple quotes/comments |
| `gd_api_check.py:101–110,113–126,129–142` | local_symbols, matching paren, top-level args |
| `gd_api_check.py:145–201` | chain members, три сообщения, порядок, дедуп, quota |
| `python/tools/agent_bridge.py:1173–1212` | прочитан caller; фактический вызов1205–1206, не1196–1197 из промпта (там комментарий); агрегатор/CLI не переносим |

## Старые тесты

| Источник | Судьба / граница |
|---|---|
| Прямых legacy tests gd_api_check нет | новые actual-old наблюдения по §3; старые tests не импортировать/копировать |
| `repro_check_*.py` | владелец verification.check; не закрываются C.12 |

`docs/tests-map.md`: все168старых судеб сохраняются. Поиск `gd_api_check`/
`check_api_usage` в legacy tests дал только комментарии в трёх файлах.
Строки verification.api_check в parity/mapping/PROGRESS найдены.

## Корпус

Снят до tests/production:52 actual-old наблюдения (51return+1TypeError),
47успешных typed проекций/5contract-refusals. Семь маленьких project/cache
вариантов/13inputs в fixtures/projects/corpus/verification/api_check;
cases/manifest в fixtures/corpus/verification/api_check. Raw reference_result
отдельно от новой проекции. Oracle только на disposable copies,
root/classes/godot_version reset на кейс; capture/source/input/case byte-SHA pins.
Реальный2004630Bкэш — только внешний temp, никогда addon/корпус.

## Спецификация и инварианты

- ToolSpec §2.1 дословно: api_check; required path/content; effects=read,
  idempotent, errors=('invalid_input',), max_file_bytes=READ_TEXT_MAX_BYTES.
- path res://→normalize_rel→PathPolicy; denied при запрете; файл не читается,
  not_found невозможен. >4MiB UTF8 content→invalid_input до порта.
- Один существующий api_cache.snapshot() на вызов, никакого глобального кэша.
- checked=false различает source/no_extends,api_cache/no_cache,
  base_class/base_not_in_cache; checked=true→unavailable[].
- Literal mask/regex/messages/order/dedup/MAX_PROBLEMS6, без улучшений.
- Domain чистый; app40≤80. Принятые механики frozen; единственная согласованная
  правка gate — точный app-шов lint_arch по ADR-0010 с red и mutation proof.

## Решения по ходу

| Дата | Решение / фактическое расхождение |
|---|---|
| 2026-10-31 | Лист отсутствовал; создан первым по §3.1/R-19 до production/corpus/tests |
| 2026-10-31 | Скелетные `# tool: check`/`# contributes: check (API)` устарели; будущий владелец api_check, не check/verify. Пока код скелета не менялся |
| 2026-10-31 | Вклад в verify отложен в C.13; все62принятыхкейса C.9 сохраняются |
| 2026-10-31 | Запись/refresh/CLI/editor/новые substrate-порты/принятые domain/shared/substrate/formats/kernel вне scope; consumer ApiCache Protocol описывает уже существующий snapshot, binding не менялся |
| 2026-10-31 | Разрешённый внешний inventory scope: context case001; test_tscn_lint names; только api_check/count/list в перечисленных §1 тестах. Companion manifest не назван — B2 |
| 2026-10-31 | Требование импортировать чужую область engine_kb.shared противоречит R-11 и frozen lint_arch — B1. Не обходить динамическим импортом, копированием inheritance или ослаблением проверок |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-31 | 1. чтение/preflight/лист | AGENTS/RULES/architecture/PORTING/parity/tests-map/PROGRESS, template/соседи/WORKLOG/NOTES/security/ADR0004/0006/0009 и actual-old source/caller прочитаны; B1/B2 воспроизведены в temp |
| 2026-10-31 | база | byte-copy2234files:2232без двух fixture .godot файлов;83UID/debris0. Числа2233/2234/двух exclusions в §0 арифметически расходятся; ничего не удалялось/не подгонялось |
| 2026-10-31 | восстановленный C.11 | inheritance1442B/38LF/0CRLF/SHA5a9bad5013fb…; import class_api ok,gen_contract20/0diff,обаexit0/stderr0. Повторное восстановление не понадобилось |

Промпт37528B,430LF/430CRLF,SHA256
`19c65bf99fac7eb2571fd0dd2a59f992c74fd7f1ecc03385653f53f0b840f318`.
Backups/полные SHA/UTF8 stdout/stderr/diagnostics — только
`C:/Users/Lich/AppData/Local/Temp/opencode/c12-api-check-20261031/`.

## Проверки исходного preflight (история)

Preflight gen_contract: exit0/stderr0,20артефактов/0diff; import C.11:exit0/stderr0.
Actual selfcheck был blocked; итоговый ok записан ниже отдельно.
Полная2601/557/3регрессия из §0 здесь не объявляется новым прогоном.
Sandbox edge check использовал неизменённый lint_arch.check_edges:
`python/modules/verification/api_check/app.py: модуль импортирует чужой модуль python.modules.engine_kb.shared.inheritance`.
Это диагностика preflight, не submitted-byte мутация готовой реализации.

## Исторические блокеры (закрыты пользователем/ADR-0010)

| ID | Что мешает | Что требуется для продолжения |
|---|---|---|
| B1 | §2.2/§4.7 требуют verification→engine_kb.shared, но R-11 разрешает shared своей области; lint_arch:169–170 отклоняет чужую область до shared-ветки:174. §1/§6 запрещают менять lint/shared/kernel | Явно согласовать архитектурный путь и необходимые ADR/правило/узкую правку lint с red-case; либо новый план повторного использования, совместимый с frozen gates. Самовольно импорт не обходить |
| B2 | §1 разрешает context case001 count/names/effects, но не companion SHA в context/gather/manifest.json. Новые bytes обязаны изменить SHA, иначе корпус несогласован | Разрешить только SHA001 companion; прочие bytes/EOL/кейсы manifest frozen |

B2 воспроизведён без записи fixture: текущий SHA001
`bfa96c53c011bd6c28655d8dd698838febf012abea0805b639913dc16a5a2e8a`,
проекция ровно разрешённых count19→20/api_check/read→SHA
`8621d6e13715980467d85eb58d49edccdcc0627cff9e32bda26a4cd12ad8ca98`.
ADR-0009 разрешал companion для C.11/api, а не расширение scope C.12.

## Следующее действие

Независимому аудитору переснять52oracle-наблюдения, проверить756дифференциальных вызовов и M1–M10/P1–P3/ADR proofs на submitted-байтах; лишь после своей приёмки решать этап7/ported. Вклад в verify — отдельный C.13.

## Продолжение C.12 (2026-10-31)

Пользователь выбрал «Узкое разрешение»: B1/B2 закрыты ADR-0010, R-11 уточнён
до общей правки. Разрешён точный app.py → engine_kb.shared.inheritance и только
companion SHA001 манифеста; произвольные shared/domain/substrate не разрешены.
Свежий preflight: inheritance1442B/38LF/SHA5a9bad5013fb, import exit0/stderr0,
gen_contract20/0diff; selfcheck C.12 blocked/exit2/stderr0:

```text
selfcheck verification.api_check
  module         not_implemented заготовка: нет MODULE (R-05)
  layers         ok              файлов 498, нарушений нет
  limits         ok              файлов 498, предупреждений 0
  contract       ok              артефактов 20, расхождений нет
  security       ok              нарушений нет
  unit           not_implemented тестов модуля нет
  corpus         not_implemented нет корпуса механики
вердикт: blocked
```

Сырые stdout/stderr и byte-backup2234files/83UID:
`C:/Users/Lich/AppData/Local/Temp/opencode/c12-resume-preflight-20d5a77247/`.
Исторические B1/B2 выше сохранены как исходная диагностика, не актуальный стоп.

Архитектурный red:1failed/7passed; после точного app-шва ADR-0010 все16
новых/старых arch-tests passed, exit0/stderr0. Корпус capture exit0/stderr0:
52кейса,51actual-oldreturns+1actualTypeError,47success/5contractrefusals,
7вариантов/13inputs; root/classes/version reset перед каждым oracle-вызовом.
Capture10034B/SHA00e00403a7e1… вне addon; manifest пинит все case/input bytes.
Фактический fixture путь `corpus/verification/api_check/<variant>`: проекты
лежат в fixtures/projects/corpus, штатный runner прибавляет fixtures/projects;
`../corpus` из промпта вел бы в другую папку. Runner не изменён.

Шаг3: ToolSpec записан дословно; новые core/mask/app/contract/integration
тесты до кода запускались красными (feature-red.xml). Production: consumer
ports.py, mask/core, app40строк, MODULE api_check без вклада в verify.
Первый green нашёл только ошибку теста: `f((1),2)` закрывается в позиции7,
не8 (это проверено индексами строки; ожидаемые oracle-сообщения не менялись).

Шаг4: feature-green-final exit0/stderr0,206tests; gen_contract --write21.
Перед правками accepted inventory: inventory-red.xml —6failed/294passed,
только api_check/20 вместо19. Разрешённые6тестов изменены только в lists/counts;
context001 только count/name/effects; SHA001 companion по ADR-0010:
`8621d6e13715980467d85eb58d49edccdcc0627cff9e32bda26a4cd12ad8ca98`.
EOL всех изменённых baseline-файлов сохранён; shared inheritance не менялся.

Шаг5: selfcheck exit0/stderr0,206unit/52corpus; layers/limits502/0warnings,
21contract/0diff/security ok. Полный snapshot-final:609кейсов/0diff,exit0.
Общий nonlive-final:2815passed (2601+206+8),43.76s,exit0/stderr0;
collect-only:2815, итог JUnit будет сверен отдельно. Accepted6inventorytests
теперь зелёные внутри общего прогона; verify corpus62 не менялся.
M1–M10 все killed; P1 unit206green/gen_contract red; P2 unit206green/lint red;
P3 unit206green/lint red/security green (запрет этой связи принадлежит lint,
не security). ADR-0010 removal:1failed/7passed. Все14mutations восстановлены
побайтово из submitted с проверкой SHA; внешние M*/P*/ADR-restore.json.

Шаг6/live:live-final.xml —3passed/0fail/0errors/0skip,17.61s,exit0/stderr0.
JUnit nonlive2815/99files == collect2815; 206feature/5files; arch8.
Соседи:gd_lint126/37,verify136/62,tscn_lint315/65,selfcheck exit0/stderr0.
class_api selfcheck фактически186/26: штатный `test_api*.py` selector
tools/selfcheck.py:215 дополнительно взял58 integration api_check tests.
Это не изменённые C.11тесты и не регресс: отдельный прежний набор128passed
(class_api tests + api contract + test_api.py + test_api_snapshot.py),exit0/stderr0.
Selfcheck/имена тестов не менялись для искусственного сохранения числа128.

## Итоговые доказательства C.12

Независимый от capture.py внешний evidence.py переснял52наблюдения с reset
gd_api_cache._cache перед каждым;0diff. Сверены все378.gd в fixtures:
756вызовов (малый кэш и настоящий2004630B/1488classes),0необъяснённых diff.
Из них2явные contract boundary refusals: large.gd4194324B >4МиБ,
old=[]/new invalid_input. Это не пропуск и не сравнение разных входов;
все остальные754result.problems совпали дословно. Кэш только externaltemp,
SHA7352d27c8d8ed77b84b3b98400093c85144c4b6f8b8919b147ca035a67c8a93c.
Первый exploratory helper остановился на oversized fixture; исправлена
лишь классификация документированного отказа, продукт/корпус не менялись.
Финальный helper exit0/stderr0,16.514s; differential-verdict.json.

Standalone:lint_arch502/0violations,limits502/0warnings,security allok,
gen_contract21/0diff, всеexit0/stderr0. Probe checked: normalized
res://scripts/missing.gd (файла нет),2literalproblems,checkedtrue,unavailable[];
probe безcache:ok/checkedfalse/api_cache:no_cache; addonprobe:denied/exit1.
Всеprobe stderr0, content не читался из проекта и не исполнялся.

Live Godot создал111новых.gd.uid в frozen scene fixtures. Удалены только
пути, которых не было в byte-baseline; исходные83UID не тронуты.
reverse-before-uid-cleanup.json сохраняет исходный список, final reverse
проверяет UID83, отсутствие пропавших baselinefiles/unknown edits/debris.
Narrow reverse projection8/8:6inventorytests + context001 + SHA001 manifest
после удаления ровно api_check/20/SHA001 обратно равны baseline побайтово.
Все прежние20cards+template, inheritance/shared/store/kernel/formats,
принятые verification/scene mechanics и все168старых тестовых судеб frozen.
Добавлено75файлов; итог2234+75=2309files/83UID; caches/tmp/bak/orig/zz=0.
PROGRESS/parity только C.12строки; WORKLOG append; tests-map +6строк (168+36=204).

Артефакты: reports/selfcheck/verification.api_check.json; полные JUnit,
UTF8stdout/stderr/meta, before/submitted/SHArestore, capture.py/evidence.py,
totals-verdict.json/differential-verdict.json/reverse-verdict.json —
`C:/Users/Lich/AppData/Local/Temp/opencode/c12-resume-preflight-20d5a77247/`.
Этап7/ported не выставлены; `_audit-handoff.md` и исходный prompt неизменны.

Финальный `python -B tools/selfcheck.py verification.api_check`, exit0/stderr0:

```text
selfcheck verification.api_check
  module         ok              verification.api_check (api_check)
  layers         ok              файлов 502, нарушений нет
  limits         ok              файлов 502, предупреждений 0
  contract       ok              артефактов 21, расхождений нет
  security       ok              нарушений нет
  unit           ok              206 passed in 1.30s
  corpus         ok              кейсов 52, расхождений нет
вердикт: ok
```

Итоговый inventory:21capability cards/20headless tool names; api_check/read
добавлен без конфликта check/verify. Frozen selfcheck prefix-особенность C.11
описана выше, не скрыта изменением гейта или переименованием тестов.

Финальная reverse-byte проверка поймала непреднамеренно потерянную пустую
строку EOF линтера. Восстановлена исходная форма EOF; теперь единственная
дельта tools/lint_arch.py — четыре строки ADR-0010. Мутация ADR-final повторена
на окончательных submitted bytes:1failed/7passed, восстановление SHA
a6c5edd4765072d11df8ac8b60da5f40d39290fe43cf108f54e7fcd3f6b9aff7
(9842B/228LF). Первоначальные доказательства сохранены отдельно, не затёрты.
Повторный финальный selfcheck: selfcheck-c12-submitted-final.stdout.txt;
общий прогон/корпус: nonlive-submitted-final.xml и
snapshot-submitted-final.stdout.txt; предыдущие прогоны тоже сохранены.

## Приёмка аудитом (сессия 64, 2026-10-31)

Принято на этап 7. Мои прогоны, не из отчёта портера:

| Что | Результат |
|---|---|
| Пересъёмка корпуса своим скриптом (`_cache` сброшен на кейс) | `reference_result` **52/52**, независимая проекция **52/52**, порт против `expect` **52/52**; 5 отказов контракта отдельно |
| Дифференциал шире корпуса | 378 `.gd`, 73 корня, 2 режима кэша (свой и реальный 2 004 630 B / 1488 классов) → 756 вызовов, 498 буквально, **0 расхождений**, 258 границ (256 `denied` на `addons/`, 2 лимит) |
| Свои мутации | A1 3, A2 3, A3 15, A4 18, A5 9, A6 12, A7 3, A8 11, A9 21, A10 15 red; P1 — только `gen_contract --check`; P2 — `lint_arch` (IO в `domain/`); P3 — `test_lint_arch_api_check.py` 1 failed / 8 + `lint_arch`; все файлы восстановлены байт-в-байт |
| Числа | 2815 non-live (99 файлов сбора, stderr 0), 3 live (24.5 с), snapshot 609/0, contract 21, selfcheck 206/52, соседи 126/37 · 136/62 · 315/65, слои/лимиты 502/0, дерево 2311, `.gd.uid` 83, debris 0 |
| Эталон | `gd_api_check.py` 9137 B / 201 LF / `B9E0DF9F604C` — совпал с пином манифеста |
| ADR-0010 | шов узкий (`tools/lint_arch.py` 9842 B `A6C5EDD47650`): разрешён только `api_check/app.py` → `engine_kb.shared.inheritance`, `_same_feature` и `ALLOWED` не тронуты |

**Открытая находка F2 (не блокирует):** `ToolSpec.errors == ('invalid_input',)`, хотя инструмент реально
отдаёт `denied` (кейсы 048/049), а соседи объявляют все три вида. Поведение и карточка согласованы,
гейты зелёные, но карточка недообъявляет вид ошибки. Закрытие — микро-срез: `errors=('invalid_input','denied')`
+ `gen_contract --write` + правка `test_api_check_contract.py`.

### Companion C.13 (2026-10-31, не принято)

Разрешённая F2-дельта: `errors=('invalid_input', 'denied')` без not_found,
соответствующий пин и только поле errors карточки; вклад
`contributes_to=('verify',)` вызывает собственный app и передаёт
checked/unavailable дословно. Принятые app/domain/mask не меняются.

Итог C.13: **готов к независимому аудиту, не принято**. errors пин и
карточка изменились только на добавление denied; contributes_to=('verify',).
Companion-пин в API integration явно разрешён пользователем, остальные
58 тестов/C.12 corpus52 неизменны. selfcheck api_check **206/52, ok**;
соседи gd126/37, tscn315/65, class_api186/26 без изменения селектора F4.
P1 откат errors: gen_contract exit1 (`устарел: api_check.json`), behavioral
357 passed, отдельно exact errors pin1 failed; это **не** зелёный весь suite.
Следующее действие — независимый аудит C.13 по `verification.check.md`.
