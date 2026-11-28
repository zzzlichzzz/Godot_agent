"""Session-local browser destination. A readable transcript is not permission to type."""
import time
from python.kernel.errors import AppError
from python.substrate.llm.browser import sites
from python.substrate.llm.browser.page_origin import matches_saved_origin
from python.substrate.llm.parsers.studio_draft import _READY, is_new_prompt, studio_route
from python.substrate.llm.parsers.studio_navigation import matching_open_chat, restore_after_home, wait_blank
from .provider_conversation import permanent, ready as provider_ready, recover_qwen, route


def site_for_record(rec):
    url = rec.get('url') or ''
    site = sites.get_site(rec['site_id']) if rec.get('site_id') else sites.detect_site(url)
    if site and site['id'] == 'kimi':
        # A saved conversation belongs to its original account and origin.
        legacy = dict(site, new_chat_url='https://www.kimi.com/')
        if permanent(legacy, url): return legacy
    return site


class SavedPage:
    def __init__(self):
        self.select(None)

    def select(self, cid, driver=None, *, restored=False):
        self.cid, self.driver, self.restored = cid, driver, restored
        self.window = getattr(driver, 'current_window_handle', None) if driver is not None else None

    def restore(self, rec, wait_driver, navigate, site, timeout=6, *, current_driver=None, save_url=None):
        cid, url = rec['id'], rec.get('url') or ''
        self.select(cid)
        studio = site and site['id'] == 'aistudio'
        history = (rec.get('primed') or rec.get('transcript_trimmed') or
                   any(r.get('role') in ('user','agent') for r in rec.get('transcript', [])))
        target = route(site, url)
        if not studio and history and not permanent(site, url):
            try:
                candidate = None
                if site and site['id']=='qwen' and target==site['new_chat_url']:
                    driver = (current_driver() if current_driver else None) or wait_driver()
                    if not route(site,driver.current_url): navigate(driver,target)
                    candidate = recover_qwen(driver, rec, site)
                if candidate and save_url and save_url(candidate):
                    self.select(cid, driver, restored=True)
                    return ''
            except Exception:
                pass
            return ('Открыта только история: не сохранена ссылка на сам диалог. Откройте исходный чат '
                    'в истории сайта во вкладке агента и повторите выбор в панели.')
        if studio and history:
            try:
                driver = current_driver() if current_driver else None
                candidate = (matching_open_chat(driver, rec) if driver is not None and
                             studio_route(driver.current_url) != target else None)
                if candidate and save_url and save_url(candidate):
                    self.select(cid, driver, restored=True)
                    return ''
            except Exception:
                pass
        if studio and (not target or (history and is_new_prompt(url))):
            return ('Открыта только история: нет подтверждённой ссылки. Откройте исходный диалог '
                    'из библиотеки AI Studio во вкладке агента и повторно выберите этот чат.')
        try:
            if not target or not matches_saved_origin(site, url):
                return 'Открыта только история: адрес страницы чата не подтверждён.'
            driver = wait_driver()
        except ValueError:
            return 'Открыта только история: сохранённый адрес страницы некорректен.'
        except RuntimeError as exc:
            return 'Открыта только история. ' + str(exc)
        window, previous = None, None
        try:
            window = driver.current_window_handle
            previous = driver.current_url if studio else None
            if navigate(driver, target):
                window = window or driver.current_window_handle
                end = time.monotonic() + timeout
                while True:
                    actual = driver.current_url
                    if window != driver.current_window_handle: break
                    if route(site, actual) == target:
                        if studio and is_new_prompt(target):
                            ready = wait_blank(driver, window, target, max(0, end - time.monotonic()))
                        elif studio:
                            ready = driver.execute_script(_READY, actual, bool(history))
                        else:
                            ready = provider_ready(driver, site)
                        if ready:
                            if studio and target != url and save_url and not save_url(target):
                                break
                            self.select(cid, driver, restored=True)
                            return ''
                    if time.monotonic() >= end: break
                    time.sleep(.2)
        except Exception:
            pass  # A dead tab or provider redirect doesn't invalidate a local transcript.
        if studio and studio_route(previous) != target:
            try:
                restore_after_home(driver, window, previous)
            except Exception:
                pass  # Restoring the view never grants write access to the old chat.
        return ('Открыта только история: браузер не подтвердил страницу диалога. '
                'Откройте исходный диалог из библиотеки AI Studio во вкладке агента и повторите выбор.' if studio else
                'Открыта только история: проверьте доступ к странице и снова откройте чат из списка.')
    def require(self, rec, driver):
        if self.cid == rec['id'] and driver is not None and driver is self.driver:
            site = site_for_record(rec)
            try:
                if not self.window or driver.current_window_handle != self.window: raise ValueError('tab changed')
                actual = route(site, driver.current_url)
                if actual and actual == route(site, rec.get('url')): return
            except Exception:
                pass
        raise AppError('conflict','Страница диалога не подтверждена. Откройте чат из списка сохранённых.')

    def page_status(self, rec, driver):
        self.require(rec, driver)
        site = site_for_record(rec)
        if site['id'] in ('arena','arena_battle'):
            from python.substrate.llm.parsers.arena_composer import page_status
            return page_status(driver)
        if site['id'] == 'aistudio':
            return dict(ready=driver.execute_script(_READY, driver.current_url, False) is True)
        return dict(ready=provider_ready(driver, site))

    def reload(self, rec, driver):
        from selenium.common.exceptions import TimeoutException, WebDriverException
        self.require(rec, driver)
        try:
            previous = driver.timeouts.page_load
            driver.set_page_load_timeout(10)
            try: driver.refresh()
            except TimeoutException: pass  # The dock polls the composer separately.
            finally: driver.set_page_load_timeout(previous)
            self.require(rec, driver)
        except WebDriverException:
            raise AppError('unavailable', 'Не удалось перезагрузить вкладку чата. Проверьте браузер.') from None
