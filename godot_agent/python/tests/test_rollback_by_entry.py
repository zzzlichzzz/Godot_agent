# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты АДРЕСНОГО отката (по id записи журнала).

Что было сломано. Кнопка отката на карточке сообщения не несла никакого
адреса: ни карточка, ни панель, ни запрос к серверу не указывали, ЧТО
откатывать. Сервер всегда откатывал `committed[-1]` — самое свежее изменение
в журнале, который к тому же общий на весь проект. Отсюда обе жалобы:
  * клик по одному облачку откатывал не его, а последнее изменение (а если
    последним был шаг плана — панель молча расширяла откат до ВСЕЙ цепочки);
  * облачко без действий тоже имело работающую кнопку и откатывало чужое.

Здесь проверяется новая механика: `entry_info` / `rollback_entry`, отказ
откатывать через более свежие правки того же файла, и отсутствие расширения
до цепочки при адресном откате.
"""
import shutil
import sys
import tempfile

import history_manager as H

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


PROJ = tempfile.mkdtemp(prefix="agent_rb_proj_")
STORE = tempfile.mkdtemp(prefix="agent_rb_store_")
H.set_storage_dir(STORE)


def write(rel, text):
    p = _os0.path.join(PROJ, rel.replace("res://", "").replace("/", _os0.sep))
    _os0.makedirs(_os0.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def read(rel):
    p = _os0.path.join(PROJ, rel.replace("res://", "").replace("/", _os0.sep))
    if not _os0.path.isfile(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def apply_patch(rel, search, replace, chat_id="c1", chat_title="Чат 1",
                chain_id=None):
    """Полный путь «как в main._apply_write_step»: запись в журнал, правка
    файла, фиксация. Возвращает entry_id."""
    action = {"action": "patch_file", "path": rel,
              "search": search, "replace": replace}
    eid = H.record_change(PROJ, action, chat_id, chat_title, chain_id=chain_id)
    cur = read(rel)
    write(rel, cur.replace(search, replace, 1))
    H.commit_change(PROJ, eid)
    return eid


def apply_create(rel, content, chat_id="c1", chat_title="Чат 1", chain_id=None):
    action = {"action": "create_file", "path": rel, "content": content}
    eid = H.record_change(PROJ, action, chat_id, chat_title, chain_id=chain_id)
    write(rel, content)
    H.commit_change(PROJ, eid)
    return eid


# ---------------------------------------------------------------------------
# 1) Адресный откат отменяет ИМЕННО своё изменение
# ---------------------------------------------------------------------------
write("res://a.gd", u"var a := 1\n")
write("res://b.gd", u"var b := 1\n")
e_a = apply_patch("res://a.gd", u"var a := 1", u"var a := 2")
e_b = apply_patch("res://b.gd", u"var b := 1", u"var b := 2")

check(u"оба изменения применены",
      read("res://a.gd").strip() == u"var a := 2"
      and read("res://b.gd").strip() == u"var b := 2")
check(u"у записей журнала есть id", bool(e_a) and bool(e_b) and e_a != e_b)

info_a = H.entry_info(PROJ, e_a)
check(u"предпросмотр находит НУЖНУЮ запись, а не последнюю",
      info_a and info_a["path"] == "res://a.gd", info_a)
check(u"видно, что запись не самая свежая", info_a["is_last"] is False)
check(u"чат-источник сохранён", info_a["chat_title"] == u"Чат 1")

# Откатываем ПЕРВОЕ изменение (не последнее) — файлы разные, мешать нечему.
ok, msg, needs_force, paths, diff = H.rollback_entry(PROJ, e_a)
check(u"адресный откат прошёл", ok, msg)
check(u"откачен именно a.gd", read("res://a.gd").strip() == u"var a := 1")
check(u"b.gd НЕ тронут (раньше откатилось бы именно оно)",
      read("res://b.gd").strip() == u"var b := 2")
check(u"обратный дифф отдан панели",
      diff and diff["path"] == "res://a.gd", diff)
check(u"затронутый путь сообщён", paths == ["res://a.gd"], paths)

# ---------------------------------------------------------------------------
# 2) Повторный откат той же записи невозможен
# ---------------------------------------------------------------------------
ok2, msg2, _nf, _p, _d = H.rollback_entry(PROJ, e_a)
check(u"второй откат той же записи отклонён", not ok2)
check(u"сказано, что запись уже откачена", u"уже откачено" in msg2.lower()
      or u"не найдено" in msg2.lower(), msg2)
check(u"предпросмотр удалённой записи -> None", H.entry_info(PROJ, e_a) is None)
check(u"b.gd по-прежнему не тронут", read("res://b.gd").strip() == u"var b := 2")

# ---------------------------------------------------------------------------
# 3) Откат ЧЕРЕЗ более свежие правки того же файла запрещён
# ---------------------------------------------------------------------------
e_b2 = apply_patch("res://b.gd", u"var b := 2", u"var b := 3")
info_b = H.entry_info(PROJ, e_b)
check(u"предпросмотр видит более свежие правки того же файла",
      len(info_b.get("newer_same_file") or []) == 1, info_b)

ok3, msg3, nf3, _p, _d = H.rollback_entry(PROJ, e_b)
check(u"откат через более свежую правку отклонён", not ok3)
check(u"причина объяснена по-человечески",
      u"правил ещё" in msg3 and u"от новых" in msg3, msg3)
check(u"это НЕ предложение нажать ещё раз (force не поможет)", nf3 is False)
check(u"файл не тронут", read("res://b.gd").strip() == u"var b := 3")

ok3f, _m, _nf, _p, _d = H.rollback_entry(PROJ, e_b, force=True)
check(u"даже force не разрешает потерять более свежую работу агента", not ok3f)
check(u"файл всё ещё не тронут", read("res://b.gd").strip() == u"var b := 3")

# А в правильном порядке — от новых к старым — всё работает.
okn, _m, _nf, _p, _d = H.rollback_entry(PROJ, e_b2)
check(u"сначала свежая правка откатывается", okn
      and read("res://b.gd").strip() == u"var b := 2")
oko, _m, _nf, _p, _d = H.rollback_entry(PROJ, e_b)
check(u"теперь и старая откатывается", oko
      and read("res://b.gd").strip() == u"var b := 1")

# ---------------------------------------------------------------------------
# 4) Внешняя правка файла: force по-прежнему уместен
# ---------------------------------------------------------------------------
e_c = apply_create("res://c.gd", u"extends Node\n")
write("res://c.gd", u"extends Node\n# правка руками\n")
okx, msgx, nfx, _p, _d = H.rollback_entry(PROJ, e_c)
check(u"внешняя правка -> откат просит подтверждения", not okx and nfx is True,
      (okx, nfx, msgx))
check(u"файл пока на месте", read("res://c.gd") is not None)
okf, _m, _nf, _p, _d = H.rollback_entry(PROJ, e_c, force=True)
check(u"с подтверждением откат проходит", okf)
check(u"созданный файл удалён", read("res://c.gd") is None)

# ---------------------------------------------------------------------------
# 5) Шаг плана: адресный откат отменяет ОДИН шаг, а не всю цепочку
# ---------------------------------------------------------------------------
chain = H.new_chain_id()
write("res://p1.gd", u"var x := 1\n")
write("res://p2.gd", u"var y := 1\n")
s1 = apply_patch("res://p1.gd", u"var x := 1", u"var x := 2", chain_id=chain)
s2 = apply_patch("res://p2.gd", u"var y := 1", u"var y := 2", chain_id=chain)

info_s2 = H.entry_info(PROJ, s2)
check(u"предпросмотр шага сообщает про цепочку",
      info_s2["chain_id"] == chain and info_s2["chain_total"] == 2, info_s2)

oks, _m, _nf, _p, _d = H.rollback_entry(PROJ, s2)
check(u"откачен ТОЛЬКО указанный шаг", oks
      and read("res://p2.gd").strip() == u"var y := 2".replace(":= 2", ":= 1"))
check(u"первый шаг плана остался применённым",
      read("res://p1.gd").strip() == u"var x := 2")
check(u"в журнале остался второй шаг цепочки",
      H.entry_info(PROJ, s1) is not None)

# Откат цепочки по-прежнему доступен отдельной операцией.
okc, msgc, _nf, pathsc, rev, tot = H.rollback_chain(PROJ, chain)
check(u"откат цепочки работает как раньше", okc, msgc)
check(u"откатан оставшийся шаг", rev == 1 and tot == 1, (rev, tot))
check(u"файл первого шага вернулся", read("res://p1.gd").strip() == u"var x := 1")

# ---------------------------------------------------------------------------
# 6) Неизвестный id не роняет сервер
# ---------------------------------------------------------------------------
check(u"предпросмотр неизвестного id -> None",
      H.entry_info(PROJ, "deadbeefcafe") is None)
okz, msgz, _nf, _p, _d = H.rollback_entry(PROJ, "deadbeefcafe")
check(u"откат неизвестного id -> понятный отказ", not okz and len(msgz) > 10, msgz)
check(u"пустой id -> отказ", not H.rollback_entry(PROJ, "")[0])

# ---------------------------------------------------------------------------
# 7) Прежнее поведение «откатить последнее» не сломано
# ---------------------------------------------------------------------------
write("res://z.gd", u"var z := 1\n")
apply_patch("res://z.gd", u"var z := 1", u"var z := 2")
info_last = H.last_committed_info(PROJ)
check(u"last_committed_info по-прежнему отдаёт последнее",
      info_last and info_last["path"] == "res://z.gd", info_last)
check(u"и теперь тоже несёт id записи", bool(info_last.get("id")))
okl, _m, _nf, _p, _d = H.rollback_last(PROJ)
check(u"rollback_last работает", okl and read("res://z.gd").strip() == u"var z := 1")

for d in (PROJ, STORE):
    shutil.rmtree(d, ignore_errors=True)
n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
