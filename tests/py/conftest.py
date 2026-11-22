# tests/py/conftest.py - общие фикстуры pytest.
# TODO: пути к корпусу, временный проект, запуск моста.

import importlib
import json
from pathlib import Path
import queue
import threading
from types import SimpleNamespace

import pytest


@pytest.fixture
def b1_socket():
    """Memory socket; the browser transport never reaches a real network."""
    class BufferSocket:
        def __init__(self, data, chunk_size=None):
            self.data, self.chunk_size = data, chunk_size
            self.sent, self.timeouts = [], []
            self.closed = False

        def recv(self, size):
            size = min(size, self.chunk_size or size)
            result, self.data = self.data[:size], self.data[size:]
            return result

        def sendall(self, data):
            self.sent.append(data)

        def settimeout(self, value):
            self.timeouts.append(value)

        def close(self):
            self.closed = True

    return BufferSocket


@pytest.fixture
def b1_session(monkeypatch):
    """Real CDPSession reader with a queue-backed, inert WebSocket."""
    sessions = []

    def factory(result=None, error=None, auto_reply=True):
        module = importlib.import_module('python.substrate.llm.browser.cdp_ws')

        class Pipe:
            def __init__(self):
                self.incoming, self.sent = queue.Queue(), []
                self.sent_event = threading.Event()
                self.closed = False

            def recv_message(self):
                return self.incoming.get()

            def send_text(self, text):
                payload = json.loads(text)
                self.sent.append(payload)
                self.sent_event.set()
                if auto_reply:
                    answer = {'id': payload['id'], 'result': result}
                    if error is not None:
                        answer['error'] = error
                    self.incoming.put(json.dumps(answer).encode('utf-8'))

            def close(self):
                self.closed = True
                self.incoming.put(None)

        pipe = Pipe()
        monkeypatch.setattr(module, 'MiniWebSocket', lambda *args, **kwargs: pipe)
        session = module.CDPSession('ws://127.0.0.1:9222/fixture')
        sessions.append(session)
        return SimpleNamespace(module=module, session=session, pipe=pipe)

    yield factory
    for session in sessions:
        session.close()
        session._reader.join(timeout=1)
        assert not session._reader.is_alive()


@pytest.fixture
def b1_browser_env(monkeypatch, tmp_path):
    """Lazy import keeps missing-facade red pins as test failures, not collection errors."""
    def factory(busy=False, ready=True, owner=True, attach_error=False, quit_error=False):
        module = importlib.import_module('python.substrate.llm.browser.facade')
        local = tmp_path / 'fake-local'
        local.mkdir()
        monkeypatch.setenv('LOCALAPPDATA', str(local))
        env = SimpleNamespace(module=module, local=local, calls=[], launch_args=None,
                              launch_kwargs=None, services=[], driver=None, cdp=None,
                              fail_method=None, navigate_error=None, close_success=True, options=None, http_closed=False)

        class Process:
            pid = 321
            returncode = None

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                env.calls.append(('process.wait', timeout))
                if self.returncode is None:
                    raise module.subprocess.TimeoutExpired('fake-chrome', timeout)
                return self.returncode

            def terminate(self):
                env.calls.append(('process.terminate', self.pid))
                self.returncode = 1

        env.process = Process()

        def popen(args, **kwargs):
            env.calls.append(('Popen',))
            env.launch_args, env.launch_kwargs = args, kwargs
            return env.process

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        def connect(*args, **kwargs):
            env.calls.append(('port-check', args, kwargs))
            if not busy:
                raise ConnectionRefusedError('fake unused port')
            return Connection()

        class Probe(Connection):
            def setsockopt(self, *args):
                env.calls.append(('probe.option', args))

            def bind(self, address):
                env.calls.append(('probe.bind', address))
                if busy:
                    raise OSError('fake occupied port')

            def __exit__(self, *args):
                env.calls.append(('probe.close',))

        class Response(Connection):
            def read(self):
                return b'{"webSocketDebuggerUrl":"ws://127.0.0.1:9222/owned-browser"}'

            def __exit__(self, *args):
                env.http_closed = True

        class Opener:
            def open(self, url, timeout=None):
                env.calls.append(('http.open', url, timeout))
                return Response()

        def opener(handler):
            env.calls.append(('proxy', handler.proxies))
            return Opener()

        class CDP:
            def __init__(self, *args, **kwargs):
                env.cdp = self
                self.calls, self.closed, self.count = [], False, 0

            def send_command(self, method, params=None, timeout=15, session_id=None):
                self.calls.append((method, params or {}, session_id))
                if method == env.fail_method:
                    raise RuntimeError('injected ' + method)
                if method == 'SystemInfo.getProcessInfo':
                    return {'processInfo': [{'type': 'browser', 'id': 321 if owner else 999}]}
                if method == 'Target.createTarget':
                    self.count += 1
                    return {'targetId': 'own-' + str(self.count)}
                if method == 'Target.attachToTarget':
                    return {'sessionId': 'session-' + params['targetId']}
                if method == 'Target.closeTarget':
                    return {'success': env.close_success}
                if method == 'Page.navigate':
                    return {'errorText': env.navigate_error} if env.navigate_error else {}
                if method == 'Runtime.evaluate':
                    return {'result': {'value': {'title': session_id, 'text': session_id}}}
                if method == 'Browser.close':
                    env.process.returncode = 0
                return {}

            def close(self):
                self.closed = True

        class Service:
            def __init__(self, **kwargs):
                self.kwargs, self.stopped = kwargs, False
                env.services.append(self)

            def stop(self):
                self.stopped = True

        class Driver:
            def __init__(self, options, service):
                env.options = options
                if attach_error:
                    raise RuntimeError('injected attach failure')
                env.driver = self
                self.quit_called = False

            def quit(self):
                self.quit_called = True
                if quit_error:
                    raise RuntimeError('injected quit failure')

        # Resolve Selenium's lazy Chrome import before replacing the stdlib socket class.
        monkeypatch.setattr(module.webdriver, 'Chrome', Driver)
        monkeypatch.setattr(module.subprocess, 'Popen', popen)
        monkeypatch.setattr(module.socket, 'create_connection', connect)
        monkeypatch.setattr(module.socket, 'socket', lambda *args, **kwargs: Probe())
        monkeypatch.setattr(module.urllib.request, 'build_opener', opener)
        monkeypatch.setattr(module, '_wait_for_debug_port', lambda *args, **kwargs: ready)
        monkeypatch.setattr(module, 'CDPSession', CDP)
        monkeypatch.setattr(module, 'ChromeService', Service)
        return env

    return factory
