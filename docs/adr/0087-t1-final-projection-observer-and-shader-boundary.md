# ADR-0087 — T1: exact predecessor projection, owned test scope, shader boundary

Дата: 2026-11-22. Scope: T-D, not an exemption for accepted native code.

## Measurements before correction

Initial final gates and six mechanic selfchecks passed twice. Full pytest failed;
the raw run is retained under `T-D-final`, not labelled complete.
`test_bootstrap_exact_two_insertions_preserve_d65` still expects T-B's planner
expression, while default composition now contains two own T-D inserts.
The new NativePlanner observation leaves imported aliases in process state.
A two-case probe did not reproduce the old binding failures and is explicitly
not RED evidence. A new isolated registry-restoration case genuinely fails.
Six shader include regressions reach the engine runner before policy refusal.
The native shader measurement returned null: actual external compilation/read
was not proved and is not claimed.

## Decision

1. In `tests/py/chat_k1/test_gateway.py` insert only the exact reverse projection
   of T-D's EngineOverlay import and NativePlanner expression. Require each
   inserted token exactly once. Then execute every existing T-B/K1/D65 byte,
   count, EOL and SHA assertion unchanged. No changed golden or relaxed assertion.
2. In the new `tests/py/editor_t1/test_structural_overlay.py`, scope its real
   native preparation with `patch.dict(sys.modules)` and restore the entire
   registry on success or refusal. Fix the own default_ports call's profile/
   state arguments. Do not change accepted alias ownership or old observers.
3. Apply the existing canonical res:// and PathPolicy boundary also to copied
   `.gdshader` quoted references. Resolve relative shader references against
   the captured file's project-relative parent, rejecting traversal/backslashes
   before engine IO. No external-path allowlist or sandbox claim.

## Required proof

Actual same-ID paired GREEN, exact reconstruction of the submitted C test after
removing only this projection, killed/restored projection/shader/observer mutants,
fresh ordered A/K1/B/C regression pairs, gates and six selfchecks, client pairs,
raw readback, docs-only closure, seal LAST and complete sibling ZIP verification.
Initial failed full and inconclusive/native/observer attempts remain immutable
evidence. No independent acceptance is asserted.
