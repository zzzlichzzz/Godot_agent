"""Packaging closure: selenium lazy browser submodules must be bundled in godot_agent_server.exe."""
from pathlib import Path
import sys
import pytest
from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[3]
EXE = ROOT / 'python/dist/godot_agent_server.exe'
REQUIRED_SELENIUM = (
    'selenium',
    'selenium.common.exceptions',
    'selenium.webdriver',
    'selenium.webdriver.chrome.options',
    'selenium.webdriver.chrome.service',
    'selenium.webdriver.chrome.webdriver',
    'selenium.webdriver.chromium.options',
    'selenium.webdriver.chromium.webdriver',
    'selenium.webdriver.common.action_chains',
    'selenium.webdriver.common.by',
    'selenium.webdriver.common.driver_finder',
    'selenium.webdriver.common.keys',
    'selenium.webdriver.common.selenium_manager',
    'selenium.webdriver.edge.options',
    'selenium.webdriver.edge.service',
    'selenium.webdriver.edge.webdriver',
)


def test_build_http_exe_collects_selenium_submodules(tmp_path, monkeypatch):
    import PyInstaller.__main__ as pi_main
    from tools import build_http_exe

    captured = []
    monkeypatch.setattr(pi_main, 'run', lambda cmd: captured.append(list(cmd)))
    work = tmp_path / 'work'
    monkeypatch.setattr(sys, 'argv', ['build_http_exe.py', '--work', str(work)])
    assert build_http_exe.main() == 0
    assert len(captured) == 1
    cmd = captured[0]
    pairs = list(zip(cmd, cmd[1:]))
    assert ('--collect-submodules', 'selenium') in pairs


def test_delivered_exe_contains_selenium_chrome_and_edge_submodules():
    assert EXE.is_file()
    archive = CArchiveReader(str(EXE))
    pyz = archive.open_embedded_archive(next(name for name in archive.toc if name.endswith('.pyz')))
    toc = set(pyz.toc)
    missing = [name for name in REQUIRED_SELENIUM if name not in toc]
    assert missing == [], missing
