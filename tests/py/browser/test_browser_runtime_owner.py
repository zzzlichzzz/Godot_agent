"""Native polling/messages over D24-owned facade, without real Chrome launches."""
import importlib
from types import SimpleNamespace

import pytest

from tests.py.browser import runtime_cases as runtime


@pytest.fixture
def owner_runtime(b1_browser_env):
    env = b1_browser_env()
    owner = env.module.ReadOnlyBrowser('inert-chrome', 'inert-driver')
    try:
        with runtime.references():
            seam = importlib.import_module('python.substrate.llm.runtime_owner')
            yield seam, owner, env
    finally:
        owner.close()


def test_ready_owner_returns_exact_driver_and_no_extra_launch(owner_runtime):
    seam, owner, env = owner_runtime
    seam.bind_owner(owner)
    assert seam.wait_driver() is owner._driver
    assert env.calls.count(('Popen',)) == 1
    assert not hasattr(seam, 'STATE') and not hasattr(seam, 'set_driver')


@pytest.mark.parametrize('timeout', [0, -1])
def test_zero_negative_deadline_never_reads_ready_holder(owner_runtime, monkeypatch, timeout):
    seam, owner, _ = owner_runtime
    seam.bind_owner(owner)
    clock = runtime.Clock()
    monkeypatch.setattr(seam, 'time', clock)
    with pytest.raises(RuntimeError, match='Браузер агента ещё запускается — подождите пару секунд и повторите.'):
        seam.wait_driver(timeout)
    assert clock.sleeps == []


def test_polling_publishes_owner_on_next_quarter_second(owner_runtime, monkeypatch):
    seam, owner, _ = owner_runtime
    clock = runtime.Clock()
    sleep = clock.sleep
    def publish(seconds):
        sleep(seconds)
        seam.bind_owner(owner)
    clock.sleep = publish
    monkeypatch.setattr(seam, 'time', clock)
    assert seam.wait_driver(1) is owner._driver
    assert clock.sleeps == [.25]


def test_timeout_is_native_message_and_poll_interval(owner_runtime, monkeypatch):
    seam, _, _ = owner_runtime
    clock = runtime.Clock()
    monkeypatch.setattr(seam, 'time', clock)
    with pytest.raises(RuntimeError, match='ещё запускается'):
        seam.wait_driver(1)
    assert clock.sleeps == [.25] * 4


def test_raw_driver_cannot_bypass_d24_owner(owner_runtime):
    seam, owner, _ = owner_runtime
    with pytest.raises(TypeError, match='ReadOnlyBrowser'):
        seam.bind_owner(owner._driver)
    assert seam._holder['owner'] is None


@pytest.mark.parametrize('invalid', ['unowned', 'dead', 'no-driver'])
def test_owner_must_be_verified_live_and_attached(owner_runtime, invalid):
    seam, owner, _ = owner_runtime
    if invalid == 'unowned':
        owner._owned = False
    elif invalid == 'dead':
        owner._process.returncode = 0
    else:
        owner._driver = None
    with pytest.raises(RuntimeError, match='owned Chrome is not live and attached'):
        seam.bind_owner(owner)
    assert seam._holder['owner'] is None


def test_closed_owner_never_leaks_stale_driver(owner_runtime):
    seam, owner, _ = owner_runtime
    seam.bind_owner(owner)
    owner.close()
    with pytest.raises(RuntimeError, match='Браузер агента не запустился: owned Chrome is not live and attached'):
        seam.wait_driver(.1)


def test_owner_priority_over_old_error_matches_native(owner_runtime):
    seam, owner, _ = owner_runtime
    seam.bind_owner(owner)
    seam._holder['driver_error'] = 'previous failure'
    assert seam.wait_driver() is owner._driver


def test_release_is_identity_checked_and_does_not_close_browser(owner_runtime):
    seam, owner, _ = owner_runtime
    seam.bind_owner(owner)
    with pytest.raises(RuntimeError, match='foreign browser owner'):
        seam.release_owner(object())
    driver = owner._driver
    seam.release_owner(owner)
    assert owner._driver is driver and owner._process.poll() is None
    with pytest.raises(RuntimeError, match='browser owner released'):
        seam.wait_driver(.1)


def test_cannot_replace_active_owner(owner_runtime):
    seam, owner, _ = owner_runtime
    seam.bind_owner(owner)
    from python.substrate.llm.browser.facade import ReadOnlyBrowser
    other = object.__new__(ReadOnlyBrowser)
    other._owned, other._process, other._driver = True, owner._process, owner._driver
    with pytest.raises(RuntimeError, match='browser owner already bound'):
        seam.bind_owner(other)
    assert seam.wait_driver() is owner._driver


def test_boot_is_explicit_lazy_and_single_shot(owner_runtime):
    seam, owner, _ = owner_runtime
    calls = []
    seam.set_browser_booter(lambda: calls.append('boot') or owner)
    assert calls == [] and seam._holder['owner'] is None
    seam.ensure_browser_booting()
    thread = seam._boot['thread']
    thread.join(2)
    assert not thread.is_alive()
    assert seam.wait_driver(.5) is owner._driver
    seam.ensure_browser_booting()
    assert calls == ['boot'] and seam._boot['thread'] is thread


def test_boot_failure_reports_native_error_without_retry(owner_runtime):
    seam, _, _ = owner_runtime
    calls = []
    def fail():
        calls.append('boot')
        raise RuntimeError('inert launch failed')
    seam.set_browser_booter(fail)
    seam.ensure_browser_booting()
    seam._boot['thread'].join(2)
    with pytest.raises(RuntimeError, match='Браузер агента не запустился: inert launch failed'):
        seam.wait_driver(.5)
    assert calls == ['boot']


def test_boot_cannot_be_reconfigured_after_start(owner_runtime):
    seam, owner, _ = owner_runtime
    seam.bind_owner(owner)
    with pytest.raises(RuntimeError, match='browser boot already started'):
        seam.set_browser_booter(lambda: owner)


def test_backend_calls_real_owner_seam_and_preserves_response_identity(owner_runtime):
    seam, owner, _ = owner_runtime
    seam.bind_owner(owner)
    backend = importlib.import_module('python.substrate.llm.browser.backends.browser_backend')
    calls, response = [], {'text': 'ёж', 'action': None}
    def send(driver, prompt, **kwargs):
        calls.append((driver, prompt, kwargs))
        return response
    parser = SimpleNamespace(send_message_and_get_response=send)
    progress, cancel = lambda _: None, lambda: False
    assert backend.BrowserBackend(parser).send('prompt', progress, cancel, 'http://127.0.0.1/owned') is response
    assert calls == [(owner._driver, 'prompt', {'progress_cb': progress, 'cancel_cb': cancel,
                                             'prefer_url': 'http://127.0.0.1/owned'})]
