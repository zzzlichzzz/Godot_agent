# C.7 — `scene_model.node_reparent` + `scene_model.node_delete` (только планы)

Ты — портер. Работаешь в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`. Ты **не аудитор**:
этап не ставишь, шапку «выполнено/принято» не пишешь, `docs/porting/_audit-handoff.md` не правишь.
Читай по порядку: `AGENTS.md` (порядок обязательного чтения), `RULES.md` (R-01…R-22), `docs/PORTING.md`,
`docs/parity.md`, `docs/tests-map.md`, `docs/PROGRESS.md`, оба листа из §1, последние 3 сессии
`docs/WORKLOG.md` («Где остановились»), `docs/NOTES.md`. Перед работой — `docs/security/invariants.md`.

## §0 База (снято аудитом, сессия 56, 2026-10-30 — не пересчитывай «на глаз»)

- `pytest python/modules tests/py --ignore=tests/py/live` → **1684 passed**, 0 failed/errors/skipped;
  `--collect-only` → **1684** (67 файлов), ID совпадают. `tests/py/live` → **3 passed** (32.5 с),
  Godot `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`.
- `tests/py/formats` → **317 passed**. `tools/snapshot_diff.py` → **345 кейсов, 0 расхождений**.
  `tools/gen_contract.py --check` → **15** артефактов (следующий шаг даёт **17**).
  `tools/lint_arch.py` / `tools/check_limits.py` → **472 файла, 0 / 0**. `tools/security_audit.py` → ok.
  `selfcheck scene_model.node_rename` → ok: unit 162, corpus 36.
- Словарь моста не трогаем: **6** примитивов, `verbs_version: 3`, sha256 `CDAF8D23A6BF…`, `protocol: 1`.
- Незыблемое: `python/kernel/schema.py` `629FCE54E6FE…` (147 строк), `tools/lint_arch.py` `1FAD8E74…`,
  `tools/gen_contract.py` `FA7E6E91…`, `tools/security_audit.py` `2CF0D7F6…`, `contract/editor_verbs.json`
  `CDAF8D23A6BF…`, `python/modules/editing/scene_ops/…` (`scene_executor.gd` `B7AFF592B75D…`).
- Принятые файлы, которые **ломать нельзя** (сверяй sha256, не «на память»):
  `python/formats/tscn.py` `AE39291E3ABF…` (333 строки; C.5-блок `to_snake:235`, `method_referenced:263`,
  `script_referenced:268`; C.6-блок с `normalize_node_name:274`, `node_rename_edits:286`, `__all__` не расширен),
  `python/formats/gdscript/node_paths.py` `B5416DEE6DBC…` (19 строк, `rename_node_paths`),
  `python/modules/scene_model/shared/node_path.py` `E747FB1B2E50…` (41 строка: единственные
  `rel_path_between`/`find_node_in_scene`), `scene_model/node_rename/domain/core.py` `B5F370906049…`,
  `scene_model/node_info/domain/core.py` `3D357E3F8784…`, `scene_model/scene_deps/domain/core.py`
  `4D192DD6FDAD…`, `scene_model/connections/domain/core.py` `4F7366C418DD…`.
- Файлов в плагине: **1550** (`__pycache__` 0, `.pytest_cache` 0, `*.bak/tmp/orig` 0, `zz_*` 0;
  `.gd.uid` в фикстурах — **8**, все из `fixtures/parity/gdscript/`, их не трогать). Правил: 22.
  Промптов: 26 (последний — этот). Листов механик: 17 (этот срез добавляет 2 → 19).
  Механик 44: этап 7 — 14, этап 6 — 1 (`editing.symbol_rename`), этап 0 — 29 (две из них — этот срез).
- Git в `agent-rebuild` намеренно нет. Старый плагин (`D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent`):
  HEAD `ba0535d4…`, ровно две чужие untracked-строки (`python/_ref2.log`, `python/godot_tools/_excl.log`),
  `git diff` пуст, `node_refactor.py` 46881 B `2D708A384177FA0A…`. Не редактировать, логи не удалять.
- Среда: PowerShell, команда >30 с умирает — дроби; в каждой команде `PYTHONDONTWRITEBYTECODE=1`;
  stderr — в файл; JSON-аргументы только через `--args-file`; две мутации одновременно запрещены;
  подложку `.gd` убирать вместе с `.uid`.

## §1 Границы среза

В срезе — **две механики сразу**, обе **read-only** (план, ничего не применяем):

1. `scene_model.node_reparent` → инструмент `node_reparent_preview`;
2. `scene_model.node_delete` → инструмент `node_delete_preview`.

Сначала листы: `docs/porting/scene_model.node_reparent.md` и `docs/porting/scene_model.node_delete.md`
по шаблону `_template.md`, статус **этап 1**. Затем модули `python/modules/scene_model/node_reparent/`
и `python/modules/scene_model/node_delete/` (по образцу принятого `node_rename/`), корпуса
`fixtures/corpus/scene_model/node_reparent/` и `…/node_delete/` (кейсы + `manifest.json`),
карточки `contract/capabilities/node_reparent_preview.json` и `node_delete_preview.json` (15 → **17**),
строки в `docs/parity.md`, строки 40/41 в `docs/PROGRESS.md`.

Вне среза: `apply_prepared_node_refactor` (`node_refactor.py:969`), любые записи в файлы проекта,
undo/история, `agent_scene_executor.gd` и мост, `node_rename` (принят — не переписывать), `verification.tscn_lint`,
`scene_model.node_info/tree/connections/scene_deps` (приняты).

Наследство (уже принято, **не дублировать**): единственные реализации `rel_path_between`/
`find_node_in_scene` — в `scene_model/shared/node_path.py` (R: единственный экземпляр логики);
разбор `.tscn` — только `formats/tscn.py` (`structure`/`fields`/`patch`/`rows` + append-only операции);
`$`-пути и `find_child` в скриптах — только через `formats/gdscript/node_paths.py`; линт — через
`verification.gd_lint` (публичный порт); diff — `node_rename/domain/diff_preview.py` (эталон
`project_tools.py build_diff_preview`); байты в плане — Base64 (решение пользователя, см. лист C.6).
Расширять `formats/*` можно только **дописыванием** (новые имена, старые — байт в байт), с паритетными
тестами и мутацией.

`structure()` уже отдаёт то, что нужно удалению: `header_span`, `body_span`, `full_span`, `path_span`,
`path`, `unique_name`, `script_id` — сверь это в `python/formats/tscn.py:16-107`, а не изобретай заново.

## §2 Контракт и раскладка (якоря эталона — `python/godot_tools/node_refactor.py`, 1095 строк)

### 2.1 `node_reparent_preview` (эталон `prepare_node_reparent:542-797`)

Вход: `{path, node, new_parent, update_scripts=true}`. Результат — **полный словарь**:
`{action:"reparent_node", scene, old_path, new_path, new_parent, target_node, target_node_path,
files[], reference_count, affected_paths[]}`, где `files[]` = `{action:"patch_file", path, before_hash,
before_bytes, after_bytes, diff, occurrences}` (Base64 для байтов; `absolute` и `scene_res` в плане
не отдаём — как в принятом C.6). Отказы (текст буквально):
`Нельзя перемещать корневой узел сцены` (:563), `Нельзя переместить узел в самого себя` (:566),
`Нельзя переместить узел в его собственного потомка` (:569),
`Узел '%s' уже находится у этого родителя` (:574),
`Узел с именем '%s' уже существует в целевом родителе` (:580).

Семантика по якорям:
- `new_parent` нормализуется: `.` остаётся `.` (`norm_new_parent`, :572); `new_path` = `target_name`
  при родителе `.` (:583-585), иначе `norm_new_parent + "/" + target_name` (:587).
- Заголовок цели (:594-604): `parent="..."` заменяется, если атрибут есть; **если атрибута нет**
  (корневой узел переезжает под другого родителя) — вставляется перед закрывающей `]`;
  +1 к `occurrences` при любом изменении.
- Наследники (:606-618): `parent` переписывается, когда `p == old_path` **или** `p.startswith(old_path + "/")`,
  хвост сохраняется (`new_path + p[len(old_path):]`).
- `[connection from/to]` (:620-637) и дорожки анимации (:639-648) — тот же префиксный принцип.
- Правки сцены применяются **в обратном порядке смещений** (:652), файл сцены попадает в план
  **всегда** (в отличие от rename, где пустой диф можно не отдавать).
- Скрипты (:671-783): `moved_subtree` = цель + наследники (:683-686), `_subtree_new_path` (:688-694),
  пары «от каждого script-узла к каждому перемещённому», плюс прямые пути при скрипте на корне (:721-722),
  дедуп с сохранением порядка (:724-729). **Ключевое правило C.7** (:736-741): если новый
  относительный путь начинается с `..` **или** содержит не-идентификатор, `$Old` переписывается как
  `$"new"` (кавычки!), иначе — обычная форма `$new`; quoted-ветка (`get_node`/`get_node_or_null`/
  `has_node`/`$"…"`) — как в C.6. После правки — линт и отказ
  `После перемещения узла в скрипте %s обнаружена синтаксическая ошибка: %s` (:762-766).
- `reference_count` = сумма `occurrences` по сцене и скриптам (:795), без «скидки» (в reparent нет `scripts_only`).

### 2.2 `node_delete_preview` (эталон `prepare_node_deletion:800-966`)

Вход: `{path, node, cleanup_code=true}`. Результат: `{action:"delete_node", scene, target_node,
target_node_path, deleted_nodes[], files[], reference_count, affected_paths[], warnings[]}`,
`warnings[]` = `{file, line, code, message}` с текстом
`Ссылка на удаляемый узел '%s' в %s:%d: %s` (:950-952). Отказ: `Нельзя удалить корневой узел сцены` (:818).

Семантика по якорям: `deleted_nodes` = цель + всё, у чего `parent` равен `old_path` или начинается
с `old_path + "/"` (:820-833); `deleted_unames` — уникальные имена цели и наследников. Вырезание
заголовка+тела (:840-846), `[connection]` с `from`/`to` в наборе (:849-855), дорожки анимации,
включая `%Unique` удалённых узлов (:858-866); **все вырезания съедают следующие за спаном `\r`/`\n`**
(:843-844, :852-853, :863-864) — иначе остаются пустые строки и расходится diff; правки в обратном
порядке (:870). Скрипты **не правятся**: только предупреждения по каждой непустой не-комментарной
строке, где встречается путь к удаляемому узлу (от каждого script-узла) или `%Unique` (:922-953);
скрипты, прикреплённые к **удаляемым** узлам, в скан не попадают (:894-896).

### 2.3 Раскладка и лимиты (R-05/R-06/R-11/R-12/R-14/R-15)

`domain/` — чистый текст, без `os/pathlib/io/socket/subprocess/re` и без `open/eval/exec`;
разбор — только `formats/tscn.py` (можно дописать append-only `node_reparent_edits`/`node_delete_edits`
рядом с `node_rename_edits`, стиль и `count` — как там), пути и резолв узлов — только
`scene_model/shared/node_path.py`, скрипты — только `formats/gdscript/node_paths.py` (+ линт через
`verification.gd_lint`), diff — общий `node_rename/domain/diff_preview.py` (не копия). `app.py` ≤80 строк,
`tools.py` ≤150, файл ≤400, модуль ≤3000. IO — только в `app.py` через порты (`RawReader`, `ProjectFiles`);
типизированные отказы `invalid_input`/`denied`/`not_found`, сцена только `.tscn/.scn`,
чтение ≤`READ_TEXT_MAX_BYTES`.

## §3 Шаги

1. **Листы** `scene_model.node_reparent.md` и `scene_model.node_delete.md` → этап 1: цель, старый код
   (якоря §2), старые тесты (`tests/test_node_refactor.py`, только чтение), решения, «Следующее действие».
2. **Корпуса с эталона.** Одноразовым скриптом `python -B` с `sys.path` на старый плагин
   (`…\godot_agent\python\godot_tools`, `…\python\parsers`, `…\python`) снять `prepare_node_reparent`/
   `prepare_node_deletion` и записать ожидания в `fixtures/corpus/scene_model/<механика>/<id>.json`
   (`{id, tool, fixture, note, args, expect}`) + `manifest.json` (sha256 и байты каждого входа,
   commit `ba0535d4…`, sha `node_refactor.py` `2d708a38…`). Свои fixture-проекты — в
   `fixtures/corpus/scene_model/<механика>/project/<id>/`, минимальные и намеренные.
3. **Кейсы `node_reparent`** (≥14): простой переезд; поддерево (родители наследников и хвосты);
   цель — корень сцены (в заголовок **вставляется** `parent=`); `new_parent="."`; `[connection from/to]`
   (включая связи внутри поддерева); дорожка анимации `NodePath("A/B:position")` и `%Unique`;
   скрипт с `$Old` → `$"../New"` (правило :736-741 — обязательный кейс, ловится отдельной мутацией);
   `get_node`/`get_node_or_null`/`has_node`/`$"…"`; скрипт на корне (прямые пути); `update_scripts=false`;
   общий скрипт у двух узлов; коллизия имени в целевом родителе; «в самого себя»; «в своего потомка»;
   «уже у этого родителя»; «нельзя перемещать корень»; BOM/CRLF/lone CR; синтаксическая ошибка после
   правки (линт-отказ); отсутствующий скрипт; `.tres`/путь вне проекта/защищённый аддон/нет файла.
4. **Кейсы `node_delete`** (≥14): лист; поддерево (`deleted_nodes` в порядке сцены); «нельзя удалить
   корень»; удаление `[connection]` с `from` и с `to`; дорожки анимации, включая `%Unique`;
   предупреждения по `$Path`, по `get_node("…")`/`$"…"`, по `%Unique`; скрипт, прикреплённый
   к удаляемому узлу, **не** даёт предупреждений; `cleanup_code=false` (предупреждений нет);
   строки-комментарии пропускаются; общий скрипт у удаляемого и остающегося узла; CRLF/BOM/lone CR
   (вырезание съедает переводы строк); отсутствующий скрипт; защищённый/внешний путь, `.tres`, нет файла.
5. **Тесты до кода**: паритет по всему словарю (включая Base64-байты, `diff`, порядок `files`,
   `deleted_nodes`, `warnings`), буквальные тексты отказов и предупреждений, AST-тест «в `domain/` нет IO»,
   пины манифеста, «данные не команды» (`open/eval/exec` не вызываются), лимиты `MAX_*`, отказ от
   `node_reparent_apply`/`node_delete_apply` как `unknown_tool`. Сначала красные — зафиксируй числа.
6. **Код** по образцу `node_rename/`: `domain/core.py` (чистые функции), `app.py` (порты, гейт
   `.tscn/.scn`, типизированные отказы), `tools.py` (`ToolSpec("node_reparent_preview",
   effects="read", idempotent=True, cost="cheap")` и то же для удаления), `module.py`, `ports.py`,
   `settings.py`. Форматные правки — append-only рядом с `node_rename_edits`.
7. `gen_contract` → **17** артефактов (две карточки), `PARITY`/`PROGRESS` — строки своих механик.
8. `selfcheck scene_model.node_reparent` и `selfcheck scene_model.node_delete` — оба ok; полная
   регрессия — сумма по файлам равна `--collect-only`; записи (листы, `PROGRESS`, `parity`, `WORKLOG`).

## §4 Решения, которые нужно принять до кода (и записать в лист)

- **База64 и проекция** как в C.6: `files[].before_bytes/after_bytes` — Base64; `absolute` и `scene_res`
  в план не отдаём; иначе паритет «в лоб» невозможен — это решение пользователя, не улучшение.
- `target_node` в плане — **имя** узла (в reparent и в delete), `target_node_path` — старый путь.
- `new_parent` в плане — нормализованный путь (`.` для корня), а не сырой ввод.
- `deleted_nodes` — цель, затем наследники в порядке сцены; `warnings` — в порядке обхода скриптов
  и строк. Порядок — часть контракта, тесты сравнивают списки как есть.
- Один общий `diff_preview` и один общий `shared/node_path`; новых экземпляров логики не заводить.
- Списки `deleted_nodes`/`warnings`/`files` строить в `domain`, IO — только `app.py`.
- Строгие схемы: `warnings[].line` — целое ≥1, `occurrences` ≥0, `deleted_nodes` непуст, `text`-полей нет.
- Никаких «улучшений» сверх эталона: не добавлять `scripts_only`/`previous_name` в reparent,
  не менять текст предупреждений, не «чинить» скрипты при удалении.

## §5 Доказательства, которые обязан предъявить (по одному за прогон, файлы восстанавливать побайтово)

Мутации — **строго по одной**, на сдаваемом файле, с байтовым бэкапом, сверкой sha256 до/после
и списком красных тестов (R-22). Две мутации одновременно запрещены. Эквивалентный мутант —
честно записать и объяснить, а не «покрасить».

| # | Что ломаем | Ожидание |
|---|---|---|
| M1 | `$"-правило` reparent (`:736-741`): всегда `$new` без кавычек | красные кейсы с `..`/не-идентификатором |
| M2 | `_subtree_new_path` (`:688-694`): хвост не переносится | красные кейсы поддерева |
| M3 | отказ «в своего потомка» (`:568-569`) | красный кейс `descendant` |
| M4 | коллизия в целевом родителе (`:577-580`) | красный кейс `collision` |
| M5 | вставка `parent=` в заголовок корня (`:600`) | красный кейс `root_to_child` |
| M6 | вырезание `\r`/`\n` после `body_span` (`:843-844`) | красные кейсы удаления (лишние пустые строки в diff) |
| M7 | трек `%Unique` удалённого узла (`:861`) | красный кейс с `%`-дорожкой |
| M8 | исключение скриптов удаляемых узлов (`:894-896`) | красные кейсы `warnings` |
| M9 | `deleted_nodes` без наследников (`:827-833`) | красные кейсы поддерева |

Подложки:
- **P1** — лишнее поле в `ToolSpec.RESULT` (не в контракте) → `gen_contract --check` обязан упасть
  на `node_reparent_preview.json`/`node_delete_preview.json`;
- **P2** — испортить ожидание в корпусе (например, порядок `deleted_nodes` или текст предупреждения)
  → красный паритет + пины манифеста;
- **P3** — `import pathlib` (или `re`) в `domain/` → красный AST-тест; помни, что `lint_arch` ловит
  только `os/pathlib/socket/subprocess`, `re` — только AST-тест модуля.

Дополнительно предъявить: «клиентские пробы» через `build_agent`/`call` (read-only: sha всех файлов
проекта до/после), неизменность принятых файлов из §0, `__pycache__` = 0, отсутствие `.gd.uid`
в новых корпусах (Godot их создаёт при живом импорте — удалять по точному списку, ровно сгенерированные).

## §6 Стоп-условия

Остановиться и доложить, если: расходится любой из принятых файлов §0; старый плагин получил diff
или потерял две `??`; `gen_contract` не даёт 17 или падает; `snapshot_diff` не 345+/0; `lint_arch`/
`check_limits` дают нарушения; `security_audit` не ok; `selfcheck` любой механики не ok; сумма тестов
не равна `--collect-only`; появился новый live-тест вместо существующих 3 (живой прогон не расширяем);
паритет недостижим и хочется «улучшить» контракт; в план просочились `absolute`/`scene_res` или
не-Base64 байты; в `domain/` появились IO/`re`; инструмент пришлось назвать иначе, чем в §1;
понадобилось тронуть `editing.scene_ops`/мост/`agent_scene_executor.gd`.

## §7 Что проверит аудитор (не чтением отчёта, а своими прогонами)

1. Свои `pytest` non-live (`--junitxml`, дробя по 30 с), `--collect-only` (сумма = число тестов),
   `tests/py/live` (осталось 3), `tests/py/formats`.
2. `selfcheck` обеих механик, `gen_contract --check` (17), `snapshot_diff`, `lint_arch`, `check_limits`,
   `security_audit` — своими руками.
3. **Пересъёмка обоих корпусов с эталона независимым скриптом** (не твоим одноразовым): полный словарь,
   Base64, diff, порядок `files`/`deleted_nodes`/`warnings`, буквальные тексты отказов.
4. **Синтетический дифференциал** на сценах, которых нет в корпусе: поддерево с 3 уровнями,
   `new_parent` внутрь другой ветки (пути `../`), `%Unique` в дорожке, скрипт на корне и на наследнике,
   BOM/CRLF, удаление с `cleanup_code=true/false`.
5. Мутации M1–M9 и подложки P1–P3 — по одной, байтовое восстановление, мои собственные (твои
   результаты — только ориентир). Жду, что M1 (кавычки) и M6 (переводы строк) краснеют
   **на твоих же тестах**, иначе тесты не про то.
6. Чтение кода: лимиты R-06, отсутствие IO/`re` в `domain/`, единственный экземпляр логики
   (`rel_path_between`, `diff_preview`, `node_paths`, `tscn`-операции), Base64-проекция, `effect=read`.
7. Байтовая неизменность принятых файлов §0 и старого плагина (две `??`, пустой diff),
   `__pycache__` 0, отсутствие `.gd.uid`-мусора, `# verb:` не добавлялись, `editor_verbs.json` не менялся.

Этап 7 ставится только при зелёном selfcheck + живом прогоне + отсутствии подложек. Иначе — замечания
с точным воспроизведением (команда + файл:строка + красный тест) и разбор, что именно «доказательство
не с того файла».

## §8 Финальный прогон и записи

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONIOENCODING='utf-8'
python -B tools/selfcheck.py scene_model.node_reparent
python -B tools/selfcheck.py scene_model.node_delete
python -B -m pytest python/modules tests/py --ignore=tests/py/live -q -p no:cacheprovider
python -B -m pytest python/modules tests/py --ignore=tests/py/live --collect-only -q -p no:cacheprovider
python -B -m pytest tests/py/live -q -p no:cacheprovider          # дробить по 30 с
python -B tools/gen_contract.py --check
python -B tools/snapshot_diff.py
python -B tools/lint_arch.py; python -B tools/check_limits.py; python -B tools/security_audit.py
```

Записи: оба листа — статус «этап 7 — ported, готово к независимому аудиту; принятие не заявлено»
(шапку «принято» пишет **только аудитор**); строки 40/41 в `docs/PROGRESS.md` («C.7 ported…»,
следующее действие — независимый аудит C.7); `docs/parity.md` строки 35/36; `docs/WORKLOG.md` —
новая сессия с числами, хешами, таблицей мутаций и честной строкой о том, что осталось непроверенным;
`docs/porting/README.md` — статус промпта. `_audit-handoff.md` не трогать.


