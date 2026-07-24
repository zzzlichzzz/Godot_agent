# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""\u0422\u0435\u0441\u0442\u044b v104.5: \u0432\u044b\u0431\u043e\u0440 \u043f\u043b\u0430\u043d\u0430 \u0432\u0441\u0442\u0430\u0432\u043a\u0438 \u043f\u043e \u0441\u0430\u0439\u0442\u0443 (PASTE_PLAN_A).
\u0420\u0435\u043f\u043e\u0440\u0442 24.07: AI Studio \u043f\u043e\u0441\u043b\u0435 \u044d\u043c\u0443\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u043e\u0433\u043e Ctrl+V \u043e\u0442\u0432\u0435\u0447\u0430\u0435\u0442 \u043e\u0448\u0438\u0431\u043a\u0430\u043c\u0438 \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u0438
(\u00abpermission denied\u00bb, \u00abAn internal error has occurred\u00bb), \u0430 \u0441\u043e \u0441\u0442\u0430\u0440\u043e\u0439 \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u043d\u043e\u0439
\u0432\u0441\u0442\u0430\u0432\u043a\u043e\u0439 \u043e\u0448\u0438\u0431\u043e\u043a \u043d\u0435 \u0431\u044b\u043b\u043e \u2014 \u0434\u043b\u044f \u043d\u0435\u0433\u043e \u043f\u043b\u0430\u043d \u0410 \u043e\u0442\u043a\u043b\u044e\u0447\u0451\u043d \u043f\u043e\u043b\u043d\u043e\u0441\u0442\u044c\u044e."""
import sys

import _fake_selenium
_fake_selenium.install()

import parser_base
import ai_parser
import kimi_parser
import qwen_parser
import deepseek_parser

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


class FakeDriver(object):
    def execute_script(self, script, *a):
        return None


class FakeEl(object):
    def click(self):
        pass


class NoPasteSite(parser_base.BaseSiteParser):
    LOG_TAG = "no_paste_site"
    PASTE_PLAN_A = False

    def __init__(self):
        self.paste_calls = 0
        self.insert_calls = 0

    def _log(self, msg):
        print("[no_paste_site] %s" % msg)

    def insert_input(self, driver, el, prompt):
        self.insert_calls += 1

    def insert_input_paste_like(self, driver, el, prompt):
        self.paste_calls += 1
        return True


# 1) \u043f\u0440\u0438 PASTE_PLAN_A = False \u044d\u043c\u0443\u043b\u044f\u0446\u0438\u044f Ctrl+V \u041d\u0415 \u0432\u044b\u0437\u044b\u0432\u0430\u0435\u0442\u0441\u044f \u0432\u043e\u043e\u0431\u0449\u0435
p = NoPasteSite()
mode = p.insert_input_for_send(FakeDriver(), FakeEl(), u"\u043c\u0435\u0433\u0430-\u043f\u0440\u043e\u043c\u043f\u0442 " * 1000)
check("PASTE_PLAN_A=False: \u0440\u0435\u0436\u0438\u043c 'insert'", mode == "insert")
check("PASTE_PLAN_A=False: Ctrl+V \u043d\u0435 \u0432\u044b\u0437\u044b\u0432\u0430\u043b\u0441\u044f \u041d\u0418 \u0420\u0410\u0417\u0423", p.paste_calls == 0)
check("PASTE_PLAN_A=False: \u0442\u0435\u043a\u0441\u0442 \u0432\u0441\u0442\u0430\u0432\u043b\u0435\u043d \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u043d\u043e \u043e\u0434\u0438\u043d \u0440\u0430\u0437", p.insert_calls == 1)


# 2) \u043f\u0440\u0438 PASTE_PLAN_A = True (\u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e) \u043f\u043b\u0430\u043d \u0410 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u043a\u0430\u043a \u0440\u0430\u043d\u044c\u0448\u0435
class PasteSite(NoPasteSite):
    LOG_TAG = "paste_site"
    PASTE_PLAN_A = True

    def _log(self, msg):
        print("[paste_site] %s" % msg)


p2 = PasteSite()
mode2 = p2.insert_input_for_send(FakeDriver(), FakeEl(), u"\u043f\u0440\u0438\u0432\u0435\u0442")
check("PASTE_PLAN_A=True: \u0440\u0435\u0436\u0438\u043c 'paste' (\u043f\u043e\u0432\u0435\u0434\u0435\u043d\u0438\u0435 \u043d\u0435 \u0438\u0437\u043c\u0435\u043d\u0438\u043b\u043e\u0441\u044c)", mode2 == "paste")
check("PASTE_PLAN_A=True: Ctrl+V \u0432\u044b\u0437\u0432\u0430\u043d \u043e\u0434\u0438\u043d \u0440\u0430\u0437", p2.paste_calls == 1)

# 3) \u0440\u0430\u0441\u043a\u043b\u0430\u0434\u043a\u0430 \u043f\u043e \u0440\u0435\u0430\u043b\u044c\u043d\u044b\u043c \u043f\u0430\u0440\u0441\u0435\u0440\u0430\u043c
check("AI Studio: \u044d\u043c\u0443\u043b\u044f\u0446\u0438\u044f Ctrl+V \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u0430", ai_parser.AiStudioParser.PASTE_PLAN_A is False)
check("kimi: Ctrl+V \u043e\u0441\u0442\u0430\u0432\u043b\u0435\u043d", getattr(kimi_parser.KimiParser, "PASTE_PLAN_A", True) is True)
check("qwen: Ctrl+V \u043e\u0441\u0442\u0430\u0432\u043b\u0435\u043d", getattr(qwen_parser.QwenParser, "PASTE_PLAN_A", True) is True)
check("deepseek: Ctrl+V \u043e\u0441\u0442\u0430\u0432\u043b\u0435\u043d", getattr(deepseek_parser.DeepSeekParser, "PASTE_PLAN_A", True) is True)

print()
if all(results):
    print("\u0412\u0421\u0415 \u0422\u0415\u0421\u0422\u042b \u041f\u0420\u041e\u0428\u041b\u0418 (%d/%d)" % (len(results), len(results)))
else:
    print("\u0415\u0421\u0422\u042c \u041f\u0410\u0414\u0415\u041d\u0418\u042f (%d/%d)" % (sum(results), len(results)))
    sys.exit(1)
