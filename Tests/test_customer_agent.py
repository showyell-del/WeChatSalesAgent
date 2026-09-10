import unittest
from unittest.mock import patch

from agent_core.customer_agent import _question_time_window_days, ask_customer_agent


class CustomerAgentTests(unittest.TestCase):
    @patch("agent_core.customer_agent.KeychainStore")
    @patch("agent_core.customer_agent.AnalysisStore")
    @patch("agent_core.customer_agent.DeepSeekClient")
    def test_agent_analyzes_only_after_a_question_and_returns_known_customers(self, client, store, keychain):
        class Cursor:
            def __init__(self, one=None, many=None, rows=None):
                self.one, self.many, self.rows = one, many, rows or []

            def fetchone(self):
                return self.one

            def fetchall(self):
                return self.many or []

            def __iter__(self):
                return iter(self.rows)

        class Connection:
            def execute(self, sql, _params=()):
                if "active_account" in sql:
                    return Cursor(one={"value": "account"})
                if "SELECT username,display_name" in sql:
                    return Cursor(rows=[{"username": "a", "display_name": "甲", "latest_timestamp": 10}, {"username": "b", "display_name": "乙", "latest_timestamp": 20}])
                return Cursor(rows=[
                    {"username": "a", "evidence_id": "e1", "is_self": 0, "sender": "甲", "timestamp": 10, "message_type": "text", "content": "我们一起做创业项目"},
                    {"username": "b", "evidence_id": "e2", "is_self": 0, "sender": "乙", "timestamp": 20, "message_type": "text", "content": "普通聊天"},
                ])

        keychain.return_value.get.return_value = "key"
        store.return_value.conn = Connection()
        store.return_value.agent_model.return_value = "deepseek-v4-flash"
        store.return_value.published_corpus.return_value = {"corpus_id": "corpus"}
        store.return_value.packet.return_value = {"facts": [], "evidence": []}
        client.return_value.complete_json.side_effect = [
            {"choices": [{"message": {"content": '{"summary":"创业讨论","time_window_days":183,"topic_groups":[{"concept":"创业","terms":["创业项目"]}],"export_requested":true}'}}]},
            {"choices": [{"message": {"content": '{"decisions":[{"customer_id":"a","matched":true,"confidence":94,"reason":"双方讨论创业项目","intent_score":90,"need":"创业","obstacles":[],"suggested_action":"跟进","evidence_ids":["e1"]}]}'}}]},
            {"choices": [{"message": {"content": '{"decisions":[{"customer_id":"a","final_match":true,"reason":"证据充分","evidence_ids":["e1"]}]}'}}]},
        ]
        result = ask_customer_agent("state.db", "找有创业意向的朋友并导出 Excel")
        self.assertEqual([lead["customer_id"] for lead in result["leads"]], ["a"])
        self.assertTrue(result["export_requested"])
        self.assertEqual(client.return_value.complete_json.call_count, 3)
        self.assertEqual(client.return_value.complete_json.call_args_list[0].args[0], "deepseek-v4-flash")
        self.assertEqual(result["analysis_trace"][0], "理解任务 · 183 天")
        self.assertEqual(result["leads"][0]["evidence"][0]["evidence_id"], "e1")
        store.return_value.close.assert_called_once()

    def test_explicit_half_year_is_a_deterministic_time_window(self):
        self.assertEqual(_question_time_window_days("找出近半年和我讨论创业的人"), 183)
        self.assertEqual(_question_time_window_days("过去3个月聊过合作的人"), 93)
