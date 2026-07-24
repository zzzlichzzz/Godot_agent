# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Оффлайн-тест v88.16: починка «плана А» (Ctrl+V) и лестница paste->type->insert."""
import sys
import time as _time
import types

# --- заглушки selenium до импорта parser_base ---
CTRL = u"\ue009"
BKSP = u"\ue003"

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

class Keys(object):
    CONTROL = CTRL
    BACKSPACE = BKSP
    ENTER = u"\ue007"
    SPACE = u" "

sel_keys.Keys = Keys

sys.modules["selenium"] = sel
sys.modules["selenium.common"] = sel_common
sys.modules["selenium.common.exceptions"] = sel_exc
sys.modules["selenium.webdriver"] = sel_wd
sys.modules["selenium.webdriver.common"] = sel_wd_common
sys.modules["selenium.webdriver.common.keys"] = sel_keys

import parser_base


class FakeDriver(object):
    def __init__(self, st):
        self.st = st

    def _field(self):
        st = self.st
        pp = st.get("pending_paste")
        if pp:
            content, t0, dur = pp
            frac = 1.0 if dur <= 0 else min(1.0, (_time.time() - t0) / dur)
            visible = st["field"] + content[: int(len(content) * frac)]
            if frac >= 1.0:
                st["field"] = st["field"] + content
                st["pending_paste"] = None
            return visible
        return st["field"]

    def execute_script(self, script, *args):
        if "location.origin" in script:
            return "https://chat.qwen.ai"
        if "TEXTAREA" in script or "innerText" in script:
            return self._field()
        return None

    def execute_async_script(self, script, *args):
        st = self.st
        if "writeText" in script:
            mode = st.get("clip_write_mode", "ok")
            if mode == "fail":
                return False
            if mode == "stale":
                return True  # заявляет успех, но буфер не меняется
            st["clipboard"] = args[0]
            return True
        if "readText" in script:
            if not st.get("clip_readable", True):
                return None
            return st.get("clipboard", "")
        return None

    def execute_cdp_cmd(self, *a, **k):
        pass


class FakeEl(object):
    def __init__(self, st):
        self.st = st

    def click(self):
        pass

    def clear(self):
        self.st["field"] = ""

    def send_keys(self, *keys):
        st = self.st
        joined = u"".join(keys)
        if CTRL in joined:
            rest = joined.replace(CTRL, u"")
            if rest == u"a":
                st["selected"] = True
            elif rest == u"v":
                mode = st.get("paste_mode", "ok")
                if st.get("selected"):
                    st["field"] = u""
                    st["selected"] = False
                if mode == "ok":
                    st["pending_paste"] = (st.get("clipboard", u""), _time.time(), st.get("paste_dur", 0.0))
                elif mode == "junk":
                    st["field"] += u"x" * 50
            return
        if joined and set(joined) == {BKSP}:
            if st.get("selected"):
                st["field"] = u""
                st["selected"] = False
            else:
                st["field"] = st["field"][: max(0, len(st["field"]) - len(joined))]
            return
        if st.get("selected"):
            st["field"] = u""
            st["selected"] = False
        st["field"] += joined


class P(parser_base.BaseSiteParser):
    LOG_TAG = "test"

    def __init__(self, st):
        self.st = st

    def insert_input(self, driver, el, prompt):
        self.st["field"] = prompt


def run_case(name, st, prompt, expect_mode, expect_field=True):
    driver = FakeDriver(st)
    el = FakeEl(st)
    p = P(st)
    t0 = _time.time()
    mode = p.insert_input_for_send(driver, el, prompt)
    dt = _time.time() - t0
    field_ok = p._insert_text_matches(driver._field(), prompt)
    ok = (mode == expect_mode) and (field_ok == expect_field)
    print("%s: mode=%s (ожидали %s), поле совпало=%s, %.1f c -> %s"
          % (name, mode, expect_mode, field_ok, dt, "OK" if ok else "FAIL"))
    return ok


results = []

# 1) Большая вставка 22 КБ, редактор «дожёвывает» её 1.2 с (кейс из репорта)
st = {"field": u"", "paste_mode": "ok", "paste_dur": 1.2}
results.append(run_case("1. большой paste с задержкой UI", st, u"A" * 22198, "paste"))

# 2) Клипборд «залип»: writeText врёт об успехе, в буфере старый текст
st = {"field": u"", "clip_write_mode": "stale", "clipboard": u"OLD_CLIP_CONTENT_50_CHARS_XXXXXXXXXXXXXXXXXXXXXXXX"}
results.append(run_case("2. залипший буфер -> быстрый insert_input (v104.2)", st, u"Привет, мир! " * 30, "insert"))

# 3) Ctrl+V вставляет мусор (сайт глотает paste) — малый текст -> печать
st = {"field": u"", "paste_mode": "junk"}
results.append(run_case("3. paste-мусор -> быстрый insert_input (v104.2)", st, u"S" * 500, "insert"))

# 4) Ctrl+V вставляет мусор, текст огромный -> последний резерв insert_input
st = {"field": u"", "paste_mode": "junk"}
results.append(run_case("4. paste-мусор, 9000 симв. -> JS-резерв", st, u"B" * 9000, "insert"))

# 5) Живой ввод (mirror_input) по-прежнему печатает клавишами
st = {"field": u"черновик"}
p = P(st)
ok5 = p._mirror_type_human(FakeDriver(st), FakeEl(st), u"черновик текста дальше")
print("5. живой ввод клавишами (diff): %s -> %s" % (st["field"], "OK" if ok5 and st["field"] == u"черновик текста дальше" else "FAIL"))
results.append(ok5 and st["field"] == u"черновик текста дальше")

print("\nИТОГО: %d/%d OK" % (sum(1 for r in results if r), len(results)))
sys.exit(0 if all(results) else 1)
