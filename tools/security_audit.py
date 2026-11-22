#!/usr/bin/env python
"""tools/security_audit.py - статическая проверка инвариантов R-20.

Запуск:  python tools/security_audit.py [--json]

Последняя строка stdout - JSON вердикта (контракт R-18):
    {"status": "ok" | "fail" | "not_implemented", "detail": "..."}
Код возврата: 0 - зелёно, 1 - есть нарушения, 2 - проверка не выполнена.

Проверяет только то, что можно проверить без запуска агента. Динамика
(SSRF, prompt injection, stale plan) живёт в tests/py/security/.
"""

import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "python"
GD_ROOTS = [ROOT / "editor", ROOT / "runtime"]
SKIP_DIRS = {"__pycache__", ".git", ".godot", "reports", "node_modules"}

FORBIDDEN_CALLS = [r"os\.system\s*\(", r"(?<![\w.])eval\s*\(", r"(?<![\w.])exec\s*\(",
                   r"^\s*import\s+pickle\b", r"^\s*import\s+marshal\b"]
NET_MODULES = ["socket", "urllib", "http.client", "requests", "httpx", "aiohttp"]
NET_ALLOWED = PY / "substrate" / "llm"
# Мост редактора (ADR-0007): слушает GDScript, Python - клиент. Клиенту нужен
# только петлевой TCP (`socket`), остальные сетевые модули здесь запрещены;
# адрес клиента проверяется ниже - исключение узкое и с проверкой петли.
BRIDGE_CLIENT = PY / "substrate" / "editor"
BRIDGE_MODULES = {"socket"}
PROC_ALLOWED = [PY / "substrate" / "engine", PY / "substrate" / "llm" / "browser"]
# Browser: Chrome запускается обычным процессом (см. contract/browser_stealth.json,
# launch.mode = plain_process_then_attach). Аргументы закреплены в контракте.

LISTEN_PATTERNS = [r"\.run\s*\(", r"HTTPServer\s*\(", r"\.listen\s*\(", r"\.bind\s*\("]
LISTEN_ALLOWED = PY / "channels" / "http"
GD_FORBIDDEN = [r"OS\.execute", r"OS\.shell_open", r"OS\.create_process", r"OS\.kill"]
SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{20,}",
    r"AIza[0-9A-Za-z_\-]{30,}",
    r"ghp_[A-Za-z0-9]{30,}",
    r"Bearer\s+[A-Za-z0-9._\-]{24,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
]
REQUIRED_GITIGNORE = [".env", "*.key", "secrets*", "reports/", "python/build/", "python/dist/"]


def files(base, suffix):
    if not base.exists():
        return []
    out = []
    for path in base.rglob("*" + suffix):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        out.append(path)
    return sorted(out)


def rel(path):
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def check_forbidden_calls():
    bad = []
    for path in files(PY, ".py"):
        text = path.read_bytes().decode("utf-8", "replace")
        for pattern in FORBIDDEN_CALLS:
            for match in re.finditer(pattern, text, re.MULTILINE):
                line = text[: match.start()].count("\n") + 1
                bad.append("SEC-01 %s:%d %s" % (rel(path), line, match.group(0).strip()))
    return bad


def check_network_imports():
    bad = []
    for path in files(PY, ".py"):
        if NET_ALLOWED in path.parents:
            continue
        text = path.read_bytes().decode("utf-8", "replace")
        bridge = BRIDGE_CLIENT in path.parents
        for module in NET_MODULES:
            if bridge and module in BRIDGE_MODULES:
                continue
            if re.search(r"^\s*(import|from)\s+%s\b" % re.escape(module), text, re.MULTILINE):
                bad.append("SEC-02 %s: импорт %s вне substrate/llm" % (rel(path), module))
        if bridge:
            for match in re.finditer(r"^(?:HOST|EDITOR_HOST)\s*=\s*[\"']([^\"']+)[\"']",
                                     text, re.MULTILINE):
                if match.group(1) not in {"127.0.0.1", "localhost"}:
                    bad.append("SEC-02 %s: мост не на петле (адрес %s)"
                               % (rel(path), match.group(1)))
    return bad


def _exclusive_probe_bind_start(path, text):
    """Recognize one non-listening B-1 match, never authorize the whole file."""
    if path != PY / "substrate/llm/browser/facade.py":
        return None
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    canonical = ast.parse("""try:
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind(('127.0.0.1', 9222))
except OSError as error: raise RuntimeError('9222 availability unknown; refusing launch') from error
""").body[0]
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ReadOnlyBrowser"]
    if len(classes) != 1:
        return None
    if classes[0].bases or classes[0].keywords or classes[0].decorator_list or getattr(classes[0], "type_params", []):
        return None
    methods = [node for node in classes[0].body if isinstance(node, ast.FunctionDef) and node.name == "__init__"]
    if len(methods) != 1:
        return None
    if methods[0].decorator_list or getattr(methods[0], "type_params", []):
        return None
    candidates = [node for node in methods[0].body if ast.dump(node) == ast.dump(canonical)]
    if len(candidates) != 1:
        return None
    protected = {"socket", "probe"}
    candidate_nodes = set(ast.walk(candidates[0]))
    socket_imports = [node for node in tree.body if isinstance(node, ast.Import)
                      and len(node.names) == 1 and node.names[0].name == "socket" and node.names[0].asname is None]
    if len(socket_imports) != 1:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in protected and node not in candidate_nodes:
            return None
        if isinstance(node, ast.arg) and node.arg in protected:
            return None
        if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name in protected:
            return None
        if isinstance(node, ast.MatchMapping) and node.rest in protected:
            return None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in protected:
            return None
        if isinstance(node, (ast.Global, ast.Nonlocal)) and protected.intersection(node.names):
            return None
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node is not socket_imports[0]:
            if any((alias.asname or alias.name.split(".")[0]) in protected for alias in node.names):
                return None
        # Reflective rebinding is not statically proven safe by this exception.
        if isinstance(node, ast.Name) and node.id in {"globals", "locals", "vars", "setattr", "delattr", "__import__", "__builtins__"}:
            return None
        if isinstance(node, ast.Attribute) and node.attr in {"globals", "locals", "vars", "setattr", "delattr", "__import__",
                                                            "__dict__", "__globals__", "__builtins__", "modules", "__getattribute__"}:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in protected:
            return None
    bind = candidates[0].body[0].body[1].value
    lines = text.splitlines(keepends=True)
    prefix = lines[bind.lineno - 1].encode("utf-8")[:bind.col_offset].decode("utf-8")
    start = sum(map(len, lines[:bind.lineno - 1])) + len(prefix)
    match = re.search(r"\.bind\s*\(", ast.get_source_segment(text, bind))
    return start + match.start() if match else None


def _subprocess_imports(tree):
    return [node for node in ast.walk(tree) if
            (isinstance(node, ast.Import) and any(a.name.split(".")[0] == "subprocess" for a in node.names))
            or (isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "subprocess")]


def _headless_process_tree(path, text):
    if path != PY / "substrate" / "verification" / "godot_headless_validation.py":
        return None
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    imports = _subprocess_imports(tree)
    allowed = [node for node in tree.body if isinstance(node, ast.Import) and len(node.names) == 1
               and node.names[0].name == "subprocess" and node.names[0].asname is None]
    return tree if len(imports) == len(allowed) == 1 and imports[0] is allowed[0] else None


def _headless_run_start(path, text):
    """D62: approve one UTF-8 byte-offset, never the file or other listeners."""
    tree = _headless_process_tree(path, text)
    if tree is None:
        return None
    for node in ast.walk(tree):
        if ((isinstance(node, ast.Name) and node.id in {"subprocess", "str"} and isinstance(node.ctx, (ast.Store, ast.Del)))
                or (isinstance(node, ast.arg) and node.arg in {"subprocess", "str"})
                or (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in {"subprocess", "str"})
                or (isinstance(node, ast.alias) and node.asname in {"subprocess", "str"})):
            return None
    calls = []
    pid = ast.dump(ast.parse("str(proc.pid)", mode="eval").body)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"):
            continue
        if len(node.args) != 1 or not isinstance(node.args[0], ast.List):
            continue
        if any(not ((isinstance(value, ast.Constant) and isinstance(value.value, str))
                   or (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "str"
                       and len(value.args) == 1 and not value.keywords and isinstance(value.args[0], ast.Name))
                   or ast.dump(value) == pid) for value in node.args[0].elts):
            continue
        if any(keyword.arg in {None, "shell"} or not (isinstance(keyword.value, ast.Constant)
                or (isinstance(keyword.value, ast.Attribute) and isinstance(keyword.value.value, ast.Name)
                    and keyword.value.value.id == "subprocess" and keyword.value.attr in {"DEVNULL", "PIPE"}))
               for keyword in node.keywords):
            continue
        calls.append(node)
    if len(calls) != 1:
        return None
    node = calls[0]
    lines = text.encode("utf-8").splitlines(keepends=True)
    match = re.search(rb"\.\s*run\s*\(", (ast.get_source_segment(text, node) or "").encode("utf-8"))
    return sum(map(len, lines[:node.lineno - 1])) + node.col_offset + match.start() if match else None


def _t1_split_source(path, text):
    """D74: byte-exact native only; any edit/path change revokes permission."""
    return (path == PY / 'substrate' / 'editing' / 'split_gd.py'
            and hashlib.sha256(text.encode('utf-8')).hexdigest()
            == '18f05d10b8e875ed77040b8a47beb6ccbdb409b55d791ec0318466473969bfc7')


def _t1_split_run_start(path, text):
    if not _t1_split_source(path, text):
        return None
    marker = b'.run(cmd, capture_output=True, text=True,'
    raw = text.encode('utf-8')
    return raw.index(marker) if raw.count(marker) == 1 else None


def check_listener():
    bad = []
    for path in files(PY, ".py"):
        text = path.read_bytes().decode("utf-8", "replace")
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            hits = True  # Unparseable source is not a proven non-listener.
        else:
            allowed_run = _headless_run_start(path, text)
            if allowed_run is None:
                allowed_run = _t1_split_run_start(path, text)
            allowed_bind = _exclusive_probe_bind_start(path, text)
            # Preserve B-1's narrow approval conditions, not a file allowlist.
            if allowed_bind is not None and any(
                    p != r"\.bind\s*\(" or match.start() != allowed_bind
                    for p in LISTEN_PATTERNS for match in re.finditer(p, text)):
                allowed_bind = None
            hits = False
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                callee = node.func
                name = callee.attr if isinstance(callee, ast.Attribute) else (
                    callee.id if isinstance(callee, ast.Name) else "")
                if not ((isinstance(callee, ast.Attribute) and name in {"bind", "listen", "run"})
                        or name.endswith("HTTPServer") or (isinstance(callee, ast.Name) and name == "run"
                            and path == PY / "substrate" / "verification" / "godot_headless_validation.py")):
                    continue
                if name == "run" and allowed_run is not None:
                    lines = text.encode("utf-8").splitlines(keepends=True)
                    match = re.search(rb"\.\s*run\s*\(", (ast.get_source_segment(text, node) or "").encode("utf-8"))
                    if match and sum(map(len, lines[:node.lineno - 1])) + node.col_offset + match.start() == allowed_run:
                        continue
                if name == "bind" and allowed_bind is not None:
                    lines = text.splitlines(keepends=True)
                    prefix = lines[node.lineno - 1].encode("utf-8")[:node.col_offset].decode("utf-8")
                    start = sum(map(len, lines[:node.lineno - 1])) + len(prefix)
                    match = re.search(r"\.bind\s*\(", ast.get_source_segment(text, node) or "")
                    if match and start + match.start() == allowed_bind:
                        continue
                hits = True
                break
        if not hits:
            continue
        if LISTEN_ALLOWED not in path.parents:
            bad.append("SEC-03 %s: слушающий сокет вне channels/http" % rel(path))
            continue
        for match in re.finditer(r"host\s*=\s*[\"']([^\"']+)[\"']", text):
            if match.group(1) not in {"127.0.0.1", "localhost"}:
                bad.append("SEC-03 %s: адрес %s" % (rel(path), match.group(1)))
    return bad


def check_processes():
    bad = []
    for path in files(PY, ".py"):
        text = path.read_bytes().decode("utf-8", "replace")
        if re.search(r"shell\s*=\s*True", text):
            bad.append("SEC-04 %s: shell=True" % rel(path))
        imported = re.search(r"^\s*(import|from)\s+subprocess\b", text, re.MULTILINE)
        if PY / "substrate" / "verification" in path.parents:
            try:
                imported = bool(_subprocess_imports(ast.parse(text)))
            except (SyntaxError, ValueError):
                imported = True
        if imported:
            if (not any(parent in path.parents for parent in PROC_ALLOWED)
                    and _headless_process_tree(path, text) is None and not _t1_split_source(path, text)):
                bad.append("SEC-04 %s: subprocess вне substrate/engine" % rel(path))
    return bad


def check_gdscript():
    bad = []
    # ADR0086: inactive exact native sites, not a directory exemption.
    native_sites = {
        'editor/native/agent_server_link.gd': ('c09783ed60d90f0bcb819ad1c9cc591dacd41f9d78fe1fd6577674db697b475c',
            {r'OS\.shell_open': (22168,), r'OS\.create_process': (28404,)}),
        'editor/native/agent_updater.gd': ('0ced1dbd685551413afb857da22077f4ee64022396d25d833f0f5ea917400e7a',
            {r'OS\.execute': (18236,19214), r'OS\.shell_open': (19989,), r'OS\.create_process': (19674,)})}
    for base in GD_ROOTS:
        for path in files(base, ".gd"):
            data = path.read_bytes(); text = data.decode("utf-8", "replace")
            record = native_sites.get(rel(path))
            proof = record is not None and hashlib.sha256(data).hexdigest() == record[0]
            for pattern in GD_FORBIDDEN:
                matches = list(re.finditer(pattern, text))
                allowed = proof and all(len(text[:match.start()].encode('utf-8')) in record[1].get(pattern, ()) for match in matches)
                if matches and not allowed:
                    bad.append("SEC-05 %s: %s" % (rel(path), pattern.replace("\\", "")))
    return bad


def check_secrets():
    bad = []
    scan_roots = [ROOT / "python", ROOT / "editor", ROOT / "runtime", ROOT / "contract",
                  ROOT / "tools", ROOT / "tests", ROOT / "fixtures"]
    for base in scan_roots:
        for suffix in (".py", ".gd", ".json", ".cfg", ".toml", ".ps1", ".md"):
            for path in files(base, suffix):
                text = path.read_bytes().decode("utf-8", "replace")
                for pattern in SECRET_PATTERNS:
                    if re.search(pattern, text):
                        bad.append("SEC-06 %s: похоже на секрет" % rel(path))
    return bad


def check_gitignore():
    path = ROOT / ".gitignore"
    if not path.exists():
        return ["SEC-07 .gitignore отсутствует"]
    text = path.read_bytes().decode("utf-8", "replace")
    return ["SEC-07 .gitignore: нет %s" % item
            for item in REQUIRED_GITIGNORE if item not in text]


def check_allow_list():
    path = ROOT / "contract" / "network_allow.json"
    if not path.exists():
        return ["SEC-08 нет contract/network_allow.json"]
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except ValueError as exc:
        return ["SEC-08 network_allow.json не разбирается: %s" % exc]
    if not isinstance(data.get("hosts"), list):
        return ["SEC-08 network_allow.json: нет списка hosts"]
    return []


def _browser_site_flag_errors(path, raw, pinned):
    """D30: inspect literal Python site records without executing their code."""
    try:
        tree = ast.parse(raw)
    except (SyntaxError, ValueError):
        return ["SEC-20 %s: site flags не разбираются" % rel(path)] if path.name == "sites.py" else []
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        fields = {key.value: value for key, value in zip(node.keys, node.values)
                  if isinstance(key, ast.Constant) and isinstance(key.value, str)}
        if not {"id", "needs_visibility_spoof"}.issubset(fields):
            continue
        site, flag = fields["id"], fields["needs_visibility_spoof"]
        if (not isinstance(site, ast.Constant) or not isinstance(site.value, str)
                or not isinstance(flag, ast.Constant) or type(flag.value) is not bool):
            bad.append("SEC-20 %s: site id/needs_visibility_spoof должны быть литералами" % rel(path))
            continue
        if flag.value and not pinned.get(site.value, {}).get("needs_visibility_spoof", False):
            bad.append("SEC-20 %s: у сайта %s спуф поднят с false на true" % (rel(path), site.value))
    return bad


def check_browser_stealth():
    """SEC-20 (R-21): браузерная ветка не получает новой маскировки."""
    contract = ROOT / "contract" / "browser_stealth.json"
    if not contract.exists():
        return ["SEC-20 нет contract/browser_stealth.json"]
    try:
        data = json.loads(contract.read_bytes().decode("utf-8"))
    except ValueError as exc:
        return ["SEC-20 browser_stealth.json не разбирается: %s" % exc]
    forbidden = data.get("forbidden_techniques") or []
    pinned = data.get("sites") or {}
    launch = data.get("launch") or {}
    base = PY / "substrate" / "llm" / "browser"
    if not base.exists():
        return []
    bad = []
    for path in files(base, ".py"):
        raw = path.read_bytes().decode("utf-8", "replace")
        bad.extend(_browser_site_flag_errors(path, raw, pinned))
        # комментарии вырезаем: упоминание запрещённого слова в комментарии не код
        text = re.sub(r"#[^\n]*", "", raw)
        text = re.sub(r"(?m)^[ \t]*//[^\n]*", "", text)
        for item in forbidden:
            if item in text:
                bad.append("SEC-20 %s: запрещённая маскировка %s" % (rel(path), item))
        for site, rule in pinned.items():
            if not rule.get("needs_visibility_spoof"):
                pattern = r"%s[^\n]*needs_visibility_spoof\W+True" % re.escape(site)
                if re.search(pattern, text):
                    bad.append("SEC-20 %s: у сайта %s спуф поднят с false на true" % (rel(path), site))
        if launch.get("selenium_launches_browser") is False and re.search(r"webdriver\.Chrome\s*\(", text):
            if "debuggerAddress" not in text:
                bad.append("SEC-20 %s: selenium запускает браузер сам (нет debuggerAddress) — "
                           "navigator.webdriver станет true" % rel(path))
        for item in data.get("forbidden_paths") or []:
            if item in text:
                bad.append("SEC-20 %s: обращение к профилю пользователя (%s) запрещено" % (rel(path), item))
    return bad


CHECKS = [
    ("SEC-01 запрещённые вызовы", check_forbidden_calls),
    ("SEC-02 сетевые импорты", check_network_imports),
    ("SEC-03 слушающий сокет", check_listener),
    ("SEC-04 запуск процессов", check_processes),
    ("SEC-05 GDScript и ОС", check_gdscript),
    ("SEC-06 секреты в репозитории", check_secrets),
    ("SEC-07 .gitignore", check_gitignore),
    ("SEC-08 список хостов", check_allow_list),
    ("SEC-20 браузерная ветка", check_browser_stealth),
]


def main(argv):
    as_json = "--json" in argv
    problems = []
    table = []
    for name, check in CHECKS:
        found = check()
        table.append((name, "ok" if not found else "fail", len(found)))
        problems.extend(found)
    if not as_json:
        for name, status, count in table:
            print("  %-30s %-5s %s" % (name, status, "" if status == "ok" else count))
        for line in problems:
            print("    " + line)
    verdict = {"status": "ok" if not problems else "fail",
               "detail": "нарушений нет" if not problems else "%d нарушений" % len(problems)}
    print(json.dumps(verdict, ensure_ascii=False))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

