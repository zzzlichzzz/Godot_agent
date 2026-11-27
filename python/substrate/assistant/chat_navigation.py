"""Open browser chats. Studio verifies the selected window; other sites reuse an open tab."""
from python.substrate.llm.parsers import studio_navigation
from python.substrate.llm.parsers.studio_draft import studio_route


def navigate(driver, url):
    if studio_route(url):
        return studio_navigation.navigate(driver, url)
    try:
        driver.set_page_load_timeout(20)
        driver.set_script_timeout(10)
    except Exception:
        pass

    def address(u):
        return (u or '').split('://', 1)[-1].split('?', 1)[0].split('#', 1)[0].rstrip('/')

    try:
        current = driver.current_window_handle
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if address(driver.current_url) == address(url):
                return True
        driver.switch_to.window(current)
    except Exception:
        pass
    try:
        driver.switch_to.window(driver.window_handles[-1])
    except Exception:
        pass
    try:
        driver.execute_script('window.location.href = arguments[0];', url)
        return True
    except Exception:
        pass
    try:
        driver.set_page_load_timeout(10)
    except Exception:
        pass
    try:
        driver.get(url)
        return True
    except Exception:
        return False
