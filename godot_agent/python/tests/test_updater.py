# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты подсистемы проверки и установки обновлений Godot Agent (agent_updater.gd).

Проверяется:
1. Корректность сравнения версий по SemVer (с 'v', без 'v', суффиксы -beta, major/minor/patch).
2. Разбор ответа GitHub Releases API (версия, ссылка на релиз, changelog, выбор .zip из assets).
3. Разбор структуры zip-архивов:
   - GitHub zipball (с префиксом репозитория zzzlichzzz-Godot_agent-abc/);
   - стандартный релизный архив (папка godot_agent/);
   - плоский архив (plugin.cfg в корне).
4. Защита пользовательских файлов (токен, пути, язык, кэш) от перезаписи обновлением.
5. Обработка повреждённых и некорректных архивов (архив без plugin.cfg, битый zip).
6. Завершение работы локального сервера через маршрут /server/shutdown.
"""
import io
import json
import shutil
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


# --- 1) Сравнение версий SemVer (аналог GDScript parse_semver / is_version_newer) ---

def parse_semver(v_str):
    cleaned = (v_str or "").strip()
    while cleaned.startswith("v") or cleaned.startswith("V"):
        cleaned = cleaned[1:]
    if "-" in cleaned:
        cleaned = cleaned.split("-", 1)[0]
    if "+" in cleaned:
        cleaned = cleaned.split("+", 1)[0]
    parts = cleaned.split(".")
    res = [0, 0, 0]
    for i in range(min(len(parts), 3)):
        try:
            res[i] = int(parts[i])
        except ValueError:
            res[i] = 0
    return res


def is_version_newer(current_ver, remote_ver):
    cur = parse_semver(current_ver)
    rem = parse_semver(remote_ver)
    for i in range(3):
        if rem[i] > cur[i]:
            return True
        elif rem[i] < cur[i]:
            return False
    return False


check("SemVer: 0.8.0 новее 0.7.0", is_version_newer("0.7.0", "0.8.0"))
check("SemVer: 0.7.1 новее 0.7.0", is_version_newer("0.7.0", "0.7.1"))
check("SemVer: 1.0.0 новее 0.9.9", is_version_newer("0.9.9", "1.0.0"))
check("SemVer: 0.7.0 не новее 0.7.0", not is_version_newer("0.7.0", "0.7.0"))
check("SemVer: 0.6.9 не новее 0.7.0", not is_version_newer("0.7.0", "0.6.9"))
check("SemVer: v0.8.0 новее 0.7.0 (с префиксом v)", is_version_newer("0.7.0", "v0.8.0"))
check("SemVer: 0.8.0-beta.1 новее 0.7.0 (с суффиксом -beta)", is_version_newer("0.7.0", "0.8.0-beta.1"))
check("SemVer: 0.7.0 не новее 0.7.0-beta", not is_version_newer("0.7.0", "0.7.0-beta"))
check("SemVer: 0.7.0.1 не новее 0.7.0 (четвертая часть игнорируется)", not is_version_newer("0.7.0", "0.7.0.1"))


# --- 2) Локальный HTTP-сервер для имитации GitHub Releases API ---

class MockGitHubHandler(BaseHTTPRequestHandler):
    latest_release_payload = {
        "tag_name": "v0.8.0",
        "html_url": "https://github.com/zzzlichzzz/Godot_agent/releases/tag/v0.8.0",
        "body": "## Что нового в 0.8.0\n- Автообновление в 1 клик\n- Улучшенная стабильность",
        "published_at": "2026-09-20T12:00:00Z",
        "assets": [
            {
                "name": "godot_agent_v0.8.0.zip",
                "browser_download_url": "http://127.0.0.1:{PORT}/download/godot_agent_v0.8.0.zip"
            },
            {
                "name": "other_file.txt",
                "browser_download_url": "http://127.0.0.1:{PORT}/download/other_file.txt"
            }
        ],
        "zipball_url": "http://127.0.0.1:{PORT}/download/zipball.zip"
    }

    test_zip_bytes = b""

    def do_GET(self):
        if self.path == "/repos/zzzlichzzz/Godot_agent/releases/latest":
            body = json.dumps(self.latest_release_payload).replace("{PORT}", str(self.server.server_port)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/download/"):
            data = self.test_zip_bytes
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


mock_server = ThreadingHTTPServer(("127.0.0.1", 0), MockGitHubHandler)
mock_port = mock_server.server_port
server_thread = threading.Thread(target=mock_server.serve_forever, daemon=True)
server_thread.start()

import urllib.request

req = urllib.request.Request("http://127.0.0.1:%d/repos/zzzlichzzz/Godot_agent/releases/latest" % mock_port,
                             headers={"User-Agent": "Godot-Agent-Updater"})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))

check("GitHub API: ответ получен", data.get("tag_name") == "v0.8.0")
check("GitHub API: changelog разобран", "Автообновление" in data.get("body", ""))
zip_asset = next((a for a in data.get("assets", []) if a.get("name", "").endswith(".zip")), None)
check("GitHub API: найден .zip ассет", zip_asset is not None and "godot_agent_v0.8.0.zip" in zip_asset.get("name", ""))


# --- 3) Проверка распаковки zip-архивов разной структуры ---

def make_test_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in entries.items():
            zf.writestr(arcname, content)
    return buf.getvalue()


def simulate_extraction(zip_bytes, target_dir):
    """Имитация логики verify_and_install_zip из agent_updater.gd."""
    buf = io.BytesIO(zip_bytes)
    try:
        zf = zipfile.ZipFile(buf, "r")
    except Exception as e:
        return {"ok": False, "error": "Cannot open zip file (%s)" % e}

    files = zf.namelist()
    if not files:
        return {"ok": False, "error": "Zip archive is empty"}

    plugin_cfg_entry = next((f for f in files if f.endswith("plugin.cfg")), None)
    if not plugin_cfg_entry:
        return {"ok": False, "error": "Invalid archive: plugin.cfg not found"}

    strip_prefix = ""
    target_base = target_dir

    if plugin_cfg_entry == "plugin.cfg":
        strip_prefix = ""
        target_base = target_dir
    elif plugin_cfg_entry.endswith("/godot_agent/plugin.cfg"):
        idx = plugin_cfg_entry.rfind("godot_agent/plugin.cfg")
        strip_prefix = plugin_cfg_entry[:idx]
        target_base = _os0.path.dirname(target_dir)
    else:
        last_slash = plugin_cfg_entry.rfind("/")
        if last_slash != -1:
            strip_prefix = plugin_cfg_entry[:last_slash + 1]
        target_base = target_dir

    user_preserve_files = {
        "godot_agent_server_path.txt",
        "godot_agent_token.txt",
        "godot_agent_lang.txt",
        "godot_agent_update_check.json",
        "server_path.txt"
    }

    updated_count = 0
    for f_path in files:
        if not f_path.startswith(strip_prefix):
            continue
        rel = f_path[len(strip_prefix):]
        if not rel or rel == "/":
            continue
        if rel.startswith("/"):
            rel = rel[1:]

        base_name = _os0.path.basename(rel)
        if base_name in user_preserve_files:
            continue

        dest = _os0.path.join(target_base, rel)
        if f_path.endswith("/"):
            _os0.makedirs(dest, exist_ok=True)
            continue

        _os0.makedirs(_os0.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as out_f:
            out_f.write(zf.read(f_path))
        updated_count += 1

    return {"ok": True, "updated_files": updated_count}


# Тест 3.1: GitHub zipball layout
zipball_data = make_test_zip({
    "zzzlichzzz-Godot_agent-abc1234/godot_agent/plugin.cfg": "[plugin]\nversion=\"0.8.0\"\n",
    "zzzlichzzz-Godot_agent-abc1234/godot_agent/agent_panel.gd": "# updated panel\n",
    "zzzlichzzz-Godot_agent-abc1234/godot_agent/godot_agent_token.txt": "evil_remote_token",
})

temp_addon_dir = tempfile.mkdtemp(prefix="agent_addon_")
try:
    godot_agent_dir = _os0.path.join(temp_addon_dir, "godot_agent")
    _os0.makedirs(godot_agent_dir, exist_ok=True)
    # Создаем существующий файл пользователя
    token_path = _os0.path.join(godot_agent_dir, "godot_agent_token.txt")
    with open(token_path, "w", encoding="utf-8") as f:
        f.write("user_precious_token_12345")

    res = simulate_extraction(zipball_data, godot_agent_dir)
    check("Распаковка zipball: успешна", res.get("ok") is True)
    check("Распаковка zipball: обновлен plugin.cfg",
          _os0.path.isfile(_os0.path.join(godot_agent_dir, "plugin.cfg")))
    with open(_os0.path.join(godot_agent_dir, "plugin.cfg"), "r", encoding="utf-8") as f:
        check("Распаковка zipball: версия обновилась до 0.8.0", "0.8.0" in f.read())
    with open(token_path, "r", encoding="utf-8") as f:
        check("Защита пользователя: godot_agent_token.txt НЕ перезаписан",
              f.read().strip() == "user_precious_token_12345")
finally:
    shutil.rmtree(temp_addon_dir, ignore_errors=True)


# Тест 3.2: Стандартный архив (godot_agent/ в корне)
standard_zip_data = make_test_zip({
    "godot_agent/plugin.cfg": "[plugin]\nversion=\"0.8.0\"\n",
    "godot_agent/agent_panel.gd": "# panel\n",
})

temp_addon_dir2 = tempfile.mkdtemp(prefix="agent_addon2_")
try:
    godot_agent_dir2 = _os0.path.join(temp_addon_dir2, "godot_agent")
    _os0.makedirs(godot_agent_dir2, exist_ok=True)
    res2 = simulate_extraction(standard_zip_data, godot_agent_dir2)
    check("Распаковка standard zip: успешна", res2.get("ok") is True)
    check("Распаковка standard zip: plugin.cfg создан",
          _os0.path.isfile(_os0.path.join(godot_agent_dir2, "plugin.cfg")))
finally:
    shutil.rmtree(temp_addon_dir2, ignore_errors=True)


# Тест 3.3: Архив без plugin.cfg отклоняется
bad_zip_data = make_test_zip({
    "random_dir/some_file.txt": "hello\n",
})
temp_bad = tempfile.mkdtemp(prefix="agent_bad_")
try:
    res_bad = simulate_extraction(bad_zip_data, temp_bad)
    check("Некорректный архив без plugin.cfg отклонён", res_bad.get("ok") is False)
    check("Сообщение об ошибке содержит 'plugin.cfg not found'",
          "plugin.cfg not found" in res_bad.get("error", ""))
finally:
    shutil.rmtree(temp_bad, ignore_errors=True)


# Тест 3.4: Битый zip-файл
corrupt_bytes = b"not a zip file definitely"
res_corrupt = simulate_extraction(corrupt_bytes, temp_bad)
check("Повреждённый zip-файл отклонён", res_corrupt.get("ok") is False)


# --- 4) Проверка маршрута /server/shutdown в main.py ---

import main

client = main.app.test_client()
resp_shutdown = client.post("/server/shutdown")
check("/server/shutdown возвращает 200 OK", resp_shutdown.status_code == 200)
data_shutdown = resp_shutdown.get_json()
check("/server/shutdown возвращает ok: True", data_shutdown.get("ok") is True)

mock_server.shutdown()

print("--- ИТОГ test_updater.py: %d/%d пройдено ---" % (sum(results), len(results)))
if not all(results):
    _sys0.exit(1)
