"""Transport failures of the current Qwen completion, on the exact composer tab."""
import re
from threading import Lock
from urllib.parse import urlsplit

from .cdp_ws import CDPSession, find_page_ws_url_for_target


class QwenRequestWatch:
    def __init__(self, cdp):
        self.cdp = cdp
        self.lock = Lock()
        self.current = self.failure = None
        cdp.on_event('Network.requestWillBeSent', self.request)
        cdp.on_event('Network.responseReceived', self.response)
        cdp.on_event('Network.loadingFailed', self.failed)

    def request(self, event):
        req = event.get('request', {})
        url = urlsplit(req.get('url', ''))
        if (req.get('method') == 'POST' and url.scheme == 'https' and url.netloc in ('chat.qwen.ai','chat.qwen.ai:443')
                and url.path.rstrip('/') == '/api/v2/chat/completions'):
            with self.lock:
                if self.current is None: self.current = event['requestId']

    def response(self, event):
        status = event['response']['status']
        if 400 <= status <= 599:
            self.mark(event, 'HTTP %d' % status)

    def failed(self, event):
        code = event.get('errorText', '')
        self.mark(event, code if re.fullmatch(r'net::ERR_[A-Z0-9_]{1,60}', code) else 'network error')

    def mark(self, event, failure):
        with self.lock:
            if self.current and event['requestId'] == self.current:
                self.failure = failure

    @classmethod
    def attach(cls, driver):
        if urlsplit(driver.current_url).hostname != 'chat.qwen.ai': return None
        cdp = None
        try:
            addr = driver.capabilities['goog:chromeOptions']['debuggerAddress']
            host, port = addr.rsplit(':', 1)
            if host not in ('localhost', '127.0.0.1'): return None
            url = find_page_ws_url_for_target(driver.current_window_handle, host, int(port), timeout=1)
            if not url: return None
            cdp = CDPSession(url); watch = cls(cdp)
            cdp.send_command('Network.enable', timeout=2)
            return watch
        except Exception:
            if cdp: cdp.close()
            return None  # DOM notices remain available without a monitor.
