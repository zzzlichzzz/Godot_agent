"""One Qwen dispatch. Provider notices are UI state, never model answers."""
import time

from parser_base import ParserCancelled
from python.kernel.errors import AppError
from . import qwen_parser as native
from .qwen_parser import QwenParser
from .qwen_choices import QwenChoices
from .qwen_rename import rename_block
from ..browser.qwen_request_watch import QwenRequestWatch


# Only the current assistant shell and provider notifications are eligible. Text in
# the composer, quoted code, reasoning and Markdown is conversation content.
_NOTICES = r'''
const turns = document.querySelectorAll('.qwen-chat-message-assistant');
const last = turns[turns.length-1];
const skip = '[class*="markdown"],pre,code,blockquote,[contenteditable],textarea,'+
    '[class*="message-user"],[class*="user-message"],[class*="thinking"],[aria-hidden="true"]';
const selector = '[role="alert"],[role="status"],[class*="error" i],[class*="toast" i],[class*="notification" i]';
const candidates = [...document.querySelectorAll(selector)];
if(last) candidates.push(last);
const notices = []; let terminal = false;
for(const el of candidates){
    const owner = el.closest('.qwen-chat-message-assistant');
    if(owner && owner !== last || el.closest(skip) || !el.checkVisibility({visibilityProperty:true})) continue;
    // Do not read the whole surrounding turn as if quoted prose were a notice.
    if(el.querySelector(skip)) continue;
    const t = el.innerText.replace(/\s+/g,' ').trim();
    const error = /^(?:Oops! There was an issue connecting to Qwen[\w. -]{0,48}\.?(?: |$))?(Invalid input chat parent_id [\w-]{1,80} is not exist)\.?($| (?:Retry|Regenerate|Try again)\b)/i.exec(t)
        || /^(Oops! There was an issue connecting to Qwen[\w.-]{0,48})\.?$/i.exec(t)
        || /^(Network (?:error|connection (?:error|failed))|Failed to fetch|Load failed|Ошибка сети|Сетевая ошибка|网络错误)(?:[.!:。]|$| (?:Retry|Please|Try again|Повторить)\b)/i.exec(t);
    if(error){
        notices.push([el,error[1]]);
        if(owner) terminal=true;
    }
}
return [notices,terminal];
'''


class QwenDelivery(QwenParser):
    SEND_RETRIES = REGENERATE_RETRIES = 0

    def __init__(self, project=None, addon=None, valid_read=None):
        self.project, self.addon, self.valid_read = project, addon, valid_read

    def send_message_and_get_response(self, driver, prompt, *, cancel_cb=None, **kwargs):
        self._baseline = None
        self._failed = False
        self._stop = cancel_cb
        self.choices = None
        self.watch = None

        def poll():
            self.check_wait(driver)
            return False

        try:
            reply = super().send_message_and_get_response(driver, prompt, cancel_cb=poll, **kwargs)
            self.check_wait(driver)
            if self.choices and self.choices.frame:
                return {'text':self.choices.frame['text'],'action':self.choices.action}
            proposal = rename_block(reply.get('text') or '') if isinstance(reply,dict) else None
            if proposal:
                prose, action, _ = proposal
                if reply.get('action') not in (None, action):
                    return {'text':prose,'action':{'action':'parse_error','error':'Несовпадающие действия Qwen'}}
                return dict(reply,text=prose,action=action)
            return reply
        finally:
            if self.watch: self.watch.cdp.close()

    def check_wait(self, driver):
        self._check_notice(driver)
        if self.choices: self.choices.resolve(driver,self._check_notice)

    def _check_notice(self, driver):
        if self._stop and self._stop():
            raise ParserCancelled('остановлено пользователем')
        if self._baseline is not None:
            notices, _ = driver.execute_script(_NOTICES)
            current = {tuple(notice) for notice in notices}
            self._failed |= bool(current - self._baseline)
            self._baseline.intersection_update(current)
            failure = self.watch.failure if self.watch else None
            if self._failed or failure:
                why = ' ('+failure+')' if failure else ''
                raise AppError('unavailable', 'Ошибка соединения с Qwen'+why+'. Обновите страницу и повторите отправку.',
                               details={'retry_prompt': True})

    def is_generating(self, driver):
        self.check_wait(driver)
        if self.choices and self.choices.frame: return False
        if self._baseline is None and driver.execute_script(_NOTICES)[1]:
            # A failed turn may never get the normal completion footer.
            return False
        return bool(driver.execute_script(native.JS_IS_GENERATING))

    def answer_stream(self, driver):
        # A plain winner must not acquire an unjudged JSON action via Plan B.
        if self.choices and self.choices.frame: return ''
        return super().answer_stream(driver)

    def wait_for_new_answer(self, driver, *args, **kwargs):
        self.check_wait(driver)
        if self.choices and self.choices.frame: return self.choices.frame
        result=super().wait_for_new_answer(driver,*args,**kwargs)
        self.check_wait(driver)
        return (self.choices and self.choices.frame) or result

    def extract_answer(self, driver):
        # The native final DOM read can wait 240 seconds without polling Stop.
        # Keep its composed (including code) snapshot and network completeness
        # criteria, but poll the owner and provider notice between reads.
        deadline = time.monotonic() + 240
        previous = None
        post_gen = 0
        while True:
            self.check_wait(driver)
            if self.choices and self.choices.frame: return self.choices.frame
            if self.net_answer_ready(driver):
                text = self._net_live_text() or ''
                prose, raw = native.split_net_text_and_action(text)
                if text and not (raw and native.answer_transfer_incomplete(raw, text)):
                    return {'text': prose, 'actionRaw': raw, 'error': None}
            frame = self.extract_answer_snapshot(driver)
            text, raw = frame['text'], frame['actionRaw']
            incomplete = (raw and native.answer_transfer_incomplete(raw, text)
                          or native.height_says_incomplete(text, native.block_height(driver)))
            if not text or (frame == previous and not incomplete):
                return frame
            if not self.is_generating(driver): post_gen += 1
            if post_gen > 8 or time.monotonic() >= deadline: return frame
            previous = frame
            next_read = time.monotonic() + 2
            while time.monotonic() < next_read:
                self.check_wait(driver)
                time.sleep(self.POLL_INTERVAL)

    def submit(self, driver, el):
        if self._baseline is not None:
            raise AppError('unavailable', 'Qwen: не удалось подтвердить отправку.', details={'retry_prompt': True})
        self.check_wait(driver)
        self._baseline = {tuple(notice) for notice in driver.execute_script(_NOTICES)[0]}
        self.choices = QwenChoices(driver,self.project,self.addon,self.valid_read,getattr(self,'rank',None))
        self.watch = QwenRequestWatch.attach(driver)
        super().submit(driver, el)

    def after_submit(self, driver, el):
        # Give the composer time to clear without issuing another Enter or Send.
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            self.check_wait(driver)
            if self.confirm_sent(driver, el): return
            time.sleep(.2)
