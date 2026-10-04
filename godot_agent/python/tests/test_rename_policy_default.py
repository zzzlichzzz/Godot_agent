# -*- coding: utf-8 -*-
"""Синтетика: дефолт «переименовывать недоказанные ссылки» не может разъезжаться.

Требование, которое зафиксировано этим файлом:

  * Серверное состояние ДОЛЖНО иметь rename_unverified=None — «решение не
    принято». Значение True появляется только после того, как панель РЕАЛЬНО
    прислала свою галочку тем же каналом, что allow_addons.
  * Пока решение не принято, агент НЕ подставляет флаг в действие: ядро само
    берёт свой безопасный strict (allow_unverified=False).
  * Явно False от панели — это отказ, и он обязан дойти до ядра как False.
  * Явно заданный в действии флаг не перетирается ничем.

Замер (баг). Три слоя объявляли дефолт «включено»:

    Слой    Дефолт   Файл
    Панель  true     agent_panel.gd:143
    Сервер  True     server/server_state.py
    Ядро    False    godot_tools/symbol_refactor.py

а агент в main.py подставлял флаг так:

    result["allow_unverified"] = STATE.get("rename_unverified") is not False

`is not False` — это не «включено», а «НЕ равно False». Свежий сервер, где
STATE["rename_unverified"] = True (литеральный дефолт) либо ключа вовсе нет
(STATE.get() -> None), давал True в обоих случаях. Значит агент МОЛЧА получал
небезопасное переименование ровно там, где панель галочку ещё не
синхронизировала, — и обещание в комментарии server_state.py («клиент,
который его не прислал, получает прежний strict») не выполнялось: агент как раз
таким клиентом и был.

Красный сейчас по делу: STATE по умолчанию True, а подстановка трактует любое
не-False как разрешение.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import main
from godot_tools import symbol_refactor
from minilich import ml_project_index
from server_state import STATE

SERVER = os.path.join(os.path.dirname(__file__), os.pardir, "server", "server_state.py")

PLAYER = "class_name Player\nextends Node2D\n"
# Прямой наследник: доказуемо связан с нашим class_name.
TYPED = "extends Node\n\nvar unit: Player\n"
# Посторонний файл с ОДНОЙ недоказанной ссылкой: ресивер не типизирован.
UNPROVEN = "extends Node\n\nfunc fire(target):\n\ttarget.spawn(Player)\n"


def _history_storage():
    """Текущее переопределение хранилища истории (или None, если не задано)."""
    import history_manager
    return getattr(history_manager, "_STORAGE_OVERRIDE", None)


def _action(**extra):
    action = {"action": "rename_symbol", "kind": "class_name",
              "declaration": "res://src/player.gd:1",
              "old_name": "Player", "new_name": "Avatar"}
    action.update(extra)
    return action


# __APPEND_POLICY_UNIT__
class RenamePolicyUnit(unittest.TestCase):
    """Подстановка флага в действие rename_symbol."""

    def setUp(self):
        self.saved = STATE.get("rename_unverified")
        self.addCleanup(self._restore)

    def _restore(self):
        if self.saved is None:
            STATE.pop("rename_unverified", None)
        else:
            STATE["rename_unverified"] = self.saved

    # --- 1. «решение не принято»: флаг НЕ добавляется ---
    def test_undecided_state_adds_no_flag(self):
        """STATE=None — панель ещё не прислала решение. Подставлять True здесь
        нельзя: ядро само возьмёт свой strict, и это безопасный исход."""
        STATE["rename_unverified"] = None
        self.assertNotIn("allow_unverified", main._with_rename_policy(_action()))

    def test_absent_key_adds_no_flag(self):
        """Ключа нет вовсе — тот же «пользователь не решал»."""
        STATE.pop("rename_unverified", None)
        self.assertNotIn("allow_unverified", main._with_rename_policy(_action()))

    # --- 2. явные решения панели доезжают как есть ---
    def test_panel_true_enables_unverified(self):
        STATE["rename_unverified"] = True
        self.assertIs(main._with_rename_policy(
            _action())["allow_unverified"], True)

    def test_panel_false_disables_unverified(self):
        STATE["rename_unverified"] = False
        self.assertIs(main._with_rename_policy(
            _action())["allow_unverified"], False)

    # --- 3. мусорное значение не превращается в разрешение ---
    def test_non_bool_state_never_enables(self):
        """Раньше `is not False` превращал в True что угодно. Теперь значение,
        которому нельзя доверять, обязано вести к strict, а не к unsafe."""
        for junk in ("true", "да", 1, [], {}, "False"):
            with self.subTest(junk=junk):
                STATE["rename_unverified"] = junk
                self.assertNotIn(
                    "allow_unverified", main._with_rename_policy(_action()))

    # --- 4. явный флаг в действии не перетирается ---
    def test_explicit_flag_in_action_wins(self):
        for state, explicit in ((None, True), (None, False),
                                (True, False), (False, True)):
            with self.subTest(state=state, explicit=explicit):
                STATE["rename_unverified"] = state
                result = main._with_rename_policy(
                    _action(allow_unverified=explicit))
                self.assertIs(result["allow_unverified"], explicit)

class RenamePolicySource(unittest.TestCase):
    """Дефолт серверного состояния обязан быть None, а не True."""

    def setUp(self):
        with open(SERVER, "r", encoding="utf-8") as handle:
            self.source = handle.read()

    def test_server_default_is_undecided(self):
        """Литеральный дефолт True здесь и есть первопричина: он неотличим от
        «панель реально прислала True»."""
        self.assertRegex(self.source, r'"rename_unverified"\s*:\s*None')

    def test_server_default_is_not_true(self):
        self.assertNotRegex(self.source, r'"rename_unverified"\s*:\s*True')


class RenamePolicyIntake(unittest.TestCase):
    """Что сервер записывает, когда панель прислала значение (или мусор)."""

    def setUp(self):
        self.saved = STATE.get("rename_unverified")
        self.saved_root = STATE.get("project_root")
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in (("rename_unverified", self.saved),
                           ("project_root", self.saved_root)):
            if value is None:
                STATE.pop(key, None)
            else:
                STATE[key] = value

    def _apply(self, **data):
        import server_state
        from unittest.mock import patch
        # allow_rebind=True — тест повторно применяет контекст к тому же корню,
        # а обычный /chat такие повторы отклоняет (смена проекта вне /init).
        with patch.object(server_state, "_discover_trusted_agent_dir",
                          return_value=None, create=True):
            return server_state._apply_session_context(data, allow_rebind=True)

    def test_panel_bool_is_recorded(self):
        self._apply(project_root="C:/proj", rename_unverified=True)
        self.assertIs(STATE["rename_unverified"], True)
        self._apply(project_root="C:/proj", rename_unverified=False)
        self.assertIs(STATE["rename_unverified"], False)

    def test_panel_garbage_is_not_recorded_as_a_decision(self):
        """Мусор в поле не должен превращаться в «пользователь снял галочку»:
        это разные утверждения, и подменять одно другим нельзя."""
        for junk in ("false", 0, [], {}, 2):
            with self.subTest(junk=junk):
                self._apply(project_root="C:/proj", rename_unverified=junk)
                self.assertIsNone(STATE["rename_unverified"])


# __APPEND_POLICY_E2E__
class RenamePolicyEndToEnd(unittest.TestCase):
    """Что реально происходит с недоказанной ссылкой при каждом состоянии."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_policy_")
        self.store = tempfile.mkdtemp(prefix="rename_policy_store_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(shutil.rmtree, self.store, True)
        self.previous_store = _history_storage()
        self.addCleanup(self._restore_store)
        import history_manager
        history_manager._STORAGE_OVERRIDE = self.store
        for rel, text in (("project.godot", "config_version=5\n"),
                          ("src/player.gd", PLAYER),
                          ("src/typed.gd", TYPED),
                          ("src/arena.gd", UNPROVEN)):
            path = os.path.join(self.root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        ml_project_index._MEM_CACHE.clear()
        ml_project_index.build_index(self.root)
        self.saved_policy = STATE.get("rename_unverified")
        self.addCleanup(self._restore_policy)
        for key in ("pending_action", "pending_refactor", "pending_validation",
                    "pending_transaction", "pending_file_refactor",
                    "pending_node_refactor", "pending_plan"):
            STATE.pop(key, None)
        STATE.update({"project_root": self.root, "pending_action": None,
                      "pending_refactor": None, "pending_validation": None,
                      "addon_intent": False, "addon_dir": None,
                      "godot_executable": ""})
        for name in ("_remember", "_sync_chat_after_reply", "_refresh_fs_snapshot",
                     "_remember_file", "_touch_file_read"):
            setattr(main, name, lambda *_a, **_k: None)
        setattr(main, "_current_chat_info", lambda: ("c", "t"))
        setattr(main, "_reply_with_self_heal",
                lambda followup, root: (followup, None))

    def _restore_store(self):
        import history_manager
        if self.previous_store is not None:
            history_manager.set_storage_dir(self.previous_store)
        else:
            history_manager._STORAGE_OVERRIDE = None

    def _restore_policy(self):
        if self.saved_policy is None:
            STATE.pop("rename_unverified", None)
        else:
            STATE["rename_unverified"] = self.saved_policy

    def _read(self, rel):
        with open(os.path.join(self.root, *rel.split("/")), "r",
                  encoding="utf-8") as handle:
            return handle.read()

    def _package(self, action):
        with main.app.test_request_context("/chat", method="POST", json={}):
            response = main._package_model_reply(
                "Переименовываю.", action, self.root, allow_followup=False)
        if isinstance(response, tuple):
            return response[0].get_json(), response[1]
        return response.get_json(), response.status_code

    # --- ГЛАВНЫЙ ТЕСТ БАГА: панель не прислала решение ---
    def test_agent_without_panel_decision_refuses_unproven(self):
        """Никто не прислал решение -> агент обязан получить strict и отказ.
        Именно это «обещание» из комментария server_state.py и не выполнялось."""
        STATE["rename_unverified"] = None
        payload, status = self._package(_action())
        self.assertEqual(status, 200)
        self.assertIsNone(
            payload.get("pending_action"),
            "агент молча получил небезопасное переименование: %r"
            % (payload.get("pending_action"),))
        self.assertIn("rename_symbol", payload["answer"])
        self.assertIn("Player", self._read("src/player.gd"))
        self.assertIn("Player", self._read("src/arena.gd"))

    def test_missing_state_key_also_refuses_unproven(self):
        """Ключа нет — тот же «не решал»: безопасный исход."""
        STATE.pop("rename_unverified", None)
        payload, _status = self._package(_action())
        self.assertIsNone(payload.get("pending_action"))
        self.assertIn("Player", self._read("src/arena.gd"))

    # --- панель РЕАЛЬНО прислала решение ---
    def test_panel_true_allows_but_discloses(self):
        """Галочка стоит: переименование проходит, но недоказанные места
        ОБЯЗАНЫ быть названы — иначе это молчаливый ущерб."""
        STATE["rename_unverified"] = True
        payload, status = self._package(_action())
        self.assertEqual(status, 200)
        pending = payload.get("pending_action")
        self.assertIsNotNone(pending, payload.get("answer"))
        self.assertIs(pending.get("allow_unverified"), True)
        self.assertTrue(pending.get("unverified_references"))
        self.assertIn("без доказательства", payload["pending_action_description"])

    def test_panel_false_refuses_unproven(self):
        STATE["rename_unverified"] = False
        payload, _status = self._package(_action())
        self.assertIsNone(payload.get("pending_action"))

    # --- MCP-путь ядра: флага нет вовсе -> strict ---
    def test_core_without_flag_is_strict(self):
        """Сторонний клиент (MCP) флага не шлёт и обязан получить прежний
        strict. Регресс на комментарий ядра: дефолт безопасный."""
        with self.assertRaises(symbol_refactor.UnsafeRenameError):
            symbol_refactor.prepare_rename(self.root, _action())


if __name__ == "__main__":
    unittest.main()
# __APPEND_POLICY_E2E__
    # --- 5. чужие действия не трогаются ---
    def test_other_actions_are_untouched(self):
        STATE["rename_unverified"] = True
        action = {"action": "patch_file", "path": "res://a.gd"}
        self.assertIs(main._with_rename_policy(action), action)
        self.assertIs(main._with_rename_policy("не dict"), "не dict")


# __APPEND_POLICY_SOURCE__