import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import patch

from agent_core.local_api import LocalAPIServer


class FakeChatlogClient:
    account_ids = ["wxid_current"]

    def __init__(self, addr="127.0.0.1:5030", timeout=30):
        self.addr = addr
        self.timeout = timeout

    def databases(self):
        return {
            "message": [
                "/Users/test/xwechat_files/%s/db_storage/message/message_0.db" % account_id
                for account_id in self.account_ids
            ]
        }

    def health(self):
        return {"status": "ok"}


class LocalAPITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = self.temp.name + "/state.sqlite3"
        connection = sqlite3.connect(self.db)
        connection.execute("CREATE TABLE app_state(key TEXT PRIMARY KEY,value TEXT,updated_at INTEGER)")
        connection.execute("INSERT INTO app_state VALUES('active_account','wxid_current',1)")
        connection.commit()
        connection.close()
        FakeChatlogClient.account_ids = ["wxid_current"]
        self.sessions = [
            {"username": "chat_%03d" % index, "display_name": "会话 %03d" % index, "is_group": False, "time": ""}
            for index in range(7)
        ]
        self.analysis_calls = []
        self.patchers = [
            patch("agent_core.local_api.ChatlogClient", FakeChatlogClient),
            patch("agent_core.local_api.list_sessions", side_effect=lambda addr, limit: list(self.sessions)),
            patch("agent_core.local_api.search_messages", side_effect=self._search_messages),
            patch("agent_core.local_api.ask_customer_agent", side_effect=self._analyze),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.server = LocalAPIServer(("127.0.0.1", 0), "secret-token", self.db, "127.0.0.1:5030")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp.cleanup()

    def _analyze(self, **kwargs):
        self.analysis_calls.append(kwargs)
        return {"schema_version": "agent.query.v2", "answer": "完成", "query": kwargs["question"]}

    def _search_messages(self, **kwargs):
        rows = [
            {"timestamp": 100 - index, "content": "消息 %02d" % index}
            for index in range(8)
        ]
        return {
            "chat": kwargs["chat"],
            "matched_total": len(rows),
            "count": min(len(rows), kwargs["limit"]),
            "messages": rows[: kwargs["limit"]],
        }

    def request(self, path, method="GET", body=None, authorized=True, headers=None):
        request_headers = dict(headers or {})
        if authorized:
            request_headers["Authorization"] = "Bearer secret-token"
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, dict(response.headers), json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), json.loads(exc.read())

    def test_health_and_openapi_are_public_but_business_routes_require_bearer_token(self):
        status, _, body = self.request("/v1/health", authorized=False)
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

        status, _, spec = self.request("/openapi.json", authorized=False)
        self.assertEqual(status, 200)
        self.assertIn("/v1/analyses", spec["paths"])

        status, headers, problem = self.request("/v1/status", authorized=False)
        self.assertEqual(status, 401)
        self.assertEqual(headers["Content-Type"], "application/problem+json; charset=utf-8")
        self.assertEqual(problem["code"], "UNAUTHORIZED")

    def test_account_mismatch_blocks_data_queries(self):
        FakeChatlogClient.account_ids = ["wxid_other"]
        status, _, problem = self.request("/v1/conversations")
        self.assertEqual(status, 409)
        self.assertEqual(problem["code"], "ACCOUNT_MISMATCH")

    def test_conversations_use_opaque_cursor_pagination(self):
        status, _, first = self.request("/v1/conversations?limit=3")
        self.assertEqual(status, 200)
        self.assertEqual([item["username"] for item in first["data"]], ["chat_000", "chat_001", "chat_002"])
        self.assertTrue(first["pagination"]["has_next"])
        cursor = urllib.parse.quote(first["pagination"]["next_cursor"])

        status, _, second = self.request("/v1/conversations?limit=3&cursor=" + cursor)
        self.assertEqual(status, 200)
        self.assertEqual([item["username"] for item in second["data"]], ["chat_003", "chat_004", "chat_005"])

        status, _, problem = self.request("/v1/conversations?cursor=broken")
        self.assertEqual(status, 400)
        self.assertEqual(problem["code"], "CURSOR_INVALID")

    def test_messages_continue_from_cursor_without_repeating_rows(self):
        status, _, first = self.request("/v1/messages?chat=chat_000&limit=3")
        self.assertEqual(status, 200)
        self.assertEqual([row["content"] for row in first["data"]], ["消息 00", "消息 01", "消息 02"])
        cursor = urllib.parse.quote(first["pagination"]["next_cursor"])
        status, _, second = self.request("/v1/messages?chat=chat_000&limit=3&cursor=" + cursor)
        self.assertEqual(status, 200)
        self.assertEqual([row["content"] for row in second["data"]], ["消息 03", "消息 04", "消息 05"])

    def test_analysis_is_idempotent_and_operation_can_be_polled(self):
        headers = {"Idempotency-Key": "workflow-1"}
        payload = {"question": "找出创业讨论", "timeout": 30}
        status, first_headers, first = self.request("/v1/analyses", "POST", payload, headers=headers)
        self.assertEqual(status, 202)
        self.assertEqual(first_headers["Location"], "/v1/operations/" + first["id"])

        status, _, duplicate = self.request("/v1/analyses", "POST", payload, headers=headers)
        self.assertEqual(status, 202)
        self.assertEqual(duplicate["id"], first["id"])

        operation = None
        for _ in range(50):
            status, _, operation = self.request("/v1/operations/" + first["id"])
            self.assertEqual(status, 200)
            if operation["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        self.assertEqual(operation["status"], "succeeded")
        self.assertEqual(operation["result"]["answer"], "完成")
        self.assertEqual(len(self.analysis_calls), 1)

        status, _, problem = self.request(
            "/v1/analyses",
            "POST",
            {"question": "不同问题", "timeout": 30},
            headers=headers,
        )
        self.assertEqual(status, 409)
        self.assertEqual(problem["code"], "IDEMPOTENCY_CONFLICT")


if __name__ == "__main__":
    unittest.main()
