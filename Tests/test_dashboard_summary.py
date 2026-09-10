import json
import unittest
from unittest import mock

from agent_core.dashboard_summary import generate_dashboard_summary


class DashboardSummaryTests(unittest.TestCase):
    def test_uses_existing_deepseek_configuration_and_key(self):
        store = mock.Mock()
        store.config.return_value = {
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "max_tokens": 1400,
            "business_profile": {
                "business_name": "business",
                "products": ["service"],
                "lead_keywords": ["price"],
                "external_api_data_transfer_approved": True,
                "minor_data_approved": False,
            },
        }
        response = {"choices": [{"message": {"content": json.dumps({"summary": "summary"})}}]}
        with mock.patch("agent_core.dashboard_summary.AnalysisStore", return_value=store), mock.patch(
            "agent_core.dashboard_summary.KeychainStore"
        ) as keychain, mock.patch("agent_core.dashboard_summary.DeepSeekClient") as client:
            keychain.return_value.get.return_value = "sk-test"
            client.return_value.complete_json.return_value = response
            self.assertEqual(generate_dashboard_summary("db", {"topics": []}), "summary")
        client.assert_called_once_with("sk-test", "https://api.deepseek.com", timeout=120)
