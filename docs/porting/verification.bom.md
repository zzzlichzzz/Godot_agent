# verification.bom — C.10, закрытие F1 в декодировании файлов

**Статус:** этап 7 — принято аудитом 2026-10-31 (сессия 62): своя пересъёмка корпуса 62/62, проекция 56/56, порт 62/62, дифференциал 1219 файлов без BOM-расхождений, мутации X1–X7/P8 красные с байтовым восстановлением. F1 закрыт.
**Обновлено:** 2026-10-31.

## Цель

Убрать false-clean на BOM-only `.gd` и вернуть потерянные находки первой строки.
`gd_lint` и `verify` снимают ровно один ведущий UTF-8 BOM при декодировании файла;
сами байты, CRLF и `checked_bytes` не меняются. Пользователь выбрал «Закрыть F1»
и разрешил отдельный срез по принятым механикам/BOM-кейсам 2026-10-31.
Исторические C.2/C.8/C.9 остаются принятыми; эта дельта сдаётся отдельно.

## Старый код

| Файл | Роль |
|---|---|
| `python/godot_tools/project_tools.py:778–786` | `read_project_file`: utf-8-sig/errors=replace; источник семантики BOM |
| `python/tools/agent_bridge.py:1173–1264` | `_check_one_path`: проверка одиночного файла, validation off |
| `python/godot_tools/gd_lint.py:69–191` | чистый алгоритм не снимает BOM сам; остаётся неизменным |
| `python/godot_tools/tscn_lint.py:455–459` | instance-файлы читаются utf-8, не utf-8-sig; менять это нельзя |

Эталон HEAD `ba0535d4dec43c32750e601a6ca86e377abc6af3`; только чтение.

## Старые тесты

Судьбы всех168 legacy-строк сохраняются. `repro_check_unchecked.py` и
`repro_check_truncated.py` уже размечены для C.9; их CLI/required/auto-ветки
этим ремонтом не закрываются. Входы C.2 №018/019/035 — действительные
BOM-репродукции; исправляются ожидания файлового слоя, но старые результаты
чистого `lint_gdscript(text)` сохраняются отдельными сырыми данными.

## Корпус

Пересняты №018/019/035 через настоящий `_check_one_path` после
`read_project_file`; сохранены старые pure-text сообщения/expect. Добавлены
24BOM-кейса для пяти видов: один/двойной/внутренний BOM, CRLF, invalid/partial
UTF-8, syntax/duplicate/empty, без исполнения Python; четыре tscn candidate
oracle отдельно на исходном тексте. Новый C.9 корпус62/59inputs, C.2 —37кейс.
Съёмщик и byte backups — `C:/Users/Lich/AppData/Local/Temp/opencode/f1-bom-20261031/`.

## Спецификация

- Новых ToolSpec/инструментов/портов нет; все19 карточек остаются прежними.
- Один чистый декодер в `verification/shared/source_text.py`, используется
  файловыми точками входа gd_lint/verify. Один ведущий BOM, errors=replace,
  без нормализации newline и без stripping внутренних/повторных U+FEFF.
- `lint_gdscript(text)` как публичная чистая функция — без изменения алгоритма.
- Принятый `check(path, content)` получает candidate-текст как есть;
  tscn app/domain/read_inputs и65кейс-корпус остаются байт-в-байт.
- Размер проверяется по исходным байтам до декодера; никаких записей проекта,
  процессов/исполнения текста, изменения PathPolicy/квоты/порядка/сообщений.
- Partial BOM EF BB: эталонный потоковый utf-8-sig даёт пустоту, bytes.decode
  даёт U+FFFD. Используется incremental decoder final=True; кейс046 сохраняет
  реальное наблюдение. Исправлен изначально неверный unit-expect до кода.

## Решения

В эталоне два разных слоя чтения: основной файл utf-8-sig, instance-файл
utf-8. Поэтому общая правка DiskFS/tscn read_inputs была бы новым дрейфом.
Исправление ограничено основным файлом gd_lint/verify. Candidate BOM остаётся
контрактом C.8; это отдельно запинено интеграционным тестом.

## Ход работы

| Дата | Этап | Доказательство |
|---|---|---|
| 2026-10-31 | 1 | handoff/PROGRESS подтвердили C.9 stage7; пользователь выбрал отдельное закрытие F1; эталон/слои прочитаны |
| 2026-10-31 | база | byte copy2116файлов,83UID до первой правки; `before.json` |
| 2026-10-31 | 2 | actual-old capture exit0/stderr0:3C.2повторных+24C.9новых,4candidate; source/scriptSHA в манифестах |
| 2026-10-31 | 3 | ADR-0008; старые raw-text тесты сохранены отдельным oracle; добавлены decoder и cross-consumer/candidate тесты до кода |
| 2026-10-31 | 4 | red32failed/537passed; production — общий incremental utf-8-sig decoder и две точки входа; green569passed30.68s,exit0/stderr0 |
| 2026-10-31 | 5 |2473nonlive64.59s;collect/XML2473,точное равенство orderedIDs/88files;531корпус/0diff;selfcheck gd126/37,verify136/62,tscn315/65;497layers/limits,19cards/securityok |
| 2026-10-31 | 6 | D1–D8 обнаружены,restored569passed;live3passed;probe BOM-only не clean;три clean selfcheck;reverseSHA8файлов,полный byte scope2170/83UID/debris0 |

## Проверки

Красный полный scope: **32failed/537passed**,569collected/XML,exit1/stderr0.
Принятая база аудитора:2428nonlive+3live,507корпус,gd126/37,tscn315/65,
verify91/38; эти числа не выдаются за новый прогон.

Новые полные регрессия/collect/корпус завершились exit0/stderr0; никаких
failed/skipped. Первые selfcheck трёх механик — verdict ok/exit0, но каждый
вывел3исторические recovery-expired строки/147Bstderr; это не stderr-clean
доказательство. Чистые повторы после остальных прогонов приведены ниже. При разборе verbose
логов count-proof сначала не учёл двойной пробел перед процентом у7строк;
парсер whitespace исправлен, все2473orderedIDs совпали, XML2473зелёных.

### Итоговые selfcheck — exit0/stderr0

F1 не новый discovered-модуль; вердикт берётся с трёх затронутых владельцев,
а не с выдуманного `selfcheck verification.bom`.

| Проверка | gd_lint | verification.check / verify | tscn_lint / check |
|---|---|---|---|
| module | ok | ok | ok |
| layers | ok,497/0 | ok,497/0 | ok,497/0 |
| limits | ok,497/0warnings | ok,497/0warnings | ok,497/0warnings |
| contract | ok,19/no drift | ok,19/no drift | ok,19/no drift |
| security | ok | ok | ok |
| unit | **126passed5.83s** | **136passed4.40s** | **315passed15.95s** |
| corpus | **37/0diff** | **62/0diff** | **65/0diff** |
| verdict | **ok** | **ok** | **ok** |

JSON отчёты: `reports/selfcheck/verification.gd_lint.json`,
`reports/selfcheck/verification.check.json`,
`reports/selfcheck/verification.tscn_lint.json`.
Полные UTF-8 логи `final-gd`, `final-verify`, `final-tscn` в external каталоге
среза. Не меняются19ToolSpec/карточек,набор инструментов,порты/editorпротокол.

### Submitted-byte мутации D1–D8

У каждой — один и тот же полный scope: три module dirs check/gd_lint/tscn_lint,
contract test_verify_contract/test_check_contract, integrations test_verify,
test_verify_bom,test_gd_lint,test_tscn_lint. Collect/XML569,без skips;
baseline и полностью восстановленный scope —569passed,exit0/stderr0.

| ID | Подмена | failed / passed | Что доказано |
|---|---|---|---|
| D1 | shared utf-8-sig→utf-8 | 29 /540 | decoder нужен для GD/PY/JSON/CFG |
| D2 | gd consumer обходит decoder | 9 /560 | оба входа должны быть исправлены |
| D3 | verify consumer обходит decoder | 21 /548 | dispatcher действительно использует decoder |
| D4 | снять все U+FEFF | 5 /564 | repeated/embedded BOM нельзя улучшать |
| D5 | нормализовать CRLF/CR | 3 /566 | decoder не меняет newline |
| D6 | checked_bytes по decoded text | 12 /557 | квота/счётчик остаются по raw |
| D7 | pure lint снимает BOM сам | 5 /564 | старый raw-text oracle сохранён |
| D8 | tscn app снимает candidate BOM | 6 /563 | accepted candidate контракт заморожен |

Все8изменений строго последовательно,copyfilebackup/restore,точное совпадение
submitted/restored SHA и LF/CRLF;stderr0. D8 временно мутирует принятый app
только как доказательство,финальные59строк/bytes полностью восстановлены.
Полные failing IDs,mutant hashes/XML — `mutations.json` и `mutation-D*`.
Submitted SHA: shared decoder **56c397cfc17185d7**,gd core **1873e0a9e68787b7**,
verify app **f1506108e191583f**,tscn app **50f77ed6b766a95b**.

### Клиент и живой редактор

`tools/probe.py verify` и `gd_lint` на `res://only.gd` (BOM-only) —
exit0/stderr0,оба сообщают **«итоговый файл получился пустым»**,не false-clean.
gd result: code empty_file,line null,checked_bytes3;verify checkedtrue,
kinds[gd],auto_fixablefalse,api/headless остаются честно unavailable.

`pytest tests/py/live`: **3passed**,0failed/error/skipped,exit0/stderr0,
Godot4.6.3. Census2170files/83UID→2281/194→2170/83;удалены только111новых
UID по before/after списку. Исходные83UID SHA сохранены,других добавлений,
удалений или изменений после live нет. `live-proof.json` содержит полный список.

### Границы и обратная SHA-проекция

`final-proof.json`: **2116→2170files**,54added,18changed,2098unchanged,
removed0/unexpected0/debris0,83UID byte-identical. Новые49fixturefiles:
24case+25inputs;остальные5 — decoder,два testfiles,ADR и worksheet.
Из18changed:8обратно проецируемых code/corpusfiles,7сопровождающих docs,
3generated selfcheckreports. Для8файлов reverseSHA равен beforeSHA;
старые поля3BOMcases и manifestpins точно восстанавливают исходные bytes.

Все38старых C.9records byte-identical;65C.8cases/manifest/project и весь
tscn app/domain/read_inputs не изменены;source/scriptSHA/все inputpins проверены.
Текст функции lint_gdscript точно совпадает с исходным AST source segment;
классификация/messages/порядок/MAX_ERRORS/публичный API остаются прежними.
Старые19карточек,DiskFS,PathPolicy/schema/static gates,editor contract/executor,
auditor handoff и все остальные файлы вне whitelist — byte-identical.
Документы сохраняют неизменённые строки/EOL;WORKLOG и C.9worksheet сохраняют
исторический byte-prefix. Все168legacy fate-строк сохранены;обновлена только
численность существующей C.9integration строки и добавлены2новые строки.

Первый запуск doc-proof не учёл grouping SequenceMatcher: заменённая строка
test_verify.py и2новых соседних строки образуют replace1→3. Исправлен только
проверяющий скрипт с точным перечислением двух разрешённых путей;код/тесты
не ослаблены. Итоговый полный proof прошёл. Все скрипты/backups/XML/logs вне
addon в `C:/Users/Lich/AppData/Local/Temp/opencode/f1-bom-20261031/`.

## Следующее действие

Независимо переснять F1 файлы через старый read_project_file/_check_one_path, проверить2consumer/raw-text/candidate границы и свои мутации; только аудитор закрывает F1 и ставит delta stage7.

## Блокеры

Нет; разрешение пользователя ограничено F1. `_audit-handoff.md` — файл аудитора,
портер его не переписывает и долг закрытым по приёмке не объявляет.

## Приёмка аудитом (сессия 62, 2026-10-31)

Независимо, не по отчёту портера:

- пересъёмка корпуса с эталона: `reference_result` 62/62, проекция 56/56, порт против `expect` 62/62;
- дифференциал 1219 файлов `fixtures/**` в одинаковых временных копиях: 407 совпало, 809 границ
  (808 отказ политики `addons`, 1 лимит), разошлись 3 — `between.gd` (граница лимита) и две сцены
  со ссылкой на `addons/`; по BOM расхождений 0 (было 3, все три файла F1 перешли в «совпало»);
- свои мутации: X1 23, X2 4, X3 3, X4 4, X5 3, X6 15, X7 4, P8 2 — все красные, байты восстановлены
  (`source_text 56C397CFC171…`, `gd core 1873E0A9E687…`, `verify app F1506108E191…`, `tscn app 50F77ED6B766…`);
- числа: 2473 non-live (junit, 60.6 с, stderr 0), live 3 (25.3 с), collect 88 файлов,
  `snapshot_diff` 531/0, `gen_contract --check` 19, layers 497, limits 497/0, security ok,
  selfcheck 126/37 · 136/62 · 315/65; `test_source_text.py` 8 и `test_verify_bom.py` 13 — совпали с `tests-map`;
- неизменность: `tscn_lint/{app,domain/read_inputs}`, `formats/tscn.py`, C.8-корпус 65/65, 19 карточек;
- гигиена: 2170 файлов, `.gd.uid` 83 (111 сгенерированных удалены), debris 0.

F1 закрыт; этап 7.
