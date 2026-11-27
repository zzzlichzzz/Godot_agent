# editing.split_gd — C.14, read-only карта ссылок `split_gd_scan`

**Статус:** этап 7 — C.15 половина 2 принята аудитом 2026-10-31 (сессия 69); **C.16 (F6/F7 закрыты, F8 ретро-разрешён) принят аудитом 2026-10-31 (сессия 71).** Запись плана в `write_preview` — срез C.17.
**Обновлено:** 2026-10-31.
**Приёмки нет.** Финальные selfcheck/регресс/дифференциал/live зелёные; план — C.15.

## Цель

### История контрольных точек реализации (2026-10-31)

Свой `text/inventory/refs/core`, consumer fs Protocol и app: только существующие
`is_file/read_raw/list_files`, payload + `AppError`, без новых runtime bindings.
`split_gd_plan` не зарегистрирован. Исправлены расхождения полного native inventory
(в частности, const.text включает предыдущие комментарии); исправлены два ошибочных
ручных пина тестов: partial BOM native декодируется в пустую строку, а «no_refs»
содержит path-ссылку в plugin.cfg. Сырой корпус не переписывался.

Первый selfcheck: module/layers/limits/contract/security `ok`; 510 Python-файлов,
22 карточки/0 drift, unit **229 passed**, corpus **47/0**, вердикт **ok**, exit0/stderr0.
Независимая пересъёмка: raw34/34, отдельно projected34/34 и inventory34/34, 0 differences.
Мутации M1–M8 и P1–P3 обнаружены **11/11**, после каждой exact bytes/SHA restore.
P1: 229 unit green, только gen_contract --check red (`split_gd_scan.json`);
P2/P3: неизменённый lint_arch red; восстановленные unit/contract/layers green.
Пины и сырые логи: `independent-recapture.json`, `mutations-proof.json`,
`mutation-*-proof.json` во внешнем evidence. Широкий дифференциал ещё не прогнан.

`gen_contract --write`: 22 карточки; 21 прежняя байт-frozen, только split_gd_scan.json добавлена.
§9 context manifest: 1009B/SHA `f87ac054c47ab35cd3366de253ff07a919188a2a74b65ab23fe4903c04ae8f3e`
→1009B/SHA `4175bf3fa9d07d40280ed57668a823164dd1d1811a9267d4a6c11c78d482a3a9`;
только SHA case001, appended facts=0. Case001SHA
`08877f04d7f46ea7429744ecc149398e823549243c937673b3d0c5d15e8c0178`.
`inventory-byte-proof.json` подтверждает лишь разрешённые count/name/effect pins.
Patch-tool LF-дрейф на трёх CRLF-файлах восстановлен из точных ожидаемых byte transforms;
исторические EOL сохранены, никакой нормализации остальных байтов.

**Историческое следующее действие этапа 4:** полный non-live/collection/snapshots, selfcheck соседей,
дифференциал по 73 editor+plugin донорам и всем 58 C.14 fixture .gd, затем три live-теста.

**Уточнение контрольной точки:** полный non-live 3161 passed/3 deselected,
all snapshots 669/0; соседи check188/75, api_check206/52, gd_lint126/37,
tscn_lint315/65, class_api186/26 сохранены; все statics и клиентский probe exit0.
Первый wide: 73 real без расхождений, два fixture-несовпадения драйвера с новым
PathPolicy-контрактом: закрытый `addons/example/plugin.cfg` как сосед и донор
`.agent_history/ref.gd`. Первые raw/driver сохранены в `differential-first.*`.
Код/корпус не менялись: исправляется только внешний comparator — отдельный
native scan на policy-visible копии входов, не фильтрация полей ответа;
запрет донору `.agent_history` отдельно классифицируется как new-contract denied.
Corrected wide и ровно три live выполняются; сдачи этапа 6 пока нет.

**Первый круг завершён, затем IO edge fix (§2.5):** corrected wide146 old calls
(131 unrestricted +15 policy-visible),262 port,131 inventory,127 public payloads
+4 явных new-contract refusals, differences0/read-only. Live3passed/30.18s/pytest exit0;
первый cleanup-wrapper отказал из-за слишком узкого собственного UID-prefix.
Удалены строго163 witnessed new fixture .gd.uid (не только C.14), исходные83 bytes
сохранены; кроме трёх параллельно обновлённых porter-документов все байты exact.
`live-observed-delta.json`/`live-cleanup.json` и сами UID-witness bytes сохранены.
В финальном чтении §2.5 найден реальный IO edge: глобальный FileNotFoundError
не должен маскировать metadata/list failure как missing donor. Новый red:2failed/1passed;
not_found теперь только при исчезновении читаемого донора, прочие OSError internal.
Добавлены3теста; app72строки. 347файлов первого круга, старые golden/SHA/логи/код
сохранены в `round1/`. Следующее — полностью повторить Python gates/мутации/wide;
корпус/descriptor/fixture данные и принятый код не менялись, приёмки нет.

Первая половина механики возвращает карту ссылок на `.gd` внутри аддона:
инвентарь донора, категории и порядок попаданий, `hard_files`/`soft_files`.
Только чтение, идемпотентность, фактический паритет с `scan_refs`.
Основание: `_start-prompt.split_gd_scan.md`. Вторая половина
`split_gd_plan`/`plan_split`/`suggest_groups`, рендер, движковые таблицы,
`apply_prepared_split` и `.py`-пила — вне C.14, планирование остаётся C.15.
Портер не меняет `_audit-handoff.md` и не объявляет принятие/этап 7.

## Старый код

Эталон: `D:/vajno/Godot/тест-плагина-ии/addons/Godot_agent/godot_agent/`.
`python/godot_tools/split_gd.py`: 63421 B, 1333 LF/0 CRLF, SHA256
`18f05d10b8e875ed77040b8a47beb6ccbdb409b55d791ec0318466473969bfc7`.
Полные пины callers и старых тестов сохранены в `oracle-pins.json` внешнего evidence.
Старый git не изменён: только прежние `_ref2.log`/`_excl.log` untracked.

| Файл / строки | Что прочитано | Граница C.14 |
|---|---|---|
| `godot_tools/split_gd.py:57–75,119,127–166` | схема, лимиты, нормализация, чтение, sorted обход | scan-примитивы; не `_FALLBACK_*` |
| `godot_tools/split_gd.py:280–332` | `_parse_params` | чистый инвентарь |
| `godot_tools/split_gd.py:396–451` | отступы, `_code_skeleton`, `_balance`, комментарии | обнаружен конфликт исключения `_code_skeleton`, см. B2 |
| `godot_tools/split_gd.py:454–554` | весь `file_inventory` | заголовок, const/var/func, границы, ошибки |
| `godot_tools/split_gd.py:794–878` | весь `scan_refs` | предмет среза, сырой payload |
| `tools/agent_bridge.py:914–932,1035–1097` | `_split_target`, scan-ветвь `cmd_split_gd` | права `agent-dev`, `.gd`, собственный аддон; без пишущего пути |
| `tools/godot_agent_mcp.py:460–465` | MCP scan-обёртка | caller, не перенос транспорта |
| `main.py:4348–4366` | Flask scan-route | caller, не перенос Flask/STATE |

Текущие швы сверены: `DiskFileSystem.is_file/read_raw/list_files` уже существуют;
обход sorted-каталогов/имён совпадает с порядком старого `os.walk` после фильтра.
`normalize_rel` и `PathPolicy.deny_reason` не меняются. Новый порт/метод не нужен.
Прочитаны security invariants и ADR-0004/0006/0009/0010; чужой shared запрещён,
узкое исключение ADR-0010 не расширяется.

## Старые тесты

| Файл | Семейство / текущая судьба | Кейсы для будущей пересъёмки |
|---|---|---|
| `test_split_gd.py` | unit / corpus, tests-map:124 | path/source_read/call/doc, hard/soft, исключение донора, skip, missing; инвентарь, параметры, аннотации, незакрытая сигнатура |
| `test_split_gd_flow.py` | flow / corpus, tests-map:125 | read-only scan, чужой путь, не `.gd`; plan/apply остаются вне C.14 |
| `test_agent_bridge.py:2076–2114` | host-bridge / replaced, tests-map:136 | read-only, `agent-dev`, отказ `.py` и чужому донору; транспорт не переносится |
| `test_split_refactor.py` | unit / corpus, tests-map:126 | старая строка про обе пилы сохранена; `.py`-поведение вне этого среза |

Старые тесты только прочитаны, не копировались, не запускались и не менялись.

## Корпус

Снят до тестов/реализации: 34 actual-old кейса (68 вызовов) и 13 отдельно
обозначенных отказов нового контракта; `fixtures/corpus/editing/split_gd/`, готовые `.gd`-фикстуры в
`fixtures/projects/corpus/editing/split_gd/<вариант>/` с корневым `plugin.cfg`.
Сырой `reference_result` сохраняет `schema`, независимая проекция убирает только его.
Отказы нового контракта отмечаются отдельно, а не выдаются за ответы `scan_refs`.
Обязательны BOM/CRLF, все категории, skip, 1 MiB/4 MiB, лимит попаданий,
инвентарь/ошибки, права/пути, ближайший `plugin.cfg`, порядок и read-only SHA.

## Спецификация

`ToolSpec` из §2.1 записан в `tools.py`: имя `split_gd_scan`, `effects=read`,
`idempotent=True`, ошибки `invalid_input/not_found/denied`, лимит донора 4 MiB.
Инварианты: никаких записей проекта; policy до IO; недоступный сосед пропускается;
обход только внутри ближайшего аддона; donor excluded; 1 MiB на соседа;
counts полные, occurrences ограничены 1000; порядок и тексты как у эталона.

## Решения по ходу

| Дата | Решение / факт | Основание |
|---|---|---|
| 2026-10-31 | `schema` остаётся только в сыром эталоне | принято §2.1/§4, никаких других потерь payload |
| 2026-10-31 | `mention` недостижим, сохраняется с нулевым count | `relevant` требует имени или `call_re`; ветвь `call` исчерпывает второй случай |
| 2026-10-31 | Ровно 1000 попаданий: `truncated=False`; 1001+: `True` | фактическое `scan_refs:863–867`; неточная формулировка §3 не заменяет эталон |
| 2026-10-31 | Старые companion-разрешения C.11–C.13 не перенесены на C.14 | whitelist этого среза, ADR-0009/0010 исторические |

## Preflight-блокеры — сняты пользователем в §9 (сессия 66)

| ID | Конфликт / проверенное основание | Предлагаемое узкое разрешение |
|---|---|---|
| B1 | §1 разрешает case001, но замораживает его SHA в `context/gather/manifest.json`; новые `.gd` в обязательной `fixtures/projects` нарушат `test_scene_deps_facts.py:40–44` (сейчас 140 фактов, exact coverage) | Только SHA записи `001-all-sections` в context manifest; только append actual-old `script_facts` для новых `.gd` C.14 в scene_deps manifest. Все 140 прежних фактов и остальные поля/EOL сохранить, тест покрытия не менять |
| B2 | §1 исключает `_code_skeleton`, но обязательный `_balance:432–439` вызывает его; без удаления строк/комментариев неверно разбираются скобки | Разрешить чистый локальный helper `code_skeleton` в `domain/text.py` исключительно как зависимость `balance`/`file_inventory`, с фактическим поведением :400–429; никаких C.15 tokenizer/render/rewrite |
| B3 | §2.5 требует `app.call` возвращать Result; принятой сборкой `Agent.call:66–71` payload всегда оборачивается в `result.ok`, а Dispatcher классифицирует исключения. Локальный Result даст двойную оболочку и `ok=True` для отказа | Как у принятых модулей: `app.call` возвращает payload/поднимает `AppError`; наружу `Agent.call` возвращает единый Result. Runtime/protocol/kernel не менять |

Все три узких решения подтверждены новым §9: B1 — две точечные companion-правки;
B2/B3 — исправления промпта. Порядок: заморозить фикстуры → actual-old корпус и
append-факты → red-тесты → код. Дельты манифестов записываются в лист и WORKLOG.
Никаких иных companion-разрешений или обходов замороженных гейтов нет.

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-31 | 1. чтение, fresh backup, лист первым | старая scan-логика/кейсы/швы прочитаны; B1–B3 вынесены пользователю |
| 2026-10-31 | 2. фикстуры → корпус → append-факты | 34 native + 13 contract cases; 136 inputs/58 новых .gd; старые 140 фактов сохранены |
| 2026-10-31 | 3. red-тесты → ToolSpec | настоящий red exit1, затем read-only descriptor |
| 2026-10-31 | 4. код и первый selfcheck | 229 unit/47 corpus, ok; независимая пересъёмка 34/0; 11/11 мутаций обнаружены и восстановлены |
| 2026-10-31 | 4. IO edge red → fix → повтор | red2/1; финальные232unit,11мутаций/exactrestore; Python gates повторены |
| 2026-10-31 | 5. двойной корпус/широкий differential | raw34/34, independent projection34/34;127payloads+4contract refusals/0,73real+58fixture |
| 2026-10-31 | 6. живой прогон/непринятая сдача | ровно3live/0skips;163generatedUID individually cleaned/original83SHA frozen; независимый аудит следующий |

## База и сохранность

Внешний каталог: `C:/Users/Lich/AppData/Local/Temp/opencode/c14-split-gd-scan-20261031-a72f3e8b/`.
`before.json` и `backup/` — свежие байтовые копии всех файлов с проверкой SHA до/после;
`oracle-pins.json`, `preflight.json` — полные фактические пины.
Аудиторский §0 не переобъявлен: его числа исторические, полный baseline-suite не перезапускался.
Собственный fresh census: 2336 файлов, 83 UID, exact script-facts coverage 140.
От 2333 C.13 добавлены пользовательский C.14-промпт и два уже существующих файла
`fixtures/corpus/scene_model/scene_deps/project/024-skip_godot/.godot/other.gd` и
`fixtures/projects/minimal/.godot/editor/state.cfg`. Это не мои добавления;
они сохранены, дерево не подгоняется к 2333/2334 удалением чужих данных.
Промпт: 36087 B / SHA256
`dae008f093b8cdd0e0fcf2fbba0ca07ac0297e0a3c1ffbbef69d3dce4a8ed37a`.
Handoff: 68042 B / SHA256
`07e69386fabfe1f02b1c2f01ed01d6480bcfabb72bc5383451da399dac3c062c`.

## Проверки — исторический preflight до §9

Вердикт `python -B -X utf8 tools/selfcheck.py editing.split_gd`:

```text
selfcheck editing.split_gd
  module         not_implemented заготовка: RuntimeError: python.modules.editing.split_gd.module: нет MODULE (R-05)
  layers         ok              файлов 502, нарушений нет
  limits         ok              файлов 502, предупреждений 0
  contract       ok              артефактов 21, расхождений нет
  security       ok              нарушений нет
  unit           not_implemented тестов модуля нет: python/modules/editing/split_gd/tests
  corpus         not_implemented нет корпуса механики: fixtures/corpus/editing/split_gd
вердикт: blocked
```

Exit 2, stderr 0. Тогдашний отчёт сохранён в `resumed-backup/reports/selfcheck/editing.split_gd.json`;
stdout/stderr/exit сохранены во внешнем evidence. Это не зелёный отчёт реализации.
На этом историческом preflight non-live/snapshots/мутации/differential/probe/live не выполнялись.
Проверено: прежний WORKLOG-префикс 458883 B сохранён дословно (включая 4479 CRLF),
в PROGRESS изменена ровно строка 53, 115 строк сохранены.
Полный after-index и SHA каждого добавления/изменения: внешний `scope-verdict.json`;
до снятия корпуса все прочие preflight-файлы остаются замороженными.

## Список изменений preflight — исторический

1. Этот новый лист — первая правка репозитория.
2. `docs/PROGRESS.md` — только строка `editing.split_gd`: этап 1, B1–B3 и следующее действие.
3. `docs/WORKLOG.md` — только новая preflight-запись C.14, без изменения исторического префикса.
4. `reports/selfcheck/editing.split_gd.json` — фактический отчёт механики, не код.

На preflight реализация-заглушки, все принятые модули, kernel/substrate/tools/editor,
21 карточка, оба чужих `.godot`-файла, prompt и handoff остаются байт-в-байт.
Whitelist inventory-правки не делались: по §3.6 они следуют после работающего инструмента.

## Следующее действие

Независимому аудитору переснять raw корпус и проекцию, проверить широкий actual-old
дифференциал по всем73реальным донорам; только аудитор решает о принятии/этапе7.

## Продолжение после §9

Пользователь сам изменил только промпт и handoff, это защищённая дельта, не работа портера.
Новый промпт 40130 B / SHA256 `a3b2aa0428bef21f143b5f8648c55c393f4712f3910659ad097bdcb4a5ac1e38`;
handoff 68988 B / SHA256 `1e2afce013512b0e6e1498a3190a1396c962378b34fcb4cf7c347f5612029d5c`.
Сняты `resumed-before.json`/`resumed-backup/`: 2338 файлов/83 UID, все байты проверены.
Исторические `before.json`/preflight-логи не перезаписаны.
Actual-old корпус: 34 успеха/68 вызовов (два на кейс, SHA-дерево неизменно),
13 отдельно обозначенных отказов нового контракта, всего 47 кейсов/136 inputs.
Все 58 новых `.gd` заморожены, включая skip-фикстуры; никакого engine cache.
Сырой `reference_result` сохраняет `schema=1`, проекция удаляет только его;
`reference_inventory` отдельно снят `file_inventory` для проверки полного инвентаря.
Evidence: `capture_scan.py`, `capture-observations.json`, `fixtures-frozen.json`.

Companion §9 `scene_model/scene_deps/manifest.json`: 140 фактов сохранены, добавлено 58;
71682 B / SHA256 `3fe9c85f50eb4311e84298fd99315a85abfdf81b98fdc04109f7366c4dd2ce59` →
91626 B / SHA256 `349ba97d0bcb54209ab1e9b566546da52936ce7c6cff893204c1f18e52bcf53f`.
Все старые байты/прочие поля/EOL сохранены, `companion-facts-proof.json` содержит
actual-old extractor pin и все 58 фактов. Фикстуры после захвата не менялись.
Red: `red.stdout.txt`, exit1/stderr0, три ошибки collection: отсутствуют inventory,
refs и SCAN. До этого был ошибочный запуск внешнего runner (`run` как label);
он не проверял тесты, оставлен отдельным `run.stderr.txt`, не считается red.
После корректного red записан ToolSpec (никакой бизнес-логики).

## Мутационные доказательства — последовательно, без изменения гейтов

M1/M2/M3/M4/M6/M7/M8/P2 меняли `domain/refs.py`, M5 — `domain/core.py`,
P1 — `tools.py`, P3 — `app.py`. После IO edge все11 повторены: M1–M8 unit exit1;
P1 unit exit0 (232 passed)
и только contract exit1; P2/P3 дали layers exit1. После каждой мутации `finally`
восстановил исходные bytes и SHA; колонка «после» означает SHA, равный «до»,
а не только возврат зелёного теста. Golden-копии и сырые stdout/stderr находятся
во внешнем `mutation-golden/`, `mutation-*-proof.json`, `mutations-proof.json`.

| ID | SHA256 до | SHA256 мутации | После |
|---|---|---|---|
| M1 | `4e4334ad0bb47cf180639442b198800c0ad1375eb4879c86e2a7211c2f94df70` | `49f0f41d3397832d7ece234f5b91f163bfcf7ce37394babeee8cd4874ab6b20b` | exact |
| M2 | `4e4334ad0bb47cf180639442b198800c0ad1375eb4879c86e2a7211c2f94df70` | `54c37fb6c289381871b66d162e523a9d5b4240515ad0f8b2765a94aed88a5ab8` | exact |
| M3 | `4e4334ad0bb47cf180639442b198800c0ad1375eb4879c86e2a7211c2f94df70` | `49df8e8d3e89a7c2459c8515277d4d9d1bb739845091d199dce8a6ee2f8e3d52` | exact |
| M4 | `4e4334ad0bb47cf180639442b198800c0ad1375eb4879c86e2a7211c2f94df70` | `21e62e4783c5d06639309afca7d56bd996f6f9c9ab147e327d0bdc1de2ef59dc` | exact |
| M5 | `d839b0716c77fb7f564199682fcefe90c56a0ddc027b6a21999f006e0b01f9bc` | `abb37be85b89afd93e1b3b3271aefa47a3a35d0f453608e817903ac79241a276` | exact |
| M6 | `4e4334ad0bb47cf180639442b198800c0ad1375eb4879c86e2a7211c2f94df70` | `7d6f5252623f7c2e2358d483133c951623cd38cc5437c6f37cd1ac55f8a5537b` | exact |
| M7 | `4e4334ad0bb47cf180639442b198800c0ad1375eb4879c86e2a7211c2f94df70` | `1d5180a91e8b70376780629a8c1b04c2ec585f10ba712ad54044864a6768d547` | exact |
| M8 | `4e4334ad0bb47cf180639442b198800c0ad1375eb4879c86e2a7211c2f94df70` | `83c5a97ce533fe44c2e893a7df265c62286f4f5f66f7108f317516626cc1cd54` | exact |
| P1 | `5896d00755fc7567d127c51969e68d85be2d113b3274222d8f832cfd0dfbee04` | `78ddf84cb210e1dfa51e3e544b118c224ed9c1219e27221a1f207ab370f738e4` | exact |
| P2 | `4e4334ad0bb47cf180639442b198800c0ad1375eb4879c86e2a7211c2f94df70` | `122cd3ee508408e2e20b164b0bf82285177be6a8fe37bf9da258131051813581` | exact |
| P3 | `f8afcd3f535e2bfe4b68f58742e8c0cd8a23dea54f6bd1c85e6f2312d469925a` | `c55d174374b2fe22dcddbe679c9b548ea044bfab0d4b1bc9812034c6e0dd4374` | exact |

Повторный восстановленный unit232passed/contract22zero drift/layers510ok;
все11detected/exactbytes+SHA. Таблица выше — финальный круг; исходная таблица/логи
первого круга сохранены в `round1/`. 202 source/test/corpus/card/fixture файлов
совпадают с новой differential-copy; `submission.json` и `final-metrics.json`:
feature701строка, max141, app72/tools48, oracle63421B/fullSHA неизменён.
Полный повтор non-live/selfcheck/snapshots и wide выполняется; этап4, не принято.

## Финальная сдача C.14 — этап6, не принято

Проверяется только `split_gd_scan`; `split_gd_plan` не зарегистрирован/не реализован.
После IO fix фактический вывод `python tools/selfcheck.py editing.split_gd`:

```text
selfcheck editing.split_gd
  module         ok              editing.split_gd (split_gd_scan)
  layers         ok              файлов 510, нарушений нет
  limits         ok              файлов 510, предупреждений 0
  contract       ok              артефактов 22, расхождений нет
  security       ok              нарушений нет
  unit           ok              232 passed in 2.07s
  corpus         ok              кейсов 47, расхождений нет
вердикт: ok
```

Exit0/stderr0; collection3164/105files; non-live3164passed/3deselected/57.59s;
all snapshots669/0 (622прежних+47новых); security/layers/limits/contract/probe exit0.
Frozen соседние selfcheck: check188/75,api_check206/52,gd_lint126/37,
tscn_lint315/65,class_api186/26; F4 остаётся открытым, не исправлялся.
Actual-old corpus34rawcases/68initialcalls+13явных contract refusal cases;
independent recapture34raw/34projection/34inventory,0differences; schema удаляется
только из публичной проекции. 136inputs/58newgd frozen; mention0/1000False/1001True.
Финальный wide на isolated copied inputs:73editor+plugin+58fixture donors,
146native scans (131unrestricted+15policy-visible),262portcalls,
131full inventories,127payload comparisons+4явных contract refusals,0differences.
Обе raw версии сохранены, policy gate меняет входную копию, не поля ответа.
Driver6348B/SHA `50b1b52f3c2a53cbb937999bf0d1fd96d29f1fc058c105e2e639dc7f6b017e27`.
Чтение копий идемпотентно, полные деревья before/after неизменны;202submitted
source/test/corpus/fixture/card файлов совпадают с исполнявшейся версией.
Ровно3существующих live/30.18s/0skips/pytest exit0; GDScript/editor/bridge byte-frozen.
Первый cleanup-wrapper red и исправленный witness cleanup сохранены, не скрыты:
163newUID individually removed, original83UIDbytes frozen; никаких broad deletes.
§9 companions: context manifest только case001SHA (0facts appended), facts manifest
140oldfacts exact +58actual-old appended; before/afterSHA приведены выше.
Cards22/toolnames21; все21previouscards и editor_verbs v3/6primitives byte-frozen.
Feature701/app72/tools48/max141lines; новых runtime/adapter/shared edges нет.

Внешнее досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c14-split-gd-scan-20261031-a72f3e8b/`.
Основные доказательства: `capture-observations.json`, `independent-recapture.json`,
`mutations-proof.json`/golden/logs, `differential.json`/inputs/driver/rawlogs,
`regression-proof.json`/`final-*`, `submission.json`, `live-cleanup.json`/UIDwitnesses,
`inventory-byte-proof.json`, `record-byte-proof.json`, оба `companion-*-proof.json`, `scope-verdict.json`,
`final-census.json`; первый круг347файлов — `round1/`, первый wide red — `differential-first.*`.
Свежая база2338files (после пользовательского §9); final2533/83UID/debris0;
2312baseline файлов byte-frozen;195additions/26authorizedchanges/0removals;
prompt40130B/handoff68988B пользовательских версий frozen, WORKLOG old prefix frozen.
PROGRESS меняет только split row; parity остаётся skeleton; tests-map судьбы сохранены.
Коммитов/пушей нет; старый git сохраняет ровно два чужих untracked log-файла.
**Следующее действие:** независимый аудит; этап7/ported/приёмку портер не ставит.


## Приёмка аудитом (сессия 67, 2026-10-31) — половина 1

| Что | Мой результат |
|---|---|
| Пересъёмка корпуса живым `split_gd.scan_refs` | `reference_result` **34/34**, `reference_inventory` совпал |
| Независимая проекция (снят только внутренний `schema`) | **34/34** |
| Порт против `expect` | **47/47**, 13 отказов сверены по `kind`, ответы идемпотентны, sha256 проекта не меняется |
| Независимые инварианты payload | счётчики = гистограмма вхождений, донор вне `occurrences`/`hard_files`/`soft_files`, `hard ∩ soft = ∅`, `public_methods` = инвентарь без `_` |
| Дифференциал шире корпуса | каждый `.gd`-донор фикстур C.14 в своём проекте: 41 донор, 38 побайтово, 3 — задокументированные границы (`no_addon` без `plugin.cfg`; два файла `refusals` за 4 МиБ) |
| Свои мутации | M1 10, M2 9, M3 6, M4 3, M5 52, M6 10, M7 75, M8 30 — все красные, байты восстановлены; P1 юнит-зелёный и пойман только `gen_contract --check` (`fail: split_gd_scan.json`); P2/P3 — `lint_arch` |
| Гейты | non-live **3164**/0/0/0 (stderr пуст), live **3** (21.8 с), `snapshot_diff` **669/0**, contract **22**, selfcheck 232/47, слои/лимиты 510/0, security ok |
| Companion-правки | `gather`: только `001-all-sections` (sha совпал, 20 → 21 имя, дельта `split_gd_scan`/`read`); `scene_deps`: 140 прежних `script_facts` в прежнем порядке + 58 новых; в 7 тестах только строки инвентаря; 22 прежние карточки, `editor/` и принятые механики байт-в-байт |
| Гигиена | `.gd.uid` 83 → 246 → 83 (удалены ровно 163 сгенерированных), дерево 2529, debris 0 |

Долг прежний: **F4** (`tools/selfcheck.py:215` собирает юниты шаблоном `test_%s*.py`, поэтому
`engine_kb.class_api` считает 186 тестов вместо 128) — отдельный микро-срез.

## C.15 — вторая половина (`split_gd_plan`): preflight, 2026-10-31

**Статус:** этап 7 (половина 1 принята); C.15 в работе, preflight заблокирован
до корпуса/ToolSpec/тестов/реализации. Приёмки C.15 нет, статус C.14 не меняется.

### Цель и границы

Добавить read-only метаданные плана в тот же модуль, не меняя поведение scan,
47 принятых кейсов или его карточку. Запись/preview/WAL/rollback — C.16.
Основание: `_start-prompt.split_gd_plan.md`, 31309 B / 384 CRLF, SHA256
`34a9e0ff1cf43a7a64923e9ced4bdc7804bfd43c142c1c0ffdf8135ace71e8e1`.

| Старый код в `python/godot_tools/split_gd.py` | Граница переноса |
|---|---|
| `tokenize:196`, `_prev_token:272`, `_collect_locals:335`, `_ENGINE_VIRTUALS:388` | Новые чистые tokens/collect; `parse_params` уже есть в принятом inventory, не дублировать |
| `suggest_groups:557`, `_normalize_groups:898` | Авто-группы, валидация и фактический порядок функций |
| `_engine_api:583`, `_FALLBACK_METHODS:79`, `_FALLBACK_PROPS:105` | Только classes из существующего `api_cache.snapshot()`, без IO в domain |
| `_apply_edits:624`, `_rewrite_body:640`, `_downgrade_panel_inference:714` | Нативное переписывание без улучшений |
| `_render_static_sig:765`, `_render_wrapper:780`, `_render_module:932` | Нативный рендер и счёт строк; content остаётся внутренним |
| `plan_split:955`, `_public_plan:1138` | Чистый план и безопасная публичная проекция |
| `_make_split_gd_prepared`, `apply_prepared_split`, `_godot_check` | Не переносить: воронка записи/C.16 |

Старые кейсы прочитаны в `python/tests/test_split_gd.py` (29322 B),
`test_split_gd_flow.py` (5931 B), `test_agent_bridge.py:2076–2135`,
нормализация — `python/tools/agent_bridge.py:1022`. Старые тесты не запускались,
их код не копировался. Строки tests-map существуют, судьбы не менялись.

### База обратной проекции

Внешнее досье:
`C:/Users/Lich/AppData/Local/Temp/opencode/c15-split-gd-plan-20261031-preflight-88e4b/`.
`before-bytes/` — свежие байтовые копии всего дерева; `before.json` содержит
bytes/SHA/EOL каждого файла, `accepted-pins.json` — модуль/корпус/карточку scan.
До правок документов `repository_unchanged=true`; ни чужие, ни аудиторские
изменения не откатывались. База тестов §0 не пересчитывалась.

| Принятый файл (путь относительно модуля, если не указан полный) | B | SHA256 |
|---|---:|---|
| `app.py` | 3197 | `f8afcd3f535e2bfe4b68f58742e8c0cd8a23dea54f6bd1c85e6f2312d469925a` |
| `tools.py` | 2274 | `5896d00755fc7567d127c51969e68d85be2d113b3274222d8f832cfd0dfbee04` |
| `module.py` | 442 | `f1e5aa9a42b3ddc8380789b175144b821903443891698a942647d8d34a833ffe` |
| `ports.py` | 493 | `28ace2976817a203a20d2ab702caad962f0dd1af6a238ecdaf5ead680493dbb8` |
| `domain/core.py` | 588 | `d839b0716c77fb7f564199682fcefe90c56a0ddc027b6a21999f006e0b01f9bc` |
| `domain/inventory.py` | 5419 | `bb01fb0b14db003f660d6e225f446a538542f0a08566436b42c81d8b790af474` |
| `domain/refs.py` | 3076 | `4e4334ad0bb47cf180639442b198800c0ad1375eb4879c86e2a7211c2f94df70` |
| `domain/text.py` | 1744 | `6f0c5a835330e6bce10aa096ea1990533f30d085629a719ee7c796eb5a43591c` |
| `fixtures/corpus/editing/split_gd/manifest.json` | 30011 | `e928076525d9328aa4d47ba05b48958c4a570b8a880d158ddd939c1a38489320` |
| `contract/capabilities/split_gd_scan.json` | 3283 | `bebc6c414bb0fea96e81f60d98082066a015f6b5ed1f3f5d81249004dfa75c17` |

Все 47 case bytes/SHA сохранены отдельно в pin-файле. Замороженные гейты,
kernel/substrate/editor/соседи и 22 карточки входят в полную byte-базу.
WORKLOG до append: 479815 B, 4479 CRLF / 5487 LF, SHA256
`d483f053fae63fa92e456a6e05e4756bb5ddc4c5ba65507dea2c2178e1329edb`.

### Фактические пробы и решения по ходу

Живой oracle pin совпал: 63421 B / 1333 LF / 0 CRLF, SHA256
`18f05d10b8e875ed77040b8a47beb6ccbdb409b55d791ec0318466473969bfc7`.
На внешнем мини-проекте сделаны два одинаковых `plan_split` и `_public_plan`:
планы идентичны, SHA дерева до/после совпал; Godot не запускался. Это preflight,
не обязательный корпус >=22. Сырые ответы, включая content, сохранены только
во внешних `native-plan-raw.json`/`native-public-raw.json`.

Публичная проекция §2.1: оставить `schema`, `kind`, `donor`, `donor_sha256`,
`newline`, `target_lines`, `groups`, `modules`, `wrappers`, `warnings`, `stats`.
Удалить абсолютные `addon_dir/project_root/donor_abs` и `donor_content`;
`modules.content` удаляет сам `_public_plan`. Модуль: `rel/const/funcs/lines`;
wrappers: список `name/module/await`; stats: `moved/modules/donor_before/donor_after`.
Алиасы `path`, `lines_before/lines_after` и integer wrappers не выдумывать.
Вход funcs `beta,alpha` вернулся в source order `alpha,beta`; это сохраняется.

| Блокер до корпуса | Свидетельство | Нужное решение |
|---|---|---|
| B1: scan-тесты несовместимы с добавлением инструмента/кейсов | `tests/py/contract/test_split_gd_scan_contract.py:17` пинит `TOOLS == (SCAN,)`; `tests/py/integration/test_split_gd_scan.py:12,39,58` грузит все numbered cases и пинит 136 inputs/fs-only MODULE | Узкое разрешение на фильтр scan-кейсов/inputs с сохранением 47/34/136 и пины двух tools/двух ports; остальные проверки неизменны |
| B2: пустой каталог занимает будущий `.gd`-путь | Живой `plan_split` бросает `StaleSplitGdError("целевой модуль уже существует: part_one.gd")`; текущий fs: is_file false, list_files не видит каталог, read_raw даёт PermissionError/EACCES | Решение пользователя о границе C.15 либо отдельное разрешение на metadata seam; новый метод/порт и изменение адаптера сейчас запрещены |
| B3: §4.2 расходится с реальным fallback | Кэш с непустым Node, пустыми methods и одной property: `_engine_api` вернул оба `_FALLBACK_*`, свойство отброшено; возврат цепочки только при methods truthy | Подтвердить фактический base -> Control -> fallback при отсутствии методов, даже если classes непусты |

Внутри разрешённой папки также потребуется сугубо механический scan-фильтр в
`tests/corpus.py` и замена имени plan на действительно неизвестное имя в
`tests/test_app.py:116` (инвариант unknown_tool не ослабляется). B1-внешние файлы
пока не правились. Manifest предполагается расширять append-only cases/inputs,
не меняя 47 старых case entries и 136 старых input facts; это уточнить вместе с B1.
`StaleSplitGdError` не наследует `SplitGdError`: первый внешний probe завершился
exit1 из-за узкого except, сохранён как `preflight.py`; отдельный continuation
`preflight_finish.py` дал exit0. Ошибка проб не скрыта, репозиторий не менялся.
Итог наблюдений — `preflight-proof.json`.

### Разрешённые записи и следующее действие

Текущий шаг меняет только этот append-раздел, split-строку `docs/PROGRESS.md`
без смены этапа 7, append в `docs/WORKLOG.md`. Корпус, fixtures, тесты,
ToolSpec/production, parity/tests-map, companions, reports и handoff не менялись.
После реализации разрешённые companions строго по §1: context name/read/count
+ SHA case001; append-only 198 script_facts; семь inventory count/list pins;
только split-строка parity. Дополнительные B1-исключения пока не разрешены.
`selfcheck` на этом preflight не запускался, verdict реализации не заявляется;
non-live/snapshot/mutations/wide/live C.15 не выполнялись. F4 не тронут.

**Следующее действие:** получить решения B1/B2/B3 до корпуса и первой строки кода;
после согласования — freeze fixture copies и actual-old capture >=22 кейсов с 101.

### Решения пользователя после preflight, 2026-10-31

- **B1 разрешён узко:** внешний scan contract — только inventory pin;
  внешний scan integration — только scan-only filters и tools/ports pins.
  Проверки 47 scan-кейсов, 34 native и 136 прежних inputs сохраняются;
  manifest расширяется append-only новыми plan facts. Разрешение записано,
  сами тесты/manifest пока не изменены: инструмент ещё не реализуется.
- **B3 подтверждён:** сохранять фактический base -> Control -> fallback при
  отсутствии методов, в том числе при непустых classes. Формулировка §4.2
  уточнена этим решением; адаптер и другие механики не меняются.
- **B2 — сохранить стоп:** native parity и текущие запреты остаются.
  Отдельный metadata seam пока не разрешён. C.15 приостановлен до корпуса,
  ToolSpec, тестов и кода; отклонение по пустым каталогам не разрешалось.

Изменения после этих ответов снова только документационные. Нет нового
selfcheck-вердикта C.15 или заявления о готовности к аудиту; accepted scan,
корпус/fixtures/карточки/frozen gates и F4 не менялись.

**Актуальное следующее действие:** отдельно согласовать read-only metadata seam,
различающий отсутствующий и занятый каталогом целевой путь; до такого разрешения
C.15 не продолжать. B1/B3 закрыты решениями выше, стоп остаётся только по B2.

### C.15 возобновлён: узкий fs.exists (2026-10-31)

Аудитор снял B2 в §9 обновлённого промпта: 36613 B, 438 CRLF,
SHA256 0f83f9a5480cef1e52aa5f0d73789c9eb9b10b32fe4615ea53d55f599eb9d542.
Новый handoff 72219 B / 422 CRLF сохранён без правки. Свежая база всех 2534
файлов: внешний dossier `resume-01/before.json` + `before-bytes/`; исходные
preflight/failed artifacts и C.14 dossier не перезаписывались.

ADR-0011 фиксирует один metadata-шов, один production-вызов будущего plan,
неизменные is_file/list_files/read_text/read_raw/_resolve и отсутствие новых
режимов ФС. _resolve возвращает str: отдельным ответом пользователь разрешил
эквивалентное os.path.exists(self._resolve(rel_path)), без нового импорта.
MemoryFileSystem не правился; F5 не оформлен портером как принятый долг.

Красный substrate-тест до метода: 5 failed / AttributeError (exists-red,
3.107 с, stderr 0). Новый exists + старые проверки is_file: 13 passed.
Отдельная мутация exists -> is_file: 1 failed, 4 passed / 0.36 с,
красный именно реальный пустой module.gd-каталог; байтовое восстановление
доказано. Инструмент patch удаляет старую пустую EOF-строку: два неудачных
byte-proof сохранены, затем EOF восстановлен бинарно после проверки golden.
Все прежние байты disk_fs после удаления нового метода равны старым.

- disk_fs до: 3628 B,
  `8d2eec86bc9cfaa3459a7579bf998f8935236207df904dc593f75e5fa7c4c1b2`;
- после: 3987 B,
  `4224f2d041759db10e9a662900202feb718c5ad2d422a2e0fe6cc58306425f20`;
- proof: `resume-01/exists-byte-proof.json`, golden-final и отдельные red logs;
- restored seam tests: 13 passed in 0.48s, stderr 0.

Selfcheck шага (237 = прежние 232 + 5 новых substrate-тестов; scan не менялся):

```text
selfcheck editing.split_gd
  module         ok              editing.split_gd (split_gd_scan)
  layers         ok              файлов 510, нарушений нет
  limits         ok              файлов 510, предупреждений 0
  contract       ok              артефактов 22, расхождений нет
  security       ok              нарушений нет
  unit           ok              237 passed in 3.85s
  corpus         ok              кейсов 47, расхождений нет
вердикт: ok
```

`seam-selfcheck-utf8`: exit0 / 28.678 с / stderr0. Первый selfcheck также
вернул0, но внешний runner упал при печати cp1251; обе записи сохранены.
Изменены только disk_fs, consumer ports, новый substrate test/ADR, эти
записи и собственный selfcheck report. Никакого plan corpus/ToolSpec/code пока.

**Следующее действие:** actual-old capture >=24 plan-кейсов от101, включая
existing_module_file/dir с дословным отказом; заморозить inputs и сырые
generated content до спецификации/red-тестов/кода C.15. Не принято.

### C.15 корпус → спецификация → красные тесты (до plan-кода)

`resume-01/capture_plan.py` (17512 B,
`da4b8623c82dd132443d0572bc9dc55088f087c1f91185b1ada296f8ecc2c013`):
55 кейсов101–155; 46 native observations/92 calls = 25 success +21 native refusals,
9 явных contract boundaries; 170 новых input files. Вызваны actual-old plan_split
и _public_plan на frozen external copies, cache reset на каждый вызов, write/Godot
sentinels; exact equality двух ответов и файлового/каталожного дерева до/после.
Raw reference_result хранит всё generated content и service paths; публичный
expect независимо спроецирован из actual _public_plan. Дополнительно сняты
token offsets/locals/inventory/engine sets. `capture-proof.json`: exit0/2.669s.

Особо:139-existing_module_file и140-existing_module_dir — native StaleSplitGdError,
дословно «целевой модуль уже существует: editor/part_one.gd», проекция invalid_input.
Есть auto/missing/zero/100/5000/99/5001, groups2/3/single, virtual/private/static/await,
multiline/default/export/lambda/panel/inference, module/donor1500/2000 thresholds,
cache empty/chain/Control/cycle/nonempty-no-methods, native conflicts/refusals,
BOM/CRLF/CR, nearest addon, non-gd/no-plugin/policy/missing/raw-limit.
Старые47 case facts/136 input facts и файлы сохранены. Manifest append-only
расширен cases/inputs + plan_capture (прежний reference/capture/projection не менялся).

Спецификация после capture: SCAN + его ARGS/RESULT сохранены; добавлены PLAN_ARGS,
PLAN_RESULT и PLAN. Эти имена избегают изменения прежних scan symbols. Native
safe payload: schema/kind/donor/donor_sha256/newline/target_lines/groups/modules/
wrappers/warnings/stats; modules rel/const/funcs/lines; wrappers list{name,module,await};
stats moved/modules/donor_before/donor_after. Без выдуманных lines aliases/path/
integer wrappers и без content/service paths. P1 удаляет wrappers из PLAN_RESULT.required;
M8 мутирует stats.donor_after, не несуществующие aliases. Тексты renderer сохраняют
native quirks, включая static static func; universal newline native делает newline LF
и donor_sha256 от decoded text, не от raw BOM/CRLF bytes.

Пользователь отдельно подтвердил границу Dispatcher/schema до app.call:
5001/non-int/empty_funcs -> штатный invalid_input схемы, сравнение по kind;
99/unknown function/existing targets и другие schema-valid native refusals — точный
native-текст. Runtime и ограничение maximum5000 не расширяются/не обходятся.
Raw native отказ empty_funcs остаётся в корпусе и проверяется чистым domain-тестом.

Новые тесты собственные, старый test code не копировался/не выполнялся:
tokens/collect/engine/render/core_plan/app_plan + helper; внешний plan contract и
integration. Internal scan corpus loader теперь scan-only, его47cases не менялись.
Первый red runner потерял importlib при override addopts: неправильные collection
ошибки сохранены; исправленный запуск с importlib: 4 missing-domain errors;
отдельный core/app/integration/contract:136failed/75passed in3.36s, stderr0.

Selfcheck до plan-кода, ожидаемо красный (mismatch specification/ModuleSpec):

```text
selfcheck editing.split_gd
  module         not_implemented заготовка: RuntimeError: python.modules.editing.split_gd.module: provides_tools ('split_gd_scan',) != TOOLS ('split_gd_scan', 'split_gd_plan')
  layers         ok              файлов 517, нарушений нет
  limits         ok              файлов 517, предупреждений 0
  contract       fail            лишний артефакт: split_gd_scan.json
  security       fail            код 1
  unit           fail            4 errors in 1.07s
  corpus         not_implemented нет кейсов для 'editing.split_gd'
вердикт: fail
```

Все красные/промежуточные evidence сохранены, это не финальный verdict/приёмка.
**Следующее действие:** реализовать tokens → collect (reuse inventory.parse_params)
→ engine → render → core → app, consumer snapshot и additive ModuleSpec; затем green.

### C.15 реализация и независимый recapture; новый стоп S1

Реализован только read-only plan: новые domain/tokens.py, collect.py, engine.py,
render.py; additive domain/core.py; новый plan_io.py и изменения app.py/tools.py/
module.py/ports.py. App76 строк, layers/limits522/0. Accepted inventory.py/refs.py/
text.py не правились. Module version0.1.0 сохранена, tools(scan,plan), ports(fs,api_cache).
ApiCache.snapshot вызывается один раз, не classes/version; единственный новый
consumer вызов `fs.exists` — проверка будущего module_rel в plan_io. Исходные три
Path.exists в чужих module tests остаются нетронутыми; grep именно fs.exists =1.
Никаких project writes, Godot, runtime/PathPolicy/bootstrap изменений.

Первые module+plan contract/integration green:524passed/4.82s, exit0/stderr0.
Дополнительные собственные проверки: inclusive4MiB, исчезающий donor, native group
refusal до snapshot, exists до preload-conflict, протокол snapshot реального adapter.
SCAN compatibility: только прежний unknown-tool pin заменён на split_gd_missing;
internal corpus scan-only. Разрешённые внешние scan contract/integration filter/pins
сохранены с checks47cases/34native/136inputs. Отдельный scan+exists run:71passed/3.49s.

Разрешённые companions: семь inventory-test name/count pins; context001 count22/
split_gd_plan:read и только его SHA в manifest; scene_deps append54 native .gd facts
после исходных198 (всего252), остальные данные/порядок/байты/EOL сохранены.
Внешний companions-proof.json содержит полный reverse-byte proof. First/finish1
ошибки доказательства сохранены; причина — инструмент patch убирал EOF blank и
смешивал EOL. Binary repair только этих байтов после проверки точного нового
текста вернул исходные EOL/EOF, без дополнительных смысловых правок.
Frozen scene_deps coverage test неизменен:298passed/1.67s.
Context manifest:4175bf3fa9d0 →69b6a6a35c7c; scene_deps:349ba97d0bcb →1b8780f63d04.
gen_contract --write/--check:23cards; прежние22cards byte-identical, новый только plan.

Независимый script resume-01/independent.py не импортирует capture/projection/tests:
повторно actual-old plan_split/_public_plan, gd_api_cache reset на каждый вызов,
positive safe field selection, полный raw-content compare и tree equality.
Round2:55cases/92native calls/25raw+25public comparisons/21native refusals/9boundaries,
0differences, exit0/2.170s/stderr0. Первый recapture сохранён: compare остановился
на144, потому что внешний rebase ошибочно нормализовал native mixed separators
в donor_abs. Исправлен только внешний rebase service paths, корпус/порт не менялись.

Implementation selfcheck (exit1/47.429s/stderr0):

```text
selfcheck editing.split_gd
  module         ok              editing.split_gd (split_gd_scan, split_gd_plan)
  layers         ok              файлов 522, нарушений нет
  limits         ok              файлов 522, предупреждений 0
  contract       ok              артефактов 23, расхождений нет
  security       fail            код 1
  unit           ok              600 passed in 7.25s
  corpus         ok              кейсов 102, расхождений нет
вердикт: fail
```

**S1 — новый стоп, не долг и не разрешённое исключение.** Frozen
tools/security_audit.py:54–57 считает каталог с суффиксом .gd файлом; check_secrets:146
вызывает read_bytes на обязательном empty-directory fixture
fixtures/projects/corpus/editing/split_gd_plan/existing_module_dir/editor/part_one.gd.
Отдельный implementation-security: exit1/PermissionError, полный traceback сохранён.
Существующий covering scene_deps test уже использует is_file и зелёный; проблема
только в замороженном security gate. Каталог нельзя убрать/скрыть, иначе пропадёт
обязательная проверка native os.path.exists vs is_file. Gate/F4/handoff не правились.

**Следующее действие:** получить отдельное разрешение на единственный is_file-filter
в security_audit.files и новый red-test обхода каталога, либо сохранить стоп.
До решения wide differential, M1–M8/P1–P3, final regression/live/census не выполняются.
C.15 не готов к независимому аудиту, не принято; accepted C.14 и stage7 не меняются.

### C.15 S1 снят отдельным разрешением; wide green

Пользователь разрешил только is_file-filter в tools/security_audit.files и новый
tests/py/security/test_split_gd_security_files.py. До gate-кода red:2failed/1passed
in0.26s (каталоги ошибочно в file list/PermissionError); после3passed/0.12s.
Проверка обычного secret-bearing файла рядом с каталогом продолжает обнаруживать
SEC-06; вложенные обычные файлы/прежние skip dirs/absent base сохранены.
Security gate:10831B/2cf0d7f6b1affd08e4d12b1a6ed92ef9be2e3649719b5cd37720912df6d5cf94
→10885B/77956be3be9f295b3d4d50de00af16a1051a0745d474f566a44a7c6536115c4d.
Reverse-byte proof удалением только двух строк восстанавливает полный old bytes;
EOL/EOF сохранены binary repair. Первый proof предполагал LF, упал на CRLF и сохранён.
Это новое узкое разрешение, не изменение прочих frozen gates/F4/PathPolicy/runtime.

Selfcheck после S1:exit0/47.427s/stderr0, moduleok/layers522/limits0/contract23/
securityok/unit600passed9.29s/corpus102/0/verdictok. Не финальная приёмка.
Independent wide на138 реальных fixture donors, auto+explicit в двух cache modes:
552 native calls/1104 port calls/368 full generated-content comparisons+368safe
payload comparisons/176native refusals/8explicit raw-limit boundaries/0differences;
exit0/22.187s/stderr0. Каждая пара port idempotent, file/directory SHA tree unchanged,
external state absent; actual-old cache reset/read-only sentinels сохранены.

**Следующее действие:** отдельные M1–M8/P1–P3 и повторный exists→is_file mutant с
native directory corpus, точное восстановление байтов; затем final regression/live.

### C.15 отдельные mutations, exact restoration

Досье resume-01/mutations/: общий golden8files, в каждом M1–M8/P1–P3/E1/E2
свои mutant/golden bytes, команды/полные stdout+stderr/elapsed/proof SHA256.
Каждый mutant единственный активный, перед следующим все8golden files byte-exact.
После каждого M:529passed; после P1 contract23green; после P2/P3 layers522green.

| mutant | изменение | red unit | public corpus disagreements |
|---|---|---:|---:|
| M1 | убрать ENGINE_VIRTUALS filter | 11 | 5 |
| M2 | target0/default100 вместо1100 | 25 | 23 |
| M3 | убрать native engine fallback | 43 | 0 |
| M4 | reverse modules | 10 | 5 |
| M5 | prettify literal warnings | 8 | 4 |
| M6 | убрать lambda/function local params | 5 | 1 (116lambda_panel) |
| M7 | skip inference downgrade | 15 | 0 |
| M8 | stats.donor_after+1 | 50 | 25 |

M3/M7 public metadata объективно не отражает изменения generated content;
их ловят native sets/full raw strict tests, не выдуманный content в публичном
контракте. Это ожидаемая причина сохранения полного reference_result.
P1 убирает wrappers из PLAN_RESULT.required: unit529/corpus102/layers522 green,
**только gen_contract--check red** (устарел split_gd_plan.json), после restore23green.
P2 importos domain/render: lint_arch red IO-импорт; P3 foreign verification.shared
edge app: lint_arch red чужой модуль. Frozen lint_arch/selfcheck не менялись.
E1 exists→is_file:2failed/60passed (substrate real directory и corpus140directory),
restore62passed. E2 убрать разрешённый gate file-filter:2failed/1passed,
restore3passed. Disk3987B/SHA4224f2d041759db10e9a662900202feb718c5ad2d422a2e0fe6cc58306425f20
и gate10885B/SHA77956be3be9f295b3d4d50de00af16a1051a0745d474f566a44a7c6536115c4d
восстановлены byte-exact, включая исходные EOF/EOL.

Неудобные артефакты сохранены: M1 first corpus CLI--module ошибочен/exit2, не
засчитан red; корректный отдельный M1-round2 даёт5diff. M4 первая guessed patch
не применилась атомарно. M6 первая patch с неверным indent отклонена runner до
тестов, mutant M6-first-indent.py сохранён; corrected proof успешен.
Restored selfcheck:exit0/44.638s/stderr0; moduleok/layers522/limits0/contract23/
securityok/unit600passed7.56s/corpus102/0/verdictok. C.15 не принято.

**Следующее действие:** полный non-live/collection/snapshot, неизменные соседние
selfchecks с сохранением/возвратом их report bytes, ровно3existing live, census/scope.

### C.15 final non-live/snapshot/neighbors

Full regression:3589passed102.56s, wall106.108s/exit0/stderr0. Delta от accepted
3164 =368 новых split/exists tests +3security +54native script-facts parameters;
не изменения чужого поведения/числа neighbor units. Snapshot:724/0 (669+55),
split102/0 (47scan+55plan), wall91.537s/exit0/stderr0. Полные команды/логи сохранены.
Collection:3589tests4.93s/wall6.745s/exit0/stderr0; unique-file census из полного
лога будет записан в final scope. Прежние neighbor selfchecks unchanged:
check188/75, api_check206/52, gd_lint126/37, tscn_lint315/65, class_api186/26 (F4
selector не менялся). Все exit0/stderr0; generated neighbor reports отдельно в
external neighbors/, original accepted report bytes возвращены строго byte-exact.

**Следующее действие:** ровно3existing live с per-file UID before/after archive и
возвратом только собственных generated UID; затем probe/final hashes/scope/census.

### C.15 live round1: остановка L1 (конфигурация внешнего проекта)

Существующие3live tests запущены неизменёнными с Godot4.6.3: harness passed,
два editor tests failed, `port.json` не появился75s; total2failed/1passed153.04s,
pytest stderr0. External wrapper exit1 после assert readiness, полный first-round
stdout/stderr/run/delta сохранены в resume-01/live/. Это не green live evidence.
У внешнего `D:/vajno/Godot/agent-rebuild/project.godot` всего3строки application/
config/name="c14d", **нет editor_plugins enabled**; редактор стартовал/загрузил layout,
но plugin не активирован. Ни project.godot, ни editor/plugin/live tests не исправлялись.

Failed-run UID cleanup: только163новых `.gd.uid`, наблюдённых after-minus-before,
проверены по SHA/формату/неизменному исходному script, скопированы external
live/generated-uids/ и удалены по одному; весь addon file+directory tree возвращён
byte-exact. UID83→246→83, accepted83UID untouched, required empty module.gd dir intact.
`failed-live-cleanup` exit0/stderr0; неудобный live failure не скрыт/не заменён.

**Следующее действие:** получить отдельное разрешение на временное включение
plugin в *внешнем* project.godot с byte-backup/exact restore, затем повторить ровно3
existing tests; без этого C.15 не готов к аудиту. Selfcheck600/102ok не означает liveok.

L1: пользователь отдельно разрешил temporary editor_plugins enabled во внешнем
project.godot, fresh byte-backup и обязательный exact restore; original live round1
и UID archive остаются. Повтор — неизменные3tests, production/editor/bootstrap frozen.

### C.15 live round2:3 passed, внешний setup restored

После отдельного разрешения: ровно3existing tests passed28.00s, child29.399s,
stderr0, Godot4.6.3; `final-live-round2` wrapperexit0/33.141s. Temporary plugin
enabled только во внешнем project.godot. Original SHA
`a5db948a35e499b62cd67bb223963317cad38e80de5c9361a3d74b85e9cb64e2`,
temporary SHA `08b28a6a798f32ef30d146c15eada361fb000f8109fcc7a4124f0bd8b43a7b68`;
config original restored byte-exact, temporary scene удалена existing tests.
Только163witnessed UID archived/removed, UID83→246→83; addon files+dirs byte-exact.
First-round2failed/1passed и отдельный cleanup proof сохраняются, не заменяются
новым green. Полные logs/proof/project byte backups: resume-01/live-round2/.

PROGRESS stage7 относится исключительно к принятому C.14. C.15 остаётся unaccepted;
parity меняется только split row, tests-map — только новые уточнения к split rows
без удаления прежней судьбы/history. Следующее — final scope/census/probe/selfcheck.

### C.15 готов к независимому аудиту, не принято — итоговый пакет

C.14 scan принят сессией67, его stage7/history/47cases/136inputs/card сохранены.
C.15 — additive read-only plan, НЕ принят/НЕ новый ported. Воронка записи,
write_preview(action split_gd)/write_apply/journal/rollback/Godot-check — C.16.

| Проверка | Фактический результат |
|---|---|
| Actual-old capture | 55cases101–155;92calls;25success+21native refusal+9contract;170inputs |
| Independent recapture round2 | 92calls;25fullraw+25independent safe projections;21refusal;0diff |
| Wide fixture differential | 138donors;2cache modes;auto/explicit;552native/1104port;368raw+368public;176refusal/8boundary;0diff |
| Full non-live | 3589passed102.56s;wall106.108s;stderr0 |
| Collection | 3589tests/115unique files;4.93s;wall6.745s;stderr0 |
| Full snapshot | 724/0=669+55;split102=47scan+55plan;wall91.537s;stderr0 |
| Live round2 | exactly3existing passed28.00s;wall29.399s;stderr0;project+addon tree byte-restored |
| Final selfcheck | 600passed5.92s;102corpus;verdictok;wall41.610s;stderr0 |
| Final gates | contract23/0;arch522/0;limits522/0;securitySEC-01…08/20ok;all exit0/stderr0 |
| Neighbor selfchecks | check188/75,api206/52,gd126/37,tscn315/65,class186/26;reports exact restored |

Full non-live delta от accepted3164:368split/exists+3new security+54native fact parameters.
Historical accepted audit collection/census pins НЕ пересчитываются: нынешние115files —
unique node-ID file paths из явно записанного collect command; полный byte-walk
2534fresh baseline→2777, +243/-0/28changed/2506unchanged. Исторический audit census
2529/2530 остаётся историей, не подменяется этим отдельным полным обходом.
UID83 (оба live83→246→83), generated debris0; accepted skip-dir fixture __pycache__/ref.gd
не удалялся как мусор. Porting24worksheets/25сREADME;prompts34;ADR11;
23cards/24JSON;gather22names/plan:read;6verb markers/version3;app76/tools102/module1631lines.

Final selfcheck output:
```text
selfcheck editing.split_gd
  module         ok              editing.split_gd (split_gd_scan, split_gd_plan)
  layers         ok              файлов 522, нарушений нет
  limits         ok              файлов 522, предупреждений 0
  contract       ok              артефактов 23, расхождений нет
  security       ok              нарушений нет
  unit           ok              600 passed in 5.92s
  corpus         ok              кейсов 102, расхождений нет
вердикт: ok
```

Probe через штатный CLI: target0→1100,4moved/1module,4wrapper records,
stats donor23→27; payload без generated content/absolute servicepaths. Отдельный
occupied-directory probe exit1/stderr0/invalid_input, дословно:
`целевой модуль уже существует: editor/part_one.gd`. Files/dirs/inputs SHA неизменны.

Отдельные mutation proofs (после КАЖДОГО all8golden SHA exact, restored-green):

| Mutation | Golden SHA256 | Mutant SHA256 |
|---|---|---|
| M1 | `457a2c9fdfbb3165faa544e086ce5d7b6205a30280f7a5de3cba114268f801bc` | `058aeee379a278243e39e6a6570e4cff47575af671137fa98d30384d399d9dcb` |
| M2 | `13da6e384299f1d81f1c57598d0c827442510a94241bb3516869294868a1b49f` | `86c315035dbb7809f4b4e01abefd2f1b95f594915e7853ccc0df154de59c2cba` |
| M3 | `783b2b59ce0d80fabc9d650aeea4e7d943f2f080af9e2b2259a89b4541483370` | `0d99d1db9f3a265a7e2ca6b47d778ab3839d69816c04dddebcda38ee87760789` |
| M4 | `13da6e384299f1d81f1c57598d0c827442510a94241bb3516869294868a1b49f` | `113dacbf3735774291a644dde8a46a6103397a24f658b6fd71e950b46a7bf1b2` |
| M5 | `13da6e384299f1d81f1c57598d0c827442510a94241bb3516869294868a1b49f` | `5bc507810017ee568d1b1e7622b544b7024d1f8071e7d25ca209e3a4478f3bd3` |
| M6 | `8ede92bae3d2fbe611908dd77ffdf3dde04fc7a9c336a20e4d1d3bc333bfabc8` | `159d15bd1956ad6f7b76d61a08c3a56b1585c1784a0cca28c656b57d1bebcf3a` |
| M7 | `13da6e384299f1d81f1c57598d0c827442510a94241bb3516869294868a1b49f` | `ea8672ebb6d4bd9ece0e0ea51eae7d2f8903dd8e2e98448fc63d6cca4c551e6c` |
| M8 | `13da6e384299f1d81f1c57598d0c827442510a94241bb3516869294868a1b49f` | `1db585dfae7134ec28b283a01f7696cb6a7cc54ba6d773b68eb4437bb1163403` |
| P1 | `27aee57ab3d04a42750b471bfcb3a012d602ec3a546a736db6bbebb3bd5d0647` | `53290704cdfd806bdbe73d14b97efd134138d6ea80370d9fcb615c659e20a8ce` |
| P2 | `457a2c9fdfbb3165faa544e086ce5d7b6205a30280f7a5de3cba114268f801bc` | `f553da89fcf1741c98d2ba9c9fac86c708011bfd6044c0b0ed4f334d8eb5bd66` |
| P3 | `5200b1aad45d10ceccfcf58d41e46eed1d6d4d4c6b7553866c11f711d3a56001` | `b591cb8ef58115a4fa4dc4c28b2a8ef660bd55df9bd6d7ee19d5c047e8edb1e5` |
| E1 | `4224f2d041759db10e9a662900202feb718c5ad2d422a2e0fe6cc58306425f20` | `35a927e2c0691406e644dc5bf701aeafac5203f5d3f92d1ad5699c8df3c2c134` |
| E2 | `77956be3be9f295b3d4d50de00af16a1051a0745d474f566a44a7c6536115c4d` | `5bc5121f1cd0cc3e0dccc62bb0e9b8c7bf84e0a17a437fec54b3344e20acd460` |

M1–M8 unit-red/public-diff:11/5,25/23,43/0,10/5,8/4,5/1,15/0,50/25.
M3/M7 ловятся native engine/fullraw, не публичной metadata; P1 только contract red
(unit529/corpus102/arch522 green);P2/P3 frozen arch red;E1directory2red→62green;
E2security2red→3green. Full commands/timing/logs/bytes: resume-01/mutations/*/proof.json.

Обратная проекция: frozen kernel/runtime/protocol/channels/editor/neighbor modules/
substrate кроме отдельно разрешённого DiskFileSystem.exists — byte-identical;
tools/{selfcheck,snapshot_diff,lint_arch,gen_contract,check_limits},handoff,prompt frozen.
Единственное отдельно разрешённое gate exception: security files() is_file filter;
baseline→golden exact proofs для него и exists сохранены. is_file/list/read/_resolve
не менялись;consumer fs.exists вызов ровно1, snapshot ровно1наcall;MemoryFileSystem
unchanged, F4 не исправлялся, новую F5 porter не объявляет. Other-module domains frozen.
SCAN декларации/функции AST-identical, scan cases47 и136input bytes/SHA unchanged.
Все seven inventory pins/context case+SHA/scene198+54facts обратнопроверены, EOL intact;
внешние scan tests — только согласованные filters/pins;original47/34/136 checks retained.
PROGRESS только row53/stage7;parity только split row58;tests-map124/125 append clarifications;
worksheet/WORKLOG fresh historical prefixes exact,4479CRLF preserved.

Стабильные changed/new non-fixture SHA (пять изменяемых status docs хэшируются
ПОСЛЕ последней записи в external final-scope.json; self-reference не подделывается):

| Файл | Bytes | SHA256 |
|---|---:|---|
| `fixtures/corpus/context/gather/001-all-sections.json` | 1899 | `f50dbd3e486ccff860e2bc0924eecdba16b33f4de1c0e10585bbe7854af8522e` |
| `fixtures/corpus/context/gather/manifest.json` | 1009 | `69b6a6a35c7cfee94767ad978bebf49a05a2a1fee284eb7b41fd83179fac0835` |
| `fixtures/corpus/editing/split_gd/manifest.json` | 71811 | `0a93e7f7df90091d02ac856b19b6d0420988da417bb77f741d0f274c054a2cdc` |
| `fixtures/corpus/scene_model/scene_deps/manifest.json` | 110763 | `1b8780f63d0433c5cd246da92d4f65059add772c8b29fd1606163d3100cd3ab5` |
| `python/modules/editing/split_gd/app.py` | 3538 | `5200b1aad45d10ceccfcf58d41e46eed1d6d4d4c6b7553866c11f711d3a56001` |
| `python/modules/editing/split_gd/domain/core.py` | 9222 | `13da6e384299f1d81f1c57598d0c827442510a94241bb3516869294868a1b49f` |
| `python/modules/editing/split_gd/module.py` | 480 | `6d756c66613dfdc2d5dd04d354b191b0b22e5e0a902e11caa2b23f1c23621808` |
| `python/modules/editing/split_gd/ports.py` | 803 | `ae7bbd0c3bde93981261add77fb53b6aaef21da9ba9bbb56af89a8ba42d070d5` |
| `python/modules/editing/split_gd/tests/corpus.py` | 1078 | `d78b9db8031ec393e1191468356ac27740ef22d25457f80977dd792069fc4c6e` |
| `python/modules/editing/split_gd/tests/test_app.py` | 5102 | `9eddb20aa935745b6e5d93e10f8eeb201405de61c8465656580d56843aec8dfd` |
| `python/modules/editing/split_gd/tools.py` | 4966 | `27aee57ab3d04a42750b471bfcb3a012d602ec3a546a736db6bbebb3bd5d0647` |
| `python/substrate/fs/disk_fs.py` | 3987 | `4224f2d041759db10e9a662900202feb718c5ad2d422a2e0fe6cc58306425f20` |
| `reports/selfcheck/editing.split_gd.json` | 949 | `dd6c7a892db6ddfb21808e377c32b972a4595e707dc5269637f5974154c8bcd5` |
| `tests/py/contract/test_functions_contract.py` | 8638 | `ad8beecbf232a68524d0d1a09e33dcb44f280f873c272c9a4e6fa98fe365455e` |
| `tests/py/contract/test_split_gd_scan_contract.py` | 1966 | `38d5f63cbd58c9edde368ebb6daa674f59dde1547ba76653648f91467c20e1a6` |
| `tests/py/contract/test_usages_contract.py` | 7353 | `120922ff222703af4fed6f9276ae1edc302f259ed68358be35675b5ca338031e` |
| `tests/py/integration/test_gd_lint.py` | 4327 | `1bdd18fe32c961926ffeb83eaa53f37a46a4bc09e1a24df725bea2efc2e9b2b3` |
| `tests/py/integration/test_node.py` | 5472 | `ba04f5826152fca13939aef2e89a2630fbd8cddf91369201dba740ee173ba456` |
| `tests/py/integration/test_scene.py` | 4884 | `391a80134c88012a207a9c23402a38028bc4863065f8b8931f23b7c723798c00` |
| `tests/py/integration/test_split_gd_scan.py` | 3830 | `f108238ecf5a7e3ab0a3748f5742caa831cae6f762093ec3aea0ab98efdd9271` |
| `tests/py/integration/test_tscn_lint.py` | 2804 | `628322705e3dfec485a0fb0ec755491003eaa8ec7f31f315d6dfa58c2c30ada3` |
| `tests/py/integration/test_verify.py` | 6550 | `bf3092553b719758dfb77088288fb1c22c24f8cb3983610719faaab39f8fba40` |
| `tools/security_audit.py` | 10885 | `77956be3be9f295b3d4d50de00af16a1051a0745d474f566a44a7c6536115c4d` |
| `contract/capabilities/split_gd_plan.json` | 4638 | `a7cf999f6fcedfd4af0966fd926212aa4c1001717f33e95eb31d8e8020bb4744` |
| `docs/adr/0011-fs-exists-split-gd.md` | 2745 | `b64a865cb91e770691420e12ead99dfc4bdf39a2796c077bd94232bd83c5fa17` |
| `python/modules/editing/split_gd/domain/collect.py` | 2198 | `8ede92bae3d2fbe611908dd77ffdf3dde04fc7a9c336a20e4d1d3bc333bfabc8` |
| `python/modules/editing/split_gd/domain/engine.py` | 3002 | `783b2b59ce0d80fabc9d650aeea4e7d943f2f080af9e2b2259a89b4541483370` |
| `python/modules/editing/split_gd/domain/render.py` | 8964 | `457a2c9fdfbb3165faa544e086ce5d7b6205a30280f7a5de3cba114268f801bc` |
| `python/modules/editing/split_gd/domain/tokens.py` | 3230 | `ff152704f1c1fe8498014f71c39e4d519ff7ef0bc2e376851035826809e4138c` |
| `python/modules/editing/split_gd/plan_io.py` | 823 | `a38175346ffc04d95548bc0554f0e8873b31a6187ef714d00ff229cd58d43e0d` |
| `python/modules/editing/split_gd/tests/plan_corpus.py` | 1334 | `a85084c2cb2e6dcaacfcba587f94163c4df0419e30c376264371195f61616c74` |
| `python/modules/editing/split_gd/tests/test_app_plan.py` | 6076 | `a56670309f5b47d30b0f065b86f09ceb77711249dab4dc9ed1573a9d4b515ae7` |
| `python/modules/editing/split_gd/tests/test_collect.py` | 898 | `5b2b0f43ecda827c4f1e3e1e2df26d35e339345951abda734758dc579d96ed64` |
| `python/modules/editing/split_gd/tests/test_core_plan.py` | 2091 | `78d320375bae8c89cc9cd06d6f8454f365bb7ef17a40d113275ab80a88937084` |
| `python/modules/editing/split_gd/tests/test_engine.py` | 666 | `2304e31c11a88f57ce47168a6d356563878a405f0b448d9281237b26e475d3a8` |
| `python/modules/editing/split_gd/tests/test_render.py` | 1827 | `d24b93b50eb4981719120cadc0e39bade1a933409efdd35018e8f191ed722fea` |
| `python/modules/editing/split_gd/tests/test_tokens.py` | 1015 | `f36af4b3480138a844dd0818560e85aab41caac7f858fbbd9ce79bb207818e25` |
| `tests/py/contract/test_split_gd_plan_contract.py` | 2344 | `23fced8a6ed81451ac1cab43db3044c07e0da7af022a1965d5ea9ac35f77c319` |
| `tests/py/integration/test_split_gd_exists.py` | 1253 | `477ea4b7e7b57f2df7dafec3a852099d6e025b89a9baecd2d25143a75a41f2eb` |
| `tests/py/integration/test_split_gd_plan.py` | 3611 | `17767758ca4b09bf3e3df93868f7f88fe4c6cf33343334648aa4beb5fcc08ebb` |
| `tests/py/security/test_split_gd_security_files.py` | 1263 | `cff1cb4651e4dee9adf021768852f82576b79278622e4f2fe09f35d971eacc3c` |

Оставшиеся225added files:55case JSON в fixtures/corpus/editing/split_gd/101–155
и170input files ТОЛЬКО fixtures/projects/corpus/editing/split_gd_plan/. Для КАЖДОГО
bytes+fullSHA есть в split manifest и exhaustive final-scope.json/-paths.md. Empty
existing_module_dir/editor/part_one.gd directory отдельно зафиксирован и остаётся пустым.

Полный external dossier:
`C:/Users/Lich/AppData/Local/Temp/opencode/c15-split-gd-plan-20261031-preflight-88e4b/resume-01/`.
final-scope.json содержит все2777byte facts (changed28+added243+unchanged2506),
full path/bytes/SHA list final-scope-paths.md, directories/collection list; reports/selfcheck/
editing.split_gd.json — финальный отчёт. before.json/before-bytes — fresh baseline.
capture-proof.json, independent-recapture-round2/summary.json, independent-wide/summary.json,
companions-proof.json, exists-byte-proof.json, security-gate-proof.json, mutations/,
neighbors/summary.json, live-round2/proof.json, full run stdout/stderr/command JSON сохранены.
First failures: oracle exception hierarchy, EOF/EOL repairs, wrong importmode/CLI,
recapture separator rebasing, M6 indentation, security directory gate, live config-disabled
round1 — НЕ удалены/НЕ заменены. Scope-pre first script KeyError (public_methods
ошибочно назван methods) и исправленный external proof сохранены; production не менялся.
Actual-old split63421B/1333LF/0CRLF/SHA18f05d10b8e875ed77040b8a47beb6ccbdb409b55d791ec0318466473969bfc7
повторно проверен; foreign _ref2.log/_excl.log и C.14 dossier не трогались.
SEC hygiene: только expired harness token fields в двух external temporary port.json
замаскированы; logs/native observations/fixture bytes untouched, proof live-auth-redaction.json.

**Следующее действие:** независимый аудит C.15 (своя пересъёмка/проекция/мутации/
scope reverse check). Porter не принимает механику. Подключение к записи — C.16.

## Приёмка C.15 аудитом (сессия 69, 2026-10-31) — половина 2 `split_gd_plan`

| Что проверено | Чем | Результат |
| --- | --- | --- |
| Корпус с эталона | свой oracle: `split_gd.plan_split` + `_public_plan`, `_cache` сброшен перед каждым кейсом | `reference_result` 55/55 |
| Порт против ожиданий | `agent.call('split_gd_plan', args)` на свежей копии фикстуры | 55/55 (13 отказов по `kind`, идемпотентность, диск не меняется) |
| Независимые инварианты | счётчики = гистограмма `occurrences`; нет `content`; донор не в своих ссылках; `modules[].rel` уникальны | 25/25 |
| Дифференциал | все `.gd` фикстур, режимы `auto`/`short` | 108 вызовов: 102 совпало, 2 — лимит 4 MiB, 4 — `addons`/`plugin.cfg` |
| Свои мутации | M1 4, M2 25, M3 2, M4 8, M5 7, M6 2, M7 18, M8 50, M9 34, M10 11 | все красные, байты восстановлены |
| Подложки | P1 `required` без `stats`; P2 `import os` в `domain/render.py`; P3 чужой `shared` в `app.py` | P1 — только `gen_contract --check`; P2/P3 — `lint_arch` |
| Гейты | selfcheck, договор, слои/лимиты, security, snapshot | 600/102, 23, 522/0, ok, 724/0 |
| Гигиена | `.gd.uid`, debris, внешний `project.godot` | 83 → 245 → 83 (163 новых удалены, `plugin.gd.uid` восстановлен), debris 0, `project.godot` побайтово |

**Находки:** F6 (тексты отказов), F7 (`newline`), F8 (правка замороженного `tools/security_audit.py` — нужна ретро-легитимация), F9 (live удаляет корневой `plugin.gd.uid`). **Долг:** F4 (`tools/selfcheck.py:215`).

## C.16 — F6/F7/F8 (сессия 70)

2026-10-31, портер. Этап 7 и приёмка C.14/C.15 сохранены; C.16 не принято.
Промпт прочитан целиком: 34314 B, 449 CRLF, без BOM, SHA256
`b52388f1f6ddb7ffb71429b12a4427759e6dc10ddef2d16586bfe9a17c1cd95f`.
Новая нумерация: воронка записи — C.17; исторические записи C.15 не переписываются.

- F6: убрать только границы PLAN_ARGS.target_lines и minItems GROUP.funcs,
  оставив типы; точные отказы 108/109/130 закрепить без пересъёмки rawreference.
- F7: file_newline(raw), приоритет CRLF → CR → LF; передать факт в core.plan.
  Это разрешённое расхождение с эталоном для 141/142/143: reference_public.newline
  остаётся LF, expect сообщает исходные байты. decode и нормализованный donor_sha256
  сохраняются. Scan/47cases/card, refs/inventory/engine и чужие слои заморожены.
- F8: ретро-разрешение аудитора, сессия70/§9. Строку files() добавил портер C.15
  в сессии68, после отдельного пользовательского разрешения на S1 (история выше);
  аудитор69 отметил отсутствие §-разрешения. Теперь нужны ADR-0012 и новый tools-test;
  никаких постоянных правок security_audit.py, SKIP_DIRS или набора проверок.

### Свежая byte-база до первой правки

Досье `C:/Users/Lich/AppData/Local/Temp/opencode/c16-split-gd-fixes-20261031-70/`:
before.json, before-bytes/ (каждый файл), project.godot.before. Полный обход:
2779 файлов, 84 UID. Это отдельный текущий census, не замена исторической базы
аудитора 2773/83. Найден до работы дополнительный
`fixtures/projects/corpus/editing/split_gd/skip_dirs/__pycache__/ref.gd.uid`:
20 B, SHA256 `1191b3d4b735fc86fff0366fc9fffb4a352afd44d318e436b4d81deeaa578e49`.
Он не создавался C.16; без отдельного решения не удаляется.

| Файл | Bytes | SHA256 до C.16 |
|---|---:|---|
| tools.py | 4966 | `27aee57ab3d04a42750b471bfcb3a012d602ec3a546a736db6bbebb3bd5d0647` |
| app.py | 3538 | `5200b1aad45d10ceccfcf58d41e46eed1d6d4d4c6b7553866c11f711d3a56001` |
| plan_io.py | 823 | `a38175346ffc04d95548bc0554f0e8873b31a6187ef714d00ff229cd58d43e0d` |
| domain/core.py | 9222 | `13da6e384299f1d81f1c57598d0c827442510a94241bb3516869294868a1b49f` |
| domain/text.py | 1744 | `6f0c5a835330e6bce10aa096ea1990533f30d085629a719ee7c796eb5a43591c` |
| domain/render.py | 8964 | `457a2c9fdfbb3165faa544e086ce5d7b6205a30280f7a5de3cba114268f801bc` |
| domain/engine.py | 3002 | `783b2b59ce0d80fabc9d650aeea4e7d943f2f080af9e2b2259a89b4541483370` |
| contract/capabilities/split_gd_plan.json | 4638 | `a7cf999f6fcedfd4af0966fd926212aa4c1001717f33e95eb31d8e8020bb4744` |
| tools/security_audit.py | 10885 | `77956be3be9f295b3d4d50de00af16a1051a0745d474f566a44a7c6536115c4d` |
| python/substrate/fs/disk_fs.py | 3987 | `4224f2d041759db10e9a662900202feb718c5ad2d422a2e0fe6cc58306425f20` |

Preflight: текущий target_lines(None) отказывает, хотя §3 требует 1100; будет отдельный
красный пин. Дословная M1 с minimum=0 не может покраснить 108 (99 ≥ 0): ожидается
red109, green108; это предел самой мутации, не повод менять её на minimum=100.
**Следующее действие:** решить судьбу дополнительного pre-existing UID; затем
перепроекция ровно шести expect и красные тесты до кода. PROGRESS пока неизменен (§3.1).

Пользователь в сессии70 отдельно разрешил «Архивировать и удалить» только указанный
pre-existing ref.gd.uid. Удалён точечно после byte-бэкапа; ref.gd сохранён,
остальные 83 UID неизменны. Это дополнительное разрешение, не результат live C.16.
**Следующее действие:** перепроекция ровно шести expect, затем красные тесты до кода.

### Корпус и red до production-кода

Перепроектор вне аддона: reproject.py/reprojection.json. Изменены только expect
108/109/130 (message = существующий expected_message) и 141/142/143 (newline),
их cases sha256/bytes, добавлен c16_recut. IDs, inputs, rawreference,
contract_refusals, plan_capture и остальные 96 кейсов побайтово сохранены; всего102.
Прогон red-before-code: **46 failed, 511 passed**, pytest5.69s/wall7.593s,
exit1, stderr0, red.xml. Включает None/default, factual newline, schema bypass
и явные пины F6/F7; raw-native preparation сохраняет прежнюю проверку содержимого.
F8 уже исправлен исторически: временно удалена ровно existing строка фильтра
(10831B), red-f8-before-code: **3 failed**/0.40s, включая PermissionError и exact pin.
SHA-восстановление 10885B/77956… подтверждено red-f8-restoration.json;
f8-restored-before-code: **3 passed**/0.17s, exit0, stderr0.
**Следующее действие:** file_newline → core.plan → plan_io/app → ToolSpec, затем ADR/contract.

### Implementation, contract, differential и mutation evidence

first-green: **557 passed**/5.91s, wall7.622s, exit0/stderr0. Добавлены чистый
file_newline(raw) и обязательный keyword newline в core.plan; plan_io получает
raw и передаёт фактический newline, decode и нормализованный SHA не изменены.
Legacy newline_of сохранён ради принятого unit-пина, production его не вызывает.
None →1100 разрешён на уровне core; JSON-schema сохраняет integer и отвергает null.
F6 снимает только bounds/minItems, не types. ADR-0012 фиксирует ретро-разрешение F8.
gen_contract --write/--check:23, поменялась только plan-карточка; остальные22 exact.

Independent recapture:55кейсов/92native calls,25full raw+25public equal,
21native refusal equal,9исторических contract boundaries; raw oracle неизменён,
ровно три явных newline-отклонения141/142/143, неожиданных0, wall2.284s/stderr0.
Широкий прогон перечислил **54 обычных .gd**, а не41 из текста задания:
это всё дерево split_gd_plan, включая existing_module_file/editor/part_one.gd,
без каталогов и без дедупликации. Проверены все54×targets1100/100:
108native/216port calls,72raw+72public equality,30exact native refusals;
6boundary calls(2addons-policy+2no-plugin+2raw4MiB) и6разрешённых factual-newline
отклонений внутри72public comparisons; unexpected0, wall6.555s/stderr0.
Первые external helper попытки сохранены: неверная гипотеза41 и отсутствие
обязательного hint:"" в ожидаемом error-envelope. Исправлены только external helpers,
полные kind/message/hint проверки не ослаблены. Native cache reset, idempotence,
деревья files+dirs и absent state неизменны, write/Godot sentinels активны.

Все отдельные M1–M8/P1–P3 имеют before-bytes, SHA before/mutant/restored и rawlogs
в mutations/*-round2/proof.json, общий mutations-summary.json:
M1=1failed/1passed(109red/108green по математике minimum0), M2=1failed,
M3=3failed, M4=3failed, M5=1failed+contractfail, M6=1failed/2passed,
M7=3failed(130+2render), M8=1failed(141BOM), P3=3failed(PermissionError+filterpin).
P1:557behavioral green, только gen_contract --check red(split_gd_plan.json).
P2:557behavioral green, lint_arch red(IO os в core). Все байты восстановлены;
затем557passed/5.12s, contract23, layers522/0, securityok/stderr0.
Ранние ошибочные external mutation helper попытки(двойной substring и serialization
CompletedProcess) сохранены; они не являются доказательствами, M1 повторён отдельно.
**Следующее действие:** полный non-live/collection/JUnit/snapshots/selfchecks, затем три live.

### Финальные прогоны C.16 — 2026-11-01, портер, не принято

`python -B -m pytest python/modules tests/py --ignore=tests/py/live` с JUnit
через `subprocess.run`: **3617 passed in 100.67s**, wall104.311s,
exit0/stderr0; JUnit3617/0fail/0error/0skip. Collection3617 в116уникальных
node-ID файлах, pytest8.23s/wall11.212s, exit0/stderr0. Это собственный счёт
файлов, не замена историческим102файлам аудитора. Delta3589→3617:
25добавленных split-unit/contract пинов плюс3новых F8tools; unit600→625.
Первый полный прогон тоже3617green/95.41s/wall98.053s; ошибся только внешний
парсер double-quiet collection. Оба stdout/stderr/JUnit сохранены.

Snapshot wall113.084s/exit0/stderr0:

```text
fixtures/corpus/editing/split_gd         кейсов 102, совпало 102, расхождений 0
{"status": "ok", "detail": "кейсов 724, расхождений нет"}
```

`python -B tools/selfcheck.py editing.split_gd --json`:
wall58.951s/exit0/stderr0; файл `reports/selfcheck/editing.split_gd.json`.

| Check | status | detail |
|---|---|---|
| module | ok | editing.split_gd (split_gd_scan, split_gd_plan) |
| layers | ok | файлов522, нарушений нет |
| limits | ok | файлов522, предупреждений0 |
| contract | ok | артефактов23, расхождений нет |
| security | ok | нарушений нет |
| unit | ok | 625 passed in 10.54s |
| corpus | ok | кейсов102, расхождений нет |
| verdict | ok | реальный selfcheck, не само-приёмка |

```json
{"module":"editing.split_gd","verdict":"ok","checks":[{"check":"module","status":"ok","detail":"editing.split_gd (split_gd_scan, split_gd_plan)"},{"check":"layers","status":"ok","detail":"файлов 522, нарушений нет"},{"check":"limits","status":"ok","detail":"файлов 522, предупреждений 0"},{"check":"contract","status":"ok","detail":"артефактов 23, расхождений нет"},{"check":"security","status":"ok","detail":"нарушений нет"},{"check":"unit","status":"ok","detail":"625 passed in 10.54s"},{"check":"corpus","status":"ok","detail":"кейсов 102, расхождений нет"}]}
```

Неизменные соседние selfcheck: check188/75 (wall28.238s),
api_check206/52 (22.048s), gd_lint126/37 (23.149s), tscn_lint315/65 (33.810s),
class_api186/26 (22.026s), каждый verdictok/exit0/stderr0.
Их новые report bytes архивированы снаружи, исходные report bytes восстановлены;
чужие тесты и код не менялись. Class186 — сохранённый F4, не исправление селектора.
Отдельные gen_contract/lint_arch/check_limits/security_audit:
23/522/522warnings0/9checksok, всеexit0/stderr0.

### F8: ретро-разрешение

C.15-портер (сессия68) добавил только `if not path.is_file(): continue`
после отдельного пользовательского разрешения S1. Аудитор69 отметил отсутствие
разрешения в §среза; аудитор70 §9 текущего prompt ретро-разрешил оставить
ровно эту правку с ADR-0012 и новым tools-test. Дата исходной правки и разрешения
не переписана. В C.16 новой постоянной правки `tools/security_audit.py` нет:
10885B/SHA256 `77956be3be9f295b3d4d50de00af16a1051a0745d474f566a44a7c6536115c4d`.
Удаление фильтра: первоначальный red3failed, P3 повторно3failed;
exact restoration:3passed и complete security gateok. Прежние3security-теста,
включая SEC-06 обычного секрет-содержащего файла рядом с каталогом, сохранены
и прошли полный non-live. SKIP_DIRS/CHECKS/link/special-file политика не менялись.

### SHA256 мутаций и восстановление

M7 дополнительно повторён с **буквальным** предписанным старым текстом
`группа %s: пустой funcs`:130 и2render-пина —3failed/61deselected/1.16s,
после exact byte restoration3passed/0.92s. Первый вариант с иным ошибочным
текстом сохранён в round2, но итоговый M7 — `mutations/M7-literal-round3/proof.json`.
Все остальные — `mutations/*-round2/proof.json`; итог `mutations-summary.json`,
исходный round2-summary также сохранён. В таблице before/restored совпадают
полностью (bytes/LF/CRLF тоже проверены); M1:109red/108green при minimum0,
отдельный M6 ловит99. P1 behavioral557green/толькоcontractred;
P2 behavioral557green/толькоarchred; P3 tools3red.

| Мутация | SHA256 before = restored | SHA256 mutant |
|---|---|---|
| M1 | `98c2a6b7714cade6e0a3e0eecc8bb78b19988ab4f3a959b1cc51a38e91090bd5` | `82dfc1d85c734d665046c6b0494a4ed208b0ab94aadd1f5b6af8bef8a0614563` |
| M2 | `98c2a6b7714cade6e0a3e0eecc8bb78b19988ab4f3a959b1cc51a38e91090bd5` | `ab75d5295ae05c7482c63a808aa3646023dd22c9463e1b87e30e838a9ced78fb` |
| M3 | `77a96eb9a4d3570e464bf194982b215cdf94d2f6ff80961aa95e9a8788c0ea69` | `3e339032e4e1d2b40f76fe7c73a69881b749c8da6503da84a21bed38f69e298e` |
| M4 | `f20982b9281ebb14db65af4b8412b7e5ecc8a855e2304b9f9dd53045a57a97d2` | `0d8e8d397993f82a4ccfffe1c380be623cb2f03512c9d42a6855b976ecbe0056` |
| M5 | `98c2a6b7714cade6e0a3e0eecc8bb78b19988ab4f3a959b1cc51a38e91090bd5` | `5596847d3aa01dc36113cb9217595fed8dfa48c2eb244ac1422dfed3aa629b8d` |
| M6 | `673df0b3f9a80374cfb3e34539d6e60670912337c2423087932acd42d3d33c0c` | `600ef3d2115ae650f09afb053bce3f2fbb9c84e06f9da7be728655824b4b5406` |
| M7 | `457a2c9fdfbb3165faa544e086ce5d7b6205a30280f7a5de3cba114268f801bc` | `8e7f7a0f662bd5e38676dff8457639c374b821cfc37e6d4771fa5204046ccf31` |
| M8 | `77a96eb9a4d3570e464bf194982b215cdf94d2f6ff80961aa95e9a8788c0ea69` | `2f4f6dbedbd3fab01875362651754125f1ca2a0952983220a0a127204a36eb18` |
| P1 | `98c2a6b7714cade6e0a3e0eecc8bb78b19988ab4f3a959b1cc51a38e91090bd5` | `fbd78cfa26aacb0ab53ca52dbceca83706dd67a7a48db65beb111d283297e5f2` |
| P2 | `673df0b3f9a80374cfb3e34539d6e60670912337c2423087932acd42d3d33c0c` | `09f9818315d824d1624a5db093d8905f60869865c09ddfc78dd851fdfb4f90ee` |
| P3 | `77956be3be9f295b3d4d50de00af16a1051a0745d474f566a44a7c6536115c4d` | `2cf0d7f6b1affd08e4d12b1a6ed92ef9be2e3649719b5cd37720912df6d5cf94` |

### Live, probe, scope и передача

Ровно3существующих live: **3passed/0skip/32.56s**, wall34.977s,
JUnit3/0/0/0, exit0/stderr0; Godot4.6.3 console, тесты не правились.
Внешний `project.godot`:335B/SHA `958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`
→ временно419B/SHA `3a55b7f7d74f91ab6574ba457ad807a00cf4c532520ee7cae8972abf388b95d3`
→ исходные bytes/SHA. UID83→246→83:163наблюдённых новых UID архивированы
и удалены по одному с проверкой неизменного .gd-источника. Корневой
`plugin.gd.uid` был отдельно сохранён; в этом прогоне не удалялся и остался
byte-identical (F9-path восстановления предусмотрен, но не потребовался).
Все addon-файлы/каталоги после live равны непосредственному pre-live снимку;
тестовая сцена удалена самими тестами. Отдельное удаление pre-existing84-го UID
ранее выполнено только после явного пользовательского разрешения (см. preflight).

Шесть `tools/probe.py split_gd_plan` вызовов из CLI подтвердили108/109 exact
`target_lines must be between 100 and 5000`,130 exact
`группа part_one: пустой список funcs`,141/142CRLF,143CR. Exit1 у3ожидаемых
отказов/exit0 у3успехов, stderr0, полные payloads и addon-tree unchanged.
Единственное намеренное oracle-расхождение F7 — factual newline вместо nativeLF
в141/142/143 (и соответствующих6wide-вариантах). Native reference_result/public,
normalized donorSHA, decode и generated raw content не переписаны.

Полный fresh byte census:2779→2780файлов,25изменены/2добавлены/
1точечно удалён по разрешению/2753неизменны; это не пересчёт исторических2773.
83UID/debris0; директории сохранены, легитимные fixture `__pycache__` не удалялись.
22чужие cards/47scan cases и все fixture inputs/editor/kernel/substrate/runtime/
protocol/channels/verification/engine_kb/gates/handoff/prompt byte-identical;
scan-функции и SCAN-декларации AST-identical. App76/tools102lines;
context22names/cards23+template/6verb-markers/verbs_version3 неизменны.
У tests-map сохранены244исторических CRLF и чужие строки; WORKLOG только `ab`,
исторические4479CRLF и весь старый byte-prefix сохраняются.
Итоговые полные before/after bytes+SHA256 всех изменённых/добавленных файлов:
в досье `final-scope.json` и `changed-files-sha256.md`; mutation/table/probe/live/
regression raw evidence там же. Финальные документационные записи не меняют
этап7/приёмку C.14/C.15, чужие строки и F4. Само-приёмки нет.

**C.16 готов к независимому аудиту, не принято.**
Следующее действие: аудитор независимо воспроизводит C.16/F6/F7/F8 по досье;
после его приёмки отдельная задача C.17 — write-funnel integration.
## Приёмка C.16 аудитом (сессия 71, 2026-10-31)

| Что | Как проверено | Итог |
|---|---|---|
| Пересъёмка корпуса | оракул заново поднял эталон: `plan_split` + `_public_plan` против сохранённых `reference_public`/`reference_error` | 46/46, 0 расхождений |
| Своя проекция | `_public_plan` минус `donor_content`/абс. пути, `newline` — мой факт из байтов | 25/25 |
| Порт против `expect` | все 102 кейса оба инструмента, идемпотентно, sha дерева проекта неизменен | 102/102 |
| Дифференциал шире корпуса | 55 вариантов, все `.gd`-доноры x 2 режима `target_lines` | 107 вызовов: 72 совпало, 30 текстов отказов равны побайтово, 1 лимит 4 MiB, 4 границы политики, 0 необъяснённых |
| Свои мутации | M1 4, M2 3, M3 7, M4 9, M5 2, M6 11, M7 5, M8 56 — все красные, байты восстановлены | 8/8 |
| Подложки | P1 убрать `newline` из `required`; P2 `import os` в домене; P3 снять строку `is_file` из гейта | P1 — только `gen_contract --check`; P2 — `lint_arch`; P3 — 3 красных в `tests/py/tools` |
| Пересчёт корпуса | шесть кейсов: у каждого изменилось ровно одно поле (`expect.message` / `expect.result.newline`); `inputs` 306 и `plan_capture` идентичны, добавлен только `c16_recut` | точечно |
| Сохранность | сверка с `before-bytes`: +2 (ADR-0012, `test_security_audit_dirs.py`), 25 изменённых, 0 удалённых; 13/13 замороженных гейтов, 23/24 карточек, принятые области и `editor/` без изменений | сохранено |
| Гейты | non-live 3617/0/0/0 (89.4 s), live 3 (24.1 s, 0 skip), `snapshot_diff` 724/0, contract 23, layers 522, limits 522/0, security ok, selfcheck 625/102 | зелено |
| Гигиена | `.gd.uid` 83 → 245 → 83 (удалены ровно 162), корневой `plugin.gd.uid` на месте, дерево 2776, debris 0 | чисто |

**Границы, зафиксированные при приёмке:** (1) **F10** — пин `target_lines must be between 100 and 5000`
короче живой строки моста (`split_gd target_lines must be between 100 and 5000`) на префикс команды;
(2) порт отдаёт `0 → 1100` и отказывает `'100'`, тогда как мост отказывает `0` и принимает `'100'` —
решения C.15 (кейсы 102/152), не менялись; (3) `newline` в `expect` — факт из байтов, `reference_public`
остаётся нативным; (4) запись плана в `write_preview`, `apply_prepared_split` и `_godot_check` — срез C.17.
