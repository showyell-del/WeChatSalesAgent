import unittest
from unittest import mock

from agent_core.chatlog_client import ChatlogError
from agent_core.message_search import list_sessions, search_messages


class MessageSearchTests(unittest.TestCase):
    def test_sessions_are_projected_for_native_picker(self):
        client = mock.Mock()
        client.all_sessions.return_value = [
            {"username": "alice", "chat": "Alice", "is_group": False, "time": "08-02"},
            {"username": "group@chatroom", "chat": "Group", "is_group": True, "time": "08-01"},
        ]
        with mock.patch("agent_core.message_search.ChatlogClient", return_value=client):
            self.assertEqual(
                list_sessions(),
                [
                    {"username": "alice", "display_name": "Alice", "is_group": False, "time": "08-02"},
                    {"username": "group@chatroom", "display_name": "Group", "is_group": True, "time": "08-01"},
                ],
            )

    def test_search_merges_real_directions_and_sorts_newest_first(self):
        client = mock.Mock()
        client.get_json.side_effect = [
            {"total_count": 1, "messages": [{"timestamp": 10}]},
            {"total_count": 1, "messages": [{"timestamp": 10, "local_id": 1, "sender": "Alice", "type": "text", "content": "in"}]},
            {"total_count": 1, "messages": [{"timestamp": 20}]},
            {"total_count": 1, "messages": [{"timestamp": 20, "local_id": 2, "sender": "Me", "type": "text", "content": "out"}]},
        ]
        with mock.patch("agent_core.message_search.ChatlogClient", return_value=client):
            result = search_messages("alice", 1, 30, keyword="price", msg_type="49", sub_type="57", limit=10)
        self.assertEqual([item["direction"] for item in result["messages"]], ["我方", "对方"])
        self.assertEqual(result["matched_total"], 2)
        self.assertEqual(client.get_json.call_count, 4)
        self.assertEqual(client.get_json.call_args_list[0].args[1]["keyword"], "price")
        self.assertEqual(client.get_json.call_args_list[0].args[1]["sub_type"], "57")

    def test_search_rejects_invalid_time_and_limit(self):
        with self.assertRaises(ChatlogError):
            search_messages("alice", 10, 10)
        with self.assertRaises(ChatlogError):
            search_messages("alice", 1, 10, limit=1001)
