# editing.file_refactor — C.22, запись переименования и переноса

**Статус:** C.22 готов к независимому аудиту, не принято; исходный этап `0`/`skeleton` и ADR-0016 `proposed` сохранены.
**Обновлено:** `2026-11-02`

## Цель и стратегия

Перенос по спецификации: prepare/apply файла и каталога, case-only на NTFS,
компаньоны и синхронизация ссылок; запись только через общую WAL-воронку.
В исходном preflight до ответа на §10 не создавались production, ToolSpec,
корпус, red-тесты и ADR-0016. Решения D1–D13 получены (дословно ниже), перенос
и проверки завершены; default C.21 прежний, False seam разрешён только D13.

## Старый код и кейсы

Frozen: `D:/vajno/Godot/random-game/addons/godot_agent` — только чтение.
`python/godot_tools/file_refactor.py`: 67833 B, SHA256
`61171473c1bb67359d551f10ef460b95790e32414696a2d1e30bfd1eabe407d8`.
Адреса: normalize46, case-only56, read76, find87, internal181, guard246,
directory266, prepare591, apply810, external-sync1139. `_cli` отсутствует.

Mapping:46/152/168–170. Строки tests-map51/52/54/57–59/76–78 имеют судьбу
`corpus`: test_asset_refactor*, test_client_refactor_flow, test_file_refactor*,
test_move_dir_safety, test_move_race_and_agent, test_move_safety. Старые тесты
не копируются и не запускаются как новый набор; отсюда берутся только кейсы.
Для preflight прочитаны file_refactor unit/flow, move_safety и case-only/companion
кейсы move_dir_safety. Read/discovery/internal уже принадлежат C.21, второй
реализации не будет; нужен разрешённый публичный шов без импорта чужого domain.

## C.22 — запись (сессия 76)

### База до первой правки

Первый STOP §6 принят аудитором: неверные SHA, путь RULES и CLI-карта исправлены
им только в `_start-prompt.file_refactor.md`. Исправленный файл подтверждён:
25714 B / 293 CRLF / 0 CRCRLF; единственная дельта к первому STOP — этот prompt.
Отсутствовавший лист механики — дефект R-19; создан до production.

Внешнее досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c22-preflight-20261102/`.
Полный byte-backup: `baseline.zip`, 3575015 B, SHA256
`ef219fccf20690a33f49570d73ba4cab592f9c86f50ee3c1afe708b2cec070e6`.
Индекс всех исходных файлов/каталогов: `baseline.json`, 644261 B, SHA256
`4fe2d5ae7ef3e50cdd17a50aa12b06217ffd59c05afe6acb477f18db2d47c911`.
Frozen-дерево целиком запинено в `frozen-reference-baseline.json`.

Аудиторская база §0 не заменяется новыми числами: 4346 non-live, selector64,
snapshot857, paths_preview58/25, layers/limits552, contract27/security0;
дерево3315/810/83, prompts41, capability-files28, reports44, ADR15, rules22.
Единственная разрешённая правка существующей таблицы PROGRESS — C.21 cell0→7
по уже записанной приёмке аудитора; остальные ячейки не меняются.

| Исходный файл | B | SHA256 до правки |
|---|---:|---|
| `docs/PROGRESS.md` | 79629 | `8aa53f22063e35793c9267a61d91fe5ce6bf4057ce583f48182795c247f8b6b8` |
| `docs/WORKLOG.md` | 595731 | `251e295d3f6aba3c5c16686c3dedf2684d7ab0398dd0357277ea320b9a99ce32` |
| `docs/parity.md` | 18527 | `691a855d22854e1f4b1efcd1775e0f14c9ff644c568c0ff8d5b10108b76e98c5` |
| `docs/tests-map.md` | 66466 | `eba1a5b9eb5c527ccccf4a9b1bc532b163ed6c972b63b5e9a6a5a1474e2e91ba` |
| `docs/security/invariants.md` | 7035 | `64bee8543c23dc485d8267bb9d17a06ac4250e7a496521d47a48dda67159ada4` |
| `file_refactor/module.py` | 665 | `24da5474724efec24793eed2e42d79e9d5dde0007dbb70dc8dc7292e1ad151fb` |
| `file_refactor/tools.py` | 372 | `109f358d9b549c101724e51760879284766621343919ae6fb4bade77ccf0e8ab` |
| `file_refactor/app.py` | 447 | `bcb4ed47f37d909c4e247ff23dc5a6e5b0a304d74e181d72bf9472b4f2ed1632` |
| `editing/shared/funnel.py` | 8331 | `60f597a414bd0759d6c24aee1e77bdbdddfcebfeea0b8e02d60517aa735e9f78` |
| `editing/shared/script_edits.py` | 3698 | `0edc1b3fb9bc4342c976b4c7313dad1fdf9b0ce110d231aa24063473c448206c` |
| `substrate/fs/atomic_write.py` | 4075 | `85dc6c184c5f37ee094e7850c3e7a21641a9d2ea7ea0d257c835cdd54f5d9a51` |
| `substrate/fs/disk_fs.py` | 5021 | `e973bd522c40a4fd2e3728bd21e1cff7c3e1b194e7f1f40f14a560d2edcc7903` |
| `substrate/fs/memory_fs.py` | 1798 | `2a9f8203562738a734bea4f783276d9fa4c0c3b5e38bdf0f83ca41f896cb14f6` |
| собственные ports/domain/tests/corpus/ADR-0016 | — | `absent` |

Пути production в таблице начинаются с `python/modules/` либо `python/`;
полные пути и SHA всех остальных файлов, включая соседей и отчёты, — в индексе.

### Намеренная граница preflight

D11: EFFECT_INTENT записывается перед **всеми** эффектами, включая принятые
create/delete/script_edit C.20; receipt-gap recovery — наше safety-поведение,
не native parity. Case106 меняет только expect.wal_states и его bytes/SHA.

Внешние диагностические скрипты и мини-проекты — не реализация порта и не корпус.
Native исполняется без подмены discovery/prepare/apply/history/MCP. Наблюдение
системных операций и отдельные инъекции отказов маркируются в raw-артефактах.
Байты/tuple в досье кодируются lossless, не выдаются за клиентскую схему.
Секреты/токены не сохраняются. Никакого live, изменения project.godot рабочего
проекта, UID/кэшей в репозитории или правки чужих отчётов/корпусов.

### Ход

| Дата | Шаг | Результат |
|---|---|---|
| 2026-11-02 | STOP §6 | три дефекта промпта подтверждены и исправлены аудитором; repository/frozen byte-exact |
| 2026-11-02 | чтение и baseline | корневой RULES и исправленный prompt прочитаны; новый внешний ZIP/index; C.21 cell0→7 по решению аудитора |
| 2026-11-02 | actual-native §10 | 66 frozen-native вызовов / 41 успех / 25 отказов-исключений, включая 1 OS-инъекцию; отдельно 8 current comparisons / 4 успеха / 4 отказа; всего 74 диагностических записи, native raw SHA запинены |
| 2026-11-02 | настоящий MCP | frozen SDK stdio user14/agent-dev24: initialize/list_tools/call_tool; rebuilt McpServer→build_agent headless26; read mini-project byte-exact, file_refactor ещё отсутствует |
| 2026-11-02 | current infrastructure | effect→до RECEIPT: actual create + маркированная crash-window инъекция, recovery left_prepared; с RECEIPT rolled_back. Whole-file script_edit не сохраняет mixed LF/CRLF, lone CR и BOM сохраняет |
| 2026-11-02 | STOP §10 | семь фактических ответов и запрос разрешений записаны во внешнем preflight-answers.md; ADR/production/ToolSpec/corpus/red не созданы |

### Семь ответов и граница решения

Полные ответы с именами raw-проб и дословными ошибками:
`C:/Users/Lich/AppData/Local/Temp/opencode/c22-preflight-20261102/preflight-answers.md`.
Source excerpts: `native-source-fragments.md`; native indices:
`native-index.json` + `native-extra-index.json`; MCP: `mcp-raw/`.

Финальная классификация: `record-classification.json`. Первые 72 записи включали
66 native и 6 current comparisons, не 72 native calls. На Windows guard filenames
addons/ADDONS столкнулись: старый lowercase raw перезаписан, его original index
сохранён, raw не выдаётся за целое доказательство. Оба current guard повторены
с уникальными ID в `current-extra-index.json`: ещё 2 записи, без изменения проекта.
Все 66 frozen-native raw SHA совпадают с original indices; их коллизия не затронула.

1. Compound create/delete не заменяет raw move/casing. Предлагается отдельный move,
   но его поля/step identity/undo/phase WAL не утверждены. Native normal move —
   hardlink/unlink с copy fallback; простой os.replace может clobber/не пройти EXDEV.
   Native проверяет все stale до эффекта; текущий write_apply — по одному шагу.
   Crash effect→receipt сейчас не восстановим: left_prepared оставляет эффект.
2. Native case-only — прямой os.rename, не временное имя/два хопа. Leaf+UID: 2
   rename при 1 item; parent+leaf+UID: 3; whole directory: 1, включая skipped payload.
   Окончательный granular Step-count и обратный casing требуют решения аудитора.
3. Import явный, UID неявный; import source_file меняется даже при references=False.
   Live direct companions запрещены, orphan разрешён. Target UID без source UID
   проверяется поздно в apply; ранняя проверка/typed projection — отдельное решение.
4. Каталог переносит все расширения; skips не равны reference whitelist. UID вне map.
   Проба: moved_files3, prepared5, физически 6 transfers + 3 content writes + 2
   новых каталога. UID-only отказывает; orphan/skipped остаются при обычном move.
5. Scanner и internal paths только из C.21 через разрешённый public seam. Native
   exact/relative/comment/ext_resource/texture и update_references=False проверены.
   Native mixed-EOL after149 B против shared152 B: standalone LF→CRLF; нужен
   утверждённый raw-preserving payload, не текстовый roundtrip.
6. Project.godot запрещён как move endpoint, разрешён как reference patch; plugin.cfg
   native root prepare разрешает, наш funnel/prompt запрещают. Native casefold-policy
   запрещает uppercase ADDONS, текущий lexical guard пропускает. Нужен operation-aware
   guard обоих концов + agent-tree overlap, без ослабления общей политики.
7. Native публичный path-tool только paths_preview(old_path,new_path), metadata
   effects/idempotent/requires_preview в MCP отсутствуют; новый ToolSpec не создан.
   Для R-11 нужны одобренный C21 public reexport/requires и инфраструктурный scope:
   write_apply preflight, rollback/app+recovery, stable identity/WAL/kernel при нужде,
   consumer ports/fs/shared. Эти расширения не разрешаются молча.

Отдельно: injected native UID-link failure вернул raw файлы, но оставил пустой dest/;
полный tree rollback native этим кейсом не доказан. Исправление — только решение/deviation.

### Последний машинный вердикт

Повторный preflight: `python -B tools/selfcheck.py editing.file_refactor` → exit2,
`вердикт: blocked`: нет MODULE, unit и корпуса; layers552/limits552,
contract27/security0. Сырой вывод, fresh report и restoration proof сохранены в
`c22-preflight-20261102`; canonical восстановлен byte-exact, весь addon до/после
команды byte-exact. Все 44 канонических отчёта сохранены.
Это не проверка реализации и не свидетельство готовности C.22.
Full non-live/snapshot/live здесь не запускались; §0 остаётся аудиторской базой.
Final boundary proof и SHA-таблица создаются наружу после WORKLOG/PROGRESS;
ожидаемая docs-only дельта: +1 worksheet, 2 изменённых документа, без новых каталогов/UID.

## §10 — решения аудитора (сессия 76, 2026-11-02)

Все семь вопросов закрыты. Где parity недостижим без ослабления R-11/R-12/R-15 или без
недетерминизма, отклонение записано здесь закрытым списком.

### D1. `move` — отдельная операция, а не составная транзакция

**Разрешаю отдельный `move`.** Составной «create+delete» отвергнут: `create` пишет текст
через `encode()` и не сохраняет произвольные raw-байты, BOM и case-only identity — ровно
то, что ты показал пробой. Обязательный контракт шага:

* `Step(op="move", target=<источник>, payload={"dest": <цель>}, expected_hash=<raw sha256 источника>)`;
  в `plan["expected"]` — хеш источника **и** `""` для цели (тот же absent-sentinel, что у `create`);
* **запрещено** декодировать/перекодировать байты: перенос = raw `os.replace` через новый
  примитив `move(rel_src, rel_dst)` в `substrate/fs/{disk_fs,memory_fs,atomic_write}.py`;
* **разрешено:** `write_apply` получает **preflight-проход** — все шаги плана проверяются
  (`guard` + `verify_absent` целей + `verify_current` источников/правок) **до первого эффекта**,
  как в native. Форма WAL не меняется;
* **фазовый WAL (разрешено менять):** перед эффектом пишется durable-запись
  `{"state": "EFFECT_INTENT", "entry_id", "op", "target", "dest", "expected_hash"}`, затем
  эффект, затем `RECEIPT`. Твой `left_prepared` на «эффект без RECEIPT» — принятая дыра:
  recovery при `EFFECT_INTENT` без `RECEIPT` проверяет post-state и откатывает
  (`move` — обратным переносом, `create` — удалением, `delete`/`replace_raw` — из backups);
  если post-state не совпал — `conflict`, не «догадка». Старые планы без `EFFECT_INTENT`
  сохраняют прежнее поведение (`left_prepared`);
* компенсация `move`: `compensates="move"`, `undo_token` = backup raw-байт источника;
  `restore` проверяет цель по `applied_hash`, затем переносит обратно;
* **ADR-0016 `proposed`** отвечает: absent-цель и case-only исключение, `EFFECT_INTENT`
  и порядок восстановления, обратный порядок в смеси `move`/`create`/`delete`/`replace_raw`,
  совместимость с ADR-0005/0015 (форма `Step/Receipt/WritePlan` не меняется).

### D2. Case-only: без temp-hop, но кейс виден в WAL

Твоя поправка принята: эталон делает прямые `os.rename`; temp-hop — **отклонение, не берём**.
Один `move` на лист. `leaf+UID = 2` и `parent+leaf+UID = 3` у нас — число наших `Step`,
а не число эффектов native (наш счётчик свой, пиннится тестами). Спецправило: `verify_absent`
не отклоняет существующую цель, **если** это тот же файл (`realpath` совпадает), иначе
`stale_plan`. Правило живёт внутри `move` и в ADR-0016; общий `verify_absent` не ослабляется.
Строки путей (`old`/`new`) пишутся в `EFFECT_INTENT`/`RECEIPT` дословно.

### D3. Компаньоны `.import` / `.uid`

* `.import` — **явный шаг** (`move`), сразу после шага владельца вперёд и сразу перед ним при откате;
* `.uid` — **тоже явный шаг**, когда он существует (иначе case-only `leaf+UID=2` невыразим
  и откат недетерминирован); «неявный» перенос не портируем;
* прямой `move` на `.import`/`.uid` при существующем владельце — отказ дословными текстами
  native (`Не следует переименовывать файл .import напрямую…`, `… .uid напрямую…`); orphan разрешён;
* занятая цель компаньона → `conflict` с дословными `Целевой файл .import уже существует: …` /
  `… .uid уже существует: …`;
* **разрешено:** проверка «целевой `.uid` без исходного `.uid`» переносится в preflight (D1);
* `companion_script` сцены — информационный, скрипт сам не переносится (в «Намеренную границу»).

### D4. Каталог

Перенос каталога выражается только `move`-шагами по файлам (`move_dir`/`mkdir` **не будет**);
`move` создаёт отсутствующие родительские каталоги цели (иначе `create` требует существующего
родителя). Переносятся **все** расширения — reference-whitelist здесь не применяется;
`.uid` исключены из `moved_files_map`, `.import` учитывается отдельно, `skipped`/orphan
остаются при обычном переносе. UID-only каталог — отказ дословно
`Папка res://empty не содержит подходящих файлов для перемещения`. Пустые каталоги при откате
не воссоздаются — **явное отклонение** (в ADR-0016 и «Намеренную границу»). Правки ссылок по
переносу каталога — по одному `replace_raw`-шагу на затронутый файл (D5), второго сканера нет.

### D5. Ссылки и байты: `replace_raw`, второй сканер запрещён

* новый op `replace_raw`: `payload={"bytes_b64": …}`, `expected_hash` = raw sha256 файла
  **обязателен**; применяется только для правок ссылок `file_refactor`. `script_edit` не меняем —
  именно он нормализует EOL, отсюда твои 152 B против 149 B;
* сканер и проекция — **переиспользование C.21** через публичный seam:
  `python/modules/editing/paths_preview/public.py` (reexport чистых функций) +
  `requires=("editing.paths_preview",)` в `module.py`; импорт чужого `domain/` напрямую запрещён;
* parity: тот же набор расширений и форм (`.gd/.tscn/.tres/.gdshader/.gdshaderinc`, `project.godot`,
  `preload/load/extends`, точный `res://`, комментарии, `ext_resource`/`Texture2D`), `internal`-проекция
  действует и при `update_references=False`, BOM/CRLF/одиночный CR сохраняются **байт-в-байт**;
  «standalone LF» пинить отдельным кейсом.

### D6. Политика: operation-aware, общий guard не ослабляется

Разрешаю `guard_transfer(ctx, src, dst)` (проверяются оба endpoint) **только** для `move`;
`guard_path` остаётся как есть. Правила: `project.godot` — отказ на rename, но допустим как
цель правки ссылок; корневой `plugin.cfg` — **разрешён** (native), это меняет прежнюю строку
промпта и требует записи в `docs/security/invariants.md` (SEC-22) и ADR-0016; `addons/**` —
запрет **регистронезависимо** (uppercase `ADDONS` сейчас проходит); перенос дерева агента
запрещён даже при trusted `allow_addons`/`allow_self_edit` (`_assert_no_agent_tree_relocation:246`).

### D7. MCP, R-11 и точный инфраструктурный scope

* native не регистрирует `file_refactor` публично — значит **C.22 не добавляет ни публичного
  ToolSpec, ни capability-артефакта**: контракт остаётся **27**, отчётов **44**, риска D8-класса
  нет; `paths_preview` (C.21) не меняется;
* native не объявляет `effects/idempotent/requires_preview` — наши поля внутренние;
  `headless26` — runtime eligibility, не замена `contract27`, в записях писать именно так;
* **разрешённый scope (закрытый список):** `editing/shared/funnel.py`, `shared/script_edits.py`,
  `editing/write_apply/app.py` (preflight), `editing/rollback/app.py`, `rollback/recovery.py`,
  `substrate/fs/{disk_fs,memory_fs,atomic_write}.py`, `paths_preview/public.py` (+`requires`),
  `modules/editing/file_refactor/**`, `docs/adr/0016-*`, `docs/security/invariants.md`,
  корпус `fixtures/corpus/editing/file_refactor/**` + его manifest. `kernel/write_plan.py` —
  только если новых полей шага не хватает (сначала `payload`), с записью в ADR;
  `kernel/paths.py` — только регистронезависимый запрет `addons`;
* остальное — стоп по §6: чужие механики и их корпуса, `tools/selfcheck.py`, `editor/**`,
  `_audit-handoff.md`, ручная правка отчётов, статусы ADR.

### D8. Четыре файла — разрешены (R-03/R-11, R-20, R-09)

Все четыре подтверждены сверкой: `docs/deviations.md` существует, R-03/R-09/R-11/R-16/R-20/R-22
на месте, в `tools/lint_arch.py` уже есть прецедент «ровно одно объявленное ребро» (ADR-0010,
`:131`), поэтому это не ослабление, а расширение того же механизма.

1. **`python/modules/editing/paths_preview/__init__.py` — только reexport.** `from .public import …`
   + `__all__`, ни строчки логики, ни импортов `substrate`/`kernel`/чужих `domain`; тест на импорт
   без побочных эффектов. Прямой импорт `paths_preview.domain.*` извне остаётся запрещённым.
2. **`tools/lint_arch.py` — узкое объявленное ребро.** Разрешаю ровно одно ребро
   `editing.file_refactor → editing.paths_preview` (через `__init__`/`public`), в стиле `ALLOWED`
   и ADR-0010: без wildcard, без ослабления слойных правил, без разрешения foreign `domain/app`.
   Доказательства: удаление объявления → lint красный именно на этом ребре (мутация);
   негативный тест — `file_refactor/domain → paths_preview/domain` по-прежнему нарушение.
3. **`tests/py/security/test_file_refactor_write.py` — обязателен (R-20).** Обязательные проверки:
   выход за проект (`res://../x`), `addons/**` в любом регистре (включая `ADDONS`), корневой
   `plugin.cfg` разрешён, `project.godot` — отказ на rename и разрешение на правку ссылок,
   перенос дерева агента запрещён при trusted-флагах, запись только через воронку (нет
   прямых `open`/`os.replace`/`shutil` в модуле).
4. **`docs/deviations.md` — раздел `C.22` (R-09),** закрытый список: без temp-hop для case-only;
   пустые каталоги при откате не воссоздаются; `replace_raw` вместо `script_edit`; структурный
   шаг `dir_case` (см. D9); `companion_script` не переносится; `absolute`/`raw` не публикуются;
   порядок `files` лексикографический. Любое новое отклонение — только через мой ответ.

### D9. Parent-case-only: модель третьего шага — `Step(op="dir_case", …)`

Твоя проба решает вопрос: `os.replace(chars/hero.gd → Chars/Hero.gd)` меняет только лист,
родитель остаётся `chars`. Значит файловыми `move` родительский регистр невыразим, и D4
(«только файловые move») недостаточен. Принимаю **ровно один структурный вид шага** — и только
для этого случая:

* `Step(op="dir_case", target="res://chars", payload={"dest": "res://Chars"}, expected_hash="")`;
* эффект — новый примитив `rename_dir_case(src, dst)` в `substrate/fs/*`: **`os.rename`, не
  `os.replace`**, с тремя предпосылками, проверяемыми в preflight: (1) `realpath(src) == realpath(dst)`
  — это тот же каталог; (2) различие только в регистре сегментов; (3) новых сегментов нет —
  `mkdir` не появляется. Нарушение любой → `invalid_input`;
* inverse — тот же шаг с переставленными путями (`compensates="dir_case"`), `applied_hash=""`,
  backups не нужны: байты не меняются;
* **порядок обязателен:** вперёд — последним шагом плана, при откате — первым (после него
  пути детей снова в старом регистре); листовые `move` для детей этого каталога **не эмитятся**,
  leaf-case остаётся обычным `move`;
* recovery: `EFFECT_INTENT` пишет оба пути дословно; intent без receipt — если `realpath(src)==realpath(dst)`
  и различие только в регистре, эффект считается применённым и откатывается swapped-шагом;
  иначе `conflict`;
* проверки: NTFS-кейс с `Path.resolve()` каталога, отсутствие второго каталога, откат
  возвращает исходный регистр, файлы детей байт-в-байт не менялись;
* `dir_case` — второй и последний структурный вид шага. `mkdir`, `move_dir` содержимого,
  перенос каталога одной операцией — по-прежнему запрещены. В ADR-0016 записать явно.

### D10. Уточнение закрытого scope D7

К списку D7 добавляются: `paths_preview/__init__.py` (reexport), `tools/lint_arch.py` (одно
объявленное ребро), `tests/py/security/test_file_refactor_write.py`, `docs/deviations.md`
(раздел C.22), плюс `rename_dir_case` в `substrate/fs/{disk_fs,memory_fs,atomic_write}.py`
и один негативный lint-пин. Контракт остаётся **27** артефактов, отчётов **44**, кейс
`context/gather/001` не сдвигается. Всё остальное — стоп по §6.

### D11. `expect.wal_states` кейса 106 — разрешаю точечно (R-22)

Да. `EFFECT_INTENT` — это улучшение наблюдаемости WAL, а не смена принятого поведения
«мимо кейса», поэтому правка допустима, но ровно в таких границах:

* **разрешено:** только `expect.wal_states` в
  `fixtures/corpus/editing/split_py/106-apply-second-write-failure.json` и только
  `bytes`/`sha256` этого кейса в `fixtures/corpus/editing/split_py/manifest.json`;
* **запрещено:** править сам тест, любые другие поля кейса (args, expect кроме wal_states,
  формат, отступы, EOL), другие кейсы `split_py` (включая 001–105 и 107–108) и чужие корпуса;
* **обязательно в отчёте:** дословный список состояний до и после (`PREPARED, APPLYING, RECEIPT,
  ROLLING_BACK, RESTORED, ROLLED_BACK` → … с `EFFECT_INTENT` в правильной позиции), diff показывает
  изменение ровно одного поля;
* **обязателен новый кейс**, который пинит crash-окно явно: `EFFECT_INTENT` записан, эффект
  выполнен, `RECEIPT` нет → recovery откатывает (и это проверяется без сравнения с native,
  потому что native такого состояния не имеет);
* записи: строка в «Намеренной границе» листа, пункт в `docs/deviations.md` (C.22) и абзац
  ADR-0016 о том, что WAL получил фазовую запись для **всех** операций, включая ранее принятые.

**Отклонённая альтернатива:** выпускать intent только для новых операций (`move`/`dir_case`/
`replace_raw`). Отвергнуто: дыра «эффект без RECEIPT» осталась бы открытой для `create`/`delete`
(ровно то, что показала проба), и появилось бы два диалекта WAL — читателю журнала пришлось бы
угадывать формат по составу плана.

### D12. Whitelist WAL в `test_write_boundary.py:103` — разрешаю точечно

Да. `tests/py/security/test_write_boundary.py:103` держит кортеж допустимых состояний
`("PREPARED", "APPLYING", "RECEIPT", "COMMITTED")`; правка ровно одна — добавить
`"EFFECT_INTENT"` в этот кортеж. Формат, EOL, порядок элементов и **все прочие assertions
этого теста** (нет абсолютных путей, нет `\\`, нет `password`/`secret`, лок отпускается
в `finally`) остаются нетронутыми — они и есть предмет теста.

Дополнительно к сдаче: `EFFECT_INTENT` пишет только `res://`-пути (`target`/`dest`), никаких
абсолютных путей и временных имён; это проверяется тем же тестом, а не на глаз.
Два `EFFECT_INTENT` в кейсе 106 — ожидаемы: intent пишется **на шаг перед эффектом**, второй
шаг упал после своей записи; комментарий кейса обязан это сказать словами, чтобы читатель
не принял за дубль.

### D13. external-sync: три точечных решения

**D13.1 — `external_relative=False` разрешено.** Добавить в шов C.21 keyword-only параметр
`external_relative: bool = True`; значение по умолчанию **сохраняет поведение C.21 байт-в-байт**,
`False` передаёт только `file_refactor` для external-sync (native directory-sync не переписывает
внешние относительные ссылки). Разрешённые файлы — `paths_preview/public.py` и
`paths_preview/domain/internal.py`, больше ничего в принятом C.21 не меняется.
Условия приёмки: корпус `paths_preview` **25/25 без пересборки**, отчёт `paths_preview` не
переснимается, пины C.21 остаются зелёными, и появляется **обратный пин**: при `False` внешние
относительные ссылки остаются дословно, а точные `res://` — по-прежнему переписываются (native
sync абсолютные правит). Это и есть кейс по R-22 на изменение принятого кода.

**D13.2 — case-only `already_moved` anchor разрешён узко.** Только при одновременном выполнении
трёх условий: `realpath(source) == realpath(destination)`, raw sha256 источника и цели совпадают,
и публикуемый casing равен **фактическому** casing цели. Тогда anchor считается уже выполненным:
`Entry`/receipt по нему **не пишется**, `entry_id` может быть `None`. Любое расхождение — `conflict`,
никаких «наверное тот же файл». Общий `verify_absent` не ослабляется (см. D2). Нужны два кейса:
NTFS-alias на том же томе (проходит) и alias с другим SHA (обязан дать `conflict`).
Отчёт обязан печатать, что anchor признан уже выполненным, отдельным полем, а не молча.

**D13.3 — отклонение по пустому внешнему каталогу принимаю в другой форме.** `entry_id: null`
в журнале не одобряю: recovery читает receipts по `plan_id#N` и такая запись либо ломает обход,
либо требует спец-обработки навсегда. Правило вместо этого: **нулевой план не создаётся**.
Если у external-sync нет ни одного патча и ни одного шага, инструмент возвращает отчёт
(`patches: []`, `moved: []`, `plan_id: null`) и **не пишет WAL вообще** — ни `PREPARED`,
ни `EFFECT_INTENT`. Тогда и откатывать нечего: местоположение внешнего каталога мы никогда
не меняли, мы только правим ссылки. Это записывается в `deviations.md` (C.22) как
«внешний пустой каталог: location не восстанавливается, потому что мы его не перемещали;
план нулевой длины не создаётся».

### Что аудитор проверит отдельными строками

`move` без декодирования (байт-в-байт на BOM/CRLF/lone CR/нетекстовом файле), preflight до
первого эффекта, `EFFECT_INTENT` + recovery на «эффект без RECEIPT», case-only без temp-hop,
компаньоны как явные шаги, пустые каталоги не воссоздаются, `replace_raw`-parity 149 B,
регистронезависимый `addons`, читаемый корневой `plugin.cfg`, отсутствие нового публичного
инструмента (contract 27, tools 26, кейс `context/gather/001` не сдвинут), full non-live,
snapshot, 44 отчёта, гигиена дерева.


## Следующее действие

Решения получены — см. «§10 — решения аудитора» выше (D1–D7, включая закрытый список
инфраструктурных файлов). Порядок: ADR-0016 `proposed` → fs-примитив `move` → preflight в
`write_apply` + `EFFECT_INTENT`/recovery → `shared` (`move`, `replace_raw`, `guard_transfer`) →
модуль `editing.file_refactor` → корпус → двойной прогон → записи (SHA-таблица последней,
WORKLOG только `ab` с CRLF). Сдача строкой «C.22 готов к независимому аудиту, не принято».

## STOP §6 после D1–D7: необходимые уточнения до ADR/production

Решения D1–D7 получены и прочитаны целиком. Их текст и исходный этап `0`
сохранены; это не повторное открытие семи вопросов, а проверка закрытого scope.
Порядок до production остаётся обязательным: корпус → спецификация → red-тесты
→ код (RULES.md:646–648, R-22:896–899), ADR `proposed` — до кода.

### B1. Public seam требует двух файлов вне D7

R-03:153–155 и R-11:452–455 разрешают foreign API только через `__init__.py`
и объявленный `requires`. Принятый `paths_preview/__init__.py` пока содержит
только docstring; `public.py` без реэкспорта этого правила не выполняет.
Дополнительно actual `tools/lint_arch.py:_same_feature` возвращает `False` и для
`python.modules.editing.paths_preview.public`, и для импорта корня модуля из
`editing.file_refactor`. Линтер вообще не реализует разрешённые public edges.
Нужен явный scope на `python/modules/editing/paths_preview/__init__.py` (только
реэкспорт) и `tools/lint_arch.py` (только этот declared public edge, без разрешения
foreign domain/app). Атакующий/мутационный тест можно оставить в своих tests.

### B2. Security-тест и общая запись deviation вне D7

R-20:807–809 и PORTING:216 требуют атакующий тест в `tests/py/security/`;
тесты только внутри `modules/editing/file_refactor/tests/` это не заменяют.
R-09:375–377 требует запись намеренных расхождений в `docs/deviations.md`,
не только в ADR/листе. Запрашиваются ровно
`tests/py/security/test_file_refactor_write.py` и секция C.22 в
`docs/deviations.md`; чужие тесты и прежние deviations не изменяются.

### B3. Parent-case-only: D2 требует структурный Step, D4 его не задаёт

D2 задаёт `parent+leaf+UID=3` наших Step, но D4 разрешает только файловые move
и запрещает move_dir/mkdir. Actual NTFS observation: raw
`os.replace(chars/hero.gd, Chars/Hero.gd)` меняет leaf на `Hero.gd`, но реальное
имя родителя остаётся `chars`; bytes точны. Файловый move не меняет casing
родительского каталога. Нужна точная модель третьего Step/его обратной фазы либо
явная граница parent/whole-directory case-only. Temp-hop не добавлялся.

### Свежий машинный вердикт и границы

Внешнее досье и полный byte ZIP/index до этих записей:
`C:/Users/Lich/AppData/Local/Temp/opencode/c22-d1-d7-scope-stop-20261102/`.
`scope-observations.json` содержит actual lint calls и NTFS file names.
`python -B tools/selfcheck.py editing.file_refactor` → exit2, **blocked**:
нет MODULE/unit/corpus; layers552/0, limits552/1 info warning,
contract27/0, security0. Raw/fresh report сохранены наружу; canonical восстановлен
побайтово, весь addon и frozen до/после команды byte-exact.
Новые production/ADR/ToolSpec/corpus/red не писались. Только записи STOP;
дерево3316/810/83, все44 canonical и947 frozen файлов сохраняются.

### Следующее действие после STOP §6

Получить явное разрешение B1/B2 и точную модель parent-case-only Step B3;
до ответа не писать ADR/production/corpus/red и не обходить lint/selfcheck.

## Продолжение C.22 — разрешения пользователя и восстановление состояния

2026-11-02: D8–D10 закрывают B1–B3; старый STOP выше — историческая запись.
Найдены уже созданные ADR-0016 (`proposed`) и 39 frozen-native prepare cards
с lossless входами и оригинальными SHA. Их pins проверены, это ещё не differential.
Свежая база: collect=executed=passed4346 (48.34s), snapshot857/0;
selfcheck file_refactor blocked: нет MODULE/unit, runner не видит вложенные cards.
Исходные production, все44 canonical и frozen сохранены.

Пользователь явно разрешил дополнить закрытый D10 четырьмя узкими правками:
`paths_preview/domain/directory.py` (вернуть уже вычисленный after-text,
прежний references/API неизменен), `tools/snapshot_diff.py` (внутренний корпус C.22),
`tools/selfcheck.py` (не пропускать именно этот корпус у вклада без tools),
`tools/probe.py` (внутренний клиент без нового MCP-инструмента).
Отдельно разрешён внешний rollback anchor существующим move с
`payload.already_moved=true`: source absent, destination raw SHA проверяется;
apply не переносит снова, durable WAL/receipt, inverse возвращает файл назад.
Каталог выражается пофайлово, без нового op или полей Step/Receipt/WritePlan.

Новый полный byte baseline до production:
`C:/Users/Lich/AppData/Local/Temp/opencode/c22-resume-20261102/`;
ZIP 3693792 B SHA5125e62d5b7578f2042cf870d9476b27f7f2d3f331cd3701f026f2f1ab82a57e;
index SHA6dbc555e5db6f6209507c3ad1d919ee76aaeeed7de7be7ec23a44cb9526df7a3.
Ни этап0, ни skeleton, ни статусы существующих ADR не меняются.

**Следующее действие:** SEC-22/внутренняя спецификация и новые red-пины на
корпус/transfer/intents/rollback/сохранность байтов; затем production и selfcheck.

## STOP §7 — точный WAL-пин принятого C.20 (2026-11-02)

D8–D10 по-прежнему закрывают B1–B3; это новый, отдельно доказанный конфликт.
ADR-0016 требует durable `EFFECT_INTENT` перед эффектом и для уже принятых
`create/delete/script_edit`. Оставить эти операции без intent нельзя.
Однако `tests/py/integration/test_split_apply.py:171` сравнивает полный WAL
с `expect.wal_states` из принятого
`fixtures/corpus/editing/split_py/106-apply-second-write-failure.json`:
`PREPARED, APPLYING, RECEIPT, ROLLING_BACK, RESTORED, ROLLED_BACK`.
Изменение этого чужого корпуса и его manifest не входит в закрытый scope.

Проверка на неизменённой production: исходный тест C.20 — **1 passed**;
тот же тест с внешней диагностической вставкой durable intent перед двумя
create — **1 failed** ровно на строке171 (`EFFECT_INTENT != RECEIPT`).
Ответ internal и byte-exact откат дерева проходят прежние assertions.
Это scope/compatibility probe, не реализация и не финальное mutation proof.
Сам тест, C.20 corpus/manifest и production не изменялись.

Добавлены 15 новых safety-тестов в
`tests/py/integration/test_file_refactor_intent_boundaries.py`: durable intent
и backup до эффекта; отказ append-intent без эффекта; receipt-gap с точным
recovery либо foreign-state conflict; intent без начатого эффекта.
Каждый сценарий проверяет create/delete/script_edit. Межмодульные tests
расположены вне modules согласно R-11; все 15 сейчас red.
Focused collect=executed97: **92 failed/5 passed/0 errors/0 skipped**.
Final JUnit SHA256:
`19524c16550c6a2b36db85332179f2195908927da542ebe84f5be23d70a4a540`.

Actual `python -B tools/selfcheck.py editing.file_refactor --json`:
**exit1/fail**; module/corpus not_implemented, unit80failed/4passed;
layers552/0, limits552/1 прежнее informational warning, contract27/0,
security0. Прежний snapshot: **857/0**, C.22 nested cards ещё не исполняются.
Свежие raw/fresh reports сохранены наружу; canonical восстановлен byte-exact,
число reports44. Stage0/skeleton и ADR-0016 proposed не менялись.

Внешнее досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c22-implementation-20261102/`.
До правок: полный byte ZIP/index,3433 files/831 dirs/44 canonical reports;
index SHA256 `1268be2f970e69aea444fea0667d51787fb0be3267cf95c6d65b358b34aa4de7`.
Первая диагностическая версия test была внутри modules и отвергалась R-11;
она перенесена в integration, финальный lint green. Первое collect с двойным
quiet не перечисляло node IDs; финальный collect перечисляет все97, сверено
с97 JUnit testcase. Черновые evidence сохранены, за итог не выдаются.

**Следующее действие:** получить узкое разрешение изменить только
`expect.wal_states` case106 на
`PREPARED, APPLYING, EFFECT_INTENT, RECEIPT, EFFECT_INTENT, ROLLING_BACK, RESTORED, ROLLED_BACK`
и соответствующий bytes/SHA-пин в `split_py/manifest.json`, сохранив исходный
тест, остальные поля/кейсы и статусы C.20. Затем продолжить реализацию
ADR-0016 и C.22; не фильтровать WAL-проверку и не отключать intent у старых op.

### Продолжение после D11 — production и новый STOP §7 (2026-11-02)

D11 выполнен точечно: у case106 изменено только expect.wal_states, у его
manifest-записи только bytes/SHA. Тест, другие поля, отступы/EOL и остальные
кейсы сохранены. Дословные состояния:

- До: `PREPARED → APPLYING → RECEIPT → ROLLING_BACK → RESTORED → ROLLED_BACK`.
- После: `PREPARED → APPLYING → EFFECT_INTENT → RECEIPT → EFFECT_INTENT → ROLLING_BACK → RESTORED → ROLLED_BACK`.

Второй EFFECT_INTENT предшествует отказавшему второму create. Доказанный
не начатый эффект не получает дополнительный RESTORED. Case106 теперь912B,
SHA256 `379cc4bb102e0d92cf347ee068b333302b50dd9278bac24a8762e2ca67832c30`;
одно-полевой diff находится в c22-d11-20261102/case106-one-field.diff.
Новый safety-create-receipt-gap.json: durable intent, выполненный эффект,
отсутствующий receipt, recovery; **our safety behaviour, not native parity**.
Граница записана в ADR-0016 proposed и C.22 deviations. Пятнадцать intent
тестов не считаются пятнадцатью независимыми mutation proofs.

Production больше не stubs: shared whole-plan preflight/intent/restore,
AtomicFileWriter.move/rename_dir_case, replace_raw, write_apply и recovery,
внутренние prepare/apply, C.21 public projection/reexport и точное lint edge.
Scanner/diff/lint переиспользованы, публичного ToolSpec нет. Internal sync
ещё не реализован; green MODULE не означал бы готовность всей механики.
Вложенные39 native cards и отдельный safety card теперь доступны внутреннему
runner, selfcheck и probe. Старый script_edit codec не менялся.

Actual проверки и доказательства, не приёмка:

- До production: collect=executed29,29failed; projection red2failed.
- Первый shared прогон: collect=executed146,107passed/39failed — все39
  падений тогда относились к ещё не реализованному native runner.
- После contributor: collect=executed195,194passed/1failed; все C.21,
  security transfer, intents, primitives и C.20 cases в этом наборе проходят.
- Full non-live: collect=executed4458,4455passed/3failed/0errors/0skipped,
  3 live cases deselected,70.03s. JUnit SHA256
  `5aef63ebe66979b9a093a7be9b9da8d630cc38fc55663ed01be476a11dcd7a40`.
- `python -B tools/selfcheck.py editing.file_refactor --json`: exit1/fail;
  MODULE ok, layers556/0, limits556/1 прежнее informational warning,
  contract27/0, security audit0; unit98passed/1failed, corpus fail.
  Global snapshot abort на C.22 — полного verdict/count нет, не green.
- Fresh selfcheck/raw outputs сохранены наружу, canonical восстановлен
  copyfile byte-exact, reports44. Live/final mutation matrix не выполнялись.

**Новый STOP §7, не повтор D11:** полный набор обнаружил ещё один принятый
пин в tests/py/security/test_write_boundary.py:104. В
test_no_secrets_or_absolute_paths_in_the_wal четыре разрешённых состояния:
`("PREPARED", "APPLYING", "RECEIPT", "COMMITTED")`; новый EFFECT_INTENT
отвергается. Предшествующие проверки отсутствия секретов/absolute paths
проходят. Этот файл не входит в разрешение править case106; он не изменён.
Grep находит именно этот literal whitelist и прежний case106 wal_states;
утверждение аудитора об одном поле wal_states остаётся верным.

Запрашиваемая узкая правка: только добавить `"EFFECT_INTENT"` между APPLYING
и RECEIPT в whitelist этой строки, сохранив остальные строки, формат/EOL,
проверки секретов/путей и принятые корпуса. Не фильтровать journal, не
переименовывать intent в receipt и не возвращать два WAL-диалекта.

Оставшиеся два full падения внутри уже разрешённого scope:
1. preflight старого delete не сохраняет not_found для отсутствующего
   файла; требуется сохранить и прежний invalid_input для каталога.
2. q2-parent: byte-proof runner после D9 parent-case преобразует prefix,
   но удаляет старый leaf/UID по старому prefix и оставляет дубликаты в
   expected. Исправить внутреннюю проекцию удаления, не native card/assertion.

Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c22-d11-20261102/.
Черновой contributor invocation exit4 из-за ошибочного имени contract test
не считается прогоном; исправленные collect/JUnit195 сохранены отдельно.
Stage editing.file_refactor=0/skeleton, ADR-0016 proposed не менялись.

**Следующее действие:** получить разрешение на единственное добавление
EFFECT_INTENT в test_write_boundary.py:104; затем исправить два указанных
падения, реализовать external-sync, повторить полный корпус/gates/mutations/live.

## Продолжение после D12: регрессии green, external-sync STOP (2026-11-02)

D12 закрывает предыдущий STOP. В test_write_boundary.py добавлен ровно один
элемент EFFECT_INTENT между APPLYING и RECEIPT; остальные bytes, assertions,
115 CRLF и порядок прежних элементов сохранены. Byte-proof: d12-security-byte-proof.json.
В case106 добавлен разрешённый comment: «Второй intent принадлежит шагу, чей
эффект упал; receipt отсутствует по конструкции.» Другие поля и WAL не менялись;
обновлён только bytes/SHA этого case в manifest. Теперь1071B, SHA256
`c4168c650752804adff53b3d2a5ad08af82d9221e13e11a935755965f1824f9e`.

Legacy delete исправлен причиной, не ожиданием: missing→not_found,
directory→invalid_input ещё в whole-plan preflight, до APPLYING/первого эффекта.
Новый red2 перед исправлением; оба теста также проверяют отсутствие более
раннего create и неизменный WAL. Старые accepted tests не менялись.
В D9 runner owner/UID удаляются по уже преобразованному parent prefix;
native card/assertions не ослаблены. Focused collect=executed84,84passed,
5.87s; JUnit SHA `896ff0a9a4f771d2c4cd31e931ea161977579a457b86b546fb639da709fc341e`.

### Корпус external-sync и фактически найденные границы

Сняты12 новых реальных frozen sync-вызовов на изолированных NTFS-проектах:
12 success, 11 inverse byte-file checks exact, один same-path no-op без entry.
Старые tests не запускались; из test_external_move_sync.py взяты кейсы.
sys.setprofile наблюдал аргумент реального native apply, не подменял исполнение.
Cases/native raw files добавлены с SHA в отдельный manifest.sync_cases;
39 прежних prepare cards и safety card сохранены. Всего52 cards:
39 prepare +12 external-sync +1 наше safety-поведение, не native parity.
Покрыты UID/import уже moved и оставшиеся, binary/no refs, internal paths,
directory, lint-skip, same, empty directory, leaf/directory case-only.
Новый red collect=executed12,12failed (sync ещё отсутствует).

**Новый STOP §7 — три вопроса спецификации, не повтор D8–D12.**
Доказательства: c22-d12-20261102/sync-gaps.json и lossless sync-native/*.json.

1. Native directory external-sync **не меняет внешние относительные ссылки**:
   `load("src/a.gd")` и `load("src/b.gd")` остаются буквально прежними.
   Принятая C.21 directory projection меняет обе на res://deep/tree/... (count2).
   Копировать regex/scanner или молча улучшать native запрещено. Нужно разрешение
   на один internal switch `external_relative=False` в C.21 directory.projections
   и public.project_directory, default=True. Прежние references/API/public MCP,
   результаты и схемы C.21 остаются неизменными; switch только для external-sync.
   Это больше, чем ранее разрешённое извлечение уже вычисленного after-text.
2. NTFS external leaf-case: old src/a.gd существует как alias src/A.gd,
   same_file=True, actual_rel="src/A.gd", raw SHA прежний. Разрешённый anchor
   требует source absent; текущий preflight честно stale_plan, без effects/WAL.
   Native успешно sync+rollback. Нужно отдельное case-only исключение к source
   absence: только same identity, правильный raw SHA и actual name==destination,
   source actual name!=old. Existing move/already_moved=true, без forward IO,
   новых op/полей и без ослабления защиты чужого destination. Directory-case
   должен использовать разрешённый dir_case, не content-directory move.
3. Native empty-directory sync даёт entry_id и возвращает пустой каталог назад.
   Поштучных move для него нет; zero-step plan COMMITTED имеет no_receipts и
   rollback конфликт. dir_case запрещён для обычного src→dest; четвёртого op нет.
   Требуется явное решение. Предложение: разрешённая deviation **только empty
   external directory** — его location не возвращается rollback; если patches
   отсутствуют, результат no-op с entry_id=None. Это ещё НЕ разрешено и НЕ
   записано как принятая deviation. Молча выбросить anchor нельзя.

Нереентерабельный FileLock не изменён/не обойдён. Для непрерывного scan+apply
под одним lock предполагается вынести существующий эффектный цикл из
write_apply/app.py в уже разрешённый editing/shared/funnel.py; оба оркестратора
используют один executor. Не будет release/reacquire gap, второго исполнителя,
нового ToolSpec, чужого domain import или нового lock adapter. Код sync не начат
до разрешения перечисленных границ. Internal runner уже отличает sync от prepare,
недоступный sync даёт unavailable и красный verdict, не ложный green MODULE.

### Actual проверка этой сдаваемой частичной версии

- Full non-live: collect=executed4472,4460passed/12failed,0errors/0skipped,
  3 live deselected,72.34s. Все12 failures — новый test_file_refactor_sync.py;
  три прежних падения устранены. JUnit SHA256
  `cb2a55d821fa831573090c30a4ce0a0cd30608a3ea0a36d0c3942d47f5ef187e`.
- Selfcheck editing.file_refactor exit1/fail: MODULE/static ok,
  unit101passed/12failed, corpus12diff. Layers556/0; limits556/1 прежнее
  informational warning; contract27/0; security audit0.
- Global snapshot909:897matched/12diff. Два focused прогона52/40/12 каждый,
  оба exit1/status fail; прежние857 и prepare39+safety1 совпадают.
- Actual probe prepare exit0/ok; probe sync exit1/unavailable. Project byte
  trees не изменились; runtime state принудительно во внешнем временном досье.
- Fresh report/raw outputs архивированы снаружи; все44 canonical сохраняются
  copyfile byte-exact. Отчёты вручную не редактировались.
- M1–M4/P1–P3, дополнительные recovery/dir_case mutations и live3 пока не
  выполнены на финальной версии: финальной реализации ещё нет, это не green.

Досье C:/Users/Lich/AppData/Local/Temp/opencode/c22-d12-20261102/;
baseline3441files/831dirs, index SHA256
`716ca2606025765d611c100c668ccabd75050397f72328d624b29fe7319fa221`.
Stage editing.file_refactor=0/skeleton и ADR-0016 proposed сохранены.
C.22 не готов к независимому аудиту, не принято.

**Следующее действие:** получить решение по трём external-sync границам выше;
после него спецификация/новые red-пины → один lock-held shared executor и sync
→ full/double corpus/selfchecks44/mutations/live3 → SHA-таблица последней.

## Продолжение D13 — spec/red и production (2026-11-02)

D13 прочитан дословно; прежний STOP закрыт, повторное разрешение не нужно.
До новых production bytes внешний baseline3467files/831dirs, index SHA256
`ce8d6099f1f57af19fd733e22db44131829d3ba581968610c68ffb110ae71db0`.
ADR-0016 proposed/deviations дополнены спецификацией D13. Новые red8/8;
после implementation8/8 и native sync12/12 =20passed2.50s.
False keyword-only defaultTrue в C.21 public, internal partition разделяет
disjoint документы для прежней directory.projections (external с moved_map={});
нового scanner/regex нет, directory.py не тронут. Generic verify_absent прежний.
Case-only проверяет actual realpaths/оба SHA/casing и snapshot SHA дважды,
anchor исключается до WAL, отдельный anchor_already_completed. No-op не
создаёт WritePlan/WAL. Shared funnel.execute — один effect loop, write_apply
domain decision/report прежние; scan→COMMITTED под одним acquire/release.
Новые actual summary/native projections явно отражают D13 и проверяют
непустые steps, отсутствие anchor receipt и WAL на no-op; raw cards/pins прежние.

**Следующее действие:** full non-live/двойной snapshot/selfcheck C.22, мутации
M1–M4/P1–P3 плюс recovery/dir_case/lint-edge, live3 с byte restoration; после
проверок финальные записи/SHA-таблица. Stage0/skeleton и ADR proposed сохранены.

### Проверка non-live/corpus/selfcheck D13 (2026-11-02)

Collect=executed4482, passed4482, failures/errors/skips0,3live deselected,
51.11s (JUnit50.791); JUnitSHA
`e14f5badfe0104cdadec90aae882bafc0964d60fc2224e03058eb52f9a984438`.
Snapshot909/909/0; два C.22 прогона52/52/0, C.21 25/25 без recapture.
Selfcheck editing.file_refactor=ok:123unit/52corpus, layers558/0,
limits558/1 прежний split_py11 informational, contract27/0,security0.
Generated C.22 report SHA
`083af0db5b3d74ec6975b41dca7fc93dce80dcae6c5c2ab0908081050ce6568a`.
Еще2 safety/P1 pins довели новые D13 tests до10, без изменения принятого теста.
Новый root sync_flow удалён переносом его orchestration в app.py≤80:
file_refactor9 элементов, нового limits warning нет. Единый executor прежний.
Следующее действие: neighbor43 restoration (C.21 report не переснимать),
live3, mutations/M/P/gates/probes, final records/SHA. Готовность ещё не объявлена.

### Мутации/live/probes и уточнение пинов (2026-11-02)

M1 target-occupied и M2 source-modified удаляют обе preflight проверки:
late guard не портит foreign tree, но строгий доэффектный WAL-пин red.
M3 text roundtrip:4failed/2passed rawvariants; M4 no inverse:wrong tree/red.
Recovery без post-state SHA:foreign preservation red. Dir_case=os.replace
на этом NTFS пережил прежние2 actual-casing/byte pins (честно архивировано
initial-survivor-*); новый11-й D13 test наблюдает реальный os.rename на каждом
parent-case segment и также проверяет actual casing/raw inverse. С ним mutant
1failed/2passed. Старые2пина не переписаны и не ослаблены. Lint-edge deletion
synthetic test red, но actual gate сперваgreen: parent-namespace imports не
попадали в exact declared edge. Четыре C.22 import spelling приведены к
`import python.modules.editing.paths_preview as paths_preview` — теперь
actual lint_arch тоже red при удалении edge; foreign domain по-прежнему denied.
Финальные7 mutants red/errors0/skips0, каждый source восстановлен copyfile
до SHA/EOL/полного byte equality. Production причиной исправлена, не assertions.

Live Godot4.6.3.stable.official.7d41c59c4:3passed0skip23.46s;
JUnitSHA `7b62bd08bb7a778f2b8f45942e0e9d4ded6ec55b7e4ecd59452ce5f98d0c0809`.
project.godot335→419→335B, restoredSHA
`958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`;
169 только новых .gd.uid удалены,84 baseline project gd.uid exact.
CLI prepare/apply/external-sync green; public write_rollback через тот же
test-profile journal возвращает raw tree; sameplan stale/noeffect и no-op
null plan/entry без нового WAL. Case-only и lock пины остаются реальными.
Следующее действие: final non-live4483×2/double/selfcheck/gates после нового
pin/import spelling, fresh neighbor42+preservedC21, P3 final boundary,
финальные docs/WORKLOG и SHA последней. Stage0/skeleton и proposed не менялись.

### Финальные green после mutations (2026-11-02)

Collect=executed4483; два полных non-live4483passed/0failed/errors/skips,
3live deselected:63.07s и62.93s. JUnitSHA a
`6d4dddb24a9e681e321bb722ea92f124887cf4cdaf5b1461b95358804c8ab242`,
b `cd60e057ca355e04dd4090d1b2a808c8b26a98a2e50317ffa23a380b0c98b092`.
Два global909/909/0, два C22 52/52/0, C21 25/25/0 безrecapture.
Selfcheck C22 exit0/verdictok:unit124passed10.33s,corpus52/0,layers558/0,
limits558/1прежний split_py informational,security0,contract27/0.
Сам selfcheck сгенерировал canonical C22 SHA
`271c0106df17a87c0279d949700608c136a80ef06332c15a33c064745cb4e3b9`.
Все4gates exit0. P3 предварительно3470files/831dirs,+3/newdirs0/deleted0,
frozen947byteexact, UID86baselineexact; ни добавленного cache/pyc/bak/temp.
Следующее действие: fresh neighbor42+C21 reportpreserved →43canonicalbyteexact,
финальная запись WORKLOGabCRLF и finalboundary→SHAтаблица последней.
Stage0/skeleton и proposed неизменны; декларация готовности только после boundary.

## Финальная передача C.22 (2026-11-02)

**C.22 готов к независимому аудиту, не принято.** Приёмка только аудитором.
Stage0/skeleton, ADR-0016 proposed сохранены, audit-handoff не менялся.

- Final non-live collect=executed4483, twice4483passed/0failed/errors/skips,
  3live deselected,63.07s/62.93s; два JUnitSHA приведены в предыдущем разделе.
- Global909/909/0 twice, C22 52/52/0 twice, C21 25/25/0 безrecapture/reportupdate.
- Actual selfcheck C22 exit0/ok:124unit10.33s/52corpus; report generated SHA
  `271c0106df17a87c0279d949700608c136a80ef06332c15a33c064745cb4e3b9`.
  Layers558/0/security0/contract27/0; limits558/1только прежний split_py info.
- Fresh42neighbor reports:fail0; прежние skeleton blocked не скрыты. C21 report
  не переснят, все43other canonical bytes restored, canonical44/runtime26.
- Inventory52 =39native prepare/apply +12native external-sync +1явно nonnative
  safety;102native SHA pins и51raw native cases exact, sync raw равны capture.
- M1–M4/recovery-post-state/parent-case-os.rename/lint-edge:7red, errors/skips0,
  copyfile source SHA/EOL/bytes exact. Dircase initial survivor честно сохранён;
  новый parent-case primitive pin добавлен, старые assertions не изменены.
- P1 unplanned refs/foreign UID untouched; P2 stale sameplan/noeffects; P3
  3467→3470files,+3/changed15/deleted0/831dirs exact, cache/pyc/bak/temp additions0.
  UID86baseline/frozen947 exact; accepted tests/corpora D13 byteexact.
- Live3passed0skip23.46s Godot4.6.3;169только новых gd.uid удалены, project
  335→419→335B/SHA958b3a92… и84project baseline gd.uid exact. No baseline delete.
- D12 exact tuple-element115CRLF/comment106+manifestbytesSHA re-proved;
  C21 protected files10byteexact, generic verify_absent exact, contract fields
  Step/Receipt/WritePlan unchanged. CLIprepare/apply/sync/publicinverse green.

Pre-final byte boundary ужеgreen по всем этим инвариантам. Исторический WORKLOG
prefix615832B exact; финальная запись только abCRLF, остальные changed docsLF.
После WORKLOG final_boundary.py повторяет проверки, пишет final-index.json,
final-boundary.json/case-inventory.json и **SHA256-final.md последним**.
Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c22-d13-20261102/`.

**Следующее действие:** независимый аудит C.22 по досье и фактическому selfcheck;
## C.22 принят аудитом 2026-11-02 (сессия 76)

Срез принят. Проверено мной на сданном дереве, независимо от прогонов портера:
non-live junit 4483 / 0 / 0 / 0; snapshot `кейсов 909, расхождений нет` (в нём
`editing/file_refactor 52/52`, `paths_preview 25/25` без пересъёмки, `split_py 108/108`);
focused 128 passed; `selfcheck editing.file_refactor` → `ok` (124 unit, 52 corpus, layers 558,
limits 558 с одним информационным `split_py`, contract 27, security ok); `gen_contract --check`
→ 27 артефактов; отчётов 44; дерево 3435 / 813 / 83; WORKLOG 625 476 B, `\r\n` 4831,
`\r\r\n` 0, U+FFFD 0.

Соответствие решениям D1–D13 подтверждено по коду: `funnel.preflight` — аддитивный проход
до первого эффекта (тени, transfers, deletions, `dir_case` строго последним, хеши, case-identity);
`EFFECT_INTENT` как durable запись на шаг перед эффектом; recovery различает intent-без-receipt
и legacy `left_prepared`; `move`/`dir_case`/`replace_raw` реализованы в `substrate/fs` и `shared`,
в `python/modules/editing/file_refactor/**` нет ни `open`, ни `os.replace`, ни `shutil`;
`paths_preview.public.external_relative=True` по умолчанию, поведение C.21 не сдвинуто.

Моя мутация вне списка портера (проверка, что case-only допуск реально запинен): `case = False`
в `funnel.preflight` краснит `tests/py/integration/test_file_refactor.py::test_native_corpus[q2-parent-prepare]`;
источник восстановлен байт-в-байт (`funnel.py` 16 804 B, sha `e35613222279`).

Долг на следующую штатную правку (не блокирует приёмку): ячейка `editing.file_refactor`
в таблице механик остаётся **0** (менять стадии — моё действие), `parity.md` для записи
`file_refactor` ещё не переведён в `ported`, `tests-map.md` не содержит строк C.22.


только аудитор решает принятие/смену stage/parity/ADR, не начинать другую механику.

### Штатная правка аудитора 2026-11-03 (сессия 77)

Долг из раздела приёмки C.22 закрыт аудитором при моих прогонах: ячейка
`editing.file_refactor` в таблице механик 0→7, `parity.md` → `ported`.
Основание — мои прогоны этой сессии: `selfcheck editing.file_refactor` ×2
(с бэкапом/возвратом отчётов байт-в-байт): verdict ok — module = вклад в
write_preview/write_apply, layers 568/0, limits 568/2, contract 28/0,
security ok, unit 124, corpus 52/0; `snapshot_diff` ×2 — «1237, расхождений
нет», в том числе `file_refactor 52/52`; полный non-live 5225 (5223/2 genuine
1314 skips); live 3/3 с побайтовым возвратом project.godot.

