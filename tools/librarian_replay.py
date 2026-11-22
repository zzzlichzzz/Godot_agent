"""D52 reference lane: all 141 envelopes + 72 checks, not public ask responses.

Reuse the accepted, newly authored reference observations, not old test code.
Their existing normalization is limited to sandbox paths, frozen time and
UTF-8/Base64 path substitution; no result-shape or substantive-field projection.
Public Agent.call answers/errors/profile logging are a separate mandatory suite.
"""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory


def replay(folder, compare):
    from tests.py.context.observations import observe
    from tests.py.context.guard_operations import replay as guard_replay

    folder = Path(folder)
    catalog = json.loads((folder / "catalog.json").read_text(encoding="utf-8"))
    expected_guard = json.loads((folder / "guard72.json").read_text(encoding="utf-8"))["checks"]
    if not isinstance(catalog, list) or len(catalog) != 141:
        raise ValueError("librarian reference catalog must contain exactly141 records")
    ids = [row.get("id") for row in catalog if isinstance(row, dict)]
    if len(ids) != 141 or len(set(ids)) != 141 or not all(isinstance(name, str) for name in ids):
        raise ValueError("librarian reference catalog requires141 unique string IDs")
    if not isinstance(expected_guard, list) or len(expected_guard) != 72:
        raise ValueError("librarian reference guard must contain exactly72 checks")
    failures, passed = [], 0
    with TemporaryDirectory(prefix="godot_agent_librarian_reference_") as temporary:
        sandbox = Path(temporary)
        for record in catalog:
            case_id = record["id"]
            expected = json.loads((folder / "observations" / (case_id + ".json")).read_text(encoding="utf-8"))
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                actual = observe(record, sandbox / case_id)
            problem = compare(actual, expected, "")
            if record["operation"] == "log" and (out.getvalue() or err.getvalue()):
                problem = problem or "native logger stdout/stderr must remain empty"
            if problem:
                failures.append("%s: %s" % (case_id, problem))
            else:
                passed += 1
        actual_guard = guard_replay(sandbox / "guard72")["checks"]
        if len(actual_guard) != 72:
            raise ValueError("librarian reference replay returned an incomplete guard set")
        for number, (actual, expected) in enumerate(zip(actual_guard, expected_guard), 1):
            problem = compare(actual, expected, "")
            if not actual.get("pass"):
                problem = problem or "guard did not pass"
            if problem:
                failures.append("guard-%02d: %s" % (number, problem))
            else:
                passed += 1
    return 213, passed, failures
