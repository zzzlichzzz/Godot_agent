# ADR-0088: T1 native script-fact coverage is additive

Date: 2026-11-22. Scope: T-D test/corpus registration only, no format/runtime change.

## Measurement

Fresh full T-D-final-A2:8237passed/1failure/2historical WinError1314 skips.
The sole failure is the unchanged required-GD coverage test:36 newly submitted
editor scripts have no facts in the accepted frozen manifest. Its assertion is
correct. Native scene_deps.py has the exact accepted reference SHA/19866bytes;
ordinary explicit import (os/re only) calls actual extract_handlers,
_collect_custom_signals and _method_connected_in_code on all36 files twice.
Both complete rounds agree; native files and repository remain unchanged.

## Decision

- Keep fixtures/corpus/scene_model/scene_deps/manifest.json byte-exact.
- Put the36 measured raw source pins/facts in separate module-owned
  fixtures/corpus/scene_model/t1_script_facts/manifest.json.
- In tests/py/formats/test_scene_deps_facts.py add exactly one in-memory manifest
  composition line before parametrization. Existing function bodies, all assertions,
  old facts and their order stay byte-exact; removing that line reconstructs the
  submitted-C test. The36 new IDs test the actual native facts, not copied old tests.
- Add one owned test for frozen-manifest pin, reference pin and exact additive scope.
- Allow only these36 measured additional format IDs in final collection; all
  published A/K1/B/C IDs/phases/order and the only two privilege gaps stay required.

## Proof required

Genuine existing coverage RED before composition; paired same-ID GREEN plus all36
native cases, exact old-test/corpus reconstruction, current-byte mutation of the
composition, fresh paired full/gates/six selfchecks/clients and raw inventory
readback. Previous failed full remains evidence, not closure. No test weakening,
new skip, format semantic change, native source modification or acceptance claim.
