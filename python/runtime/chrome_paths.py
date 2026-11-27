"""Startup Chrome/Edge discovery for isolated CDP browser launch (D111/BUG-008)."""
import os
from pathlib import Path

CHROME_ENV = 'GODOT_AGENT_CHROME_PATH'
CHROME_NOT_FOUND_MSG = 'Chrome не найден, укажите путь в настройках'
_APP_PATHS_SUBKEY = r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe'


def _is_safe_browser_binary(raw):
    text = str(raw or '').strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        text = text[1:-1].strip()
    if not text:
        return None
    try:
        path = Path(text)
        # Keep SEC-20 user-profile quarantine even if registry/env is poisoned.
        if any(part.lower() == 'user data' for part in path.parts):
            return None
        if path.is_file():
            return str(path)
    except (OSError, ValueError):
        return None
    return None


def _standard_chrome_paths(environ=None):
    env = os.environ if environ is None else environ
    candidates = [
        Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'),
        Path(r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'),
    ]
    local_app = (env.get('LOCALAPPDATA') or '').strip()
    if not local_app and env is os.environ:
        expanded = os.path.expandvars('%LOCALAPPDATA%')
        if expanded and '%' not in expanded:
            local_app = expanded
    if local_app:
        candidates.append(Path(local_app) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe')
    return tuple(candidates)


def _standard_edge_paths():
    return (
        Path(r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'),
        Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),
    )


def _winreg_module():
    try:
        import winreg
        return winreg
    except ImportError:
        return None


def read_registry_chrome_path():
    """Read HKLM App Paths\\chrome.exe default value safely; return None on absence."""
    winreg = _winreg_module()
    if winreg is None:
        return None
    views = (getattr(winreg, 'KEY_WOW64_64KEY', 0), getattr(winreg, 'KEY_WOW64_32KEY', 0))
    for flag in views:
        access = winreg.KEY_READ | flag
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _APP_PATHS_SUBKEY, 0, access) as key:
                value, _kind = winreg.QueryValueEx(key, '')
            safe = _is_safe_browser_binary(value)
            if safe:
                return safe
        except (OSError, ValueError, RuntimeError):
            continue
    return None


def detect_chrome_path(environ=None, standard_paths=None, edge_paths=None, registry_lookup=None):
    """Find Chrome or Edge binary path in standard folders and HKLM App Paths."""
    chrome_candidates = _standard_chrome_paths(environ) if standard_paths is None else standard_paths
    for candidate in chrome_candidates:
        safe = _is_safe_browser_binary(candidate)
        if safe:
            return safe
    reg_value = read_registry_chrome_path() if registry_lookup is None else registry_lookup()
    safe_reg = _is_safe_browser_binary(reg_value)
    if safe_reg:
        return safe_reg
    edge_candidates = _standard_edge_paths() if edge_paths is None else edge_paths
    for candidate in edge_candidates:
        safe = _is_safe_browser_binary(candidate)
        if safe:
            return safe
    return None


def configure_chrome_env(environ=None):
    """Populate GODOT_AGENT_CHROME_PATH at server startup when unset/empty."""
    env = os.environ if environ is None else environ
    existing = str(env.get(CHROME_ENV, '') or '').strip()
    if existing:
        return _is_safe_browser_binary(existing)
    detected = detect_chrome_path(environ=env)
    if detected:
        env[CHROME_ENV] = detected
        return detected
    return None
