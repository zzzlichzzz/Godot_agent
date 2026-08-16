# -*- coding: utf-8 -*-
"""История диалога для API-режима: то, что модель помнит о разговоре.

ЗАЧЕМ ОТДЕЛЬНОЕ ХРАНИЛИЩЕ. В браузерном режиме контекст живёт на самом сайте:
вкладка помнит весь диалог, и агенту достаточно напечатать новое сообщение.
По API модель НЕ ПОМНИТ НИЧЕГО — всю переписку нужно присылать заново каждым
запросом. Значит владельцем истории становится плагин.

ПОЧЕМУ НЕЛЬЗЯ ВЗЯТЬ transcript ИЗ chat_store. Он для другого — перерисовать
панель, и как контекст модели не годится по трём причинам:
  1. В нём НЕ сырой ответ модели: блок ```agent_action уже вырезан и заменён
     заглушкой, а текст сконвертирован в BBCode. Отдать это модели как её
     собственные слова — значит показать ей искажённую версию себя, после чего
     она начинает путаться в формате действий.
  2. MAX_TRANSCRIPT = 300 молча режет начало — для панели это незаметно, для
     контекста это тихая потеря памяти.
  3. Реплика пользователя пишется туда ДО склейки с системными заметками
     (заметка о действии, сводка внешних изменений), то есть в транскрипте не
     то, что реально ушло в модель.
Поэтому здесь лежит ВТОРОЕ хранилище со своей задачей. Объединять их нельзя:
transcript — что показать человеку, messages — что помнит модель.

ПОЧЕМУ ОТДЕЛЬНЫЙ ФАЙЛ НА ЧАТ, А НЕ ПОЛЕ В agent_chats.json. chat_store при
каждом добавлении реплики читает и перезаписывает ВЕСЬ список чатов целиком
(_load/_save). История содержит полные тексты прочитанных файлов, то есть
мегабайты, и такая перезапись на каждое сообщение — заметный тормоз и риск
потерять весь список чатов при обрыве. Отдельный файл на чат это снимает:
    <user_data_dir>/agent_api_history/<chat_id>.json

АТОМАРНОСТЬ ОБМЕНА. Пара «запрос пользователя + ответ модели» дописывается
ТОЛЬКО после успешного ответа (append_exchange). Если запрос не дошёл, модель
его не видела — значит и в её памяти его быть не должно. Иначе история
разошлась бы с тем, что реально знает модель, и следующий запрос стал бы врать
про несуществующую реплику.
"""
import json
import os
import time

_DIR_NAME = "agent_api_history"

# Жёсткий предел числа сообщений в файле — страховка от бесконечного роста.
# Рабочее ограничение контекста делается не им, а бюджетом токенов ниже.
MAX_MESSAGES = 400

# Бюджет токенов на СИСТЕМНЫЙ блок + историю (без нового запроса). Значение
# приходит из agent_prompts, где оно посчитано вместе с лимитом вывода и
# предполагаемым окном контекста модели: провайдер отклоняет запрос, если
# prompt_tokens + max_tokens больше окна, поэтому эти числа нельзя подбирать
# по отдельности. Точный предел конкретной модели заранее неизвестен, поэтому
# есть и второй, реактивный механизм: на ContextTooLongError бэкенд сообщает
# пользователю, что пора начать новый чат.
from agent_prompts import API_HISTORY_BUDGET as DEFAULT_CONTEXT_BUDGET

# Сколько последних сообщений не трогаем при обрезке ни при каких условиях:
# свежий контекст — это как раз то, чем модель занята сейчас.
KEEP_RECENT = 6

# Роли и виды сообщений.
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"

KIND_PROMPT = "prompt"          # реплика пользователя
KIND_TOOL_RESULT = "tool_result"  # результат действия: файлы, дерево, справка
KIND_NOTE = "note"              # системная заметка (откат, внешние правки)
KIND_ANSWER = "answer"          # ответ модели


# ---------------------------------------------------------------------------
# Файлы
# ---------------------------------------------------------------------------

def _safe_id(chat_id):
    """Идентификатор чата как имя файла. chat_id генерируется через uuid4 и
    безопасен, но проверяем явно: имя файла из внешних данных без фильтра —
    классический путь к записи куда не следует."""
    s = str(chat_id or "")
    return "".join(ch for ch in s if ch.isalnum() or ch in "-_")[:64]


def history_dir(base_dir):
    return os.path.join(str(base_dir or ""), _DIR_NAME)


def history_path(base_dir, chat_id):
    cid = _safe_id(chat_id)
    if not base_dir or not cid:
        return ""
    return os.path.join(history_dir(base_dir), cid + ".json")


def _empty():
    return {"version": 1, "messages": [],
            "usage_total": {"prompt_tokens": 0, "completion_tokens": 0,
                            "requests": 0},
            "trimmed": 0}


def _load(base_dir, chat_id):
    p = history_path(base_dir, chat_id)
    if not p or not os.path.isfile(p):
        return _empty()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("[api_history] Файл истории чата %s не читается (%s) — начинаю пустую."
              % (chat_id, e))
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
        return _empty()
    out = _empty()
    for m in data["messages"]:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "")
        content = m.get("content")
        if role not in (ROLE_USER, ROLE_ASSISTANT, ROLE_SYSTEM):
            continue
        if not isinstance(content, str):
            continue
        out["messages"].append({
            "role": role,
            "content": content,
            "kind": str(m.get("kind") or ""),
            "ts": float(m.get("ts") or 0.0),
        })
    if isinstance(data.get("usage_total"), dict):
        for k in ("prompt_tokens", "completion_tokens", "requests"):
            try:
                out["usage_total"][k] = int(data["usage_total"].get(k) or 0)
            except Exception:
                pass
    try:
        out["trimmed"] = int(data.get("trimmed") or 0)
    except Exception:
        pass
    return out


def _save(base_dir, chat_id, data):
    p = history_path(base_dir, chat_id)
    if not p:
        return False
    tmp = p + ".tmp"
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        return True
    except Exception as e:
        print("[api_history] Не удалось сохранить историю чата %s (%s)" % (chat_id, e))
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Оценка размера
# ---------------------------------------------------------------------------

def estimate_tokens(text):
    """ПРИБЛИЗИТЕЛЬНОЕ число токенов. Используется ТОЛЬКО для решения об
    обрезке, никогда для показа расхода пользователю — точные числа приходят
    от провайдера в поле usage.

    Считаем 3 символа на токен. Настоящего токенизатора в проекте нет и
    заводить его (tiktoken и подобные) ради оценки не стоит: это ещё одна
    зависимость в exe. Оценка сознательно ЗАВЫШЕНА: русский текст и код
    дают примерно 2–4 символа на токен, и лучше схлопнуть историю чуть
    раньше, чем получить отказ провайдера посреди задачи.
    """
    return int(len(str(text or "")) / 3.0) + 1


def _messages_tokens(messages):
    return sum(estimate_tokens(m.get("content")) for m in messages)


# ---------------------------------------------------------------------------
# Запись
# ---------------------------------------------------------------------------

def append(base_dir, chat_id, role, content, kind=""):
    """Дописывает одно сообщение. Обычный путь — append_exchange; эта функция
    нужна для одиночных системных вставок."""
    if not base_dir or not chat_id or not isinstance(content, str) or not content:
        return False
    data = _load(base_dir, chat_id)
    data["messages"].append({"role": role, "content": content,
                             "kind": kind, "ts": time.time()})
    _enforce_hard_cap(data)
    return _save(base_dir, chat_id, data)


def append_exchange(base_dir, chat_id, user_text, assistant_text,
                    user_kind=KIND_PROMPT, usage=None):
    """Атомарно дописывает пару «что отправили — что ответили».

    assistant_text должен быть СЫРЫМ текстом ответа модели: с блоком
    ```agent_action и маркером ===DONE===, без конвертации в BBCode. Именно
    это модель считает своими словами, и именно это должно вернуться ей в
    следующем запросе.
    """
    if not base_dir or not chat_id:
        return False
    data = _load(base_dir, chat_id)
    now = time.time()
    if isinstance(user_text, str) and user_text:
        data["messages"].append({"role": ROLE_USER, "content": user_text,
                                 "kind": user_kind, "ts": now})
    if isinstance(assistant_text, str) and assistant_text:
        data["messages"].append({"role": ROLE_ASSISTANT, "content": assistant_text,
                                 "kind": KIND_ANSWER, "ts": now})
    if isinstance(usage, dict):
        tot = data["usage_total"]
        for src, dst in (("prompt_tokens", "prompt_tokens"),
                         ("completion_tokens", "completion_tokens")):
            try:
                tot[dst] += int(usage.get(src) or 0)
            except Exception:
                pass
        tot["requests"] = int(tot.get("requests") or 0) + 1
    else:
        data["usage_total"]["requests"] = int(
            data["usage_total"].get("requests") or 0) + 1
    _enforce_hard_cap(data)
    return _save(base_dir, chat_id, data)


def _enforce_hard_cap(data):
    msgs = data["messages"]
    if len(msgs) > MAX_MESSAGES:
        drop = len(msgs) - MAX_MESSAGES
        del msgs[:drop]
        data["trimmed"] = int(data.get("trimmed") or 0) + drop


def clear(base_dir, chat_id):
    """Забыть весь диалог, но сохранить накопленный расход токенов."""
    data = _load(base_dir, chat_id)
    keep = data.get("usage_total")
    fresh = _empty()
    if isinstance(keep, dict):
        fresh["usage_total"] = keep
    return _save(base_dir, chat_id, fresh)


def delete(base_dir, chat_id):
    """Удаляет файл истории — вызывается при удалении самого чата, чтобы
    папка не копила файлы уже несуществующих переписок."""
    p = history_path(base_dir, chat_id)
    if not p:
        return False
    try:
        if os.path.isfile(p):
            os.remove(p)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Чтение и обрезка
# ---------------------------------------------------------------------------

def load_messages(base_dir, chat_id):
    """Сообщения как есть, без системного блока и без обрезки."""
    return _load(base_dir, chat_id)["messages"]


def stats(base_dir, chat_id):
    """Сводка для панели: расход токенов и размер истории."""
    data = _load(base_dir, chat_id)
    msgs = data["messages"]
    return {"messages": len(msgs),
            "approx_tokens": _messages_tokens(msgs),
            "usage_total": data["usage_total"],
            "trimmed": int(data.get("trimmed") or 0)}


_COLLAPSE_NOTE = (u"[Система]: содержимое, присланное здесь ранее, убрано из "
                  u"памяти диалога для экономии контекста (%d симв.). Если оно "
                  u"снова нужно — запроси файл заново; учти, что за это время "
                  u"он мог измениться.")

_TRIM_NOTE = (u"[Система]: начало этого диалога (%d сообщений) не поместилось "
              u"в контекст и было забыто. Не ссылайся на договорённости из "
              u"начала разговора — если что-то важно, переспроси.")

_CUT_MARK = u"\n[Система]: …сообщение обрезано, не поместилось в контекст."

# Меньше этого размера схлопывать нечего: заметка займёт почти столько же.
_MIN_COLLAPSE_CHARS = 400


def _collapse(msg):
    """Заменяет тяжёлое содержимое короткой заметкой. Возвращает True, если
    было что схлопывать.

    Повторное схлопывание отсекается служебным флагом, а НЕ сравнением начала
    текста с началом заметки: настоящие результаты инструментов начинаются
    теми же словами («[Система]: содержимое res://...»), и такая проверка
    молча отключала бы схлопывание для всех реальных чтений файлов. Флаг
    ставится на копии сообщения внутри build_request_messages и наружу не
    уходит — в запрос попадают только role и content.
    """
    content = msg.get("content") or ""
    if msg.get("_collapsed") or len(content) < _MIN_COLLAPSE_CHARS:
        return False
    msg["_collapsed"] = True
    msg["content"] = _COLLAPSE_NOTE % len(content)
    return True


def _fit_to_limit(msgs, limit, keep_recent):
    """Приводит историю к бюджету. Возвращает число выброшенных сообщений.

    Шаги от самого безобидного к самому грубому. Важно, что последний шаг
    гарантирует попадание в бюджет: запрос, который провайдер заведомо
    отклонит, хуже урезанного запроса.

      1. Схлопнуть старые результаты инструментов, КРОМЕ последнего —
         прочитанный когда-то файл самая тяжёлая и самая бесполезная часть
         контекста: он уже мог измениться, и честнее сказать «перечитай»,
         чем держать устаревшую копию. Последний не трогаем: именно с ним
         модель работает сейчас.
      2. Выбросить самые старые сообщения, сохраняя свежий хвост.
      3. Если всё ещё не влезаем — схлопнуть и последний результат тоже.
         Хвост сам по себе может быть больше бюджета (одно чтение большого
         файла), и защищать его до отказа провайдера бессмысленно.
      4. Выбросить старое дальше, оставив хотя бы последний обмен.
      5. Обрезать содержимое самых больших оставшихся сообщений.
    """
    dropped = 0

    tool_idx = [i for i, m in enumerate(msgs) if m.get("kind") == KIND_TOOL_RESULT]
    protect = tool_idx[-1] if tool_idx else -1
    for i in tool_idx:
        if _messages_tokens(msgs) <= limit:
            break
        if i == protect:
            continue
        _collapse(msgs[i])

    while _messages_tokens(msgs) > limit and len(msgs) > keep_recent:
        msgs.pop(0)
        dropped += 1

    if _messages_tokens(msgs) > limit:
        for m in msgs:
            if m.get("kind") != KIND_TOOL_RESULT:
                continue
            _collapse(m)
            if _messages_tokens(msgs) <= limit:
                break

    while _messages_tokens(msgs) > limit and len(msgs) > 2:
        msgs.pop(0)
        dropped += 1

    # Ограниченное число проходов: каждый шаг гарантированно уменьшает объём,
    # но цикл без предела в коде, который вызывается на каждый запрос, — риск.
    for _ in range(len(msgs) + 2):
        if _messages_tokens(msgs) <= limit or not msgs:
            break
        j = max(range(len(msgs)), key=lambda k: len(msgs[k].get("content") or ""))
        content = msgs[j].get("content") or ""
        over = _messages_tokens(msgs) - limit
        keep = max(0, len(content) - (over * 3 + 32))
        if keep <= 0 and len(msgs) > 1:
            msgs.pop(j)
            dropped += 1
            continue
        msgs[j]["content"] = content[:keep] + _CUT_MARK
    return dropped


def build_request_messages(base_dir, chat_id, system_text, user_text,
                           budget_tokens=DEFAULT_CONTEXT_BUDGET,
                           keep_recent=KEEP_RECENT):
    """Готовый массив messages для запроса к провайдеру.

    Порядок сборки: системный блок, обрезанная история, новое сообщение.
    В хранилище ничего не пишется — запись делает append_exchange ПОСЛЕ
    успешного ответа.

    ЧТО ВХОДИТ В БЮДЖЕТ. Ограничиваются системный блок и история. Новое
    сообщение (user_text) не обрезается никогда: это и есть суть запроса, а
    когда оно большое — это результат инструмента, размер которого уже
    ограничен на своём уровне (PER_FILE_CHAR_LIMIT, TOTAL_CHAR_BUDGET).
    Значит полный запрос равен бюджету плюс размер нового сообщения.
    """
    data = _load(base_dir, chat_id)
    msgs = [dict(m) for m in data["messages"]]

    sys_tokens = estimate_tokens(system_text) if system_text else 0
    limit = max(0, int(budget_tokens) - sys_tokens)
    dropped = _fit_to_limit(msgs, limit, max(2, int(keep_recent)))

    out = []
    if system_text:
        out.append({"role": ROLE_SYSTEM, "content": system_text})
    forgotten = dropped + int(data.get("trimmed") or 0)
    if forgotten:
        out.append({"role": ROLE_USER, "content": _TRIM_NOTE % forgotten})
    for m in msgs:
        out.append({"role": m["role"], "content": m["content"]})
    if user_text:
        out.append({"role": ROLE_USER, "content": user_text})
    return out
