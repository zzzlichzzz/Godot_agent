import os
import time
import socket
import subprocess
import urllib.request

from selenium import webdriver
# Явные статические импорты: PyInstaller не видит "ленивые" импорты selenium
# (selenium.webdriver.__getattr__), из-за чего собранный exe падал с ошибкой
# ModuleNotFoundError: No module named 'selenium.webdriver.chrome.options'.
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeDriver

# Стартовый адрес браузера. РАНЬШЕ здесь сразу открывался AI Studio —
# теперь браузер стартует на пустой странице, а конкретный сайт/чат
# выбирается уже из панели агента (стартовый экран → «Новый чат» / «Загрузиться»).
START_URL = "about:blank"


def find_chrome():
    """Ищет установленный Chrome в системе"""
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _wait_for_debug_port(port=9222, timeout=15.0):
    """Ждём, пока Chrome реально поднимет remote-debugging порт,
    вместо слепого sleep(3), который может не хватить на медленной машине
    или, наоборот, зря тратить время."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                pass
            # Порт открыт, но убедимся что HTTP-эндпоинт CDP тоже отвечает
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.5)
            return True
        except Exception:
            time.sleep(0.3)
    return False


# JS, который подменяет признаки "страница свёрнута/не в фокусе".
# Без этого Angular-приложение AI Studio может приостанавливать рендер
# ответа, когда окно Chrome свёрнуто или не активно — из-за этого парсер
# видит недорисованный DOM.
VISIBILITY_SPOOF_JS = r"""(function() {
    try {
        Object.defineProperty(document, 'visibilityState', { get: () => 'visible', configurable: true });
        Object.defineProperty(document, 'hidden', { get: () => false, configurable: true });
        Object.defineProperty(document, 'hasFocus', { value: () => true, configurable: true });
        const blockEvent = function(e) {
            if (e && e.stopImmediatePropagation) e.stopImmediatePropagation();
        };
        document.addEventListener('visibilitychange', blockEvent, true);
        window.addEventListener('blur', blockEvent, true);
        window.addEventListener('pagehide', blockEvent, true);
        window.addEventListener('freeze', blockEvent, true);
    } catch (e) {
        // тихо игнорируем — не должно ронять страницу
    }
})();"""


def harden_background_tab(driver):
    """
    1. Регистрирует spoof-скрипт на КАЖДУЮ будущую загрузку страницы
       (перезагрузка, переход по ссылке и т.п.) через CDP.
    2. Немедленно выполняет тот же скрипт на уже загруженной прямо сейчас
       странице — т.к. addScriptToEvaluateOnNewDocument не действует
       на уже отрендеренный документ.
    """
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": VISIBILITY_SPOOF_JS}
        )
    except Exception as e:
        print(f"[browser_manager] Не удалось зарегистрировать visibility spoof на будущее: {e}")
    try:
        driver.execute_script(VISIBILITY_SPOOF_JS)
    except Exception as e:
        print(f"[browser_manager] Не удалось применить visibility spoof к текущей странице: {e}")


def setup_browser():
    """Запускает браузер и возвращает объект драйвера"""
    chrome_path = find_chrome()
    if not chrome_path:
        raise Exception("Google Chrome не найден на этом ПК!")
    profile_dir = os.path.expandvars(r"%LOCALAPPDATA%\Godot_AI_Profile")
    # Если браузер агента уже запущен (порт отладки жив) — не открываем новый,
    # а просто подключаемся к существующему окну со всеми его вкладками.
    if _wait_for_debug_port(9222, timeout=1.0):
        print("1. Обнаружен уже запущенный браузер агента — подключаюсь к нему.")
    else:
        print("1. Запускаю выделенный браузер...")
        subprocess.Popen([
            chrome_path,
            '--remote-debugging-port=9222',
            f'--user-data-dir={profile_dir}',
            # Отключаем троттлинг фоновых/свёрнутых окон на уровне самого Chrome —
            # без этого движок таймеров и рендер могут замедляться, пока окно
            # свёрнуто или не в фокусе.
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-background-timer-throttling',
            # Windows иногда считает свёрнутое/перекрытое окно "occluded"
            # и дополнительно троттлит рендер — отключаем эту эвристику.
            '--disable-features=CalculateNativeWinOcclusion',
            START_URL
        ])
        print("2. Жду готовности remote-debugging порта...")
        if not _wait_for_debug_port(9222, timeout=20.0):
            print("⚠ Порт отладки Chrome не ответил вовремя, пробую подключиться всё равно...")
    print("3. Подключаю управление...")
    options = ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = ChromeDriver(options=options)
    print("4. Отключаю троттлинг рендера для фонового/свёрнутого окна...")
    harden_background_tab(driver)
    return driver
