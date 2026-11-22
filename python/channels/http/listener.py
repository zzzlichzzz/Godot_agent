"""One owned loopback listener; never adopts or kills another process."""
import json
import os
from pathlib import Path
import uuid
from werkzeug import serving
from python.kernel.errors import AppError

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
    try:
        with endpoint.open('x',encoding='utf-8',newline='\n') as output:
            stat=os.fstat(output.fileno());proof=(stat.st_dev,stat.st_ino)
            output.write(expected.decode('utf-8'));output.flush();os.fsync(output.fileno())
        published=True
        print(json.dumps(dict(ok=True,endpoint=record),sort_keys=True),flush=True)
        server.serve_forever()
    finally:
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
