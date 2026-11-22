# editing.resource_ops — C.23: строгая схема `.tres`, prepare-only

**Статус:** C.23 готов к независимому аудиту, не принято. D14–D17: prepare-only, module-owned read seam через существующий fs. В таблице PROGRESS этап 0, skeleton; этап не назначается портером.
**Обновлено:** 2026-11-02.

## Цель

Перенести нормализацию действий `edit_resource`, canonical digest, raw SHA,
prepare/public projection/operation summary с дословными отказами native.
По D14 C.23 — только внутренний prepare: нет apply, transformed bytes или записи.
ResourceSaver, редакторская половина и выбор byte producer относятся к C.24 (D15).
Решения §10 и D17 получены. Исторический инфраструктурный STOP ниже сохранён
как доказательство; corpus/specification/SEC-23/red/production выполнены.
Финальные gates выполнены; следующее действие — независимый аудит без назначения этапа портером.

## Старый код

Эталон `D:/vajno/Godot/random-game/addons/godot_agent/` только читается.
`python/godot_tools/resource_actions.py`: 19642 B, SHA256
`edef33817b0f5e9a9885dae55648b2c0c01fa2a8f908c07b10007fa1ff7fbbc5`.
Тот же размер/SHA подтверждён у yandex-game-dev и backup 0.9.1 от 20261027-0113.
Архив 0.8.0 не является эталоном этого среза.

| Файл / строки | Назначение | Граница |
|---|---|---|
| resource_actions.py:14–128 | ошибки, константы, exact/text/number/path/target/tagged | чистые правила и потребительский read-only порт |
| resource_actions.py:131–298 | шесть операций и normalize_action | схема native, порядок отказов дословно |
| resource_actions.py:301–355 | dependencies, digest, raw hash, prepare/public/summary | перенос C.23 |
| scene_actions.py:94–128 | стандартные tagged Variant | источник правил, не foreign-domain импорт |
| main.py:1747–1772,3218–3251,3393–3590 | prepare → confirm → editor result/history | выяснение actual маршрута; старый host не переносится |
| agent_resource_executor.gd:18–161,540–622 | editor prepare/execute/temp-save/UID/recovery | только исследование; вне production C.23 |
| transaction_actions.py:87–153; agent_bridge.py:2514–2572 | отдельная файловая transaction/MCP write | не предполагать поддержку edit_resource |

## Старые тесты

| Файл | Семейство / судьба | Кейсы |
|---|---|---|
| test_resource_actions.py:50–144 | unit / corpus, tests-map114 | шесть групп операций, dependencies, defaults, strict fields, policy, digest/public, read-only prepare |
| test_resource_action_flow.py:49–160 | flow / corpus, tests-map113 | confirm/result/history/duplicate/rollback/recovery; не считать подставленные bytes/semantic hashes actual editor-success |
| test_path_policy_safety.py | unit / corpus | resolved identity и независимые trusted-флаги |

Старые тесты не скопированы и не запущены. Строки 113–114 сохранили судьбу corpus,
порядок и исторические счётчики; ошибочная принадлежность scene_model.node_rename
исправлена только на editing.resource_ops/.tres.

## Корпус

Создан `fixtures/corpus/editing/resource_ops/`: 235 executable карточки и отдельно
74 provenance diagnostics =64native+10current. Native/current origin, исходные
и masked bytes/SHA сохранены; current guards и transaction не считаются resource
parity. Raw before/after совпадают, UUID маскируется только в проекции корпуса.

## Спецификация

По D14 нового ToolSpec и capability-артефакта не будет: native MCP stdio 14/24
не объявляет ресурсный инструмент, контракт остаётся 27. Реализован внутренний
entrypoint prepare, `TOOLS = ()`; metadata contributor как у C.22 не добавляет
public dispatch. Service-only ModuleSpec без contributes_to существующая сборка
не принимает; менять ModuleSpec/loader/registry для C.23 не требуется.
Write op и ADR-0017 в C.23 не создаются; ADR-0016 не расширяется.

## База до первой правки

Досье `C:/Users/Lich/AppData/Local/Temp/opencode/c23-preflight-20261102/`.
`baseline.json` 666902 B / SHA256
`abe050db8dec8bb619449ef2c5091bfa496e34ee3c6883f796013a45b04e566c`;
`baseline.zip` 3786340 B / SHA256
`9c75d4281e90a042ab927c9dd6fb0d5c3fc7a5c38ef600d87bfc8ed6d112ca50`.
Полные исходные bytes/SHA всех файлов сохранены до создания этого листа;
`frozen-reference-baseline.json` фиксирует всё native-дерево.

Audit-предикат исключает компоненты __pycache__/.godot/.pytest_cache, включает
.git; число каталогов включает корень: 3436 файлов / 813 каталогов / 83 gdUID.
Raw: 3471 файлов / 832 каталога с корнем. Это проверка геометрии, не замена
аудиторской базы non-live4483/snapshot909/contract27/gates558/reports44.
Промптов42, ADR16, stage-строк45 = 25/1/19. Внешний project.godot335B/SHA
`958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29` сохранён.
WORKLOG625476B/SHA
`79af5650e7f5707fe1e57370db6aca71a3eb387a7edc3041f858dceee1f04902`:
4831CRLF, CRCRLF0; весь prefix, включая исторические4479CRLF, сохраняется.

## Намеренная граница

C.23 — **prepare-only** по D14: internal service/contributor, без нового public
инструмента, capability-артефакта или ресурсной ветки accepted write_preview.
**Apply отсутствует.** Нет transformed bytes, replace_raw для ресурсов, записи
файлов проекта, WAL-плана или расширения ADR-0016; ADR-0017 не пишется.
Native public_prepared — только action_id/action_digest/expected_resource_hash/
prepare_in_editor; raw bytes наружу не публикуются ни в какой форме.

По D16 target и dependency получают одну module-local resolved-identity/casefold
политику до плана: addons, .agent_history, project.godot и выход из проекта
запрещены независимо от регистра и trusted-флагов; root plugin.cfg разрешён
только для чтения dependency. Realpath-containment обязателен; порядок
policy → extension → safe resolution → isfile и native тексты сохраняются.
Trusted addon edits не портируются. SEC-23 записан до production;
security-тесты следуют после расширения frozen диагностического корпуса.
Общие guard_path/guard_transfer не меняются и не ослабляются.

На текущем шаге — внешний post-D17 baseline/реальная read-seam проба и спецификация.
Никаких изменений editor, принятых реализаций/тестов/корпусов, контракта,
статусов ADR или таблицы механик. Canonical reports после диагностического
selfcheck возвращаются copyfile из исходных bytes с SHA-проверкой; JSON руками
не редактируется. Токены/секреты не сохраняются; данные не превращаются в команды.

**Закрытый инфраструктурный список D17** (причина: «tool-less вклад без публичного инструмента»):
`tools/selfcheck.py` — только corpus discovery/routing по module_id;
`tools/snapshot_diff.py` — data-declared `internal_call` рядом с `native_call`;
`tools/probe.py` — internal prepare client; `python/runtime/bootstrap.py` —
только composition module-owned read-only порта. Иных инфраструктурных правок нет.
`python/substrate/fs/resource_read.py` отклонён и не создаётся. Module-owned
`resource_ops/ports.py` использует существующий DiskFileSystem, публичный
project_root, module-side realpath и fs containment. Отдельный экземпляр fs
с max_bytes=sys.maxsize сохраняет native full-raw SHA без чужого read_text cap;
существующие десять портов/их параметры/порядок не меняются.

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-11-02 | чтение и внешний baseline | обязательные документы/исходники прочитаны; SHA трёх актуальных копий совпал; лист — первый repository-байт C.23 |
| 2026-11-02 | actual preflight | MCP stdio 14/24; 64 native + 10 current schema/policy probes; 7 engine serializer fixtures; 6 current pure-op byte probes. Не red-тесты, не корпус, не parity |
| 2026-11-02 | selfcheck | exit 2 / blocked; static gates green, MODULE/unit/corpus отсутствуют; все 44 canonical JSON восстановлены побайтово |
| 2026-11-02 | D14–D16 и свежий baseline | auditor block сохранён; worksheet 39252 B/SHA dea2c264…321df до этой правки; audit 3437/813/83, native 947 файлов exact, contract27/reports44 |
| 2026-11-02 | проверка интеграционного scope | hypothetical tool-less manifest: check_corpus возвращает ok при 0 вызовов корпуса/snapshot; fresh real selfcheck exit2/blocked. STOP §6(5), production0 |

## §10 — семь ответов до production

### 1. Регистрация и фактический public

Настоящие SDK ClientSession → native MCP subprocess/stdin: initialize,
list_tools и call_tool, отдельно оба профиля. Внешние `mcp-raw/*` содержат
дословные запросы, входные JSON Schema, ответы и before/after SHA мини-проекта.

- `user`, 14: status, engine, api, ask, search, read, scene, functions, usages,
  analyze_rename, context, check, check_action, paths_preview.
- `agent-dev`, 24: те же 14 + write_preview, write_apply, write_rollback,
  node_rename_preview, node_reparent_preview, node_delete_preview, split_scan,
  split_plan, split_gd_scan, split_gd_plan.
- Ресурсной пары к paths_preview **нет**. resource_ops и edit_resource дают
  `Unknown tool: resource_ops` / `Unknown tool: edit_resource` в обоих профилях.
- paths_preview принимает `{old_path: str, new_path: str}`, возвращает текст
  CallToolResult, не типизированный ResourcePrepared. User happy-path `.tres`
  нашёл 1 ссылку; исходные файлы побайтово неизменны. Offline user сообщает
  деградацию addon → project; offline agent-dev закрывается до dispatch.
- Поэтому первый agent-dev write_preview в мини-проекте **не** доказывает
  отсутствие resource dispatch: отказ был `trusted running Godot Agent root
  is unavailable; agent-dev fails closed`.
- Дополнительный actual stdio на подлинном native project/source root:
  user → `Unknown tool: write_preview`; agent-dev → дословно
  `refused: write request must be create_file, patch_file, move_file,
  rename_node, reparent_node, delete_node, or transaction`. В последнем
  CallToolResult `isError=false` — не исправлено и не названо успехом операции.
  См. `mcp-native-root-v2-{user,agent-dev}.json`, proof; native addon byte-exact.
- Отказ подтверждается agent_bridge.py:1379–1387,2085–2156 и настоящим
  transaction_actions.normalize_action: `Операция 1 должна быть create_file,
  patch_file или move_file` (`schema-raw/transaction-rejects-resource.json`).

Native объявления write_preview `{request: dict}`, write_apply
`{plan_id: str, request: dict}` возвращают текстовый MCP результат;
аннотаций effects/idempotent/requires_preview native не объявляет. Из этих
регистраций нельзя получить схему нового ресурсного инструмента.
mapping.md:31 — имя старого модуля `project_ops.resources`, не MCP tool-name;
:66 описывает resource_actions, :120 — его редакторскую половину. При такой
интерпретации противоречия mapping/native не обнаружено.

**Намеренная граница public:** contributor/internal service без нового
ToolSpec/resource_ops.json, contract **27**, не 28. Общедоступный ресурсный
dispatch в нынешнем write_preview не появляется сам от регистрации вклада.

### 2. Кто применяет, считает квитанцию и откатывает

resource_actions.prepare:333–341 только normalize → UUID → raw before_hash;
не изменяет `.tres`. Python-плана с готовыми новыми байтами здесь нет.
Native host main.py:1747–1772 хранит normalized action и preview metadata.
Panel:1117–1153 вызывает **agent_resource_executor.gd**, не MCP transaction.

Редакторский prepare:18–35 загружает Resource, выполняет операции в памяти,
вычисляет semantic hash/dependency fingerprint, требует реальное изменение;
диск не публикует. Execute:38–105 повторяет загрузку/операции и проверки
утверждённой semantic projection/dependencies. `_open_target`:137–161:
EditorPlugin → running game → res://*.tres → raw expected hash → Inspector
→ scanning/import dependencies → target load. Например, дословно:

- `editor_unavailable`: `EditorPlugin недоступен`;
- `stale_resource`: `Ресурс изменился после подготовки`;
- `preview_mismatch`: `Результат выполнения отличается от предпросмотра`;
- `dependency_changed`: `Импортируемая зависимость изменилась после предпросмотра`.

Executor сохраняет случайный staging `.tmp.tres` через ResourceSaver, при valid
UID вызывает set_uid, reload/semantic verification. Публикация:540–573 —
copy original → backup, hash backup → staging → target, rename staging → target,
postvalidation/cleanup. Это не наш atomic raw writer: native специально
страхует Windows rename-overwrite от delete-then-move. Recovery:575–622
проверяет original backup hash и принадлежность опубликованных bytes, не
перезаписывает foreign state; final raw hash обязан совпасть с original.

Host confirm:3218–3251: pending prepare → normalize/policy → before_hash
(`Ресурс изменился после предпросмотра.`) → подтверждённые редактором
semantic/dependency hashes (`Godot не подтвердил структурный предпросмотр
ресурса.`) → history reservation → execution envelope. Editor result:
3393–3549 проверяет identity/token/state/policy/reported-vs-actual raw hash,
затем commit history либо guarded reserved restore. Квитанция/history — host,
фактическая запись — editor executor; duplicate response — host cache.

**Граница доказательства:** actual Python normalize/prepare и настоящие engine
helpers исполнены. Полный prepare/execute без EditorPlugin дал именно
editor_unavailable; fake Plugin, semantic hashes, успешный finalize и receipt
не подставлялись. Полный живой panel→host→execute→history→rollback здесь
не выполнен и не заявляется. Исторический flow-тест с ручной записью after
bytes не является таким доказательством.

### 3. Байты, UID и выбор op

Godot **4.6.3**, внешние мини-проекты, byte-identical копия native executor:
actual `_apply_operations`, `_save_temporary_resource` → ResourceSaver,
ResourceLoader reload и semantic hash. Исходники, before fixtures и логи
сохранены: `serializer-proof.json`, `serializer-extra-proof.json` и проекты.
Это serializer/helper probes, **не полный редакторский success-path**.

| Input | Actual результат |
|---|---|
| LF | load/save/reload success; итог LF + trailing LF |
| CRLF без BOM | success; итог LF, CRLF 0 |
| mixed LF/CRLF | success; итог LF, CRLF 0 |
| одиночный CR | success; итог LF, lone CR 0 |
| без trailing LF | success; добавлен trailing LF |
| UTF-8 BOM + CRLF | load failure: `Parse Error: Expected '['.`; output отсутствует |
| UTF-8 BOM + LF | тот же load failure; output отсутствует |

Существующий `StyleBoxFlat_keep` sub_resource id в этих успешных fixtures
сохранён; новый StyleBoxFlat получает engine-generated id. Побайтовой общей
стабильности id из этого не следует. В standalone runtime UID registry не
зарегистрирован: get_resource_uid=-1, ветка set_uid не исполнена. Native
код сохраняет valid UID явно; его editor-success parity ещё **не доказан**.
Операции не являются поиском/заменой uid:// или id в тексте.

Current pure-op probes: `bytes-*.json`, исходные/ожидаемые/полученные bytes
base64 + raw SHA. BOM+CRLF и lone CR случайно сохраняют оба op. Mixed fixture:
script_edit дал **30 B** вместо **29 B**, SHA отличается; replace_raw exact.
Важно: kernel.text нормализует только CRLF, **не** lone CR; потеря здесь —
отдельный LF при восстановлении общего CRLF стиля, а не blanket CR stripping.

**Предлагаемый op публикации:** replace_raw, step.expected_hash и
WritePlan.expected[target] = raw before SHA; никакого пересчёта stale плана.
Он переносит **уже вычисленные** bytes, а не осуществляет шесть структурных
операций Resource. Native ResourceSaver не сохраняет требуемый input EOL/BOM.
Две разные задачи — вычисление результата и его безопасная публикация —
нельзя выдавать за готовую реализацию одним выбором replace_raw.

### 4. Полная native схема

Все объекты exact: обязательные поля, затем лишние; _exact:30–38.
Верх: `{action,resource,operations}`, optional wait_for_import/summary;
action только edit_resource. При require_exists=True resource `.tres`
проверяется до operations; operations 1..20. wait_for_import: `value or []`,
массив до32, существующие пути, dedup first-seen до нормализации операций;
dependencies затем добавляются first-seen. summary если не None — str≤500,
strip; пустой после strip не включается. require_exists=False:249–273 не
требует существования цели, но safe resolution/policy остаются.

| op / source | Required | Optional / ограничения |
|---|---|---|
| set_property:137–144 | op,target,property,value | property≤160 + MEMBER_RE; затем target, tagged value |
| replace_reference:146–157 | op,target,old,new,expected_count | old/new существующие Resource paths, count int без bool 1..10000, old!=new; затем target |
| animation_add_value_track:159–181 | op,path,keys | interpolation=linear, update_mode=continuous; keys1..512; key `{time,value}`, optional transition=1.0; finite time≥0 строго растёт; transition finite>0; path str≤500 проверяется последним |
| sprite_frames_add_animation:183–200 | op,name,fps,loop,frames | name≤120, fps finite>0, loop bool; frames1..256 `{texture}`, optional duration=1.0 finite>0; texture только ResourcePath; проверка frames до loop/name/fps |
| theme_set_item:202–217 | op,data_type,theme_type,name,value | overwrite=False bool; theme_type/name≤120; матрица type проверяется после tagged |
| tileset_add_atlas_source:219–246 | op,source_id,texture,texture_region_size,tiles | source_id int без bool≥0; texture ResourcePath; region exactly2 positive ints без bool; tiles1..512, exactly2 nonnegative ints без bool, без duplicates |

Константы: _THEME_TYPES = color/constant/font/font_size/icon/stylebox;
_INTERPOLATION = nearest/linear/cubic; _UPDATE_MODES = continuous/discrete/capture.
_THEME_VALUE_TYPES: color→Color; constant/font_size→int;
font/icon/stylebox→ResourcePath либо NewSubresource.
_MEMBER_RE и _CLASS_RE: `^[A-Za-z_][A-Za-z0-9_]*$`, **match, не fullmatch**.
Actual `terminal-newline-member` принят native; молча ужесточать `$` нельзя.

`_target`: список до8 (пустой root), каждый member str≤160 + regex.
`_tagged`: ResourcePath exact type/value, существующий разрешённый путь без
ограничения расширения; NewSubresource exact type/class, optional properties.
class≤120 + regex; depth>=4 запрещён; общий счётчик NewSubresource до32;
properties=`value or []`, список до32 exact `{property,value}`, уникальные
member≤160, запрещены resource_path/resource_name/script; рекурсивный tagged.
В SpriteFrames texture отдельная проверка без action-wide counter.
Actual properties=False и wait_for_import=False превращаются в [] — литерально.

Остальные tagged values по scene_actions.normalize_variant:94–128:
exact type/value; Nil=None, bool именно bool, int не bool, float finite int/float
не bool→float, String/StringName str≤4000 (пустая допустима), NodePath≤500
с native segment restrictions и специальным `.`; Vector2/2i,Vector3/3i,Color
массив арности2/3/4 finite nonbool numbers. Integer vectors используют int()
(actual Vector2i [1.9,-2.8]→[1,-2]), не проверку исходных integer components.

prepare:333–341 возвращает action_id(UUID32hex), normalized action, resource,
target, action_digest, before_hash(raw), state=preview. public_prepared:344–346
**ровно четыре** поля: action_id, action_digest,
expected_resource_hash=before_hash, prepare_in_editor=True. Никаких absolute/raw.
operation_summary:349–355 нумерует шесть русских названий операций, fallback op.
canonical_digest:322–325 = SHA256 UTF-8 JSON ensure_ascii=False,
sort_keys=True, separators=(",",":"); **порядок входных dict keys не значим**,
порядок массива операций значим. Actual reordered-fields digest совпал.
file_sha256:328–330 = SHA256 исходных rb bytes, не текста.

### 5. Периметр, ADR и решения, без которых STOP

Новый file-effect op не требуется: replace_raw уже имеет strict base64/raw
guard, backup, intent, receipt, compensation и повторный apply→stale_plan.
Но ADR-0016:75–80 разрешает его **только для reference edits file_refactor**.
Использование для C.23 требует явного расширения назначения; принятый ADR
самостоятельно не правится. После ответа возможен отдельный **proposed**
ADR-0017, не новое молчаливое значение accepted ADR.

Нет одобренного Python byte producer, эквивалентного native ResourceLoader /
ResourceSaver / class-and-property checks / semantic preview / dependencies.
Raw read-port достаточен для normalize/prepare, **не для применения** всех6 ops.
Engine/editor transformer-port потребует решения и может затронуть запрещённые
editor/**, editor_verbs и bootstrap/портовую сборку. Textual трансформация —
отдельное, существенное отклонение, не доказанный literal native перенос.

Внутренний service/contributor как C.22 оставляет contract27. Если пользователь
требует именно новый public dispatch через write_preview, его нынешний
app/domain/tools и contract/capabilities/write_preview.json принимают только
symbol rename и публикуют script_edit, не arbitrary resource action/raw bytes.
OperationCompiler:33–37 имеет symbol-analysis/text сигнатуру. Эти принятые
файлы/тесты не в разрешённом C.23 scope; менять их или объявлять фиктивный
ресурсный ToolSpec запрещено. Публичная утечка bytes_b64 также запрещена.

Нужны решения пользователя:

1. Оставить C.23 internal (27 artifacts) и уточнить production объём: только
   normalize/prepare сейчас либо отдельный одобренный источник transformed bytes.
2. Для полного apply выбрать/разрешить engine primitive-port и его файлы либо
   явно специфицировать textual deviation; **native save + byte-preserving BOM/EOL
   одновременно этими пробами не подтверждены и противоречат serializer behavior**.
3. Явно разрешить C.23 use of replace_raw через proposed ADR-0017, определить
   guards для targets/dependencies (ниже) и строгую internal/public projection.
4. Если нужен public write_preview resource branch — отдельный closed scope
   владельца/контракта/новых пинов, не ослабление принятых tests по умолчанию.

Предлагаемые отклонения пока **не приняты** и не реализованы: preserving input
BOM/EOL вместо ResourceSaver serialization; strict AppError kind вместо native
текстового MCP refusal с isError=false; module-local resolved/casefold policy
при неизменном generic guard. Native public_prepared уже без absolute/raw,
по нему отклонение не требуется. Editor-only отказы не симулируются Python-кодом.

### §10.5 — решения аудитора (сессия 76, 2026-11-02)

**D14. Срез режется надвое: C.23 — только prepare, запись не входит.**
Native не объявляет ресурсного инструмента (actual MCP 14/24) → `contract` остаётся **27**,
`capability`-артефакт не создаётся, `ToolSpec` с `bytes_b64` не появляется никогда (утечка
байтов наружу запрещена). C.23 портирует **чистую половину**: `_exact/_text/_number/_path/_target/_tagged`,
`_normalize_operation:131`, `normalize_action:249`, `_operation_dependencies:301`,
`canonical_digest:322`, `file_sha256:328`, `prepare:333`, `public_prepared:344`,
`operation_summary:349` — с дословными текстами отказов и полным native-поведением prepare.
`replace_raw` в C.23 **не используется**, ADR-0016 не расширяется, ADR-0017 не пишется,
принятые `write_preview`/`write_apply`/`symbol_rename` не трогаются. Отсутствие apply
фиксируется в «Намеренной границе» и в `parity.md` как `prepare-only`; этап механики остаётся **0**.

**D15. Применение — отдельный срез C.24, с ADR-0017 proposed.**
Там решается ровно один вопрос: **кто производит transformed bytes**. Два допустимых ответа —
(а) engine/editor transformer-port (ResourceLoader/ResourceSaver через редакторскую ветку;
потребует `editor/**` и моего отдельного разрешения на него), (б) собственная текстовая
трансформация секций с байтовым сохранением входа (BOM/EOL/одиночный CR) — **явное отклонение**
от native, потому что Godot 4.6.3 отвергает BOM и приводит CRLF/lone CR к LF. Выбор делает
портер пробами, я утверждаю в C.24; до этого ни `replace_raw`-для-ресурсов, ни «молчаливое»
### §11 — допуск к инфраструктуре: решение аудитора (D17)

**Разрешаю четыре файла из пяти, `resource_read.py` — нет.** Причина отказа не в осторожности:
`substrate/fs` — общий порт для всех механик, и второй read-порт рядом с `DiskFileSystem`
создаёт две правды о containment. Резолв-чтение делается **module-owned портом** в
`python/modules/editing/resource_ops/ports.py` поверх существующего `fs`
(`read_raw`/`is_file`/`exists` + нормализация в модуле), как это уже сделано в C.21 (D6)
и C.22 (`ports.py`/`sync_ports.py`). Если после этого останется настоящая дыра
(`resolve()` с realpath наружу) — присылаешь пробу, и я решаю отдельно, а не превентивно.

**1. `tools/selfcheck.py` — разрешён, узко.** Изменение только в том, что «корпус находится
по `module_id`», а не по списку инструментов: tool-less вклад должен получать вердикт
`corpus` наравне с остальными. Запрещено: трогать `_owner`/`check_unit`/селектор,
менять единицы и порядок целей, трогать `run_device`/`STATIC_CHECKS`, менять формат отчёта.
Доказательства: 64 пина C.19 зелёные, `editing.file_refactor`/`split_py`/`split_gd` и
`class_api`/`node_info`/`tree` сохраняют **свои** числа (124/52, 583/107, 625/102, 128/26,
247/65, 116/40), после прогона всех 44 selfcheck **43 отчёта байт-в-байт**, изменён только
`editing.resource_ops.json`. Плюс новый пин: tool-less модуль с корпусом получает `corpus`,
а не `not_implemented`. Новый SHA `selfcheck.py` становится эталоном; принятие C.19 байтами
не пересматривается — оно пинило поведение, и оно обязано остаться прежним.

**2. `tools/snapshot_diff.py` — разрешён, узко.** Внутренний маршрут объявляется **полем кейса**
(например `internal_call` рядом с `native_call`), существующие 909 кейсов и их `native_call`
не трогаются. Доказательство: `snapshot_diff` даёт ровно **909/0** до добавления кейсов среза
и `909 + N`/0 после; формат старых кейсов побайтово тот же.

**3. `tools/probe.py` — разрешён.** Клиент подготовки без публичного инструмента; никаких
новых публичных имён, только вызов внутреннего маршрута.

**4. `python/runtime/bootstrap.py` — разрешён, только сборка.** Добавляется сборка
module-owned порта `resource_ops`; существующие порты, их имена и порядок не меняются.
Доказательство: тесты bootstrap/agent зелёные, `security_audit` без новых находок,
импорт-побочек нет.

**5. `python/substrate/fs/resource_read.py` — отклонён** (см. выше). Если считаешь, что без
него резолв невозможен, приложи к следующему STOP пробу: что именно не выражается через
`read_raw`/`is_file`/`exists` + `realpath` в модуле.

Границы неизменны: принятые write-модули, generic guards, `editor/**`, ADR, контракт (27)
и таблица механик не трогаются. Все правки — в «Намеренную границу» и в `deviations.md`
закрытым списком с причиной «tool-less вклад без публичного инструмента».

изменение назначения ADR-0016 недопустимы. Расширение назначения `replace_raw` оформляется
**новым ADR-0017 `proposed`**, а не правкой принятого ADR-0016.

**D16. Политика: разрешаю module-local resource policy, generic guard не ослабляется.**
В C.23 (prepare) и C.24 (apply) действует следующее, и это записывается в
`docs/security/invariants.md` (SEC-23) и в «Намеренную границу»:

* `target` **и** `dependency` проверяются одинаково, `resolved identity + casefold`, **до** плана,
  затем общий `guard_path`/`guard_transfer` как второй барьер;
* запрещены (регистронезависимо): `addons/**` включая `ADDONS/**`, `.agent_history` включая
  `.AGENT_HISTORY`, `project.godot` (и как target, и как dependency), выход за проект (`res://../`);
  trusted-флаги `allow_addons`/`allow_self_edit` в C.23/C.24 **не поддерживаются** —
  поведение записывается как отклонение («trusted addon edits не портированы»);
* корневой `plugin.cfg`: схема native его как dependency допускает, наш read-policy —
  тоже разрешает чтение, но **записи** в него нет; если проба покажет иное — стоп;
* `realpath`-containment обязателен на чтении и записи (lexical casefold симлинки не закрывает);
* порядок отказов — как `_path:58–72`: policy → extension → safe resolution → isfile;
  тексты — дословные native (`Ресурсы аддонов разрешены только по явному запросу…`,
  `Ресурс не найден: …`), наш `kind` маппится отдельно и не подменяет текст.

Остальные отклонения из §10.5 («preserving BOM/EOL вместо ResourceSaver», «strict AppError kind
вместо MCP-отказа с isError=false», «editor-only отказы не симулируются») — принимаются
**только** в редакции D14/D15: в C.23 они не нужны вовсе (нет записи), в C.24 идут закрытым
списком в `deviations.md`.

### 6. Политика, actual против current



Native project_tools:197–211,384–438 использует resolved identity/casefold,
валидированный server addon root и независимые trusted allow_addons/self_edit.
Model prose/JSON не включает эти флаги. Пробы `schema-raw/*` сняты actual-native,
включая обе роли и все четыре сочетания trusted bool flags.

| Путь | Native resource schema | Existing guard_path (default policy) |
|---|---|---|
| addons/**, ADDONS/** | target/dependency denied; allow_addons с valid addon_dir разрешает other addon | lowercase denied; uppercase lexical alias **пропускается** |
| agent addon | allow_self_edit независимо от allow_addons; обе формы resolved | lowercase закрыт; generic policy case-sensitive |
| root plugin.cfg | target unsupported extension; dependency schema разрешает | target always denied |
| project.godot | target **и dependency** denied generic write policy до extension | generic guard **разрешает** |
| .agent_history и .AGENT_HISTORY | target/dependency denied | lowercase denied; uppercase **пропускается** |
| res://../outside.tres | denied policy до existence/extension | denied normalization |
| missing file / directory.tres | `Ресурс не найден: ...` после policy | guard лишь lexical/policy, не existence |

Дословный native policy отказ для перечисленных blocked paths:
`Ресурсы аддонов разрешены только по явному запросу и текущей политике доступа`;
он употребляется также для outside/history/project, не только addon.
_path policy→extension→safe resolution→isfile:58–72 не переупорядочивается.
Dependency plugin.cfg принят **схемой**, ResourceLoader-success этого не следует.

guard_transfer casefold закрывает addon/history/project и agent relocation,
но это policy **переноса**: применять его к replace_raw значило бы запретить
разрешённый trusted addon edit и изменить семантику. Он не заменяет resource
target/dependency guards. Generic PathPolicy/guard_path не ослаблять/не править.
Предлагается module-local native-equivalent resolved/read policy до plan,
затем shared guard_path как второй барьер. Решение о trusted addon edits и
dependency plugin.cfg должно быть явным; payload не расширяет capabilities.
Realpath containment при read/write остаётся обязательным, lexical casefold
сам по себе не закрывает symlinks. Production security invariant/test нужны
до нового write boundary; сейчас оба не написаны до решения.

### 7. Старые кейсы и будущий корпус

AST readonly census, не запуск старых тестов:

- test_resource_actions.py — **3 test_ functions, 10 assert nodes**;
- test_resource_action_flow.py — **0 test_ functions**, 1 executable flow,
  **23 assert nodes**; before/after file mutation и semantic hashes в нём
  подставляются, поэтому это источник сценариев, не actual apply evidence;
- test_path_policy_safety.py — **12 unittest test_ methods**, 0 bare assert
  nodes (проверки unittest); use только relevant resource access cases.

Исторические tests-map counts7/8/18 — не новые pytest counts; строки не удалены,
не пересчитаны задним числом. Resource строки113–114 нужно после решения
переадресовать с scene_model.node_rename/.tscn на resource_ops/.tres, сохранив
их судьбу corpus и историю. Копировать/запускать старый код тестов не надо.

Actual evidence сейчас: **74** read-only calls (**64 native + 10 current**),
34 success / 40 error; input byte tree exact для каждого. JSON `schema-index`,
`schema-inputs`, `schema-raw` содержат payload/result/exception text/raw SHA;
tuple normalize_action представлен JSON array, не считается client schema.
Дополнительно 7 actual-engine fixtures и 6 current pure-op byte comparisons,
MCP sessions отдельно: эти числа **не складываются в native corpus/test count**.
Первый дополнительный MCP driver остановился после user response из-за
agent-authored обращения isError вместо SDK is_error; первый payload сохранён,
v2 снят отдельно. Это ошибка диагностики, не native отказ/production defect.

Будущий corpus после решения: success каждой из6 групп, tagged scalar/ResourcePath/
NewSubresource/embedded target; все exact/missing/unknown/limits/type/value
отказы и их precedence; dependency dedup/digest/public/raw before hash;
missing/non-tres/directory/path escape/addon aliases/agent flags/history aliases/
plugin.cfg/project.godot; BOM/CRLF/mixed/loneCR/no-final-newline. После выбора
byte producer отдельно actual apply/occupied target/stale/repeat/rollback/
foreign-state/crash-gap. Отказы и serializer limitations не заменять выдуманными
успехами. После approval расширить actual probes на ещё не снятые nested limits,
animation/sprite/theme/tile edge cases и настоящий editor UID/execute/history.

Формат как C.21/C.22: external raw request + actual response/exception с origin,
before/after files и raw SHA/байты; в corpus fixture bytes + payload + reference
projection + manifest SHA. UUID/engine-generated ids фиксировать как переменные
только явно выбранной проекцией; не редактировать oracle ради совпадения.
Существующие чужие корпуса/manifest остаются frozen. Red/M1–M3/P1–P3 ещё
не запускались: до ответа это было бы запрещённым продолжением production цикла.

## Проверки / машинный вердикт

Дословный существенный stdout `python tools/selfcheck.py editing.resource_ops`:

```text
selfcheck editing.resource_ops
  module         not_implemented заготовка: RuntimeError: python.modules.editing.resource_ops.module: нет MODULE (R-05)
  layers         ok              файлов 558, нарушений нет
  limits         ok              файлов 558, предупреждений 1
  contract       ok              артефактов 27, расхождений нет
  security       ok              нарушений нет
  unit           not_implemented тестов модуля нет: python/modules/editing/resource_ops/tests
  corpus         not_implemented нет корпуса механики: fixtures/corpus/editing/resource_ops
вердикт: blocked
```

Exit **2**. Fresh JSON SHA
`6f4a3b573e3a5159019c7593a037c4c968ad6fa0ea52d21dc37a9c3b8037c29f`;
stdout SHA `9e9882c8a19e95da742f5769212cd99cf9d143b5dc2a4392c28bd8611feca672`.
Canonical до/после byte copy SHA
`900ce0236cb51c1ce14caa3d8588c8d364831b70e14398ffb26609f78e1614c4`;
**все44** canonical bytes exact. Это не ручное редактирование JSON.
Fresh evidence снаружи; full non-live/snapshot/live3 не выполнялись и база §0
не заменяется. Static checks исполнены самим selfcheck, tools/selfcheck.py exact.

Final boundary/EOL/WORKLOG-prefix proof и SHA-таблица всех changed docs и
внешнего evidence будут `boundary-proof.json` и `SHA256-final.md` в досье.
SHA-таблица создаётся **последней**, после записей; в лист её собственный SHA
не вписывается, чтобы не менять уже хешированный лист.

## Блокеры / следующее действие

**Исторический STOP preflight §6 (3/5), снят для C.23 решениями D14–D16:** native apply требует редакторского semantic byte producer,
не имеющего одобренного порта в нынешнем scope; ResourceSaver противоречит
требованию input BOM/EOL preservation. Использование replace_raw для C.23
вне буквальной ADR-0016 границы и возможный public dispatch требовали решения.
D14 исключил apply/public dispatch из C.23, D15 отложил применение в C.24,
D16 утвердил module-local policy. Эти вопросы повторно не запрашиваются.

## §11 — STOP §6(5): проверочная инфраструктура и resolved read seam

Это новый узкий STOP, не пересмотр D14–D16. Необходимые файлы отсутствуют
в закрытом списке §1 start-prompt, а tools/selfcheck.py прямо запрещён.

### Машинно подтверждённый разрыв

1. `tools/selfcheck.py:282–287` обходит корпус любого tool-less вклада, кроме
   editing.file_refactor. Внешняя чистая диагностика подставила **только в память**
   hypothetical ModuleSpec resource_ops с TOOLS=(), contributes_to=write_preview.
   `check_corpus` вернул дословно `ok / корпуса нет: вклад в write_preview (схемы
   и фейк вместо корпуса)`; обращений к corpus_folders/run_check — **0**, самого
   resource-корпуса нет. Это не red-тест и не настоящий green-вердикт механики.
   При неизменном файле future selfcheck мог бы написать ok, не сверив ни одного
   resource case; такая сдача нарушает R-09/R-18 и требования пользователя.
2. `tools/snapshot_diff.py:308–331` знает internal route только для file_refactor;
   остальные записи уходят в agent.call(tool, args). Resource public tool по D14
   отсутствует. `module_tools` возвращает resource_ops как фильтр, не исполнитель.
   `tools/probe.py:242–245` также умеет internal client только для file_refactor.
   Поддельный ToolSpec, monkeypatch в production/тесте и встраивание resource
   corpus в accepted file_refactor не являются допустимыми обходами.
3. `fs` и `paths_fs` не открывают public resolved identity. DiskFileSystem._resolve
   — private containment helper и возвращает lexical full path, не resolved
   относительную identity. Из is_file/exists/read_raw нельзя отличить безопасную
   lexical ссылку в addons/.agent_history/project.godot от разрешённого ресурса.
   Прямой os/pathlib IO в domain и импорт substrate модулем запрещены R-11/R-13.
   Native file_sha256:328–330 читает все raw bytes без общего read_text cap;
   новый resource read seam не должен молча наследовать чужой лимит чтения.

### Минимальное запрашиваемое расширение closed scope

| Файл | Только разрешаемая дельта |
|---|---|
| `tools/selfcheck.py` | провести editing.resource_ops через существующий corpus_folders → corpus_readiness → snapshot_diff; не давать tool-less resource обход corpus, не менять прежние C.19/C.22 дельты |
| `tools/snapshot_diff.py` | internal resource prepare corpus route; полное сравнение формы и дословного message отказа, не новый public tool и не изменение соседних проекций |
| `tools/probe.py` | internal resource prepare client как C.22, без MCP/ToolSpec, вывод только native public_prepared |
| `python/substrate/fs/resource_read.py` (новый) | физический read-only порт resource_fs: contained resolved identity, is_file, raw read для SHA; никаких write/effect methods |
| `python/runtime/bootstrap.py` | только импорт/сборка этого read-only resource_fs в default_ports; без resource-логики, изменений generic policy/guards и accepted write-веток |

Новые проверки этих дельт остаются в уже разрешённых test_resource* путях.
ModuleSpec/loader/registry, accepted write_preview/write_apply/symbol_rename,
editor/**, editor verbs, ADR и публичный контракт менять не требуется.
SEC-23 будет записан до production; исключения безопасности не запрашиваются.

### Свежая база и реально выполненные проверки

Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c23-prepare-scope-20261102/`.
До первой новой repository-правки сохранены baseline.json/baseline.zip целого
дерева после auditor D14–D16; worksheet **39252 B**, SHA256
`dea2c2643211e94de11f413a3559575bf34454abaa5d54455d28305edbe321df`.
Audit **3437/813/83**, raw **3472/832**; native **947** файлов exact, все три
resource_actions pins 19642 B/edef3381…bbc5; project.godot335 B exact.

Реальный `python tools/selfcheck.py editing.resource_ops`: **exit 2 / blocked**;
MODULE/unit/corpus not_implemented, layers558/0, limits558/1 прежний info,
contract27/0, security0. Полный stdout: selfcheck.stdout; fresh report1133 B/SHA
`6f4a3b573e3a5159019c7593a037c4c968ad6fa0ea52d21dc37a9c3b8037c29f`;
stdout721 B/SHA `9e9882c8a19e95da742f5769212cd99cf9d143b5dc2a4392c28bd8611feca672`.
Все **44** canonical reports побайтово восстановлены из исходных bytes.
integration-gap.json и integration-fragments.txt фиксируют диагностический
skip и строки инфраструктуры. После проб всё repository/native/project byte-exact.
Non-live4483, snapshots909, all-selfchecks и live3 на этом STOP не перезапускались;
они не заменяются гипотетической диагностикой. Production/red/corpus/ADR0.

**Историческое следующее действие до D17:** разрешение на пять файлов таблицы §11.
Оно заменено D17: четыре разрешены, substrate read-порт отклонён.
Stage0/skeleton и auditor D14–D17 сохраняются; долги C.22 не исправляются.

Это документация STOP, **не сдача C.23**. SHA256-final.md в новом досье создаётся
последней после WORKLOG(ab/CRLF), проверки всего prefix и boundary proof.

## D17 — продолжение после допуска (2026-11-02)

До правок сохранён новый внешний baseline.json/baseline.zip в
`C:/Users/Lich/AppData/Local/Temp/opencode/c23-d17-20261102/`: worksheet52662B/LF,
audit3437/813/83, raw3472/832, native947exact, contract27, reports44.
Весь auditor block (включая нынешнее расположение D17 внутри D15) сохранён
отдельными исходными bytes; его текст и порядок не исправляются.

Реальная проба read_probe.py/read-seam-proof.json: Windows junctions в addons,
history и наружу; resolved/casefold запрещает первые два, fs повторно запрещает
escape PermissionError. ADDONS/.AGENT_HISTORY/PROJECT.GODOT запрещены; root
plugin.cfg читается. Default fs отказал на4194305B errno27; тот же существующий
DiskFileSystem с max_bytes=sys.maxsize прочитал4194305B побайтово (SHA
8d3d3c04baadfd31cbebf771836900097b5f36cc142b74e40747c7b372beab8b).
Файловый symlink не доступен WinError1314; использованы реальные directory
junctions без mock. Repository/native/project bytes не изменились пробой.
Это проверка достаточности D17, не production и не native corpus parity.

**Следующее действие:** расширить native refusal diagnostics и losslessly
оформить64native+10current с provenance; затем новые red-пины с внешним JUnit.

### Corpus/spec/red перед production

Snapshot before909/0 и C.19 before64/64 сохранены снаружи. Generated corpus185
cases:63 resource calls исходной съёмки +122 expanded; отдельно все74 diagnostics
(64native/10current), original и masked SHA, полные before/after, native_call рядом
с internal_call. Transaction refusal/current guard evidence не выдаётся за parity.
AppError: policy→denied, missing/dir→not_found, прочая schema→invalid_input;
message дословный, hint пустой. Полное сравнение C.23 включает error.message.

Внутренний API: entrypoints normalize_action/prepare/file_sha256/canonical_digest/
public_prepared/operation_summary; input action или соответствующий native value.
normalize возвращает action + relative target (без absolute); prepare — ровно
native семь полей, public_prepared — ровно четыре, UUID32hex маскируется только
для corpus comparison. No apply/byte producer/ресурсный WritePlan/WAL.
Ports: ResourceRead получает существующий fs; snapshot только metadata identity/
is_file для res:// строк, domain получает факты и соблюдает native order;
raw read/hash — только после полной нормализации в app. Domain без IO/foreign
imports; canonical JSON — существующий kernel.canonical_json.
Target guard_path, dependencies guard_transfer — дополнительные неизменённые
барьеры после module-local policy; plugin.cfg не становится write endpoint.

Новые431пина collected/executed до production (unit176/integration188/security60/
formats7), red.xml снаружи; код absent и routing defect красные, без skip/xfail.
**Следующее действие:** ports → pure domain → app/metadata; четыре узких D17
инфраструктурных дельты, затем green и double corpus.

### D17 — production prepare-only и предельные кейсы

Реализованы module-owned read-only ports, чистая схема и Variant validation,
короткий app, metadata-only MODULE и TOOLS=(). Единственные инфраструктурные
дельты — закрытый список D17. Первые gates: 431/431 green; snapshot909+185/0;
C.19 64/64; layers560/0; limits560/0 с одним прежним split_py warning;
security без нарушений; contract27/0. Это прогон, не приёмка/назначение этапа.

Дополнительно46 native-only кейсов: теперь231 executable +74 diagnostics.
Максимумы20operations,32imports/properties/subresources,8target,512keys/tiles,
256frames и соседние отказы; scalar/vector/NodePath, root res://, ./ и backslash.
Исходные185карточек/74diagnostics не перезаписаны; native before/after совпали.
Capture сначала отказал до записи из-за import root, исправленный запуск exit0.
Реальные disk-кейсы совпали сразу; три pure-пина выявили неполные root/./ metadata
факты в тесте. Исправлена фабрика фактов, не expectations/native карточки.

Физическая containment использует native normcase (case-sensitive на POSIX),
защищённые относительные identities — отдельный casefold. После raw-read порт
повторно проверяет resolved identity. Security пины: no raw-read до полной
схемы/политики, настоящая junction-подмена после чтения, read-only API.
Contract пины: ровно шесть internal entrypoints, apply/replace_raw/динамический
dispatch запрещены. Root metadata is_file=False; fixture клиента — basename.

**Следующее действие:** двойной full collect/run, все44selfcheck и точное
восстановление43соседнихreports, double snapshot, live3, mutations/substrate,
финальная документация и последняя SHA-таблица. Resource_ops 0/skeleton,
C.24 не начат; готовность к аудиту пока не заявляется.

### Завершение предельных отказов и R-06

Первый all44 прогон обнаружил R-06: editing8010>8000 после последних дополнений.
Этот fail сохранён снаружи. Семь пинов canonical digest/number перенесены из unit
в новый C.23 contract-файл: меняется расположение тестов, не selector, кейсы или
бизнес-код. Повторный limits —560 файлов, zero violations, прежний split_py warning.
Двойной full после переноса: collect=executed5012, failed/skipped0 в обоих прогонах.

Прямая native/current диагностика обнаружила два несовпадения текста в отдельной
ветке normalize_action(require_exists=False): escape и .agent_history. Добавлены
native-only карточки232–233, исходные231/74 не перезаписаны. Четыре независимых
pure/integration пина действительно red; затем сохранён native порядок safe
resolution refusal перед policy. Regular _path и preparerequire_exists=True
не меняются; AppError.kind остаётся denied, exact message берётся из native.

Четыре scoped мутанта пойманы: addons-policy8fail, rawCRLF hash2fail, tool-less
corpus skip1fail, пропуск exact error comparison1fail. Все четыре исходника
восстановлены byte-exact; коллекционных ошибок/skip нет в действительных
mutation-пусках. Неверный -k дал deselected/exit5 и не считается mutant evidence.

**Следующее действие:** green233, двойной native/snapshot/full5016, свежие44selfcheck
и43exact restore, затем финальная запись/последняя SHA-таблица и независимый аудит.

### Safe dependency alias — последняя сверка resolved identity

Native success и current denied для `res://unused/../old.tres` подтверждены прямым
prepare diagnostic без эффектов. Карточки234–235 native-only; текущий prepare pin
действительно red, normalize success служит контрольным случаем. Общий guard_transfer
получает повторно проверенный resolved relative dependency, а не исходную строку.
Сам guard не изменён: addons/history/project/реальный escape по-прежнему отклоняются
до него, plugin.cfg остаётся только read dependency. Native normalized action и
digest сохраняют исходное представление пути, canonical identity используется
исключительно для проверки/чтения. Это D16 parity, не расширение прав.

Последний R-06 fail8002 также сохранён: helper response/digest/summary корпусные
кейсы размещены в C.23 contract tests, schema cases остаются module unit. Тесты
не удалены, old-код не скопирован, selector/лимит не изменён. После235cards полный
набор C.23 содержит536 пинов, полный non-live ожидает5019.

Этот промежуточный next action закрыт результатами ниже; этап0/skeleton сохранён.

## C.23 — итог для независимого аудита (не приёмка)

**C.23 готов к независимому аудиту, не принято.** Только schema/normalize,
dependencies/digest/raw SHA/prepare/public/summary. `TOOLS=()`, публичных resource
имён и новых capability artifacts нет. Apply, transformed bytes, resource
replace_raw, ResourceSaver и ADR-0017 не переносились: это отдельное разрешение C.24.
Trusted addon edits не портированы — явная D16 deviation, не native-success parity.

Фактический вывод `python tools/selfcheck.py editing.resource_ops`
(`selfcheck-editing.resource_ops-closed.stdout`, exit0):

```text
selfcheck editing.resource_ops
  module         ok              editing.resource_ops (вклад в write_preview)
  layers         ok              файлов 560, нарушений нет
  limits         ok              файлов 560, предупреждений 1
  contract       ok              артефактов 27, расхождений нет
  security       ok              нарушений нет
  unit           ok              452 passed in 25.11s
  corpus         ok              кейсов 235, расхождений нет
вердикт: ok
```

Итоговые свидетельства в
`C:/Users/Lich/AppData/Local/Temp/opencode/c23-d17-20261102/`:

| Проверка | Фактический результат | Свидетельство |
|---|---|---|
| Независимый native replay | дважды235/0; old tests не импортировались | native-replay-235-proof.json |
| Snapshot до/после |909/0 до новых cards; дважды1144=909+235/0 после; прежние909 неизменны | snapshot-before, snapshot235a/b |
| Полный non-live | дважды collect5019=executed5019,0failures/errors/skips | full-closed-proof.json, full-closed1/2.xml |
| C.23 tests |536passed; selfcheck unit452 — свой сохранённый selector | green-closed.xml |
| C.19 |64passed; owner/check_unit/target order/multiplicity неизменны | c19-closed.xml |
| All44 selfchecks |27ok/17baseline blocked/0fail;43 canonical reports восстановлены byte-exact | all44-closed-proof.json, fresh-selfchecks-closed/ |
| Live infrastructure |3passed/0skips; не ресурсный apply | live3.xml, live-proof.json |
| Статика |layers560/0, limits560/0, security0, contract27/0 | layers/limits/security/contract-closed |
| Импорт |4imports,0file-write/process/socket effects | import-closed-proof.json |
| Клиент prepare |exit0, native seven-field preview, raw before_hash | probe-closed.stdout |
| Реальные границы fs |junctions into addons/history/outside;4MiB+1 raw read; read-time identity attack fail-closed | read-seam-proof.json, security tests |
| Четыре мутации |8/2/1/1 assertion failures; база каждого цикла восстановлена byte-exact | mutant-policy/raw/corpus/message proofs |

Соседи сохранены: file_refactor124/52, split_py583/107, split_gd625/102,
class_api128/26, node_info247/65, tree116/40. Global split_py108 остаётся отдельным
полным корпусом, не повод менять module-filtered107. Новая ссылка selfcheck SHA256:
`004daa4edbae4d636b69183c1c6e1cd06105be82febdd8352919e04a220e5731`.

Перед финальной записью boundary check подтвердил3771audit files/829dirs/83gdUID
(raw3806/848), editing7997≤8000, без удалённых файлов и без выхода за closed scope.
Единственное предупреждение limits — прежний split_py11items, нового нет.
Native947files, три19642B source pins и внешний project.godot335B остались byte-exact.
Live recipe335→419→335 восстановлена; удалены только witnessed-new UID,
preexisting raw84/audit83 сохранены. Auditor block,43reports, mechanic table,
contract27, accepted write/editor/ADRs и пользовательские C.22 долги не изменены.

SEC-23 и tests-map приведены к LF без изменения текста соседей: у tests-map
текстуально изменились только113–114, все строки/исторические counts/fates/order
сохранены. WORKLOG дополняется исключительно binary `ab`+CRLF с доказательством
неизменного полного префикса; CRCRLF0. Финальные boundary и SHA-таблица выполняются
после этой документации и последнего append; сама таблица создаётся последней.

**Следующее действие:** независимому аудитору проверить prepare-only parity,
SEC-23, четыре D17 seams и внешние доказательства; только аудитор решает приёмку.
Портер не меняет0/skeleton/ported и не начинает C.24.

## C.24 — запись: STOP §6 по входному числу файлов (2026-11-02)

Постановка `_start-prompt.resource_ops_apply.md` прочитана полностью. Она
фиксирует приёмку C.23 аудитом; исторические записи C.23 выше, таблица механик
и статусы ADR портером не переписываются. ADR-0017 отсутствует; источник
transformed bytes ещё не выбран и не утверждён. Production C.24 не начат.

До F1 и новых native-проб сняты внешний byte baseline/zip и source pins:
`C:/Users/Lich/AppData/Local/Temp/opencode/c24-write-preflight-20261102/`.

| Входной показатель | Фиксированная база §0 | Факт до наших правок |
|---|---:|---:|
| audit files | 3771 | **3772** |
| audit directories | 829 | 829 |
| audit `.gd.uid` | 83 | 83 |
| prompts (`_start-prompt*.md`) | 43 | 43 |
| ADR / reports / contract artifacts | 16 / 44 / 27 | 16 / 44 / 27 |

Raw census:3807files/848dirs. Побайтовая проекция закрытого C.23 собрана из
его baseline и final-sha256.json: изменённых/удалённых файлов **0/0**, новый
файл **ровно один** — `docs/porting/_start-prompt.resource_ops_apply.md`.
Это обнаруженный пользовательский файл, он не удаляется и не исключается
из счётчика. База §0 не заменяется пересчитанным числом без решения аудитора.

Native947files совпадают с frozen baseline; три resource_actions19642B имеют
SHA `edef33817b0f5e9a9885dae55648b2c0c01fa2a8f908c07b10007fa1ff7fbbc5`.
Внешний project.godot335B/SHA958b3a92… точен. Selfcheck16700B/SHA004daa4e…
не менялся: F1-условие подтверждено в tools/selfcheck.py:286, но не удалено.

Actual `python -B tools/selfcheck.py editing.resource_ops --json`: **exit0/ok**,
unit452passed/12.65s, corpus235/0, layers560/0, limits560/1прежнееwarning,
security0, contract27/0. Fresh report957B/SHA
`6ff2c80e8430e25451b856047d88231322ddafa2161d1a56b34c7f93ef5a92ed` сохранён
снаружи; все44canonical reports восстановлены byte-copy и SHA-проверкой.
Stderr392B содержит8 `recovery … action=expired`, не ошибки тестов;
сырой вывод сохранён, stderr0 не заявляется. Полный non-live5019, snapshot1144,
64C.19pins, соседние selfcheck и live3 сейчас не перезапускались.

**STOP §6:** §0 не сходится по одному файлу. F1, 3–4actual-native применения,
ответы §10, ADR-0017, red/production/corpus C.24 не выполнялись. Пробы C.23
не выдаются за новые пробы применения. C.24 не готов к аудиту и не принят.

**Следующее действие:** получить решение аудитора о базе3771→3772 из-за самой
постановки C.24; затем снять F1 и выполнить новые native-write пробы до ответа §10.

## C.24 — запись: F1 и §10-пробы, STOP до решения аудитора (2026-11-02)

Аудитор подтвердил базу **3772/829/83**, prompts43, и сам исправил §0 постановки.
Свежий baseline/zip снят до F1: относительно первого STOP изменился только
пользовательский промпт; native947/source pins3/project.godot335B exact.
Записи приёмки C.23 принадлежат аудитору: исторические блоки, этапы, таблица
механик, parity и статусы ADR этим продолжением не меняются.

Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c24-f1-native-20261102/`.
Первое STOP-досье и закрытый C.23 не перезаписывались. Здесь только F1,
диагностический внешний harness и ответы §10; production resource-write,
ADR-0017, новые repository tests/corpus/SEC-24 **не начаты**.

### F1 — фактическая узкая правка и проверки

В `tools/selfcheck.py:286` удалено ровно
` and module_id != "editing.file_refactor"`; все остальные байты exact.
SHA до: `004daa4edbae4d636b69183c1c6e1cd06105be82febdd8352919e04a220e5731`
(16700B); после: `7f066391665b003a2965cd68c187ea8dc7a8703a91320f08078c929b17ebe389`
(16659B). Проверка exact single deletion находится в `F1-proof.json`.

| Actual selfcheck | unit collect = executed | corpus / diff | Вердикт |
|---|---:|---:|---|
| editing.file_refactor |124|52/0|ok|
| editing.resource_ops |452|235/0|ok|
| editing.split_py |583|107/0|ok|
| editing.split_gd |625|102/0|ok|
| engine_kb.class_api |128|26/0|ok|
| scene_model.node_info |247|65/0|ok|
| scene_model.tree |116|40/0|ok|

В каждом actual unit-run fail/error/skip0; XML, collect, stdout/stderr и свежие
отчёты сохранены снаружи. Все44canonical reports возвращены byte-copy из
baseline и SHA-проверены, не редактировались как JSON. Resource XML58313B/SHA
`cb1421d60719ffd8435f59792c101ca96b6d33b0e470be708f1dcedf234afc23`.
C.19 до/после: **64 collected =64 executed, fail/error/skip0**; XML11254B,
SHA до `d5ccbe6161e68e149da643b7f3b1ba50580df5c08d36a435e285ad54e45ea072`,
после `338b616ba41f758bc6c3dca667bb1732d1ae6f68ee54f1a342d5d759fc84bc2c`.
Actual resource selfcheck: exit0/ok,452passed/12.81s,235/0; layers560/0,
limits560/1прежнееsplit_py warning, contract27/0, security0.
Отдельно actual probe resource_ops prepare: exit0/ok, raw-target unchanged;
security_audit/lint_arch/check_limits/gen_contract --check: exit0/ok.
Полные5019, snapshot1144 и live3 в этом подготовительном STOP не перезапускались.

### Native-пробы — новый полный механический путь, не helper-замена

Godot **4.6.3-stable official 7d41c59c4**, настоящий headless EditorPlugin.
Внешний проект содержит byte-exact копии native executor, полного
agent_panel_part1, agent_server и agent_locale. Native Python host импортирован
с `-B`; исходники и native947files не меняются. Используются оригинальные
panel prepare/execute, host prepare/confirm/finalize, native history/rollback.
State-only panel witness заменяет только UI-состояние и фиксирует запрос
finalize; handler вызван в Flask request_context, не через HTTP. Поэтому
**UI-клик, HTTP/auth/admission и end-to-end транспорт не доказаны и не заявлены**.
Семантические хэши, dependency fingerprint, успешный result и UID получены
реальным executor; нет fake ResourceSaver, EditorPlugin или успешного ответа.
Execution token остаётся только в памяти host и редактируется в evidence;
ключи/токены/пароли не записываются в проект или досье.

| Проба | Операции | Вход → native output | Commit / rollback |
|---|---|---|---|
|P1 Animation без final LF|set_property + animation_add_value_track|177→436B; добавлен final LF, комментарий удалён|реальный commit;177B exact|
|P2 Theme CRLF|set_property + replace_reference + theme_set_item(NewSubresource)|294→386B;8CRLF→LF; новые ext/sub секции и IDs|реальный commit;294B exact|
|P3 SpriteFrames lone CR|sprite_frames_add_animation|77→362B;3loneCR→LF; materialized default + walk animations|реальный commit;77B exact|
|P4 TileSet LF|tileset_add_atlas_source|72→336B; ext Texture2D + sub TileSetAtlasSource + sources/7|реальный commit;72B exact|
|N1 Theme BOM+CRLF, отдельный негатив|theme_set_item, prepare и execute|load_failed;76B/SHA unchanged|history reservation/commit отсутствуют|

У всех4применений prepare не меняет raw target, реальные UID сохранены,
reserved→committed journal и addressed rollback получены; повторный **finalize**
идемпотентен. Это не повторный apply. Обе texture dependency byte-exact.
Payload/result/error, before/after/rollback.bytes и полный SHA — в каждом
`native-r2/<probe>/`, сводка `native-proof.json`/`native-supplement-proof.json`.
У N1 реальный stderr: `Parse Error: Expected '['.` и executor `load_failed`.
Начальная попытка harness имела missing agent_locale/timeout, не успех;
диагностика сохранена в `native-first-attempt.json`, исправление только снаружи.
Первый P1 не повторялся из-за ошибочно широкой проверки debris: native создал
folding metadata `.godot/editor/*agent-resource*cfg`. Эти4внешних cache-файла
сохранены как evidence; resource staging/backup вне cache отсутствуют.
Гигиена repository проверяется отдельно, не смешивается с внешним Godot cache.

Дословные source fragments с исходными номерами строк и SHA находятся в
`source-fragments/` (10файлов+index). Ключевые строки frozen executor/host:

```text
agent_resource_executor.gd
44: 	var applied := _apply_operations(resource, action.get("operations", []), changes)
57: 	var save_error := _save_temporary_resource(resource, temporary_path)
64: 		var uid_error := ResourceSaver.set_uid(temporary_path, uid_before)
78: 	var published := _replace_resource_file(temporary_path, path, temporary_hash, expected_hash)
114: 	return ResourceSaver.save(resource, path)
158: 	var loaded = ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE)
159: 	if not loaded is Resource:
160: 		return _fail("load_failed", "ResourceLoader не смог загрузить ресурс")
python/main.py
3237:             entry_id = history.record_batch_change(
3238:                 project_root, "edit_resource", [prepared["resource"]], *_current_chat_info())
3545:         history.commit_change(project_root, entry_id)
```

### §10.1 — предлагаемый byte producer, ещё не разрешён

Предлагаю **(б): module-local чистый section/span transformer**, не engine-port.
Он читает raw через существующий ResourceRead/DiskFileSystem; domain без IO.
`replace_raw` только публикует произведённые байты, не исполняет resource ops.
Неправленые spans, комментарии, порядок секций, UID, BOM и исходные разделители
сохраняются. Значение existing property меняется своим span; missing property
вставляется в нужную root/sub секцию. Новые ResourcePath/NewSubresource создают
ext/sub секции с детерминированными свободными IDs; existing IDs не перенумеруются.
Существующий load_steps пересчитывается при добавлении секций, UID не меняется.
Track создаёт tracks/<n>/*, SpriteFrames — элемент animations, Theme — нужный
ключ/type/name, TileSet — atlas subresource и sources/<id>; несколько ops одной
цели сворачиваются в один output. Отсутствующий final EOL остаётся отсутствующим;
новые разделители берутся из окружения/первого EOL, нет глобальной нормализации.

Это **предложение**, не реализация и не обещание общего Godot ClassDB-паритета.
Семантика всех6операций должна получить новые actual-native кейсы/проверку
Godot на произведённых байтах. Неизвестные stored property/class/default,
неподдержанный Variant/неоднозначная структура отказываются до PREPARED,
а не считаются успешными. Нужна явная приёмка этой ограниченной текстовой
семантики (§10.5); она не выдаётся за нативный semantic preview.

### §10.2 — native / наше / отклонение

«Наше» ниже — **предложенный контракт после разрешения**, пока не измеренный код.

| Формат | Native, новые actual пробы | Предлагаемое наше | Отклонение |
|---|---|---|---|
|BOM|prepare/execute load_failed, raw76B unchanged|разбирать после BOM, сохранить BOM|BOM-вход принимается вопреки ResourceLoader4.6.3; engine-loadability не обещается|
|CRLF|P2:8CRLF→0, output LF|сохранить CRLF и нетронутые spans|не ResourceSaver-нормализация|
|lone CR|P3:3CR→0, output LF|сохранить lone CR|не ResourceSaver-нормализация|
|нет final LF|P1:false→true|оставить без final EOL|native добавляет, наше не добавляет|
|есть final LF|P4:true→true|сохранить исходный final EOL|на LF-входе совпадение; на CRLF/CR сохраняется иной separator|

### §10.3 — воронка, hash и обратные действия

Новый op **не нужен**. После отдельного ADR-0017 proposed: один
`Step("replace_raw", target, {"bytes_b64": ...}, raw_expected_hash, ...)` на
resolved target; target/dependency policy + casefold + containment до плана,
unchanged guard_path/guard_transfer — второй барьер. Dependencies read-only;
их raw expected SHA можно включить в existing plan.expected без write-step.
Canonical action_digest зависит от нормализованного action, не от BOM/EOL;
raw guards отдельно обеспечивают stale при изменении входа, repeat apply — stale_plan.
Ни output bytes, ни абсолютные пути не попадают в public projection.
Существующий funnel уже делает project lock + preflight всех expected,
raw backup→EFFECT_INTENT→write_raw→RECEIPT→COMMITTED, raw compensation/recovery.
Оригинальный script_edit и accepted ADR-0016 не меняются; ресурсное расширение
replace_raw авторизуется только новым ADR-0017.
Шесть операций action изменяют **один** .tres: subresource встроен, зависимости
не переписываются, нового batch API нет. Если согласованный план содержит
несколько файлов, это несколько unique-target replace_raw steps, общий
preflight до первого эффекта, фиксированный порядок, откат в обратном порядке
receipt/intent; не несколько steps одной цели и не отдельная воронка.

### §10.4 — закрытый список infrastructure, требуется отдельное расширение scope

Все existing write paths достаточны: **без правок** shared/funnel.py,
shared/script_edits.py, write_apply/app.py, rollback/*, substrate/fs/*,
kernel/write_plan.py, runtime/bootstrap.py, tools/probe.py, editor/** и verbs.
Порт/компилятор/entrypoints расширяются только внутри resource_ops; текущие
prepare-only entrypoints остаются прежними, контракт27 не меняется.

Но доступный бюджет editing — **7997/8000**. Обнаружен дефект правила/гейта:
RULES.md:276–278 определяет area overflow как warning с разовым cohesion
обоснованием, а tools/check_limits.py:66–70 записывает его в violations.
Actual check_totals на byte-exact внешней копии editing +4synthetic строки
получил `область8001строк(лимит8000)`; это не production selfcheck.
Evidence: `limits-discrepancy-proof.json`, исходный check_limits byte-exact.

Предлагаемый **единственный дополнительный infrastructure файл**:
`tools/check_limits.py` — привести только area-overflow к R-06 при записанном
cohesion; не менять8000, hard file/app limits, module checks, selectors и не
добавлять resource-specific skip. Нужны новый red resource-test и запись
cohesion в deviations после решения. Этот путь **не входит в исходный §1**:
прошу явное расширение scope, а не подразумеваемое разрешение. Сейчас не правлю.
Без такого решения производственный шаг заблокирован бюджетом/расхождением.

### §10.5 — закрытый предлагаемый список отклонений для нового ADR/deviations

1. **Формат:** сохранить/принимать BOM, CRLF, loneCR и отсутствие final EOL;
   BOM не становится обещанием загрузки Godot, отказ native сохранён в корпусе.
2. **Сериализация:** patch spans вместо полного ResourceSaver rewrite;
   comments/order/existing IDs/UID сохраняются, новые IDs детерминированы,
   defaults/служебные поля materialize только где нужны для6операций.
3. **Валидация:** bounded textual resource/Variant/class/default semantics;
   неподдержанное — явный отказ до плана, не fake ClassDB/semantic_hash.
   Нет native Inspector/game/import-ready checks или editor semantic preview;
   target/dependency raw hashes и SEC-23 policy остаются обязательными.
4. **Lifecycle:** existing WAL/backup/receipt/recovery вместо native
   ResourceSaver temp→reload→publish→history; UID-header сохраняется,
   native preview/cache invalidation/import notifications не добавляются.
5. **Cohesion/лимит:** разовое документированное превышение editing-area
   по R-06 и отдельно разрешённая минимальная согласованность area-гейта.

Других отклонений не предлагается. Принятые D14–D17 и generic guards не
переписываются, engine-port не начинается. Этот список должен утвердить аудитор.

**STOP:** F1/новые native-пробы выполнены; C.24 пока не готов к независимому
аудиту и не принят. До явного ответа §10 нет ADR-0017/red/production/corpus.
**Следующее действие:** решение аудитора по (б), пяти отклонениям и отдельному
scope-extension tools/check_limits.py; после него proposed ADR→red→код→корпус.

### §12 — решения аудитора по §10 C.24 (D18, 2026-11-02)

1. **Вариант (б) утверждён**: чистый section/span-трансформер внутри `resource_ops`.
2. **BOM — ОТКАЗ, а не «принять»**: native на BOM даёт load_failed и не меняет байты — это отказ. Писать BOM-файл, который Godot 4.6.3 не загрузит, хуже паритета. CRLF/lone CR — сохранять, final LF — не добавлять; новые строки получают EOL заменяемой строки, а при вставке — доминирующий EOL файла; mixed EOL пинится кейсом.
3. **Новый op не нужен**: `replace_raw` + raw SHA guard; один step на цель, обратный порядок компенсаций, dependencies не переписываются. Расширение назначения — только ADR-0017 `proposed`.
4. **`tools/check_limits.py` — разрешён узко**: area-overflow становится warning по R-06 **только до явно задокументированного потолка 8400 строк**, выше — error; 8000 не менять, resource-specific исключений не делать; red-тест на 8001-поведение до правки и на 8401 после; запись в deviations и invariants.
5. **Закрытый список отклонений утверждён** с поправкой п.2 (BOM — отказ) и п.4 (cohesion гейт); новые отклонения — только через отдельное решение аудитора.

### §13 — C.24 D18: ADR/red/начальный production (2026-11-02)

Новый byte baseline3772/829/83: относительно закрытого F1-досье изменён только
auditor D18-append листа; source pins/native947/project335 точны. Старые
завершённые dossiers/SHA-таблицы не модифицируются. ADR-0017 **proposed** создан
с пятью ответами; SEC-24 и закрытые deviations записаны до кода.
Actual red-r2:9area collected/executed,6failed/3passed;37resource collected/
executed,37failed/0errors/skips. Первый red сохраняется отдельно: новый helper
имел неверный build_agent positional argument, до production исправлен и red
повторён; ни одного accepted теста не меняли. Начальный green45/46 выявил orphan
track; отдельный mixed append pin дал2failed/45passed, затем исправление pure
span replacement и malformed track refusal. Actual green4:47passed/0/0/0.

Новые domain/document.py и transform.py чистые; token-aware string/comment/
balanced-value spans, шесть bounded operations, deterministic free IDs,
существующие ext/sub spans и UID сохраняются. Existing prepare entrypoints
остались прежними; добавлены prepare_write/apply/transform_summary, TOOLS=().
read_raw расширен только в module-owned ResourceRead поверх existing DiskFS.
write_flow: normalize/target+dependency policy → pure bytes → one replace_raw
step/raw SHA → existing preflight/WAL; apply делегирует public write_apply.
transform_summary — read-only before/after hashes без raw/absolute output,
поддержан существующим data-declared corpus клиентом без tools/probe edits.

Area gate изменён только в разрешённой D18 ветке:8000base,warning до8400,error
выше8400, без feature/per-file исключений; other hard limits неизменны.
Current editing8400 ровно; это не разрешение дальнейшего превышения.
Пока нет C.24 corpus/native validation/double/M1–M3/P1–P3/live3/full all44.
**Следующее действие:** получить actual selfcheck и проверить generated bytes
шести операций реальным Godot/native projection, затем дополнить corpus/safety.
Это продолжение, не приёмка/не stage change; C.23 auditor append остаётся за
пользователем. Evidence: `C:/Users/Lich/AppData/Local/Temp/opencode/c24-d18-20261102/`.

### §14 — STOP §6: принятые C.23 boundary pins (2026-11-02)

Новый manifest столкнулся с принятым `tests/py/contract/test_resource_ops_contract.py`:

```python
29:     assert MODULE.requires_ports == ("resource_read",)
31:     assert set(MODULE.entrypoints) == {"prepare", "normalize_action", "file_sha256", "canonical_digest",
32:                                        "public_prepared", "operation_summary"}
```

Кроме того, :35–40 пинит отказ internal client на `apply`; новая регистрация
дала unavailable вместо invalid_input. Actual отдельный прогон этих двух
selectors:4collected/executed,2failed/2passed/0errors/skips. Accepted test bytes
не менялись. Это §6 «нужна правка принятых тестов», не основание ослабить пин.

**Запрос ограниченного scope:** разрешить только `test_tool_less_manifest_and_fixed_entrypoints`
(:24–32), сохранив no-public tools/contribution/service и все шесть старых
entrypoints; добавить C.24 declared ports/dependency и prepare_write/
transform_summary. Internal client effect refusal :35–40 **не менять**:
убрать собственную новую MODULE apply-регистрацию, использовать existing
public write_apply. app helper и integration вызывают общий apply через caller,
отдельный resource executor не появляется. Других accepted tests не требуется.

Actual R18 selfcheck без XML environment override: exit1/fail, unit460passed
(baseline452+8integration), corpus235/0, limits563/2warnings, contract27/securityok.
Оба новых domain imports json нарушают существующий lint_arch/R-11, layers2fail:
это **мой дефект**, не запрос расширить IO allowlist или изменить гейт. После
разрешения manifest pin — repair собственного pure codec с соблюдением8400.
47focused green и460unit green не выдаются за общий успех; contract pin находится
вне unit selector tool-less модуля и выявлен отдельным настоящим прогоном.

Первый capture с PYTEST_ADDOPTS XML дал unit fail/no XML; этот неполный capture
сохранён. Retry без override: actual collect460=execute460,0fail/error/skip,
CLI XML сохранён отдельно; вердикт selfcheck всё равно fail по layers. All44
canonical reports возвращены copyfile по baseline SHA, JSON не редактировался.
После выявления STOP production больше не менялся; engine/corpus/double/M-P/
live/финальная готовность не заявлены. Следующее — один явный ответ аудитора
по manifest pin; затем собственный layer repair и повторный selfcheck.

### §13 — D19: постоянный мандат вместо разовых разрешений (2026-11-02)

Причина: срез C.24 потребовал четырёх отдельных разрешений подряд (D11, D12, D13, D17, D18) и ещё пяти STOP-ов. Это дефект постановки, а не дисциплины портера.

**Разрешено без отдельного вопроса** (мандат, действует во всех срезах):
1. Пины, перечисляющие **состав нашего же нового модуля**: `count`, списки имён, эффекты, `entrypoints`, `provides_tools`, `requires_ports` — при условии, что (а) до правки есть красный прогон, (б) diff трогает только эти значения, (в) смысловой запрет пакета сохраняется дословно.
2. Тесты, корпус и manifest **собственной новой механики** среза.
3. Записи: лист, `PROGRESS.md`, `WORKLOG.md` (только `ab`, CRLF), `parity.md`, `tests-map.md`, `deviations.md`, `invariants.md` (новый `SEC-n` своего среза).
4. Файлы собственного модуля, module-owned порты, `tools/probe.py`, сборка своего порта в `bootstrap.py`.
5. Снятие мёртвых хардкодов в `tools/*`, которые уже названы замечанием аудитора.
6. Кейс-поле в `tools/snapshot_diff.py` для внутреннего маршрута (как в D17).

**По-прежнему требует явного «да»** (стоп-условие §6, без исключений):
(а) смысловая правка чужих frozen-корпусов и их manifest; (б) ослабление любого guard/лимита/инварианта безопасности; (в) изменение поведения `tools/selfcheck.py` сверх «корпус по module_id»; (г) правка содержания принятых ADR и любых статусов; (д) статусы ADR, таблица механик, стадии, `ported`; (е) `editor/**` и `contract/editor_verbs.json`; (ж) новые инфраструктурные файлы в `substrate/` и `kernel/`; (з) ослабление принятого зелёного теста без красного следа.

**Как оформлять**: ничего не спрашивать по пунктам 1–6; вместо этого в сдаче таблица «Мандат» — что изменено, какой красный прогон это доказал, какие SHA. Аудитор проверяет таблицу отдельной строкой.

### §15 — C.24 D19: explicit apply, strict client и native bytes (2026-11-02)

Дополнительный ответ аудитора сохраняет явный MODULE `apply`; только собственные
inventory values (:29–32 принятого contract pin) обновлены после actual red.
TOOLS=MODULE.provides_tools=() (:27) неизменно. Из negative dispatch удалён только
`apply`; `replace_raw` и `arbitrary.module.function` сохраняют дословный отказ.
Новый positive pin проверяет strict schema и настоящую common WAL-воронку клиента.
Actual mandate-red49collected=executed:17failed/32passed/0errors/skips; затем
mandate-green1:76/0/0/0. Domain json imports удалены, codec pure, lint не менялся.
Actual phase1 selfcheck exit0/ok:460unit/235corpus, layers/limits563,2warnings,
securityok,contract27. Отдельный actual unit collect460=execute460, XML SHA
`f793242214e1ff3e05a04c2c22bf4b79e9ecbf7ce07ec646b64b55e2f5c4977d`.
Area8396≤8400; canonical44reports восстановлены byte-exact из baseline.zip.

Fresh native oracle-r1:6 отдельных genuine EditorPlugin prepare→execute→reload
применений. Bytes нашей strict client/WAL-воронки Godot загрузил; полные original
native `_resource_projection` и `_semantic_hash` совпали для каждой операции,
dependencies byte-exact. Это не совпадение native serializer bytes: D18 formatting
deviations остаются явными. Первые4host/panel/history пробы F1 не подменяются,
UI/HTTP/auth не заявлены. New corpus route actual red9:4failed/5passed, затем
9passed/0/0/0; safety включает dependency staleness, expected raw hash, one-target
multi-operation, foreign poststate и raw compensation после RECEIPT failure.

Evidence: `C:/Users/Lich/AppData/Local/Temp/opencode/c24-d19-20261102/`.
**Следующее действие:** добавить C.24 собственные corpus cards с native-semantic
provenance/D18 byte expectations, затем full/snapshot double, M/P, live3 и записи.
Стадии/statuses не менялись; §14 предложение удалить apply отозвано ответом D19.

### §16 — C.24 D19: корпус, native EOL и мутации (2026-11-02)

- Корпус расширен только своими карточками 236–271: 36 новых, всего 271;
  прежние 235 карточек и 74 native diagnostics сохраняются. Шесть операций,
  CRLF/lone CR/mixed/final EOL, BOM, lock, expected/raw/dependency stale,
  target/dependency policy, reference conflict и malformed/unsupported input.
  Успех проходит настоящий strict client → PREPARED → общий apply → repeat stale
  → raw rollback с побайтовой проверкой всего fixture-проекта.
- Genuine native oracle: все шесть apply/load полных проекций точны;
  дополнительно пять EOL-карточек загружены настоящим EditorPlugin/ResourceLoader,
  full projection/semantic hash совпали, загрузка не изменила байты.
  Native не завершает `;`-комментарий одиночным CR: первая дополнительная проба
  дала `Parse Error: Unexpected end of file.`. Этот исходный input сохранён
  отдельной refusal-карточкой 271; валидный comment-free lone CR остался успехом.
  Новый pytest red 1/1 → общий green 34/34; это fail-closed bounded validation
  D18, не новое отклонение. Чужие тесты/корпуса не менялись.
- Raw second-read policy witness: actual red 20 collected/executed = 1 failed,
  19 passed; проверка до второго IO добавлена в module-owned port; green 20/20.
  Editing area теперь ровно 8400 строк; потолок не увеличивался.
- M1: снятие трёх существующих raw hash barriers → red 1/1, restore green 1/1.
  M2: снятие module dependency policy → red 2/2 на ADDONS/project.godot,
  restore green 2/2; common guard оставался и продолжал запрещать запись.
  M3: `script_edit` вместо replace_raw действительно сохранил single-style CR
  (первый survivor не скрыт), но mixed CRLF/LF byte assertion красный 1/1;
  точное восстановление → green 1/1. M4: отключение >8400 → red 2/9 на обеих
  areas; восстановление → green 9/9. Все mutation sources восстановлены байтово.
- Первый full дал 5131 collected/executed: 1 failed, 5130 passed, 0 errors/skips.
  Причина — alias собственного генератора карточки 271, а не production:
  исходный refusal seed заменялся comment-free success seed. Исходная карточка
  и red junit сохранены наружу; seed восстановлен из первоначальных raw bytes,
  semantic refusal не ослаблен. Native-client corpus green: 274/0/0/0,
  из них 271 карточка и три routing/boundary pins.

**Следующее действие:** завершить свежие двойные full/snapshot и 44 selfchecks,
live3 с точным восстановлением, записи handoff и финальную SHA-таблицу.
Этап/ported/accepted не выставляются; C.23 acceptance-блоки остаются за аудитором.

### §17 — C.24 D19: доказательства для независимого аудита (2026-11-02)

- Actual `python tools/selfcheck.py editing.resource_ops --json`: exit0,
  verdict `ok`; unit503 passed, corpus271/0; layers563/0, limits563/2warnings,
  securityok, contract27/0. Отдельные collect503=execute503, errors/skips0,
  XML SHA `efeb5c709fa080d97ba9f1b05edaf5281cdd81889caf9b8101a8e70f02b9b20e`.
- Full double: каждый collect=execute5131, failures/errors/skips0;
  три live deselected и затем реально выполнены отдельно, не записаны как skip.
  XML первого `aed55f3acb25bb903b6e974cd401c660459962ddb0a38ad61f4ee8f18534c3e8`,
  второго `67a8b90a4388bdf8d2e2b17a59f7cebe274abe08f3d07be91069b87f4297f3f4`.
  Snapshot double1180/0=909 неизменных чужих+271 resource.
- Actual all44:27ok/17baseline blocked/0fail/0needs_live. Это не «44green».
  Все44 canonical report JSON восстановлены байтово; актуальные ответы вынесены
  в external `final-selfchecks/`. Seven selected unit/corpus: file_refactor124/52,
  resource503/271, split_py583/107, split_gd625/102, class_api128/26,
  node_info247/65, tree116/40. C19before/after64/0/0/0, target masks сохранены.
- Native: исходный F1 genuine host/panel/history4+BOM остаётся неизменным;
  свежие6 genuine native execute/generated load/full projections точны,
  плюс5 EOL-карточек. Дополнительные6 прогонов используют фактические F1
  dependency bytes old32x32/new64x32: все projections точны, byte producer
  выдаёт те же resource bytes, а oracle различает зависимые проекции.
  Это не доказательство UI/HTTP/auth/Inspector/cache или saver-byte parity.
- P1/P2: настоящие CLI `tools/probe.py resource_ops --operation prepare_write`
  при занятом реальном lock→conflict/no plan; prepare→strict apply→COMMITTED,
  один replace_raw; repeat→stale_plan/no effect; whole-project raw rollback exact.
  Первая CLI harness-проба не передала captured ENV state_dir и сохранена как
  дефект пробы; свежая r2 передаёт настоящий общий state. Это не production red.
- Live: collect3=execute3, failures/errors/skips0;
  XML SHA `5580a976294f7f3183c755c90e49edef3aa3549957054da27dfdbcb2dd011bae`.
  Project335→419→335 байтово; SHA
  `958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`.
  Удалены только witnessed-new UID, прежние raw84/audit83 сохранены.
- P3:3827files/833dirs/83auditUID, debris0; native947, три original source pins,
  foreign corpora, original235+74diagnostics, accepted ADR/editor/verbs/contract
  и stages/statuses точны. P3 выявил31 CRLF в новом NOTES-разделе; только эти
  EOL нормализованы в LF, все строки содержания сохранены. Остальные changed
  docs LF; WORKLOG binaryab+CRLF с точным прежним префиксом.
- Мандат и closed deviations: `HANDOFF.md` содержит отдельную таблицу;
  `mandate.json` — конкретные changed source/evidence byte counts+SHA и actual
  red. ADR0017 остаётся proposed. M1/M2/M3mixed/M4 red→restore green сохранены,
  включая initial single-CR M3survivor и first-full own-card-producer red.

Артефакты: `C:/Users/Lich/AppData/Local/Temp/opencode/c24-d19-20261102/`.
Финальная `final-sha256.json` пишется после handoff и всех record append,
последней; её SHA будет в финальном отчёте. Closed F1/D18 dossier не меняются.
**Следующее действие:** независимый аудит C.24, включая отдельный вердикт
по «Мандату». C.23 acceptance-блоки заполняет аудитор; porter их не принимает.
Стадии/ported/accepted не выставлены.

C.24 готов к независимому аудиту, не принято

### C.23 + C.24 — приняты аудитом 2026-11-03 (сессия 77)

Приёмка — только моими прогонами, числа портера не пересчитывались как источник.

- Полный non-live: 5225 collect=executed, 5223 passed, 2 genuine WinError1314
  skips, 0 failed/errors (99.9 с); JUnit SHA мой `0cd41ebae104276c…e8408`.
- `snapshot_diff` ×2: «кейсов 1237, расхождений нет», в обоих `resource_ops 271/271`.
- `selfcheck editing.resource_ops` ×2 с бэкапом всех отчётов и возвратом
  байт-в-байт (mismatch 0): verdict ok — module = вклад в write_preview,
  layers 568/0, limits 568/2 (split_py 11, editing 8400 R-06/D18),
  contract 28/0, security ok, unit 503, corpus 271/0.
- Гейты отдельными прогонами: `gen_contract --check` 28/0, `lint_arch` 568/0,
  `check_limits` ok/2 warning, `security_audit` SEC-01…08/20 ok.
- Live 3/3 passed, project.godot 335→419→335 побайтно, SHA `958b3a92…`
  восстановлен, новые `.gd.uid` удалены; гигиена: `__pycache__` в `python/` 0.
- Своя мутация (не из списка портера): снятие `rel != "project.godot"` в
  `allowed()` (`domain/core.py`) красит ровно 2 теста SEC-24 —
  `test_forbidden_identity_before_plan[False-res://project.godot]` и
  `test_existing_external_dependency_uses_module_policy_before_common_guard[res://project.godot]`;
  источник восстановлен байт-в-байт (SHA == бэкапу), после — 14 green.
- Периметр по коду: `module.py` — `provides_tools=()`,
  `contributes_to=("write_preview",)`, `internal_services=("resource_ops",)`;
  в контракте артефакта resource_ops нет (контракт 28 растёт только от `read`).

Записи аудитора: строка `editing.resource_ops` в `PROGRESS.md` 0→7,
`parity.md` → `ported`, ADR-0017 → принят (см. статус в ADR), блоки C.23/C.24
в `PROGRESS.md`, WORKLOG append CRLF. Прежние статусы stages/ported не
пересматривались.

