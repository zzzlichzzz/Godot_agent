# -*- coding: utf-8 -*-
"""Маршруты стартового экрана и чатов: список сайтов, список чатов,
создание нового чата на выбранном сайте, открытие сохранённого чата
(с переходом браузера на его страницу), переименование и удаление.
Вынесено из main.py в отдельный Blueprint.
"""
import threading
import time
from flask import Blueprint, request, jsonify

import chat_store
import sites
import server_state as S
import history_manager as history
import api_history
import anthropic_compat
import api_keys
import providers
import model_cache
import catalog
import openai_compat
import api_backend
from agent_prompts import PROMPT_HASH

chats_bp = Blueprint("chats", __name__)


def _busy_error():
    """Пока идёт обработка запроса, браузер занят парсером — навигация по
    чатам привела бы к вечной загрузке. Возвращаем понятную ошибку."""
    if (S.STATE.get("progress") or {}).get("active"):
        return jsonify({"error": "Агент сейчас обрабатывает запрос — браузер занят. "
                                 "Дождитесь ответа или нажмите «Стоп»."}), 409
    return None


def _navigate(driver, url):
    """Неблокирующая навигация браузера на URL.

    driver.get() у тяжёлого SPA (AI Studio) ждёт полной загрузки страницы
    и может упереться в таймаут HTTP-запроса от плагина — тогда
    браузер уже открыл страницу, а плагин так и не получил ответ и не открыл чат.
    Меняем адрес через JS: браузер начинает грузить страницу, а сервер сразу
    отвечает. Транскрипт диалога хранится локально, полная загрузка для ответа не нужна.
    """
    try:
        # Короткие таймауты: на мёртвой/удалённой странице команды браузеру
        # могут висеть до 300 с (дефолт Selenium) — отсюда «вечное» зависание.
        driver.set_page_load_timeout(20)
        driver.set_script_timeout(10)
    except Exception:
        pass
    # v54: если вкладка с этим адресом уже открыта — просто переключаемся на неё,
    # не перезагружая страницу и не занимая другую вкладку (иначе появлялись две
    # вкладки одного чата, и агент мог печатать не в ту).
    def _p54(u):
        return (u or "").split("://", 1)[-1].split("?", 1)[0].split("#", 1)[0].rstrip("/")
    try:
        want = _p54(url)
        cur_handle = driver.current_window_handle
        found = False
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if _p54(driver.current_url or "") == want:
                found = True
                break
        if found:
            return
        driver.switch_to.window(cur_handle)
    except Exception:
        pass
    try:
        driver.switch_to.window(driver.window_handles[-1])
    except Exception:
        pass
    try:
        driver.execute_script("window.location.href = arguments[0];", url)
        return
    except Exception:
        pass
    # Фолбэк: обычная навигация с ограничением по времени, чтобы не зависнуть.
    try:
        driver.set_page_load_timeout(10)
    except Exception:
        pass
    try:
        driver.get(url)
    except Exception:
        pass


def _check_chat_page(driver, url, wait=6.0):
    """После перехода на страницу чата проверяем (не дольше wait секунд),
    что браузер остался на ней. Если чат удалён на сайте, сайт обычно
    перекидывает на главную — возвращаем текст предупреждения (или "").
    Главное: проверка ОГРАНИЧЕНА ПО ВРЕМЕНИ и никогда не виснет вечно."""
    deadline = time.time() + wait
    last_url = ""
    state = ""
    while time.time() < deadline:
        time.sleep(0.5)
        try:
            last_url = driver.current_url or ""
            state = driver.execute_script("return document.readyState") or ""
        except Exception:
            continue  # страница ещё грузится — команды могут временно падать
        if state == "complete" and last_url:
            break
    if not last_url:
        return ("Браузер не ответил при открытии страницы чата — вкладка могла "
                "зависнуть. Если чат был удалён на сайте — удалите его и здесь.")

    def _path(u):
        return u.split("://", 1)[-1].split("?", 1)[0].split("#", 1)[0].rstrip("/")

    if _path(last_url) != _path(url):
        return ("Похоже, этот чат удалён на сайте: страница не открылась "
                "(браузер оказался на %s). История сообщений сохранена локально. "
                "Отправка сообщений сюда не сработает — удалите чат или создайте новый." % last_url)
    return ""


@chats_bp.route('/sites/list', methods=['POST'])
def sites_list():
    # Список доступных сайтов-нейросетей для vbox на стартовом экране.
    return jsonify({"sites": sites.list_sites()})


@chats_bp.route('/api/providers', methods=['POST'])
def api_providers():
    """Провайдеры для работы по ключу + состояние их настройки.
    Сырых ключей в ответе не бывает — только маски (см. api_keys.status)."""
    return jsonify(_api_settings_payload())


def _catalog_payload():
    u"""Состояние каталога для панели + включён ли полный список провайдеров.

    Переключатель живёт в настройках (api_keys), а не в состоянии каталога:
    каталог — это данные, а показывать их или нет решает пользователь. Панель
    при этом читает оба поля из одного места, иначе флажок и список собирались бы
    из разных ответов и расходились бы при перерисовке.
    """
    out = catalog.state()
    out["show_all"] = api_keys.catalog_enabled()
    return out


def _api_settings_payload(extra=None):
    """Единый вид настроек для панели. Всегда возвращается целиком, чтобы
    панель после любого изменения перерисовалась из одного источника и не
    хранила своё представление о состоянии."""
    out = {"providers": providers.list_providers(),
           "defaults": api_keys.get_defaults(),
           "proxy": api_keys.get_proxy(),
           "dns": api_keys.get_dns(),
           # Состояние ВТОРИЧНОГО источника сведений о моделях (models.dev):
           # возраст, ошибка загрузки, сколько моделей известно. Панель
           # подписывает им цены и лимиты контекста — значит обязана показать и
           # то, насколько это знание свежее. Число без возраста измерения в
           # этом проекте не показывается.
           "catalog": _catalog_payload(),
           # Недавно выбранные пары «провайдер + модель»: панель поднимает их в
           # начало списка моделей. Порядок задаёт СЕРВЕР, потому что он же его и
           # пишет (api_keys.note_model_used) — панель тут только показывает.
           "recent": api_keys.get_recent(),
           "config_path": api_keys.config_path()}
    if extra:
        out.update(extra)
    return out


@chats_bp.route('/api/settings/set', methods=['POST'])
def api_settings_set():
    """Сохранение настроек API: ключ, модель, свой адрес, прокси.

    Один эндпоинт на всё, потому что панель сохраняет форму целиком, а
    дробить это на пять маршрутов значит пять раз описывать одно и то же.
    Применяются ТОЛЬКО присланные поля: отсутствие поля — это «не менять»,
    а не «очистить». Особенно важно для пароля прокси, который панель не
    пересылает при каждой правке хоста.
    """
    data = request.json or {}
    pid = (data.get("provider") or "").strip()
    if pid and providers.get_provider(pid) is None:
        return jsonify({"error": u"Неизвестный провайдер «%s»." % pid}), 400
    problems = {}
    if pid:
        if "key" in data:
            # Ключ приходит сюда сырым один раз — при вводе. Дальше панель
            # видит только маску, а сам ключ живёт в файле настроек вне проекта.
            #
            # ВНИМАНИЕ НА СМЫСЛ: set_key заменяет ВСЕ ключи провайдера одним.
            # Так и надо, потому что панель сохраняет форму с одним полем и
            # «сохранить» там всегда означало «пусть будет вот этот». Добавление
            # второго ключа — отдельное поле add_key ниже, и путать их нельзя:
            # иначе правка первого ключа молча стирала бы остальные.
            api_keys.set_key(pid, data.get("key") or "")
        if data.get("add_key"):
            # Ещё один ключ того же провайдера. Нужен потому, что квота
            # бесплатных тарифов считается НА КЛЮЧ: когда первый упирается в
            # суточный лимит, второй работает как ни в чём не бывало.
            api_keys.add_key(pid, data.get("add_key"))
        if "delete_key_index" in data:
            # Удаление одного ключа из списка, по позиции. Позиция, а не сам
            # ключ: панель сырых ключей не видит и присылать их обратно не может.
            if not api_keys.delete_key_at(pid, data.get("delete_key_index")):
                problems["key_error"] = u"Такого ключа в списке нет."
        if data.get("clear_cooldowns"):
            # «Пробуй заново»: пользователь знает про свои квоты то, чего не
            # знает агент (пополнил баланс, наступило утро), и обязан иметь
            # возможность сказать это, не удаляя ключи.
            api_keys.clear_key_cooldowns(pid)
        if "model" in data:
            api_keys.set_model(pid, data.get("model") or "")
        if "base_url" in data:
            was = api_keys.get_base_url(pid)
            ok, err = api_keys.set_base_url(pid, data.get("base_url") or "")
            if not ok:
                # Отдельным полем, как и ошибка прокси: остальные настройки уже
                # сохранены, и панель должна перерисоваться с пояснением, а не
                # показать общий отказ на всю форму.
                problems["base_url_error"] = err
            elif api_keys.get_base_url(pid) != was:
                # Адрес сменился — всё, что известно о моделях, относилось к
                # ПРЕЖНЕМУ адресу. Оставить список и числа значит выдать факты
                # об одном сервисе за факты о другом; пользователь при этом
                # выбирал бы модель, которой на новом адресе может не быть.
                model_cache.forget(pid)
                api_keys.reset_models_stats(pid)
                print("--> %s: адрес endpoint'а изменён, список моделей забыт" % pid)
        if data.get("make_default"):
            api_keys.set_defaults(pid, api_keys.get_model(pid))
    proxy = data.get("proxy")
    if isinstance(proxy, dict):
        ok, err = api_keys.set_proxy(
            enabled=proxy.get("enabled") if "enabled" in proxy else None,
            host=proxy.get("host") if "host" in proxy else None,
            port=proxy.get("port") if "port" in proxy else None,
            user=proxy.get("user") if "user" in proxy else None,
            password=proxy.get("password") if "password" in proxy else None)
        if not ok:
            # Неверный адрес прокси возвращаем ОТДЕЛЬНЫМ полем, а не общей
            # ошибкой: остальные настройки (ключ, модель) уже сохранены, и
            # панель должна перерисоваться, а не показать пустую форму.
            problems["proxy_error"] = err
    dns = data.get("dns")
    if isinstance(dns, dict):
        ok, err = api_keys.set_dns(
            enabled=dns.get("enabled") if "enabled" in dns else None,
            url=dns.get("url") if "url" in dns else None)
        if not ok:
            problems["dns_error"] = err
    cat = data.get("catalog")
    if isinstance(cat, dict) and "enabled" in cat:
        # Полный список провайдеров из каталога models.dev. Включается ОСОЗНАННО:
        # про 161 запись сверх наших семи не проверено ничего, и показывать их
        # вперемешку с разобранными значит стереть разницу между «проверено» и
        # «взято из справочника».
        api_keys.set_catalog_enabled(cat.get("enabled"))
    return jsonify(_api_settings_payload(problems or None))


def _fetch_models(pid, connect_timeout=None):
    """Список моделей провайдера как записи [{"id", "free"}, ...].

    Возвращает (записи, текст_ошибки). Одна из двух половин всегда пуста.
    Общая для кнопки «Обновить» и для автообновления: два места, собирающие
    один и тот же запрос по-своему, однажды разойдутся в заголовках или в
    таймауте, и «обновилось само» перестанет значить то же, что «обновил
    кнопкой».
    """
    provider = providers.get_provider(pid)
    if provider is None:
        return [], u"неизвестный провайдер «%s»" % pid
    url = providers.models_url(pid)
    if not url:
        return [], u"не задан адрес списка моделей"
    blocked = providers.unavailable_reason(pid)
    if blocked:
        # К такому провайдеру не ходим вовсе — даже за списком моделей: он и его
        # отдаёт только клиентам из своего списка, а лишний отказ в его логах
        # нам ни к чему.
        return [], u"«%s» пока недоступен: %s" % (provider["name"], blocked)
    if connect_timeout is None:
        connect_timeout = providers.connect_timeout_for(pid)
    try:
        raw = openai_compat.fetch_models(
            url, api_keys.resolve_key(pid, providers.env_names_for(pid)),
            extra_headers=providers.headers_for(pid),
            proxy=api_keys.proxy_url(),
            connect_timeout=connect_timeout)
    except openai_compat.ApiError as e:
        msg, _status, _retry = api_backend.describe_api_error(e, provider["name"])
        return [], msg
    except Exception as e:
        # Никакая неожиданность в разборе чужого ответа не должна превращаться в
        # 500 на весь маршрут: у обхода это уронило бы обновление ВСЕХ
        # провайдеров из-за одного, ответившего чем-то неожидаемым.
        return [], u"неожиданный ответ от «%s»: %s" % (provider["name"], e)
    return providers.parse_models_detailed(raw, provider_id=pid), ""


# ---------------------------------------------------------------------------
# Каталог models.dev как ВТОРИЧНЫЙ источник
#
# ЖИВОЙ ОТВЕТ ПРОВАЙДЕРА — ПЕРВИЧНАЯ ПРАВДА. Он говорит, что доступно ИМЕННО
# ЭТОМУ ключу. Каталог говорит, что существует в мире и сколько стоит, — и
# только ДОПОЛНЯЕТ поля, которых в живом ответе нет (цена, окно контекста,
# поддержка вызова инструментов). Замерено: у Opencode Zen каталог знает 91
# модель, живой /models отдаёт 62; оба числа верные, но про разное, и брать
# список из каталога нельзя — пользователь выбрал бы модель, которой ему не
# отдают, и получил бы 404.
# ---------------------------------------------------------------------------

# Одновременных загрузок каталога быть не должно: панель может прислать запрос
# дважды (открытие экрана и открытие окна выбора), а два раза по 400 КБ ради
# одного и того же справочника — это трата чужого трафика.
_catalog_lock = threading.Lock()


def _catalog_extra_ids():
    u"""Провайдеры ИЗ КАТАЛОГА, которых пользователь выбрал сам.

    Для них тоже нужны модели каталога (цены и лимиты контекста). Для всех 161
    держать модели нельзя: замерено 680 КБ против 100 КБ, а кэш читается целиком
    на каждый запрос настроек.
    """
    try:
        chosen = set(api_keys.configured_provider_ids())
        return sorted(pid for pid in chosen if providers.is_from_catalog(pid))
    except Exception as e:
        print(u"[catalog] Не удалось узнать выбранных из каталога: %s" % e)
        return []


def _catalog_needs_models():
    """Есть ли выбранный из каталога провайдер, чьих моделей в кэше ещё нет.

    Без этого выбор провайдера из полного списка ждал бы недельного срока
    свежести каталога, и до тех пор у него не было бы ни цен, ни лимитов —
    снаружи это выглядит как «каталог про него не знает».
    """
    extra = _catalog_extra_ids()
    if not extra:
        return False
    return any(not catalog.get(pid) for pid in extra)


def _refresh_catalog(force):
    u"""Обновляет каталог, если пора. Возвращает текст ошибки или "".

    ПОЧЕМУ ВНУТРИ ОБХОДА ПРОВАЙДЕРОВ, А НЕ ОТДЕЛЬНЫМ МАРШРУТОМ. Каталог нужен
    ровно там, где нужны списки моделей, и обновляется он раз в неделю против
    суток у списков. Отдельный маршрут потребовал бы нового вида запроса в
    панели и нового сигнала GDScript — три места вместо нуля ради того, чтобы
    делать это в том же самом момент времени.

    НЕУДАЧА КАТАЛОГА НЕ ЛОМАЕТ ОБХОД. Она запоминается в кэше каталога и уходит
    в панель отдельным полем (catalog.state), а провайдеры опрашиваются как
    обычно: без каталога у моделей просто не будет цен и лимитов, а работать
    по ключу это не мешает.
    """
    if not force and not catalog.is_stale() and not _catalog_needs_models():
        return ""
    if not _catalog_lock.acquire(False):
        # Загрузка уже идёт в другом запросе. Ждать её нечего: панель получит
        # свежее состояние каталога следующим ответом сервера.
        print(u"--> Каталог models.dev уже загружается — пропускаю")
        return ""
    try:
        _updated, err = catalog.refresh(force=force,
                                        extra_ids=_catalog_extra_ids())
        return err
    except Exception as e:
        # Никакая неожиданность в чужом справочнике не должна превращаться в
        # 500 на весь маршрут: это уронило бы обновление списков моделей у ВСЕХ
        # провайдеров из-за недоступного models.dev.
        print(u"[catalog] Неожиданная ошибка обновления каталога: %s" % e)
        return u"каталог не обновился: %s" % e
    finally:
        _catalog_lock.release()


def _enrich(pid, records):
    u"""Записи моделей + дополнения каталога. Живые поля не перезаписываются.

    Одна точка на все места, где записи уходят наружу или на диск: кнопка
    «Обновить список», обход провайдеров и индекс для поиска. Обогащать по
    месту значило бы, что в одном ответе у модели есть цена, а в другом нет, —
    и пользователь считал бы, что цена «то появляется, то исчезает».
    """
    try:
        return catalog.enrich(pid, records)
    except Exception as e:
        # Каталог — удобство. Если он сломан, список моделей всё равно обязан
        # доехать до панели: без цен, но рабочим.
        print(u"[catalog] Не удалось дополнить модели %s из каталога: %s" % (pid, e))
        return list(records or [])


def _models_index():
    u"""Индекс моделей ВСЕХ провайдеров для поиска — с дополнениями каталога.

    Дополняется ещё раз ЗДЕСЬ, а не только при записи в кэш: каталог
    обновляется раз в неделю, а списки моделей раз в сутки, и после недельного
    обновления каталога записи в кэше остались бы без свежих цен до следующего
    опроса провайдера. Повторное дополнение ничего не портит — catalog.enrich
    только заполняет отсутствующие поля.
    """
    idx = model_cache.index()
    return {pid: _enrich(pid, recs) for pid, recs in idx.items()}


@chats_bp.route('/api/models/refresh', methods=['POST'])
def api_models_refresh():
    """Список моделей с самого сервиса.

    В реестре списки пустые намеренно: идентификаторы моделей меняются
    постоянно, и зашитый в код перечень начал бы врать пользователю. Поэтому
    он тянется отсюда, а поле модели в панели остаётся редактируемым — можно
    вписать любой идентификатор руками.
    """
    data = request.json or {}
    pid = (data.get("provider") or "").strip()
    provider = providers.get_provider(pid)
    if provider is None:
        return jsonify({"error": u"Неизвестный провайдер «%s»." % pid}), 400
    if not providers.models_url(pid):
        return jsonify({"error": u"У «%s» не задан адрес списка моделей."
                                 % provider["name"]}), 400
    blocked = providers.unavailable_reason(pid)
    if blocked:
        # К такому провайдеру не ходим вовсе — даже за списком моделей: он и его
        # отдаёт только клиентам из своего списка, а лишний отказ в его логах
        # нам ни к чему. Неудачей это НЕ запоминаем: попытки не было, а «список
        # получить не удалось» на карточке значило бы, что мы сходили и получили
        # отказ.
        return jsonify(_api_settings_payload({
            "error": u"«%s» пока недоступен: %s" % (provider["name"], blocked),
            "provider": pid}))
    # Разбираем ВЕСЬ ответ, без фильтра, и только потом отбираем бесплатные.
    # Порядок важен: счётчики у провайдера должны считаться по полному списку,
    # иначе при включённом флажке «только бесплатные» всего == бесплатных, и в
    # списке провайдеров у любого платного сервиса оказалось бы 100%
    # бесплатных моделей.
    everything, err = _fetch_models(pid)
    if err:
        print("<-- Список моделей %s не получен: %s" % (pid, err))
        # Неудачу запоминаем: панель показывает её в карточке провайдера. Без
        # этого там осталось бы «список ещё не загружался» — то есть плагин
        # выглядел бы просто ничего не делающим, хотя он сходил и получил отказ.
        api_keys.record_models_error(pid, err)
        # Отвечаем 200 с текстом причины, а НЕ 502. Панель для любого не-200
        # показывает общее «сервер вернул ошибку (HTTP 502)» и выбрасывает тело
        # ответа — то есть пользователь не видел настоящей причины (недоступен
        # провайдер, неверный прокси, отклонён ключ). Здесь сервер отработал
        # штатно; неисправен внешний сервис, и об этом надо сказать словами.
        return jsonify(_api_settings_payload({"error": err, "provider": pid}))
    free_only = bool(data.get("free_only"))
    # В КЭШ УХОДИТ ЖИВОЙ ОТВЕТ, БЕЗ ДОПОЛНЕНИЙ. Каталог прикладывается только на
    # выходе (_enrich): попав на диск, его поля стали бы неотличимы от
    # присланных провайдером, и подпись «по каталогу models.dev» под живой ценой
    # начала бы врать об источнике. Побочная выгода — обновление каталога
    # действует сразу, не дожидаясь нового опроса провайдеров.
    model_cache.put(pid, everything)
    # А считаем и отдаём — по обогащённым: число «бесплатных по каталогу» иначе
    # пришлось бы получать вторым проходом по другому списку.
    everything = _enrich(pid, everything)
    total, free = providers.count_models(everything)
    free_catalog = catalog.count_free(pid, everything)
    api_keys.record_models_stats(pid, total, free, free_catalog)
    detailed = [r for r in everything if r["free"]] if free_only else everything
    models = [r["id"] for r in detailed]
    print("--> Список моделей %s обновлён: %d шт. (бесплатных %d из %d, "
          "по каталогу бесплатных %d)%s"
          % (pid, len(models), free, total, free_catalog,
             " (показаны только бесплатные)" if free_only else ""))
    return jsonify(_api_settings_payload({
        "models": models,
        # Записи с признаком бесплатности — рядом с прежним списком строк, а не
        # вместо него: панель читает "models" и продолжит работать, пока не
        # переедет на "models_info". Убрать "models" можно будет только после
        # того, как это сделает GDScript.
        "models_info": detailed,
        # Списки моделей ВСЕХ провайдеров, какие известны. Панель ищет по ним
        # модель по названию, поэтому индекс приходит и здесь, а не только с
        # обходом: иначе после ручного обновления одного провайдера поиск знал
        # бы про него старое.
        "models_index": _models_index(),
        "provider": pid,
        "free_only": free_only}))


# Сколько ждать ответа со списком моделей при автообновлении. Меньше обычного
# таймаута запроса: пользователь в это время смотрит на открытый список
# провайдеров, и минута ожидания там выглядит как зависший плагин. Провайдер,
# не ответивший за 12 секунд, получит вторую попытку через MODELS_RETRY_SECONDS.
SCAN_TIMEOUT = 12.0
# Одновременных обходов быть не должно: панель может прислать запрос дважды
# (открытие экрана и открытие списка), а два обхода — это двойной трафик к
# провайдерам ради одних и тех же чисел. Второй запрос не ждёт, а отвечает
# текущими данными: список провайдеров у него и так на экране.
_scan_lock = threading.Lock()


@chats_bp.route('/api/models/scan', methods=['POST'])
def api_models_scan():
    """Обновляет списки моделей у провайдеров, которых можно спросить молча.

    ЗАЧЕМ ОТДЕЛЬНЫЙ МАРШРУТ. Числа «моделей столько, из них бесплатных
    столько» появлялись ТОЛЬКО после того, как пользователь сам открывал
    провайдера и нажимал «Обновить список». Поэтому фильтр «с бесплатными»,
    который отбирает как раз по этим числам, показывал не провайдеров с
    бесплатными моделями, а провайдеров, которых пользователь успел открыть.
    Догадаться об этом снаружи нельзя: список ведь уже показан, и выглядит он
    как полный ответ.

    Спрашиваем только тех, у кого ответ возможен без участия человека
    (providers.can_fetch_models) и чьи числа устарели или отсутствуют
    (providers.models_stale). Обход идёт параллельно, потому что это ожидание
    сети, а не работа: последовательно пять провайдеров складывались бы в
    минуту, которую пользователь видит как зависшее окно.

    force=True — обновить всё, что вообще можно спросить, не глядя на свежесть.
    Это ручное «обновить все списки», а не поведение по умолчанию: обходить
    провайдеров на каждое открытие окна значит тратить чужие лимиты запросов на
    подпись под названием. Тем же force обновляется и каталог models.dev.
    """
    data = request.json or {}
    force = bool(data.get("force"))
    # Каталог — ПЕРЕД опросом провайдеров: живые записи дополняются его полями
    # сразу, а не при следующем обходе. Своя свежесть (неделя против суток) и
    # свой замок внутри; неудача не мешает опросу провайдеров и уходит в панель
    # отдельным полем catalog в ответе.
    _refresh_catalog(force)
    if force:
        targets = [pid for pid in providers.provider_ids()
                   if providers.can_fetch_models(pid)]
    else:
        targets = providers.autoscan_targets()
    if not targets:
        return jsonify(_api_settings_payload({"scanned": [], "failed": [],
                                              "scan_skipped": True,
                                              "models_index": _models_index()}))
    if not _scan_lock.acquire(False):
        # Обход уже идёт в другом запросе. Ждать его нечего: панель получит
        # свежие числа следующим ответом сервера, а сейчас — то, что есть.
        print("--> Автообновление списков моделей уже идёт — пропускаю")
        return jsonify(_api_settings_payload({"scanned": [], "failed": [],
                                              "scan_skipped": True,
                                              "models_index": _models_index()}))
    try:
        print("--> Автообновление списков моделей: %s" % ", ".join(targets))
        results = {}

        def work(pid):
            recs, err = _fetch_models(pid, connect_timeout=SCAN_TIMEOUT)
            results[pid] = (recs, err)

        threads = [threading.Thread(target=work, args=(pid,),
                                    name="models-scan-%s" % pid, daemon=True)
                   for pid in targets]
        for t in threads:
            t.start()
        for t in threads:
            # Запас над таймаутом запроса: поток должен успеть вернуться сам.
            t.join(SCAN_TIMEOUT + 10.0)
        changes, scanned, failed = {}, [], []
        lists = {}
        for pid in targets:
            if pid not in results:
                # Поток не уложился в join — считаем это неудачей попытки, а не
                # молчанием: иначе провайдер остался бы без объяснения, почему у
                # него нет чисел.
                changes[pid] = api_keys.models_error_fields(
                    u"ответ не пришёл за %.0f с" % SCAN_TIMEOUT)
                failed.append(pid)
                continue
            recs, err = results[pid]
            if err:
                changes[pid] = api_keys.models_error_fields(err)
                failed.append(pid)
                print("<-- %s: список моделей не получен (%s)" % (pid, err))
                continue
            # В кэш — ЖИВОЙ ответ, в счётчики — обогащённый. Разделение
            # обязательно: на диске поля каталога стали бы неотличимы от
            # присланных провайдером, и подпись об источнике начала бы врать.
            raw_recs = recs
            recs = _enrich(pid, recs)
            total, free = providers.count_models(recs)
            free_catalog = catalog.count_free(pid, recs)
            changes[pid] = api_keys.models_stats_fields(total, free, free_catalog)
            lists[pid] = raw_recs
            scanned.append(pid)
            print("--> %s: моделей %d, из них бесплатных %d "
                  "(по каталогу models.dev бесплатных %d)"
                  % (pid, total, free, free_catalog))
        # Одной записью на весь обход: иначе каждый провайдер отдельно читал бы
        # и перезаписывал файл настроек, и параллельное сохранение ключа из
        # другого запроса могло бы пропасть.
        api_keys.record_stats_bulk(changes)
        # Сами списки — в свой файл, тоже одной записью. Из них панель ищет
        # модель по названию сразу у всех провайдеров; неудачные провайдеры в
        # кэш не попадают, поэтому прошлый удачный список у них сохраняется.
        model_cache.put_bulk(lists)
    finally:
        _scan_lock.release()
    # Ошибки отдельных провайдеров НЕ уходят полем "error": панель показала бы
    # их красной строкой на весь экран, а это обычное дело — у половины
    # провайдеров ключа нет и не должно быть. Причина видна в карточке того
    # провайдера, к которому относится.
    return jsonify(_api_settings_payload({"scanned": scanned, "failed": failed,
                                          "scan_skipped": False,
                                          "models_index": _models_index()}))


def _tls_note(pid):
    """Кто отвечает по адресу провайдера — по издателю TLS-сертификата.

    Главная диагностика при непонятных отказах: если сертификат выдан не
    публичным удостоверяющим центром, а, например, антивирусом, значит трафик
    перехватывается, и «отказ сервиса» на самом деле пришёл от посредника.
    """
    try:
        probe = openai_compat.tls_probe(providers.base_url_for(pid),
                                       proxy=api_keys.proxy_url())
    except Exception as e:
        return {"ok": False, "error": str(e)}, ""
    if not probe.get("ok"):
        return probe, ""
    issuer = probe.get("issuer") or "?"
    low = issuer.lower()
    # Признаки перехвата: издателем выступает не удостоверяющий центр, а
    # программа на машине или в сети.
    suspicious = any(w in low for w in (
        "kaspersky", "eset", "avast", "avg", "bitdefender", "dr.web", "drweb",
        "norton", "mcafee", "sophos", "fortinet", "zscaler", "netskope",
        "proxy", "firewall", "gateway", "local", "self-signed"))
    note = u"Сертификат выдан: %s." % issuer
    if suspicious:
        note += (u" Это НЕ публичный удостоверяющий центр — значит HTTPS "
                 u"перехватывается программой на вашей машине или в сети "
                 u"(антивирус, шлюз). Ответы «доступ запрещён» приходят от неё, "
                 u"а не от провайдера: добавьте адрес провайдера в исключения "
                 u"этой программы.")
    return probe, note


@chats_bp.route('/api/test', methods=['POST'])
def api_test():
    """Проверка подключения: НАСТОЯЩИЙ минимальный запрос к модели.

    Именно запрос, а не пинг: у Gemini адрес API
    (generativelanguage.googleapis.com) — другой хост, чем у сайта
    (gemini.google.com), и доступность через прокси у них может отличаться.
    Пользователь должен узнать это здесь, а не посреди задачи.

    При неудаче дополнительно сообщается издатель TLS-сертификата: по нему
    видно, отвечает ли настоящий сервис или трафик перехватывает посредник.
    """
    data = request.json or {}
    pid = (data.get("provider") or "").strip()
    provider = providers.get_provider(pid)
    if provider is None:
        return jsonify({"error": u"Неизвестный провайдер «%s»." % pid}), 400
    model = (data.get("model") or "").strip() or providers.model_for(pid)
    blocked = providers.unavailable_reason(pid)
    if blocked:
        # Проверять нечего: запрос всё равно отклонит сам сервис, а «проверка»,
        # которая заведомо стучится в закрытую дверь, только путает.
        return jsonify({"ok": False,
                        "error": u"«%s» пока недоступен: %s"
                                 % (provider["name"], blocked)})
    ok, why = providers.readiness(pid)
    if not ok and not model:
        return jsonify({"ok": False, "error": u"Не готово: %s." % why})
    try:
        transport = anthropic_compat if providers.transport_for(pid, model) == "anthropic" else openai_compat
        args = (providers.base_url_for(pid),
                api_keys.resolve_key(pid, providers.env_names_for(pid)),
                model, [{"role": "user", "content": "ping"}])
        kwargs = {"max_tokens": 64,
                  "extra_headers": providers.headers_for(pid),
                  "proxy": api_keys.proxy_url(),
                  "connect_timeout": providers.connect_timeout_for(pid)}
        # У части шлюзов обычный (non-stream) запрос не успевает пройти сквозь
        # их собственный таймаут и возвращается 504 — на рабочем ключе. Поток
        # к тому же ближе к боевому режиму: чат работает именно им.
        if providers.test_with_stream(pid):
            res = transport.stream_chat(*args, **kwargs)
        else:
            res = transport.complete_chat(*args, **kwargs)
    except openai_compat.ApiError as e:
        msg, _status, _retry = api_backend.describe_api_error(
            e, provider["name"], model)
        probe, note = _tls_note(pid)
        if note:
            msg += u" " + note
        print("<-- Проверка подключения к %s: %s" % (pid, msg))
        # Неудачу запоминаем так же, как удачу: в списке провайдеров «проверка
        # не прошла» — это полезное знание о СВОЕЙ машине, которого нет ни в
        # каком реестре. Молчать о ней и показывать провайдера нейтральным
        # значит предлагать человеку снова наступить на то же место.
        api_keys.record_test_result(pid, False, 0)
        return jsonify({"ok": False, "error": msg,
                        "tls_issuer": probe.get("issuer", ""),
                        "tls_error": probe.get("error", "")})
    ms = int((res.get("elapsed") or 0) * 1000)
    api_keys.record_test_result(pid, True, ms)
    proxy_note = u" через прокси" if api_keys.proxy_url() else u""
    print("--> Проверка подключения к %s (%s): успех, %d мс%s"
          % (pid, model, ms, proxy_note))
    return jsonify({"ok": True, "model": res.get("model") or model,
                    "elapsed_ms": ms, "via_proxy": bool(api_keys.proxy_url()),
                    "message": u"Ответ получен за %d мс%s." % (ms, proxy_note)})


def _new_api_chat(data, base):
    """Новый чат по ключу API: без браузера, без адреса страницы.

    Провайдер и модель ЗАКРЕПЛЯЮТСЯ за чатом. Смена модели в настройках на
    уже созданный чат не влияет: другая модель — другой стиль и другая
    точность соблюдения формата действий, а разбираться потом в истории,
    склеенной из ответов разных моделей, невозможно.
    """
    pid = (data.get("provider") or "").strip() or api_keys.get_defaults().get("provider")
    pid = pid or providers.DEFAULT_PROVIDER_ID
    provider = providers.get_provider(pid)
    if provider is None:
        return jsonify({"error": u"Неизвестный провайдер «%s»." % pid}), 400
    model = (data.get("model") or "").strip() or providers.model_for(pid)
    if model:
        api_keys.set_model(pid, model)
    ok, why = providers.readiness(pid)
    if not ok:
        return jsonify({"error": u"Провайдер «%s» не готов: %s. Откройте "
                                 u"настройки API-ключа." % (provider["name"], why)}), 400
    api_keys.set_defaults(pid, model)
    api_keys.note_model_used(pid, model)
    rec = chat_store.create_chat(base, url="", primed=False)
    chat_store.update_chat(base, rec["id"], kind="api", provider=pid, model=model,
                           # site_name переиспользуем как подпись чата в списке:
                           # панель уже умеет её показывать, отдельное поле не нужно.
                           site_name=u"%s · %s" % (provider["name"], model))
    rec = chat_store.find_chat(base, rec["id"]) or rec
    S.STATE["current_chat_id"] = rec["id"]
    S.STATE["current_site_id"] = None
    S.STATE["is_primed"] = False
    S._save_primed(S.STATE.get("project_root"), False)
    S.clear_pending_confirmations()
    S.STATE["stale_note"] = ""
    api_history.clear(base, rec["id"])
    chat_store.append_transcript(
        base, rec["id"], "system",
        u"Чат работает по ключу API: %s, модель %s. Модель закреплена за этим "
        u"чатом — чтобы работать на другой, создайте новый чат."
        % (provider["name"], model))
    print("--> Новый API-чат:", rec["id"], pid, model)
    return jsonify({"chats": chat_store.list_chats(base, PROMPT_HASH),
                    "current_id": rec["id"], "title": rec["title"],
                    "site": rec.get("site_name", ""), "site_id": "",
                    "kind": "api", "provider": pid, "model": model})


@chats_bp.route('/chats/model', methods=['POST'])
def chats_model():
    u"""Продолжить ТЕКУЩИЙ чат по ключу на другой модели или у другого провайдера.

    ЗАЧЕМ ЭТО ОТДЕЛЬНОЕ ДЕЙСТВИЕ, А НЕ АВТОПОДМЕНА. Модель закреплена за чатом
    намеренно: другая модель — другой стиль и другая точность соблюдения формата
    действий, а разбираться потом в истории, склеенной из ответов разных моделей,
    невозможно. Поэтому агент НИКОГДА не меняет модель сам. Но тупика тоже быть
    не должно: когда у провайдера кончились все ключи или модель перестала
    подходить, единственным выходом было создать новый чат и потерять переписку.
    Здесь пользователь решает это сам, одним осознанным действием.

    ПОЧЕМУ МЕНЯЕТСЯ И ПРОВАЙДЕР. Квота считается на КЛЮЧ, а ключи принадлежат
    провайдеру: если у него исчерпаны все, другая модель ТОГО ЖЕ провайдера не
    поможет — нужен другой сервис. Ограничить смену одним провайдером значило бы
    не решить как раз главный случай.

    ИСТОРИЯ НЕ ОЧИЩАЕТСЯ — в этом весь смысл. Но в неё уходит явная пометка о
    смене: новая модель обязана понимать, что предыдущие ответы писала не она, а
    иначе она будет считать чужой стиль и чужие обещания своими.

    КОДЫ ОТВЕТА. Отказы, которые пользователь должен ПРОЧИТАТЬ (провайдер не
    готов, сервис недоступен, это та же модель), отдаются с кодом 200 и полем
    ok=false — как это делает /api/test. Причина не в стиле, а в проводке
    панели: на любой не-200 agent_server_link уходит в автозапуск второй копии
    сервера, и осмысленный текст отказа пользователь бы просто не увидел. Код
    400 остаётся для запросов, которые панель сформировать не может вовсе.
    """
    data = request.json or {}
    base = S._chats_dir()
    cid = S.STATE.get("current_chat_id")
    rec = chat_store.find_chat(base, cid) if (base and cid) else None
    if rec is None:
        return jsonify({"error": u"Нет открытого чата."}), 400
    if S.chat_kind(rec) != "api":
        # У браузерного чата модель выбирает сам сайт, и подменить её здесь
        # нечем: разговор живёт на странице сервиса.
        return jsonify({"ok": False,
                        "error": u"Сменить модель можно только в чате по "
                                 u"ключу API."})

    pid = (data.get("provider") or "").strip() or str(rec.get("provider") or "")
    provider = providers.get_provider(pid)
    if provider is None:
        return jsonify({"error": u"Неизвестный провайдер «%s»." % pid}), 400
    model = (data.get("model") or "").strip()
    if not model:
        # ТА ЖЕ ПОДСТАНОВКА, ЧТО И ПРИ СОЗДАНИИ ЧАТА (см. _new_api_chat выше):
        # модель, уже выбранная у этого провайдера, иначе его модель из реестра.
        #
        # Раньше здесь был отказ, и получалось, что одно и то же действие
        # человека — «переключиться на этого провайдера» — при создании чата
        # работало, а при смене модели у открытого отвечало «не выбрана модель».
        # Разницы между этими случаями нет никакой: и там и там человек назвал
        # провайдера и не назвал модель.
        model = providers.model_for(pid)
    if not model:
        # У провайдера не выбрано вообще ничего (только что заведён). Отказ с
        # кодом 200: его должен ПРОЧИТАТЬ пользователь, а на любой не-200
        # панель уходит в автозапуск второй копии сервера (см. коды ответа
        # в описании маршрута) и текст до человека не доедет.
        return jsonify({"ok": False,
                        "error": u"У «%s» ещё не выбрана модель. Откройте его в "
                                 u"списке провайдеров и нажмите нужную модель — "
                                 u"чат перейдёт на неё сразу."
                                 % provider["name"]})
    was_pid = str(rec.get("provider") or "")
    was_model = str(rec.get("model") or "")
    if pid == was_pid and model == was_model:
        return jsonify({"ok": False,
                        "error": u"Это та же модель, что и сейчас."})
    blocked = providers.unavailable_reason(pid)
    if blocked:
        return jsonify({"ok": False,
                        "error": u"«%s» пока недоступен: %s"
                                 % (provider["name"], blocked)})
    ok, why = providers.readiness(pid)
    if not ok:
        return jsonify({"ok": False,
                        "error": u"Провайдер «%s» не готов: %s. Откройте "
                                 u"настройки API-ключа."
                                 % (provider["name"], why)})

    chat_store.update_chat(base, cid, provider=pid, model=model,
                           site_name=u"%s · %s" % (provider["name"], model))
    was_name = (providers.get_provider(was_pid) or {}).get("name") or was_pid
    note = (u"[Система]: дальше в этом чате отвечает другая модель — %s (%s) "
            u"вместо %s (%s). Предыдущие ответы в переписке писала ПРЕЖНЯЯ "
            u"модель: не считай её обещания и её стиль своими, но пользуйся её "
            u"выводами как контекстом задачи."
            % (model, provider["name"], was_model or u"?", was_name or u"?"))
    # В историю запроса — чтобы понимала новая модель. Роль user и вид «заметка»:
    # обрезка контекста не имеет права схлопнуть эту строку, иначе новая модель
    # решит, что весь диалог её собственный.
    api_history.append(base, cid, api_history.ROLE_USER, note,
                       kind=api_history.KIND_NOTE)
    # В транскрипт — чтобы видел пользователь. Тот же факт, но своими словами:
    # ему не нужны инструкции, адресованные модели.
    chat_store.append_transcript(
        base, cid, "system",
        u"Модель чата изменена: %s (%s) вместо %s (%s). Переписка сохранена."
        % (model, provider["name"], was_model or u"?", was_name or u"?"))
    # Предложение по умолчанию для СЛЕДУЮЩЕГО нового чата тоже обновляем: раз
    # человек ушёл на эту модель посреди задачи, вероятнее всего он и дальше
    # захочет её, а не ту, что исчерпалась.
    api_keys.set_defaults(pid, model)
    api_keys.note_model_used(pid, model)
    # Модель у ПРОВАЙДЕРА тоже запоминаем: следующий переход на этого провайдера
    # без явного выбора модели (см. подстановку выше) должен привести к той, на
    # которой человек только что остановился, а не к записи из реестра.
    api_keys.set_model(pid, model)
    print("--> Чат %s: модель сменена %s/%s -> %s/%s"
          % (cid, was_pid, was_model, pid, model))
    return jsonify({"ok": True, "kind": "api", "provider": pid, "model": model,
                    "site": u"%s · %s" % (provider["name"], model),
                    "chats": chat_store.list_chats(base, PROMPT_HASH),
                    "current_id": cid})


@chats_bp.route('/browser/status', methods=['POST'])
def browser_status():
    """Готова ли текущая страница браузера (панель показывает уведомление,
    когда сайт догрузился, чтобы не казалось, что агент завис)."""
    driver = S.get_driver()
    if driver is None:
        # Различаем два разных «браузера нет»: он ещё грузится (booting) или
        # его вообще не запускали, потому что работа идёт по ключу API (idle).
        # Панель смотрит только на ready, но в диагностике разница важна.
        state = "booting" if S.browser_boot_started() else "idle"
        return jsonify({"ready": False, "state": state, "url": ""})
    state = ""
    url = ""
    try:
        url = driver.current_url or ""
        state = driver.execute_script("return document.readyState") or ""
    except Exception as e:
        return jsonify({"ready": False, "state": "error", "url": url, "error": str(e)})
    return jsonify({"ready": state == "complete", "state": state, "url": url})


@chats_bp.route('/chats/list', methods=['POST'])
def chats_list():
    data = request.json or {}
    S._apply_session_context(data)
    base = S._chats_dir()
    if not base:
        return jsonify({"chats": [], "current_id": None})
    return jsonify({"chats": chat_store.list_chats(base, PROMPT_HASH),
                    "current_id": S.STATE.get("current_chat_id")})


@chats_bp.route('/chats/new', methods=['POST'])
def chats_new():
    data = request.json or {}
    S._apply_session_context(data)
    busy = _busy_error()
    if busy:
        return busy
    base = S._chats_dir()
    if not base:
        return jsonify({"error": "Нет user_data_dir (отправьте сообщение или Синхронизацию)."}), 400
    if (data.get("kind") or "").strip() == "api":
        return _new_api_chat(data, base)
    site = sites.get_site(data.get("site_id") or "aistudio") or sites.get_site("aistudio")
    target_url = site["new_chat_url"] if site else "https://aistudio.google.com/prompts/new_chat"
    try:
        driver = S.wait_driver()
    except Exception as e:
        return jsonify({"error": str(e)}), 503
    try:
        _navigate(driver, target_url)
        time.sleep(1.5)
    except Exception as e:
        return jsonify({"error": "Не удалось открыть новую страницу: %s" % e}), 500
    url = ""
    try:
        url = driver.current_url or ""
    except Exception:
        pass
    rec = chat_store.create_chat(base, url=url, primed=False)
    if site:
        chat_store.update_chat(base, rec["id"], site_id=site["id"], site_name=site["name"])
        rec = chat_store.find_chat(base, rec["id"]) or rec
    S.STATE["current_chat_id"] = rec["id"]
    S.STATE["current_site_id"] = site["id"] if site else None
    S.STATE["is_primed"] = False
    S._save_primed(S.STATE.get("project_root"), False)
    S.clear_pending_confirmations()
    S.STATE["stale_note"] = ""  # новый чат праймится свежим деревом — сводка не нужна
    # v48: первое сообщение нового чата — системное напоминание выбрать модель.
    chat_store.append_transcript(base, rec["id"], "system",
        "Не забудьте выбрать нейросеть (модель) на странице в браузере, прежде чем отправлять первое сообщение.")
    print("--> Новый чат:", rec["id"], "на сайте", site["name"] if site else "?")
    return jsonify({"chats": chat_store.list_chats(base, PROMPT_HASH), "current_id": rec["id"],
                    "title": rec["title"], "site": site["name"] if site else "",
                    "site_id": site["id"] if site else ""})


@chats_bp.route('/chats/open', methods=['POST'])
def chats_open():
    data = request.json or {}
    S._apply_session_context(data)
    busy = _busy_error()
    if busy:
        return busy
    base = S._chats_dir()
    cid = (data.get("id") or "").strip()
    rec = chat_store.find_chat(base, cid) if base else None
    if rec is None:
        return jsonify({"error": "Чат не найден."}), 404
    page_note = ""
    if rec.get("url"):
        try:
            driver = S.wait_driver()
        except Exception as e:
            return jsonify({"error": str(e)}), 503
        try:
            _navigate(driver, rec["url"])
        except Exception as e:
            return jsonify({"error": "Не удалось открыть страницу чата: %s" % e}), 500
        page_note = _check_chat_page(driver, rec["url"])
        if page_note:
            print("--> ВНИМАНИЕ:", page_note)
    S.STATE["current_chat_id"] = cid
    S.STATE["current_site_id"] = rec.get("site_id")
    S.STATE["is_primed"] = bool(rec.get("primed"))
    S._save_primed(S.STATE.get("project_root"), S.STATE["is_primed"])
    S.clear_pending_confirmations()
    prev_used = rec.get("last_used", 0)
    chat_store.touch_chat(base, cid)
    # Сводка «что изменилось в проекте, пока чат был неактивен» — уйдёт
    # модели вместе со СЛЕДУЮЩИМ сообщением пользователя. Защита от полотна —
    # внутри summarize_changes_since (лимит строк / короткий абзац).
    S.STATE["stale_note"] = ""
    _root = S.STATE.get("project_root")
    if _root:
        try:
            _note = history.summarize_changes_since(_root, prev_used, exclude_chat_id=cid)
            if _note:
                S.STATE["stale_note"] = _note
                print("--> Подготовлена сводка изменений проекта для чата (%d симв.)" % len(_note))
        except Exception:
            pass
    print("--> Открыт чат:", rec.get("title"), cid)
    return jsonify({"chats": chat_store.list_chats(base, PROMPT_HASH), "current_id": cid,
                     "title": rec.get("title"),
                     "site": rec.get("site_name", ""),
                     "site_id": rec.get("site_id", ""),
                     # Панели нужно знать вид чата: у чата по ключу нет страницы
                     # в браузере, поэтому ей нельзя ждать её загрузки и незачем
                     # напоминать про выбор модели на сайте.
                     "kind": S.chat_kind(rec),
                     "provider": rec.get("provider", ""),
                     "model": rec.get("model", ""),
                     "warning": page_note,
                    "transcript": rec.get("transcript", [])})


@chats_bp.route('/chats/rename', methods=['POST'])
def chats_rename():
    data = request.json or {}
    S._apply_session_context(data)
    base = S._chats_dir()
    cid = (data.get("id") or "").strip()
    title = (data.get("title") or "").strip()
    if not base or not cid or not title:
        return jsonify({"error": "Нужны id и title."}), 400
    chat_store.update_chat(base, cid, title=title, manual_title=True)
    return jsonify({"chats": chat_store.list_chats(base, PROMPT_HASH),
                    "current_id": S.STATE.get("current_chat_id")})


@chats_bp.route('/chats/delete', methods=['POST'])
def chats_delete():
    data = request.json or {}
    S._apply_session_context(data)
    busy = _busy_error()
    if busy:
        return busy
    base = S._chats_dir()
    cid = (data.get("id") or "").strip()
    if not base or not cid:
        return jsonify({"error": "Нужен id."}), 400
    # История API-чата лежит отдельным файлом — убираем вместе с чатом, иначе
    # папка копит переписки уже несуществующих чатов.
    if not api_history.delete(base, cid):
        return jsonify({"error": "Не удалось удалить историю API-чата с диска."}), 500
    if not chat_store.delete_chat(base, cid):
        return jsonify({"error": "Чат не найден или его не удалось удалить с диска."}), 404
    # Журнал отката хранит изменения файлов отдельно от переписки. Сам откат
    # сохраняем, но убираем id и название удалённого чата.
    history.forget_chat(S.STATE.get("project_root"), cid)
    S.discard_action_note_for_chat(cid)  # v45: не копим отложенные заметки удалённых чатов
    if S.STATE.get("current_chat_id") == cid:
        S.clear_pending_confirmations()
        S.STATE["current_chat_id"] = None
        S.STATE["current_site_id"] = None
    return jsonify({"chats": chat_store.list_chats(base, PROMPT_HASH),
                    "current_id": S.STATE.get("current_chat_id")})
