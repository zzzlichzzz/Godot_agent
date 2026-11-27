"""Session-local browser destination. A readable transcript is not permission to type."""
import time

from python.kernel.errors import AppError
from python.substrate.llm.browser import sites
from python.substrate.llm.browser.page_origin import matches_saved_origin
from python.substrate.llm.parsers.studio_draft import _READY, is_new_prompt, studio_route


def site_for_record(rec):
    if rec.get('site_id'):
        return sites.get_site(rec['site_id'])
    return sites.detect_site(rec.get('url') or '')


class SavedPage:
    def __init__(self):
        self.select(None)

    def select(self, cid, driver=None, *, restored=False):
        self.cid, self.driver, self.restored = cid, driver, restored
        self.window = getattr(driver, 'current_window_handle', None) if driver is not None else None

    def restore(self, rec, wait_driver, navigate, site, timeout=6):
        cid, url = rec['id'], rec.get('url') or ''
        self.select(cid)
        studio = site and site['id'] == 'aistudio'
        history = (rec.get('primed') or rec.get('transcript_trimmed') or
                   any(r.get('role') in ('user','agent') for r in rec.get('transcript', [])))
        if studio and (not studio_route(url) or (history and is_new_prompt(url))):
            return 'Сохранена только история: у этой переписки нет ссылки на диалог AI Studio. Для продолжения создайте новый чат.'
        try:
            if not matches_saved_origin(site, url):
                return 'Открыта только история: адрес страницы чата не подтверждён.'
            driver = wait_driver()
        except ValueError:
            return 'Открыта только история: сохранённый адрес страницы некорректен.'
        except RuntimeError as exc:
            return 'Открыта только история. ' + str(exc)
        try:
            if navigate(driver, url):
                window = driver.current_window_handle
                end = time.monotonic() + timeout
                while True:
                    actual = driver.current_url
                    if window != driver.current_window_handle: break
                    if (studio_route(actual) == studio_route(url) if studio else actual == url):
                        if (driver.execute_script(_READY, actual, bool(history)) if studio else
                                driver.execute_script('return document.readyState') == 'complete'):
                            self.select(cid, driver, restored=True)
                            return ''
                    if time.monotonic() >= end: break
                    time.sleep(.2)
        except Exception:
            pass  # A dead tab or provider redirect doesn't invalidate a local transcript.
        return ('Открыта только история: браузер не подтвердил страницу диалога. '
                'Проверьте доступ к чату на сайте и снова откройте его из списка.')

    def require(self, rec, driver):
        if self.cid == rec['id'] and driver is not None and driver is self.driver:
            studio = (site_for_record(rec) or {}).get('id') == 'aistudio'
            try:
                if not self.window or driver.current_window_handle != self.window: raise ValueError('tab changed')
                if not self.restored and not studio: return
                actual = driver.current_url
                same = (studio_route(actual) is not None and studio_route(actual) == studio_route(rec.get('url'))
                        if studio else actual == rec.get('url'))
                if same: return
            except Exception:
                pass
        raise AppError('conflict','Страница диалога не подтверждена. Откройте чат из списка сохранённых.')
