import json
import os
import sqlite3
import tempfile
import threading
import unittest
import socket
import urllib.error
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from unittest import mock

from agent_core.ai_cli import command_configure, command_estimate, command_run
from agent_core.ai_models import BusinessProfile
from agent_core.analysis_engine import (
    AnalysisError,
    cost_usd,
    run_analysis,
    validate_provider_response,
)
from agent_core.analysis_store import AnalysisStore
from agent_core.corpus_store import CorpusStore
from agent_core.deepseek_client import DeepSeekClient
from agent_core.sync_store import SyncStore


def business_profile():
    return BusinessProfile.model_validate(
        {
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
        }
    )


def packet():
    return {
        "customer_id": "wxid_customer",
        "display_name": "客户",
        "recent_contact_ts": 1700000000,
        "facts": [],
        "evidence": [
            {
                "evidence_id": "ev_1",
                "is_self": 0,
                "sender": "客户",
                "timestamp": 1700000000,
                "message_type": "text",
                "content": "想体验街舞，周六方便",
            }
        ],
    }


def response(content=None, usage=None):
    if content is None:
        content = {
            "customer_id": "wxid_customer",
            "intent_score": 60,
            "intent_band": "待激活",
            "recent_contact_ts": 1700000000,
            "evidence_ids": ["ev_1"],
            "obstacles": ["尚未确认时间"],
            "suggested_action": "确认周六到店时段",
        }
    if usage is None:
        usage = {
            "prompt_tokens": 100,
            "prompt_cache_hit_tokens": 40,
            "prompt_cache_miss_tokens": 60,
            "completion_tokens": 50,
            "total_tokens": 150,
        }
    return {
        "id": "resp_1",
        "model": "deepseek-v4-flash",
        "system_fingerprint": "fp_1",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(content, ensure_ascii=False),
                },
            }
        ],
        "usage": usage,
    }


class Phase3AITests(unittest.TestCase):
    def test_ai_cli_rejects_nonfinite_prices_and_invalid_bounds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            business_path = os.path.join(tmpdir, "business.json")
            with open(business_path, "w", encoding="utf-8") as handle:
                handle.write(business_profile().model_dump_json())
            base = dict(
                business_file=business_path,
                base_url="https://api.deepseek.com",
                model="deepseek-v4-flash",
                max_tokens=1400,
                cache_hit_price="0.0028",
                cache_miss_price="0.14",
                output_price="0.28",
                api_key_env="UNSET_TEST_API_KEY",
                db=os.path.join(tmpdir, "state.sqlite3"),
            )
            for field, value in (
                ("cache_hit_price", "NaN"),
                ("cache_miss_price", "Infinity"),
                ("output_price", "-Infinity"),
                ("max_tokens", 0),
                ("max_tokens", 8193),
            ):
                candidate = dict(base)
                candidate[field] = value
                self.assertEqual(command_configure(SimpleNamespace(**candidate)), 1)

    def test_ai_cli_rejects_negative_limit_and_nonpositive_timeout(self):
        self.assertEqual(
            command_estimate(
                SimpleNamespace(db=":memory:", account_id="account", limit=-1)
            ),
            1,
        )
        for timeout in (0, -1):
            self.assertEqual(
                command_run(
                    SimpleNamespace(
                        db=":memory:", account_id="account", limit=0, timeout=timeout
                    )
                ),
                1,
            )

    def test_business_truth_lists_reject_blank_and_duplicate_values(self):
        base = business_profile().model_dump()
        for field, invalid in (
            ("lead_keywords", [""]),
            ("lead_keywords", ["   "]),
            ("products", ["课程", " 课程 "]),
            ("prices", ["  "]),
            ("allowed_claims", ["真实", "真实"]),
        ):
            candidate = dict(base)
            candidate[field] = invalid
            with self.assertRaisesRegex(ValueError, "blank|unique"):
                BusinessProfile.model_validate(candidate)

    def test_valid_response_and_exact_decimal_cost(self):
        judgment, usage, _ = validate_provider_response(
            response(), packet(), business_profile()
        )
        self.assertEqual(judgment.intent_band, "待激活")
        settings = {
            "cache_hit_usd_per_million": "0.0028",
            "cache_miss_usd_per_million": "0.14",
            "output_usd_per_million": "0.28",
        }
        self.assertEqual(cost_usd(usage, settings), Decimal("0.000022512"))

    def test_unknown_evidence_is_rejected(self):
        content = json.loads(response()["choices"][0]["message"]["content"])
        content["evidence_ids"] = ["ev_unknown"]
        with self.assertRaisesRegex(AnalysisError, "outside the supplied packet"):
            validate_provider_response(
                response(content=content), packet(), business_profile()
            )

    def test_provider_cannot_author_outbound_draft(self):
        content = json.loads(response()["choices"][0]["message"]["content"])
        content["draft_text"] = "保证学会，限时优惠价999元"
        content["draft_evidence_ids"] = ["ev_1"]
        with self.assertRaises(AnalysisError) as caught:
            validate_provider_response(
                response(content=content), packet(), business_profile()
            )
        self.assertEqual(caught.exception.code, "DEEPSEEK_SCHEMA_INVALID")

    def test_outbound_draft_is_controlled_and_contains_no_model_business_claims(self):
        claims = [
            "本周六还有最后一个名额",
            "到店赠送舞鞋",
            "我们在人民路店",
            "今晚营业到十点",
        ]
        for claim in claims:
            content = json.loads(response()["choices"][0]["message"]["content"])
            content["suggested_action"] = claim
            judgment, _, _ = validate_provider_response(
                response(content=content), packet(), business_profile()
            )
            self.assertNotIn(claim, judgment.draft_text)
            self.assertEqual(
                judgment.draft_text,
                "您好，想跟您确认一下，目前是否方便聊聊您的需求？",
            )

    def test_transport_timeout_is_typed(self):
        with mock.patch(
            "urllib.request.urlopen", side_effect=socket.timeout("timed out")
        ):
            with self.assertRaisesRegex(RuntimeError, "configured timeout"):
                DeepSeekClient(
                    "key", "https://api.deepseek.com", timeout=1
                ).complete_json("model", [], 10)

    def test_wrapped_transport_timeout_is_typed(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError(socket.timeout("timed out")),
        ):
            with self.assertRaises(RuntimeError) as caught:
                DeepSeekClient(
                    "key", "https://api.deepseek.com", timeout=1
                ).complete_json("model", [], 10)
        self.assertEqual(caught.exception.code, "DEEPSEEK_TIMEOUT")

    def test_usage_mismatch_is_rejected(self):
        bad_usage = {
            "prompt_tokens": 100,
            "prompt_cache_hit_tokens": 20,
            "prompt_cache_miss_tokens": 20,
            "completion_tokens": 50,
            "total_tokens": 150,
        }
        with self.assertRaises(AnalysisError) as caught:
            validate_provider_response(
                response(usage=bad_usage), packet(), business_profile()
            )
        self.assertEqual(caught.exception.code, "DEEPSEEK_SCHEMA_INVALID")

    def test_extra_output_field_is_rejected_without_repair(self):
        content = json.loads(response()["choices"][0]["message"]["content"])
        content["explanation"] = "should fail"
        with self.assertRaises(AnalysisError) as caught:
            validate_provider_response(
                response(content=content), packet(), business_profile()
            )
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
            data = DeepSeekClient(
                "test-key", "http://127.0.0.1:%d" % server.server_port, timeout=2
            ).complete_json(
                "deepseek-v4-flash", [{"role": "system", "content": "JSON"}], 100
            )
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
                store.configure(
                    {
                        "base_url": "https://api.deepseek.com",
                        "model": "deepseek-v4-flash",
                        "max_tokens": 1400,
                        "cache_hit_usd_per_million": "0.0028",
                        "cache_miss_usd_per_million": "0.14",
                        "output_usd_per_million": "0.28",
                    },
                    profile.model_dump_json(),
                )
                run_id = store.create_run(
                    corpus,
                    "account",
                    {
                        "model": "deepseek-v4-flash",
                        "prompt_version": "v1",
                        "prompt_sha256": "a" * 64,
                        "schema_version": "v1",
                        "config_snapshot": {
                            key: value
                            for key, value in store.config().items()
                            if key not in ("setting_id", "updated_at")
                        },
                    },
                    1,
                    Decimal("0.1"),
                )
                store.add_call(
                    {
                        "call_id": "call_1",
                        "run_id": run_id,
                        "username": "customer",
                        "status": "succeeded",
                        "request_sha256": "b" * 64,
                        "provider_response_id": "resp",
                        "provider_model": "deepseek-v4-flash",
                        "system_fingerprint": "fp",
                        "finish_reason": "stop",
                        "prompt_tokens": 100,
                        "cache_hit_tokens": 40,
                        "cache_miss_tokens": 60,
                        "completion_tokens": 50,
                        "total_tokens": 150,
                        "usage_json": json.dumps(response()["usage"], sort_keys=True),
                        "estimated_cost_usd": "0.1",
                        "actual_cost_usd": "0.000022512",
                        "response_sha256": "c" * 64,
                        "error_code": None,
                        "error_message": None,
                        "created_at": 1,
                    }
                )
                store.publish_run(run_id, "account")
                actual = store.conn.execute(
                    "SELECT actual_cost_usd FROM analysis_runs WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
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
                profile = business_profile().model_copy(
                    update={
                        "external_api_data_transfer_approved": False,
                        "minor_data_approved": False,
                    }
                )
                store.configure(
                    {
                        "base_url": "https://api.deepseek.com",
                        "model": "deepseek-v4-flash",
                        "max_tokens": 1400,
                        "cache_hit_usd_per_million": "0.0028",
                        "cache_miss_usd_per_million": "0.14",
                        "output_usd_per_million": "0.28",
                    },
                    profile.model_dump_json(),
                )
                updated = profile.model_copy(
                    update={"external_api_data_transfer_approved": True}
                )
                store.update_business_profile(updated.model_dump_json())
                current = BusinessProfile.model_validate(
                    store.config()["business_profile"]
                )
                self.assertTrue(current.external_api_data_transfer_approved)
                self.assertFalse(current.minor_data_approved)
            finally:
                store.close()

    def test_minor_grade_is_excluded_without_explicit_approval(self):
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
            corpus_store.add_conversation(
                corpus,
                {"username": "minor", "chat": "家长"},
                "eligible",
                "",
                1,
                1,
                1700000000,
            )
            corpus_store.add_evidence_and_facts(
                corpus,
                "account",
                generation,
                "minor",
                {
                    "local_id": 1,
                    "timestamp": 1700000000,
                    "sender": "家长",
                    "type": "text",
                    "content": "孩子小学三年级想体验街舞",
                    "is_self": False,
                },
                [{"field": "grade", "value": "小学三年级", "extractor": "fixture"}],
            )
            corpus_store.commit_conversation()
            corpus_store.publish_run(corpus, "account")
            connection.close()
            store = AnalysisStore(path)
            try:
                blocked = store.candidates(corpus, ["街舞"], minor_data_approved=False)
                allowed = store.candidates(corpus, ["街舞"], minor_data_approved=True)
                self.assertEqual(blocked["privacy_excluded"], 1)
                self.assertEqual(blocked["candidates"], [])
                self.assertEqual(
                    [item["username"] for item in allowed["candidates"]], ["minor"]
                )
            finally:
                store.close()

    def test_child_semantics_without_age_or_grade_is_screened_and_stored(self):
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
            corpus_store.add_conversation(
                corpus,
                {"username": "child", "chat": "家长"},
                "eligible",
                "",
                1,
                1,
                1700000000,
            )
            corpus_store.add_evidence_and_facts(
                corpus,
                "account",
                generation,
                "child",
                {
                    "local_id": 1,
                    "timestamp": 1700000000,
                    "sender": "家长",
                    "type": "text",
                    "content": "我家孩子想体验少儿街舞",
                    "is_self": False,
                },
                [
                    {
                        "field": "explicit_need",
                        "value": "少儿街舞",
                        "extractor": "fixture",
                    }
                ],
            )
            corpus_store.commit_conversation()
            corpus_store.publish_run(corpus, "account")
            connection.close()
            store = AnalysisStore(path)
            try:
                result = store.candidates(corpus, ["街舞"], False)
                screening = store.conn.execute(
                    "SELECT * FROM minor_screenings WHERE corpus_id=? AND username='child'",
                    (corpus,),
                ).fetchone()
                self.assertEqual(result["candidates"], [])
                self.assertEqual(screening["decision"], "positive")
                self.assertIn("孩子", screening["indicators_json"])
            finally:
                store.close()

    def test_merchant_authored_minor_terms_do_not_classify_customer(self):
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
            corpus_store.add_conversation(
                corpus,
                {"username": "adult", "chat": "客户"},
                "eligible",
                "",
                2,
                1,
                1700000001,
            )
            corpus_store.add_evidence_and_facts(
                corpus,
                "account",
                generation,
                "adult",
                {
                    "local_id": 1,
                    "timestamp": 1700000000,
                    "sender": "商家",
                    "type": "text",
                    "content": "我们也有少儿课，孩子可以报名",
                    "is_self": True,
                },
                [],
            )
            corpus_store.add_evidence_and_facts(
                corpus,
                "account",
                generation,
                "adult",
                {
                    "local_id": 2,
                    "timestamp": 1700000001,
                    "sender": "客户",
                    "type": "text",
                    "content": "我想了解成人街舞",
                    "is_self": False,
                },
                [
                    {
                        "field": "explicit_need",
                        "value": "成人街舞",
                        "extractor": "fixture",
                    }
                ],
            )
            corpus_store.commit_conversation()
            corpus_store.publish_run(corpus, "account")
            connection.close()
            store = AnalysisStore(path)
            try:
                result = store.candidates(corpus, ["街舞"], False)
                self.assertEqual(
                    [item["username"] for item in result["candidates"]], ["adult"]
                )
                screening = store.conn.execute(
                    "SELECT decision FROM minor_screenings WHERE corpus_id=? AND username='adult'",
                    (corpus,),
                ).fetchone()
                self.assertEqual(screening["decision"], "clear")
            finally:
                store.close()

    def test_provider_model_mismatch_fails_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            self._create_runnable_analysis(path)
            bad = response()
            bad["model"] = "different-model"
            with mock.patch(
                "agent_core.analysis_engine.DeepSeekClient.complete_json",
                return_value=bad,
            ):
                with self.assertRaises(AnalysisError) as caught:
                    run_analysis(path, "account", "key")
            self.assertEqual(caught.exception.code, "DEEPSEEK_MODEL_MISMATCH")
            row = (
                sqlite3.connect(path)
                .execute(
                    "SELECT status,failure_code FROM analysis_runs ORDER BY started_at DESC LIMIT 1"
                )
                .fetchone()
            )
            self.assertEqual(row, ("failed", "DEEPSEEK_MODEL_MISMATCH"))

    def test_malformed_provider_message_is_typed_and_journaled(self):
        for malformed in ("bad", []):
            with (
                self.subTest(malformed=malformed),
                tempfile.TemporaryDirectory() as tmpdir,
            ):
                path = os.path.join(tmpdir, "state.sqlite3")
                self._create_runnable_analysis(path)
                bad = response()
                bad["choices"][0]["message"] = malformed
                with mock.patch(
                    "agent_core.analysis_engine.DeepSeekClient.complete_json",
                    return_value=bad,
                ):
                    with self.assertRaises(AnalysisError) as caught:
                        run_analysis(path, "account", "key")
                self.assertEqual(caught.exception.code, "DEEPSEEK_MESSAGE_INVALID")
                connection = sqlite3.connect(path)
                try:
                    run_row = connection.execute(
                        "SELECT status,failure_code FROM analysis_runs ORDER BY started_at DESC LIMIT 1"
                    ).fetchone()
                    call_row = connection.execute(
                        "SELECT status,error_code FROM ai_calls LIMIT 1"
                    ).fetchone()
                finally:
                    connection.close()
                self.assertEqual(run_row, ("failed", "DEEPSEEK_MESSAGE_INVALID"))
                self.assertEqual(call_row, ("failed", "DEEPSEEK_MESSAGE_INVALID"))

    def test_unexpected_persistence_error_finalizes_staging_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            self._create_runnable_analysis(path)
            mocked_response = response()
            evidence_id = (
                sqlite3.connect(path)
                .execute("SELECT evidence_id FROM evidence LIMIT 1")
                .fetchone()[0]
            )
            content = json.loads(mocked_response["choices"][0]["message"]["content"])
            content["evidence_ids"] = [evidence_id]
            mocked_response["choices"][0]["message"]["content"] = json.dumps(
                content, ensure_ascii=False
            )
            with (
                mock.patch(
                    "agent_core.analysis_engine.DeepSeekClient.complete_json",
                    return_value=mocked_response,
                ),
                mock.patch.object(
                    AnalysisStore,
                    "add_success",
                    side_effect=sqlite3.OperationalError("disk write failed"),
                ),
            ):
                with self.assertRaises(AnalysisError) as caught:
                    run_analysis(path, "account", "key")
            self.assertEqual(caught.exception.code, "AI_ANALYSIS_INTERNAL_ERROR")
            row = (
                sqlite3.connect(path)
                .execute(
                    "SELECT status,failure_code FROM analysis_runs ORDER BY started_at DESC LIMIT 1"
                )
                .fetchone()
            )
            self.assertEqual(row, ("failed", "AI_ANALYSIS_INTERNAL_ERROR"))

    def test_business_config_change_supersedes_published_analysis_and_send(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            self._create_runnable_analysis(path)
            mocked_response = response()
            evidence_id = (
                sqlite3.connect(path)
                .execute("SELECT evidence_id FROM evidence LIMIT 1")
                .fetchone()[0]
            )
            content = json.loads(mocked_response["choices"][0]["message"]["content"])
            content["evidence_ids"] = [evidence_id]
            mocked_response["choices"][0]["message"]["content"] = json.dumps(
                content, ensure_ascii=False
            )
            with mock.patch(
                "agent_core.analysis_engine.DeepSeekClient.complete_json",
                return_value=mocked_response,
            ):
                run_analysis(path, "account", "key")
            store = AnalysisStore(path)
            try:
                profile = BusinessProfile.model_validate(
                    store.config()["business_profile"]
                )
                changed = profile.model_copy(update={"lead_keywords": ["新关键词"]})
                store.update_business_profile(changed.model_dump_json())
                status = store.conn.execute(
                    "SELECT status FROM analysis_runs ORDER BY started_at DESC LIMIT 1"
                ).fetchone()[0]
                self.assertEqual(status, "superseded")
            finally:
                store.close()

    def test_run_finalization_failure_is_never_silenced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.sqlite3")
            self._create_runnable_analysis(path)
            with (
                mock.patch(
                    "agent_core.analysis_engine.DeepSeekClient.complete_json",
                    side_effect=RuntimeError("provider failed"),
                ),
                mock.patch.object(
                    AnalysisStore,
                    "fail_run",
                    side_effect=sqlite3.OperationalError("finalization failed"),
                ),
            ):
                with self.assertRaises(AnalysisError) as caught:
                    run_analysis(path, "account", "key")
            self.assertEqual(caught.exception.code, "AI_RUN_FINALIZATION_FAILED")
            self.assertIn("finalization failed", caught.exception.message)

    def _create_runnable_analysis(self, path):
        sync = SyncStore(path)
        sync.upsert_account("account", "/tmp/account", "verified")
        generation = sync.create_generation("account")
        sync.publish_generation(generation, "account")
        sync.close()
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        corpus_store = CorpusStore(connection)
        corpus = corpus_store.create_run(generation, "account", 0, 1800000000)
        corpus_store.add_conversation(
            corpus,
            {"username": "wxid_customer", "chat": "客户"},
            "eligible",
            "",
            1,
            1,
            1700000000,
        )
        corpus_store.add_evidence_and_facts(
            corpus,
            "account",
            generation,
            "wxid_customer",
            {
                "local_id": 1,
                "timestamp": 1700000000,
                "sender": "客户",
                "type": "text",
                "content": "想体验街舞，周六方便",
                "is_self": False,
            },
            [{"field": "explicit_need", "value": "想体验街舞", "extractor": "fixture"}],
        )
        corpus_store.commit_conversation()
        corpus_store.publish_run(corpus, "account")
        connection.close()
        store = AnalysisStore(path)
        store.configure(
            {
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "max_tokens": 1400,
                "cache_hit_usd_per_million": "0.0028",
                "cache_miss_usd_per_million": "0.14",
                "output_usd_per_million": "0.28",
            },
            business_profile().model_dump_json(),
        )
        store.close()

    def test_full_analysis_run_publishes_one_mocked_lead(self):
        captured = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                request_payload = json.loads(self.rfile.read(length))
                captured.append(request_payload)
                customer_packet = json.loads(
                    request_payload["messages"][-1]["content"].split("\n", 1)[1]
                )
                content = json.loads(response()["choices"][0]["message"]["content"])
                evidence = customer_packet["evidence"][0]["evidence_id"]
                content["evidence_ids"] = [evidence]
                body = json.dumps(response(content=content), ensure_ascii=False).encode(
                    "utf-8"
                )
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
                corpus_store.add_conversation(
                    corpus, session, "eligible", "", 1, 1, 1700000000
                )
                message = {
                    "local_id": 1,
                    "timestamp": 1700000000,
                    "sender": "客户",
                    "type": "text",
                    "content": "想体验街舞，周六方便",
                    "is_self": False,
                }
                corpus_store.add_evidence_and_facts(
                    corpus,
                    "account",
                    generation,
                    "wxid_customer",
                    message,
                    [
                        {
                            "field": "explicit_need",
                            "value": "想体验街舞",
                            "extractor": "fixture",
                        }
                    ],
                )
                corpus_store.commit_conversation()
                corpus_store.publish_run(corpus, "account")
                connection.close()
                store = AnalysisStore(path)
                store.configure(
                    {
                        "base_url": "http://127.0.0.1:%d" % server.server_port,
                        "model": "deepseek-v4-flash",
                        "max_tokens": 1400,
                        "cache_hit_usd_per_million": "0.0028",
                        "cache_miss_usd_per_million": "0.14",
                        "output_usd_per_million": "0.28",
                    },
                    business_profile().model_dump_json(),
                )
                store.close()
                result = run_analysis(path, "account", "test-key", timeout=2)
                self.assertEqual(result["candidate_count"], 1)
                check = sqlite3.connect(path)
                self.assertEqual(
                    check.execute(
                        "SELECT status FROM analysis_runs WHERE run_id=?",
                        (result["run_id"],),
                    ).fetchone()[0],
                    "published",
                )
                self.assertEqual(
                    check.execute(
                        "SELECT count(*) FROM lead_results WHERE run_id=?",
                        (result["run_id"],),
                    ).fetchone()[0],
                    1,
                )
                check.close()
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(len(captured), 1)


if __name__ == "__main__":
    unittest.main()
