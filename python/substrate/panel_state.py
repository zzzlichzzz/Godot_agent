"""Plain external panel files; native serialization through exclusive staging."""
from contextlib import contextmanager
from io import StringIO
import os
from pathlib import Path
import stat
import tempfile
from python.kernel.errors import AppError

class ExternalPanelState:
    def __init__(self,profile,project):
        self.profile=Path(profile).absolute();self.project=Path(project).resolve()
        self.source=Path(__file__).parents[2].resolve()

    def check(self,path,*,directory=False):
        path=Path(path).absolute();actual=path.resolve()
        if not path.is_relative_to(self.profile) or not actual.is_relative_to(self.profile.resolve()) or any(actual.is_relative_to(root) for root in (self.project,self.source)):
            raise AppError('denied','Panel state must remain inside its external profile')
        for candidate in (path,*path.parents):
            try:info=candidate.lstat()
            except FileNotFoundError:continue
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                raise AppError('denied','Linked panel state is not allowed')
            if candidate==path and not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1):
                raise AppError('denied','Panel state must be an ordinary single-link file')
        return path

    def write_text(self,path,text):
        path=self.check(path);self.check(path.parent,directory=True)
        path.parent.mkdir(parents=True,exist_ok=True);self.check(path.parent,directory=True)
        parent=path.parent.stat();anchor=(parent.st_dev,parent.st_ino)
        descriptor,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
        temporary=Path(name);owned=os.fstat(descriptor);raw=text.encode('utf-8')
        try:
            with os.fdopen(descriptor,'wb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            self.check(path);self.check(temporary)
            current=path.parent.stat();proof=temporary.stat()
            if (current.st_dev,current.st_ino)!=anchor or (proof.st_dev,proof.st_ino)!=(owned.st_dev,owned.st_ino) or temporary.read_bytes()!=raw:
                raise AppError('conflict','Panel state changed during staging')
            os.replace(temporary,path)
        finally:
            try:
                proof=temporary.lstat()
                if stat.S_ISREG(proof.st_mode) and not getattr(proof,'st_file_attributes',0)&0x400 and proof.st_nlink==1 and (proof.st_dev,proof.st_ino)==(owned.st_dev,owned.st_ino) and temporary.read_bytes()==raw:
                    temporary.unlink()
            except FileNotFoundError:pass

    @contextmanager
    def native_output(self,module,path):
        expected=self.check(path);missing=object();previous=module.__dict__.get('open',missing)
        @contextmanager
        def opened(actual,mode,*,encoding):
            if Path(actual).absolute()!=expected or mode!='w' or encoding!='utf-8':
                raise AppError('denied','Unexpected native panel state output')
            self.check(expected)
            with StringIO() as buffer:
                yield buffer
                self.write_text(expected,buffer.getvalue())
        module.open=opened
        try:yield
        finally:
            if previous is missing:del module.open
            else:module.open=previous
