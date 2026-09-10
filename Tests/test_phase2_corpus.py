import unittest
import os
import sqlite3
import tempfile
from decimal import Decimal

from agent_core.chatlog_client import ChatlogClient
from agent_core.analysis_store import AnalysisStore
from agent_core.corpus_builder import (
    build_corpus,
    has_effective_interaction,
    static_exclusion,
)
from agent_core.corpus_store import CorpusStore, evidence_id
from agent_core.extractors import extract_facts
from agent_core.sync_store import SyncStore
from unittest import mock


class FixtureClient(ChatlogClient):
    def __init__(self):
        pass

    def history_page(self, chat, since, until, limit, offset, is_self):
        source = {
            False: [
                {
                    "local_id": 1,
                    "timestamp": 10,
                    "sender": "客户",
                    "type": "text",
                    "content": "想体验街舞",
                },
                {
                    "local_id": 2,
                    "timestamp": 20,
                    "sender": "客户",
                    "type": "text",
                    "content": "电话13800138000",
                },
                {
                    "local_id": 3,
                    "timestamp": 30,
                    "sender": "客户",
                    "type": "text",
                    "content": "周六有时间",
                },
            ],
            True: [
                {
                    "local_id": 4,
                    "timestamp": 40,
                    "sender": "店主",
                    "type": "text",
                    "content": "可以预约",
                },
            ],
        }[is_self]
        page = source[offset : offset + limit]
        return {"total_count": len(source), "messages": page}


class Phase2CorpusTests(unittest.TestCase):
    def test_directional_pagination_has_no_loss(self):
        messages = FixtureClient().history("wxid_demo", 0, 100, page_size=2)
        self.assertEqual([item["local_id"] for item in messages], [1, 2, 3, 4])
        self.assertEqual(
            [item["is_self"] for item in messages], [False, False, False, True]
        )

    def test_static_filters_and_bidirectional_requirement(self):
        self.assertEqual(
            static_exclusion(
                {
                    "username": "gh_demo",
                    "chat": "公众号",
                    "chat_type": "private",
                    "is_group": 0,
                }
            ),
            "OFFICIAL_ACCOUNT",
        )
        self.assertEqual(
            static_exclusion(
                {
                    "username": "123@chatroom",
                    "chat": "群",
                    "chat_type": "group",
                    "is_group": 1,
                }
            ),
            "GROUP_CHAT",
        )
        self.assertTrue(
            has_effective_interaction(
                [{"type": "text", "content": "想了解"}],
                [{"type": "text", "content": "您好"}],
            )
        )
        self.assertFalse(
            has_effective_interaction([{"type": "text", "content": "广告"}], [])
        )

    def test_fact_extraction_keeps_evidence_binding(self):
        facts = extract_facts(
            "孩子10岁，在工业园区，想周六体验街舞，预算1000元，电话13800138000",
            "ev_demo",
        )
        fields = {item["field"] for item in facts}
        self.assertTrue(
            {
                "age",
                "region",
                "available_time",
                "explicit_need",
                "budget_cny",
                "mobile",
            }.issubset(fields)
        )
        self.assertTrue(all(item["evidence_id"] == "ev_demo" for item in facts))

    def test_fact_extraction_rejects_generic_time_region_and_wechat_noise(self):
        facts = extract_facts(
            "系统出款需要时间，所在城市投诉重灾区，到帐篷区的数据来自wxappTokenABC，这课程以后再看看",
            "ev_noise",
        )
        fields = {item["field"] for item in facts}
        self.assertNotIn("available_time", fields)
        self.assertNotIn("region", fields)
        self.assertNotIn("wechat_id", fields)
        self.assertNotIn("explicit_need", fields)

    def test_evidence_id_changes_with_direction_or_content(self):
        base = {
            "local_id": 1,
            "timestamp": 10,
            "sender": "客户",
            "type": "text",
            "content": "你好",
            "is_self": False,
        }
        first = evidence_id("account", "generation", "chat", base)
        changed = dict(base, is_self=True)
        self.assertNotEqual(
            first, evidence_id("account", "generation", "chat", changed)
        )
        changed = dict(base, content="您好")
        self.assertNotEqual(
            first, evidence_id("account", "generation", "chat", changed)
        )

    def test_corpus_conversation_schema_accepts_one_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            sync = SyncStore(path)
            sync.upsert_account("account", "/tmp/account", "verified")
            generation = sync.create_generation("account")
            sync.publish_generation(generation, "account")
            sync.close()
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            store = CorpusStore(connection)
            corpus = store.create_run(generation, "account", 0, 100)
            store.add_conversation(
                corpus, {"username": "chat", "chat": "客户"}, "eligible", "", 1, 1, 10
            )
            store.commit_conversation()
            self.assertEqual(store.run_counts(corpus)["eligible"], 1)
            connection.close()

    def test_non_text_metadata_never_enters_evidence_or_ai_packet(self):
        class MixedClient:
            def __init__(self, *_):
                pass

            def history(self, chat, since, until, page_size):
                return [
                    {
                        "local_id": 1,
                        "timestamp": 10,
                        "sender": "客户",
                        "type": "text",
                        "content": "想了解课程",
                        "is_self": False,
                    },
                    {
                        "local_id": 2,
                        "timestamp": 11,
                        "sender": "客户",
                        "type": "image",
                        "content": "<img aeskey='secret' cdnurl='private'/>",
                        "is_self": False,
                    },
                    {
                        "local_id": 3,
                        "timestamp": 12,
                        "sender": "店主",
                        "type": "text",
                        "content": "您好",
                        "is_self": True,
                    },
                ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            sync = SyncStore(path)
            sync.upsert_account("account", "/tmp/account", "verified")
            generation = sync.create_generation("account")
            sync.insert_sessions(
                generation,
                [{"username": "chat", "chat": "客户", "timestamp": 12}],
            )
            sync.publish_generation(generation, "account")
            sync.close()
            with mock.patch("agent_core.corpus_builder.ChatlogClient", MixedClient):
                result = build_corpus(path, "account", 0, 100)
            connection = sqlite3.connect(path)
            try:
                contents = [
                    row[0]
                    for row in connection.execute(
                        "SELECT content FROM evidence WHERE corpus_id=? ORDER BY timestamp",
                        (result["corpus_id"],),
                    )
                ]
            finally:
                connection.close()
            self.assertEqual(contents, ["想了解课程", "您好"])
            self.assertNotIn("cdnurl", " ".join(contents))

    def test_publishing_new_corpus_supersedes_old_published_analysis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            sync = SyncStore(path)
            sync.upsert_account("account", "/tmp/account", "verified")
            generation = sync.create_generation("account")
            sync.publish_generation(generation, "account")
            sync.close()
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            corpus_store = CorpusStore(connection)
            first = corpus_store.create_run(generation, "account", 0, 100)
            corpus_store.publish_run(first, "account")
            connection.close()
            analysis = AnalysisStore(path)
            run_id = analysis.create_run(
                first,
                "account",
                {
                    "model": "deepseek-v4-flash",
                    "prompt_version": "v",
                    "prompt_sha256": "a" * 64,
                    "schema_version": "v",
                    "config_snapshot": {},
                },
                0,
                Decimal("0"),
            )
            analysis.conn.execute(
                "UPDATE analysis_runs SET status='published',published_at=1 WHERE run_id=?",
                (run_id,),
            )
            analysis.conn.commit()
            analysis.close()
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            corpus_store = CorpusStore(connection)
            second = corpus_store.create_run(generation, "account", 0, 200)
            corpus_store.publish_run(second, "account")
            status = connection.execute(
                "SELECT status FROM analysis_runs WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            connection.close()
            self.assertEqual(status, "superseded")


if __name__ == "__main__":
    unittest.main()
