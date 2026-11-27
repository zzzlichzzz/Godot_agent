"""D24 read-only glue; native launch/spoof functions are deliberately not called."""
import json
import os
import re
import socket
import subprocess
import urllib.request
from contextlib import suppress
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from .browser_manager import _wait_for_debug_port
from .cdp_ws import CDPSession

class ReadOnlyBrowser:
    def __init__(self, chrome_path, driver_path=None, *, live_profile=None):
        self._process = self._driver = self._service = self._cdp = None
        self._owned, self._tabs = False, {}
        root = Path(os.environ['LOCALAPPDATA']).resolve()
        profile = root / 'Godot_AI_Profile' if live_profile is None else Path(live_profile).resolve()
        if live_profile is not None:
            if (profile.parent != root or not re.fullmatch(r'Godot_AI_Profile_B1_[0-9a-f]{32}', profile.name)
                    or not profile.is_dir() or any(profile.iterdir())):
                raise ValueError('live profile must be a new empty dedicated sibling')
        try:
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                probe.bind(('127.0.0.1', 9222))
        except OSError as error: raise RuntimeError('9222 availability unknown; refusing launch') from error
        args = [chrome_path, '--remote-debugging-port=9222', f'--user-data-dir={profile}',
                '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
                '--disable-background-timer-throttling', '--disable-features=CalculateNativeWinOcclusion']
        args += (['--no-first-run'] if live_profile is not None else []) + ['about:blank']
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 7  # WinUser.h SW_SHOWMINNOACTIVE (not exported by subprocess).
        try:
            self._process = subprocess.Popen(args, startupinfo=info, close_fds=True)
            if not _wait_for_debug_port(9222, timeout=20):
                raise RuntimeError('own Chrome debugger did not become ready')
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open('http://127.0.0.1:9222/json/version', timeout=5) as response:
                self._cdp = CDPSession(json.loads(response.read())['webSocketDebuggerUrl'])
            processes = self._cdp.send_command('SystemInfo.getProcessInfo')['processInfo']
            if not any(item['type'] == 'browser' and int(item['id']) == self._process.pid for item in processes):
                raise RuntimeError('debugger owner does not match own process')
            self._owned = True
            options = webdriver.ChromeOptions()
            options.binary_location = str(chrome_path)
            options.add_experimental_option('debuggerAddress', '127.0.0.1:9222')
            self._service = ChromeService(executable_path=driver_path, popen_kw={'close_fds': True})
            self._driver = webdriver.Chrome(options=options, service=self._service)
        except Exception:
            self.close()
            raise

    def open(self, uri):
        if not uri.startswith('file:///'): raise ValueError('only local file URLs are allowed')
        target = self._cdp.send_command('Target.createTarget', {'url': 'about:blank', 'newWindow': False, 'background': True})['targetId']
        self._tabs[target] = None
        try:
            session = self._cdp.send_command('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
            self._tabs[target] = session
            self._cdp.send_command('Page.enable', session_id=session)
            if error := self._cdp.send_command('Page.navigate', {'url': uri}, session_id=session).get('errorText'):
                raise RuntimeError(error)
        except Exception:
            self.close_tab(target)
            raise
        return target

    def read(self, target):
        if target not in self._tabs: raise ValueError('foreign target')
        return self._cdp.send_command('Runtime.evaluate', {
            'expression': '({title:document.title,text:document.body.textContent})', 'returnByValue': True,
        }, session_id=self._tabs[target])['result']['value']

    def close_tab(self, target):
        if target not in self._tabs: raise ValueError('foreign target')
        if not self._cdp.send_command('Target.closeTarget', {'targetId': target}).get('success'):
            raise RuntimeError('own target close refused')
        self._tabs.pop(target)

    def close(self):
        for obj, method in [(self._driver, 'quit'), (self._service, 'stop')]:
            with suppress(Exception): getattr(obj, method)()
        if self._cdp and self._owned:
            with suppress(Exception): self._cdp.send_command('Browser.close', timeout=2)
        with suppress(Exception): self._cdp.close()
        if self._process and self._process.poll() is None:
            try: self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                self._process.wait(timeout=5)
        self._driver = self._service = self._cdp = None
        self._tabs.clear()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
