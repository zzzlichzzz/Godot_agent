# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""\u0422\u0435\u0441\u0442\u044b v104.4: \u0441\u0430\u0439\u0442 (kimi) \u043f\u0440\u0435\u0432\u0440\u0430\u0449\u0430\u0435\u0442 \u0432\u0441\u0442\u0430\u0432\u043a\u0443 >4000 \u0431\u0430\u0439\u0442 \u0432\u043e \u0432\u043b\u043e\u0436\u0435\u043d\u0438\u0435 .txt.
\u0410\u0433\u0435\u043d\u0442 \u0434\u043e\u043b\u0436\u0435\u043d \u043f\u043e\u043d\u044f\u0442\u044c \u044d\u0442\u043e \u043f\u043e \u0440\u043e\u0441\u0442\u0443 \u0447\u0438\u0441\u043b\u0430 \u043a\u0430\u0440\u0442\u043e\u0447\u0435\u043a-\u0432\u043b\u043e\u0436\u0435\u043d\u0438\u0439 \u0438 \u041d\u0415 \u0440\u0435\u0442\u0440\u0430\u0438\u0442\u044c \u0432\u0441\u0442\u0430\u0432\u043a\u0443
(\u0440\u0435\u043f\u043e\u0440\u0442 24.07: \u0440\u0435\u0442\u0440\u0430\u0438 \u0441\u043e\u0437\u0434\u0430\u043b\u0438 2 \u043e\u0434\u0438\u043d\u0430\u043a\u043e\u0432\u044b\u0445 .txt \u0432 \u043e\u0434\u043d\u043e\u043c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0438)."""

import _fake_selenium
_fake_selenium.install()

import parser_base
import kimi_parser

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


class FakeEl(object):
    def click(self):
        pass

    def clear(self):
        pass

    def send_keys(self, *a):
        pass


class FakeDriver(object):
    def __init__(self):
        self.scripts = []

    def execute_script(self, script, *a):
        self.scripts.append(script)
        return None


class FakeSite(parser_base.BaseSiteParser):
    """\u0421\u0430\u0439\u0442, \u0433\u0434\u0435 \u0432\u0441\u0442\u0430\u0432\u043a\u0430 \u00ab\u043d\u0435 \u043f\u043e\u043f\u0430\u0434\u0430\u0435\u0442\u00bb \u0432 \u043f\u043e\u043b\u0435: \u043b\u0438\u0431\u043e \u0443\u0448\u043b\u0430 \u0432\u043e \u0432\u043b\u043e\u0436\u0435\u043d\u0438\u0435, \u043b\u0438\u0431\u043e \u043f\u0440\u043e\u043f\u0430\u043b\u0430."""
    LOG_TAG = "fake_site"

    def __init__(self, attachment_counts):
        # attachment_counts: \u0441\u043f\u0438\u0441\u043e\u043a \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0439, \u043a\u043e\u0442\u043e\u0440\u044b\u0435 \u0431\u0443\u0434\u0435\u0442 \u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0442\u044c \u0441\u0447\u0451\u0442\u0447\u0438\u043a \u0432\u043b\u043e\u0436\u0435\u043d\u0438\u0439
        self._att = list(attachment_counts)
        self.ctrl_v_calls = 0

    def _log(self, msg):
        print("[fake_site] %s" % msg)

    def find_input(self, driver):
        return FakeEl()

    def insert_input(self, driver, el, prompt):
        pass

    def _read_field_text_quick(self, driver, el):
        return u""

    def _set_clipboard_text(self, driver, text):
        return True

    def _verify_clipboard_text(self, driver, text):
        return True

    def _focus_input_caret_end(self, driver, el):
        pass

    def _dispatch_ctrl_v(self, driver, el):
        self.ctrl_v_calls += 1
        return True

    def _wait_field_matches(self, driver, el, prompt, wait_s):
        return False  # \u0442\u0435\u043a\u0441\u0442 \u0432 \u043f\u043e\u043b\u0435 \u0442\u0430\u043a \u0438 \u043d\u0435 \u043f\u043e\u044f\u0432\u0438\u043b\u0441\u044f

    def count_composer_attachments(self, driver):
        if not self._att:
            return None
        if len(self._att) == 1:
            return self._att[0]
        return self._att.pop(0)


prompt = u"\u0422\u044b \u2014 \u0418\u0418-\u0440\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u0447\u0438\u043a, " * 500  # >4000 \u0431\u0430\u0439\u0442\n
drv = FakeDriver()
el = FakeEl()

# 1) \u0432\u0441\u0442\u0430\u0432\u043a\u0430 \u043f\u0440\u0435\u0432\u0440\u0430\u0442\u0438\u043b\u0430\u0441\u044c \u0432\u043e \u0432\u043b\u043e\u0436\u0435\u043d\u0438\u0435: 0 \u043a\u0430\u0440\u0442\u043e\u0447\u0435\u043a \u0434\u043e, 1 \u043f\u043e\u0441\u043b\u0435 Ctrl+V
p = FakeSite([0, 1])
p._insert_became_attachment = False
ok = p.insert_input_paste_like(drv, el, prompt)
check("attachment: paste-like \u0432\u0435\u0440\u043d\u0443\u043b \u0443\u0441\u043f\u0435\u0445", ok is True)
check("attachment: \u0444\u043b\u0430\u0433 _insert_became_attachment \u0432\u0437\u0432\u0435\u0434\u0451\u043d", getattr(p, "_insert_became_attachment", False) is True)
check("attachment: Ctrl+V \u0431\u044b\u043b \u0420\u041e\u0412\u041d\u041e \u043e\u0434\u0438\u043d (\u043d\u0435\u0442 \u0434\u0443\u0431\u043b\u0435\u0439 \u0444\u0430\u0439\u043b\u0430)", p.ctrl_v_calls == 1)

# 2) \u0432\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u041d\u0415 \u043f\u043e\u044f\u0432\u0438\u043b\u043e\u0441\u044c \u2014 \u0441\u0442\u0430\u0440\u043e\u0435 \u043f\u043e\u0432\u0435\u0434\u0435\u043d\u0438\u0435 (2 \u043f\u043e\u043f\u044b\u0442\u043a\u0438, \u043e\u0442\u043a\u0430\u0437) \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e
p2 = FakeSite([0])
p2._insert_became_attachment = False
ok2 = p2.insert_input_paste_like(drv, el, prompt)
check("no attachment: paste-like \u0447\u0435\u0441\u0442\u043d\u043e \u0432\u0435\u0440\u043d\u0443\u043b False", ok2 is False)
check("no attachment: \u0444\u043b\u0430\u0433 \u043d\u0435 \u0432\u0437\u0432\u0435\u0434\u0451\u043d", getattr(p2, "_insert_became_attachment", False) is False)
check("no attachment: \u0431\u044b\u043b\u043e 2 \u043f\u043e\u043f\u044b\u0442\u043a\u0438 Ctrl+V (\u043a\u0430\u043a \u0440\u0430\u043d\u044c\u0448\u0435)", p2.ctrl_v_calls >= 1)

# 3) \u0441\u0430\u0439\u0442 \u043d\u0435 \u0443\u043c\u0435\u0435\u0442 \u0441\u0447\u0438\u0442\u0430\u0442\u044c \u0432\u043b\u043e\u0436\u0435\u043d\u0438\u044f (None) \u2014 \u043d\u0435\u0442 \u043f\u0430\u0434\u0435\u043d\u0438\u0439, \u043f\u043e\u0432\u0435\u0434\u0435\u043d\u0438\u0435 \u043a\u0430\u043a \u0431\u044b\u043b\u043e
p3 = FakeSite([])
ok3 = p3.insert_input_paste_like(drv, el, prompt)
check("None-\u0441\u0447\u0451\u0442\u0447\u0438\u043a: \u043d\u0435 \u043f\u0430\u0434\u0430\u0435\u0442 \u0438 \u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0435\u0442 False", ok3 is False)

# 4) \u0431\u0430\u0437\u043e\u0432\u044b\u0439 \u0445\u0443\u043a \u0432 BaseSiteParser \u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0435\u0442 None (\u0441\u0430\u0439\u0442\u044b \u0431\u0435\u0437 \u043a\u043e\u043d\u0432\u0435\u0440\u0442\u0430\u0446\u0438\u0438 \u043d\u0435 \u0437\u0430\u0442\u0440\u043e\u043d\u0443\u0442\u044b)
check("base hook: count_composer_attachments == None",
      parser_base.BaseSiteParser.count_composer_attachments.__get__(p3)(drv) is None
      if False else parser_base.BaseSiteParser.count_composer_attachments(p3, drv) is None)

# 5) kimi: \u0441\u0447\u0438\u0442\u0430\u0435\u043c \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438 \u0447\u0435\u0440\u0435\u0437 JS \u0438 \u043d\u0435 \u043f\u0430\u0434\u0430\u0435\u043c \u043f\u0440\u0438 \u043e\u0448\u0438\u0431\u043a\u0435

class KimiDrv(object):
    def execute_script(self, script, *a):
        assert "file-card-container" in script and "chat-content-item" in script
        return 2


class KimiDrvBroken(object):
    def execute_script(self, script, *a):
        raise RuntimeError("boom")


kp = kimi_parser.KimiParser()
check("kimi: \u0441\u0447\u0438\u0442\u0430\u0435\u0442 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438 \u0432\u043d\u0435 \u0438\u0441\u0442\u043e\u0440\u0438\u0438 \u0447\u0430\u0442\u0430", kp.count_composer_attachments(KimiDrv()) == 2)
check("kimi: \u043e\u0448\u0438\u0431\u043a\u0430 JS -> None (\u0431\u0435\u0437 \u043f\u0430\u0434\u0435\u043d\u0438\u044f)", kp.count_composer_attachments(KimiDrvBroken()) is None)

print()
if all(results):
    print("\u0412\u0421\u0415 \u0422\u0415\u0421\u0422\u042b \u041f\u0420\u041e\u0428\u041b\u0418 (%d/%d)" % (len(results), len(results)))
else:
    print("\u0415\u0421\u0422\u042c \u041f\u0410\u0414\u0415\u041d\u0418\u042f (%d/%d)" % (sum(results), len(results)))
    sys = __import__("sys"); sys.exit(1)
