# -*- coding: utf-8 -*-
"""v80: дашборд сервера.

- install() зеркалит stdout/stderr в кольцевой журнал (консоль работает как раньше).
- DASHBOARD_HTML — страница http://127.0.0.1:5000/dashboard: секторы со статистикой
  (сервер / план / мини-лич / события) и полный копируемый журнал внизу.
- Данные страница берёт с /dashboard/data (маршрут в main.py).
"""
import collections
import sys
import threading
import time

STARTED = time.time()
MAX_LINES = 600
_lines = collections.deque(maxlen=MAX_LINES)
_lock = threading.Lock()


class _Tee(object):
    """Обёртка над stdout/stderr: пишет в консоль КАК РАНЬШЕ и копит строки в журнал."""

    def __init__(self, orig):
        self._orig = orig
        self._part = ""

    def write(self, s):
        try:
            self._orig.write(s)
        except Exception:
            pass
        try:
            self._part += s
            while "\n" in self._part:
                line, self._part = self._part.split("\n", 1)
                line = line.rstrip("\r")
                if line.strip():
                    with _lock:
                        _lines.append("%s %s" % (time.strftime("%H:%M:%S"), line))
        except Exception:
            pass

    def flush(self):
        try:
            self._orig.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._orig, name)


def install():
    if not isinstance(sys.stdout, _Tee):
        sys.stdout = _Tee(sys.stdout)
    if not isinstance(sys.stderr, _Tee):
        sys.stderr = _Tee(sys.stderr)


def get_lines(limit=None):
    with _lock:
        items = list(_lines)
    if limit:
        items = items[-int(limit):]
    return items


def uptime_text():
    sec = int(time.time() - STARTED)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return "%d:%02d:%02d" % (h, m, s)


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Godot AI Agent — сервер</title>
<style>
body{margin:0;background:#0d1117;color:#c9d1d9;font:14px/1.45 "Segoe UI",Arial,sans-serif}
header{padding:14px 20px;background:#161b22;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center}
header h1{margin:0;font-size:16px;color:#58a6ff}
#uptime{color:#8b949e;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px;padding:14px 20px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 14px}
.card h2{margin:0 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#8b949e;border-bottom:1px solid #21262d;padding-bottom:6px}
.row{display:flex;justify-content:space-between;gap:10px;padding:2px 0}
.row .k{color:#8b949e}
.row .v{color:#e6edf3;text-align:right;word-break:break-all}
.ok{color:#3fb950}.warn{color:#d29922}.off{color:#8b949e}
.events{font:12px/1.5 Consolas,monospace;white-space:pre-wrap;word-break:break-all;max-height:220px;overflow-y:auto;color:#9ea7b3}
.logwrap{padding:0 20px 20px}
.logwrap h2{font-size:13px;color:#8b949e;text-transform:uppercase;letter-spacing:.06em}
textarea#rawlog{width:100%;height:260px;box-sizing:border-box;background:#0a0d12;color:#b7c1cc;border:1px solid #30363d;border-radius:8px;padding:10px;font:12px/1.5 Consolas,monospace;resize:vertical}
button{background:#238636;color:#fff;border:0;border-radius:6px;padding:7px 14px;cursor:pointer;margin:8px 0}
button:hover{background:#2ea043}
</style>
</head>
<body>
<header><h1>Godot AI Agent — сервер</h1><div id="uptime">аптайм —</div></header>
<div class="grid">
 <div class="card"><h2>Сервер</h2><div id="srv">…</div></div>
 <div class="card"><h2>План и действия</h2><div id="plan">…</div></div>
 <div class="card"><h2>Мини-лич (обучение)</h2><div id="ml">…</div></div>
 <div class="card"><h2>Последние события</h2><div id="events" class="events">…</div></div>
</div>
<div class="logwrap">
 <h2>Полный журнал (удобно копировать)</h2>
 <button onclick="copyLog()">Скопировать журнал</button>
 <textarea id="rawlog" readonly></textarea>
</div>
<script>
function row(k,v,cls){return '<div class="row"><span class="k">'+k+'</span><span class="v '+(cls||'')+'">'+v+'</span></div>';}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}
function fmtBytes(b){b=b||0;if(b>1048576)return (b/1048576).toFixed(1)+' МБ';if(b>1024)return (b/1024).toFixed(1)+' КБ';return b+' Б';}
async function tick(){
 try{
  const r = await fetch('/dashboard/data'); const d = await r.json();
  document.getElementById('uptime').textContent = 'аптайм ' + d.uptime;
  document.getElementById('srv').innerHTML =
    row('Проект', esc(d.project_root)||'<span class="off">не синхронизирован</span>') +
    row('Ожидает подтверждения', d.pending_action?'да':'нет', d.pending_action?'warn':'off');
  const p = d.plan||{};
  document.getElementById('plan').innerHTML =
    row('План', p.active?('выполняется — шаг '+p.index+' из '+p.total):'нет активного плана', p.active?'ok':'off');
  const m = d.minilich||{};
  let ml = row('Включён', m.enabled?'да':'нет', m.enabled?'ok':'off') +
    row('Обучение идёт', m.training_active?'да':'нет', m.training_active?'ok':'off') +
    row('Примеров в датасете', esc(m.examples)) +
    row('Шаг обучения', esc(m.train_step)) +
    row('Последний loss', m.last_loss==null?'—':esc(m.last_loss)) +
    row('Мозг на диске', fmtBytes(m.disk_bytes));
  if (m.error) ml += row('Ошибка', esc(m.error), 'warn');
  if (m.lines && m.lines.length) ml += '<div class="events" style="margin-top:6px;max-height:120px">'+esc(m.lines.slice(-6).join('\n'))+'</div>';
  document.getElementById('ml').innerHTML = ml;
  const ev = (d.log||[]).slice(-14).join('\n');
  document.getElementById('events').textContent = ev || 'пока пусто';
  const ta = document.getElementById('rawlog');
  const stick = ta.scrollTop + ta.clientHeight >= ta.scrollHeight - 8;
  ta.value = (d.log||[]).join('\n');
  if (stick) ta.scrollTop = ta.scrollHeight;
 }catch(e){ document.getElementById('events').textContent = 'нет связи с сервером: '+e; }
}
function copyLog(){
 const ta = document.getElementById('rawlog');
 ta.select(); ta.setSelectionRange(0, ta.value.length);
 try{ document.execCommand('copy'); }catch(e){}
 if (navigator.clipboard) navigator.clipboard.writeText(ta.value).catch(function(){});
}
tick(); setInterval(tick, 3000);
</script>
</body>
</html>
"""
