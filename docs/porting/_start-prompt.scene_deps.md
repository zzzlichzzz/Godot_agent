# Срез C.5 — две механики: `scene_model.connections` и `scene_model.scene_deps`

Ты продолжаешь перенос Godot-агента в новый проект `D:\vajno\Godot\agent-rebuild\addons\godot_agent`.
Старый плагин `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent` — **только чтение**
(`python -B`, дампы в `%TEMP%`, два чужих лога `python/_ref2.log` и `python/godot_tools/_excl.log` не удалять).
До тебя приняты аудитом: часть C (`python/formats/tscn.py`, `structure`/`fields`/`patch`/`rows`),
C.2 (`verification.gd_lint`), C.3 (`scene_model.tree`, инструмент `scene`), C.4
(`scene_model.node_info`, инструмент `node`). Этот срез — **две read-only механики сразу**, потому что у них
один эталонный файл и один разбор: связи сигналов (`connections`) и анализ зависимостей
(`scene_deps`). Логика переноса — по правилам `RULES.md` (R-04 один экземпляр логики, R-07 эталон только
вызовом, R-08 без улучшений, R-16 старые тесты не копируем, R-17/R-19 лист механики до кода, R-22
приёмка по инструменту, а не по тексту отчёта).

## 0. База на старте (мой замер, аудит 2026-10-29, сессия 52)

Проверь и запиши свои числа — мои только для сверки.

```powershell
cd 'D:\vajno\Godot\agent-rebuild\addons\godot_agent'
$env:PYTHONDONTWRITEBYTECODE=1
python -m pytest python/modules tests/py --ignore=tests/py/live -q -p no:cacheprovider   # 1056 passed
python -m pytest tests/py/live -v                                                        # 3 passed (~30 s)
python -m pytest python/modules tests/py --ignore=tests/py/live --collect-only -q         # 53 файла, сумма 1056
python -m pytest tests/py/formats -q                                                      # 135 passed
python tools/gen_contract.py --check      # {"status":"ok","detail":"артефактов 12, расхождений нет"}
python tools/snapshot_diff.py             # {"status":"ok","detail":"кейсов 244, расхождений нет"}
python tools/lint_arch.py                 # {"status":"ok","detail":"файлов 460, нарушений нет"}
python tools/check_limits.py              # {"status":"ok","detail":"файлов 460, нарушений 0"}
python tools/security_audit.py            # ok
python tools/selfcheck.py scene_model.node_info   # ok: unit 247, corpus 65
```

| Якорь | Значение |
|---|---|
| Файлов в плагине | **1199**; этот промпт добавляет один → у тебя на старте **1200** (запиши своё число) |
| Правил `RULES.md` | 22; листов механик 13 → после среза **15**; промптов 25 |
| Заморожено | `python/kernel/schema.py 629FCE54E6FE`, `tools/lint_arch.py 1FAD8E7470D5`, `tools/gen_contract.py FA7E6E91C872`, `tools/security_audit.py 2CF0D7F6B1AF` |
| Мост | `contract/editor_verbs.json CDAF8D23A6BF`, `verbs_version 3`, 6 примитивов |
| Формат сцены | `python/formats/tscn.py` **F535566EF2FE**, 9550 B, 228 строк (`structure`,`fields`,`patch`,`rows`) |
| Принятые механики | `scene_model.tree/domain/core.py DB7164485858`, `scene_model.node_info/domain/core.py C974A7BD50A3` |
| Эталон | `godot_tools/scene_deps.py` **dbd502afeca7…** 19866 B; `godot_tools/node_refactor.py` 2d708a38… 46881 B |
| Гигиена | `__pycache__` 0, `.pytest_cache` 0, `*.bak/tmp/orig` 0, `zz_*` 0 |
| Движок | `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe` |
| Git | в `agent-rebuild` его нет намеренно — не инициализировать |

## 1. Границы среза

**В срезе:**
- два листа механик (R-19), каждый на этапе 1 **до** первой строки кода:
  `docs/porting/scene_model.connections.md` и `docs/porting/scene_model.scene_deps.md`;
- два модуля: `python/modules/scene_model/connections/` и `python/modules/scene_model/scene_deps/`
  (сейчас там заглушки 3–8 строк), `ModuleSpec.corpus="corpus"` у обоих;
- два корпуса: `fixtures/corpus/scene_model/connections/` и `fixtures/corpus/scene_model/scene_deps/`
  (форма `{id, tool, fixture, note, args, expect}` + `manifest.json`, как в C.3/C.4);
- две карточки: `contract/capabilities/connections.json` и `contract/capabilities/scene_deps.json`
  → `gen_contract --check` даёт **14** артефактов;
- строки `docs/parity.md` для `connections`/`scene_deps` переводятся в `ported` **только** после
  зелёного `selfcheck` обеих механик;
- записи: `docs/WORKLOG.md` (сессия), `docs/PROGRESS.md` (две строки), листы механик.
- при необходимости — **минимальное** расширение `python/formats/tscn.py` и/или `python/formats/gdscript/`
  с parity-корпусом и мутациями (см. §2.4); любое такое расширение назвать в листах.

**Не в срезе:** любые другие механики (`node_rename`/`node_reparent`/`node_delete`,
`verification.tscn_lint`, `editing.*`, `engine_kb.*`), запись на диск и undo, мост (`# verb:`, `editor/**`),
`runtime/**`, `contract/**` кроме двух новых карточек, четыре замороженных инструмента и `schema.py`,
принятые корпуса (`fixtures/parity/tscn/`, `fixtures/corpus/scene_model/tree|node_info`),
`docs/tests-map.md` без прогона R-09/R-10.

**Наследство C.3/C.4 (не твоё, но не потеряй):** `patch` в `tscn.py` намеренно не диагностирует
перекрывающиеся правки — это требование среза `node_rename`; корпус `fixtures/parity/tscn/` (16 файлов)
закрыт; карточка узла и её `parent_path`/`children` — **наша** проекция поверх эталона, такие места
называются вслух (R-08).

## 2. Контракт и раскладка

### 2.1 Якоря эталона (проверены мной в старом коде, файл `python/godot_tools/scene_deps.py`)

| Якорь | Что там |
|---|---|
| `:68` | `_ATTR_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|[^\s\]]+)')` — уже перенесён в `formats/tscn.py:13`, второй копии не делать |
| `:73` | `to_snake(name)` — имя узла/сигнала → snake_case |
| `:102` / `:111` | `_parse_attrs` (снимает кавычки) / `_attr_id` (`ExtResource(…)` → голый id) |
| `:120` | `parse_scene(text)` → `(ext, nodes, connections)`; узлы несут `path`, `script_id`, `instance_id`; связи — `{signal, from, to, method}` |
| `:175` | `extract_handlers(script_text)` — обработчики `.gd` по `_HANDLER_RE` (`^(?:static\s+)?func\s+(_on_\w+)\s*\(`) и `_CUSTOM_SIGNAL_RE` |
| `:271` | `analyze_scene_action(scene_text, scene_res_path, project_root)` — что сломается в сцене, если тронуть узел/файл |
| `:362` | `analyze_script_action(script_text, script_res_path, project_root)` — то же для скрипта |
| `_MAX_FILE_BYTES` | 512 KiB — лимит читаемого файла; `_SKIP_DIRS` — что не обходим |
| старый вход | `main.py:1904` (`analyze_scene_action`), `main.py:1930` (`analyze_script_action`) — оттуда снимай фактические аргументы и форму ответа |

Порядок работы с эталоном: **сначала** прочитать эти функции и записать в листы их настоящие сигнатуры и
форму возврата, **потом** объявлять ToolSpec. Ничего не додумывать: если эталон отдаёт список строк —
переносим список строк, если словарь — словарь (R-08).

### 2.2 Инструменты

- `connections` — «связи сигналов сцены»: вход `{path}` (или `{path, node}` — реши по эталону и запиши
  решение), выход — данные о связях (`from`, `to`, `signal`, `method`) плюс то, что эталон реально отдаёт;
  `effects="read"`, `idempotent=True`, `cost="cheap"`; отказы `invalid_input`/`not_found`/`denied`.
- `scene_deps` — «зависимости сцены/скрипта»: вход `{path}` (и, если эталон требует, `action`/`node`);
  выход — отчёт о зависимостях в форме эталона; `effects="read"`, `idempotent=True`, `cost="heavy"`
  (обходит файлы проекта), лимиты объявить в `ToolSpec.limits`.
- Оба инструмента обслуживают **одну** область, но это **две** механики: два листа, две строки в
  `PROGRESS`, две карточки в `contract/capabilities/`.

### 2.3 Раскладка и лимиты

`app.py` ≤ 80 строк (только оркестрация: нормализация пути, `PathPolicy`, порт `fs`, вызов домена,
маппинг исключений в типизированные отказы), `tools.py` ≤ 150, `domain/` — без `os`/`pathlib`/`io`/
`socket`/`subprocess`/`re` (последнее проверяет AST-тест модуля, как в C.2/C.4), файл ≤ 400 строк,
порт `RawReader` в `ports.py` (`typing.Protocol`, `@runtime_checkable`), привязка — в
`runtime/bootstrap.py` (его не переписывать), лимит чтения — `kernel/limits.READ_TEXT_MAX_BYTES`;
обход проекта для `scene_deps` — через **порт**, объявленный в `ports.py` (например `ProjectFiles`:
список `.gd`/`.tscn` + чтение), а не через `os.walk` в домене: домен получает данные, IO живёт в
`substrate`.

### 2.4 Разбор — только через `formats/`

- `.tscn` разбирается **только** `python/formats/tscn.py` (`structure`/`fields`/`rows`). Если для
  `scene_deps` нужен факт, которого нет — добавь минимальную функцию в `tscn.py`, с parity-тестом и
  мутацией; запись в листе обязательна. Искать `ExtResource(`/`[node ` по проекту запрещено.
- `.gd` разбирается **только** `python/formats/gdscript/` (публичный API `tokenize`, `parse`,
  `line_indents`, `script_parent`, `exact_string_value`). Если `extract_handlers` нужен, реализуй его
  **в `formats/gdscript/`**, а не в домене механики: иначе появится второй разбор скриптов.
  Сравни свой `handlers` с эталонным `extract_handlers` на всех `.gd` из `editor/**`,
  `fixtures/projects/**` и корпуса — расхождений быть не должно.

## 3. Шаги

1. **Листы** `docs/porting/scene_model.connections.md` и `docs/porting/scene_model.scene_deps.md` по
   `_template.md`: цель, старый код (таблица `файл:строка` → что делает → как делим), старые тесты
   (`docs/tests-map.md:56-130` относится к `node_rename` — не менять), корпус, спецификация, решения,
   ход работы, проверки, следующее действие, блокеры. Статус — «этап 1».
2. **Корпус до кода**, отдельно на каждую механику: ≥14 кейсов на `connections` (нет связей, одна,
   несколько, `from="."`, `to="."`, `<root>`-подстановка, дубли сигналов, связь на отсутствующий метод,
   связь с `flags=`, экранированные кавычки, CRLF, BOM, `.tres`, отсутствующий файл, не-сцена) и ≥14 на
   `scene_deps` (сцена без скриптов, скрипт с обработчиками, кастомные сигналы, `_on_` вне сцены,
   инстанс сцены, зависимость по `ExtResource`, цикл, битый скрипт, `.gd` вне проекта, лимит 512 KiB,
   пустой файл, `.tres`, отсутствующий файл, не-сцена). Ожидания снимаются **одним** одноразовым
   скриптом `python -B` через настоящие старые функции (`sys.path` = `godot_tools`, `python/parsers`,
   `python`), скрипт после съёмки удаляется; `manifest.json` хранит дату, коммит `ba0535d4…`, sha256 и
   размеры эталонных файлов и каждого входа, а также `copied_source` для скопированных сцен.
3. **Тесты до реализации**, red на заглушке: записать «N тестов, M падений, exit 1» в листы.
   Обязательны: parity карточек, parity текстов отказов, AST-тест домена (IO/`re`/второй разбор),
   пиннинг манифеста, «данные не команды» (`open`/`eval`/`exec` запрещены).
4. **Реализация**: `formats` (если нужно) → `domain` → `app.py` → `tools.py` → `module.py` → `ports.py`.
5. `python tools/gen_contract.py` (генерация, не `--check`) → две новые карточки → `--check` = **14**.
6. `python tools/selfcheck.py scene_model.connections` и `... scene_model.scene_deps` — оба ok.
7. Записи: `WORKLOG`, `PROGRESS` (две строки), `parity.md` (две строки), листы (этап 7 +
   «Следующее действие»).

## 4. Решения, которые примешь сам

- Имена инструментов (`connections`, `scene_deps`) и их аргументы — по `docs/parity.md:33-34` и по тому,
  что реально требует эталон; если решишь иначе, обоснование в лист.
- Где живёт «сборка отчёта зависимостей»: домен получает разобранные данные и сам обходит граф, IO — порт.
- Форма отчёта `scene_deps`: буквально эталонная (список строк/словарь) или структурная проекция —
  выбери и **назови вслух**; если проецируешь, в лист и в манифест корпуса.
- `to_snake`/`_parse_attrs`/`_attr_id`: что уже есть в `formats/tscn.py`, не дублировать; чего нет —
  добавить в `formats`, а не в домен.
- Поведение на битом входе: тот же тип отказа и тот же текст, что у эталона (R-08), без «улучшений».
- `truncated`/лимиты: если обрезаешь отчёт — это отдельное поле и тест, что обрезка реальная, а не
  насыщение.

## 5. Чем доказывается (мутации и подложки)

Каждая работа — на сдаваемом файле, с байтовым бэкапом (`shutil.copyfile` в `%TEMP%`), sha256 до и
после, один прогон на мутацию, восстановление с печатью `identical_to_backup=True`, EOL не менять.
Мутация, которая не краснит ни одного теста, — незакрытое требование, а не «норма».

- **M1**: `connections` — выкинуть подстановку `<root>` (или то, что эталон делает для `.`/пустого).
- **M2**: `connections` — не фильтровать связи, у которых метод не найден.
- **M3**: `scene_deps` — обойти проект только по корню, не заходя в подпапки.
- **M4**: `scene_deps` — взять `handlers` из домена (локальная регулярка) вместо `formats/gdscript/`.
- **P1**: лишнее поле в `ToolSpec.result`, которого нет в карточке → `gen_contract --check` обязан упасть
  с `расходится: connections.json` / `scene_deps.json`.
- **P2**: испортить одно ожидание в корпусе → parity-тест и пиннинг манифеста красные.
- **P3**: `import pathlib` (или `import re`) в `domain/` → AST-тест модуля красный; `lint_arch` поймает
  только `os/pathlib/socket/subprocess` — про `re` помнить (в C.4 так и было).

## 6. Стоп-условия

- Старый плагин не изменён: `git status --porcelain` = ровно два `??` (`python/_ref2.log`,
  `python/godot_tools/_excl.log`), `git diff --stat` пуст.
- `gen_contract --check` = **14** артефактов; `snapshot_diff` = **244 / 0** (новые корпуса в snapshot не
  входят, если ты не добавил их в инструмент — тогда число вырастет, и это надо объяснить в отчёте).
- `lint_arch` / `check_limits` — 0 нарушений; `security_audit` — ok; `selfcheck` трёх ранее принятых
  механик (`scene_model.tree`, `scene_model.node_info`, `verification.gd_lint`) остаётся зелёным.
- Сумма тестов совпадает с `--collect-only`; живых тестов ровно **3**; два чужих лога и `.uid` не трогать.
- Две мутации одновременно — запрещено; `PYTHONDONTWRITEBYTECODE=1` в каждой команде; JSON только через
  `--args-file`; команда дольше 30 с дробится, вывод — в файл; stderr — тоже в файл.
- Git в `agent-rebuild` не инициализировать. `# verb:`/`editor/**`/`runtime/**` не трогать,
  `verbs_version` остаётся 3.

## 7. Что проверит аудитор

1. Свои прогоны: non-live, live, `--collect-only`, `gen_contract --check`, `snapshot_diff`,
   `lint_arch`, `check_limits`, `security_audit`, `selfcheck` обеих новых механик.
2. Проверка ожиданий: переснимет корпус **своими** скриптами поверх настоящего старого кода и сравнит
   через `app.call` (не через домен — гейты живут в `app.py`).
3. Свои мутации и подложки с байтовым бэкапом и sha256, включая «подложку в контракт».
4. Чтение кода: лимиты 80/150/400, отсутствие IO и `re` в `domain/`, единственный разбор `.tscn`/`.gd`
   (поиск `ext_resource`/`\[node ` и регулярки обработчиков по `python/**` — только в `formats/`).
5. Гигиена: `__pycache__` 0, `.pytest_cache` 0, `*.bak/tmp/orig` 0, `zz_*` 0; старый плагин побайтово тот
   же; замороженные хеши и `tscn.py` не изменились без записи в листе.
6. Вердикт — по инструменту, а не по твоему отчёту (R-22). Шапку «выполнено/принято» ставит аудитор.

## 8. Финальный прогон и записи

```powershell
$env:PYTHONDONTWRITEBYTECODE=1
python -m pytest python/modules tests/py --ignore=tests/py/live -q -p no:cacheprovider
python -m pytest tests/py/live -v
python -m pytest python/modules tests/py --ignore=tests/py/live --collect-only -q
python tools/gen_contract.py --check
python tools/snapshot_diff.py
python tools/lint_arch.py
python tools/check_limits.py
python tools/security_audit.py
python tools/selfcheck.py scene_model.connections
python tools/selfcheck.py scene_model.scene_deps
```

Записи обязательны: сессия в `docs/WORKLOG.md` с числами и командами; две строки в `docs/PROGRESS.md`
(этап 7, числа, «Следующее действие»); `docs/parity.md` — два статуса; оба листа механик — этап 7 и
краткие доказательства. `docs/porting/README.md` и `_audit-handoff.md` правит **только аудитор**.


