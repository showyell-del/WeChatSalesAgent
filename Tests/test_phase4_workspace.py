import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent_core.workspace_service import (
    WorkspaceError,
    load_snapshot,
    workspace_readiness,
)


SCHEMA = """
CREATE TABLE accounts(account_id TEXT,data_root TEXT,status TEXT,updated_at INTEGER);
CREATE TABLE app_state(key TEXT PRIMARY KEY,value TEXT,updated_at INTEGER);
CREATE TABLE generations(generation_id TEXT,account_id TEXT,status TEXT,published_at INTEGER);
CREATE TABLE analysis_runs(
 run_id TEXT, corpus_id TEXT, account_id TEXT, status TEXT, model TEXT,
 prompt_version TEXT, prompt_sha256 TEXT, schema_version TEXT,
 config_snapshot_json TEXT, candidate_count INTEGER, started_at INTEGER,
 published_at INTEGER, failure_code TEXT, failure_message TEXT,
 estimated_cost_usd TEXT, actual_cost_usd TEXT
);
CREATE TABLE lead_results(
 run_id TEXT, username TEXT, display_name TEXT, intent_score INTEGER,
 intent_band TEXT, recent_contact_ts INTEGER, evidence_ids_json TEXT,
 obstacles_json TEXT, suggested_action TEXT, draft_text TEXT,
 draft_evidence_ids_json TEXT, facts_json TEXT
);
CREATE TABLE ai_calls(
 run_id TEXT, username TEXT, status TEXT, prompt_tokens INTEGER,
 cache_hit_tokens INTEGER, cache_miss_tokens INTEGER, completion_tokens INTEGER,
 total_tokens INTEGER, actual_cost_usd TEXT
);
CREATE TABLE evidence(
 evidence_id TEXT, is_self INTEGER, sender TEXT, timestamp INTEGER, content TEXT
);
CREATE TABLE corpus_runs(corpus_id TEXT,generation_id TEXT,account_id TEXT,status TEXT,published_at INTEGER);
CREATE TABLE corpus_conversations(corpus_id TEXT,status TEXT);
"""


def create_fixture(path):
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.execute(
        "INSERT INTO accounts VALUES('account_1','/tmp/account_1','verified',1)"
    )
    connection.execute("INSERT INTO app_state VALUES('active_account','account_1',1)")
    connection.execute(
        "INSERT INTO generations VALUES('generation_1','account_1','published',1)"
    )
    connection.execute(
        "INSERT INTO corpus_runs VALUES('corpus_1','generation_1','account_1','published',1)"
    )
    connection.execute(
        "INSERT INTO analysis_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "run_1",
            "corpus_1",
            "account_1",
            "published",
            "deepseek-v4-flash",
            "prompt.v1",
            "a" * 64,
            "lead.v1",
            "{}",
            2,
            1700000000,
            1700100000,
            None,
            None,
            "0.01",
            "0.00004",
        ),
    )
    leads = [
        (
            "run_1",
            "wxid_a",
            "小陈",
            88,
            "高意向",
            1700090000,
            '["ev_1"]',
            '["尚未确定时间"]',
            "确认周六体验时段",
            "您好，周六哪个时间方便到店体验？",
            '["ev_1"]',
            '[{"field":"mobile","value":"13800138000","evidence_id":"ev_1","extractor":"phone"},{"field":"explicit_need","value":"街舞体验课","evidence_id":"ev_1","extractor":"need"}]',
        ),
        (
            "run_1",
            "wxid_b",
            "李女士",
            61,
            "待激活",
            1696000000,
            '["ev_2"]',
            "[]",
            "询问是否仍计划报名",
            "您好，之前咨询的街舞课还需要帮您安排吗？",
            '["ev_2"]',
            '[{"field":"explicit_need","value":"成人街舞课","evidence_id":"ev_2","extractor":"need"}]',
        ),
    ]
    connection.executemany(
        "INSERT INTO lead_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", leads
    )
    connection.executemany(
        "INSERT INTO ai_calls VALUES(?,?,?,?,?,?,?,?,?)",
        [
            ("run_1", "wxid_a", "succeeded", 100, 20, 80, 40, 140, "0.00002"),
            ("run_1", "wxid_b", "succeeded", 100, 20, 80, 40, 140, "0.00002"),
        ],
    )
    connection.executemany(
        "INSERT INTO evidence VALUES(?,?,?,?,?)",
        [
            (
                "ev_1",
                0,
                "小陈",
                1700090000,
                "想上街舞体验课，电话13800138000，周六方便",
            ),
            ("ev_2", 0, "李女士", 1696000000, "想了解成人街舞课"),
        ],
    )
    connection.commit()
    connection.close()


class Phase4WorkspaceTests(unittest.TestCase):
    def test_native_app_enforces_sip_preflight(self):
        source = (Path(__file__).parents[1] / "app" / "Phase0App" / "main.m").read_text(
            encoding="utf-8"
        )
        self.assertIn("- (BOOL)isSIPDisabled", source)
        self.assertIn('@"/usr/bin/csrutil"', source)
        self.assertIn("if (![self isSIPDisabled])", source)
        self.assertIn("关闭 SIP 指引", source)

    def test_first_launch_without_database_has_typed_empty_readiness(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "missing.sqlite3")
            self.assertEqual(workspace_readiness(path)["account_id"], "")
            with self.assertRaises(WorkspaceError) as caught:
                load_snapshot(path)
            self.assertEqual(caught.exception.code, "PUBLISHED_ANALYSIS_MISSING")

    def test_snapshot_metrics_and_evidence_share_one_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            create_fixture(path)
            snapshot = load_snapshot(path, "account_1")
            self.assertEqual(snapshot["run"]["run_id"], "run_1")
            self.assertEqual(snapshot["metrics"]["customer_total"], 2)
            self.assertEqual(snapshot["metrics"]["high_intent"], 1)
            self.assertEqual(snapshot["metrics"]["activation_needed"], 1)
            self.assertEqual(snapshot["leads"][0]["contact"], "13800138000")
            self.assertEqual(
                snapshot["leads"][0]["evidence"][0]["content"],
                "想上街舞体验课，电话13800138000，周六方便",
            )

    def test_no_published_analysis_fails_without_empty_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            connection = sqlite3.connect(path)
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT INTO accounts VALUES('account_1','/tmp/account_1','verified',1)"
            )
            connection.execute(
                "INSERT INTO app_state VALUES('active_account','account_1',1)"
            )
            connection.execute(
                "INSERT INTO generations VALUES('generation_1','account_1','published',1)"
            )
            connection.execute(
                "INSERT INTO corpus_runs VALUES('corpus_1','generation_1','account_1','published',1)"
            )
            connection.execute(
                "INSERT INTO corpus_conversations VALUES('corpus_1','eligible')"
            )
            connection.commit()
            connection.close()
            with self.assertRaises(WorkspaceError) as caught:
                load_snapshot(path, "account_1")
            self.assertEqual(caught.exception.code, "PUBLISHED_ANALYSIS_MISSING")
            self.assertIn("1 eligible", caught.exception.message)
            readiness = workspace_readiness(path)
            self.assertEqual(readiness["account_id"], "account_1")
            self.assertEqual(readiness["eligible_conversations"], 1)
            self.assertEqual(readiness["published_runs"], 0)

    def test_first_sync_is_ready_before_ai_tables_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE accounts(account_id TEXT,data_root TEXT,status TEXT,updated_at INTEGER);
                CREATE TABLE app_state(key TEXT PRIMARY KEY,value TEXT,updated_at INTEGER);
                CREATE TABLE generations(generation_id TEXT,account_id TEXT,status TEXT,published_at INTEGER);
                CREATE TABLE corpus_runs(corpus_id TEXT,generation_id TEXT,account_id TEXT,status TEXT,published_at INTEGER);
                CREATE TABLE corpus_conversations(corpus_id TEXT,status TEXT);
                """
            )
            connection.execute(
                "INSERT INTO accounts VALUES('account_1','/tmp/account_1','verified',1)"
            )
            connection.execute(
                "INSERT INTO app_state VALUES('active_account','account_1',1)"
            )
            connection.execute(
                "INSERT INTO generations VALUES('generation_1','account_1','published',1)"
            )
            connection.execute(
                "INSERT INTO corpus_runs VALUES('corpus_1','generation_1','account_1','published',1)"
            )
            connection.execute(
                "INSERT INTO corpus_conversations VALUES('corpus_1','eligible')"
            )
            connection.commit()
            connection.close()

            readiness = workspace_readiness(path)
            self.assertEqual(readiness["account_id"], "account_1")
            self.assertEqual(readiness["eligible_conversations"], 1)
            self.assertEqual(readiness["published_runs"], 0)
            self.assertEqual(readiness["lead_results"], 0)
            with self.assertRaises(WorkspaceError) as caught:
                load_snapshot(path)
            self.assertEqual(caught.exception.code, "PUBLISHED_ANALYSIS_MISSING")
            self.assertIn("1 eligible", caught.exception.message)

    def test_active_account_never_falls_back_to_another_accounts_analysis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            create_fixture(path)
            connection = sqlite3.connect(path)
            connection.execute(
                "INSERT INTO accounts VALUES('account_2','/tmp/account_2','verified',2)"
            )
            connection.execute(
                "UPDATE app_state SET value='account_2',updated_at=2 WHERE key='active_account'"
            )
            connection.execute(
                "INSERT INTO generations VALUES('generation_2','account_2','published',2)"
            )
            connection.commit()
            connection.close()
            readiness = workspace_readiness(path)
            self.assertEqual(readiness["account_id"], "account_2")
            self.assertEqual(readiness["published_runs"], 0)
            with self.assertRaises(WorkspaceError) as caught:
                load_snapshot(path)
            self.assertEqual(caught.exception.code, "PUBLISHED_ANALYSIS_MISSING")

    def test_old_analysis_is_rejected_when_generation_or_corpus_is_not_current(self):
        for stale_layer in ("generation", "corpus"):
            with (
                self.subTest(stale_layer=stale_layer),
                tempfile.TemporaryDirectory() as tmpdir,
            ):
                path = os.path.join(tmpdir, "state.sqlite3")
                create_fixture(path)
                connection = sqlite3.connect(path)
                if stale_layer == "generation":
                    connection.execute(
                        "UPDATE generations SET status='old' WHERE generation_id='generation_1'"
                    )
                    connection.execute(
                        "INSERT INTO generations VALUES('generation_2','account_1','published',2)"
                    )
                else:
                    connection.execute(
                        "UPDATE corpus_runs SET status='old' WHERE corpus_id='corpus_1'"
                    )
                    connection.execute(
                        "INSERT INTO corpus_runs VALUES('corpus_2','generation_1','account_1','published',2)"
                    )
                connection.commit()
                connection.close()
                with self.assertRaises(WorkspaceError) as caught:
                    load_snapshot(path, "account_1")
                self.assertEqual(caught.exception.code, "PUBLISHED_ANALYSIS_MISSING")


if __name__ == "__main__":
    unittest.main()
