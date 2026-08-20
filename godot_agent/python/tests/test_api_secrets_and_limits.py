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

# ---------------------------------------------------------------------------
# 7) Разбор адреса прокси
# ---------------------------------------------------------------------------
# Реальный случай из отчёта: в поле хоста ввели адрес DNS-over-HTTPS
# «https://xbox-dns.ru/dns-query». Раньше он сохранялся как есть, из него
# собиралось «http://https://xbox-dns.ru/dns-query», и ВСЕ запросы к
# провайдеру падали с невнятной ошибкой разрешения имени.
host, port, err = api_keys.parse_proxy_host(u"https://xbox-dns.ru/dns-query")
check(u"адрес с путём отклонён", err != "" and host == "", (host, port, err))
check(u"в отказе объяснено, что это не прокси",
      u"путь" in err and u"хост и порт" in err, err)

check(u"простой хост принимается",
      api_keys.parse_proxy_host(u"proxy.local") == (u"proxy.local", 0, u""))
check(u"хост:порт разбирается",
      api_keys.parse_proxy_host(u"proxy.local:3128") == (u"proxy.local", 3128, u""))
check(u"схема http:// отбрасывается",
      api_keys.parse_proxy_host(u"http://proxy.local:8080") == (u"proxy.local", 8080, u""))
check(u"схема https:// тоже принимается",
      api_keys.parse_proxy_host(u"https://proxy.local:8080")[0] == u"proxy.local")
check(u"завершающий слэш не мешает",
      api_keys.parse_proxy_host(u"http://proxy.local:8080/") == (u"proxy.local", 8080, u""))
check(u"IPv6 в скобках", api_keys.parse_proxy_host(u"[::1]:8080") == (u"[::1]", 8080, u""))
check(u"socks5 отклонён с объяснением",
      u"SOCKS" in api_keys.parse_proxy_host(u"socks5://127.0.0.1:1080")[2])
check(u"мусор вместо порта отклонён",
      api_keys.parse_proxy_host(u"proxy.local:abc")[2] != u"")
check(u"пробел в адресе отклонён",
      api_keys.parse_proxy_host(u"proxy local")[2] != u"")
check(u"пустой адрес — не ошибка (прокси просто не задан)",
      api_keys.parse_proxy_host(u"") == (u"", 0, u""))

# Сохранение: неверный адрес НЕ попадает в настройки.
ok_p, err_p = api_keys.set_proxy(host=u"https://xbox-dns.ru/dns-query", enabled=True)
check(u"неверный адрес не сохраняется", not ok_p and err_p != "", (ok_p, err_p))
check(u"прокси остался выключенным", api_keys.proxy_url() is None,
      api_keys.proxy_url())

ok_p, err_p = api_keys.set_proxy(host=u"http://proxy.local:3128", enabled=True)
check(u"нормальный адрес сохраняется", ok_p and err_p == "", (ok_p, err_p))
check(u"порт взят из адреса", api_keys.get_proxy()["port"] == 3128)
check(u"собранный адрес прокси корректен",
      api_keys.proxy_url() == u"http://proxy.local:3128", api_keys.proxy_url())

ok_p, err_p = api_keys.set_proxy(host=u"", enabled=True)
check(u"включить прокси без адреса нельзя", not ok_p and u"без адреса" in err_p, err_p)
api_keys.set_proxy(enabled=False)

# ---------------------------------------------------------------------------
# 4) Несколько ключей на провайдера: порядок, исчерпание, миграция
#
# Квота бесплатных тарифов считается НА КЛЮЧ, поэтому второй ключ того же
# провайдера работает, когда первый упёрся в суточный лимит.
# ---------------------------------------------------------------------------
K1 = "sk-or-v1-1111111111111111111111111111111111"
K2 = "sk-or-v1-2222222222222222222222222222222222"
K3 = "sk-or-v1-3333333333333333333333333333333333"

api_keys.set_key("groq", K1)
api_keys.add_key("groq", K2)
api_keys.add_key("groq", K3)
check(u"ключи легли по порядку добавления",
      [k for _i, k in api_keys.usable_keys("groq")] == [K1, K2, K3])
check(u"дубликат не добавляется",
      api_keys.add_key("groq", K2) and api_keys.key_count("groq") == 3)
check(u"resolve_key отдаёт ПЕРВЫЙ пригодный", api_keys.resolve_key("groq") == K1)

# Исчерпание без названного срока — только на сессию.
api_keys.note_key_exhausted("groq", 0, reason=u"free-models-per-day")
check(u"исчерпанный ключ выпал из кандидатов",
      [k for _i, k in api_keys.usable_keys("groq")] == [K2, K3])
check(u"resolve_key перешёл на следующий", api_keys.resolve_key("groq") == K2)
check(u"исчерпание без срока НЕ попало в файл (это была бы догадка)",
      all(not item.get("cooldown_until")
          for item in api_keys.keys_state("groq")))
check(u"панель видит, какой именно ключ исчерпан",
      [k["spent"] for k in api_keys.keys_state("groq")] == [True, False, False])
check(u"в состоянии для панели нет сырых ключей",
      all(K1 not in str(k.values()) and K2 not in str(k.values())
          for k in api_keys.keys_state("groq")))
check(u"причина исчерпания названа пользователю",
      any(u"free-models-per-day" in r for _i, _m, r, _u in api_keys.spent_keys("groq"))
      or api_keys.spent_keys("groq")[0][2] != u"")

# Исчерпание со сроком от провайдера — на диск, потому что это факт.
api_keys.note_key_exhausted("groq", 1, reason=u"rate limit", retry_after=120)
_st = api_keys.keys_state("groq")
check(u"названный провайдером срок сохранён", _st[1]["until"] > 0)
check(u"ключ со сроком тоже выпал из кандидатов",
      [k for _i, k in api_keys.usable_keys("groq")] == [K3])
check(u"срок виден панели в секундах, а не как «когда-нибудь»",
      110 < (_st[1]["until"] - __import__("time").time()) <= 120)

# Когда исчерпаны все — кандидатов нет, но ключи не потеряны.
api_keys.note_key_exhausted("groq", 2, reason=u"insufficient credits")
check(u"пригодных ключей не осталось", api_keys.usable_keys("groq") == [])
check(u"все три перечислены как исчерпанные",
      len(api_keys.spent_keys("groq")) == 3)
check(u"has_key по-прежнему True: ключи есть, просто выдохлись",
      api_keys.has_key("groq") and api_keys.key_count("groq") == 3)
check(u"resolve_key отдаёт первый, а не пустоту (иначе панель скажет «введите ключ»)",
      api_keys.resolve_key("groq") == K1)

api_keys.clear_key_cooldowns("groq")
check(u"сброс по кнопке возвращает все ключи в игру",
      [k for _i, k in api_keys.usable_keys("groq")] == [K1, K2, K3])

# redact обязан затирать ВСЕ ключи, включая исчерпанные.
api_keys.note_key_exhausted("groq", 0, reason=u"quota")
_red = api_keys.redact(u"провайдер вернул ключ %s и ключ %s" % (K1, K3))
check(u"redact затирает и исчерпанный ключ, и действующий",
      K1 not in _red and K3 not in _red)

# Удаление одного ключа из списка.
api_keys.delete_key_at("groq", 1)
check(u"удалён именно указанный ключ",
      [k for _i, k in api_keys.usable_keys("groq")] == [K1, K3])
check(u"память об исчерпании сброшена: индексы сдвинулись",
      api_keys.keys_state("groq")[0]["spent"] is False)

# Переменная окружения отменяет ротацию: её ставят тесты и CI.
_os0.environ["GODOT_AGENT_GROQ_KEY"] = "env-key-long-enough-value"
check(u"ключ из окружения — единственный кандидат",
      [k for _i, k in api_keys.usable_keys("groq")] == ["env-key-long-enough-value"])
check(u"источник назван честно", api_keys.key_source("groq") == "env")
check(u"исчерпание чужой переменной окружения не записывается",
      api_keys.note_key_exhausted("groq", api_keys.ENV_KEY_INDEX) is False)
del _os0.environ["GODOT_AGENT_GROQ_KEY"]

# Миграция файла версии 1: один ключ строкой.
_old = {"providers": {"deepseek": {"key": K1, "model": "m", "base_url": ""}}}
with open(api_keys.config_path(), "w", encoding="utf-8") as f:
    __import__("json").dump(_old, f)
api_keys._invalidate_cfg()
api_keys._invalidate_secrets()
check(u"старый файл читается: ключ стал списком из одного",
      [k for _i, k in api_keys.usable_keys("deepseek")] == [K1])
check(u"модель из старого файла не потеряна",
      api_keys.get_model("deepseek") == "m")
api_keys.add_key("deepseek", K2)
check(u"после миграции можно добавить второй ключ",
      [k for _i, k in api_keys.usable_keys("deepseek")] == [K1, K2])
api_keys.set_key("openrouter", KEY)

api_keys.delete_key("openrouter")
api_keys.set_proxy(enabled=False, password="")
shutil.rmtree(CFG, ignore_errors=True)

n_ok = sum(1 for r in results if r)
# Итог печатаем в исходный поток: перехватчик установлен, и его строки нам
# в журнале уже не нужны.
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
