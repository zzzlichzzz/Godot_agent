# C.8 — `verification.tscn_lint` (инструмент `check` для сцен)

Ты — портер. Продолжаешь перенос Godot-агента по эталону из старого плагина
`D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\python\godot_tools\`.
Ты **не аудитор**: этап сам себе не ставишь, шапку «выполнено/принято» не пишешь,
`docs/porting/_audit-handoff.md` не правишь.

Обязательное чтение до кода: `AGENTS.md` → `RULES.md` (R-01…R-22) → `docs/architecture.md` →
`docs/PORTING.md` → `docs/parity.md` (строка 67) → `docs/tests-map.md` → `docs/PROGRESS.md`
(строка механизма) → `docs/porting/_template.md` → `docs/WORKLOG.md` (последние 3 сессии) →
`docs/security/invariants.md`.

## §0 База (снято аудитом, сессия 58, 2026-10-30 — не пересчитывай «на глаз»)

- pytest non-live (`python -B -m pytest python/modules tests/py --ignore=tests/py/live -q
  -p no:cacheprovider`) → **2014 passed**, 0 fail/err/skip; `--collect-only` — **2014** в **76** файлах.
- `tests/py/live` → **3 passed** (~20 с; Godot `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`).
- `python -B tools/snapshot_diff.py` → **404** кейсов, 0 расхождений.
- `python -B tools/gen_contract.py --check` → **17** артефактов, 0 расхождений (цель среза — 18).
- `python -B tools/lint_arch.py` / `tools/check_limits.py` → **481** файл, 0 нарушений, 0 предупреждений.
- `python -B tools/security_audit.py` → ok.
- selfcheck: `scene_model.node_reparent` ok (unit 155, corpus 32), `scene_model.node_delete` ok (131/27),
  `scene_model.node_rename` ok (162/36), `scene_model.connections` ok (108/25), `scene_model.scene_deps`
  ok (176/40), `scene_model.tree` ok, `scene_model.node_info` ok, `verification.gd_lint` ok.
- Мост не трогаем: `contract/editor_verbs.json` sha `CDAF8D23A6BF…`, 6 примитивов, `verbs_version: 3`,
  `protocol: 1`; `editor/bridge/verbs/scene/scene_executor.gd` `B7AFF592B75D…`.
- Замороженные файлы (менять нельзя): `python/kernel/schema.py 629FCE54E6FE… 147 строк`,
  `tools/lint_arch.py 1FAD8E7470D5…`, `tools/gen_contract.py FA7E6E91C872…`,
  `tools/security_audit.py 2CF0D7F6B1AF…`.
- Принятые артефакты, которые нельзя сломать: `python/formats/tscn.py 9D69AFECDCC0… 345 строк`
  (`__all__` = `structure/fields/patch/rows` + append-only блоки C.5/C.6/C.7),
  `python/formats/tscn_refactor.py e4a9f60a6381… 74 строки`, `python/formats/gdscript/node_paths.py
  92531952fd26… 63 строки`, `python/modules/scene_model/shared/node_path.py E747FB1B2E50… 41 строка`,
  `python/modules/scene_model/shared/refactor_plan.py 37 строк`,
  `node_rename/domain/core.py B5F370906049…`, `node_reparent/domain/core.py f53a3384f34e…`,
  `node_delete/domain/core.py fe63bc232bbc…`, `node_info/domain/core.py 3D357E3F8784…`,
  `scene_deps/domain/core.py 4D192DD6FDAD…`, `connections/domain/core.py 4F7366C418DD…`.
- Дерево — **1932** на старте C.8 (после этапа 3 с корпусом и permanent-тестами — 2031; 2043 было до чистки 111 `.gd.uid`, которые создал мой live-прогон C.7 — удалены по времени, 8 старых в `fixtures/parity/gdscript/` не тронуты), `__pycache__` 0, `.pytest_cache` 0, `.bak/.tmp/.orig` 0, `zz_*` 0.
- Правил 22, промптов 27, листов механик 18 (+1 = 19), механик 44 → **17** на этапе 7,
  1 на этапе 6 (`editing.symbol_rename`), 26 на нуле.
- Git в `agent-rebuild` нет намеренно. Старый плагин: HEAD `ba0535d4`, `tscn_lint.py` —
  **74080 B, 1315 строк**, `node_refactor.py` `2D708A384177FA0A…` 46881 B; в `git status` ровно два
  `??` (`_ref2.log`, `godot_tools/_excl.log`), `git diff` пуст.
- Среда: PowerShell, команда дольше ~30 с умирает — дроби; в каждой команде
  `PYTHONDONTWRITEBYTECODE=1`; stderr считай ошибкой — пиши в файл; JSON только через `--args-file`;
  две мутации одновременно запрещены; подложку `.gd` убирай вместе с `.uid`.

## §1 Границы среза

- Механика: `verification.tscn_lint` — инструмент **`check`** (сцена). Имя и аргументы сверь со
  скелетом `python/modules/verification/tscn_lint/module.py` (`tool: check`) и с записью
  `docs/parity.md:67`; если фактическое имя в эталоне иное — зафиксируй в листе и в §4.
- Лист механики: `docs/porting/verification.tscn_lint.md` — создаёшь **первым**, статус «этап 1»,
  дальше по ходу обновляешь (R-19).
- Модуль уже существует скелетом: `python/modules/verification/tscn_lint/`
  (`module.py`, `tools.py`, `app.py`, `domain/core.py`, `domain/__init__.py`, `tests/test_core.py`).
  Заполняешь его, папку не переименовываешь.
- Корпус: `fixtures/corpus/verification/tscn_lint/` — кейсы `NNN-id.json` + `manifest.json`
  (пины sha/байтов кейсов, `reference_commit`, sha и размер `tscn_lint.py`). Ожидания снимаешь с
  эталона одноразовым скриптом `python -B` (в репозиторий он не попадает), как в C.2/C.6/C.7.
- Карточка: `contract/capabilities/check.json` → артефактов станет **18**.
- Записи: строка `verification.tscn_lint` в `docs/PROGRESS.md`, строка 67 в `docs/parity.md`,
  сессия в `docs/WORKLOG.md`, статус промпта в `docs/porting/README.md`.
- **Вне среза** (не начинать, даже если «рядом»): `verification.check` (агрегатор пайплайна),
  `verification.api_check`, `verification.headless`, `verification.runtime_checks`,
  `verification.action_judge`, `editing.write_apply`/WAL/undo, `editing.scene_ops`,
  `agent_scene_executor.gd`, мост, `apply_prepared_node_refactor`, любые записи на диск.
- Расширение `python/formats/*` — только append-only и только если без него нельзя (там уже живут
  единственные парсеры `.tscn` и `$`-путей). Своих регулярок «на сцену» в модуле быть не должно:
  разбор структуры — `formats/tscn.py`, ищи в нём нужное (`structure`, `fields`, `patch`, `rows`).
- Наследство: `shared/node_path.py` и `shared/refactor_plan.py` — единственные места резолва узлов и
  сборки планов; `verification/gd_lint` — единственный линтер `.gd` (если понадобится); диффы —

## §2 Контракт и раскладка (якоря эталона — `godot_tools/tscn_lint.py`, 1315 строк)

**Публичный вход (копируй буквально, не «улучшай»):**

- `is_scene_path(path)` (`:155`) — гейт по расширению `.tscn/.scn/.res`;
- `lint_and_fix_tscn(text, project_root=None, addon_dir=None, planned_paths=None) -> (fixed, problems)`
  (`:953`) — «ничего не бросает и не печатает, только анализирует текст»; `problems` — **список
  строк** (не словарей), `fixed` — текст с механическими починками.

**Эталонный порядок (его и воспроизводи):**

1. нет `[gd_scene` в тексте → `(text, [])` без анализа;
2. построчно по заголовкам: удалить закрывающие теги `[/node]`, `[/sub_resource]` и т.п.
   (`_CLOSING_TAG_RE:22`, «закрывающих тегов в .tscn не существует»); `>` в конце заголовка без `]`
   → заменить на `]`; заголовок без `]` при чётном числе кавычек → дозакрыть; иначе → `problems`
   «строка N: заголовок секции «…» не закрыт «]» …» и **немедленный выход**;
3. `_scan_value_balance` → `_scan_property_syntax` → `_scan_scene_semantics` →
   `_scan_scene_semantics_v83` → `_find_resource_cycles`; если что-то нашлось — выход **без**
   дальнейших починок (порядок и ранние выходы — часть контракта);
4. автопочинки: `_reorder_resource_sections` (`ext/sub_resource` перед первым `[node]`),
   `_strip_invalid_uids`, `_reorder_nodes_for_parent_order`, `_convert_ctor_values` (`Type.new()` →
   `[sub_resource]`, спорные — в `problems`), `_toposort_sub_resources`;
5. `_check_connections_and_parents` → `_scan_node_path_refs`;
6. `_fix_single_candidate_refs` — единственная битая ссылка на единственный ресурс своего вида
   чинится молча;
7. при `project_root`: `[ext_resource path="res://…"]`, которого нет на диске → в `problems`;
   пути из `planned_paths` отсутствие файла ошибкой **не** считают (нормализация: без `res://`,
   `\`→`/`, strip `/`, lower);
8. вернуть `(fixed, problems)`.

**Контракт инструмента (сверь `gen_contract`):**

- аргументы: `path` (`res://…`, только `.tscn/.scn`, иначе типизированный отказ), `content`
  (проверяемый текст), `planned_paths` (массив `res://`-путей плана, по умолчанию пустой);
- результат: `fixed` (строка), `changed` (bool, `fixed != content`), `problems` (массив строк);
  `fixed` — **данные плана**, инструмент на диск не пишет;
- `effects="read"`, `idempotent=True`, `cost="cheap"`, ошибки `invalid_input`/`not_found`/`denied`;
  лимит чтения — существующий `READ_TEXT_MAX_BYTES` ядра, свой не выдумывай.

**Раскладка и лимиты (R-05, R-06, R-11, R-12, R-14, R-15):**

- `domain/core.py` — чистая логика над текстом: без `os`, `pathlib`, `io`, `socket`, `subprocess`,
  `re` (регулярки `.tscn` уже в `formats/tscn.py`; нужен новый — append-only в форматах, не в домене),
  без `open/eval/exec/__import__`;
- `app.py` ≤ 80 строк — только оркестрация: снять `res://`, проверить политику путей, прочитать файлы
  для шага 7 через порт, вызвать домен, отдать типизированные ошибки;
- `tools.py` ≤ 150 строк — строгая схема (`additionalProperties: false`), `problems` — массив строк,
  `changed` — `boolean`;
- файл ≤ 400 строк, модуль ≤ 3000, зона ≤ 8000; тексты ошибок — буквально как в эталоне.


## §3 Шаги

1. **Лист** `docs/porting/verification.tscn_lint.md` по шаблону `_template.md`, статус «этап 1»:
   цель, старый код (`tscn_lint.py:1-1315`), старые тесты (см. ниже), границы, решения.
2. **Инвентарь старого**: `godot_tools/tscn_lint.py` (1315 строк), его единственный вызов —
   `main.py:38` (импорт), `main.py:1987` (`tscn_lint.is_scene_path(path)`), `main.py:2062`
   (`lint_and_fix_tscn(candidate, project_root, STATE.get("addon_dir"), planned_paths=…)`).
   Ветка `_lint_action_scene` подменяет `patch_file` на `create_file` с исправленным текстом — это
   **логика старого агента**, а не контракт нового инструмента; в срез не входит.
3. **Корпус** `fixtures/corpus/verification/tscn_lint/` — одноразовый `python -B` скрипт, `sys.path`
   = `…\godot_agent\python\godot_tools`, `…\python\parsers`, `…\python`; на каждый кейс пиши
   `expect.result = {fixed, changed, problems}` буквально из эталона. Минимум **20** кейсов, из них
   обязательны: валидная сцена (0 problems, `changed=False`), `>` вместо `]`, отсутствующий `]` при
   чётных кавычках, отсутствующий `]` при нечётной кавычке (проблема + выход), `[/node]`-мусор,
   `ext_resource` после `[node]`, `uid://dummy`, узлы не по порядку `parent`, `Type.new()` →
   `[sub_resource]`, цикл ресурсов, `[connection]` на несуществующий узел, неверный `parent`,
   `NodePath` на несуществующий узел, единственная битая ссылка на единственный ресурс, спорные две
   кандидатуры (молча не чинится), `load_steps` не сходится, `.tres` (ранний выход), CRLF, BOM,
   lone `\r`, без финального `\n`, «команды в данных» (текст с `eval(`/`__import__`), не-сцена
   (`path` не `.tscn`), защищённый путь. В `manifest.json` — пины sha/байтов, `reference_commit`,
   sha и размер `tscn_lint.py` (74080 B).
4. **Тесты до кода** (сначала красные): `tests/test_core.py` — параметризация по всем кейсам с
   полным `fixed` (побайтово) и полным списком `problems` (порядок!), AST-тест «домен без IO/`re`/
   команд», «данные не становятся командами», «пины манифеста», «дедуп логики» (домен только
   делегирует в `formats`); `tests/test_app.py` — те же кейсы через `app.call` с типизированными
   отказами, лимит чтения, «преflight отказ до IO», `check_apply`-подобных инструментов у модуля нет;
   интеграционный `tests/py/integration/test_tscn_lint.py` — через настоящий `build_agent`.
5. **Код**: `domain/core.py` (шаги §2), `app.py` (оркестрация), `tools.py` (`ToolSpec`), `module.py`
   (`ModuleSpec(id="verification.tscn_lint", capabilities=["verification.tscn_lint"])`), `ports.py`.
6. `gen_contract` → **18** артефактов; `selfcheck verification.tscn_lint` зелёный; `snapshot_diff`
   404+кейсы/0; полная регрессия суммой = collect-only; live остаётся 3.
7. Записи: лист (этап 7 «ported, готово к независимому аудиту; принятие не заявлено»), `PROGRESS`,
   `parity.md:67`, `WORKLOG` (сессия), `README` (промпт выполнен).

## §4 Решения, которые нужно принять до кода (и записать в лист)

1. **Дом — не `formats`.** `lint_and_fix_tscn` — поведение фичи, а не парсер: живёт в
   `verification/tscn_lint/domain/core.py`. В `formats/tscn.py` — только примитивы, которых реально
   не хватает; каждый такой добавок — append-only + parity-тест + мутация.
2. **Регулярки.** В домене `re` запрещён; вынеси их в `formats` как именованные примитивы или
   обойдись `structure/fields/rows`. Исключение «в домене можно re» — не принимается (R-11 покрывает
   `os/pathlib/socket/subprocess`, `re` ловится только AST-тестом модуля — не дай ему покраснеть).
3. **`problems` — строки.** Не превращай в `[{line, code, message}]` «для красоты»: эталон отдаёт
   строки, старый агент показывает их префиксом до 8 и добавляет «…и ещё N». Формат — контракт.
4. **`fixed`/`changed` вместо записи.** Инструмент read-only: `fixed` возвращается как данные.
   Никаких `write_*`, WAL, undo, `agent_scene_executor.gd`.
5. **Ранние выходы — контракт.** Порядок сканеров и «нашли проблему → не чиним» воспроизводи
   буквально; «улучшение» (например, продолжать починки после проблем) запрещено (R-22).
6. **Пути и политика.** `planned_paths` — обычная нормализация (`res://`, `\`, `/`, lower); доступ
   к файлам — через политику ядра, отказ → `denied`; `res://` в `path` обязателен, иначе
   `invalid_input` с текстом эталона.
7. **Один экземпляр логики.** Проверка существования `ext_resource` — одна функция; если она уже
   есть в `scene_deps`/`tree`, переиспользуй, не копируй.


## §5 Доказательства, которые обязан предъявить (по одному за прогон, файлы восстанавливать побайтово)

Правила R-22: одна мутация за прогон, до мутации — байтовый бэкап и sha256 файла, после — тот же
sha256 и тот же EOL-профиль; доказательство — падение **твоих** тестов на **сдаваемом** файле;
эквивалентная мутация объявляется честно с объяснением, почему тесты её не видят.

| # | Что сломать | Где (эталон) | Ожидание |
|---|---|---|---|
| M1 | не заменять `>` на `]` в заголовке | `:953+` | красный кейс «`>` вместо `]`» |
| M2 | не удалять `[/node]`-теги | `_CLOSING_TAG_RE:22` | красный кейс с мусорными тегами |
| M3 | не сортировать узлы по `parent` | `_reorder_nodes_for_parent_order:167` | красный кейс «узлы не по порядку» |
| M4 | пропустить проверку существования `ext_resource` | шаг 7 | красный кейс missing dependencies |
| M5 | продолжать починки после найденных проблем | шаг 3 | красный кейс раннего выхода |
| M6 | отдавать `problems` как dict/`{line,...}` | контракт | red в контрактном/интеграционном тесте |
| M7 | `planned_paths` не учитывать | шаг 7 | красный кейс «путь из плана» |
| M8 | `Type.new()` не конвертировать | `_convert_ctor_values:288` | красный кейс конструктора |
| P1 | добавить в `ToolSpec.RESULT` неоговорённое поле | — | `gen_contract --check` exit≠0 + red в контрактных |
| P2 | испортить одно ожидание корпуса | — | red в core/app/manifest-пинах |
| P3 | `import pathlib` (или `re`) в `domain/core.py` | — | red в AST-тесте домена |

Дополнительно предъяви: CLI-пробы через `build_agent`/`call` (валидная сцена, `>`-сцена, missing
dependency, `.tres`, защищённый путь) с неизменным SHA-снимком проекта до/после — инструмент
read-only; `selfcheck` после последней мутации; полную регрессию суммой, равной `--collect-only`.

## §6 Стоп-условия

Останавливаешься и спрашиваешь, если:

- нужно изменить замороженный файл (`schema.py`, `lint_arch.py`, `gen_contract.py`, `security_audit.py`)
  или мост (`editor_verbs.json`, `agent_scene_executor.gd`, `verbs_version`);
- ломается любой принятый артефакт из §0 (нужен рефакторинг принятого кода — только с разрешения);
- `snapshot_diff` расходится, `lint_arch`/`check_limits` дают нарушения, `security_audit` не ok,
  любой `selfcheck` не ok;
- сумма тестов не равна `--collect-only`, появились skip, live-тестов стало не 3;
- хочется «улучшить» эталон: другой порядок сканеров, `problems` как объекты, запись `fixed` на диск,
  новые имена инструментов, автопочинки сверх эталона;
- нужна запись на диск, WAL, undo, редакторный мост или агрегатор `verification.check`;
- старый плагин изменился (`git diff` не пуст или `??` не два).

## §7 Что проверит аудитор (своими прогонами, не по отчёту)

1. `pytest --ignore=tests/py/live` (junit, дробить по 30 с), `--collect-only` — сравнить ID и сумму;
   `tests/py/live` — 3 passed.
2. `selfcheck verification.tscn_lint` + повторно `gd_lint`, `node_info`, `tree`, `connections`,
   `scene_deps`, `node_rename`, `node_reparent`, `node_delete` (принятое не поехало).
3. `gen_contract --check` = 18, `snapshot_diff` 404+/0, `lint_arch`/`check_limits` 481+/0,
   `security_audit` ok.
4. **Независимая пересборка корпуса**: своим скриптом с эталона `lint_and_fix_tscn` — побайтовое
   сравнение `fixed` и полное сравнение списка `problems` по всем кейсам, плюс дифференциал на всём
   `fixtures/**/*.tscn` (эталон vs порт) с подсчётом расхождений.
5. **Свои мутации** M1–M8 и подложки P1–P3 по одному разу, с побайтовым восстановлением; M5/M6
   ожидаются красными обязательно — если 0 red, это дыра в корпусе, а не «эквивалент».
6. Чтение кода: лимиты файлов, IO только в `app.py`, `re` в домене отсутствует, единственный
   экземпляр логики, `problems` — строки, `fixed` не пишется на диск.
7. Байтовая неизменность замороженных и принятых файлов, старый плагин (два `??`, пустой diff),
   `__pycache__` 0, `.gd.uid` в `fixtures` = 8.
8. Этап 7 — только если всё зелёное; иначе — замечания с точным воспроизведением и промпт на правку.

## §8 Финальный прогон и записи

```powershell
$env:PYTHONDONTWRITEBYTECODE="1"; $env:PYTHONIOENCODING="utf-8"
python -B -m pytest python/modules tests/py --ignore=tests/py/live -q -p no:cacheprovider
python -B -m pytest python/modules tests/py --ignore=tests/py/live -q -p no:cacheprovider --collect-only
python -B -m pytest tests/py/live -q -p no:cacheprovider
python -B tools/gen_contract.py --check
python -B tools/snapshot_diff.py
python -B tools/lint_arch.py
python -B tools/check_limits.py
python -B tools/security_audit.py
python -B tools/selfcheck.py verification.tscn_lint
```

Записи: лист механики (этап 7 «ported, готово к независимому аудиту; принятие не заявлено» + все
числа и таблица мутаций), `docs/PROGRESS.md` (строка механики), `docs/parity.md:67`, `docs/WORKLOG.md`
(сессия), `docs/porting/README.md` (статус промпта). Шапку «принято/выполнено» и этап ставит только
аудитор; `docs/porting/_audit-handoff.md` не трогаешь.

  `node_rename/domain/diff_preview.py`. Дублировать логику запрещено (R-04).
