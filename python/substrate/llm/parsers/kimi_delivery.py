"""Use Kimi's native stream parser on the selected conversation's browser target."""
from python.kernel.errors import AppError
from python.substrate.llm.browser import cdp_ws
from python.substrate.llm.browser.page_origin import matches_saved_origin, route
from .kimi_parser import KimiChatMonitor, KimiParser


class KimiDelivery(KimiParser):
    def __init__(self, site, driver):
        self.site = site
        self.window = driver.current_window_handle

    def _require_window(self, driver):
        if driver.current_window_handle != self.window or not matches_saved_origin(self.site, driver.current_url):
            raise AppError('conflict', 'Вкладка Kimi изменилась. Откройте нужный чат в панели.')

    def switch_to_site_window(self, driver, prefer_url=None):
        self._require_window(driver)
        expected = route(self.site, prefer_url)
        if not expected or route(self.site, driver.current_url) != expected:
            raise AppError('conflict', 'Адрес выбранного чата Kimi не подтверждён.')

    def mirror_input(self, driver, text, prefer_url=None):
        # The native draft mirror treats window selection as best-effort.
        self.switch_to_site_window(driver, prefer_url)
        return super().mirror_input(driver, text, prefer_url=prefer_url)

    def _ensure_monitor(self, driver):
        self._require_window(driver)
        with KimiParser._monitor_lock:
            old = KimiParser._monitor
            target = (self.window, self.site['new_chat_url'])
            same = old is not None and getattr(old, 'target', None) == target
            if same and old._cdp.is_alive(): return old
            if old is not None:
                KimiParser._monitor = None
                old._cdp.close()
            ws = cdp_ws.find_page_ws_url_for_target(self.window)
            if not ws: raise AppError('unavailable', 'Вкладка Kimi недоступна для чтения ответа.')
            cdp = cdp_ws.CDPSession(ws)
            try:
                monitor = KimiChatMonitor(cdp)
                monitor.target = target
                if same:  # Reconnecting the same turn must not reset its counters.
                    monitor._assistant_message_count = old.assistant_message_count()
                    monitor._chat_request_count = old.chat_request_count()
                cdp.send_command('Network.enable')
            except Exception:
                cdp.close()
                raise
            KimiParser._monitor = monitor
            return monitor
