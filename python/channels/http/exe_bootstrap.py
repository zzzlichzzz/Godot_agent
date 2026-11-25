"""Thin channel entry over runtime-owned project/token IO."""
import os
import sys
from python.kernel.errors import AppError
from python.runtime.chrome_paths import configure_chrome_env
from python.runtime.exe_binding import configuration,ensure_token,secrets

def main(argv=None):
    try:
        project,state,port=configuration(list(sys.argv[1:] if argv is None else argv),sys.executable,os.environ)
        ensure_token(project,state)
        configure_chrome_env()
        from .app import serve
        serve(project,state,port)
    except (AppError,OSError,ValueError):
        print('HTTP startup refused: invalid deployment, external userdata or listener',file=sys.stderr)
        return 2
    return 0
