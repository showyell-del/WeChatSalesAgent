import os
import tempfile
import unittest
import sqlite3
import subprocess
from pathlib import Path

from agent_core.chatlog_client import ChatlogClient, derive_account_ids
from agent_core.sync_cli import DEFAULT_CHATLOG_BIN, select_account_id
from agent_core.sync_cli import command_sync
from types import SimpleNamespace
from agent_core.sync_store import SyncStore
from agent_core.chatlog_runtime import primary_db_paths, verify_runtime_account
from agent_core.chatlog_client import ChatlogError
from agent_core.chatlog_runtime import ChatlogRuntime
from unittest import mock


class Phase1SyncTests(unittest.TestCase):
    def test_sync_switches_selected_historical_account_before_reading(self):
        class Client:
            calls = 0

            def __init__(self, *_):
                pass

            def health(self):
                return {"status": "ok"}

            def databases(self):
                Client.calls += 1
                account = "wxid_current" if Client.calls == 1 else "wxid_history"
                return {
                    "message": [
                        f"/source/xwechat_files/{account}/db_storage/message/message_0.db"
                    ]
                }

            def all_sessions(self, page_size):
                return [{"username": "customer"}]

        class Runtime:
            switched = []

            def __init__(self, *_):
                pass

            def list_accounts(self):
                return [{"account": "wxid_history"}]

            def switch_account(self, account):
                Runtime.switched.append(account)
                return {"account": account}

        store = mock.MagicMock()
        store.create_generation.return_value = "generation"
        args = SimpleNamespace(
            addr="127.0.0.1:5030",
            timeout=1,
            chatlog_bin="chatlog",
            db="state.sqlite3",
            account_id="wxid_history",
            limit=100,
        )
        with (
            mock.patch("agent_core.sync_cli.ChatlogClient", Client),
            mock.patch("agent_core.sync_cli.ChatlogRuntime", Runtime),
            mock.patch("agent_core.sync_cli.SyncStore", return_value=store),
            mock.patch(
                "agent_core.sync_cli.prepare_account",
                return_value=(
                    {"message": ["db"]},
                    "/root",
                    {"verified_databases": ["db"]},
                ),
            ),
        ):
            self.assertEqual(command_sync(args), 0)
        self.assertEqual(Runtime.switched, ["wxid_history"])

    def test_chatlog_action_timeout_is_typed(self):
        runtime = ChatlogRuntime("/tmp/chatlog")
        with mock.patch(
            "agent_core.chatlog_runtime.subprocess.run",
            side_effect=subprocess.TimeoutExpired("chatlog", 20),
        ):
            with self.assertRaises(ChatlogError) as caught:
                runtime.status()
        self.assertEqual(caught.exception.code, "CHATLOG_ACTION_TIMEOUT")

    def test_runtime_database_path_cannot_escape_db_storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = os.path.join(tmpdir, "wxid_demo")
            os.makedirs(os.path.join(work_dir, "db_storage"))
            with self.assertRaises(ChatlogError) as caught:
                verify_runtime_account(
                    {
                        "account": "wxid_demo",
                        "data_key": "a" * 64,
                        "work_dir": work_dir,
                    },
                    "wxid_demo",
                    {
                        "message": [
                            "/source/xwechat_files/wxid_demo/db_storage/../../outside.db"
                        ]
                    },
                )
        self.assertEqual(caught.exception.code, "DATABASE_PATH_INVALID")

    def test_runtime_database_map_cannot_mix_accounts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = os.path.join(tmpdir, "wxid_selected")
            os.makedirs(os.path.join(work_dir, "db_storage", "message"))
            with self.assertRaises(ChatlogError) as caught:
                verify_runtime_account(
                    {
                        "account": "wxid_selected",
                        "data_key": "a" * 64,
                        "work_dir": work_dir,
                    },
                    "wxid_selected",
                    {
                        "message": [
                            "/source/xwechat_files/wxid_other/db_storage/message/message_0.db"
                        ]
                    },
                )
        self.assertEqual(caught.exception.code, "DATABASE_ACCOUNT_PATH_MISMATCH")

    def test_default_chatlog_binary_is_present_and_executable(self):
        binary = Path(DEFAULT_CHATLOG_BIN)
        self.assertTrue(binary.is_file())
        self.assertTrue(os.access(binary, os.X_OK))

    def test_derive_account_id_from_db_paths(self):
        db_map = {
            "message": [
                "/Users/me/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_demo/db_storage/message/message_1.db"
            ]
        }
        self.assertEqual(derive_account_ids(db_map), ["wxid_demo"])

    def test_sync_requires_explicit_selection_for_multiple_accounts(self):
        with self.assertRaisesRegex(RuntimeError, "Select exactly one"):
            select_account_id(["wxid_a", "wxid_b"])
        self.assertEqual(select_account_id(["wxid_a", "wxid_b"], "wxid_b"), "wxid_b")

    def test_session_pagination_reads_every_page_without_duplicates(self):
        class Client(ChatlogClient):
            def sessions(self, limit=2, offset=0):
                assert offset == 0
                return [{"username": name} for name in "abcd"][:limit]

        self.assertEqual(
            [item["username"] for item in Client().all_sessions(page_size=2)],
            ["a", "b", "c", "d"],
        )

    def test_full_sessions_rejects_disappearing_rows(self):
        client = ChatlogClient()
        with mock.patch.object(client, "sessions", side_effect=[
            [{"username": "a"}, {"username": "b"}],
            [{"username": "b"}, {"username": "c"}, {"username": "d"}],
        ]):
            with self.assertRaises(ChatlogError) as caught:
                client.all_sessions(page_size=2)
            self.assertEqual(caught.exception.code, "CHATLOG_SESSIONS_CHANGED")

    def test_full_sessions_has_no_5000_limit(self):
        client = ChatlogClient()
        rows = [{"username": str(i)} for i in range(6001)]
        with mock.patch.object(client, "sessions", side_effect=lambda limit, **kw: rows[:limit]):
            self.assertEqual(client.all_sessions(page_size=500), rows)

    def test_publish_generation_marks_previous_old(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SyncStore(os.path.join(tmpdir, "state.sqlite3"))
            try:
                store.upsert_account("wxid_demo", "/tmp/wxid_demo", "discovered")
                first = store.create_generation("wxid_demo")
                store.publish_generation(first, "wxid_demo")
                second = store.create_generation("wxid_demo")
                store.publish_generation(second, "wxid_demo")
                statuses = {
                    item["generation_id"]: item["status"]
                    for item in store.status()["generations"]
                }
                self.assertEqual(statuses[first], "old")
                self.assertEqual(statuses[second], "published")
            finally:
                store.close()

    def test_new_generation_invalidates_downstream_published_chain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            store = SyncStore(path)
            store.upsert_account("wxid_demo", "/tmp/wxid_demo", "verified")
            first = store.create_generation("wxid_demo")
            store.publish_generation(first, "wxid_demo")
            store.conn.execute(
                "CREATE TABLE corpus_runs(corpus_id TEXT,generation_id TEXT,account_id TEXT,status TEXT)"
            )
            store.conn.execute(
                "CREATE TABLE analysis_runs(run_id TEXT,account_id TEXT,status TEXT)"
            )
            store.conn.execute(
                "INSERT INTO corpus_runs VALUES('corpus_1',?,'wxid_demo','published')",
                (first,),
            )
            store.conn.execute(
                "INSERT INTO analysis_runs VALUES('run_1','wxid_demo','published')"
            )
            store.conn.commit()
            second = store.create_generation("wxid_demo")
            store.publish_generation(second, "wxid_demo")
            self.assertEqual(
                store.conn.execute(
                    "SELECT status FROM corpus_runs WHERE corpus_id='corpus_1'"
                ).fetchone()[0],
                "old",
            )
            self.assertEqual(
                store.conn.execute(
                    "SELECT status FROM analysis_runs WHERE run_id='run_1'"
                ).fetchone()[0],
                "superseded",
            )
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
                "session": [
                    "/source/xwechat_files/wxid_demo/db_storage/session/session.db"
                ],
                "contact": [
                    "/source/xwechat_files/wxid_demo/db_storage/contact/contact_fts.db"
                ],
            }
            self.assertEqual(
                primary_db_paths(db_map),
                ["/source/xwechat_files/wxid_demo/db_storage/session/session.db"],
            )
            result = verify_runtime_account(
                {
                    "account": "wxid_demo",
                    "data_key": "a" * 64,
                    "work_dir": work_dir,
                },
                "wxid_demo",
                db_map,
            )
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
                statuses = {
                    item["generation_id"]: item["status"]
                    for item in store.status()["generations"]
                }
                self.assertEqual(statuses[published], "published")
                self.assertEqual(statuses[failed], "failed")
            finally:
                store.close()

    def test_unexpected_sync_error_fails_staging_and_preserves_published(self):
        class Client:
            def __init__(self, *_):
                pass

            def health(self):
                return {"status": "ok"}

            def databases(self):
                return {
                    "message": [
                        "/source/xwechat_files/wxid_demo/db_storage/message/message_0.db"
                    ]
                }

            def all_sessions(self, page_size):
                return [{"username": "customer"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            existing = SyncStore(path)
            existing.upsert_account("wxid_demo", "/tmp/wxid_demo", "verified")
            published = existing.create_generation("wxid_demo")
            existing.publish_generation(published, "wxid_demo")
            existing.close()
            args = SimpleNamespace(
                addr="127.0.0.1:5030",
                timeout=1,
                chatlog_bin="chatlog",
                db=path,
                account_id="wxid_demo",
                limit=100,
            )
            with (
                mock.patch("agent_core.sync_cli.ChatlogClient", Client),
                mock.patch("agent_core.sync_cli.ChatlogRuntime"),
                mock.patch(
                    "agent_core.sync_cli.prepare_account",
                    return_value=(
                        Client().databases(),
                        "/tmp/wxid_demo",
                        {"verified_databases": ["message/message_0.db"]},
                    ),
                ),
                mock.patch.object(
                    SyncStore,
                    "insert_sessions",
                    side_effect=sqlite3.OperationalError("write failed"),
                ),
            ):
                self.assertEqual(command_sync(args), 1)
            recovered = SyncStore(path)
            try:
                statuses = {
                    item["generation_id"]: item["status"]
                    for item in recovered.status()["generations"]
                }
                self.assertEqual(statuses[published], "published")
                self.assertEqual(
                    [status for key, status in statuses.items() if key != published],
                    ["failed"],
                )
            finally:
                recovered.close()


if __name__ == "__main__":
    unittest.main()
