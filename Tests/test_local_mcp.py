import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from agent_core.local_mcp import LocalMCPBridge, StdioMCPServer, TOOLS


class FakeAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _json(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self):
        if self.headers.get("Authorization") == "Bearer test-token":
            return True
        self._json(401, {"code": "UNAUTHORIZED", "detail": "Bearer token 无效。"})
        return False

    def do_GET(self):
        if not self._authorized():
            return
        path = urlsplit(self.path)
        query = parse_qs(path.query)
        self.server.requests.append(("GET", path.path, query, None, dict(self.headers)))
        if path.path == "/v1/conversations":
            self._json(200, {"data": [{"username": "chat_1"}], "pagination": {"has_next": False, "next_cursor": None, "limit": 50}})
        elif path.path == "/v1/messages":
            self._json(200, {"chat": query["chat"][0], "data": [{"content": "创业"}], "pagination": {"has_next": False, "next_cursor": None, "limit": 50}})
        elif path.path == "/v1/dashboard":
            self._json(200, {"time_range": query.get("time_range", ["today"])[0], "message_total": 8})
        elif path.path == "/v1/operations/op_0123456789abcdef0123456789abcdef":
            self._json(200, {"id": "op_0123456789abcdef0123456789abcdef", "status": "succeeded", "result": {"answer": "完成"}})
        else:
            self._json(404, {"code": "NOT_FOUND", "detail": "资源不存在。"})

    def do_POST(self):
        if not self._authorized():
            return
        path = urlsplit(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        self.server.requests.append(("POST", path.path, {}, body, dict(self.headers)))
        self._json(202, {"id": "op_0123456789abcdef0123456789abcdef", "status": "queued"})


class LocalMCPTest(unittest.TestCase):
    def setUp(self):
        self.api = ThreadingHTTPServer(("127.0.0.1", 0), FakeAPIHandler)
        self.api.requests = []
        self.thread = threading.Thread(target=self.api.serve_forever, daemon=True)
        self.thread.start()
        self.bridge = LocalMCPBridge(
            "http://127.0.0.1:%d" % self.api.server_address[1],
            token="test-token",
        )

    def tearDown(self):
        self.api.shutdown()
        self.api.server_close()
        self.thread.join(timeout=2)

    def test_declares_five_stable_typed_tools(self):
        tools = {tool["name"]: tool for tool in TOOLS}
        self.assertEqual(set(tools), {
            "list_conversations",
            "search_wechat_messages",
            "get_dashboard",
            "analyze_conversation",
            "get_analysis_result",
        })
        for tool in tools.values():
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertFalse(tool["inputSchema"]["additionalProperties"])
            self.assertEqual(tool["outputSchema"], {"type": "object"})

    def test_all_tools_call_the_authenticated_rest_contract(self):
        conversations = self.bridge.call_tool("list_conversations", {"limit": 25})
        self.assertEqual(conversations["data"][0]["username"], "chat_1")

        messages = self.bridge.call_tool("search_wechat_messages", {
            "chat": "chat_1",
            "keyword": "创业",
            "direction": "other",
        })
        self.assertEqual(messages["data"][0]["content"], "创业")

        dashboard = self.bridge.call_tool("get_dashboard", {"time_range": "last-30d"})
        self.assertEqual(dashboard["message_total"], 8)

        operation = self.bridge.call_tool("analyze_conversation", {
            "question": "分析群聊热门话题",
            "task_type": "topic_analysis",
            "timeout": 120,
        }, request_id=9)
        self.assertEqual(operation["id"], "op_0123456789abcdef0123456789abcdef")

        result = self.bridge.call_tool("get_analysis_result", {"operation_id": "op_0123456789abcdef0123456789abcdef"})
        self.assertEqual(result["result"]["answer"], "完成")

        self.assertTrue(all(row[4].get("Authorization") == "Bearer test-token" for row in self.api.requests))
        post = next(row for row in self.api.requests if row[0] == "POST")
        self.assertEqual(post[3]["question"], "分析群聊热门话题")
        self.assertRegex(post[4]["Idempotency-Key"], r"^mcp-[0-9a-f]{64}$")

    def test_stdio_initializes_lists_and_calls_tools(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_conversations", "arguments": {"limit": 1}}},
        ]
        input_stream = io.BytesIO(b"".join(
            json.dumps(item, ensure_ascii=False).encode("utf-8") + b"\n"
            for item in requests
        ))
        output_stream = io.BytesIO()
        server = StdioMCPServer(self.bridge, input_stream=input_stream, output_stream=output_stream)
        self.assertEqual(server.serve(), 0)
        responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
        self.assertEqual([item["id"] for item in responses], [1, 2, 3])
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(len(responses[1]["result"]["tools"]), 5)
        call_result = responses[2]["result"]
        self.assertFalse(call_result.get("isError", False))
        self.assertEqual(call_result["structuredContent"]["data"][0]["username"], "chat_1")

    def test_tool_errors_are_returned_as_mcp_error_results(self):
        output = io.BytesIO()
        server = StdioMCPServer(self.bridge, input_stream=io.BytesIO(), output_stream=output)
        server.initialized = True
        server.handle({
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "search_wechat_messages", "arguments": {}},
        })
        response = json.loads(output.getvalue())
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["code"], "ARGUMENT_REQUIRED")

    def test_bridge_rejects_non_loopback_api_bases(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            LocalMCPBridge("https://example.com:8765", token="test-token")


if __name__ == "__main__":
    unittest.main()
