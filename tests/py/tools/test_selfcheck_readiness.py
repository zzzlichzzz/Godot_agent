"""tools/selfcheck.py: решение о готовности модуля (R-18).

Строка `module` — единственное место, которое отличает «собран» от «заготовка», и
именно она решает, получит ли вклад вида `context.editor_context` вердикт `ok` или
`fail`. Поэтому решение вынесено в чистую функцию и проверяется на всех случаях:
заготовка, вклад без тестов, вклад с тестами, спек без объявлений.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]


def _load(name):
    path = ROOT / "tools" / (name + ".py")
    spec = importlib.util.spec_from_file_location("tool_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


selfcheck = _load("selfcheck")


def spec(provides=(), contributes=(), module_id="context.editor_context"):
    return SimpleNamespace(id=module_id, provides_tools=tuple(provides),
                           contributes_to=tuple(contributes))


def test_stub_without_spec_is_not_implemented():
    status, detail = selfcheck.module_readiness(None, True, False,
                                                "RuntimeError: нет MODULE")
    assert status == "not_implemented"
    assert "заготовка" in detail and "нет MODULE" in detail


def test_contribution_without_tests_is_not_implemented():
    status, detail = selfcheck.module_readiness(spec(contributes=("context",)), False, False)
    assert status == "not_implemented"
    assert "нет tests" in detail and "context" in detail


def test_contribution_with_tests_is_ok():
    status, detail = selfcheck.module_readiness(spec(contributes=("context",)), True, False)
    assert status == "ok"
    assert "вклад в context" in detail


def test_module_without_tools_and_contribution_fails():
    status, detail = selfcheck.module_readiness(spec(), True, True)
    assert status == "fail"
    assert "provides_tools" in detail and "contributes_to" in detail


def test_tool_module_with_tests_and_corpus_is_ok():
    status, detail = selfcheck.module_readiness(
        spec(provides=("write_preview",), module_id="editing.write_preview"), True, True)
    assert status == "ok"
    assert "корпуса нет" not in detail


def test_tool_module_without_corpus_stays_ok_but_says_so():
    status, detail = selfcheck.module_readiness(
        spec(provides=("write_preview",), module_id="editing.write_preview"), True, False)
    assert status == "ok"
    assert "корпуса нет" in detail


def test_editor_context_is_never_fail():
    """Живой вклад до реализации: заготовка или ok, но не провал."""
    module = ROOT / "python" / "modules" / "context" / "editor_context"
    status, detail = selfcheck.check_module("context.editor_context", module)
    assert status in ("ok", "not_implemented"), detail


# --- политика корпуса: corpus | live (B.1) ------------------------------
def test_live_corpus_with_live_test_is_ok():
    """Флаг `live` + живой тест механики — корпус не нужен, провала нет."""
    live = [ROOT / "tests" / "py" / "live" / "test_editor_branch_live.py"]
    status, detail = selfcheck.corpus_readiness("live", "editing.scene_ops", [], live)
    assert status == "ok"
    assert "GDScript" in detail and "test_editor_branch_live.py" in detail


def test_live_corpus_without_live_test_is_not_implemented():
    """Флаг `live` без живого теста — `not_implemented`, а не «зелено»."""
    status, detail = selfcheck.corpus_readiness("live", "editing.scene_ops", [], [])
    assert status == "not_implemented"
    assert "живого теста" in detail and "editing.scene_ops" in detail


def test_default_corpus_policy_unchanged():
    """Политика по умолчанию: нет папки корпуса — `not_implemented`."""
    status, detail = selfcheck.corpus_readiness("corpus", "editing.scene_ops", [], [])
    assert status == "not_implemented"
    assert "нет корпуса" in detail
    status, _detail = selfcheck.corpus_readiness("corpus", "editing.scene_ops",
                                                 [ROOT / "fixtures"], [])
    assert status == "corpus"


def test_live_tests_found_by_module_id():
    """Живые тесты ищутся по упоминанию `module_id` в `tests/py/live/*.py`."""
    found = selfcheck.live_tests("editing.scene_ops")
    assert found, "живой тест должен называть editing.scene_ops"
    assert all(path.parent.name == "live" for path in found)


def test_scene_ops_manifest_declares_live_corpus():
    """Манифест механики объявляет политику `live` (данные, а не текст отчёта)."""
    spec, reason = selfcheck._spec("editing.scene_ops")
    assert spec is not None, reason
    assert spec.corpus == "live"

def test_check_corpus_uses_live_flag_of_manifest():
    """Сквозная сверка: `check_corpus` читает флаг манифеста, а не имя модуля."""
    status, detail = selfcheck.check_corpus("editing.scene_ops")
    assert status == "ok", detail
    assert "корпус live" in detail
