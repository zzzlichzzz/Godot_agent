"""Rebuild-only DeepSeek composer policy; keep the reference answer parser intact."""
from urllib.parse import urlsplit

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.keys import Keys

from parser_base import ParserCancelled
from .deepseek_completion import PLACEHOLDER, complete
from . import deepseek_parser as native
from .deepseek_parser import DeepSeekParser, _DeliveryUncertainError


_FIND = """
const fields = Array.from(document.querySelectorAll('textarea#chat-input, textarea[name="search"]'))
    .filter(el => el.isConnected && !el.matches(':disabled,[readonly],textarea[name="user query"]')
        && !el.closest('dialog,[role="dialog"],[inert],[aria-hidden="true"]')
        && el.getClientRects().length && getComputedStyle(el).visibility === 'visible');
return fields.length === 1 ? fields[0] : null;
"""
# _1d5e44c is the public frontend's withFile class (main.b2127178f0.js),
# for file chips whose picker is already empty. Keep the semantic checks too.
_FILES = """
const el = arguments[0];
if (!el.isConnected) return null;
for (let node = el.parentElement, n = 0; node && n < 5; node = node.parentElement, n++) {
    if (node.classList.contains('_1d5e44c')) return true;
    if (node.querySelector('.ds-markdown')) break;
    if (node.querySelector('.ds-file-card, [class*="file-card"], [class*="attachment-card"]')) return true;
    if (Array.from(node.querySelectorAll('input[type="file"]')).some(input => input.files.length)) return true;
}
return false;
"""


def chat_url(url):
    """Canonical DeepSeek origin/path, ignoring presentation-only query and hash."""
    try:
        parsed = urlsplit(url or '')
        if parsed.scheme == 'https' and parsed.netloc == 'chat.deepseek.com':
            return 'https://chat.deepseek.com' + (parsed.path.rstrip('/') or '/')
    except ValueError:
        pass
    return None


class DeepSeekDelivery(DeepSeekParser):
    REGENERATE_RETRIES = 0

    def __init__(self, driver):
        self.driver = driver
        self.conversation_url = None
        self.composer_touched = False

    def extract_answer(self, driver):
        # Always verify two whole frames, including separate action bytes.
        if not self.is_generating(driver):
            first = self.extract_answer_snapshot(driver) or {}
            if complete(driver,first):
                native.time.sleep(self.POLL_INTERVAL)
                second = self.extract_answer_snapshot(driver)
                if second == first and not self.is_generating(driver):
                    return second
        return super().extract_answer(driver)

    def answer_stream(self, driver):
        stream = super().answer_stream(driver)
        # The DOM may render DONE, then the action card. Expose the actual
        # terminal line of the prose to the native wait, never manufacture one.
        if '===DONE===' in stream and not stream.rstrip().endswith('===DONE===') and not self.is_generating(driver):
            frame = self.extract_answer_snapshot(driver) or {}
            if frame.get('actionRaw') and complete(driver, frame):
                return frame['text'].replace(PLACEHOLDER, '').rstrip()
        return stream

    def send_message_and_get_response(self, driver, prompt, *, prefer_url=None, progress_cb=None, cancel_cb=None):
        self._target = chat_url(prefer_url)
        self.composer_touched = False
        self._dispatch_started = False
        self._insert_became_attachment = False
        self.conversation_url = None
        try:
            if driver is not self.driver or not self._target:
                raise _DeliveryUncertainError('DeepSeek: не удалось определить вкладку выбранного чата.')
            def check_cancel():
                if self._dispatch_started:
                    self._verify_route(driver)
                return cancel_cb is not None and cancel_cb()
            result = super().send_message_and_get_response(
                driver, prompt, input_retries=1, prefer_url=prefer_url,
                progress_cb=progress_cb, cancel_cb=check_cancel)
            if self.conversation_url:
                self.conversation_url = self._verify_route(driver)
            return result
        except WebDriverException:
            message = ('не удалось подтвердить доставку; проверьте чат перед повтором' if self._dispatch_started
                       else 'поле ввода недоступно, сообщение не отправлено')
        except TimeoutError:
            message = ('ответ не получен; проверьте чат перед повтором' if self._dispatch_started
                       else 'предыдущий ответ ещё не завершился; сообщение не отправлено')
        except _DeliveryUncertainError as error:
            return {'text': '[Ошибка]: ' + str(error), 'action': None}
        return {'text': '[Ошибка]: DeepSeek: ' + message + '.', 'action': None}

    def switch_to_site_window(self, driver, prefer_url=None):
        super().switch_to_site_window(driver, prefer_url=prefer_url)
        current = chat_url(driver.current_url)
        if current == 'https://chat.deepseek.com/sign_in':
            raise _DeliveryUncertainError('DeepSeek: войдите в аккаунт в браузере агента; сообщение не отправлено.')
        if not self._target or current != self._target:
            raise _DeliveryUncertainError('DeepSeek: откройте вкладку выбранного чата; сообщение не отправлено.')
        self._window = driver.current_window_handle

    def find_input(self, driver):
        if self._dispatch_started:
            self._verify_route(driver)
        elif driver.current_window_handle != self._window or chat_url(driver.current_url) != self._target:
            raise _DeliveryUncertainError('DeepSeek: вкладка сменилась, сообщение не отправлено.')
        return driver.execute_script(_FIND)

    def mirror_input(self, driver, text, prefer_url=None):
        """Mirror only the same composer accepted for sends; never submit."""
        self._dispatch_started = False
        self._target = chat_url(prefer_url)
        if driver is not self.driver or not self._target:
            return False
        try:
            self.switch_to_site_window(driver, prefer_url=prefer_url)
            el = self.find_input(driver)
            if el is None:
                return False
            self._verify_composer(driver, el)
            if not self._insert_text_matches(self._read_input_text(driver, el), text):
                super().insert_input(driver, el, text)
                self._verify_composer(driver, el)
            return self._insert_text_matches(self._read_input_text(driver, el), text)
        except (WebDriverException, _DeliveryUncertainError):
            return False

    def _verify_composer(self, driver, el):
        if driver.current_window_handle != self._window or chat_url(driver.current_url) != self._target:
            raise _DeliveryUncertainError('DeepSeek: вкладка сменилась, сообщение не отправлено.')
        files = driver.execute_script(_FILES, el)
        if files is None:
            raise _DeliveryUncertainError('DeepSeek: поле ввода изменилось, сообщение не отправлено.')
        if files:
            raise _DeliveryUncertainError('DeepSeek: проверьте вложения в черновике и уберите лишние файлы перед отправкой.')

    def _wait_for_input(self, driver, retries, cancel_cb=None):
        # The generic fallback searches all textareas, including unrelated forms.
        deadline = native.time.monotonic() + 10.0
        while native.time.monotonic() < deadline:
            if cancel_cb and cancel_cb():
                raise ParserCancelled('остановлено пользователем')
            el = self.find_input(driver)
            if el is not None:
                self._verify_composer(driver, el)
                return el
            native.time.sleep(0.2)
        raise _DeliveryUncertainError('DeepSeek: поле выбранного чата не найдено; сообщение не отправлено.')

    def _insert_text_matches(self, value, prompt):
        # The DOM textarea normalizes CR/CRLF, but all other bytes of the text matter.
        return value == prompt.replace('\r\n', '\n').replace('\r', '\n')

    def insert_input_for_send(self, driver, el, prompt):
        try:
            self.insert_input(driver, el, prompt)
            if not self._wait_field_matches(driver, el, prompt, 2.0):
                raise _DeliveryUncertainError('DeepSeek: поле не сохранило точный текст; сообщение не отправлено.')
            self._verify_composer(driver, el)
        except WebDriverException:
            raise _DeliveryUncertainError('DeepSeek: поле ввода изменилось, сообщение не отправлено.') from None
        return 'insert'

    def insert_input(self, driver, el, prompt):
        if self.composer_touched:
            raise _DeliveryUncertainError('DeepSeek: поле не сохранило точный текст; повторной вставки не было.')
        self._verify_composer(driver, el)
        self.composer_touched = True
        self._expected = prompt
        super().insert_input(driver, el, prompt)

    def submit(self, driver, el):
        try:
            self._verify_composer(driver, el)
            if not self._insert_text_matches(self._read_input_text(driver, el), self._expected):
                raise _DeliveryUncertainError('DeepSeek: текст изменился перед отправкой; сообщение не отправлено.')
            self._composer_had_text = True
            self._dispatch_started = True
            el.send_keys(Keys.ENTER)
        except WebDriverException:
            # Do not let the reference pipeline retry on a stale element.
            message = ('не удалось подтвердить доставку; проверьте чат перед повтором' if self._dispatch_started
                       else 'поле ввода изменилось, сообщение не отправлено')
            raise _DeliveryUncertainError('DeepSeek: ' + message + '.') from None

    def confirm_sent(self, driver, el):
        result = super().confirm_sent(driver, el)
        self.conversation_url = self._verify_route(driver)
        return result

    def _verify_route(self, driver):
        current = chat_url(driver.current_url)
        permitted = self.conversation_url or self._target
        new_chat = (permitted == 'https://chat.deepseek.com/' and current
                    and current.startswith(permitted + 'a/chat/s/'))
        if driver.current_window_handle != self._window or not (
            current == permitted or new_chat
        ):
            raise _DeliveryUncertainError('DeepSeek: вкладка изменилась; проверьте чат перед повтором.')
        if new_chat:
            self.conversation_url = current
        return current
