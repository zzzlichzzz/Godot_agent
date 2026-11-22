# C.25 — `project_text.read` + `project_text.tree`: чтение файла и дерево проекта

Ты — **портер**. Работаешь только в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`.
Этапы сам себе не ставишь, «выполнено/принято/ported» не пишешь, `_audit-handoff.md`,
статусы ADR и таблицу механик не правишь. Сдаёшь строкой
«C.25 готов к независимому аудиту, не принято». Приёмка — только моими прогонами.

## Читать до первой строки кода

1. `AGENTS.md`, `RULES.md` в корне плагина (`docs/porting/RULES.md` **не существует**):
   R-02, R-03, R-05, R-06, R-09, R-11, R-12, R-13, R-15, R-16, R-20, R-22.
2. `docs/architecture.md`, `docs/PORTING.md`, `docs/security/invariants.md` (SEC-20…SEC-23),
   `docs/deviations.md` (C.20–C.24).
3. ADR-0005, ADR-0006, ADR-0012 (security directories), ADR-0016 (принят) — и помни, что
   ADR-0017 остаётся `proposed`.
4. Листы: `editing.split_py.md` (C.20), `editing.file_refactor.md` (D1–D13),
   `editing.resource_ops.md` (§10–§13, включая **D19 «постоянный мандат»** — читать целиком).
5. Реализованный сосед `python/modules/project_text/search/**` (этап 7) — он и есть образец
   стиля, портов, схем и тестов для этого же пакета; `project_text/shared/file_index.py`.
6. Скелеты среза: `project_text/read/{app 467, module 477, tools 358, domain/core 250}`,
   `project_text/tree/{app 447, module 540, tools 338, domain/core 230}` — всё TODO.
7. Эталон: `D:\vajno\Godot\random-game\addons\godot_agent\python\godot_tools\project_tools.py`,
   **102 471 B, sha256 `79e9b035bd211f4a44623573d64f88f5bf47a049725c18dc90d985f47c6a7877`**.
   Не совпал — STOP §6. Карта: `begin_case_only_dir_casing:121`, `_is_generated_sidecar:126`,
   `exclude_agent_addon_dirs:131`, `build_project_tree:142`, `_resolve_safe_path:197`,
   `is_addon_path:214`, `is_agent_path:302`, `_classify_resolved:333`,
   `classify_project_path:384`, `can_read_project_path:441`, `policy_snapshot:743`,
   `assert_can_read_project_path:760`, `read_project_file:778`,
   `policy_read_project_file:1370`, `build_project_overview:1449`.
   В этом же файле живут запись/перенос/поиск — они **не** наш срез.
8. `docs/mapping.md:65` (project_tools → 8 адресов) и `:139` (пункты 2 `project_text/tree`
   и 3 `project_text/read`).
9. Промпты C.23/C.24 (§9 уроки, §10 вопросы) — как образец формы.

## §0 База (снято мной на сданном C.24; не пересчитывать)

- non-live: **5 131** тест, 0 failures/errors/skips (моя junit, rc 0).
- snapshot: **1 180 / 0** (909 чужих + 271 resource).
- contract: **27** артефактов (`contract/capabilities` — 28 файлов, `_template.json` не артефакт).
- гейты: `lint_arch` 563, `check_limits` 563 + 2 предупреждения (area-потолок **8 400**,
  база 8000; второе — прежнее `split_py` 11 элементов), `security_audit` 0 нарушений.
- selfcheck: `resource_ops` **503 / 271**, `file_refactor` 124 / 52, `split_py` 583 / 107,
  `split_gd` 625 / 102, `class_api` 128 / 26, `node_info` 247 / 65, `tree` 116 / 40,
  `check` 188 / 75, `api_check` 206 / 52, `gd_lint` 126 / 37, `tscn_lint` 315 / 65.
  Отчётов **44**; свежий отчёт не обязан быть побайтово равен прежнему (ADR-0013 — длительности).
- дерево: **3 828 файлов / 833 каталога / 83 audit-UID / 44 промпта** (прирост +1 к C.24 — сам этот промпт); `project.godot` 335 B,
  sha `958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`.
- `docs/PROGRESS.md`: 45 строк этапа = **25 / 1 / 19**; `project_text.read` = 0,
  `project_text.tree` = 0, `resource_ops` = 0 (принят, но этап поднимаю я).
- `docs/WORKLOG.md`: исторический префикс **4 479 CRLF**; писать только `ab` + CRLF.
- ADR: 17 файлов (0017 создан в C.24, `proposed`); правил 22.

## §1 Границы среза

Делаем **обе read-only механики** пакета: чтение файла и дерево проекта.

| можно менять | условие |
|---|---|
| `python/modules/project_text/read/**` | весь модуль |
| `python/modules/project_text/tree/**` | весь модуль |
| `python/modules/project_text/shared/**` | только если нужен общий кусок; без правки `search` |
| `contract/capabilities/*.json` + `docs/tests-map.md` | по итогам §10.1 (растёт контракт или нет) |
| `fixtures/corpus/project_text/read/**`, `.../tree/**` + manifest | новые кейсы |
| `tests/py/{contract,integration,formats,security}/test_project_text*` | свои тесты |
| `docs/deviations.md`, `docs/security/invariants.md` | `SEC-24`, закрытый список отклонений |
| записи: лист `project_text.read.md`, `project_text.tree.md`, `parity.md`, `PROGRESS.md`, `WORKLOG.md` | по мандату D19 |
| `python/runtime/bootstrap.py` | только сборка своих портов |

**Запрещено:** `editor/**`, `contract/editor_verbs.json`, `_audit-handoff.md`, таблица механик и
стадии, статусы ADR, `reports/selfcheck/*.json` руками, чужие frozen-корпуса, `project.godot`,
`.gd.uid` вне `fixtures/`, `__pycache__`/`.pyc`/`.bak`/временные файлы, `tools/selfcheck.py`
(кроме снятия уже названных мёртвых хардкодов), ослабление любого guard или потолка.

## §2 Контракт правки

**2.1 Литеральный перенос чтения.** `read_project_file:778` вместе с политикой
`policy_read_project_file:1370`, `assert_can_read_project_path:760`, `_resolve_safe_path:197`,
`can_read_project_path:441` и классификацией путей (`_classify_resolved:333`,
`classify_project_path:384`, `is_addon_path:214`, `is_agent_path:302`). Отказы — дословными
текстами эталона, порядок проверок не переставлять, `kind` маппится в наши (`invalid_input`,
`denied`, `not_found`, `conflict`, `internal`). Кодировка и BOM: как в эталоне (raw-чтение,
`utf-8-sig` с fallback `utf-8`/`replace`); EOL не нормализовать, если эталон не нормализует —
проверить пробой.

**2.2 Дерево.** `build_project_tree:142` с `exclude_agent_addon_dirs:131`,
`_is_generated_sidecar:126`, `begin_case_only_dir_casing:121`. Форма узла, сортировка,
глубина, `count`, скрытие `.godot`/`.import`/служебных каталогов — по эталону, с фиксацией
в кейсах. Никаких «улучшений».

**2.3 Чистая домёнка.** `domain/` без I/O и без импортов `json`/`os`/`pathlib` под линтером
(в C.24 json-импорт в `domain` дал два красных layers). Больше 80 строк в `app.py` — нет.

**2.4 Один сканер.** Поиск/обход — существующий `fs.list_files` + `project_text/shared/file_index.py`,
свой `os.walk` запрещён (R-12). Если чего-то не хватает — §10.4, а не правка соседей.

**2.5 Периметр.** Если native не объявляет публичного инструмента для чтения/дерева —
контракт остаётся **27**, механики уходят во вклад (`contributes_to`), публичной утечки
абсолютных путей и raw-байтов нет (R-15). Это решает §10.1, не ты.

## §3 Шаги

0. **Мандат D19** (`editing.resource_ops.md` §13) уже действует: пины своего модуля, свои тесты,
   свой корпус, записи, module-owned порты, `probe.py`, сборка порта — **без вопросов**, но
   с красным прогоном до правки и таблицей «Мандат» в сдаче.
1. Лист `docs/porting/project_text.read.md` и `project_text.tree.md` из `_template.md`:
   цель, старый код, старые тесты, корпус, спецификация, SHA до правки.
2. **§10 — пробы** (actual native + настоящий MCP в обоих профилях), досье наружу, дословные
   фрагменты с номерами строк. Ни строки production до моего ответа.
3. После ответа: red-тесты по R-16 (старые тесты = источник кейсов), затем production.
4. Корпус: успех, BOM, CRLF, одиночный CR, пустой файл, большой файл (лимит), бинарный,
   каталог вместо файла, отсутствующий, `res://../`, `addons`/`ADDONS`, `.agent_history`,
   `plugin.cfg`, `project.godot`, спецсимволы и кириллица в путях, симлинк/выход за корень.
5. Контракт/схемы по §10.1, строгая схема ответа, `effects="read"`, `idempotent=True`.
6. Двойной прогон: non-live ×2, snapshot, все 44 selfcheck, четыре гейта, live 3.
7. Мутации M1–M3 и подложки P1–P3 (см. §5), записи, SHA-таблица последней.

## §4 Доказательства

- **M1** — снять проверку `can_read_project_path` → кейс `addons/**` обязан покраснеть.
- **M2** — вернуть абсолютный путь в ответ → пин «нет абсолютных путей» красный.
- **M3** — в дереве показать скрытые каталоги (`.godot`, `.import`) → кейс дерева красный.
- **P1** — подложка: файл с BOM и CRLF читается без изменения байтов на диске (sha до/после равны).
- **P2** — идемпотентность: два чтения подряд дают одинаковый ответ, дерево побайтово то же.
- **P3** — гигиена: дерево = база + прирост среза, `.gd.uid` 83, debris 0, `__pycache__` нет.

## §5 Стоп-условия

Эталон не совпал по SHA; mapping противоречит эталону; §0 не сходится с фактом; нужна правка
чужого frozen-корпуса, `editor/**`, `selfcheck.py` (сверх мёртвых хардкодов), guard/потолка,
статуса ADR или таблицы механик; нельзя выбрать форму публичного периметра без меня.
Формат: «STOP §6: …» + досье, production не тронут.

## §6 Что проверяю я

Свои прогоны (non-live, snapshot, selfcheck обеих механик, четыре гейта), своя проекция SHA,
свои мутации сверх твоих, байтовая неприкосновенность прочитанных файлов, отсутствие I/O
в `domain`, дословность отказов, неизменность соседей и 44 отчётов, гигиену дерева,
записи (WORKLOG через `ab`, префикс цел), таблицу «Мандат» построчно.

## §7 Финал и записи

Отчёт: число тестов (collect = executed), время (не контракт), SHA junit; snapshot `1 180 + N`;
44 отчёта с объяснением изменений; contract 27 или 28 по §10.1; гейты 563; live 3 по рецепту
(`project.godot` 335 → 419 → 335, sha `958b3a92…`, удалить ровно созданные `.gd.uid`);
дерево и UID после уборки; таблица кейсов; M1–M3/P1–P3 со SHA; SHA-таблица **последней**;
строка сдачи. EOL: `WORKLOG.md` только `ab` + CRLF, остальные `docs/**` LF, `\r\r\n` — ноль.

## §8 Уроки прошлых срезов

Буква ≠ смысл (`tree 128` против 116); приёмка, записанная в один файл, теряется; SHA,
снятая до записей, устаревает; живой прогон оставляет `.gd.uid`; числа берём из источника,
а не из handoff; `\r\r\n` — ноль; JSON руками не правим; чужие корпуса не переформатируем;
ослабленный пин без красного следа — не пин; адреса в промпте проверяем (мои ошибки:
несуществующий `docs/porting/RULES.md`, `_cli:792`, SHA соседнего файла); «entrypoint» ≠
атрибут модуля.

## §9 Вопросы (ответить до кода)

1. Какие публичные имена даёт native для чтения файла и дерева: `list_tools` в профилях
   `user` и `agent-dev`, затем настоящий `call_tool` — и совпадает ли это с `mapping.md:139`.
   От ответа зависит, растёт контракт до 28 или остаётся 27.
2. Точная форма ответа обоих инструментов (поля, сортировка, лимиты, что отдаётся для
   бинарного и для большого файла), и что native делает с BOM/EOL при чтении.
3. Как native обходится с `.godot`, `.import`, `.agent_history`, `addons`/`ADDONS`, симлинками
   и выходом за корень — и чем это отличается от наших `guard_*`/`PathPolicy`.
4. Что уже есть в `substrate/fs/*` и `project_text/shared/file_index.py`, чего не хватает,
   и можно ли обойтись без новых файлов (новые файлы в `substrate/` — только с моего «да»).
5. Какие старые тесты эталона становятся кейсами (R-16), их число и формат actual-native
   записи; какие отклонения идут закрытым списком в `deviations.md`.

