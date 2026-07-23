import json
import os
import tempfile
import unittest

from Tests.test_phase4_workspace import create_fixture
from agent_core.send_store import SendError, SendStore
from agent_core.workspace_service import load_snapshot


class Phase6SendTests(unittest.TestCase):
    def test_create_batch_selects_actionable_leads_and_updates_workspace_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            create_fixture(path)
            store = SendStore(path)
            try:
                batch = store.create_batch("account_1", "你好 {客户}，这周还方便来体验吗？")
                self.assertEqual(batch["total"], 2)
                self.assertEqual(batch["status"], "queued")
                self.assertEqual(batch["recipients"][0]["status"], "queued")
                snapshot = load_snapshot(path, "account_1")
                statuses = {lead["customer_id"]: lead["send_status"] for lead in snapshot["leads"]}
                self.assertEqual(statuses["wxid_a"], "已排队")
                self.assertEqual(statuses["wxid_b"], "已排队")
            finally:
                store.close()

    def test_dispatch_blocks_without_certified_native_adapter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            create_fixture(path)
            store = SendStore(path)
            try:
                batch = store.create_batch("account_1", "测试")
                blocked = store.block_batch(batch["batch_id"], "NATIVE_SEND_ADAPTER_NOT_CERTIFIED", "not certified")
                self.assertEqual(blocked["status"], "blocked")
                self.assertEqual(blocked["failed"], 2)
                self.assertTrue(all(item["status"] == "blocked" for item in blocked["recipients"]))
                snapshot = load_snapshot(path, "account_1")
                self.assertEqual(snapshot["leads"][0]["send_status"], "发送阻断")
            finally:
                store.close()

    def test_empty_text_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            create_fixture(path)
            store = SendStore(path)
            try:
                with self.assertRaises(SendError) as caught:
                    store.create_batch("account_1", " ")
                self.assertEqual(caught.exception.code, "SEND_TEXT_EMPTY")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
