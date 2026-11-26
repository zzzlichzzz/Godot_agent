# T-F — D90 и далее

История D01–D89 остаётся неизменной в [../deviations.md](../deviations.md).
Мандат T-F требует этот путь; до T-F файл отсутствовал. Это отдельное
продолжение нумерации, не копия или перенумерация прежней истории.

## D90 — rebuild-only observer: абсолютный superclass resource path

Разрешённая мандатом минимальная правка: `editor/core/resource_publication_observer.gd`
должен расширять `res://addons/godot_agent/editor/native/agent_resource_executor.gd`,
а не отсутствующий файл в `editor/core/`. Native executor и все frozen UI
не изменяются. Настоящий `test_bridge_live.py` и Godot `--check-only`
должны дать RED до кода, затем тот же live ID GREEN дважды.
Проверено: настоящий live ID RED/exit1 → тот же ID GREEN/exit0 дважды;
Godot4.6.3 `--check-only` RED/exit1 → GREEN/exit0 дважды. `observer/proof.json`
доказывает только path-delta и неизменный EOL. Внешние fixture UID сохранены
и удалены исключительно как extra к T-E allowlist; все T-E fixture pins exact.

## D91 — native confirmation binds to an immutable server preview

Part1:925 sends approved-only, not a public-tool digest. Server pending owns
plan_id/digest; missing/corrupt server digest or mismatched supplied values
refuse. Nonempty exclude requires a new preview, never recompiles underneath
approval. No native editor envelope is issued: panel gets a generic transaction
card for server/WAL effects. Explicit native Apply buttons (part4:594) map their
exact previewed action/options to assistant_confirm true, not direct write_apply.
`/chat/confirm` retains its separate predecessor contract.
Each native refactor preview additionally pins its own plan_id/digest. An old
confirmation cannot leave a reusable action-only card that approves a different
new chat plan. Genuine two-case RED → same IDs GREEN ×2; rejected refactor
reports changed_paths=[] and no entry_id, not prepared-but-unwritten paths.

## D92 — excluded or unported effects are not authorized by new routes

NN fail-closed unavailable/F0, no network/training/repository fetch. Runtime/
editor result routes have no issued execution token in the server/WAL model:
malformed metadata400, unsolicited valid result409; no foreign effects adopted.
Split scan/plan dispatch public tools within native agent-addon scope; default
policy still denies self-edit; split apply without sanctioned WAL preview409.
Nondefault scripts_only/previous_name/cleanup options unsupported by accepted
planner refuse, never ignored. Explicit semantic limitations, not full workflows.

## D93 — automatic post_move_sync is not confirmation

Part4:657 sends an automatic FileSystem notification. Native sync writes and
records its own history, with no prepare-only entrypoint. Calling it from HTTP
would bypass WAL/approval. Route refuses conflict/requires_confirmation without
project effects; manual native-safe file preview/apply remains available. No
automatic reference-sync claim.
The accepted internal C.22 file_refactor.sync executor does exist and uses WAL;
it is not the legacy function above and is not exposed through this HTTP Agent's
public registry. It is left unchanged, not declared absent or newly authorized.

## D94 — external cache/log storage and owned graceful shutdown

Native gd_api_cache operates inside existing external history scope; global
cache restored, addon_dir never passed to save. check_log uses native
collect_errors(user_data_dir,project_root,external_storage), not predecessor's
reversed two arguments. Report consumed only after successful assistant turn.
Shutdown invokes owned listener callback then existing finally cleanup; no
os._exit/unowned process/driver killing.

## D95 — no-argument exe bootstrap is bound before listening

Frozen ServerLink always passes zero arguments. Onefile is built at its exact
`python/dist/godot_agent_server.exe` fallback lookup (no duplicate source tree
inside python/dist). Bootstrap derives only its own addons/godot_agent project,
parses bounded ordinary project.godot scalar config without executing Godot,
and uses Windows APPDATA/Godot/app_userdata/config-name and port5000. Unsafe or
ambiguous custom userdata refuses with explicit --project/--state alternative.
Token uses frozen server_auth TOKEN_FILE/read_token, exclusive creation only if
missing, never overwrites a token already created by panel; strict ProjectAuth
installed before any native fail-open guard. Explicit args retain port0 support.
PyInstaller is already installed: no pip, downloads or external network.
Onefile bootloader owns a separate child server process; real socket evidence
checks exact Win32 child/parent lineage, not false equality with launcher PID.
Graceful shutdown exits both and removes only the listener-owned endpoint.

## D96 — live input mirrors only the session's existing owned browser

Native LiveInputMirror retains sequence/busy/best-effort semantics. Selected
site registry determines parser; existing gateway.current_driver only, no wait,
start, browser adoption, submit, provider call or stealth changes. Genuine
offline parser RED/no_parser → same positive service IDs GREEN ×2. No real
browser/provider workflow is claimed from the synthetic parser test.

## D97 — external cache/log files are not a project-write escape

Pre-seal synthetic measurement: native cache open(w) followed an ordinary
hardlink and changed a synthetic project file (HTTP200). Real projects were not
touched. Five permanent real-hardlink tests are genuinely RED before the fix,
with no new privilege skip. Existing native source files remain byte-exact.
The external IO port rejects reparse/symlink/multi-link files and stages native
UTF8 serialization exclusively before replacement, checking plain paths and
owned stage/parent identity. Native open binding is restored exactly under the
existing scope lock. Cache/log reads are guarded too; log marker/tmp validation
precedes assistant_turn and is repeated at output, preserving an unsent report
on refusal. These path/stage guards are not an OS sandbox claim.

## D98 — versioned D90 source input, not a changed extraction golden

First full regression: only the old observer input pin failed (370 vs409 B).
Accepted test and both old manifests remain byte-exact. An additive test input
revision applies only to the observer's existing differential test ID, checking
old SHA fa449727bf5b461b0cdff330bc4d60ced5a6a7765b665098486ea8bf05eb4706,
new SHA 4e61db341215fc73142098265e243fb12a996f5a35348b3fcaa77faf9ed90f47,
and complete raw equality to the one authorized extends replacement. Only the
input bytes/SHA fields change; handlers/signals/connected goldens do not. Any
other source drift or attempt to rebind another path fails. This is unrelated
to UID drift: original T-E fixture files and input manifests stay untouched.

## D99 — ZIP timestamp range is metadata, not corpus normalization

The identical publisher failed genuinely on a separately sealed synthetic file
with mtime epoch0: ZIP DOS dates start at1980. Two fresh synthetic peers are
GREEN after strict_timestamps=False; only ZIP date metadata is clamped to its
format range. No source bytes/times, file membership, SHA256 or EOL are changed.
Every file including seal and each empty directory is re-read and verified;
the failed synthetic partial archive is retained. Actual T-F publication runs
only after seal LAST and writes exclusively to sibling ZIP/receipt paths; its
authoritative full-member bad0 result is external to the sealed dossier.

## D100 — owned diagnostic junction entries are preserved as raw metadata

First actual seal attempt refused 365 NTFS directory junctions before writing
the seal. The first normalization attempt also refused before raw capture or
detach: `Path.resolve()` retained `\\?\C:\...` for readlink targets but `C:\...`
for HERE, so its containment comparison was false. The failed script and its
exclusive `final/dossier-links/before.json` are retained unchanged.

All measured links and existing targets belong to this dossier's diagnostic
pytest trees; no installed, native, previous sealed or project path is included.
The retry uses a fresh namespace, strips extended drive/UNC prefixes only for
containment comparisons, captures exact FSCTL_GET_REPARSE_POINT buffers and
link/target identities, and then revalidates all entries before detaching only
each measured junction entry with nonrecursive `os.rmdir`. No target deletion,
source-byte normalization, empty-file recovery or production-code change.
Before/after inventories must preserve every pre-existing ordinary file's
bytes/SHA256/EOL and directory membership, with all target identities intact
and zero remaining links. The proof is `final/dossier-links-retry-01/proof.json`;
seal and publication remain pending until that proof exists and passes.
Completed: raw metadata captured for365 entries; the separately pinned actual
detacher removed only those junction entries. `links_remaining=0`; all original
ordinary bytes/SHA256/EOL, directory membership and target identities passed.
Both failed original artifacts and the capture script remain unchanged. Earlier
final identity/repository/checkpoint records are retained byte-exact before
refresh. Production/tests/corpus/checkers/exe were not changed for packaging.

## D101 — T-F.5 config-only activation and foreign baseline (2026-11-22)

The mandate selects `editor/native/agent_entry.gd` in root `plugin.cfg`.
Its stale prototype docstring is intentionally frozen; `plugin.gd` and
`editor/t1_panel.gd` remain byte-exact rollback assets. No capability, executor,
provider, confirmation policy or native dependency is changed. The empty
`fixtures/.gdignore` already existed before this work (auditor WORKLOG tail),
and is preserved, not falsely recorded as an executor addition. Preflight found
additional fixture `.gd.uid`/`.pytest_cache` entries relative to T-F's seal:
all are foreign baseline and retained, not cleaned or restored. Exact raw
before-inventory and predecessor deltas are in the separate `tf5-20261122`
dossier. Godot probes run only on owned synthetic project copies with external
userdata; a fresh native updater cache prevents its automatic GitHub request
without changing frozen scripts. Production change is one config value only;
installed copy, previous seals, exe and frozen native/substrate bytes untouched.

## D102 — Superseded T1 entry expectation and retained REDs (2026-11-22)

The first complete 8433-ID pair genuinely failed four cases in each run:
one T1 assertion still required inactive native entry, and three frozen C.21
cases copied seven preexisting Godot UID sidecars not declared in their original
manifest. No failure is skipped, xfailed, deleted, or relabelled GREEN. T-F.5
explicitly supersedes only the entry choice: the historical T1 node ID is kept,
its one config expectation selects the native entry, and both remaining updater
and rollback-plugin assertions stay unchanged. This T1 test is not a frozen
T-A…T-E file. Its complete original bytes are retained against the preflight pin.
Native GDScript, old C.21 tests, source inputs, manifests and goldens are frozen.

Live harness failures (imports, cache filename/provider mapping, nonexistent PID
reader, console-wrapper ancestry, wrong provider URL, JSON versus JSONL journal,
and secret scan racing pytest temp handles) are retained/disclosed, not production
failures. Fresh independent rounds 19/20 passed actual provider UI, native button
HTTPRequest `/chat/confirm_action`, physical WAL commit/rollback and zero-arg exe
lineage/shutdown. No backend/native/exe rebuild was needed; no network/key claim.

## D103 — Explicit frozen input materialization plus current-UID corpus (2026-11-22)

Do not delete auditor-owned UID files or rewrite byte-exact C.21 tests/manifests.
The external `tf5_corpus.py` pytest input adapter verifies the entire actual
C.21 fixture file set equals original manifest inputs plus exactly seven pinned
UID additions in new `fixtures/corpus/editor/tf5-panel-ui/input-revision.json`.
It copies only the original manifest-declared raw inputs into an owned external
view and redirects this one frozen suite's fixture ROOT, not its assertions,
expected results, test functions or production imports. This recovers the exact
original test input revision; all original node IDs still execute normally.
In addition, 25 new cases run the genuine production agent against unfiltered
current fixture copies, assert complete bytes/SHA/file membership including the
seven sidecars, exact original native results/messages, and two-call idempotence.
Nothing is ignored in those current-input checks; new/changed/missing files fail.

Final regression is 8427 predecessor IDs +31 new IDs =8458, with the adapter
explicitly recorded in each command/receipt. Without this declared input adapter,
direct pytest of the frozen C.21 suite still reports the three preexisting input
membership failures; it must not be advertised as a clean unadapted run.
The initial adapter failed before any test (`junitxml` option name); that retained
harness error was corrected to pytest's actual `xmlpath`, without predicate changes.

The additional genuine C.21 selfcheck initially returned `unit=fail: no tests ran`
(corpus=ok, 25/0diff). Its collect-count and actual pytest are separate processes:
the adapter reused one exclusive receipt filename when JUnit was absent. This
retained harness failure is fixed only by including actual process ID in the
receipt filename; fixture pins/predicates remain identical. Final closure gates
must run all eight selfchecks twice after this correction.

## D104 — Owned diagnostic junctions at publication boundary (2026-11-22)

T-F.5 full/security runs create their own NTFS junction entries under external
`diagnostics/*/pytest-*`. Before sealing, `normalize_links.py` may detach only
these exact measured entries: capture raw `FSCTL_GET_REPARSE_POINT`, raw target
strings and source/target identities; require ordinary targets within the same
owned pytest root; validate every entry before any operation and again immediately
before single nonrecursive `os.rmdir`. No ordinary file/directory or link target
may be removed, normalized or overwritten; unknown/foreign links are STOP.
Original ordinary bytes/SHA/EOL/membership and directories must compare exactly.
Actual count/verdict belong to `links/raw-capture.json` and `links/proof.json`;
this decision alone is not evidence of execution. No production/native/installed
change or exe rebuild is authorized by it.

The source-only preclosure inspector first assumed `fixtures/corpus/editor`
already existed. Actual measured directory delta is exactly that parent plus
`tf5-panel-ui` child (no removed directories/links). Inspector expectations were
corrected to those two declared new corpus directories, not by changing any
source/baseline bytes; the original assertion failure is disclosed here.

## D105 — Observed installed-copy drift; no unauthorized restoration (2026-11-22)

Read-only preclosure inventory found 181 fixture `.uid` files absent relative to
`installed-before.json`; no added/modified ordinary files, directory or reparse
changes. Initial pins and measured missing paths remain in
`final/installed-parallel-{current,drift,summary}.json`. These paths are outside
this executor's authorized write scope. No executor command synchronized or
wrote the installed copy; grep of executed tests/Python found no installed-path
references. Attribution of removal is not proven: do not silently blame auditor
or claim whole installed tree is still byte-exact. Do not recreate/delete/revert
foreign installed work. Final identity reports initial-vs-observed drift explicitly
and only asserts stability against the separately captured observed snapshot.
Rebuild baseline UID/cache/frozen sources still must compare exactly; this does
not waive their invariants or authorize installed sync/git.

## D106 — T-F.6 diagnostic-port adapter and executable deployment STOP (2026-11-23)

This is an observation record, **not** permission to change frozen Python,
rebuild the executable, sync installed bytes, or waive the T-F.6 mandate.
Separate dossier: `%TEMP%/opencode/c8_audit/tf6-20261122/`.

Native/rebuild cold routes were observed twice each with a CPython audit hook
refusing external requests before urllib/DNS/connect. Both return eight top-level
API providers and six browser sites. Empty `catalog.providers`/`catalog.models`
is a different, secondary models.dev cache. `aistudio`/`qwen` are currently site
IDs; the API registry uses `gemini` and has no literal `qwen` provider. Keyless
refresh attempts OpenRouter; scan attempts models.dev and public provider model
endpoints. Guarded timing is **not** a measurement of real network latency.
No external catalog/provider request was sent and no real key was used.

The first zero-argument panel probe refused to start: user-owned port 5000 was
occupied (observed PID 25808). The listener was neither requested nor stopped.
Successful diagnostic rounds 7/8 launch the unchanged pinned exe with explicit
project/state/isolated port. Exactly the HOST constant in an **owned copied**
`agent_server.gd` is adapted; production/installed UI remains unchanged. Real
native sites-tab signal -> real HTTPRequest -> six visible enabled Button nodes
and viewport PNG were verified in an actual visible Godot editor. This is not
a zero-argument native-launcher acceptance or a provider/API-tab live check.
The API tab was not opened, because it automatically starts the unfixed scan.
Only the ordinary owned updater TTL is seeded; provider/catalog caches are cold.

PyInstaller read-only inspection extracts six packaged raw Python sources, all
byte-exact current source, and inspects four compiled PYZ modules. The packaged
`NativeServerReferences._load` derives routes from packaged `__file__`, not the
adjacent addon source. Live rounds 7/8 run successfully despite three deliberately
failing **owned adjacent-source** sentinels. Therefore a source-only guard/fallback
fix will not repair the deployed pinned exe. No extracted or embedded code is
patched. A separate user decision about rebuilding or using a source-based Python
entry is required before claiming the mandatory live correction.

All failed diagnostics remain disclosed: initial port collision; headless round
1 populated buttons but visibility predicate failed; visible round 3 hit a PNG
write/read race; round 5 hit a mixed-encoding exe log decode failure. The strict
visibility predicate was retained, PNG publication ordered before its receipt,
and raw logs retained (replacement decoding is only for diagnostic assertions).
Unrelated synthetic-project `/chats/list` 500 responses are retained, not accepted
as chat-regression proof. Only rounds 7/8 are successful paired diagnostics.

Observation RED: 13 cases, 9 failures/4 passes; literal provider IDs, keyless
refusal and scene UID remain unresolved. Genuine `assistant.chat` selfcheck
checkpoint: `ok`, unit 29 passed, corpus 10 with zero differences, unchanged
predicates; external report relocation, explicit existing D103 input adapter and
the existing synthetic offline chat transport are disclosed. This baseline check
does not close T-F.6. No production repair, full final regression, paired final
gates/eight selfchecks, seal or postseal ZIP has been performed.

## D107 — T-F.6 auditor-authorized offline executable build (2026-11-23)

The user explicitly overturns D106's STOP: rebuilding using installed PyInstaller
6.21.0 is an authorized executor build step, no network needed. Preserve D106 and
failed diagnostics as history; do not rewrite the original mandate. Working exe
may change; installed/native/git/sync/prior publications remain read-only. Capture
old exe bytes and exact inputs, build with tools/build_http_exe.py in fresh external
work, verify packaged sources and real panel. READ.md in the independent dossier
documents this mandate revision. No embedded/adjacent-source hotpatches.

## D108 — T-F.6 offline registry and keyless correction specification (2026-11-23)

Specification before code. Cold native/rebuild observations are retained, not
rewritten; the following authorized correction intentionally differs:
- Static fallback only, zero models.dev fetches. Keep accepted providers.py,
  catalog/model_cache and API253 corpus byte-exact. Existing locked runtime scope
  temporarily extends registry with aistudio (Gemini compatible API, not browser
  URL) and qwen (DashScope international compatible API). Preserve gemini/old IDs.
  Empty models, mandatory keys, verified=false, no price/free claims. Restore
  registry identity/cache on return and exceptions.
- Frozen chat_routes.py receives only key guards/target filtering through one new
  llm policy. Unknown/unavailable refusals remain. Keyless refresh: HTTP200/full
  settings/error='Нужен ключ провайдера'/error_code='no_key'/kind='denied'/hint;
  no network or model-error stats/cache write. Keyless scan: same error, empty
  scanned/failed, scan_skipped=true and existing models index, before catalog work.
  Keyed scans target only keyed available endpoints, not keyless public/custom
  endpoints; fresh keyed scans skip catalog. Internal fetch repeats key guard.
- Repin exact-path/full-SHA chat_routes size permission to measured final bytes,
  never a directory exemption. Existing cap-test IDs/predicates remain; only the
  measured positive cap fixture changes. New byte/EOL/sibling/cap tests protect it.
- Scene changes only Script ext_resource UID to existing sidecar. Sites UI and
  response stay unchanged; real visible providers/sites/refresh/auto-scan required.

Cases: fixtures/corpus/editor/tf6-providers/, new panel/llm/security tests; genuine
RED before implementation. Predecessor8458 IDs/order/phases plus additions x2,
gates4/selfchecks8 x2, seal LAST/verified sibling ZIP. No new public tool/writer,
browser/stealth/provider call or live-verification claim.

## D109 — T-F.6 implementation/build and retained harness failures (2026-11-23)

D108 implemented via llm policies and locked HTTP composition; accepted native
API providers/catalog/model-cache byte-exact. Route1174 CRLF lines/SHA256
`21d5609abf6873b9f8d3183c67d2062e57252fde728ab2fd6214f08eee7cef5d`.
Only exact-path/full-SHA permission changes. Four historical cap-test IDs retain
`chat_routes.py-1169` explicitly; measured input1174, assertions/other caps exact.
Scene Script UID alone matches actual sidecar.

First offline PyInstaller6.21.0 build succeeds: exe30866721B/SHA256
`d374b9227a482b7f32e74bb2dffb895e74936f9bf3e79ea88c884d8e77c94427`;
old exe backed up, build inputs unchanged except output. Six raw embedded sources
exact, three compiled policies/scope verified. No download/catalog/provider call
or real key; interpreter audit guard is not an OS sandbox. Cold corrected source
x2: ten providers/no_key, zero network attempts/config file writes.

All failures retained: wrong fixture import/module/tuple/token keyword and finally
ensure_token's None return used as header. Apparent17fail/2pass included auth403
and is NOT complete feature RED. Original pre-code observation13=9fail/4pass is
valid; fixed explicitly synthetic auth fixture gives targeted34passed (25 new +9
existing cap cases). Eight delivered-byte mutants killed, no errors/new skips,
exact raw SHA/EOL restored. Original HTTP replay is mutation, not backdated RED.

Rebuilt live1 did not expand native collapsed groups; live3 searched refresh in
model-list box rather than sibling toolbar. Both observer failures retained,
real native IDs/rows/no_key proved but not full live acceptance. Concurrent live3
copy and baseline mutation could capture historical scene bytes: never claim its
UID warning is delivered-source failure. Further live copies must not overlap
source mutation. Only observer changes: native group toggles/row buttons, actual
popup viewport, toolbar lookup/scroll. Production GDScript logic unchanged.

## D110 — honest scoped HTTP model-list badge (2026-11-23, before code)

Live popup exposes inherited `models_public` as “model list without a key”, which
contradicts D108 HTTP refusal. In same locked metadata-only scope, copy public
records with models_public=false and explicit key-required note; never mutate
accepted registry dictionaries or API253 reference behavior. No endpoint or
transport availability claim changes outside HTTP scope. Tests assert original
record/caches restored by identity and force a public-target bypass mutant;
rebuild again to deliver corrected metadata. No new effects/tool.


## D111 — startup Chrome/Edge auto-detection and fail-closed missing-browser message (2026-11-25)

- **Decision context**: `docs/porting/_start-prompt.TF6-providers.md` §1.5 (`BUG-008`). Panel reported `Browser is unavailable; configure GODOT_AGENT_CHROME_PATH` because the headless HTTP server launched without `GODOT_AGENT_CHROME_PATH`.
- **Change**: Add `python/runtime/chrome_paths.py` invoked from `python/channels/http/exe_bootstrap.py` and `python/runtime/http_services.py` (`NativeServerReferences.activate` / `build_http_agent`) while preserving `app.py` 80-line cap. Auto-detect order: standard Chrome paths (`Program Files`, `Program Files (x86)`, `%LOCALAPPDATA%`), Windows Registry `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe`, then standard Edge paths (`msedge.exe`), setting `os.environ["GODOT_AGENT_CHROME_PATH"]` when unset/empty and a regular binary file is found. Never touches `Google\Chrome\User Data` or adopts arbitrary non-binary paths.
- **Fail-closed error**: `InteractiveGateway._ensure_browser` and `InteractiveGateway.wait_driver` report `Chrome не найден, укажите путь в настройках` when `GODOT_AGENT_CHROME_PATH` is absent/invalid; explicit valid env is preserved.
- **Boundary**: Preserves `ReadOnlyBrowser` `plain_process_then_attach`, `facade.py` exact bytes/SHA, and all SEC-20 stealth invariants (`contract/browser_stealth.json`).

## D112 — systemic locale/theme wrapper return fix in frozen native panel (2026-11-25)

- **Decision context**: `docs/bugs-register.md` (`BUG-004`, `BUG-010`, `BUG-011`) and `WORKLOG.md` systemic locale issue, explicitly authorized by user prompt.
- **Defect**: `editor/native/agent_panel.gd` wrapper methods `_locale()` (line 400) and `_T()` (line 418) invoked `AgentPanelPart1._locale(self)` and `AgentPanelPart1._T(self)` without `return`, returning `null` so `_t(key)` always fell back to bare key strings and `%`-formatting in `agent_panel_part3.gd` / `agent_panel_part4.gd` raised operator `%` errors while theme styling received `null`.
- **Change**: Prepend `return ` to both one-line forwarding bodies in `editor/native/agent_panel.gd`; keep `agent_entry.gd`, `plugin.gd`, `agent_panel_part*.gd`, and all other GDScript files unchanged.
- **Verification**: Static wrapper check + real Godot 4.6.3 headless SceneTree test (`tests/py/live/test_panel_locale_live.py`) verifying `_locale()`, `_T()`, `%`-formatted keys, `AgentStatusBar.tscn`, and `agent_start_screen.set_sites()`.

## D113 — Explicit D112 source-input revision for editor/native/agent_panel.gd (2026-11-25)

- **Pattern (D98 continuation)**: Adding `return ` to `_locale()` and `_T()` changed `editor/native/agent_panel.gd` from `82171` B (`a751d654842db5097a1dd0e712960a10d3e4272f20edd27bd4b7666f4edaafd7`) to `82185` B (`c160c67762741a4b0d55596f4d4c1e44527e2e2c297b6013a61d2a99b8b3ac43`) with zero change to GDScript signal/handler extraction facts or business goldens.
- **Change**: Keep `tests/py/formats/test_scene_deps_facts.py` and both `fixtures/corpus/scene_model/*/manifest.json` files byte-exact. Extend `tests/py/panel_tf/source_inputs.py` (`revised_panel_fact`) and `tests/conftest.py` (`D113`) to verify exact inverse reconstruction back to the `82171`-byte preimage SHA256 and update only `bytes`/`sha256` on the single matching `fact`, plus dedicated `tests/py/panel_tf/test_panel_source_input.py` checks refusing any unproved byte drift or path rebinding.

## D114 — Safe stale dead-PID http_endpoint archiving (ADR-0092, 2026-11-25)

- **Context**: User's server failed to launch on startup because `http_endpoint.json` from dead `PID 29240` (`2026-11-23`) caused `FileExistsError` on exclusive `'x'` create (`listener.py:24`), repeating the same lockout previously seen for `PID 18332` and `PID 26668`.
- **Change**: Archive `PID 29240` to `http_endpoint.stale-29240-20261125.json` (with explicit user authorization), and implement ADR-0092 in `python/channels/http/listener.py`: only when an existing `http_endpoint.json` is an ordinary plain file (`nlink == 1`, no symlink/reparse), contains a complete 4-field loopback record (`host == '127.0.0.1'`, valid `port`, `pid > 0`, `session_id`), and OS checks confirm `pid` is dead (`ERROR_INVALID_PARAMETER` or exited handle, never `ERROR_ACCESS_DENIED`), preserve its exact bytes as `http_endpoint.stale-<pid>-<ts>.json` before exclusive `'x'` creation. Incomplete/malformed/foreign-shape/live/linked files still raise `FileExistsError` untouched (`test_endpoint_owner.py` and `test_http_metadata_policy.py` remain 100% unchanged and passing).

## D115 — Bundle selenium lazy browser submodules in tools/build_http_exe.py (2026-11-25)

- **Defect**: Live `/chats/new` against the rebuilt `godot_agent_server.exe` launched Chrome via `D111` auto-detection and immediately failed 503 with `No module named 'selenium.webdriver.chrome.options'`, because `selenium 4.46.0` loads `selenium.webdriver.chrome.options`, `webdriver`, `driver_finder`, `selenium_manager`, etc. dynamically and PyInstaller omitted 42 submodules.
- **Change**: Add `'--collect-submodules', 'selenium'` to `tools/build_http_exe.py` (`tools/build_http_exe.py:17`), test closure in `tests/py/panel_tf/test_exe_selenium_closure.py`, rebuild `godot_agent_server.exe` offline via PyInstaller `6.21.0`, and verify live Chrome/CDP attach startup in the rebuilt executable.

## D116 — ADR-0093 HTTP chat prompt/live_input compatibility, fail-closed GDScript policy UI, and scene UID alignment (2026-11-25)

- **Context**: User live run against `PID 11044` hit `403 HTTP cannot elevate startup policy` on both `/chat/live_input` (`BUG-009`) and `/chat` because `user://godot_agent_policy.txt` held `"1"`; inspecting downstream flow also uncovered `routes_chat.py:15` ignoring Godot panel's `"prompt"` key (`400`), missing `active` on `/chat/progress`, `panel_services.live_input` returning the parser module instead of `getattr(module, 'PARSER', module)` and missing `_selection()` fallback before turn 1, plus 7 stale script `uid://` attributes in `editor/native/*.tscn` (`UserMessageCard.tscn` et al.).
- **Change**: Implement ADR-0093 (`docs/adr/0093-http-chat-prompt-and-ui-policy.md`, `SEC-HTTP-CHAT-POLICY` in `docs/security/invariants.md`):
  - Keep `python/channels/http/auth.py` `_CONTROL_POSTS` unchanged (14 exact ADR-0091 routes), preserving all strict `403` HTTP policy-elevation blocks (`test_panel_tf_security.py`, `test_http_control_envelope.py`, `test_http_metadata_policy.py`, `test_http_chat_policy.py` all pass without relaxing a single security assertion).
  - Support `message` / `prompt` / `text` and `active=session.busy` on `/chat` and `/chat/progress` (`python/channels/http/routes_chat.py`), and resolve `gateway._record` or `gateway._selection()` + `getattr(module, 'PARSER', module)` + `kind == 'api'` guard in `python/runtime/panel_services.py` (`test_chat_prompt_and_live_input.py`).
  - Make `editor/native/agent_panel_part1.gd`, `agent_panel_part4.gd`, and `agent_locale.gd` fail closed (`_allow_addons = false`, `_allow_self_edit = false`, disabled HTTP-locked checkboxes with RU/EN tooltips) with exact inverse-verified `D116_REVISIONS` in `tests/py/panel_tf/source_inputs.py` and `tests/conftest.py` (without changing `fixtures/corpus/scene_model/t1_script_facts/manifest.json` or any extraction golden).
  - Align all 7 `editor/native/*.tscn` script UIDs to their `.gd.uid` sidecars (`test_scene_uids_and_policy_live.py`, `godot --editor --headless --quit` 0 warnings).

## D117 — DeepSeek: одно текстовое заполнение и не более одного submit (2026-11-26)

В реальной панели `/chat` вернул 400, в DeepSeek остались `.txt` в черновике;
последующий `live_input` изменял поле. До правки отдельная модель DOM в реальной
HTTP-композиции дала 6 RED. Длинная вставка шла путём Ctrl+V; общая ветка не
распознавала вкладку с файлом и могла снова заполнять поле или повторить Enter
после stale. Разрешён точечный адаптер только для DeepSeek: штатный текстовый
сеттер без Ctrl+V, точная сверка поля, максимум один Enter, без автоповтора при
неясной доставке; ошибки подготовки докладываются панели. Живое зеркало не
работает одновременно с браузерным ходом и не переписывает черновик после
ошибки DeepSeek. Пины, другие сайты, защита HTTP и маскировка неизменны.

## D118 — актуальное поле DeepSeek и восстановление зеркала (2026-11-26)

Живой отчёт: `/chat` 400 «поле выбранного чата не найдено», зеркало не пишет.
Публичный JS DeepSeek `main.b2127178f0.js` задаёт `name="search"` полю нового
сообщения; `name="user query"` используется для редактирования старого.
Адаптер D117 проверял только `textarea#chat-input`. Три RED в HTTP-композиции:
именное поле при отправке и зеркалировании, восстановление зеркала после
отказа без записи. Разрешён общий точный поиск поля для DeepSeek, без
произвольного `textarea`, без повторной отправки и без изменения пинов,
других сайтов, авторизации или маскировки.

## D119 — навигация для клиентов агента

Расширение после паритета: `read` получает включительный диапазон строк (с 1)
и абсолютное смещение в декодированных символах; `next_offset` продолжает тот
же диапазон. `search` получает включающие префиксы каталогов и расширения,
явный `offset` по группам совпадений и `next_offset` с одной группой опережения.
Вызовы без новых полей сохраняют ответы корпуса. Новый публичный `tree`
использует тот же сборщик и PathPolicy, с отдельной границей на объём выдачи;
внутренний `build` и его корпус не меняются. Сканирование публичного дерева
ограничено 4096 записями, замечает ещё одну для `truncated`; `search.snippet_chars`
ограничивает выдержку без изменения границ группы.

`chat` и `assistant_turn` имеют общую таблицу read-действий и карту проекта
на один запрос. `context.architecture` отдаёт фрагмент только явно выделенного
`res://AGENT_ARCHITECTURE.md`, если нет отдельного вклада секции. Файл читается
как данные через публичный `read` с той же политикой пути. Без файла ответ
`no_module` сохраняется. `usages`/`analyze_rename` принимают уникальное объявление
без locator (необязательная область `declaration_path`); при нескольких или
не полностью прочитанных кандидатах выбора нет. Для правки locator обязателен.

`assistant_plan.operations` принимает типизированные файловые правки через
прежний предпросмотр (SEC-11); MCP `initialize` объясняет инструменты без смены
имён. У DeepSeek только адаптер доставки ускоряет проверку стабильного финала
без действия. Нативный протокол, пины и проверка неполных действий сохраняются.
Новые сценарии проверяются через реестр; исторические снимки не переснимаются.

Сравнение `context/gather::001-all-sections` дополняет ожидаемый инвентарь
четырьмя READ (`ask`, `chat`, `judge`, `tree`) и четырьмя WRITE
(`assistant_confirm`, `assistant_plan`, `assistant_rollback`, `assistant_turn`),
возникшими после снимка из 27 инструментов. Имена, количество и эффекты
сравниваются строго. K1-каталог `assistant.chat` воспроизводится напрямую из
записанного SSE в `tools/chat_replay.py` с синтетическими ключами и запретом сети.
Сравнение ответов не меняется, внешний startup hook больше не требуется.

## D120 — доказательство завершения процесса на Windows

В `listener.py` Win32-дескриптор открывается с `SYNCHRONIZE` и проверяется
нулевым ожиданием ([ADR-0095](../adr/0095-win32-process-exit-proof.md)).
Это устраняет ложный отказ D114 для завершившегося процесса, чей PID ещё
можно открыть, в том числе с кодом выхода `259`. Сохраняются доказательство
владения, точные байты архива и эксклюзивный запуск; сомнительный результат
не разрешает замену endpoint. D118 и D120 сопоставлены на изолированном
запуске без аргументов; пользовательский профиль не использован.

## D121 — первый браузерный запрос без отдельной настройки

[ADR-0096](../adr/0096-browser-prompt-in-first-user-turn.md) заменяет два
браузерных хода D117/D119 одним: при необходимости действующая инструкция
идёт вместе с запросом пользователя. После ответа шлюз запоминает версию
инструкции и URL чата, включая переход DeepSeek на URL нового диалога.
Системное поле API не меняется. Снимок редактора подсказывает путь активной
сцены, но не прикладывает `.tscn`: модель запрашивает структуру или нужные
строки по задаче. Формат действий, проверки доставки и подтверждение правок
сохранены; исторический корпус не переснимался.

## D122 — запрашиваемый контекст панели и подтверждение чтения

[ADR-0097](../adr/0097-panel-read-consent.md) заменяет подсказку активной сцены
и стартовую карту D119/D121 в установленном контуре HTTP: провайдер получает
проектные данные лишь по запросу модели и с разрешения пользователя. Каждый
запрос чтения возвращает управление панели; отказ и отзыв не разрешают запись.
Неинтерактивные циклы и исторические эталоны сохранены. Для проверки исходников
GDScript зафиксированы две точные ревизии UI и отдельный факт нового помощника.
Изменения ожидания DeepSeek ограничены адаптером доставки: учтены JSON отдельно
от его визуального заместителя и фактическая высота строк при переносе.

## D123 — оформление нативной панели после переноса

В [TF5](TF5-panel-ui.md) добавлены штатная навигация дока, поля редактора,
оформление карточек и отдельная карточка разрешения. Для четырёх изменённых
GDScript зафиксированы исходные и новые хеши; прежняя промежуточная ревизия
главной сохранена. Исторические эталоны и ожидания сигналов не переснимались.

## D124 — видимая история диалога панели

Модульный `/chat` дописывает видимые реплики в тот профиль и чат, куда был
отправлен запрос. Используется существующий формат нативного `chat_store`.
На продолжениях не сохраняются техническая подсказка, результат инструмента
и повтор пользовательского запроса. Отказ сохранения виден в панели.

По отдельному запросу изменены главная и карточки переписки ([TF5](TF5-panel-ui.md)).
Для локализации новые подписи обратимо отделены от проверяемой ревизии D116.
Цепочка проверенных исходников D123 и извлечение сигналов сохранены.
