"""Launch only the packaged FileAccess primitive, in an empty project."""
import json
from pathlib import Path
from queue import Queue
import shutil
import struct
import subprocess
import tempfile
from threading import Thread
from python.kernel.errors import AppError

SCRIPT = Path(__file__).resolve().parents[3] / 'editor/core/project_file_io.gd'


class Session:
    def __init__(self, binary, root):
        base = self.temp = Path(tempfile.mkdtemp(prefix='godot-agent-io-'))
        try:
            (base/'project.godot').write_text('config_version=5\n[application]\nconfig/name="GodotAgentFileIO"\n','utf-8')
            self.proc = subprocess.Popen([binary,'--headless','--no-header','--path',str(base),'--script',str(SCRIPT),'--',root],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=base,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError:
            shutil.rmtree(base)
            raise AppError('unavailable','Не удалось запустить Godot для работы с файлами.') from None
        self.responses = Queue()
        Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        try:
            for line in self.proc.stdout:
                if line.startswith(b'GDIO:'): self.responses.put(line[5:])
        finally: self.responses.put(None)

    def close(self):
        try: self.proc.stdin.close()
        except OSError: pass
        try: self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait()
        self.proc.stdout.close(); shutil.rmtree(self.temp)

    def request(self, packet):
        data = json.dumps(packet, ensure_ascii=True, separators=(',',':')).encode('ascii')
        self.proc.stdin.write(struct.pack('<I',len(data)) + data); self.proc.stdin.flush()
        raw = self.responses.get(timeout=30)
        if raw is None: raise EOFError
        return json.loads(raw)
