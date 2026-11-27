# engine_kb.class_api — C.11, класс Godot по read-only кэшу API

**Статус:** этап 7 — принято аудитом 2026-10-31 (сессия 63).
**Обновлено:** 2026-10-31.

## Цель

Инструмент `api` возвращает сведения о классе из существующего `api_cache`:
цепочку наследования, методы с арностью и сигнатурами, свойства и сигналы.
Основание — `_start-prompt.engine_kb_class_api.md`; ToolSpec переносится дословно.
Портер не ставит этап 7 и не правит `_audit-handoff.md`.

Вне scope: `engine_info`, `api_cache_refresh`, `verification.api_check`, CLI,
save/migrate/write/mkdir, новый порт или bundled-кэш, editor/WAL/undo.
Принятая C.10/F1 закрыта аудитом сессии 62 и не открывается заново.

## Старый код

Эталон: `D:/vajno/Godot/тест-плагина-ии/addons/Godot_agent/godot_agent/`.
HEAD по промпту `ba0535d4dec43c32750e601a6ca86e377abc6af3`.
`gd_api_cache.py`: 11545 B, 216 LF/0 CRLF, SHA256
`6e6f5e0c83de40d2469e167554cfa1084952f0812175bc4f67239a259650b65a` — сверено.

| Файл | Что переносим / граница |
|---|---|
| `python/godot_tools/gd_api_cache.py:19–27,115–216` | read API, версия, truthy-кэш, chain guard/depth30, setdefault members/signatures |
| `python/tools/agent_bridge.py:534–581` | прочитан cmd_api; bool(record), fallback арности через int; CLI-текст/RC не переносим |
| `gd_api_cache.py:32–114` | прочитано, но save/migrate вне scope; oracle только на одноразовых проектах |

## Старые тесты

| Источник | Судьба | Что берём |
|---|---|---|
| Отдельных старых тестов class_api нет (промпт §3) | новые кейсы actual-old | ≥18 библиотечных наблюдений; py_compile/CLI не считаются тестами |

В `docs/tests-map.md` нет отдельных строк этой механики; все 168 старых судеб
сохраняются. Новые128unit/contract/integration тестов внесены пятью строками
в приложение карты. Строка api в `docs/parity.md` — этап6, не `ported`.

## Корпус

Снят: **26 кейсов, 14 вариантов, 27 входных файлов**,20успешных/6refusals;
повторная библиотечная пересъёмка26/26, reference/projection differences0.
Манифест: `fixtures/corpus/engine_kb/class_api/manifest.json`; capture_script
11145B/SHA8bf9424d117a7601. Скрипт вне addon, `capture.py` во внешнем каталоге.
Покрыты цепочка4класса/overrides/signatures/−1arity/null/cycle/missing/falsy,
no/empty/broken/list-root cache,strip/invalid args,35-level chain с depth30.
Raw oracle mkdir эффекты сохранены в reference_effects; fixture bytes неизменны
на disposable copies, созданные `.agent_history/snapshots` в addon не попали.
Маленькие проекты в
`fixtures/projects/corpus/engine_kb/class_api/<variant>/`; перед каждым oracle
сбросить `gd_api_cache._cache['root']=None`, `['classes']={}`. Сырые
`reference_result`, SHA исходника/съёмщика/входов сохраняются до кода и тестов.
Реальный 2 МБ кэш разрешён только во временной копии, не в addon/корпусе.

## Спецификация и инварианты

- ToolSpec §2.1: `api`, `args{class_name}`, `effects='read'`, `limits={}`.
- `class_name.strip()`, пусто → invalid_input; `found=bool(record)`.
- Chain порядок эталона, cycle guard/depth30; ближайший член побеждает.
- Member lists сортируются; строки сигнатур дословны; битая арность −1/−1.
- Версия только при непустых classes; no_cache — успешный unavailable-ответ.
- Domain/shared чистые; app ≤80 строк; запись/миграция и новые порты запрещены.
- Свежесть обеспечивает один additive snapshot() (ADR-0009); classes(), _read(),
  constructor/cache_path и приватное memoized-состояние не меняются.

## Решения по ходу

Восемь решений §4 приняты как требования. Пользователь разрешил решения трёх
блокеров: аддитивный fresh snapshot() существующего api_cache без изменения
classes(); P3 на domain/core.py + отдельный shared purity test/mutation;
точный companion whitelist из пункта3 ниже. Зафиксировано в ADR-0009.

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-31 | 1 | обязательные документы/соседи/ADR-0004/0006/0008 и оба эталонных файла прочитаны; лист ранее отсутствовал, создан по §3 |
| 2026-10-31 | база | byte-copy 2171 файлов/83 UID, capability files20=19+template; +1 к базе2170 — новый start-prompt |
| 2026-10-31 | preflight | sandbox: classes() после замены JSON отдаёт Old, свежий экземпляр — New; shared pathlib не ловится текущими lint_arch checks |
| 2026-10-31 | 2 | actual-old26cases/27inputs, повтор26/0diff; selfcheck blocked,exit2/stderr0 — MODULE ещё нет, статические497/19/securityok |
| 2026-10-31 | 3 | ToolSpec по §2.1; новый scope128tests/5files: red110failed/18passed,exit1/stderr0 до core/app/snapshot/MODULE. XML red.xml вне addon |
| 2026-10-31 | 4 | продолжение другого чата: существующая реализация сохранена; свежий selfcheck ok/exit0/stderr0,128unit/26corpus,498layers/limits,20cards; actual-old recapture26/0diff. Companion SHA001 завершён, исходные EOL inventory-вставок восстановлены |
| 2026-10-31 | 5 | non-live2601passed/93files=2473+128, ordered collect/executed IDs совпали; corpus557=531+26/0diff; соседи126/37,136/62,315/65 unchanged; gen_contract write/check20, прежние19карточек byte-identical |
| 2026-10-31 | 6 | wide actual-old17caches/1573queries/0diff; live3passed; Node2D probe read-only338methods/51properties/17signals; D1–D8/P1–P3/shared красные, все SHA/EOL restored; final selfcheck ok128/26; готово к независимому аудиту, не принято |

Промпт подтверждён: 35237 B, 419 CRLF/419 LF, без BOM, SHA256
`3fa8f44cdfb8cd391f19d7482c9987fff81cc90e09c0c68a43d081c2748ccff6`.
Backups, `before.json`, `baseline.json`, `diagnostics.json` и driver — вне addon:
`C:/Users/Lich/AppData/Local/Temp/opencode/c11-engine-kb-20261031/`.
Sandbox-диагностика не выдаётся за submitted-byte мутацию P3.

## Проверки

Итоговый `python -B tools/selfcheck.py engine_kb.class_api`: exit0/stderr0,
вердикт **ok**,unit128passed1.52s,corpus26/0diff,layers498/0,
limits498/0warnings,contract20/0diff,securityok. Отчёт
`reports/selfcheck/engine_kb.class_api.json`; stdout/метаданные
`final-owner.*` в `C:/Users/Lich/AppData/Local/Temp/opencode/c11-resume-20261031/`.
Первичный blocked preflight остаётся историческим доказательством, не итогом.
Полная non-live регрессия **2601passed/93files**, XML без fail/error/skip;
collect-only2601 и ordered executed IDs совпали (`count-proof.json`). По файлам:
core35,app35,contract16,integration_api32,snapshot10 — всего128.
Финальный полный прогон:64.22s pytest/66.072s wrapper,exit0/stderr0.
Все корпуса **557/0diff**; gd_lint **126/37**,verify **136/62**,tscn_lint **315/65**.
`gen_contract --write/--check`:20/0diff, исходные19карточек и template неизменны.
Все финальные security/layers/limits/contract проверки exit0/stderr0.

| selfcheck gate | Итог |
|---|---|
| module | ok engine_kb.class_api(api) |
| layers | ok498/0violations |
| limits | ok498/0warnings |
| contract | ok20/0diff |
| security | ok |
| unit | ok128passed1.52s |
| corpus | ok26/0diff |
| verdict | ok,exit0/stderr0 |

```text
selfcheck engine_kb.class_api
  module         ok              engine_kb.class_api (api)
  layers         ok              файлов 498, нарушений нет
  limits         ok              файлов 498, предупреждений 0
  contract       ok              артефактов 20, расхождений нет
  security       ok              нарушений нет
  unit           ok              128 passed in 1.52s
  corpus         ok              кейсов 26, расхождений нет
вердикт: ok
```

## Доказательства финального среза

- Собственная повторная actual-old съёмка26/26,reference/projection0diff,
  exit0/stderr0. Corpus diff строка нового корпуса: class_api26/26/0diff;
  полный итог557/0diff (`corpus.stdout.txt`).
- Wide differential на всех16fixture caches (включая C.8 api/api_broken/api_falsy)
  и реальном external2МБ: **17caches/1573queries/0diff**,108.876s,exit0/stderr0.
  Oracle root/classes reset перед каждым запросом; sandbox project SHA/дерево
  и полное addon-дерево неизменны (`differential.json`, `differential-tree-proof.json`).
  Первый wide запуск был остановлен whole-tree guard после параллельного обновления
  отчётов соседей; второй чистый прогон завершён без ослабления проверки.
- Probe `api` с args-file Node2D на external temp-копии:foundtrue,
  version `4.6.3-stable (official)`,chain Node2D→CanvasItem→Node→Object,
  methods338/properties51/signals17;exit0/stderr0,project bytes unchanged.
  Real cache2004630B/SHA7352d27c8d8ed77b84b3b98400093c85144c4b6f8b8919b147ca035a67c8a93c;
  ответ/proof сохранены вне addon (`probe.*`,`probe-proof.json`).
- Live **3passed21.75s**,XML fail/error/skip0,exit0/stderr0; сгенерированные
  только этим запуском111UID byte-copied наружу и удалены точным списком;
  исходные83UID/все остальные bytes сохранены (`live-proof.json`).
- Full-byte scope2171→2233files,+62,removed/unexpected0,83UID/debris0;
  2171=принятая база2170+start-prompt. Девять reverse projections accepted
  seams exact, frozen source/прежние карточки/схема/статические tools/editor/
  scene_model/verification/старые168test fates byte-identical.
  Полный список изменённых/добавленных файлов с SHA256/bytes/LF/CRLF —
  `final-proof.json` снаружи; inventory projection — `inventory-eol-proof.json`.
  Original ApiCacheStore prefix (constructor/cache_path/_read/classes) exact;
  memoized classes совместимы, новые snapshot fresh/coherent tests зелёные.
- Контекст:19имён/api:read,capability files21=20+template,
  editor markers6/verbs_version3. Companion SHA001
  `bfa96c53c011bd6c28655d8dd698838febf012abea0805b639913dc16a5a2e8a`.

### Submitted-byte мутации (последовательно, не sandbox)

| Мутация | Результат на128тестах / gate |
|---|---|
| D1 found=True | 24failed/104passed |
| D2 убрать сортировку | 18failed/110passed |
| D3 cycle guard off | 7failed/121passed |
| D4 members только leaf | 21failed/107passed |
| D5 signatures ignored | 17failed/111passed |
| D6 bad arity0/0 | 7failed/121passed |
| D7 unavailable=[] | 11failed/117passed |
| D8 app version="" | 32failed/96passed |
| P1 required без found | 128unit green; gen_contract exit1/api.json stale |
| P2 app foreign domain | lint_arch exit1/foreign module |
| P3 domain pathlib (ADR-0009) | lint_arch exit1/domain IO |
| shared pathlib | 1failed/127passed, explicit shared purity gate |

Все красные exit1/stderr0; errors/skips0. Бэкапы submitted bytes сделаны до
первой мутации; после каждой восстановлены и сверены SHA/bytes/LF/CRLF.
После всех восстановлений128passed,contract/layers зелёные. Полные команды,
failed test IDs и before/mutant/restored pins — `mutation-proof.json`.
Submitted core SHA888bcb485e5212f380ae78a53b8e3c3b60e8cb1fb2e3c211c93523df60eac000;
shared SHA5a9bad5013fbcb3a96d3def0b08118924699b8e3432d12ddf38d75ef0c1e7294;
app SHAe7cdda5f4e96182d8573832bb4e3f9d7d2fdf99caf745e5da8acc4b567bcb0c7;
tools SHA5fffe966f159f5b0b3ee4f4c29ee3b7ec04b23f00962df37a9ed940c93d55efa.

## Блокеры preflight (согласованно закрыты)

1. `ApiCacheStore.classes():42–55` держит truthy self._classes. §2.3/§4 требуют
   свежий диск на каждый api-вызов, но §1/§6 запрещают менять classes(). Только
   additive version() не устраняет stale classes и может рассогласовать версию.
2. P3 из §5 (`shared/inheritance.py: import pathlib`) не ловится frozen
   `lint_arch.is_domain():102–105`; правило охватывает только feature/domain/**.
   Sandbox: shared violations=[], domain/core.py violations=[pathlib].
3. Whitelist не называет `fixtures/corpus/context/gather/manifest.json`, хотя
   смена case001 требует нового SHA. Пункт4 говорит о19именах/карточках, но
   инвентари реально пинят18: integrations gd_lint/node/scene и contracts
   functions/usages, помимо явно разрешённого test_tscn_lint.py. Нужна точная
   авторизация только count/list/api:read и companion SHA, без иных правок.

## Следующее действие

Независимому аудитору переснять26кейсов своим oracle-скриптом, повторить wide differential/свои мутации и проверить final-proof.json; только аудитор решает принятие/этап7.

## Приёмка аудитом (сессия 63, 2026-10-31)

Принято своими прогонами, не по отчёту портера:

- Пересъёмка корпуса с эталона (`gd_api_cache` со сбросом `_cache` на каждый кейс): `reference_result` **26/26**, независимая проекция **20/20**, порт `api` против `expect` **26/26** (6 отказов сверены по `kind`), идемпотентность и неизменность sha256 дерева проекта.
- Дифференциал шире корпуса: 16 кэшей `fixtures/**` по всем классам кэша + реальный кэш старого плагина (`agent_api_cache/default_api_cache.json`, 2 004 630 B, 1488 классов) в temp-проекте → **296 запросов, 0 расхождений, 0 исключений**.
- Свои мутации: M1 24, M2 18, M3 15, M4 7, M5 9, M6 7, M7 10, M8 11, M10 4 красных; M9 (`cache_version` без `if classes`) эквивалентна — инвариант держит `ApiCacheStore._read_snapshot` (проба: пустые `classes` → `({}, '')`); P1 ловится только `gen_contract --check`, P2 — `lint_arch`. Все файлы восстановлены побайтово (`core 888BCB485E52`, `inheritance 5A9BAD5013FB`, `app E7CDDA5F4E96`, `tools 5FFFE966F159`).
- Числа: 2601 non-live (93 файла, = collect) + 3 live (23.1 с, stderr 0); `snapshot_diff` 557/0; `gen_contract --check` 20; selfcheck 128/26, layers 498, limits 498/0, security ok; соседи `gd_lint` 126/37, `verify` 136/62, `tscn_lint` 315/65 без сдвига; дерево 2233 / `.gd.uid` 83 / debris 0, 111 сгенерированных UID удалены.
