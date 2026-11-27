"""Navigate the selected agent window; a same-site home tab is not a restored chat."""
from selenium.common.exceptions import TimeoutException, WebDriverException
from python.substrate.llm.parsers import studio_navigation
from python.substrate.llm.parsers.studio_draft import studio_route


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
