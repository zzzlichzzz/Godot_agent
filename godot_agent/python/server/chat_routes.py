# -*- coding: utf-8 -*-
"""Маршруты стартового экрана и чатов: список сайтов, список чатов,
создание нового чата на выбранном сайте, открытие сохранённого чата
(с переходом браузера на его страницу), переименование и удаление.
Вынесено из main.py в отдельный Blueprint.
"""
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


def _api_settings_payload(extra=None):
    """Единый вид настроек для панели. Всегда возвращается целиком, чтобы
    панель после любого изменения перерисовалась из одного источника и не
    хранила своё представление о состоянии."""
    out = {"providers": providers.list_providers(),
           "defaults": api_keys.get_defaults(),
           "proxy": api_keys.get_proxy(),
           "dns": api_keys.get_dns(),
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
    if pid:
        if "key" in data:
            # Ключ приходит сюда сырым один раз — при вводе. Дальше панель
            # видит только маску, а сам ключ живёт в файле настроек вне проекта.
            api_keys.set_key(pid, data.get("key") or "")
        if "model" in data:
            api_keys.set_model(pid, data.get("model") or "")
        if "base_url" in data:
            api_keys.set_base_url(pid, data.get("base_url") or "")
        if data.get("make_default"):
            api_keys.set_defaults(pid, api_keys.get_model(pid))
    proxy = data.get("proxy")
    problems = {}
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
    return jsonify(_api_settings_payload(problems or None))


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
    url = providers.models_url(pid)
    if not url:
        return jsonify({"error": u"У «%s» не задан адрес списка моделей."
                                 % provider["name"]}), 400
    try:
        raw = openai_compat.fetch_models(
            url, api_keys.resolve_key(pid, providers.env_names_for(pid)),
            extra_headers=providers.headers_for(pid),
            proxy=api_keys.proxy_url(),
            connect_timeout=providers.connect_timeout_for(pid))
    except openai_compat.ApiError as e:
        msg, _status, _retry = api_backend.describe_api_error(e, provider["name"])
        print("<-- Список моделей %s не получен: %s" % (pid, msg))
        # Отвечаем 200 с текстом причины, а НЕ 502. Панель для любого не-200
        # показывает общее «сервер вернул ошибку (HTTP 502)» и выбрасывает тело
        # ответа — то есть пользователь не видел настоящей причины (недоступен
        # провайдер, неверный прокси, отклонён ключ). Здесь сервер отработал
        # штатно; неисправен внешний сервис, и об этом надо сказать словами.
        return jsonify(_api_settings_payload({"error": msg, "provider": pid}))
    free_only = bool(data.get("free_only"))
    models = providers.parse_models_response(raw, free_only=free_only)
    print("--> Список моделей %s обновлён: %d шт.%s"
          % (pid, len(models), " (только бесплатные)" if free_only else ""))
    return jsonify(_api_settings_payload({"models": models,
                                          "provider": pid,
                                          "free_only": free_only}))


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
        return jsonify({"ok": False, "error": msg,
                        "tls_issuer": probe.get("issuer", ""),
                        "tls_error": probe.get("error", "")})
    ms = int((res.get("elapsed") or 0) * 1000)
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
