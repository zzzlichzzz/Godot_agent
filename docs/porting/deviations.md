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
