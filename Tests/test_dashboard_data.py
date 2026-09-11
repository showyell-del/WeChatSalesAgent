import unittest
from unittest import mock

from agent_core.dashboard_data import load_dashboard


class DashboardDataTests(unittest.TestCase):
    def test_dashboard_aggregates_groups_and_speakers(self):
        client = mock.Mock()
        client.all_sessions.return_value = [
            {"username": "brandsessionholder", "chat": "brandsessionholder", "is_group": False},
            {"username": "private", "chat": "Private", "is_group": False},
            {"username": "g1", "chat": "Group 1", "is_group": True},
            {"username": "g2", "chat": "Group 2", "is_group": True},
        ]
        client.databases.return_value = {"message": ["/tmp/biz_message_0.db"]}
        client.get_json.side_effect = [
            {"chat": "Private", "total": 10, "sent_count": 4, "received_count": 6, "active_days": 2, "by_hour": []},
            {"chat": "Group 1", "total": 20, "active_senders": 3, "active_days": 2, "by_hour": [{"hour": 9, "count": 8}], "by_type": [{"type": "text", "count": 7}, {"type": "image", "count": 3}], "top_senders": [{"sender": "A", "count": 7}]},
            {"chat": "Group 2", "total": 30, "active_senders": 4, "active_days": 3, "by_hour": [{"hour": 18, "count": 9}], "by_type": [], "top_senders": [{"sender": "A", "count": 5}, {"sender": "B", "count": 4}]},
            {"daily": [{"date": "2026-08-01", "count": 50}], "topics": [{"topic": "AI", "count": 8}], "mentions": [{"name": "A", "count": 3}]},
        ]
        with mock.patch("agent_core.dashboard_data.ChatlogClient", return_value=client), mock.patch("agent_core.dashboard_data.daily_trend", return_value=[{"date": "2026-08-01", "count": 50}]):
            result = load_dashboard(time_range="last-30d")
        self.assertEqual(result["overview"], {"messages": 50, "groups": 2, "active_sender_slots": 7})
        self.assertEqual(result["leaderboard"][0]["count"], 12)
        self.assertEqual(result["groups"][1]["peak_hour"], 18)
        self.assertEqual(result["daily"], [{"date": "2026-08-01", "count": 50}])
        self.assertEqual(
            result["message_types"],
            [{"type": "text", "count": 7}, {"type": "image", "count": 3}],
        )
        self.assertEqual(len(result["by_hour"]), 24)
        self.assertEqual(result["databases"], [{"kind": "message", "path": "/tmp/biz_message_0.db"}])
        self.assertEqual(result["selected_group"]["chat"], "Group 1")
        self.assertEqual(
            [row["username"] for row in result["private_sessions"]], ["private"]
        )
        self.assertEqual(
            [row["username"] for row in result["group_sessions"]], ["g1", "g2"]
        )
        self.assertEqual(result["groups"][0]["type_summary"], "text 70% · image 30%")

    def test_today_uses_chatlog_supported_window(self):
        client = mock.Mock()
        client.all_sessions.return_value = [
            {"username": "private", "chat": "Private", "is_group": False}
        ]
        client.databases.return_value = {}
        client.get_json.side_effect = [
            {"chat": "Private", "total": 1, "by_hour": []},
            {"daily": [], "topics": [], "mentions": []},
        ]
        with mock.patch("agent_core.dashboard_data.ChatlogClient", return_value=client), mock.patch("agent_core.dashboard_data.daily_trend", return_value=[]):
            load_dashboard(time_range="today")
        self.assertEqual(client.get_json.call_args_list[0].args[1]["time"], "last-1d")
