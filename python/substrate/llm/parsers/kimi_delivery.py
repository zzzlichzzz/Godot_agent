"""Use Kimi's native stream parser on the selected conversation's browser target."""
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from python.kernel.errors import AppError
from python.substrate.llm.browser import cdp_ws
from python.substrate.llm.browser.page_origin import matches_saved_origin, route
from .kimi_parser import KimiChatMonitor, KimiParser


class KimiDelivery(KimiParser):
    def __init__(self, site, driver, *, request=''):
        self.site = site
        self.window = driver.current_window_handle
        self.start_url = driver.current_url
        # The attachment already contains the complete request and first-turn context.
        self.caption = request if len(request) <= 256 and request.splitlines() == [request] else ''

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

    def insert_input_for_send(self, driver, el, prompt):
        # A single paste on the selected page; never copy a prompt to the system clipboard.
        self.switch_to_site_window(driver, self.start_url)
        if el != self.find_input(driver) or self.count_composer_attachments(driver) != 0:
            raise AppError('conflict', 'Проверьте поле Kimi: в нём уже есть вложение или оно недоступно.')
        self.insert_input(driver, el, '')
        driver.execute_script('''
          const [el, text] = arguments, dt = new DataTransfer(); dt.setData('text/plain', text);
          if (document.activeElement !== el) return;
          if (el.dispatchEvent(new ClipboardEvent('paste', {bubbles:true, cancelable:true, clipboardData:dt})) && document.activeElement === el)
            document.execCommand('insertText', false, text);
        ''', el, prompt)
        def inserted(d):
            self.switch_to_site_window(d, self.start_url)
            self._insert_became_attachment = self.count_composer_attachments(d) == 1
            return self._insert_became_attachment or self._insert_text_matches(self._read_input_text(d, el), prompt)
        try:
            WebDriverWait(driver, 10, poll_frequency=.2).until(inserted)
        except TimeoutException:
            raise AppError('unavailable', 'Kimi не показал текст или вложение. Проверьте вход в аккаунт и поле сообщения.') from None
        return 'paste'

    def _type_attachment_note(self, driver, el):
        self.SEND_RETRIES = 0  # A slow file submission must never send the attachment twice.
        self.switch_to_site_window(driver, self.start_url)
        el = self.find_input(driver)
        if not el or self.count_composer_attachments(driver) != 1:
            raise AppError('conflict', 'Вложение Kimi не подтверждено. Проверьте поле сообщения.')
        if not self._insert_text_matches(self._read_input_text(driver, el), self.caption):
            # Replace only the editable text, leaving the separate file card in place.
            self.insert_input(driver, el, self.caption)

    def submit(self, driver, el):
        self.switch_to_site_window(driver, self.start_url)
        if getattr(self, '_insert_became_attachment', False):
            el = self.find_input(driver)
            if (not el or self.count_composer_attachments(driver) != 1 or
                    not self._insert_text_matches(self._read_input_text(driver, el), self.caption)):
                raise AppError('conflict', 'Вложение или текст Kimi изменились. Проверьте поле сообщения.')
        elif self.count_composer_attachments(driver) != 0:
            raise AppError('conflict', 'Перед отправкой появилось другое вложение Kimi.')
        return super().submit(driver, el)

    def confirm_sent(self, driver, el):
        if not self._insert_became_attachment: return super().confirm_sent(driver, el)
        # An empty text field alone cannot confirm an attachment-only send.
        def accepted(d):
            self._require_window(d)
            before = self._req_count_before_send
            mon = KimiParser._monitor
            if before is not None and mon is not None and mon.chat_request_count() > before: return True
            if route(self.site, d.current_url) != route(self.site, self.start_url): return False
            field = self.find_input(d)
            return field is not None and self.count_composer_attachments(d) == 0 and not self._input_leftover(d, field)
        try: return WebDriverWait(driver, 5).until(accepted)
        except TimeoutException: return False

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
