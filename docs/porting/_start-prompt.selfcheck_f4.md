# C.19 — долг F4: селектор юнитов в `tools/selfcheck.py` (ровно три разрешённые дельты)

Ты — **портер**. Работаешь только в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`.
Эталон (старый плагин) читаешь, но не меняешь. Этапы сам себе не ставишь, «выполнено/принято/ported»
не пишешь, `docs/porting/_audit-handoff.md` не правишь. Сдаёшь строкой «C.19 готов к независимому
аудиту, не принято». Приёмка — только моими прогонами.

## Читать до первой строки кода

1. `AGENTS.md`, `RULES.md` (R-02, R-05, R-09, R-11, R-13, R-22 — гейты и запреты).
2. `docs/architecture.md`, `docs/PORTING.md`.
3. `docs/porting/editing.split_py.md` — раздел «C.18 … preflight» и подраздел про F4: там уже лежат
   `selector-prediction.json`, `counts-before.json`, `counts-before/<id>.stdout.txt`, внешний архив
   красных пинов и черновик ADR.
4. `docs/adr/0013-selfcheck-unit-selector.md` (сейчас `proposed`).
5. `tools/selfcheck.py` целиком: `check_unit`, `MODULES`, `REPORTS`, `module_readiness`.
6. `docs/porting/_start-prompt.split_py_plan.md` §10 (B6) — почему F4 вынесен в отдельный срез.
7. `docs/security/invariants.md`, WORKLOG сессий 73–74.

## §0 База (снято аудитом, сессия 75, 2026-11-01 — не пересчитывать)

- Полный прогон: **4185 passed**, junit 4185/0/0/0, 91.4 с, stderr пуст.
- Live: **3** passed, 0 skip (нужен временный `[editor_plugins]` во внешнем
  `D:\vajno\Godot\agent-rebuild\project.godot`, 335 B, sha256 `958b3a92d706…`, восстановление побайтово);
  Godot — `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`.
- `tools/snapshot_diff.py` → **820/0**; `tools/gen_contract.py --check` → **25** артефактов (26 файлов).
- Selfcheck-точки (меняются только три дельты из §1): `editing.split_py` 568/96,
  `editing.split_gd` 625/102, `engine_kb.class_api` 186/26, `scene_model.node_info` 352/65,
  `scene_model.tree` 168/40, `verification.check` 188/75, `verification.api_check` 206/52,
  `verification.gd_lint` 126/37, `verification.tscn_lint` 315/65.
- Гейты: `lint_arch` 544 ok, `check_limits` 544/0, `security_audit` ok.
- Дерево **3182** файла, `.gd.uid` **83**, debris 0; промптов 37; ADR 13.

## §1 Границы среза

Срез — **только долг F4**: селектор юнит-тестов в `tools/selfcheck.py` собирает файлы по префиксу
`integration.glob("test_%s*.py" % name)`, поэтому один файл попадает в несколько механик. Правило —
**самый длинный известный инструмент**: файл `test_<X>_<rest>.py` принадлежит `<X>_<rest>`, если
`<X>_<rest>` — публичное имя известного инструмента (из `discover()`), иначе `<X>`.

**Разрешённые дельты — ровно три, заранее:**

| механика | было | станет | что выпадает |
|---|---|---|---|
| `engine_kb.class_api` (`api`) | 186 | **128** | `test_api_check.py` (58) |
| `scene_model.node_info` (`node`) | 352 | **247** | `test_node_delete_preview.py`, `test_node_rename_preview.py`, `test_node_reparent_preview.py` |
| `scene_model.tree` (`scene`) | 168 | **116** | `test_scene_deps.py`, `test_scene_ops_bridge.py` |

Остальные **41 механика обязаны сохранить число, состав и порядок** файлов списка.
`test_api_snapshot.py` остаётся у `api` — `api_snapshot` не является публичным инструментом.

В срезе: `tools/selfcheck.py` (минимальная правка в `check_unit`), ADR-0013 → **принято**,
новый `tests/py/tools/test_selfcheck_unit_selector.py`, запись в лист и `docs/tests-map.md`.

Не в срезе: production-код механик, `python/kernel|substrate|runtime|protocol`, `editor/**`,
корпуса, карточки, `contract/editor_verbs.json`, остальные `tools/*`, `_audit-handoff.md`.

## §2 Контракт правки

`check_unit` берёт список инструментов один раз и для каждого `name` отбрасывает чужие файлы:

```python
tools = {t for item in loaded for t in item.spec.provides_tools}
for extra in sorted(integration.glob("test_%s*.py" % name)):
    stem = extra.stem[len("test_"):]
    if stem != name and stem in tools:
        continue          # test_<X>_<rest>.py принадлежит другому инструменту
    targets.append(extra)
```

Требования: ≤ 10 строк в одном месте; никаких захардкоженных исключений; `sorted` сохраняется;
для `name`, не являющегося инструментом, поведение прежнее; ошибки не глотать.

## §3 Шаги

1. Лист: раздел «C.19 — F4 (сессия 75)» с таблицей трёх дельт и sha256 файлов до правки.
2. Красные пины (до правки): три дельты не совпадают — тест красный; сохранить `f4-red.xml` и счётчики.
3. Правка селектора по §2.
4. ADR-0013: `proposed` → «принято аудитором 2026-11-01 (сессия 75)» + таблица трёх дельт.
5. Полная таблица «было/стало» по всем 44 механикам (`counts-before.json` уже снят, сними `after`).
6. Двойной прогон: полный pytest (4185 + новые), `snapshot_diff` 820/0, все 44 selfcheck,
   `lint_arch`/`check_limits`/`security_audit`, live 3, `.gd.uid` 83, debris 0.
7. Записи: лист (этап 7 + C.19), `docs/tests-map.md`, `docs/PROGRESS.md` (строка `editing.split_py`
   не меняется, долг F4 — в примечании), `docs/WORKLOG.md` — **append в `ab` без нормализации EOL**
   (исторический префикс 4479 CRLF обязателен).

## §4 Решения, которые уже приняты

1. Правило — «самый длинный известный инструмент», без списков исключений.
2. `test_api_snapshot.py` остаётся у `api`.
3. Ровно три дельты; четвёртая — стоп и вопрос.
4. Отчёты `reports/selfcheck/*.json` руками не правятся — их перезапишет selfcheck.
5. `snapshot_diff` и корпуса не затрагиваются вовсе.

## §5 Доказательства

- Мутации: M1 «вернуть старый селектор» → три пина красные; M2 «исключение только для `api_check`» →
  пины `node_info`/`tree` красные; M3 «не учитывать `tools`» → те же три.
- Подложка P1: убрать условие `stem != name` → пины красные.
- Обратная проекция sha256: `tools/selfcheck.py` отличается только фрагментом §2; 44 отчёта равны
  baseline кроме трёх механик.
- Гигиена: дерево 3182 + новые, `.gd.uid` 83, без `__pycache__`/`.pytest_cache`/`.bak|tmp|orig`/`zz_*`,
  одноразовые скрипты только в `%TEMP%`.

## §6 Стоп-условия

Появляется четвёртая дельта; нужна правка вне `tools/selfcheck.py` (кроме ADR/тестов/записей);
нужны `python/kernel|substrate|runtime|protocol`; `snapshot_diff` ≠ 820/0; меняется корпус или
карточка; у неизменённых механик `reports` перестают быть байтово равными baseline.

## §7 Что будет проверять аудитор

Свой прогон `discover()` и собственный пересчёт числа тестов по обоим правилам; сверка «ровно три
дельты, 41 механика без изменений»; свои мутации M1–M3 и P1; полный прогон, `snapshot_diff`, гейты,
live 3; обратная проекция sha256; гигиена.

## §8 Финальный прогон и записи

Один отчёт в лист + WORKLOG: полный pytest (число/время/collect), `snapshot_diff`, таблица 44 механик
«было/стало», `gen_contract --check` = 25, гейты, live 3, дерево/`uid`/debris, мутации с sha256.
Пишешь: лист, ADR-0013, `docs/tests-map.md`, `docs/PROGRESS.md`, `docs/WORKLOG.md`.
Не пишешь: `_audit-handoff.md`, «принято/ported», новый этап 7.

## §9 Ошибки прошлых срезов — не повторять

- Формы полей и тексты снимать **живым** вызовом (F6/F10/F11 родились из моих формулировок).
- `WORKLOG` — только `ab`-append, EOL не нормализовать.
- `--junitxml` — только python-драйвер.
- `recovery: plan=… expired` в stderr — не падение.
- Мутации — по одному прогону, без параллельных и без `Stop-Process`.
- Одноразовые скрипты — только в `%TEMP%`.
- Патч-скрипты — `assert` ровно одного попадания.
- F4 вынесен отдельно именно из-за правила «не двигать счётчики соседей»: здесь разрешены
  **только** три дельты.

## §10 Уточнения аудитора (сессия 76) — оба противоречия сняты

§2 настоящего промпта дал **буквальный** селектор, и он неверен: условие `stem in tools` роняет только точные имена, поэтому `test_scene_ops_bridge.py` остаётся у `scene` (tree 128 вместо 116) и меняются списки ещё четырёх механик. Разрешаю **настоящий longest-prefix** и протокол отчётов.

### B1 — разрешено: правило «самого длинного известного инструмента»

Владелец тест-файла определяется по **стему** и множеству публичных инструментов (те же `provides_tools`, что в `discover()`):

```python
tools = {t for item in loaded for t in item.spec.provides_tools}   # один раз, без побочных эффектов
def _owner(stem):
    cands = [t for t in tools if stem == t or stem.startswith(t + '_')]
    return max(cands, key=len) if cands else None
...
    for extra in sorted(integration.glob('test_%s*.py' % name)):
        own = _owner(extra.stem[len('test_'):])
        if own is not None and own != name:
            continue
        targets.append(extra)
```

Обязательные свойства правила (все три — повод остановиться, если не выполняются):

1. `stem == t` (точное совпадение) всегда выигрывает; префикс засчитывается только по границе `_`.
2. Если `_owner` вернул `None` (стем не начинается ни с одного инструмента) — файл **остаётся** у текущего `name`. Именно поэтому `test_api_snapshot.py` остаётся у `api`: `api_snapshot` не инструмент, longest-prefix даёт `api`, а `api == name`.
3. `test_scene_ops_bridge.py` уходит к `scene_ops` (а не остаётся у `scene`), поэтому `scene_model.tree` = **116**, а не 128.

Где взять `tools`: если в `check_unit` нет `loaded` — допустим один модульный кэш `_TOOLS = None` и ленивый вызов того же `discover()`, что уже используется в файле (без новых импортов `os/pathlib`, без чтения диска вручную). Никаких исключений по именам модулей и никаких хардкодов `api_check`/`scene_ops` — правило должно быть одно.

Эталонный результат (проверяется пином и таблицей 44 механик): `engine_kb.class_api` **186 → 128**, `scene_model.node_info` **352 → 247**, `scene_model.tree` **168 → 116**; остальные 41 механика — **тот же счёт, тот же состав, тот же порядок**. Если правило даёт четвёртую дельту — не подкручивать, а остановиться и вынести в лист.

### B2 — разрешено: протокол отчётов `reports/selfcheck/*.json`

Требование «44 отчёта равны baseline, кроме трёх» из §5 невыполнимо буквально: каждый прогон `selfcheck` перезаписывает отчёт вместе с длительностью pytest. Разрешаю ровно этот порядок:

1. Прогнать все 44 механики последовательно, **каждый** отдельным процессом `python -B -X utf8 tools/selfcheck.py <id> --json`.
2. Свежие отчёты и stdout сложить во внешний архив (`C:/Users/Lich/AppData/Local/Temp/opencode/c19-…/fresh/<id>.json` + `.stdout.txt`) и снять sha256 по каждому.
3. Для **41 неизменной** механики вернуть `reports/selfcheck/<id>.json` **побайтово** из baseline-бэкапа (`counts-before/<id>.report.json`), сверив sha256 до и после копии.
4. У **трёх изменённых** (`engine_kb.class_api`, `scene_model.node_info`, `scene_model.tree`) оставить свежие отчёты, в которых `unit` = 128 / 247 / 116.
5. JSON руками не править, длительности не нормализовать, baseline-бэкапы не удалять.

Доказательство: список 44 файлов с «baseline sha256 → финальный sha256» в листе и WORKLOG, из них 41 совпадает с baseline побайтово, 3 отличаются и содержат новые счётчики; сам приём (архив + побайтовый возврат) описан в ADR-0013 абзацем «длительность в отчёте — не контракт».

### Что остаётся в силе

`snapshot_diff` 820/0, корпуса, карточки контракта и `tools/selfcheck.py` вне `check_unit` не меняются; `test_api_snapshot.py` остаётся у `api`; мутации M1–M3 из §5 и подложка P1 остаются, M2 переформулируется под новое правило (исключение только для `api_check` → краснеют `node_info`/`tree`); ADR-0013 из `proposed` в «принято»; передача — «C.19 готов к независимому аудиту, не принято» плюс sha256-список и таблица 44 механик «было / стало / дельта».
