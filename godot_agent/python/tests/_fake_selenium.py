# -*- coding: utf-8 -*-
"""Заглушки selenium для оффлайн-тестов (общий помощник, не тест).
Импортировать ДО parser_base/kimi_parser/qwen_parser."""
import sys
import types


def install():
    if "selenium" in sys.modules:
        return
    sel = types.ModuleType("selenium")
    sel_common = types.ModuleType("selenium.common")
    sel_exc = types.ModuleType("selenium.common.exceptions")

    class JavascriptException(Exception):
        pass

    class StaleElementReferenceException(Exception):
        pass

    class WebDriverException(Exception):
        pass

    sel_exc.JavascriptException = JavascriptException
    sel_exc.StaleElementReferenceException = StaleElementReferenceException
    sel_exc.WebDriverException = WebDriverException

    sel_wd = types.ModuleType("selenium.webdriver")
    sel_wd_common = types.ModuleType("selenium.webdriver.common")
    sel_keys = types.ModuleType("selenium.webdriver.common.keys")
    sel_ac = types.ModuleType("selenium.webdriver.common.action_chains")

    class Keys(object):
        CONTROL = u"\ue009"
        SHIFT = u"\ue008"
        BACKSPACE = u"\ue003"
        ENTER = u"\ue007"
        SPACE = u" "

    class ActionChains(object):
        def __init__(self, driver):
            pass

        def key_down(self, *a):
            return self

        def send_keys(self, *a):
            return self

        def key_up(self, *a):
            return self

        def perform(self):
            pass

    sel_keys.Keys = Keys
    sel_ac.ActionChains = ActionChains

    sys.modules["selenium"] = sel
    sys.modules["selenium.common"] = sel_common
    sys.modules["selenium.common.exceptions"] = sel_exc
    sys.modules["selenium.webdriver"] = sel_wd
    sys.modules["selenium.webdriver.common"] = sel_wd_common
    sys.modules["selenium.webdriver.common.keys"] = sel_keys
    sys.modules["selenium.webdriver.common.action_chains"] = sel_ac
