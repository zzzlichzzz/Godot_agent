# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты истории диалога API-режима (api_history).

Главное, что проверяется: история отдельна от transcript, ответ модели
сохраняется СЫРЫМ (с блоком agent_action и ===DONE===), пара «запрос-ответ»
дописывается только целиком, а обрезка контекста сначала схлопывает старые
чтения файлов и только потом выбрасывает сообщения — и никогда не трогает
свежий хвост.
"""
import shutil
import sys
import tempfile

import api_history as H

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


BASE = tempfile.mkdtemp(prefix="agent_api_hist_")
CID = "abc123def456"

RAW_ANSWER = (u"Добавлю двойной прыжок.\n"
              u"```agent_action\n"
              u'{"action": "patch_file", "path": "res://p.gd", '
              u'"search": "A", "replace": "B", "summary": "s"}\n'
              u"```\n===DONE===")

# ---------------------------------------------------------------------------
# 1) Пустая история и путь к файлу
# ---------------------------------------------------------------------------
check(u"пустой чат — пустая история", H.load_messages(BASE, CID) == [])
check(u"файл истории лежит в отдельной папке",
      H.history_path(BASE, CID).endswith(
          _os0.path.join("agent_api_history", CID + ".json")))
check(u"без chat_id пути нет", H.history_path(BASE, "") == "")
check(u"опасное имя чата отфильтровано",
      ".." not in H.history_path(BASE, "../../evil"))

# ---------------------------------------------------------------------------
# 2) Атомарная запись обмена
# ---------------------------------------------------------------------------
H.append_exchange(BASE, CID, u"добавь двойной прыжок", RAW_ANSWER,
                  usage={"prompt_tokens": 100, "completion_tokens": 20})
msgs = H.load_messages(BASE, CID)
check(u"обмен записан как две реплики", len(msgs) == 2)
check(u"роли верные",
      msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant")
check(u"ответ сохранён СЫРЫМ: блок agent_action на месте",
      "```agent_action" in msgs[1]["content"])
check(u"ответ сохранён СЫРЫМ: маркер ===DONE=== на месте",
      msgs[1]["content"].endswith("===DONE==="))
check(u"BBCode не появился", "[b]" not in msgs[1]["content"])

st = H.stats(BASE, CID)
check(u"расход токенов накоплен",
      st["usage_total"]["prompt_tokens"] == 100
      and st["usage_total"]["completion_tokens"] == 20)
check(u"счётчик запросов", st["usage_total"]["requests"] == 1)

H.append_exchange(BASE, CID, u"второй вопрос", u"второй ответ",
                  usage={"prompt_tokens": 50, "completion_tokens": 10})
st = H.stats(BASE, CID)
check(u"расход суммируется между обменами",
      st["usage_total"]["prompt_tokens"] == 150 and st["usage_total"]["requests"] == 2)
check(u"история выросла", st["messages"] == 4)

# ---------------------------------------------------------------------------
# 3) Провальный запрос не оставляет следов
# ---------------------------------------------------------------------------
before = len(H.load_messages(BASE, CID))
# Так ведёт себя бэкенд при ошибке: append_exchange просто не вызывается.
check(u"неудачный запрос не пишется в историю",
      len(H.load_messages(BASE, CID)) == before)

# ---------------------------------------------------------------------------
# 4) Сборка запроса
# ---------------------------------------------------------------------------
req = H.build_request_messages(BASE, CID, u"СИСТЕМНЫЙ БЛОК", u"новый вопрос")
check(u"системный блок первым",
      req[0]["role"] == "system" and req[0]["content"] == u"СИСТЕМНЫЙ БЛОК")
check(u"новое сообщение последним",
      req[-1]["role"] == "user" and req[-1]["content"] == u"новый вопрос")
check(u"история между ними", len(req) == 1 + 4 + 1)
check(u"сборка запроса НЕ пишет в хранилище",
      len(H.load_messages(BASE, CID)) == 4)
check(u"в запросе только роль/содержимое (без служебных полей)",
      all(set(m.keys()) == {"role", "content"} for m in req))

# ---------------------------------------------------------------------------
# 5) Обрезка: сначала схлопываются старые чтения файлов
# ---------------------------------------------------------------------------
CID2 = "trim0000test"
BIG = u"x" * 9000          # ~3000 токенов на «прочитанный файл»
for i in range(6):
    H.append_exchange(BASE, CID2, u"дай файл %d" % i, u"вот он")
    H.append(BASE, CID2, H.ROLE_USER,
             u"[Система]: содержимое res://f%d.gd:\n%s" % (i, BIG),
             kind=H.KIND_TOOL_RESULT)
H.append_exchange(BASE, CID2, u"САМЫЙ СВЕЖИЙ ВОПРОС", u"САМЫЙ СВЕЖИЙ ОТВЕТ")

full = H.stats(BASE, CID2)["approx_tokens"]
check(u"нетронутая история заведомо больше бюджета", full > 5000)

req2 = H.build_request_messages(BASE, CID2, u"СИС", u"вопрос",
                                budget_tokens=5000)
joined = u"\n".join(m["content"] for m in req2)


def budget_used(req):
    """Бюджет ограничивает системный блок и историю; новое сообщение
    (последнее) в него не входит и не обрезается никогда."""
    return sum(H.estimate_tokens(m["content"]) for m in req[:-1])


check(u"после обрезки укладываемся в бюджет", budget_used(req2) <= 5000)
check(u"свежий хвост сохранён",
      u"САМЫЙ СВЕЖИЙ ВОПРОС" in joined and u"САМЫЙ СВЕЖИЙ ОТВЕТ" in joined)
check(u"старые чтения файлов схлопнуты в заметку",
      u"убрано из памяти диалога" in joined)
check(u"нетронутым остался ровно один (самый свежий) прочитанный файл",
      sum(1 for m in req2 if (u"x" * 500) in m["content"]) == 1)
check(u"модели сказано перечитать файл при необходимости",
      u"запроси файл заново" in joined)

# ---------------------------------------------------------------------------
# 6) Обрезка: жёсткий случай — выбрасывание старого целиком
# ---------------------------------------------------------------------------
req3 = H.build_request_messages(BASE, CID2, u"СИС", u"вопрос",
                                budget_tokens=400)
joined3 = u"\n".join(m["content"] for m in req3)
check(u"при крошечном бюджете старое выброшено", len(req3) < len(req2))
check(u"крошечный бюджет тоже соблюдён", budget_used(req3) <= 400)
check(u"о забытом начале модель предупреждена",
      u"не поместилось в контекст" in joined3)
check(u"даже при крошечном бюджете свежий хвост на месте",
      u"САМЫЙ СВЕЖИЙ ОТВЕТ" in joined3)
check(u"системный блок никогда не выбрасывается",
      req3[0]["role"] == "system")
check(u"новое сообщение не обрезано даже при крошечном бюджете",
      req3[-1]["content"] == u"вопрос")

# 6b) Патология: одно гигантское сообщение в хвосте всё равно должно влезть.
CID5 = "huge0000test"
H.append_exchange(BASE, CID5, u"дай файл", u"вот")
H.append(BASE, CID5, H.ROLE_USER, u"[Система]: файл:\n" + (u"y" * 200000),
         kind=H.KIND_TOOL_RESULT)
req5 = H.build_request_messages(BASE, CID5, u"СИС", u"вопрос",
                                budget_tokens=1000)
check(u"одно гигантское сообщение всё равно укладывается в бюджет",
      budget_used(req5) <= 1000)
check(u"о факте обрезки сказано",
      any((u"обрезано" in m["content"]) or (u"убрано из памяти" in m["content"])
          for m in req5))

# ---------------------------------------------------------------------------
# 7) Жёсткий предел числа сообщений
# ---------------------------------------------------------------------------
CID3 = "cap00000test"
for i in range(H.MAX_MESSAGES // 2 + 20):
    H.append_exchange(BASE, CID3, u"q%d" % i, u"a%d" % i)
st3 = H.stats(BASE, CID3)
check(u"жёсткий предел сообщений соблюдён", st3["messages"] <= H.MAX_MESSAGES)
check(u"факт обрезки зафиксирован", st3["trimmed"] > 0)
check(u"самые свежие сообщения остались",
      H.load_messages(BASE, CID3)[-1]["content"].startswith("a"))

# ---------------------------------------------------------------------------
# 8) Очистка и удаление
# ---------------------------------------------------------------------------
H.clear(BASE, CID)
check(u"clear забывает диалог", H.load_messages(BASE, CID) == [])
check(u"clear сохраняет накопленный расход",
      H.stats(BASE, CID)["usage_total"]["prompt_tokens"] == 150)
H.delete(BASE, CID)
check(u"delete убирает файл", not _os0.path.isfile(H.history_path(BASE, CID)))

# ---------------------------------------------------------------------------
# 9) Битый файл не валит сервер
# ---------------------------------------------------------------------------
CID4 = "broken00test"
p = H.history_path(BASE, CID4)
_os0.makedirs(_os0.path.dirname(p), exist_ok=True)
with open(p, "w", encoding="utf-8") as f:
    f.write("{ это не json")
check(u"битый файл истории -> пустая история", H.load_messages(BASE, CID4) == [])
check(u"после битого файла запись работает",
      H.append_exchange(BASE, CID4, u"q", u"a")
      and len(H.load_messages(BASE, CID4)) == 2)

with open(p, "w", encoding="utf-8") as f:
    f.write('{"messages": [{"role": "bogus", "content": "x"}, '
            '{"role": "user"}, {"role": "user", "content": "ok"}]}')
check(u"мусорные записи внутри файла отфильтрованы",
      [m["content"] for m in H.load_messages(BASE, CID4)] == ["ok"])

check(u"оценка токенов растёт с длиной",
      H.estimate_tokens("x" * 300) > H.estimate_tokens("x" * 30))
check(u"оценка токенов завышена, а не занижена",
      H.estimate_tokens("x" * 300) >= 100)

# ---------------------------------------------------------------------------
# 10) Согласованность бюджетов токенов
# ---------------------------------------------------------------------------
# Провайдер отклоняет запрос, если prompt_tokens + max_tokens больше окна
# контекста модели. Значит три числа связаны, и подобрать их по отдельности
# нельзя: раньше здесь было 24000 истории + 16000 вывода = 40000, что не влезало
# в типичное для бесплатных моделей окно 32k, и длинный диалог гарантированно
# упирался бы в отказ по контексту.
import agent_prompts as AP
check(u"история + вывод влезают в предполагаемое окно контекста",
      AP.API_HISTORY_BUDGET + AP.API_MAX_TOKENS <= AP.API_CONTEXT_WINDOW,
      (AP.API_HISTORY_BUDGET, AP.API_MAX_TOKENS, AP.API_CONTEXT_WINDOW))
check(u"остался запас на новое сообщение (не меньше 4k)",
      AP.API_CONTEXT_WINDOW - AP.API_HISTORY_BUDGET - AP.API_MAX_TOKENS >= 4000)
check(u"бюджет истории берётся из одного места",
      H.DEFAULT_CONTEXT_BUDGET == AP.API_HISTORY_BUDGET)
check(u"на вывод отведено осмысленно много (план и файл за один ответ)",
      AP.API_MAX_TOKENS >= 4000)

shutil.rmtree(BASE, ignore_errors=True)
n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
