"""Fail-closed project-bound HTTP authentication, ahead of native routes."""
import hmac
from pathlib import Path
from flask import jsonify, request
from python.kernel.errors import AppError

class ProjectAuth:
    def __init__(self, project_root, user_data_dir):
        self.project=Path(project_root).resolve();self.user_data=Path(user_data_dir).resolve()
        source=Path(__file__).resolve().parents[3]
        if any(self.user_data==root or root in self.user_data.parents for root in (self.project,source)):
            raise AppError('denied','HTTP user data must be outside project/source')
        path=self.user_data/'godot_agent_token.txt'
        if path.is_symlink() or (path.exists() and path.resolve().parent!=self.user_data):
            raise AppError('denied','HTTP token must not follow a link')
        try: expected=path.read_text('utf-8').strip()
        except OSError as error: raise AppError('denied','Project token is missing') from error
        if not expected or len(expected)>4096: raise AppError('denied','Project token is missing or invalid')
        self._expected=expected.encode('utf-8')

    def install(self, app):
        app.config['MAX_CONTENT_LENGTH']=1_000_000
        @app.before_request
        def authenticate():
            host=request.environ.get('HTTP_HOST','').lower()
            name,separator,port=host.partition(':')
            if name not in ('127.0.0.1','localhost') or (separator and
                    (len(port)>5 or not port.isascii() or not port.isdigit() or not 1<=int(port)<=65535)):
                return jsonify(ok=False,kind='denied',error='Loopback Host required'),403
            origin=request.headers.get('Origin')
            if origin is not None and origin!='http://'+host:
                return jsonify(ok=False,kind='denied',error='Same-origin request required'),403
            if request.path=='/health': return None
            value=request.headers.get('X-Agent-Token','').encode('utf-8')
            if not hmac.compare_digest(value,self._expected):
                return jsonify(ok=False,kind='denied',error='Project authentication failed'),403
            if request.method=='POST':
                body=request.get_json(silent=True)
                if not isinstance(body,dict): return jsonify(ok=False,kind='invalid_input',error='JSON object required'),400
                udd=body.get('user_data_dir')
                if udd is not None and Path(str(udd)).resolve()!=self.user_data:
                    return jsonify(ok=False,kind='denied',error='Server belongs to another project'),409
                root=body.get('project_root')
                if root is not None and Path(str(root)).resolve()!=self.project:
                    return jsonify(ok=False,kind='denied',error='Server belongs to another project'),409
            return None
        @app.errorhandler(413)
        def too_large(_error):
            return jsonify(ok=False,kind='invalid_input',error='Request body exceeds limit'),413
