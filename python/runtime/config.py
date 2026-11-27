"""runtime/config.py - конфигурация: порт, пути, лимиты, таймауты.

Модули не знают, где лежит состояние: путь приходит адаптером. В боевом профиле
это `user://godot_agent`, в headless/CLI — переменная окружения, в тестах —
временный каталог. Проект остаётся чистым.
"""

import os
import tempfile

#: Переменная окружения перекрывает путь по умолчанию (headless/CI).
STATE_DIR_ENV = "GODOT_AGENT_STATE_DIR"


def state_root(profile, explicit=None):
    """Корень состояния профиля: `<база>/<profile>`; база — explicit/env/времянка."""
    base = explicit or os.environ.get(STATE_DIR_ENV) or os.path.join(
        tempfile.gettempdir(), "godot_agent")
    return os.path.join(os.path.abspath(str(base)), str(profile or "default"))


def journal_dir(profile, explicit=None):
    """Каталог WAL: `<state_root>/journal` (ADR-0005)."""
    return os.path.join(state_root(profile, explicit), "journal")
