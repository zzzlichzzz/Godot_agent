# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты барьера секретов и уважения Retry-After.

Два разных вопроса, но оба про то, чтобы сервер вёл себя честно:
  * ключ не должен попадать в журнал /dashboard, кем бы он ни был напечатан;
  * если провайдер сказал, сколько ждать, ждать надо ровно столько, а не
    угадывать по своему расписанию.
"""
import shutil
import sys
import tempfile

CFG = tempfile.mkdtemp(prefix="agent_cfg_secrets_")
_os0.environ["GODOT_AGENT_CONFIG_DIR"] = CFG

import api_keys
import dashboard
import rate_limit

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


KEY = "sk-or-v1-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
PROXY_PASS = "pr0xy-Passw0rd-long-enough"

# ---------------------------------------------------------------------------
# 1) redact знает про ключи и пароль прокси
# ---------------------------------------------------------------------------
check(u"без ключей redact ничего не меняет",
      api_keys.redact(u"обычная строка") == u"обычная строка")

api_keys.set_key("openrouter", KEY)
api_keys.set_proxy(enabled=True, host="p.local", port=3128, user="u",
                   password=PROXY_PASS)

masked = api_keys.redact(u"Authorization: Bearer %s" % KEY)
check(u"ключ из заголовка замаскирован", KEY not in masked, masked)
check(u"маска узнаваема", masked.startswith(u"Authorization: Bearer sk-or-"))
check(u"пароль прокси замаскирован",
      PROXY_PASS not in api_keys.redact(u"proxy http://u:%s@p.local" % PROXY_PASS))
check(u"несколько секретов в одной строке",
      KEY not in api_keys.redact(KEY + " и " + PROXY_PASS)
      and PROXY_PASS not in api_keys.redact(KEY + " и " + PROXY_PASS))

# ---------------------------------------------------------------------------
# 2) Кэш секретов сбрасывается при изменении настроек
# ---------------------------------------------------------------------------
NEW_KEY = "gsk_ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ9999"
api_keys.set_key("groq", NEW_KEY)
check(u"новый ключ маскируется сразу (кэш сброшен)",
      NEW_KEY not in api_keys.redact(u"key=" + NEW_KEY))
api_keys.delete_key("groq")
check(u"после удаления ключа он больше не в списке секретов",
      api_keys.redact(u"key=" + NEW_KEY) == u"key=" + NEW_KEY)

# ---------------------------------------------------------------------------
# 3) Барьер в журнале /dashboard
# ---------------------------------------------------------------------------
# Перехватчик вывода ставит main.py при старте сервера; здесь ставим сами,
# потому что проверяем именно его поведение.
dashboard.install()
before = len(dashboard.get_lines())
print(u"[test] отладочный вывод с ключом: Bearer %s конец" % KEY)
print(u"[test] и с паролем прокси: %s конец" % PROXY_PASS)
lines = dashboard.get_lines()[before:]
joined = u"\n".join(lines)
check(u"строки попали в журнал дашборда", len(lines) >= 2, lines)
check(u"КЛЮЧА в журнале /dashboard нет", KEY not in joined)
check(u"пароля прокси в журнале нет", PROXY_PASS not in joined)
check(u"остальной текст строки сохранён", u"отладочный вывод" in joined)
check(u"в журнале видна маска, а не пустое место", u"sk-or-" in joined)

# 3b) Испорченный файл настроек не уводит вывод в бесконечную рекурсию:
# api_keys печатает предупреждение, а печать снова идёт через маскирование.
with open(api_keys.config_path(), "w", encoding="utf-8") as f:
    f.write("{ это не json")
api_keys._invalidate_secrets()
crashed = False
try:
    print(u"[test] строка при испорченном файле настроек")
except RecursionError:
    crashed = True
check(u"испорченный файл настроек не роняет вывод сервера", not crashed)
check(u"строка всё равно попала в журнал",
      any(u"испорченном файле" in ln for ln in dashboard.get_lines()[-6:]))
_os0.remove(api_keys.config_path())
api_keys._invalidate_secrets()

# ---------------------------------------------------------------------------
# 4) Расписание пауз без Retry-After — как было
# ---------------------------------------------------------------------------
check(u"паузы по-прежнему 30/60/120/300",
      [rate_limit.sleep_seconds(i) for i in range(4)] == [30, 60, 120, 300])
check(u"после исчерпания попыток — остановка",
      rate_limit.sleep_seconds(4) is None and rate_limit.sleep_seconds(-1) is None)

# ---------------------------------------------------------------------------
# 5) Retry-After уважается
# ---------------------------------------------------------------------------
check(u"Retry-After побеждает расписание",
      rate_limit.sleep_seconds(0, retry_after=7) == 7)
check(u"Retry-After действует и на поздних попытках",
      rate_limit.sleep_seconds(3, retry_after=12) == 12)
check(u"Retry-After = 0 -> ждём минимум 1 с, а не мгновенный повтор",
      rate_limit.sleep_seconds(0, retry_after=0) == 1)
check(u"Retry-After строкой (как в заголовке)",
      rate_limit.sleep_seconds(0, retry_after="15") == 15)
check(u"мусорный Retry-After -> расписание",
      rate_limit.sleep_seconds(0, retry_after=u"позже") == 30)
check(u"отрицательный Retry-After -> расписание",
      rate_limit.sleep_seconds(1, retry_after=-5) == 60)

# ---------------------------------------------------------------------------
# 6) Слишком долгое ожидание -> честная остановка
# ---------------------------------------------------------------------------
check(u"порог ожидания задан", rate_limit.MAX_HONORED_RETRY_AFTER == 300)
check(u"на пределе порога ещё ждём",
      rate_limit.sleep_seconds(0, retry_after=300) == 300)
check(u"суточный лимит (час ожидания) -> остановка, а не блокировка редактора",
      rate_limit.sleep_seconds(0, retry_after=3600) is None)
check(u"бюджет попыток действует и с Retry-After (нет бесконечного цикла)",
      rate_limit.sleep_seconds(4, retry_after=5) is None)

api_keys.delete_key("openrouter")
api_keys.set_proxy(enabled=False, password="")
shutil.rmtree(CFG, ignore_errors=True)

n_ok = sum(1 for r in results if r)
# Итог печатаем в исходный поток: перехватчик установлен, и его строки нам
# в журнале уже не нужны.
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
