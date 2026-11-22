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
