import json
import sqlite3
import time
import uuid
from decimal import Decimal
from typing import Dict, List

from .extractors import minor_indicators


AI_SCHEMA = """
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS ai_settings (
    setting_id INTEGER PRIMARY KEY CHECK(setting_id=1),
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    max_tokens INTEGER NOT NULL,
    cache_hit_usd_per_million TEXT NOT NULL,
    cache_miss_usd_per_million TEXT NOT NULL,
    output_usd_per_million TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS business_profiles (
    profile_id INTEGER PRIMARY KEY CHECK(profile_id=1),
    profile_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_settings (
    setting_id INTEGER PRIMARY KEY CHECK(setting_id=1),
    model TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    question TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY(session_id) REFERENCES agent_sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_turns_session_created
ON agent_turns(session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_account_updated
ON agent_sessions(account_id, updated_at);

CREATE TABLE IF NOT EXISTS saved_analyses (
    saved_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    title TEXT NOT NULL,
    question TEXT NOT NULL,
    task_type TEXT NOT NULL,
    result_json TEXT NOT NULL,
    last_evidence_ts INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    FOREIGN KEY(session_id) REFERENCES agent_sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_saved_analyses_account_updated
ON saved_analyses(account_id, updated_at);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    prompt_sha256 TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    config_snapshot_json TEXT NOT NULL,
    candidate_count INTEGER NOT NULL,
    started_at INTEGER NOT NULL,
    published_at INTEGER,
    failure_code TEXT,
    failure_message TEXT,
    estimated_cost_usd TEXT NOT NULL,
    actual_cost_usd TEXT NOT NULL,
    FOREIGN KEY(corpus_id) REFERENCES corpus_runs(corpus_id)
);

CREATE TABLE IF NOT EXISTS ai_calls (
    call_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    username TEXT NOT NULL,
    status TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    provider_response_id TEXT,
    provider_model TEXT,
    system_fingerprint TEXT,
    finish_reason TEXT,
    prompt_tokens INTEGER,
    cache_hit_tokens INTEGER,
    cache_miss_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    usage_json TEXT,
    estimated_cost_usd TEXT NOT NULL,
    actual_cost_usd TEXT,
    response_sha256 TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at INTEGER NOT NULL,
    FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
);

CREATE TABLE IF NOT EXISTS lead_results (
    run_id TEXT NOT NULL,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    intent_score INTEGER NOT NULL,
    intent_band TEXT NOT NULL,
    recent_contact_ts INTEGER NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    obstacles_json TEXT NOT NULL,
    suggested_action TEXT NOT NULL,
    draft_text TEXT,
    draft_evidence_ids_json TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    PRIMARY KEY(run_id, username),
    FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
);

CREATE TABLE IF NOT EXISTS minor_screenings (
    corpus_id TEXT NOT NULL,
    username TEXT NOT NULL,
    decision TEXT NOT NULL,
    indicators_json TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    checked_at INTEGER NOT NULL,
    PRIMARY KEY(corpus_id, username)
);
"""

CALL_COLUMNS = (
    "call_id",
    "run_id",
    "username",
    "status",
    "request_sha256",
    "provider_response_id",
    "provider_model",
    "system_fingerprint",
    "finish_reason",
    "prompt_tokens",
    "cache_hit_tokens",
    "cache_miss_tokens",
    "completion_tokens",
    "total_tokens",
    "usage_json",
    "estimated_cost_usd",
    "actual_cost_usd",
    "response_sha256",
    "error_code",
    "error_message",
    "created_at",
)


class AnalysisStore:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(AI_SCHEMA)
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(ai_calls)")}
        if "usage_json" not in columns:
            self.conn.execute("ALTER TABLE ai_calls ADD COLUMN usage_json TEXT")
            self.conn.commit()

    def close(self):
        self.conn.close()

    def agent_model(self, default: str) -> str:
        row = self.conn.execute(
            "SELECT model FROM agent_settings WHERE setting_id=1"
        ).fetchone()
        return str(row["model"]) if row is not None else default

    def set_agent_model(self, model: str):
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO agent_settings VALUES(1,?,?)",
                (model, int(time.time())),
            )

    def ensure_agent_session(self, account_id: str, session_id: str = "") -> str:
        if session_id:
            row = self.conn.execute(
                "SELECT account_id FROM agent_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if row is None or str(row["account_id"]) != account_id:
                raise RuntimeError("AGENT_SESSION_INVALID")
            return session_id
        session_id = "agent_" + uuid.uuid4().hex
        now = int(time.time())
        with self.conn:
            self.conn.execute(
                "INSERT INTO agent_sessions VALUES(?,?,?,?,?)",
                (session_id, account_id, "新分析", now, now),
            )
        return session_id

    def agent_context(self, session_id: str, limit: int = 6) -> List[Dict]:
        rows = self.conn.execute(
            """SELECT question,result_json FROM agent_turns WHERE session_id=?
               ORDER BY created_at DESC,rowid DESC LIMIT ?""",
            (session_id, max(1, min(12, int(limit)))),
        ).fetchall()
        context = []
        for row in reversed(rows):
            result = json.loads(row["result_json"])
            context.append(
                {
                    "question": row["question"],
                    "task_type": result.get("task_type"),
                    "result_title": result.get("result_title"),
                    "answer": result.get("answer"),
                    "subject_names": result.get("subject_names") or [],
                    "suggested_followups": result.get("suggested_followups") or [],
                }
            )
        return context

    @staticmethod
    def _compact_agent_result(result: Dict) -> Dict:
        return {
            "schema_version": result.get("schema_version"),
            "task_type": result.get("task_type"),
            "result_title": result.get("result_title"),
            "answer": result.get("answer"),
            "subject_names": result.get("subject_names") or [],
            "suggested_followups": result.get("suggested_followups") or [],
        }

    def _compact_session_turns(self, session_id: str) -> None:
        rows = self.conn.execute(
            "SELECT turn_id,result_json FROM agent_turns WHERE session_id=?", (session_id,)
        ).fetchall()
        for row in rows:
            result = json.loads(row["result_json"])
            compact = self._compact_agent_result(result)
            if result != compact:
                self.conn.execute(
                    "UPDATE agent_turns SET result_json=? WHERE turn_id=?",
                    (json.dumps(compact, ensure_ascii=False, sort_keys=True), row["turn_id"]),
                )

    def _prune_unsaved_sessions(self, account_id: str, keep: int = 100) -> None:
        rows = self.conn.execute(
            """SELECT s.session_id FROM agent_sessions s
               LEFT JOIN saved_analyses a ON a.session_id=s.session_id
               WHERE s.account_id=? AND a.saved_id IS NULL
               ORDER BY s.updated_at DESC,s.session_id DESC LIMIT -1 OFFSET ?""",
            (account_id, max(1, int(keep))),
        ).fetchall()
        for row in rows:
            self.conn.execute("DELETE FROM agent_turns WHERE session_id=?", (row["session_id"],))
            self.conn.execute("DELETE FROM agent_sessions WHERE session_id=?", (row["session_id"],))

    def add_agent_turn(self, session_id: str, question: str, result: Dict):
        now = int(time.time())
        with self.conn:
            self._compact_session_turns(session_id)
            self.conn.execute(
                "INSERT INTO agent_turns VALUES(?,?,?,?,?)",
                (
                    "turn_" + uuid.uuid4().hex,
                    session_id,
                    question,
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
            self.conn.execute(
                "UPDATE agent_sessions SET title=?,updated_at=? WHERE session_id=?",
                (str(result.get("result_title") or question)[:80], now, session_id),
            )
            row = self.conn.execute(
                "SELECT account_id FROM agent_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if row is not None:
                self._prune_unsaved_sessions(str(row["account_id"]))

    def _account_corpus_watermark(self, account_id: str) -> int:
        corpus = self.published_corpus(account_id)
        row = self.conn.execute(
            "SELECT coalesce(max(timestamp),0) AS watermark FROM evidence WHERE corpus_id=?",
            (corpus["corpus_id"],),
        ).fetchone()
        return int(row["watermark"] or 0)

    def account_corpus_watermark(self, account_id: str) -> int:
        return self._account_corpus_watermark(account_id)

    def save_agent_session(self, session_id: str) -> Dict:
        row = self.conn.execute(
            """SELECT s.account_id,s.title,t.question,t.result_json
               FROM agent_sessions s JOIN agent_turns t ON t.session_id=s.session_id
               WHERE s.session_id=? ORDER BY t.created_at DESC,t.rowid DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("AGENT_SESSION_EMPTY")
        result = json.loads(row["result_json"])
        saved_id = "saved_" + uuid.uuid4().hex
        now = int(time.time())
        values = (
            saved_id,
            session_id,
            row["account_id"],
            row["title"],
            row["question"],
            result.get("task_type") or "general_search",
            row["result_json"],
            self._account_corpus_watermark(str(row["account_id"])),
            now,
            now,
        )
        with self.conn:
            self.conn.execute(
                """INSERT INTO saved_analyses VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(session_id) DO UPDATE SET
                   title=excluded.title,question=excluded.question,task_type=excluded.task_type,
                   result_json=excluded.result_json,last_evidence_ts=excluded.last_evidence_ts,
                   updated_at=excluded.updated_at""",
                values,
            )
            self._compact_session_turns(session_id)
        return self.saved_analysis_by_session(session_id)

    def saved_analysis_by_session(self, session_id: str) -> Dict:
        row = self.conn.execute(
            "SELECT * FROM saved_analyses WHERE session_id=?", (session_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("SAVED_ANALYSIS_MISSING")
        result = dict(row)
        result["result"] = json.loads(result.pop("result_json"))
        return result

    def saved_analysis(self, saved_id: str) -> Dict:
        row = self.conn.execute(
            "SELECT * FROM saved_analyses WHERE saved_id=?", (saved_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("SAVED_ANALYSIS_MISSING")
        result = dict(row)
        result["result"] = json.loads(result.pop("result_json"))
        return result

    def list_saved_analyses(self, account_id: str) -> List[Dict]:
        return [
            dict(row)
            for row in self.conn.execute(
                """SELECT saved_id,session_id,title,question,task_type,last_evidence_ts,updated_at
                   FROM saved_analyses WHERE account_id=? ORDER BY updated_at DESC""",
                (account_id,),
            )
        ]

    def update_saved_analysis(self, saved_id: str, result: Dict):
        saved = self.conn.execute(
            "SELECT account_id FROM saved_analyses WHERE saved_id=?", (saved_id,)
        ).fetchone()
        if saved is None:
            raise RuntimeError("SAVED_ANALYSIS_MISSING")
        watermark = self._account_corpus_watermark(str(saved["account_id"]))
        with self.conn:
            cursor = self.conn.execute(
                """UPDATE saved_analyses SET title=?,question=?,task_type=?,result_json=?,
                   last_evidence_ts=?,updated_at=? WHERE saved_id=?""",
                (
                    str(result.get("result_title") or "智能分析")[:80],
                    str(result.get("query") or ""),
                    str(result.get("task_type") or "general_search"),
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                    watermark,
                    int(time.time()),
                    saved_id,
                ),
            )
            if cursor.rowcount == 0:
                raise RuntimeError("SAVED_ANALYSIS_MISSING")

    def delete_saved_analysis(self, saved_id: str, account_id: str) -> None:
        row = self.conn.execute(
            "SELECT session_id FROM saved_analyses WHERE saved_id=? AND account_id=?",
            (saved_id, account_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("SAVED_ANALYSIS_MISSING")
        with self.conn:
            self.conn.execute("DELETE FROM saved_analyses WHERE saved_id=?", (saved_id,))
            self.conn.execute("DELETE FROM agent_turns WHERE session_id=?", (row["session_id"],))
            self.conn.execute("DELETE FROM agent_sessions WHERE session_id=?", (row["session_id"],))

    def configure(self, settings: Dict, profile_json: str):
        now = int(time.time())
        existing_settings = self.conn.execute(
            "SELECT * FROM ai_settings WHERE setting_id=1"
        ).fetchone()
        existing_profile = self.conn.execute(
            "SELECT profile_json FROM business_profiles WHERE profile_id=1"
        ).fetchone()
        normalized_profile = json.dumps(
            json.loads(profile_json),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        setting_keys = (
            "base_url",
            "model",
            "max_tokens",
            "cache_hit_usd_per_million",
            "cache_miss_usd_per_million",
            "output_usd_per_million",
        )
        changed = existing_settings is not None and any(
            str(existing_settings[key]) != str(settings[key]) for key in setting_keys
        )
        if existing_profile is not None:
            changed = changed or json.loads(
                existing_profile["profile_json"]
            ) != json.loads(normalized_profile)
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO ai_settings VALUES(1,?,?,?,?,?,?,?)",
                (
                    settings["base_url"],
                    settings["model"],
                    settings["max_tokens"],
                    settings["cache_hit_usd_per_million"],
                    settings["cache_miss_usd_per_million"],
                    settings["output_usd_per_million"],
                    now,
                ),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO business_profiles VALUES(1,?,?)",
                (normalized_profile, now),
            )
            if changed:
                self.conn.execute(
                    "UPDATE analysis_runs SET status='superseded' WHERE status IN ('published','staging')"
                )
        return changed

    def config(self) -> Dict:
        settings = self.conn.execute(
            "SELECT * FROM ai_settings WHERE setting_id=1"
        ).fetchone()
        profile = self.conn.execute(
            "SELECT * FROM business_profiles WHERE profile_id=1"
        ).fetchone()
        if settings is None or profile is None:
            raise RuntimeError("AI_CONFIGURATION_MISSING")
        result = dict(settings)
        result["business_profile"] = json.loads(profile["profile_json"])
        return result

    def update_business_profile(self, profile_json: str) -> bool:
        now = int(time.time())
        normalized_profile = json.dumps(
            json.loads(profile_json),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self.conn:
            existing = self.conn.execute(
                "SELECT profile_json FROM business_profiles WHERE profile_id=1"
            ).fetchone()
            if existing is None:
                raise RuntimeError("AI_CONFIGURATION_MISSING")
            changed = json.loads(existing["profile_json"]) != json.loads(
                normalized_profile
            )
            self.conn.execute(
                "UPDATE business_profiles SET profile_json=?,updated_at=? WHERE profile_id=1",
                (normalized_profile, now),
            )
            if changed:
                self.conn.execute(
                    "UPDATE analysis_runs SET status='superseded' WHERE status IN ('published','staging')"
                )
        return changed

    def published_corpus(self, account_id: str) -> Dict:
        row = self.conn.execute(
            """SELECT cr.* FROM corpus_runs cr
               JOIN generations g ON g.generation_id=cr.generation_id
               WHERE cr.account_id=? AND cr.status='published' AND g.status='published'
               ORDER BY cr.published_at DESC LIMIT 1""",
            (account_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("PUBLISHED_CORPUS_MISSING")
        return dict(row)

    def candidates(
        self,
        corpus_id: str,
        lead_keywords: List[str],
        minor_data_approved: bool = False,
    ) -> Dict:
        rows = self.conn.execute(
            """SELECT cc.username,cc.display_name,cc.latest_timestamp,
                      count(distinct f.evidence_id) fact_evidence_count
               FROM corpus_conversations cc
               LEFT JOIN extracted_facts f ON f.corpus_id=cc.corpus_id AND f.username=cc.username
               WHERE cc.corpus_id=? AND cc.status='eligible'
               GROUP BY cc.username,cc.display_name,cc.latest_timestamp
               ORDER BY cc.latest_timestamp DESC""",
            (corpus_id,),
        ).fetchall()
        no_fact = {row["username"] for row in rows if not row["fact_evidence_count"]}
        keyword_users = set()
        if no_fact:
            for evidence_row in self.conn.execute(
                """SELECT e.username,e.content FROM evidence e
                   JOIN corpus_evidence ce ON ce.evidence_id=e.evidence_id
                   JOIN corpus_conversations cc ON cc.corpus_id=ce.corpus_id AND cc.username=e.username
                   WHERE ce.corpus_id=? AND cc.status='eligible' AND e.is_self=0""",
                (corpus_id,),
            ):
                if evidence_row["username"] not in no_fact:
                    continue
                content = evidence_row["content"].lower()
                if any(keyword.lower() in content for keyword in lead_keywords):
                    keyword_users.add(evidence_row["username"])
        candidates = []
        privacy_excluded = 0
        for row in rows:
            item = dict(row)
            if item["fact_evidence_count"] or item["username"] in keyword_users:
                evidence = list(
                    self.conn.execute(
                        """SELECT e.evidence_id,e.content FROM evidence e
                       JOIN corpus_evidence ce ON ce.evidence_id=e.evidence_id
                       WHERE ce.corpus_id=? AND e.username=? AND e.is_self=0""",
                        (corpus_id, item["username"]),
                    )
                )
                matches = []
                evidence_ids = []
                for evidence_item in evidence:
                    found = minor_indicators(str(evidence_item["content"] or ""))
                    if found:
                        evidence_ids.append(evidence_item["evidence_id"])
                        matches.extend(
                            {**indicator, "evidence_id": evidence_item["evidence_id"]}
                            for indicator in found
                        )
                decision = (
                    "positive"
                    if any(match["decision"] == "positive" for match in matches)
                    else ("uncertain" if matches else "clear")
                )
                with self.conn:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO minor_screenings VALUES(?,?,?,?,?,?)",
                        (
                            corpus_id,
                            item["username"],
                            decision,
                            json.dumps(matches, ensure_ascii=False, sort_keys=True),
                            json.dumps(sorted(set(evidence_ids)), ensure_ascii=False),
                            int(time.time()),
                        ),
                    )
                if not minor_data_approved and decision != "clear":
                    privacy_excluded += 1
                    continue
                candidates.append(item)
        return {"candidates": candidates, "privacy_excluded": privacy_excluded}

    def packet(
        self,
        corpus_id: str,
        username: str,
        max_evidence: int = 18,
        max_chars: int = 7000,
    ) -> Dict:
        fact_rows = [
            dict(row)
            for row in self.conn.execute(
                """SELECT f.field,f.value,f.evidence_id,f.extractor,e.timestamp
               FROM extracted_facts f JOIN evidence e ON e.evidence_id=f.evidence_id
               WHERE f.corpus_id=? AND f.username=? ORDER BY e.timestamp DESC""",
                (corpus_id, username),
            )
        ]
        latest_by_value = {}
        for row in fact_rows:
            latest_by_value.setdefault((row["field"], row["value"]), row)
        priority = {
            name: index
            for index, name in enumerate(
                (
                    "mobile",
                    "landline",
                    "wechat_id",
                    "explicit_need",
                    "budget_cny",
                    "age",
                    "grade",
                    "available_time",
                    "obstacle",
                    "region",
                )
            )
        }
        selected_facts = sorted(
            latest_by_value.values(),
            key=lambda row: (
                priority.get(row["field"], 99),
                -row["timestamp"],
                row["value"],
            ),
        )[:max_evidence]
        facts = [
            {key: row[key] for key in ("field", "value", "evidence_id", "extractor")}
            for row in selected_facts
        ]
        fact_ids = {item["evidence_id"] for item in facts}
        rows = [
            dict(row)
            for row in self.conn.execute(
                """SELECT e.evidence_id,e.is_self,e.sender,e.timestamp,e.message_type,e.content
               FROM corpus_evidence ce JOIN evidence e ON e.evidence_id=ce.evidence_id
               WHERE ce.corpus_id=? AND e.username=? ORDER BY e.timestamp DESC,e.local_id DESC""",
                (corpus_id, username),
            )
        ]
        ordered = sorted(
            rows,
            key=lambda row: (row["evidence_id"] not in fact_ids, -row["timestamp"]),
        )
        selected = []
        chars = 0
        for item in ordered:
            content = item["content"]
            if item["evidence_id"] in fact_ids and (
                len(selected) >= max_evidence or chars + len(content) > max_chars
            ):
                raise RuntimeError("AI_CONTEXT_TOO_LARGE")
            if selected and (
                len(selected) >= max_evidence or chars + len(content) > max_chars
            ):
                continue
            item["content"] = content
            selected.append(item)
            chars += len(content)
        selected.sort(key=lambda row: row["timestamp"])
        if not fact_ids.issubset({item["evidence_id"] for item in selected}):
            raise RuntimeError("AI_CONTEXT_TOO_LARGE")
        return {"facts": facts, "evidence": selected}

    def create_run(
        self,
        corpus_id: str,
        account_id: str,
        metadata: Dict,
        candidate_count: int,
        estimated_cost: Decimal,
    ) -> str:
        run_id = "analysis_" + uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO analysis_runs VALUES(?,?,?,'staging',?,?,?,?,?,?,?,NULL,NULL,NULL,?,?)",
            (
                run_id,
                corpus_id,
                account_id,
                metadata["model"],
                metadata["prompt_version"],
                metadata["prompt_sha256"],
                metadata["schema_version"],
                json.dumps(
                    metadata["config_snapshot"], ensure_ascii=False, sort_keys=True
                ),
                candidate_count,
                int(time.time()),
                str(estimated_cost),
                "0",
            ),
        )
        self.conn.commit()
        return run_id

    def add_call(self, values: Dict):
        columns = ",".join(CALL_COLUMNS)
        placeholders = ",".join("?" for _ in CALL_COLUMNS)
        self.conn.execute(
            "INSERT INTO ai_calls(%s) VALUES(%s)" % (columns, placeholders),
            tuple(values[key] for key in CALL_COLUMNS),
        )
        self.conn.commit()

    def add_result(
        self, run_id: str, username: str, display_name: str, judgment, facts: List[Dict]
    ):
        self.conn.execute(
            "INSERT INTO lead_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                username,
                display_name,
                judgment.intent_score,
                judgment.intent_band,
                judgment.recent_contact_ts,
                json.dumps(judgment.evidence_ids, ensure_ascii=False),
                json.dumps(judgment.obstacles, ensure_ascii=False),
                judgment.suggested_action,
                judgment.draft_text,
                json.dumps(judgment.draft_evidence_ids, ensure_ascii=False),
                json.dumps(facts, ensure_ascii=False, sort_keys=True),
            ),
        )
        self.conn.commit()

    def add_success(
        self,
        call_values: Dict,
        run_id: str,
        username: str,
        display_name: str,
        judgment,
        facts: List[Dict],
    ):
        call_tuple = tuple(call_values[key] for key in CALL_COLUMNS)
        result_tuple = (
            run_id,
            username,
            display_name,
            judgment.intent_score,
            judgment.intent_band,
            judgment.recent_contact_ts,
            json.dumps(judgment.evidence_ids, ensure_ascii=False),
            json.dumps(judgment.obstacles, ensure_ascii=False),
            judgment.suggested_action,
            judgment.draft_text,
            json.dumps(judgment.draft_evidence_ids, ensure_ascii=False),
            json.dumps(facts, ensure_ascii=False, sort_keys=True),
        )
        with self.conn:
            self.conn.execute(
                "INSERT INTO ai_calls(%s) VALUES(%s)"
                % (",".join(CALL_COLUMNS), ",".join("?" for _ in CALL_COLUMNS)),
                call_tuple,
            )
            self.conn.execute(
                "INSERT INTO lead_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", result_tuple
            )

    def fail_run(self, run_id: str, code: str, message: str):
        actual = sum(
            (
                Decimal(row[0])
                for row in self.conn.execute(
                    "SELECT actual_cost_usd FROM ai_calls WHERE run_id=? AND actual_cost_usd IS NOT NULL",
                    (run_id,),
                )
            ),
            Decimal("0"),
        )
        self.conn.execute(
            "UPDATE analysis_runs SET status='failed',failure_code=?,failure_message=?,actual_cost_usd=? WHERE run_id=?",
            (code, message, str(actual), run_id),
        )
        self.conn.commit()

    def publish_run(self, run_id: str, account_id: str):
        actual = sum(
            (
                Decimal(row[0])
                for row in self.conn.execute(
                    "SELECT actual_cost_usd FROM ai_calls WHERE run_id=? AND actual_cost_usd IS NOT NULL",
                    (run_id,),
                )
            ),
            Decimal("0"),
        )
        with self.conn:
            run = self.conn.execute(
                """SELECT ar.config_snapshot_json FROM analysis_runs ar
                   JOIN corpus_runs cr ON cr.corpus_id=ar.corpus_id
                   JOIN generations g ON g.generation_id=cr.generation_id
                   WHERE ar.run_id=? AND ar.account_id=? AND ar.status='staging'
                     AND cr.account_id=? AND cr.status='published'
                     AND g.account_id=? AND g.status='published'""",
                (run_id, account_id, account_id, account_id),
            ).fetchone()
            if run is None:
                raise RuntimeError("ANALYSIS_SOURCE_SUPERSEDED")
            recorded_config = json.loads(run["config_snapshot_json"])
            recorded_config.pop("selector_version", None)
            current_config = self.config()
            current_config = {
                key: value
                for key, value in current_config.items()
                if key not in ("setting_id", "updated_at")
            }
            if recorded_config != current_config:
                raise RuntimeError("ANALYSIS_CONFIGURATION_SUPERSEDED")
            self.conn.execute(
                "UPDATE analysis_runs SET status='old' WHERE account_id=? AND status='published'",
                (account_id,),
            )
            self.conn.execute(
                "UPDATE analysis_runs SET status='published',published_at=?,actual_cost_usd=? WHERE run_id=?",
                (int(time.time()), str(actual), run_id),
            )
