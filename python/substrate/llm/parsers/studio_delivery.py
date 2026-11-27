"""Pin AI Studio writes to the selected tab; adopt a prompt URL only on proven delivery."""
from .ai_parser import AiStudioParser, _DeliveryUncertainError
from .studio_draft import _COMPOSER, is_new_prompt, studio_route
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException

_FIELD = _COMPOSER + 'return location.href === arguments[0] ? el : null;'
_HAS_REQUEST = '''
const turns = document.querySelectorAll('[data-turn-role="User"]');
const norm = s => s.replace(/\\s+/g, ' ').trim();
if (location.href !== arguments[0] || !turns.length) return false;
const turn = turns[turns.length-1], expected = norm(arguments[1]);
return [turn, ...turn.querySelectorAll('ms-text-chunk, [mssnapshotlink], .turn-content')]
    .some(el => norm(el.innerText) === expected);
'''


class StudioDelivery(AiStudioParser):
    def __init__(self, driver, url):
        self.driver, self.target = driver, studio_route(url)
        self.window = driver.current_window_handle
        self.conversation_url = None
        self._accepted = False
        self._sent_text = ''

    def switch_to_site_window(self, driver, prefer_url=None):
        # A host match (or another tab at new_chat) is not a conversation identity.
        self._check(driver)

    def _check(self, driver):
        if (driver is not self.driver or driver.current_window_handle != self.window or
                not self.target or studio_route(driver.current_url) != self.target):
            raise _DeliveryUncertainError('Вкладка AI Studio изменилась. Снова откройте нужный чат.')

    def find_input(self, driver):
        self._check(driver)
        return driver.execute_script(_FIELD, driver.current_url)

    def _field(self, driver, el):
        if el is None or el != self.find_input(driver):
            raise _DeliveryUncertainError('Поле выбранного диалога AI Studio не найдено.')

    def insert_input(self, driver, el, prompt):
        self._field(driver, el)
        self._sent_text = prompt
        super().insert_input(driver, el, prompt)

    def before_submit(self, driver, el):
        self._field(driver, el)
        super().before_submit(driver, el)

    def submit(self, driver, el):
        self._field(driver, el)
        try:
            super().submit(driver, el)
        except StaleElementReferenceException:
            raise _DeliveryUncertainError('AI Studio: поле изменилось при отправке. Проверьте чат перед повтором.') from None

    def confirm_sent(self, driver, el):
        self._accepted = super().confirm_sent(driver, el)
        if self._accepted and not self._observe(driver):
            raise _DeliveryUncertainError('AI Studio: адрес изменился, но отправленный запрос в диалоге не подтверждён. Проверьте чат перед повтором.')
        return self._accepted

    def _observe(self, driver):
        try:
            if driver is not self.driver or driver.current_window_handle != self.window: return False
            observed = driver.current_url
            actual = studio_route(observed)
            if actual == (self.conversation_url or self.target): return True
            if (not self.conversation_url and actual and is_new_prompt(self.target) and not is_new_prompt(actual)
                    and self._sent_text and driver.execute_script(_HAS_REQUEST, observed, self._sent_text)):
                self.conversation_url = actual
                return True
        except WebDriverException:
            pass
        return False

    def send_message_and_get_response(self, driver, prompt, **kwargs):
        result = super().send_message_and_get_response(driver, prompt, **kwargs)
        if self._accepted and not self._observe(driver):
            return {'text': '[Ошибка]: AI Studio: страница изменилась после отправки. Проверьте чат перед повтором.', 'action': None}
        return result
