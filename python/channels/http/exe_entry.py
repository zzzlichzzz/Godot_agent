"""PyInstaller entry: use an absolute package import, never script-relative IO."""
from python.channels.http.exe_bootstrap import main

if __name__=='__main__':raise SystemExit(main())
