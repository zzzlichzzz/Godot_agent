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
check(u"наблюдения приложены к записи провайдера",
      orec["stats"].get("models_free") == 57)
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

shutil.rmtree(CFG, ignore_errors=True)
n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
