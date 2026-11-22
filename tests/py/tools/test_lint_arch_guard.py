"""tools/lint_arch.py: стража границ домена (R-11, R-22).

Две вещи, на которые ссылались отчёты фаз 0–1, держались на ревью: в `domain/`
проходил `import os`, а лазейка `len < 4 → True` в `_same_feature` пропускала
импорт корня чужой области (`from python.modules import scene_model`). Здесь
закреплено ровно то поведение, которое обязано ломаться мутацией: убрать
правило IO — краснеет `test_domain_io_import_is_a_violation`; вернуть
`len < 4 → True` — краснеет `test_foreign_module_root_in_domain_is_a_violation`.
Граница правила тоже проверяется: `app.py` того же модуля импортировать `os`
может, а `kernel/` правилом не покрыт вовсе.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load(name):
    path = ROOT / "tools" / (name + ".py")
    spec = importlib.util.spec_from_file_location("tool_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lint = _load("lint_arch")


def _project(tmp_path, monkeypatch):
    """Проект в `tmp_path`: инструмент видит только его `python/`."""
    python = tmp_path / "python"
    (python / "modules").mkdir(parents=True)
    monkeypatch.setattr(lint, "ROOT", tmp_path)
    monkeypatch.setattr(lint, "PYTHON", python)
    return python


def _write(python, rel, text):
    path = python / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_domain_io_import_is_a_violation(tmp_path, monkeypatch):
    """(а) `import os` в `domain/` — нарушение с путём файла и модулем."""
    python = _project(tmp_path, monkeypatch)
    path = _write(python, "modules/context/gather/domain/core.py",
                  '"""Домен."""\n\nimport os\n')
    assert lint.check_domain_io(path) == [
        "python/modules/context/gather/domain/core.py:3: "
        "в domain/ запрещён IO-импорт os"]
    assert lint.main(["lint_arch"]) == 1


def test_domain_io_from_import_is_a_violation(tmp_path, monkeypatch):
    """`from X import ...` — та же граница: вложенный модуль называется корнем."""
    python = _project(tmp_path, monkeypatch)
    path = _write(python, "modules/context/gather/domain/core.py",
                  "from pathlib import Path\n"
                  "from urllib.request import urlopen\n")
    assert lint.check_domain_io(path) == [
        "python/modules/context/gather/domain/core.py:1: "
        "в domain/ запрещён IO-импорт pathlib",
        "python/modules/context/gather/domain/core.py:2: "
        "в domain/ запрещён IO-импорт urllib"]


def test_app_io_import_is_outside_the_rule(tmp_path, monkeypatch):
    """(б) `app.py` того же модуля — граница правила: `os` там законен."""
    python = _project(tmp_path, monkeypatch)
    path = _write(python, "modules/context/gather/app.py", "import os\n")
    assert lint.is_domain(path) is False
    assert lint.check_domain_io(path) == []
    assert lint.main(["lint_arch"]) == 0


def test_foreign_module_root_in_domain_is_a_violation(tmp_path, monkeypatch):
    """(в) `from python.modules import scene_model` — чужая область, не «своё»."""
    python = _project(tmp_path, monkeypatch)
    path = _write(python, "modules/context/gather/domain/core.py",
                  "from python.modules import scene_model\n")
    violations = lint.check_edges(path)
    assert len(violations) == 1, violations
    assert "python/modules/context/gather/domain/core.py" in violations[0]
    assert "python.modules" in violations[0]
    assert lint.main(["lint_arch"]) == 1


def test_own_area_shared_in_domain_is_allowed(tmp_path, monkeypatch):
    """(г) общий код своей области (`shared/`) — разрешён по-прежнему."""
    python = _project(tmp_path, monkeypatch)
    _write(python, "modules/context/shared/__init__.py",
           '"""Общий код области context."""\n')
    path = _write(python, "modules/context/gather/domain/core.py",
                  "from python.modules.context.shared import context_section\n")
    assert lint.check_edges(path) == []
    assert lint.check_domain_io(path) == []
    assert lint.main(["lint_arch"]) == 0
