"""One owned loopback listener; never adopts or kills another process."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat as stat_mod
import uuid
import threading
from werkzeug import serving
from python.kernel.errors import AppError


def _pid_alive(pid):
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return True
    if os.name == 'nt':
        import ctypes
        from ctypes.wintypes import BOOL, DWORD, HANDLE

        if pid > 0xFFFFFFFF:
            return True  # Do not let ctypes truncate a malformed PID.
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.OpenProcess.argtypes = (DWORD, BOOL, DWORD)
        kernel32.OpenProcess.restype = HANDLE
        kernel32.WaitForSingleObject.argtypes = (HANDLE, DWORD)
        kernel32.WaitForSingleObject.restype = DWORD
        kernel32.CloseHandle.argtypes = (HANDLE,)
        kernel32.CloseHandle.restype = BOOL
        handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no such PID
        try:
            # WAIT_OBJECT_0 proves exit even if a parent still holds a handle or
            # the child returned 259 (also used for STILL_ACTIVE).
            return kernel32.WaitForSingleObject(handle, 0) != 0
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _archive_stale_endpoint(profile, endpoint):
    """Archive a verified plain-file dead-PID loopback endpoint without modifying live/foreign claims."""
    try:
        if endpoint.is_symlink():
            return False
        st = endpoint.stat(follow_symlinks=False)
        if getattr(st, 'st_file_attributes', 0) & 0x400:
            return False
        if not stat_mod.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size <= 0 or st.st_size > 4096:
            return False
        raw = endpoint.read_bytes()
        if len(raw) != st.st_size:
            return False
        old = json.loads(raw.decode('utf-8'))
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    if not isinstance(old, dict) or set(old) != {'host', 'port', 'pid', 'session_id'}:
        return False
    if old['host'] != '127.0.0.1':
        return False
    port, pid, sid = old['port'], old['pid'], old['session_id']
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        return False
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
        return False
    if not isinstance(sid, str) or not sid.strip() or _pid_alive(pid):
        return False
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for idx in range(100):
        suffix = '' if idx == 0 else f'-{idx}'
        target = profile / f'http_endpoint.stale-{pid}-{stamp}{suffix}.json'
        if target.exists():
            continue
        try:
            st2 = endpoint.stat(follow_symlinks=False)
            if (st2.st_dev, st2.st_ino) != (st.st_dev, st.st_ino) or endpoint.read_bytes() != raw:
                return False
            os.rename(endpoint, target)
            return True
        except FileExistsError:
            continue
        except OSError:
            return False
    return False


def serve(app,project_root,state_dir,port=0):
    if isinstance(port,bool) or not isinstance(port,int) or (port!=0 and not 1024<=port<=65535):
        raise AppError('invalid_input','HTTP port must be zero or 1024..65535')
    root=Path(project_root).resolve();profile=Path(state_dir).resolve()
    if profile==root or root in profile.parents:
        raise AppError('denied','HTTP state must be outside project')
    owner=uuid.uuid4().hex
    server=serving.make_server('127.0.0.1',port,app,threaded=True)
    record=dict(host='127.0.0.1',port=server.server_port,pid=os.getpid(),session_id=owner)
    expected=(json.dumps(record,sort_keys=True)+'\n').encode('utf-8')
    endpoint=profile/'http_endpoint.json';published=False;proof=None
    extensions=getattr(app,'extensions',{})
    shutdown=(lambda:threading.Thread(target=server.shutdown,daemon=True).start()) if hasattr(server,'shutdown') else None
    try:
        try:
            output=endpoint.open('x',encoding='utf-8',newline='\n')
        except FileExistsError:
            if not _archive_stale_endpoint(profile,endpoint):
                raise
            output=endpoint.open('x',encoding='utf-8',newline='\n')
        with output:
            stat=os.fstat(output.fileno());proof=(stat.st_dev,stat.st_ino)
            output.write(expected.decode('utf-8'));output.flush();os.fsync(output.fileno())
        published=True
        if shutdown is not None:extensions['godot_shutdown']=shutdown
        print(json.dumps(dict(ok=True,endpoint=record),sort_keys=True),flush=True)
        server.serve_forever()
    finally:
        if shutdown is not None and extensions.get('godot_shutdown') is shutdown:extensions.pop('godot_shutdown',None)
        try:
            server.server_close()
            if published and not endpoint.is_symlink():
                try:
                    stat=endpoint.stat(follow_symlinks=False)
                    if (stat.st_dev,stat.st_ino)==proof and endpoint.read_bytes()==expected:endpoint.unlink()
                except (OSError,ValueError):pass
        finally:
            session=getattr(app,'extensions',{}).get('godot_session')
            gateway=getattr(session,'gateway',None)
            if gateway is not None:gateway.close()
