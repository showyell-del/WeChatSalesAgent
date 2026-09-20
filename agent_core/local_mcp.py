import argparse
import hashlib
import json
import re
import sys
import uuid
from typing import Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .local_api import _load_token


SERVER_NAME = "wechat-customer-analysis"
SERVER_VERSION = "1.0.0"
SUPPORTED_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)
TASK_TYPES = (
    "customer_search",
    "opportunity_analysis",
    "reengagement_analysis",
    "customer_risk",
    "commitment_tracker",
    "person_profile",
    "relationship_insight",
    "comparison",
    "topic_analysis",
    "timeline",
    "general_search",
)


class MCPToolError(RuntimeError):
    def __init__(self, code: str, detail: str, data: Optional[Dict] = None):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.data = data or {"code": code, "detail": detail}


def _object_schema(properties: Dict, required=None) -> Dict:
    schema = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


TOOLS = (
    {
        "name": "list_conversations",
        "title": "列出微信会话",
        "description": "列出当前微信账号的私聊和群聊会话；使用返回的 username 调用消息检索。",
        "inputSchema": _object_schema({
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            "cursor": {"type": "string", "description": "上一页返回的 next_cursor。"},
        }),
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "search_wechat_messages",
        "title": "检索微信消息",
        "description": "在一个明确会话中按时间、关键词、消息类型和方向检索原始消息。",
        "inputSchema": _object_schema({
            "chat": {"type": "string", "minLength": 1, "description": "list_conversations 返回的 username。"},
            "since": {"type": "integer", "minimum": 1, "description": "起始 Unix 秒。"},
            "until": {"type": "integer", "minimum": 2, "description": "结束 Unix 秒。"},
            "keyword": {"type": "string"},
            "msg_type": {"type": "string"},
            "sub_type": {"type": "string"},
            "direction": {"type": "string", "enum": ["all", "self", "other"], "default": "all"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            "cursor": {"type": "string", "description": "上一页返回的 next_cursor。"},
        }, ["chat"]),
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "get_dashboard",
        "title": "读取微信仪表盘",
        "description": "读取当前微信账号的真实仪表盘统计、趋势和会话概览。",
        "inputSchema": _object_schema({
            "time_range": {"type": "string", "enum": ["today", "last-1d", "last-30d", "all"], "default": "today"},
            "private_chat": {"type": "string"},
            "group_chat": {"type": "string"},
        }),
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "analyze_conversation",
        "title": "发起微信智能分析",
        "description": "异步发起客户、人物、关系、群聊话题或时间线分析；返回 operation id 后用 get_analysis_result 轮询。",
        "inputSchema": _object_schema({
            "question": {"type": "string", "minLength": 1},
            "session_id": {"type": "string", "description": "延续同一分析会话时传入。"},
            "task_type": {"type": "string", "enum": list(TASK_TYPES)},
            "timeout": {"type": "integer", "minimum": 10, "maximum": 600, "default": 120},
        }, ["question"]),
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
    },
    {
        "name": "get_analysis_result",
        "title": "查询微信分析结果",
        "description": "使用 analyze_conversation 返回的 operation id 查询 queued、running、succeeded 或 failed 状态。",
        "inputSchema": _object_schema({
            "operation_id": {"type": "string", "minLength": 1},
        }, ["operation_id"]),
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    },
)


class LocalMCPBridge:
    def __init__(self, api_base: str = "http://127.0.0.1:8765", token: Optional[str] = None):
        parsed = urlsplit(api_base)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.path.rstrip("/") or parsed.query or parsed.fragment:
            raise ValueError("MCP bridge may only use a loopback HTTP API base")
        if parsed.port is None:
            raise ValueError("MCP bridge API base must include a port")
        self.api_base = api_base.rstrip("/")
        self.token = token if token is not None else _load_token()
        self.instance_id = uuid.uuid4().hex

    def _request(self, path: str, method: str = "GET", body: Optional[Dict] = None, headers: Optional[Dict[str, str]] = None) -> Dict:
        request_headers = {"Authorization": "Bearer %s" % self.token}
        request_headers.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = Request(self.api_base + path, data=data, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = {}
            raise MCPToolError(
                str(payload.get("code") or "API_HTTP_%s" % exc.code),
                str(payload.get("detail") or "本机 API 返回 HTTP %s。" % exc.code),
                payload if isinstance(payload, dict) else None,
            ) from exc
        except (OSError, URLError) as exc:
            raise MCPToolError("LOCAL_API_UNAVAILABLE", "无法连接微信客户分析 App，请先打开 App 并连接微信。") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MCPToolError("LOCAL_API_RESPONSE_INVALID", "本机 API 未返回有效 JSON。") from exc
        if not isinstance(payload, dict):
            raise MCPToolError("LOCAL_API_RESPONSE_INVALID", "本机 API 返回格式无效。")
        return payload

    @staticmethod
    def _validate_arguments(name: str, arguments: Dict) -> Dict:
        if not isinstance(arguments, dict):
            raise MCPToolError("ARGUMENTS_INVALID", "工具参数必须是 JSON 对象。")
        schemas = {tool["name"]: tool["inputSchema"] for tool in TOOLS}
        schema = schemas.get(name)
        if schema is None:
            raise MCPToolError("TOOL_NOT_FOUND", "未知工具：%s" % name)
        unknown = set(arguments) - set(schema["properties"])
        if unknown:
            raise MCPToolError("ARGUMENT_UNKNOWN", "不支持的参数：%s" % ", ".join(sorted(unknown)))
        for required in schema.get("required", []):
            value = arguments.get(required)
            if not isinstance(value, str) or not value.strip():
                raise MCPToolError("ARGUMENT_REQUIRED", "%s 必须是非空字符串。" % required)
        for key, value in arguments.items():
            field = schema["properties"][key]
            if field.get("type") == "string" and not isinstance(value, str):
                raise MCPToolError("ARGUMENT_INVALID", "%s 必须是字符串。" % key)
            if field.get("type") == "integer":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise MCPToolError("ARGUMENT_INVALID", "%s 必须是整数。" % key)
                if "minimum" in field and value < field["minimum"]:
                    raise MCPToolError("ARGUMENT_INVALID", "%s 小于允许的最小值。" % key)
                if "maximum" in field and value > field["maximum"]:
                    raise MCPToolError("ARGUMENT_INVALID", "%s 超过允许的最大值。" % key)
            if "enum" in field and value not in field["enum"]:
                raise MCPToolError("ARGUMENT_INVALID", "%s 不在允许范围内。" % key)
        return dict(arguments)

    @staticmethod
    def _query(arguments: Dict) -> str:
        values = {key: value for key, value in arguments.items() if value not in (None, "")}
        return ("?" + urlencode(values)) if values else ""

    def call_tool(self, name: str, arguments: Dict, request_id=None) -> Dict:
        values = self._validate_arguments(name, arguments)
        if name == "list_conversations":
            return self._request("/v1/conversations" + self._query(values))
        if name == "search_wechat_messages":
            return self._request("/v1/messages" + self._query(values))
        if name == "get_dashboard":
            return self._request("/v1/dashboard" + self._query(values))
        if name == "get_analysis_result":
            if not re.fullmatch(r"op_[0-9a-f]{32}", values["operation_id"]):
                raise MCPToolError("OPERATION_ID_INVALID", "operation_id 格式无效。")
            return self._request("/v1/operations/%s" % values["operation_id"])
        fingerprint = json.dumps(
            {"instance": self.instance_id, "request_id": request_id, "arguments": values},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        idempotency_key = "mcp-" + hashlib.sha256(fingerprint).hexdigest()
        return self._request(
            "/v1/analyses",
            method="POST",
            body=values,
            headers={"Idempotency-Key": idempotency_key},
        )


def _tool_result(payload: Dict, is_error: bool = False) -> Dict:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    result = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
    }
    if is_error:
        result["isError"] = True
    return result


class StdioMCPServer:
    def __init__(self, bridge: LocalMCPBridge, input_stream=None, output_stream=None):
        self.bridge = bridge
        self.input_stream = input_stream or sys.stdin.buffer
        self.output_stream = output_stream or sys.stdout.buffer
        self.initialized = False

    def _write(self, message: Dict) -> None:
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        self.output_stream.write(raw)
        self.output_stream.flush()

    def _response(self, request_id, result: Dict) -> None:
        self._write({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _error(self, request_id, code: int, message: str, data=None) -> None:
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        self._write({"jsonrpc": "2.0", "id": request_id, "error": error})

    def handle(self, message: Dict) -> None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            self._error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
            return
        method = message["method"]
        if "id" not in message:
            if method == "notifications/initialized":
                self.initialized = True
            return
        request_id = message["id"]
        params = message.get("params", {})
        if not isinstance(params, dict):
            self._error(request_id, -32602, "Invalid params")
            return
        if method == "initialize":
            requested = params.get("protocolVersion")
            if requested not in SUPPORTED_PROTOCOL_VERSIONS:
                self._error(
                    request_id,
                    -32022,
                    "Unsupported protocol version",
                    {"supported": list(SUPPORTED_PROTOCOL_VERSIONS), "requested": requested},
                )
                return
            self.initialized = True
            self._response(request_id, {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "只读取当前 App 严格绑定的微信账号；分析请求返回 operation id，需继续轮询结果。",
            })
            return
        if method == "ping":
            self._response(request_id, {})
            return
        if not self.initialized:
            self._error(request_id, -32002, "Server is not initialized")
            return
        if method == "tools/list":
            self._response(request_id, {"tools": list(TOOLS)})
            return
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not name:
                self._error(request_id, -32602, "Tool name is required")
                return
            try:
                payload = self.bridge.call_tool(name, arguments, request_id=request_id)
                self._response(request_id, _tool_result(payload))
            except MCPToolError as exc:
                self._response(request_id, _tool_result(exc.data, is_error=True))
            return
        self._error(request_id, -32601, "Method not found")

    def serve(self) -> int:
        for raw in self.input_stream:
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._error(None, -32700, "Parse error")
                continue
            self.handle(message)
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WeChat Customer Analysis MCP stdio server")
    parser.add_argument("--api-base", default="http://127.0.0.1:8765")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    bridge = LocalMCPBridge(api_base=args.api_base)
    return StdioMCPServer(bridge).serve()


if __name__ == "__main__":
    raise SystemExit(main())
