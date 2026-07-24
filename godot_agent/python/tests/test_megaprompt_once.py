# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v104.2: мега-промпт не должен уходить повторно в чат, который уже
обучен. Источник истины — запись САМОГО чата (флаг primed + prompt_hash),
а не глобальный флаг проекта (он перетирается при создании/открытии других
чатов и перезапусках сервера — репорт 23.07: «мегапромпт прислался ещё раз,
хотя не менялся»)."""
import sys
import tempfile

import chat_store
import server_state

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


tmp = tempfile.mkdtemp(prefix="agent_chats_test_")
server_state.STATE["user_data_dir"] = tmp

# 1) нет текущего чата -> праймить нужно
server_state.STATE["current_chat_id"] = None
check("1. нет текущего чата -> False",
      server_state.chat_already_primed("HASH") is False)

# 2) чат есть, но не обучен -> праймить нужно
rec = chat_store.create_chat(tmp, url="https://chat.qwen.ai/c/1",
                             title="тестовый чат", primed=False)
server_state.STATE["current_chat_id"] = rec["id"]
check("2. чат не обучен -> False",
      server_state.chat_already_primed("HASH") is False)

# 3) обучен, prompt_hash пуст (старая запись) -> повторно НЕ шлём
chat_store.touch_chat(tmp, rec["id"], primed=True)
check("3. обучен, prompt_hash пуст -> True",
      server_state.chat_already_primed("HASH") is True)

# 4) обучен той же версией промпта -> повторно НЕ шлём
chat_store.update_chat(tmp, rec["id"], prompt_hash="HASH")
check("4. обучен той же версией -> True",
      server_state.chat_already_primed("HASH") is True)

# 5) версия промпта изменилась -> нужен новый прайм
check("5. версия промпта изменилась -> False",
      server_state.chat_already_primed("NEW_HASH") is False)

print("\nИТОГО: %d/%d OK" % (sum(1 for r in results if r), len(results)))
sys.exit(0 if all(results) else 1)
