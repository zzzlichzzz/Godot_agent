"""Opt-in native browser/API write-loop gateway; accepted K1 gateway unchanged."""
import contextlib
import hashlib
from importlib import import_module
import io
import os
from pathlib import Path
import threading
from python.kernel.errors import AppError
from python.substrate.assistant.chat_gateway import ChatGateway
from python.substrate.assistant.native_bindings import NativeBindings
from python.substrate.context.librarian_read import _LOCK

class InteractiveGateway(ChatGateway):
    def __init__(self,project_root,state_dir,addon_dir,selection=None,editor=None):
        super().__init__(project_root,state_dir,addon_dir)
        self._selection=selection;self._editor=editor;self._cancel=threading.Event()
        self._owned_browser=None;self._browser_prime={};self._browser_started=False

    def send(self,text,*,system_text=None,provider=None,model=None,max_chars=200000):
        with _LOCK:
            self._guard_storage();NativeBindings().register()
            import chat_store
            selected=self._selection() if self._selection else None
            if selected:
                self._record=selected
            if self._editor:
                from python.substrate.editor.references.editor_context import attach_to_prompt
                text,_stats=attach_to_prompt(text,self._editor())
            browser=(self._record or {}).get('kind')=='site' or os.environ.get('GODOT_AGENT_CHAT_MODE')=='browser'
            if not browser:return super().send(text,system_text=system_text,provider=provider or (self._record or {}).get('provider'),
                                               model=model or (self._record or {}).get('model'),max_chars=max_chars)
            self._cancel.clear()
            return self._send_browser(text,system_text or self.system_prompt())

    def _ensure_browser(self,timeout=1):
        from python.substrate.llm import runtime_owner
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
        try:driver=self._ensure_browser(timeout=timeout)
        except AppError as error:
            raise RuntimeError(error.message) from None
        except (OSError,RuntimeError,TypeError):
            raise RuntimeError('Browser is unavailable for this session; Chrome не найден, укажите путь в настройках') from None
        if driver is not self.current_driver():raise RuntimeError('Foreign browser owner is not adopted')
        return driver

    def browser_boot_started(self):return self._browser_started or self._owned_browser is not None

    def _send_browser(self,text,system):
        from python.substrate.llm.browser import sites
        from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
        import parser_base,api_keys,chat_store
        rec=self._record or {}
        site=sites.get_site(rec.get('site_id') or os.environ.get('GODOT_AGENT_CHAT_SITE','qwen'))
        if not site:raise AppError('invalid_input','Unknown browser site')
        parser_name=site['parser']
        parser=import_module('python.substrate.llm.parsers.'+parser_name)
        driver=self._ensure_browser()
        url=rec.get('url') or site['new_chat_url']
        if self._record is None:
            self._record=chat_store.create_chat(str(self.storage_base),url=url,title='Browser agent',primed=False)
            self._record=chat_store.update_chat(str(self.storage_base),self._record['id'],kind='site',site_id=site['id']) or self._record
        backend=BrowserBackend(parser)
        capture=[];strip=parser_base._strip_done_marker;sample=parser_base._save_corpus_sample
        def observe(raw):capture.append(raw);return strip(raw)
        parser_base._strip_done_marker=observe;parser_base._save_corpus_sample=lambda *_a,**_k:None
        log=io.StringIO()
        try:
            with contextlib.redirect_stdout(log):
                marker=(self._record['id'],hashlib.sha256(system.encode()).hexdigest())
                if marker not in self._browser_prime:
                    primed=backend.send(system,prefer_url=url,cancel_cb=self._cancel.is_set)
                    if primed.get('action') or str(primed.get('text','')).startswith('[Ошибка]'):
                        raise AppError('unavailable','Browser prompt priming did not produce a valid acknowledgement')
                    self._browser_prime[marker]=True;capture.clear()
                    chat_store.update_chat(str(self.storage_base),self._record['id'],primed=True)
                result=backend.send(text,prefer_url=url,cancel_cb=self._cancel.is_set)
            raw=str(capture[-1]) if capture else str(result.get('text',''))
            action=result.get('action');parse_error=(action or {}).get('error') if isinstance(action,dict) and action.get('action')=='parse_error' else None
            return self._redact(dict(text=str(result.get('text',''))[:200000],raw=raw[:200000],action=action,
                done=parser_base._has_done_marker(raw),finish_reason=None,parse_error=parse_error),api_keys.redact)
        except parser_base.ParserCancelled as error:raise AppError('unavailable','Browser turn stopped') from error
        finally:
            parser_base._strip_done_marker=strip;parser_base._save_corpus_sample=sample
            api_keys.redact(log.getvalue());log.close()

    def stop(self):self._cancel.set();return True

    def close(self):
        self._browser_started=False
        if self._owned_browser is not None:
            from python.substrate.llm import runtime_owner
            owner=self._owned_browser;self._owned_browser=None
            try:runtime_owner.release_owner(owner)
            finally:owner.close()
