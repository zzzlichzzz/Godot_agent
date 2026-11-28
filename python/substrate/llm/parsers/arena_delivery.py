"""Keep Arena's native branch protocol, evaluating only a Godot-read project view."""
import time
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
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
        self._inline_check = self._expected = None
        self.draft_local = False
        self._stage = 'field'

    def switch_to_site_window(self, driver, prefer_url=None):
        if not self.target or driver.current_window_handle != self.window or route(self.site, driver.current_url) != self.target:
            raise AppError('conflict', 'Вкладка Arena изменилась. Откройте нужный чат в панели.')

    def find_input(self, driver):
        self.switch_to_site_window(driver)
        return composer(driver)

    def _read_input_text(self, driver, el):
        if self._expected is not None and self._stage == 'prepare':
            return self._verified_field(driver, self._expected)[1]
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
        self._stage, self._expected = 'field', prompt
        try:
            # The native loop re-finds a detached element. Only its first pass may write.
            return super().send_message_and_get_response(driver, prompt, **dict(kwargs, input_retries=3))
        except (AppError, ParserCancelled): raise
        except Exception as error:
            # The pinned parser sometimes raises bare Exception containing page data.
            if type(error) is not Exception and not isinstance(error, (WebDriverException, TimeoutError)): raise
            message = {'field':'поле ввода недоступно. Откройте вкладку и проверьте, доступен ли чат.',
                       'prepare':'не удалось подтвердить текст в поле. Сообщение не отправлено.',
                       'submit':'отправка не подтверждена. Перед повтором проверьте чат на сайте.',
                       'read':'не удалось получить ответ. Проверьте последнее сообщение на сайте.'}[self._stage]
            raise AppError('unavailable', 'Arena: '+message) from None
        finally:
            self._inline_check = self._expected = None

    def insert_input_for_send(self, driver, el, prompt):
        if self._stage == 'field':
            value = draft_text(driver, el)
            self._stage = 'prepare'
            if not super()._insert_text_matches(value, prompt):
                self._write_field(driver, el, prompt)
        self._verified_field(driver, prompt)
        self._inline_check = driver
        return 'insert'

    def insert_input(self, driver, el, prompt):
        # The pinned parser may request a recovery write before submit. Stop instead.
        raise AppError('unavailable', 'Arena: текст в поле изменился. Повторная вставка отменена; сообщение не отправлено.')

    def _insert_text_matches(self, value, prompt):
        # The native pipeline's first post-insert check reads innerText directly.
        driver, self._inline_check = self._inline_check, None
        if driver is not None:
            _, value = self._verified_field(driver, prompt)
        return super()._insert_text_matches(value, prompt)

    def _verified_field(self, driver, prompt):
        end = time.monotonic() + 1.5
        while True:
            field, value = self.find_input(driver), None
            if field is not None:
                try: value = draft_text(driver, field)
                except StaleElementReferenceException: pass
            if value is not None and super()._insert_text_matches(value, prompt):
                return field, value
            if time.monotonic() >= end: break
            time.sleep(.1)
        reason = ('редактор недоступен' if value is None else
                  'текст редактора отличается от запроса (символов: %d, ожидалось: %d)' % (len(value), len(prompt)))
        raise AppError('unavailable', 'Arena: '+reason+'. Сообщение не отправлено.')

    def _write_field(self, driver, el, prompt):
        if self.find_input(driver) != el:
            raise AppError('conflict', 'Поле ввода Arena изменилось.')
        el.click()
        el.send_keys(Keys.CONTROL, 'a')
        if not driver.execute_script('return document.activeElement === arguments[0]', el):
            raise AppError('conflict', 'Поле ввода Arena потеряло фокус.')
        driver.execute_cdp_cmd('Input.insertText', {'text':prompt})

    def submit(self, driver, el):
        if self._stage != 'prepare':
            raise AppError('conflict', 'Arena: отправка уже началась. Проверьте чат на сайте.')
        el, _ = self._verified_field(driver, self._expected)
        self._submitted_field = el
        self._stage = 'submit'
        return super().submit(driver, el)

    def confirm_sent(self, driver, el):
        if not super().confirm_sent(driver, self._submitted_field):
            raise AppError('unavailable', 'Arena не подтвердила отправку. Перед повтором проверьте чат на сайте.')
        self._stage = 'read'
        return True
