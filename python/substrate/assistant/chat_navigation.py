"""Navigate the selected agent window; a same-site home tab is not a restored chat."""
import time

from selenium.common.exceptions import NoSuchWindowException, TimeoutException, WebDriverException
from urllib3.exceptions import HTTPError
from python.kernel.errors import AppError
from python.substrate.llm.parsers import studio_navigation
from python.substrate.llm.parsers.studio_draft import studio_route


def prepare_window(owner, driver, bound):
    """Explicit navigation only. False means the owned browser has no remaining page."""
    try:
        handles = driver.window_handles
    except (WebDriverException, HTTPError):
        # ChromeDriver may invalidate the session before the last window's process exits.
        if owner._process.poll() is not None: return False
        if owner._cdp.is_alive():
            try: targets = owner._cdp.send_command('Target.getTargets', timeout=2)['targetInfos']
            except Exception: targets = None  # The browser can exit during the query.
            if targets is not None and not any(t['type'] == 'page' for t in targets): return False
        deadline = time.monotonic() + 2
        while owner._process.poll() is None and time.monotonic() < deadline: time.sleep(.1)
        if owner._process.poll() is not None: return False
        raise AppError('unavailable', 'Потеряно соединение с браузером агента. Закройте его окно и снова выберите чат.') from None
    if not handles: return False
    try: current = driver.current_window_handle
    except NoSuchWindowException: current = None
    if current in handles and (not bound or bound in handles): return True
    # Selenium needs a live context for new_window. Never navigate the surviving tab.
    driver.switch_to.window(handles[0]); driver.switch_to.new_window('tab')
    if driver.current_window_handle in handles:
        raise AppError('unavailable', 'Не удалось открыть отдельную вкладку агента. Повторите создание чата.')
    return True


def navigate(driver, url):
    if studio_route(url): return studio_navigation.navigate(driver, url)
    try:
        driver.switch_to.window(driver.current_window_handle)
        previous = driver.timeouts.page_load
        driver.set_page_load_timeout(10)
        try: driver.get(url)
        except TimeoutException: pass  # Caller checks the selected window and document.
        finally: driver.set_page_load_timeout(previous)
        return True
    except WebDriverException:
        return False
