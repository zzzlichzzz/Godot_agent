# Project-core — preflight остановлен (2026-11-06)

Мандат: `_start-prompt.project-core.md`, 13597 B, чистый CRLF,
SHA256 `345e7d9380099727ffd4e830e6c08a093969db4528fac6661c8fffe6ce18b4b4`.
Класс жёсткий, модель gpt-6.1-sol; приёмка только независимым аудитом.
Цель: byte-exact project_tools + project_settings_actions в substrate/project/,
SEC-матрицы на fixture-проектах, затем отдельная MODULE-интеграция.

## §0. Свежая база до первой repository-правки

Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/project-core-20261106/`.
`§0-recount.json`, `tree-before.json`, `baseline-bytes/`, `native-before.json`:
4701 файл / 863 каталога / reports44 / UID86 / pyc0. Четыре фактических
сентинела в __pycache__ (ref.gd ×2, ref.gd.uid, ref.py), точные пути/SHA в JSON;
неточно названные в мандате «4 ref.gd» не заменялись и не удалялись.
project.godot335 B / `958b3a92…`; WORKLOG772342 B / `b08eccff…`;
README33254 B / `db06bc5b…`, bareLF0. Это подтверждает последние значения
пользователя; приближённые старые значения §0 мандата не подгонялись.
parity24262 B / `5d1cec37…`, LF194; binding2725 B / `f310b781…`, 58 строк/
27 алиасов; check_limits5384 B / `5ef23793…` — без изменений.
Прежняя routing-печать `c4cab10c…` проверена: после неё изменились только
WORKLOG/porting README/routing-runtime.md (записи аудитора), добавлен prompt.
Все недокументальные байты репозитория и весь native inventory прежние.

## §1. Фактическое замыкание: явный STOP

Native-корень: `D:/vajno/Godot/random-game/addons/godot_agent/python/`.
Источники read-only: AST разбор всех байтов; native не импортировался и
не исполнялся. Полный анализ поведения/съём кейсов не начинались.

| Источник | Фактические байты/SHA256/EOL | Top-level импорты |
|---|---|---|
| godot_tools/project_tools.py | 102471 B; `79e9b035bd211f4a44623573d64f88f5bf47a049725c18dc90d985f47c6a7877`; LF1960/CRLF1960 | errno, **os, shutil, stat, tempfile**, text_sanitize |
| godot_tools/project_settings_actions.py | 13735 B; `fcdb4635aa8ccb965f0775e6b52f6f339c18809da3a3baac3b9e12da6c8e932f`; LF251/CRLF0 | **hashlib, json, math, os, re, uuid**, project_tools |

Жирным — импорты, отсутствующие в таблице мандата L28–29. Оба source-пина
совпали: это не иной исходник. Все дополнительные импорты — stdlib; прямых
новых проектных зависимостей AST не обнаружил. Late imports project_tools:
posixpath:221, re:1272, hashlib:1706, difflib:1824/1861 (тоже stdlib).
Тем не менее L31/L85 требуют STOP при **любом ином top-level импорте**.
Считать таблицу «только внутренними зависимостями» без согласования нельзя.
Точные строки/imported names и полные source-пины: `closure.json`.

## §2. Проверено, но не перенесено

Actual selfcheck.main из неизменённого tools/selfcheck.py выполнен для
project_ops.settings_get/settings_set/architecture: **blocked, exit2**;
нет MODULE, unit-тестов, module-owned corpus. Изменён только параметр пути
REPORTS в external runner: свежие JSON/logs в module-selfchecks/, ни один
из44canonical reports не записывался и не требовал восстановления.
Общие строки selfcheck: layers596/0, limits2прежних warning, contract28/0,
security0. Имена settings_get/settings_set/architecture через actual probe
на внешнем synthetic project: unknown_tool/exit1; это отрицательная проверка
этих имён, не заявка на наличие публичного ToolSpec или MODULE-интеграции.
Гейты до записей зелёные: lint596/0, limits0violations/2прежних warning,
contract28/0, security0. Повтор после записей хранится в after-records/.
Полные/focused/frozen/API pytest, корпус, red-пины и мутации в этом preflight
**не выполнялись**; прежние прогоны остаются только историческим свидетельством.

Не создан substrate/project/, не скопирован ни один эталон, не добавлены
алиасы/fixture/корпус/тесты/лимиты/D39. text_sanitize is-проверка ещё не
выполнялась: связка не исполнялась. Tests-map L48–49/L85–86 имеют судьбу
corpus, их покрытие не закрывалось; mapping указывает на project_ops.*.
parity L95–97 остаются skeleton; полные MODULE-этапы0. README L71 уже
зарегистрирован: повторная регистрация и ремонт исторических строк запрещены.
WORKLOG/PROGRESS — только новые CRLF-добавки с полным prefix assert;
deviations/tests-map/parity/README и все программные файлы заморожены.

## Вердикт и продолжение

**STOP на reference-preflight, до переноса. Срез не выполнен и не принят.**
Статическая безопасность зелёная не снимает дефект таблицы замыкания.
tree-after/scope/prefix receipts и SHA256-final.json описывают только эту
остановку; SHA-печать досье пишется последней после повторных гейтов.

**Следующее действие:** получить исправленную таблицу top-level импортов либо
явное разрешение продолжить с перечисленными stdlib-импортами; затем native
корпус SEC-матриц → спецификация/D39 → red-тесты → byte-exact код/связка.

## Технический инцидент нового листа (до добавок в старые файлы)

Patch при создании этого листа нормализовал заданный CRLF в LF78/CRLF0.
Pre-record assert отказал до WORKLOG/PROGRESS append; отвергнутые6741B/
45d52dfa… и exit-coded отказ сохранены в worksheet-eol-incident/.
Исправлен только новый лист текущей сессии (r+b, backup и exact assert),
содержимое прежних78строк сохранено, EOL теперь CRLF; исторические файлы,
native и frozen не переписывались. Этот инцидент не отменяет import STOP.

## Закрытие STOP-preflight (2026-11-06)

Повтор after-records фактически: lint596/0, limits0violations/2прежних
warning, contract28/0, security0, все exit0. После этих closeout-добавок
дополнительный контроль after-closeout предшествует tree-after/SHA-печати.
Полные старые document-prefixes exact; исправление EOL только в новом листе.
STOP/не принят; reference1/MODULE0, pytest/мутации не запускались.
Следующее действие: исправленная таблица или явное разрешение перечисленных
stdlib-импортов; затем corpus→spec/D39→red→code, не исключение по умолчанию.

## F0: продолжение в прежнем досье (2026-11-06)

Поправка аудитора F0 разрешила полные top-level списки; исходный STOP остаётся
историческим фактом, причиной была неполная таблица, не исходник. Prompt15778B/
a70fb087…, WORKLOG778208B/1bfcad41… проверены. Дерево кода/frozen/native
совпало с оригинальным tree-before; относительно STOP-печати изменились только
две разрешённые F0-добавки WORKLOG/prompt. Старые tree-before/байтовые backups
и SHA256-final.json1b4ab279… сохранены, новое свидетельство в resume-f0/.
Полный AST повторён: поздние posixpath/re/hashlib/difflib — только stdlib;
их фиксация войдёт в D39 до кода. README L71 уже есть, повтор не добавляется.
Reference этап1 (preflight завершён), MODULE0/skeleton без изменений.
Следующее действие: снять native SEC-корпус в fixtures/corpus/project/ на
fixture-проектах, без внешней сети/Godot/old-test bootstrap.

## Capture: отказ до публикации и исправление шва (2026-11-06)

Первый native capture завершился exit1: два error.message содержали repr-путь
с удвоенными обратными слешами. Проверено: только замена sandbox-префикса
делает все упорядоченные наблюдения равными; классы/тексты остальных ошибок,
errno/winerror и before/after SHA/casing не меняются. Оригинальные два результата
и harness сохранены в resume-f0/native-capture-{1,2}/ и capture-setup-incident/.
Исправлена исключительно маска префикса в observer, native не менялся;
goldens ещё не опубликованы, SEC ожидания не ослаблялись. Reference этап1.
Следующее действие: два свежих native capture-v2, затем публикация корпуса и D39.

## Reference этап2: native SEC-корпус снят (2026-11-06)

288 наблюдений ×2: security126, reading47, settings110, casing5. Свежие
native-capture-v2-{1,2}, общий capture exit0; ordered IDs/наблюдения одинаковы,
каждый ID ровно один раз. manifest84064B/bc440d0b… с полными SHA/bytes исходников,
fixture-файлов и read-only старых case sources. Все before/after SHA/casing,
ошибки, errno/winerror сохранены; normalizer меняет только sandbox prefix,
UUID фиксирован, fixture mtime1000. Реальные junction outside/addon/agent сняты;
symlink creation действительно WinError1314: это явный environment refusal,
не успешная symlink-policy проверка и не новый skip. UNC через local OS seam,
без SMB/DNS. Empty/broken/malformed сцены отражают native, не новый validator.
Ни старые тесты, ни bootstrap/STATE/Godot/сеть не исполнялись.
Следующее действие: зафиксировать D39/spec до tests и reference-кода.

## Reference этап3: D39/spec зафиксированы до tests/code (2026-11-06)

D39 в deviations: два byte-exact файла в substrate/project, narrow FILE_MAX2000
с неизменными entry/default/старыми caps, два aliases после parsers, SEC-инварианты
и честные raw/policy/settings/UNC/symlink границы. ToolSpec/MODULE/HTTP не добавляются.
Следующее действие: новый native replay288 ×2 и red проверки reference/bindings/
точной limit-class, до byte-copy и правки check_limits.


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

## Tests setup: точный red-guard отказал (2026-11-06)

Первый class run16 завершился16fail из-за сигнатуры/имён в новом тесте:
python_files() без args, реальные константы *_FILE_MAX. code_preflight exit1
отверг это как невалидное доказательство: требовались ровно три cap-fail.
Исходный новый тест, preflight и exit-coded результаты/JUnit сохранены отдельно.
Исправлены только обращения к API checker в своём тесте; все expected caps и
booleans прежние, checker/reference/native/SEC-06/старые тесты не менялись.
Ни byte-copy, ни aliases/cap до настоящего red не допускаются. Reference этап3.
Следующее действие: повторить class/general red-v2, затем exact preflight.

## Reference этап4: tests/native replay/red до code (2026-11-06)

Новые case-level tests: native288 ×2 exit0, одинаковые ordered IDs/outcomes,
ровно один call на ID. Полный новый focused314 до кода: exit1, outcomes {'failed': 299, 'passed': 15}.
Narrow class red16: ровно 3fail/13pass — project_tools1960, project/reference2000,
project/nested/reference2000 отклоняются старым400. Boundary2001, lookalikes,
entry/default/старые классы уже правильно fail-closed. Две изменяемые программы
byte-copy backed up вне проекта; их bytes совпали с оригинальным tree-before.
Ни новых native-копий, ни aliases, ни cap-правки до red не было.
Следующее действие: byte-copy двух native refs, inert __init__, ровно два explicit
aliases после parsers и narrow D39 cap2000, затем те же focused tests ×2.

## Reference этап5–6: code и differential (2026-11-06)

Две reference-копии116206B байт-в-байт: project_tools102471B SHA79e9b035…
LF1960/CRLF1960; settings13735B SHAfcdb4635… LF251/CRLF0. Inert __init__.
Binding:29 aliases, ровно две вставки после parsers; удаление этих двух строк
восстанавливает все прежние bytes/27pairs/order/algorithm. Checker: удаление
только D39 additions восстанавливает полный старый файл/defaults/caps/warnings.
Focused314 ×2 exit0, once-only ordered IDs/outcomes равны; первые288 IDs/outcomes
точно равны native replay. Native/new observations совпали без правки goldens.
Фактический sanitizer-at-import tracer сработал один раз; foreign aliases,
idempotence, ImportError/KeyboardInterrupt и replaced-new-alias rollback зелёные.
MODULE0/skeleton, no bootstrap wiring/ToolSpec/live Godot/HTTP. Не принято.
Следующее действие: killed mutations submitted bytes с exact restore и теми же
green tests, затем full/frozen/API regressions ×2 и реальные selfcheck/probe.

## Mutation setup guard (2026-11-06)

Первые две мутации killed73/26, exact restore, same security126 green каждую.
Третий selector отказал до применения: harness ожидал existing, реальный
binding использует previous. Процесс exit1, но третьей мутации/pytest не было;
это не non-red mutant. Все submitted SHA/LF/CRLF и native tree точны.
Первый script/backup/logs сохранены; исправлен только selector в новом external
continuation. Этап6 не завершён. Следующее действие: остальные4 mutation runs.

## Reference этап6: submitted-byte mutations завершены (2026-11-06)

Убиты6: can_read deny→allow, safe-resolver realpath→abspath, project alias
identity bypass, class2000→400, owned-alias rollback, case-only rollback order.
Каждая: external copyfile backup → actual red exit1 → r+b full-byte restore
SHA/LF/CRLF exact → те же once-only tests green exit0. Native tree exact.
Failure IDs/числа и pins: mutation-results.json, mutations/, mutation-continuation/.
Setup-refusal до третьего apply сохранён, не считается mutation run или green.
Следующее действие: full6564/frozen230/API253 ×2, ordered JUnit delta/protected
bytes, реальные gates/selfcheck/probe и append-only closeout. MODULE0, не принято.

## Full regression STOP → разбор fixture ownership (2026-11-06)

Full6564 ×2 actual exit1:6561pass/2 прежних1314skip/1fail в старом
test_capture_covers_every_current_required_gd. Новые project-core .gd расширили
глобальную область fixtures/projects, которой владеет frozen scene-deps capture.
Gates599/0, frozen230 ×2 и API253 ×2 зелёные. Source/native/restores точные.
Разбор: свой fixture-project принадлежит project-core corpus, не scene-deps.
Перемещается только собственный новый каталог в fixtures/corpus/project/fixtures;
runtime проекты всё так же materialize/copy во внешний sandbox с теми же .gd,
.tscn/project.godot. Все fixture SHA/bytes/relative paths и288 golden cases,
manifest bytes сохраняются, старый test/corpus/expectations не меняются.
Этап6/не принято. Следующее действие: native/focused/full повторить ×2 на
новом layout; полный green необходим, прежние exit1 остаются доказательством.

## Reference6: повтор mutation proof на финальном fixture layout (2026-11-06)

Все6 submitted-byte mutants повторно killed; same tests green после каждого
exact SHA/LF/CRLF restore. Финальный helper/fixture layout зафиксирован receipt;
golden288/manifest bytes прежние. Earlier отказ/failed full/мутации сохранены.
Следующее действие: final native288/focused314/full6564 ×2, JUnit/delta checks,
реальные selfcheck/probe и gates вокруг closeout. MODULE0/skeleton, не принято.

## Final full green; checks-adapter setup refusal (2026-11-06)

Новый layout: final-native288 ×2, final-focused314 ×2, final-full6564 ×2 exit0.
Перед реальными final checks новый внешний adapter отказал на import preflight
(3 запуска exit1; ни gate, ни selfcheck, ни probe не вызывались). Original adapter
сохранён; добавлен только BASE import path, как в уже работающем external runner.
Repository код/expectations не менялись. Reference6, MODULE0, не принято.
Следующее действие: реальные final before-records gates/selfcheck/probe,
ordered JUnit/delta verification, append-only closeout и final gates/seal last.

## Project-core F0: reference evidence complete, independent acceptance pending (2026-11-06)

После честного STOP и поправки F0 мандат продолжен в том же досье; оригинальные
tree-before, STOP SHA256-final.json и все STOP-записи сохранены. Копии116206B
native-exact: project_tools102471B/79e9b035…/LF1960=CRLF1960;
project_settings_actions13735B/fcdb4635…/LF251/CRLF0. Inert project/__init__.
Ровно +2 aliases после parser bindings:29 total; прежние27pairs/order и весь
алгоритм восстанавливаются удалением только двух новых строк. Sanitize identity
проверена tracer на фактическом fresh import, ровно один раз; idempotence,
foreign refusal, BaseException и owned/replaced alias rollback подтверждены.
D39 узкий project-directory cap2000, entry/default/все старые caps неизменны;
до правки exact class-red16=3fail/13pass; byte reconstruction старого checker ok.

Корпус288: security126/reading47/settings110/casing5. SHA/bytes/provenance
manifest сохранён, native capture ×2; финальные native-replay288 ×2 и new focused
314 ×2 actual exit0, ordered/once-only IDs/outcomes, native/new первые288 равны.
Full non-live6564 ×2 exit0:6562pass/2 только прежних genuine WinError1314 skips.
Все6250 старых IDs/outcomes и их порядок сохранились; delta ровно focused314.
Frozen230 ×2 и API253 ×2 exit0: IDs/outcomes идентичны accepted routing baseline.
На окончательном fixture layout повторены6 submitted-byte mutants: failures
73/26/2/3/1/2 (can_read, realpath, identity, cap, owned rollback, casing order).
Каждый actual red1 → external-copy backup/r+b restore full SHA+LF/CRLF exact →
те же once-only tests green0. Native/замороженные sources не изменялись.

Final before-records gates actual0: lint599/0; limits599/0, только прежние
split_py11/editing8400 warnings; contract28/0; SEC-01…SEC-08/SEC-20 ok,0.
Реальные selfcheck.main (только REPORTS redirected externally) для
project_ops.settings_get/settings_set/architecture: blocked/exit2 — нет MODULE,
module unit и module-owned corpus. Common checks green. Канонические44 reports
никогда не писались/восстанавливались. Реальные client probe этих имён на внешнем
synthetic project: unknown_tool/exit1, не доказательство public ToolSpec/capability.
UID86/actual sentinels4/project.godot335B/native tree/frozen references exact;
pyc0. Current tree5021files/879dirs, original-baseline delta changed6/added320/
deleted0; дополнительные docs-пины F0 учтены отдельно, README не трогался.

Полнота ограничена reference: settings_actions normalize/prepare/schema,
не Godot ProjectSettings getter/setter/apply. _parse_project_godot — file-parser
observation; native action path uses can_write, can_read проверен в foundation
policy/architecture, отсутствующий native getter не выдуман. HTTP/confirm/editor
completion/history rollback/STATE/host authority и живой Godot вне мандата.
Actual Windows junction identity/casing проверены на fixture; symlink capability
refused errno22/WinError1314 как corpus observation без skip, не symlink-policy
success. Fixed UNC seam предотвращает SMB/DNS; live UNC не заявлен. Сети не было.

Сохранённые incident receipts: initial capture exit1 на двух repr-escaped sandbox
prefixes (prefix-only correction, no golden publication); false-red новых limit
tests отвергнут exact guard до cap (API names/signature fixed, expectations intact);
mutation selector existing/previous refused до apply; full ×2 exit1 на global
scene-deps .gd scope; только свой new fixture каталог byte-exact перенесён внутрь
project-owned corpus, old test/corpus/goldens не менялись. Final native/focused/full
повторены после разбора. External check adapters дважды отказали на preflight
import до real checks; originals/logs сохранены, import path исправлен только в
external runner, реальные результаты выше получены повторным вызовом.

Fixture owner: fixtures/corpus/project/fixtures/{core,blank}; external test copies
содержат те же .gd/.tscn/project.godot. No ToolSpec/MODULE/bootstrap integration.
tests-map project_ops rows48–49/85–86 остаются corpus: partial foundation не
закрывает host/HTTP legacy cases. README L71 уже зарегистрирован; L69/L70 и
полные README/parity/tests-map bytes сохранены. Никакой annotation «принят» нет.

Вердикт: reference evidence complete/submitted for independent review;
reference stage6, MODULE settings_get/settings_set/architecture0/skeleton.
Не accepted/ported, live editor не выполнялся. After-records/after-closeout gates
и финальная byte/prefix/evidence печать ещё должны выполниться после этой записи.
Следующее действие: независимая приёмка reference по resume-f0/SHA256-final.json;
MODULE/HTTP/downstream integration — только отдельный мандат после приёмки.

### Final measured gate receipt / project-core F0 (2026-11-06)

After-records actual exit0×4: lint599/0, limits599/0/two unchanged warnings,
contract28/0, security0. Final-results-verification bad0: native288/focused314/
full6564/frozen230/API253 pairs ordered/once-only;6250 old outcomes/order exact,
new314; six final mutants restored exact. Original STOP/F0 records remain.
Reference6 submitted, independent acceptance pending; MODULE0/skeleton.
Последняя проверка и immutable seal находятся в resume-f0/final-verification.json
и resume-f0/SHA256-final.json: seal пишется последним после after-closeout gates,
полных byte-prefix/scope/native/old-evidence проверок, не заменяя STOP seal.
Следующее действие: independent reference acceptance по этому seal; никаких
изменений MODULE/HTTP/downstream без отдельного мандата. Не accepted/ported.

### Приёмка независимого аудита (2026-11-06, сессия 78)

**Вердикт: project-core reference-срез ПРИНЯТ.** Полные project-модули (MODULE/HTTP/Godot-интеграция) НЕ ported — отдельный мандат.

Проверено независимо:
- Печать resume-f0 SHA256-final (c7a4c525…): repository 5021/5021 bad=0; evidence files 124645/124645 bad=0 missing=0 (чанковая верификация аудитора); dirs 119140 / links 1130 — метаданные.
- Репо == tree-after 5021/5021 (0 mismatch); дельта STOP→F0 ровно 6 changed + 320 added, removed=0.
- Пины byte-exact vs native: project_tools 102471 B 79e9b035…, project_settings_actions 13735 B fcdb4635…; связка runtime_bindings 2877 B 432a9b32 (+2 алиаса), check_limits 5681 B 862ce80e (D39).
- Прогоны (ordered/once-only): native 288×2, focused 314×2, полный 6564×2 = 6562 passed/2 legacy skip; frozen 230×2, api-core 253×2; все 6250 старых ID/outcomes сохранены.
- Мутации 6/6 убиты (red exits=1): can-read-deny-allow 73 (SEC-матрица), 26, 2, 3, project-class-default 3, alias-owned-rollback 1, casing-rollback-order 2; restores SHA/LF/CRLF byte-exact, зелёные повторы.
- Гейты: lint 599/0, limits ok/2 (прежние), contract 28/0, security ok/0. Hygiene 44/86/0/4 сентинела.
- Selfcheck честный: project_ops.* blocked/exit 2 (MODULE отсутствуют), setup-refusal сохранён; parity L95–97 осознанно не тронуты портёром — отклонение принято, пометку реестр несёт здесь и в README.

Инцидент F0 (неполная таблица импортов аудитора) закрыт поправкой; STOP портёра признан корректным.

