"""Godot owns file contents. The OS supplies WAL durability and atomic publication."""
from base64 import b64encode
import errno
import os
import tempfile
from .atomic_write import AtomicFileWriter
from .godot_io import GodotFiles, MAX_BYTES


class GodotWriter(AtomicFileWriter):
    def __init__(self, root):
        super().__init__(root); self.files=GodotFiles(root,MAX_BYTES)

    def read_raw(self,rel): return self.files.read_raw(rel)
    def exists(self,rel): return self.files.exists(rel)
    def is_file(self,rel): return self.files.is_file(rel)
    def is_dir(self,rel): return self.files.is_dir(rel)

    def mkdir(self, rel):
        self.files._op('mkdir',rel); self._fsync_dir(os.path.dirname(self._resolve(rel)))
        return self.directory_identity(rel)

    def remove_empty_directory(self, rel, proof):
        if self.directory_identity(rel)!=proof: raise PermissionError(errno.EACCES,'directory replaced')
        self.files._op('remove',rel); self._fsync_dir(os.path.dirname(self._resolve(rel)))

    def delete(self, rel):
        if self.is_dir(rel): raise IsADirectoryError(errno.EISDIR,'not a file')
        self.files._op('remove',rel); self._fsync_dir(os.path.dirname(self._resolve(rel)))

    def move(self,src,dest):
        if not self.is_file(src): raise FileNotFoundError(errno.ENOENT,'source missing')
        if self.exists(dest) and not (src!=dest and src.casefold()==dest.casefold() and self.same_file(src,dest)):
            raise FileExistsError(errno.EEXIST,'destination exists')
        parts=dest.split('/')[:-1]
        for i in range(1,len(parts)+1):
            directory='/'.join(parts[:i])
            if not self.is_dir(directory): self.mkdir(directory)
        path=self._resolve(dest); self.files._op('rename',src,dest=dest)
        for parent in (os.path.dirname(self._resolve(src)),os.path.dirname(path)): self._fsync_dir(parent)
        return path

    def rename_dir_case(self,src,dest):
        if src==dest or src.casefold()!=dest.casefold() or not self.same_directory(src,dest): raise ValueError('not same directory')
        a,b=src.split('/'),dest.split('/')
        for n in range(len(a)-1,-1,-1):
            if a[n]!=b[n]:
                self.files._op('rename','/'.join(a[:n+1]),dest='/'.join(a[:n]+[b[n]]))
                self._fsync_dir(os.path.dirname(self._resolve('/'.join(a[:n+1]))))
        return self._resolve(dest)

    def create(self,rel,data): return self._publish(rel,data,True)
    def write_raw(self,rel,data): return self._publish(rel,data,False)

    def _publish(self,rel,data,exclusive):
        if len(data)>MAX_BYTES: raise OSError(errno.EFBIG,'file too large')
        self.files.exists(rel); path=self._resolve(rel); parent=os.path.dirname(path)
        fd,temp=tempfile.mkstemp(prefix='.agent-stage-',dir=parent); os.close(fd)
        try:
            staged=os.path.relpath(temp,self.project_root).replace(os.sep,'/')
            if not self.files._op('stage',staged,data=b64encode(data).decode('ascii')): raise OSError(errno.EIO,'short write')
            with open(temp,'rb+') as f: os.fsync(f.fileno())
            if exclusive: os.link(temp,path)
            else: os.replace(temp,path)
        finally:
            if os.path.exists(temp): os.remove(temp)
        self._fsync_dir(parent); return path
