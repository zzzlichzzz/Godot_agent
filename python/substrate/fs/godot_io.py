"""Project-bound FileAccess/DirAccess sessions; no sockets or project initialization."""
import atexit
from base64 import b64decode
from collections import OrderedDict
import errno
import os
from pathlib import Path
from queue import Empty
import shutil
import stat
from threading import RLock

from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import normalize_rel

from python.substrate.engine.file_session import Session
_sessions = OrderedDict()
_lock = RLock()
MAX_BYTES = 64 * 1024 * 1024


class MissingGodot(AppError):
    def __init__(self):
        super().__init__('unavailable', 'Не найден Godot. Запустите сервер из панели Godot или укажите путь к редактору в GODOT_AGENT_GODOT_BIN.')


def engine():
    binary = os.environ.get('GODOT_AGENT_GODOT_BIN') or shutil.which('godot4') or shutil.which('godot')
    if not binary or not os.path.isabs(binary) or not os.path.isfile(binary):
        raise MissingGodot()
    return binary


def request(root, op, rel='', **fields):
    if rel and (normalize_rel(rel) != rel or ':' in rel): raise PermissionError(errno.EACCES,'неверный путь')
    key = (engine(),root)
    with _lock:
        if key not in _sessions:
            if len(_sessions) >= 3: _sessions.popitem(last=False)[1].close()
            _sessions[key] = Session(*key)
        _sessions.move_to_end(key)
        try: result = _sessions[key].request(dict(op=op,rel=rel,**fields))
        except (OSError, ValueError, Empty, EOFError):
            _sessions.pop(key).close()
            raise AppError('unavailable','Godot не подтвердил файловую операцию.') from None
    if 'errno' in result: raise OSError(result['errno'],os.strerror(result['errno']),rel)
    return result['value']


@atexit.register
def close_sessions():
    with _lock:
        while _sessions: _sessions.popitem()[1].close()


class GodotFiles:
    def __init__(self, root, max_bytes=READ_TEXT_MAX_BYTES):
        self.project_root = os.path.abspath(root); self.max_bytes = min(MAX_BYTES,max_bytes)

    def _op(self, op, rel='', **fields):
        # OS-level reparse checks supplement DirAccess.is_link (not all Windows reparse tags are links).
        path = Path(self.project_root)
        if rel and (normalize_rel(rel) != rel or ':' in rel): raise PermissionError(errno.EACCES,'неверный путь')
        for part in ('', *rel.split('/')):
            if getattr(os.path,'isreserved',lambda _:False)(part): raise PermissionError(errno.EACCES,'reserved project path')
            path = path / part
            try: info = path.lstat()
            except FileNotFoundError: break
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)) or getattr(info,'st_file_attributes',0) & 0x400:
                raise PermissionError(errno.EACCES,'linked project path')
        return request(self.project_root,op,rel,**fields)

    def read_raw(self, rel): return b64decode(self._op('read',rel,limit=self.max_bytes), validate=True)
    def read_text(self, rel): return self.read_raw(rel).decode('utf-8-sig','replace').replace('\r\n','\n').replace('\r','\n')
    def exists(self, rel): return bool(self._op('stat',rel))
    def is_file(self, rel): return self._op('stat',rel)=='file'
    def is_dir(self, rel): return self._op('stat',rel)=='dir'

    def list_entries_bounded(self, subdir, accept, max_scanned):
        rows=[]; remaining=max_scanned; stack=[subdir]
        while stack:
            rel=stack.pop(); entries,seen,cut=self._op('list',rel,limit=remaining if remaining is not None else -1)
            if cut: return sorted(rows,key=lambda r:r['path']),True
            if remaining is not None: remaining-=seen
            sub=[]
            for name,isdir in sorted(entries):
                path=rel+'/'+name if rel else name
                row=dict(path=path,type='dir' if isdir else 'file')
                if not accept or accept(row):
                    rows.append(row)
                    if isdir: sub.append(path)
            stack.extend(reversed(sub))
        return sorted(rows,key=lambda r:r['path']),False

    def list_entries(self, subdir='', accept=None): return self.list_entries_bounded(subdir,accept,None)[0]
    def list_files(self): return [r['path'] for r in self.list_entries() if r['type']=='file']
