# -*- coding: utf-8 -*-
"""Step-4 audit regression checks for the editor-side GDScript (agent_panel.gd).

Без запуска Godot здесь возможны только статические проверки исходников —
по образцу test_gdscript_wiring.py. Полная верификация поведения (закрытие
вкладок, UID после сканирования) делается вручную в редакторе.
"""
import os as _os0
import sys as _sys0
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(
    _os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401

import re
import sys

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail:
        print("     %s" % (detail,))
    results.append(bool(cond))


ADDON = _os0.path.abspath(_os0.path.join(
    _os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir, _os0.pardir))
PANEL = _os0.path.join(ADDON, "agent_panel.gd")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def func_src(src, func_name):
    """Исходник одной функции верхнего уровня (до следующего 'func ')."""
    m = re.search(r"^func\s+%s\s*\(" % re.escape(func_name), src, re.MULTILINE)
    if not m:
        return ""
    nxt = re.search(r"^func\s+", src[m.end():], re.MULTILINE)
    end = m.end() + nxt.start() if nxt else len(src)
    return src[m.start():end]


panel = read(PANEL)
hfm = func_src(panel, "handle_filesystem_move")
sync_uid = func_src(panel, "_sync_resource_uid")

# --- audit 4.3: нормализация путей через localize_path ----------------------
check("handle_filesystem_move нормализует пути через ProjectSettings.localize_path",
      "ProjectSettings.localize_path" in hfm)
check("handle_filesystem_move больше не порождает res://D:/... через trim_prefix",
      'trim_prefix("/")' not in hfm)

# --- audit 3.1: UID через штатный API ---------------------------------------
check("_sync_resource_uid использует ResourceLoader.get_resource_uid",
      "ResourceLoader.get_resource_uid" in sync_uid)
check("_sync_resource_uid больше не парсит первую строку файла",
      "get_line()" not in sync_uid)
check("_sync_resource_uid рекурсивно обходит папки",
      "DirAccess" in sync_uid and "_sync_resource_uid(" in sync_uid.replace(
          "func _sync_resource_uid", ""))
check("_sync_resource_uid объявляет old_path как неиспользуемый (_old_path)",
      "func _sync_resource_uid(_old_path" in panel)

# --- audit 3.2: зомби-вкладки даже без внешних ссылок ------------------------
check("есть хелпер закрытия вкладок перемещения с префиксом для папок",
      "func _close_ghost_script_tabs_for_move" in panel
      and "begins_with(prefix)" in panel)
check("старый точечный вызов _close_ghost_script_tab(clean_old) удалён",
      "_close_ghost_script_tab(clean_old)" not in panel)
check("новый хелпер вызывается с признаком папки",
      "_close_ghost_script_tabs_for_move(clean_old, is_folder)" in panel)

# --- audit 1.4 (GDScript-сторона): очередь вместо шквала запросов ------------
check("есть очередь post_move_sync-запросов",
      "_fs_move_queue" in panel and "func _process_fs_move_queue" in panel)
check("handle_filesystem_move ставит событие в очередь, а не шлёт сразу",
      "_fs_move_queue.append(" in hfm and "_process_fs_move_queue()" in hfm)
check("отправка выделена в _send_post_move_sync",
      "func _send_post_move_sync" in panel
      and "REFACTOR_FILE_POST_MOVE_SYNC_URL" in func_src(panel, "_send_post_move_sync"))
check("прямая отправка из handle_filesystem_move удалена",
      "REFACTOR_FILE_POST_MOVE_SYNC_URL" not in hfm)
check("busy-флаг снимается по завершении запроса",
      "_fs_move_busy = false" in func_src(panel, "_send_post_move_sync"))

# --- audit 3.4: предупреждение о project.godot -------------------------------
check("предупреждение о нечитаемом в памяти project.godot",
      "project.godot" in panel[panel.find("func _send_post_move_sync"):
                                panel.find("func _on_safe_node_rename_pressed")])

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)

