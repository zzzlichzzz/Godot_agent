# editing.paths_preview — ссылки на путь и проекция внутренних путей

**Статус:** этап `0`; назначается аудитором, `skeleton` сохранён.
**Обновлено:** `2026-11-02`

## Цель

C.21 реализует один `paths_preview(old_path, new_path)` по решениям D1–D8:
поиск ссылок и read-only проекцию без записи. Функции prepare_*/apply, физический
перенос каталога, case-only rename и external sync остаются C.22. Локальный
selfcheck зелёный; полный non-live остановлен двумя глобальными соседними пинами (§13).

## Старый код

Эталон только читается: `D:/vajno/Godot/random-game/addons/godot_agent`.

| Файл | Что делает | Как делим |
|---|---|---|
| `python/godot_tools/file_refactor.py` | normalize:46, read:76, find:87, internal:181; prepare:591 | портируются read-части; prepare-функции только наблюдались как native oracle |
| `python/tools/agent_bridge.py:833–877` | `paths preview old new` вызывает prepare | публичная read-only preparation разрешена D1 |
| `python/tools/godot_agent_mcp.py:356–360` | публичный `paths_preview(old_path, new_path)` | не два инструмента и не `op`-мультиплексор |
| `python/godot_tools/project_tools.py` | containment и независимые флаги доступа | сравнить с существующей PathPolicy, не дублировать адаптер |

Прочитаны обязательные документы AGENTS/RULES, architecture, PORTING, parity,
tests-map, PROGRESS, WORKLOG («Где остановились» и приёмка C.20), NOTES;
mapping, security/invariants и ADR-0005/0006/0013/0015, лист split_py и оба
стартовых промпта; эталон file_refactor целиком, native MCP/bridge и тест-кейсы,
скелеты модуля, shared/funnel и script_edits, fs, kernel paths/write_plan,
селектор selfcheck. Отсутствие этого листа до C.21 явно отмечено как дефект.

## Старые тесты

| Файл | Семейство | Судьба | Что взяли |
|---|---|---|---|
| `test_file_refactor.py` | unit | `corpus` (владельцем остаётся `editing.file_refactor`) | find, lexical exact/relative, внутренние пути, map каталога; только кейсы, не код |
| `test_agent_bridge.py` | unit/host-bridge | `replaced` (владелец `protocol/dispatch`) | прочитаны preview без переименования и missing-source:380–439; судьба не изменена |

D1–D8 получены до реализации. Из старых тестов взяты кейсы, не код;
исторические строки tests-map не переписываются. Финальные строки новых тестов
будут добавлены после устранения STOP §13 и полного зелёного прогона.

## Корпус

Добавлены 25 карточек `fixtures/corpus/editing/paths_preview` и три собственных
проекта basic/projection/directory. Корпус снят до production: 50 реальных native
вызовов, ответы двух прогонов равны, байты фикстур неизменны. Полные raw/tuple/bytes
результаты oracle остаются во внешнем досье; проекция карточек ровно D4/D5.

## Спецификация

- Один ToolSpec `paths_preview`: read, idempotent=True, requires_preview=False,
  два строковых аргумента, строгий результат D4; `op` и helper-инструментов нет.
- Consumer-owned `paths_fs`: list_files/read_raw/is_file/exists. Чистый domain,
  app только оркестрация (17 строк). ReadOnlyFileSystem в substrate/fs и binding
  runtime/bootstrap: локальные 5 MiB, общий DiskFileSystem/default4MiB не изменён.
- Расширения буквально `(".gd", ".tscn", ".tres", ".gdshader", ".gdshaderinc")`,
  плюс точное имя project.godot; native exact/relative regex, grouped char offsets.
- utf-8-sig / fallback replace, BOM-флаг, CRLF/lone CR сохраняются; shared.decode
  и normalize_newlines не используются. uid:// и немаппированные missing неизменны.
- Отказы D5; чтение plugin.cfg разрешено. Нет funnel, WAL, journal, lock и write API.
- Контракт27; canonical reports44, изменён только фактически прогнанный paths_preview.

## Исходные SHA256 до правки

Полный внешний byte-backup всех 3265 исходных файлов: `baseline.zip`.
Индекс всех файлов/каталогов и всего frozen-эталона: `baseline.json`, SHA256
`a3ff7d5ecaa88db7bec0fc33ef608befd67e9f1d7ebc2896175d7ec47d585ccb`.
Папка досье: `%LOCALAPPDATA%/Temp/opencode/c21-paths-preview-20261101/`.
Новые лист/корпус/тесты до правки отсутствуют; все будущие правки существующих
файлов сверяются с этим индексом, а не с повторно снятой «базой».

| Исходный файл | B | SHA256 |
|---|---:|---|
| `python/modules/editing/paths_preview/module.py` | 502 | `d3e875a9d0eb664127167ff30c20c37e40e7da5527272505fa862f67253a2600` |
| `python/modules/editing/paths_preview/tools.py` | 382 | `7f6c6e0d65a851da9de9ef7b7baa04352eb96758c91ac22403cee922987b0ff7` |
| `python/modules/editing/paths_preview/app.py` | 457 | `b334e6caedda7ad8b79eea754df3827754fb9d1c47cda49ac75dcb1e6e4019d9` |
| `docs/tests-map.md` | 61869 | `fb4ed4e2e0672b046bb1f240105f08426c00d750df2b6fe1d94116fba18a31c7` |
| `docs/PROGRESS.md` | 64339 | `ab4838bebd6529a7f84f5b43fdef55f0d8fa474a909a3ece6196e965f7fd0634` |
| `docs/WORKLOG.md` | 583219 | `ce9af4ae848e058e0876c992fa3f59e981f53a16681b02ff910c5f8917af809f` |
| `docs/parity.md` | 18298 | `aa2e4a236b7e628f7670b6f8072737335c24ddea16a92a293983b4d1ed010661` |
| `fixtures/corpus/context/gather/001-all-sections.json` | 2379 | `9afcc882f2f69b41c5162866d456643176d052c5e1102b647e0c8a788f828000` |
| `fixtures/corpus/context/gather/manifest.json` | 986 | `e4389133c2ffbe5b9f9d65e541edecff4f7d60a420214cefff7a5f71a18a1360` |
| `reports/selfcheck/editing.split_py.json` | 942 | `29bdad5897280d2901ee6cdabd5f3101dcf620c4055fcae8d7d4a9782aca9d0b` |
| `reports/selfcheck/editing.paths_preview.json` | 1137 | `88bd91a4a699ef8f19b44c9111624d7456cf7aab92cce34faa0384afad767460` |
| Эталон `python/godot_tools/file_refactor.py` | 67833 | `61171473c1bb67359d551f10ef460b95790e32414696a2d1e30bfd1eabe407d8` |
| Эталон `python/godot_tools/project_tools.py` | 102471 | `79e9b035bd211f4a44623573d64f88f5bf47a049725c18dc90d985f47c6a7877` |
| Эталон `python/tools/agent_bridge.py` | 140086 | `0c7eb496807a8330076b7ed2fd08eb59abf59e93f072130fd9656b00c3b6894c` |
| Эталон `python/tools/godot_agent_mcp.py` | 31135 | `c5e0911566afc17d34c8569abbe91a8a9930220efe72ed83fa202769ec59e3d6` |

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-11-01 | сохранить этап 0 и исходный production | §10: смысл контракта требует ответа пользователя |
| 2026-11-01 | восстановить compact F3, не данные | найден исходный 56-строчный byte-backup C.18; count25/split_apply требуют теперь 57 строк |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-11-01 | 0. F1–F3 | свежий split_py583/107; 7 файлов/32 теста; compact F3, JSON-данные exact; snapshot832/0 |
| 2026-11-01 | 1. лист и база | внешний полный backup; таблица SHA; аудитное дерево3232/790/83 |
| 2026-11-01 | 2. preflight | чтение эталона окончено; следующий шаг — isolated native calls §10 |
| 2026-11-02 | 2. §10 завершён, STOP | 67 сохранённых probe-вызовов + настоящий MCP list_tools/call_tool; байты фикстур неизменны; production не начат |

## Проверки

F1 `python -B tools/selfcheck.py editing.split_py`:

```text
selfcheck editing.split_py
  module         ok              editing.split_py (split_scan, split_plan, split_apply)
  layers         ok              файлов 547, нарушений нет
  limits         ok              файлов 547, предупреждений 1
  contract       ok              артефактов 26, расхождений нет
  security       ok              нарушений нет
  unit           ok              583 passed in 5.48s
  corpus         ok              кейсов 107, расхождений нет
вердикт: ok
```

Свежий report SHA256
`ced9dc3457bf8d08954ef9cc4dcaa64b1d7238e21092b9918ce165e34c554d00`;
остальные 43 отчёта byte-exact. Длительности не редактировались.
F2: collect32 = executed32 = passed32, 1.76 с, `f2-tests.xml` SHA256
`aa05bb69fe6fc2e941ce8a58987af8f29bc949988f2dd4ae026dc23d4cecfb02`.
F3: case SHA256
`2345bffa85f5650c3547d69f8b0bd85f6e7e0a3852ae8f43f9f7fc6a7ef06013`;
manifest обновлён, snapshot832/0; gen_contract26/0, layers547/0, limits547/1
(прежнее информационное предупреждение split_py), security0.

База §0 уточнена, не заменена: исключаем компоненты __pycache__/.godot/
.pytest_cache, считаем корень каталога →3232/790/83. Сырые3265/806/84 включают
26 ранее существовавших `.pyc` и intentional skip-dir фикстуры; чужой мусор не
удалялся. WORKLOG583219B содержит4499CRLF: сохраняются все, включая исторические
4479 и позднейшие20. Промптов40, ADR15. В selfcheck уже44 отчёта с paths_preview,
поэтому «новый45-й отчёт» не следует из состава репозитория. Общие31 contract
JSON не равны26 генерируемым capability-артефактам.

Свежий `python -B tools/selfcheck.py editing.paths_preview`, exit2:

```text
selfcheck editing.paths_preview
  module         not_implemented заготовка: RuntimeError: python.modules.editing.paths_preview.module: нет MODULE (R-05)
  layers         ok              файлов 547, нарушений нет
  limits         ok              файлов 547, предупреждений 1
  contract       ok              артефактов 26, расхождений нет
  security       ok              нарушений нет
  unit           not_implemented тестов модуля нет: python/modules/editing/paths_preview/tests
  corpus         not_implemented нет корпуса механики: fixtures/corpus/editing/paths_preview
вердикт: blocked
```

Настоящий свежий JSON сохранён снаружи как `c21-selfcheck.json`, SHA256
`ab8282ac18a24b3365b7c6b2aa4981baac5d420ab4b193760afdb84379db675c`.
Исходный canonical paths_preview-report восстановлен byte-exact: это
preflight заготовки, не попытка выдать её за реализованную механику. JSON
длительностей не редактировался. Полный non-live и live на этом шаге не
перезапускались; 4281/live3 остаются явно аудиторской базой, не новым результатом.

## §10 — семь ответов actual-native до production

Досье в папке выше: `native-probes.py`, `native-supplement.py`,
`native-extra.py`; 67 файлов `native-raw/*.json` с настоящими аргументами,
результатом/exception, stdout/stderr и проверкой неизменности байтов фикстуры.
Bytes сохранены lossless через base64, tuple отмечен `$tuple`; это кодировка
досье, **не** придуманная схема инструмента. `native-identities.json`
фиксирует реальные пути загруженных frozen-модулей и сигнатуры. MCP реально
импортирован из установленного пакета, без mock. `q1-mcp-path-tools.json`
и `q1-mcp-call-result.json` — настоящие list_tools/call_tool.
`native-source-fragments.md` автоматически извлечён из неизменных исходников;
ниже дословные фрагменты с исходными номерами строк, без адаптации под порт.

### 1. Публичные имена и регистрация

**Прогон:** настоящий `build_server(profile="user", root=<external>).list_tools()`
выдал единственный соответствующий инструмент `paths_preview`, required
`old_path`, `new_path`, оба string. `op` отсутствует; output_schema=null,
annotations=null. `find_file_references` и `update_internal_relative_paths`
не зарегистрированы. Настоящий call_tool вернул text, structured_content=null,
is_error=false, result_type=complete. На мини-проекте: reference_count19,
file_count13; предупреждение user/addon→project без trusted Agent root.
Прямой bridge `q1-bridge-preview` дал те же19/13, RC0; отсутствие источника
`q1-bridge-preview-missing` — RC2, `refused: Исходный файл не найден: res://missing.gd`.

**Дословно**, frozen `python/tools/godot_agent_mcp.py:359–360`:

```python
    def paths_preview(old_path: str, new_path: str) -> CallToolResult:
        return call(["paths", "preview", old_path, new_path])
```

Frozen `python/tools/agent_bridge.py:848–851`:

```python
        policy = _access_policy(opts, root, _policy_warning_writer())
        prepared = file_refactor.prepare_file_rename(
            root, old_path, new_path, update_references=True,
            **_access_kwargs(policy))
```

Mapping:46/152 описывает функции find/internal/prepare, но не добавляет их
публичных регистраций. **Конфликт:** сохранение старого публичного preview
требует read-only preparation, запрещённого C.21 и отнесённого к C.22.
Два новых helper-инструмента или `paths_preview(op=...)` были бы новой схемой,
не паритетом старого API. Ни один вариант не выбран самостоятельно.

### 2. Расширения и формы ссылок

**Прогон:** `q2-find-default` —12 файлов/19 вхождений; a_exact4,
b_relative4, src/relative2, BOM1, broken.tscn1, project.godot1,
extensions/project.godot1, пять разрешённых extension-файлов по1.
Абсолютные строки, комментарии и `*res://` учитываются лексически; похожий
более длинный путь и unquoted-путь не учтены. Относительные preload/load/extends
учтены, в том числе в комментарии; обычная строка относительного пути — нет.
Кириллица: `q2-find-cyrillic` —1/1. Файл >5MiB пропущен.
Отдельный `q2-extensions-case-and-relative` — ровно replacement.gd и upper.GD
по1; относительные ext_resource в .tscn/.tres, plain-relative.gd и отдельный
uppercase `PROJECT.GODOT` не включены. Некорректный UTF-8 в разрешённом .gd
декодирован с U+FFFD, а не отклонён как не-Godot расширение. .shader/.cfg/.py/
.json/.txt/.bin/.import/.uid не включены.

**Дословно**, frozen `file_refactor.py:104–107,119–121,159–163`:

```python
    exact_pattern = re.compile(
        r'(?<=["\'\*])' + re.escape(old_godot_path) + r'(?=["\'\s,\]])'
    )
```

```python
            ext = os.path.splitext(filename)[1].lower()
            if ext not in (".gd", ".tscn", ".tres", ".gdshader", ".gdshaderinc") and filename != "project.godot":
                continue
```

```python
                        rel_pat = re.compile(
                            r'(\b(?:preload|load|extends)\s*\(?\s*["\'])' +
                            re.escape(cand) +
                            r'(["\'])'
                        )
```

Это regex, не разбор AST/ресурсов. `.tscn` ext_resource с абсолютным путём
находится как строка; malformed .tscn сам по себе не вызывает ошибку поиска.

### 3. Точная форма результата, spans, счётчики и порядок

**Прогон:** native find вернул list из12 per-file dict. Каждый содержит ровно
`path, absolute, occurrences, exact_matches, rel_matches, raw, text, bom`.
Нет `line`, `snippet`, списка абсолютных spans или полей transaction/plan.
`q3-find-empty` вернул `[]`; `q3-find-repeat` совпал с первым вызовом.
У b_relative.gd occurrences4/exact_matches0, rel_matches:
`[(9,23,"assets/item.gd"),(75,89,"assets/item.gd"),(103,117,"assets/item.gd"),
(42,58,"./assets/item.gd")]`. Это character offsets `[start,end)` в native
text, не byte offsets; они сгруппированы по candidate, **не** отсортированы
по позиции. Сумма per-file occurrences19; публичный preview file_count13
включает ещё исходный файл, поэтому не равен длине результата discovery12.

**Дословно**, frozen `file_refactor.py:166–177`:

```python
            total_occurrences = len(matches) + len(rel_matches)
            if total_occurrences > 0:
                references.append({
                    "path": godot_file,
                    "absolute": abs_file,
                    "occurrences": total_occurrences,
                    "exact_matches": len(matches),
                    "rel_matches": rel_matches,
                    "raw": raw,
                    "text": text,
                    "bom": bom,
                })
```

Порядок файлов следует несортированным `os.walk`/files: в прогоне a_exact,
bom_mixed, broken.tscn, b_relative, project.godot, затем extensions и src.
В исходнике:112 `for root, dirs, files in os.walk(root_path):`, :118
`for filename in files:`; сортировки нет. Существующий DiskFileSystem сортирует
и потому не даёт автоматически паритет того же порядка. `absolute` и bytes
— внутренний результат native, не разрешение публиковать абсолютный путь
машины/bytes в новом клиентском JSON вопреки R-15.

### 4. Что именно означает allow_addons=False

**Прогон:** default, False+trusted и True+untrusted дали12/19 без addon refs.
True+trusted дал13/20, добавив только addons/external/ref.gd.
self_edit=True+trusted при addons=False дал13/20, добавив только
addons/godot_agent/ref.gd; оба флагаTrue+trusted дали14/21.
Следовательно, False не закрывает собственный аддон при явном self_edit,
а True без server-derived trusted addon_dir не открывает внешние аддоны.
История/.git/.godot/.import/__pycache__ не попали в поиск.

**Дословно**, frozen `file_refactor.py:114–116`:

```python
        dirs[:] = [d for d in dirs
                   if d not in _SKIP_DIRS
                   or (d.casefold() == "addons" and (allow_addons or allow_self_edit))]
```

Frozen `project_tools.py:430–437`:

```python
    if classification.get("is_agent"):
        # External-addon access never implies self-edit access.  This is the
        # whole point of keeping the two capabilities independent.
        return bool(allow_self_edit and classification.get("agent_root_valid"))
    if classification.get("is_addon"):
        # Without a valid server-derived current-agent root, no add-on can be
        # safely distinguished from the protected installation.
        return bool(allow_addons and classification.get("agent_root_valid"))
```

Не путать политику **кандидатов со ссылками** с проверкой исходного пути — §6.

### 5. Проекция file/directory, неизменяемое, uid и битая сцена

**Прогон:** `q5-file-move`, src/unit.gd→src/entities/unit.gd, дал `(text,3)`:
extends ../base.gd→res://base.gd, preload weapon.gd→res://src/weapon.gd,
такой же load в комментарии тоже заменён. Абсолютный res://src/shield.gd,
uid://c21opaque, missing.gd и обычная строка weapon.gd не изменились.
CRLF и lone CR сохранены в returned text. `q5-same-dir` вернул исходный text/0.
`q5-directory-map` дал1 замену абсолютного shield на systems/battle/shield;
shield.gd и ./sword.gd остались относительными. Отсутствующий mapped target
может меняться: `q5-missing-mapped-changed` вернул
`('preload("res://elsewhere/renamed.gd")',1)`. Отсутствующий немаппированный
target остаётся как был. `q5-broken-tscn` вернул исходный text/0: helper
не понимает ext_resource и не валидирует сцену. Поиск broken.tscn при этом
нашёл1 абсолютную ссылку. `q5-relative-escape` — ValueError
`Путь вне проекта отклонен: res://../outside.gd`.

**Дословно**, frozen `file_refactor.py:191–199,203–211,225–229`:

```python
    if old_dir == new_dir and not moved_files_map:
        return text, 0

    import_pat = re.compile(r'(\b(?:preload|load|extends)\s*\(?\s*["\'])([^"\']+)(["\'])')
```

```python
        if raw_path.startswith("uid://"):
            return match.group(0)

        if raw_path.startswith("res://"):
            if moved_files_map and raw_path in moved_files_map:
                changes += 1
                return prefix + moved_files_map[raw_path] + suffix
            return match.group(0)
```

```python
        # Verify existence
        target_abs = _resolve_safe_path(project_root, target_godot)
        if not os.path.isfile(target_abs) and not (moved_files_map and target_godot in moved_files_map):
            return match.group(0)
```

Результат helper — `(updated_text,count)`, не план переноса. Map передаётся
готовым; построение move-map каталога и preparation остаются C.22. Старый
helper не нормализует old/new: сам срезает `[6:]`; строгая нормализация
в публичном preview происходит до него в prepare. Нельзя незаметно смешать
эти два уровня и приписать helper публичную валидацию.

### 6. Порядок валидации и дословные ошибки

**Прогон:** find и prepare для not-res дали FileRefactorError
`Путь должен начинаться с res://: assets/item.gd`; абсолютный внешний путь
тоже отвергается первым требованием res://. Для `res://./assets/item.gd`,
`res://assets//item.gd`, `res://../outside.gd` — FileRefactorError
`Некорректный путь: <исходный путь>`. Missing — FileNotFoundError
`Исходный файл не найден: res://missing.gd`. Directory в find — тот же класс,
`Исходный файл не найден: res://assets`; **публичный preview** принимает
directory: `q6-public-directory-clean` RC0/is_directory=True,22 refs/15files.
В отдельном испорченном UTF-8 проекте directory preview дал RC2 из-за U+FFFD
в изменяемом .gd, не потому, что directory запрещён.

`q6-find-plugin` нашёл1 ссылку; `q6-public-plugin` RC0/0refs/1file: корневой
plugin.cfg native не запрещён. Для addon source discovery при обоих флагах
False нашёл1 ссылку в обычном cfg_refs.gd: **источник не проверяется политикой**.
Native prepare/public preview для тех же addon sources отказали:
`Путь защищён текущей политикой доступа: res://addons/external/plugin.cfg`
или agent counterpart. Trusted allow_addons разрешил external prepare;
trusted allow_self_edit разрешил agent prepare. `.agent_history` в обоих
helper/prepare — ValueError `Доступ к служебной папке истории запрещён.`
Safe resolver для `../outside.gd` — ValueError
`Путь вне проекта отклонен: ../outside.gd`.

Пины порядка prepare: old-not-res раньше new-not-res; new-not-res раньше
missing; identical-path раньше missing (`Новый путь совпадает со старым:
res://missing.gd`); missing раньше addon policy; occupied destination раньше
addon policy (`Целевой файл уже существует: res://assets/item.gd`, FileExistsError).
Публичные malformed/missing/policy-refusal пробы дали RC2 и точные
stdout `refused: ...`, stderr `bridge: not-found: preview refused: ...`.
Outer-slash/whitespace/backslash normalize дал `res://assets/item.gd`;
skip_source_check=True для missing разрешил пустой результат.

**Дословно**, frozen `file_refactor.py:46–53`:

```python
def _normalize_godot_path(path):
    p = str(path or "").strip().replace("\\", "/")
    if not p.startswith("res://"):
        raise FileRefactorError("Путь должен начинаться с res://: %s" % path)
    rel = p[6:].strip("/")
    if not rel or any(part in ("", ".", "..") for part in rel.split("/")):
        raise FileRefactorError("Некорректный путь: %s" % path)
    return "res://" + rel
```

Frozen `file_refactor.py:597–615`:

```python
    old_path = _normalize_godot_path(old_godot_path)
    new_path = _normalize_godot_path(new_godot_path)

    if old_path == new_path:
        raise FileRefactorError("Новый путь совпадает со старым: %s" % old_path)

    abs_old = _resolve_safe_path(project_root, old_path)
    abs_new = _resolve_safe_path(project_root, new_path)

    if os.path.isdir(abs_old):
        return prepare_directory_relocation(
            project_root, old_path, new_path,
            update_references=update_references, allow_addons=allow_addons,
            allow_self_edit=allow_self_edit, addon_dir=addon_dir
        )

    if not os.path.isfile(abs_old):
        raise FileNotFoundError("Исходный файл не найден: %s" % old_path)
```

Это наблюдение frozen preparation, не его перенос. Нужен ответ, какую
политику/последовательность ошибок новый контракт обязан сохранять:
публичную preview или внутреннего discovery. Shared write guard с blanket
plugin.cfg-deny здесь не эквивалентен ни одному native read-helper.

### 7. Shared/fs: что переиспользуется, чего не хватает, граница R-11

**Прогон:** native `_read_file_text` вернул raw SHA256
`810bb0e28fe1b3a9515cbcc4c63781db4469e0c6f35196ce3c15ee83726b4d05`, bom=True,
text `# prefix\r\nconst A=preload("res://assets/item.gd")\r# tail\n`.
Настоящий shared.decode дал
`('# prefix\nconst A=preload("res://assets/item.gd")\r# tail\n','crlf',True)`.
То есть BOM-сигнал сохраняется, CRLF меняется, lone CR **не** меняется.
DiskFileSystem.read_raw дал исходные bytes; list_files существует, но
возвращает сортированный обход без фильтра скрытых/native skip/addons файлов.
Kernel normalize_rel('./assets/item.gd') дал assets/item.gd, тогда как native
строго отверг dot; он не заменяет native lexical validation.
PathPolicy plugin.cfg дал пустую причину, addon при закрытом флаге —
`аддоны закрыты`. Write-specific funnel добавляет blanket plugin.cfg запрет.

`q7-native-size-4mb`: matching candidate >4MiB и <5MiB найден1/1;
`q7-fs-size-4mb`: тот же файл новым fs по умолчанию — OSError
`[Errno 27] файл больше лимита чтения`. Поэтому одним read_raw по нынешнему
ctx нельзя молча заявить паритет native5MiB.

**Дословно**, новый `shared/script_edits.py:35–41`:

```python
def decode(raw):
    """(нормализованный текст, стиль переводов строк, был ли BOM)."""
    bom = raw.startswith(BOM)
    body = raw[len(BOM):] if bom else raw
    newline = "crlf" if b"\r\n" in body else "lf"
    text = normalize_newlines(body.decode("utf-8", "replace"))
    return text, newline, bom
```

Новый `kernel/text.py:9–11`:

```python
def normalize_newlines(text):
    """`\\r\\n` -> `\\n`. Одиночный `\\r` остаётся как есть (так делает эталон)."""
    return str(text).replace("\r\n", "\n")
```

Frozen `file_refactor.py:76–84`:

```python
def _read_file_text(abs_path):
    with open(abs_path, "rb") as handle:
        raw = handle.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return raw, text, bom
```

Новый `substrate/fs/disk_fs.py:36–42`:

```python
        for dirpath, dirnames, filenames in os.walk(self._root):
            dirnames[:] = sorted(name for name in dirnames
                                 if not os.path.islink(os.path.join(dirpath, name)))
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, self._root).replace(os.sep, "/")
                found.append(rel)
        return found
```

**Возможное законное разделение, не утверждённое решение:** module-owned
read-only port для enumeration/read_raw/is_file/exists; IO остаётся в fs
адаптере, domain получает данные через порт, app не импортирует substrate
или чужой domain. Существующий list_files можно вызывать только через порт,
но его нужно разрешить сверх неполного списка §2. Нужны отдельные решения
о порядке, read-cap5MiB без изменения соседнего default4MiB и сохранении
native text без CRLF-нормализации. Funnel/plan_log/journal не нужны для read;
подмена native decode shared.decode без решения нарушила бы паритет.

### Что должен разрешить пользователь перед продолжением

1. Старый публичный `paths_preview(old_path,new_path)` с необходимой read-only
   preparation (изменить границу C.21/C.22), либо новые helper-схемы как явное
   отклонение, либо отложить публичный инструмент до C.22. Не изобретать `op`.
2. Native newline/порядок/5MiB и необходимые read-only fs/shared расширения,
   либо явно согласованные отклонения с документом решения; соседей не менять.
3. Native discovery source-policy против общей PathPolicy, и plugin.cfg:
   сохранить native уровень или явно согласовать более строгую границу.
4. Скорректировать delivery counts после выбора API: existing44 reports
   включают paths_preview, а native регистрирует один tool, не два.

## §10 — решения аудитора (сессия 76, 2026-11-01)

Отвечаю по всем пунктам «Что должен разрешить пользователь». Ничего из native не
выдумываем; где паритет недостижим без поломки R-15 или детерминизма тестов —
это явное отклонение, записанное здесь. Раздел «Следующее действие» ниже
действует с поправками этого раздела.

### D1. API: публичный `paths_preview(old_path, new_path)` входит в C.21

**Разрешаю вариант A** — read-only preparation внутри C.21, потому что в native
публичный инструмент и есть она: `godot_agent_mcp.py:359–360` делает
`call(["paths", "preview", old, new])`, а `agent_bridge.py:848–851` внутри
вызывает `prepare_file_rename(update_references=True)`. Отложить публичный
инструмент до C.22 — значит сдать C.21 без единого инструмента; это не срез.

Границы:

* ровно **один** публичный tool: `paths_preview`, required `old_path`,
  `new_path`, оба string; никакого `op`, никаких `find_file_references` /
  `update_internal_relative_paths` в `ToolSpec` — они остаются внутренними
  функциями domain;
* `effects="read"`, `idempotent=True`, `requires_preview=False`,
  `availability="*"`;
* **никакой записи**: ни `create`/`delete`, ни `write_preview`, ни плана, ни
  журнала, ни `store/*`; `editing.file_refactor` остаётся скелетом этапа 0,
  `prepare_file_rename`, `prepare_directory_relocation`,
  `apply_prepared_file_rename`, `sync_references_after_external_move`
  запрещены — они C.22;
* в C.22 уходит только запись (apply, транзакция переноса каталога, case-only
  rename); публичная сигнатура инструмента не меняется.

### D2. Контракты и отчёты: 27 артефактов и 44 отчёта

Твоя поправка принимается, мой §1 в промпте был неверен:

* `contract/capabilities` — сейчас 27 файлов, из них `_template.json` не
  артефакт, поэтому `gen_contract --check` = **26**; после C.21 будет 28 файлов
  = **27 артефактов** (`paths_preview.json`);
* отчётов остаётся **44**: `reports/selfcheck/editing.paths_preview.json` уже
  есть и сейчас `blocked`, после среза он становится `ok`; остальные **43** —
  байт-в-байт прежние (проверю по SHA).

### D3. Расширения и формы ссылок — копировать литерально

* список расширений — ровно кортеж из frozen `file_refactor.py:119–121` плюс
  особый случай `project.godot`; выпиши кортеж дословно в лист и закрепи
  кейсами (`PROJECT.GODOT` в верхнем регистре **не** входит, `.shader/.cfg/.py/`
  `.json/.txt/.bin/.import/.uid` **не** входят);
* exact-ссылка — ровно регулярка `:104–107`: `(?<=["'\*])` … `(?=["'\s,\]])`,
  лексически, в том числе в комментариях; похожий более длинный путь,
  unquoted-путь и обычная строка не считаются;
* относительные `preload|load|extends` (включая вариант в комментарии) —
  считаются как rel; обычная строка относительного пути — **нет**;
* `uid://` — не трогаем и не считаем;
* кодировка — литерально `_read_file_text:76–84`: `utf-8-sig`, при ошибке
  `utf-8` + `errors="replace"`, BOM-флаг, переводы строк сохраняются как есть.
  **`shared.script_edits.decode` и `kernel.text.normalize_newlines` здесь не
  применяются** — они нормализуют CRLF и меняют BOM-семантику, это нарушило бы
  паритет;
* кириллица — считается; невалидный UTF-8 в `.gd` — U+FFFD, не отказ; файлы
  сверх лимита чтения — пропускаются, как native (>5 MiB).

### D4. Результат: что отдаём и что не отдаём (отклонения)

Контракт результата:

```text
{old_path, new_path, is_directory,
 file_count, reference_count,
 files: [{path, occurrences, exact_matches,
          rel_matches: [[start, end, raw], ...], bom}],
 source_text}            # текст донора после проекции; null для каталога
```

* `rel_matches` — character offsets `[start, end)` в тексте файла, сгруппированы
  по кандидату, **не отсортированы** по позиции (как native :243–249);
* `file_count` — как в публичном preview: `len(files) + 1` для файла (native
  считает и исходник: наблюдалось 12/13) и `len(files)` для каталога (15/22);
  оба случая закрепи кейсами;
* `source_text` — результат проекции донора, CRLF и lone CR сохранены; для
  каталога — `null` (агрегированные счётчики + `files`).

**Отклонения (явные, обоснованные):**

1. `absolute` (путь машины) и `raw`-bytes в per-file результате **не
   публикуются** — R-15;
2. порядок `files` — **лексикографический по `path`**, а не native `os.walk`:
   `DiskFileSystem.list_files` сортирует, а неотсортированный порядок нельзя
   закрепить тестом; отклонение формы, не семантики;
3. `text` каждого кандидата не публикуется (R-15 и размер) — только spans и
   счётчики; текст донора отдаётся в `source_text`.

### D5. Политика чтения: native уровень публичного preview

Источник и цель проверяются **как в публичном preview**, а не как в общей
воронке записи:

* внутри `addons/**` — `denied`, дословно
  `Путь защищён текущей политикой доступа: <path>`;
* `.agent_history` — `denied`, дословный текст из прогона `q6-*`, не
  переформулируй;
* путь вне проекта / `../` (в т.ч. `res://../outside.gd`) — `invalid_input`,
  `Путь вне проекта отклонен: <путь>`;
* не-`res://` — `invalid_input`, `Путь должен начинаться с res://: <путь>`;
* `res://./x`, `res://a//b` — `invalid_input`, `Некорректный путь: <путь>`;
* отсутствующий источник — `not_found`, `Исходный файл не найден: <old>`;
* занятая цель (файл) — `conflict`, `Целевой файл уже существует: <new>`;
* **корневой `plugin.cfg` читается** (native `q6-public-plugin` = RC0,
  0 ссылок / 1 файл); blanket-запрет `plugin.cfg` из воронки — про запись, к
  read-инструменту не применяется. Запиши это в лист как границу SEC-20/21;
* порядок проверок — ровно наблюдённый :385–392: old-not-res → new-not-res →
  identical (`Новый путь совпадает со старым: …`) → источник отсутствует →
  цель занята → политика аддонов.

### D6. Shared/fs: разрешён module-owned read-only порт

* `list_files`, `read_raw` (лимит **5 MiB для этого инструмента**; общий
  default 4 MiB не менять), `is_file`, `exists` — через **собственный
  read-only порт модуля**; IO остаётся в `substrate/fs`, `domain` — чистые
  функции, `app` ≤ 80 строк без импорта substrate и чужого domain (R-11/R-12);
* существующий `list_files` уже отдаёт sorted — принимается (см. D4.2);
* порт объявляется в `ports.py` и в `requires_ports` контракта;
* `funnel`, `plan_log`, `journal`, `backups`, `lock` для read не нужны.

### D7. Что это меняет в промпте и когда сдавать

* до реализации D1–D6 production, ToolSpec, корпус и red-тесты C.21 не пишутся;
* шаг 0 (F1–F3) **уже закрыт и проверен мной**: отчёт `editing.split_py` = ok
  (583/107, три tool), семь строк в `tests-map.md` (337–343), кейс
  `context/gather/001` вернулся к компактному виду (1 993 B);
* счётчики: контракт **27**, отчётов **44**; дерево базовое **3233/790/83**
  (плюс ровно прирост среза);
* directory-кейсы и `is_directory` — обязательны, как и кейсы «CRLF/lone CR
  сохранены», «BOM», «`uid://` не тронут», «битая сцена = 0 замен»,
  «отсутствующий mapped target меняется», «отсутствующий немаппированный — нет»;
### D8 (точечно): соседний кейс `context/gather` получает 26-й инструмент

**Разрешаю.** Регистрация 26-го инструмента обязана изменить секцию `tools`
соседнего кейса — это следствие состава API, а не правка «для удобства».
Границы ровно такие:

* `fixtures/corpus/context/gather/001-all-sections.json`: `sections.tools.count`
  25→26; в `names` вставить `"paths_preview"` на алфавитное место (после
  `node_reparent_preview`, до `scene`); в `effects` — `"paths_preview": "read"`.
  Формат файла, отступы, порядок остальных полей и EOL не трогать;
* `fixtures/corpus/context/gather/manifest.json`: обновить **только** sha256
  этого кейса, больше в манифесте ничего не меняется;
* тот же класс правки («плюс одно имя и count 26, ничего больше») разрешён в
  тестах, которые перечисляют полный список инструментов:
  `tests/py/integration/test_verify.py:43` (`== 25` → `== 26`),
  `tests/py/integration/test_gd_lint.py:87–89`,
  `tests/py/integration/test_node.py:103–105`,
  `tests/py/integration/test_scene.py:93–95`,
  `tests/py/integration/test_tscn_lint.py:50–59`,
  `tests/py/contract/test_functions_contract.py:144`,
  `tests/py/contract/test_usages_contract.py:158`. Выражение эффектов не
  переписывать — `paths_preview` попадает в `read` существующим правилом;
* **нельзя**: переформатировать кейс (F3 остаётся в силе), править другие кейсы
  `context/gather`, трогать корпуса других механик, «причёсывать» списки;
  `tests/py/integration/test_split_gd_plan.py:51` (`== 25`) считает кейсы, а не
  инструменты — не трогать;
* доказательства к сдаче: diff этих файлов содержит только перечисленное;
  `snapshot_diff` снова `832/0` (плюс ровно кейсы C.21, если добавляешь);
  non-live зелёный; в листе — раздел «Намеренная граница» с этим списком и
  причиной, чтобы аудитор проверял его отдельной строкой;
* сдача — строкой «C.21 готов к независимому аудиту, не принято».


### D9. Два мониторинговых пина: точные границы (2026-11-02)

Пользователь разрешил обе правки из §13: это последствия собственных фикстур
и read-only порта C.21, а не изменение frozen-эталона.

* `tests/py/formats/test_scene_deps_facts.py`: внутри прежней comprehension
  исключить только литеральный префикс
  `fixtures/projects/corpus/editing/paths_preview/` через `startswith`.
  Базы обхода, MANIFEST и равенство наборов не менять; никакого более широкого
  фильтра или glob. Чужой `scene_deps/manifest.json` побайтно сохранить.
* Каждый `.gd` этого корня закрепить `bytes` + `sha256` в собственном manifest
  C.21; в существующих corpus-тестах проверить покрытие и метаданные входов,
  не добавляя новых pytest-кейсов. Закреплены все47 файлов, включая28 `.gd`.
* `tests/py/integration/test_split_plan.py`: count3→4, добавить только
  `python/modules/editing/paths_preview/ports.py`; имя теста заменить на
  `test_exactly_four_production_exists_calls`. Область сканирования, литерал
  `fs.exists(` и формат списка прежние.
* Дословные AssertionError до правки сохранены в новом внешнем досье
  `c21-final-d9-20261102`: `d9-red-assertions.txt`, `d9-red-pins.xml` и исходный
  полный красный прогон в `pre-D9/`. Полный baseline до D9: индекс SHA
  `43ba36628b74e5ba19e2a2672838573684f111c0abe0a3cc8b2f39ec3ebb06d2`.
* К сдаче: точные diff/EOL, collect=executed4346/0, snapshot832+25/0,
  selfcheck58/25, остальные43 canonical reports byte-exact, финальная SHA
  таблица после всех записей. До этих проверок готовность не заявляется.

## §12 — проверка регистрации после D1–D7: STOP §6 (2026-11-02)

D1–D7 прочитаны и приняты в работу; первоначальные вопросы §10 решены.
До production сохранён новый полный байтовый baseline после правок аудитора:
`C:\Users\Lich\AppData\Local\Temp\opencode\c21-implementation-20261102\baseline.zip`
и индекс `baseline.json`, SHA256
`fc885a1731b6e088217c40bdbf5434a952c415d0e6c3cced5d56f67914a81e97`.
Аудит-дерево подтверждено: 3233 файла / 790 каталогов / 83 UID.

Обнаружено обязательное стоп-условие §6: новая регистрация D1 меняет полный
реестр инструментов, закреплённый соседним кейсом
`fixtures/corpus/context/gather/001-all-sections.json`. §4.4 промпта всё ещё
запрещает менять этот корпус, кроме уже закрытой форматной правки F3.
Разрешённые отклонения D4 не разрешают скрывать новый инструмент из `context`
или подменять ожидание динамическим вычислением.

Проверка сделана на настоящих `Registry` и вызове `context` в отдельном процессе.
В память добавлены только метаданные tool `paths_preview`, effects `read`, под
тестовым владельцем `preflight.paths_preview`; обработчик намеренно не вызывается.
Это проверка последствий регистрации, **не реализация preview и не native-проба**.
Рабочие MODULE/ToolSpec/корпус/red-тесты C.21 не созданы.

Результат до добавления метаданных: существующий кейс совпадает, count25.
После добавления: count26, новое имя `paths_preview`, effect `read`.
Реальный `snapshot_diff.describe` возвращает дословно:

```text
sections.tools.count: новый='26' эталон='25'
```

Источник зависимости: `python/modules/context/gather/app.py:48–50` собирает
`ctx.registry.entries()`, `domain/core.py:97–104` вычисляет `len(names)` и effects.
Полный ответ до/после и точное расхождение сохранены в
`registration-context-proof.json` нового внешнего досье, SHA256
`53a68dc5a8c35725ba8d722e76d692f1fadb4e833e17d501a7136aa167379775`.

Нужно разрешить **ровно две** семантические правки соседнего корпуса:

1. Кейс001: count25→26, одно имя `paths_preview` в алфавитном месте, один
   effect `paths_preview: read`; компактную раскладку F3 и прочие данные сохранить.
2. Manifest: заменить только SHA256 кейса001; кейсы002/003 не менять.

До ответа эти файлы не тронуты. D1–D7, §11 промпта, стадия0 и F1–F3 сохранены.

Повторные реальные гейты до записи этого раздела:

| Проверка | Фактический результат |
|---|---|
| `selfcheck editing.paths_preview` | blocked, exit2: нет MODULE, тестов, корпуса |
| `snapshot_diff` | 832 кейса / 0 расхождений, exit0 |
| `gen_contract --check` | 26 / 0, exit0 |
| `lint_arch` | 547 / 0, exit0 |
| `check_limits` | 547 / 1 прежнее информационное предупреждение split_py, exit0 |
| `security_audit` | 0 нарушений, exit0 |

Свежий blocked-отчёт архивирован как `editing.paths_preview.blocked.json`,
SHA256 `ab8282ac18a24b3365b7c6b2aa4981baac5d420ab4b193760afdb84379db675c`.
Канонический JSON восстановлен побайтно; все44reports совпадают с новым baseline.
Сырые stdout/stderr гейтов и их SHA — `preflight-results.json` внешнего досье.
Полный non-live и live заново не запускались; готовность к аудиту не заявляется.

## §13 — реализация после D1–D8 и STOP полного non-live (2026-11-02)

Перед первой правкой сохранён полный baseline после D8:
`C:\Users\Lich\AppData\Local\Temp\opencode\c21-delivery-20261102\baseline.zip`,
индекс SHA256 `98f1d475fdd6fb897e91fdb41ae78123e51e511aa364812847d34c61deaf0c9f`.
Изначальные 3233/790/83 подтверждены. Старый §12 — история STOP, закрытого D8;
на момент этого STOP разрешение на нижеследующие два теста ещё не было получено;
теперь оно записано в D9. Исторический красный след сохранён без подмены.

### Выполненный срез и фактические проверки

| Проверка | Фактический вывод |
|---|---|
| RED до production | collect=executed60, failed59/pass1, error/skip0; AST-пин проходит на TODO |
| GREEN нового среза | collect=executed=passed65, failed/error/skipped0 |
| `selfcheck editing.paths_preview` | ok, exit0; unit58 passed in7.70s, corpus25/0 |
| `snapshot_diff` | 857/0 = прежние832 + новые25; exit0 |
| `gen_contract --check` | 27/0, exit0; 28 capability-файлов с template |
| `lint_arch` / `check_limits` | 552/0; limits552/1 прежнее informational split_py предупреждение |
| `security_audit` / `probe paths_preview` | exit0; security0, probe typed ok |
| Полный non-live | collect=executed4346: passed4344, failed2, error/skip0; pytest81.82s |
| Все44 свежих selfcheck / live3 | не выполнены: общий прогон остановился раньше; не выдаются за зелёные |

Первоначальные60 RED расширены пятью дополнительными пинами (generic internal
helper, границы4/5MiB, invalid UTF8/BOM char offsets, отсутствие effect ports):
итого unit21 + contract7 + integration30 + formats3 + security4 =65. Собственный
selector selfcheck выбирает21+7+30=58, остальные7 проверены отдельным GREEN.
`red.xml` SHA `df9d94e3d6ca46dcbb4687902885fc7204aba633537882b7933ec1a39d5b59b1`;
`green65.xml` SHA `5cd6060869e2aec54424d2dd37c37d35cb0e1ffb1ee628a520e9860d44513218`.
Полный JUnit `full-non-live.xml` SHA
`c3706fcb39cf7eee9e670a6a492d77e1a4b80a0ea27b16231faf81ae974f90f0`.
Сырые ответы, argv, stdout/stderr и JUnit лежат в этом внешнем досье.

Канонический `editing.paths_preview.json` получен реальным selfcheck, не правкой
JSON; SHA `6a5b9a117fd05930e5daa1b62f8e99e2c729eea6efc4296e11bafd59ac540f2c`.
Остальные43 отчёта, включая split_py/F1, побайтно равны baseline; split_py не
переснимался. Этап0 и статус skeleton/не принято сохранены до решения аудитора.

### Намеренная граница — D8

Причина: **26-й инструмент меняет секцию tools соседнего кейса**. Это не
переформатирование F3. Внешний `D8-proof.json` и девять отдельных byte-diff
подтверждают ровно следующие преобразования; ни одного дополнительного байта:

| Файл | Только разрешённая правка |
|---|---|
| `fixtures/corpus/context/gather/001-all-sections.json` | count25→26; paths_preview после node_reparent_preview/до scene; один read effect |
| `fixtures/corpus/context/gather/manifest.json` | только SHA кейса001 |
| `tests/py/integration/test_verify.py` | len(tools)25→26 |
| `tests/py/integration/test_gd_lint.py` | одно имя и count26 |
| `tests/py/integration/test_node.py` | одно имя и count26 |
| `tests/py/integration/test_scene.py` | одно имя и count26 |
| `tests/py/integration/test_tscn_lint.py` | одно имя; count из прежнего len(names) становится26 |
| `tests/py/contract/test_functions_contract.py` | одно имя в sorted list |
| `tests/py/contract/test_usages_contract.py` | одно имя в sorted list |

Кейс теперь2047B/58LF/0CR, SHA
`2580e98f3338a549aed48abadf17332116c94fc8574de2f4f6ac00659500cb56`;
добавилась только строка effect, остальные отступы/переносы сохранены. Выражение
effects, кейсы002/003, test_split_gd_plan.py и остальные26 артефактов не изменены.

### Намеренная граница — D9

* coverage-пин scene_deps сужен до корня C.21; корпус C.21 запинен своим manifest.
* exists в read-only порту paths_preview — чтение, не запись (D6); пиновый счётчик вызовов 3 → 4.

| Файл | Только разрешённая граница |
|---|---|
| `tests/py/formats/test_scene_deps_facts.py` | в той же comprehension один literal startswith('fixtures/projects/corpus/editing/paths_preview/'); прежние базы/MANIFEST/равенство |
| `tests/py/integration/test_split_plan.py` | count4, один путь paths_preview/ports.py, test_exactly_four_production_exists_calls; прежняя область/литерал/формат списка |

До правки оба пина реально упали: `d9-red-pins.xml`, SHA
`70f9400033dfcc79f57106fbea77a40fd94d8c3ab3926184fdbbf3b14e060e24`.
Дословные AssertionError (включая `assert paths=={f['path'] for f in MANIFEST['script_facts']}`
и `assert len(calls) == 3`) сохранены в `d9-red-assertions.txt`, SHA
`5a14e285f322d4c3010dc3543a61e51c48de93d5561a0b667c09cf19b03297d6`.
Точные byte-diff/EOL подтверждены `D9-proof.json`. Manifest C.21 хранит bytes/SHA
всех47 входов, включая28 gd; прежние25 card-SHA и native_raw_SHA не изменены.
Существующие corpus-тесты проверяют входы и полный gd-инвентарь этого корня;
число новых тестов осталось65. Frozen scene_deps manifest не изменён.

### M1–M3 / P1–P3

| Проба | Фактический результат |
|---|---|
| M1 bypass addons-кандидатов | выбранный filter pin1/1 failed |
| M2 убрать strict dot/double-slash/parent validation | unit21 executed,4 failed |
| M3 разрешить любое расширение | выбранный filter pin1/1 failed |
| Восстановление M1–M3 | core.py и refs.py byte-exact к green; SHA до/после во внешних mutation proof |
| P1 чужая minimal-фикстура | временный BOM/CRLF/loneCR донор прочитан без правки; SHA равны; подложка удалена точно |
| P2 два вызова | ответы равны; полная байтовая инвентаризация всего addon до/после совпадает |
| P3 перед STOP | 3314/810/83 audit = база3233/790/83 +81 файлов/+20 каталогов/0UID; raw3349/828/84 |

Новых pyc/bak/temp нет; intentional skip-dir фикстуры C.21 содержат ref.gd, не
bytecode. Исторические26 pyc и прежние skip-dir данные не удалялись. Live не
запускался, project.godot и UID не трогались. SHA-таблица STOP снимается последней.

### Два новых глобальных пина за пределами D8: история STOP, закрытого D9

1. `tests/py/formats/test_scene_deps_facts.py::test_capture_covers_every_current_required_gd`
   (:40–44) сравнивает все .gd в editor/fixtures/projects с frozen script_facts
   корпуса scene_deps. Лишние28 путей — **только** собственные проекты C.21;
   старые captured пути не пропали и их байты не изменены. Запрос: исключить
   только `fixtures/projects/corpus/editing/paths_preview/**` из этой глобальной
   проверки покрытия. Все прежние native fact-кейсы и corpus/manifest scene_deps
   оставить побайтно; никаких общих исключений новых фикстур не добавлять.
2. `tests/py/integration/test_split_plan.py::test_exactly_three_production_exists_calls`
   (:72–79) считает `fs.exists(` во всём production, а не только split. Теперь4:
   три прежних пути + `python/modules/editing/paths_preview/ports.py`.
   Запрос: count3→4 и ровно этот четвёртый путь в ожидаемое множество; прежние
   вызовы, остальные тесты и F11 не менять.

Оба файла пока побайтно равны baseline. Подмена записи вызова fs.exists ради
пина, перенос/переименование C.21 фикстур, изменение чужого корпуса или скрытый
skip тестов не делались. До ответа STOP §6; готовность к независимому аудиту
**не** заявляется. После разрешения — эти точные правки, полный non-live,
44 selfcheck с сохранением43 canonical bytes, live3/cleanup, финальные записи.

## §14 — D9 завершён: готовность к независимому аудиту (2026-11-02)

Оба точных мониторинговых пина применены по D9; STOP из §13 закрыт. Этап0 и
аудиторский статус skeleton сохранены: **C.21 готов к независимому аудиту,
не принято**. Следующее действие — независимая проверка, не перенос C.22.

| Проверка | Реальный итог после D9 |
|---|---|
| RED пинов | 2 executed / 2 failed; дословные AssertionError и исходный full RED сохранены |
| Новый срез | collect=executed65, passed65, error/fail/skip0; JUnit `e3f7facf0644b86568f9c2d61cabb38e82777eb145097741136a0e0f914908e9` |
| Full non-live | collect=executed4346, passed4346, error/fail/skip0; JUnit time 66.939s |
| Snapshot | 857/0 = прежние832 + ровно25 C.21; соседние корпуса неизменны кроме D8 |
| Contract / layers / limits / security | 27/0; 552/0; 552/1 прежний split_py informational warning; security0 |
| Selfcheck paths_preview | ok: 58 passed in 6.73s; кейсов 25, расхождений нет |
| Все44 selfcheck | реально выполнены, verdicts {'blocked': 19, 'ok': 25}; соседние verdicts совпадают с baseline |
| Live Godot4.6.3 | 3passed/0fail/error/skip; JUnit time 21.941s |
| Live restoration | project335→419→335B; удалено точно 169 новых gd.uid; baseline UID восстановлены: [] |

Full JUnit SHA `ef5582953468751efe26b521b926c1ade1078fe3fe00358a7f13cad961514ee3`; live JUnit SHA `d4869b720e7f1cc7e8af2669872062e9ef9f8fe878dcff51a12c5d5040130348`.
Canonical paths_preview получен настоящим selfcheck, SHA `19f13f715f131577443de8182818af7a91ba0223dfafda418487a2463eb0f74b`.
Свежие44 JSON/stdout архивированы снаружи (`fresh-selfchecks/`);43 соседних
канонических отчёта, включая split_py/F1, восстановлены из baseline без изменения
байтов или durations. Это не освежение соседних canonical reports.

Фактический stdout собственного selfcheck (сырой UTF8 рядом с JSON):

```text
selfcheck editing.paths_preview
  module         ok              editing.paths_preview (paths_preview)
  layers         ok              файлов 552, нарушений нет
  limits         ok              файлов 552, предупреждений 1
  contract       ok              артефактов 27, расхождений нет
  security       ok              нарушений нет
  unit           ok              58 passed in 6.73s
  corpus         ok              кейсов 25, расхождений нет
вердикт: ok
```

D8: девять exact byte-transform сохранены. D9: два exact diff, ноль CRCRLF,
собственный manifest пинит47 входов/28 gd; прежние25 card/native_raw SHA и все
байты фикстур сохранены. Frozen scene_deps manifest, test_split_gd_plan.py,
26 прежних capability-артефактов, editor/**, selector, handoff, ADR statuses
и frozen reference не изменены.

M1/M2/M3 дали1/4/1 failed и восстановлены byte-exact; после D9 production
core/refs не менялись. P1/P2 и probe повторены: BOM/CRLF/loneCR/uid текст и
байты сохранены, временный чужой донор удалён точно, два ответа равны и всё
дерево byte-exact. Итог audit3314/810/83 = baseline3233/790/83 +81files/+20dirs;
raw3349/828/84. Live project SHA прежний
`958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`.
Новых pyc/bak/temp/UID нет; исторические26pyc и intentional fixtures сохранены.

Полное досье: `C:\Users\Lich\AppData\Local\Temp\opencode\c21-final-d9-20261102`.
Финальная `SHA256-C21-final.md` формируется **после** этого раздела, PROGRESS,
tests-map, parity и бинарного ab-append WORKLOG; дальнейших правок записей нет.

## Следующее действие

Независимый аудит C.21 по D1–D9 и SHA-таблице; до вердикта статус/этап не менять.

## Блокеры

| Что мешает | Кто решает |
|---|---|
| Старый публичный paths_preview → prepare_file_rename, запрещённый C.21 | решено аудитором D1: read-only preparation разрешена |
| «без нормализации» против shared.decode и неполный список fs-методов | решено аудитором D3/D6 |
| 26→28 артефактов и 44→45 отчётов не вытекают из native/schema/inventory | решено аудитором D2: 27/44 |
| Native5MiB/unsorted против fs4MiB/sorted и source-policy/plugin.cfg | решено аудитором D4/D5/D6 |
| Новый tool меняет context/gather/001, но §4.4 запрещает его правку | решено аудитором D8; exact byte-transform проверен |
| Глобальное gd-покрытие scene_deps и production fs.exists count3 | решено D9; exact diff, manifest-пины и полный4346/0 подтверждены |
