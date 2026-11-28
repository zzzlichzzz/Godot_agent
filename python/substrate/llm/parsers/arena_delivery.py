"""Keep Arena's native branch protocol, evaluating only a Godot-read project view."""
from selenium.webdriver.common.keys import Keys

from python.kernel.errors import AppError
from python.substrate.llm.browser.page_origin import route
from .arena_composer import composer, draft_text
from .arena_parser import ArenaParser


class ArenaDelivery(ArenaParser):
    PASTE_PLAN_A = False

    def __init__(self, site, driver, url, judge=None):
        super().__init__()
        self.judge = judge
        self.site, self.window, self.target = site, driver.current_window_handle, route(site, url)
        self._pasted_field = None

    def switch_to_site_window(self, driver, prefer_url=None):
        if not self.target or driver.current_window_handle != self.window or route(self.site, driver.current_url) != self.target:
            raise AppError('conflict', 'Вкладка Arena изменилась. Откройте нужный чат в панели.')

    def find_input(self, driver):
        self.switch_to_site_window(driver)
        return composer(driver)

    def _read_input_text(self, driver, el):
        return draft_text(driver, el)

    def insert_input_for_send(self, driver, el, prompt):
        mode = super().insert_input_for_send(driver, el, prompt)
        self._pasted_field = driver, el
        return mode

    def _insert_text_matches(self, value, prompt):
        # The native pipeline's first post-insert check reads innerText directly.
        # Read logical paragraphs from that very field; later checks already use draft_text.
        field, self._pasted_field = self._pasted_field, None
        if field is not None:
            driver, el = field
            if el != self.find_input(driver): return False
            value = draft_text(driver, el)
        return super()._insert_text_matches(value, prompt)

    def insert_input(self, driver, el, prompt):
        if self.find_input(driver) != el:
            raise AppError('conflict', 'Поле ввода Arena изменилось.')
        el.click()
        el.send_keys(Keys.CONTROL, 'a')
        if not driver.execute_script('return document.activeElement === arguments[0]', el):
            raise AppError('conflict', 'Поле ввода Arena потеряло фокус.')
        if prompt:
            driver.execute_cdp_cmd('Input.insertText', {'text':prompt})
        else:
            el.send_keys(Keys.BACKSPACE)

    def _project_judgments(self, mon):
        return self.judge.select(mon.branch_variants()) if mon.branch_count() >= 2 else None

    def _judge_single_current_answer(self, mon):
        return self.judge.judge(mon.current_text())

    def send_message_and_get_response(self, *args, **kwargs):
        reply = super().send_message_and_get_response(*args, **kwargs)
        if isinstance(reply, dict) and ArenaParser._last_choice_summary:
            return dict(reply, battle_choice=dict(ArenaParser._last_choice_summary))
        return reply
