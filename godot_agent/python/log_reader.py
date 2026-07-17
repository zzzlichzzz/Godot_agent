import os
import json
import re
import time

from project_tools import _resolve_safe_path

# ---------------------------------------------------------------------------
# Чтение лога последнего запуска игры (user://logs/godot.log).
#
# Надёжность и защита от УСТАРЕВШИХ ошибок:
#   - Godot сам держит файл «всегда новым»: текущая сессия пишется в
#     godot.log, прошлые сессии автоматически ротируются с таймстампом;
#   - отпечаток (mtime + размер) последнего ОТПРАВЛЕННОГО модели лога
#     хранится в log_state.json рядом с журналом истории — один и тот же
#     лог физически нельзя отправить дважды;
#   - время лога возвращается в панель, чтобы пользователь видел, какой
#     именно запуск он отправляет.
# ---------------------------------------------------------------------------

MAX_ERRORS = 15          # максимум уникальных ошибок в одном отчёте
CONTEXT_LINES = 5        # строк кода вокруг строки ошибки

_STATE_FILENAME = "log_state.json"

_ERROR_PREFIXES = ("SCRIPT ERROR:", "USER SCRIPT ERROR:", "ERROR:", "USER ERROR:")
_SKIP_PREFIXES = ("WARNING:", "USER WARNING:")

_LOCATION_RE = re.compile(r"at:\s*(?P<func>[^(]*)\((?P<file>[^:)]+):(?P<line>\d+)\)")
_INPUT_ACTION_RE = re.compile(r'^([A-Za-z0-9_\-. ]+?)\s*=\s*\{')


def _log_path(user_data_dir):
    return os.path.join(user_data_dir, "logs", "godot.log")


def _state_path(state_dir):
    return os.path.join(state_dir, _STATE_FILENAME)


def _load_sent_fingerprint(state_dir):
    try:
        with open(_state_path(state_dir), "r", encoding="utf-8") as f:
            return json.load(f).get("sent_fingerprint")
    except Exception:
        return None


def save_sent_fingerprint(state_dir, fingerprint):
    """Запоминаем отпечаток лога, который УЖЕ ушёл модели."""
    os.makedirs(state_dir, exist_ok=True)
    tmp = _state_path(state_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"sent_fingerprint": fingerprint}, f)
    os.replace(tmp, _state_path(state_dir))


def _code_context(project_root, res_path, line_no):
    """±CONTEXT_LINES строк реального кода С ДИСКА вокруг строки ошибки.
    Читается в момент отправки — контекст всегда актуальный."""
    try:
        abs_path = _resolve_safe_path(project_root, res_path)
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().split("\n")
    except Exception:
        return None
    lo = max(0, line_no - 1 - CONTEXT_LINES)
    hi = min(len(lines), line_no + CONTEXT_LINES)
    out = []
    for i in range(lo, hi):
        marker = ">>" if (i + 1) == line_no else "  "
        out.append("%s %4d: %s" % (marker, i + 1, lines[i]))
    return "\n".join(out)


def _list_input_actions(project_root):
    """Список пользовательских действий из секции [input] в project.godot.
    Локальное чтение текстового файла — никаких запросов и API.
    None — если project.godot прочитать не удалось."""
    try:
        path = _resolve_safe_path(project_root, "res://project.godot")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return None
    actions, in_input = [], False
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            in_input = (s == "[input]")
            continue
        if not in_input:
            continue
        m = _INPUT_ACTION_RE.match(s)
        if m:
            actions.append(m.group(1).strip())
    return actions


def collect_errors(user_data_dir, project_root, state_dir):
    """Возвращает (ok, result). При ok=False result — строка с причиной."""
    path = _log_path(user_data_dir)
    if not os.path.isfile(path):
        return False, ("Лог запуска не найден: %s. Запустите игру хотя бы один раз "
                       "(файловое логирование должно быть включено)." % path)
    st = os.stat(path)
    fingerprint = {"mtime": st.st_mtime, "size": st.st_size}
    already_sent = _load_sent_fingerprint(state_dir) == fingerprint

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")

    errors = {}   # (message, location) -> запись; дубль = +1 к счётчику
    order = []
    warnings_skipped = 0
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if line.startswith(_SKIP_PREFIXES):
            warnings_skipped += 1
            continue
        if not line.startswith(_ERROR_PREFIXES):
            continue
        message = line
        location, res_path, line_no = "", None, None
        # Строка "at: ..." обычно идёт следом за сообщением ошибки.
        if i < len(lines):
            m = _LOCATION_RE.search(lines[i])
            if m:
                location = lines[i].strip()
                file_path = m.group("file").strip()
                if file_path.startswith("res://"):
                    res_path = file_path
                    line_no = int(m.group("line"))
                i += 1
        key = (message, location)
        if key in errors:
            errors[key]["count"] += 1
            continue
        errors[key] = {
            "message": message,
            "location": location,
            "path": res_path,
            "line": line_no,
            "count": 1,
        }
        order.append(key)

    unique = [errors[k] for k in order]
    total_unique = len(unique)
    unique = unique[:MAX_ERRORS]
    for e in unique:
        if e["path"] and e["line"]:
            e["context"] = _code_context(project_root, e["path"], e["line"])

    # Если среди ошибок есть несуществующие InputMap-действия — прикладываем
    # список РЕАЛЬНО существующих действий, чтобы модель не гадала имена.
    input_actions = None
    if any("The InputMap action" in e["message"] for e in unique):
        input_actions = _list_input_actions(project_root)

    log_time = time.strftime("%H:%M:%S", time.localtime(st.st_mtime))
    age_minutes = max(0, int((time.time() - st.st_mtime) / 60))
    return True, {
        "errors": unique,
        "total_unique": total_unique,
        "warnings_skipped": warnings_skipped,
        "log_time": log_time,
        "age_minutes": age_minutes,
        "fingerprint": fingerprint,
        "already_sent": already_sent,
        "input_actions": input_actions,
    }


def build_summary(report):
    """Краткая сводка для панели Godot — пользователь решает, слать ли модели."""
    parts = []
    for idx, e in enumerate(report["errors"], 1):
        loc = " — %s:%s" % (e["path"], e["line"]) if e["path"] else ""
        rep = " (повторов: %d)" % e["count"] if e["count"] > 1 else ""
        parts.append("%d) %s%s%s" % (idx, e["message"], loc, rep))
    if report["total_unique"] > len(report["errors"]):
        parts.append("... и ещё %d (обрезано)" % (report["total_unique"] - len(report["errors"])))
    return "\n".join(parts)


def format_report(report):
    """Полное сообщение для модели с контекстом кода."""
    fence = "`" * 3
    n = len(report["errors"])
    parts = [
        "[Система: Ошибки последнего запуска игры (лог от %s). Уникальных ошибок: %d." % (report["log_time"], n),
        "Исправляй ПО ОДНОЙ, начиная с первой — остальные часто являются её следствием.",
    ]
    for idx, e in enumerate(report["errors"], 1):
        block = "Ошибка %d/%d: %s" % (idx, n, e["message"])
        if e["location"]:
            block += "\n%s" % e["location"]
        if e["count"] > 1:
            block += "\n(повторилась %d раз — считай одной проблемой)" % e["count"]
        if e.get("context"):
            block += ("\nАктуальный код вокруг (строка ошибки помечена >>):\n"
                      "%s\n%s\n%s" % (fence, e["context"], fence))
        parts.append(block)
    if report["total_unique"] > n:
        parts.append("Ещё %d ошибок обрезано — после исправления этих пользователь пришлёт новый лог." % (report["total_unique"] - n))
    acts = report.get("input_actions")
    if acts is not None:
        if acts:
            listing = ", ".join('"%s"' % a for a in acts)
            parts.append(
                "СПРАВКА InputMap: в project.godot (секция [input]) существуют ТОЛЬКО эти действия: "
                + listing + " (плюс встроенные ui_* самого Godot). НЕ придумывай имена действий: "
                "либо используй имя из этого списка, либо предложи patch_file для res://project.godot, "
                "добавляющий недостающее действие в секцию [input].")
        else:
            parts.append(
                "СПРАВКА InputMap: в project.godot НЕТ пользовательских действий (секция [input] пуста "
                "или отсутствует; есть только встроенные ui_* самого Godot). Чтобы такие ошибки "
                "исчезли, предложи patch_file для res://project.godot, добавляющий нужные действия "
                "в секцию [input], или объясни пользователю, как создать их в Project Settings → Input Map. "
                "ВАЖНО: секции [input] в файле скорее всего НЕТ вообще — НЕ используй '[input]' в 'search'. "
                "Добавь СРАЗУ ВСЕ недостающие действия ОДНИМ патчем: возьми в 'search' реально "
                "существующую секцию файла и в 'replace' поставь блок [input] перед ней. "
                "Если содержимое project.godot тебе неизвестно — сначала запроси его через read_file.")
    parts.append("Приложенные фрагменты кода — АКТУАЛЬНОЕ содержимое файлов с диска (равнозначно read_file).]")
    return "\n\n".join(parts)
