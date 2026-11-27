"""SEC-02: петлевой клиент моста - узкое исключение с проверкой адреса.

Правило: `socket` разрешён только в `python/substrate/editor/` (Python - клиент,
слушает GDScript, ADR-0007); `requests`/`urllib` там по-прежнему запрещены, а
не-петлевой адрес - нарушение. Правила: R-20 (статический инвариант), R-22.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load(name):
    spec = importlib.util.spec_from_file_location("tool_" + name,
                                                  ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = _load("security_audit")


def _tree(tmp_path, monkeypatch, rel_path, text):
    """Файл в поддельном `python/`: корень аудита смотрит в `tmp_path`."""
    py = tmp_path / "python"
    path = py / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "PY", py)
    monkeypatch.setattr(audit, "NET_ALLOWED", py / "substrate" / "llm")
    monkeypatch.setattr(audit, "BRIDGE_CLIENT", py / "substrate" / "editor")
    return path


def test_bridge_client_may_use_loopback_socket(tmp_path, monkeypatch):
    """Клиенту моста нужен TCP на петле - это не «сеть наружу»."""
    _tree(tmp_path, monkeypatch, "substrate/editor/client.py",
          'import socket\nHOST = "127.0.0.1"\n')
    assert audit.check_network_imports() == []


def test_bridge_client_may_not_use_requests(tmp_path, monkeypatch):
    """Исключение узкое: HTTP-клиенты в мосте запрещены."""
    _tree(tmp_path, monkeypatch, "substrate/editor/client.py",
          'import requests\nHOST = "127.0.0.1"\n')
    assert audit.check_network_imports() == [
        "SEC-02 python/substrate/editor/client.py: импорт requests вне substrate/llm"]


def test_socket_outside_bridge_is_still_a_violation(tmp_path, monkeypatch):
    """В модуле `socket` запрещён: исключение только для каталога моста."""
    _tree(tmp_path, monkeypatch, "modules/x/y/app.py", "import socket\n")
    assert audit.check_network_imports() == [
        "SEC-02 python/modules/x/y/app.py: импорт socket вне substrate/llm"]


def test_bridge_with_public_address_is_a_violation(tmp_path, monkeypatch):
    """Адрес моста проверяется: `0.0.0.0` - нарушение, а не «клиент же»."""
    _tree(tmp_path, monkeypatch, "substrate/editor/client.py",
          'import socket\nHOST = "0.0.0.0"\n')
    assert audit.check_network_imports() == [
        "SEC-02 python/substrate/editor/client.py: мост не на петле (адрес 0.0.0.0)"]
