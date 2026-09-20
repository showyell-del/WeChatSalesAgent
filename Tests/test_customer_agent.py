import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock
from unittest.mock import patch

from agent_core.analysis_store import AnalysisStore
from agent_core.corpus_store import CorpusStore, evidence_id
from agent_core.customer_agent import (
    DEFAULT_TIME_WINDOW_DAYS,
    CustomerAgentError,
    _active_account,
    _conversation_stats,
    _group_message_chunks,
    _lead_from_match,
    _name_matches,
    _plan_query,
    _question_group_names,
    _question_time_window_days,
    _rank_conversations,
    _time_window_display,
    _validated_final_evidence,
    ask_customer_agent,
    refresh_saved_analysis,
)


class CustomerAgentTests(unittest.TestCase):
    @patch("agent_core.customer_agent.ChatlogClient")
    @patch("agent_core.customer_agent.DeepSeekClient")
    @patch("agent_core.customer_agent.AnalysisStore")
    @patch("agent_core.customer_agent.KeychainStore")
    def test_named_group_topic_analysis_reads_only_the_target_group_messages(
        self, keychain, store_class, deepseek_class, chatlog_class
    ):
        class Cursor:
            def __init__(self, one=None, rows=None):
                self.one = one
                self.rows = rows or []

            def fetchone(self):
                return self.one

            def __iter__(self):
                return iter(self.rows)

        class Connection:
            private_query_seen = False

            def execute(self, sql, _params=()):
                if "active_account" in sql:
                    return Cursor(one={"value": "account"})
                if "min(e.timestamp)" in sql:
                    return Cursor(one={"first_ts": 100, "last_ts": 200, "evidence_count": 2})
                if "FROM sessions" in sql:
                    raise AssertionError("群聊分析不得使用已发布世代中的过期会话列表")
                if "SELECT username,display_name" in sql:
                    self.private_query_seen = True
                return Cursor(rows=[])

        messages = [
            {"local_id": 1, "timestamp": 100, "sender": "甲", "type": "text", "content": "大家在讨论 AI Agent 产品", "is_self": False},
            {"local_id": 2, "timestamp": 200, "sender": "乙", "type": "text", "content": "重点是智能体落地和工作流", "is_self": False},
        ]
        evidence_ids = [
            evidence_id("account", "generation", "group@chatroom", item)
            for item in messages
        ]
        plan = {
            "task_type": "topic_analysis",
            "summary": "分析目标群热门话题",
            "subject_names": [],
            "requested_dimensions": ["热门话题", "讨论重点"],
            "output_title": "破壳群热门话题",
            "conversation_scope": "group",
            "target_conversations": ["AI+🌞破壳HATCH"],
            "time_window_days": DEFAULT_TIME_WINDOW_DAYS,
            "topic_groups": [{"concept": "群聊话题", "terms": ["热门话题"]}],
            "export_requested": False,
        }
        responses = [
            {"choices": [{"message": {"content": json.dumps(plan, ensure_ascii=False)}}]},
            {"choices": [{"message": {"content": json.dumps({"topics": [{"title": "AI Agent 落地", "summary": "讨论智能体产品与工作流", "confidence": 92, "evidence_ids": evidence_ids}]}, ensure_ascii=False)}}]},
            {"choices": [{"message": {"content": json.dumps({"topics": [{"title": "智能体工作流", "summary": "独立复核确认落地话题", "confidence": 90, "evidence_ids": evidence_ids}]}, ensure_ascii=False)}}]},
            {"choices": [{"message": {"content": json.dumps({"title": "破壳群热门话题", "answer": "最热门的是 AI Agent 落地与工作流。", "sections": [{"title": "AI Agent 落地", "content": "群成员集中讨论智能体产品和工作流。", "confidence": 91, "evidence_ids": evidence_ids, "counter_evidence_ids": []}], "limitations": ["仅基于目标群文本消息。"], "suggested_followups": ["谁参与这个话题最多？", "话题随时间如何变化？"]}, ensure_ascii=False)}}]},
        ]

        keychain.return_value.get.return_value = "key"
        store = store_class.return_value
        store.conn = Connection()
        store.agent_model.return_value = "deepseek-v4-flash"
        store.ensure_agent_session.return_value = "session"
        store.agent_context.return_value = []
        store.published_corpus.return_value = {
            "corpus_id": "corpus",
            "generation_id": "generation",
            "since_ts": 0,
            "until_ts": 300,
        }
        deepseek_class.return_value.complete_json.side_effect = responses
        chatlog_class.return_value.databases.return_value = {
            "MSG": ["/tmp/xwechat_files/account/db_storage/message/message_0.db"]
        }
        chatlog_class.return_value.all_sessions.return_value = [
            {"username": "group@chatroom", "chat": "AI+🌞破壳HATCH", "timestamp": 390},
            {"username": "other@chatroom", "chat": "其他群", "timestamp": 380},
        ]
        chatlog_class.return_value.history.return_value = messages
        progress = []

        with patch("agent_core.customer_agent.time.time", return_value=400):
            result = ask_customer_agent(
                "state.db",
                '帮我分析群聊：“AI+🌞破壳HATCH”里讨论最热门的话题',
                progress=progress.append,
            )

        self.assertEqual(result["target_conversations"], ["AI+🌞破壳HATCH"])
        self.assertEqual(result["leads"][0]["customer_id"], "group@chatroom")
        self.assertEqual(result["leads"][0]["conversation_stats"]["message_count"], 2)
        self.assertEqual(len(result["leads"][0]["evidence"]), 2)
        self.assertFalse(store.conn.private_query_seen)
        chatlog_class.return_value.all_sessions.assert_called_once_with()
        chatlog_class.return_value.history.assert_called_once_with("group@chatroom", 0, 400)
        retrieval = next(item for item in progress if item["stage"] == "retrieval")
        self.assertEqual(retrieval["stats"]["conversations"], 1)
        self.assertEqual(retrieval["stats"]["candidates"], 2)
        self.assertEqual(retrieval["stats"]["time_window_label"], "全部历史")
        self.assertNotIn("36500", "\n".join(result["analysis_trace"]))

    @patch("agent_core.customer_agent.KeychainStore")
    @patch("agent_core.customer_agent.AnalysisStore")
    def test_unchanged_saved_analysis_refresh_is_local_and_uses_no_api_key(self, store_class, keychain):
        connection = mock_connection = mock.Mock()
        connection.execute.return_value.fetchone.return_value = {"value": "account"}
        store = store_class.return_value
        store.conn = mock_connection
        store.saved_analysis.return_value = {
            "saved_id": "saved",
            "session_id": "session",
            "account_id": "account",
            "question": "甲怎么样",
            "task_type": "person_profile",
            "last_evidence_ts": 200,
            "result": {"query": "甲怎么样", "leads": [], "answer": "原结论"},
        }
        store.account_corpus_watermark.return_value = 200
        result = refresh_saved_analysis("state.db", "saved")
        self.assertEqual(result["refresh_status"], "unchanged")
        self.assertEqual(result["answer"], "原结论")
        keychain.assert_not_called()

    @patch("agent_core.customer_agent.KeychainStore")
    @patch("agent_core.customer_agent.AnalysisStore")
    @patch("agent_core.customer_agent.DeepSeekClient")
    def test_agent_analyzes_only_after_a_question_and_returns_known_customers(self, client, store, keychain):
        class Cursor:
            def __init__(self, one=None, many=None, rows=None):
                self.one, self.many, self.rows = one, many, rows or []

            def fetchone(self):
                return self.one

            def fetchall(self):
                return self.many or []

            def __iter__(self):
                return iter(self.rows)

        class Connection:
            def execute(self, sql, _params=()):
                if "active_account" in sql:
                    return Cursor(one={"value": "account"})
                if "min(e.timestamp)" in sql:
                    return Cursor(one={"first_ts": 10, "last_ts": 20, "evidence_count": 2})
                if "SELECT username,display_name" in sql:
                    return Cursor(rows=[{"username": "a", "display_name": "甲", "latest_timestamp": 10}, {"username": "b", "display_name": "乙", "latest_timestamp": 20}])
                return Cursor(rows=[
                    {"username": "a", "evidence_id": "e1", "is_self": 0, "sender": "甲", "timestamp": 10, "message_type": "text", "content": "我们一起做创业项目"},
                    {"username": "b", "evidence_id": "e2", "is_self": 0, "sender": "乙", "timestamp": 20, "message_type": "text", "content": "普通聊天"},
                ])

        keychain.return_value.get.return_value = "key"
        store.return_value.conn = Connection()
        store.return_value.agent_model.return_value = "deepseek-v4-flash"
        store.return_value.ensure_agent_session.return_value = "agent_session"
        store.return_value.agent_context.return_value = []
        store.return_value.published_corpus.return_value = {"corpus_id": "corpus"}
        store.return_value.packet.return_value = {"facts": [], "evidence": []}
        client.return_value.complete_json.side_effect = [
            {"choices": [{"message": {"content": '{"task_type":"customer_search","summary":"创业讨论","subject_names":[],"requested_dimensions":["创业需求","意向强度"],"output_title":"创业客户分析","time_window_days":183,"topic_groups":[{"concept":"创业","terms":["创业项目"]}],"export_requested":true}'}}]},
            {"choices": [{"message": {"content": '{"decisions":[{"customer_id":"a","matched":true,"confidence":94,"reason":"双方讨论创业项目","headline":"有明确创业讨论","summary":"甲讨论了创业项目","insights":[{"label":"创业需求","value":"正在讨论创业项目","evidence_ids":["e1"]}],"intent_score":90,"need":"创业","obstacles":[],"suggested_action":"跟进","evidence_ids":["e1"]}]}'}}]},
            {"choices": [{"message": {"content": '{"decisions":[{"customer_id":"a","final_match":true,"reason":"证据充分","evidence_ids":["e1"]}]}'}}]},
            {"choices": [{"message": {"content": '{"title":"创业客户分析","answer":"甲正在讨论创业项目。","sections":[{"title":"创业需求","content":"甲正在讨论创业项目。","evidence_ids":["e1"]}],"suggested_followups":["谁近期推进最快？","哪些人需要再次联系？"]}'}}]},
        ]
        result = ask_customer_agent("state.db", "找有创业意向的朋友并导出 Excel")
        self.assertEqual([lead["customer_id"] for lead in result["leads"]], ["a"])
        self.assertTrue(result["export_requested"])
        self.assertEqual(client.return_value.complete_json.call_count, 4)
        self.assertEqual(client.return_value.complete_json.call_args_list[0].args[0], "deepseek-v4-flash")
        self.assertIn("理解任务 · 全部历史 · 数据覆盖", result["analysis_trace"][0])
        self.assertNotIn("36500", result["analysis_trace"][0])
        self.assertEqual(result["leads"][0]["evidence"][0]["evidence_id"], "e1")
        self.assertEqual(result["schema_version"], "agent.query.v2")
        self.assertEqual(result["result_title"], "创业客户分析")
        self.assertEqual(result["session_id"], "agent_session")
        self.assertEqual(store.return_value.close.call_count, 2)
        store.return_value.add_agent_turn.assert_called_once()

    def test_person_profile_prioritizes_the_named_contact_over_third_party_mentions(self):
        class Cursor:
            def __init__(self, rows):
                self.rows = rows

            def __iter__(self):
                return iter(self.rows)

        class Connection:
            def execute(self, sql, _params=()):
                if "SELECT username,display_name" in sql:
                    return Cursor([
                        {"username": "yang", "display_name": "杨凯", "latest_timestamp": 200},
                        {"username": "snoop", "display_name": "勺子 Snoop", "latest_timestamp": 210},
                    ])
                return Cursor([
                    {"username": "yang", "evidence_id": "y1", "is_self": 0, "sender": "杨凯", "timestamp": 200, "message_type": "text", "content": "我最近常说先把事情做完"},
                    {"username": "snoop", "evidence_id": "s1", "is_self": 0, "sender": "勺子", "timestamp": 210, "message_type": "text", "content": "杨凯今天在吗"},
                ])

        store = type("Store", (), {"conn": Connection()})()
        plan = {
            "task_type": "person_profile",
            "subject_names": ["杨凯"],
            "time_window_days": 3650,
            "topic_groups": [{"concept": "人物特征", "terms": ["杨凯", "常说"]}],
        }
        ranked, count = _rank_conversations(store, "corpus", plan)
        self.assertEqual(count, 2)
        self.assertEqual([item["username"] for item in ranked], ["yang"])
        self.assertEqual(ranked[0]["match_role"], "direct_subject")

        refreshed, _ = _rank_conversations(store, "corpus", plan, newer_than_timestamp=300)
        self.assertEqual(refreshed, [])

    def test_explicit_half_year_is_a_deterministic_time_window(self):
        self.assertEqual(_question_time_window_days("找出近半年和我讨论创业的人"), 183)
        self.assertEqual(_question_time_window_days("过去3个月聊过合作的人"), 93)

    def test_explicit_group_name_is_a_deterministic_query_scope(self):
        self.assertEqual(
            _question_group_names('帮我分析群聊：“AI+🌞破壳HATCH”里讨论最热门的话题'),
            ["AI+🌞破壳HATCH"],
        )
        self.assertEqual(_question_group_names("分析群「产品共创营」最近的待办"), ["产品共创营"])
        self.assertEqual(_question_group_names("找最近聊过合作的朋友"), [])

    def test_group_message_chunking_preserves_every_message_without_a_candidate_cap(self):
        rows = [
            {"evidence_id": "e%s" % index, "content": "群聊消息%s" % index}
            for index in range(523)
        ]
        chunks = _group_message_chunks(rows)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(
            [item["evidence_id"] for chunk in chunks for item in chunk],
            [item["evidence_id"] for item in rows],
        )

    def test_full_history_sentinel_is_never_user_visible(self):
        self.assertEqual(_time_window_display(DEFAULT_TIME_WINDOW_DAYS, True), "全部历史")
        self.assertEqual(_time_window_display(183, False), "183 天")

    def test_unspecified_time_always_uses_full_history_not_model_guess(self):
        payload = {
            "task_type": "person_profile",
            "summary": "了解甲",
            "subject_names": ["甲"],
            "requested_dimensions": ["性格"],
            "output_title": "甲的人物画像",
            "time_window_days": 30,
            "topic_groups": [{"concept": "人物特征", "terms": ["性格"]}],
            "export_requested": False,
        }
        response = {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}
        client = mock.Mock()
        client.complete_json.return_value = response
        plan = _plan_query(client, "deepseek-v4-flash", "甲是什么样的人", [])
        self.assertEqual(plan["time_window_days"], DEFAULT_TIME_WINDOW_DAYS)
        self.assertTrue(plan["full_history"])

    def test_single_character_contact_names_require_an_exact_display_name(self):
        self.assertTrue(_name_matches("凯", ["凯"]))
        self.assertFalse(_name_matches("杨凯", ["凯"]))

    def test_incremental_audit_must_cite_evidence_after_the_saved_watermark(self):
        packet = [
            {"evidence_id": "old", "timestamp": 100},
            {"evidence_id": "new", "timestamp": 201},
        ]
        with self.assertRaisesRegex(CustomerAgentError, "真正新增"):
            _validated_final_evidence(packet, ["old"], 200)
        self.assertEqual(_validated_final_evidence(packet, ["old", "new"], 200), ["old", "new"])

    def test_active_account_never_falls_back_to_most_recent_account(self):
        store = type("Store", (), {"conn": sqlite3.connect(":memory:")})()
        with self.assertRaisesRegex(CustomerAgentError, "请先连接并同步微信"):
            _active_account(store)
        store.conn.close()

    def test_precise_stats_and_evidence_context_are_deterministic(self):
        rows = [
            {"evidence_id": "e1", "is_self": 0, "sender": "甲", "timestamp": 1_700_000_000, "content": "想了解报价"},
            {"evidence_id": "e2", "is_self": 1, "sender": "我", "timestamp": 1_700_000_600, "content": "好的"},
            {"evidence_id": "e3", "is_self": 0, "sender": "甲", "timestamp": 1_700_001_200, "content": "想了解报价"},
        ]
        stats = _conversation_stats(rows)
        self.assertEqual(stats["message_count"], 3)
        self.assertEqual(stats["incoming_count"], 2)
        self.assertEqual(stats["my_median_response_minutes"], 10.0)
        self.assertEqual(stats["their_median_response_minutes"], 10.0)
        candidate = {"username": "a", "display_name": "甲", "latest_timestamp": rows[-1]["timestamp"], "evidence_rows": rows, "conversation_stats": stats, "match_role": "direct_subject"}
        packet = {"facts": [], "conversation_stats": stats, "evidence": rows}
        match = {"confidence": 91, "headline": "重视价格", "summary": "两次询价", "reason": "重复询价", "evidence_ids": ["e2"], "insights": [{"label": "关注点", "value": "报价", "confidence": 91, "evidence_ids": ["e2"], "counter_evidence_ids": []}]}
        lead = _lead_from_match(candidate, packet, match, {"task_type": "person_profile"})
        evidence = lead["evidence"][0]
        self.assertEqual(evidence["evidence_id"], "e2")
        self.assertEqual([item["evidence_id"] for item in evidence["context"]], ["e1", "e2", "e3"])
        self.assertTrue(evidence["context"][1]["is_target"])

        risk_match = dict(match, task_score=88)
        risk = _lead_from_match(candidate, packet, risk_match, {"task_type": "customer_risk"})
        self.assertEqual(risk["score_label"], "风险严重度")
        self.assertEqual(risk["status_label"], "高风险")
        self.assertEqual(risk["intent_band"], "")

    def test_agent_sessions_can_be_saved_and_listed(self):
        handle, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        try:
            store = AnalysisStore(path)
            store.conn.execute("CREATE TABLE generations (generation_id TEXT PRIMARY KEY,status TEXT NOT NULL)")
            CorpusStore(store.conn)
            store.conn.execute("INSERT INTO generations VALUES('generation','published')")
            store.conn.execute(
                "INSERT INTO corpus_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("corpus", "generation", "account", 0, 456, "published", 1, 2, None, None),
            )
            store.conn.execute(
                "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                ("evidence", "corpus", "account", "generation", "a", 1, 0, "甲", 456, "text", "消息", "hash"),
            )
            store.conn.commit()
            session_id = store.ensure_agent_session("account")
            result = {"task_type": "person_profile", "result_title": "甲画像", "answer": "结论", "subject_names": ["甲"], "suggested_followups": ["继续"], "leads": [{"evidence": [{"timestamp": 123}]}]}
            store.add_agent_turn(session_id, "甲怎么样", result)
            saved = store.save_agent_session(session_id)
            self.assertEqual(saved["session_id"], session_id)
            self.assertEqual(saved["last_evidence_ts"], 456)
            self.assertEqual(store.agent_context(session_id)[0]["subject_names"], ["甲"])
            self.assertEqual(store.list_saved_analyses("account")[0]["title"], "甲画像")
            stored_turn = json.loads(store.conn.execute("SELECT result_json FROM agent_turns WHERE session_id=?", (session_id,)).fetchone()[0])
            self.assertNotIn("leads", stored_turn)
            self.assertEqual(saved["result"]["leads"][0]["evidence"][0]["timestamp"], 123)
            store.close()
        finally:
            os.unlink(path)
