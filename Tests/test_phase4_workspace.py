import hashlib
import json
import os
import sqlite3
import tempfile
import unittest

from agent_core.workspace_service import WorkspaceError, load_snapshot


SCHEMA = """
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
CREATE TABLE corpus_runs(corpus_id TEXT,account_id TEXT,status TEXT,published_at INTEGER);
CREATE TABLE corpus_conversations(corpus_id TEXT,status TEXT);
"""


def create_fixture(path):
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.execute(
        "INSERT INTO analysis_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("run_1", "corpus_1", "account_1", "published", "deepseek-v4-flash", "prompt.v1", "a" * 64,
         "lead.v1", "{}", 2, 1700000000, 1700100000, None, None, "0.01", "0.00004"),
    )
    leads = [
        ("run_1", "wxid_a", "小陈", 88, "高意向", 1700090000, '["ev_1"]', '["尚未确定时间"]',
         "确认周六体验时段", "您好，周六哪个时间方便到店体验？", '["ev_1"]',
         '[{"field":"mobile","value":"13800138000","evidence_id":"ev_1","extractor":"phone"},{"field":"explicit_need","value":"街舞体验课","evidence_id":"ev_1","extractor":"need"}]'),
        ("run_1", "wxid_b", "李女士", 61, "待激活", 1696000000, '["ev_2"]', '[]',
         "询问是否仍计划报名", "您好，之前咨询的街舞课还需要帮您安排吗？", '["ev_2"]',
         '[{"field":"explicit_need","value":"成人街舞课","evidence_id":"ev_2","extractor":"need"}]'),
    ]
    connection.executemany("INSERT INTO lead_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", leads)
    connection.executemany(
        "INSERT INTO ai_calls VALUES(?,?,?,?,?,?,?,?,?)",
        [("run_1", "wxid_a", "succeeded", 100, 20, 80, 40, 140, "0.00002"),
         ("run_1", "wxid_b", "succeeded", 100, 20, 80, 40, 140, "0.00002")],
    )
    connection.executemany(
        "INSERT INTO evidence VALUES(?,?,?,?,?)",
        [("ev_1", 0, "小陈", 1700090000, "想上街舞体验课，电话13800138000，周六方便"),
         ("ev_2", 0, "李女士", 1696000000, "想了解成人街舞课")],
    )
    connection.commit()
    connection.close()


class Phase4WorkspaceTests(unittest.TestCase):
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
            self.assertEqual(snapshot["leads"][0]["evidence"][0]["content"], "想上街舞体验课，电话13800138000，周六方便")

    def test_no_published_analysis_fails_without_empty_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            connection = sqlite3.connect(path)
            connection.executescript(SCHEMA)
            connection.execute("INSERT INTO corpus_runs VALUES('corpus_1','account_1','published',1)")
            connection.execute("INSERT INTO corpus_conversations VALUES('corpus_1','eligible')")
            connection.commit()
            connection.close()
            with self.assertRaises(WorkspaceError) as caught:
                load_snapshot(path, "account_1")
            self.assertEqual(caught.exception.code, "PUBLISHED_ANALYSIS_MISSING")
            self.assertIn("1 eligible", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
