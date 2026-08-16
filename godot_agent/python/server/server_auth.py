# -*- coding: utf-8 -*-
"""Проверка того, что запрос пришёл именно от панели этого проекта.

ЧТО ЭТО РЕАЛЬНО ДАЁТ И ЧЕГО НЕ ДАЁТ. Токен лежит в файле, который читается
тем же пользователем, что запускает Godot. Значит программа, работающая под
той же учётной записью, прочитает его так же, как панель, и НИКАКОЙ защиты от
вредоносного ПО здесь нет — от этого не спасает ничего, кроме изоляции на
уровне ОС. Не надо считать этот модуль защитой от целенаправленной атаки.

Что он закрывает по-настоящему:
  * другую учётную запись на той же машине (файл создаётся в личной папке
    проекта, чужому пользователю он недоступен);
  * случайные обращения: чужой скрипт, скопированный пример с curl, сканер
    локальных портов, другой инструмент, занявший тот же порт;
  * панель ДРУГОГО проекта Godot, подключившуюся к этому серверу — известная
    проблема из ОТЛОЖЕНО.md: сервер теперь привязывается к первому проекту и
    чужие user_data_dir отклоняет, поэтому правки не уезжают в чужой проект.

Веб-страницы в браузере отдельного барьера не требуют: все маршруты панели
принимают только JSON, а такой кросс-доменный запрос вызывает preflight,
который Flask без CORS-заголовков отклоняет.

ПРИВЯЗКА ПРИ ПЕРВОМ ОБРАЩЕНИИ. Сервер не знает заранее, какой проект его
запустил, поэтому первый запрос с корректной парой «user_data_dir + токен из
его файла» становится хозяином сессии. Панель запускает сервер сама и
обращается к нему сразу, так что окно между запуском и привязкой — миллисекунды.
"""
import os

HEADER = "X-Agent-Token"
TOKEN_FILE = "godot_agent_token.txt"

# Маршруты без проверки. /dashboard открывается в обычном браузере, который
# никаких наших заголовков не пошлёт; секреты из журнала вырезаются отдельно
# (dashboard._redact), поэтому смысла закрывать страницу токеном нет.
OPEN_PATHS = ("/dashboard", "/dashboard/data")

_bound = {"user_data_dir": None, "token": None, "warned": False}


def reset():
    """Сбрасывает привязку. Нужно тестам; в работе сервер живёт один проект."""
    _bound["user_data_dir"] = None
    _bound["token"] = None
    _bound["warned"] = False


def bound_dir():
    return _bound["user_data_dir"]


def token_path(user_data_dir):
    if not user_data_dir:
        return ""
    return os.path.join(str(user_data_dir), TOKEN_FILE)


def read_token(user_data_dir):
    """Токен из файла проекта или "" — если файла нет или он пуст."""
    p = token_path(user_data_dir)
    if not p or not os.path.isfile(p):
        return ""
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _same_dir(a, b):
    """Сравнение путей без учёта регистра и слэшей: панель и сервер могут
    записать один и тот же путь по-разному (C:/x vs C:\\x)."""
    try:
        na = os.path.normcase(os.path.abspath(str(a or "")))
        nb = os.path.normcase(os.path.abspath(str(b or "")))
        return na == nb and na != ""
    except Exception:
        return False


def check(path, header_token, user_data_dir):
    """Пускать ли запрос. Возвращает (ok, код_ошибки, текст_для_панели).

    Логика намеренно простая и предсказуемая: сначала привязка, потом сверка
    и токена, и проекта. Любая неоднозначность трактуется как отказ — тихо
    пустить чужой запрос хуже, чем показать пользователю понятную ошибку.
    """
    for open_path in OPEN_PATHS:
        if path == open_path or path.startswith(open_path + "/"):
            return True, 0, ""

    token = (header_token or "").strip()
    udd = str(user_data_dir or "").strip()

    if _bound["token"] is None:
        # Ещё не привязан: ждём первый запрос с папкой проекта и токеном из неё.
        if not udd:
            # Запрос без user_data_dir до привязки пропускаем: панель шлёт его
            # в каждом запросе, а вот сторонний вызов без папки всё равно
            # ничего полезного не сделает — проект не синхронизирован.
            return True, 0, ""
        expected = read_token(udd)
        if not expected:
            if not _bound["warned"]:
                _bound["warned"] = True
                print("--> ВНИМАНИЕ: панель не создала файл токена (%s). Сервер "
                      "работает без проверки источника запросов — обновите "
                      "аддон." % token_path(udd))
            return True, 0, ""
        if token != expected:
            return False, 403, (u"Сервер агента не принял запрос: токен не "
                                u"совпал с файлом %s. Перезапустите Godot — "
                                u"панель создаст токен заново." % TOKEN_FILE)
        _bound["token"] = expected
        _bound["user_data_dir"] = udd
        print("--> Сервер привязан к проекту: %s" % udd)
        return True, 0, ""

    if token != _bound["token"]:
        if udd and _same_dir(udd, _bound["user_data_dir"]):
            # Папка та же, а токен другой: файл токена пересоздан (папка
            # user:// была очищена, проект перенесён). Про «другой проект»
            # говорить нельзя — это тот же проект, и совет тут другой.
            return False, 403, (u"Токен проекта изменился, а сервер агента ещё "
                                u"помнит прежний. Закройте окно сервера "
                                u"(godot_agent_server) — панель запустит его "
                                u"заново.")
        return False, 403, (u"Сервер агента занят другим проектом Godot "
                            u"(%s). Запустите отдельный сервер для этого "
                            u"проекта или закройте тот." % _bound["user_data_dir"])
    if udd and not _same_dir(udd, _bound["user_data_dir"]):
        # Токен совпал, а папка другая: так бывает, если пользователь скопировал
        # проект вместе с файлом токена. Правки в чужой проект не пускаем.
        return False, 409, (u"Этот сервер уже обслуживает проект %s. Для "
                            u"другого проекта нужен свой сервер."
                            % _bound["user_data_dir"])
    return True, 0, ""


def install(app, jsonify):
    """Ставит проверку на все маршруты приложения."""
    from flask import request

    @app.before_request
    def _guard():  # noqa: ANN202
        body = {}
        if request.method == "POST":
            try:
                body = request.get_json(silent=True) or {}
            except Exception:
                body = {}
        ok, code, message = check(request.path,
                                  request.headers.get(HEADER, ""),
                                  body.get("user_data_dir"))
        if ok:
            return None
        print("<-- Запрос отклонён (%s %s): %s" % (request.method, request.path,
                                                   message))
        return jsonify({"error": message}), code
