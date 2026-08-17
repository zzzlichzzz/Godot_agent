# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты проверки источника запросов к серверу (server_auth).

Честная область действия проверяется тоже: токен лежит в файле, читаемом тем
же пользователем, поэтому от программы под той же учётной записью он не
защищает. Здесь проверяется то, что он ДОЛЖЕН закрывать — чужой токен, чужой
проект и открытый доступ к странице диагностики.
"""
import shutil
import sys
import tempfile

CFG = tempfile.mkdtemp(prefix="agent_cfg_auth_")
UDD_A = tempfile.mkdtemp(prefix="agent_udd_A_")
UDD_B = tempfile.mkdtemp(prefix="agent_udd_B_")
_os0.environ["GODOT_AGENT_CONFIG_DIR"] = CFG

import server_auth as SA
import main

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


TOKEN_A = "a" * 32
TOKEN_B = "b" * 32
with open(SA.token_path(UDD_A), "w", encoding="utf-8") as f:
    f.write(TOKEN_A + "\n")
with open(SA.token_path(UDD_B), "w", encoding="utf-8") as f:
    f.write(TOKEN_B)

cl = main.app.test_client()


def post(path, body=None, token=None):
    headers = {}
    if token is not None:
        headers[SA.HEADER] = token
    r = cl.post(path, json=body or {}, headers=headers)
    return r.status_code, r.get_json()


# ---------------------------------------------------------------------------
# 1) Чтение токена из файла проекта
# ---------------------------------------------------------------------------
check(u"токен читается и обрезается по краям", SA.read_token(UDD_A) == TOKEN_A)
check(u"нет файла -> пустой токен", SA.read_token(tempfile.mkdtemp()) == "")
check(u"нет папки -> пустой токен", SA.read_token("") == "")
check(u"файл токена лежит в папке проекта, а не в проекте",
      SA.token_path(UDD_A).startswith(UDD_A))

# ---------------------------------------------------------------------------
# 2) Страница диагностики открыта без токена
# ---------------------------------------------------------------------------
SA.reset()
r = cl.get("/dashboard")
check(u"/dashboard открывается без токена", r.status_code == 200)
r = cl.get("/dashboard/data")
check(u"/dashboard/data открывается без токена", r.status_code == 200)

# ---------------------------------------------------------------------------
# 3) Привязка при первом обращении
# ---------------------------------------------------------------------------
SA.reset()
check(u"до привязки сервер ни к чему не привязан", SA.bound_dir() is None)
st, j = post("/api/providers", {"user_data_dir": UDD_A}, token=TOKEN_A)
check(u"панель с верным токеном принята", st == 200, j)
check(u"сервер привязался к проекту", SA.bound_dir() == UDD_A)

st, j = post("/api/providers", {"user_data_dir": UDD_A}, token=TOKEN_A)
check(u"повторные запросы того же проекта проходят", st == 200)

# ---------------------------------------------------------------------------
# 4) Чужой токен и чужой проект
# ---------------------------------------------------------------------------
st, j = post("/api/providers", {"user_data_dir": UDD_B}, token=TOKEN_B)
check(u"панель ДРУГОГО проекта отклонена", st == 403, (st, j))
check(u"в отказе назван занятый проект", UDD_A in str(j.get("error", "")))

st, j = post("/api/providers", {"user_data_dir": UDD_A}, token=None)
check(u"запрос без токена отклонён", st == 403, (st, j))

st, j = post("/api/providers", {"user_data_dir": UDD_A}, token="c" * 32)
check(u"запрос с выдуманным токеном отклонён", st == 403)
check(u"тот же проект с НОВЫМ токеном -> совет перезапустить сервер",
      u"Токен проекта изменился" in str(j.get("error", "")), j)
check(u"и НЕ говорится про «другой проект»",
      u"другим проектом" not in str(j.get("error", "")))

# Скопированный проект: токен тот же, а папка другая — правки в чужой проект
# не пускаем, иначе агент писал бы файлы не туда.
st, j = post("/api/providers", {"user_data_dir": UDD_B}, token=TOKEN_A)
check(u"верный токен + чужая папка -> отказ 409", st == 409, (st, j))

# ---------------------------------------------------------------------------
# 5) Отклонённый запрос НЕ доходит до логики
# ---------------------------------------------------------------------------
st, j = post("/chats/new", {"user_data_dir": UDD_B, "kind": "api",
                            "provider": "openrouter"}, token=TOKEN_B)
check(u"создание чата чужой панелью отклонено", st == 403)
check(u"чат в чужом проекте не создан",
      not _os0.path.isfile(_os0.path.join(UDD_B, "agent_chats.json")))

# ---------------------------------------------------------------------------
# 6) Старая панель без файла токена: работаем, но громко предупреждаем
# ---------------------------------------------------------------------------
SA.reset()
UDD_OLD = tempfile.mkdtemp(prefix="agent_udd_old_")
st, j = post("/api/providers", {"user_data_dir": UDD_OLD}, token=None)
check(u"панель без файла токена не блокируется (совместимость)", st == 200)
check(u"но сервер к ней и не привязывается", SA.bound_dir() is None)

# ---------------------------------------------------------------------------
# 7) Сравнение путей терпимо к слэшам и регистру
# ---------------------------------------------------------------------------
SA.reset()
post("/api/providers", {"user_data_dir": UDD_A}, token=TOKEN_A)
weird = UDD_A.replace("\\", "/") + "/"
st, j = post("/api/providers", {"user_data_dir": weird}, token=TOKEN_A)
check(u"тот же путь с другими слэшами принимается", st == 200, (st, j, weird))

SA.reset()
for d in (UDD_A, UDD_B, UDD_OLD):
    shutil.rmtree(d, ignore_errors=True)
shutil.rmtree(CFG, ignore_errors=True)
n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
