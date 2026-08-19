# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты каталога провайдеров: признак бесплатности моделей, наблюдения о
провайдерах (provider_stats), проверка своего адреса endpoint'а.

Что здесь проверяется по существу — это ЧЕСТНОСТЬ подписей в списке
провайдеров. Панель собирается показывать «столько-то бесплатных моделей»,
«проверен», «готов к работе», и каждая такая подпись может соврать по-своему:
счётчик — если считать по отфильтрованному списку, пометка «проверен» — если
поставить её по предположению, а не по прогону, «готов» — если причина
неготовности приходит текстом на одном языке. Тесты закрывают ровно эти места.

ВАЖНО: папка настроек подменяется через GODOT_AGENT_CONFIG_DIR ДО импорта
модулей, иначе прогон писал бы в настоящий %APPDATA%\\Godot_agent.
"""
import json
import shutil
import sys
import tempfile
import time

CFG = tempfile.mkdtemp(prefix="agent_cfg_catalog_")
_os0.environ["GODOT_AGENT_CONFIG_DIR"] = CFG

import api_keys
import providers as P

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


# ---------------------------------------------------------------------------
# 1) Признак бесплатности доходит до панели, а не выбрасывается
# ---------------------------------------------------------------------------
RAW = {"data": [
    {"id": "vendor/paid", "pricing": {"prompt": "0.01", "completion": "0.02"}},
    {"id": "vendor/gift:free", "pricing": {"prompt": "0", "completion": "0"}},
    # Нулевая цена БЕЗ суффикса в имени: главный случай, ради которого признак
    # и понадобился отдельным полем — по имени такую модель не отличить.
    {"id": "vendor/quiet-gift", "pricing": {"prompt": "0E-8", "completion": "0"}},
    # Голая строка вместо объекта: судим по имени.
    "vendor/named-free",
]}

detailed = P.parse_models_detailed(RAW)
by_id = {r["id"]: r["free"] for r in detailed}
check(u"платная модель помечена платной", by_id["vendor/paid"] is False)
check(u"модель с суффиксом :free помечена бесплатной", by_id["vendor/gift:free"] is True)
check(u"нулевая цена БЕЗ суффикса тоже даёт признак «бесплатная»",
      by_id["vendor/quiet-gift"] is True)
check(u"голая строка с суффиксом -free разобрана", by_id["vendor/named-free"] is True)
check(u"бесплатные идут первыми",
      [r["free"] for r in detailed] == sorted([r["free"] for r in detailed], reverse=True))

# ---------------------------------------------------------------------------
# 1а) Старый и новый разбор не могут разойтись
#
# Раньше признак бесплатности вычислялся и выбрасывался, а панель судила по
# имени. Если бы «список строк» и «список записей» считались двумя
# независимыми проходами, они однажды разошлись бы в трактовке бесплатности —
# и список моделей начал бы противоречить счётчику на том же экране.
# ---------------------------------------------------------------------------
check(u"список строк — это ровно идентификаторы из списка записей",
      P.parse_models_response(RAW) == [r["id"] for r in detailed])
check(u"фильтр «только бесплатные» согласован между двумя видами",
      P.parse_models_response(RAW, free_only=True)
      == [r["id"] for r in P.parse_models_detailed(RAW, free_only=True)])
check(u"мусор вместо ответа не роняет разбор",
      P.parse_models_detailed(None) == [] and P.parse_models_detailed({"data": 5}) == [])

# ---------------------------------------------------------------------------
# 1б) ЧИСЛА ИЗ ЖИВОГО ОТВЕТА ПРОВАЙДЕРА — первичные, каталог им не нужен
#
# Замерено (OpenRouter, 19.08.2026): pricing есть у всех 416 записей,
# context_length у 416, top_provider.max_completion_tokens у 367,
# supported_parameters с "tools" — у большинства. Раньше всё это выбрасывалось,
# и цену приходилось брать из каталога models.dev, который отстаёт: у
# moonshotai/kimi-k2.6 он показывал 0.95/4.0 против живых 0.646/2.72, то есть
# завышал на 47%.
#
# ЕДИНИЦА ЦЕНЫ — САМОЕ ОПАСНОЕ МЕСТО. OpenRouter присылает доллары ЗА ТОКЕН,
# каталог — за МИЛЛИОН. Ошибка здесь показывает цену, завышенную в миллион раз,
# поэтому единица берётся из реестра (live_pricing) и только после сверки живым
# запросом, а не угадывается по «OpenAI-совместимости».
# ---------------------------------------------------------------------------
LIVE_OR = {"data": [
    {"id": "a/paid", "pricing": {"prompt": "0.000005", "completion": "0.000025"},
     "context_length": 1000000,
     "top_provider": {"max_completion_tokens": 128000},
     "supported_parameters": ["tools", "temperature"]},
    {"id": "a/gift:free", "pricing": {"prompt": "0", "completion": "0"},
     "context_length": 65536, "supported_parameters": ["temperature"]},
    # «-1» у OpenRouter означает «цена зависит от маршрута». Превращать это в
    # число значит соврать, поэтому цены у такой записи не будет вовсе.
    {"id": "a/router", "pricing": {"prompt": "-1", "completion": "-1"},
     "context_length": 0},
]}
by = {r["id"]: r for r in P.parse_models_detailed(LIVE_OR, provider_id="openrouter")}
check(u"цена за токен переведена в цену за миллион",
      by["a/paid"]["cost_in"] == 5.0 and by["a/paid"]["cost_out"] == 25.0)
check(u"окно контекста и предел ответа взяты из живого ответа",
      by["a/paid"]["context"] == 1000000 and by["a/paid"]["max_output"] == 128000)
check(u"родной function calling виден по supported_parameters",
      by["a/paid"]["tool_call"] is True and by["a/gift:free"]["tool_call"] is False)
check(u"«цена зависит от маршрута» (-1) не превращается в число",
      "cost_in" not in by["a/router"] and "cost_out" not in by["a/router"])
check(u"нулевое context_length — это не окно нулевого размера, а его отсутствие",
      "context" not in by["a/router"])
check(u"у записи без top_provider предела ответа нет, а не ноль",
      "max_output" not in by["a/gift:free"])

# Тот же ответ у провайдера, у которого единица цены НЕ проверена: цены нет
# вовсе. Показать её не в тех единицах хуже, чем не показать.
by_c = {r["id"]: r for r in P.parse_models_detailed(LIVE_OR, provider_id="custom")}
check(u"без отметки live_pricing цена из ответа игнорируется",
      "cost_in" not in by_c["a/paid"] and "cost_out" not in by_c["a/paid"])
check(u"а окно контекста берётся всё равно — его единица однозначна",
      by_c["a/paid"]["context"] == 1000000
      and by_c["a/paid"]["max_output"] == 128000)
check(u"единица цены OpenRouter проверена и записана в реестр",
      P.live_pricing_unit("openrouter") == "per_token"
      and P.live_pricing_unit("custom") == ""
      and P.live_pricing_unit("opencode_zen") == "")
check(u"признак бесплатности от новых полей не изменился",
      by["a/gift:free"]["free"] is True and by["a/paid"]["free"] is False)

# Opencode Zen присылает ТОЛЬКО id, object, created, owned_by (замерено) —
# оттуда брать нечего, и это нормально: для него и нужен каталог.
zen = P.parse_models_detailed(
    {"data": [{"id": "big-pickle", "object": "model", "created": 1,
               "owned_by": "opencode"}]}, provider_id="opencode_zen")
check(u"из ответа без цен и лимитов ничего не выдумывается",
      zen == [{"id": "big-pickle", "free": False}])
check(u"старый вызов без provider_id по-прежнему работает",
      [r["id"] for r in P.parse_models_detailed(LIVE_OR)]
      == ["a/gift:free", "a/paid", "a/router"])

# ---------------------------------------------------------------------------
# 2) Счётчики считаются по ПОЛНОМУ списку, а не по отфильтрованному
#
# Главная ловушка счётчика: посчитать total по списку, из которого уже убрали
# платные. Тогда у любого платного сервиса в списке провайдеров было бы
# написано «все модели бесплатные».
# ---------------------------------------------------------------------------
total_all, free_all = P.count_models(P.parse_models_detailed(RAW))
check(u"всего моделей посчитано верно", total_all == 4)
check(u"бесплатных посчитано верно", free_all == 3)
total_f, free_f = P.count_models(P.parse_models_detailed(RAW, free_only=True))
check(u"по отфильтрованному списку всего == бесплатных (то, чего нельзя писать в счётчик)",
      total_f == free_f == 3)

# ---------------------------------------------------------------------------
# 3) Наблюдения переживают запись и ЧТЕНИЕ с диска
#
# Мина, ради которой этот тест написан в первую очередь: _load() не объединяет
# конфигурацию с файлом, а собирает её заново по известным полям. Раздел,
# добавленный только в _DEFAULT_CONFIG, исправно сохранялся бы и молча
# исчезал при каждом чтении — снаружи это выглядит как «кэш не работает».
# ---------------------------------------------------------------------------
check(u"о неизвестном провайдере наблюдений нет", api_keys.get_stats("openrouter") == {})
api_keys.record_models_stats("openrouter", 324, 57)
st = api_keys.get_stats("openrouter")
check(u"числа моделей сохранены",
      st.get("models_total") == 324 and st.get("models_free") == 57)
check(u"дата измерения проставлена", st.get("models_at", 0) > 0)
with open(api_keys.config_path(), "r", encoding="utf-8") as f:
    on_disk = json.load(f)
check(u"раздел наблюдений реально дошёл до файла",
      (on_disk.get("provider_stats") or {}).get("openrouter", {}).get("models_total") == 324)
check(u"раздел наблюдений НЕ выбрасывается при следующем чтении",
      (api_keys._load().get("provider_stats") or {}).get("openrouter", {}).get("models_free") == 57)

# ---------------------------------------------------------------------------
# 3-1) Второй счётчик бесплатных — ПО КАТАЛОГУ models.dev
#
# Та же мина, что и у всего раздела наблюдений, но на одно поле: _load()
# собирает конфигурацию заново по известным полям, и счётчик, добавленный
# только в _DEFAULT_CONFIG, исправно сохранялся бы и молча исчезал при каждом
# чтении. Снаружи это выглядит как «каталог не работает».
#
# Держать его ОТДЕЛЬНО от models_free обязательно: одно измерено по ответу
# провайдера, другое взято из справочника, и они расходятся (у Opencode Zen
# модель big-pickle в каталоге с нулевой ценой, а по суффиксу платная). Свести
# их в одно число значит потерять ответ на вопрос, кто это утверждает.
# ---------------------------------------------------------------------------
check(u"без каталога второй счётчик молчит (-1), а не пишет ноль",
      api_keys.get_stats("openrouter").get("models_free_catalog") == -1)
api_keys.record_models_stats("openrouter", 324, 57, 61)
st = api_keys.get_stats("openrouter")
check(u"счётчик каталога сохранён отдельно от измеренного по провайдеру",
      st.get("models_free") == 57 and st.get("models_free_catalog") == 61)
with open(api_keys.config_path(), "r", encoding="utf-8") as f:
    on_disk = json.load(f)
check(u"счётчик каталога реально дошёл до файла",
      (on_disk.get("provider_stats") or {}).get("openrouter", {}).get(
          "models_free_catalog") == 61)
check(u"счётчик каталога НЕ выбрасывается при следующем чтении",
      (api_keys._load().get("provider_stats") or {}).get("openrouter", {}).get(
          "models_free_catalog") == 61)
check(u"старый вызов без счётчика каталога не выдумывает число",
      api_keys.models_stats_fields(5, 2).get("models_free_catalog") == -1)
api_keys.reset_models_stats("openrouter")
check(u"сброс наблюдений (смена адреса endpoint'а) обнуляет и счётчик каталога",
      api_keys.get_stats("openrouter").get("models_free_catalog") == -1)
api_keys.record_models_stats("openrouter", 324, 57)

check(u"результата проверки подключения пока нет", "test_ok" not in api_keys.get_stats("openrouter"))
api_keys.record_test_result("openrouter", True, 812)
st = api_keys.get_stats("openrouter")
check(u"исход проверки сохранён", st.get("test_ok") is True and st.get("test_ms") == 812)
check(u"запись проверки не затёрла числа моделей", st.get("models_total") == 324)
api_keys.record_test_result("openrouter", False, 0)
check(u"неудачная проверка тоже запоминается",
      api_keys.get_stats("openrouter").get("test_ok") is False)
check(u"наблюдения по одному провайдеру не видны у другого",
      api_keys.get_stats("groq") == {})
check(u"все наблюдения выдаются одним словарём",
      "openrouter" in api_keys.get_stats() and "groq" not in api_keys.get_stats())

# ---------------------------------------------------------------------------
# 3а) Неудача получения списка моделей — это ЗНАНИЕ, а не пустота
#
# «Список моделей ещё не загружался» на провайдере, к которому плагин сходил и
# получил 401, — это неправда, и она читается как бездействие плагина.
# Наоборот, старая ошибка рядом со свежими числами читается как поломка,
# которой уже нет: поэтому удача обязана ошибку снимать.
# ---------------------------------------------------------------------------
api_keys.record_models_error("groq", u"ключ отклонён провайдером")
gstats = api_keys.get_stats("groq")
check(u"причина неудачи сохранена словами",
      gstats.get("models_error") == u"ключ отклонён провайдером")
check(u"у неудачи есть время попытки", gstats.get("models_try_at", 0) > 0)
check(u"неудача не выдумала чисел моделей", gstats.get("models_total") == -1)
api_keys.record_models_error("openrouter", u"сеть недоступна")
check(u"прежние числа моделей неудачей не стёрты",
      api_keys.get_stats("openrouter").get("models_total") == 324)
api_keys.record_models_stats("openrouter", 330, 60)
check(u"удача снимает прежнюю ошибку",
      "models_error" not in api_keys.get_stats("openrouter"))

# ---------------------------------------------------------------------------
# 3б) Свежесть наблюдений и отбор провайдеров для автообновления
#
# Мина, из-за которой всё это заведено: числа моделей появлялись ТОЛЬКО после
# ручного нажатия «Обновить список» у конкретного провайдера, а фильтр «с
# бесплатными» отбирает именно по ним. Значит фильтр показывал не провайдеров с
# бесплатными моделями, а провайдеров, которых пользователь успел открыть.
# ---------------------------------------------------------------------------
now = time.time()
check(u"свежие числа обновлять не надо", P.models_stale("openrouter") is False)
check(u"числа старше суток пора обновить",
      P.models_stale("openrouter", {"models_total": 5, "models_free": 1,
                                    "models_at": now - P.MODELS_FRESH_SECONDS - 1}))
check(u"провайдер, о котором ничего не известно, всегда устарел",
      P.models_stale("deepseek", {}) is True)
check(u"сразу после неудачи не долбимся заново",
      P.models_stale("groq") is False)
check(u"через паузу после неудачи попытку повторяем",
      P.models_stale("groq", {"models_error": u"сеть",
                              "models_try_at": now - P.MODELS_RETRY_SECONDS - 1}))
check(u"честный нуль моделей — это измерение, а не отсутствие данных",
      P.models_stale("deepseek", {"models_total": 0, "models_free": 0,
                                  "models_at": now}) is False)

check(u"провайдера с публичным /models можно спросить без ключа",
      P.can_fetch_models("openrouter") is True
      and P.can_fetch_models("opencode_zen") is True)
api_keys.set_key("deepseek", "")
check(u"провайдера без ключа и без публичного /models не спрашивают",
      P.can_fetch_models("deepseek") is False)
api_keys.set_key("deepseek", "sk-TESTVALUE0123456789")
check(u"с сохранённым ключом спросить можно",
      P.can_fetch_models("deepseek") is True)
api_keys.set_key("deepseek", "")
check(u"к недоступному сервису не ходят даже за списком моделей",
      P.can_fetch_models("agentrouter") is False)
check(u"«свой адрес» без адреса спрашивать некуда",
      P.can_fetch_models("custom") is False)

targets = P.autoscan_targets()
check(u"в обход попадают только те, кого можно спросить",
      all(P.can_fetch_models(pid) for pid in targets))
check(u"свежий провайдер в обход не попадает", "openrouter" not in targets)
check(u"провайдер без данных в обход попадает", "opencode_zen" in targets)

# Пакетная запись: обход касается нескольких провайдеров, и запись по одному
# означала бы несколько чтений-перезаписей файла подряд — лишние шансы потерять
# чужое изменение, пришедшее в это же время другим HTTP-запросом.
api_keys.record_stats_bulk({
    "opencode_zen": api_keys.models_stats_fields(12, 3),
    "gemini": api_keys.models_error_fields(u"нет ключа"),
})
check(u"пакетная запись сохранила удачу одного провайдера",
      api_keys.get_stats("opencode_zen").get("models_free") == 3)
check(u"и неудачу другого в той же записи",
      bool(api_keys.get_stats("gemini").get("models_error")))
check(u"пакетная запись не тронула чужие наблюдения",
      api_keys.get_stats("openrouter").get("models_total") == 330)

# ---------------------------------------------------------------------------
# 3в) Кэш списков моделей — то, по чему панель ищет модель у ВСЕХ провайдеров
#
# Поиск в списке провайдеров умеет искать не только по названию провайдера, но и
# по названию модели: человек помнит «kimi» или «deepseek», а не то, кто из
# сервисов их отдаёт. Для этого нужны сами списки, а не только их количество.
# ---------------------------------------------------------------------------
import model_cache

check(u"кэш моделей лежит ОТДЕЛЬНО от файла с ключами",
      model_cache.cache_path() != api_keys.config_path())
check(u"о неизвестном провайдере моделей нет", model_cache.get("openrouter") == [])
model_cache.put("openrouter", [
    {"id": "vendor/kimi-k2", "free": False},
    {"id": "vendor/gift:free", "free": True},
    # Дубль и мусор: в кэш попадать не должны.
    {"id": "vendor/kimi-k2", "free": True},
    {"id": "   ", "free": True},
    "vendor/plain-string",
])
got = model_cache.get("openrouter")
check(u"список моделей сохранён", [r["id"] for r in got]
      == ["vendor/kimi-k2", "vendor/gift:free", "vendor/plain-string"])
check(u"признак бесплатности сохранён",
      got[0]["free"] is False and got[1]["free"] is True)
check(u"строка без записи о цене НЕ объявлена бесплатной", got[2]["free"] is False)
check(u"слишком длинный идентификатор отброшен",
      model_cache.put("groq", [{"id": "x" * (model_cache.MAX_ID_LEN + 1)}]) is False
      and model_cache.get("groq") == [])
check(u"кэш переживает чтение с диска",
      len(model_cache.index().get("openrouter") or []) == 3)

# Кэш хранит ПЕРВИЧНУЮ правду — то, что присылает сам провайдер (у OpenRouter
# это цена, окно контекста, предел ответа и поддержка function calling у всех
# 416 записей). Дополнения каталога models.dev здесь НЕ хранятся намеренно:
# попав на диск, они стали бы неотличимы от присланных провайдером, и подпись
# «по каталогу models.dev» встала бы под живой ценой. Каталог прикладывается на
# выходе (chat_routes._enrich) и сам сообщает, что дописал.
model_cache.put("deepseek", [
    {"id": "deepseek-chat", "free": False, "cost_in": 0.28, "cost_out": 0.42,
     "context": 128000, "max_output": 8192, "tool_call": True,
     # Поля каталога, которые обязаны быть отброшены при записи.
     "catalog_free": False, "status": "deprecated", "deprecated": True,
     "from_catalog": ["context"],
     # Чужое поле: набор в кэше ЗАКРЫТЫЙ, иначе туда однажды уедет описание
     # модели на три абзаца, а файл читается целиком на каждый поиск.
     "description": u"описание, которому в кэше не место"},
    # Провайдер про эту модель прислал только id: полей быть НЕ должно, а не
    # нулей. Ноль вместо неизвестной цены означал бы «бесплатная».
    {"id": "deepseek-brand-new", "free": False},
])
drec = {r["id"]: r for r in model_cache.get("deepseek")}
check(u"числа ИЗ ЖИВОГО ОТВЕТА переживают запись и чтение кэша",
      drec["deepseek-chat"]["cost_in"] == 0.28
      and drec["deepseek-chat"]["context"] == 128000
      and drec["deepseek-chat"]["max_output"] == 8192
      and drec["deepseek-chat"]["tool_call"] is True)
check(u"утверждения КАТАЛОГА в кэш не попадают — иначе подпись об источнике соврёт",
      not any(k in drec["deepseek-chat"]
              for k in ("catalog_free", "status", "deprecated", "from_catalog")))
check(u"чужие поля в кэш не пропускаются",
      "description" not in drec["deepseek-chat"])
check(u"о модели без данных провайдера кэш не выдумывает ни цены, ни лимитов",
      set(drec["deepseek-brand-new"]) == {"id", "free"})
model_cache.forget("deepseek")

# Пустой ответ /models означает «моделей сейчас нет». Оставить прошлый список
# значит предложить выбрать модель, которой у провайдера уже нет.
model_cache.put("opencode_zen", [{"id": "hy3-free", "free": True}])
check(u"списки нескольких провайдеров живут рядом",
      set(model_cache.index()) == {"openrouter", "opencode_zen"})
model_cache.put("opencode_zen", [])
check(u"пустой список убирает провайдера из кэша, а не оставляет прошлый",
      "opencode_zen" not in model_cache.index())
model_cache.forget("openrouter")
check(u"забыть можно и вручную — например при смене адреса endpoint'а",
      model_cache.index() == {})

# ---------------------------------------------------------------------------
# 4) Свой адрес endpoint'а: открыт всем, но мусор не принимает
#
# Поле открыто у ВСЕХ провайдеров, чтобы переехавший сервис лечился без новой
# версии плагина. Обратная сторона — одной опечаткой можно молча сломать
# рабочего провайдера, поэтому проверка обязательна. Ровно такой случай уже
# был с полем прокси, куда вставили адрес DNS-over-HTTPS.
# ---------------------------------------------------------------------------
ok, err = api_keys.set_base_url("openrouter", "https://mirror.example.com/v1/")
check(u"зеркало известного провайдера принято", ok and not err)
check(u"завершающий слэш срезан", api_keys.get_base_url("openrouter")
      == "https://mirror.example.com/v1")
check(u"адрес, заданный руками, выигрывает у реестра",
      P.base_url_for("openrouter") == "https://mirror.example.com/v1")

ok, err = api_keys.set_base_url("openrouter", "openrouter.ai/api/v1")
check(u"адрес без схемы отклонён с объяснением", not ok and u"http://" in err)
check(u"отклонённый адрес НЕ затёр прежний",
      api_keys.get_base_url("openrouter") == "https://mirror.example.com/v1")
ok, err = api_keys.set_base_url("openrouter", "ftp://host/v1")
check(u"чужая схема отклонена", not ok and u"ftp" in err)
ok, err = api_keys.set_base_url("openrouter", "https://")
check(u"схема без хоста отклонена", not ok and u"хоста" in err)
ok, err = api_keys.set_base_url("openrouter", "https://ho st/v1")
check(u"пробел в адресе отклонён", not ok and u"пробел" in err)

ok, err = api_keys.set_base_url("openrouter", "")
check(u"пустое значение принято — это сброс, а не ошибка", ok and not err)
check(u"после сброса действует адрес из реестра",
      P.base_url_for("openrouter") == "https://openrouter.ai/api/v1")

# ---------------------------------------------------------------------------
# 5) Что видит панель в списке провайдеров
# ---------------------------------------------------------------------------
listed = {p["id"]: p for p in P.list_providers()}
orec = listed["openrouter"]
# Сверяемся с наблюдениями, а не с числом из середины теста: иначе любая новая
# проверка выше, дописавшая наблюдение, ломала бы эту строку, и правили бы
# число вместо того, чтобы читать, что она проверяет — что наблюдения ВООБЩЕ
# доезжают до записи провайдера.
check(u"наблюдения приложены к записи провайдера",
      orec["stats"].get("models_free")
      == api_keys.get_stats("openrouter").get("models_free")
      and orec["stats"].get("models_free", -1) >= 0)
check(u"второй счётчик бесплатных доехал до записи провайдера отдельным полем",
      "models_free_catalog" in orec["stats"]
      and orec["stats"]["models_free_catalog"]
      == api_keys.get_stats("openrouter").get("models_free_catalog"))
check(u"адрес открыт для правки у обычного провайдера, а не только у «своего»",
      orec["base_url_editable"] is True and listed["custom"]["base_url_editable"] is True)
check(u"показан адрес из реестра — к нему вернёт очистка поля",
      orec["base_url_default"] == "https://openrouter.ai/api/v1")
check(u"подмены адреса сейчас нет", orec["base_url_custom"] is False)
api_keys.set_base_url("openrouter", "https://mirror.example.com/v1")
check(u"подмена адреса помечена флагом",
      [p for p in P.list_providers() if p["id"] == "openrouter"][0]["base_url_custom"] is True)
api_keys.set_base_url("openrouter", "")

check(u"видно, что список моделей OpenRouter доступен без ключа",
      orec["models_public"] is True and listed["opencode_zen"]["models_public"] is True)
check(u"у провайдера с закрытым /models этого обещания нет",
      listed["groq"]["models_public"] is False)

# ПОМЕТКА «ПРОВЕРЕН» — самая опасная подпись в этом списке. Живого обмена
# настоящим ключом не было ни с одним провайдером (ОТЛОЖЕНО.md, раздел «Работа
# по ключу API — что осталось до релиза»), поэтому True здесь означал бы
# обещание, за которое пользователь ловит 401 или 402 и считает, что плагин
# соврал. Тест держит поле честным: он упадёт, если кому-то поставят флаг, не
# обновив документ.
check(u"ни один провайдер не помечен проверенным, пока не было живого прогона",
      all(p["verified"] is False for p in P.list_providers()))

# ---------------------------------------------------------------------------
# 5а) Причина неготовности приходит КОДОМ, а не только русским текстом
#
# Текст причины сервер составляет по-русски: он писался под строку в
# настройках. Как подпись на карточке провайдера в английской локали он
# выглядел бы поломкой, а перевести готовую фразу панель не может.
# ---------------------------------------------------------------------------
api_keys.set_key("groq", "")
grec = [p for p in P.list_providers() if p["id"] == "groq"][0]
check(u"без ключа код причины — no_key", grec["not_ready_code"] == "no_key")
check(u"текст причины остался для журнала", bool(grec["not_ready_reason"]))
api_keys.set_key("groq", "gsk_TESTVALUE0123456789")
grec = [p for p in P.list_providers() if p["id"] == "groq"][0]
check(u"с ключом, но без модели код причины — no_model",
      grec["not_ready_code"] == "no_model")
api_keys.set_model("groq", "llama-3.3-70b")
grec = [p for p in P.list_providers() if p["id"] == "groq"][0]
check(u"готовый провайдер отдаёт пустой код", grec["ready"] and grec["not_ready_code"] == "")
arec = [p for p in P.list_providers() if p["id"] == "agentrouter"][0]
check(u"недоступность сервиса важнее нехватки ключа",
      arec["not_ready_code"] == "unavailable")
check(u"код неизвестного провайдера", P.readiness_code("нет-такого") == "unknown_provider")
check(u"readiness() по-прежнему отдаёт пару из двух значений",
      len(P.readiness("groq")) == 2 and P.readiness("groq")[0] is True)

# ---------------------------------------------------------------------------
# 6) В новых полях не появилось секретов
#
# Наблюдения и метаданные уходят в панель целиком, поэтому проверяем весь
# ответ разом: маска ключа допустима, сам ключ — нет.
# ---------------------------------------------------------------------------
dump = json.dumps(P.list_providers(), ensure_ascii=False)
check(u"СЫРОГО ключа в списке провайдеров нет", "TESTVALUE" not in dump)
check(u"маска ключа при этом на месте",
      [p for p in P.list_providers() if p["id"] == "groq"][0]["masked"].startswith("gsk_"))

# ---------------------------------------------------------------------------
# 7) ПОЛНЫЙ СПИСОК ПРОВАЙДЕРОВ ИЗ КАТАЛОГА models.dev
#
# Замерено: из 192 записей каталога 166 имеют адрес endpoint'а, у остальных 26
# его нет вовсе — им нужен родной SDK провайдера, а у нас единственный транспорт
# это HTTP. Показать такого значило бы предложить выбор, который заведомо не
# заработает.
#
# ЧТО ЗДЕСЬ ПРОВЕРЯЕТСЯ ПО СУЩЕСТВУ — что добавление ста шестидесяти
# непроверенных записей НЕ размывает знание о семи разобранных: реестр
# выигрывает при совпадении идентификаторов, каталожным не выставляется
# models_public (значит их не спрашивают без ключа и не трогают автообходом), и
# они видны только по явному включению.
# ---------------------------------------------------------------------------
import catalog as CAT

CAT.forget()
check(u"без кэша каталога список провайдеров прежний — семь разобранных",
      len(P.provider_ids()) == 7 and P.catalog_records() == {})

FAKE_API = {
    # Наши: реестр обязан выиграть, каталожная копия в список не попадает.
    "openrouter": {"id": "openrouter", "name": "OpenRouter — из каталога",
                   "api": "https://openrouter.example/v1",
                   "env": ["OPENROUTER_API_KEY"], "npm": "@ai-sdk/openai-compatible",
                   "doc": "https://doc.example",
                   "models": {"a/b": {"cost": {"input": 1, "output": 2},
                                      "limit": {"context": 1000}}}},
    # Наш gemini живёт в каталоге под именем google, и адреса там нет вовсе —
    # ровно поэтому подменять записи реестра каталогом нельзя.
    "google": {"id": "google", "name": "Google", "api": None,
               "env": ["GEMINI_API_KEY"], "npm": "@ai-sdk/google",
               "models": {"g/1": {"limit": {"context": 1000}}}},
    # Чужой, пригодный: попадёт в список.
    "nano-like": {"id": "nano-like", "name": "NanoLike",
                  "api": "https://nano.example/api/v1",
                  "env": ["NANO_LIKE_API_KEY"], "npm": "@ai-sdk/openai-compatible",
                  "doc": "https://docs.nano.example",
                  "models": {"m/paid": {"cost": {"input": 1, "output": 2},
                                        "limit": {"context": 128000}},
                             "m/free": {"cost": {"input": 0, "output": 0},
                                        "limit": {"context": 8000}},
                             # Снятая не должна попасть в число моделей.
                             "m/old": {"status": "deprecated",
                                       "limit": {"context": 8000}}}},
    # Anthropic-протокол: у нас транспорт для него есть, но живьём не проверен.
    "claude-like": {"id": "claude-like", "name": "ClaudeLike",
                    "api": "https://claude.example/v1",
                    "env": ["CLAUDE_LIKE_API_KEY"], "npm": "@ai-sdk/anthropic",
                    "models": {"c/1": {"limit": {"context": 200000}}}},
    # Адрес — неподставленный шаблон. Живьём такой один (neon), и запрос по нему
    # упал бы невнятной сетевой ошибкой.
    "template-url": {"id": "template-url", "name": "Template", "npm": "x",
                     "api": "${SOME_BASE_URL}/v1", "env": ["T_API_KEY"],
                     "models": {"t/1": {}}},
    # Локальный сервер: НЕ отбраковываем, транспорт с такими умеет работать.
    "local-like": {"id": "local-like", "name": "LocalLike", "npm": "x",
                   "api": "http://127.0.0.1:1234/v1", "env": ["LOCAL_KEY"],
                   "models": {"l/1": {"limit": {"context": 8000}}}},
    # Адреса нет вовсе — записи в списке быть не должно.
    "sdk-only": {"id": "sdk-only", "name": "SdkOnly", "npm": "@ai-sdk/azure",
                 "env": ["AZURE_API_KEY"], "models": {"z/1": {}}},
    # Сервису нужно несколько значений, а форма умеет один ключ.
    "two-secrets": {"id": "two-secrets", "name": "TwoSecrets", "npm": "x",
                    "api": "https://two.example/v1",
                    "env": ["TWO_ACCOUNT_ID", "TWO_API_KEY"],
                    "models": {"w/1": {"limit": {"context": 8000}}}},
}
meta = CAT._compact_providers(FAKE_API)
check(u"пригодными считаются только записи с рабочим адресом",
      set(meta) == {"openrouter", "nano-like", "claude-like", "local-like",
                    "two-secrets"})
check(u"запись без адреса отброшена (ей нужен родной SDK)", "sdk-only" not in meta)
check(u"неподставленный шаблон вместо адреса отброшен", "template-url" not in meta)
check(u"локальный http-адрес НЕ отброшен", "local-like" in meta)
check(u"снятые модели не попали в число моделей провайдера",
      meta["nano-like"]["models_total"] == 2
      and meta["nano-like"]["models_free"] == 1)
check(u"протокол взят по npm-пакету",
      meta["claude-like"]["transport"] == "anthropic"
      and meta["nano-like"]["transport"] == "openai")
check(u"несколько переменных окружения помечены отдельно",
      meta["two-secrets"]["multi_secret"] is True
      and meta["nano-like"]["multi_secret"] is False)

# Пишем кэш целиком, как это сделал бы refresh(), и смотрим на слияние.
CAT._save({"version": 1, "at": time.time(), "etag": "", "error": "",
           "try_at": 0.0, "providers": CAT._compact(FAKE_API),
           "catalog_providers": meta})
check(u"пока полный список выключен, провайдеров по-прежнему семь",
      api_keys.catalog_enabled() is False and len(P.provider_ids()) == 7)
api_keys.set_catalog_enabled(True)
ids = P.provider_ids()
check(u"с включённым списком добавились только ЧУЖИЕ пригодные записи",
      set(ids) - set(p["id"] for p in P.PROVIDERS)
      == {"nano-like", "claude-like", "local-like", "two-secrets"})
check(u"РЕЕСТР ВЫИГРЫВАЕТ: у openrouter остался разобранный адрес, а не каталожный",
      P.get_provider("openrouter")["base_url"] == "https://openrouter.ai/api/v1"
      and not P.is_from_catalog("openrouter"))
check(u"наш gemini не подменён каталожным google",
      P.get_provider("gemini")["base_url"].startswith("https://generativelanguage"))
nano = P.get_provider("nano-like")
check(u"у каталожной записи адрес и переменная окружения из каталога",
      nano["base_url"] == "https://nano.example/api/v1"
      and nano["env_names"] == ("NANO_LIKE_API_KEY",))
check(u"каталожная запись помечена как непроверенная",
      P.is_from_catalog("nano-like") and not nano.get("verified"))
check(u"протокол каталожной записи доехал до transport_for",
      P.transport_for("claude-like") == "anthropic"
      and P.transport_for("nano-like") == "openai")

# САМОЕ ВАЖНОЕ: включение полного списка НЕ ДОЛЖНО означать сто шестьдесят
# запросов к незнакомым сервисам при открытии окна выбора. models_public им не
# выставляется никогда — обещать публичный /models по справочнику нельзя, это
# проверяется запросом.
check(u"у каталожной записи нет обещания публичного списка моделей",
      nano.get("models_public") is None)
check(u"без ключа её список моделей не спрашивают",
      P.can_fetch_models("nano-like") is False)
check(u"и в автообход она не попадает",
      "nano-like" not in P.autoscan_targets())
api_keys.set_key("nano-like", "sk-TESTVALUE0123456789")
check(u"с сохранённым ключом спросить можно — это уже выбор пользователя",
      P.can_fetch_models("nano-like") is True)

# Выключение полного списка не должно прятать провайдера, у которого уже есть
# ключ: иначе свой же ключ негде было бы убрать.
api_keys.set_catalog_enabled(False)
check(u"настроенный из каталога остаётся видимым после выключения списка",
      "nano-like" in P.provider_ids() and "claude-like" not in P.provider_ids())
listed_extra = {p["id"]: p for p in P.list_providers()}
check(u"и приходит в панель с пометкой и ссылкой на документацию",
      listed_extra["nano-like"]["from_catalog"] is True
      and listed_extra["nano-like"]["doc"] == "https://docs.nano.example"
      and listed_extra["nano-like"]["catalog_models"] == 2)
check(u"у разобранной записи пометки «из каталога» нет",
      listed_extra["openrouter"]["from_catalog"] is False)
check(u"в описании каталожной записи прямо сказано, что она не проверялась",
      u"не проверял" in listed_extra["nano-like"]["note_ru"]
      and "never tested" in listed_extra["nano-like"]["note_en"])
check(u"про несколько секретов предупреждено словами",
      api_keys.set_key("two-secrets", "sk-TESTVALUE0123456789") is not None)
api_keys.set_catalog_enabled(True)
two = [p for p in P.list_providers() if p["id"] == "two-secrets"][0]
check(u"предупреждение о нескольких значениях видно в описании",
      u"несколько значений" in two["note_ru"] and "several values" in two["note_en"])
api_keys.set_key("nano-like", "")
api_keys.set_key("two-secrets", "")
api_keys.set_catalog_enabled(False)
check(u"после удаления ключей и выключения список снова из семи",
      len(P.provider_ids()) == 7)
check(u"СЫРОГО ключа каталожных записей в списке провайдеров нет",
      "TESTVALUE" not in json.dumps(P.list_providers(), ensure_ascii=False))
CAT.forget()

shutil.rmtree(CFG, ignore_errors=True)
n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
