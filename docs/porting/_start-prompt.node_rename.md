# C.6 — `scene_model.node_rename`: предпросмотр переименования узла (`.tscn` + скрипты)

**Кому:** портер. Срез один: механика `scene_model.node_rename` (инструмент `node_rename_preview`).
**Ты не аудитор:** этап не ставишь, шапку «выполнено» не пишешь; сдаёшь лист, записи и доказательства.

## §0 База (снято аудитом сессия 54, 2026-10-29 — не пересчитывай «на глаз»)

- pytest non-live: **1519 passed**, `--collect-only` → 1519 (62 файла), совпадение по ID обязательно.
- `tests/py/live` → **3 passed** (3.17 / 17.10 / 9.26 с; Godot `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`).
- `tools/gen_contract.py --check` → **14** артефактов ok; `tools/snapshot_diff.py` → **309** кейсов, 0 расхождений;
  `tools/lint_arch.py` → 467 файлов, 0 нарушений; `tools/check_limits.py` → 467 файлов, 0 предупреждений;
  `tools/security_audit.py` → ok. `selfcheck scene_model.connections` 108/25 ok, `scene_model.scene_deps` 176/40 ok.
- Файлов в дереве: **1429**, `__pycache__` 0, `.pytest_cache` 0, `.bak/.tmp/.orig` 0, `zz_*` 0.
- Незыблемое (сверять, а не помнить): `python/kernel/schema.py 629FCE54E6FE`, `tools/lint_arch.py 1FAD8E7470D5`,
  `tools/gen_contract.py FA7E6E91C872`, `tools/security_audit.py 2CF0D7F6B1AF`, `contract/editor_verbs.json CDAF8D23A6BF`
  (6 примитивов, `verbs_version: 3`; `protocol: 1` — другая константа).
- Уже принятые срезы: `formats/tscn.py AB2E8D9D7B60` (270 строк: `structure`, `fields`, `patch`, `rows`, `to_snake:235`,
  `method_referenced:263`, `script_referenced:268`, `__all__` не расширялся), `formats/gdscript/` (`handlers`,
  `custom_signals`, `method_connected` в `handler_facts.py`, 27 строк), `scene_model.node_info core C974A7BD50A3`,
  `scene_model.scene_deps core 4D192DD6FDAD`, `scene_model.connections core 4F7366C418DD`, карточки
  `capabilities/connections.json 5DB30F983712`, `scene_deps.json 848F08C01395`.
- Промптов в `docs/porting/` 26, листов механик 17 после твоего нового листа, правил 22. Git в `agent-rebuild` нет намеренно.

## §1 Границы среза

В срезе:
1. Лист `docs/porting/scene_model.node_rename.md` — **первым**, по шаблону `_template.md`, статус этап 1.
2. Модуль `python/modules/scene_model/node_rename/` (скелет уже создан: `module.py`, `app.py`, `tools.py`,
   `domain/core.py`, `tests/test_core.py`; общий код переиспользования — `python/modules/scene_model/shared/node_path.py`, R-02).
3. Инструмент **`node_rename_preview`** (эффект `read`, в проект не пишет): вход и выход — как в §2, план правок
   возвращается как данные, применение — отдельный срез.
4. Корпус `fixtures/corpus/scene_model/node_rename/` (≥14 кейсов, ожидания сняты с эталона `node_refactor.py`,
   `manifest.json` с sha256 входов), capability `contract/capabilities/node_rename_preview.json` → `gen_contract` 14→15.
5. Строка паритета `node_rename_preview` в `docs/parity.md` (статус: ported до аудита) и запись в `docs/PROGRESS.md`.

Вне среза: `node_reparent_preview`, `node_delete_preview` (свои срезы), запись на диск и undo в редакторе
(`apply_prepared_node_refactor:969`), `agent_scene_executor.gd`, мост `editor/*`, `verification.tscn_lint`.
Расширять `formats/tscn.py` можно только append-only и только если без этого нельзя: правка заголовка, `parent=`,
`[connection]` и `NodePath` анимаций делается через `patch(text, edits)` по смещениям, а не новой реконструкцией текста.

## §2 Контракт и раскладка (якоря эталона — `python/godot_tools/node_refactor.py`, 1095 строк)

Инструмент `node_rename_preview`, вход `{path, node, new_name, update_scripts=true, scripts_only=false, previous_name=""}`,
выход — план: `{action:"rename_node", scene, old_name, new_name, old_path, new_path, target_node_path, files[], reference_count,
affected_paths[], scripts_only, previous_name}` (эталон `:525-541`), где элемент `files[]` —
`{action:"patch_file", path, before_hash(sha256), before_bytes, after_bytes, diff, occurrences}` (`:394-401`, `:512-519`).

Правила, которые обязаны совпасть с эталоном:
- нормализация имени `:66 _normalize_node_name`, поиск узла `:185 find_node_in_scene` (как в C.4), `seen_name` из `previous_name` `:255`;
- **коллизия имён среди соседей** — отказ; сам целевой узел коллизией не считается (нужно для обратного переименования при `scripts_only`) `:268-279`;
- `new_path` по `:280`, `is_unique` `:288`;
- `.tscn`: заголовок `[node name="Old"` `:297-308`; `parent="…"` у детей `:310-333`; `[connection from/to]` `:334-355`;
  `tracks/N/path = NodePath("…")` `:356-378`; применение замен в обратном порядке смещений `:379-383`; BOM сохраняется `:391`;
- скрипты, прикреплённые к узлам сцены `:408-466`: `$Путь`/`$"Путь"`/`get_node("…")`/`get_node_or_null`/`has_node` `:467-487`,
  `find_child("OldName")` `:481-487`; после правки — `gd_lint.lint_gdscript` и **отказ** при синтаксической ошибке `:490-497`;
- `reference_count`: в `scripts_only` из счёта вычитаются ссылки `.tscn`, потому что сцена на диске не меняется `:404-406`, `:523`;
- `scripts_only=True` — `files[]` только скрипты, `.tscn` не переписывается; `previous_name` — имя, под которым узел известен
  редактору (см. docstring `:225-243`), замены в скриптах считаются от него, а `.tscn` остаётся как на диске.

Раскладка (R-06/R-11): `domain/` без `os`/`pathlib`/`io`/`socket`/`subprocess`/`re`-по-файлам; чтение — через порт
(`RawReader`/`ProjectFiles`, как в `scene_deps/ports.py`), разбор `.tscn` — только `python/formats/tscn.py`,
`.gd` — только `python/formats/gdscript/`; `app.py` ≤80 строк, `tools.py` ≤150, файл ≤400; один экземпляр логики
(никаких копий `parse_tscn_structure`/`find_node_in_scene` — `shared/node_path.py` или `formats/`).


## §3 Шаги

1. Лист `docs/porting/scene_model.node_rename.md`: цель, старый код (`node_refactor.prepare_node_rename:225-541`,
   `_normalize_node_name:66`, `find_node_in_scene:185`, `_read_file_text:40`, `apply_prepared_node_refactor:969` — вне среза),
   старые тесты (`tests/test_node_refactor.py` — прочитать, но не переписывать), корпус, спецификация, решения, ход, проверки.
2. Корпус: `fixtures/corpus/scene_model/node_rename/` ≥14 кейсов с фикстурными проектами, ожидания снимаются
   **одноразовым** `python -B` скриптом из эталона (`sys.path` = `…\godot_agent\python\godot_tools`,
   `…\python\parsers`, `…\python`), результат — JSON в корпус + `manifest.json` (sha256/размеры входов).
   Обязательные кейсы: простое переименование; дети (`parent=`); connections `from`/`to`; анимационные `NodePath`;
   `$Узел` и `$Узел/Ребёнок`; `get_node("…")`/`get_node_or_null`/`has_node`; `find_child`; `%Unique`;
   `scripts_only` (сцена не меняется, `reference_count` без ссылок сцены); `previous_name`; коллизия имён (отказ);
   синтаксическая ошибка после правки (отказ); BOM; CRLF; отсутствующий/чужой путь; `.tres` (отказ).
3. Тесты **до кода**, красные: паритет с корпусом (полный dict + порядок `files`), отказы дословно (тип + текст),
   `domain` без IO (AST), `manifest`-пины, «данные, а не команды», лимиты `MAX_*`.
4. Domain: чистые функции над текстами (`prepare_rename(...) -> dict`), без файловой системы; `app.py` — чтение через порт,
   типизированные ошибки `invalid_input`/`denied`/`not_found`, гейт `.tscn/.scn` (как в `tree`/`node_info`), лимит чтения.
5. `tools.py`: `ToolSpec("node_rename_preview", effects="read", idempotent=True, cost="cheap")`,
   строгая схема входа/выхода (никаких полей «на будущее»).
6. `gen_contract` 14→15; `selfcheck scene_model.node_rename` зелёный; `snapshot_diff` + новые кейсы, 0 расхождений.
7. Записи: лист (ход, проверки), `docs/PROGRESS.md`, `docs/parity.md`, `docs/WORKLOG.md` (сессия), `docs/porting/README.md`.

## §4 Решения, которые нужно принять до кода (и записать в лист)

- Где собираются `before_bytes`/`after_bytes`: в `domain` (текст) или `app.py` (кодирование/BOM); в эталоне это `:391`, `:506`.
  Bytes + BOM — ближе к IO: выбирай по R-11 и зафиксируй решение в листе.
- Diff: эталон зовёт `build_diff_preview` (`:384`, `:508`); если такая функция в проекте уже есть — переиспользовать,
  иначе diff как данные, но ключи обязаны совпасть с эталоном.
- `reference_count` — одна функция на оба режима, чтобы `scripts_only` не «обещал» правки сцены (`:404-406`, `:523`).
- Линт после правки скрипта — переиспользовать домен `verification.gd_lint` (не копировать регексы).
- Отказы — дословно из `NodeRefactorError` (коллизия; «После обновления узла в скрипте … обнаружена синтаксическая ошибка»).

## §5 Доказательства, которые обязан предъявить (по одному за прогон, файлы восстанавливать побайтово)

Мутации на сдаваемом файле (байтовый бэкап → правка → красный тест → восстановление + сверка sha256):
- **M1** убрать обработку `parent=` у детей (`:310-333`) — красные кейсы с детьми;
- **M2** применить замены в прямом порядке вместо обратного (`:379`) — красные кейсы с несколькими правками в одном файле;
- **M3** в `reference_count` не вычитать ссылки сцены при `scripts_only` (`:523`) — красный кейс `scripts_only`;
- **M4** убрать отказ по синтаксической ошибке после правки скрипта (`:490-497`) — красный кейс «битый скрипт после правки»;
- **M5** не исключать целевой узел из проверки коллизии (`:268-279`) — красный кейс обратного переименования.
Подложки:
- **P1** лишнее поле в result-схеме `ToolSpec`, не объявленное в карточке → `gen_contract --check` fail;
- **P2** испорченное ожидание в корпусе (лишняя строка/байт) → паритет красный;
- **P3** `import pathlib` (или `re`) в `domain/core.py` → `lint_arch`/AST-тест красные. Помни: `lint_arch` ловит только
  `os/pathlib/socket/subprocess`; `re` ловится только AST-тестом домена — проверь оба.
Две мутации одновременно — запрещено. Каждая — отдельный прогон и отдельная строка в листе
(файл, что менял, кто покраснел, sha256 до/после). Если мутация эквивалентна (тесты зелёные) — не «подкручивай»
тесты, а напиши это в лист честно и подбери другую.

## §6 Стоп-условия

- старый плагин (`D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent`) не изменён: `git status --porcelain`
  даёт ровно два `??`-лога (`_ref2.log`, `_excl.log`), diff пуст;
- `gen_contract --check` → 15 артефактов, 0 расхождений; `snapshot_diff` → 309+новые, 0;
- `lint_arch` → 0 нарушений, `check_limits` → 0 предупреждений, `security_audit` → ok;
- `selfcheck scene_model.node_rename` зелёный (module/layers/limits/contract/security/unit/corpus);
- сумма тестов по файлам = `--collect-only`, наборы ID совпадают; live остаются **3** (новых живых нет);
- `python/formats/*` не переписан: `structure`/`fields`/`patch`/`rows` и их тесты зелёные;
- файлов 1429 + ровно твои новые; `__pycache__` 0, `.pytest_cache` 0, `.bak/.tmp/.orig` 0, `zz_*` 0;
- инструмент ничего не пишет на диск (эффект `read`); мост не тронут: `contract/editor_verbs.json` без изменений,
  `verbs_version` остаётся 3; никаких `# verb:`;
- `PYTHONDONTWRITEBYTECODE=1` в каждой команде; JSON только через `--args-file`; команды >30 с — дробить;
  stderr — в файл; git в `agent-rebuild` не инициализировать.

## §7 Что проверит аудитор

1. Свои прогоны: non-live + live + `--collect-only`, `snapshot_diff`, `gen_contract --check`, `selfcheck` новой механики,
   `lint_arch`/`check_limits`/`security_audit`.
2. Независимое переснятие корпуса с эталона (свой одноразовый скрипт, не твой) и дифференциал «эталон против порта»
   на всех фикстурах, включая отказы.
3. Подложки P1–P3 и мутации M1–M5 — по одной, с байтовым восстановлением и сверкой sha256.
4. Чтение кода: лимиты R-06, отсутствие IO в `domain/`, единственный экземпляр разбора, отсутствие «улучшений» контракта.
5. Байтовая неизменность принятых файлов (`schema`, `lint_arch`, `gen_contract`, `security_audit`, `editor_verbs`,
   `formats/*`, `scene_model.{tree,node_info,connections,scene_deps}`) и старого плагина; `__pycache__` = 0.
6. Этап 7 — только при зелёном selfcheck + живом прогоне + отсутствии подложек; иначе замечания с точным
   воспроизведением и промпт на исправление.

## §8 Финальный прогон и записи

```powershell
$env:PYTHONDONTWRITEBYTECODE=1; $env:PYTHONIOENCODING='utf-8'
# non-live дробить: Start-Process python -B -m pytest <файл> --junitxml=<tmp> -q -p no:cacheprovider
python -B -m pytest python/modules tests/py --ignore=tests/py/live --collect-only -q
python -B -m pytest tests/py/live -q -p no:cacheprovider
python -B tools/gen_contract.py --check
python -B tools/snapshot_diff.py
python -B tools/lint_arch.py; python -B tools/check_limits.py; python -B tools/security_audit.py
python -B tools/selfcheck.py scene_model.node_rename
```

Записи к сдаче: лист механики (статус «этап 7 — ported, готов к независимому аудиту», **без** «принято»),
`docs/PROGRESS.md` (строка механики + «следующее»), `docs/parity.md` (строка `node_rename_preview`),
`docs/WORKLOG.md` (сессия: числа, мутации, честные отклонения), `docs/porting/README.md` (пометка «выполнен»).
Шапку «выполнено/принято» и этап ставит аудитор — не ты.

- `%Unique`, `find_child`, анимации — только в объёме эталона (`:467-487`, `:356-378`); «улучшений» не добавлять.