# Срез C.3 — механика `scene_model.tree` (инструмент `scene`)

Ты портируешь один read-инструмент нового Godot-агента в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`.
Эталон читается **только на чтение** из `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent`
(`python -B`, дампы в `%TEMP%`); старый плагин не правится, его два чужих лога
(`python/_ref2.log`, `python/godot_tools/_excl.log`) не удаляются.

Разбор `.tscn` уже есть в новом агенте — `python/formats/tscn.py` (часть C принята 2026-10-29).
`gd_lint` (C.2) принят аудитом 2026-10-29. Этот срез — первый шаг в `scene_model`: сводка сцены
как данные и как текст, **без записи, без моста, без `# verb:`**.

## 0. База на старте (мой замер, аудит 2026-10-29, сессия 48)

```powershell
cd 'D:\vajno\Godot\agent-rebuild\addons\godot_agent'
$env:PYTHONDONTWRITEBYTECODE=1
python -m pytest python/modules tests/py --ignore=tests/py/live -q -p no:cacheprovider   # 658 passed
python -m pytest tests/py/live -q -p no:cacheprovider                                    # 3 passed
python -m pytest python/modules tests/py --ignore=tests/py/live --collect-only -q        # 46 файлов, сумма 658
python -m pytest tests/py/formats -q -p no:cacheprovider                                 # 100 passed
python tools/gen_contract.py --check        # артефактов 10
python tools/snapshot_diff.py               # кейсов 139, расхождений 0
python tools/lint_arch.py                   # файлов 456, 0
python tools/check_limits.py                # файлов 456, 0
python tools/security_audit.py              # ok
python tools/selfcheck.py verification.gd_lint   # ok, unit 126, corpus 37
```

| Якорь | Значение |
|---|---|
| Файлов в плагине | **1017** (этот промпт добавляет один: у тебя на старте **1018** — запиши своё число) |
| Правил `RULES.md` | 22; листов механик 11; промптов 23 |
| `python/kernel/schema.py` | `629FCE54E6FE…` (неизменяем) |
| `tools/lint_arch.py` / `gen_contract.py` / `security_audit.py` | `1FAD8E7470D5…` / `FA7E6E91C872…` / `2CF0D7F6B1AF…` (неизменяемы) |
| `contract/editor_verbs.json` | `CDAF8D23A6BF…` (мост не трогаем) |
| `editor/bridge/verbs/scene/scene_executor.gd` | `B7AFF592B75D…` |
| `python/formats/tscn.py` | `BF844574D6E5…`, 6698 Б, lf=167/crlf=0 |
| `python/modules/verification/gd_lint/domain/core.py` | `9EBB211FB387…` (принятый C.2) |
| Godot | `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe` |
| Гигиена на старте | `__pycache__` 0, `.pytest_cache` 0, `*.bak/tmp/orig` 0, `zz_*` 0 |
| Git | в `agent-rebuild` намеренно нет |

## 1. Границы среза

В срезе:
- лист механики `docs/porting/scene_model.tree.md` по `_template.md` — **первым делом, до кода** (R-19);
- модуль `python/modules/scene_model/tree/` (`module.py`, `tools.py`, `app.py`, `domain/`, `ports.py`, `tests/`),
  `ModuleSpec.corpus = "corpus"`, инструмент с именем **`scene`** (имя из `docs/parity.md:30`);
- корпус `fixtures/corpus/scene_model/tree/` — снят с эталона, не подогнан;
- новая capability-карта `contract/capabilities/scene.json`; после неё `gen_contract --check`
  даёт **11** артефактов — это ожидаемо;
- строка `docs/parity.md` этой механики (статус) и записи `WORKLOG`/`PROGRESS`;
- **расширение `python/formats/tscn.py` разрешено только если без него не обойтись**, и тогда:
  одна реализация разбора, паритет и тесты в `tests/py/formats/`, мутации на новой функции,
  и запись об этом в листе и в `PROGRESS`.

Не в срезе: `scene_model.node_info`, `connections`, `scene_deps`, `node_rename/reparent/delete`;
`verification.tscn_lint`; `editing.*`; любые записи на диск; `# verb:`, `editor/**`, `runtime/**`;
`contract/**` кроме нового `scene.json`; неизменяемые `tools/lint_arch.py`, `tools/gen_contract.py`,
`tools/security_audit.py`, `python/kernel/schema.py`; уже принятые механики, их корпуса и листы.

**Наследство предыдущих срезов.** `patch` в `tscn.py` не диагностирует пересекающиеся правки — это
требование к `scene_model.node_rename`, не к сводке; не «починяй». Форматный корпус
`fixtures/parity/tscn/` (16 файлов) закрыт и неприкосновенен. Новые тесты фиксируются в листе
механики и `PROGRESS`, но не строками в `tests-map.md`.

## 2. Контракт и раскладка (якоря эталона: файл:строка)

Эталон: `python/godot_tools/project_tools.py:1269-1372`, `def describe_scene(project_root, godot_path,
max_chars=12000)`. Читает файл `utf-8-sig` (`:1276`), собирает `ext`-ресурсы `:1284-1296`,
`sub_resource` `:1297-1300`, затем построчно узлы/связи `:1302-1334`, скрипт узла `:1332-1336`,
рендер `:1349-1368`, обрезка `:1369-1371`.

Правила, которые обязаны совпасть **побайтово** (это и есть паритет):

- отступ узла: `depth = 0` для корня, `1`, если `parent == "."`, иначе `parent.count("/") + 2` (`:1315-1319`);
- строка узла: `"  " * depth + "- " + name`, затем `" ("` + `", ".join(extra)` + `")"`, где `extra` —
  `[type]`, плюс `"инстанс: <путь ext-ресурса>"`, если есть `instance=ExtResource(...)`;
  `type=""` у узла без типа не печатается; затем `"  [скрипт: <путь>]"` при `script = ExtResource(...)`;
- связи: пустая строка, `Сигналы ([connection]):`, затем `"- " + from + "." + signal + " -> " + to + "." + method + "()"`,
  где `from`/`to`, равные `""` или `"."`, печатаются как `<root>`;
- ресурсы: пустая строка, `Ресурсы (id/uid для точных ссылок в ExtResource/SubResource):`,
  `"- ext id=%s %s: %s"` (+ `" (uid=%s)"` если `uid=` был), `"- sub id=%s %s"`; отсутствующие
  `id`/`type`/`path` печатаются как `?`;
- обрезка: если `len(result) > max_chars`, то `result[:max_chars] + "\n… (сводка обрезана — сцена очень большая)"`;
- пустая сцена без `[node]` — отказ, дословно `В файле не найдено ни одного узла [node].`;
- только `.tscn`/`.scn` (иначе отказ), отсутствующий файл — `not_found`;
- порядок строк = порядок файла; никакой сортировки, дедупликации и «улучшений» (R-08).

Результат инструмента — `{text, truncated, nodes[], connections[], resources{ext[], sub[]}}`:
`text` — эталонная сводка (обязана совпадать с эталоном), остальное — новая проекция данных,
как `check()` в `gd_lint`: узлы `{name, type, parent, path, depth, script, instance}`,
связи `{from, to, signal, method}`, ресурсы `{id, type, path, uid}` / `{id, type}`.
`truncated` — правда только тогда, когда `text` реально обрезан.

Раскладка и правила:
- `app.py` ≤ 80 строк — только политика пути, порт чтения байтов, домен; `tools.py` ≤ 150;
- `domain/` без IO и без импортов `os`/`pathlib`/`io`/`socket`/`subprocess` (правило `lint_arch`);
- данные эталона декодируются `utf-8-sig` (`errors="replace"`), CRLF при построчном разборе не ломает
  вывод — это поведение эталона, а не наше улучшение;
- **разбор `.tscn` — только `python/formats/tscn.py`** (R-04): второго парсера в модуле быть не
  должно. Если `structure()` не даёт `sub_resource`/`uid`/`depth` — добавь в `formats/tscn.py`
  минимальную функцию, докажи паритет и мутации, зафиксируй в листе;
- порт `RawReader` объявляется в `ports.py` (`typing.Protocol`), реализуется существующим
  `substrate/fs` (`read_raw`), привязка — через `runtime/bootstrap.py`, код бутстрапа не менять;
- лимит размера — существующий `kernel/limits.READ_TEXT_MAX_BYTES`; `max_chars` по умолчанию 12000,
  объявить в `ToolSpec.limits`.

## 3. Шаги

1. **Лист механики** `docs/porting/scene_model.tree.md` по `_template.md`: цель, старый код
   (`project_tools.describe_scene:1269-1372` — что делает, как делим), старые тесты (в `tests-map.md`
   строк этой механики нет; в `tests-map.md:56-130` они отданы `scene_model.node_rename` — не менять),
   корпус, `ToolSpec` + инварианты, решения, ход, проверки, следующее действие одной строкой. Этап 1.
2. **Корпус до кода** `fixtures/corpus/scene_model/tree/` в существующей форме
   `{id, tool, fixture, args, expect}`: не меньше **14** сцен — простая (`minimal/player.tscn`),
   вложенные узлы, `parent="."`, инстанс другой сцены, `[connection]` с `from="."`/`to="."`,
   узел со скриптом, `unique_name_in_owner`, `[editable]`, `sub_resource`, `[resource]` (`.tres`),
   сцена без `[node]` (отказ), пустой файл, BOM, CRLF, большая сцена с `max_chars` поменьше
   (обрезка), `.scn` или чужое расширение (отказ). Ожидания снимаются **одним** `python -B`-скриптом
   из старого каталога (обычный импорт `_bootstrap`/`project_tools`; `sys.path` = `godot_tools`,
   `parsers`, `python`), скрипт после снятия удаляется; `manifest.json` — дата, commit, sha256/размер
   эталона и каждого входа, sha256 ожиданий.
3. **Тесты до реализации** (обязаны покраснеть на заглушке, зафиксируй `N tests, M failures, exit 1`):
   паритет `text` побайтово для каждого кейса; структурная проекция; обрезка `max_chars`;
   отказ без `[node]`; отказ не-`.tscn`; `not_found` без утечки абсолютного пути; `domain/` без IO
   (AST-тест); манифест пинит входы и ожидания.
4. **Реализация** в порядке «формат → домен → приложение»: сначала при необходимости расширение
   `formats/tscn.py` (с паритетом), затем `domain/` (рендер и проекция, без IO), затем `app.py`
   (политика `PathPolicy`, `res://` и относительный путь, `read_raw`, `EFBIG` → `invalid_input`),
   `tools.py` (`ToolSpec(name="scene", effects="read", idempotent=True, cost="cheap")`), `module.py`.
5. `python tools/gen_contract.py` (без `--check`) — появится `contract/capabilities/scene.json`;
   затем `--check` = **11** артефактов.
6. `python tools/selfcheck.py scene_model.tree` → `ok`.
7. Записи: `WORKLOG` (сессия с числами и мутациями), `PROGRESS` (строка механики и следующий шаг),
   `docs/parity.md` (статус `scene`), лист механики (этап 7 и «Следующее действие»).

## 4. Решения, которые примешь сам (и запишешь в лист §4)

- Как назвать расширение `formats`, если оно понадобится (`subsections(text)`/`rows(text)`), и почему
  не «второй парсер» — обязателен абзац с якорем эталона.
- Где живёт рендер текста (домен) и как он доказывается: `text` из домена == эталон, без склейки
  в `app.py`.
- Что делать с квирками эталона (`?` вместо отсутствующего `id`, `<root>` в связях, `type=""` не
  печатается) — переносить как есть, R-08.
- Как считается `truncated` (по факту обрезки, а не «текст длинный»).
- Форма `nodes[]`/`connections[]`/`resources` — новая проекция; поле в схеме без значения в
  результатах запрещено.

## 5. Чем доказывается (мутации и подложки, строго по одной)

Бэкап сдаваемого файла — `shutil.copyfile` в `%TEMP%`, sha256 до/после, восстановление побайтовое,
`restored identical: True`, EOL сохранён, бэкап удалён в конце.

- M1: снять правило глубины (`parent.count("/") + 2` → всегда `1`) — паритет обязан покраснеть на
  вложенных сценах.
- M2: не печатать `[скрипт: …]` — красный кейс с узлом-скриптом.
- M3: снять обрезку `max_chars` — красный кейс обрезки (`truncated` и длина `text`).
- Подложка в инструмент: поле результата без объявления в `ToolSpec` → `gen_contract --check` падает.
- Подложка в корпус: испортить одно ожидание → паритет краснеет ровно на этом кейсе, пин манифеста
  тоже.
- Подложка IO: `import pathlib` в `domain/` → AST-тест и `lint_arch` красные.
- Мутация, которая ничего не покрасила, — незакрытое требование: либо тест, либо отказ от ветки.

## 6. Стоп-условия

- Старый плагин только читается (`python -B`, дампы в `%TEMP%`); после среза `git status --porcelain` —
  те же две строки, `git diff` пуст.
- `gen_contract --check` = **11**; `snapshot_diff` = **139/0** (чужие корпуса не менялись);
  `lint_arch`/`check_limits` 0 нарушений; `security_audit` ok; `selfcheck verification.gd_lint` и
  `selfcheck editing.scene_ops` остаются зелёными.
- Общее число тестов = сумме `--collect-only`; live-набор остаётся **3** (механика read, Godot не
  нужен; если решишь иначе — обоснуй в листе).
- Двух мутаций одновременно нет; `PYTHONDONTWRITEBYTECODE=1` в каждой команде; JSON только через
  `--args-file`; команда дольше 30 с — дроби, вывод в файл; stderr — в файл.
- Git в `agent-rebuild` не инициализируется; `# verb:` и `editor/**` не трогаются.

## 7. Что проверит аудитор

Свои прогоны, не твои числа: non-live, live, `--collect-only` (сумма), `gen_contract --check` (11),
`snapshot_diff`, `lint_arch`, `check_limits`, `security_audit`, `selfcheck scene_model.tree`;
пересъёмку корпуса с эталона своим скриптом; дифференциальный прогон сводки на всех `.tscn`/`.tres`
корпуса и `fixtures/projects`; свои мутации на сдаваемом файле с байтовым бэкапом и sha256;
подложки в инструмент, контракт и ожидание; чтение кода (лимиты 80/150/400, IO в `domain/`,
единственный разбор `.tscn` — поиск `ext_resource` по `python/**` не должен находить второй парсер);
гигиену (`__pycache__` 0, `zz_*` 0); байтовую неизменность старого плагина и хешей-инвариантов.

## 8. Финальный прогон и записи

```powershell
python -m pytest python/modules tests/py --ignore=tests/py/live -q -p no:cacheprovider --junitxml=$xml
python -m pytest tests/py/live -q -p no:cacheprovider        # 3 passed
python -m pytest python/modules tests/py --ignore=tests/py/live --collect-only -q   # сумма == junit
python tools/gen_contract.py --check                         # артефактов 11
python tools/snapshot_diff.py                                # 139/0
python tools/lint_arch.py ; python tools/check_limits.py ; python tools/security_audit.py
python tools/selfcheck.py scene_model.tree                   # ok
```

Записи: `WORKLOG.md` — сессия с числами, мутациями и честными границами; `PROGRESS.md` — строка
`scene_model.tree` (этап и доказательства) и следующий шаг; лист механики — этап 7 и «Следующее
действие» одной строкой; `docs/parity.md` — статус `scene`. `docs/porting/README.md` и
`docs/porting/_audit-handoff.md` правит **аудитор**, не ты.



