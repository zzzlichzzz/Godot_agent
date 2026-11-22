# Инварианты безопасности (SEC-01…)

Каждая строка — обещание с проверкой. `P` — проверяется автоматически (`tools/security_audit.py`
или тест), `T` — тестом в `tests/py/security/`, `R` — ревью (временная мера, подлежит
автоматизации). Инвариант без проверки — не инвариант.

| ID | Инвариант | Проверка |
|---|---|---|
| SEC-01 | В `python/` нет `os.system`, `eval`, `exec`, `pickle`, `marshal` | P: `security_audit` (запрещённые вызовы) |
| SEC-02 | Сеть (`socket`, `urllib`, `http.client`, `requests`) только в `python/substrate/llm/` | P: `security_audit` (импорты) |
| SEC-03 | Слушающий сокет: HTTP-канал — только `python/channels/http/`, мост редактора — `editor/` (GDScript), оба на `127.0.0.1`; порт моста случайный, токен в каждом кадре, второй слушающий сокет запрещён (ADR-0007). Non-listening B-1 probe не слушатель: допускается только AST-доказанный exclusive bind127.0.0.1:9222 в facade, закрытый with до Popen; alias/escape/listen/иной адрес или порт не получают исключение | P: `security_audit` (расположение + адрес) + T: кадр без токена → отказ и закрытие; `test_sec03_nonlistening_probe.py` |
| SEC-04 | Запуск процессов — только `python/substrate/engine/`; `shell=True` запрещён | P: `security_audit` |
| SEC-05 | В `editor/` и `runtime/` нет `OS.execute`, `OS.shell_open`, `OS.create_process`, `OS.kill` | P: `security_audit` (GDScript) |
| SEC-06 | В репозитории нет секретов (шаблоны `sk-…`, `AIza…`, `ghp_…`, `Bearer …`, `-----BEGIN … PRIVATE KEY-----`) | P: `security_audit` (секреты), исключены `docs/` и `contract/errors.json` |
| SEC-07 | `.gitignore` исключает `.env`, `*.key`, `secrets*`, `reports/`, `python/build/`, `python/dist/` | P: `security_audit` |
| SEC-08 | Список разрешённых хостов — данные (`contract/network_allow.json`); кода со «своим» хостом нет | P: `security_audit` + T: запрос к чужому хосту → `denied` |
| SEC-09 | Приватные и metadata-адреса запрещены всегда (`127.*`, `10.*`, `192.168.*`, `172.16-31.*`, `169.254.*`, `*.local`) | T: SSRF-набор |
| SEC-10 | HTTP: обязательный токен; чужой `Origin`/`Host` → `denied`; тело больше лимита → отказ | T: `tests/py/security/` |
| SEC-11 | Запись только через воронку: `apply` без `plan_id`/`digest` невозможен; `preview` не меняет файлы (хеши до/после) | T: воронка (ADR-0005) |
| SEC-12 | `PathPolicy`: выход за корень проекта и `user://godot_agent/` невозможен (`..`, абсолютный путь, симлинк, junction, UNC, регистр, юникод) | T: `path_policy` набор |
| SEC-13 | Секреты не попадают в логи, ошибки, отчёты `selfcheck` и корпус (редакция по шаблонам) | T: прогон с фейковым ключом → в выводе нет ключа |
| SEC-14 | Команды из данных не выполняются: «отравленный» файл проекта с инструкцией не меняет ход вызова | T: prompt-injection набор |
| SEC-15 | Автоподтверждение записи читается только из настроек пользователя; флаг из содержимого проекта игнорируется | T: инъекция флага |
| SEC-16 | Обновление: zip-slip невозможен (пути нормализуются, выход за корень → отказ), код из архива не исполняется, применение только по подтверждению | T: updater (когда появится) |
| SEC-17 | Домен не делает HTTP: у инструментов нет возможности «сходить по URL» (если появится — только allow-list + лимиты) | P: `security_audit` + R |
| SEC-18 | Лимиты на объём: размер файла чтения, число результатов, размер тела, время операции — есть и проверяются | T: лимиты (R-06/R-18) |
| SEC-19 | Браузерная ветка правит только `visibilityState`/`hidden` и только у сайтов, где ответ читается из DOM; `hasFocus`, `toString`, `navigator.*` не подменяются | P: `security_audit` (запрещённые техники + D30 literal site flags) + T: `test_sec19_site_flags.py` + R: ревью спуф-скрипта |
| SEC-20 | Chrome запускается обычным процессом, selenium только подключается (`debuggerAddress`); `--enable-automation`/`--headless` запрещены; `navigator.webdriver` остаётся `false` и не подменяется; `needs_visibility_spoof` не поднимается с `false` | P: `security_audit` (сверка с `contract/browser_stealth.json`, D30 AST для multiline flags) + T: `test_sec19_site_flags.py` |
| SEC-21 | Создание и удаление файлов проекта выполняет только общая WAL-воронка: `create` требует отсутствующую цель, `delete` — обычный файл с точным raw sha256; каталог не удаляется, а rollback/recovery возвращает дерево побайтово | T: `tests/py/security/test_split_apply_write.py` + C.20 integration |

| SEC-22 | C.22 transfer проверяет оба endpoint до эффекта; addons case-insensitive и agent-tree запрещены даже с flags, project.godot нельзя переносить, root plugin.cfg можно; move/dir_case/replace_raw только через общую WAL-воронку, durable EFFECT_INTENT до эффекта и RECEIPT до следующего, raw-byte rollback/recovery не трогает чужую правку | T: `tests/py/security/test_file_refactor_write.py` + C.22 integration |

| SEC-23 | C.23 prepare-only: target и dependency проходят одинаковую module-local resolved-identity/casefold политику до подготовки; addons/**, .agent_history, project.godot и escape запрещены независимо от регистра/trusted flags; root plugin.cfg допускается только read-dependency. Реальный fs containment обязателен, generic guards неизменны и остаются вторым барьером. Нет apply, файловых эффектов, transformed/raw bytes или absolute paths в публичном ответе; trusted addon edits не портированы. C.24 отдельно утверждает write/transformer boundary | T: `tests/py/security/test_resource_ops_policy.py` + C.23 integration/corpus |

| SEC-24 | C.24 D18/D19: BOM отказ invalid_input/load_failed без эффекта; target и все dependencies сохраняют SEC-23 resolved/casefold/real containment до WAL, повторное raw-чтение проверяет policy до IO; resource bytes только pure span transformer и существующая replace_raw WAL-воронка, raw SHA guard/stale repeat apply, one step per target, reverse raw compensation, чужая poststate не перезаписывается; public bytes/abs нет. R-06 cohesion area допускает только warning (8000,8400], >8400 error во всех areas без feature/per-file исключений; остальные hard limits неизменны | T: новые `tests/py/security/test_resource_apply_security.py`, `tests/py/integration/test_resource_ops_apply.py`, `tests/py/integration/test_resource_ops_apply_safety.py`, `tests/py/formats/test_resource_transform.py`, `tests/py/contract/test_resource_ops_area_limits.py`, `tests/py/contract/test_resource_write_client.py`; R-22 mutations |

## Как это встроено в работу

Дополнение SEC-24 (C.25, D20/D21): регистрация internal service не расширяет
публичный периметр: tree `TOOLS=()`, без fictitious contributes/capability;
public tool без call и отсутствующий required port по-прежнему изолированно denied.
Проверки: `tests/py/security/test_project_text_registration.py` и
`tests/py/contract/test_project_text_tree_registration.py`. Чтение/новый list_entries
не обходят и не выдают symlink/junction pointer; проверка типа до обхода,
real containment/casefold policy до чтения, сырые байты не меняются. Native
WinError1314 требует `pytest.skip("symlink unsupported: WinError 1314")`, это
не покрытие разрешённых symlink-сценариев. Все прежние C.24 части SEC-24 сохранены.

- `python tools/security_audit.py` — статическая часть; входит в `selfcheck` (R-18).
- `tests/py/security/` — атакующие тесты; пополняются вместе с механикой.
- Модуль с `effects != read` не получает `ported` без своих строк в этой таблице.
- Новый инвариант добавляется при появлении новой поверхности (браузер, git-операции,
  сеть, установка плагинов), а не «после инцидента».

## Чего здесь нет намеренно

- Антивирусных обещаний и проверки «на вирусы»: проверяется поведение агента, а не
  содержимое диска.
- Шифрования журнала правок: он не содержит секретов, а ключ пришлось бы хранить рядом.
- Песочницы ОС: процесс и так под учёткой пользователя; песочница (AppContainer,
  job objects) — возможное улучшение, но не замена инвариантам.


## J1b D62–D64 — дополнение SEC-03/SEC-04 (2026-11-14)

Граница санкционирована; доказательства реализации записываются после red/green,
не утверждаются этой спецификацией. ADR-0018 и новые tests/py/security/test_headless_process_pin.py.
- SEC-03/D62: один конкретный byte-offset subprocess.run в exact verification/headless path,
  настоящий одиночный bare top-level import subprocess; argv List строк/str(Name) и
  только уточнённого пользователем str(Attribute(Name(proc), pid)); без shell/kwargs spread,
  kwargs Constant либо subprocess.DEVNULL/PIPE. Это timeout termination owned-child,
  не listener и не освобождение файла. Другие run/bind/listen/HTTPServer и parse errors red;
  B-1 и его условия не меняются; snippets не запускаются, bind/listen не выполняются.
- SEC-04/D63: ровно один top-level bare import subprocess в том же exact path;
  alias/from/multi/duplicate/nested/neighbor verification запрещены. shell=True запрещён
  везде; PROC_ALLOWED неизменен, blanket verification exemption отсутствует.
- D64: exact python/agent_headless_validator.gd 1701 B/799ec9e26f43f65a… LF39/CRLF0;
  native primitive только ResourceLoader/owned overlay result/quit, без OS launcher,
  бизнес-логики или изменения _MEIPASS. Проверки default/explicit + byte-pin обязательны.


### J1b / A1 фактическая проверка (2026-11-14)

D62/D63 implemented с exact-path/byte-offset AST-исключениями, B-1/PROC_ALLOWED сохранены; D64 exact1701 B/default+explicit green. Genuine red192 collected/135failed/57passed/0errors → 192 same-ID green, все прежние121 failure ID зелёные; native118×2/canonical118×2/0diff. Real Godot4.6:4 own-sandbox default-harness probes/8 engine processes/0diff/no source writes. Mutants:15 checker+2 D64 killed/0survivors, exact SHA/EOL restore/same-ID green. Full non-live×2:7400passed/2 historical WinError1314 skips; frozen230/API253/project288×2, gates×2 и post-resource gates0. Actual selfcheck assistant.judge fail/exit1 (missing MODULE), probe unknown_tool/exit1; context.ask ok/exit0,104unit/213corpus. Aliases0, MODULE/D59/D60/A2 не implemented. A1 reference mini-seal готовится, MODULE не ported, independent acceptance pending. Все rejected setup/invocation/scope records сохранены, native originals/NN/browser-live/production HTTP нетронуты.

Подэтап reference не закрывает historical verification.check/live fate или assistant.judge MODULE. Frozen230 membership сохранён: browser141 + B-1 AST72 + B217; D51 detector34 дополнительно в full/security/mutations. Мини-seal — integrity, не самостоятельная приёмка.
Следующее действие: После A1 mini-seal: A2 native cases/corpus×2 для scene/editing/actions; D60 genuine red exact-six caps перед переносом.


### J1 / A2 private reference, no new public effects (2026-11-15)

A2 reference-read/prepare проверен, не public MODULE. Six sources152941 B/EOL byte-exact; native214+supp1 ×2/canonical214+supp1 ×2/0diff, full snapshots no-write. Genuine A2220/221 red → same221green, D6013/26 red → same26green; restored all249green. 6 A2+4 D60 mutants killed/0final survivors, exact bytes/SHA/LF/CRLF restore/same-ID green. Первый ambiguity survivor сохранён: wrongly named old negative-case не создавал candidates; gap закрыт новым genuine native supplement×2 и теми же mutant bytes, frozen214 не переписан. Full non-live7649passed ×2 + ровно два historical WinError1314 skips, no added skips/xfails; collected7651 и executed IDs/order exact. Frozen230/API253/project288 ×2, все288 manifest IDs. Gates/security ×2 green. Real Godot4.6:4 native/canonical reference probes/8 processes, default harness,0diff/no source writes/owned validation leftovers0; это headless structural validation, не semantic editor apply/rollback и не public judge probes. Actual selfcheck assistant.judge fail/exit1 (missing MODULE) ×2; actual probe judge unknown_tool/exit1 ×2. Actual context.ask selfcheck ok/exit0 ×2,104unit/213corpus. D60 exact-six caps реализованы minimal two-insertion checker delta, old constants/caps сохранены; D59/A3/B/+15 aliases/MODULE/public corpus не реализованы. Rejected baseline assumptions, freeze path, pytest basetemp setup, outer120s partial canonical capture, singular collected-item receipt, double-q collect verbosity и initial survivor сохранены, не засчитаны как successful evidence. A1 accepted record read-only; mini-seal/ZIP фиксируют integrity, не самостоятельную приёмку.

Legacy apply/materialize/sync functions are inert private references, not registered public tools. Judge may not bypass the existing write funnel. NN/browser masking/HTTP unchanged.
Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/answer-judge-J1-A2-20261114/
Следующее действие: После A2 mini-seal/ZIP: A3 symbol_refactor native cases/observations ×2 до missing-code red; затем B/D59/adapter/MODULE.


### SEC-J1 — public deterministic read judge (2026-11-15)

Project bytes/metadata/dirs/links не меняются, candidate actions остаются inert data. Data/history/API/index storage только вне проекта внутри profile; guard до активации, shared lock, finally restoration на return/Exception/BaseException. Raw parser sample sink временно no-op только в JudgeRead; native parser неизменён. Tests: test_judge_read_boundaries.py, test_judge_parser_privacy.py, judge_j1/test_adapter.py/test_binding.py, contract/test_judge_disabled.py;14 critical final killed/0survivors, four actual CLI no-write proofs. SEC03/B-1/PROC_ALLOWED/SEC06/browser spoof/NN/HTTP не расширены.
### SEC-K1 — публичный read-only chat (2026-11-20)

Явный native READ allowlist + проверка реального registry.effects перед dispatch;
write/plan/exec/recursive chat не выполняются и получают объяснение. Публичная
диагностика оборачивается только app.call; judge получает native STRING.
ChatGateway активирует bindings только внутри send под shared librarian lock;
50aliases unchanged, ключи/history/cache только внутри external state profile,
realpath guard до IO. ENV/cache/parser-sample hook восстанавливаются даже при
Exception/BaseException и ошибке самого финального redacted logger.
`tests/py/security/test_chat_boundaries.py` genuine2 RED→3 same-ID GREEN (masking
case был GREEN уже в RED); native mask/redact неизменён. Gateway12 tests, bounded
loop/public29, CLI8; реальных provider calls/нового listen/spoof/exec нет.

### SEC-T1-WRITE — specification before new write tools

`assistant_plan/turn` никогда не применяют проектные байты; returned model action
не является approval. `assistant_confirm` требует отдельный boolean approved,
immutable preview TTL, exact digest и project/policy; rejected/replayed/stale/
foreign plans закрыты. Generic WAL marker `requires_confirmation=true` требует
USER_CONFIRMED с тем же digest даже при прямом вызове старого write_apply.
Исторические untagged editing plans не меняют семантику. Rollback требует own
assistant plan и receipt; чужая локальная правка не перезаписывается. Windows
ADS/drive colon запрещён до native prepare и повторно в delta compiler; содержимое
файла остаётся данными. Native executors/50 aliases/K1 bytes не меняются.
Тесты: `tests/py/security/test_t1_write_confirmation.py`, новые transfer_t1
write/turn cases и `assistant/write/tests/test_core.py`; no network/credentials.
## SEC-T1-PARENTS — подтверждённый footprint и receipt-owned каталоги

- Только отсутствующие родители из validated native file deltas становятся
  mkdir Steps; ожидаемая absence и полный список входят в immutable digest.
- Intent до mkdir, directory identity receipt после; проверка matching parent
  receipt до записи и inverse потомка. Никакого второго writer или native apply.
- Для tagged assistant.write также нужен plain proof существующих ancestors
  непосредственно до эффекта. Empty/OSError proof → typed refusal без записи;
  это не ownership receipt, pre-existing parent не удаляется (ADR0082).
- Обратный rmdir только пустого plain каталога с matching device/inode proof;
  чужие/pre-existing/replaced/reparse каталоги не удаляются и не перезаписываются.
- Missing directory receipt блокирует recovery без угадывания владельца и без
  ложного clean rollback. Тест: assistant/write/tests/test_directories.py,
  все пять самостоятельных сценариев и реальный parent-proof mutant;
  tests/py/security/test_t1_parent_ownership.py: foreign clone/filled directory,
  nested move, genuine interrupted recovery и bounded footprint;
  test_t1_parent_plain.py — empty/unavailable existing-parent proof, без новой
  symlink skip или заявления о live junction coverage.
## SEC-T1-LOCAL — local HTTP/MCP boundary (ADR0085)

- SEC-T1-LOCAL-01: HTTP requires external token before dispatch/JSON; Host/Origin
  checked before health; body/object/project/policy bounds fail closed.
- SEC-T1-LOCAL-02: One Agent/B funnel, explicit preview/digest approval; native
  executor/model never authorizes project effects. Stop remains available.
- SEC-T1-LOCAL-03: Session-scoped native/profile overrides restore in finally;
  accepted aliases and foreign browsers never adopted. No stealth increase.
- SEC-T1-LOCAL-04: Owned random loopback listener only; endpoint cleanup proves
  identity and complete raw bytes; finally closes only the session gateway's owned
  facade, never a global foreign browser. No native unowned-orphan killing.
- SEC-T1-LOCAL-05: MCP finite depth64/newline1,000,000; malformed record cannot
  kill next frame. External profile outside project/source before adapters/recovery.
- SEC-T1-LOCAL-06: Two native caps require exact path/full SHA; EOL/sibling changes
  fail. Old global caps remain closed. Tests: tests/py/channels_t1 and
  tests/py/security/test_t1_local_channels.py; no real sockets/provider/browser.

## SEC-T1-OVERLAY — preparation cannot write the real project (ADR0086)

- Fixed absolute configured Godot binary/argv, shell=False, bounded timeout;
  actions cannot choose an executable or become command strings.
- Exclusive external state-owned scratch; no project/source state, reparse
  traversal, foreign adoption/cleanup. Policy before reads/copies.
- No untrusted code in overlay: Script references/autoloads/binary resources
  fail closed, not silently stubbed. Unrelated scripts are never copied/executed.
  Quoted engine references canonical policy-readable res:// or UID only;
   external/escaped text resource references refused before import. Shader quoted
   references use the same policy; relative shader paths normalize against their
   captured project-relative parent, None/traversal/backslashes denied (ADR0087).
   Relative editor/resource references, escaped settings and executable/config
   suffixes cannot bypass classification; .gdc also denied (ADR0089). Conservative
   scalar/parent-node false refusals are an explicit safety gap, not native parity.
- Actual native prepare/raw/semantic/dependency proof before execute. Only target
  delta; before bytes reproved; original project unchanged.
- Refusals/restoration remain refusals; no stdout/stderr/path leak to clients.
  One B executor/WAL/explicit confirmation only.
- SEC05 permission exact path/full raw SHA/byte positions, inactive references.
  Tests: tests/py/security/test_t1_overlay_security.py,
   tests/py/editor_t1/test_structural_overlay.py and test_native_gd_security.py.

## SEC-TF — frozen-panel HTTP adapters (specification before code)

- All 27 added routes use ProjectAuth before JSON/dispatch; Host/Origin and
  project binding remain strict. HTTP payload cannot elevate startup policy.
- Native approved-only confirmation binds to one pending server plan with
  nonempty exact digest; mismatched IDs/digests fail closed. Exclusion/editor
  proof cannot silently replace that plan. No automatic approval.
- Explicit native refactor `/apply` is a separate button contract: exact prior
  action/options AND still-pending preview identity only, translated to assistant_confirm with immutable server
  plan_id/digest and boolean approval. No native apply/direct write_apply;
  USER_CONFIRMED, existing WAL and receipt remain mandatory.
- Automatic external-move notification cannot authorize writes. Excluded NN,
  unsupported runtime/editor claims and protected addon split edits refuse.
- Shutdown targets only this listener callback. Endpoint cleanup preserves raw
  bytes+identity proof and gateway ownership; no process killing.
- Cache/log markers stay inside guarded external state; no addon cache mirror
  or migration, no credentials/raw log text in evidence.
Tests: `tests/py/panel_tf/`, `tests/py/security/test_panel_tf_security.py`;
auth/digest/direct-WAL mutants required before completion.
- Exe no-arg binding precedes the listener: only its own deployment project and
  plain external Godot userdata; malformed/ambiguous configuration refuses.
  Exclusive token creation preserves native read semantics and never replaces
   an existing panel token. No startup shell or execution of project scripts.
 - Old `/chat/confirm` cannot make a stale native `/apply` approve another chat
    plan. Refactor rejection reports no changed paths or committed entry.
- External cache/log file reads and writes reject reparse/symlink/multi-link
  targets. Native serialization uses an exclusive external stage and exact
  owned-stage/parent proof before replace, never truncates a project hardlink.
  Log marker/native tmp checks precede assistant_turn; refused send keeps its
  prepared report. Native output binding is restored exactly after success or
  failure. Permanent cases: tests/py/security/test_panel_tf_state.py (real
  hardlinks, no new privilege skip). D97 is a guarded IO boundary, not a sandbox.
