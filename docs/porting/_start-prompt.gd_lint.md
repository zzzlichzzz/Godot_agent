# Срез C.2 — механика `verification.gd_lint`

Ты портер Godot-агента в `D:\vajno\Godot\agent-rebuild\addons\godot_agent` (не путать со старым
плагином `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent` — он только читается).
Это **первый срез после форматного слоя C**: парсер `.tscn/.tres` готов и принят аудитом, теперь
пора превратить линт GDScript в настоящую механику агента. Эталон — `python/godot_tools/gd_lint.py`
(191 строка). Механики до этапа 7 доводятся по `RULES.md` (R-17/R-18/R-19/R-22), лист механики
создаётся **до** первой строки кода.

## 0. База на старте (мой замер, аудит 2026-10-29, сессия 46)

```powershell
cd 'D:\vajno\Godot\agent-rebuild\addons\godot_agent'
$env:PYTHONDONTWRITEBYTECODE=1
python -m pytest python/modules tests/py --ignore=tests/py/live -q -p no:cacheprovider
python -m pytest tests/py/live -q -p no:cacheprovider        # ~20 c, дроби при лимите 30 с
python -m pytest tests/py/formats -q -p no:cacheprovider     # 100
python tools/gen_contract.py --check                         # артефактов 9
python tools/snapshot_diff.py                                # кейсов 102, расхождений нет
python tools/lint_arch.py ; python tools/check_limits.py     # 453 файла, 0 нарушений
python tools/security_audit.py                               # ok
python tools/selfcheck.py editing.scene_ops                   # ok, unit 25, corpus live
```

Мои числа: non-live **532** (43 файла, `--collect-only` даёт ту же сумму), live **3** (2.6/12.7/5.2 с,
Godot `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`), формат-тесты **100**
(17 gd + 83 новых). Файлов **933** — этот промпт добавляет один, значит у тебя на старте **934**:
запиши своё число, а не моё. Правил 22, листов механик 10, промптов 22.

Хеши-инварианты (не должны сдвинуться ни на байт):
`schema.py 629FCE54E6FE`, `lint_arch 1FAD8E7470D5`, `gen_contract FA7E6E91C872`,
`security_audit 2CF0D7F6B1AF`, `editor_verbs.json CDAF8D23A6BF`, `scene_executor.gd B7AFF592B75D`,
`python/formats/tscn.py BF844574D6E5` (6698 Б, lf=167/crlf=0).

Гигиена на старте: `__pycache__` 0, `.pytest_cache` 0, `*.bak/*.tmp/*.orig` 0, `zz_*` 0.
Старый плагин: `git status --porcelain` — ровно два чужих `??` (`python/_ref2.log`,
`python/godot_tools/_excl.log`), `git diff` пуст. Их не удалять. Git в `agent-rebuild` нет намеренно.

## 1. Границы среза

В срезе:
- лист механики `docs/porting/verification.gd_lint.md` (по `_template.md`, **первым делом**);
- модуль `python/modules/verification/gd_lint/` (`module.py`, `tools.py`, `app.py`, `domain/`,
  `ports.py`, `tests/`), `ModuleSpec.corpus = "corpus"`;
- корпус `fixtures/corpus/verification/gd_lint/` — снят с эталона, не подогнан;
- новая capability-карта `contract/capabilities/gd_lint.json` (после неё `gen_contract --check`
  даст **10** артефактов — это ожидаемо, не «сломалось»);
- тесты механики (`python/modules/verification/gd_lint/tests/`, общий `tests/py/integration/…` при
  надобности), строка `docs/tests-map.md:65` (`test_gdscript_wiring.py`, 41 проверка) — уже отдана
  этой механике, её судьбу не менять без прогона R-09/R-10;
- записи `docs/WORKLOG.md`, `docs/PROGRESS.md`.

Не в срезе: агрегатор `verification.check` и его findings, `verification.tscn_lint`,
`verification.api_check`, `verification.headless`, `verification.action_judge`,
`verification.runtime_checks`; любые `scene_model.*`; правки `python/formats/**` (в том числе
`tscn.py` и `gdscript/`) — линт их **использует** только если это правда нужно, и тогда пишет об
этом; `contract/**` кроме нового `gd_lint.json`; `# verb:`, `editor/**`, `runtime/**`;
неизменяемые `tools/lint_arch.py`, `tools/gen_contract.py`, `tools/security_audit.py`,
`python/kernel/schema.py`; уже принятые механики и их корпуса.
**Наследство части C (не твоё, но не потеряй).** `patch` в `tscn.py` намеренно не диагностирует
пересекающиеся правки — это требование к первому потребителю записи (`scene_model.node_rename`),
а не к линту: не «починяй» `tscn.py` по дороге и не заводи на это тест в своём срезе. Форматный
корпус `fixtures/parity/tscn/` (16 файлов, ожидания сняты с эталона, `tscn.py BF844574D6E5…`)
закрыт и неприкосновенен. Новые формат-тесты в `tests-map.md` не заводились (прецедент
`test_gdscript_parity.py`) — свои тесты фиксируй в листе механики и в `PROGRESS`, не в `tests-map.md`.



## 2. Контракт и раскладка (якоря эталона: файл:строка)

`gd_lint.py`: `MAX_ERRORS = 8` `:13`; `_PAIRS` `:15`; `_FUNC_RE`/`_CLASS_RE` `:16-17`;
`_VAR_TYPED_RE` `:24`; литералы `:25-30`; `_TYPE_ALLOWED_LITERALS` `:33`; RU-таблицы `:39-40`;
`_literal_kind(rhs)` `:50`; `lint_gdscript(text)` `:69-191`.

Поведение, которое обязано совпасть (это не «улучшения», это эталон):
1. Пустой/пробельный текст → одна находка «итоговый файл получился пустым».
2. `\ufffd` в тексте → находка о побитом тексте, разбор продолжается.
3. Сканер идёт посимвольно: строки в одинарных/двойных кавычках, тройные кавычки, `\`-escape,
   комментарий `#` до конца строки, стек скобок `([{`, несовпадение по `_PAIRS`, лишняя
   закрывающая, незакрытая на конце — с номером строки в тексте находки.
4. Незакрытая кавычка закрывается на переводе строки и даёт находку с номером строки начала.
5. `var x: int|float|bool|String = <литерал>` — проверка вида литерала (`_literal_kind`), при
   несовпадении находка; выражения/переменные/вызовы не трогаются (`None` от `_literal_kind`).
6. Ограничение `MAX_ERRORS` — после него разбор останавливается.

Форма ответа (наше решение, фиксируется в листе §4): находки — **данные**, не проза:
`{"findings": [{"code": "<латиница, стабильный id>", "line": <int|null>, "message": "<строка эталона дословно>"}], "truncated": <bool>, "checked_bytes": <int>}`.
Порядок находок = порядок эталона. Паритет сравнивает **последовательность** `(code, line, message)`
и `truncated`; коды выдумывать нельзя — словарь кодов живёт в `domain/` и в листе.

Раскладка по R-06/R-11: `app.py` ≤ 80 строк и только оркестрация, `tools.py` ≤ 150 (один ToolSpec
на файл, как в `editing/write_preview`), `domain/` без IO (`os`, `pathlib`, `socket`, `subprocess`
запрещены — это ловит `lint_arch`), `ports.py` с `typing.Protocol` для чтения файла проекта,
привязка в `runtime/bootstrap.py`. `io`/чтение — только через порт и существующий `fs`.
Логика — **один** экземпляр: второго сканера GDScript в `python/**` быть не должно (эталонный
`gd_lint` в старом плагине не копируется и не импортируется — R-16/R-07).

## 3. Шаги

1. **Лист механики** `docs/porting/verification.gd_lint.md` по `_template.md`: цель, старый код
   (`gd_lint.py` — что делает, как делим), старые тесты (строка `test_gdscript_wiring.py` из
   `tests-map.md:65` и что из 41 проверки действительно относится к линту), корпус, ToolSpec и
   инварианты, решения, ход работы, проверки, следующее действие, блокеры. Статус — этап 1.
2. **Корпус до кода.** `fixtures/corpus/verification/gd_lint/` — кейсы как в существующих корпусах
   (`fixture` + `args`), ≥ 14 штук: чистый файл; пустой; пробельный; незакрытая кавычка; незакрытая
   скобка; лишняя закрывающая; несовпадение пары; `\ufffd`; строка с `#` внутри кавычек; комментарий
   после кода; тройные кавычки с `{`/`(` внутри; `var x: int = "s"`; `var x: float = 5`;
   `var x: bool = "true"`; файл с более чем 8 находками (`truncated`); CRLF; BOM. Ожидания снимаются
   вызовом настоящего `gd_lint.lint_gdscript` из **старого** каталога одноразовым `python -B`-скриптом
   (обычные импорты старого `_bootstrap`; `sys.path` = `godot_tools`, `python/parsers`, `python` —
   `project_tools` тянет `text_sanitize`), скрипт после снятия **удаляется**; в корпусе остаётся
   `manifest.json` с датой, commit, sha256 и размерами входов и эталонного файла.
3. **Тесты до кода**: паритет находок с корпусом (последовательность `(code, line, message)` +
   `truncated`), тест «словарь кодов ⊇ коды находок», тест лимита `MAX_ERRORS`, тест «находки — данные,
   не команда» (R-20), тест «`domain/` без IO». На заглушке они красные — зафиксируй `N tests,
   M failures, exit 1`.
4. **Код**: `domain/` (сканер, словарь кодов, сборка находок), `tools.py` (ToolSpec `gd_lint`,
   `effects="read"`, вход `{path}` внутри проекта через `PathPolicy`), `app.py` (оркестрация),
   `module.py` (`MODULE`, `provides_tools=("gd_lint",)`, `corpus="corpus"`), `ports.py`, привязка в
   `runtime/bootstrap.py`. Отказы типизированные: `invalid_input` для пути вне проекта; слишком
   большой файл — по существующим лимитам (`SEC-18`); если лимита на размер файла нет, объяви его в
   листе и в контракте, а не молча.
5. **Контракт**: `python tools/gen_contract.py` (не `--check`) создаёт `contract/capabilities/gd_lint.json`;
   затем `--check` обязан дать `артефактов 10, расхождений нет`.
6. **selfcheck** `python tools/selfcheck.py verification.gd_lint` — зелёный (unit + corpus).
7. **Записи**: лист до этапа 7, `PROGRESS.md` (строка механики + при нужде долг), `WORKLOG.md`
   (сессия), строка `tests-map.md:65` — только если решил её судьбу прогоном.

## 4. Решения, которые примешь сам (и запишешь в лист §4)

- Имена кодов находок (латиница): словарь в листе §4 и **одно** место в `domain/`. RU-сообщения —
  данные (корпус), не строки в ветвлениях кода.
- Находки, которые в эталоне не отделены кодом: одинаковый `message` → один код.
- `checked_bytes` — байты исходного файла, не символы: так честнее для лимитов.
- Странности эталона (порядок проверок, ложные срабатывания) переносятся **как есть** (R-08) и
  записываются в лист.
- Автоисправлений и записи в файл нет: `effects="read"`.


## 5. Чем доказывается (мутации и подложки, строго по одной)

- Бэкап сдаваемого файла — `shutil.copyfile` в `%TEMP%`, sha256 до/после, восстановление
  побайтовое, `restored identical: True`, EOL сохранён.
- M1: убрать проверку пары скобок (`_PAIRS`) → красный паритет на кейсе несовпадения пары.
- M2: не закрывать незакрытую кавычку на переводе строки → красный кейс незакрытой кавычки.
- M3: снять ограничение `MAX_ERRORS` → красный кейс `truncated`.
- Подложка в инструмент: добавить в `tools.py` поле, которого нет в `contract/capabilities/gd_lint.json`
  → `gen_contract --check` обязан упасть; убрать.
- Подложка в корпус: испортить одно ожидание в корпусе → паритет краснеет ровно на этом кейсе.
- Мутация, которая ничего не покрасила, — незакрытое требование: либо тест, либо отказ от ветки.

## 6. Стоп-условия

- Старый плагин только читается: `python -B`, дампы в `%TEMP%`, два чужих лога не трогать; после
  среза `git status --porcelain` — те же две строки, `git diff` пуст.
- `gen_contract --check` = ровно 10 артефактов; `snapshot_diff` = 102/0 (корпуса писателей не
  менялись); `lint_arch`/`check_limits` 0 нарушений; `security_audit` ok; `selfcheck
  editing.scene_ops` остаётся зелёным.
- Общее число тестов = сумме `--collect-only`; live-набор остаётся **3** (линт — read-механика;
  если решишь иначе — обоснуй в листе).
- Двух мутаций одновременно нет; `PYTHONDONTWRITEBYTECODE=1` в каждой команде; JSON только через
  `--args-file`; команда дольше 30 с — дроби, вывод в файл; stderr — в файл, не в консоль.
- Git в `agent-rebuild` не инициализируется.

## 7. Что проверит аудитор

Свои прогоны, не твои числа: non-live, live, `--collect-only`, `gen_contract --check` (10),
`snapshot_diff`, `lint_arch`, `check_limits`, `security_audit`, `selfcheck verification.gd_lint`;
пересъёмка корпуса с эталона своим скриптом; своя мутация на сдаваемом файле с байтовым бэкапом и
сверкой sha256; подложка в инструмент/контракт; чтение кода (лимиты 400/150/80, IO в `domain/`,
единственный экземпляр сканера — поиск `_PAIRS`/`lint_gdscript` по `python/**`); гигиена
(`__pycache__` 0, `zz_*` 0); байтовая неизменность старого плагина и хешей-инвариантов.

## 8. Финальный прогон и записи

```powershell
python -m pytest python/modules tests/py --ignore=tests/py/live -q -p no:cacheprovider --junitxml=$xml
python -m pytest tests/py/live -q -p no:cacheprovider        # 3 passed
python -m pytest ... --collect-only -q                       # сумма == junit
python tools/gen_contract.py --check                         # артефактов 10
python tools/snapshot_diff.py                                # 102/0
python tools/lint_arch.py ; python tools/check_limits.py ; python tools/security_audit.py
python tools/selfcheck.py verification.gd_lint                # ok
```

Записи: `WORKLOG.md` — сессия с числами, мутациями и честными границами; `PROGRESS.md` — строка
`verification.gd_lint` (этап и доказательства) и, если что-то осталось, строка долга; лист
механики — этап 7 и «Следующее действие» одной строкой; `docs/porting/README.md` и
`_audit-handoff.md` правит **аудитор**, не ты.

