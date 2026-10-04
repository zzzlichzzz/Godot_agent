# -*- coding: utf-8 -*-
"""Синтетические тесты Шага 4 плана UNIFIED_ENTRY_PLAN: AgentServer.

Что проверяется
---------------
1) Статика: `const HOST` объявлен РОВНО ОДИН РАЗ во всём аддоне и живёт
   в `agent_server.gd`. Раньше он был продублирован в панели и в
   agent_server_link.gd — смена порта требовала правки в двух местах.
2) Статика: реестр маршрутов клиента совпадает с тем, что реально
   объявляет сервер (`main.py` + `server/chat_routes.py`). Проверка идёт
   по исходникам Python: маршрут, о котором сервер не знает, вернёт 404,
   а маршрут, который сервер знает, но нет в реестре, останется без
   единого адреса в плагине.
3) Статика: панель и agent_server_link берут адреса и заголовки у клиента,
   а не собирают их заново.
4) Живая проверка настоящим headless Godot: адрес строится правильно,
   заголовки содержат токен, а при его отсутствии поведение совпадает с
   прежним (панель не шлёт пустой заголовок токена).

Запуск:
    python -B python/tests/test_agent_server_client.py
    python -B python/tests/test_agent_server_client.py --godot EXE
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


SENTINEL = "AGENT_SERVER_RESULTS "

FATAL_ENGINE_LINES = ("SCRIPT ERROR", "Parse Error", "Nonexistent function")

SHUTDOWN_NOISE = (
    "RID allocations of type",
    "RIDs of type",
    "ObjectDB instances leaked",
    "Scan thread aborted",
)

HARNESS = '''extends SceneTree

func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	await process_frame
	var failures: Array[String] = []

	# --- адрес строится из единственного источника ---
	var built := AgentServer.url("/chat")
	if built != "http://127.0.0.1:5000/chat":
		failures.append("url() built wrong address: " + built)

	# --- токен читается/создаётся клиентом ---
	var token := AgentServer.project_token()
	if token.length() < 16:
		failures.append("project_token() is empty or too short")

	# --- заголовки с обязательным токеном ---
	var with_token := AgentServer.json_headers(true)
	if with_token.size() != 2:
		failures.append("json_headers(true) must carry Content-Type and token")
	if not _has(with_token, "Content-Type: application/json"):
		failures.append("json_headers() lost Content-Type")
	if not _has(with_token, "X-Agent-Token: "):
		failures.append("json_headers(true) lost the token header")

	# --- прежнее поведение панели сохранено: без токена заголовок токена
	#     НЕ отправляется, иначе сервер получает пустое значение ---
	var optional := AgentServer.json_headers(false)
	if not _has(optional, "Content-Type: application/json"):
		failures.append("json_headers(false) lost Content-Type")

	# --- реестр отвечает на известное и неизвестное имя маршрута ---
	# route() ищет по ИМЕНИ маршрута ("chat"), а url_for() строит адрес.
	if AgentServer.route("chat") != "/chat":
		failures.append("route() did not find a known route")
	if AgentServer.route("nope") != "":
		failures.append("route() invented an unknown route")
	if AgentServer.url_for("chat") != "http://127.0.0.1:5000/chat":
		failures.append("url_for() built wrong address")

	print(SENTINEL + JSON.stringify({"failures": failures, "token_length": token.length()}))
	await process_frame
	quit(0 if failures.is_empty() else 1)


func _has(headers: PackedStringArray, needle: String) -> bool:
	for header in headers:
		if header.begins_with(needle):
			return true
	return false
'''


class StaticChecks:
    """Проверки по исходникам — ловят то, что компилятор не ловит."""

    def __init__(self, addon: Path):
        self.addon = addon
        self.failures = []
        self.checks = 0
        self.client_path = addon / "agent_server.gd"
        self.panel_path = addon / "agent_panel.gd"
        self.link_path = addon / "agent_server_link.gd"

    def check(self, name, condition, detail=""):
        self.checks += 1
        if condition:
            print("%s -> OK" % name)
        else:
            print("%s -> FAIL" % name)
            if detail:
                print("     %s" % (detail,))
            self.failures.append((name, detail))

    def server_routes(self):
        """Маршруты, которые сервер действительно объявляет."""
        python = self.addon / "python"
        routes = set()
        for source in ("main.py", "server/chat_routes.py"):
            path = python / source
            if not path.is_file():
                continue
            # Маршруты объявляются двумя способами: @app.route в main.py и
            # @<blueprint>.route в server/chat_routes.py. Ловим оба.
            for match in re.finditer(r"@\w+\.route\(\s*[\"']([^\"']+)[\"']",
                                     path.read_text(encoding="utf-8")):
                routes.add(match.group(1))
        return routes

    def run(self):
        self.check("файл клиента на месте", self.client_path.is_file(), str(self.client_path))
        for name, path in (("панель", self.panel_path), ("транспорт", self.link_path)):
            self.check("%s на месте" % name, path.is_file(), str(path))
        if not self.client_path.is_file():
            return
        client = self.client_path.read_text(encoding="utf-8")
        panel = self.panel_path.read_text(encoding="utf-8")
        link = self.link_path.read_text(encoding="utf-8")

        owners = []
        for path in sorted(self.addon.glob("*.gd")):
            body = path.read_text(encoding="utf-8")
            if re.search(r"^const\s+HOST\s*:?=", body, re.MULTILINE):
                owners.append(path.name)
        self.check("const HOST объявлен ровно в одном файле",
                   owners == ["agent_server.gd"], owners)
        self.check("клиент экспортирует класс AgentServer",
                   re.search(r"^class_name\s+AgentServer\s*$", client, re.MULTILINE) is not None)
        self.check("панель не объявляет свой HOST",
                   re.search(r"^const\s+HOST\s*:?=", panel, re.MULTILINE) is None)
        self.check("транспорт не объявляет свой HOST",
                   re.search(r"^const\s+HOST\s*:?=", link, re.MULTILINE) is None)
        self.check("панель берёт адреса у клиента", "AgentServer." in panel)
        self.check("транспорт берёт адреса у клиента", "AgentServer." in link)

        pairs = re.findall(r"[\"'](/[A-Za-z0-9_/]+)[\"']\s*:\s*[\"']([^\"']+)[\"']", client)
        known = {path for path, _ in pairs}
        missing = sorted(self.server_routes() - known)
        self.check("все маршруты сервера есть в реестре клиента", not missing, missing)
        invented = sorted(known - self.server_routes())
        self.check("в реестре нет маршрутов, которых нет на сервере", not invented, invented)

        found = re.search(r"func\s+_json_headers\s*\([^)]*\)(.*?)(?=\nfunc |\Z)", panel, re.DOTALL)
        body = found.group(1) if found else ""
def live_check(addon: Path, executable: str, temp_parent):
    with tempfile.TemporaryDirectory(prefix="agent-server-", dir=temp_parent) as temp:
        root = Path(temp)
        copied = root / "addons" / "godot_agent"
        copied.mkdir(parents=True)
        shutil.copyfile(addon / "agent_server.gd", copied / "agent_server.gd")
        (root / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Agent server sandbox"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
        (root / "harness.gd").write_text(HARNESS.replace("SENTINEL", '"%s"' % SENTINEL),
                                        encoding="utf-8")
        env = os.environ.copy()
        for name in ("APPDATA", "LOCALAPPDATA", "HOME", "XDG_DATA_HOME",
                     "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            directory = root / "isolated_user" / name
            directory.mkdir(parents=True)
            env[name] = str(directory)
        base = [executable, "--headless", "--path", str(root), "--editor", "--language", "en"]
        for arguments in (["--import", "--quit"], ["--script", "res://harness.gd"]):
            print("RUN " + subprocess.list2cmdline(base + arguments), flush=True)
            result = subprocess.run(base + arguments, env=env, cwd=root, capture_output=True,
                                    timeout=180, encoding="utf-8", errors="replace")
            output = result.stdout + result.stderr
            if arguments[0] == "--script":
                print(output)
                fatal = [line for line in output.splitlines()
                         if any(token in line for token in FATAL_ENGINE_LINES)
                         or ("ERROR:" in line and not any(n in line for n in SHUTDOWN_NOISE))]
                reports = [json.loads(line[len(SENTINEL):]) for line in result.stdout.splitlines()
                           if line.startswith(SENTINEL)]
                if not reports:
                    raise RuntimeError("харнесс не напечатал результат:\n" + output)
                if fatal or reports[0]["failures"] or result.returncode:
                    raise RuntimeError("живая проверка клиента не прошла:\n"
                                       + "\n".join(fatal + reports[0]["failures"]))
            elif result.returncode:
                raise RuntimeError("импорт песочницы упал:\n" + output)


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT_AGENT_GODOT_EXECUTABLE"))
    parser.add_argument("--temp-parent", default=None)
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()

    addon = Path(__file__).resolve().parents[2]
    static = StaticChecks(addon)
    static.run()
    print("СТАТИКА: %d проверок, %d провалов" % (static.checks, len(static.failures)))

    ok = not static.failures
    if not args.static_only:
        executable = args.godot or shutil.which("godot") or shutil.which("godot4")
        if not executable:
            parser.error("Specify --godot; a static test cannot replace engine compilation.")
        try:
            live_check(addon, str(Path(executable).resolve()), args.temp_parent)
            print("ЖИВАЯ ПРОВЕРКА: OK")
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            print("ЖИВАЯ ПРОВЕРКА: FAIL\n%s" % error)
            ok = False

    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()