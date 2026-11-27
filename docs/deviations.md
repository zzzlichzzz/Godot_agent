# Отличия от старого агента (deviations)

Здесь фиксируются **осознанные** отличия нового поведения от старого. Правило
простое (R-09): любое расхождение — либо баг переноса, либо запись сюда. Третьего
не бывает.

## Как пополнять

| Поле | Что писать |
|---|---|
| Дата | когда зафиксировано |
| Возможность | `область.фича` или имя инструмента |
| Старое поведение | что делал старый агент, с примером |
| Новое поведение | что делает новый, с примером |
| Причина | почему отличие нужно (баг, безопасность, лимиты, ясность) |
| Кто решил | человек / ADR-номер |
| Обратимо? | да/нет и как вернуть старое поведение |

## Таблица

| Дата | Возможность | Старое | Новое | Причина | Решение | Обратимо |
|---|---|---|---|---|---|---|
| 2026-10-27 | `write_apply` (кейс 015) | у эталона нет отката: `apply→rollback→apply` проверить нечем | ожидание кейса задано контрактом ADR-0005 (`conflict/already_rolled_back`), а не съёмкой; помечено в `note` кейса | R-07 требует эталон, но безопасности без кейса нет; ожидание — из ADR, а не из нового кода | ADR-0005 | да: удалить кейс, когда появится эталонный откат |
| 2026-10-27 | `analyze_rename` (`mode`, `allow_unverified`) | `action["mode"]` любой строкой уходил в отчёт; `allow_unverified` не проверялся по типу | `mode` — `enum strict\|probable`, иначе `invalid_input`; `allow_unverified` — только `boolean` | опечатка (`"fast"`) молча ослабила бы проверки и вернула бы отчёт с несуществующим режимом (R-15: ошибка — часть контракта) | ToolSpec-схема (S4 `code_intel.usages`) + проверка в `domain/core.build_rename_query` | да: убрать `enum`/`default` из `tools.py` и проверку `mode` в `build_rename_query` |
| 2026-10-27 | `write_preview` (коллизии имён) | `_collision`/`_is_real_conflict` смотрели проект целиком: другие `class_name`, autoload и InputMap из `project.godot`, классы движка через `gd_api_cache` | проверяется только целевой файл (`editing/symbol_rename/domain/collisions.name_conflict`); проект-wide проверки — долг части 2/3 | в срезе нет `formats/tscn` и кеша классов движка (`engine_kb` ещё заготовка); подделывать проверку нельзя | лист `docs/porting/write_preview.md`, решение 2026-10-27 | да: добавить `_project_global_names`-аналог и ClassDB, когда появятся порты |
| 2026-10-27 | `write_preview` (смещения и переводы строк) | эталон отдаёт `before_hash` от СЫРЫХ байтов и правит файл целиком в его стиле | `expected_hash` — sha256 текста после `\r\n → \n`, стиль едет в `payload.newline`; применяет часть 2 | иначе план зависел бы от платформы съёмки, а `stale_plan` не отличил бы смысловую правку от смены стиля | ADR-0005 + лист `write_preview` | нет: нормализация нужна для сверки хешей |

| 2026-10-27 | `write_rollback` (ожидание корпуса) | своего отката у эталона нет: восстановление жило в `history_manager` (не портируется, R-08) | ожидание отката снимается с `before_bytes` плана `prepare_rename` — это байты ДО применения | побайтовая гарантия и есть предмет проверки; переносить `history_manager` запрещено | ветка `write_rollback` в `tools/_reference_runner.py` | да: заменить ожидание, если появится эталонный откат |
| 2026-10-27 | `write_apply`/`write_rollback` (съёмка корпуса) | кейс = один вызов инструмента | кейс описывает сценарий (`scenario: preview_apply\|preview_apply_rollback`), `snapshot_diff` проигрывает его агентом на копии фикстуры | `write_apply` требует `plan_id` и `digest` от предпросмотра — одним вызовом его не снять | `snapshot_diff.scenario_answer` | да: убрать сценарии, если появится одношаговый вызов |

## C.9 — согласованные границы `verify` (2026-10-30)

Пользователь подтвердил: старый `_check_one_path` обрезает на 2 Ми символов и
сообщает о частичной проверке; `verify` проверяет весь файл до 4 МиБ включительно,
а превышение возвращает `invalid_input`. Диапазон >2 Ми символов и ≤4 МиБ —
также явное отклонение, не побуквенный паритет. Сырые ответы старого агрегатора
сохраняются в корпусе; ожидаемые результаты этой границы помечаются отдельно.
Отмена возможна отдельным решением о лимитах, не ослаблением тестов.

API/headless диагностика не переносится: доступность отражается в `unavailable`;
`kinds` — новый фильтр. Новый PathPolicy и строгая схема могут отказать раньше
старого кода. Blocking/CLI-ветки трёх repro остаются непокрытыми этим срезом.

## F1 — ремонт исторической BOM-границы (2026-10-31)

Историческая C.2 сохраняла ведущий BOM, и её файловый слой мог возвращать
false-clean; аудит C.9 локализовал это в принятом C.2. Пользователь разрешил
отдельный ремонт: основные файлы gd_lint/verify декодируются потоковым
utf-8-sig/errors=replace, ровно один BOM; исходные bytes/checked_bytes/CRLF
не меняются. Убрана ошибочная BOM-граница, а не добавлена новая политика линта.

Старые pure-text ожидания сохранены, алгоритм публичного lint_gdscript и
candidate/instance tscn остаются прежними. Partial EF BB сохраняет наблюдаемую
пустоту старого потокового decoder. Доказательства/приёмка дельты —
`docs/porting/verification.bom.md`, ADR-0008; историческая приёмка C.9 не
отменяется, открытая аудиторская F1 запись не переписывается портером.

## Что сюда не пишется

- Разница в тексте сообщений об ошибке при том же `kind` — это шум, не отличие.
- Изменения внутри модуля, невидимые снаружи (рефакторинг) — это не deviation.
- Незавершённый перенос — это не deviation, а незакрытая строка в `parity.md`.

## C.22 — закрытые решения D8/D9 (2026-11-02)

Возможность: `editing.file_refactor`; человек: аудитор, D1–D10 в листе механики;
архитектурная запись: ADR-0016 **proposed**. Это одобренные границы, не приёмка кода.

| Старое / предмет | Новое / граница | Причина | Обратимость |
|---|---|---|---|
| case-only native direct rename | без temp-hop, прямой перенос/casing | не вводить дополнительное имя и crash-фазу | только новым решением аудитора |
| история учитывает directory-состояния | пустые каталоги при rollback не воссоздаются | нет op mkdir/move_dir содержимого | нужен отдельный одобренный структурный op |
| native reference update сохраняет raw EOL | replace_raw вместо нормализующего script_edit | BOM/CRLF/lone CR/standalone LF байт-в-байт | возможно отдельным решением о payload |
| native casing parent/whole directory | последний dir_case, inverse первым | file move не меняет casing родителя NTFS | только новым решением о структурных шагах |
| companion_script из TSCN | информационный, сам скрипт не переносится | поле не является native companion-transfer | только отдельной механикой |
| native prepared absolute/raw | не публикуются в summaries | R-15, отсутствие машинных путей и сырых buffers | нельзя без нового решения контракта |
| native filesystem traversal files order | files лексикографически | стабильная projection, принятая C.21 | возможно отдельным решением о результате |
| прежний C.20 WAL: эффект → RECEIPT | EFFECT_INTENT до всех эффектов, включая create/delete/script_edit | D11: закрыть receipt-gap единым recovery; наше safety-поведение, не native parity | legacy WAL читается прежним способом; ослабление только новым решением |

Новых отличий этот раздел не разрешает. Внутренние raw oracle в корпусе не
являются публичными summaries; их original/masked SHA и provenance записаны явно.

### D13 — external-sync (решение аудитора 2026-11-02)

«внешний пустой каталог: location не восстанавливается, потому что мы его не перемещали;
план нулевой длины не создаётся».

Case-only file anchor при same realpath/raw SHA/actual destination casing уже
выполнен: отдельное anchor_already_completed в отчёте, без anchor Entry/receipt.
Rollback возвращает patches, но не ранее выполненный внешний case-only move.
При любом расхождении conflict. Empty/no-effect report не пишет WAL вообще;
entry_id=None не записывается в журнал. D13.1 сохраняет native external relative
literals и переписывает exact res://. Отмена — только новым решением аудитора.

## C.23 — закрытая prepare-only граница D14–D17 (2026-11-02)

Решения: аудитор, D14–D17 в `porting/editing.resource_ops.md`; не приёмка.

- D14: только normalize/digest/raw SHA/prepare/public projection/summary;
  native editor apply и transformed bytes относятся к C.24, не эмулируются.
  TOOLS=(), контракт27; accepted write dispatch/replace_raw/ADR не меняются.
- D16: target и dependency одинаково resolved-identity + casefold до prepare,
  addons/history/project.godot/escape запрещены при любых trusted flags.
  «trusted addon edits не портированы»; root plugin.cfg разрешён только read
  dependency. Native тексты/порядок отказов сохраняются, AppError.kind —
  отдельная типизированная проекция, не изменение native сообщения.
- D17: **ровно четыре** инфраструктурных пути; причина для каждого —
  «tool-less вклад без публичного инструмента»:
  `tools/selfcheck.py` (только corpus discovery/routing по module_id),
  `tools/snapshot_diff.py` (data-declared internal_call, прежние909case bytes frozen),
  `tools/probe.py` (internal prepare client без public имён),
  `python/runtime/bootstrap.py` (только composition module-owned read-only порта,
  прежние порты/имена/порядок/параметры неизменны).

`python/substrate/fs/resource_read.py` отклонён; второй substrate read-порт не
создаётся. Module-owned ports.py поверх существующего DiskFileSystem использует
realpath и его containment; отдельная настройка max_bytes=sys.maxsize сохраняет
native full-file SHA, не наследует cap4MiB текстового чтения. Никаких иных
отличий, BOM/EOL трансформации или расширения accepted ADR-0016 это не разрешает.
Отмена границ — только новым решением аудитора.

## C.24 — D18, resource bytes и ограниченная cohesion (2026-11-02)

Решение: аудитор D18 в листе resource_ops, ADR-0017 **proposed**, не приёмка.
Закрытый список: EOL/final-EOL preservation; section/span-сериализация и
existing IDs/comments/UID; bounded textual validation вместо ClassDB/editor
semantic preview; existing WAL вместо native save/reload/cache lifecycle;
разовое R-06 cohesion превышение editing-area до 8400 строк включительно.
BOM — **отказ**, `invalid_input` с native `ResourceLoader не смог загрузить ресурс`
и code `load_failed`, исходные байты неизменны. CRLF/lone CR/mixed EOL сохраняются;
replacement получает EOL заменяемой строки, insertion — доминирующий (first wins
при tie, LF при отсутствии). Final EOL не добавляется, existing final EOL цел.
Это не ResourceSaver formatting parity; unsupported schema/class/Variant
отказывает до PREPARED. Dependencies не переписываются, public bytes/abs запрещены.

R-06: 8000 не меняется, interval (8000,8400] — warning, >8400 — error во всех
areas, без resource-specific/per-file allowlist. Причина: единый immutable
resource document связывает spans, IDs, операции и raw-byte контракт; feature
logic не уносится в kernel и не дробится только по размеру. Editing baseline7997;
потолок 8400 закрытый, другие file/entry/module limits и guards неизменны.
Red-тесты до правки, верхний safety pin и мутация guard обязательны по R-22.
Снять границу или добавить отклонение можно только новым решением аудитора.

## C.25 — D20/D21, закрытый internal-only периметр (2026-11-03)

Решение пользователя D21, причина: **«internal-only сервис без публичного инструмента»**.
Устаревшее допущение «модуль обязан давать публичный инструмент или вклад»
опровергнуто тремя независимыми actual red-пинами: 3 failed / 1 passed,
`c25-d21-20261103/d21-original-red/red-run.stdout.txt` содержит дословные имена,
AssertionError/ValueError и исходный JUnit. Это допуск инфраструктуры, не приёмка C.25.

Закрытый список ровно трёх D21 файлов:

| Файл / функция | Разрешённое изменение | Неизменная граница |
|---|---|---|
| `python/kernel/module_spec.py` / `ModuleSpec.__post_init__` | идентичность также задают internal_services, entrypoints или capabilities | совсем пустой spec и прежний текст ошибки; ID/environment/corpus/uniqueness/прочие поля прежние |
| `python/runtime/bootstrap.py` / `_register` | tool-less internal_services/entrypoints регистрируются без фиктивного contributes_to | public tools требуют call; ports/profile/failure isolation/чужие регистрации прежние |
| `tools/selfcheck.py` / `module_readiness` | internal-only с тестами и корпусом ready | None/empty/no-tests/no-corpus не green; selector/формат/семь проверок/прочие функции прежние |

Публичный tree не появляется: `TOOLS=()`, contributes_to только реальный consumer
следующего среза. Отмена — только новым решением пользователя, не hardcode по имени.
Public read — единственный прирост контракта 27→28 по D20; типизированная проекция
native helper без внешнего 60000-character transport clip. D20 отдельно разрешает
только новый list_entries в существующих disk_fs/memory_fs, без изменения list_files
и принятого search; pointer entries не выдаются и не обходятся. Реальная WinError1314
обозначается skip с точным текстом, не выдаётся за зелёное доказательство symlink.

### D22 — четвёртый guard, разрешение аудитора 2026-11-03

`python/runtime/module_loader.py::load_one`: только условие отказа — одновременно
пустые provides_tools/internal_services/entrypoints; прежний текст «нет TOOLS
(ADR-0006)» дословно. Discover/порядок/изоляция R-03/прочие ошибки неизменны,
исключений по module_id нет. TOOLS дерева остаётся (). Actual loader/bootstrap
red2 до правки сохранён в c25-d21-20261103/ и новом c25-d22-20261103/.

**допущение ADR-0006 уточнено решением аудитора D22, поправка ADR — за аудитором**.
Принятый ADR-0006 портером не редактируется.

Два skip `test_real_symlink_type_is_checked_before_traversal[False/True]` приняты
по D20.4/D22: Windows действительно отказала os.symlink с WinError1314, точный
текст `symlink unsupported: WinError 1314`. Это не green coverage. Проверка типа
записи перед обходом существует: lstat/stat(follow_symlinks=False), symlink и
FILE_ATTRIBUTE_REPARSE_POINT; настоящие четыре NTFS junction проверяются без skip.

Аудитор определил169 UID как мусор прогонов и разрешил точечное удаление ровно
сохранённого списка, с bytes/SHA/mtime/ctime; proof cleanup169 в новом досье.
Дальше после каждого selfcheck/live фиксируются созданные UID и убираются в том
же шаге, исходные UID остаются побайтово прежними. Это не broad glob-cleanup.

### D23 — разрешённый аудитором inventory-only context projection

После actual non-live5225=executed (7failed/5216passed/2true1314skip) и snapshot1237
(1236matched/1difference) аудитор явно разрешил через question D23 узкую правку
`fixtures/corpus/context/gather/001-all-sections.json`: только tools.count26→27,
names+read,effects.read="read"; в manifest только SHA001. Прочие fields/cases,
reference SHA/captured_at и production context неизменны. Это композиционный
инвентарь нового публичного read, не изменение механики context и не context
consumer внутреннего дерева (он остаётся следующим срезом).

По D19 после того же actual red обновляются только values inventory-пинов:
contract test_functions/test_usages; integration test_gd_lint/test_node/test_scene/
test_tscn_lint; test_resource_ops — только appended project_text_fs в port order.
Полные assert-сравнения, no-public/no-conflict/unknown-tool запреты неизменны;
без фильтрации registry и без ослабления ожидаемых effects соседей.

C.25 provenance repair: ранняя собственная запись «only_exts=[] как None»
не была разрешённой девиацией. Actual native tree-only-empty и повтор helper
с exact[] выбирают0files/сохраняютdirs. Ошибка recorder устранена: own007
native_result/expect и его SHA в own manifest обновлены, pure condition
`only_exts is not None` даёт actual red1→green1. Cards22/unit23 неизменны;
referenceSHA не менялся. Полный final маршрут повторён на исправленных bytes.

Final C.25: nonlive×2collect=executed5225/5223pass/2documented1314skips each,
snapshot1237matched,44freshreports29ok/15existingblocked;read38/35/tree23/22ok.
Gates568=563+3production+2ownmoduletests,2existingwarnings,contract28,security0;
live3exact335→419→335,M1–M3/P1–P3 proven. Аудит готовности не приёмка; стадии,
ported/acceptedADR и parity не изменены. ADR-0006 debt сохраняется за аудитором.

## B-1 — D24/D25/D26: решения аудитора до первой правки (2026-11-03)

STOP портера: `%TEMP%\opencode\c8_audit\b1-stop-20261103` (досье запечатано
SHA256-stop.json; репозиторий и native побайтово неизменны; Chrome не
запускался; временный selfcheck-report сохранён наружу и удалён — проверено
аудитором: 44 отчёта, WORKLOG 675 480 B, `project.godot` `958b3a92…`).

### D24 — no-focus запуск: фасад владеет запуском, transport-файлы — эталон

Native `browser_manager.py:156–170` не передаёт STARTUPINFO (AST-доказательство
портера + мой grep по всему native: `STARTUPINFO`/`SW_*` в `python/**`
отсутствуют), тогда как R-21 и контракт-данные закрепляют свёрнутое окно без
захвата фокуса. Правило главнее кода (AGENTS.md §5): verbatim-стратегия служит
R-21, а не отменяет её. Разрешён **не-verbatim фасад ≤100 строк**, который
владеет запуском: pinned аргументы из `contract/browser_stealth.json` +
`STARTUPINFO(STARTF_USESHOWWINDOW, wShowWindow=SW_SHOWMINNOACTIVE)`,
`close_fds=True`, **отказ (fail closed)** при занятом порте 9222 без проверки
владельца (native-attach к живому порту не переносится), хранение process handle
и уборка только собственного процесса; подключение selenium — через
`debuggerAddress` с `popen_kw={"close_fds": True}`. Оба нативных файла
(`browser_manager.py`, `cdp_ws.py`) остаются в `substrate/llm/browser` побайтово
как эталон; их `setup_browser` в B-1 не вызывается — это осознанное отклонение
от verbatim в пользу R-21, не «улучшение» (diff фасада против native запуска
описывается в листе). Пины: unit — Popen получает startupinfo с
SW_SHOWMINNOACTIVE (mock), занятый порт → отказ без Popen; живой — окно без
захвата фокуса, `navigator.webdriver === false` честно. Это заменяет пункт 4
моих разрешений в `_start-prompt.browser_b1.md` («обе правки verbatim, фасад
только клей»): фасад владеет запуском, правки verbatim-файлов по-прежнему
запрещены.

### D25 — профиль: disposable sibling только для live

Разрешён новый пустой профиль `%LOCALAPPDATA%\Godot_AI_Profile_B1_<nonce>`,
только для live-прогонов B-1: создаётся прогоном, удаляется тем же прогоном с
доказательством (nonce, до/после listing каталога %LOCALAPPDATA%). Существующий
`%LOCALAPPDATA%\Godot_AI_Profile` не читается, не изменяется, не копируется и не
удаляется (портер подтвердил: содержимое не открывалось). Production-пин пути в
`contract/browser_stealth.json` не меняется. Chrome не запускается без этого
решения; при занятом 9222 — отказ без запуска (см. D24). Это расходится с
exact-путём live-пина сознательно: путь pinned для production, тестовая
изоляция — гигиена, не ослабление.

### D26 — маршрут R-18 для substrate-среза B-1

`tools/selfcheck.py browser` неприменим к substrate (браузер вне 44 механик) и
не запускается в сдаче; фиктивный модуль не регистрируется; `selfcheck.py`,
`gen_contract`, `lint_arch` не правятся. Приёмка B-1 = батарея: (1) focused
pytest новых substrate-тестов + security-стражи; (2) неизменённые общие гейты
`lint_arch`, `check_limits`, `gen_contract --check`, `security_audit`; (3)
двойной прогон fixture-корпуса (file:// кадры) без расхождений, отчёты наружу;
(4) живой запуск Chrome по D24/D25 с полным докладом; (5) своя мутация
red → restore байт-в-байт → green. Маршрут закрепляется в листе
`docs/porting/browser.md` (секция «Проверка (R-18 для substrate)») и здесь.
Новые отчёты не пишутся в `reports/selfcheck/` — 44 канонических остаются
нетронутыми; вердикт батареи печатается в stdout и хранится в досье.

Порядок после решений: лист до кода → marker «B-1 в работе» в parity-блоке
«Отложено» → native-корпус (file://) → красные стражи → фасад D24 → green →
мутация → двойной прогон → live D25 → передача аудиту.

### D27 — B-1: first-run только в тестовой изоляции и драйвер (2026-11-03)

Два своих oracle-прогона с пустым sibling D25 открыли chrome://intro/ вместо
обычного окна. Во втором foreground PID10320 совпал с process handle Chrome;
Target.createTarget отказал: `Failed to open new tab - no browser is open`.
STARTUPINFO dwFlags=1/wShowWindow=7 был передан. Оба процесса завершены и оба
профиля удалены; listing %LOCALAPPDATA% до/после совпал. Первый prelaunch fail
из-за отсутствия константы в subprocess также убран (только собственная пустая
директория); SW_SHOWMINNOACTIVE — WinUser.h constant 7.

Пользователь явно разрешил через два вопроса:
- `--no-first-run` **только в disposable live/oracle запуске D25**; production
  контракт и transport-эталоны неизменны. First-run UI не проходить, никакие
  настройки/данные существующего профиля не читать. No-focus/minimized и
  честный webdriver=false заново доказываются, не предполагаются по флагам.
- официальную загрузку совместимого ChromeDriver156 через Selenium Manager
  (локально были только154/155); источник/версия/SHA — наружу. Это зависимость,
  не посещение площадок и не расширение маскировки. Несовместимость драйвера
  не обходить и не отключать проверку версии.

Доказательства/неуспешные попытки сохраняются во внешнем b1-final-20261103
досье. Статус B-1 остаётся в работе, не ported и не принят.

### B-1 — открытый STOP SEC-20 (решения ещё нет)

После успешного native-корпуса D27 (2 own file:// pages, minimized/no-focus,
webdriver=false, process/profile cleanup) external byte-exact preview выявил:
неизменённый check_browser_stealth краснит hasFocus/toString в native
browser_manager.py:71–73. Это JS-комментарии внутри VISIBILITY_SPOOF_JS;
страж снимает только Python # комментарии. Отказы реальные (вызван тот же
неизменённый checker на sandbox-копиях), не предсказание по grep.

Transport ещё не скопирован в production, фасад/тесты/мутация не начаты.
Нельзя вырезать native-комментарии, сокращать forbidden_techniques или менять
замороженный security_audit в B-1. Требуется решение аудитора; exemption и
изменение правила не объявлены. Proof: sec20-native-preview.json в досье.

### D28 — SEC-20: распознавание JS-комментариев в проекции стража (2026-11-03)

STOP B-1 (b1-final-20261103): неизменённый `check_browser_stealth()` на
byte-exact native-копиях даёт 2 ложных срабатывания (hasFocus, toString) — оба в
`//`-комментариях внутри JS-литерала `VISIBILITY_SPOOF_JS`
(`browser_manager.py:71–73`, текст о «НЕ подменяем»). Страж вырезает только
Python-комментарии (`#[^\n]*`) и ищет подстроки по всему raw. Инвариант SEC-20
сам обработку комментариев не определяет; комментарий в коде стража («упоминание
в комментарии не код») фиксирует намерение — это неполнота проекции стража, не
изменение правила. Отдельным решением утверждаю **узкий ремонтный срез
`sec20_js_comments`**, выполняемый портером (дешёвая модель достаточна), вне
рамок B-1 — запрет на правку стражей действовал только внутри B-1.

Разрешено и обязательно:
1. **Сначала red-пины** (новый `tests/py/security/test_sec20_js_comments.py`):
   (a) реальная подмена в JS-коде (например, `Object.defineProperty(window,
   'hasFocus', ...)` в JS-литерале) — красная до и после фикса;
   (b) JS-комментарий-описание с токеном forbidden_techniques — красный до фикса,
   зелёный после.
2. **Фикс проекции** (только в `check_browser_stealth`, только проекция скана):
   после выреза Python-комментариев добавить вырез полных JS-строчных
   комментариев: `re.sub(r"(?m)^[ \t]*//[^\n]*", "", text)`. Проекция общая для
   forbidden/pinned/launch/forbidden_paths сканов — комментарий не должен
   триггерить ни одну из них. Инлайн-`//` внутри строки кода не вырезается
   (риск для `https://` в строках) — остающееся FP-направление консервативно и
   допустимо; FN-направление запрещено.
3. **Green**: SEC-20 зелёный на byte-exact native-копиях обоих transport-файлов;
   forbidden_techniques, `contract/browser_stealth.json`, остальные чеки
   security_audit и другие стражи не тронуты; файлы вне границы байт-идентичны.
4. **Мутация**: удалить добавленный вырез → FP возвращается → restore
   байт-в-байт → зелёный. Двойной прогон security_audit (ok/0), отчёты наружу,
   в `reports/` не писать.

Запрещено: удалять/править native-комментарии, сокращать forbidden_techniques,
менять контракт, трогать другие чеки и гейты, начинать B-1-код до зелёного
SEC-20. B-1 возобновляется после приёмки этого среза. Мой запрет «не править
security_audit» из `_start-prompt.browser_b1.md` распространяется только на
рамки B-1; D28 — отдельное явное разрешение с red-пинами на реальные подмены.

### Статус D28 — принято аудитом (2026-11-03, сессия 78)

Срез `sec20_js_comments` исполнен портером и принят независимым аудитом:
фикс — ровно одна добавленная проекция `(?m)^[ \t]*//[^\n]*`
(tools/security_audit.py, +57 B, CRLF сохранён). Мутация аудитора (вырез
строки 197) возвращает файл байт-в-байт в состояние до фикса (77956be3…) и
даёт ровно 8 ожидаемых красных; byte-exact restore → зелёный 16/16; полный
tests/py/security — 148 тестов / 0 fail / 0 err / 2 прежних skip; security_audit
ok/0. Граница соблюдена (вне двух файлов байт-идентичность). B-1 возобновляется
по D24/D25/D26.



### Статус SEC-03 non-listening probe — принято аудитом (2026-11-03, сессия 78)

Срез `sec03_nonlistening_probe` исполнен портером и принят независимым аудитом.
Граница — ровно 5 файлов (tree-before → tree-final: +лист, +тест 71; изменены
WORKLOG, invariants.md (SEC-03), tools/security_audit.py 10942 → 14764 B), вне
границы — байт-идентичность всех 3937 файлов репо.

Прогоны аудита: фокус 71/71 ×2 (двойной корпус), полный tests/py/security
237 passed / 0 fail / 0 err / 2 прежних skip, B-1+D28 regression 93/93;
lint_arch 569/0, check_limits ok/2 (прежние), gen_contract --check 28/0,
security_audit ×2 ok/0. Мутации аудита: (1) `allowed_bind = -1` (сокрытие
исключения) — ровно 3 красных (canonical LF/CRLF + actual frozen facade);
(2) нейтрализация reflection-фильтра (`node.id in set()`) — 0 красных в наборе
(каждый кейс портера ловится и другими фильтрами), но прямой пробник доказал:
только reflection-фильтр отсекает динамическую сборку имени
(`globals()['soc' + 'ket'] = ...`) — принятый guard возвращает None (denied),
мутант — 277 (маскированный rebind прошёл бы). Byte-exact restore после
каждой мутации. Замечание (мелкий долг): reflection-фильтр не имеет
независимого мутационного покрытия в тест-наборе — добавить кейс, где он
единственная отсечка.
### D29 — B-2: классовый допуск FILE_MAX 400→600 для verbatim-эталонов substrate/llm/browser (2026-11-04)

Native `net_monitor.py` — 456 строк, 24206 B, один сплочённый класс `BaseNetMonitor`
(33 метода). Verbatim-паритет R-08 запрещает резать сплочённый класс (D24-прецедент:
разрезанный вербатим нельзя сверить побайтово), а жёсткий FILE_MAX=400 стража R-06
делает байтовый перенос невозможным. Решение: классовое правило в
`tools/check_limits.py` — для файлов по каталогу `python/substrate/llm/browser/`
(verbatim-эталоны browser-ветки) FILE_MAX 400 → 600; вне каталога лимит прежний.
Правило по каталогу, не по одному файлу: последующие B-3-эталоны
(ai_studio_net 224, qwen_net 238 строк) укладываются и в 400, но допуск не точечный хак.
Красные пины до правки стража (tmp-структура + monkeypatch, не живое репо):
456-строчный файл под substrate/llm/browser красен с «лимит 400» и зелен после;
601-строчный под каталогом красен с «лимит 600»; 456 строк вне каталога остаются красными.
Мутация допуска: снять правило → страж снова красен на тест-файле → byte-exact
restore → зелен. Прочие гейты не тронуты; check_limits обязан остаться ok
с теми же двумя прежними предупреждениями (split_py 11, editing 8400) и без новых.

### D30 — SEC-19/SEC-20: статический разбор многострочных site flags (2026-11-04)

STOP B-3 доказан на трёх byte-mutants native sites.py: поднятые kimi/arena/
arena_battle False→True проходили прежний однострочный regex; inline control
отсекался. Пользователь отдельно разрешил узкий ремонт security_audit и тесты,
не изменение контракта/маскировки/B-1/B-2. Правило SEC-19/SEC-20/R-21 прежнее.
Дополнительно разбираются Python AST dict с id/needs_visibility_spoof независимо
от порядка/LF/CRLF; True допускается только literal id с pinned admission;
нелитеральный id/boolean не доказывает допуск, broken sites.py denied.
Прежний regex и D28 projection сохраняются для JS/text fixtures. SEC-03 helper
не меняется. Это статический контроль literal records, не sandbox Python и не
доказательство полноты runtime. Скелет без записей пока допустим.
Red до кода:28 выполнено,19 expected failures/9 passed; лист browser-sec19.md.

### D31 — B-3: эталонный срез, не закрытие рабочего browser runtime (2026-11-04)

После STOP пользователь выбрал пять byte-exact эталонов с честными offline-тестами
на инертных зависимостях. Native absolute net_monitor/server_state не находятся
в новой package-раскладке; parsers не входят в эти пять файлов. Production
sys.path/sys.modules aliases, bootstrap и старый server_state не добавляются.
Сборка работающего runtime/парсеры/записанный site live требуют отдельного мандата.
LiveInputMirror делегирует parser.mirror_input (не содержит CDP Input); backend
отправляет один prompt (не собирает message history). Корпус фиксирует native,
не ошибочные обещания промпта; тестовый scoped dependency injection не runtime.
Завершение B-3 означает готовность эталонного среза к независимой приёмке, а не
ported/accepted всей browser-ветки. PROGRESS/44-таблица остаются frozen по D26.


## D32 — B runtime: классовый лимит byte-exact parser-эталонов (2026-11-04)

Явный B.1 мандат разрешает достаточный FILE_MAX для native parser_base.
Только python/substrate/llm/parsers/ получает3400 строк; browser600, обычные400,
entry/module/area/cohesion-пределы неизменны. Native parser_base3352 строки.
Редукция исходника нарушила бы SHA/R-08; это verbatim-класс, не исключение файла.
До правки guard: corrected red-limit-corrected — 2failed/3passed; разрешённые
3352/3400 пока красны по400, остальные три запрещённые границы правильно красны.
Первый общий red имел дефект harness-вызова check_files(args), сохранён в dossier;
исправлен только test API до production, чистый red проведён заново.
Прежние split_py11/editing8400 warning должны остаться ровно двумя.

## D33 — B runtime: explicit aliases и D24-owned wait_driver, частичный Arena

Спецификация до кода в docs/porting/browser-runtime.md, B kickoff2026-11-04.
Runtime bindings — только явно импортируемый substrate-модуль, не bootstrap/tool;
legacy alias is canonical module, idempotent, foreign alias refusal, явный missing
reference и rollback только новых aliases. Нет sys.path/meta_path/PathHook.
server_state НЕ переносится: единственный alias указывает на runtime_owner со
швом wait_driver, который выдаёт driver только настоящего живого D24-facade.
Native deadline/messages/0.25s polling/driver-before-error и zero/negative deadline
сохраняются; trusted booter лениво запускается один раз, не расширяя Chrome launch.
Raw set_driver/STATE/сервер/Flask/история отсутствуют. Caller владеет facade cleanup.
Native Arena:19 импортирует answer_judge безусловно; позднее тянет server STATE.
Семь parser-файлов переносятся byte-exact, но Arena import/judge/STATE остаются
deferred без фиктивного judge. Проверка честного missing dependency не является
закрытием требования B.3 об инертном Arena import. Полная B-приёмка пока невозможна
без отдельного решения; допустим только частичный вердикт.
Optional json_repair/brotli остаются native optional, не маскируются заглушками.
Новые raw inputs — synthetic, источник/native pins и двойные observations в
fixtures/corpus/browser/runtime/manifest.json; native tests не копируются/не исполняются.
Native parser_corpus write failures в тестах уходят только в external basetemp;
Kimi tool-only debug-finalizer не исполняется. Production-профили связку не импортируют.
tests-map174–202 deferred остаётся byte-exact: новые частичные кейсы не закрывают
полный legacy-файл. parity/PROGRESS/44 canonical reports и stealth контракт frozen.

## D38 — routing-runtime: новые byte-exact reference-классы (2026-11-05)

Размещение A: `python/substrate/editor/references/` (runtime_debug/editor_context),
не существующий editor transport; B: `python/substrate/llm/backends/` (api_backend).
Мандат routing-runtime разрешает directory-class FILE_MAX3400 для новых эталонов.
Entry/default/editor transport/browser/parser/API/module/area/cohesion caps прежние;
точные границы проверяются собственными red-пинами до правки check_limits.
Нативные imports/bytes не правятся, aliases только explicit runtime_bindings D33.
Corpus-before-code по R-07/R-16; D37 Authorization-only observer masking и D36
real DoH deferred сохранены. Это reference-срез, не публичный ToolSpec/MODULE/HTTP
и не повышение ported. Приёмку реализации назначает независимый аудитор.

## D39 — project-core: byte-exact foundation reference (2026-11-06, F0)

Размещение двух эталонов: `python/substrate/project/project_tools.py` и
`python/substrate/project/project_settings_actions.py`, один инертный __init__.
Pins: project_tools102471B/79e9b035bd211f4a44623573d64f88f5bf47a049725c18dc90d985f47c6a7877/
LF1960/CRLF1960; settings13735B/fcdb4635aa8ccb965f0775e6b52f6f339c18809da3a3baac3b9e12da6c8e932f/
LF251/CRLF0. Импорты/содержимое/EOL сохраняются без edits.
F0 разрешает errno/os/shutil/stat/tempfile + accepted text_sanitize; settings:
hashlib/json/math/os/re/uuid + project_tools. Поздние stdlib posixpath/re/hashlib/
difflib сохранены, новых application/network/binary зависимостей нет.
Directory-class FILE_MAX2000 только для python/substrate/project/ и потомков,
не prefix-lookalike; module.py/tools.py150/app.py80 всегда приоритетны.
Default400/browser600/parser/API/routing3400/module3000/area8000/cohesion8400
и две прежние warnings не меняются. Точные 1960/2000/2001 и escape/entry-границы
должны дать red до правки check_limits, затем green; широкое ослабление запрещено.
Bindings: ровно project_tools и project_settings_actions после parser aliases,
настоящая identity accepted text_sanitize проверяется при импорте project_tools.
27 старых пар/их порядок и D33 identity/idempotence/conflict refusal/rollback
только новых aliases сохраняются; production bootstrap не интегрируется.

SEC/spec: containment realpath+normcase, history fail-closed, addon/self-edit
независимы и требуют действительный inner addon root. Raw read проверяет корень/
history, policy-read дополнительно права; не объявляем raw helper публичным safe
tool. Generic project.godot write denied. Settings schema/normalize/prepare читает
hash и готовит intent; apply/confirm/undo/ProjectSettings.get/set/HTTP/Godot deferred.
Architecture/autoload — read observations с can_read filtering. Case-only parents
проверяются на fixture-копиях: commit/idempotence/rollback/apply-failure/recovery
failure, exact file SHA и casing. UNC local seam не является live SMB проверкой;
symlink1314 — honest capability refusal, real junction coverage отдельно.
Byte-exact raw write helpers существуют в инертном эталоне, но никакой публичный
эффект/ToolSpec/MODULE/воронка/production call этим срезом не разрешаются.
Corpus→spec→tests→code соблюдается. Mutation obligations: can_read deny→allow,
resolver realpath→abspath, alias identity; дополнительно class/rollback где нужны.
Никаких улучшений native/SEC-06/старых ожиданий или новых skip/xfail.
Полные project_ops.settings_get/settings_set/architecture остаются0/skeleton;
case sources Flow/STATE/history/editor completion не закрываются foundation-корпусом.
Это ещё не принятие: независимый аудитор назначает итоговый вердикт.

### D39 — fixture ownership / проверенный closeout (2026-11-06)

Project-core synthetic projects хранятся в fixtures/corpus/project/fixtures/ и
byte-copy materialize во внешние sandboxes. Причина: global scene-deps corpus
владеет .gd под fixtures/projects; новые project refs не расширяют его scope.
Перенесён только новый session-owned fixture tree, все17 fixture SHA/bytes/
relative paths,288 goldens и manifest exact; frozen old test/corpus не менялись.
Первый full6564 ×2 exit1 сохранён; final full ×2=6562pass/2 legacy1314skip.
D39 caps/byte-exact imports/no MODULE policy прежние. Reference готов к audit,
не accepted; public Godot get/set и ToolSpecs отдельно. No SEC-06 weakening.

## D40 — engine-cache dormant byte-exact reference placement / C11 coexistence

History48840B/f6655173 CRLF939 -> substrate/store; cache11545B/6e6f5e0c LF216
-> substrate/engine; API9137B/b9e0df9f LF201 and lint9640B/66618648 LF191
-> new substrate/verification. Original imports/EOL unchanged; dependency order
project_tools -> history_manager -> gd_api_cache -> gd_api_check; gd_lint stdlib.
F1 full AST closure verified; no Flask/backend/judge closure, no import side IO.
Existing C11 api_cache_loader/store snapshot projection, classes(), public tool,
contracts/ports/bootstrap unchanged. Native cache is a separate dormant reference:
load can migrate/write; save_cache(root,classes,version,addon) directly writes
sandbox files. It is NOT the C11 pure snapshot provider and not a production tool.
History native user-storage override/locks/journal/errors/rollback preserved, not
integrated into the accepted durable WAL/funnel or assistant history MODULE.
No new ToolSpec or effects: native writes are only exercised through fixture doubles.

## D41 — pinned engine API dataset, not executable/configuration or user storage

Native addon-root agent_api_cache/default_api_cache.json,2004630B,
SHA2567352d27c8d8ed77b84b3b98400093c85144c4b6f8b8919b147ca035a67c8a93c,
LF0/CRLF0, copied unchanged to plugin-root same path last, no module alias.
Read only during tests; refresh/migration writes only disposable user/addon copies.
Unchanged SEC06 patterns scan dataset explicitly; any match requires honest STOP.

## D42 — narrow engine/store/verification byte-reference classes3400

Only python/substrate/{engine,store,verification}/ descendants, exact directory
prefix and entry names still priority module.py/tools.py150/app.py80.
File default400/browser600/parser/API/routing3400/project2000, module3000,
area8000/cohesion8400, folder5–9 and original two warnings unchanged. Actual
939/3400/3401/lookalike/outside/entry boundaries must fail before class additions.
Do not integrate these classes with C11 behavior or loosen global caps.

## D43 — explicit binding fixed-count pins and F1 one-token authorization

Binding fixed-count expectation changes minimally with an explicit extension,
always equals actual len(BINDINGS). For this F1 only accepted test line16 changes
29->33, one token, other bytes and LF94/CRLF0 exact. Actual red with expectation33
and old29 table must precede code; retained memory33/old-test29 refusal is separate.
Other accepted pins remain exact without explicit audit authorization; future
extensions still require red-before-code and minimal sanctioned count change.
Four explicit aliases append at absolute end after all29 existing pairs, so the
project pair stays after deepseek_parser and before old runtime/API/routing pairs.
D33 identity/idempotence/conflict/BaseException/new-only/replacement-preserving
rollback algorithm unchanged; no sys.path/meta_path/path-hook or production wiring.

Corpus228=history72/cache36/API55/lint65 captured actual native twice. Old52 API
inputs/raw outputs reused, no contract envelope invented;3 synthetic inputs;
literal lint errors/skip cases; history real Windows busy-file/casing, BOM/CRLF,
atomic fsync/replace cleanup, partial rollback compensation/retry, lock reentrancy.
Initial observer signature refusal retained; no golden/body/security mask change.
Mutations planned: atomic journal direct write, broken JSON validation bypass,
API denial/quota reduction, weakened lint declaration regex, plus class and alias
identity if needed. Each submitted bytes red/exact SHA+EOL restore/same tests green.
Concurrent-worker, live Godot/engine_info/refresh MODULE/HTTP/tscn aggregator/judges
remain deferred; engine_info/refresh MODULE0/skeleton; independent acceptance only.

## D40 failure observation / guarded-call receipts

Signature guard rejected record_change type/path misuse before publication; actual
action-dict call fixed. Next capture differed only one native leftover rollback
temp basename in batch second-replace failure/retry. Native leak retained: one
10-byte temp with original B SHA; no cleanup improvement. Normalize only its
random owned basename, assert no multiplicity collapse; preserve count/bytes/SHA
and all results. Both refusals/rounds retained. Next final capture+native replay.

## D40/D41 partial evidence: coexistence STOP, not accepted

F1 final full6833×2 has25 failures (1 browser line budget,24 old bundled-cache
availability expectations). Source C11/classes()/snapshot()/bootstrap unchanged;
mandated dataset at addon-root activates their existing fallback. Sandbox-only
counterfactual0→1488 classes proves cause without source or real-cache changes.
Do not weaken tests/pack source lines/move data as a covert workaround. D40/D41
remain partial reference evidence, pending explicit isolation/deployment scope;
independent acceptance not granted. Seven exact-restored mutation kills retained.

## D44 — deployed default data and explicit degradation environment (F2)

Repo-root agent_api_cache/default_api_cache.json is native-default input;
unchanged C11 fallback may legitimately read1488 classes/4.6.3-stable (official).
Degradation tests select an explicitly empty sandbox addon. Only test-side
bootstrap.ApiCacheStore factory is patched for F2-approved cases in exactly5
integration files; constructor delegates to original class with project/state
unchanged and sandbox addon only. AGENT_DIR and PathPolicy line98 untouched.
Other cases retain real addon/default data. Assertions/corpora/C11/bootstrap
source remain exact. Deployed fallback/read-only pin is added to existing data
test (new attacking assertions, not a new pytest ID), preserving6833 collection.

## D45 — explicit binding line-budget pin adjustment (F2)

Sole accepted browser-test token at line34 <=60→<=72, other bytes/CRLF exact.
Actual submitted binding64→73 lines temporarily must make unchanged token72
guard red, then exact SHA/LF/CRLF restore and same test green. No source packing
or business-logic changes. Future pin changes require the explicit pin template,
token-only red proof; unrelated accepted assertions remain protected.

### D44/D45 final F2 observations (2026-11-06)

Actual browser-test byte/EOL recount LF98/CRLF0; only60→72, no EOL conversion.
Real73-line submitted binding killed guard, exact64-line restore green.
Factory-only empty-addon isolation across5files preserves all original assertions
and byte-reconstructable fixture-argument edits; C11/AGENT_DIR/PathPolicy/source
and1488 deployed default unchanged. Existing dataset pin asserts1488/version
4.6.3-stable (official)/read-only without adding or dropping pytest IDs.
Full6831passed/2legacy skips twice, frozen230 twice; old6564 outcomes/order exact.
Reference6 ready for independent audit, NOT accepted; MODULE0/skeleton.

## D46 — librarian: уточнённая explicit reference-связка (2026-11-07, спецификация до кода)

Основание: аудиторская поправка F0 в _start-prompt.librarian.md L69–143.
Только два новых BINDINGS в конце после engine-четвёрки: gd_semantic_parser,
librarian; прежние33 пары/порядок сохраняются, итог35. ml_data/ml_project_index
не становятся отдельными legacy-алиасами. ModuleType('minilich') без __path__
показывает атрибутами реальные canonical context.ml_data/context.ml_project_index;
identity/idempotence, foreign-parent refusal и BaseException rollback лишь своих
добавок обязательны. Native minilich/__init__.py не импортируется; production
bootstrap, sys.path/meta_path/path hooks не меняются. Это не MODULE context.ask.
Новая связка пока не реализована; hard source-budget72 остаётся действующим.

## D47 — librarian: narrow context reference-класс (спецификация, не реализация)

Разрешён лишь python/substrate/context/ и его настоящие descendants, FILE_MAX3400.
module.py/tools.py150/app.py80 всегда приоритетны; prefix-lookalike/outside denied.
Default400 и все browser/parser/API/routing/project/engine/store/verification caps,
module3000/area8000/cohesion8400/folder5–9 и две прежние warnings frozen.
До правки check_limits нужен настоящий red на новом классе; перенос/правка cap
не начаты, старый checker побайтно сохранён. Это разрешение, не зелёный вердикт.

## D48 — librarian: semantic leaf, byte-exact (спецификация до кода)

godot_tools/gd_semantic_parser.py → python/substrate/context/gd_semantic_parser.py:
15723B/bf35dcea5e77011dd758d7b0559c42cf61270d0361af3f62c65e63b6d4da8a8a,
LF392/CRLF0; единственный import re. Семантика/импорты/EOL не переписываются.
Абсолютный import index L36 закрывается ровно D46 gd_semantic_parser alias.
function_card/gd_functions/symbol_refactor_part1 остаются отдельными, без aliases.

## D49 — librarian: ml_data только инфраструктура storage индекса

minilich/ml_data.py → python/substrate/context/ml_data.py byte-exact:
32324B/e13d56800d124627679af96f3259192f280dae0bbae9c637fa5832a446ae96bf,
LF757/CRLF0. Полное статическое замыкание: hashlib/json/os/re/history_manager;
late shutil в set_storage_base, time в record_reference_exam_result, tscn_lint
в ensure_reference_material/generate_synthetic/revalidate_pairs. Последние NN/
reference-data процедуры не вызываются; tscn_lint alias не разрешён.
ml_model/ml_train/ml_tokenizer/ml_github/ml_fix и native initializer исключены.
storage_dir и set_storage_base без migration root вызываются только в sandbox.
Индекс64059B/474dcc3b959559b86e7d7a98250d44343d9adadf7305ce87cf23b9c06abf41dd,
LF1083/CRLF847, относительный ml_data рядом; librarian96356B/
90f4f66440fa6ecb8d97d28767abab35385259f1a4282f6219465a971cd1a383, LF=CRLF1525.
Все30 import statements четырёх источников, включая late/relative, перечислены
в external import-closure-all/reconciled.json до native execution.

Native _log_query глотает Exception, включая missing ml_data, а не бросает наружу.
Цель <history>/minilich/librarian_log.jsonl, fallback project/.agent_history/minilich,
override addon/minilich_brain; UTF8 JSON+LF, ts/root, strict >262144 rotation .1.
Только synthetic external storage, не user telemetry. L1214 function_card вне try
честно ImportError; L1221 внутри try молчит. Пока это static control-flow spec,
не наблюдённое поведение. Нельзя обещать all-read guards на основании MAP-filter:
native index L338/L455 открывает файлы напрямую, update_entries L645–712 и
_symbol_card L1095–1107 требуют отдельного native traversal/security наблюдения.
При outside read/exposure — STOP, не исправление byte-exact исходника.

## D50 — librarian: минимальная санкция engine binding pin

Только tests/py/engine_cache/test_engine_cache_binding.py L12: ==33→==35 и
BINDINGS[-4:]→BINDINGS[-6:-2]. Все прочие байты/assertions/первые29/late-gd_lint/
owned rollback остаются exact. Реальный неизменённый тест обязан краснеть до
токен-правки; D43/D45 и hard binding≤72 сохраняются. Пока old test unchanged,
red/токен-правок/новых BINDINGS0. Это спецификация, не доказанная реализация.

Историческое §0 archive-loss не скрыто: 1148 sealed0B empty.tscn отсутствовали.
Пользователь явно разрешил exclusive восстановление только этих файлов; все
31836 старых sealed files затем verified bad0, печать и существующие файлы exact.
Missing-list, before-tree, authorization и restoration receipts сохраняются
в librarian-20261107, исходные отказы не переписаны. Это не пересоздание прогонов.

### F1-librarian — уточнение D46–D50 по corrected-native (2026-11-08)

F1 _start-prompt.librarian.md L146–181 supersedes прежний LF-only/static logger
текст: corpus pins измеренные CRLF JSONL, strict >262144 rotation, measured ts/root;
native _log_query bytes unchanged. Security prerequisite native-first принят:
frozen72green×2. Corrected pins librarian340b5dd2/index2f7694a9, leaf/data unchanged.
D46 helper внутри старого try/lock/owned added rollback; ровно2aliases parser/librarian,
canonical minilich attrs, no __path__/NN/bootstrap. D47/D48/D49/D50 unchanged scope;
явный helper не изменяет старые33pair/order/algorithm, glue≤72. Контекст MODULE0/skeleton.

### 2026-11-08 — F1 partial transfer STOP-SEC03 (NOT accepted)

Corrected-native четыре файла перенесены byte-exact с исходными SHA/EOL;
явная связка: 35 пар, 69 строк, старые33пары/порядок/алгоритм восстановимы;
synthetic minilich без __path__, canonical data/index identity, owned-only
BaseException rollback, foreign-parent refusal. Native/init/NN/production неизменны.
D47 реальный red2fail/10pass→green12; D50/D43 реальный red2fail/15pass→green17,
accepted-test изменения только разрешённые count/suffix tokens.

Корпус: 141 newly-authored cases измерены genuine native дважды (initial124,
17 quota/exact-budget/ranking/index edges); guard72 genuine native×2 green.
Начальный case111 ошибочно сохранял cached minilich.ml_data; corrected genuine
absence twice молчит и не пишет, заменён лишь этот golden с backup/receipt.
Native/logger не изменены. Golden raw-base64 сохраняет измеренный CRLF JSONL,
ts/root/strict rotation>262144; реальная telemetry только sandbox.
Focused×2: каждый246collected/called/pass, exact ordered unique IDs и одинаковые
setup/call/teardown outcomes. Guard72 входит в каждый. Real junction coverage;
genuine directory/file symlink WinError1314 остаются gaps, НЕ pass.

STOP сработал при первом квартете гейтов: lint610/0; limits610/0 и ровно два
старых warning; contract28/0; security_audit FAIL/exit1, SEC-03 librarian.py.
Неизменённый tools/security_audit.py ищет .bind( в raw text и помечает native
GDScript search literals/comments как слушающий сокет. Actual matches:
librarian.py L111/L853 STRING, L848/L850 COMMENT; AST bind/listen calls=0.
Флаг НЕ подавлен; native/ported bytes НЕ правились ради аудита. Исправление
security-checker запрещено текущим scope (other tools), требует отдельной санкции.

Actual external-report selfcheck context.ask: FAIL/exit1 из-за SEC-03;
MODULE/unit/corpus механики по-прежнему not_implemented. Это не прежний blocked/2:
security fail доминирует. Actual sandbox probe ask: unknown_tool/exit1.
44 canonical reports/86UID/4sentinels/pyc0 сохраняются; diagnostics reports внешние.
context.ask остаётся MODULE0/skeleton; reference transfer НЕ принят, parity не повышен.

После STOP новые мутации НЕ начаты, post-transfer full/frozen/API253/native-project288
регрессии×2 НЕ выполнены, gates×4/security×2 НЕ завершены, независимой приёмки НЕТ.
Ранее принятые native-only baselines и исторические STOP/seals остаются историей,
не выдаются за проверки переноса. Все rejected harness attempts сохранены.

Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/librarian-transfer-20261108/.
**Этап:** context.ask MODULE0/skeleton; librarian reference1, partial STOP-SEC03.
**Следующее действие:** получить отдельное разрешение на узкую корректировку
SEC-03 классификации STRING/COMMENT vs executable calls с red tests настоящих
bind/listen и сохранением B-1 probe exception; без file-wide allowlist. Затем
получить security green и заново продолжить неисполненный цикл переноса.
До санкции не менять security_audit/native/bytes и не заявлять acceptance/parity.

## D51 — SEC-03: AST detector fixture, authorized (2026-11-10)

Разрешение аудитора WORKLOG872010B SHA56212cab…: raw listener regex ловил native
librarian GDScript search strings/comments (.bind), selfcheck fail/1. D51 переводит
SEC03 на реальные AST Calls, не file-wide allowlist. bind/listen/run/HTTPServer
реальные вызовы запрещены как раньше; parse error fail-closed. B-1 canonical probe
helper/tests/узкие approval constraints остаются в поведении, включая дополнительные
listener-text constraints старого exception; никакой реальной сети в fixture.
True-positive s.bind(('127.0.0.1',0)) must red; librarian-present false-positive
guard must green; red before minimal checker code, diff/pins в fresh dossier.
Четыре corrected-native source SHA/EOL неизменны; MODULE context.ask0/skeleton.

### D51 verification (2026-11-10)

Actual red106=17fail/89pass → same106pass, old B-1 bytes/outcomes unchanged;
minimal check_listener-only diff saved, corrected-native copies exact. Gates×4,
extra security×2 green; actual selfcheck blocked/2 (security ok), probe unknown_tool/1.
D51 infrastructure fixture complete, not MODULE/context.ask parity or acceptance.

### D46–D51/F1 final verification (2026-11-11; auditor acceptance pending)

Four corrected-native SHA/bytes/EOL exact;35binding pairs/69lines unchanged;
D47 narrow context cap/entry priority, D50/D43 token-only edits retain real red receipts.
D51 minimal check_listener-only AST diff, B-1 helper/tests unchanged; red106→green106,
gates×4/security×2+final×2 green. Focused352×2/native-canonical213×2; five submitted-byte
mutants killed with exact restorations; immutable full7096/frozen230/API253/native288×2.
No corpus normalization/logger/import/ranking/capability improvement. Symlink genuine1314
gaps remain, junction coverage real. Actual selfcheck context.ask blocked2/probe unknown_tool1,
MODULE0/skeleton, reference submitted only; independent acceptance follows separately.

## D52 — разрешён narrow corpus-catalog bugfix/replay (L2a, 2026-11-11)

Источник санкции: _start-prompt.librarian-L2.md131–156, WORKLOG9379–9397,
и сообщение аудитора по STOP §0. Предпосылка старого §4 исправлена: F1 corpus213
шёл через pytest, не snapshot_diff. Разрешены list records через прежний pipeline,
явная ошибка неожиданной структуры, новый reproduction red→green, новые helper
tests; минимальный вызов helper из snapshot_diff, corpus_folders по manifest.module.
Старые assertions/goldens/catalog/guard/fixtures не менять; весь старый corpus
и selfcheck-readiness/selector×2 до/после, actual IDs/outcomes; ярус B.
Статус: решение получено, common-code bugfix/helper НЕ реализованы.
Открытая несовместимость D52§2: native observations001-tokens/107-log имеют dict
result (private token/log operations), публичный answer возвращает str,107 нет
query. Нужна отдельная санкция на component213 + реальные public checks; нельзя
маскировать эту разницу недетерминированной нормализацией. Измерения в L2a dossier.

## D53 — native logger в profile state_dir, no-op запрещён (L2a, 2026-11-11)

Источник санкции: _start-prompt.librarian-L2.md158–174 и WORKLOG9379–9397.
Формулировка F0 «нативное молчание» отменена: healthy logger реально пишет;
native исключения по dependency/storage глотаются как прежде. Лог/index/cache
только в state_dir профиля, не в проекте; native rotation строго>262144→.1,
JSONL UTF8/CRLF; запрет менять четыре frozen файла, отключать лог/NN/network.
Native set_storage_base(state_directory) без migration проверен в отдельном
внешнем sandbox: два append bytes==107-log после прежней root нормализации,
project unchanged. Статус: routing feasible, production adapter и public
rotation tests ещё НЕ реализованы; полноценная приёмка не заявлена.

## L2a — explicit replay-level authorization, 2026-11-11

The user selected «Разделить реплей (Recommended)» in response to the
measured001-tokens/107-log dictionary-vs-answer-string and046-answer typed-error
question. This explicitly resolves the previous temporary replay-level STOP.
D52 now has two mandatory, honestly labelled lanes:
- snapshot_diff structurally compares ALL141 component/reference envelopes and
  ALL72 guard checks, with unchanged golden/catalog/fixture bytes and existing
  reference normalizations only;
- separate mandatory real build_agent(headless)→Agent.call("ask") public cases
  compare valid answer text and verify typed errors plus profile-local native
  append/strict rotation/CRLF. They are NOT counted as component213.
No diagnostic/operation/record parameter is added to the public ask contract.
Invalid-query/budget native texts remain in the reference lane; strict public
typed invalid_input is verified separately and is not a golden projection.
D53 is unchanged: healthy logging cannot be disabled, profile state only,
native source bytes frozen. Routing feasibility is not production acceptance.

Next action: run ALL existing snapshot corpora×2 and the unchanged selector/
readiness tests×2, then add new red list-catalog tests before the narrow D52 fix.
No implementation or parity acceptance is claimed at this documentary step.

L2a D52 checkpoint: new10 red(7failed/3passed)→same10green. Actual
snapshot_diff context.ask reference213/213, verdictok/exit0 twice; NOT213public
ask calls. All35 folders×2 before/after: ALL34 unrelated full outcome rows
exactly identical, including their6fail/1exception/3not_implemented. Only the
authorized librarian route changes list.get crash→213ok. Old comparator,
projection and write-scenario bytes exact; snapshot400lines. Selector/readiness
same77 IDs/all phases green×2 before/after. Native4/corpus/goldens exact.
Verification-driver failure retained: D52_green.py expected33unchanged,
actual34 (its presumed runtime_reference root-shape change did not occur).
No source fix or repeat runs; new checkpoint verifies completed receipts.
Next action: public ask spec/new module red tests, then Protocol→pure domain→
app→ToolSpec/ModuleSpec→lazy state-only adapter→one bootstrap port.

### D54 — authorized test-only composition placement (L2a, 2026-11-11)

User explicitly selected Helper (Recommended) after genuine selfcheck R-11
FAIL/exit1. Authorized one new tests/py/context/ask_composition.py helper and
bootstrap/adapter setup changes ONLY in the newly submitted test_core/public.
Integration composition belongs to the common test harness, not the module
layer; module assertions and real Agent.call remain in their existing tests.
All101 test IDs/order/assert ASTs and production/checkers/selfcheck/etalon bytes
must remain exact. No dynamic-import workaround or architecture exemption.
Failed first selfcheck retained. Next setup-only implementation then actual
same101 green/selfcheck ok; mutations and final double regressions still pending.

### D55 — authorized narrow existing composition expectations/NEW setup isolation

User selected «Узкий D55 (Recommended)» after genuine full33fail/frozen1fail.
Only nine old test files authorized: contract/functions+usages; integration/
gd_lint,node,resource_ops,scene,tscn_lint,verify; browser/runtime_binding.
Permit only registry +ask/read, ports +librarian, one checked function-local
runtime binding activation inside LibrarianRead.answer, NOT import/bootstrap.
NEW ask composition helper/public test setup may isolate native global activation.
All IDs/order/other assertions unchanged. Historic pinned context inventory must
still compare unmodified to its old names; CURRENT real registry expected +ask.
No golden edits/projection, frozen4/bindings/production/checker/reference-harness
changes, or broad import exemptions. Raw first full/frozen fail preserved.
Next setup-only deployment with literal/AST scope proof, identical public101 and
actual full/frozen twice, old outcomes restored, then final diagnostics/closeout.
Authorization is not acceptance; stage4/parity skeleton/L2a unsealed.

## D56 / 2026-11-11 — explicit NEW adapter history-profile routing authorization

User selected «Узкий D56 (Recommended)». Bare probe project-directory side effect
remains genuine STOP evidence. Only NEW librarian_read adapter may route legacy
history/API-cache storage inside profile under same lock, physical-check and
restore override in finally; only NEW test_public strengthened, existing101 IDs/
assertions preserved. Frozen4/history_manager/gd_api_cache/bindings/old tests/
checkers/goldens unchanged. Real red→green, final-code mutations/restores and
fresh double final regressions/gates/native/selfcheck/probe required, no acceptance.

## D57 / 2026-11-11 — explicit read-only legacy API-cache migration suppression

User selected «Узкий D57 (Recommended)». Static gd_api_cache read calls migration
if addon-root default_api_cache.json exists; currently protected deployed cache
has no such migration. Only NEW adapter may temporarily disable precisely that
migration function under shared lock, restore original function in finally;
native cache/fallback reading and healthy logger unchanged. One NEW actual legacy
cache test added, original103 IDs/assertions/calls preserved. Cache/history/frozen4/
bindings/oldtests/checkers/goldens source bytes untouched. Next actual legacy
red before NEW adapter change, same104green; final submitted-byte mutations and
fresh paired regressions/selfcheck/native/reference/probes; no acceptance/seal.

### L2a FINAL PUBLIC SUBMISSION 2026-11-11 — independent audit pending

MODULE1 registered public ask, only query/budget_chars, native STRING result;
effectsread/idempotent, typed invalid_input/not_found/denied, capability ask.json.
Pure domain/local Protocol/thin app, one inert default_ports librarian adapter;
native binding activation solely on real ask execution. No frozen/native source
change, no initializer/NN/function_card requirement/network/Godot/project writes.
Native healthy UTF8 WindowsCRLF log in profile, strict>262144 rotation/.1 and
storage/physical denial/data+history override restoration proven by real Agent.call.
D52 snapshot lane: full141 immutable reference envelopes+72 guard checks=213,
no substantive field projections, NOT213publiccalls. Separate module104
same IDs/all phases green with actual build_agent→Agent.call and native strings.
D53 native logging retained; D54 test composition in common harness; explicit D55
only old registry/port literals + exact local-binding guard and NEW-test isolation.
D56 only NEW adapter profile history routing/guards and NEW tests strengthening;
original101 IDs/assertions/calls kept, plus3 NEW storage/migration tests.
D57 suppresses only native addon-cache migration under lock, original function
restored in finally; legacy fallback answer matches unchanged deployed golden,
addon bytes/dirs unchanged. Native history/cache/bindings and goldens untouched;
checkers retain only authorized D52 changes. Bare project-directory-write STOP retained.
All old unrelated tests/assertions/goldens/source pins preserved, scope receipts.
Final six submitted NEW-code mutants genuinely red1→exact raw byte/SHA/LF/CRLF
restoration→same104/all phases green0; frozen/native exact during every mutant.
Fresh final full7210 twice=7208pass+2 genuine WinError1314 skips; accepted7096
IDs/order/all phase outcomes exact, real junction cases pass. Focused352/frozen230/
API253/genuine-native-project288 pass twice. Gates4 twice0 +extra security twice0,
limits613/two unchanged warnings; contract29 exact. Actual selfcheck twiceok0:
module/layers/limits/contract/security/unit104/corpus213 allok. Separate canonical
snapshot213/213 twice0 and genuine-native213 twice0 with origins/accepted phases.
Real headless public tools/probe.py external project: native MAP/FRAGMENTS STRING0;
invalid_input1/denied1/not_found1; one profile CRLF log and project state exact.
Historical sealed dossiers/restoration archives/F1/initialL2STOP all file bytes,
empty dirs/link metadata/ZIP decompressed bytes independently checked bad0.
All rejected genuine failures retained: first R11selfcheck1, full33/frozen1,
catalog-timeout/count, summary-key/history-prefix assumptions, bare project history
write, real legacy addon-cache migration red and corrected NEW-test
state-signature/preexisting-fixture assumptions.
Prior green baselines/STOPs are history, not replacements or public acceptance.
Progress6 = described live HEADLESS Agent/probe verification, no Godot claim;
parity remains skeleton/pending independent audit, no ported/stage7/self-acceptance.
Next action: independent auditor verifies submitted source pins/contract/corpus,
red→restore→green proofs/paired regressions and external postseal full-byte ZIP;
only auditor/user may accept or request correction. README registered last after
phased records; seal written LAST then separate verifier/archive process.


## D62 — J1b SEC-03 точечный subprocess.run (санкция 2026-11-13; уточнение 2026-11-14)

Разрешено исключить один exact UTF-8 byte-offset call только в
python/substrate/verification/godot_headless_validation.py: bare subprocess import,
List argv Constant(str)/str(Name), дополнительно только str(Attribute(Name(proc), pid))
по прямому подтверждению пользователя; другие Attribute/Subscript/Starred запрещены.
Без shell/kwargs spread; kwargs только Constant либо subprocess.DEVNULL/PIPE.
Timeout termination собственного child не listener; общего послабления .run нет.
Иные call matches/parse errors и B-1 остаются прежними. Новая security-матрица и
mutants обязательны; эта запись до реализации не является green/приёмкой. ADR-0018.

## D63 — J1b SEC-04 точечный import subprocess (санкция 2026-11-13)

Только тот же exact path, ровно один bare top-level import subprocess без asname;
from/multi/alias/duplicate/nested imports и verification neighbors запрещены.
Нет directory exemption, PROC_ALLOWED не меняется, shell=True везде red.
Новые genuine red/green tests до source edits; итог берётся из receipts, не этой записи.

## D64 — J1b exact primitive harness resource (санкция 2026-11-13)

Разрешён python/agent_headless_validator.gd: 1701 B,
799ec9e26f43f65aa8208a1cf1e5379b8d5c3ca80fbd3ad7a0a8e87251da895e, LF39/CRLF0.
Default relative lookup byte-exact verification reference находит ресурс в python/.
Explicit/default tests и seal/ZIP pin обязательны; _MEIPASS нетронут/вне среза.
Замыкание 15 py + 1 gd = 436437 B; alias budget остаётся +15. ADR-0018.


### J1b / A1 фактическая проверка (2026-11-14)

D62/D63 implemented с exact-path/byte-offset AST-исключениями, B-1/PROC_ALLOWED сохранены; D64 exact1701 B/default+explicit green. Genuine red192 collected/135failed/57passed/0errors → 192 same-ID green, все прежние121 failure ID зелёные; native118×2/canonical118×2/0diff. Real Godot4.6:4 own-sandbox default-harness probes/8 engine processes/0diff/no source writes. Mutants:15 checker+2 D64 killed/0survivors, exact SHA/EOL restore/same-ID green. Full non-live×2:7400passed/2 historical WinError1314 skips; frozen230/API253/project288×2, gates×2 и post-resource gates0. Actual selfcheck assistant.judge fail/exit1 (missing MODULE), probe unknown_tool/exit1; context.ask ok/exit0,104unit/213corpus. Aliases0, MODULE/D59/D60/A2 не implemented. A1 reference mini-seal готовится, MODULE не ported, independent acceptance pending. Все rejected setup/invocation/scope records сохранены, native originals/NN/browser-live/production HTTP нетронуты.

Подэтап reference не закрывает historical verification.check/live fate или assistant.judge MODULE. Frozen230 membership сохранён: browser141 + B-1 AST72 + B217; D51 detector34 дополнительно в full/security/mutations. Мини-seal — integrity, не самостоятельная приёмка.
Следующее действие: После A1 mini-seal: A2 native cases/corpus×2 для scene/editing/actions; D60 genuine red exact-six caps перед переносом.


## D60 — J1 exact-six native caps (2026-11-15, J1a sanction)

R-08 verbatim vs R-06: только six full paths в J1_NATIVE_CAPS с измеренными 1457/824/718/714/492/412. Arbitrary401, same basename elsewhere и entries остаются red; default/class/module/area/folder constants не меняются. Checker6373 B превратился только двумя insertions, старый byte stream после их удаления точен. Pending draft26 включён byte-exact: genuine red13fail/13pass/0errors → same26green; первые setup errors отвергнуты, только owned runner исправлен. ADR-0019; досье answer-judge-J1-A2-20261114. Killed mutations/gates записываются отдельно; ни D59, ни MODULE, ни новые production aliases этой правкой не реализуются.


### D60 — actual verification (2026-11-15)

A2 reference-read/prepare проверен, не public MODULE. Six sources152941 B/EOL byte-exact; native214+supp1 ×2/canonical214+supp1 ×2/0diff, full snapshots no-write. Genuine A2220/221 red → same221green, D6013/26 red → same26green; restored all249green. 6 A2+4 D60 mutants killed/0final survivors, exact bytes/SHA/LF/CRLF restore/same-ID green. Первый ambiguity survivor сохранён: wrongly named old negative-case не создавал candidates; gap закрыт новым genuine native supplement×2 и теми же mutant bytes, frozen214 не переписан. Full non-live7649passed ×2 + ровно два historical WinError1314 skips, no added skips/xfails; collected7651 и executed IDs/order exact. Frozen230/API253/project288 ×2, все288 manifest IDs. Gates/security ×2 green. Real Godot4.6:4 native/canonical reference probes/8 processes, default harness,0diff/no source writes/owned validation leftovers0; это headless structural validation, не semantic editor apply/rollback и не public judge probes. Actual selfcheck assistant.judge fail/exit1 (missing MODULE) ×2; actual probe judge unknown_tool/exit1 ×2. Actual context.ask selfcheck ok/exit0 ×2,104unit/213corpus. D60 exact-six caps реализованы minimal two-insertion checker delta, old constants/caps сохранены; D59/A3/B/+15 aliases/MODULE/public corpus не реализованы. Rejected baseline assumptions, freeze path, pytest basetemp setup, outer120s partial canonical capture, singular collected-item receipt, double-q collect verbosity и initial survivor сохранены, не засчитаны как successful evidence. A1 accepted record read-only; mini-seal/ZIP фиксируют integrity, не самостоятельную приёмку.

Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/answer-judge-J1-A2-20261114/
Следующее действие: После A2 mini-seal/ZIP: A3 symbol_refactor native cases/observations ×2 до missing-code red; затем B/D59/adapter/MODULE.


## D65/D66 — J1 B, санкция пользователя 2026-11-15

Разрешены обе границы sealed B-preflight: две замены bootstrap для lazy JudgeRead через librarian; пять named old-pin tests: count50, untouched35-prefix, exact84 lines, только обязательные J1 aliases и один точный lazy import JudgeRead.judge. Genuine new2 red/noerrors уже в STOP; новые D59 ownership/rollback и public cases дают дополнительный red до кода. Security checker/ToolSpec kernel/snapshot normalization не меняются.


## D68 / D69 — J1 final read boundary (2026-11-15)

Пользователь разрешил обе точные границы sealed B-boundary2. D68: только JudgeRead.judge под существующим shared lock временно заменяет parser_base._save_corpus_sample на no-op и в finally восстанавливает original identity, в том числе KeyboardInterrupt; native parser байты неизменны, другие клиенты не меняются. Genuine2red→same2green; bypass/finally mutants killed. D69: ровно восемь old catalogue/selector pins: judge/read,28→29 tools,44→45 MODULEs; старые names/order/effects/masks/IDs сохранены. Genuine52fail→same-ID green; real-catalog mutant killed. Изоляция исправлена только в новом B conftest: согласование package-child caches с actual sys.modules и восстановление generations; accepted reference helpers и fail-closed parent guard не изменены. Сильный preceding-A3 reproducer и мутант fixture дают red→exact-restore green. Восемь собственных synthetic parser logs сохранены byte-exact вне ROOT, затем удалены только после сверки с STOP snapshot; user/code files не удалялись. Shared snapshot/selfcheck/security нормализация и browser/NN/HTTP не расширяются.


### J1 public judge — final submitted parity (2026-11-15)

J1 полностью реализован и передаётся на независимый аудит: public assistant.judge/judge, read/idempotent, fs+librarian, strict input/result envelope, domain pure/app7. Genuine native74×2 → actual build_agent→agent.call74×2/0diff; final ordinary public corpus74×2/0diff. Actual selfcheck assistant.judge ok/exit0×2 (8unit/74corpus), context.ask ok/exit0×2 (104/213). Final full7923collected/7921passed×2, exact ordered once-only IDs, только два исторических symlink WinError1314 gaps. Frozen230/API253/project288×2, все288 IDs, security/layers/limits/contract×2 green. Четыре actual CLI probes: answer0/invalid_input1/denied1/no-write0; owned state only, no project writes. Final185 new tests green;14 current-submitted mutants killed/0survivors, byte/SHA/LF/CRLF restores/same-ID green. Fifteen Python references+GD harness436437 B byte-exact; part1CRLF824; old35 binding prefix exact,total50/rawLF84. D59/D65–D69 только в санкционированных границах. Native parser/quartet/parser_base/security/check_limits и shared snapshot/selfcheck/generator unchanged. A1/A2/A3 full readback/seal/archive pins exact, только уже раскрытая A1 empty-file inode cohort1430. Rejected invocations/full failures/sample-write defect и initial A2 survivor не удалены; D68 genuine2red→same2green, D69 genuine52fail→same-ID green, fixture isolation repaired only in new B scope, no foreign-parent adoption. Один поздний full run дал importlib source_to_code MemoryError: cause unestablished; unchanged node alone exit0, fresh exclusive full7921pass/2oldskips exit0; failed run retained, not counted. Полный final ZIP включает byte-exact7 mini-seals/8 prior archives, включая rejected incomplete A1 ZIP; их наличие не означает принятия rejected artifacts. Prior real Godot reference probes retained; no public apply/rollback/editor semantic/live/NN/browser/HTTP claim. MODULE_ready=true; independent_acceptance=false, audit pending.

D59/D65–D69 подтверждены genuine reds, actual greens и мутациями. D67 передаёт provides_tools только missing-port ветке; unknown name остаётся unknown_tool. D68 подавляет только raw parser sample sink на время JudgeRead под shared lock и восстанавливает original hook даже BaseException. D69 меняет ровно8 named catalogue/selector pins, old members/order/effects сохранены. Никакого общего gate/schema/import/parent/security исключения не добавлено.
# K1c / D72–D73, начало (2026-11-20)

D72 заменяет bootstrap freeze D70.3/5 ровно двумя token insertions внутри
default_ports; before8451 B/180LF/0CRLF, SHA256
`2c0643473d82cf54355a34704afe784548506c3438db1d2b77221cbc5c096d41`.
After-pin и exact deltas будут записаны по факту. D65 JudgeRead bytes сохраняются.
D73 заменяет D71.2: публичный required closed object, domain final STRING,
обёртка только app. Новый chat.json — генерация ToolSpec. Eight named D69 B-list
получат только public advertisement/count tokens после RED. Общие checkers,
kernel/protocol, pinned API/parser/judge/quartet/runtime-bindings заморожены.
Никакой новой normalization поля корпуса не разрешено; сравнение целого объекта.
Synthetic offline SSE не является проверкой real-provider/live-network.
# K1c checkpoint: измеренные D72/D70 изменения (2026-11-20)

Bootstrap before8451 B/180LF/0CRLF → after8592 B/182LF/0CRLF,
SHA256 `d6d933ee8d142efb131372b155992213dadf8390d776f92bdeb4b9d4a9caf2e8`.
Две вставки, окружающие D65 bytes exact; будущий restore обязан использовать after.
Ни один frozen тест не потребовал изменения из-за D72. D70 guard
`tests/py/browser/test_browser_runtime_binding.py::test_production_bootstrap_and_profiles_do_not_import_binding`
genuine RED; добавлен только точный сайт ChatGateway.send к прежним двум сайтам.
Gateway12 same-ID GREEN; loop RED ещё не является успехом K1.

## D72 additional frozen port-order token (2026-11-20)

Первый full выявил единственный дополнительный D72 pin:
`tests/py/integration/test_resource_ops.py::test_bootstrap_port_order_and_no_public_tools`.
Он явно включён в D72.4 list до исправления; отдельный genuine RED→same-ID GREEN.
Ровно один токен `"chat_gateway"` вставлен после `"librarian"` перед `"journal"`.
Другие bytes/assertions и public resource capability boundaries не менялись.
Receipts: D72-additional-frozen-test-list.json/D72-additional-frozen-after.json.
Bootstrap remains8592 B/182LF/full after-pin; D65 inverse byte-exact.
Предыдущая checkpoint-фраза «ни один frozen» верна только для scoped gateway этапа,
не для позднего полного прогона; новая находка не скрыта и не засчитана как success.
Пять routing stdout failures и redactor failure исправлены исключительно изоляцией
наших тестов: свежие canonical modules/aliases, восстановление cached parent attrs.
Native parser counters, protected routing tests/goldens/checkers не редактировались.

## D73 final exact advertisement deltas / K1 new (2026-11-20)

Genuine seven failures in453candidate tests → same453IDs GREEN; surrounding bytes
во всех8 files восстановлены из baseline плюс следующие token substitutions:
- contract/test_functions_contract.py, test_usages_contract.py:
  `"ask", "check"` → `"ask", "chat", "check"`.
- integration/test_gd_lint.py: `'ask', 'check'` → `'ask', 'chat', 'check'`,
  `'count': 29` → `'count': 30`.
- integration/test_node.py, test_scene.py: `'ask','check'` → `'ask','chat','check'`,
  `'count':29` → `'count':30`.
- integration/test_tscn_lint.py: live suffix `['ask', 'judge']` →
  `['ask', 'chat', 'judge']`; historical corpus list/count unchanged.
- integration/test_verify.py: `len(agent.tools()) == 29` → `== 30`.
- tools/test_selfcheck_unit_selector.py: **unchanged**, pre-existing module
  discovery already counts45; selected-module count assertions did not fail.
Paths are under tests/py/. Full before/after SHA/LF/CRLF/token receipts:
`D73-token-only-after.json`. No member removed, order unchanged except inserted chat.
NEW generated contract/capabilities/chat.json; public result required closed object,
domain final STRING/app wrapping; no kernel/protocol hooks.
Final selfcheck assistant.chat ok×2/exit0, ordinary10cases×2/0diff, raw observations
byte-equal/no normalization; classification new, independent acceptance pending.

## D74 T1 byte-exact godot_tools closure and fail-closed gates (2026-11-21)

Measured eight sources: arch_map22088/454LF; gd_functions3367/81LF;
log_reader13864/276LF; node_refactor46881/1095CRLF; split_gd63421/1333LF;
split_refactor44114/872CRLF; function_card37878/751CRLF;
gather_context17226/404CRLF. All native/rebuild SHA/EOL pins are in
T1-20261121/T-A-source-pins.json and exact-copies receipt. No source adaptation.
Mandatory gather_context log_reader dependency is scheduled early from T-C.
function_card is required by accepted corrected librarian1238–1246 and native
agent_bridge500–504; D48 helper exclusion reversed, excluded NN untouched.

Native split_gd1162–1174 executes only Godot argv, no shell. Existing gates were
genuinely RED after exact copy (D74-SEC-native-source-RED and limits RED). Decision:
full-source SHA256 18f05d10b8e875ed77040b8a47beb6ccbdb409b55d791ec0318466473969bfc7,
exact relative path, one native UTF8 .run byte-offset. Every byte mutation revokes
permission. Five exact caps454/1095/1333/872/751; old D60 dictionary unchanged.
No global process/network/listener exemptions. ADR0074; gate matrix and mutations
in tests/py/security/test_t1_native_gate.py; receipts remain append-only.

## D75 T1 lazy binding activation without changing K1 (2026-11-21)

Historical librarian corpus038/039 observes excluded func-card behavior, so adding
eight aliases to accepted base50 would silently alter accepted semantics. Instead
new NativeBindings.register opts in lazily with native dependency order and owned
alias rollback. Base runtime_bindings.py and accepted gateway bytes unchanged.
Existing import-site guard genuinely RED (one exact test ID); one mapping entry
added: python/substrate/assistant/native_bindings.py → NativeBindings.register.
All other guard conditions remain exact. No import-time/bootstrap activation.
RED/matched GREEN/identity/foreign-alias/BaseException tests in T1 evidence.

## D76 T-A mini-seal: in-place вместо privileged link-copy (2026-11-21)

Первый snapshot-copy T1-T-A-20261121 реально отказан WinError1314 на native
directory junction; копия осталась незапечатанной, её physical inventory сохранён.
Принятый K1 seal_and_package.py использует in-place seal: процедура перенесена
без повышения прав, потери ссылок или обхода guards. Реальный retained-junction
test сначала RED/WinError1314, затем тот же ID GREEN; source inode/mtime/tag
не изменились. См. ADR0076 и T-A-package-link-same-ID.json.

T-A досье — c8_audit/T1-20261121; regular production snapshot в submitted, seal
LAST, sibling -postseal ZIP с проверкой каждого physical member и native reparse
tags. После seal это досье не изменяется; T-B начинает новый рабочий каталог.
Windows metadata хранится в seal, не заявляется lossless в ZIP. Native bytes,
K1 dossier и глобальные security/gates неизменны; independent acceptance=false.

## D77 T-B semantic write/explicit confirmation (2026-11-21)

Native13 paired raw-delta preparations/no project writes сняты до production;
43 own IDs genuine missing-code RED→GREEN×2. Native prepare only; все project
effects выполняет existing write_apply/funnel и journal/rollback. Generic
requires_confirmation marker обязателен для assistant preview; boolean approval
отдельно от model action. Immutable TTL/digest/project-policy/receipt ownership
проверяются до эффекта; historical untagged plans unchanged. ADR0077/SEC-T1-WRITE.

Измеренная native preparation ADS-shaped create не вызывала apply. Adapter
отказывает colon target до native и в delta compiler; declaration coordinates
и content остаются data. Own five-ID RED→GREEN сохранён. Accepted native bytes,
base50/84LF и K1 gateway неизменны. Bootstrap добавляет только NativePlanner
import/port; genuine old guard RED→same-ID GREEN восстанавливает полный K1
8592B SHA256 d6d933ee8d142efb131372b155992213dadf8390d776f92bdeb4b9d4a9caf2e8,
затем исходные D65 8451B SHA256. Старые predicates остаются точными.
Write_apply добавляет generic helper import/call, удаляет только два пустых
separator, сохраняя все original nonempty lines/newline style/line budget8400.
Rejected installer needle args вместо actual plan_id сохранён; partial own files
верифицированы exact, native/old write_apply не перезаписывались по догадке.

## D78 T-B exact advertisements/CLI/contract (2026-11-21)

Two old inventory IDs genuine RED после регистрации четырёх write tools;
добавлены только assistant_confirm/plan/rollback/turn в sorted names, затем
same-ID GREEN. Conflict/duplicate/disabled predicates unchanged. ADR0078.
Genuine renderer exclusively добавил четыре артефакта без старых byte changes;
genuine gen_contract --check GREEN. Rejected default-check invocation сохранён.
CLI own tests precede turn/plan/confirm/rollback adapters; explicit mutually
exclusive approve/reject, bounded JSON data, no model-derived approval, legacy
chat/repl read-only. Structural Godot overlay deferred T-D; provider/browser-live
и independent acceptance не заявлены.

## D79 T-B selector registration (2026-11-21)

Native write loop добавляет assistant.write, отсутствующий в прежней 45-ID
selector matrix. Первый полный регресс реально отказан на undeclared new ID;
ADR0079 регистрирует только assistant.write и count45→46 без перестановки
прежних списков. Все46 selector IDs same-ID GREEN; rejected full сохранён.

## D80 T-B owned missing parents (2026-11-21)

Native prepare допускает new/nested/file.gd и measured×2 не меняет проект;
native apply transaction_actions333/359 создаёт parents, history_manager693–705
удаляет даже pre-existing empty directories. Existing rebuild create отказывает
missing parent: пять новых actual RED IDs. ADR0080/SEC-T1-PARENTS до реализации.
Минимальное решение: read-only parent discovery, pure bounded mkdir Steps перед
файлами, absence/footprint в digest; existing funnel intent→mkdir→identity receipt.
Inverse только plain/empty/matching receipt directories; unreceipted recovery
blocked, pre-existing/replaced/reparse/foreign-filled never deleted. Public counts,
hashes и receipts остаются file-only, directory receipts хранятся только в WAL.
Generic pure WAL reader перемещён целиком в kernel с compatibility import:
единственная реализация и неизменные predicates, а не разделение по размеру.
Five-ID GREEN×2; дополнительный genuine RED показал equal-byte foreign child
deletion при inverse до проверки родителя: proofs добавлены перед каждым inverse
в rollback/compensation/recovery. 58same-ID GREEN×2. Native nested move×2/no writes
доказал UID side effect: rejected three-step/one-file test сохранён, exact test
теперь five steps/three file effects. Forward/inverse/unique-bound mutants killed
и raw restored; bound-mutant survivor сохранён, новый independent unique-bound
test убил retry. WAL reader original2746B/63CRLF exact целиком (первая LF-only
копия rejected). Final gates/regressions pending; текущие bytes не sealed.
Первый final lint отклонил module-test host imports. Как в accepted
tests/py/context/ask_composition.py, wiring и owner recovery probe вынесены
в test-host tests/py/transfer_t1/write_composition.py, сохраняя все assertions
и exact test IDs. Не module product dependency и не checker exception.

## D81 — complete declared T-B inventory delta, genuine six-ID full RED

ADR0081. Actual first final full:8103pass/6fail/2 historical skips. Разрешены
только четыре новых sorted names, count30→34, write effects всех четырёх и
native_planner slot после chat_gateway в шести tests/py/integration files.
Pinned context corpus остаётся byte-exact; только live projection меняется.
Все исходные bytes/SHA/EOL сохранены перед patch; strict byte reconstruction,
same six-ID GREEN×2/mutant/fresh full пока pending. Никакого filtered registry.
Actual registry/common_tool_defs: plan/turn тоже conservatively write из-за
WAL/history, не project apply. Rejected two-write observer и4fail followup
сохранены; исходные четыре generated contracts остаются unchanged.

## D82 — existing-parent plain proof is not created-parent ownership

ADR0082/SEC-T1-PARENTS. Два реальных unsubmitted port-attack RED показывают:
pre-existing ancestor с empty/OSError directory_identity ещё не блокировал
tagged write. NativePlanner prep already requires ordinary ancestors; проверка
должна повторяться до forward/inverse эффекта только assistant.write.
Не присваивать/удалять старые родители, не менять historical untagged plans.
Production RED→GREEN×2 и mutant pending; реальная junction-race не заявлена.

## D83 — preview steps bound includes existing bounded mkdir steps

ADR0083. Actual four Agent calls all succeed/no project effects; initial observer
не знал, что result validation отдельная. Усиленный schema test:1pass/3fail,
не новая dispatcher policy. Новый PLAN_RESULT maximum100→356 вычисляется из
MAX_FILES100+MAX_PARENTS256; file/parent/action caps неизменны.
Только assistant_plan/assistant_turn artifacts меняются; old31/newother2 pinned.
Port-generated deep plans — schema coverage, не native/live NTFS verification.

## D84 — parent proof cohesion, frozen limits

Genuine A3 check_limits failed: editing8407 > frozen8400. ADR0084 preserves
complete checker bytes/all caps and combines duplicate ordinary/receipt checks
into one parent map. Actual-area RED→same-ID GREEN; directory/security pair
GREEN×2; area now8400, original two warnings. No unrelated stub deletion,
kernel relocation, arbitrary splitting or directory/area exemption.
Current compact source forward/inverse/ordinary mutants killed and byte/SHA/EOL
exactly restored with same-ID GREEN. A3 selected82/probes×2 remain real results,
but its final gate failure and source-drift regression are rejected, not final
completion. Fresh A4 verification required; no additional atomic-race claim.
## D85 — local channels and exact native server composition

ADR0085 records measured native auth five pairs/eleven exact refs, strict auth ahead
of native fail-open, session native namespaces/profile restoration, owned typed
browser seam, random loopback/raw+identity endpoint inverse, finite bounded MCP and
two exact-SHA/path native caps. Four production entry/corpus RED + native-cap9
2fail/7pass→own28GREEN×2/native5corpus×2. Prototype61pairs are separate. No K1/native/
global SEC/old caps changes, no real network/live/self-acceptance. Full verification
and current-byte mutants pending; all observer failures retained.

## D86 — owned structural preparation and explicit executable-resource gap

ADR0086 follows actual A7 seven-case paired native observations, proved generated
UID/hash-only normalization, and recovery-mode import0/SDK1×2 refusal. Overlay is
not an OS sandbox: untrusted scripts/extensions/binary scenes cannot run there.
Script-bearing structural targets/autoloads fail closed before subprocess; no
silent source stubs and no script-bearing parity claim. Normal native file edits
and safe structural assets continue through one B executor. Engine path explicit,
state external/plain, actual native prepare hashes/configuration/readiness,
target-only raw deltas and typed diagnostic errors; candidate SEC05 allowance
exact path/full SHA/byte positions only, inactive references. Production RED,
live native/production comparison/mutants/gates remain required; not acceptance.

## D87 — exact predecessor projection, own observer registry, shader boundary

ADR0087 records the retained initial full result:7163passed/1068failures/2historical
skips, not a successful final pair. Only T-D's two inserts are reversed before
all unchanged accepted T-B/K1/D65 byte/EOL/SHA assertions. Genuine own registry
RED leads to scoped new-test preparation, not accepted alias changes. Six shader
reference REDs extend the same canonical policy before engine IO; inconclusive
native null result does not prove outside reads. Paired same-ID GREEN, byte-exact
old-test reconstruction, current restored mutants and complete fresh final
regression/gates/selfchecks/clients/seal verification remain mandatory.

## D88 — additive native GD format facts, frozen corpus unchanged

ADR0088 preserves second failed full8237pass/1failure/2historic gaps. Genuine
unchanged coverage RED;36 actual native facts×2 with original reference SHA.
Separate sibling format corpus, one in-memory test data composition line, exact
submitted-C test reconstruction and unchanged assertions/facts/order. Only36
measured additional format IDs admitted; no old corpus/native code modification.

## D89 — relative engine references do not bypass pre-IO policy

ADR0089 six genuine relative plugin/resource reference failures→paired GREEN.
Classify parent/escaped/code-config references, compiled.gdc included; same central
policy and B executor. Conservative scalar/node-path false refusals are explicit
safety gaps; outside native execution unproved/not claimed. Fresh current mutants,
native/B/full/gates/selfchecks/clients/readback/seal still required.
