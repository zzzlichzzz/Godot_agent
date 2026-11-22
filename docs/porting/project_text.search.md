# project_text.search — поиск подстроки по проекту

**Статус:** этап `7` (ported; см. `docs/PROGRESS.md`)
**Обновлено:** `2026-10-27`

## Цель

Клиент (модель, панель, другой модуль) спрашивает: «где в файлах проекта встречается
такая-то подстрока?» — и получает список совпадений с путём `res://…`, номером
первой строки и сниппетом с контекстом, плюс флаг «список обрезан квотой». Поиск
ищет литеральную подстроку (не регулярное выражение), уважает политику путей
(аддоны и исходники самого агента скрыты по умолчанию), набор индексируемых
расширений и квоту `max_results`. Ничего не пишет.

## Старый код

| Файл | Что делает | Как делим |
|---|---|---|
| `python/godot_tools/project_tools.py:1132-1267` `search_project_text()` | обход проекта, фильтр расширений, `exclude_rel_prefixes`, `case_insensitive`, склейка соседних совпадений в окно `context_lines`, квота на подстроку, флаг `truncated` | ядро → `modules/project_text/search/domain/core.py` (чистые функции: кандидат по расширению, разбор текста, окна, квота, обрезка строки) |
| `project_tools.py:1084-1109` `SEARCH_EXTS`, `AGENT_ONLY_SEARCH_EXTS`, `search_extensions_for()` | набор расширений + `.py` только в developer mode | `domain/core.py` (набор) + `kernel/paths.py` (решение о `.py` — право, а не расширение) |
| `project_tools.py:1112-1129` `SNIPPET_LINE_MAX`, `_clip_snippet_line()` | обрезка слишком длинной (minified) строки сниппета с пометкой полной длины | `kernel/text.py: clip_snippet_line()` + `kernel/limits.py: SNIPPET_LINE_MAX` |
| `project_tools.py:1187-1197` (`os.walk`, `EXCLUDED_DIRS`, `_filter_project_scan_entries`) | обход: сортировка, скрытые каталоги, шумовые каталоги, отсев по политике | обход — в адаптере `substrate/fs/disk_fs.py` (порядок и «не ходить по ссылкам»), шумовые каталоги — `domain/core.py`, политика (аддоны/агент) — `kernel/paths.py` |
| `project_tools.py:423-462` `_path_access_allowed`, `can_read_project_path()` | что вообще можно читать: аддоны только с флагом, `.py` агента — только в self-edit, история проекта и `project.godot` на запись запрещены | `kernel/paths.py: PathPolicy` (R-13), в срезе — только `can_read` |
| `project_tools.py:1199-1223` (BOM/CRLF/ошибки чтения) | `utf-8-sig`, `errors='replace'`, `\r\n`→`\n`, нечитаемый файл пропускается | адаптер `disk_fs.read_text()` (BOM, кодировка) + `domain/core.py` (`normalize_newlines`) |

Остальные семь частей `project_tools.py` (дерево, чтение/патч, move/copy,
`describe_scene`, обзор проекта, снапшоты, `kernel/diff.py`) — не эта механика.

## Старые тесты

| Файл | Семейство | Судьба | Что взяли |
|---|---|---|---|
| `test_search_quality.py` | unit (харнесс качества) | **не эта механика** | Это recall@8/MRR@8 по индексу Библиотекаря (`minilich.ml_project_index`) с золотым набором 150 пар; в `docs/tests-map.md` строка отнесена к `context.gather`. Для `project_text.search` кейсов не даёт — берём их из `test_librarian.py` (там прямой вызов `search_project_text`) |
| `test_librarian.py:551,558,1210-1224,1353-1371` | unit | corpus | вызовы `search_project_text` слоями FRAGMENTS/CALLERS/SIGNALS: квоты, `context_lines=0`, метка `needle` |
| `test_path_policy_safety.py:163,239,249` | unit | corpus | «аддоны и `.py` агента скрыты по умолчанию» |
| `test_scan_policy_cost.py:154-174` | unit | corpus (частично) | стоимость обхода: шумовые каталоги не сканируются (`.godot`, `node_modules`, `__pycache__`) |
| `test_project_settings_actions.py` / `…_flow.py` | unit/flow | не эта механика | правки `project.godot` — это `project_ops.settings_*` |

## Корпус

| Что снято | Откуда | Файл |
|---|---|---|
| 16 кейсов: happy path; пустой результат; кириллица в запросе и в пути; `case_insensitive=true`; `exclude_rel_prefixes`; `max_results=1`; файл с BOM; файл с CRLF; `.py` вне набора расширений; `.png` вне набора; minified-строка (обрезка 300 символов); аддон (политика); шумовой каталог `.godot`; пустой запрос; `context_lines=0` | старый агент: `godot_tools/project_tools.py:search_project_text()` на `fixtures/projects/minimal/`, запуск `python -B` (без записи байткода в эталон) | `fixtures/corpus/project_text/search/*.json` + `manifest.json` |

Формат записи (Q-21): один файл на кейс — `{id, tool, fixture, note, args, expect: {ok, result}}`;
`expect` пишет `tools/snapshot_record.py`, руками не правится (иначе это не эталон, а мнение).
Пути нормализованы (`<PROJECT>` в манифесте, в выдаче — `res://…`), абсолютных путей нет
(проверено обходом JSON: 0 совпадений `[A-Za-z]:[\\/]` в 17 файлах). `manifest.json` фиксирует
`schema_version`, дату, `reference.sha256` старого файла и sha256 каждого кейса.

Чего в корпусе нет и почему:

- пакетный `needles` — внутренний API `context.gather`, в срез не входит (см. «Решения по ходу»);
- `allow_addons` / `allow_self_edit` — это capability-флаги панели, а не аргументы инструмента;
  закрытость аддонов проверяется кейсом 011 end-to-end;
- файлы больше 4 МиБ — лимит `READ_TEXT_MAX_BYTES`, это бюджет (R-09), а не наблюдаемое паритета.

## Спецификация

`ToolSpec` в `python/modules/project_text/search/tools.py` (источник правды, ADR-0006);
`contract/capabilities/search.json` — сгенерированный артефакт (`python tools/gen_contract.py --check`).

- имя: `search`; `effects="read"`; `idempotent=True`; `requires_preview=False`; `availability="*"`; `cost="cheap"`;
- аргументы: `query` (string, обязательный), `max_results` (integer 1..200, по умолчанию 30),
  `context_lines` (integer 0..20, по умолчанию 2), `exclude_rel_prefixes` (массив строк),
  `case_insensitive` (boolean); `additionalProperties=False`;
- результат: `{matches: [{path, line, snippet}], truncated: bool}`; `additionalProperties=False`;
- ошибки: `invalid_input`, `not_found`, `denied`.

Инварианты (R-20/SEC):

| ID | Как обеспечен здесь | Чем проверен |
|---|---|---|
| SEC-18 (объём) | `max_results ≤ 200`, `context_lines ≤ 20` в схеме и в `app._check_ranges`; файл больше `READ_TEXT_MAX_BYTES` (4 МиБ) не читается — `disk_fs.read_text` | contract-тест (схема), `check_limits.py` |
| SEC-12 (выход за корень) | `kernel.paths.normalize_rel` (отказ на `..`, абсолютный путь, NUL) + `realpath`-проверка в `disk_fs._resolve`, симлинки при обходе не разыменовываются | код + `lint_arch`; отдельный атакующий набор — открытый вопрос Q-32 |
| SEC-13 (секреты/пути в выдаче) | в ответе только `res://` пути и `snippet`; ошибки — `kind/message/hint` без стектрейсов, корни редакции `redact_paths` | contract-тест `test_os_error_is_redacted_to_kind_and_no_path` |
| R-15 (типизация) | `protocol/error_map.from_exception` — единственная классификация; `Dispatcher` не пропускает сырых исключений | contract-тест (`unknown_tool`, `invalid_input`) |

Наблюдаемая особенность эталона, сохранённая намеренно: попадание ровно в квоту (совпадений
ровно `max_results`) тоже даёт `truncated=true` — кейс 006 корпуса. Это не улучшение и не баг
переноса; кандидат на `deviations.md` записан как Q-31.

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-10-27 | Корпус хранится в репозитории (`fixtures/corpus/project_text/search/`), а не в артефактах CI — Q-19 | Кейсов 16, каждый < 20 КБ; без корпуса в репозитории `snapshot_diff` и `selfcheck` невоспроизводимы у следующего чата (R-07/R-18) |
| 2026-10-27 | Аргумент `needles` (пакетный поиск для Библиотекаря) в срез **не входит** | Это внутренняя оптимизация `context.gather` (12–24 обхода на ответ), а не клиентский контракт; `context.gather` не портирован. Одиночный `query` — тот же код, поведение не меняется |
| 2026-10-27 | Формат корпуса — Q-21 решён: один JSON на кейс (`args` + `expect`), `manifest.json` с хешами (см. «Корпус») | Кейс самодостаточен: `snapshot_diff` не нужен отдельный список входов, а подмена `args` руками сразу видна как расхождение с `expect` |
| 2026-10-27 | Q-23 решён: `pytest>=8` в `[project.optional-dependencies] dev`, прогон `python -m pytest`; режим `--import-mode=importlib` | У 44 фич одинаковое имя `python/modules/*/*/tests/test_core.py`; в обычном режиме pytest падает на дублях имён, а не на коде. Тесты не попадают в рантайм агента |
| 2026-10-27 | Появился `tools/run_tests.py`: pytest не печатает JSON-вердикт, а `selfcheck` без вердикта считает проверку невыполненной | Иначе `unit` честно даёт `not_implemented` и вердикта по механике нет (R-18) |
| 2026-10-27 | Граница: шумовые каталоги (`.godot`, `__pycache__`, `node_modules`) — домен поиска; аддоны и исходники агента — `kernel.paths.PathPolicy` | Шум — это качество выдачи (имеет право меняться по области), аддоны — право доступа (R-13), одна точка решения |
| 2026-10-27 | `.py` — не расширение, а право: `PathPolicy.agent_py_allowed` (нужны и `allow_self_edit`, и известный корень агента) | Иначе поиск стал бы способом прочитать исходник агента в обход developer mode (набор fail-closed) |
| 2026-10-27 | `redact_paths` в `kernel/text.py` чинит экранированный вид пути (`D:\\proj` внутри `repr(OSError)`) | Contract-тест поймал: корень в тексте ошибки ОС печатается с удвоенными разделителями, и простая замена не срабатывала |
| 2026-10-27 | `tools/probe.py` получил `--args-file` | PowerShell 5.1 съедает кавычки JSON и рвёт аргумент по пробелу внутри строки (`"func _ready"`); содержимое файла — тот же JSON, поведение агента не меняется |
| 2026-10-27 | Каркас (kernel/substrate/runtime/protocol/channels) написан по спецификации ADR-0003, а не переносом | Это единственное место, где допустим код «по спецификации»; после второго модуля (`code_intel.functions`) ожидается переделка — это нормально, а не регресс |
| 2026-10-27 | **Правка аудита A:** вопросы среза перенумерованы `Q-28 → Q-31`, `Q-29 → Q-32` | Номера Q-28/Q-29 были заняты браузерной веткой (сессия 8); одинаковый номер для двух вопросов ломает поиск по журналу (R-19) |
| 2026-10-27 | **Правка аудита B:** квоты поиска (`SEARCH_MAX_RESULTS`, `SEARCH_MAX_CONTEXT_LINES`, `SNIPPET_LINE_MAX`) перенесены из `kernel/limits.py` в `modules/project_text/search/settings.py`; `kernel/text.clip_snippet_line(line, limit)` больше не имеет значения по умолчанию | Ядро не должно знать про поиск: `kernel` = универсальные лимиты, квота = параметр фичи (R-11). Значения совпали с эталоном, корпус 16/16 без изменений |
| 2026-10-27 | **Правка аудита C:** `ctx.path_policy` внесён в ADR-0003 как поле контекста; зафиксировано, что поверхность `ModuleContext` — закрытый список | Поле было в коде, но не в ADR: без записи следующий модуль добавит себе что угодно «по аналогии» |
| 2026-10-27 | **Правка аудита D:** расхождение R-03 (`unknown_tool` вместо `unavailable` для отключённого модуля) перенесено из «Блокеров» этого листа в `docs/PROGRESS.md` → раздел «Долги» | Лист читают ради одной механики; нарушение правила видно всем и живёт в индексе, а не в приватной заметке. В `deviations.md` не пишется: там отличия от **старого агента**, а это долг перед собственным правилом |
| 2026-10-27 | **Правка аудита E:** в `docs/tests-map.md` строка `test_scan_policy_cost.py` (`replaced`) получила примечание, что часть кейсов ушла в корпус поиска | Иначе через месяц это выглядело бы как тихо потерянное покрытие (R-17) |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-27 | 1. лист создан | прочитаны `godot_tools/project_tools.py` (поиск `1132-1267`, расширения `1084-1129`, политика `423-462`), `test_search_quality.py`, `test_librarian.py` (места вызова), `docs/tests-map.md`, `docs/mapping.md` |
| 2026-10-27 | 2. корпус | `fixtures/projects/minimal/`: 13 файлов (`project.godot`, `README.md`, `scripts/{player,health_hud,legacy_bom,crlf_line}.gd`, `scenes/player.tscn`, `notes/здоровье.md`, `data/levels.json`, `tools/build.py`, `assets/atlas.png`, `addons/other_plugin/plugin.gd`, `.godot/editor/state.cfg`); 16 кейсов; `python tools/snapshot_record.py --corpus fixtures/corpus/project_text/search --reference '<эталон>/python'` → `{"status": "ok", "detail": "корпус снят: 16 кейсов"}`; в эталоне `__pycache__` не появился (сверка списков до/после прогона внутри `snapshot_record`) |
| 2026-10-27 | 3. спецификация + тесты | `tools.py: SEARCH`, `contract/capabilities/search.json` сгенерирован `gen_contract.py --write`; `modules/project_text/search/tests/test_core.py` — 14 тестов домена (литеральные тексты из кейсов); `tests/py/contract/test_search_contract.py` — 15 проверок (схема, `kind`, дубль `tool_name`, редакция путей). Всего `29 passed` |
| 2026-10-27 | 4. код | `ports.py` (`FileSystem`: `list_files`/`read_text`) → `domain/core.py` (расширения, шум, префиксы, окна, квота, обрезка) → `app.py` (64 строки: диапазоны → домен → порт → результат) → `module.py` (`provides_tools=("search",)`, `requires_ports=("fs",)`); каркас: `kernel/{errors,result,limits,text,paths,schema,tool_spec,module_spec,ids}`, `substrate/fs/{disk_fs,memory_fs}`, `runtime/{bootstrap,context,module_loader}`, `protocol/{registry,validation,dispatch,error_map}`, `channels/mcp/{server,stdio}` |
| 2026-10-27 | 5. двойной прогон | `python tools/snapshot_diff.py` → `fixtures/corpus/project_text/search  кейсов 16, совпало 16, расхождений 0`; повторён в `selfcheck` после правки `redact_paths` — тот же результат (16/16) |
| 2026-10-27 | 7. аудит аудитором (независимый прогон) | Подтверждено своими командами: `selfcheck` exit 0 (module/layers/limits/contract/security/unit/corpus), `snapshot_diff` 16/16, MCP-канал вручную (`initialize` → `tools/list` → `tools/call nope` → `isError`, exit 0), `tests-map.md` 168 строк, в эталоне 12 `__pycache__` — все старые (21.09–27.10 01:32), домен без `os`/`pathlib`, размеры 141/65/92/18. Найдено 5 замечаний (A–E) — все внесены: самопроверка после правок снова exit 0, файлов 429 |

## Проверки

Вердикт `python tools/selfcheck.py project_text.search` (exit `0`), отчёт —
`reports/selfcheck/project_text.search.json`:

```
selfcheck project_text.search
  module         ok              project_text.search
  layers         ok              файлов 428, нарушений нет
  limits         ok              файлов 428, предупреждений 0
  contract       ok              артефактов 1, расхождений нет
  security       ok              нарушений нет
  unit           ok              29 passed in 0.44s
  corpus         ok              кейсов 16, расхождений нет
вердикт: ok
```

Отдельно: `python tools/snapshot_diff.py` → `{"status": "ok", "detail": "кейсов 16,
расхождений нет"}`; `python tools/security_audit.py` → `ok`; `python -B` при прогоне
эталона, правок в старом плагине нет (свежие mtime под `тест-плагина-ии` — только
`.git`-метаданные чужого `git fetch` в 17:12, исходники плагина не тронуты).

## Следующее действие

Следующая механика — `code_intel.functions`:

1. создать лист `docs/porting/code_intel.functions.md` (R-19) и прочитать
   `godot_tools/gd_functions.py` в эталоне;
2. снять корпус в `fixtures/corpus/code_intel/functions/` (кейсы из
   `test_gdscript_wiring.py`, R-16) — до первой строки кода;
3. затем `modules/code_intel/functions/{tools,ports,app,module}.py` + `formats/gdscript.py`;
4. вердикт: `python tools/selfcheck.py code_intel.functions`.

## Блокеры

| Что мешает | Кто решает |
|---|---|
| Инструмент **отключённого** модуля сейчас отвечает `unknown_tool`, а не `unavailable` с причиной (R-03): реестр не помнит имена из `contract/`. На `search` не влияет (единственный живой модуль), но станет заметно на втором модуле | следующий срез: `code_intel.functions` — там впервые появятся два инструмента; чинить в `protocol/registry.py` + `runtime/bootstrap.py` |
