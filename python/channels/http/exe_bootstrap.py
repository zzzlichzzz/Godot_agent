"""Thin channel entry over runtime-owned project/token IO."""
import os
import sys
from python.kernel.errors import AppError
from python.runtime.chrome_paths import configure_chrome_env
from python.runtime.exe_binding import MissingGodot,configuration,ensure_token,secrets,use_selected_editor


def _configuration(argv):
    try:
        return configuration(argv,sys.executable,os.environ)
    except MissingGodot as missing:
        if argv or not sys.stdin or not sys.stdin.isatty():raise
        print(missing.message, file=sys.stderr)
        try:
            value=input('Полный путь к Godot 4 (.exe), Enter для выхода: ')
            if not value.strip():raise missing
            use_selected_editor(sys.executable,value,os.environ)
        except (EOFError,KeyboardInterrupt,OSError,ValueError):raise missing from None
    return configuration(argv,sys.executable,os.environ)

def main(argv=None):
    try:
        project,state,port=_configuration(list(sys.argv[1:] if argv is None else argv))
        ensure_token(project,state)
        configure_chrome_env()
        from .app import serve
        serve(project,state,port)
    except MissingGodot as exc:
        print('HTTP startup refused:', exc.message, file=sys.stderr)
        return 2
    except (AppError,OSError,ValueError):
        print('HTTP startup refused: invalid deployment, external userdata or listener',file=sys.stderr)
        return 2
    return 0
