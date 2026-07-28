import json
import os
import sqlite3
import tempfile
import threading
import unittest
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer

from agent_core.ai_models import BusinessProfile, LeadJudgment
from agent_core.analysis_engine import AnalysisError, cost_usd, run_analysis, validate_provider_response
from agent_core.analysis_store import AnalysisStore
from agent_core.corpus_store import CorpusStore
from agent_core.deepseek_client import DeepSeekClient
from agent_core.sync_store import SyncStore


def business_profile():
    return BusinessProfile.model_validate({
        "business_name": "街舞店",
        "products": ["少儿街舞体验课"],
        "prices": ["体验课99元"],
        "offers": [],
        "address": "苏州市",
        "business_hours": "周一至周日",
        "allowed_claims": [],
        "forbidden_claims": ["保证学会"],
        "lead_keywords": ["街舞", "体验"],
        "minor_data_approved": False,
        "external_api_data_transfer_approved": True,
    })


def packet():
    return {
        "customer_id": "wxid_customer",
        "display_name": "客户",
        "recent_contact_ts": 1700000000,
        "facts": [],
        "evidence": [{
            "evidence_id": "ev_1", "is_self": 0, "sender": "客户", "timestamp": 1700000000,
            "message_type": "text", "content": "想体验街舞，周六方便",
        }],
    }


def response(content=None, usage=None):
    if content is None:
        content = {
            "customer_id": "wxid_customer", "intent_score": 60, "intent_band": "待激活",
            "recent_contact_ts": 1700000000, "evidence_ids": ["ev_1"],
            "obstacles": ["尚未确认时间"], "suggested_action": "确认周六到店时段",
            "draft_text": "您好，您之前想体验街舞，周六哪个时段方便？", "draft_evidence_ids": ["ev_1"],
        }
    if usage is None:
        usage = {
            "prompt_tokens": 100, "prompt_cache_hit_tokens": 40, "prompt_cache_miss_tokens": 60,
            "completion_tokens": 50, "total_tokens": 150,
        }
    return {
        "id": "resp_1", "model": "deepseek-v4-flash", "system_fingerprint": "fp_1",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)}}],
        "usage": usage,
    }


class Phase3AITests(unittest.TestCase):
    def test_valid_response_and_exact_decimal_cost(self):
        judgment, usage, _ = validate_provider_response(response(), packet(), business_profile())
        self.assertEqual(judgment.intent_band, "待激活")
        settings = {"cache_hit_usd_per_million": "0.0028", "cache_miss_usd_per_million": "0.14", "output_usd_per_million": "0.28"}
        self.assertEqual(cost_usd(usage, settings), Decimal("0.000022512"))

    def test_unknown_evidence_is_rejected(self):
        content = json.loads(response()["choices"][0]["message"]["content"])
        content["evidence_ids"] = ["ev_unknown"]
        with self.assertRaisesRegex(AnalysisError, "outside the supplied packet"):
            validate_provider_response(response(content=content), packet(), business_profile())

    def test_forbidden_claim_is_rejected(self):
        content = json.loads(response()["choices"][0]["message"]["content"])
        content["draft_text"] = "保证学会，欢迎报名"
        with self.assertRaisesRegex(AnalysisError, "forbidden"):
            validate_provider_response(response(content=content), packet(), business_profile())

    def test_usage_mismatch_is_rejected(self):
        bad_usage = {"prompt_tokens": 100, "prompt_cache_hit_tokens": 20, "prompt_cache_miss_tokens": 20, "completion_tokens": 50, "total_tokens": 150}
        with self.assertRaises(AnalysisError) as caught:
            validate_provider_response(response(usage=bad_usage), packet(), business_profile())
        self.assertEqual(caught.exception.code, "DEEPSEEK_SCHEMA_INVALID")

    def test_extra_output_field_is_rejected_without_repair(self):
        content = json.loads(response()["choices"][0]["message"]["content"])
        content["explanation"] = "should fail"
        with self.assertRaises(AnalysisError) as caught:
            validate_provider_response(response(content=content), packet(), business_profile())
        self.assertEqual(caught.exception.code, "DEEPSEEK_SCHEMA_INVALID")

    def test_direct_client_sends_json_mode_once(self):
        captured = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                captured.append(json.loads(self.rfile.read(length)))
                body = json.dumps(response(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            data = DeepSeekClient("test-key", "http://127.0.0.1:%d" % server.server_port, timeout=2).complete_json("deepseek-v4-flash", [{"role": "system", "content": "JSON"}], 100)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(data["id"], "resp_1")
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["response_format"], {"type": "json_object"})
        self.assertEqual(captured[0]["thinking"], {"type": "disabled"})
        self.assertEqual(captured[0]["temperature"], 0)

    def test_analysis_store_publishes_exact_cost_text(self):
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
            corpus = corpus_store.create_run(generation, "account", 0, 100)
            corpus_store.publish_run(corpus, "account")
            connection.close()
            store = AnalysisStore(path)
            try:
                profile = business_profile()
                store.configure({
                    "base_url": "https://api.deepseek.com", "model": "deepseek-v4-flash", "max_tokens": 1400,
                    "cache_hit_usd_per_million": "0.0028", "cache_miss_usd_per_million": "0.14", "output_usd_per_million": "0.28",
                }, profile.model_dump_json())
                run_id = store.create_run(corpus, "account", {
                    "model": "deepseek-v4-flash", "prompt_version": "v1", "prompt_sha256": "a" * 64,
                    "schema_version": "v1", "config_snapshot": {},
                }, 1, Decimal("0.1"))
                store.add_call({
                    "call_id": "call_1", "run_id": run_id, "username": "customer", "status": "succeeded", "request_sha256": "b" * 64,
                    "provider_response_id": "resp", "provider_model": "deepseek-v4-flash", "system_fingerprint": "fp", "finish_reason": "stop",
                    "prompt_tokens": 100, "cache_hit_tokens": 40, "cache_miss_tokens": 60, "completion_tokens": 50, "total_tokens": 150,
                    "usage_json": json.dumps(response()["usage"], sort_keys=True),
                    "estimated_cost_usd": "0.1", "actual_cost_usd": "0.000022512", "response_sha256": "c" * 64,
                    "error_code": None, "error_message": None, "created_at": 1,
                })
                store.publish_run(run_id, "account")
                actual = store.conn.execute("SELECT actual_cost_usd FROM analysis_runs WHERE run_id=?", (run_id,)).fetchone()[0]
                self.assertEqual(actual, "0.000022512")
            finally:
                store.close()

    def test_business_profile_transfer_approval_preserves_minor_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            sync = SyncStore(path)
            sync.close()
            connection = sqlite3.connect(path)
            CorpusStore(connection)
            connection.close()
            store = AnalysisStore(path)
            try:
                profile = business_profile().model_copy(update={
                    "external_api_data_transfer_approved": False,
                    "minor_data_approved": False,
                })
                store.configure({
                    "base_url": "https://api.deepseek.com", "model": "deepseek-v4-flash", "max_tokens": 1400,
                    "cache_hit_usd_per_million": "0.0028", "cache_miss_usd_per_million": "0.14", "output_usd_per_million": "0.28",
                }, profile.model_dump_json())
                updated = profile.model_copy(update={"external_api_data_transfer_approved": True})
                store.update_business_profile(updated.model_dump_json())
                current = BusinessProfile.model_validate(store.config()["business_profile"])
                self.assertTrue(current.external_api_data_transfer_approved)
                self.assertFalse(current.minor_data_approved)
            finally:
                store.close()

    def test_full_analysis_run_publishes_one_mocked_lead(self):
        captured = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                request_payload = json.loads(self.rfile.read(length))
                captured.append(request_payload)
                customer_packet = json.loads(request_payload["messages"][-1]["content"].split("\n", 1)[1])
                content = json.loads(response()["choices"][0]["message"]["content"])
                evidence = customer_packet["evidence"][0]["evidence_id"]
                content["evidence_ids"] = [evidence]
                content["draft_evidence_ids"] = [evidence]
                body = json.dumps(response(content=content), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
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
                corpus = corpus_store.create_run(generation, "account", 0, 1800000000)
                session = {"username": "wxid_customer", "chat": "客户"}
                corpus_store.add_conversation(corpus, session, "eligible", "", 1, 1, 1700000000)
                message = {"local_id": 1, "timestamp": 1700000000, "sender": "客户", "type": "text", "content": "想体验街舞，周六方便", "is_self": False}
                corpus_store.add_evidence_and_facts(corpus, "account", generation, "wxid_customer", message, [{
                    "field": "explicit_need", "value": "想体验街舞", "extractor": "fixture",
                }])
                corpus_store.commit_conversation()
                corpus_store.publish_run(corpus, "account")
                connection.close()
                store = AnalysisStore(path)
                store.configure({
                    "base_url": "http://127.0.0.1:%d" % server.server_port, "model": "deepseek-v4-flash", "max_tokens": 1400,
                    "cache_hit_usd_per_million": "0.0028", "cache_miss_usd_per_million": "0.14", "output_usd_per_million": "0.28",
                }, business_profile().model_dump_json())
                store.close()
                result = run_analysis(path, "account", "test-key", timeout=2)
                self.assertEqual(result["candidate_count"], 1)
                check = sqlite3.connect(path)
                self.assertEqual(check.execute("SELECT status FROM analysis_runs WHERE run_id=?", (result["run_id"],)).fetchone()[0], "published")
                self.assertEqual(check.execute("SELECT count(*) FROM lead_results WHERE run_id=?", (result["run_id"],)).fetchone()[0], 1)
                check.close()
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(len(captured), 1)


if __name__ == "__main__":
    unittest.main()
