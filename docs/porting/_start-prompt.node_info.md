# Срез C.4 — механика `scene_model.node_info` (инструмент `node`)

Ты портируешь Godot-агент из старого плагина в новый проект **по одному срезу**, не «улучшая»
эталон. Новый проект: `D:\vajno\Godot\agent-rebuild\addons\godot_agent`. Старый плагин —
`D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent` — **только читаешь** (`python -B`,
дампы в `%TEMP%`), два чужих лога (`python/_ref2.log`, `python/godot_tools/_excl.log`) не трогаешь.
Готовы и приняты аудитом: `formats/tscn.py` (часть C: `structure`/`fields`/`patch`/`rows`, 228 строк),
`verification.gd_lint` (C.2), `scene_model.tree` (C.3). Этот срез — второй шаг `scene_model`:
**только чтение**, без записи на диск, без моста редактора, без `# verb:`.

## 0. База на старте (мой замер, аудит 2026-10-29, сессия 50)

```powershell
$env:PYTHONDONTWRITEBYTECODE=1
python -m pytest python/modules tests/py --ignore=tests/py/live -q -p no:cacheprovider   # 809 passed
python -m pytest tests/py/live -q -p no:cacheprovider                                   # 3 passed (~31 с)
python -m pytest tests/py/formats -q -p no:cacheprovider                                # 135 passed
python tools/gen_contract.py --check        # артефактов 11
python tools/snapshot_diff.py               # кейсов 179, расхождений нет
python tools/lint_arch.py                   # файлов 458, нарушений нет
python tools/check_limits.py                # файлов 458, нарушений 0
python tools/security_audit.py              # ok
python tools/selfcheck.py scene_model.tree  # unit 128, corpus 40, вердикт ok
```

| Якорь | Значение |
|---|---|
| Файлов в плагине | **1101** (этот промпт добавляет один: у тебя на старте **1102** — запиши своё число) |
| Правил `RULES.md` | 22; листов механик 11 (после среза — 12); промптов 24 |
| `python/kernel/schema.py` | `629FCE54E6FE…` — не менять |
| `tools/lint_arch.py` / `gen_contract.py` / `security_audit.py` | `1FAD8E7470D5…` / `FA7E6E91C872…` / `2CF0D7F6B1AF…` — не менять |
| `contract/editor_verbs.json` | `CDAF8D23A6BF…`, `verbs_version: 3` — не менять |
| `editor/bridge/verbs/scene/scene_executor.gd` | `B7AFF592B75D…` — не менять |
| `python/formats/tscn.py` | `F535566EF2FE…`, 9550 Б, 228 строк (`structure`, `fields`, `patch`, `rows`) |
| `python/modules/scene_model/tree/domain/core.py` | `DB7164485858…`, 2583 Б — образец стиля и порта |
| Гигиена | `__pycache__` 0, `.pytest_cache` 0, `*.bak/tmp/orig` 0, `zz_*` 0; Git в `agent-rebuild` нет |
| Движок | `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe` |

## 1. Границы среза

**В срезе:** лист механики `docs/porting/scene_model.node_info.md` (этап 1, **до первой строки кода**);
модуль `python/modules/scene_model/node_info/` (`domain/`, `app.py` ≤ 80, `tools.py` ≤ 150, `ports.py`,
`module.py`, `ModuleSpec.corpus="corpus"`); корпус `fixtures/corpus/scene_model/node_info/`;
новая карточка `contract/capabilities/node.json` (`gen_contract --check` 11 → **12**); тесты механики;
работа с `python/formats/tscn.py` — **только если без этого нельзя** (тогда parity + мутации + запись);
`docs/porting/README.md`, `PROGRESS.md`, `WORKLOG.md` — ты, `_audit-handoff.md` — аудитор.

**Не в срезе:** остальные `scene_model.*` (`node_rename`, `node_reparent`, `node_delete`,
`connections`, `scene_deps`), `verification.tscn_lint`, любые `editing.*`; запись на диск, undo,
`ResourceSaver`, `# verb:`; `editor/**`, `runtime/**`, `contract/**` кроме `node.json`;
четыре неизменяемых инструмента и `schema.py`; принятые корпуса (`fixtures/parity/tscn/`,
`fixtures/corpus/verification/gd_lint/`, `fixtures/corpus/scene_model/tree/`).

**Наследство C.3, не твоё:** гейт расширения в `tree/app.py` стоит после чтения (в эталоне — до);
домен `tree` нормализует одиночный `\r`, эталон нет. Это принято, **не исправляй**. `rows` в
`tscn.py` — единственный разбор сцены, второй не появляется.

## 2. Что переносится (контракт с якорями эталона)

Инструмент: **`node`**, `effects="read"`, `idempotent=True`, `cost="cheap"`.
Вход: `{path, node}` — `path` = `res://…tscn` или относительный путь сцены, `node` = спецификация узла.

Разрешение спецификации — literal `node_refactor.find_node_in_scene` (`node_refactor.py:185-225`),
порядок проверок сохранить:
1. `spec = node.strip().replace("\\", "/")` — нормализация до всего остального;
2. `%имя` → единственный узел с `unique_name is True` и `name == имя`; иначе отказ
   `Уникальный узел %%%s не найден в сцене`;
3. `spec in (".", "")` → узел с `parent is None`; иначе `Корневой узел сцены не найден`;
4. точное совпадение `n["path"] == spec`;
5. единственное совпадение по имени `n["name"] == spec`; при нескольких — отказ
   `Имя узла '%s' неоднозначно (%d совпадений). Укажите полный путь: %s` (пути через `", "`);
6. иначе `Узел '%s' не найден в сцене`.

Относительный путь между узлами — literal `_rel_path_between` (`node_refactor.py:163-183`):
он нужен карточке (`parent_path`, `children`), переносится вместе с правилами `..`-подъёма.

Карточка узла (данные, а не текст): `{name, type, parent, path, depth, script, instance,
unique_name, parent_path, children[]}` — `children` = пути прямых детей в порядке файла
(это то, что позже нужно `node_rename`, чтобы не пересчитывать дерево в GDScript).
`depth`/`path` считать **теми же правилами, что `scene_model.tree`** (`tree/domain/core.py`),
чтобы два инструмента не разошлись: `depth = 0`, если `parent is None`; `1`, если `parent == "."`;
иначе `parent.count("/") + 2`.

Отказы типизированные: `invalid_input` (кривой `path`, пустой `node`, не-сцена, неизвестный узел
по правилам 2/3/5/6 — эталонный текст сохранить в `message`), `denied` (PathPolicy),
`not_found` (нет файла). `conflict/*` не использовать.

Раскладка: `domain/` без `os`/`pathlib`/`io`/`socket`/`subprocess`/`re`; разбор — только
`from python.formats import tscn`; чтение — объявленный порт `RawReader` (`ports.py`, реализован
`substrate/fs.read_raw`, связывание в `runtime/bootstrap.py` без правок кода bootstrap);
лимит размера — `kernel/limits.READ_TEXT_MAX_BYTES`, объявить в `ToolSpec.limits`.

## 3. Шаги

1. **Лист механики** `docs/porting/scene_model.node_info.md` по `_template.md`: цель, старый код
   (`node_refactor.py:185-225` и `:163-183` как строки, `NodeRefactorError` как источник текстов),
   старые тесты (строки `tests-map.md:56-130` принадлежат `scene_model.node_rename` — **их судьбу
   не меняешь**; если считаешь, что часть belongs сюда, сначала R-09/R-10, иначе долг в `PROGRESS`),
   корпус, спецификация, решения, проверки. Этап 1.
2. **Корпус до кода** — `fixtures/corpus/scene_model/node_info/` с `manifest.json`; ≥ 14 кейсов,
   ожидания сняты `python -B`-скриптом с `find_node_in_scene` + собранной карточкой (скрипт удалить,
   в манифест дату, commit, sha256 входов и ожиданий). Покрыть: `.`, `""`, `%unique`, точный путь,
   короткое уникальное имя, **неоднозначное имя** (два узла с одним именем в разных родителях),
   отсутствующий узел, `%имя` у неуникального узла, `node` со обратными слэшами, `node` с пробелами
   по краям, вложенность 3 уровня, узел-инстанс, узел со скриптом, `.tres`/не-сцена, сцена без узлов.
3. **Тесты до реализации** (`python/modules/scene_model/node_info/tests/`, `tests/py/integration/test_node.py`),
   на заглушке red — записать `N tests, M failures, exit 1`. Обязательно: parity карточки по всем
   кейсам, literal-тексты отказов, AST-запрет IO и `re` в `domain/`, `test_domain_delegates_parse_to_formats`,
   манифест-пины (`len(inputs)`, sha256 файлов и ожиданий), read-only (`effects="read"`),
   строгая схема результата (`additionalProperties: false`).
4. **Реализация**: `domain/core.py` (разрешение + карточка, без IO), `app.py` (порт `fs`, PathPolicy,
   гейт `.tscn/.scn`, типизированные отказы), `tools.py` (`ToolSpec(name="node", …)`), `module.py`
   (`id="scene_model.node_info"`, `provides_tools=("node",)`), `ports.py`.
5. **Контракт**: `python tools/gen_contract.py` (без `--check`), затем `--check` = **12** артефактов.
6. `python tools/selfcheck.py scene_model.node_info` — вердикт ok (unit + corpus).
7. Записи: `WORKLOG.md` (сессия), `PROGRESS.md` (строка `scene_model.node_info` → 7, следующее действие),
   `docs/parity.md` (строка `scene_model.node_info` → ported, с якорем `node_refactor.py:185`),
## 4. Решения, которые примешь сам (и запишешь в лист)

- Как назвать инструмент в `docs/parity.md`: строка там помечена «(внутри `scene`)» — этот срез
  делает её отдельным инструментом `node`; поправь строку и укажи причину (у `scene` уже есть
  свой контракт и корпус C.3; склейка двух ответов сломала бы принятый артефакт).
- Где живёт сборка карточки (один экземпляр логики, R-04): разрешение спецификации и карточка — в
  `domain/core.py`; никакого дублирования правил `path`/`depth` из `tree` — либо переиспользование
  чистых функций `tree/domain` (если это не нарушает R-11: `tree` — свой же модуль), либо копия
  с обоснованием и тестом на равенство.
- Эталонные тексты отказов переносятся как есть (R-08), включая `%%%s` в сообщении про `%unique`.
- Код отказа выбираешь сам, но одно сообщение — один код (иначе в схеме появится дырка).

## 5. Чем доказывается (сдаёшь этими артефактами)

Бэкап — `shutil.copyfile` в `%TEMP%`, sha256 до/после, восстановление побайтовое, EOL не меняется,
в конце `restored identical: True`. Мутации **по одной**, на сдаваемом файле:

| # | Мутация | Что обязано покраснеть |
|---|---|---|
| M1 | убрать нормализацию `\` → `/` в `spec` | кейс с обратными слэшами |
| M2 | убрать ветку `%unique` | кейс `%имя` |
| M3 | при неоднозначном имени возвращать первый узел | кейс неоднозначности |
| M4 | `children` считать без `..`-правил `_rel_path_between` | кейс вложенности 3 уровня |
| P1 | добавить в `ToolSpec` поле результата, которого нет в `node.json` | `gen_contract --check` fail + 1 тест |
| P2 | испортить одно ожидание корпуса | parity-тест и манифест-пин |
| P3 | `import pathlib` (или `import re`) в `domain/core.py` | AST-тест и `lint_arch` |

Мутация, которая ничего не покрасила, — незакрытое требование: либо тест, либо код.

## 6. Стоп-условия (нарушил — срез не принят)

- Старый плагин не изменён: те же две `??`, `git diff` пуст, `python -B`, дампы в `%TEMP%`.
- `gen_contract --check` = 12; `snapshot_diff` 179/0; `lint_arch`/`check_limits` 0 нарушений;
  `security_audit` ok; `selfcheck scene_model.tree`, `selfcheck verification.gd_lint`,
  `selfcheck editing.scene_ops` остаются зелёными.
- Сумма тестов = сумме `--collect-only`; live-набор остаётся 3; ни один существующий тест
  не удалён и не ослаблен. Две мутации одновременно — запрещено.
- `PYTHONDONTWRITEBYTECODE=1` в каждой команде; команда дольше 30 с дробится, вывод в файл;
  stderr читается через файл; JSON в инструменты — только `--args-file`; Git не инициализируется.
- `# verb:` и `editor/**` не трогаются; `verbs_version` остаётся 3; подложки `.gd` убираются
  вместе с `.uid`.

## 7. Что проверит аудитор (готовься именно к этому)

1. Свои прогоны: non-live, live, `--collect-only`, `gen_contract --check`, `snapshot_diff`,
   `lint_arch`, `check_limits`, `security_audit`, три `selfcheck`.
2. Пересъёмку корпуса эталоном через `app.call` (не только `domain`): 100 % кейсов.
3. Свои мутации P1–P3 и хотя бы две из M1–M4 — с бэкапом и sha256; смотрит на список красных.
4. Чтение кода: лимиты 80/150/400, нет IO и `re` в `domain/`, один экземпляр логики,
   единственный разбор `.tscn` (`ext_resource|\[node ` по `python/**` находит только `formats/tscn.py`).
5. Гигиену (`__pycache__` 0 и т.д.), неизменность инвариантов и старого плагина.
6. Вердикт — из инструмента, а не из текста отчёта (R-22).

## 8. Финальный прогон и записи

```powershell
$env:PYTHONDONTWRITEBYTECODE=1
$xml = Join-Path $env:TEMP 'c4_junit.xml'; $o = Join-Path $env:TEMP 'c4.txt'
python -m pytest python/modules tests/py --ignore=tests/py/live -q -p no:cacheprovider --junitxml=$xml
python -m pytest tests/py/live -q -p no:cacheprovider
python -m pytest python/modules tests/py --ignore=tests/py/live --collect-only -q -p no:cacheprovider
python tools/gen_contract.py --check ; python tools/snapshot_diff.py ; python tools/lint_arch.py
python tools/check_limits.py ; python tools/security_audit.py
python tools/selfcheck.py scene_model.node_info
```

В отчёте: числа из junit и `--collect-only` (должны совпасть), sha256 сдаваемых файлов до/после
мутаций, размеры и `lf/crlf`, таблица «мутация → красные тесты», честный список того, что не
доказано. Записи: `WORKLOG.md` новая сессия, `PROGRESS.md` строка механики, `docs/parity.md`,
лист механики. Шапку «выполнено» в `_audit-handoff.md` и статус промпта в `README.md` ставит
только аудитор.


