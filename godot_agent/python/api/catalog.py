# -*- coding: utf-8 -*-
u"""Каталог моделей models.dev — ВТОРИЧНЫЙ источник сведений о моделях.

ГЛАВНОЕ ПРАВИЛО, ВОКРУГ КОТОРОГО ВСЁ ПОСТРОЕНО. Живой ответ провайдера
(/models) — ПЕРВИЧНАЯ правда о том, что доступно ЭТОМУ ключу. Каталог —
ВТОРИЧНАЯ правда о том, что существует в мире и сколько стоит. Каталог только
ЗАПОЛНЯЕТ поля, которых нет в живом ответе, и НИКОГДА их не заменяет; любое
число из каталога в интерфейсе подписано «по каталогу models.dev».

ПОЧЕМУ ЭТО НЕ ПРИДИРКА. Замерено 19.08.2026: у Opencode Zen каталог знает 91
модель, а живой /models отдаёт 62. Оба числа верные, но отвечают на разные
вопросы: «что бывает у этого сервиса» и «что отдадут вашему ключу». Смешать их
в одном утверждении значит соврать, а пользователь после этого выбирает модель,
которой ему не отдают, и получает 404 от провайдера.

ЧТО КАТАЛОГ ДАЁТ СВЕРХ ЖИВОГО ОТВЕТА:
  * цены там, где провайдер их не присылает (Opencode Zen в /models отдаёт
    ТОЛЬКО id, object, created, owned_by — ни цены, ни лимитов);
  * окно контекста и предел вывода (limit.context / limit.output);
  * признак поддержки родного function calling (tool_call) — плагин им не
    пользуется, но знать полезно;
  * status: alpha / beta / deprecated — то есть «провайдер её уже снял».

ЧЕГО ЗДЕСЬ НАМЕРЕННО НЕТ.
  * Список моделей для ВЫБОРА. Живой /models — единственный, кто знает, что
    отдадут ЭТОМУ ключу.
  * Подмена адресов endpoint'ов и имён переменных окружения У НАШИХ СЕМИ.
    У 26 провайдеров каталога поле "api" равно null (google, groq, openai,
    anthropic, azure, amazon-bedrock, vercel — они работают через родной SDK), а
    у deepseek адрес там без "/v1". Расхождения печатаются в вывод сервера
    (compare_registry), но записи реестра правит человек.
  * ПЕРЕБИВАНИЕ ЖИВЫХ ЧИСЕЛ. Если провайдер присылает цену и контекст сам
    (OpenRouter присылает), берутся ЕГО числа, а каталог остаётся ни при чём.
    Замерено, зачем: у moonshotai/kimi-k2.6 каталог показывал 0.95/4.0, а живой
    ответ 0.646/2.72 — то есть подпись «по каталогу» завысила бы цену на 47%.

ОСТАЛЬНЫЕ ПРОВАЙДЕРЫ КАТАЛОГА — ЕСТЬ, НО ОТДЕЛЬНО И С ПОМЕТКОЙ.
Кроме наших семи разобранных записей каталог знает ещё 163 сервиса с рабочим
адресом. Они доступны для выбора, но:
  * только по ЯВНОМУ включению (api_keys «catalog.enabled»), а не по умолчанию;
  * своей группой в окне выбора и с пометкой «из каталога, не проверено»;
  * БЕЗ обещаний, которых каталог дать не может: models_public не выставляется
    никогда (значит список моделей у них не спрашивают без ключа и не трогают
    при обходе), verified остаётся False, особых таймаутов нет.
Причина такой осторожности не в лени: наш реестр держит знание, которого в
каталоге нет — белый список клиентов AgentRouter, ловушка api.opencode.ai
(отвечает 200 с текстом «Not Found»), connect_timeout=150 для посредника.
Смешать проверенное с непроверенным в одном списке значит потерять разницу.

ПОЧЕМУ 166, А НЕ 192. У 26 записей каталога нет поля "api" — им нужен родной
SDK провайдера (opencode так и делает через npm-пакеты), а у нас единственный
транспорт это HTTP: OpenAI-совместимый /chat/completions и Anthropic /messages.
Показать такого провайдера значило бы предложить выбор, который заведомо не
заработает. Замерено: из 166 пригодных 153 помечены npm
«@ai-sdk/openai-compatible», 8 — «@ai-sdk/anthropic», 3 — «@ai-sdk/openai».

ЗАМЕРЕННЫЕ ФАКТЫ О САЙТЕ (19.08.2026, живыми запросами):
  * ЭНДПОИНТОВ ТРИ, а не один (документировано в README репозитория):
      api.json      390 КБ с gzip / 3.8 МБ — провайдеры И их модели вместе;
      models.json    30 КБ с gzip / 0.3 МБ — 352 записи О МОДЕЛЯХ, без
                     привязки к провайдеру;
      catalog.json  419 КБ с gzip / 4.1 МБ — и то, и другое.
    Берём api.json, и это не лень: цены и лимиты ЗАВИСЯТ ОТ ПРОВАЙДЕРА (один и
    тот же GPT у OpenRouter и у Opencode Zen стоит разное, у второго ещё и окно
    другое), а models.json про провайдеров не знает вовсе. Соблазн взять
    маленький models.json стоит запомнить как ложный: он отвечает на другой
    вопрос. Есть ещё /logos/<provider>.svg — логотипы, нам пока не нужны.
  * urllib НЕ распаковывает gzip сам — нужен gzip.decompress, иначе прилетит
    3.8 МБ вместо 390 КБ.
  * Отдаётся ETag вида W/"...", Last-Modified НЕТ. Условный запрос
    If-None-Match работает. ВНИМАНИЕ: urllib считает 304 ошибкой — её надо
    ловить как HTTPError и проверять e.code == 304.
  * ЛОВУШКА: https://models.dev/api/<id>.json отвечает 200, но это HTML самого
    сайта (1.8 МБ), а не JSON. Постранично каталог не отдаётся — только целиком.
  * 192 провайдера, 6611 моделей. В кэш кладём ТОЛЬКО своих и только нужные
    поля: замерено 59 КБ вместо 3.8 МБ.
  * ПРО «91 ПРОТИВ 62» У OPENCODE ZEN. Каталог знает 91 модель, живой /models
    отдаёт 62 — и это НЕ завышение каталога, как показалось сначала. Ровно 29
    записей помечены status="deprecated", и это РОВНО те 29, которых нет
    живьём; у всех 62 живых статуса нет. Совпадение полное, 29 из 29. То есть
    каталог честно помечает снятые модели, а поле status надо читать, а не
    считать все записи доступными.
  * Данные живые: по всем 192 провайдерам самая свежая правка записи — сутки
    назад, у openrouter пять дней, у groq 51 день. Сверка с живым ответом
    OpenRouter (единственный из наших, кто отдаёт цены сам): из 353 совпавших
    моделей окно контекста расходится у 0, цена ввода у 2, цена вывода у 1.

ПОЧЕМУ ОТДЕЛЬНЫЙ ФАЙЛ КЭША, А НЕ api_keys.json. Файл настроек перечитывается
целиком по несколько раз за один HTTP-запрос (ключ, модель, адрес,
наблюдения) — 59 КБ лишнего JSON на каждое обращение. И вторая причина
важнее: в настройках лежат КЛЮЧИ, и чем меньше кода трогает тот файл, тем
меньше шансов, что секрет уедет туда, где его не ждут.

СЕКРЕТОВ ЗДЕСЬ НЕТ И БЫТЬ НЕ МОЖЕТ. Запрос к каталогу уходит БЕЗ единого
ключа в заголовках: models.dev — публичный справочник, ключ ему не нужен, а
отправить его туда «на всякий случай» значит подарить секрет третьей стороне.
Прокси берётся из настроек (api_keys.proxy_url), DoH применяется сам — он
патчит getaddrinfo на весь процесс.
"""
import gzip
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import api_keys

# АДРЕС КОНСТАНТОЙ МОДУЛЯ, а не строкой внутри функции: тест подменяет его на
# локальный HTTP-сервер. Прогон тестов не должен ходить в сеть — иначе он
# падает на машине без интернета и стучится в чужой сервис при каждом запуске.
CATALOG_URL = "https://models.dev/api.json"

_FILE_NAME = "catalog_cache.json"

# Сколько каталог считается свежим. НЕДЕЛЯ, а не сутки как у живых списков
# моделей: каталог описывает, что существует в мире и сколько стоит, а это
# меняется не ежечасно. Живой /models при этом обновляется по-прежнему раз в
# сутки — он отвечает на другой вопрос («что отдадут вашему ключу»), и его
# свежесть важнее.
FRESH_SECONDS = 7 * 24 * 60 * 60
# Пауза после неудачи загрузки. Час: неудача чаще всего значит «в этот момент
# не было сети», и держать пользователя без цен до следующей недели из-за
# минутного обрыва незачем. Но и повторять на каждое открытие окна нельзя —
# ожидание ответа от недоступного хоста человек видит как задумчивость плагина.
RETRY_SECONDS = 60 * 60

# Сколько ждать ответа каталога. Заметно меньше обычного таймаута запроса:
# каталог — удобство, и он обновляется внутри обхода провайдеров, за которым
# пользователь смотрит на открытый экран настроек.
CONNECT_TIMEOUT = 20.0

# Предохранитель на случай, если по адресу окажется не каталог. 4 МБ — это
# измеренный размер РАСПАКОВАННОГО ответа; берём запас, но не бесконечность:
# читать в память чужой мегабайтный HTML (см. ловушку /api/<id>.json в
# заголовке модуля) незачем.
MAX_BYTES = 32 * 1024 * 1024

# СООТВЕТСТВИЕ НАШИХ ИДЕНТИФИКАТОРОВ ИХ. Проверено живым запросом: у нас
# "gemini" — у них "google", у нас "opencode_zen" — у них "opencode".
# Соответствие применяется ОДИН РАЗ при записи кэша, поэтому ключи в кэше и во
# всех функциях чтения — НАШИ идентификаторы. Иначе каждое место чтения
# помнило бы про переименование, и однажды одно из них забыли бы.
PROVIDER_MAP = {
    "openrouter": "openrouter",
    "groq": "groq",
    "gemini": "google",
    "opencode_zen": "opencode",
    "deepseek": "deepseek",
}

# Провайдеры нашего реестра, которых в каталоге нет, — с причиной. Список
# ЯВНЫЙ, а не «всё остальное»: тест сверяет его с providers.PROVIDERS и падает,
# если добавили провайдера и не решили, есть ли он в каталоге. Молчаливое
# отсутствие выглядело бы как «каталог про него ничего не знает», хотя на самом
# деле про него забыли здесь.
NOT_IN_CATALOG = {
    "agentrouter": u"в каталоге models.dev такой записи нет вовсе",
    "custom": u"свой адрес — что за ним, знает только пользователь",
}


# Статусы, которые каталог ставит модели. Читать их обязательно: у Opencode Zen
# ровно 29 записей из 91 помечены deprecated, и это РОВНО те, которых нет в
# живом /models. Не читая status, легко решить, что каталог завышает число
# моделей, — именно так я и решил сначала.
STATUS_DEPRECATED = "deprecated"
_KNOWN_STATUS = ("alpha", "beta", STATUS_DEPRECATED)

# Поля, которые каталог МОЖЕТ дописать в запись модели. Список нужен снаружи:
# запись в панели должна знать, какие числа пришли от каталога, а какие от самого
# провайдера, — подписи у них разные («по каталогу models.dev» против «по ответу
# провайдера»), и перепутать их значит соврать про источник.
FILLABLE = ("cost_in", "cost_out", "context", "max_output", "tool_call")

# Сколько провайдеров каталога держать в кэше. 166 пригодных сейчас (замерено);
# запас на рост, но не бесконечность — файл читается целиком на каждый запрос
# настроек. Метаданные 166 записей это 37 КБ (замерено), 400 дадут около 90.
MAX_PROVIDERS = 400
# Ограничения на строки из чужого JSON: они попадают в интерфейс и в адрес
# запроса. Длина взята с большим запасом от настоящих (самый длинный адрес
# каталога — 52 символа).
MAX_NAME_LEN = 80
MAX_URL_LEN = 300
MAX_ENV_NAMES = 4


def catalog_path():
    """Путь к кэшу каталога. Отдельный файл от настроек и от кэша списков
    моделей: см. пояснение в заголовке модуля."""
    return os.path.join(api_keys.config_dir(), _FILE_NAME)


# ---------------------------------------------------------------------------
# Чтение и запись кэша
# ---------------------------------------------------------------------------

def _num_or_none(value):
    """Число из чужого JSON или None. Строку не принимаем намеренно: цена,
    пришедшая строкой, — признак другого формата, и молча превращать её в
    число значит однажды показать пользователю цену от другой версии API."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _clean_model(rec):
    u"""Одна модель каталога в компактном виде: только нужные поля.

    ПОЧЕМУ НЕ ЦЕЛИКОМ. Полный каталог — 4 МБ на 192 провайдера; запись модели
    несёт description, family, modalities, reasoning_options, release_date и
    прочее, чего интерфейс не показывает. Отобранные пять полей дают 59 КБ
    (замерено) — разница в семьдесят раз при том же результате на экране.

    ОТСУТСТВУЮЩЕЕ ПОЛЕ НЕ ВЫДУМЫВАЕТСЯ. Нет цены — нет ключа cost_in, и в
    интерфейсе про цену этой модели не сказано ничего. Ноль вместо
    отсутствующей цены означал бы «бесплатная», а это обещание за сервис:
    измерено, что у 15 моделей наших провайдеров (openrouter/auto, whisper-*,
    veo-*) поля cost нет вовсе.
    """
    if not isinstance(rec, dict):
        return None
    out = {}
    cost = rec.get("cost") if isinstance(rec.get("cost"), dict) else {}
    # tiers НЕ разбираем. У 300+ моделей каталога цена зависит от размера
    # контекста (tiers, context_over_200k), но верхний уровень input/output при
    # этом всегда заполнен базовым тарифом — проверено по всем 192
    # провайдерам. Показать базовый тариф честно; выбрать за пользователя один
    # из ярусов и назвать его ценой — нет.
    cin = _num_or_none(cost.get("input"))
    cout = _num_or_none(cost.get("output"))
    if cin is not None:
        out["cost_in"] = cin
    if cout is not None:
        out["cost_out"] = cout
    lim = rec.get("limit") if isinstance(rec.get("limit"), dict) else {}
    ctx = _num_or_none(lim.get("context"))
    mout = _num_or_none(lim.get("output"))
    if ctx is not None and ctx > 0:
        out["context"] = int(ctx)
    if mout is not None and mout > 0:
        out["max_output"] = int(mout)
    if isinstance(rec.get("tool_call"), bool):
        out["tool_call"] = bool(rec["tool_call"])
    # status — короткая строка, но именно она отличает «каталог знает модель» от
    # «каталог знает, что модель уже сняли». Неизвестные значения отбрасываем:
    # схема каталога перечисляет ровно три, и молча пропускать четвёртое
    # значило бы показать пользователю слово, которого мы не понимаем.
    status = str(rec.get("status") or "").strip().lower()
    if status in _KNOWN_STATUS:
        out["status"] = status
    return out


def is_free(info):
    u"""Бесплатна ли модель ПО КАТАЛОГУ: обе цены известны и равны нулю.

    ОТДЕЛЬНАЯ функция от providers.is_free_model, а не замена ей. Та судит по
    ответу самого провайдера (суффикс :free/-free и pricing), эта — по
    справочнику. Расхождения бывают и полезны: замерено, что у Opencode Zen
    модель big-pickle имеет в каталоге нулевую цену, а по нашей эвристике
    (суффикса нет) выглядит платной. Это выигрыш каталога, но заявлять его
    надо от имени каталога, а не подменяя ответ провайдера.

    Неизвестная цена — НЕ бесплатная. Иначе 15 моделей без поля cost
    (openrouter/auto, whisper-*, veo-*) объявились бы бесплатными.
    """
    if not isinstance(info, dict):
        return False
    if "cost_in" not in info or "cost_out" not in info:
        return False
    try:
        return float(info["cost_in"]) == 0.0 and float(info["cost_out"]) == 0.0
    except Exception:
        return False


def _empty_cache():
    return {"version": 1, "at": 0.0, "etag": "", "error": "", "try_at": 0.0,
            "providers": {}, "catalog_providers": {}}


# ---------------------------------------------------------------------------
# Реестр ВСЕХ пригодных провайдеров каталога
#
# Отдельно от секции "providers": там модели наших пяти разобранных записей, а
# здесь метаданные всех, кого можно предложить на выбор. Разделение по размеру:
# метаданные 166 провайдеров — 37 КБ, а те же 166 вместе со всеми их 5555
# моделями — 680 КБ (замерено), и этот файл читается целиком на каждый запрос
# настроек. Модели держим только у тех, кого пользователь реально выбрал.
# ---------------------------------------------------------------------------

# Транспорт по имени npm-пакета из каталога. У нас их два: OpenAI-совместимый
# /chat/completions и Anthropic /messages — оба уже написаны и работают. Всё
# незнакомое считаем OpenAI-совместимым: 153 из 166 записей помечены именно
# «@ai-sdk/openai-compatible», и это же поведение по умолчанию у самого каталога
# (поле api обязательно только для openai-compatible).
_NPM_TRANSPORT = {
    "@ai-sdk/anthropic": "anthropic",
}


def transport_for_npm(npm):
    return _NPM_TRANSPORT.get(str(npm or "").strip(), "openai")


def _clean_url(raw):
    u"""Адрес endpoint'а из каталога или "" — если он нам не годится.

    ОТБРАКОВЫВАЕМ ТРИ ВИДА МУСОРА, все встречены живьём:
      * отсутствие поля вовсе (26 записей из 192 — им нужен родной SDK);
      * неподставленный шаблон «${NEON_AI_GATEWAY_BASE_URL}/v1» (1 запись) —
        схемы в нём нет, и запрос по такому адресу упал бы сетевой ошибкой;
      * что угодно, что не проходит нашу же проверку адреса endpoint'а.
    Локальные http://127.0.0.1:… (lmstudio, lynkr, privatemode-ai,
    atomic-chat — 4 записи) НЕ отбраковываем: это локальные серверы, и
    транспорт умеет с ними работать, не гоняя их через прокси.
    """
    s = str(raw or "").strip()
    if not s or len(s) > MAX_URL_LEN or "${" in s:
        return ""
    clean, err = api_keys.validate_base_url(s)
    return "" if err else clean


def _clean_provider_meta(pid, rec):
    u"""Метаданные одного провайдера каталога или None.

    Модели здесь НЕ хранятся — только их количество, чтобы в списке выбора было
    видно, у кого их сколько, не читая 680 КБ.
    """
    if not isinstance(rec, dict):
        return None
    api_url = _clean_url(rec.get("api"))
    if not api_url:
        return None
    env = []
    for name in (rec.get("env") or [])[:MAX_ENV_NAMES]:
        name = str(name or "").strip()
        # Имя переменной окружения уходит в os.environ.get и в интерфейс.
        # Пропускаем только то, что похоже на имя переменной.
        if name and len(name) <= MAX_NAME_LEN and name.replace("_", "").isalnum():
            env.append(name)
    models = rec.get("models") if isinstance(rec.get("models"), dict) else {}
    total = 0
    free = 0
    for m in models.values():
        if not isinstance(m, dict):
            continue
        if str(m.get("status") or "") == STATUS_DEPRECATED:
            # Снятые не считаем: «у него 100 моделей», где часть провайдер уже
            # не отдаёт, — завышение, по которому человек и выберет.
            continue
        total += 1
        if is_free(_clean_model(m) or {}):
            free += 1
    return {
        "id": str(pid),
        "name": str(rec.get("name") or pid)[:MAX_NAME_LEN],
        "api": api_url,
        "env": env,
        "doc": _clean_url(rec.get("doc")) or "",
        "transport": transport_for_npm(rec.get("npm")),
        # Числа ПО КАТАЛОГУ, а не измеренные у этого ключа. Панель подписывает их
        # отдельно: сколько моделей отдадут именно вам, знает только сам сервис.
        "models_total": total,
        "models_free": free,
        # Несколько переменных окружения означает, что одного ключа сервису
        # мало (cloudflare-workers-ai хочет ACCOUNT_ID + API_KEY,
        # snowflake-cortex — ACCOUNT + PAT). Наша форма умеет один ключ, поэтому
        # честно предупреждаем, а не делаем вид, что всё получится.
        "multi_secret": len(env) > 1,
    }


def _compact_providers(data):
    """Метаданные всех пригодных провайдеров каталога: {catalog_id: {...}}."""
    out = {}
    for pid, rec in sorted(data.items()):
        meta = _clean_provider_meta(pid, rec)
        if meta is not None:
            out[str(pid)] = meta
        if len(out) >= MAX_PROVIDERS:
            break
    return out


def _load():
    u"""Кэш каталога с диска. Любая проблема чтения — ПУСТОЙ кэш.

    Каталог — удобство: он добавляет цены и лимиты к тому, что и так работает.
    Ронять из-за него сервер или экран настроек нельзя, поэтому битый файл
    здесь равносилен «каталога пока нет», и следующий обход попробует загрузить
    его заново.
    """
    p = catalog_path()
    if not os.path.isfile(p):
        return _empty_cache()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(u"[catalog] Кэш каталога не читается (%s) — считаю его пустым." % e)
        return _empty_cache()
    if not isinstance(data, dict):
        return _empty_cache()
    out = _empty_cache()
    try:
        out["at"] = float(data.get("at") or 0.0)
    except Exception:
        out["at"] = 0.0
    try:
        out["try_at"] = float(data.get("try_at") or 0.0)
    except Exception:
        out["try_at"] = 0.0
    out["etag"] = str(data.get("etag") or "")
    out["error"] = str(data.get("error") or "")
    known = data.get("catalog_providers")
    if isinstance(known, dict):
        for pid, rec in known.items():
            # Метаданные прогоняем через ту же проверку, что и при записи: файл
            # мог быть испорчен или собран другой версией, а адрес отсюда уходит
            # прямо в запрос.
            meta = _clean_provider_meta(str(pid), dict(
                rec if isinstance(rec, dict) else {},
                # В кэше уже посчитанные числа и готовый транспорт, а
                # _clean_provider_meta ждёт форму каталога — models там нет,
                # поэтому числа переносим руками ниже.
                models={}))
            if meta is None:
                continue
            if isinstance(rec, dict):
                meta["models_total"] = _int_or_zero(rec.get("models_total"))
                meta["models_free"] = _int_or_zero(rec.get("models_free"))
                meta["transport"] = ("anthropic"
                                     if str(rec.get("transport")) == "anthropic"
                                     else "openai")
            out["catalog_providers"][str(pid)] = meta
            if len(out["catalog_providers"]) >= MAX_PROVIDERS:
                break
    src = data.get("providers")
    if isinstance(src, dict):
        # Чьи модели вообще имеют право лежать в кэше: пять разобранных записей
        # реестра плюс те, кого пользователь выбрал из полного списка каталога.
        # Остальное отбрасываем — кэш мог остаться от версии с другим набором, и
        # «каталог знает про провайдера, которого у нас нет» это мусор в
        # интерфейсе, а не знание.
        allowed = set(PROVIDER_MAP) | set(out["catalog_providers"])
        for pid, rec in src.items():
            pid = str(pid)
            if pid not in allowed or not isinstance(rec, dict):
                continue
            models = {}
            src_models = rec.get("models")
            if isinstance(src_models, dict):
                for mid, info in src_models.items():
                    mid = str(mid or "").strip()
                    clean = _clean_model_stored(info)
                    if mid and clean is not None:
                        models[mid] = clean
            out["providers"][pid] = {
                "catalog_id": str(rec.get("catalog_id") or pid),
                "name": str(rec.get("name") or ""),
                "models": models,
            }
    return out


def _int_or_zero(value):
    if isinstance(value, bool):
        return 0
    try:
        n = int(value)
    except Exception:
        return 0
    return n if n >= 0 else 0


def _clean_model_stored(info):
    u"""Запись модели, прочитанная из НАШЕГО кэша.

    Отдельно от _clean_model: та разбирает формат models.dev (cost.input,
    limit.context), а эта — уже отобранные поля. Один разбор на два формата
    однажды принял бы чужую форму за свою и записал бы None вместо цены.
    """
    if not isinstance(info, dict):
        return None
    out = {}
    for key in ("cost_in", "cost_out"):
        val = _num_or_none(info.get(key))
        if val is not None:
            out[key] = val
    for key in ("context", "max_output"):
        val = _num_or_none(info.get(key))
        if val is not None and val > 0:
            out[key] = int(val)
    if isinstance(info.get("tool_call"), bool):
        out["tool_call"] = bool(info["tool_call"])
    status = str(info.get("status") or "").strip().lower()
    if status in _KNOWN_STATUS:
        out["status"] = status
    return out


def _save(cache):
    """Запись через временный файл + os.replace: обрыв на середине не оставляет
    полуфабрикат вместо кэша."""
    p = catalog_path()
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(tmp, p)
        return True
    except Exception as e:
        print(u"[catalog] Не удалось сохранить кэш каталога (%s)" % e)
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Загрузка
# ---------------------------------------------------------------------------

def _fetch(etag=""):
    u"""Каталог с models.dev. Возвращает (данные_или_None, etag, ошибка).

    (None, etag, "") означает 304 Not Modified — данные на сервере те же, кэш
    трогать не надо.

    БЕЗ КЛЮЧЕЙ В ЗАГОЛОВКАХ. models.dev — публичный справочник; Authorization
    здесь не собирается вообще, и это проверяется тестом (test_api_routes
    ловит попадание ключа в запрос каталога).
    """
    import openai_compat  # только за USER_AGENT: имя клиента одно на весь плагин

    req = urllib.request.Request(CATALOG_URL, method="GET")
    req.add_header("User-Agent", openai_compat.USER_AGENT)
    req.add_header("Accept", "application/json")
    # ЗАЧЕМ ЯВНЫЙ gzip. Без этого заголовка ответ приходит несжатым — 4.0 МБ
    # вместо 399 КБ (замерено). urllib сам его не запрашивает и сам НЕ
    # распаковывает, поэтому ниже gzip.decompress вручную.
    req.add_header("Accept-Encoding", "gzip")
    if etag:
        req.add_header("If-None-Match", etag)
    # Прокси — только для внешнего адреса. Локальный (так подменяет адрес тест)
    # через прокси гнать нельзя: ровно эта ошибка уже ломала обращения к своему
    # серверу, см. openai_compat._build_opener.
    proxy = api_keys.proxy_url()
    if openai_compat.is_local_host(
            urllib.parse.urlsplit(CATALOG_URL).hostname or ""):
        proxy = None
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        if proxy else urllib.request.ProxyHandler({}))
    try:
        resp = opener.open(req, timeout=CONNECT_TIMEOUT)
    except urllib.error.HTTPError as e:
        # 304 — это УСПЕХ, а не ошибка: сервер сообщил, что наш кэш актуален.
        # urllib поднимает его исключением, и без этой ветки каждая проверка
        # свежести выглядела бы как неудача загрузки каталога.
        if e.code == 304:
            return None, etag, ""
        return None, etag, u"каталог models.dev ответил HTTP %s" % e.code
    except Exception as e:
        return None, etag, u"каталог models.dev недоступен: %s" % e
    try:
        raw = resp.read(MAX_BYTES + 1)
        new_etag = resp.headers.get("ETag") or ""
        encoding = (resp.headers.get("Content-Encoding") or "").lower()
    finally:
        try:
            resp.close()
        except Exception:
            pass
    if len(raw) > MAX_BYTES:
        return None, etag, u"ответ каталога больше %d МБ — это не каталог" % (
            MAX_BYTES // (1024 * 1024))
    if "gzip" in encoding:
        try:
            raw = gzip.decompress(raw)
        except Exception as e:
            return None, etag, u"ответ каталога не распаковался: %s" % e
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception as e:
        # Сюда попадает и ловушка постраничного доступа: /api/<id>.json
        # отвечает 200 с HTML самого сайта. Текст ошибки должен позволить
        # опознать это по журналу, поэтому в него идёт начало ответа.
        head = raw[:80].decode("utf-8", "replace").replace("\n", " ")
        return None, etag, u"каталог пришёл не в JSON (%s): %s" % (e, head)
    if not isinstance(data, dict) or not data:
        return None, etag, u"каталог пришёл в неожидаемом виде"
    return data, (new_etag or etag), ""


def _compact(data, extra_ids=()):
    u"""Модели для тех, у кого они нам нужны. Ключи — НАШИ идентификаторы.

    Всегда: пять разобранных записей реестра (PROVIDER_MAP) — их модели нужны
    для цен и лимитов в списке выбора.
    По просьбе: провайдеры из полного списка каталога, которых пользователь
    выбрал сам (extra_ids). Держать модели ВСЕХ 166 нельзя — замерено 680 КБ
    против 90 КБ, а файл читается целиком на каждый запрос настроек.

    Провайдер, которого в каталоге не нашлось, в кэш не попадает: пустая запись
    означала бы «каталог знает о нём и у него нет моделей», а это другое
    утверждение.
    """
    wanted = dict(PROVIDER_MAP)
    for pid in extra_ids or ():
        pid = str(pid or "").strip()
        # У выбранного из каталога наш идентификатор совпадает с его: отдельного
        # соответствия для них нет и быть не может.
        if pid and pid not in wanted:
            wanted[pid] = pid
    out = {}
    for our, theirs in wanted.items():
        rec = data.get(theirs)
        if not isinstance(rec, dict):
            continue
        src = rec.get("models")
        if not isinstance(src, dict):
            continue
        models = {}
        for mid, info in src.items():
            mid = str(mid or "").strip()
            clean = _clean_model(info)
            if mid and clean is not None:
                models[mid] = clean
        if not models:
            continue
        out[our] = {"catalog_id": theirs,
                    "name": str(rec.get("name") or ""),
                    "models": models}
    return out


def refresh(force=False, extra_ids=()):
    u"""Обновляет кэш каталога, если пора. Возвращает (обновлён, ошибка).

    (False, "") — обновлять было нечего: кэш свежий, или после неудачи ещё не
    прошла пауза. Это НЕ ошибка, и сообщать о нём пользователю незачем.

    extra_ids — провайдеры из полного списка каталога, которых пользователь
    выбрал сам: для них тоже нужны модели (цены и лимиты). Для остальных 160+
    хранятся только метаданные — иначе кэш вырастет с 90 КБ до 680 (замерено).

    НЕУДАЧА ЗДЕСЬ НЕ ДОЛЖНА НИЧЕГО ЛОМАТЬ. Функция вызывается из обхода
    провайдеров (/api/models/scan), и исключение отсюда сорвало бы обновление
    списков моделей У ВСЕХ — то есть отсутствие интернета у models.dev
    выглядело бы как «плагин перестал видеть провайдеров». Поэтому наружу
    уходит текст причины, а не исключение, и прежний кэш при неудаче
    сохраняется: каталог, загруженный неделю назад, полезнее пустоты.
    """
    cache = _load()
    need_models = _missing_models(cache, extra_ids)
    if not force and not is_stale(cache) and not need_models:
        return False, ""
    # ЕСЛИ НУЖНЫ МОДЕЛИ ВЫБРАННОГО ПРОВАЙДЕРА — ИДЁМ БЕЗ If-None-Match.
    # Иначе сервер честно отвечает 304 (каталог и правда не менялся), тела нет,
    # и модели взять негде: пользователь выбрал провайдера и остался без цен до
    # следующего изменения каталога, то есть, возможно, на неделю. Условный
    # запрос экономит трафик только когда данные у нас полные.
    data, etag, err = _fetch("" if need_models else (cache.get("etag") or ""))
    now = time.time()
    if err:
        cache["error"] = err
        cache["try_at"] = now
        _save(cache)
        print(u"[catalog] %s" % err)
        return False, err
    if data is None:
        # 304: содержимое то же. Обновляем только отметку времени, иначе
        # неизменившийся каталог считался бы устаревшим при каждой проверке и
        # мы ходили бы к models.dev раз в открытие окна вместо раза в неделю.
        cache["at"] = now
        cache["error"] = ""
        cache["try_at"] = 0.0
        _save(cache)
        print(u"[catalog] Каталог models.dev не менялся (304), кэш оставлен как есть")
        return False, ""
    compact = _compact(data, extra_ids)
    if not compact:
        err = u"в каталоге не нашлось ни одного знакомого провайдера"
        cache["error"] = err
        cache["try_at"] = now
        _save(cache)
        print(u"[catalog] %s" % err)
        return False, err
    cache["providers"] = compact
    cache["catalog_providers"] = _compact_providers(data)
    cache["etag"] = etag
    cache["at"] = now
    cache["error"] = ""
    cache["try_at"] = 0.0
    if not _save(cache):
        return False, u"кэш каталога не удалось записать на диск"
    total = sum(len(r["models"]) for r in compact.values())
    print(u"--> Каталог models.dev обновлён: моделей %d у %d провайдеров, "
          u"пригодных для выбора записей %d (из %d в каталоге)"
          % (total, len(compact), len(cache["catalog_providers"]), len(data)))
    for line in compare_registry(data):
        # Расхождение реестра и каталога — ПЕЧАТАЕМ, а не применяем. Реестр
        # правит человек: адреса в каталоге есть не у всех (у groq, google,
        # anthropic, openai поле "api" равно null), и подмена вслепую сломала бы
        # рабочего провайдера.
        print(u"[catalog] %s" % line)
    return True, ""


def _missing_models(cache, extra_ids):
    u"""Есть ли выбранный провайдер, чьих моделей в кэше ещё нет.

    Нужно, чтобы выбор провайдера из полного списка не ждал недельного срока
    свежести: сразу после выбора у него не было бы ни цен, ни лимитов, и
    пользователь решил бы, что каталог про него не знает. Условный запрос при
    этом дешёвый — 304 без тела, если каталог не менялся.
    """
    have = cache.get("providers") or {}
    for pid in extra_ids or ():
        pid = str(pid or "").strip()
        if pid and pid not in have:
            return True
    return False


def compare_registry(data=None):
    u"""Расхождения нашего реестра и каталога — СПИСКОМ СТРОК для журнала.

    Замерено 19.08.2026: у deepseek каталог даёт адрес без «/v1»
    (https://api.deepseek.com против нашего https://api.deepseek.com/v1), а у
    google знает лишнее имя переменной окружения
    (GOOGLE_GENERATIVE_AI_API_KEY). Первое — разница в оформлении пути,
    второе — реальная польза: у кого эта переменная задана, тот сейчас увидит
    «ключ не задан».

    Ничего не меняет и ничего не решает: это подсказка тому, кто читает вывод
    сервера. Возвращает [] когда сравнивать нечего.
    """
    import providers  # локально: providers импортирует api_keys, а не нас

    out = []
    if data is None:
        # Сравнивать по кэшу нельзя: адреса и переменные окружения в него не
        # попадают (в кэше только модели). Значит без свежего ответа каталога
        # сравнивать просто нечего.
        return out
    for our, theirs in PROVIDER_MAP.items():
        rec = data.get(theirs)
        if not isinstance(rec, dict):
            out.append(u"провайдера «%s» (в каталоге «%s») в каталоге нет"
                       % (our, theirs))
            continue
        reg = providers.get_provider(our) or {}
        api = str(rec.get("api") or "")
        ours_url = str(reg.get("base_url") or "")
        if api and ours_url and api.rstrip("/") != ours_url.rstrip("/"):
            out.append(u"адрес «%s»: в реестре %s, в каталоге %s — реестр "
                       u"правит человек, менять автоматически нельзя"
                       % (our, ours_url, api))
        env = [str(e) for e in (rec.get("env") or []) if e]
        ours_env = tuple(reg.get("env_names") or ())
        extra = [e for e in env if e not in ours_env]
        if extra:
            out.append(u"переменные окружения «%s»: каталог знает ещё %s — "
                       u"у кого они заданы, тот сейчас видит «ключ не задан»"
                       % (our, ", ".join(extra)))
    return out


# ---------------------------------------------------------------------------
# Чтение наружу
# ---------------------------------------------------------------------------

def get(provider_id):
    u"""Модели провайдера ПО КАТАЛОГУ: {model_id: {cost_in, cost_out, context,
    max_output, tool_call, status}}. Ничего не известно — пустой словарь.

    Ключ — НАШ идентификатор провайдера. Для пяти разобранных записей он
    отличается от каталожного (см. PROVIDER_MAP), для выбранных из полного
    списка совпадает с ним — соответствие применено один раз при записи кэша.

    Это НЕ список для выбора модели: у Opencode Zen в каталоге 91 запись против
    62 живых, и 29 из них сам каталог помечает снятыми.
    """
    rec = (_load().get("providers") or {}).get(str(provider_id or ""))
    return dict((rec or {}).get("models") or {})


def known_providers():
    u"""Все пригодные провайдеры каталога: {catalog_id: {метаданные}}.

    Пригодный — значит с рабочим адресом endpoint'а. Из 192 записей их 166
    (замерено): у остальных поля "api" нет вовсе, им нужен родной SDK, и
    предлагать их на выбор значило бы обещать то, чего наш транспорт не умеет.

    ЗДЕСЬ НЕТ МОДЕЛЕЙ — только их количество. Метаданные 166 записей это 37 КБ,
    те же записи вместе с моделями — 680 КБ, а файл читается целиком на каждый
    запрос настроек.
    """
    return dict(_load().get("catalog_providers") or {})


def provider_meta(catalog_id):
    """Метаданные одного провайдера каталога или пустой словарь."""
    return dict(known_providers().get(str(catalog_id or "")) or {})


def model_info(provider_id, model_id):
    u"""Сведения каталога об ОДНОЙ модели или пустой словарь.

    ТОЧНОЕ совпадение идентификатора, без «отбросить суффикс и поискать
    базовую модель». Замерено: у OpenRouter 62 модели из 415 не нашлись в
    каталоге, и все они — варианты с суффиксом «:batch», у которых ДРУГОЙ
    тариф. Подставить им цену базовой модели значит показать пользователю
    неверную цену с чужой подписью «по каталогу».
    """
    return dict(get(provider_id).get(str(model_id or "")) or {})


def enrich(provider_id, records):
    u"""Дополняет записи моделей полями каталога. Возвращает НОВЫЙ список.

    ЗАПОЛНЯЕТ, А НЕ ЗАМЕНЯЕТ. Поле, которое уже есть в записи (пришло из
    живого ответа провайдера), не трогается: живой ответ — первичная правда о
    том, что доступно этому ключу. OpenRouter, например, присылает цену и окно
    контекста сам, и они точнее: замерено, что у moonshotai/kimi-k2.6 каталог
    отстал и завышал цену на 47%.

    КАЖДОЕ ДОПИСАННОЕ ПОЛЕ ЗАПИСЫВАЕТСЯ В "from_catalog". Без этого списка
    нельзя отличить число от провайдера от числа из справочника, а подписи у
    них разные — и «по каталогу models.dev» под живой ценой это ровно то
    враньё об источнике, ради предотвращения которого весь модуль и написан.

    Признак бесплатности из каталога кладётся в ОТДЕЛЬНОЕ поле catalog_free,
    рядом с нашим free, а не вместо него. Расхождения бывают (Opencode Zen
    big-pickle: в каталоге ноль, по суффиксу платная).
    """
    known = get(provider_id)
    out = []
    for rec in list(records or []):
        if isinstance(rec, dict):
            item = dict(rec)
        else:
            item = {"id": str(rec or ""), "free": False}
        info = known.get(str(item.get("id") or "")) if known else None
        if info:
            filled = []
            for key in FILLABLE:
                if key in info and key not in item:
                    # Не setdefault: нужно ЗНАТЬ, дописали мы поле или оно уже
                    # было от провайдера.
                    item[key] = info[key]
                    filled.append(key)
            if filled:
                item["from_catalog"] = filled
            item["catalog_free"] = is_free(info)
            status = str(info.get("status") or "")
            if status:
                item["status"] = status
            if status == STATUS_DEPRECATED:
                # Провайдер её ещё отдаёт, а каталог считает снятой. Само по
                # себе не запрет, но пользователь должен это увидеть ДО того,
                # как закрепит модель за чатом: закреплённую не сменить.
                item["deprecated"] = True
        out.append(item)
    return out


def count_free(provider_id, records):
    u"""Сколько записей помечено бесплатными ПО КАТАЛОГУ. -1 — «не считали».

    Считается по тем же записям, что и models_free (живой список провайдера), —
    иначе два числа рядом отвечали бы на разные вопросы, а выглядели бы как
    сравнение. «91 модель в каталоге» и «62 живых» — как раз тот случай.

    -1, А НЕ НОЛЬ, когда каталог про этого провайдера молчит или не узнал ни
    одной его модели. Ноль означал бы утверждение «каталог проверил и
    бесплатных не нашёл», а «каталог про них ничего не сказал» — совсем другое
    сведение, и панель показывает его отдельной строкой. Так же, как -1 в
    models_free отличает «не измеряли» от честного «бесплатных нет».
    """
    known = get(provider_id)
    if not known:
        return -1
    matched = 0
    free = 0
    for rec in list(records or []):
        if not isinstance(rec, dict) or str(rec.get("id") or "") not in known:
            continue
        matched += 1
        if rec.get("catalog_free"):
            free += 1
    return free if matched else -1


def age(cache=None):
    u"""Сколько секунд прошло с последней УДАЧНОЙ проверки каталога.

    -1 означает «каталог никогда не загружался» и отличается от честного 0:
    панель показывает это разными строками, потому что «цен пока нет, каталог
    не грузился» и «цены из каталога, обновлён только что» — разные сведения.
    """
    cache = _load() if cache is None else cache
    at = float(cache.get("at") or 0.0)
    if at <= 0:
        return -1.0
    return max(0.0, time.time() - at)


def is_stale(cache=None):
    """Пора ли обновлять каталог: не грузился ни разу, старше FRESH_SECONDS
    или последняя попытка была неудачной и с неё прошло больше RETRY_SECONDS."""
    cache = _load() if cache is None else cache
    now = time.time()
    if cache.get("error"):
        return (now - float(cache.get("try_at") or 0.0)) >= RETRY_SECONDS
    at = float(cache.get("at") or 0.0)
    if at <= 0 or not (cache.get("providers") or {}):
        return True
    return (now - at) >= FRESH_SECONDS


def state():
    u"""Состояние каталога для панели. Секретов здесь нет.

    Уходит в ответ /api/providers целиком, чтобы пользователь видел, ОТКУДА
    взялись цены и лимиты и насколько это знание свежее. Числа без возраста
    измерения в этом проекте не показываются.
    """
    cache = _load()
    provs = cache.get("providers") or {}
    live = 0
    dead = 0
    for rec in provs.values():
        for m in (rec.get("models") or {}).values():
            if str(m.get("status") or "") == STATUS_DEPRECATED:
                dead += 1
            else:
                live += 1
    return {
        "url": CATALOG_URL,
        # Отметка времени, а не «сколько назад»: возраст панель считает сама по
        # своим часам, как и для наблюдений о провайдерах.
        "at": float(cache.get("at") or 0.0),
        "error": str(cache.get("error") or ""),
        "try_at": float(cache.get("try_at") or 0.0),
        "providers": sorted(provs.keys()),
        # СНЯТЫЕ МОДЕЛИ ЗДЕСЬ НЕ СЧИТАЮТСЯ. Иначе строка «сведения о 502
        # моделях» включала бы 30 записей, про которые сам каталог говорит
        # «провайдер их больше не отдаёт», — то есть завышала бы полезность
        # справочника.
        "models": live,
        "deprecated": dead,
        # Сколько провайдеров каталога вообще пригодны для выбора. Панель
        # показывает это рядом с переключателем: «включить ещё 163» честнее, чем
        # безымянная галочка.
        "known_providers": len(cache.get("catalog_providers") or {}),
    }


def forget():
    """Удаляет кэш каталога. Нужно тестам и на случай испорченного файла."""
    p = catalog_path()
    try:
        if os.path.isfile(p):
            os.remove(p)
        return True
    except Exception as e:
        print(u"[catalog] Не удалось удалить кэш каталога (%s)" % e)
        return False
