# -*- coding: utf-8 -*-
"""Вызов инструмента n8n MCP-сервера (JSON-RPC tools/call) из командной строки.

Зачем. Разработка фабрики идёт не только через веб-редактор, но и через
MCP-сервер n8n (по умолчанию http://localhost:5678/mcp-server/http):
чтение исполнений, статусы, точечные правки воркфлоу. Скрипт делает один
вызов tools/call и печатает ответ — общая утилита для остальных сценариев
(например, dump_execution.py вызывает его функции напрямую).

Токен (Bearer): сначала переменная окружения N8N_MCP_TOKEN, затем локальный
файл ~/n8n/mcp_call.py (строка TOKEN = '...') — этот файл в репозиторий не
входит. Адрес: переменная N8N_MCP_URL или localhost по умолчанию.

Запуск (из папки n8n):
    python -B scripts/mcp_invoke.py <tool> <json-args> [out.json]
    python -B scripts/mcp_invoke.py get_workflow_execution \
        '{"workflowId":"v81fH05KY5uKUNK0","executionId":"61"}'
    python -B scripts/mcp_invoke.py update_workflow @ops.json out.json

<json-args> — объект JSON строкой или @файл с объектом. Ответ печатается
как JSON (длинный — обрезается до 8000 символов; пишите в файл через out.json).
"""

import json
import os
import re
import sys
import time
import urllib.request

DEFAULT_URL = "http://localhost:5678/mcp-server/http"
TOKEN_SRC = os.path.join(os.path.expanduser("~"), "n8n", "mcp_call.py")


def find_token():
    """Bearer-токен n8n MCP: N8N_MCP_TOKEN или ~/n8n/mcp_call.py."""
    token = os.environ.get("N8N_MCP_TOKEN")
    if token:
        return token
    if os.path.isfile(TOKEN_SRC):
        with open(TOKEN_SRC, encoding="utf-8") as fh:
            match = re.search(r"TOKEN = '([^']+)'", fh.read())
        if match:
            return match.group(1)
    raise SystemExit(
        "Токен не найден: задайте N8N_MCP_TOKEN или положите в %s строку "
        "TOKEN = '...'" % TOKEN_SRC)


def call_tool(tool, arguments, url=None, token=None, timeout=180):
    """Один вызов tools/call; возвращает распарсенный JSON-RPC ответ."""
    url = url or os.environ.get("N8N_MCP_URL") or DEFAULT_URL
    token = token or find_token()
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json, text/event-stream",
        })
    response = urllib.request.urlopen(request, timeout=timeout)
    buf = b""
    started = time.time()
    while time.time() - started < timeout - 10:
        try:
            chunk = response.read1(1048576)
        except Exception:
            break
        if not chunk:
            break
        buf += chunk
        text = buf.decode("utf-8", errors="replace")
        if '"result"' in text or '"error"' in text:
            parsed = _parse_sse(text)
            if parsed is not None:
                return parsed
    return _parse_sse(buf.decode("utf-8", errors="replace"), keep_raw=True)


def _parse_sse(text, keep_raw=False):
    """Разобрать ответ (text/event-stream или чистый JSON)."""
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except ValueError:
                continue
    try:
        return json.loads(text)
    except ValueError:
        return {"raw": text[:4000]} if keep_raw else None


def tool_result(response):
    """Внутренний JSON ответа tools/call (structuredContent или content[0])."""
    if not response or "result" not in response:
        return None
    result = response["result"]
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    if result.get("content"):
        try:
            return json.loads(result["content"][0]["text"])
        except (KeyError, IndexError, ValueError):
            return None
    return None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        raise SystemExit(__doc__.strip())
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    tool, raw = argv[0], argv[1]
    out_path = argv[2] if len(argv) > 2 else None
    if raw.startswith("@"):
        # utf-8-sig: PowerShell Set-Content -Encoding UTF8 пишет BOM.
        with open(raw[1:], encoding="utf-8-sig") as fh:
            arguments = json.load(fh)
    else:
        arguments = json.loads(raw)
    response = call_tool(tool, arguments)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(response, fh, ensure_ascii=False, indent=1)
        print("WROTE %s" % out_path)
    else:
        print(json.dumps(response, ensure_ascii=False)[:8000])


if __name__ == "__main__":
    main()
