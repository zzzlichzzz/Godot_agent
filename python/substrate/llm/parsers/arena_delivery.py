"""Keep Arena's native branch protocol, evaluating only a Godot-read project view."""
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.keys import Keys

from python.kernel.errors import AppError
from python.substrate.llm.browser.page_origin import route
from .arena_composer import composer, draft_text, mirror_draft
from .arena_choices import ArenaChoices
from .parser_base import ParserCancelled


class ArenaDelivery(ArenaChoices):
    PASTE_PLAN_A = False

    def __init__(self, site, driver, url, judge=None, valid_read=None):
        super().__init__()
        self.judge, self.valid_read = judge, valid_read
        self.events, self._ranked = [], []
        self._frame = self._number = self._decision = self._before = None
        self.site, self.window, self.target = site, driver.current_window_handle, route(site, url)
        self._pasted_field = None
        self.draft_local = False
        self._stage = 'field'

    def switch_to_site_window(self, driver, prefer_url=None):
        if not self.target or driver.current_window_handle != self.window or route(self.site, driver.current_url) != self.target:
            raise AppError('conflict', 'Вкладка Arena изменилась. Откройте нужный чат в панели.')

    def find_input(self, driver):
        self.switch_to_site_window(driver)
        return composer(driver)

    def _read_input_text(self, driver, el):
        return draft_text(driver, el)

    def mirror_input(self, driver, text, prefer_url=None):
        field = self.find_input(driver)
        if field is None: return False  # A field that has not loaded yet is retryable.
        self.draft_local = True  # Never replay an unverified keyboard edit on a timer.
        return mirror_draft(self, driver, field, text)

    def send_message_and_get_response(self, driver, prompt, **kwargs):
        self.switch_to_site_window(driver)
        if self._ensure_monitor(driver) is None:
            raise AppError('unavailable', 'Arena: нет связи с вкладкой для чтения ответа. Сообщение не отправлено. Заново откройте чат из панели.')
        try:
            return super().send_message_and_get_response(driver, prompt, **dict(kwargs, input_retries=1))
        except (AppError, ParserCancelled): raise
        except Exception as error:
            # The pinned parser sometimes raises bare Exception containing page data.
            if type(error) is not Exception and not isinstance(error, (WebDriverException, TimeoutError)): raise
            message = {'field':'поле ввода недоступно. Откройте вкладку и проверьте, доступен ли чат.',
                       'prepare':'не удалось подтвердить текст в поле. Сообщение не отправлено.',
                       'submit':'отправка не подтверждена. Перед повтором проверьте чат на сайте.',
                       'read':'не удалось получить ответ. Проверьте последнее сообщение на сайте.'}[self._stage]
            raise AppError('unavailable', 'Arena: '+message) from None

    def insert_input_for_send(self, driver, el, prompt):
        self._stage = 'prepare'
        if not self._insert_text_matches(draft_text(driver, el), prompt):
            self._write_field(driver, el, prompt)
        self._pasted_field = driver, el
        return 'insert'

    def insert_input(self, driver, el, prompt):
        # The pinned parser may request a recovery write before submit. Stop instead.
        raise AppError('unavailable', 'Arena: текст в поле изменился. Повторная вставка отменена; сообщение не отправлено.')

    def _insert_text_matches(self, value, prompt):
        # The native pipeline's first post-insert check reads innerText directly.
        # Read logical paragraphs from that very field; later checks already use draft_text.
        field, self._pasted_field = self._pasted_field, None
        if field is not None:
            driver, el = field
            if el != self.find_input(driver): return False
            value = draft_text(driver, el)
        return super()._insert_text_matches(value, prompt)

    def _write_field(self, driver, el, prompt):
        if self.find_input(driver) != el:
            raise AppError('conflict', 'Поле ввода Arena изменилось.')
        el.click()
        el.send_keys(Keys.CONTROL, 'a')
        if not driver.execute_script('return document.activeElement === arguments[0]', el):
            raise AppError('conflict', 'Поле ввода Arena потеряло фокус.')
        driver.execute_cdp_cmd('Input.insertText', {'text':prompt})

    def submit(self, driver, el):
        if self._stage != 'prepare' or self.find_input(driver) != el:
            raise AppError('conflict', 'Arena: поле изменилось или отправка уже началась. Проверьте чат на сайте.')
        self._stage = 'submit'
        return super().submit(driver, el)

    def confirm_sent(self, driver, el):
        if not super().confirm_sent(driver, el):
            raise AppError('unavailable', 'Arena не подтвердила отправку. Перед повтором проверьте чат на сайте.')
        self._stage = 'read'
        return True
