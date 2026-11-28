"""Opt-in native browser/API write-loop gateway; accepted K1 gateway unchanged."""
import contextlib
import hashlib
from importlib import import_module
import io
import json
import os
from pathlib import Path
import re
import threading
from python.kernel.errors import AppError
from python.substrate.assistant.chat_gateway import ChatGateway
from python.substrate.assistant.native_bindings import NativeBindings
from python.substrate.context.librarian_read import _LOCK

_WRAPPED_DONE=re.compile(r'\[(code|b|i)\]\s*={2,}\s*DONE\s*={2,}\s*\[/\1\]\s*\Z',re.IGNORECASE)
_ACTION_START=re.compile(r'^\s*```agent_action\b',re.IGNORECASE|re.MULTILINE)
_STUDIO_UNAVAILABLE=re.compile(r"Model\s+\d{1,2}:\d{2}(?:\s*[AP]M)?\s+error\s+Model isn['’]t available right now\.\s+Please wait a minute and try again\.",re.I)

class InteractiveGateway(ChatGateway):
    def __init__(self,project_root,state_dir,addon_dir,selection=None,progress=None,approved_read=None,bind_chat=None):
        super().__init__(project_root,state_dir,addon_dir)
        self._selection=selection;self._progress=progress;self.approved_read=approved_read;self._cancel=threading.Event()
        self._owned_browser=None;self._browser_context={};self._browser_started=False;self._implicit_id=None
        self._mirror_held=set();self._bind_chat=bind_chat

    def _new_title(self, store, prompt):
        # The panel store names the chat from the first redacted, visible user message.
        return store.DEFAULT_TITLE if self._bind_chat else super()._new_title(store, prompt)

    def send(self,text,*,system_text=None,provider=None,model=None,max_chars=200000):
        with _LOCK:
            self._guard_storage();NativeBindings().register()
            import chat_store
            selected=self._selection() if self._selection else None
            if self._selection:
                if selected and selected['id']!=self._implicit_id:self._implicit_id=None
                self._record=selected or (chat_store.find_chat(str(self.storage_base),self._implicit_id)
                                          if self._implicit_id else None)
            rec=self._record
            browser=(rec is not None and rec.get('kind')!='api') or os.environ.get('GODOT_AGENT_CHAT_MODE')=='browser'
            if not browser:
                reply=super().send(text,system_text=system_text,provider=provider or (self._record or {}).get('provider'),
                                   model=model or (self._record or {}).get('model'),max_chars=max_chars)
                if self._record and self._record.get('kind')!='api':
                    updated=chat_store.update_chat(str(self.storage_base),self._record['id'],kind='api')
                    self._record=updated or dict(self._record,kind='api')
                if (reply.get('finish_reason')=='stop' and not reply.get('parse_error')
                        and reply.get('action') is None and str(reply.get('text','')).strip()):
                    import parser_base
                    raw=str(reply.get('raw') or reply.get('text') or '').rstrip()
                    reply=self._finish_plain(reply,raw,max_chars,parser_base)
                if self._bind_chat and not reply.get('parse_error') and reply.get('finish_reason')=='stop':
                    from python.substrate.llm.api.md_to_bbcode import to_bbcode
                    reply=dict(reply,text=to_bbcode(reply['text']))
            else:
                self._cancel.clear()
                self._check_cancelled()
                reply=self._send_browser(text,system_text or self.system_prompt(),max_chars)
            if not selected and self._record:self._implicit_id=self._record['id']
            if self._bind_chat and self._record:self._bind_chat(self._record['id'])
            return reply

    @staticmethod
    def _finish_plain(reply,raw,max_chars,parser):
        if _ACTION_START.search(raw):return dict(reply,done=False,parse_error='incomplete action')
        if not parser._has_done_marker(raw):raw=raw.rstrip()+'\n===DONE==='
        if len(raw)>max_chars:return dict(reply,done=False,finish_reason='length')
        return dict(reply,raw=raw,done=True,finish_reason='stop')

    def _ensure_browser(self,timeout=1):
        live=self.current_driver()
        if live is not None:return live
        from python.substrate.llm import runtime_owner
        if self._owned_browser is not None:
            # Its child exited since the last request. Release only this session's owner.
            self.close()
        if self._owned_browser is None:
            chrome=os.environ.get('GODOT_AGENT_CHROME_PATH','').strip()
            if not chrome or not Path(chrome).is_file():
                raise AppError('unavailable','Chrome не найден, укажите путь в настройках')
            from python.substrate.llm.browser.facade import ReadOnlyBrowser
            driver=os.environ.get('GODOT_AGENT_CHROMEDRIVER_PATH') or None
            self._browser_started=True
            try:owner=ReadOnlyBrowser(chrome,driver)
            except BaseException:self._browser_started=False;raise
            try:runtime_owner.bind_owner(owner)
            except BaseException:self._browser_started=False;owner.close();raise
            self._owned_browser=owner
        return runtime_owner.wait_driver(timeout=timeout)

    def current_driver(self):
        from python.substrate.llm import runtime_owner
        if self._owned_browser is None:return None
        try:return runtime_owner._live_driver(self._owned_browser)
        except (RuntimeError,TypeError):return None

    def wait_driver(self,timeout=90.0):
        from .chat_navigation import prepare_window
        try:
            previous=self.current_driver()
            driver=self._ensure_browser(timeout=timeout)
            if previous is not None and driver is previous:
                page=getattr(self,'selected_page',None)
                bound=page.window if page and page.driver is driver else None
                if not prepare_window(self._owned_browser,driver,bound):
                    self.close();driver=self._ensure_browser(timeout=timeout)
        except AppError as error:
            raise RuntimeError(error.message) from None
        except Exception as error:
            # Don't expose Selenium stack traces, profile paths or debugger addresses.
            reason = str(error)
            if '9222 availability' in reason:
                hint = 'Порт 9222 занят или недоступен. Закройте прежнее окно браузера агента и повторите.'
            elif 'did not become ready' in reason or 'owner does not match' in reason:
                hint = 'Не удалось подключиться к отдельному окну браузера агента. Закройте прежнее окно агента и повторите.'
            else:
                hint = 'Не удалось запустить браузер агента или подключить ChromeDriver. Проверьте драйвер и повторите.'
            raise RuntimeError(hint) from None
        if driver is not self.current_driver():raise RuntimeError('Foreign browser owner is not adopted')
        return driver

    def browser_boot_started(self):return self._browser_started or self._owned_browser is not None

    def _send_browser(self,text,system,max_chars):
        from python.substrate.llm.browser import sites
        from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
        import parser_base,api_keys,chat_store
        rec=self._record or {}
        if rec and getattr(self,'selected_page',None):self.selected_page.require(rec,self.current_driver())
        from python.substrate.assistant.saved_page import site_for_record
        site=site_for_record(rec) if rec else sites.get_site(os.environ.get('GODOT_AGENT_CHAT_SITE','qwen'))
        if not site:raise AppError('invalid_input','Unknown browser site')
        parser_name=site['parser']
        parser=import_module('python.substrate.llm.parsers.'+parser_name)
        driver=self._ensure_browser()
        url=rec.get('url') or site['new_chat_url']
        if self._record is None:
            self._record=chat_store.create_chat(str(self.storage_base),url=url,title='Browser agent',primed=False)
            self._record=chat_store.update_chat(str(self.storage_base),self._record['id'],kind='site',site_id=site['id']) or self._record
        chat_id=self._record['id']
        digest=hashlib.sha256(system.encode()).hexdigest()
        include_context=self._browser_context.get(chat_id)!=(url,digest)
        if include_context:
            self._browser_context.pop(chat_id,None)
        prompt=(system+'\n\n=== CURRENT REQUEST (answer it directly) ===\n'+text if include_context else text)
        delivery=None
        studio=None
        if site['id']=='deepseek':
            from python.substrate.llm.parsers.deepseek_delivery import DeepSeekDelivery
            delivery=DeepSeekDelivery(driver)
        elif site['id']=='qwen':
            from python.substrate.llm.parsers.qwen_delivery import QwenDelivery
            parser=QwenDelivery(self.project_root,self.addon_dir,getattr(self,'valid_read_proposal',None))
            parser.rank=self.judge.select
        elif site['id']=='kimi':
            from python.substrate.llm.parsers.kimi_delivery import KimiDelivery
            parser=KimiDelivery(site,driver,request=text)
        elif site['id'] in ('arena','arena_battle'):
            from python.substrate.llm.parsers.arena_delivery import ArenaDelivery
            parser=ArenaDelivery(site,driver,url,self.judge,getattr(self,'valid_read_proposal',None))
            self._mirror_held.add(chat_id)  # A late draft cannot overwrite an unresolved send.
        elif site['id']=='aistudio':
            from python.substrate.llm.parsers.studio_delivery import StudioDelivery
            studio=StudioDelivery(driver,url)
        backend=BrowserBackend(studio or delivery or parser)
        capture=[];strip=parser_base._strip_done_marker;sample=parser_base._save_corpus_sample
        def observe(raw):capture.append(raw);return strip(raw)
        def report(update):
            if self._progress:
                self._progress(dict(phase=str(update.get('phase',''))[:100],elapsed=int(update.get('elapsed',0)),
                    chars=int(update.get('chars',0)),stream=api_keys.redact(str(update.get('stream','')))[:30000]))
        parser_base._strip_done_marker=observe;parser_base._save_corpus_sample=lambda *_a,**_k:None
        log=io.StringIO()
        def send_browser(prompt):
            nonlocal url
            from .provider_conversation import FirstReply, permanent, save_unique
            first = None if studio or delivery else FirstReply(driver,site,url)
            def remember(response):
                nonlocal url
                confirmed=(studio or delivery).conversation_url if studio or delivery else None
                if first and response is not None and not str(response.get('text','')).startswith('[Ошибка]'):
                    confirmed=first.confirmed(driver,prompt,accepted=True,parser=parser,check=self._check_cancelled)
                elif first and response is None and site['id']=='qwen' and not self._cancelled():
                    # Qwen can assign a permanent URL even when its reply fails.
                    if permanent(site,driver.current_url): confirmed=first.confirmed(driver,prompt,accepted=False)
                if confirmed and confirmed!=url:
                    updated=save_unique(chat_store,str(self.storage_base),chat_id,site,confirmed)
                    if not updated: raise AppError('conflict','Ссылка уже привязана к другому чату или не подтверждена.')
                    self._record=updated; url=updated['url']
                    if getattr(self,'selected_page',None): self.selected_page.select(chat_id,driver,restored=True)
            try:
                response=backend.send(prompt,prefer_url=url,progress_cb=report,cancel_cb=self._cancelled)
                self._check_cancelled()
            except Exception:
                if not self._cancelled():
                    with contextlib.suppress(Exception): remember(None)
                raise
            finally:
                if delivery and delivery.composer_touched:self._mirror_held.add(self._record['id'])
                if site['id'] in ('arena','arena_battle') and getattr(self,'report_arena',None):
                    self.report_arena(parser.events, parser.stream_posts())
            remember(response)
            return response
        try:
            with contextlib.redirect_stdout(log):
                result=send_browser(prompt)
            result_text=str(result.get('text',''))
            action=result.get('action');parse_error=(action or {}).get('error') if isinstance(action,dict) and action.get('action')=='parse_error' else None
            if site['id']=='aistudio' and not action and _STUDIO_UNAVAILABLE.fullmatch(result_text.strip()):
                raise AppError('unavailable','AI Studio: модель сейчас недоступна. Попробуйте через минуту.')
            if result_text.startswith('[Ошибка]'):
                return self._redact(dict(text=result_text[:200000],raw='',action=None,
                    done=False,finish_reason='error',parse_error=None),api_keys.redact)
            if (delivery or site['id'] in ('arena','arena_battle')) and (result_text.strip() or action):self._mirror_held.discard(chat_id)
            raw=str(capture[-1]) if capture else result_text
            if site['id']=='qwen' and getattr(parser,'choices',None) and parser.choices.frame:
                raw=parser.choices.text
            elif site['id']=='qwen' and action:
                from python.substrate.llm.parsers.qwen_rename import rename_block
                proposal=rename_block(raw)
                if proposal and proposal[1]==action:raw=proposal[2]
            if isinstance(action,dict) and parse_error is None and not _ACTION_START.search(raw):
                raw=(raw.rstrip()+'\n```agent_action\n'+json.dumps(action,ensure_ascii=False)+'\n```').strip()
            raw=_WRAPPED_DONE.sub('\n===DONE===',raw)
            clean_text=parser_base._strip_done_marker(_WRAPPED_DONE.sub('',result_text)).strip()
            has_done=parser_base._has_done_marker(raw)
            reply=dict(text=clean_text[:max_chars],raw=raw[:max_chars],action=action,
                       done=has_done,finish_reason='stop' if has_done else None,parse_error=parse_error)
            if len(raw)>max_chars:reply.update(action=None,done=False,finish_reason='length')
            elif action is None and not parse_error and clean_text:
                reply=self._finish_plain(reply,raw,max_chars,parser_base)
            if include_context and not reply['parse_error'] and reply['finish_reason']!='length' and (reply['done'] or action):
                self._browser_context[chat_id]=(url,digest)
                chat_store.update_chat(str(self.storage_base),chat_id,primed=True,prompt_hash=digest)
            return self._redact(reply,api_keys.redact)
        except parser_base.ParserCancelled as error:raise AppError('unavailable','Browser turn stopped') from error
        finally:
            parser_base._strip_done_marker=strip;parser_base._save_corpus_sample=sample
            api_keys.redact(log.getvalue());log.close()

    def _cancelled(self):return self._cancel.is_set() or getattr(self,'turn_cancelled',lambda:False)()

    def _check_cancelled(self):
        if self._cancelled():raise AppError('unavailable','Ожидание остановлено.')

    def stop(self):self._cancel.set();return True

    def close(self):
        self._browser_started=False
        self._browser_context.clear()
        if self._owned_browser is not None:
            from python.substrate.llm import runtime_owner
            owner=self._owned_browser;self._owned_browser=None
            try:runtime_owner.release_owner(owner)
            finally:owner.close()
