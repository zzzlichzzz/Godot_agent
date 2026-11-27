"""D33 wait_driver seam: no server STATE and no driver without a D24 owner."""
import threading
import time

from .browser.facade import ReadOnlyBrowser

_LOCK = threading.Lock()
_holder = {'owner': None, 'driver_error': None}
_boot = {'started': False, 'fn': None, 'thread': None}


def _live_driver(owner):
    if not isinstance(owner, ReadOnlyBrowser):
        raise TypeError('browser owner must be ReadOnlyBrowser')
    process, driver = getattr(owner, '_process', None), getattr(owner, '_driver', None)
    if not getattr(owner, '_owned', False) or process is None or process.poll() is not None or driver is None:
        raise RuntimeError('owned Chrome is not live and attached')
    return driver


def bind_owner(owner):
    """Publish the facade, not an arbitrary Selenium driver; no ownership transfer."""
    with _LOCK:
        _live_driver(owner)
        previous = _holder['owner']
        if previous is not None and previous is not owner:
            raise RuntimeError('browser owner already bound')
        _holder['owner'], _holder['driver_error'] = owner, None
        _boot['started'] = True


def release_owner(owner):
    """Unpublish only this identity; the caller still closes its own facade."""
    with _LOCK:
        if _holder['owner'] is not owner:
            raise RuntimeError('foreign browser owner')
        _holder['owner'], _holder['driver_error'] = None, 'browser owner released'


def set_browser_booter(fn):
    """Trusted zero-argument callable returning ReadOnlyBrowser; not executed here."""
    if not callable(fn):
        raise TypeError('browser booter must be callable')
    with _LOCK:
        if _boot['started']:
            raise RuntimeError('browser boot already started')
        _boot['fn'] = fn


def _run_boot(fn):
    try:
        bind_owner(fn())
    except Exception as error:
        with _LOCK:
            _holder['driver_error'] = str(error) or type(error).__name__


def ensure_browser_booting():
    """Single-shot native demand-start; no retries, profiles, flags or launch code."""
    with _LOCK:
        if _boot['started'] or _boot['fn'] is None:
            return
        _boot['started'] = True
        thread = threading.Thread(target=_run_boot, args=(_boot['fn'],),
                                  daemon=True, name='browser-runtime-boot')
        _boot['thread'] = thread
        thread.start()


def wait_driver(timeout=90.0):
    """Native deadline/messages/polling, strengthened only by D24 ownership."""
    ensure_browser_booting()
    deadline = time.time() + timeout
    while time.time() < deadline:
        with _LOCK:
            owner = _holder['owner']
            if owner is not None:
                try:
                    return _live_driver(owner)
                except RuntimeError as error:
                    _holder['driver_error'] = str(error)
            error = _holder['driver_error']
        if error:
            raise RuntimeError('Браузер агента не запустился: %s' % error)
        time.sleep(0.25)
    raise RuntimeError('Браузер агента ещё запускается — подождите пару секунд и повторите.')
