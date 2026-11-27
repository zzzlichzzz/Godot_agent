"""SEC-19/20/R-21 pins: no contract slimming, new spoof, user-profile or URL escape."""
import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / 'contract/browser_stealth.json'
FORBIDDEN = ['navigator.webdriver', 'AutomationControlled', '--enable-automation',
             'excludeSwitches', 'useAutomationExtension', '--headless', 'hasFocus',
             'window.chrome', 'navigator.plugins', 'toString']


def _assert_contract(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['forbidden_techniques'] == FORBIDDEN
    assert data['launch']['mode'] == 'plain_process_then_attach'
    assert data['launch']['selenium_launches_browser'] is False
    assert data['webdriver_flag']['expected'] is False and data['webdriver_flag']['spoof_allowed'] is False
    assert data['profile']['path'] == '%LOCALAPPDATA%\\Godot_AI_Profile'
    assert data['profile']['user_profile_refused'] is True
    assert data['window_policy']['focus'] == 'no_steal' and data['window_policy']['tabs'] == 'own_window_only'
    assert data['window_policy']['offscreen_position'] is False
    assert data['allowed_masking'] == ['visibilityState', 'hidden']
    assert data['raise_spoof_without_proof'] is False
    assert {name: item['needs_visibility_spoof'] for name, item in data['sites'].items()} == {
        'aistudio': True, 'deepseek': True, 'qwen': True, 'kimi': False, 'arena': False, 'arena_battle': False}


def test_current_stealth_contract_has_all_immutable_pins():
    _assert_contract(CONTRACT)


def test_missing_contract_is_red(tmp_path):
    with pytest.raises(FileNotFoundError):
        _assert_contract(tmp_path / 'browser_stealth.json')


@pytest.mark.parametrize('index', range(10))
def test_each_forbidden_technique_cannot_be_removed(index, tmp_path):
    data = json.loads(CONTRACT.read_text(encoding='utf-8'))
    data['forbidden_techniques'].pop(index)
    path = tmp_path / 'browser_stealth.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(AssertionError):
        _assert_contract(path)


def test_facade_only_sends_approved_literal_primitive_commands():
    path = ROOT / 'python/substrate/llm/browser/facade.py'
    text = path.read_text(encoding='utf-8')
    assert len(text.splitlines()) <= 100
    tree = ast.parse(text)
    allowed = {'SystemInfo.getProcessInfo', 'Target.createTarget', 'Target.attachToTarget',
               'Target.closeTarget', 'Page.enable', 'Page.navigate', 'Runtime.evaluate', 'Browser.close'}
    methods = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'send_command':
            assert isinstance(node.args[0], ast.Constant)
            methods.add(node.args[0].value)
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
        assert name not in {'setup_browser', 'harden_background_tab', 'execute_script', 'execute_cdp_cmd'}
    assert methods == allowed


@pytest.mark.parametrize('name', ['Godot_AI_Profile', 'Godot_AI_Profile_B1_bad',
                                 'Google/Chrome/User Data', 'Godot_AI_Profile_B1_' + 'z' * 32])
def test_arbitrary_or_production_profile_override_is_refused(name, b1_browser_env):
    env = b1_browser_env()
    with pytest.raises(ValueError):
        env.module.ReadOnlyBrowser('fake-chrome.exe', live_profile=env.local / name)
    assert env.launch_args is None


def test_live_profile_outside_dedicated_parent_is_refused(b1_browser_env, tmp_path):
    env = b1_browser_env()
    profile = tmp_path / ('Godot_AI_Profile_B1_' + 'a' * 32)
    profile.mkdir()
    with pytest.raises(ValueError):
        env.module.ReadOnlyBrowser('fake-chrome.exe', live_profile=profile)
    assert env.launch_args is None


def test_nonempty_live_profile_is_refused_without_launch(b1_browser_env):
    env = b1_browser_env()
    profile = env.local / ('Godot_AI_Profile_B1_' + 'a' * 32)
    profile.mkdir()
    (profile / 'sentinel.txt').write_bytes(b'own test data')
    with pytest.raises(ValueError):
        env.module.ReadOnlyBrowser('fake-chrome.exe', live_profile=profile)
    assert env.launch_args is None and (profile / 'sentinel.txt').read_bytes() == b'own test data'


def test_read_only_api_does_not_expose_mutating_backend_handles(b1_browser_env):
    env = b1_browser_env()
    with env.module.ReadOnlyBrowser('fake-chrome.exe', 'fake-driver.exe') as browser:
        assert all(name.startswith('_') for name in vars(browser))
