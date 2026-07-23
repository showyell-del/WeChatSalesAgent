import os
import tempfile
import unittest
import sqlite3

from agent_core.chatlog_client import derive_account_ids
from agent_core.sync_store import SyncStore
from agent_core.chatlog_runtime import primary_db_paths, verify_runtime_account


class Phase1SyncTests(unittest.TestCase):
    def test_derive_account_id_from_db_paths(self):
        db_map = {
            "message": [
                "/Users/me/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_demo/db_storage/message/message_1.db"
            ]
        }
        self.assertEqual(derive_account_ids(db_map), ["wxid_demo"])

    def test_publish_generation_marks_previous_old(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SyncStore(os.path.join(tmpdir, "state.sqlite3"))
            try:
                store.upsert_account("wxid_demo", "/tmp/wxid_demo", "discovered")
                first = store.create_generation("wxid_demo")
                store.publish_generation(first, "wxid_demo")
                second = store.create_generation("wxid_demo")
                store.publish_generation(second, "wxid_demo")
                statuses = {item["generation_id"]: item["status"] for item in store.status()["generations"]}
                self.assertEqual(statuses[first], "old")
                self.assertEqual(statuses[second], "published")
            finally:
                store.close()

    def test_primary_db_verification_never_requires_fts_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = os.path.join(tmpdir, "wxid_demo")
            db_dir = os.path.join(work_dir, "db_storage", "session")
            os.makedirs(db_dir)
            db_path = os.path.join(db_dir, "session.db")
            connection = sqlite3.connect(db_path)
            connection.execute("CREATE TABLE sample(value TEXT)")
            connection.close()
            db_map = {
                "session": ["/source/xwechat_files/wxid_demo/db_storage/session/session.db"],
                "contact": ["/source/xwechat_files/wxid_demo/db_storage/contact/contact_fts.db"],
            }
            self.assertEqual(primary_db_paths(db_map), ["/source/xwechat_files/wxid_demo/db_storage/session/session.db"])
            result = verify_runtime_account({
                "account": "wxid_demo",
                "data_key": "a" * 64,
                "work_dir": work_dir,
            }, "wxid_demo", db_map)
            self.assertEqual(result["verified_databases"], ["session/session.db"])

    def test_failed_staging_generation_does_not_replace_published_generation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SyncStore(os.path.join(tmpdir, "state.sqlite3"))
            try:
                store.upsert_account("wxid_demo", "/tmp/wxid_demo", "discovered")
                published = store.create_generation("wxid_demo")
                store.publish_generation(published, "wxid_demo")
                failed = store.create_generation("wxid_demo")
                store.fail_generation(failed, "READ_FAILED", "fixture")
                statuses = {item["generation_id"]: item["status"] for item in store.status()["generations"]}
                self.assertEqual(statuses[published], "published")
                self.assertEqual(statuses[failed], "failed")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
