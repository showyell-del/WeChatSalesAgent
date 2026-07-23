import json
import os
import tempfile
import unittest
from pathlib import Path

from Tests.test_phase4_workspace import create_fixture
from agent_core.send_store import SendError, SendStore
from agent_core.send_certification import certified_capabilities, required_send_types, uncertified_required_types
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

    def test_attachment_audit_records_hash_size_and_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            create_fixture(path)
            attachment = Path(tmpdir) / "poster.png"
            attachment.write_bytes(b"street dance poster")
            store = SendStore(path)
            try:
                batch = store.create_batch("account_1", "测试", attachments=[str(attachment)])
                self.assertEqual(batch["attachments"][0]["name"], "poster.png")
                self.assertEqual(batch["attachments"][0]["media_type"], "image")
                self.assertEqual(batch["attachments"][0]["size_bytes"], len(b"street dance poster"))
                self.assertEqual(len(batch["attachments"][0]["sha256"]), 64)
            finally:
                store.close()

    def test_certification_registry_reports_required_uncertified_types(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            create_fixture(path)
            attachment = Path(tmpdir) / "lesson.mov"
            attachment.write_bytes(b"video")
            store = SendStore(path)
            try:
                batch = store.create_batch("account_1", "测试", attachments=[str(attachment)])
                self.assertEqual(required_send_types(batch), ["text", "video"])
                self.assertFalse(certified_capabilities(store.conn)["text"]["certified"])
                self.assertEqual(uncertified_required_types(store.conn, batch), ["text", "video"])
            finally:
                store.close()

    def test_missing_attachment_fails_before_batch_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            create_fixture(path)
            store = SendStore(path)
            try:
                with self.assertRaises(SendError) as caught:
                    store.create_batch("account_1", "测试", attachments=[os.path.join(tmpdir, "missing.mp4")])
                self.assertEqual(caught.exception.code, "SEND_ATTACHMENT_NOT_FOUND")
                self.assertEqual(store.list_batches("account_1"), [])
            finally:
                store.close()

    def test_cancel_recipient_preserves_remaining_queue_and_block_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            create_fixture(path)
            store = SendStore(path)
            try:
                batch = store.create_batch("account_1", "测试")
                cancelled = store.cancel_recipient(batch["batch_id"], "wxid_a")
                statuses = {item["customer_id"]: item["status"] for item in cancelled["recipients"]}
                self.assertEqual(statuses["wxid_a"], "cancelled")
                self.assertEqual(statuses["wxid_b"], "queued")
                self.assertEqual(cancelled["status"], "queued")
                blocked = store.block_batch(batch["batch_id"], "NATIVE_SEND_ADAPTER_NOT_CERTIFIED", "not certified")
                self.assertEqual(blocked["failed"], 1)
                statuses = {item["customer_id"]: item["status"] for item in blocked["recipients"]}
                self.assertEqual(statuses["wxid_a"], "cancelled")
                self.assertEqual(statuses["wxid_b"], "blocked")
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
