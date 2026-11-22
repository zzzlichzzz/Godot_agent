# Задача: часть C — `.tscn`/`.tres` как файлы, один разбор `formats/tscn.py`

Ты в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`. Мост редактора закрыт
(части A и B приняты: `editing.scene_ops` — этап 7, аудит 2026-10-29). Следующий
срез — **не механика, а фундамент под них**: `python/formats/tscn.py` сейчас
заглушка из четырёх строк, поэтому девять механик `scene_model.*` и
`verification.tscn_lint` стоят на этапе 0 (R-04: один разбор `.tscn` на весь агент).

## 0. База на старте (мой замер, аудит 2026-10-29, сессия 44)

```
python -m pytest python/modules tests/py --ignore=tests/py/live -q   # 449 passed, exit 0
python -m pytest python/modules tests/py --collect-only -q          # 449 (41 файл) = сумма 41 строки
python -m pytest tests/py/live -q                                   # 3 passed (4.6.3), exit 0
python tools/gen_contract.py --check      # ok, артефактов 9, verbs_version 3, примитивов 6
python tools/snapshot_diff.py             # 102/0
python tools/lint_arch.py                 # 453, нарушений 0
python tools/check_limits.py              # 453, нарушений 0
python tools/security_audit.py            # ok (SEC-06/07/08/20 ok)
python tools/selfcheck.py editing.scene_ops  # ok: unit 25, corpus live
```
Хеши-опоры (сверены мной, не из отчёта): `python/kernel/schema.py` `629FCE54E6FE`,
`tools/lint_arch.py` `1FAD8E7470D5`, `tools/gen_contract.py` `FA7E6E91C872`,
`tools/security_audit.py` `2CF0D7F6B1AF`, `contract/editor_verbs.json`
`CDAF8D23A6BF`, `editor/bridge/verbs/scene/scene_executor.gd` `B7AFF592B75D`
(19131 Б, lf=444 crlf=0), `scene_verbs.gd` `712BDB494995` (1269 Б).
`python/formats/tscn.py` — **4 строки**, `sha256 330D68046DF3…`, в шапке TODO
`parse (ext/sub/узлы/connections), serialize, node_paths`.
Файлов 911 на момент замера (902 в подкаталогах + 9 в корне, считая `.gitignore`);
этот промпт добавляет один файл, так что у тебя на старте будет **912** — запиши своё
число, а не моё. `__pycache__` 0,
`.pytest_cache` 0, `*.bak/tmp/orig` 0, `zz_*` 0. Правил 22, листов механик 10.
Старый плагин: `git status --porcelain` — ровно два чужих untracked-лога
(`python/_ref2.log`, `python/godot_tools/_excl.log`), `git diff` пуст;
**не удалять, не править, не коммитить**.
Движок: `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`.

## 1. Границы среза

**В срезе:**
1. `python/formats/tscn.py` (или пакет `python/formats/tscn/`, если не влезает в
   400 строк — как у `gdscript`, R-06) — единственный разбор `.tscn`/`.tres` в агенте.
2. Корпус формата `fixtures/parity/tscn/` + `expected.*.json`, снятые с эталона (R-07).
3. Постоянные тесты `tests/py/formats/test_tscn_parity.py` (+`test_tscn_edit.py`), включая
   запрет IO в `formats/` (как в `test_gdscript_parity.py:26`).
4. Записи: `docs/WORKLOG.md` (сессия), `docs/PROGRESS.md` (долг + «следующее действие»).

**Не в срезе** (не начинать, даже если «рядом»):
- линт как механика (`verification.tscn_lint`, `verification.gd_lint`) — следующий срез C.2;
- любые механики `scene_model.*`, `editing.resource_ops`, `editing.paths_preview`;
- запись в открытую сцену, undo, `ResourceSaver`, `contract/**`, новые инструменты и
  capability-артефакты, `# verb:`, `editor/**`, `runtime/**`;
- правки `python/kernel/schema.py`, `tools/lint_arch.py`, `tools/gen_contract.py`,
  `tools/security_audit.py` (неизменяемые), принятые механики и их корпуса.

## 2. Контракт и раскладка (якоря эталона — файл:строка)

**2.1 `structure(text)` — ровно ответ эталона `parse_tscn_structure`.**
Эталон: `тест-плагина-ии/addons/Godot_agent/godot_agent/python/godot_tools/node_refactor.py:73-160`.
Смысл полей брать оттуда дословно, ничего не добавлять и не нормализовать:
`ext_resources: {id: attrs}` (`:81-87`), `nodes[{name,parent,type,path,unique_name,script_id,header_span,body_span}]`
(`:89-134`; тело узла кончается на следующем `[node`, а внутри — на
`[connection|sub_resource|editable`, `:101-117`), `connections[{from,to,signal,method,span,raw}]`
(`:136-148`), `anim_tracks[{full_span,path_span,path}]` (`:150-158`, шаблон
`tracks/\d+/path\s*=\s*NodePath\(...`).

**2.2 `fields(text)` — ровно ответ второго эталона `parse_scene`.**
Эталон: `.../python/godot_tools/scene_deps.py:120-172`: `ext {id:{type,path}}`,
`nodes[{name,type,parent,path,script_id,instance_id}]` (`instance=ExtResource("1_x")` →
**голый** id, комментарий `:150-154`), `connections[{signal,from,to,method}]`.
Тот же файл — `_parse_attrs` (`:102-108`) и `_attr_id` (`:111-117`).

**2.3 `patch(text, edits)` — правка по смещениям, без реконструкции.**
`edits` — список `(span, replacement)`, применяется от конца к началу; `patch(text, [])`
возвращает **тот же текст байт в байт** (включая CRLF и BOM). Реконструкция структуры
обратно в текст запрещена: формат Godot не воспроизводится из модели (R-08), а
`scene_model.node_rename` будет править именно смещения из `structure()`.

**2.4 Раскладка.** Образец — `python/formats/gdscript/` (`__init__.py` с `__all__`,
внутренние модули; 299/107/54 строки) и `python/formats/tscn.py:1-4` (заглушка).
`python/formats/**` не импортирует `os`, `pathlib`, `io`, `open` — тест-страж уже есть
в `test_gdscript_parity.py:26` (`BANNED_IN_FORMATS`), для `.tscn` — такой же.
Заголовочный комментарий файла: что заменяет (шапка заглушки это уже говорит:
`project_tools.describe_scene`, `node_refactor.parse_tscn_structure`, `scene_deps`, `tscn_lint`).


## 3. Шаги

**3.1 Корпус (до кода).** `fixtures/parity/tscn/` — не меньше 12 файлов:
`basic.tscn` (ext_resource Script + корень + два ребёнка), `instance.tscn`
(`instance=ExtResource(...)` без `type`, вложенная сцена), `unique.tscn`
(`unique_name_in_owner = true`), `connections.tscn` (три `[connection]`, пути
`from`/`to`), `anim.tscn` (`tracks/0/path`, `tracks/1/path` = `NodePath("Gun/Muzzle:position")`),
`editable.tscn`, `sub.tscn` (`[sub_resource]` + `SubResource(...)` в свойствах),
`spans.tscn` (значения со `]`, `"` и многострочный `PackedVector2Array([...])`),
`crlf.tscn` (CRLF), `bom.tscn` (BOM), `flat.tres` (`[gd_resource type="Resource" ...]` +
`[resource]`), `curve.tres` (sub_resource + ext_resource). Один файл можно взять из
`fixtures/projects/minimal/scenes/player.tscn` как есть — но копией, не ссылкой.

`expected.structure.json` и `expected.fields.json` снимаются **одноразовым скриптом**
через `python -B` из старого каталога (как в `docs/porting/code_intel.usages.md:52-58`),
скрипт после снятия удаляется; в корпусе остаётся манифест: дата, sha256 каждого файла,
sha256 эталонных файлов. Ни один ожидаемый ответ руками не правится.

**3.2 Код.** `structure`/`fields`/`patch` в `python/formats/tscn.py`, публичные имена — в
`__all__`. Все решения о «как правильно» — из эталона: расхождение с эталоном на
корпусе = дефект переноса, а не повод поправить ожидание (R-07/R-08).

**3.3 Тесты.** `test_tscn_parity.py`: по параметру на файл — `structure(text) ==
expected.structure[name]`, `fields(text) == expected.fields[name]`; `patch(text, []) ==
text` для всех файлов корпуса; `patch` с двумя правками в одном файле (одна в
`header_span` узла, одна в значении свойства) — обе применились, остальное не тронуто;
BOM/CRLF сохраняются. Отдельный тест: `formats/tscn.py` не содержит `import os|pathlib|io`
и `open(`. Никаких `sleep`, сети, движка — срез целиком не-live.

**3.4 Доказательства** — §5, до отчёта.

## 4. Решения по ходу

- Разделять файл на пакет можно **только** по лимиту R-06 (>400 строк), не «для красоты».
- Если эталон на каком-то файле ведёт себя неожиданно (например, `type` пустой у
  инстанса) — это фиксируется в отчёте как факт эталона и переносится как есть.
- Если нужен ключ, которого в эталоне нет (например, `uid=` в шапке `[gd_scene]`), —
  **не добавлять**: это отдельное решение с записью в `docs/NOTES.md` и вопросом
  пользователю, а не «мелочь по ходу».
- `serialize` из TODO заглушки в этом срезе **не реализуется**: вместо него `patch` по
  смещениям. Причину — в шапку файла.

## 5. Доказательства (мутации и подложки — последовательно!)

На сдаваемом `python/formats/tscn.py`, байтовый бэкап `shutil.copyfile` в `$env:TEMP`,
`sha256` до/после, EOL сохраняется, `restored identical: True`:

1. **M1** — из списка границ тела узла убрать `editable` (эталон `node_refactor.py:105`)
   → `body_span` расходится, parity краснеет.
2. **M2** — в `patch` применять правки в прямом порядке вместо обратного → тест с двумя
   правками краснеет (смещения съезжают).
3. **M3** — в `patch` нормализовать `\r\n` → `\n` → краснеет `patch(text, []) == text`
   и BOM/CRLF-тест.
4. **Подложка** — `import pathlib` (или `open(`) в `python/formats/tscn.py` → краснеет
   тест-страж IO. Подложку убирать вместе с возможным `.uid` (урок сессии 42).

Мутация, которая не краснит ни одного теста, — незакрытое требование: сдавать нельзя,
в отчёт — как долг.

## 6. Стоп-условия

- Старый плагин — только чтение (`python -B`, дампы в `$env:TEMP`), два чужих лога не
  удалять; его `git status` до и после среза одинаковый.
- Ни одного нового `capability`-артефакта: `gen_contract --check` остаётся **9**.
- `snapshot_diff` остаётся **102/0** (корпус `fixtures/corpus/**` не трогается).
- `pytest` без `--ignore=tests/py/live` = сумма `--collect-only`; живые 3 теста не ломать.
- Две мутации одновременно запрещены; в каждой команде `PYTHONDONTWRITEBYTECODE=1`.
- Команда дольше 30 с умирает — дробить, вывод в файл, JSON только `--args-file`.
- Никакого git в `agent-rebuild`.

## 7. Что проверит аудитор

Свои прогоны: non-live pytest + `--collect-only` (сумма = число тестов), `gen_contract
--check` (9), `snapshot_diff` (102/0), `lint_arch`/`check_limits` (файлов станет больше —
сверю числа заново), `security_audit`, `selfcheck` уже принятой механики (регресс).
Свою **подложку** (IO в `formats/tscn.py` → красный) и **свою мутацию** на сдаваемом
файле с байтовым бэкапом и сверкой `sha256`. Чтение кода: нет IO в `formats/`, нет
второго разбора `.tscn` (поиск `ext_resource` по `python/` не находит реализацию вне
`formats/tscn.py`), лимиты 400/150/80, `__pycache__` = 0, старый плагин байт-в-байт
(`git status` — те же два `??`). Числа из отчёта сверю со своими; вердикт — по
инструменту, а не по тексту (R-22).

## 8. Финальный прогон и записи

```
python -m pytest python/modules tests/py --ignore=tests/py/live -q
python -m pytest python/modules tests/py --collect-only -q
python -m pytest tests/py/live -q
python tools/gen_contract.py --check
python tools/snapshot_diff.py
python tools/lint_arch.py ; python tools/check_limits.py ; python tools/security_audit.py
python tools/selfcheck.py editing.scene_ops
```
Записи: `docs/WORKLOG.md` — сессия (что сделано, числа, мутации, что осталось
непроверенным); `docs/PROGRESS.md` — строка `scene_model.node_rename` (следующее
действие) и долг «`formats/tscn.py` — заглушка» с датой закрытия; лист механики **не**
создаётся (срез — форматный слой, не механика; лист `scene_model.*` создаётся в своём
срезе, R-19). Шапки промптов, `docs/porting/README.md`, `_audit-handoff.md` — правит
аудитор.
