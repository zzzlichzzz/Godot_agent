"""channels/mcp/server.py - MCP-сервер: `tools/list` и `tools/call` (R-04).

Канал ничего не решает: схема инструмента приходит из реестра (ADR-0006),
вызов уходит в `protocol/dispatch`, ошибки уже типизированы доменом (R-15).
"""

import json

PROTOCOL_VERSION = "2024-11-05"
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


class McpServer:
    def __init__(self, agent, name="godot-agent", version="0.1.0"):
        self._agent = agent
        self._name = name
        self._version = version

    def handle(self, request):
        """JSON-RPC запрос → ответ; уведомления дают None (ответа нет)."""
        if not isinstance(request, dict):
            return error(None, INVALID_REQUEST, "запрос должен быть объектом")
        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            return error(request_id, INVALID_REQUEST, "нет поля method")
        if method.startswith("notifications/"):
            return None
        if method == "initialize":
            return answer(request_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": self._name, "version": self._version},
            })
        if method == "tools/list":
            return answer(request_id, {"tools": self._agent.tools()})
        if method == "tools/call":
            return self._call(request_id, request.get("params"))
        return error(request_id, METHOD_NOT_FOUND, "метод не поддержан: %r" % method)

    def _call(self, request_id, params):
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return error(request_id, INVALID_PARAMS, "нужен params.name")
        answer_payload = self._agent.call(params["name"], params.get("arguments") or {})
        return answer(request_id, {
            "content": [{"type": "text",
                         "text": json.dumps(answer_payload, ensure_ascii=False)}],
            "isError": not answer_payload.get("ok"),
        })


def answer(request_id, value):
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}

