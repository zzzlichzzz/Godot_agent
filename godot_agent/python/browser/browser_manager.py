import os
import time
import socket
import subprocess
import urllib.request

from selenium import webdriver

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
#
# v105 (чище отпечаток): свойства определяются на Document.prototype, а не на
# самом объекте document. Раньше они становились СОБСТВЕННЫМИ свойствами
# экземпляра — чего у настоящего Chrome нет, и подмена читалась одной строкой:
# Object.getOwnPropertyDescriptor(document, 'visibilityState') возвращал
# дескриптор вместо undefined.
VISIBILITY_SPOOF_JS = r"""(function() {
    try {
        var proto = Document.prototype;
        // Идемпотентность: скрипт выполняется при каждой отправке, и без этой
        // проверки на каждый прогон навешивалась бы ещё одна четвёрка
        // слушателей. Признак «уже стоит» берём из дескриптора геттера, а НЕ из
        // флага на window: своё свойство на window само стало бы приметой.
        var cur = Object.getOwnPropertyDescriptor(proto, 'visibilityState');
        if (cur && cur.get && String(cur.get).indexOf('__gdspoof') >= 0) return;
        var visGetter = function() { var __gdspoof = 1; return 'visible'; };
        var hidGetter = function() { var __gdspoof = 1; return false; };
        Object.defineProperty(proto, 'visibilityState', { get: visGetter, configurable: true });
        Object.defineProperty(proto, 'hidden', { get: hidGetter, configurable: true });
        // v105: hasFocus НЕ подменяем. document.hasFocus.toString() выдавал
        // "() => true" вместо "function hasFocus() { [native code] }" — проверка
        // toString() у нативных методов это классика антибот-фингерпринтинга.
        // Для рендера он не нужен: хватает visibilityState/hidden и глушения
        // событий ниже.
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

    ВАЖНО (v105): вызывать только для сайтов, которые читают ответ ИЗ DOM.
    Подмена свойств document — самый заметный след автоматизации из всего,
    что делает агент: она видна странице одной строкой JS. Сайтам, чей
    ответ читается из СЕТИ (BaseNetMonitor), рендер не нужен вовсе —
    троттлинг Chrome душит таймеры и рендер, но не сетевые потоки.
    Управляется флагом needs_visibility_spoof в sites.SITES.
    """
    # v105: регистрация «на будущие загрузки» делается ОДИН раз на вкладку.
    # Функция зовётся при каждой отправке, а Page.addScriptToEvaluateOnNewDocument
    # накапливает скрипты: после 50 отправок следующая же навигация выполнила бы
    # 50 копий. Сам скрипт теперь идемпотентен, так что лишние копии безвредны,
    # но плодить их в CDP незачем.
    handle = None
    try:
        handle = driver.current_window_handle
    except Exception:
        handle = None
    done = getattr(driver, "_gd_spoof_registered", None)
    if done is None:
        done = set()
        try:
            driver._gd_spoof_registered = done
        except Exception:
            done = None
    if done is None or handle not in done:
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": VISIBILITY_SPOOF_JS}
            )
            if done is not None:
                done.add(handle)
        except Exception as e:
            print(f"[browser_manager] Не удалось зарегистрировать visibility spoof на будущее: {e}")
    # На уже отрендеренный документ addScriptToEvaluateOnNewDocument не влияет,
    # поэтому применяем и напрямую (повторный вызов гасится проверкой в JS).
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
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = webdriver.Chrome(options=options)
    # v105: спуф видимости БОЛЬШЕ НЕ ставится вслепую при старте браузера.
    # Раньше он вешался здесь на стартовую вкладку (about:blank), а
    # Page.addScriptToEvaluateOnNewDocument живёт до закрытия вкладки — значит
    # ЛЮБОЙ сайт, открытый потом в этой же вкладке, получал подмену document
    # ещё до первого запроса. Троттлинг рендера при этом и так придавлен
    # флагами запуска выше (--disable-renderer-backgrounding и остальные).
    # Теперь спуф ставится точечно, по флагу сайта — см.
    # BaseSiteParser.send_message_and_get_response.
    return driver
