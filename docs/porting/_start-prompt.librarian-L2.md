# Мандат L2 — modules/context/ask: рабочий инструмент `ask` (MODULE этап 1)

Класс: жёсткий. Приёмка: независимый аудит. Частичный вердикт легален (честная фиксация фазы).

**Предусловие, выполнено**: librarian F1 corrected-native reference-срез ПРИНЯТ независимым
аудитом (досье librarian-D51-F1-20261110, WORKLOG 2026-11-10, 886 962 B `2d20efaa…`);
восстановление 2296 закрыто; D51 (AST-детектор SEC-03) принят. Параллельные срезы запрещены.

## Цель (критерии готовности)

1. `python tools/selfcheck.py context.ask --json` → verdict `ok`, exit 0:
   module ok (ModuleSpec собирается реестром, `ask` в tools/list), unit ok (тесты модуля),
   corpus ok (snapshot_diff: 141 кейс librarian + guard72 = 213, расхождений нет),
   static layers/limits/contract/security ok.
2. Probe: `Agent.call("ask", {...})` на fixture-проекте → реальный ответ (карта кода и
   фрагменты), exit 0; на некорректном вводе — типизированные invalid_input/denied.
3. `contract/capabilities` обновлён генератором (`gen_contract --check` зелёный).
4. Четыре замороженных файла byte-exact до и после (пины в §2).

## §0 — самопересчёт (всё по факту)

Корень репо: `D:\vajno\Godot\agent-rebuild\addons\godot_agent`; project.godot уровнем выше.
docs/WORKLOG.md — CRLF; пересчитай размер/SHA на старте (ориентир 886 962 B, `2d20efaa…`);
append чистой добавкой с prefix-assert. Tree-identity до старта и на каждом шаге.

Текущее честное состояние: `modules/context/ask/` — заглушки TODO (tools.py 3 строки,
app/module/domain/test — TODO); selfcheck context.ask → blocked/exit2 (module/unit/corpus
not_implemented; static ×4 ok); probe `ask` → unknown_tool/exit1 (в реестре нет владельца).
Корпус УЖЕ существует: `fixtures/corpus/context/librarian/` — manifest.json
(`mechanic: librarian, module: context.ask, module_stage: 0, reference_only: true`),
catalog.json (141 кейс: tokens/answer/synonyms/log/policy-path/edge), guard72.json,
fixtures/basic (мини-проект), fixtures/guard, observations 001–141.

## §2 — замороженные пины (байты не трогать)

- `python/substrate/context/librarian.py` 97 676 B `340b5dd2be96ebc4…` (LF 1551 / CRLF 1551)
- `python/substrate/context/ml_project_index.py` 65 753 B `2f7694a91a48e294…` (LF 1120 / CRLF 866)
- `python/substrate/context/ml_data.py` 32 324 B `e13d56800d124627…` (LF 757 / CRLF 0)
- `python/substrate/context/gd_semantic_parser.py` 15 723 B `bf35dcea5e77011d…` (LF 392)

Любая потребность изменить их байты — STOP, санкция у пользователя. Адаптация — ТОЛЬКО
новыми файлами. Нативные EOL сохраняются во всех новых файлах по образцу среза.

## §3 — архитектура (рамка; детали по ADR-0003/0004/0006, R-02..R-15)

- `modules/context/ask` — владелец инструмента `ask` (R-02 фича=папка, R-05 манифест):
  tools.py ToolSpec (name "ask", effects "read", idempotent True, errors
  ("invalid_input","not_found","denied"), availability "*", limits — нативные константы
  бюджета/квот через D47 exact-cap pins, не выдумывать); module.py ModuleSpec
  (id "context.ask", provides_tools=("ask",), requires_ports=(...), capabilities,
  entrypoints={"call": app.call}, corpus "corpus"); app.py — оркестрация ≤80 строк (R-04);
  domain/core.py — чистая логика (R-11: без os/pathlib/socket/subprocess); ports.py —
  Protocol (runtime_checkable, только сигнатуры).
- Движок — ported librarian в `python/substrate/context/`. Модуль НЕ импортирует substrate
  напрямую: реализация порта — НОВЫЙ файл-адаптер в `python/substrate/context/`
  (например adapter.py), регистрация порта — в `runtime/bootstrap.py` default_ports
  (композиционный корень — единственное место, знающее адаптеры).
- Импорт-окружение нативного librarian (gd_api_cache; project_tools:
  can_read_project_path/describe_scene/read_project_file/search_project_text; minilich.
  ml_project_index/.ml_data через runtime_parent; псевдонимы gd_semantic_parser/librarian)
  активируется существующим механизмом runtime_bindings; production-активация — только
  в адаптере ask-пути. `substrate/context/__init__.py` docstring «Inert… no production
  registration» обновить на честное производственное состояние (авторизовано этим мандатом).
- function_card НЕ портирован: нативные ветки ImportError (L1214) и молчание (L1221)
  сохраняются; реализация ask не должна требовать function_card. `_log_query` остаётся
  нативным молчанием (no-op). Логгер/ротация — нативные байты как есть.
- Хранилище индекса/кэша задаёт адаптер (state_dir профиля), НЕ проект пользователя.
  Если нативный код жёстко пишет в фиксированные пути внутри проекта — STOP, санкция.
- Форма args/result — по фактическому выводу нативного ask; сверяй с observation-файлами
  корпуса (001–141) и catalog.json; не invent поля.

## §4 — корпус и selfcheck (развилка — выбрать минимум, эталоны не переписывать)

observations 001–141 — эталоны нативного поведения, записаны в F1; их НЕ переписывать.
Проблема: `tools/selfcheck.py::corpus_folders` (строка 239) ищет только
`fixtures/corpus/context/ask/`, а корпус лежит в `context/librarian` (манифест уже
`module: context.ask`; snapshot_diff обходит все `*/*/manifest.json` и фильтрует по
module — corpus 213×2 в F1 зелёный именно так). Варианты:
  (i) минимальная правка corpus_folders: учитывать манифесты с `"module" == module_id`
      в области модуля (скан `*/*/manifest.json`), без прочих изменений selfcheck;
  (ii) `fixtures/corpus/context/ask/manifest.json` — алиас-манифест, ссылающий на
      librarian-корпус (если snapshot_diff это поддерживает без правок).
Выбери (i) или (ii) по минимальности диффа; правка selfcheck — общая механика: прогони
`tests/py/tools/test_selfcheck_readiness.py` + `test_selfcheck_unit_selector.py` ×2 до и
после, зафиксируй в досье. manifest.json librarian: `module_stage: 0→1`,
`reference_only: true→false` (авторизовано); сам манифест запинить в досье.

## §5 — порядок работ (порядок G)

1) Полный перечитанный мандат + действующие решения D43–D51, поправки F0/F1, обе приёмки
   (engine-cache, librarian reference1). 2) Свежий §0 пересчёт: tree-identity, пины ×2,
   инвентарь корпуса. 3) Red-before-code: тесты, фиксирующие current blocked/unknown_tool,
   красные до реализации. 4) Реализация: ports → domain → app → tools → module → adapter →
   bootstrap-порт; unit-тесты модуля по кейсам корпуса (R-07). 5) Corpus: snapshot_diff
   141 + guard72, расхождений ноль. 6) Мутации ≥3 на НОВОМ коде (адаптер теряет порт,
   domain ломает валидацию/бюджет, app теряет read-guard) — каждая убита, restore-pin
   bytes/SHA/LF/CRLF == original, same_test_ids. 7) Гейты ×2 (lint_arch, check_limits,
   gen_contract --check, security_audit) + security ×2: guard corpus 72/72 зелёный в
   focused, реальный bind/listen остаётся красным (B-1). 8) Регрессии ×2: full
   (7094 pass + 2 genuine1314 skip, старые ID/outcomes точные), frozen230, API253,
   project288; focused 352 остаётся зелёным. 9) Записи: WORKLOG по этапам,
   docs/porting/librarian.md (статус MODULE 1), deviations (новые D при отклонениях),
   README строка статуса — в конце. 10) Досье: staging → прогоны → SHA256-final.json
   (seal последним) → postseal ZIP + побайтовая проверка; submission.json (пины, delta,
   счётчики, selfcheck/probe дословно, честные маркеры).

## §6 — заранее авторизованные правки репо (каждая — с записью в WORKLOG)

Новые/заменяемые файлы modules/context/ask/* (заглушки → реализация), ports.py, adapter,
тесты модуля; runtime/bootstrap.py: +1 порт в default_ports; substrate/context/__init__.py:
docstring; fixtures/corpus/context/librarian/manifest.json: stage/reference_only; контракт
capabilities (генерируемый); минимальная правка corpus_folders ИЛИ алиас-манифест (§4).
Всё сверх списка — STOP с запросом санкции.

## §7 — честность и STOP-пункты

Не объявлять parity/live за пределами факта; selfcheck/probe — дословно в досье.
STOP немедленно: (а) нужна правка байт четырёх замороженных файлов; (б) нативный код
требует записи в проект пользователя или реальных сокетов; (в) эталон корпуса не
воспроизводится; (г) требуется импорт function_card; (д) правка selfcheck сверх §4(i).
Сеть/сокеты запрещены (SEC-03/B-1). symlink1314 остаётся честным пробелом. engine_kb.*
в этот мандат не входит.

## §8 — приёмка аудитора (что проверяется независимо)

seals/ZIP побайтно; repo tree-after == диск; 4 пина byte-exact; red→green; мутации killed
с exact restore; регрессии exact IDs; selfcheck построчно exit0; probe — реальный ответ;
B-1 красный на реальном bind; corpus 141/141 + guard72; честные маркеры; WORKLOG/README/
deviations согласованы; досье-дисциплина (seal последним).

# Поправка L2a — решения по STOP §0 (аудитор, 2026-11-11)

## D52 — корпусный реплей: разрешение на механизмы (эталоны неприкосновенны)

Факт: snapshot_diff падает AttributeError/exit1 на catalog.json (список кейсов попадает
в record.get); F1 прогонял 213 кейсов через pytest-раннер, а не через snapshot_diff —
предпосылка §4 о готовности snapshot_diff к librarian-механике была неточной. Для
«corpus ok» в selfcheck прогон обязан идти через snapshot_diff (check_corpus вызывает
его) — значит, исправление обязательно. РАЗРЕШЕНО, узко:
1. Bugfix чтения каталогов: список-каталог не должен падать (AttributeError) — записи
   списка обрабатываются тем же пайплайном; неожиданная структура — явная ошибка, не
   молчание. red→green: новый тест воспроизводит AttributeError до фикса.
2. Ветки librarian-механики (tokens/answer/synonyms/log/policy-path/edge) — предпочтительно
   В НОВОМ helper (replay-helper); snapshot_diff трогается минимально (вызов helper).
   Прогон кейса: build_agent(project_root=fixture/basic, profile="headless") →
   agent.call("ask", …) → структурное сравнение с эталоном observation.
3. Эталоны 001–141, catalog.json, guard72.json, fixtures — byte-неизменны (запинить в
   досье). Расхождение ask ↔ эталон = баг портёра либо реальная дивергенция → STOP;
   правка эталонов запрещена. Нормализация в КОМПАРАТОРЕ — только для документированных
   недетерминированных полей (перечислить в досье), не для сокрытия содержательных
   расхождений.
4. Доказательство «старые assertions не тронуты»: полный прогон snapshot_diff по ВСЕМ
   существующим корпусам ×2 до и после фикса — outcomes/verdicts идентичны; тесты
   selfcheck (readiness + unit_selector) ×2 до/после.
5. Новые тесты на багфикс и helper. Это правка общей механики — класс «устав
   самопоправок» ярус B (как D51); записать в deviations.md под номером D52.

## D53 — _log_query: лог живёт в state_dir; отключение НЕ разрешено

Факт (измерение портёра): нативный _log_query реально пишет JSONL-лог (ротация
>262 144 → .1, CRLF); no-op лишь при отсутствии зависимости/ошибке хранилища.
Прежняя формулировка F0 «нативное молчание» неточна и ОТМЕНЯЕТСЯ. РЕШЕНИЕ:
1. Продакшн-адаптер обязан направлять лог в state_dir профиля (как api_cache); ротация
   и формат — нативные как есть. Писать лог в проект пользователя запрещено (побочный
   эффект в проекте + обход writer/policy-дисциплины).
2. Молчаливое отключение лога в продакшне ЗАПРЕЩЕНО: кейсы 094–115 (log/ротация) обязаны
   воспроизводиться через ask в corpus — иначе corpus ok недостижим, а «паритет» без
   лога был бы ложным заявлением.
3. Если маршрутизация в state_dir невозможна без правки байт четырёх замороженных файлов
   (путь жёстко зашит от корня проекта без параметра) — STOP, санкция; тогда
   рассматривается узкая токен-правка (прецедент D50) либо явное отклонение D с
   корпусной развилкой.
4. В досье запинить: точный путь лога в state_dir в проде; воспроизведение ротации
   кейсами 094–115; формат JSONL CRLF.

## Порядок продолжения (L2a)

STOP-срез librarian-L2-20261111 остаётся запечатанным как запись остановки. Продолжение —
новый срез: свежий §0 пересчёт (tree-identity, 4 пина byte-exact, корпус-пины),
corpus-реплей по D52, далее реализация по §3/§5 исходного мандата; corpus_folders-развилка
§4 остаётся (первичен вариант (i)). Досье librarian-L2a-<дата>, seal последним, postseal
ZIP; selfcheck/probe — дословно; приёмка — независимый аудит.
